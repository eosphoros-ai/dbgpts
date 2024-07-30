import asyncio

from dbgpt.core.awel import CommonLLMHttpRequestBody


async def main():
    from financial_robot_app import dag

    req = CommonLLMHttpRequestBody(
        model="gpt-3.5-turbo",
        messages="贵州航天电器法定代表是谁",
        conv_uid="123456",
        stream=True,
        extra={
            "space": "my_knowledge_space",
            "db_name": "my_knowledge_space_fin_report",
            "embedding_model": "/opt/model_links/bge-large-zh-v1.5/",
        },
    )
    node = dag.leaf_nodes[0]
    async for out in await node.call_stream(req):
        print(out)


if __name__ == "__main__":
    from dbgpt.component import SystemApp
    from dbgpt.core.awel import DAGVar

    DAGVar.set_current_system_app(SystemApp())
    asyncio.run(main())
