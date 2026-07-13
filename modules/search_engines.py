"""
搜索引擎发现模块 v3.0 — DeepSeek 联网搜索
==========================================
使用 DeepSeek API 联网搜索，简短英文提示词逐个站点搜索，
跟豆包一样，一句话搜出所有蒙古国涉毒新闻。

无需 ddgs、primp、curl_cffi 等任何第三方搜索库。
"""
import json
import os
import re
import time
from datetime import datetime, timedelta

import httpx

from modules.logger import get_logger

log = get_logger("search_engines")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_SEARCH_AVAILABLE = bool(DEEPSEEK_API_KEY)

# 简短英文搜索查询（每个查询一句话，这样 DeepSeek 才会稳定触发联网搜索）
SIMPLE_QUERIES = [
    # 蒙古主流媒体
    "search site:montsame.mn drug narcotics khark tamkhi. list real article URLs.",
    "search site:ikon.mn drug narcotics khark tamkhi. list real article URLs.",
    "search site:news.mn drug narcotics khark tamkhi. list real article URLs.",
    "search site:gogo.mn drug narcotics khark tamkhi. list real article URLs.",
    "search site:shuum.mn drug narcotics. list real article URLs.",
    # 蒙古政府
    "search site:customs.gov.mn drug narcotics seizure. list real article URLs.",
    "search site:mojha.gov.mn drug narcotics. list real article URLs.",
    "search site:police.gov.mn drug narcotics. list real article URLs.",
    "search site:parliament.mn drug narcotics. list real article URLs.",
    # 国际
    "search site:unodc.org Mongolia drug narcotics. list real article URLs.",
    "search site:interpol.int Mongolia drug narcotics. list real article URLs.",
    # 中文源
    "search site:chinanews.com.cn Mongolia drug. list real article URLs.",
    "search site:people.com.cn Mongolia drug. list real article URLs.",
    # 区域态势
    "search Mongolia drug trafficking seizure bust 2026. list real article URLs.",
    "search Mongolia narcotics arrest border customs 2026. list real article URLs.",
    "search China Mongolia cross-border drug smuggling. list real article URLs.",
]


def _call_deepseek_search(query: str, max_tokens: int = 2000) -> str:
    """调用 DeepSeek API 联网搜索（简短提示词）"""
    if not DEEPSEEK_SEARCH_AVAILABLE:
        return ""

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": query}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "search_enable": True,
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(
                "https://api.deepseek.com/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                log.warning("DeepSeek API %d: %s", resp.status_code, resp.text[:100])
                return ""
    except Exception as e:
        log.warning("DeepSeek API 异常: %s", e)
        return ""


def _extract_urls(text: str) -> list[str]:
    """从 DeepSeek 回复中提取 URL"""
    urls = set()
    # 匹配 markdown 链接和裸 URL
    for m in re.finditer(r"https?://[a-zA-Z0-9.-]+[^\s<>\"\'\)\]\}`]*", text):
        url = m.group().rstrip(".,;:!?)]}`*")
        # 过滤非文章 URL
        skip = ["google.com", "bing.com", "youtube.com", "facebook.com", "twitter.com",
                "instagram.com", "wikipedia.org", "github.com", ".css", ".js", ".png", ".jpg"]
        if not any(s in url.lower() for s in skip):
            urls.add(url)
    return list(urls)


def search_all_sites() -> list[str]:
    """逐个简短查询搜索所有站点，返回去重后的文章 URL"""
    if not DEEPSEEK_SEARCH_AVAILABLE:
        log.warning("DEEPSEEK_API_KEY 未设置，搜索引擎不可用")
        return []

    all_urls = set()
    for i, query in enumerate(SIMPLE_QUERIES):
        try:
            raw = _call_deepseek_search(query)
            if raw:
                urls = _extract_urls(raw)
                for u in urls:
                    all_urls.add(u)
                if urls:
                    log.info("查询 %d/%d: %d 个URL", i + 1, len(SIMPLE_QUERIES), len(urls))
            time.sleep(0.5)  # API 调用间隔
        except Exception as e:
            log.warning("查询失败 [%s]: %s", query[:50], e)

    log.info("DeepSeek 搜索完成: %d 次查询, %d 个去重URL",
             len(SIMPLE_QUERIES), len(all_urls))
    return list(all_urls)


def search_mongolia_drug_news() -> list[dict]:
    """快速搜索，返回带 URL 的结果列表"""
    urls = search_all_sites()
    return [{"url": u, "title": "", "body": ""} for u in urls]


def get_search_discovery_urls() -> list[str]:
    """对 crawler 的接口：返回搜索引擎发现的所有涉毒文章 URL"""
    return search_all_sites()


# 兼容旧接口
def _search_ddg(query: str, max_results: int = 25) -> list[dict]:
    """旧接口兼容"""
    return []
