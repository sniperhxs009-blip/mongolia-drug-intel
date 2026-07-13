"""
搜索引擎发现模块 v6.1 — RSS 双引擎搜索
=======================================
Google News RSS + Bing News RSS，共 90 个查询并行执行。
所有链接来自 RSS feed 原文，保证真实可打开。
DeepSeek 后备已彻底移除，宁缺毋滥。
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

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 国际化新闻域名，仅用于 source_name 展示
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
    "mongolia drug kingpin arrest",
    "mongolia drug production lab dismantled",
    "mongolia international drug ring busted",
    "mongolia drug mule courier arrested",
    "mongolia anti-narcotics squad operation",
    "mongolia drug sniffing dog detection",
    "mongolia chemical drug factory raid",
    "mongolia ice drug methamphetamine",
    "mongolia drug crime statistics 2024 2025",
    "mongolia poppy opium cultivation eradication",
]

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


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def extract_source_name(url: str) -> str:
    for domain in TRUSTED_DOMAINS:
        if domain in url.lower():
            return domain.split(".")[0].upper() if domain.endswith((".org", ".int")) else domain.split(".")[0].title()
    return "国际新闻"


def _parse_rss(xml_text: str, feed_label: str = "RSS") -> list[dict]:
    """解析 RSS 2.0 XML — 搜索词已限定主题，不再二次过滤"""
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
        # 去掉 Google News 自身重定向链接
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
    """从 RSS feed 抓取文章，返回 (articles, http_status)"""
    if engine == "google":
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en&gl=US&ceid=US:en"
    else:
        url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss"

    label = f"{engine.title()} News"
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                     headers={"User-Agent": BROWSER_UA}) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                body = resp.text
                if len(body) < 100:
                    log.warning("%s RSS 返回过短 (%d 字节): %s", engine, len(body), query[:60])
                    return [], resp.status_code
                articles = _parse_rss(body, label)
                if articles:
                    log.info("%s RSS +%d: %s", engine, len(articles), query[:60])
                return articles, resp.status_code
            log.warning("%s RSS HTTP %d: %s", engine, resp.status_code, query[:60])
            return [], resp.status_code
    except Exception as e:
        log.warning("%s RSS 异常 '%s': %s", engine, query[:60], e)
        return [], 0


# ============================================================
# 主入口
# ============================================================

async def search_all_articles(progress_callback=None) -> list[dict]:
    """
    主入口：并行执行 Google News RSS + Bing News RSS。
    所有链接来自 RSS feed，保证真实可打开。
    不启用任何 AI 后备——宁缺毋滥。
    """
    all_articles = []
    seen_urls = set()
    lock = asyncio.Lock()

    google_tasks = [(q, "google") for q in RSS_QUERIES_EN + RSS_QUERIES_MN]
    bing_tasks = [(q, "bing") for q in RSS_QUERIES_EN[:20] + RSS_QUERIES_MN[:10]]
    all_rss_tasks = google_tasks + bing_tasks
    total_tasks = len(all_rss_tasks)
    completed = [0]
    google_ok = [0]
    bing_ok = [0]

    async def _run_rss(query: str, engine: str):
        articles, status = await _fetch_rss(query, engine)
        async with lock:
            if status == 200:
                if engine == "google":
                    google_ok[0] += 1
                else:
                    bing_ok[0] += 1
            count_before = len(all_articles)
            for a in articles:
                url = a.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)
            added = len(all_articles) - count_before
            completed[0] += 1
            current_count = len(all_articles)
        if progress_callback:
            await progress_callback(
                "search_engine", completed[0], total_tasks, current_count,
                f"RSS {completed[0]}/{total_tasks}：累计 {current_count} 篇"
            )

    log.info("启动 %d RSS 查询 (Google: %d, Bing: %d)",
             total_tasks, len(google_tasks), len(bing_tasks))
    await asyncio.gather(*[_run_rss(q, e) for q, e in all_rss_tasks])

    log.info("RSS 完成: Google 成功 %d/%d, Bing 成功 %d/%d, 总文章 %d",
             google_ok[0], len(google_tasks), bing_ok[0], len(bing_tasks),
             len(all_articles))

    return all_articles


def get_search_discovery_urls() -> list[dict]:
    return asyncio.run(search_all_articles())


def search_mongolia_drug_news() -> list[dict]:
    return asyncio.run(search_all_articles())
