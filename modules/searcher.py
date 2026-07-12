"""
蒙古国涉毒新闻情报爬虫 - 搜索抓取模块 v3.1
============================================
两阶段采集：
  Phase 1 发现：搜索/列表页 → 提取具体文章 URL
  Phase 2 详情：访问每篇文章页面 → 解析正文内容

保证 19 个站点全部遍历，不遗漏任何一个。
v3.1: 失败重试队列 + 断点续爬 + 阶梯反爬延迟
"""

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Awaitable
from urllib.parse import urljoin, urlparse, quote

import httpx

from modules.logger import get_logger

log = get_logger("searcher")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_DIR / "sites.json", "r", encoding="utf-8") as f:
    SITES_CONFIG = json.load(f)

with open(CONFIG_DIR / "keywords.json", "r", encoding="utf-8") as f:
    KEYWORDS_CONFIG = json.load(f)

CRAWL_SETTINGS = SITES_CONFIG["crawl_settings"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
]

# RSS 地址候选
RSS_PATHS = ["/rss", "/feed", "/rss.xml", "/feed.xml", "/atom.xml", "/feeds/posts/default", "/news/rss"]


def get_random_ua() -> str:
    return random.choice(USER_AGENTS)


def get_delay() -> float:
    return 0.01 + random.uniform(0, 0.03)


def get_all_sites() -> list[dict]:
    all_sites = []
    for cat_key, category in SITES_CONFIG["categories"].items():
        for site in category["sites"]:
            site_info = dict(site)
            site_info["category_key"] = cat_key
            site_info["category_name"] = category["name"]
            all_sites.append(site_info)
    return all_sites


def get_keywords_for_site(site: dict) -> list[str]:
    """获取站点的全部搜索关键词（primary + secondary + combined_phrases）"""
    lang = site.get("language", "mn")
    kw = KEYWORDS_CONFIG["keywords"].get(lang, KEYWORDS_CONFIG["keywords"]["en"])
    all_kw = list(kw.get("primary", [])) + list(kw.get("secondary", [])) + list(kw.get("combined_phrases", []))
    # 去重并保持顺序
    seen = set()
    unique = []
    for k in all_kw:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique


class DailyRateLimiter:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self._load()

    def _get_counter_path(self) -> Path:
        return DATA_DIR / ".daily_counter.json"

    def _load(self):
        p = self._get_counter_path()
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                    self.counts = data.get("counts", {})
            except Exception:
                pass

    def _save(self):
        with open(self._get_counter_path(), "w", encoding="utf-8") as f:
            json.dump({"date": datetime.now().strftime("%Y-%m-%d"), "counts": self.counts}, f, ensure_ascii=False)

    def can_fetch(self, site_name: str) -> bool:
        return self.counts.get(site_name, 0) < CRAWL_SETTINGS["max_articles_per_site_per_day"]

    def increment(self, site_name: str):
        self.counts[site_name] = self.counts.get(site_name, 0) + 1
        self._save()

    def get_remaining(self, site_name: str) -> int:
        return CRAWL_SETTINGS["max_articles_per_site_per_day"] - self.counts.get(site_name, 0)


class CrawlLock:
    def __init__(self):
        self.lock_path = DATA_DIR / ".crawl.lock"

    def _is_process_alive(self, pid: int) -> bool:
        """检查 PID 是否仍在运行"""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def acquire(self) -> bool:
        if self.lock_path.exists():
            try:
                content = self.lock_path.read_text().strip()
                if content.isdigit():
                    pid = int(content)
                    # 如果是同一个进程，直接返回 True（重入）
                    if pid == os.getpid():
                        return True
                    # 如果进程还活着且在超时内，拒绝
                    if self._is_process_alive(pid):
                        if (time.time() - self.lock_path.stat().st_mtime) / 60 < CRAWL_SETTINGS["lock_timeout_minutes"]:
                            return False
            except Exception:
                pass
            # 进程已死或超时，释放旧锁
            self.release()
        self.lock_path.write_text(str(os.getpid()))
        return True

    def release(self):
        if self.lock_path.exists():
            try:
                os.unlink(str(self.lock_path))
            except OSError:
                pass


class CrawlCheckpoint:
    """断点续爬：持久化记录已抓取 URL 和失败 URL 重试次数"""

    def __init__(self):
        self.checkpoint_path = DATA_DIR / ".crawl_checkpoint.json"
        self.crawled: set[str] = set()
        self.failed: dict[str, int] = {}  # url -> retry_count
        self._load()

    def _load(self):
        try:
            if self.checkpoint_path.exists():
                with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.crawled = set(data.get("crawled", []))
                self.failed = data.get("failed", {})
                # 清理超过 24h 的旧记录
                saved_time = data.get("timestamp", 0)
                if time.time() - saved_time > 86400:
                    self.crawled.clear()
                    self.failed.clear()
        except Exception:
            pass

    def _save(self):
        try:
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({
                    "crawled": list(self.crawled),
                    "failed": self.failed,
                    "timestamp": time.time(),
                }, f, ensure_ascii=False)
        except Exception:
            pass

    def is_crawled(self, url: str) -> bool:
        return url in self.crawled

    def mark_crawled(self, url: str):
        self.crawled.add(url)
        self.failed.pop(url, None)  # 成功后清除失败计数
        self._save()

    def can_retry(self, url: str, max_retries: int = 3) -> bool:
        return self.failed.get(url, 0) < max_retries

    def mark_failed(self, url: str):
        self.failed[url] = self.failed.get(url, 0) + 1
        if self.failed[url] >= 3:
            log.warning("URL 失败 %d 次，丢弃: %s", self.failed[url], url[:100])
        self._save()


# ============================================================
# Phase 1: 文章链接提取
# ============================================================

def extract_article_links(html: str, base_url: str, site_domain: str) -> list[str]:
    """
    从搜索页/列表页 HTML 中提取文章详情页 URL。
    使用多种策略确保不遗漏。
    """
    from bs4 import BeautifulSoup

    links = set()
    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(base_url).netloc or site_domain

    # 候选容器选择器（新闻列表常见结构）
    container_selectors = [
        "article", ".article", ".post", ".news-item", ".entry", ".story",
        ".news-list li", ".article-list li", ".posts li", ".entry-list li",
        "[class*='article']", "[class*='post']", "[class*='news']",
        ".list-item", ".card", ".item", ".row",
        "main a", "#content a", ".content a",
    ]

    for selector in container_selectors:
        try:
            for el in soup.select(selector):
                # 找容器内的所有链接
                for a in el.find_all("a", href=True):
                    href = a.get("href", "").strip()
                    if _is_valid_article_url(href, domain):
                        full_url = urljoin(base_url, href)
                        links.add(full_url)
        except Exception:
            continue

    # 如果容器选择器没找到，回退到全局链接扫描
    if len(links) < 2:
        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            text = a.get_text(strip=True)
            # 链接文本较长（可能是标题），且 URL 匹配文章特征
            if len(text) > 15 and _is_valid_article_url(href, domain):
                full_url = urljoin(base_url, href)
                links.add(full_url)

    # 最多返回 15 个链接
    return list(links)[:6]


def _is_valid_article_url(href: str, domain: str) -> bool:
    """判断 URL 是否是文章详情页"""
    if not href or href.startswith("#") or href.startswith("javascript:"):
        return False
    if href.startswith("mailto:") or href.startswith("tel:"):
        return False
    # 排除明显非文章链接
    skip_patterns = [
        "/search", "/login", "/register", "/about", "/contact",
        "/category", "/tag", "/author", "/page/", "/more/", "wp-admin",
        "/cdn-cgi", "#", "facebook.com", "twitter.com", "youtube.com",
    ]
    href_lower = href.lower()
    for p in skip_patterns:
        if p in href_lower:
            return False
    # URL 应包含域名或相对路径
    if href_lower.startswith("http") and domain not in href_lower:
        return False
    return True


# ============================================================
# Phase 2: 流式采集协调器
# ============================================================

class StreamingCrawlCoordinator:
    """
    两阶段高速并行爬虫协调器。
    Phase 1: 搜索/列表页 → 提取文章链接
    Phase 2: 访问文章详情页 → 解析 → 过滤 → 翻译 → 回调推送
    """

    def __init__(self, on_article: Optional[Callable[[dict], Awaitable[None]]] = None,
                 on_progress: Optional[Callable[[str], Awaitable[None]]] = None):
        self.rate_limiter = DailyRateLimiter()
        self.lock = CrawlLock()
        self.checkpoint = CrawlCheckpoint()
        self.on_article = on_article
        self.on_progress = on_progress
        self.timeout = 6
        self.semaphore = asyncio.Semaphore(20)
        self.cancel_event = asyncio.Event()
        # 阶梯反爬：记录每个域名的连续失败次数，用于增加延迟
        self._domain_fail_count: dict[str, int] = {}

    async def _progress(self, msg: str):
        if self.on_progress:
            await self.on_progress(msg)

    async def _article_callback(self, item: dict):
        if self.on_article:
            await self.on_article(item)

    async def _http_get(self, client: httpx.AsyncClient, url: str, max_retries: int = 3) -> Optional[str]:
        """执行 HTTP GET 请求，带指数退避重试"""
        domain = urlparse(url).netloc
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "mn-MN,mn;q=0.9,en-US;q=0.8,zh-CN;q=0.6",
        }

        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200 and resp.text and len(resp.text) > 300:
                    self._domain_fail_count[domain] = 0
                    return resp.text
                if resp.status_code in (429, 503):
                    wait = 2 ** attempt
                    log.debug("HTTP %d on %s, retry in %ds", resp.status_code, url[:80], wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (403, 404):
                    break  # 不重试 403/404
            except Exception:
                wait = 2 ** attempt
                await asyncio.sleep(wait)

        self._domain_fail_count[domain] = self._domain_fail_count.get(domain, 0) + 1
        return None

    def _get_backoff_delay(self, domain: str) -> float:
        """根据域名失败次数返回阶梯延迟"""
        fails = self._domain_fail_count.get(domain, 0)
        if fails == 0:
            return get_delay()
        return min(0.01 + fails * 0.5, 5.0) + random.uniform(0, 0.5)

    async def _discover_from_pages(self, client: httpx.AsyncClient, site: dict, urls: list[str]) -> list[str]:
        """从给定的页面 URL 列表中提取文章链接"""
        discovered = []
        domain = urlparse(site.get("url", "")).netloc
        for url in urls:
            async with self.semaphore:
                await asyncio.sleep(get_delay())
                html = await self._http_get(client, url)
            if html:
                links = extract_article_links(html, url, domain)
                discovered.extend(links)
        return list(dict.fromkeys(discovered))[:6]

    async def _discover_articles(self, client: httpx.AsyncClient, site: dict, keywords: list[str]) -> list[str]:
        """
        Phase 1: 从站点页面发现文章链接。
        策略：站内搜索（关键词）→ 首页+列表页 → RSS。
        用多个关键词逐个尝试搜索 URL，直到找到足够链接。
        """
        site_url = site.get("url", "").rstrip("/")
        domain = urlparse(site_url).netloc
        discovered = []

        # Phase 1: 使用配置的搜索 URL，用毒品关键词真正搜索
        search_urls = site.get("search_urls", [])
        if search_urls:
            for kw in (keywords[:3] if keywords else [""]):
                if not kw or self.cancel_event.is_set():
                    break
                for search_url in search_urls[:2]:
                    if self.cancel_event.is_set():
                        break
                    try:
                        url = search_url.replace("{keyword}", quote(kw))
                    except Exception:
                        url = search_url
                    async with self.semaphore:
                        await asyncio.sleep(get_delay())
                        html = await self._http_get(client, url)
                    if html:
                        links = extract_article_links(html, url, domain)
                        for link in links:
                            if link not in discovered:
                                discovered.append(link)
                    if len(discovered) >= 5:
                        break
                if len(discovered) >= 5:
                    break

        # Phase 2: 补充首页和新闻列表页
        pages_to_try = [site_url]
        for suffix in ["/news", "/mn", "/en", "/articles", "/archive",
                       "/news/all", "/category/news", "/mn/news", "/mn/read",
                       "/news/latest", "/latest", "/all-news"]:
            pages_to_try.append(site_url + suffix)

        homepage_links = await self._discover_from_pages(client, site, pages_to_try[:3])
        for link in homepage_links:
            if link not in discovered:
                discovered.append(link)

        # Phase 3: RSS 回退
        if len(discovered) < 2:
            for rss_path in RSS_PATHS[:2]:
                rss_url = site_url + rss_path
                async with self.semaphore:
                    await asyncio.sleep(get_delay())
                    html = await self._http_get(client, rss_url)
                if html and ("<rss" in html.lower() or "<feed" in html.lower() or "<item>" in html or "<entry>" in html):
                    links = _extract_rss_links(html, site_url)
                    for link in links:
                        if link not in discovered:
                            discovered.append(link)
                    break

        return discovered[:8]

    async def _crawl_site(self, site: dict) -> list[dict]:
        """
        完整采集单个站点：发现 → 详情 → 解析 → 过滤。
        返回该站点采集到的所有情报。
        """
        site_name = site["name"]
        if not self.rate_limiter.can_fetch(site_name):
            await self._progress(json.dumps({"type":"site_skip","site":site_name,"reason":"日上限"}))
            return []

        keywords = get_keywords_for_site(site)
        remaining = self.rate_limiter.get_remaining(site_name)
        articles = []
        seen_urls = set()

        from modules.parser import parse_article_html
        from modules.filter_module import strict_filter

        await self._progress(json.dumps({"type":"site_start","site":site_name}))

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            all_links = []
            links = await self._discover_articles(client, site, keywords)
            for link in links:
                if link not in seen_urls:
                    seen_urls.add(link)
                    all_links.append(link)

            await self._progress(json.dumps({"type":"site_discovery","site":site_name,"links":len(all_links)}))

            # Phase 2: 访问每个文章详情页
            async def fetch_article(article_url: str):
                if len(articles) >= remaining:
                    return
                if self.cancel_event.is_set():
                    return

                # 断点续爬：跳过已抓取的 URL
                if self.checkpoint.is_crawled(article_url):
                    return

                # 失败重试检查：超过 3 次的直接跳过
                if not self.checkpoint.can_retry(article_url, max_retries=3):
                    return

                domain = urlparse(article_url).netloc
                async with self.semaphore:
                    delay = self._get_backoff_delay(domain)
                    await asyncio.sleep(delay)
                    html = await self._http_get(client, article_url)

                if html:
                    parsed = parse_article_html(html, article_url, site)
                    if parsed and strict_filter(parsed):
                        articles.append(parsed)
                        self.rate_limiter.increment(site_name)
                        self.checkpoint.mark_crawled(article_url)
                        await self._article_callback(parsed)
                    else:
                        self.checkpoint.mark_crawled(article_url)
                else:
                    self.checkpoint.mark_failed(article_url)

            # 并行抓取文章详情
            if all_links:
                # 过滤掉已抓取和失败过多的
                to_fetch = [l for l in all_links[:min(remaining, 8)]
                           if not self.checkpoint.is_crawled(l) and self.checkpoint.can_retry(l)]
                if to_fetch:
                    tasks = [fetch_article(link) for link in to_fetch]
                    await asyncio.gather(*tasks, return_exceptions=True)

        return articles

    async def crawl_all_streaming(self) -> dict:
        """并行采集所有 19 个站点，流式输出结果"""
        if not self.lock.acquire():
            return {"error": "采集锁被占用"}

        all_sites = get_all_sites()
        total_sites = len(all_sites)
        site_results = {}
        total_articles = 0

        await self._progress(json.dumps({"type":"crawl_start","total_sites":total_sites}))

        try:
            batch_size = 10
            for i in range(0, total_sites, batch_size):
                if self.cancel_event.is_set():
                    break
                batch = all_sites[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (total_sites + batch_size - 1) // batch_size
                await self._progress(json.dumps({
                    "type":"batch_start","batch":batch_num,"total_batches":total_batches,
                    "sites":[s["name"] for s in batch]
                }))

                tasks = [self._crawl_site(site) for site in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for site, result in zip(batch, results):
                    result_count = len(result) if isinstance(result, list) else 0
                    site_results[site["name"]] = result_count
                    total_articles += result_count
                    await self._progress(json.dumps({
                        "type":"site_done","site":site["name"],"articles":result_count
                    }))

                await self._progress(json.dumps({
                    "type":"batch_done","batch":batch_num,"total_batches":total_batches,
                    "total_articles":total_articles
                }))

            await self._progress(json.dumps({
                "type":"crawl_done","total_sites":total_sites,"total_articles":total_articles
            }))

        finally:
            self.lock.release()

        return {"total_articles": total_articles, "total_sites": total_sites, "site_results": site_results}

    def stop(self):
        self.cancel_event.set()


# ============================================================
# RSS 链接提取
# ============================================================

def _extract_rss_links(xml_text: str, base_url: str) -> list[str]:
    """从 RSS/Atom XML 中提取文章链接"""
    links = []
    # RSS: <link>url</link>
    for m in re.finditer(r'<link>\s*(https?://[^<\s]+)\s*</link>', xml_text):
        links.append(m.group(1))
    # Atom: <link href="url"/>
    for m in re.finditer(r'<link[^>]*href="(https?://[^"]+)"', xml_text):
        links.append(m.group(1))
    # RSS <guid>
    for m in re.finditer(r'<guid[^>]*>(https?://[^<\s]+)</guid>', xml_text):
        links.append(m.group(1))
    if not links:
        # 简单的 URL 提取
        links = re.findall(r'https?://[^\s<>"]+', xml_text)
        links = [l for l in links if urlparse(base_url).netloc in l]
    return list(dict.fromkeys(links))[:15]


# ============================================================
# 兼容旧接口
# ============================================================

class CrawlCoordinator:
    """旧接口兼容，内部使用 StreamingCrawlCoordinator"""

    def __init__(self):
        self._coordinator = StreamingCrawlCoordinator()

    async def crawl_all_sites(self, progress_callback=None):
        results = []
        coordinator = StreamingCrawlCoordinator(
            on_article=lambda item: results.append(item),
            on_progress=lambda msg: progress_callback("progress", msg, 0, 0) if progress_callback else None
        )
        await coordinator.crawl_all_streaming()
        return results
