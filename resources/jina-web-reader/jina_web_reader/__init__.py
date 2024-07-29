"""A tool for searching and crawling the web using Jina."""

import os

import aiohttp
from dbgpt.agent.resource import tool
from typing_extensions import Annotated, Doc

_API_TOKEN_ENV_KEY = "DBGPT_TOOL_JINA_API_TOKEN"
_SEARCH_URL_ENV_KEY = "DBGPT_TOOL_JINA_API_SEARCH_URL"
_SEARCH_TIMEOUT_ENV_KEY = "DBGPT_TOOL_JINA_API_SEARCH_TIMEOUT"
_READER_URL_ENV_KEY = "DBGPT_TOOL_JINA_API_READER_URL"
_READER_TIMEOUT_ENV_KEY = "DBGPT_TOOL_JINA_API_READER_TIMEOUT"


def _search_to_view(results) -> str:
    view_results = []
    for item in results:
        view_results.append(
            f"### [{item['title']}]({item['url']})\n{item['content']}\n"
        )
    return "\n".join(view_results)


@tool
async def jina_reader_web_search(
    query: Annotated[str, Doc("The query to search for.")],
    json_output: Annotated[
        bool, Doc("Whether to return the JSON output(default: False).")
    ] = False,
    num_results: Annotated[
        int, Doc("The number of search results to return(default: 5.")
    ] = 5,
) -> str | list[dict[str, str]]:
    """Search the web for the specified query and return the text content."""
    if not query:
        raise ValueError("The query is required.")
    query = query.strip()
    api_token = os.getenv(_API_TOKEN_ENV_KEY)
    jina_search_url = os.getenv(_SEARCH_URL_ENV_KEY, "https://s.jina.ai/")
    jina_search_timeout = os.getenv(_SEARCH_TIMEOUT_ENV_KEY, 60)
    if not jina_search_url.endswith("/"):
        jina_search_url += "/"
    url = f"{jina_search_url}{query}"
    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    # json response
    headers["Accept"] = "application/json"
    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=jina_search_timeout)
    ) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            resp_content = await resp.json()
            if "data" not in resp_content:
                raise ValueError("Invalid response content.")
            data = resp_content["data"]
            results = []
            if not isinstance(data, list):
                raise ValueError("Invalid response content(data is not a list).")
            for item in data:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", ""),
                    }
                )
            results = results[:num_results]
            if json_output:
                return results
            return _search_to_view(results)


@tool
async def jina_reader_web_crawler(
    url: Annotated[str, Doc("The URL to crawl.")],
    json_output: Annotated[
        bool, Doc("Whether to return the JSON output(default: False).")
    ] = False,
) -> str | dict[str, str]:
    """Crawl the web for the specified URL and return the text content."""
    if not url:
        raise ValueError("The URL is required.")
    url = url.strip()
    api_token = os.getenv(_API_TOKEN_ENV_KEY)
    jina_reader_url = os.getenv(_READER_URL_ENV_KEY, "https://r.jina.ai/")
    jina_reader_timeout = os.getenv(_READER_TIMEOUT_ENV_KEY, 60)
    if not jina_reader_url.endswith("/"):
        jina_reader_url += "/"
    url = f"{jina_reader_url}{url}"
    headers = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    headers["Accept"] = "application/json"

    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=jina_reader_timeout)
    ) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            resp_content = await resp.json()
            if "data" not in resp_content:
                raise ValueError("Invalid response content.")
            data = resp_content["data"]
            result = {
                "title": data.get("title", ""),
                "url": data.get("url", ""),
                "content": data.get("content", ""),
            }
            if json_output:
                return result
            return _search_to_view([result])


if __name__ == "__main__":
    import asyncio

    async def main():
        res = await jina_reader_web_crawler("https://en.m.wikipedia.org/wiki/Main_Page")
        print(res)
        search_res = await jina_reader_web_search("The weather in Beijing today?")
        print(search_res)

    asyncio.run(main())
