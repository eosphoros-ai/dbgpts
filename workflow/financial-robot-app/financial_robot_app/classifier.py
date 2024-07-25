"""The Question Classifier Operator."""

from concurrent.futures import Executor, ThreadPoolExecutor
from enum import Enum
from typing import Dict, Optional, List
import os

import joblib
from dbgpt.util.executor_utils import blocking_func_to_async
from tqdm import tqdm
from transformers import AutoModel, AutoTokenizer

from dbgpt.core import ModelRequest
from dbgpt.core.awel import BranchFunc, BranchOperator, BranchTaskType, MapOperator
from dbgpt.core.awel.flow import IOField, OperatorCategory, Parameter, ViewMetadata
from dbgpt.core.awel.task.base import IN, OUT
from dbgpt.util.i18n_utils import _


class FinQuestionClassifierType(Enum):
    ANALYSIS = "报告解读分析"
    BASE_INFO = "年报基础信息问答"
    FINANCIAL_INDICATOR = "财务指标计算"
    GLOSSARY = "专业名称解释"
    COMPARISON = "统计对比"
    OTHER = "其他问题"

    @classmethod
    def get_by_value(cls, value: str):
        """Get the enum member by value."""
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"{value} is not a valid value for {cls.__name__}")


class QuestionClassifierOperator(MapOperator[IN, OUT]):
    """The Question Classifier Operator."""

    metadata = ViewMetadata(
        label=_("Question Classifier Operator"),
        name="question_classifier_operator",
        category=OperatorCategory.EXPERIMENTAL,
        description=_(_("Question Classifier Operator.")),
        inputs=[
            IOField.build_from(
                _("Question"),
                "question",
                ModelRequest,
                _("user question."),
            )
        ],
        outputs=[
            IOField.build_from(
                _("prediction"),
                "prediction",
                ModelRequest,
                description=_("classifier prediction."),
            )
        ],
        parameters=[
            Parameter.build_from(
                label=_("model"),
                name="model",
                type=str,
                optional=True,
                default=None,
                description=_("model."),
            ),
        ],
        documentation_url="https://github.com/openai/openai-python",
    )

    def __init__(
        self,
        model: str = None,
        adapter_model_path: str = None,
        device: Optional[str] = None,
        executor: Optional[Executor] = None,
        **kwargs,
    ):
        """Create a new Question Classifier Operator."""
        if not model:
            raise ValueError("model must be provided")
        if not adapter_model_path:

            current_dir = os.path.dirname(os.path.abspath(__file__))
            adapter_model_path = os.path.join(
                current_dir, "models", "dbgpt-hub-nlu-v0.1"
            )
        if not device:
            from dbgpt.configs.model_config import get_device

            device = get_device()

        self._model = model
        self._pretrained_model = None
        self._tokenizer = None
        self._adapter_model = None
        self._adapter_model_path = adapter_model_path
        self._device = device
        self._batch_size = 4
        self._executor = executor or ThreadPoolExecutor()
        super().__init__(**kwargs)

    async def map(self, request: ModelRequest) -> ModelRequest:
        """Map the user question to a financial."""
        question = request.messages[-1].content
        # check and load models
        await self._init_models()

        predictions = await blocking_func_to_async(
            self._executor, self._predict, [question]
        )
        if not request.context.extra:
            request.context.extra = {}
        request.context.extra["classifier"] = FinQuestionClassifierType.get_by_value(
            predictions[0]
        )
        return request

    def _predict(self, texts: List[str]) -> List[str]:
        from .model import batch_sentence_embeddings

        input_ids = batch_sentence_embeddings(
            texts, self._tokenizer, self._pretrained_model, self._device
        )
        predictions, _ = self._adapter_model.predict(input_ids, self._device)
        return predictions

    async def _init_models(self):
        if not self._pretrained_model:
            self._pretrained_model = await blocking_func_to_async(
                self._executor, AutoModel.from_pretrained, self._model
            )
            self._pretrained_model = self._pretrained_model.to(self._device)
            self._pretrained_model.eval()
        if not self._tokenizer:
            self._tokenizer = await blocking_func_to_async(
                self._executor,
                AutoTokenizer.from_pretrained,
                self._model,
                map_location=self._device,
            )
        if not self._adapter_model:
            from .model import SimpleIntentClassifier

            self._adapter_model = await blocking_func_to_async(
                self._executor,
                SimpleIntentClassifier.from_pretrained,
                self._adapter_model_path,
            )
            self._adapter_model = self._adapter_model.to(self._device)
            self._adapter_model.eval()


class QuestionClassifierBranchOperator(BranchOperator[ModelRequest, ModelRequest]):
    """The intent detection branch operator."""

    def __init__(self, **kwargs):
        """Create the intent detection branch operator."""
        super().__init__(**kwargs)
        # self._end_task_name = end_task_name

    async def branches(
        self,
    ) -> Dict[BranchFunc[ModelRequest], BranchTaskType]:
        """Branch the intent detection result to different tasks."""
        download_task_names = set(task.node_name for task in self.downstream)  # noqa
        branch_func_map = {}
        for task_name in download_task_names:

            def check(r: ModelRequest, outer_task_name=task_name):
                if not r.context or not r.context.extra:
                    return False
                classifier = r.context.extra.get("classifier")
                if not classifier:
                    return False
                if classifier == FinQuestionClassifierType.FINANCIAL_INDICATOR:
                    return outer_task_name == "chat_indicator"
                elif classifier == FinQuestionClassifierType.OTHER:
                    return outer_task_name == "chat_normal"
                else:
                    return outer_task_name == "chat_knowledge"

            branch_func_map[check] = task_name
        return branch_func_map  # type: ignore
