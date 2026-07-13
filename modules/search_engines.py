"""
搜索引擎发现模块 v5.0 — AI 搜索 + Google News RSS
================================================
双引擎并行：DeepSeek 联网搜索 (13 查询) + Google News RSS (14 查询)。
AI 搜索覆盖国际新闻源，RSS 返回真实可打开的原文链接。
"""
import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

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
    "odkb-csto.org",
]

# 13 个多角度查询（并行执行，每步上报进度）
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
]

# 14 个 Google News RSS 查询 — 返回真实原文链接，不依赖 AI 生成
GOOGLE_NEWS_QUERIES = [
    "mongolia drug trafficking narcotics seizure",
    "mongolia drug bust police arrest smuggle",
    "mongolia methamphetamine synthetic drugs crystal",
    "mongolia narcotics border customs smuggling",
    "mongolia drug cartel organized crime syndicate",
    "mongolia UNODC drug control report",
    "mongolia INTERPOL drug operation",
    "монгол хар тамхи мансууруулах бодис",
    "монгол наркотик хууль бус наймаа",
    "монгол мансууруулагч баривчилсан",
    "монгол цагдаа хар тамхи хураагдсан",
    "Mongolia drug addiction treatment harm reduction",
    "Mongolia fentanyl ketamine new psychoactive substance",
    "Mongolia cross-border drug route China Russia",
]

REFUSE_SIGNALS = [
    "I cannot browse", "I am unable to browse",
    "I cannot access", "cannot provide real",
    "I cannot provide real",
]


async def _call_deepseek(query: str, max_tokens: int = 3500) -> tuple[str, list[dict]]:
    """
    调用 DeepSeek API 联网搜索。
    返回 (content, search_results)，其中 search_results 是从 API 响应中提取的真实搜索结果 URL。
    """
    if not DEEPSEEK_SEARCH_AVAILABLE:
        return "", []

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
                msg = data["choices"][0]["message"]
                content = msg.get("content", "")

                # 尝试从 API 响应提取真实搜索结果
                search_results = []
                # DeepSeek 可能在 message 或顶层返回 search_results/citations
                for field in ["search_results", "citations", "web_search_results", "references"]:
                    raw_results = msg.get(field) or data.get(field)
                    if raw_results and isinstance(raw_results, list):
                        for r in raw_results:
                            if isinstance(r, dict):
                                url = r.get("url") or r.get("link") or ""
                                title = r.get("title") or r.get("name") or ""
                                if url and title:
                                    search_results.append({"news_title": title, "source_url": url})
                        break

                return content, search_results
            log.warning("DeepSeek API %d", resp.status_code)
            return "", []
    except Exception as e:
        log.warning("DeepSeek error: %s", e)
        return "", []


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


def _strip_html(text: str) -> str:
    """移除 HTML 标签"""
    return re.sub(r'<[^>]+>', '', text).strip()


def _parse_rss(xml_text: str) -> list[dict]:
    """解析 Google News / Bing News RSS XML，提取文章"""
    articles = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for item in root.findall('.//item'):
        title = item.findtext('title', '').strip()
        link = item.findtext('link', '').strip()
        pub_date = item.findtext('pubDate', '').strip()
        description = item.findtext('description', '').strip()
        source_elem = item.find('source')
        source_name = source_elem.text.strip() if source_elem is not None and source_elem.text else ""

        if not title or not link:
            continue
        if "example.com" in link or "example.org" in link:
            continue
        title_clean = _strip_html(title)
        desc_clean = _strip_html(description)

        if not _is_drug_related(title_clean, desc_clean):
            continue
        if not _is_mongolia_related(title_clean, desc_clean):
            continue

        lang = "en"
        combined = title_clean + " " + desc_clean
        if any('А' <= c <= 'я' or c in 'өүӨҮ' for c in combined):
            lang = "mn"
        elif any('一' <= c <= '鿿' for c in combined):
            lang = "zh"

        articles.append({
            "news_title": title_clean[:300],
            "source_url": link,
            "publish_time": pub_date,
            "content_summary": desc_clean[:400],
            "source_name": source_name or extract_source_name(link),
            "language": lang,
            "site_category": "Google News",
        })

    return articles


async def _fetch_google_news(query: str) -> list[dict]:
    """从 Google News RSS 抓取真实文章"""
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en&gl=US&ceid=US:en"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return _parse_rss(resp.text)
            log.warning("Google News RSS %d for: %s", resp.status_code, query[:50])
            return []
    except Exception as e:
        log.warning("Google News RSS error for '%s': %s", query[:50], e)
        return []


def extract_source_name(url: str) -> str:
    for domain in TRUSTED_DOMAINS:
        if domain in url.lower():
            return domain.split(".")[0].upper() if domain.endswith((".org", ".int")) else domain.split(".")[0].title()
    return "国际新闻"


async def search_all_articles(progress_callback=None) -> list[dict]:
    """
    主入口：并行执行 AI 搜索 + Google News RSS 搜索。
    Google News RSS 返回真实原文链接，AI 搜索补充覆盖广度。
    progress_callback(phase, current, total, article_count, msg)
    """
    all_articles = []
    seen_urls = set()
    lock = asyncio.Lock()

    # AI 搜索用 semaphore 限流，RSS 不限
    ai_sem = asyncio.Semaphore(3)
    ai_total = len(SEARCH_QUERIES) if DEEPSEEK_SEARCH_AVAILABLE else 0
    rss_total = len(GOOGLE_NEWS_QUERIES)
    total_tasks = ai_total + rss_total
    completed = 0

    if total_tasks == 0:
        log.warning("无可用搜索源")
        if progress_callback:
            await progress_callback("search_engine", 0, 0, 0, "无可用搜索源")
        return []

    async def _add_articles(new_articles: list[dict], label: str):
        nonlocal completed
        async with lock:
            count_before = len(all_articles)
            for a in new_articles:
                url = a.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)
            added = len(all_articles) - count_before
            completed += 1
            current_count = len(all_articles)
        log.info("%s: +%d 篇 (累计 %d)", label, added, current_count)
        if progress_callback:
            await progress_callback(
                "search_engine", completed, total_tasks, current_count,
                f"搜索 {completed}/{total_tasks}：+{added} 篇，累计 {current_count} 篇"
            )

    async def _run_ai(i: int, query: str):
        async with ai_sem:
            raw, search_results = await _call_deepseek(query)
        articles = []
        if raw:
            articles = _parse_json_response(raw)
        # 同时加入从 API 响应提取的真实搜索结果
        if search_results:
            for sr in search_results:
                sr_url = sr.get("source_url", "")
                sr_title = sr.get("news_title", "")
                if sr_url and sr_title and _is_drug_related(sr_title, "") and _is_mongolia_related(sr_title, ""):
                    articles.append({
                        "news_title": sr_title,
                        "source_url": sr_url,
                        "publish_time": "",
                        "content_summary": "",
                        "source_name": extract_source_name(sr_url),
                        "language": "en",
                        "site_category": "搜索引擎发现",
                    })
        await _add_articles(articles, f"AI {i + 1}/{ai_total}")

    async def _run_rss(i: int, query: str):
        articles = await _fetch_google_news(query)
        await _add_articles(articles, f"RSS {i + 1}/{rss_total}")

    tasks = []
    for i, q in enumerate(SEARCH_QUERIES):
        if DEEPSEEK_SEARCH_AVAILABLE:
            tasks.append(_run_ai(i, q))
    for i, q in enumerate(GOOGLE_NEWS_QUERIES):
        tasks.append(_run_rss(i, q))

    await asyncio.gather(*tasks)

    log.info("总计: %d 篇涉毒文章 (AI+RSS)", len(all_articles))
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
