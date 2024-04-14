from typing import Optional
from dbgpt.agent import (
    Action,
    ActionOutput,
    AgentResource,
    ResourceType,
)
from dbgpt.agent.util import cmp_string_equal
from dbgpt.vis import Vis
from pydantic import BaseModel, Field

NOT_RELATED_MESSAGE = "Did not find the information you want."


class SummaryActionInput(BaseModel):
    summary: str = Field(
        ...,
        description="The summary content",
    )


class SummaryAction(Action[SummaryActionInput]):
    def __init__(self):
        super().__init__()

    @property
    def resource_need(self) -> Optional[ResourceType]:
        # The resource type that the current Agent needs to use
        # here we do not need to use resources, just return None
        return None

    @property
    def render_protocol(self) -> Optional[Vis]:
        # The visualization rendering protocol that the current Agent needs to use
        # here we do not need to use visualization rendering, just return None
        return None

    @property
    def out_model_type(self):
        return SummaryActionInput

    async def run(
            self,
            ai_message: str,
            resource: Optional[AgentResource] = None,
            rely_action_out: Optional[ActionOutput] = None,
            need_vis_render: bool = True,
            **kwargs,
    ) -> ActionOutput:
        """Perform the action.

        The entry point for actual execution of Action. Action execution will be
        automatically initiated after model inference.
        """
        extra_param = kwargs.get("action_extra_param_key", None)
        try:
            # Parse the input message
            param: SummaryActionInput = self._input_convert(ai_message,
                                                            SummaryActionInput)
        except Exception:
            return ActionOutput(
                is_exe_success=False,
                content="The requested correctly structured answer could not be found, "
                        f"ai message: {ai_message}",
            )
        # Check if the summary content is not related to user questions
        if param.summary and cmp_string_equal(
                param.summary,
                NOT_RELATED_MESSAGE,
                ignore_case=True,
                ignore_punctuation=True,
                ignore_whitespace=True,
        ):
            return ActionOutput(
                is_exe_success=False,
                content="the provided text content is not related to user questions at "
                        f"all. ai message: {ai_message}",
            )
        else:
            return ActionOutput(
                is_exe_success=True,
                content=param.summary,
            )
