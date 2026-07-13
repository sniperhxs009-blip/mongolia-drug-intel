"""
搜索引擎发现模块 v4.1 — DeepSeek 联网搜索（并行版）
====================================================
6 个核心查询并行执行，速度提升 3-4 倍。
单次查询返回 JSON 格式的标题+URL+中文摘要。
只信任国际新闻源（Reuters, BBC, AP, Al Jazeera, UNODC, INTERPOL 等）。
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from modules.logger import get_logger

log = get_logger("search_engines")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_SEARCH_AVAILABLE = bool(DEEPSEEK_API_KEY)

# 可信国际新闻域名
TRUSTED_DOMAINS = [
    "reuters.com", "bbc.com", "bbc.co.uk", "apnews.com",
    "aljazeera.com", "france24.com", "theguardian.com",
    "bangkokpost.com", "channelnewsasia.com", "scmp.com",
    "unodc.org", "interpol.int", "incb.org",
    "thediplomat.com", "eurasianet.org", "rfa.org",
    "voanews.com", "abc.net.au", "dw.com", "nikkei.com",
]

# 10 个核心查询（全部并行执行，速度 = 最慢单次查询 ≈ 5 秒）
SEARCH_QUERIES = [
    "search site:unodc.org Mongolia drug narcotics trafficking. list real articles as JSON with title, URL, Chinese summary.",
    "search site:interpol.int Mongolia drug trafficking operation. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia drug bust seizure cannabis methamphetamine record tonnes. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia narcotics seizure customs border police arrest smuggling. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia drug trafficking network organized crime syndicate cartel. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia cross-border drug smuggling China Russia route. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia drug control policy international cooperation UNODC strategy. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia methamphetamine synthetic drugs crystal meth lab NPS precursor. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia khark tamkhi monsuuruulakh bodis narkotik. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia drug law enforcement police raid arrest dealer network. list real articles as JSON with title, URL, Chinese summary.",
]

REFUSE_SIGNALS = [
    "I cannot browse", "I am unable to browse",
    "I cannot access", "cannot provide real",
    "I cannot provide real",
]


def _call_deepseek(query: str, max_tokens: int = 3500) -> str:
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
            log.warning("DeepSeek API %d", resp.status_code)
            return ""
    except Exception as e:
        log.warning("DeepSeek error: %s", e)
        return ""


def _is_trusted_url(url: str) -> bool:
    """只信任国际新闻源域名"""
    url_lower = url.lower()
    return any(d in url_lower for d in TRUSTED_DOMAINS)


def _is_mongolia_related(title: str, summary: str) -> bool:
    """检查文章是否与蒙古国相关"""
    text = (title + " " + summary).lower()
    mongolia_signals = [
        "mongolia", "mongolian", "ulaanbaatar", "乌兰巴托",
        "蒙古", "蒙通社", "montsame",
        "中蒙", "蒙俄", "中俄蒙",
    ]
    return any(sig in text for sig in mongolia_signals)


def _is_drug_related(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    drug_signals = [
        # English
        "drug", "narcotic", "trafficking", "seizure", "bust",
        "smuggl", "cartel", "meth", "heroin", "cocaine", "opioid",
        "fentanyl", "ecstasy", "cannabis", "marijuana", "hashish",
        "interpol", "unodc", "dealer", "syndicate", "contraband",
        "narco", "criminal gang", "organized crime",
        # Cyrillic Mongolian
        "хар тамхи", "мансууруулах", "наркотик",
        "мансууруулагч", "худалдаа", "наймаа",
        "хууль бус", "хураагдсан", "хэрэглээ",
        "гэмт хэрэг", "баривчилсан",
        # Chinese
        "毒品", "贩毒", "缉毒", "禁毒", "海洛因", "冰毒",
        "大麻", "可卡因", "走私", "缴获", "查获", "抓捕",
        "毒枭", "吸毒", "戒毒", "摇头丸", "麻古",
        "跨境贩", "贩运", "运毒", "藏毒", "制毒",
        "跨国毒", "合成毒品", "易制毒",
    ]
    return any(sig in text for sig in drug_signals)


def _parse_json_response(text: str) -> list[dict]:
    """解析 DeepSeek 返回的 JSON 文章列表"""
    articles = []

    for sig in REFUSE_SIGNALS:
        if sig in text:
            return []

    # 提取 JSON 数组（可能在 ```json 代码块中）
    json_match = re.search(r'\[[\s\S]*\]', text)
    if not json_match:
        return []

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    for item in data:
        if not isinstance(item, dict):
            continue
        title = item.get("title", "").strip().strip('"').strip()
        url = item.get("url", "").strip()
        # DeepSeek 可能用不同的 key 名
        summary = item.get("summary", "") or item.get("chinese_summary", "") or item.get("content", "")
        summary = summary.strip()

        if not title or not url:
            continue
        # 拒绝明显虚假的 URL
        if "example.com" in url or "example.org" in url or "[ID]" in url:
            continue
        # 必须来自可信域名
        if not _is_trusted_url(url):
            continue
        # 必须与毒品相关
        if not _is_drug_related(title, summary):
            continue
        # 必须与蒙古国相关（至少提及蒙古）
        if not _is_mongolia_related(title, summary):
            continue

        # 根据标题+摘要检测语种
        lang = "en"  # 默认
        combined = title + " " + summary
        if any('一' <= c <= '鿿' for c in combined):
            lang = "zh"
        elif any('Ѐ' <= c <= 'ӿ' for c in combined):
            lang = "mn"

        articles.append({
            "news_title": title,
            "source_url": url,
            "publish_time": item.get("date", ""),
            "content_summary": summary[:400],
            "source_name": extract_source_name(url),
            "language": lang,
            "site_category": "搜索引擎发现",
        })

    return articles


def extract_source_name(url: str) -> str:
    for domain in TRUSTED_DOMAINS:
        if domain in url.lower():
            return domain.split(".")[0].upper() if domain.endswith(".org") or domain.endswith(".int") else domain.split(".")[0].title()
    return "国际新闻"


def _process_query(query: str, idx: int) -> list[dict]:
    """处理单个查询，返回文章列表"""
    raw = _call_deepseek(query)
    if raw:
        articles = _parse_json_response(raw)
        log.info("Query %d/%d: %d articles (%d chars)", idx + 1, len(SEARCH_QUERIES), len(articles), len(raw))
        return articles
    log.info("Query %d/%d: API failed", idx + 1, len(SEARCH_QUERIES))
    return []


def search_all_articles() -> list[dict]:
    if not DEEPSEEK_SEARCH_AVAILABLE:
        log.warning("DEEPSEEK_API_KEY not set")
        return []

    all_articles = []
    seen_urls = set()

    # 并行执行所有查询
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_process_query, q, i): i for i, q in enumerate(SEARCH_QUERIES)}
        for future in as_completed(futures):
            try:
                articles = future.result()
                for a in articles:
                    url = a.get("source_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_articles.append(a)
            except Exception as e:
                log.warning("Query worker error: %s", e)

    log.info("Total: %d drug-related articles from trusted sources", len(all_articles))
    return all_articles


def get_search_discovery_urls() -> list[str]:
    articles = search_all_articles()
    return [a["source_url"] for a in articles if a.get("source_url")]


def search_mongolia_drug_news() -> list[dict]:
    return search_all_articles()


def _search_ddg(query: str, max_results: int = 25) -> list[dict]:
    return []
