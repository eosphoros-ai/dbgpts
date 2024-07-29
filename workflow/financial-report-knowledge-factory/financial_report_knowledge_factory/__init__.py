import glob
import json
import logging
import os
import uuid
from abc import ABC
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import pandas as pd
from dbgpt._private.config import Config
from dbgpt._private.pydantic import BaseModel, Field
from dbgpt.core import Chunk, Document
from dbgpt.core.awel import (
    DAG,
    BaseOperator,
    BranchFunc,
    BranchOperator,
    BranchTaskType,
    JoinOperator,
    MapOperator,
)
from dbgpt.core.awel.trigger.http_trigger import HttpTrigger
from dbgpt.datasource.db_conn_info import DBConfig
from dbgpt.datasource.rdbms.base import RDBMSConnector
from dbgpt.datasource.rdbms.conn_sqlite import SQLiteConnector
from dbgpt.rag import ChunkParameters
from dbgpt.rag.chunk_manager import ChunkManager
from dbgpt.rag.embedding import EmbeddingFactory, Embeddings
from dbgpt.rag.index.base import IndexStoreBase
from dbgpt.rag.knowledge.base import Knowledge, KnowledgeType
from dbgpt.storage.vector_store.base import VectorStoreConfig
from dbgpt.util.executor_utils import blocking_func_to_async
from pandas import DataFrame
from tqdm import tqdm

from .extract import FinTableExtractor, FinTableProcessor
from .fin_knowledge import FinReportKnowledge

logger = logging.getLogger(__name__)


class RAGMixin(BaseOperator, ABC):
    _EMBEDDINGS_CACHE_KEY = "__embeddings__"
    _VECTOR_STORE_CACHE_KEY = "__vector_store__"

    async def get_embeddings(
        self,
        embedding_model: Optional[str] = None,
    ) -> Embeddings:
        from dbgpt.configs.model_config import EMBEDDING_MODEL_CONFIG, get_device

        embeddings = await self.current_dag_context.get_from_share_data(
            RAGMixin._EMBEDDINGS_CACHE_KEY
        )
        if embeddings:
            return embeddings

        if not self.dev_mode:
            cfg = Config()
            embedding_factory = EmbeddingFactory.get_instance(self.system_app)
            embeddings = embedding_factory.create(
                model_name=EMBEDDING_MODEL_CONFIG[cfg.EMBEDDING_MODEL]
            )
        else:
            from dbgpt.rag.embedding import DefaultEmbeddingFactory

            embeddings = DefaultEmbeddingFactory.default(
                embedding_model, device=get_device()
            )
        await self.current_dag_context.save_to_share_data(
            RAGMixin._EMBEDDINGS_CACHE_KEY, embeddings
        )
        return embeddings

    async def get_vector_store(
        self, space_name: str, tmp_dir_path: str, embedding_model: Optional[str] = None
    ) -> IndexStoreBase:
        cached_key = f"{RAGMixin._VECTOR_STORE_CACHE_KEY}_{space_name}"

        index_store = await self.current_dag_context.get_from_share_data(cached_key)
        if index_store:
            return index_store
        embeddings = await self.get_embeddings(embedding_model)

        if not self.dev_mode:
            # Run this code in DB-GPT
            from dbgpt.configs.model_config import EMBEDDING_MODEL_CONFIG
            from dbgpt.serve.rag.connector import VectorStoreConnector

            cfg = Config()

            config = VectorStoreConfig(
                name=space_name,
                embedding_fn=embeddings,
            )
            connector = VectorStoreConnector(
                vector_store_type=cfg.VECTOR_STORE_TYPE, vector_store_config=config
            )
            index_store = connector.index_client
        else:
            from dbgpt.storage.vector_store.chroma_store import (
                ChromaStore,
                ChromaVectorConfig,
            )

            index_store = ChromaStore(
                vector_store_config=ChromaVectorConfig(
                    name=space_name,
                    persist_path=os.path.join(tmp_dir_path, space_name),
                    embedding_fn=embeddings,
                ),
            )
        await self.current_dag_context.save_to_share_data(cached_key, index_store)
        return index_store

    async def save_database_profile(
        self, db_name: str, connector: RDBMSConnector, tmp_dir_path: str
    ):
        vector_store_name = db_name + "_profile"

        index_store = await self.get_vector_store(vector_store_name, tmp_dir_path)
        await self.blocking_func_to_async(
            self._save_to_vector_store, connector, index_store
        )

    def _save_to_vector_store(
        self, connector: RDBMSConnector, index_store: IndexStoreBase
    ):
        from dbgpt.rag.assembler.db_schema import DBSchemaAssembler

        db_assembler = DBSchemaAssembler.load_from_connection(
            connector=connector,
            index_store=index_store,
            chunk_parameters=ChunkParameters(chunk_strategy="CHUNK_BY_SIZE"),
        )
        if len(db_assembler.get_chunks()) > 0:
            db_assembler.persist()
        else:
            logger.info("No chunks found in DBSchemaAssembler")


class KnowledgeLoaderOperator(MapOperator[Dict, Dict]):
    """Knowledge Factory Operator."""

    def __init__(
        self,
        datasource: Optional[str] = None,
        knowledge_type: Optional[str] = KnowledgeType.DOCUMENT.name,
        executor: Optional[Executor] = None,
        **kwargs,
    ):
        """Init the query rewrite operator.

        Args:
            knowledge_type: (Optional[KnowledgeType]) The knowledge type.
        """
        super().__init__(**kwargs)
        self._datasource = datasource
        self._knowledge_type = knowledge_type
        self._executor = executor or ThreadPoolExecutor()

    async def map(self, knowledge_request: Dict) -> Dict:
        """Create knowledge from datasource."""
        datasource = self._datasource or knowledge_request.get("datasource")
        knowledge = FinReportKnowledge(file_path=datasource)
        await blocking_func_to_async(self._executor, knowledge.load)
        knowledge_request["knowledge"] = knowledge
        return knowledge_request


class FinTextExtractOperator(MapOperator[Dict, Dict]):
    """Financial Text Extract Operator."""

    def __init__(
        self,
        task_name="extract_text_task",
        chunk_parameters: Optional[ChunkParameters] = None,
        **kwargs,
    ):
        self._chunk_parameters = chunk_parameters or "./tmp"
        super().__init__(task_name=task_name, **kwargs)

    async def map(self, knowledge_request: Dict) -> Dict:
        knowledge = knowledge_request.get("knowledge")
        merged_data = {}
        chunk_manager = ChunkManager(
            knowledge=knowledge, chunk_parameter=self._chunk_parameters
        )
        file_title = knowledge.file_path.rsplit("/", 1)[-1].replace(".pdf", "")
        for i, item in list(knowledge.all_text.items()):
            page = item.get("page")
            inside = item.get("inside")
            if page in merged_data:
                merged_data[page] += " " + inside
            else:
                merged_data[page] = inside
        page_documents = []
        for item in list(merged_data.items()):
            page_documents.append(
                Document(
                    content=item[1], metadata={"page": item[0], "title": file_title}
                )
            )
        chunks: List[Chunk] = chunk_manager.split(page_documents)
        knowledge_request["chunks"] = chunks
        return knowledge_request


class FinTableExtractorOperator(MapOperator[str, DataFrame]):
    """Financial Table Extract Operator."""

    def __init__(
        self,
        task_name="extract_table_task",
        tmp_dir_path: Optional[str] = None,
        executor: Optional[Executor] = None,
        **kwargs,
    ):
        self._tmp_dir_path = tmp_dir_path or "./tmp"
        self._tmp_excel_path = tmp_dir_path
        self._executor = executor or ThreadPoolExecutor()
        super().__init__(task_name=task_name, **kwargs)

    async def map(self, knowledge_request: Dict) -> Dict:
        """Extract knowledge from text."""
        # read txt file
        space = knowledge_request.get("space")
        fin_knowledge = knowledge_request.get("knowledge")
        self._tmp_dir_path = self._tmp_dir_path + f"/{space}/{uuid.uuid4()}"
        self._tmp_excel_path = os.path.expanduser(self._tmp_dir_path + "/output/excel/")
        print("tmp_dir_path: " + self._tmp_dir_path)
        print("tmp_excel_path: " + self._tmp_excel_path)
        # read txt file
        _tmp_txt_path = os.path.join(
            self._tmp_dir_path + "/txt",
            os.path.basename(fin_knowledge.file_path).replace(".pdf", ".txt"),
        )
        await blocking_func_to_async(
            self._executor,
            self._save_all_text,
            fin_knowledge.all_text,
            _tmp_txt_path,
        )
        # self._save_all_text(
        # all_text=fin_knowledge.all_text, tmp_txt_path=_tmp_txt_path
        # )
        file_names = glob.glob(self._tmp_dir_path + "/txt/*")
        file_names = sorted(file_names, reverse=True)
        print("now process files: " + str(file_names))
        # process base col
        results = []
        df1 = pd.DataFrame(
            columns=[
                "文件名",
                "日期",
                "公司名称",
                "股票代码",
                "股票简称",
                "年份",
                "类型",
                "代码",
                "简称",
                "电子信箱",
                "注册地址",
                "办公地址",
                "中文名称",
                "中文简称",
                "外文名称",
                "外文名称缩写",
                "公司网址",
                "法定代表人",
                "职工总数",
                "生产人员",
                "销售人员",
                "技术人员",
                "财务人员",
                "行政人员",
                "本科及以上人员",
                "本科人员",
                "硕士及以上人员",
                "硕士人员",
                "博士及以上人员",
                "博士人员",
                "研发人数",
                "全文",
            ]
        )
        for file_name in file_names:
            txt_extractor = FinTableExtractor(file_name)
            results.append(
                await blocking_func_to_async(
                    self._executor,
                    txt_extractor.extract_base_col,
                )
            )
        df1 = pd.DataFrame(results)
        # excel_directory = os.path.dirname(self._tmp_excel_path)
        if not os.path.exists(self._tmp_excel_path):
            os.makedirs(self._tmp_excel_path)
        df1.to_excel(self._tmp_excel_path + "table_data_base_info.xlsx", index=False)
        results = []
        list1 = [
            "文件名",
            "日期",
            "公司名称",
            "股票代码",
            "股票简称",
            "年份",
            "类型",
            "合并资产负债表",
            "合并利润表",
            "合并利润表",
            "全文",
        ]
        list2 = [
            "货币资金",
            "结算备付金",
            "拆出资金",
            "交易性金融资产",
            "以公允价值计量且其变动计入当期损益的金融资产",
            "衍生金融资产",
            "应收票据",
            "应收账款",
            "应收款项融资",
            "预付款项",
            "应收保费",
            "应收分保账款",
            "应收分保合同准备金",
            "其他应收款",
            "应收利息",
            "应收股利",
            "买入返售金融资产",
            "存货",
            "合同资产",
            "持有待售资产",
            "一年内到期的非流动资产",
            "其他流动资产",
            "流动资产合计",
            "发放贷款和垫款",
            "债权投资",
            "可供出售金融资产",
            "其他债权投资",
            "持有至到期投资",
            "长期应收款",
            "长期股权投资",
            "其他权益工具投资",
            "其他非流动金融资产",
            "投资性房地产",
            "固定资产",
            "在建工程",
            "生产性生物资产",
            "油气资产",
            "使用权资产",
            "无形资产",
            "开发支出",
            "商誉",
            "长期待摊费用",
            "递延所得税资产",
            "其他非流动资产",
            "非流动资产合计",
            "资产总计",
            "短期借款",
            "向中央银行借款",
            "拆入资金",
            "交易性金融负债",
            "以公允价值计量且其变动计入当期损益的金融负债",
            "衍生金融负债",
            "应付票据",
            "应付账款",
            "预收款项",
            "合同负债",
            "卖出回购金融资产款",
            "吸收存款及同业存放",
            "代理买卖证券款",
            "代理承销证券款",
            "应付职工薪酬",
            "应交税费",
            "其他应付款",
            "应付利息",
            "应付股利",
            "应付手续费及佣金",
            "应付分保账款",
            "持有待售负债",
            "一年内到期的非流动负债",
            "其他流动负债",
            "流动负债合计",
            "保险合同准备金",
            "长期借款",
            "应付债券",
            "租赁负债",
            "长期应付款",
            "长期应付职工薪酬",
            "预计负债",
            "递延收益",
            "递延所得税负债",
            "其他非流动负债",
            "非流动负债合计",
            "负债合计",
            "股本",
            "实收资本",
            "其他权益工具",
            "资本公积",
            "库存股",
            "其他综合收益",
            "专项储备",
            "盈余公积",
            "一般风险准备",
            "未分配利润",
            "归属于母公司所有者权益合计",
            "少数股东权益",
            "所有者权益合计",
            "负债和所有者权益总计",
            "营业总收入",
            "营业收入",
            "利息收入",
            "已赚保费",
            "手续费及佣金收入",
            "营业总成本",
            "营业成本",
            "利息支出",
            "手续费及佣金支出",
            "退保金",
            "赔付支出净额",
            "提取保险责任合同准备金净额",
            "保单红利支出",
            "分保费用",
            "税金及附加",
            "销售费用",
            "管理费用",
            "研发费用",
            "财务费用",
            "利息费用",
            "其他收益",
            "投资收益",
            "其中：对联营企业和合营企业的投资收益",
            "以摊余成本计量的金融资产终止确认收益",
            "汇兑收益",
            "净敞口套期收益",
            "公允价值变动收益",
            "信用减值损失",
            "资产减值损失",
            "资产处置收益",
            "营业利润",
            "营业外收入",
            "营业外支出",
            "利润总额",
            "所得税费用",
            "净利润",
            "按经营持续性分类",
            "持续经营净利润",
            "终止经营净利润",
            "按所有权归属分类",
            "归属于母公司所有者的净利润",
            "少数股东损益",
            "其他综合收益的税后净额",
            "归属母公司所有者的其他综合收益的税后净额",
            "不能重分类进损益的其他综合收益",
            "重新计量设定受益计划变动额",
            "权益法下不能转损益的其他综合收益",
            "其他权益工具投资公允价值变动",
            "企业自身信用风险公允价值变动",
            "其他",
            "将重分类进损益的其他综合收益",
            "权益法下可转损益的其他综合收益",
            "其他债权投资公允价值变动",
            "可供出售金融资产公允价值变动损益",
            "金融资产重分类计入其他综合收益的金额",
            "持有至到期投资重分类为可供出售金融资产损益",
            "其他债权投资信用减值准备",
            "现金流量套期储备",
            "外币财务报表折算差额",
            "其他",
            "归属于少数股东的其他综合收益的税后净额",
            "综合收益总额",
            "归属于母公司所有者的综合收益总额",
            "归属于少数股东的综合收益总额",
            "基本每股收益",
            "稀释每股收益",
            "销售商品、提供劳务收到的现金",
            "客户存款和同业存放款项净增加额",
            "向中央银行借款净增加额",
            "向其他金融机构拆入资金净增加额",
            "收到原保险合同保费取得的现金",
            "收到再保业务现金净额",
            "保户储金及投资款净增加额",
            "收取利息、手续费及佣金的现金",
            "拆入资金净增加额",
            "回购业务资金净增加额",
            "代理买卖证券收到的现金净额",
            "收到的税费返还",
            "收到其他与经营活动有关的现金",
            "经营活动现金流入小计",
            "购买商品、接受劳务支付的现金",
            "客户贷款及垫款净增加额",
            "存放中央银行和同业款项净增加额",
            "支付原保险合同赔付款项的现金",
            "拆出资金净增加额",
            "支付利息、手续费及佣金的现金",
            "支付保单红利的现金",
            "支付给职工以及为职工支付的现金",
            "支付的各项税费",
            "支付其他与经营活动有关的现金",
            "经营活动现金流出小计",
            "经营活动产生的现金流量净额",
            "收回投资收到的现金",
            "取得投资收益收到的现金",
            "处置固定资产、无形资产和其他长期资产收回的现金净额",
            "处置子公司及其他营业单位收到的现金净额",
            "收到其他与投资活动有关的现金",
            "投资活动现金流入小计",
            "购建固定资产、无形资产和其他长期资产支付的现金",
            "投资支付的现金",
            "质押贷款净增加额",
            "取得子公司及其他营业单位支付的现金净额",
            "支付其他与投资活动有关的现金",
            "投资活动现金流出小计",
            "投资活动产生的现金流量净额",
            "吸收投资收到的现金",
            "子公司吸收少数股东投资收到的现金",
            "取得借款收到的现金",
            "收到其他与筹资活动有关的现金",
            "筹资活动现金流入小计",
            "偿还债务支付的现金",
            "分配股利、利润或偿付利息支付的现金",
            "子公司支付给少数股东的股利、利润",
            "支付其他与筹资活动有关的现金",
            "筹资活动现金流出小计",
            "筹资活动产生的现金流量净额",
            "汇率变动对现金及现金等价物的影响",
            "现金及现金等价物净增加额",
            "期初现金及现金等价物余额",
            "期末现金及现金等价物余额",
        ]
        all_list = list1 + list2
        df2 = pd.DataFrame(columns=all_list)
        for file_name in file_names:
            txt_extracter = FinTableExtractor(file_name)
            # results.append(txt_extracter.extract_fin_data())
            results.append(
                await blocking_func_to_async(
                    self._executor,
                    txt_extracter.extract_fin_data,
                )
            )
        df2 = pd.DataFrame(results)
        df2.to_excel(self._tmp_excel_path + "/table_data_fin_info.xlsx", index=False)
        # process other col
        results = []
        df3 = pd.DataFrame(
            columns=[
                "文件名",
                "日期",
                "公司名称",
                "股票代码",
                "股票简称",
                "年份",
                "类型",
                "审计意见",
                "关键审计事项",
                "主要会计数据和财务指标",
                "主要销售客户",
                "主要供应商",
                "研发投入",
                "现金流",
                "资产及负债状况",
                "重大资产和股权出售",
                "主要控股参股公司分析",
                "公司未来发展的展望",
                "合并报表范围发生变化的情况说明",
                "聘任、解聘会计师事务所情况",
                "面临退市情况",
                "破产重整相关事项",
                "重大诉讼、仲裁事项",
                "处罚及整改情况",
                "公司及其控股股东、实际控制人的诚信状况",
                "重大关联交易",
                "重大合同及其履行情况",
                "重大环保问题",
                "社会责任情况",
                "公司董事、监事、高级管理人员变动情况",
                "公司员工情况",
                "非标准审计报告的说明",
                "公司控股股东情况",
                "审计报告",
                "全文",
            ]
        )
        for file_name in file_names:
            txt_extracter = FinTableExtractor(file_name)
            # results.append(txt_extracter.extract_other_col())
            results.append(
                await blocking_func_to_async(
                    self._executor,
                    txt_extracter.extract_other_col,
                )
            )
        df3 = pd.DataFrame(results)
        df3.to_excel(self._tmp_excel_path + "/table_data_other_info.xlsx", index=False)
        # check if the three files have the same "文件名" column
        if (
            "文件名" not in df1.columns
            or "文件名" not in df2.columns
            or "文件名" not in df3.columns
        ):
            raise ValueError("One of the Excel files does not have the '文件名' column.")
        # merge to DataFrame
        df = df1.merge(df2, on="文件名", how="inner").merge(df3, on="文件名", how="inner")
        # to excel
        df.to_excel(
            self._tmp_excel_path + "/big_data_old.xlsx", engine="openpyxl", index=False
        )
        df.to_excel(
            self._tmp_excel_path + "/table_data_final.xlsx",
            engine="openpyxl",
            index=False,
        )
        # set txt path
        txt_folder = self._tmp_dir_path + "/txt"
        # txt_folder = _tmp_txt_path
        # get all the txt name
        txt_files = [file for file in os.listdir(txt_folder) if file.endswith(".txt")]
        # process txt
        final_report_df = await blocking_func_to_async(
            self._executor,
            self._process_financial_txt,
            txt_files,
            txt_folder,
        )

        knowledge_request["dataframe"] = final_report_df
        return knowledge_request

    def _process_financial_txt(self, txt_files, txt_folder):
        final_report_df = None
        for txt_file in tqdm(txt_files, desc="Processing financial report"):
            # txt path
            txt_path = os.path.join(txt_folder, txt_file)
            # create txt dir
            folder_name = txt_file.split(".")[0]
            output_folder = os.path.join(self._tmp_excel_path, folder_name)
            os.makedirs(output_folder, exist_ok=True)
            print(txt_path)
            # create TableExtractor process txt file
            processor = FinTableProcessor(txt_path)
            processor.read_file()
            processor.process_text_data()
            processor.process_excel_data()
            processor.process_tables()
            processor.create_excel_files(output_folder)
            final_report_df = pd.read_excel(
                self._tmp_excel_path + "/table_data_final.xlsx"
            )
            print(f"{txt_path} table -> dataframe process finished!")
        return final_report_df

    def _save_all_text(self, all_text, tmp_txt_path):
        directory = os.path.dirname(tmp_txt_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        for key in all_text.keys():
            with open(tmp_txt_path, "a+", encoding="utf-8") as file:
                file.write(json.dumps(all_text[key], ensure_ascii=False) + "\n")
        logger.info(f"save all text to txt {directory} file finished.")


class DatabaseStorageOperator(RAGMixin, MapOperator[Dict, str]):
    """Database Storage Operator."""

    def __init__(
        self,
        db_config: Optional[DBConfig] = None,
        conn_database: Optional[RDBMSConnector] = None,
        tmp_dir_path: Optional[str] = None,
        executor: Optional[Executor] = None,
        **kwargs,
    ):
        """Init the datasource operator."""
        MapOperator.__init__(self, **kwargs)
        self._db_config = db_config
        self._conn_database = conn_database
        self._tmp_dir_path = tmp_dir_path
        self._executor = executor or ThreadPoolExecutor()

    async def map(self, knowledge_request: Dict) -> str:
        """Create datasource."""
        dataframe: DataFrame = knowledge_request.get("dataframe")
        space = knowledge_request.get("space")
        db_name = f"{space}_fin_report"

        tmp_dir_path = self._tmp_dir_path or "./tmp"
        sqlite_path = os.path.join(tmp_dir_path, space, f"{db_name}.db")

        self._conn_database = self._conn_database or SQLiteConnector.from_file_path(
            sqlite_path
        )
        self._db_config = DBConfig(
            db_name=db_name,
            db_type=self._conn_database.db_type,
            file_path=sqlite_path,
        )
        if self._conn_database:
            dataframe.to_sql(
                "fin_report",
                self._conn_database._engine,
                if_exists="append",
                index=False,
            )
        if not self.dev_mode:
            from dbgpt.datasource.manages import ConnectorManager

            connector_manager = ConnectorManager.get_instance(self.system_app)
            db_list = [item["db_name"] for item in connector_manager.get_db_list()]
            if self._db_config.db_name not in db_list:
                connector_manager.add_db(self._db_config)
        else:
            await self.save_database_profile(db_name, self._conn_database, tmp_dir_path)
        return sqlite_path


class VectorStorageOperator(RAGMixin, MapOperator[Dict, List[Chunk]]):
    """Vector Storage Operator."""

    def __init__(
        self,
        tmp_dir_path: Optional[str] = None,
        index_store: Optional[IndexStoreBase] = None,
        embeddings: Optional[Embeddings] = None,
        max_chunks_once_load: Optional[int] = None,
        **kwargs,
    ):
        """Init the datasource operator."""
        MapOperator.__init__(self, **kwargs)
        self._tmp_dir_path = tmp_dir_path
        self._index_store = index_store
        self._embeddings = embeddings
        self._max_chunks_once_load = max_chunks_once_load

    async def map(self, storage_request: Dict) -> List[Chunk]:
        """Persist chunks in vector db."""
        chunks = storage_request.get("chunks")
        vector_store = await self.get_vector_store(
            storage_request["space"],
            self._tmp_dir_path,
            storage_request["embedding_model"],
        )
        max_chunks_once_load = self._max_chunks_once_load or int(
            os.getenv("KNOWLEDGE_MAX_CHUNKS_ONCE_LOAD", 10)
        )
        await vector_store.aload_document_with_limit(chunks, max_chunks_once_load)
        return chunks


class KnowledgeExtractBranchOperator(BranchOperator[Knowledge, Knowledge]):
    """The Knowledge Extract branch operator."""

    def __init__(
        self,
        text_task_name: Optional[str] = None,
        table_task_name: Optional[str] = None,
        **kwargs,
    ):
        """Create the intent detection branch operator."""
        super().__init__(**kwargs)
        self._text_task_name = text_task_name
        self._table_task_name = table_task_name

    async def branches(
        self,
    ) -> Dict[BranchFunc[Knowledge], BranchTaskType]:
        """Branch the intent detection result to different tasks."""
        download_task_names = set(task.node_name for task in self.downstream)  # noqa
        branch_func_map = {}

        async def check_extract_table(r: Knowledge) -> bool:
            # If check table is true, we will run extract table task.
            return True

        async def check_extract_text(r: Knowledge) -> bool:
            # If check text is true, we will run extract text task.
            return True

        branch_func_map[check_extract_table] = self._table_task_name
        branch_func_map[check_extract_text] = self._text_task_name
        return branch_func_map  # type: ignore


class FinKnowledgeJoinOperator(JoinOperator[List[str]]):
    """Evaluator for retriever."""

    def __init__(
        self,
        **kwargs,
    ):
        """Create a new RetrieverEvaluatorOperator."""
        super().__init__(combine_function=self._join, **kwargs)

    async def _join(
        self,
        db_name: str,
        chunks: List[Chunk],
    ) -> Tuple[List[Chunk], str]:
        """Join results.

        Args:
            db_name: The list of db names.
            chunks: The list of chunks.
        """

        logger.info(f"async persist vector store success {len(chunks)} chunks.")
        logger.info(f"async persist database {db_name} success")
        return chunks, db_name


class TriggerReqBody(BaseModel):
    space: str | None = Field(None, description="space")
    file_path: str | None = Field(None, description="file path")
    embedding_model: str | None = Field(None, description="embedding model path")


class RequestHandleOperator(MapOperator[TriggerReqBody, Dict]):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def map(self, input_value: TriggerReqBody) -> Dict:
        if isinstance(input_value, dict):
            input_value = TriggerReqBody(**input_value)
        print(f"Receive input value: {input_value}")
        return {
            "space": input_value.space,
            "datasource": input_value.file_path,
            "embedding_model": input_value.embedding_model,
        }


with DAG(
    "fin_report_knowledge_processing_task",
    tags={"knowledge_factory_domain_type": "FinancialReport"},
) as dag:
    dev_mode = dag.dev_mode

    trigger = HttpTrigger(
        "/dbgpts/fin_knowledge_process", methods="POST", request_body=TriggerReqBody
    )
    request_task = RequestHandleOperator()

    if dev_mode:
        tmp_dir_path = f"./output"
    else:
        # Run this code in DB-GPT
        from dbgpt.configs.model_config import PILOT_PATH

        tmp_dir_path = f"{PILOT_PATH}/data/"
    knowledge_factory = KnowledgeLoaderOperator()
    extract_branch = KnowledgeExtractBranchOperator(
        text_task_name="extract_text_task", table_task_name="extract_table_task"
    )
    chunk_parameters = ChunkParameters(chunk_strategy="Automatic")
    extract_text_task = FinTextExtractOperator(chunk_parameters=chunk_parameters)
    vector_storage = VectorStorageOperator(tmp_dir_path=tmp_dir_path)
    extractor_table_task = FinTableExtractorOperator(tmp_dir_path=tmp_dir_path)
    database_storage = DatabaseStorageOperator(
        tmp_dir_path=tmp_dir_path,
    )
    result_join_task = FinKnowledgeJoinOperator()
    trigger >> request_task >> knowledge_factory >> extract_branch
    extract_branch >> extract_text_task >> vector_storage >> result_join_task
    extract_branch >> extractor_table_task >> database_storage >> result_join_task

if __name__ == "__main__":
    pass
