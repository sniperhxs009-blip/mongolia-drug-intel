"""
蒙古国涉毒新闻情报爬虫 - 搜索抓取模块
========================================
高速并行抓取，流式输出解析结果。
- 请求延迟 0.05s + 0.1s 抖动
- 10 并发同时抓取，5 站点并行
- 每条结果立即回调输出（用于 SSE 实时推送）
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable, Awaitable

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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
]


def get_random_ua() -> str:
    return random.choice(USER_AGENTS)


def get_delay() -> float:
    """请求延迟：基础 0.05s + 随机抖动 0~0.1s（高速模式）"""
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
    """单站点单日上限 30 条"""

    def __init__(self):
        self.counts: dict[str, int] = {}
        self._load()

    def _get_counter_path(self) -> Path:
        return DATA_DIR / ".daily_counter.json"

    def _load(self):
        counter_path = self._get_counter_path()
        if counter_path.exists():
            try:
                with open(counter_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
                    self.counts = data.get("counts", {})
                else:
                    self.counts = {}
            except (json.JSONDecodeError, KeyError):
                self.counts = {}

    def _save(self):
        with open(self._get_counter_path(), "w", encoding="utf-8") as f:
            json.dump({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "counts": self.counts
            }, f, ensure_ascii=False, indent=2)

    def can_fetch(self, site_name: str) -> bool:
        return self.counts.get(site_name, 0) < CRAWL_SETTINGS["max_articles_per_site_per_day"]

    def increment(self, site_name: str):
        self.counts[site_name] = self.counts.get(site_name, 0) + 1
        self._save()

    def get_remaining(self, site_name: str) -> int:
        return CRAWL_SETTINGS["max_articles_per_site_per_day"] - self.counts.get(site_name, 0)


class CrawlLock:
    """采集锁：15 分钟自动释放"""

    def __init__(self):
        self.lock_path = DATA_DIR / ".crawl.lock"

    def acquire(self) -> bool:
        if self.lock_path.exists():
            age = (time.time() - self.lock_path.stat().st_mtime) / 60
            if age < CRAWL_SETTINGS["lock_timeout_minutes"]:
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
# 流式采集协调器（高速并行 + 实时回调）
# ============================================================

class StreamingCrawlCoordinator:
    """
    高速并行爬虫协调器。
    - 10 并发 HTTP 请求（semaphore）
    - 5 站点同时采集
    - 每获取一页立即解析、过滤、回调（用于 SSE 推送）
    """

    def __init__(self, on_article: Optional[Callable[[dict], Awaitable[None]]] = None,
                 on_progress: Optional[Callable[[str], Awaitable[None]]] = None):
        """
        on_article: 每解析出一条情报时的异步回调
        on_progress: 进度更新回调
        """
        self.rate_limiter = DailyRateLimiter()
        self.lock = CrawlLock()
        self.on_article = on_article
        self.on_progress = on_progress
        self.timeout = 15  # 单请求超时
        self.semaphore = asyncio.Semaphore(10)  # 10 并发请求
        self.site_semaphore = asyncio.Semaphore(5)  # 5 站点并行
        self.cancel_event = asyncio.Event()

        # 延迟导入解析和过滤模块（避免循环引用）
        from modules.parser import parse_html_result
        from modules.filter_module import should_keep
        self.parse_html = parse_html_result
        self.should_keep = should_keep

    async def _progress(self, msg: str):
        if self.on_progress:
            await self.on_progress(msg)

    async def _article(self, item: dict):
        if self.on_article:
            await self.on_article(item)

    async def _fetch_url(self, client: httpx.AsyncClient, url: str, site: dict, keyword: str) -> Optional[dict]:
        """单次 HTTP 请求"""
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "mn-MN,mn;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200 and response.text and len(response.text) > 200:
                return {
                    "html": response.text,
                    "site_name": site["name"],
                    "site_url": site["url"],
                    "site_category": site.get("category", "unknown"),
                    "site_category_name": site.get("category_name", ""),
                    "language": site.get("language", "unknown"),
                    "keyword": keyword,
                    "fetch_url": url,
                    "fetch_time": datetime.now().isoformat(),
                }
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            pass
        except Exception:
            pass
        return None

    async def _crawl_site(self, site: dict) -> int:
        """
        采集单个站点：并行尝试多个搜索 URL。
        每取到一页立即解析、过滤、回调。
        返回成功入库条数。
        """
        site_name = site["name"]
        if not self.rate_limiter.can_fetch(site_name):
            return 0

        keywords = get_keywords_for_site(site)[:6]  # 每站点 6 个关键词
        remaining = self.rate_limiter.get_remaining(site_name)
        count = 0

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            # 为每个关键词创建一个抓取任务
            async def fetch_for_keyword(keyword: str):
                nonlocal count
                if count >= remaining:
                    return

                for search_url_template in site.get("search_urls", [])[:2]:  # 每站点限 2 个搜索 URL 模板
                    if count >= remaining:
                        return

                    search_url = search_url_template.replace("{keyword}", keyword)
                    async with self.semaphore:
                        if self.cancel_event.is_set():
                            return
                        await asyncio.sleep(get_delay())
                        raw = await self._fetch_url(client, search_url, site, keyword)

                    if raw:
                        # 立即解析
                        try:
                            parsed = self.parse_html(raw)
                            if parsed and self.should_keep(parsed):
                                self.rate_limiter.increment(site_name)
                                count += 1
                                await self._article(parsed)
                        except Exception:
                            pass

                # 也尝试首页
                if count == 0 and site.get("url"):
                    async with self.semaphore:
                        if not self.cancel_event.is_set():
                            await asyncio.sleep(get_delay())
                            raw = await self._fetch_url(client, site["url"], site, keyword)
                    if raw:
                        try:
                            parsed = self.parse_html(raw)
                            if parsed and self.should_keep(parsed):
                                self.rate_limiter.increment(site_name)
                                count += 1
                                await self._article(parsed)
                        except Exception:
                            pass

            # 并行执行所有关键词
            tasks = [fetch_for_keyword(kw) for kw in keywords]
            await asyncio.gather(*tasks, return_exceptions=True)

        return count

    async def crawl_all_streaming(self) -> dict:
        """
        并行采集所有站点，流式输出结果。
        返回统计摘要。
        """
        if not self.lock.acquire():
            return {"error": "采集锁被占用"}

        all_sites = get_all_sites()
        total_sites = len(all_sites)
        total_articles = 0
        site_results = {}

        await self._progress(f"开始并行采集 {total_sites} 个站点...")

        try:
            # 分批并行处理站点（每批 5 个）
            batch_size = 5
            for batch_start in range(0, total_sites, batch_size):
                if self.cancel_event.is_set():
                    break

                batch = all_sites[batch_start:batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                total_batches = (total_sites + batch_size - 1) // batch_size

                await self._progress(f"采集批次 {batch_num}/{total_batches} ({len(batch)} 站点并行)...")

                # 并行采集当前批次的所有站点
                tasks = [self._crawl_site(site) for site in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for site, result in zip(batch, results):
                    if isinstance(result, int):
                        site_results[site["name"]] = result
                        total_articles += result
                    elif isinstance(result, Exception):
                        site_results[site["name"]] = 0

            await self._progress(f"采集完成！共采集 {total_articles} 条情报。")

        finally:
            self.lock.release()

        return {
            "total_articles": total_articles,
            "total_sites": total_sites,
            "site_results": site_results,
        }

    def stop(self):
        """取消采集"""
        self.cancel_event.set()
