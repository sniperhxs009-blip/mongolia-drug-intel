"""
搜索引擎发现模块 v4.2 — DeepSeek 联网搜索
==========================================
12 个多角度查询，串行执行，每步通过 callback 推送进度到前端。
单次查询返回 JSON 格式的标题+URL+中文摘要。
只信任国际新闻源（Reuters, BBC, AP, Al Jazeera, UNODC, INTERPOL 等）。
"""
import asyncio
import json
import os
import re

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
    "people.com.cn", "mps.gov.cn", "nncc.org.cn", "nncc626.com",
    "odkb-csto.org",
]

# 17 个多角度查询（并行执行，每步上报进度）
SEARCH_QUERIES = [
    # 国际组织
    "search site:unodc.org Mongolia drug narcotics trafficking. list real articles as JSON with title, URL, Chinese summary.",
    "search site:unodc.org Mongolia drug control prevention treatment. list real articles as JSON with title, URL, Chinese summary.",
    "search site:interpol.int Mongolia drug trafficking operation. list real articles as JSON with title, URL, Chinese summary.",
    "search site:odkb-csto.org Mongolia drug trafficking Central Asia. list real articles as JSON with title, URL, Chinese summary.",
    # 毒品查获
    "search Mongolia drug bust seizure cannabis methamphetamine record tonnes. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia narcotics seizure customs border police arrest smuggling. list real articles as JSON with title, URL, Chinese summary.",
    # 毒品网络和贩运
    "search Mongolia drug trafficking network organized crime syndicate cartel. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia cross-border drug smuggling China Russia route. list real articles as JSON with title, URL, Chinese summary.",
    # 禁毒政策和合作
    "search Mongolia drug control policy international cooperation UNODC strategy. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia drug addiction treatment harm reduction program. list real articles as JSON with title, URL, Chinese summary.",
    # 合成毒品
    "search Mongolia methamphetamine synthetic drugs crystal meth lab NPS precursor. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia new psychoactive substance drug trend fentanyl ketamine. list real articles as JSON with title, URL, Chinese summary.",
    # 蒙文搜索 + 执法
    "search Mongolia khark tamkhi monsuuruulakh bodis narkotik police raid arrest. list real articles as JSON with title, URL, Chinese summary.",
    # 中文来源：中蒙跨境缉毒
    "search site:people.com.cn 蒙古 毒品 贩毒 缉毒 禁毒. list real articles as JSON with title, URL, Chinese summary.",
    "search site:mps.gov.cn 蒙古 毒品 贩毒 跨境. list real articles as JSON with title, URL, Chinese summary.",
    "search site:nncc.org.cn OR site:nncc626.com 蒙古 毒品 禁毒. list real articles as JSON with title, URL, Chinese summary.",
    "search 中蒙 跨境毒品 内蒙古 缉毒 禁毒 查获. list real articles as JSON with title, URL, Chinese summary.",
]

REFUSE_SIGNALS = [
    "I cannot browse", "I am unable to browse",
    "I cannot access", "cannot provide real",
    "I cannot provide real",
]


async def _call_deepseek(query: str, max_tokens: int = 3500) -> str:
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
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
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
    url_lower = url.lower()
    return any(d in url_lower for d in TRUSTED_DOMAINS)


def _is_mongolia_related(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    mongolia_signals = [
        "mongolia", "mongolian", "ulaanbaatar",
        "蒙古", "蒙通社", "montsame",
        "中蒙", "蒙俄", "中俄蒙",
    ]
    return any(sig in text for sig in mongolia_signals)


def _is_drug_related(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    drug_signals = [
        "drug", "narcotic", "trafficking", "seizure", "bust",
        "smuggl", "cartel", "meth", "heroin", "cocaine", "opioid",
        "fentanyl", "ecstasy", "cannabis", "marijuana", "hashish",
        "interpol", "unodc", "dealer", "syndicate", "contraband",
        "narco", "criminal gang", "organized crime",
        "хар тамхи", "мансууруулах", "наркотик",
        "мансууруулагч", "худалдаа", "наймаа",
        "хууль бус", "хураагдсан", "хэрэглээ",
        "гэмт хэрэг", "баривчилсан",
        "毒品", "贩毒", "缉毒", "禁毒", "海洛因", "冰毒",
        "大麻", "可卡因", "走私", "缴获", "查获", "抓捕",
        "毒枭", "吸毒", "戒毒", "摇头丸", "麻古",
        "跨境贩", "贩运", "运毒", "藏毒", "制毒",
        "跨国毒", "合成毒品", "易制毒",
    ]
    return any(sig in text for sig in drug_signals)


def _parse_json_response(text: str) -> list[dict]:
    articles = []

    for sig in REFUSE_SIGNALS:
        if sig in text:
            return []

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
        summary = item.get("summary", "") or item.get("chinese_summary", "") or item.get("content", "")
        summary = summary.strip()

        if not title or not url:
            continue
        if "example.com" in url or "example.org" in url or "[ID]" in url:
            continue
        if not _is_trusted_url(url):
            continue
        if not _is_drug_related(title, summary):
            continue
        if not _is_mongolia_related(title, summary):
            continue

        # 语种检测
        lang = "en"
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
            return domain.split(".")[0].upper() if domain.endswith((".org", ".int")) else domain.split(".")[0].title()
    return "国际新闻"


async def search_all_articles(progress_callback=None) -> list[dict]:
    """
    主入口：并行执行 12 个查询，每完成一个就调用 progress_callback 推送进度。
    progress_callback(phase, current, total, article_count, msg)
    """
    if not DEEPSEEK_SEARCH_AVAILABLE:
        log.warning("DEEPSEEK_API_KEY not set")
        if progress_callback:
            await progress_callback("search_engine", 0, len(SEARCH_QUERIES), 0, "DeepSeek API Key 未设置")
        return []

    all_articles = []
    seen_urls = set()
    lock = asyncio.Lock()
    completed = 0
    total = len(SEARCH_QUERIES)

    async def _run_one(i: int, query: str):
        nonlocal completed
        raw = await _call_deepseek(query)
        if raw:
            articles = _parse_json_response(raw)
            async with lock:
                count_before = len(all_articles)
                for a in articles:
                    url = a.get("source_url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_articles.append(a)
                added = len(all_articles) - count_before
                completed += 1
                current_count = len(all_articles)
            log.info("查询 %d/%d: +%d 篇 (累计 %d)", i + 1, total, added, current_count)
            if progress_callback:
                await progress_callback(
                    "search_engine", completed, total, current_count,
                    f"DeepSeek 搜索 {completed}/{total}：+{added} 篇，累计 {current_count} 篇"
                )
        else:
            async with lock:
                completed += 1
                current_count = len(all_articles)
            log.info("查询 %d/%d: 失败", i + 1, total)
            if progress_callback:
                await progress_callback(
                    "search_engine", completed, total, current_count,
                    f"DeepSeek 搜索 {completed}/{total}：无结果"
                )

    await asyncio.gather(*[_run_one(i, q) for i, q in enumerate(SEARCH_QUERIES)])

    log.info("总计: %d 篇毒品相关文章", len(all_articles))
    return all_articles


def get_search_discovery_urls() -> list[dict]:
    """同步包装，供旧代码调用"""
    import asyncio
    return asyncio.run(search_all_articles())


def search_mongolia_drug_news() -> list[dict]:
    import asyncio
    return asyncio.run(search_all_articles())


def _search_ddg(query: str, max_results: int = 25) -> list[dict]:
    return []
