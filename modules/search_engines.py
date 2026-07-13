"""
搜索引擎发现模块 v6.2 — RSS 双引擎搜索（Vercel 优化）
======================================================
Bing News RSS 主力 + Google News RSS 补充，70+ 查询并行。
Vercel 10s 超时优化：8s 请求超时、8 并发限流。
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
_ON_VERCEL = os.environ.get("VERCEL", "") == "1"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 请求超时：Vercel 上 5s，其他环境 25s
RSS_TIMEOUT = 5 if _ON_VERCEL else 25
# 并发限制：Vercel 上 25（配合 5s 超时 = 10s 内完成），其他环境 50
RSS_CONCURRENCY = 25 if _ON_VERCEL else 50

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
# RSS 查询列表
# ============================================================

# Bing News 查询 — 主力引擎（Vercel 可达）
BING_QUERIES = [
    # 英文核心查询
    "mongolia drug trafficking narcotics seizure",
    "mongolia drug bust police arrest smuggle",
    "mongolia methamphetamine crystal meth synthetic",
    "mongolia narcotics border customs smuggling",
    "mongolia drug cartel organized crime syndicate",
    "mongolia UNODC drug control report",
    "mongolia INTERPOL drug operation",
    "mongolia drug addiction treatment harm reduction",
    "mongolia fentanyl ketamine psychoactive",
    "mongolia cross-border drug China Russia route",
    "mongolia heroin cocaine opioid seizure",
    "mongolia cannabis marijuana bust",
    "mongolia drug dealer arrest prosecution",
    "mongolia drug policy law reform",
    "mongolia synthetic drug precursor chemical",
    "mongolia anti-drug police raid campaign",
    "mongolia drug money laundering",
    "mongolia prison drug smuggling",
    "mongolia drug trafficking Central Asia route",
    "mongolia drug cooperation Russia China",
    "ulaanbaatar drug arrest police raid",
    "mongolia opiate narcotic painkiller abuse",
    "mongolia cocaine smuggling ring",
    "mongolia drug kingpin arrest",
    "mongolia drug production lab dismantled",
    "mongolia international drug ring busted",
    "mongolia drug mule courier arrested",
    "mongolia poppy opium cultivation",
    "mongolia ice drug methamphetamine",
    "mongolia drug crime statistics",
    # 蒙文核心查询
    "монгол хар тамхи мансууруулах бодис",
    "монгол наркотик наймаа хууль бус",
    "монгол мансууруулагч баривчилсан цагдаа",
    "монгол цагдаа хар тамхи хураагдсан",
    "монгол хил гааль хар тамхи саатуулах",
    "улаанбаатар хар тамхи баривчилгаа",
    "монгол героин кокаин хураагдсан",
    "монгол гэмт хэрэг хар тамхи бүлэглэл",
    "монгол мансууруулах бодис эмчилгээ",
    "хар тамхи хураалт монгол",
]

# Google News 查询 — 精简（Vercel 上 Google RSS 可能返回空）
GOOGLE_QUERIES = [
    "mongolia drug trafficking seizure",
    "mongolia methamphetamine bust",
    "mongolia narcotics smuggling",
    "Mongolia UNODC narcotics",
    "Mongolia INTERPOL drug",
    "mongolia drug cartel arrest",
    "mongolia fentanyl ketamine",
    "mongolia heroin cocaine",
    "ulaanbaatar drug police",
    "Mongolia drug smuggler arrested",
    "mongolia cannabis marijuana",
    "Mongolia drug crime",
    "монгол хар тамхи",
    "монгол наркотик",
    "монгол мансууруулах",
]


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def extract_source_name(url: str) -> str:
    for domain in TRUSTED_DOMAINS:
        if domain in url.lower():
            return domain.split(".")[0].upper() if domain.endswith((".org", ".int")) else domain.split(".")[0].title()
    return "国际新闻"


def _parse_rss(xml_text: str, feed_label: str = "RSS") -> list[dict]:
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
        if any(bad in link.lower() for bad in ["example.com", "example.org"]):
            continue
        if "news.google.com" in link.lower():
            continue

        title_clean = _strip_html(title)
        desc_clean = _strip_html(description)

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


async def _fetch_rss(query: str, engine: str = "google") -> tuple[list[dict], int]:
    if engine == "bing":
        url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss"
    else:
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"

    label = f"{engine.title()} News"
    try:
        async with httpx.AsyncClient(timeout=RSS_TIMEOUT, follow_redirects=True,
                                     headers={"User-Agent": BROWSER_UA}) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                body = resp.text
                if len(body) < 100:
                    return [], resp.status_code
                articles = _parse_rss(body, label)
                if articles:
                    log.info("%s +%d: %s", engine, len(articles), query[:60])
                return articles, resp.status_code
            log.debug("%s RSS %d: %s", engine, resp.status_code, query[:50])
            return [], resp.status_code
    except Exception as e:
        log.debug("%s RSS err: %s", engine, str(e)[:80])
        return [], 0


# ============================================================
# 主入口
# ============================================================

async def search_all_articles(progress_callback=None) -> list[dict]:
    """主入口：并行执行 Bing News + Google News RSS"""
    all_articles = []
    seen_urls = set()
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(RSS_CONCURRENCY)

    all_tasks = []
    for q in BING_QUERIES:
        all_tasks.append((q, "bing"))
    for q in GOOGLE_QUERIES:
        all_tasks.append((q, "google"))

    total = len(all_tasks)
    completed = [0]
    bing_hits = [0]
    google_hits = [0]

    async def _run_one(query: str, engine: str):
        async with sem:
            articles, status = await _fetch_rss(query, engine)
        async with lock:
            if articles:
                if engine == "bing":
                    bing_hits[0] += len(articles)
                else:
                    google_hits[0] += len(articles)
            for a in articles:
                url = a.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)
            completed[0] += 1
            current = len(all_articles)
        if progress_callback and completed[0] % 10 == 0:
            await progress_callback(
                "search_engine", completed[0], total, current,
                f"RSS {completed[0]}/{total}：累计 {current} 篇"
            )

    log.info("RSS 启动: %d Bing + %d Google (并发=%d, 超时=%ds)",
             len(BING_QUERIES), len(GOOGLE_QUERIES), RSS_CONCURRENCY, RSS_TIMEOUT)

    # Vercel 上给整个 RSS 阶段加 8 秒总超时，防止被平台杀掉
    rss_coro = asyncio.gather(*[_run_one(q, e) for q, e in all_tasks])
    if _ON_VERCEL:
        try:
            await asyncio.wait_for(rss_coro, timeout=8)
        except asyncio.TimeoutError:
            log.warning("RSS 总超时 8s，已获取 %d 篇", len(all_articles))
    else:
        await rss_coro

    log.info("RSS 完成: Bing=%d 篇, Google=%d 篇, 总计=%d 篇",
             bing_hits[0], google_hits[0], len(all_articles))
    return all_articles


def get_search_discovery_urls() -> list[dict]:
    return asyncio.run(search_all_articles())


def search_mongolia_drug_news() -> list[dict]:
    return asyncio.run(search_all_articles())
