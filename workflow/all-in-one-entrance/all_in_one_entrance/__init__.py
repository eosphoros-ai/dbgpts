"""all-in-one-entrance flow package"""

import json
from typing import List, Optional

from dbgpt.core import (
    BaseMessage,
    InMemoryStorage,
    ModelMessage,
    ModelMessageRoleType,
    ModelOutput,
    ModelRequest,
    StorageConversation,
    StorageInterface,
)
from dbgpt.core.awel import DAG, JoinOperator, MapOperator, is_empty_data
from dbgpt.core.awel.flow import IOField, OperatorCategory, ViewMetadata
from dbgpt.core.awel.trigger.http_trigger import (
    CommonLLMHttpRequestBody,
    CommonLLMHttpTrigger,
)
from dbgpt.core.interface.operators.llm_operator import BaseLLM
from dbgpt.core.operators import BaseConversationOperator
from dbgpt.experimental.intent.base import IntentDetectionResponse
from dbgpt.experimental.intent.operators import (
    IntentDetectionBranchOperator,
    IntentDetectionOperator,
)
from dbgpt.model.operators import LLMOperator, StreamingLLMOperator

from .chat_database import (
    ChatDatabaseChartOperator,
    ChatDatabaseOperator,
    ChatDatabaseOutputParserOperator,
)
from .chat_knowledge import ChatKnowledgeOperator

_DEFAULT_INTENT_DEFINITIONS = """**********************************
intent: Chat With Database
task_name: chat_database
description_en: Used for database conversation, all conversations related to data queries, SQL generation, etc. will be matched to database conversations
description_zh: 用于数据库对话的意图，所有与数据查询SQL生成等相关的对话都会匹配到数据库对话
slots: 
- Database Name(database_name): The name of the database
**********************************
intent: Chat With Knowledge
task_name: chat_knowledge
description_zh: 用于知识库对话的意图, 当你无法直接回答用户问题或者不知道如何回答时，可以将用户的问题匹配到知识库对话
description_en: Used for knowledge base conversation, when you can't answer the user's question directly or don't know how to answer, you can match the user's question to the knowledge base conversation
slots: 
- Knowledge Name(knowledge_name): The name of the knowledge base
**********************************
**********************************
intent: Normal Chat
task_name: chat_normal
description_en: Chat with user normally, no need to fill any slots, when no other intent can be matched, it will be matched to normal chat intent
description_zh: 与用户正常聊天，无需填充任何槽位，当无法匹配到其他意图时，会匹配到正常聊天意图
slots: no need to fill any slots
"""

EXAMPLES = [
    {
        "user": "The weather of Beijing today?",
        "assistant": {
            "intent": "Normal Chat",
            "thought": "User asked about the weather in Beijing today, matched to the Normal Chat intent, no need to fill any slots, the language of user question is english, i generate `user_input` in english",
            "task_name": "chat_normal",
            "slots": {},
            "ask_user": "",
            "user_input": "The weather of Beijing today?",
        },
    },
    {
        "user": "Write a SQL to query the names, majors and grades of all students, in descending order.",
        "assistant": {
            "intent": "Chat With Database",
            "thought": "User asked to write a SQL to query the names, majors and grades of all students, in descending order, matched to the Chat With Database intent, need to fill the Database Name slot, the language of user question is english, i generate `ask_user` in english",
            "task_name": "chat_database",
            "slots": {
                "database_name": "",
            },
            "ask_user": "Please provide the name of the database.",
            "user_input": "Write a SQL to query the names, majors and grades of all students, in descending order.",
        },
    },
    {
        "user": "My database is case_1_student_manager.",
        "assistant": {
            "intent": "Chat With Database",
            "thought": "According to the user's input and historical dialogue information, the user provided the database name case_1_student_manager, matched to the Chat With Database intent, not need to fill any slots, the language of user question is english, i generate `user_input` in english",
            "task_name": "chat_database",
            "slots": {
                "database_name": "case_1_student_manager",
            },
            "ask_user": "",
            "user_input": "Database name is case_1_student_manager, please write a SQL to query the names, majors and grades of all students, in descending order.",
        },
    },
    {
        "user": "我的数据是 case_1_student_manager, 请写一个SQL查询所有学生的姓名，专业和成绩，按降序排列。",
        "assistant": {
            "intent": "Chat With Database",
            "thought": "User provided the database name case_1_student_manager, matched to the Chat With Database intent, not need to fill any slots, the language of user question is chinese, i generate `user_input` in chinese",
            "task_name": "chat_database",
            "slots": {
                "database_name": "case_1_student_manager",
            },
            "ask_user": "",
            "user_input": "数据库是 case_1_student_manager, 请写一个SQL查询所有学生的姓名，专业和成绩，按降序排列。",
        },
    },
    {
        "user": "What is the AWEL?",
        "assistant": {
            "intent": "Chat With Knowledge",
            "thought": "User asked what is the AWEL, can't answer this question directly, matched to the Chat With Knowledge intent, need to fill the Knowledge Name slot, the language of user question is english, i generate `ask_user` in english",
            "task_name": "chat_knowledge",
            "slots": {
                "knowledge_name": "",
            },
            "ask_user": "I'm sorry, I can't answer this question directly. please provide the name of the knowledge base.",
            "user_input": "What is the AWEL?",
        },
    },
]
EXAMPLES_STRING = ""

for e in EXAMPLES:
    example_out = json.dumps(e["assistant"], ensure_ascii=False)
    EXAMPLES_STRING += f"user: {e['user']}\nassistant: ```json\n{example_out}\n```\n\n"


class RequestHandleOperator(
    BaseConversationOperator, MapOperator[CommonLLMHttpRequestBody, ModelRequest]
):
    def __init__(self, storage: StorageInterface, **kwargs):
        MapOperator.__init__(self, **kwargs)
        BaseConversationOperator.__init__(
            self, storage=storage, message_storage=storage
        )

    async def map(self, input_value: CommonLLMHttpRequestBody) -> ModelRequest:
        # Create a new storage conversation, this will load the conversation from
        # storage, so we must do this async
        storage_conv: StorageConversation = await self.blocking_func_to_async(
            StorageConversation,
            conv_uid=input_value.conv_uid,
            chat_mode=input_value.chat_mode,
            user_name=input_value.user_name,
            sys_code=input_value.sys_code,
            conv_storage=self.storage,
            message_storage=self.message_storage,
            param_type="",
            param_value=input_value.chat_param,
        )
        # Get history messages from storage
        history_messages: List[BaseMessage] = storage_conv.get_history_message()
        messages = ModelMessage.from_base_messages(history_messages)
        messages.append(ModelMessage.build_human_message(input_value.messages))

        # Save the storage conversation to share data, for the child operators
        await self.current_dag_context.save_to_share_data(
            self.SHARE_DATA_KEY_STORAGE_CONVERSATION, storage_conv
        )
        await self.current_dag_context.save_to_share_data(
            self.SHARE_DATA_KEY_MODEL_REQUEST_CONTEXT, input_value
        )
        return ModelRequest.build_request(input_value.model, messages)


class MyIntentDetectionOperator(BaseConversationOperator, IntentDetectionOperator):
    def __init__(
        self,
        intent_definitions: str,
        examples: Optional[str] = None,
        history_count: int = 10,
        **kwargs,
    ):
        BaseConversationOperator.__init__(self, **kwargs)
        IntentDetectionOperator.__init__(
            self, intent_definitions=intent_definitions, examples=examples, **kwargs
        )
        self.history_count = history_count

    def parse_messages(self, request: ModelRequest) -> List[ModelMessage]:
        messages = request.get_messages()
        history_messages = messages[:-1]
        return history_messages[-self.history_count :] + [messages[-1]]

    async def map(self, input_value: ModelRequest) -> ModelRequest:
        request = await super().map(input_value)
        await self.start_new_round_conv(request.get_messages())
        return input_value

    async def start_new_round_conv(self, messages: List[ModelMessage]) -> None:
        lass_user_message = None
        for message in messages[::-1]:
            if message.role == ModelMessageRoleType.HUMAN:
                lass_user_message = message.content
                break
        if not lass_user_message:
            raise ValueError("No user message")
        storage_conv: Optional[
            StorageConversation
        ] = await self.get_storage_conversation()
        if not storage_conv:
            return
        # Start new round
        storage_conv.start_new_round()
        storage_conv.add_user_message(lass_user_message)

    async def after_dag_end(self, event_loop_task_id: int):
        # Save the storage conversation to storage after the whole DAG finished
        storage_conv: Optional[
            StorageConversation
        ] = await self.get_storage_conversation()

        if not storage_conv:
            return
        model_output: Optional[
            ModelOutput
        ] = await self.current_dag_context.get_from_share_data(
            BaseLLM.SHARE_DATA_KEY_MODEL_OUTPUT
        )
        if model_output:
            # Save model output message to storage
            storage_conv.add_ai_message(model_output.text)
            # End current conversation round and flush to storage
            storage_conv.end_current_round()


class ChatNormalOperator(MapOperator[ModelRequest, ModelRequest]):
    def __init__(self, task_name="chat_normal", **kwargs):
        super().__init__(task_name=task_name, **kwargs)

    async def map(self, input_value: ModelRequest) -> ModelRequest:
        return input_value


class EndOperator(BaseLLM, MapOperator[ModelRequest, str]):
    def __init__(self, task_name="end", **kwargs):
        MapOperator.__init__(self, task_name=task_name, **kwargs)

    async def map(self, input_value: ModelRequest) -> str:
        ic: IntentDetectionResponse = input_value.context.extra.get("intent_detection")
        await self.save_model_output(
            self.current_dag_context, ModelOutput(text=ic.ask_user, error_code=0)
        )
        return ic.ask_user


def join_func(*args):
    for arg in args:
        if not is_empty_data(arg):
            return arg
    return None


class FinalJoinOperator(JoinOperator[str]):
    streaming_operator = True
    metadata = ViewMetadata(
        label="All In One Entrance Output Join Operator",
        name="final_join_operator",
        category=OperatorCategory.COMMON,
        description="A example operator to say hello to someone.",
        parameters=[],
        inputs=[],
        outputs=[
            IOField.build_from(
                "Output value", "value", str, description="The output value"
            )
        ],
    )

    def __init__(self, **kwargs):
        super().__init__(join_func, can_skip_in_branch=False, **kwargs)


with DAG("dbgpts_all_in_one_entrance_intent_detection_dag") as dag:
    trigger = CommonLLMHttpTrigger(
        "/dbgpts/all-in-one-entrance",
        methods="POST",
        streaming_predict_func=lambda x: x.stream,
    )
    storage = InMemoryStorage()
    request_handle_task = RequestHandleOperator(storage)
    intent_task = MyIntentDetectionOperator(
        intent_definitions=_DEFAULT_INTENT_DEFINITIONS,
        examples=EXAMPLES_STRING,
    )
    intent_detection_task = IntentDetectionBranchOperator(end_task_name="end")
    chat_normal_task = ChatNormalOperator()
    chat_database_task = ChatDatabaseOperator()
    sql_parse_task = ChatDatabaseOutputParserOperator()
    sql_chart_task = ChatDatabaseChartOperator()

    chat_knowledge_task = ChatKnowledgeOperator()
    end_task = EndOperator()
    join_task = FinalJoinOperator()

    trigger >> request_handle_task >> intent_task >> intent_detection_task

    # Chat normal task
    (intent_detection_task >> chat_normal_task >> StreamingLLMOperator() >> join_task)
    # Chat database task
    (
        intent_detection_task
        >> chat_database_task
        >> LLMOperator()
        >> sql_parse_task
        >> sql_chart_task
        >> join_task
    )

    # Chat knowledge task
    (
        intent_detection_task
        >> chat_knowledge_task
        >> StreamingLLMOperator()
        >> join_task
    )
    # End task, ask user for more information
    intent_detection_task >> end_task >> join_task
