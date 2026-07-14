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

# 延迟加载以避免循环导入，在 _discover_articles 中首次引用时赋值
_STRONG_DRUG_WORDS = None


def _get_drug_keywords():
    global _STRONG_DRUG_WORDS
    if _STRONG_DRUG_WORDS is None:
        from modules.filter_module import STRONG_DRUG_WORDS as sdw
        _STRONG_DRUG_WORDS = list(sdw)
    return _STRONG_DRUG_WORDS

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
_DATA_DIR = Path("/tmp/data") if os.environ.get("VERCEL") == "1" else BASE_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

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


def _quick_keyword_check(title: str) -> bool:
    """快速标题关键词预筛，过滤明显无关的结果"""
    drug_signals = [
        "drug", "narcotic", "trafficking", "seizure", "bust", "smuggling",
        "opioid", "fentanyl", "meth", "cocaine", "heroin", "cannabis",
        "cartel", "arrest", "raid", "anti-drug", "organized crime", "illicit",
        "UNODC", "interpol", "methamphetamine", "ecstasy", "amphetamine",
        "drug lord", "drug dealer", "drug ring", "drug network",
        "хар тамхи", "мансууруулах", "наркотик", "фентанил",
        "психотроп", "каннабис", "марихуан", "кокаин", "гаалийн",
        "毒品", "贩毒", "缉毒", "禁毒", "走私毒品", "跨境贩毒",
        "吸毒", "海洛因", "冰毒", "吗啡", "摇头丸", "查获", "缴获", "抓捕", "捣毁",
    ]
    title_lower = title.lower()
    return any(sig in title_lower for sig in drug_signals)


def get_all_sites() -> list[dict]:
    all_sites = []
    for cat_key, category in SITES_CONFIG["categories"].items():
        for site in category["sites"]:
            site_info = dict(site)
            site_info["category_key"] = cat_key
            site_info["category_name"] = category["name"]
            all_sites.append(site_info)
    # 媒体站点优先（有 RSS、可达性高），再到政府/国际站点
    cat_order = {"media": 0, "government": 1, "ngo": 2, "international": 3}
    all_sites.sort(key=lambda s: cat_order.get(s.get("category", ""), 5))
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
        return _DATA_DIR / ".daily_counter.json"

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
        self.lock_path = _DATA_DIR / ".crawl.lock"

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
        self.checkpoint_path = _DATA_DIR / ".crawl_checkpoint.json"
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
        self.timeout = 8
        self.semaphore = asyncio.Semaphore(30)
        # 域名级别并发控制：montsame.mn 等站点有反爬，限制并发
        self._domain_semaphores = {
            "montsame.mn": asyncio.Semaphore(10),
            "see.mn": asyncio.Semaphore(10),
        }
        self.cancel_event = asyncio.Event()
        # 阶梯反爬：记录每个域名的连续失败次数，用于增加延迟
        self._domain_fail_count: dict[str, int] = {}
        self._domain_reachable: dict[str, bool] = {}  # 缓存可达性
        self._sampled_domains: set = set()  # 已完成ID采样的域名

    async def _progress(self, msg: str):
        if self.on_progress:
            await self.on_progress(msg)

    async def _article_callback(self, item: dict):
        if self.on_article:
            await self.on_article(item)

    async def _http_get(self, client: httpx.AsyncClient, url: str, max_retries: int = 2) -> Optional[str]:
        """执行 HTTP GET 请求，带指数退避重试。403 也重试（应对速率限制）"""
        parsed = urlparse(url)
        domain = parsed.netloc
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "mn-MN,mn;q=0.9,en-US;q=0.8,zh-CN;q=0.6",
            "Referer": f"{parsed.scheme}://{domain}/",
        }

        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200 and resp.text and len(resp.text) > 300:
                    self._domain_fail_count[domain] = 0
                    return resp.text
                if resp.status_code in (429, 503, 403):
                    wait = 2 ** attempt + random.uniform(0, 1)
                    log.debug("HTTP %d on %s, retry %d in %.1fs", resp.status_code, url[:80], attempt+1, wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (404,):
                    break  # 404 不重试
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
        策略：RSS（标题关键词预筛）→ 站内搜索 → 首页+列表页。
        RSS 优先，因为标题预筛能最快定位涉毒文章。
        """
        site_url = site.get("url", "").rstrip("/")
        domain = urlparse(site_url).netloc
        discovered = []
        drug_kw = _get_drug_keywords()

        # Phase 1: RSS（标题关键词预筛，最快定位涉毒文章）
        for rss_path in RSS_PATHS:
            if self.cancel_event.is_set():
                break
            rss_url = site_url + rss_path
            async with self.semaphore:
                await asyncio.sleep(get_delay())
                html = await self._http_get(client, rss_url)
            if html and ("<rss" in html.lower() or "<feed" in html.lower() or "<item>" in html or "<entry>" in html):
                # 用毒品关键词预筛 RSS 标题，只取相关链接
                links = _extract_rss_links_with_filter(html, site_url, drug_kw)
                for link in links:
                    if link not in discovered:
                        discovered.append(link)
                if len(discovered) >= 5:
                    break

        # Phase 1.5: montsame.mn 文章ID采样（首页只有当日新闻，ID采样可回溯90天）
        if "montsame.mn" in domain and len(discovered) < 5:
            sampled = await self._sample_montsame_ids(client, site_url, drug_kw)
            for link in sampled:
                if link not in discovered:
                    discovered.append(link)

        # Phase 1.6: see.mn 文章ID采样（URL 格式 see.mn/{id}.html，ID 递增）
        if "see.mn" in domain and len(discovered) < 5:
            sampled = await self._sample_see_ids(client, site_url, drug_kw)
            for link in sampled:
                if link not in discovered:
                    discovered.append(link)

        # Phase 2: 使用配置的搜索 URL，用毒品关键词搜索（扩大关键词数量）
        search_urls = site.get("search_urls", [])
        if search_urls and len(discovered) < 5:
            search_kws = [kw for kw in (keywords[:4] if keywords else []) if kw.strip()]
            for kw in search_kws:
                if self.cancel_event.is_set() or len(discovered) >= 5:
                    break
                for search_url in search_urls[:3]:
                    if self.cancel_event.is_set() or len(discovered) >= 5:
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

        # Phase 3: 不再回退到首页 — 搜索结果不足时直接返回已有链接，宁可少抓不可抓错
        return discovered[:8]

    async def _quick_check(self, site: dict) -> bool:
        """1.5 秒超时快速检查站点是否可达（失败不重试，不可达直接跳过）"""
        site_url = site.get("url", "").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=3, follow_redirects=True, verify=False) as client:
                resp = await client.get(site_url, headers={
                    "User-Agent": get_random_ua(),
                    "Accept": "text/html",
                })
                if 200 <= resp.status_code < 400:
                    return True
        except Exception:
            pass
        return False

    async def _sample_montsame_ids(self, client: httpx.AsyncClient, base_url: str, drug_keywords: list[str]) -> list[str]:
        """montsame.mn 专用：优先用法律/社会分类页发现涉毒文章，分类不足时回退 ID 采样。
        分类页每个有 ~120 篇文章 ID，标题命中率远高于随机采样。
        """
        discovered = []
        try:
            # 策略1: 分类页面扫描（法律=36 最相关，社会=6）
            category_ids = [36, 6]
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "text/html",
            }

            montsame_sem = self._domain_semaphores.get("montsame.mn", self.semaphore)

            async def _check_category(cat_id: int):
                if self.cancel_event.is_set() or len(discovered) >= 3:
                    return
                try:
                    resp = await client.get(f"{base_url}/mn/more/{cat_id}", headers=headers)
                    if resp.status_code != 200:
                        return
                    article_ids = list(dict.fromkeys(re.findall(r'/read/(\d+)', resp.text)))[:100]
                    batch_size = 10
                    for i in range(0, len(article_ids), batch_size):
                        if self.cancel_event.is_set() or len(discovered) >= 3:
                            return
                        batch = article_ids[i:i + batch_size]
                        async def _check_one(aid: str):
                            if self.cancel_event.is_set() or len(discovered) >= 3:
                                return
                            url = f"{base_url}/mn/read/{aid}"
                            async with montsame_sem:
                                html_text = await self._http_get(client, url)
                            if html_text:
                                snippet = html_text[:2000]
                                title_match = re.search(r'<title>(.*?)</title>', snippet, re.DOTALL)
                                title = title_match.group(1).strip() if title_match else ""
                                title = re.sub(r'<[^>]+>', '', title)
                                if any(kw.lower() in title.lower() for kw in drug_keywords):
                                    log.info("montsame.mn 分类%d命中: ID=%s — %s", cat_id, aid, title[:60])
                                    await self._progress(json.dumps({"type":"sampling_hit","site":"蒙通社MONTSAME","url":url,"title":title[:60]}))
                                    discovered.append(url)
                        await asyncio.gather(*[_check_one(aid) for aid in batch], return_exceptions=True)
                        if i + batch_size < len(article_ids):
                            await asyncio.sleep(0.03)
                except Exception as e:
                    log.debug("montsame 分类%d 异常: %s", cat_id, e)

            await self._progress(json.dumps({"type":"site_detail","site":"蒙通社MONTSAME","msg":f"分类扫描: 法律+社会"}))
            await asyncio.gather(*[_check_category(cid) for cid in category_ids], return_exceptions=True)

            # 策略2: 分类无结果时回退随机 ID 采样（有 1 篇就不回退，省时间做 Phase 2）
            if len(discovered) == 0:
                html = await self._http_get(client, base_url + "/mn/")
                if html:
                    ids = re.findall(r'/read/(\d+)', html)
                    if ids:
                        max_id = max(int(i) for i in ids)
                        min_id = max(0, max_id - 6000)
                        sample_size = min(100, max_id - min_id + 1)
                        sample_ids = random.sample(range(min_id, max_id + 1), sample_size)
                        await self._progress(json.dumps({"type":"site_detail","site":"蒙通社MONTSAME","msg":f"ID采样: {min_id}-{max_id}, {sample_size}个"}))
                        log.info("montsame ID采样: %d个, 范围 %d-%d", sample_size, min_id, max_id)

                        candidates = [f"{base_url}/mn/read/{aid}" for aid in sample_ids]

                        async def _check_sample(url: str):
                            if self.cancel_event.is_set() or len(discovered) >= 3:
                                return
                            async with montsame_sem:
                                html_text = await self._http_get(client, url)
                            if html_text and len(discovered) < 3:
                                snippet = html_text[:2000]
                                title_match = re.search(r'<title>(.*?)</title>', snippet, re.DOTALL)
                                title = title_match.group(1).strip() if title_match else ""
                                title = re.sub(r'<[^>]+>', '', title)
                                if any(kw.lower() in title.lower() for kw in drug_keywords):
                                    log.info("montsame ID采样命中: %s — %s", url.rsplit("/", 1)[-1], title[:60])
                                    await self._progress(json.dumps({"type":"sampling_hit","site":"蒙通社MONTSAME","url":url,"title":title[:60]}))
                                    discovered.append(url)

                        batch_size = 20
                        for i in range(0, len(candidates), batch_size):
                            if self.cancel_event.is_set() or len(discovered) >= 3:
                                break
                            batch = candidates[i:i + batch_size]
                            await asyncio.gather(*[_check_sample(u) for u in batch], return_exceptions=True)
                            if i + batch_size < len(candidates):
                                await asyncio.sleep(0.02)

        except Exception as e:
            log.warning("montsame.mn 采样异常: %s", e)
        return discovered

    async def _sample_see_ids(self, client: httpx.AsyncClient, base_url: str, drug_keywords: list[str]) -> list[str]:
        """see.mn 专用：随机采样文章 ID。URL 格式 see.mn/{id}.html。
        从首页获取最新 ID，在 6000 个 ID 范围内随机选 50 个，快速扫描。
        """
        discovered = []
        try:
            html = await self._http_get(client, base_url)
            if not html:
                log.warning("see.mn 首页获取失败")
                return discovered
            ids = re.findall(r'/(\d+)\.html', html)
            if not ids:
                log.warning("see.mn 首页无ID")
                return discovered
            max_id = max(int(i) for i in ids)
            min_id = max(0, max_id - 6000)
            sample_size = min(50, max_id - min_id + 1)
            sample_ids = random.sample(range(min_id, max_id + 1), sample_size)
            await self._progress(json.dumps({"type":"site_detail","site":"See.mn","msg":f"see.mn采样: {min_id}-{max_id}, {sample_size}个ID"}))
            log.info("see.mn 采样: 最新ID=%d, 范围 %d-%d, 采样%d", max_id, min_id, max_id, sample_size)

            see_sem = self._domain_semaphores.get("see.mn", self.semaphore)
            candidates = [f"{base_url}/{aid}.html" for aid in sample_ids]

            async def _check_one(url: str):
                if self.cancel_event.is_set() or len(discovered) >= 3:
                    return
                async with see_sem:
                    html_text = await self._http_get(client, url)
                if html_text and len(discovered) < 3:
                    snippet = html_text[:2000]
                    title_match = re.search(r'<title>(.*?)</title>', snippet, re.DOTALL)
                    title = title_match.group(1).strip() if title_match else ""
                    title = re.sub(r'<[^>]+>', '', title)
                    if any(kw.lower() in title.lower() for kw in drug_keywords):
                        log.info("see.mn 采样命中: ID=%s — %s", url.rsplit("/", 1)[-1], title[:60])
                        await self._progress(json.dumps({"type":"sampling_hit","site":"See.mn","url":url,"title":title[:60]}))
                        discovered.append(url)

            batch_size = 10
            for i in range(0, len(candidates), batch_size):
                if self.cancel_event.is_set() or len(discovered) >= 3:
                    break
                batch = candidates[i:i + batch_size]
                await asyncio.gather(*[_check_one(u) for u in batch], return_exceptions=True)
                if i + batch_size < len(candidates):
                    await asyncio.sleep(0.03)

        except Exception as e:
            log.warning("see.mn 采样异常: %s", e)
        return discovered

    async def _crawl_site(self, site: dict) -> list[dict]:
        """
        完整采集单个站点：发现 → 详情 → 解析 → 过滤。
        返回该站点采集到的所有情报。
        """
        site_name = site.get("name", "unknown")
        articles = []
        rejected_count = {"parse_fail": 0, "filter_fail": 0, "http_fail": 0}

        try:
            if not self.rate_limiter.can_fetch(site_name):
                await self._progress(json.dumps({"type":"site_skip","site":site_name,"reason":"日上限"}))
                return []

            # 快速可达性检查，跳过不可达站点
            reachable = await self._quick_check(site)
            if not reachable:
                await self._progress(json.dumps({"type":"site_skip","site":site_name,"reason":"不可达"}))
                return []

            keywords = get_keywords_for_site(site)
            remaining = self.rate_limiter.get_remaining(site_name)
            seen_urls = set()

            from modules.parser import parse_article_html
            from modules.filter_module import strict_filter

            await self._progress(json.dumps({"type":"site_start","site":site_name}))

            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, verify=False) as client:
                all_links = []
                try:
                    links = await self._discover_articles(client, site, keywords)
                except Exception as e:
                    log.warning("%s 链接发现异常: %s", site_name, e)
                    await self._progress(json.dumps({"type":"site_detail","site":site_name,"msg":f"发现异常: {str(e)[:80]}"}))
                    links = []

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

                    if self.checkpoint.is_crawled(article_url):
                        return

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
                        elif parsed:
                            rejected_count["filter_fail"] += 1
                            self.checkpoint.mark_crawled(article_url)
                        else:
                            rejected_count["parse_fail"] += 1
                            self.checkpoint.mark_crawled(article_url)
                    else:
                        rejected_count["http_fail"] += 1
                        self.checkpoint.mark_failed(article_url)

                # 并行抓取文章详情
                if all_links:
                    to_fetch = [l for l in all_links[:min(remaining, 8)]
                               if not self.checkpoint.is_crawled(l) and self.checkpoint.can_retry(l)]
                    if to_fetch:
                        tasks = [fetch_article(link) for link in to_fetch]
                        await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            log.error("%s 爬取异常: %s", site_name, e, exc_info=True)
            await self._progress(json.dumps({"type":"site_detail","site":site_name,"msg":f"爬取异常: {str(e)[:80]}"}))

        return articles, rejected_count

    async def crawl_all_streaming(self) -> dict:
        """并行采集所有站点，含搜索引擎预发现 + 流式输出结果。
        Vercel 上 RSS 与传统爬虫并行运行，共享 10s 窗口。
        """
        if not self.lock.acquire():
            return {"error": "采集锁被占用"}

        all_sites = get_all_sites()
        total_sites = len(all_sites)
        site_results = {}
        total_articles = 0
        _ON_VERCEL = os.environ.get("VERCEL", "") == "1"

        await self._progress(json.dumps({"type":"crawl_start","total_sites":total_sites}))

        # 统一回调：文章立即推送 SSE（RSS 搜索引擎 + 站点爬虫共用）
        # 需要 strict_filter 过滤，避免非蒙古/非毒品新闻混入
        from modules.filter_module import strict_filter as _sf

        async def on_article_all(article: dict):
            if self.cancel_event.is_set():
                return
            url = article.get("source_url", "")
            title = article.get("news_title", "")
            if not title or len(title) < 5:
                return
            if url:
                self.checkpoint.mark_crawled(url)
            # RSS 搜索引擎返回的文章也必须经过 strict_filter，过滤掉非蒙古/非毒品新闻
            if not _sf(article):
                return
            nonlocal total_articles
            total_articles += 1
            await self._article_callback(article)

        async def search_progress(phase, current, total, article_count, msg):
            await self._progress(json.dumps({
                "type": "search_progress", "phase": phase,
                "current": current, "total": total,
                "article_count": article_count, "msg": msg,
            }))

        try:
            from modules.search_engines import search_all_articles

            if _ON_VERCEL:
                # ============================================================
                # Vercel 模式: RSS + 传统爬虫并行，共享 9s 总超时
                # ============================================================
                rss_task = asyncio.create_task(
                    search_all_articles(progress_callback=search_progress, on_article=on_article_all)
                )
                crawl_task = asyncio.create_task(
                    self._crawl_all_sites_fast(all_sites, site_results, on_article_all)
                )

                await self._progress(json.dumps({"type":"phase","phase":"all","msg":"RSS + 19站点并行爬取中..."}))

                done, pending = await asyncio.wait(
                    [rss_task, crawl_task],
                    timeout=9,
                    return_when=asyncio.ALL_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                # 收集 RSS 结果用于日志
                try:
                    rss_result = rss_task.result()
                    log.info("RSS 搜索: %d 篇", len(rss_result))
                except Exception:
                    pass
                await self._progress(json.dumps({
                    "type":"search_done","total_urls":total_articles
                }))
            else:
                # ============================================================
                # 非 Vercel 模式: RSS 先跑，再跑传统爬虫
                # ============================================================
                await self._progress(json.dumps({"type":"phase","phase":"search_engine","msg":"RSS 新闻检索中..."}))
                search_articles = await search_all_articles(
                    progress_callback=search_progress, on_article=on_article_all
                )
                log.info("RSS 搜索: %d 篇(过滤前), 通过过滤: %d 篇", len(search_articles), total_articles)
                await self._progress(json.dumps({"type":"search_done","total_urls":len(search_articles),"filtered":total_articles}))

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
                    tasks = [asyncio.ensure_future(self._crawl_site(s)) for s in batch]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for site, result in zip(batch, results):
                        if isinstance(result, BaseException):
                            log.error("%s 采集异常: %s", site.get("name","?"), result, exc_info=result if not isinstance(result, KeyboardInterrupt) else False)
                            result = []
                        if isinstance(result, tuple) and len(result) == 2:
                            result_articles, rejected = result
                            site_results[site["name"]] = len(result_articles)
                            total_articles += len(result_articles)
                        elif isinstance(result, list):
                            site_results[site["name"]] = len(result)
                            total_articles += len(result)
                        else:
                            site_results[site["name"]] = 0
                        await self._progress(json.dumps({
                            "type":"site_done","site":site["name"],
                            "articles":site_results[site["name"]],
                        }))
                    await self._progress(json.dumps({
                        "type":"batch_done","batch":batch_num,"total_batches":total_batches,
                        "total_articles":total_articles
                    }))

            await self._progress(json.dumps({
                "type":"crawl_done","total_sites":total_sites,"total_articles":total_articles
            }))

        except Exception as e:
            log.warning("采集异常: %s", e)
        finally:
            self.lock.release()

        return {"total_articles": total_articles, "total_sites": total_sites, "site_results": site_results}

    async def _crawl_all_sites_fast(self, all_sites: list, site_results: dict, on_article):
        """Vercel 快速模式：所有 19 个站点并行爬取（主要用 RSS，跳过慢速检测）"""
        from modules.parser import parse_article_html
        from modules.filter_module import strict_filter

        sem = asyncio.Semaphore(30)  # 高并发

        async def _fast_crawl_one(site: dict):
            if self.cancel_event.is_set():
                return
            site_name = site["name"]
            site_url = site.get("url", "").rstrip("/")
            domain = urlparse(site_url).netloc
            drug_kw = _get_drug_keywords()

            try:
                async with httpx.AsyncClient(timeout=4, follow_redirects=True) as client:
                    # 优先 RSS
                    found_links = []
                    for rss_path in RSS_PATHS:
                        if len(found_links) >= 3:
                            break
                        try:
                            rss_url = site_url + rss_path
                            resp = await client.get(rss_url, headers={
                                "User-Agent": get_random_ua(),
                                "Accept": "text/xml,application/xml,*/*",
                            })
                            if resp.status_code == 200 and len(resp.text) > 200:
                                links = _extract_rss_links_with_filter(resp.text, site_url, drug_kw)
                                for l in links:
                                    if l not in found_links:
                                        found_links.append(l)
                        except Exception:
                            continue

                    # 兜底：首页提取链接
                    if len(found_links) < 2:
                        try:
                            resp = await client.get(site_url, headers={
                                "User-Agent": get_random_ua(),
                                "Accept": "text/html",
                            })
                            if resp.status_code == 200:
                                links = extract_article_links(resp.text, site_url, domain)
                                for l in links[:3]:
                                    if l not in found_links:
                                        found_links.append(l)
                        except Exception:
                            pass

                    # 抓取文章详情
                    articles_found = 0
                    for link in found_links[:5]:
                        if articles_found >= 3 or self.cancel_event.is_set():
                            break
                        try:
                            async with sem:
                                resp = await client.get(link, headers={
                                    "User-Agent": get_random_ua(),
                                    "Accept": "text/html",
                                })
                            if resp.status_code == 200 and resp.text:
                                parsed = parse_article_html(resp.text, link, site)
                                if parsed and strict_filter(parsed):
                                    articles_found += 1
                                    await on_article(parsed)
                        except Exception:
                            continue

                    if articles_found > 0:
                        site_results[site_name] = articles_found
                        await self._progress(json.dumps({
                            "type":"site_done","site":site_name,"articles":articles_found
                        }))
            except Exception:
                pass

        # 所有站点并行
        tasks = [asyncio.create_task(_fast_crawl_one(s)) for s in all_sites]
        await asyncio.gather(*tasks, return_exceptions=True)

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


def _extract_rss_links_with_filter(xml_text: str, base_url: str, drug_keywords: list[str]) -> list[str]:
    """从 RSS XML 中提取文章链接，只保留标题含毒品关键词的条目。
    同时返回其他条目（不限标题），但毒品相关条目优先排在前面。
    """
    drug_links = []
    other_links = []

    # 解析每个 <item> 条目
    items = re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL)
    if not items:
        items = re.findall(r'<entry>(.*?)</entry>', xml_text, re.DOTALL)

    for item in items:
        # 提取标题
        title_match = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""
        # 清理 CDATA 和 HTML
        title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', title)
        title = re.sub(r'<[^>]+>', '', title)

        # 提取链接
        link = ""
        link_match = re.search(r'<link>\s*(https?://[^<\s]+)\s*</link>', item)
        if link_match:
            link = link_match.group(1)
        else:
            # 尝试 ikon.mn 风格短链接: <link>https://ikon.mn/n/xxxx</link>
            # 或相对链接
            link_match = re.search(r'<link>(?!\s*https?://)([^<\s]+)</link>', item)
            if link_match:
                link = urljoin(base_url, link_match.group(1))

        if not link:
            # Atom: <link href="url"/>
            link_match = re.search(r'<link[^>]*href="(https?://[^"]+)"', item)
            if link_match:
                link = link_match.group(1)

        if not link:
            # GUID fallback
            guid_match = re.search(r'<guid[^>]*>(https?://[^<\s]+)</guid>', item)
            if guid_match:
                link = guid_match.group(1)

        if not link:
            continue

        # 标题关键词检查
        title_lower = title.lower()
        is_drug = any(kw.lower() in title_lower for kw in drug_keywords)
        if is_drug:
            drug_links.append(link)
        else:
            other_links.append(link)

    # 毒品相关优先，其他只取少量兜底（避免大量非涉毒文章涌入）
    result = drug_links + other_links[:3]
    return list(dict.fromkeys(result))[:10]


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


# ============================================================
# 批量站点爬取（适配 Vercel 10s 超时）
# ============================================================

async def crawl_sites_batch(site_names: list[str]) -> list[dict]:
    """爬取指定站点列表：RSS → 详情页 → 站内搜索 → 详情页。
    优先 RSS（快速），RSS 文章用 strict_filter 判断，不够时抓详情页丰富内容。
    无 RSS 站点用关键词搜索，然后抓详情页。适配 Vercel 10s 超时。
    """
    from modules.filter_module import strict_filter
    from modules.parser import parse_article_html

    all_sites = get_all_sites()
    sites_to_crawl = [s for s in all_sites if s["name"] in site_names]
    if not sites_to_crawl:
        return []

    articles: list[dict] = []
    seen: set[str] = set()
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(8)

    async def _fetch_detail(client: httpx.AsyncClient, url: str, site: dict) -> Optional[dict]:
        """抓取单篇文章详情页并解析"""
        try:
            async with sem:
                resp = await client.get(url, headers={
                    "User-Agent": get_random_ua(),
                    "Accept": "text/html,application/xhtml+xml,*/*",
                })
            if resp.status_code == 200 and resp.text and len(resp.text) > 300:
                parsed = parse_article_html(resp.text, url, site)
                if parsed and strict_filter(parsed):
                    return parsed
        except Exception:
            pass
        return None

    async def _crawl_one(site: dict):
        site_url = site.get("url", "").rstrip("/")
        site_name = site["name"]
        domain = urlparse(site_url).netloc
        found = 0  # 该站点已采集的文章数

        try:
            async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
                rss_all_items = []  # 从 RSS 提取的所有条目（未过滤）

                # === Step 1: RSS 快速提取 ===
                for rss_path in RSS_PATHS:
                    try:
                        resp = await client.get(site_url + rss_path, headers={
                            "User-Agent": get_random_ua(),
                            "Accept": "text/xml,application/xml,text/html,*/*",
                        })
                        if resp.status_code != 200 or len(resp.text) < 200:
                            continue
                        rss_all_items = _parse_rss_items(resp.text, site_url, site_name, site)
                        if rss_all_items:
                            break
                    except Exception:
                        continue

                # === Step 2: 先用 RSS 数据快速过滤（日期已标准化） ===
                rss_pass = []
                rss_fail = []
                for a in rss_all_items:
                    url = a.get("source_url", "")
                    if not url:
                        continue
                    if strict_filter(a):
                        rss_pass.append(a)
                    else:
                        rss_fail.append(a)

                async with lock:
                    for a in rss_pass:
                        url = a.get("source_url", "")
                        if url and url not in seen:
                            seen.add(url)
                            articles.append(a)
                            found += 1

                # === Step 3: RSS 未通过的，抓 2-3 个详情页获取完整内容 ===
                if found < 3 and rss_fail:
                    for a in rss_fail[:3]:
                        url = a.get("source_url", "")
                        async with lock:
                            if url in seen:
                                continue
                            seen.add(url)
                        detail = await _fetch_detail(client, url, site)
                        if detail:
                            async with lock:
                                articles.append(detail)
                                found += 1

                # === Step 4: 无 RSS 或结果不足，尝试站内搜索 ===
                if found < 2:
                    search_urls = site.get("search_urls", [])
                    drug_kw = _get_drug_keywords()
                    # 用最可能的毒品关键词搜索
                    search_kws = [kw for kw in drug_kw[:6] if len(kw) >= 4][:3]
                    if not search_kws:
                        search_kws = drug_kw[:2]

                    for kw in search_kws:
                        if found >= 3:
                            break
                        for search_url in search_urls[:2]:
                            if found >= 3:
                                break
                            try:
                                url = search_url.replace("{keyword}", quote(kw))
                            except Exception:
                                continue
                            try:
                                async with sem:
                                    resp = await client.get(url, headers={
                                        "User-Agent": get_random_ua(),
                                        "Accept": "text/html,*/*",
                                    })
                                if resp.status_code == 200:
                                    links = extract_article_links(resp.text, url, domain)
                                    for link in links[:3]:
                                        if found >= 3:
                                            break
                                        async with lock:
                                            if link in seen:
                                                continue
                                            seen.add(link)
                                        detail = await _fetch_detail(client, link, site)
                                        if detail:
                                            async with lock:
                                                articles.append(detail)
                                                found += 1
                            except Exception:
                                continue
        except Exception:
            pass

    tasks = [asyncio.create_task(_crawl_one(s)) for s in sites_to_crawl]
    try:
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=8)
    except asyncio.TimeoutError:
        log.warning("站点批次超时 8s: %s", site_names)

    return articles


def _normalize_rss_date(raw_date: str) -> str:
    """将 RSS/Atom 各种日期格式标准化为 YYYY-MM-DD"""
    from email.utils import parsedate_to_datetime as email_parse
    raw_date = raw_date.strip()
    if not raw_date:
        return ""

    # ISO 8601: 2026-07-14T10:30:00+08:00
    try:
        return raw_date[:10]
    except Exception:
        pass

    # RFC 2822: Mon, 14 Jul 2026 10:30:00 +0800
    try:
        return email_parse(raw_date).strftime("%Y-%m-%d")
    except Exception:
        pass

    # 各种数字格式
    for pat, fmt in [
        (r'(\d{4})\s*[年./]\s*(\d{1,2})\s*[月./]\s*(\d{1,2})', 'ymd'),
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'dmy'),
        (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', 'ymd'),
    ]:
        m = re.search(pat, raw_date)
        if m:
            try:
                if fmt == 'ymd':
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                else:
                    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
            except ValueError:
                continue

    return raw_date[:10] if len(raw_date) >= 10 else ""


def _parse_rss_items(xml_text: str, base_url: str, site_name: str, site: dict) -> list[dict]:
    """从 RSS/Atom XML 直接提取文章标题、摘要、链接，不额外发 HTTP 请求。"""
    import re
    from html import unescape

    items = []
    # 分割 <item> 或 <entry> 块
    raw_items = re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL)
    if not raw_items:
        raw_items = re.findall(r'<entry>(.*?)</entry>', xml_text, re.DOTALL)

    for raw in raw_items:
        # 标题
        title = ""
        tm = re.search(r'<title[^>]*>(.*?)</title>', raw, re.DOTALL)
        if tm:
            title = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', tm.group(1))
            title = re.sub(r'<[^>]+>', '', title).strip()
            title = unescape(title)

        # 链接
        link = ""
        lm = re.search(r'<link>\s*(https?://[^<\s]+)\s*</link>', raw)
        if lm:
            link = lm.group(1)
        if not link:
            lm = re.search(r'<link[^>]*href="(https?://[^"]+)"', raw)
            if lm:
                link = lm.group(1)
        if not link:
            lm = re.search(r'<guid[^>]*>(https?://[^<\s]+)</guid>', raw)
            if lm:
                link = lm.group(1)
        if not link:
            # ikon.mn 风格短链接
            lm = re.search(r'<link>\s*([^<\s]+)\s*</link>', raw)
            if lm:
                link = urljoin(base_url, lm.group(1).strip())

        if not link or not title:
            continue

        # 摘要
        desc = ""
        dm = re.search(r'<description[^>]*>(.*?)</description>', raw, re.DOTALL)
        if dm:
            desc = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', dm.group(1))
            desc = re.sub(r'<[^>]+>', '', desc).strip()
            desc = unescape(desc)
        if not desc:
            dm = re.search(r'<summary[^>]*>(.*?)</summary>', raw, re.DOTALL)
            if dm:
                desc = re.sub(r'<[^>]+>', '', dm.group(1)).strip()

        # 日期 — 标准化为 YYYY-MM-DD
        pub_date = ""
        dm = re.search(r'<pubDate[^>]*>(.*?)</pubDate>', raw, re.DOTALL)
        if dm:
            pub_date = _normalize_rss_date(dm.group(1).strip())
        if not pub_date:
            dm = re.search(r'<published[^>]*>(.*?)</published>', raw, re.DOTALL)
            if dm:
                pub_date = _normalize_rss_date(dm.group(1).strip())
        if not pub_date:
            dm = re.search(r'<updated[^>]*>(.*?)</updated>', raw, re.DOTALL)
            if dm:
                pub_date = _normalize_rss_date(dm.group(1).strip())

        # 来源
        source_name = site_name
        sm = re.search(r'<source[^>]*>(.*?)</source>', raw, re.DOTALL)
        if sm:
            source_name = sm.group(1).strip() or site_name

        # 语言检测
        combined = title + " " + desc
        lang = "en"
        if any('А' <= c <= 'я' or c in 'өүӨҮ' for c in combined):
            lang = "mn"
        elif any('一' <= c <= '鿿' for c in combined):
            lang = "zh"

        items.append({
            "news_title": title[:300],
            "source_url": link,
            "publish_time": pub_date,
            "content_summary": desc[:400],
            "source_name": source_name,
            "language": lang,
            "site_category": site_name,
        })

    return items[:10]  # 每个站点最多 10 篇
