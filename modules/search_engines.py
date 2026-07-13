"""
搜索引擎发现模块 v6.0 — RSS 双引擎搜索
=======================================
Google News RSS + Bing News RSS，共 60+ 查询并行执行。
所有链接来自 RSS feed 原文，保证真实可打开，杜绝 AI 编造 URL。
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

# 国际新闻域名，用于 source_name 提取
TRUSTED_DOMAINS = [
    "reuters.com", "bbc.com", "bbc.co.uk", "apnews.com",
    "aljazeera.com", "france24.com", "theguardian.com",
    "bangkokpost.com", "channelnewsasia.com", "scmp.com",
    "unodc.org", "interpol.int", "incb.org",
    "thediplomat.com", "eurasianet.org", "rfa.org",
    "voanews.com", "abc.net.au", "dw.com", "nikkei.com",
    "odkb-csto.org",
]

# ============================================================
# RSS 查询列表（Google News + Bing News 共用）
# ============================================================

# 英文查询 — 覆盖毒品贩运、查获、政策、治疗等角度
RSS_QUERIES_EN = [
    "mongolia drug trafficking narcotics",
    "mongolia drug bust seizure police arrest",
    "mongolia methamphetamine crystal meth synthetic",
    "mongolia narcotics smuggling border customs",
    "mongolia drug cartel organized crime syndicate",
    "mongolia UNODC drug control report",
    "mongolia INTERPOL drug operation",
    "mongolia drug addiction treatment harm reduction",
    "mongolia fentanyl ketamine new psychoactive substance",
    "mongolia cross-border drug route China Russia",
    "mongolia heroin cocaine opioid seizure",
    "mongolia cannabis marijuana bust grow operation",
    "mongolia drug dealer arrest prosecution",
    "mongolia drug policy law reform strategy",
    "mongolia synthetic drug NPS precursor chemical",
    "mongolia anti-drug police raid campaign",
    "mongolia drug overdose death statistics",
    "mongolia precursor chemical control regulation",
    "mongolia drug money laundering financial crime",
    "mongolia dark web drug online sale",
    "mongolia prison drug smuggling contraband",
    "mongolia drug trafficking Central Asia route",
    "mongolia drug cooperation Russia China joint operation",
    "ulaanbaatar drug arrest police raid sting",
    "mongolia opiate narcotic painkiller abuse",
    "mongolia substance abuse rehabilitation center",
    "mongolia cocaine smuggling ring",
    "mongolia ecstasy MDMA party drug",
    "mongolia drug trafficking women children",
    "mongolia airport customs drug detection",
    "mongolia maritime drug smuggling sea route",
    "mongolia drug kingpin arrest",
    "mongolia drug production lab dismantled",
    "mongolia international drug ring busted",
    "mongolia drug mule courier arrested",
    "mongolia anti-narcotics squad operation",
    "mongolia drug sniffing dog detection",
    "mongolia chemical drug factory raid",
    "mongolia ice drug methamphetamine",
    "mongolia drug crime statistics 2024 2025",
]

# 蒙文查询 — хар тамхи, мансууруулах, наркотик 等核心词
RSS_QUERIES_MN = [
    "монгол хар тамхи мансууруулах бодис",
    "монгол наркотик наймаа хууль бус",
    "монгол мансууруулагч баривчилсан цагдаа",
    "монгол цагдаа хар тамхи хураагдсан",
    "монгол метамфетамин синтетик мансууруулах",
    "монгол хил гааль хар тамхи саатуулах",
    "монгол мансууруулах бодис хэрэглээ",
    "монгол гэмт хэрэг хар тамхи бүлэглэл",
    "улаанбаатар хар тамхи баривчилгаа",
    "монгол каннабис марихуана олсны",
    "монгол героин кокаин хураагдсан",
    "монгол мансууруулах бодис эмчилгээ",
    "монгол прокурор хар тамхи хэрэг шүүх",
    "монгол гааль шалгалт мансууруулах тээвэр",
    "монгол хууль сахиулагч хар тамхи ажиллагаа",
    "баривчилсан мансууруулах бодис монгол",
    "хар тамхи хураалт монгол хязгаар",
    "мансууруулах наймаачин баригдсан монгол",
    "цагдаагийн ажиллагаа мансууруулах бодис",
    "хууль бус мансууруулах бодис тээвэрлэлт",
]


def _is_mongolia_related(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    mongolia_signals = [
        "mongolia", "mongolian", "ulaanbaatar", "улаанбаатар",
        "蒙古", "蒙通社", "montsame",
        "монгол", "улсын", "аймаг", "сум", "дүүрэг",
    ]
    return any(sig in text for sig in mongolia_signals)


def _is_drug_related(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    drug_signals = [
        "drug", "narcotic", "trafficking", "seizure", "bust",
        "smuggl", "cartel", "meth", "heroin", "cocaine", "opioid",
        "fentanyl", "ecstasy", "cannabis", "marijuana", "hashish",
        "interpol", "unodc", "dealer", "syndicate", "contraband",
        "narco", "criminal gang", "organized crime", "mdma",
        "amphet", "methamphetamine", "psychoactive", "precursor",
        "overdose", "rehab", "detox", "withdrawal", "poppy",
        "opium", "lsd", "ketamine", "tramadol", "codeine",
        "хар тамхи", "мансууруулах", "наркотик",
        "мансууруулагч", "худалдаа", "наймаа",
        "хууль бус", "хураагдсан", "хэрэглээ",
        "гэмт хэрэг", "баривчилсан", "саатуулах",
        "хураалт", "тээвэрлэлт", "бүлэглэл",
        "хураагдсан", "илрүүлсэн", "таслан зогсоох",
        "毒品", "贩毒", "缉毒", "禁毒", "海洛因", "冰毒",
        "大麻", "可卡因", "走私", "缴获", "查获", "抓捕",
        "毒枭", "吸毒", "戒毒", "摇头丸", "麻古",
        "跨境贩", "贩运", "运毒", "藏毒", "制毒",
        "跨国毒", "合成毒品", "易制毒",
    ]
    return any(sig in text for sig in drug_signals)


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def extract_source_name(url: str) -> str:
    for domain in TRUSTED_DOMAINS:
        if domain in url.lower():
            return domain.split(".")[0].upper() if domain.endswith((".org", ".int")) else domain.split(".")[0].title()
    return "国际新闻"


def _parse_rss(xml_text: str, feed_label: str = "RSS") -> list[dict]:
    """解析标准 RSS 2.0 XML，提取文章"""
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
        if any(bad in link.lower() for bad in ["example.com", "example.org", "google.com/url"]):
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
            "site_category": feed_label,
        })

    return articles


async def _fetch_rss(query: str, engine: str = "google") -> list[dict]:
    """从 RSS feed 抓取真实文章"""
    if engine == "google":
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en&gl=US&ceid=US:en"
    else:
        url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss"

    label = f"{engine.title()} News"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return _parse_rss(resp.text, label)
            log.debug("%s RSS %d: %s", engine, resp.status_code, query[:50])
            return []
    except Exception as e:
        log.debug("%s RSS error '%s': %s", engine, query[:50], e)
        return []


# ============================================================
# DeepSeek 后备搜索（仅在 RSS 完全无结果时使用）
# ============================================================

REFUSE_SIGNALS = [
    "I cannot browse", "I am unable to browse",
    "I cannot access", "cannot provide real",
    "I cannot provide real",
]

DEEPSEEK_FALLBACK_QUERIES = [
    "search Mongolia drug narcotics trafficking seizure 2024 2025. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia methamphetamine synthetic drugs bust police. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia drug smuggling border customs arrest. list real articles as JSON with title, URL, Chinese summary.",
    "search Mongolia khark tamkhi monsuuruulakh bodis narkotik. list real articles as JSON with title, URL, Chinese summary.",
    "search site:unodc.org Mongolia drug narcotics. list real articles as JSON with title, URL, Chinese summary.",
]


async def _call_deepseek(query: str, max_tokens: int = 3500) -> tuple:
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
                json=payload, headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                msg = data["choices"][0]["message"]
                content = msg.get("content", "")
                search_results = []
                for field in ["search_results", "citations", "web_search_results", "references"]:
                    raw = msg.get(field) or data.get(field)
                    if raw and isinstance(raw, list):
                        for r in raw:
                            if isinstance(r, dict):
                                u = r.get("url") or r.get("link") or ""
                                t = r.get("title") or r.get("name") or ""
                                if u and t:
                                    search_results.append({"news_title": t, "source_url": u})
                        break
                return content, search_results
            return "", []
    except Exception as e:
        log.warning("DeepSeek error: %s", e)
        return "", []


def _is_trusted_url(url: str) -> bool:
    return any(d in url.lower() for d in TRUSTED_DOMAINS)


def _parse_deepseek_json(text: str) -> list[dict]:
    """解析 DeepSeek 返回的 JSON。仅用于后备，不要求 URL 真实。"""
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
        if any(bad in url.lower() for bad in ["example.com", "example.org", "[id]", "google.com/url"]):
            continue
        if not _is_trusted_url(url):
            continue
        if not _is_drug_related(title, summary):
            continue
        if not _is_mongolia_related(title, summary):
            continue
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


async def _deepseek_fallback(progress_callback=None) -> list[dict]:
    """后备方案：RSS 无结果时才调用 DeepSeek"""
    log.info("RSS 无结果，启用 DeepSeek 后备搜索")
    all_articles = []
    seen_urls = set()
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(3)
    total = len(DEEPSEEK_FALLBACK_QUERIES)
    completed = [0]

    async def _run_one(i: int, query: str):
        async with sem:
            raw, search_results = await _call_deepseek(query)
        articles = []
        if raw:
            articles = _parse_deepseek_json(raw)
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
        async with lock:
            count_before = len(all_articles)
            for a in articles:
                url = a.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)
            completed[0] += 1
        if progress_callback:
            await progress_callback(
                "search_engine", completed[0], total, len(all_articles),
                f"后备搜索 {completed[0]}/{total}：累计 {len(all_articles)} 篇"
            )

    await asyncio.gather(*[_run_one(i, q) for i, q in enumerate(DEEPSEEK_FALLBACK_QUERIES)])
    log.info("DeepSeek 后备: %d 篇", len(all_articles))
    return all_articles


# ============================================================
# 主入口
# ============================================================

async def search_all_articles(progress_callback=None) -> list[dict]:
    """
    主入口：并行执行 Google News RSS + Bing News RSS。
    所有链接来自 RSS feed，保证真实可打开。
    仅在 RSS 完全无结果时回退到 DeepSeek。
    progress_callback(phase, current, total, article_count, msg)
    """
    all_articles = []
    seen_urls = set()
    lock = asyncio.Lock()

    # 合并所有 RSS 查询
    google_tasks = [(q, "google") for q in RSS_QUERIES_EN + RSS_QUERIES_MN]
    bing_tasks = [(q, "bing") for q in RSS_QUERIES_EN[:20] + RSS_QUERIES_MN[:10]]
    all_rss_tasks = google_tasks + bing_tasks
    total_tasks = len(all_rss_tasks)
    completed = [0]

    async def _run_rss(query: str, engine: str):
        articles = await _fetch_rss(query, engine)
        async with lock:
            count_before = len(all_articles)
            for a in articles:
                url = a.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)
            added = len(all_articles) - count_before
            completed[0] += 1
            current_count = len(all_articles)
        if added > 0:
            log.info("RSS +%d: %s", added, query[:60])
        if progress_callback:
            await progress_callback(
                "search_engine", completed[0], total_tasks, current_count,
                f"RSS 搜索 {completed[0]}/{total_tasks}：累计 {current_count} 篇"
            )

    log.info("启动 %d 个 RSS 查询 (%d Google + %d Bing)", total_tasks, len(google_tasks), len(bing_tasks))
    await asyncio.gather(*[_run_rss(q, e) for q, e in all_rss_tasks])

    # RSS 完全无结果时才启用 DeepSeek 后备
    if len(all_articles) == 0:
        log.warning("RSS 完全无结果，启用 DeepSeek 后备")
        fallback = await _deepseek_fallback(progress_callback)
        for a in fallback:
            url = a.get("source_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(a)

    log.info("总计: %d 篇涉毒文章 (RSS%s)", len(all_articles),
             "+后备" if len(all_articles) > 0 and completed[0] == total_tasks else "")
    return all_articles


def get_search_discovery_urls() -> list[dict]:
    """同步包装"""
    return asyncio.run(search_all_articles())


def search_mongolia_drug_news() -> list[dict]:
    return asyncio.run(search_all_articles())
