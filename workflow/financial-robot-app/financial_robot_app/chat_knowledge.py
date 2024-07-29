"""ChatKnowledgeOperator."""

import os
from typing import Optional

from dbgpt._private.config import Config
from dbgpt.core import (
    ChatPromptTemplate,
    HumanPromptTemplate,
    ModelMessage,
    ModelRequest,
)
from dbgpt.core.awel import MapOperator
from dbgpt.datasource import RDBMSConnector
from dbgpt.rag.embedding.embedding_factory import RerankEmbeddingFactory
from dbgpt.rag.retriever.rerank import RerankEmbeddingsRanker
from dbgpt.storage.vector_store.filters import MetadataFilter, MetadataFilters

from .common import FinConfigMixin
from .intent import FinReportIntent

_DEFAULT_TEMPLATE_ZH = """你是专业的金融财报分析专家，基于以下给出的已知信息, 准守规范约束，专业、简要回答用户的金融问题.
规范约束:
    
    1.作为一个金融财报分析专家，你只能回答所有与金融领域相关的问题.
    2.如果已知信息包含的图片、链接、表格、代码块等特殊markdown标签格式的信息，确保在答案中包含原文这些
    图片、链接、表格和代码标签，不要丢弃不要修改，如:图片格式：![image.png](xxx), 链接格式:
    [xxx](xxx), 表格格式:|xxx|xxx|xxx|, 代码格式:```xxx```.
    3.回答的时候最好按照1.2.3.点进行总结, 并以markdwon格式显示。
    已知内容: 
    {context}
    问题:
    {question},请使用和用户相同的语言进行回答.
"""

_DEFAULT_TEMPLATE_EN = """You are Professional Financial Expert. Based on the known information below, provide users with 
professional and concise answers to their questions.
    constraints:
    1.Ensure to include original markdown formatting elements such as images, links, 
    tables, or code blocks without alteration in the response if they are present 
    in the provided information.For example, image format should be ![image.png](xxx), 
    link format [xxx](xxx), 
    table format should be represented with |xxx|xxx|xxx|, and code format with xxx.
    2.If the information available in the knowledge base is insufficient to answer the 
    question, state clearly: "The content provided in the knowledge base is not enough 
    to answer this question," and avoid making up answers.
    3.When responding, it is best to summarize the points in the order of 1, 2, 3.
        known information: 
        {context}
        question:
        {question},when answering, use the same language as the "user".
"""


class ChatKnowledgeOperator(FinConfigMixin, MapOperator[ModelRequest, ModelRequest]):
    """ChatKnowledgeOperator."""

    def __init__(
        self,
        task_name="chat_knowledge",
        intent: Optional[FinReportIntent] = None,
        **kwargs,
    ):
        """ChatKnowledgeOperator."""
        self._intent = intent
        self._cfg = Config()
        MapOperator.__init__(self, task_name=task_name, **kwargs)

    async def map(self, input_value: ModelRequest) -> ModelRequest:
        """Map function for ChatKnowledgeOperator."""
        from dbgpt.rag.retriever.embedding import EmbeddingRetriever

        (
            db_name,
            space_name,
            tmp_dir_path,
            embedding_model,
        ) = await self._get_chat_config()

        user_input = input_value.messages[-1].content
        user_inputs = [user_input]
        intent: FinReportIntent = input_value.context.extra.get("intent")

        # Cached connection
        db_conn: RDBMSConnector = await self.get_connector(
            space_name, db_name, tmp_dir_path
        )

        (
            hit_document_title,
            new_user_input,
            metadata_filter,
        ) = await self.blocking_func_to_async(
            self.get_fuzzy_match, user_input, intent, space_name, db_conn
        )
        if hit_document_title:
            user_inputs.append(new_user_input)

        if not space_name:
            raise ValueError("Knowledge name is required.")

        index_store = await self.get_vector_store(
            space_name, tmp_dir_path, embedding_model
        )

        reranker = None
        retriever_top_k = self._cfg.KNOWLEDGE_SEARCH_TOP_SIZE
        if not self.dev_mode and self._cfg.RERANK_MODEL:
            # Dev mode not support reranker
            rerank_embeddings = RerankEmbeddingFactory.get_instance(
                self._cfg.SYSTEM_APP
            ).create()
            reranker = RerankEmbeddingsRanker(
                rerank_embeddings, topk=self._cfg.RERANK_TOP_K
            )
            if retriever_top_k < self._cfg.RERANK_TOP_K or retriever_top_k < 20:
                # We use reranker, so if the top_k is less than 20,
                # we need to set it to 20
                retriever_top_k = max(self._cfg.RERANK_TOP_K, 20)

        embedding_retriever = EmbeddingRetriever(
            top_k=retriever_top_k,
            index_store=index_store,
            rerank=reranker,
        )
        chunks = []
        for query_text in user_inputs:
            if metadata_filter:
                chunks.extend(
                    await embedding_retriever.aretrieve_with_scores(
                        query_text,
                        0.3,
                        MetadataFilters(filters=[metadata_filter]),
                    )
                )
            else:
                chunks.extend(
                    await embedding_retriever.aretrieve_with_scores(
                        query_text,
                        0.3,
                    )
                )
        contents = [doc.content for doc in chunks]
        context = "\n".join(set(contents))

        input_values = {"context": context, "question": user_input}

        user_language = self.system_app.config.get_current_lang(default="en")
        prompt_template = (
            _DEFAULT_TEMPLATE_EN if user_language == "en" else _DEFAULT_TEMPLATE_ZH
        )
        prompt = ChatPromptTemplate(
            messages=[
                HumanPromptTemplate.from_template(prompt_template),
                HumanPromptTemplate.from_template("{question}"),
            ]
        )
        messages = prompt.format_messages(**input_values)
        model_messages = ModelMessage.from_base_messages(messages)
        request = input_value.copy()
        request.messages = model_messages
        return request

    def get_fuzzy_match(self, user_input, intent, space, db_conn: RDBMSConnector):
        """fuzzy match for user input and get label filter"""
        if self.dev_mode:
            company_df = db_conn.run_to_df(f"select 文件名 from fin_report")
            document_titles = [
                item[0] for item in company_df.values.tolist() if item is not None
            ]
        else:
            from dbgpt.serve.rag.service.service import Service

            knowledge_service = Service.get_instance(self._cfg.SYSTEM_APP)
            document_list = knowledge_service.get_document_list(
                {"space": space}, page=1, page_size=1000
            )
            document_titles = [document.doc_name for document in document_list.items]

        # Keep file name, not full path
        file_names = [
            os.path.splitext(os.path.basename(path))[0] for path in document_titles
        ]

        if intent and intent.company and intent.company != "":
            from fuzzywuzzy import process

            best_match, confidence = process.extractOne(intent.company, file_names)
            hit_title = best_match or intent.company
            user_input = intent.intent
            filter = MetadataFilter(key="title", value=hit_title.replace(".pdf", ""))
            return hit_title, user_input, filter
        return None, user_input, None
