import logging
from tavily import TavilyClient

logger = logging.getLogger(__name__)

# ⚠️ 填入你全新的 Tavily API Key
TAVILY_API_KEY = "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"
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

def search_web(query: str, max_results=3) -> str:
    try:
        logger.info(f"🌐 正在呼叫 Tavily 军用雷达搜索关键词: {query}")
        response = tavily_client.search(query=query, max_results=max_results, search_depth="basic")
        results = response.get('results', [])

        if not results: return "Tavily 全网未检索到相关情报。"

        snippets = [f"- {res['title']}: {res['content']}" for res in results]
        return "\n".join(snippets)
    except Exception as e:
        logger.error(f"Tavily 雷达搜索失败: {str(e)}")
        return "Tavily 搜索接口暂时不可用。"