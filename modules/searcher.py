"""
蒙古国涉毒新闻情报爬虫 - 搜索抓取模块
========================================
负责遍历所有配置站点，使用关键词检索涉毒新闻，
返回原始 HTML 供 parser 模块解析。

硬性规则：
- 所有站点无高低优先级，统一分配抓取页数
- 请求基础延迟 0.3s，随机抖动 0.5s
- 多组 PC+移动端 User-Agent 池轮换
- 单站点单日上限 30 条
- 取消额度预留逻辑，不因蒙古渠道消耗跳过中文口岸
"""

import asyncio
import json
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"

# 确保数据目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 加载站点配置
with open(CONFIG_DIR / "sites.json", "r", encoding="utf-8") as f:
    SITES_CONFIG = json.load(f)

# 加载关键词配置
with open(CONFIG_DIR / "keywords.json", "r", encoding="utf-8") as f:
    KEYWORDS_CONFIG = json.load(f)

CRAWL_SETTINGS = SITES_CONFIG["crawl_settings"]

# ============================================================
# User-Agent 池：PC + 移动端轮换，降低封禁风险
# ============================================================
USER_AGENTS = [
    # PC Chrome / Edge / Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    # 移动端
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.135 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
]


def get_random_ua() -> str:
    """从 UA 池随机获取一个 User-Agent"""
    return random.choice(USER_AGENTS)


def get_delay() -> float:
    """计算请求延迟：基础 0.3s + 随机抖动 0~0.5s"""
    return CRAWL_SETTINGS["base_delay_seconds"] + random.uniform(0, CRAWL_SETTINGS["random_jitter_seconds"])


def get_all_sites() -> list[dict]:
    """
    获取所有站点扁平化列表，无类别优先级区分。
    所有站点统一处理，不因蒙古渠道消耗额度跳过中文口岸资讯。
    """
    all_sites = []
    for cat_key, category in SITES_CONFIG["categories"].items():
        for site in category["sites"]:
            site_info = dict(site)
            site_info["category_key"] = cat_key
            site_info["category_name"] = category["name"]
            all_sites.append(site_info)
    return all_sites


def get_keywords_for_site(site: dict) -> list[str]:
    """
    根据站点语种返回对应关键词列表。
    合并 primary 和 secondary 关键词，primary 优先。
    """
    lang = site.get("language", "mn")
    kw = KEYWORDS_CONFIG["keywords"].get(lang, KEYWORDS_CONFIG["keywords"]["en"])
    return kw["primary"] + kw["secondary"]


class DailyRateLimiter:
    """
    单站点单日抓取上限控制。
    上限 30 条/站点/天，不限国别。
    """

    def __init__(self):
        self.counts: dict[str, dict[str, int]] = {}
        self._load()

    def _get_counter_path(self) -> Path:
        return DATA_DIR / ".daily_counter.json"

    def _load(self):
        counter_path = self._get_counter_path()
        if counter_path.exists():
            try:
                with open(counter_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                today = datetime.now().strftime("%Y-%m-%d")
                if data.get("date") == today:
                    self.counts = data.get("counts", {})
                else:
                    self.counts = {}
            except (json.JSONDecodeError, KeyError):
                self.counts = {}
        else:
            self.counts = {}

    def _save(self):
        counter_path = self._get_counter_path()
        with open(counter_path, "w", encoding="utf-8") as f:
            json.dump({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "counts": self.counts
            }, f, ensure_ascii=False, indent=2)

    def can_fetch(self, site_name: str) -> bool:
        """检查站点是否还有当日配额"""
        max_count = CRAWL_SETTINGS["max_articles_per_site_per_day"]
        current = self.counts.get(site_name, 0)
        return current < max_count

    def increment(self, site_name: str):
        """增加站点当日抓取计数"""
        self.counts[site_name] = self.counts.get(site_name, 0) + 1
        self._save()

    def get_remaining(self, site_name: str) -> int:
        """获取站点剩余配额"""
        max_count = CRAWL_SETTINGS["max_articles_per_site_per_day"]
        return max_count - self.counts.get(site_name, 0)


class CrawlLock:
    """
    采集锁机制：防止并发重复采集。
    若爬虫进程异常崩溃，锁 15 分钟后自动释放。
    """

    def __init__(self):
        self.lock_path = DATA_DIR / ".crawl.lock"

    def acquire(self) -> bool:
        """尝试获取锁，返回是否成功"""
        if self.lock_path.exists():
            mtime = self.lock_path.stat().st_mtime
            age_minutes = (time.time() - mtime) / 60
            if age_minutes < CRAWL_SETTINGS["lock_timeout_minutes"]:
                return False
            # 锁超时，自动释放
            self.release()
        self.lock_path.write_text(str(os.getpid()))
        return True

    def release(self):
        """释放锁"""
        if self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except OSError:
                pass

    def is_locked(self) -> bool:
        """检查锁状态"""
        if not self.lock_path.exists():
            return False
        mtime = self.lock_path.stat().st_mtime
        age_minutes = (time.time() - mtime) / 60
        if age_minutes >= CRAWL_SETTINGS["lock_timeout_minutes"]:
            return False
        return True


class SiteSearcher:
    """
    站点搜索器：对单个站点执行关键词检索。
    每个站点使用对应语种的关键词，尝试多种搜索 URL 模式。
    """

    def __init__(self, rate_limiter: DailyRateLimiter):
        self.rate_limiter = rate_limiter
        self.timeout = CRAWL_SETTINGS["request_timeout_seconds"]

    async def search_site(self, site: dict, keywords: list[str]) -> list[dict]:
        """
        对单个站点执行搜索，返回原始抓取结果列表。
        每个结果包含：html, site_info, keyword, search_url
        """
        results = []
        site_name = site["name"]

        if not self.rate_limiter.can_fetch(site_name):
            return results

        remaining = self.rate_limiter.get_remaining(site_name)

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True, verify=False) as client:
            for keyword in keywords[:8]:  # 每个站点使用前 8 个关键词（primary + 部分 secondary）
                if len(results) >= remaining:
                    break

                # 尝试站点的每种搜索 URL 模板
                for search_url_template in site.get("search_urls", []):
                    if len(results) >= remaining:
                        break

                    search_url = search_url_template.replace("{keyword}", keyword)

                    # 尝试直接访问首页作为备选
                    result = await self._fetch_url(client, search_url, site, keyword)
                    if result:
                        results.append(result)
                        self.rate_limiter.increment(site_name)

                    # 请求延迟
                    await asyncio.sleep(get_delay())

                # 也尝试首页抓取
                if len(results) < remaining and site.get("url"):
                    result = await self._fetch_url(client, site["url"], site, keyword)
                    if result:
                        results.append(result)
                        self.rate_limiter.increment(site_name)

        return results

    async def _fetch_url(
        self, client: httpx.AsyncClient, url: str, site: dict, keyword: str
    ) -> Optional[dict]:
        """执行单次 HTTP 请求，返回抓取结果或 None"""
        headers = {
            "User-Agent": get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "mn-MN,mn;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
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
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as e:
            # 连接失败或超时，静默跳过
            pass
        except Exception:
            pass

        return None


class CrawlCoordinator:
    """
    爬虫协调器：统一调度所有站点采集任务。
    无站点优先级区分，全站点平等分配资源。
    """

    def __init__(self):
        self.rate_limiter = DailyRateLimiter()
        self.searcher = SiteSearcher(self.rate_limiter)
        self.lock = CrawlLock()

    async def crawl_all_sites(self, progress_callback=None) -> list[dict]:
        """
        遍历所有站点执行采集，返回全部原始抓取结果。

        progress_callback: 可选回调函数，接收 (stage, site_name, count) 更新进度
        """
        if not self.lock.acquire():
            # 锁被占用且未超时
            return []

        try:
            all_results = []
            all_sites = get_all_sites()

            total_sites = len(all_sites)
            for idx, site in enumerate(all_sites):
                site_name = site["name"]

                if progress_callback:
                    progress_callback("crawling", site_name, idx + 1, total_sites)

                keywords = get_keywords_for_site(site)
                site_results = await self.searcher.search_site(site, keywords)
                all_results.extend(site_results)

            return all_results

        finally:
            self.lock.release()


# 同步包装器，方便直接调用
def run_crawl_sync() -> list[dict]:
    """同步执行全站采集"""
    coordinator = CrawlCoordinator()
    return asyncio.run(coordinator.crawl_all_sites())
