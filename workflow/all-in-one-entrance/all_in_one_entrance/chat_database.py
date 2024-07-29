import json

from dbgpt.core import (
    ChatPromptTemplate,
    HumanPromptTemplate,
    ModelMessage,
    ModelOutput,
    ModelRequest,
    SQLOutputParser,
    SystemPromptTemplate,
)
from dbgpt.core.awel import MapOperator
from dbgpt.experimental.intent.base import IntentDetectionResponse

_DEFAULT_TEMPLATE_EN = """You are a database expert. 
Please answer the user's question based on the database selected by the user and some of the available table structure definitions of the database.
Database name:
     {db_name}
Table structure definition:
     {table_info}

Constraint:
    1.Please understand the user's intention based on the user's question, and use the given table structure definition to create a grammatically correct {dialect} sql. If sql is not required, answer the user's question directly.. 
    2.Always limit the query to a maximum of {top_k} results unless the user specifies in the question the specific number of rows of data he wishes to obtain.
    3.You can only use the tables provided in the table structure information to generate sql. If you cannot generate sql based on the provided table structure, please say: "The table structure information provided is not enough to generate sql queries." It is prohibited to fabricate information at will.
    4.Please be careful not to mistake the relationship between tables and columns when generating SQL.
    5.Please check the correctness of the SQL and ensure that the query performance is optimized under correct conditions.
    6.Please choose the best one from the display methods given below for data rendering, and put the type name into the name parameter value that returns the required format. If you cannot find the most suitable one, use 'Table' as the display method. , the available data display methods are as follows: {display_type}

User Question:
    {user_input}
Please think step by step and respond according to the following JSON format:
    {response}
Ensure the response is correct json and can be parsed by Python json.loads.

"""

_DEFAULT_TEMPLATE_ZH = """你是一个数据库专家.
请根据用户选择的数据库和该库的部分可用表结构定义来回答用户问题.
数据库名:
    {db_name}
表结构定义:
    {table_info}

约束:
    1. 请根据用户问题理解用户意图，使用给出表结构定义创建一个语法正确的 {dialect} sql，如果不需要sql，则直接回答用户问题。
    2. 除非用户在问题中指定了他希望获得的具体数据行数，否则始终将查询限制为最多 {top_k} 个结果。
    3. 只能使用表结构信息中提供的表来生成 sql，如果无法根据提供的表结构中生成 sql ，请说：“提供的表结构信息不足以生成 sql 查询。” 禁止随意捏造信息。
    4. 请注意生成SQL时不要弄错表和列的关系
    5. 请检查SQL的正确性，并保证正确的情况下优化查询性能
    6.请从如下给出的展示方式种选择最优的一种用以进行数据渲染，将类型名称放入返回要求格式的name参数值种，如果找不到最合适的则使用'Table'作为展示方式，可用数据展示方式如下: {display_type}
用户问题:
    {user_input}
请一步步思考并按照以下JSON格式回复：
      {response}
确保返回正确的json并且可以被Python json.loads方法解析.

"""

_SHARE_DATA_DATABASE_NAME_KEY = "__database_name__"


class ChatDatabaseOperator(MapOperator[ModelRequest, ModelRequest]):
    def __init__(self, task_name="chat_database", **kwargs):
        super().__init__(task_name=task_name, **kwargs)

    async def map(self, input_value: ModelRequest) -> ModelRequest:
        from dbgpt._private.config import Config
        from dbgpt.rag.summary.db_summary_client import DBSummaryClient
        from dbgpt.vis.tags.vis_chart import default_chart_type_prompt

        cfg = Config()

        ic: IntentDetectionResponse = input_value.context.extra.get("intent_detection")
        db_name = ic.slots.get("database_name")
        if not db_name:
            raise ValueError("Database name is required.")

        await self.current_dag_context.save_to_share_data(
            _SHARE_DATA_DATABASE_NAME_KEY, db_name
        )

        database = cfg.local_db_manager.get_connector(db_name)
        client = DBSummaryClient(system_app=self.system_app)

        user_input = ic.user_input
        table_infos = await self.blocking_func_to_async(
            client.get_db_summary, db_name, user_input, 5
        )

        input_values = {
            "db_name": db_name,
            "user_input": user_input,
            "top_k": 5,
            "dialect": database.dialect,
            "table_info": table_infos,
            "display_type": default_chart_type_prompt(),
        }

        response_format_simple = {
            "thoughts": "thoughts summary to say to user",
            "sql": "SQL Query to run",
            "display_type": "Data display method",
        }

        user_language = self.system_app.config.get_current_lang(default="en")
        prompt_template = (
            _DEFAULT_TEMPLATE_EN if user_language == "en" else _DEFAULT_TEMPLATE_ZH
        )
        prompt = ChatPromptTemplate(
            messages=[
                SystemPromptTemplate.from_template(
                    prompt_template,
                    response_format=json.dumps(
                        response_format_simple, ensure_ascii=False, indent=4
                    ),
                ),
                HumanPromptTemplate.from_template("{user_input}"),
            ]
        )

        messages = prompt.format_messages(**input_values)
        model_messages = ModelMessage.from_base_messages(messages)
        request = input_value.copy()
        request.messages = model_messages
        return request


class ChatDatabaseOutputParserOperator(SQLOutputParser):
    async def map(self, input_value: ModelOutput) -> dict:
        return self.parse_model_nostream_resp(input_value, "#########")


class ChatDatabaseChartOperator(MapOperator[dict, str]):
    def __init__(self, task_name="chat_database_parser", **kwargs):
        super().__init__(task_name=task_name, **kwargs)

    async def map(self, input_value: dict) -> str:
        from dbgpt._private.config import Config
        from dbgpt.datasource import RDBMSConnector
        from dbgpt.vis.tags.vis_chart import VisChart

        db_name = await self.current_dag_context.get_from_share_data(
            _SHARE_DATA_DATABASE_NAME_KEY
        )
        vis = VisChart()
        cfg = Config()
        database: RDBMSConnector = cfg.local_db_manager.get_connector(db_name)
        sql = input_value.get("sql")
        data_df = await self.blocking_func_to_async(database.run_to_df, sql)
        view = await vis.display(chart=input_value, data_df=data_df)
        return view
