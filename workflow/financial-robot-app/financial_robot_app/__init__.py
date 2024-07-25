"""FinReportJoinOperator."""

from typing import List

from dbgpt._private.config import Config
from dbgpt.component import ComponentType
from dbgpt.core import (
    ModelMessage,
    ModelRequest,
    StorageInterface,
    InMemoryStorage,
    StorageConversation,
    BaseMessage,
)
from dbgpt.core.awel import (
    CommonLLMHttpRequestBody,
    JoinOperator,
    MapOperator,
    is_empty_data,
    DAG,
)
from dbgpt.core.awel.flow import IOField, OperatorCategory, ViewMetadata
from dbgpt.core.awel.trigger.http_trigger import CommonLLMHttpTrigger
from dbgpt.core.interface.operators.message_operator import BaseConversationOperator
from dbgpt.model import DefaultLLMClient
from dbgpt.model.cluster import WorkerManagerFactory
from dbgpt.model.operators import StreamingLLMOperator, LLMOperator

from .chat_database import (
    ChatDataOperator,
    ChatDatabaseChartOperator,
    ChatDatabaseOutputParserOperator,
)
from .chat_indicator import ChatIndicatorOperator
from .chat_knowledge import ChatKnowledgeOperator
from .classifier import QuestionClassifierOperator, QuestionClassifierBranchOperator
from .intent import FinIntentExtractorOperator
from .chat_normal import ChatNormalOperator


class RequestHandleOperator(
    BaseConversationOperator, MapOperator[CommonLLMHttpRequestBody, ModelRequest]
):
    """RequestHandleOperator."""

    def __init__(self, storage: StorageInterface, **kwargs):
        """Create a new RequestHandleOperator."""
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
    CFG = Config()
    worker_manager_factory: WorkerManagerFactory = CFG.SYSTEM_APP.get_component(
        ComponentType.WORKER_MANAGER_FACTORY,
        WorkerManagerFactory,
        default_component=None,
    )
    if worker_manager_factory:
        llm_client = DefaultLLMClient(worker_manager_factory.create())
    storage = InMemoryStorage()
    request_handle_task = RequestHandleOperator(storage)
    fin_intent_task = FinIntentExtractorOperator(llm_client=llm_client)
    # query classifier
    query_classifier = QuestionClassifierOperator(model=CFG.FIN_REPORT_MODEL)
    classifier_branch = QuestionClassifierBranchOperator()
    chat_data_task = ChatDataOperator()
    llm_task = LLMOperator()
    sql_parse_task = ChatDatabaseOutputParserOperator()
    sql_chart_task = ChatDatabaseChartOperator()
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
    # chat database branch
    (
        classifier_branch
        >> chat_data_task
        >> llm_task
        >> sql_parse_task
        >> sql_chart_task
        >> join_task
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
