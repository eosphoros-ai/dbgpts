"""FinReportJoinOperator."""

import os
from typing import List, Optional

from dbgpt.core import (
    BaseMessage,
    InMemoryStorage,
    LLMClient,
    ModelMessage,
    ModelRequest,
    StorageConversation,
    StorageInterface,
)
from dbgpt.core.awel import (
    DAG,
    CommonLLMHttpRequestBody,
    JoinOperator,
    MapOperator,
    is_empty_data,
)
from dbgpt.core.awel.flow import IOField, OperatorCategory, ViewMetadata
from dbgpt.core.awel.trigger.http_trigger import CommonLLMHttpTrigger
from dbgpt.core.interface.operators.message_operator import BaseConversationOperator
from dbgpt.model.operators import LLMOperator, StreamingLLMOperator

from .chat_database import ChatDatabaseChartOperator, ChatDatabaseOutputParserOperator
from .chat_indicator import ChatIndicatorOperator
from .chat_knowledge import ChatKnowledgeOperator
from .chat_normal import ChatNormalOperator
from .classifier import QuestionClassifierBranchOperator, QuestionClassifierOperator
from .common import FinConfigMixin
from .intent import FinIntentExtractorOperator


class RequestHandleOperator(
    FinConfigMixin,
    BaseConversationOperator,
    MapOperator[CommonLLMHttpRequestBody, ModelRequest],
):
    """RequestHandleOperator."""

    def __init__(
        self, storage: StorageInterface, tmp_dir_path: Optional[str] = None, **kwargs
    ):
        """Create a new RequestHandleOperator."""
        self._tmp_dir_path = tmp_dir_path
        MapOperator.__init__(self, **kwargs)
        BaseConversationOperator.__init__(
            self, storage=storage, message_storage=storage
        )

    async def map(self, input_value: CommonLLMHttpRequestBody) -> ModelRequest:
        """Map the input value to the output value."""
        print(f"fin chat input:{input_value}")
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
        model_request = ModelRequest.build_request(input_value.model, messages)
        model_request.context.extra = input_value.extra

        db_name = input_value.context.extra.get("db_name")
        space = input_value.context.extra.get("space")
        embedding_model = input_value.context.extra.get("embedding_model")

        # Save config for the child operators
        await self._save_chat_config(
            db_name=db_name,
            space_name=space,
            embedding_model=embedding_model,
            tmp_dir_path=self._tmp_dir_path,
        )
        return model_request


def join_func(*args):
    """Join function."""
    for arg in args:
        if not is_empty_data(arg):
            return arg
    return None


class FinChatJoinOperator(JoinOperator[str]):
    """FinReportJoinOperator."""

    streaming_operator = True
    metadata = ViewMetadata(
        label="Fin Report Output Join Operator",
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
        """Create a new FinReportJoinOperator."""
        super().__init__(join_func, can_skip_in_branch=False, **kwargs)


with DAG(
    "fin_report_assistant_example",
    tags={"knowledge_chat_domain_type": "FinancialReport"},
) as dag:
    trigger = CommonLLMHttpTrigger(
        "/dbgpts/financial-robot-app",
        methods="POST",
        streaming_predict_func=lambda x: x.stream,
    )
    dev_mode = dag.dev_mode

    llm_client: Optional[LLMClient] = None
    if dev_mode:
        from dbgpt.model.proxy import OpenAILLMClient

        llm_client = OpenAILLMClient(
            model_alias="gpt-4o",
            api_base=os.getenv("OPENAI_API_BASE"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        tmp_dir_path = os.getenv("TMP_DIR_PATH", "./output")
    else:
        # Run this code in DB-GPT
        from dbgpt.configs.model_config import PILOT_PATH

        tmp_dir_path = f"{PILOT_PATH}/data/"

    fin_report_model = os.getenv("FIN_REPORT_MODEL", "BAAI/bge-large-zh-v1.5")

    storage = InMemoryStorage()
    request_handle_task = RequestHandleOperator(storage, tmp_dir_path=tmp_dir_path)
    fin_intent_task = FinIntentExtractorOperator(default_client=llm_client)
    # query classifier
    query_classifier = QuestionClassifierOperator(model=fin_report_model)
    classifier_branch = QuestionClassifierBranchOperator()
    indicator_task = ChatIndicatorOperator()
    chat_normal_task = ChatNormalOperator()
    indicator_llm_task = LLMOperator()
    indicator_sql_parse_task = ChatDatabaseOutputParserOperator(
        task_name="indicator_sql_parse_task"
    )
    indicator_sql_chart_task = ChatDatabaseChartOperator(
        task_name="indicator_sql_chart_task"
    )
    chat_knowledge_task = ChatKnowledgeOperator()
    stream_llm_task = StreamingLLMOperator()
    join_task = FinChatJoinOperator()
    # query classifier
    (
        trigger
        >> request_handle_task
        >> fin_intent_task
        >> query_classifier
        >> classifier_branch
    )
    # chat indicator branch
    (
        classifier_branch
        >> indicator_task
        >> indicator_llm_task
        >> indicator_sql_parse_task
        >> indicator_sql_chart_task
        >> join_task
    )
    # chat knowledge branch
    (classifier_branch >> chat_knowledge_task >> stream_llm_task >> join_task)
    # chat normal branch
    (classifier_branch >> chat_normal_task >> StreamingLLMOperator() >> join_task)
