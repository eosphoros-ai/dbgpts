"""The ChatDatabaseOperator."""

from dbgpt.core import ModelOutput, SQLOutputParser
from dbgpt.core.awel import MapOperator
from dbgpt.core.awel.flow import IOField, OperatorCategory, ViewMetadata
from dbgpt.util.i18n_utils import _

from .common import FinConfigMixin

_SHARE_DATA_DATABASE_NAME_KEY = "__database_name__"


class ChatDatabaseOutputParserOperator(SQLOutputParser):
    """ChatDatabaseOutputParserOperator."""

    metadata = ViewMetadata(
        label=_("Chat Data Output Operator"),
        name="chat_data_out_parser_operator",
        category=OperatorCategory.EXPERIMENTAL,
        description=_(_("Chat Data Output Operator.")),
        inputs=[
            IOField.build_from(
                _("model output"),
                "model_output",
                ModelOutput,
                description=_("model output."),
            )
        ],
        outputs=[
            IOField.build_from(
                _("dict"),
                "dict",
                dict,
                description=_("dict."),
            )
        ],
        parameters=[],
        documentation_url="https://github.com/openai/openai-python",
    )

    async def map(self, input_value: ModelOutput) -> dict:
        """Map the input value to the output value."""
        return self.parse_model_nostream_resp(input_value, "#########")


class ChatDatabaseChartOperator(FinConfigMixin, MapOperator[dict, str]):
    """The ChatDatabaseChartOperator."""

    metadata = ViewMetadata(
        label=_("Chat Data Chart Operator"),
        name="chat_data_chart_operator",
        category=OperatorCategory.EXPERIMENTAL,
        description=_(_("Chat Data Output Operator.")),
        inputs=[
            IOField.build_from(
                _("dict"),
                "dict",
                dict,
                description=_("dict."),
            )
        ],
        outputs=[
            IOField.build_from(
                _("str"),
                "str",
                str,
                description=_("dict."),
            )
        ],
        parameters=[],
        documentation_url="https://github.com/openai/openai-python",
    )

    def __init__(self, task_name="chat_database_parser", **kwargs):
        """Create a new ChatDatabaseChartOperator."""
        MapOperator.__init__(self, task_name=task_name, **kwargs)

    async def map(self, input_value: dict) -> str:
        """Map the input value to the output value."""
        from dbgpt.datasource import RDBMSConnector
        from dbgpt.vis.tags.vis_chart import VisChart

        (
            db_name,
            space_name,
            tmp_dir_path,
            embedding_model,
        ) = await self._get_chat_config()
        vis = VisChart()
        database: RDBMSConnector = await self.get_connector(
            space_name, db_name, tmp_dir_path
        )
        sql = input_value.get("sql")
        data_df = None
        try:
            data_df = await self.blocking_func_to_async(database.run_to_df, sql)
        except Exception as e:
            if "no such table" in str(e):
                import re

                table_regex = re.compile(r"FROM\s+([^\s;]+)", re.IGNORECASE)
                matches = table_regex.finditer(sql)
                raw_table = None
                for match in matches:
                    raw_table = match.group(1)
                if raw_table:
                    sql = sql.replace(raw_table, "fin_report")
                    input_value["sql"] = sql
                data_df = await self.blocking_func_to_async(database.run_to_df, sql)
        view = await vis.display(chart=input_value, data_df=data_df)
        return view
