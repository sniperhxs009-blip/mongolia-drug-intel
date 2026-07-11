"""
蒙古国涉毒新闻情报爬虫 - 搜索抓取模块 v3.0
============================================
两阶段采集：
  Phase 1 发现：搜索/列表页 → 提取具体文章 URL
  Phase 2 详情：访问每篇文章页面 → 解析正文内容

保证 19 个站点全部遍历，不遗漏任何一个。
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
from urllib.parse import urljoin, urlparse

import httpx

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
    return 0.05 + random.uniform(0, 0.1)


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
    lang = site.get("language", "mn")
    kw = KEYWORDS_CONFIG["keywords"].get(lang, KEYWORDS_CONFIG["keywords"]["en"])
    return kw["primary"] + kw["secondary"]


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

    def acquire(self) -> bool:
        if self.lock_path.exists():
            if (time.time() - self.lock_path.stat().st_mtime) / 60 < CRAWL_SETTINGS["lock_timeout_minutes"]:
                return False
            self.release()
        self.lock_path.write_text(str(os.getpid()))
        return True

    def release(self):
        if self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                pass


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
    return list(links)[:15]


def _is_valid_article_url(href: str, domain: str) -> bool:
    """判断 URL 是否是文章详情页"""
    if not href or href.startswith("#") or href.startswith("javascript:"):
        return False
    if href.startswith("mailto:") or href.startswith("tel:"):
        return False
    # 排除明显非文章链接
    skip_patterns = [
        "/search", "/login", "/register", "/about", "/contact",
        "/category", "/tag", "/author", "/page/", "wp-admin",
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
        self.on_article = on_article
        self.on_progress = on_progress
        self.timeout = 15
        self.semaphore = asyncio.Semaphore(10)
        self.cancel_event = asyncio.Event()

    async def _progress(self, msg: str):
        if self.on_progress:
            await self.on_progress(msg)

    async def _article_callback(self, item: dict):
        if self.on_article:
            await self.on_article(item)

    async def _http_get(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        """执行 HTTP GET 请求，返回 HTML 文本"""
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "mn-MN,mn;q=0.9,en-US;q=0.8,zh-CN;q=0.6",
        }
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200 and resp.text and len(resp.text) > 300:
                return resp.text
        except Exception:
            pass
        return None

    async def _discover_articles(self, client: httpx.AsyncClient, site: dict, keyword: str) -> list[str]:
        """
        Phase 1: 从搜索/列表页发现文章链接。
        尝试搜索 URL → RSS → 首页。
        """
        discovered = []
        site_url = site.get("url", "")
        domain = urlparse(site_url).netloc

        # 1. 尝试搜索 URL
        for template in site.get("search_urls", [])[:2]:
            search_url = template.replace("{keyword}", keyword)
            async with self.semaphore:
                await asyncio.sleep(get_delay())
                html = await self._http_get(client, search_url)
            if html:
                links = extract_article_links(html, search_url, domain)
                discovered.extend(links)
                if len(discovered) >= 10:
                    break

        # 2. 尝试 RSS
        if len(discovered) < 3:
            for rss_path in RSS_PATHS:
                rss_url = site_url.rstrip("/") + rss_path
                async with self.semaphore:
                    await asyncio.sleep(get_delay())
                    html = await self._http_get(client, rss_url)
                if html and ("<rss" in html.lower() or "<feed" in html.lower() or "<item>" in html or "<entry>" in html):
                    links = _extract_rss_links(html, site_url)
                    discovered.extend(links)
                    break

        # 3. 尝试首页
        if len(discovered) < 2 and site_url:
            async with self.semaphore:
                await asyncio.sleep(get_delay())
                html = await self._http_get(client, site_url)
            if html:
                links = extract_article_links(html, site_url, domain)
                discovered.extend(links)

        # 去重
        return list(dict.fromkeys(discovered))[:12]

    async def _crawl_site(self, site: dict) -> list[dict]:
        """
        完整采集单个站点：发现 → 详情 → 解析 → 过滤。
        返回该站点采集到的所有情报。
        """
        site_name = site["name"]
        if not self.rate_limiter.can_fetch(site_name):
            await self._progress(f"  {site_name}: 已达日上限，跳过")
            return []

        keywords = get_keywords_for_site(site)[:5]
        remaining = self.rate_limiter.get_remaining(site_name)
        articles = []
        seen_urls = set()

        # 延迟导入
        from modules.parser import parse_article_html
        from modules.filter_module import strict_filter

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            # Phase 1: 发现文章链接
            all_links = []
            for kw in keywords:
                if len(all_links) >= remaining * 2:
                    break
                links = await self._discover_articles(client, site, kw)
                for link in links:
                    if link not in seen_urls:
                        seen_urls.add(link)
                        all_links.append(link)

            await self._progress(f"  {site_name}: 发现 {len(all_links)} 个文章链接，开始抓取详情...")

            # Phase 2: 访问每个文章详情页
            async def fetch_article(article_url: str):
                if len(articles) >= remaining:
                    return
                if self.cancel_event.is_set():
                    return

                async with self.semaphore:
                    await asyncio.sleep(get_delay())
                    html = await self._http_get(client, article_url)

                if html:
                    parsed = parse_article_html(html, article_url, site)
                    if parsed and strict_filter(parsed):
                        articles.append(parsed)
                        self.rate_limiter.increment(site_name)
                        await self._article_callback(parsed)

            # 并行抓取文章详情
            if all_links:
                tasks = [fetch_article(link) for link in all_links[:remaining * 2]]
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

        await self._progress(f"启动全站采集：{total_sites} 个站点，并行采集...")

        try:
            # 每批 5 个站点并行
            batch_size = 5
            for i in range(0, total_sites, batch_size):
                if self.cancel_event.is_set():
                    break
                batch = all_sites[i:i + batch_size]
                batch_num = i // batch_size + 1
                total_batches = (total_sites + batch_size - 1) // batch_size
                await self._progress(f"批次 {batch_num}/{total_batches}：{', '.join(s['name'] for s in batch)}")

                tasks = [self._crawl_site(site) for site in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for site, result in zip(batch, results):
                    if isinstance(result, list):
                        site_results[site["name"]] = len(result)
                        total_articles += len(result)
                    else:
                        site_results[site["name"]] = 0

            await self._progress(f"全部采集完成！{total_sites} 个站点，共采集 {total_articles} 条情报。")

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
