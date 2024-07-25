from dbgpt.core import ModelRequest
from dbgpt.core.awel import MapOperator


class ChatNormalOperator(MapOperator[ModelRequest, ModelRequest]):
    def __init__(self, task_name="chat_normal", **kwargs):
        super().__init__(task_name=task_name, **kwargs)

    async def map(self, input_value: ModelRequest) -> ModelRequest:
        return input_value
