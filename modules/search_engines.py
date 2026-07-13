"""
多搜索引擎发现模块
==================
通过 DuckDuckGo (底层使用 Bing 索引) 的 site: 语法，
一次性搜索所有蒙古国涉毒机构网站，大幅提升发现效率。

替代原来逐个站点爬取的方案，用搜索引擎的索引覆盖所有站点。
"""
import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from modules.logger import get_logger

log = get_logger("search_engines")

# 30天前的日期，用于时间过滤
CUTOFF_DATE = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

# 搜索目标站点分组（对应豆包的7大类）
SEARCH_TARGETS = {
    "mongolia_media": {
        "label": "蒙古主流媒体",
        "sites": [
            "montsame.mn", "ikon.mn", "news.mn", "shuum.mn",
            "gogo.mn", "see.mn", "ubpost.mongolnews.mn",
        ],
    },
    "mongolia_gov": {
        "label": "蒙古政府机构",
        "sites": [
            "customs.gov.mn", "mojha.gov.mn", "mohs.mn",
            "parliament.mn", "nfa.gov.mn", "police.gov.mn",
        ],
    },
    "international": {
        "label": "国际组织",
        "sites": [
            "unodc.org", "interpol.int",
        ],
    },
    "china_crossborder": {
        "label": "中方跨境信源",
        "sites": [
            "nncc.org.cn", "chinanews.com.cn", "people.com.cn",
        ],
    },
}

# 三语种搜索关键词（每站点每个语种搜一次）
SEARCH_QUERIES = {
    "mn": [
        "хар тамхи", "мансууруулах бодис", "мансууруулах",
        "наркотик", "фентанил", "хар тамхины наймаа",
        "мансууруулах бодисын наймаа", "гаалийн хар тамхи илрүүлэлт",
    ],
    "en": [
        "drug trafficking", "narcotics seizure", "drug bust",
        "drug smuggling", "anti-drug operation", "drug arrest",
    ],
    "zh": [
        "毒品", "缉毒", "贩毒", "走私毒品", "禁毒",
        "跨境贩毒", "中蒙边境毒品",
    ],
}


def _search_ddg(query: str, max_results: int = 25) -> list[dict]:
    """用 ddgs 库搜索 DuckDuckGo (底层走 Bing 索引)，返回结果列表"""
    try:
        from ddgs import DDGS
    except ImportError:
        log.warning("ddgs 未安装，跳过搜索引擎发现")
        return []

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, timelimit="m"):
                url = r.get("href", "")
                title = r.get("title", "")
                body = r.get("body", "")
                if url:
                    results.append({"url": url, "title": title, "body": body})
    except Exception as e:
        log.warning("ddgs 搜索异常: %s", e)

    return results


def search_all_sites() -> list[str]:
    """
    用搜索引擎的 site: 语法，对每个站点+关键词组合搜索，
    返回所有发现的涉毒文章 URL 列表。
    """
    all_urls = set()
    total_queries = 0

    for group_key, group in SEARCH_TARGETS.items():
        sites = group["sites"]
        for site in sites:
            # 每个站点用 site: 语法搜索
            site_query = f"site:{site}"

            # 三语种各搜前2个关键词（减少请求量）
            for lang, queries in SEARCH_QUERIES.items():
                for kw in queries[:2]:  # 每种语言前2个
                    query = f"{site_query} {kw}"
                    try:
                        results = _search_ddg(query, max_results=10)
                        total_queries += 1
                        for r in results:
                            url = r["url"]
                            if url and url not in all_urls:
                                all_urls.add(url)
                        # 请求间隔，避免被限速
                        time.sleep(0.5)
                    except Exception as e:
                        log.warning("搜索失败 [%s]: %s", query, e)
                        continue

    log.info("搜索引擎发现: %d次查询, 去重后 %d 个URL, 覆盖 %d 个站点",
             total_queries, len(all_urls),
             sum(len(g["sites"]) for g in SEARCH_TARGETS.values()))
    return list(all_urls)


def search_mongolia_drug_news() -> list[dict]:
    """
    快速搜索蒙古国涉毒新闻（不需要 site: 逐个限定，
    用通用关键词 + Mongolia 限定即可）。
    返回带标题和摘要的结果列表。
    """
    all_results = []
    seen_urls = set()

    # 直接搜蒙古+毒品，搜索引擎会自动覆盖所有站点
    broad_queries = [
        "Mongolia drug trafficking seizure 2026",
        "Mongolia narcotics arrest bust",
        "Mongolia хар тамхи мансууруулах",
        "蒙古 毒品 缉毒 2026",
        "Mongolia customs drug bust",
        "Mongolia border drug smuggling",
    ]

    for query in broad_queries:
        try:
            results = _search_ddg(query, max_results=20)
            for r in results:
                url = r["url"]
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
            time.sleep(0.3)
        except Exception as e:
            log.warning("搜索失败 [%s]: %s", query, e)

    log.info("快速搜索: %d次查询, 去重后 %d 条结果",
             len(broad_queries), len(all_results))
    return all_results


def get_search_discovery_urls() -> list[str]:
    """
    对 crawler 的接口：返回搜索引擎发现的所有涉毒文章 URL。
    优先用 site: 逐个站点搜索（精准），失败时回退到 broad search。
    """
    urls = search_all_sites()
    if len(urls) < 10:
        # site: 搜索太少，补充 broad search
        log.info("site:搜索仅 %d 个URL，补充broad search", len(urls))
        broad = search_mongolia_drug_news()
        for r in broad:
            if r["url"] not in urls:
                urls.append(r["url"])
    return list(set(urls))
