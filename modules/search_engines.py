"""
多搜索引擎发现模块 v2.0
========================
通过 Google News RSS + curl_cffi (Chrome TLS 指纹模拟) 搜索蒙古国涉毒新闻。
不需要 Rust 依赖，纯 Python 实现。

替代原来 ddgs (依赖 Rust primp) 的方案。
"""
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote

from modules.logger import get_logger

log = get_logger("search_engines")

# 30天前的日期
CUTOFF_DATE = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

# 蒙古国域名列表，用于过滤结果
MONGOLIA_DOMAINS = [
    "montsame.mn", "ikon.mn", "news.mn", "shuum.mn",
    "gogo.mn", "see.mn", "ubpost.mongolnews.mn",
    "customs.gov.mn", "mojha.gov.mn", "mohs.mn",
    "parliament.mn", "nfa.gov.mn", "police.gov.mn",
    "unodc.org", "interpol.int",
]

# 多语种搜索关键词组
SEARCH_QUERY_GROUPS = [
    # 英文 - Mongolia-specific drug queries
    [
        "Mongolia drug trafficking seizure",
        "Mongolia narcotics arrest bust",
        "Mongolia drug smuggling border",
        "Mongolia customs drug seizure",
        "Mongolia anti-drug operation",
        "Mongolia UNODC drug report",
        "Mongolia organized crime drug",
        "Mongolia methamphetamine seizure",
        "Mongolia cocaine smuggling arrest",
        "Mongolia drug crime statistics",
    ],
    # 蒙古文
    [
        "Монгол хар тамхи мансууруулах",
        "Монгол наркотик хууль бус",
        "Монгол гаалийн хар тамхи",
        "Монгол мансууруулах бодис хураагдсан",
    ],
    # 中文
    [
        "蒙古 毒品 贩毒 缉毒",
        "蒙古国 禁毒 毒品走私",
        "中蒙 跨境贩毒 毒品",
        "蒙古 海关 查获毒品",
    ],
]

# 毒品关键词，用于标题二次过滤
DRUG_TITLE_KEYWORDS = [
    # EN
    "drug", "narcotic", "trafficking", "seizure", "bust", "smuggling",
    "opioid", "fentanyl", "meth", "cocaine", "heroin", "cannabis",
    "cartel", "arrest", "raid", "operation", "anti-drug",
    "organized crime", "illicit", "UNODC", "interpol",
    "methamphetamine", "ecstasy", "amphetamine", "LSD", "MDMA",
    "drug lord", "drug dealer", "drug ring", "drug network",
    # MN
    "хар тамхи", "мансууруулах", "наркотик", "фентанил",
    "психотроп", "каннабис", "марихуан", "кокаин",
    "амфетамин", "MDMA", "гаалийн",
    # ZH
    "毒品", "贩毒", "缉毒", "禁毒", "走私毒品", "跨境贩毒",
    "吸毒", "海洛因", "冰毒", "吗啡", "摇头丸",
    "查获", "缴获", "抓捕", "捣毁",
]

# 非毒品关键词，用于排除
NON_DRUG_KEYWORDS = [
    "horse doping", "doping scandal", "sports doping",
    "performance-enhancing", "athlete", "olympic",
    "baseball", "football", "basketball", "soccer",
    "sumo wrestler", "wrestling", "boxing",
    "alcohol", "drunk driving", "DUI",
    "tobacco", "cigarette", "vaping",
    "pharmaceutical stock", "stock market", "IPO",
    "movie", "film", "TV show", "netflix",
    "music", "concert", "album",
    "recipe", "cooking", "food",
]


def _search_google_news(query: str, max_results: int = 20) -> list[dict]:
    """用 curl_cffi + Google News RSS 搜索，返回结果列表"""
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        log.warning("curl_cffi 未安装，跳过 Google News 搜索")
        return []

    results = []
    try:
        encoded_q = quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
        r = cffi_requests.get(url, impersonate="chrome124", timeout=15)

        if r.status_code != 200:
            return []

        items = re.findall(r"<item>(.*?)</item>", r.text, re.DOTALL)
        for item in items:
            if len(results) >= max_results:
                break

            t = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
            l = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
            s = re.search(r'<source[^>]*url="([^"]+)"', item)
            p = re.search(r"<pubDate>(.*?)</pubDate>", item, re.DOTALL)
            d = re.search(r"<description>(.*?)</description>", item, re.DOTALL)

            title = re.sub(r"<[^>]+>", "", t.group(1)).strip() if t else ""
            link = l.group(1).strip() if l else ""
            source_url = s.group(1) if s else ""
            pubdate = p.group(1).strip() if p else ""
            desc = re.sub(r"<[^>]+>", "", d.group(1)).strip() if d else ""

            if title and (source_url or link):
                results.append({
                    "url": source_url or link,
                    "title": title,
                    "body": desc,
                    "pubdate": pubdate,
                })

    except Exception as e:
        log.warning("Google News 搜索异常 [%s]: %s", query, e)

    return results


def _is_drug_related(title: str, body: str = "") -> bool:
    """检查标题/摘要是否涉毒"""
    text = (title + " " + body).lower()
    for kw in NON_DRUG_KEYWORDS:
        if kw in text:
            return False
    for kw in DRUG_TITLE_KEYWORDS:
        if kw.lower() in text:
            return True
    return False


def _is_mongolia_related(title: str, body: str = "", source_url: str = "") -> bool:
    """检查是否与蒙古国相关"""
    text = (title + " " + body + " " + source_url).lower()
    mongolia_signals = [
        "mongolia", "mongolian", "ulaanbaatar", "ulan bator",
        "монгол", "монголын", "улаанбаатар",
        "蒙古", "蒙古国",
    ]
    for sig in mongolia_signals:
        if sig in text:
            return True
    # 检查域名
    for domain in MONGOLIA_DOMAINS:
        if domain in source_url:
            return True
    return False


def search_all_sites() -> list[str]:
    """
    用 Google News RSS 对每组关键词搜索，返回所有涉毒文章 URL。
    """
    all_urls = set()
    total_queries = 0

    for group in SEARCH_QUERY_GROUPS:
        for query in group:
            try:
                results = _search_google_news(query, max_results=20)
                total_queries += 1
                for r in results:
                    url = r.get("url", "")
                    title = r.get("title", "")
                    body = r.get("body", "")
                    if url and url not in all_urls:
                        if _is_drug_related(title, body) and _is_mongolia_related(title, body, url):
                            all_urls.add(url)
                time.sleep(0.3)  # 请求间隔
            except Exception as e:
                log.warning("搜索失败 [%s]: %s", query, e)
                continue

    log.info("Google News 发现: %d次查询, 去重后 %d 个URL",
             total_queries, len(all_urls))
    return list(all_urls)


def search_mongolia_drug_news() -> list[dict]:
    """
    快速搜索蒙古国涉毒新闻，返回带标题和摘要的结果列表。
    """
    all_results = []
    seen_urls = set()

    broad_queries = [
        "Mongolia drug trafficking seizure 2026",
        "Mongolia narcotics arrest bust 2026",
        "Mongolia drug smuggling border customs",
        "Mongolia UNODC drug crime report",
        "Mongolia organized crime trafficking",
        "Mongolia methamphetamine cocaine seizure",
    ]

    for query in broad_queries:
        try:
            results = _search_google_news(query, max_results=20)
            for r in results:
                url = r.get("url", "")
                title = r.get("title", "")
                body = r.get("body", "")
                if url and url not in seen_urls:
                    if _is_drug_related(title, body) and _is_mongolia_related(title, body, url):
                        seen_urls.add(url)
                        all_results.append(r)
            time.sleep(0.3)
        except Exception as e:
            log.warning("快速搜索失败 [%s]: %s", query, e)

    log.info("Google News 快速搜索: %d 条结果", len(all_results))
    return all_results


def get_search_discovery_urls() -> list[str]:
    """
    对 crawler 的接口：返回搜索引擎发现的所有涉毒文章 URL。
    """
    urls = search_all_sites()
    if len(urls) < 10:
        log.info("site搜索仅 %d 个URL，补充broad search", len(urls))
        broad = search_mongolia_drug_news()
        for r in broad:
            if r["url"] not in urls:
                urls.append(r["url"])
    return list(set(urls))


# 兼容旧接口
def _search_ddg(query: str, max_results: int = 25) -> list[dict]:
    """旧接口兼容：内部调用 Google News RSS"""
    return _search_google_news(query, max_results)
