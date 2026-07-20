"""
Unified in-memory crawler for Mongolian news sites.
Articles cached in memory with JSON disk persistence.
Thread-safe. Used by auto-crawler, live fetch, drug filter, and index search.
"""
import json
import os
import re
import time
import threading
import concurrent.futures
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from translate import translate_articles_batch

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en;q=0.9,ru;q=0.7",
}

http_session = requests.Session()
http_session.headers.update(HEADERS)

# ---- In-memory article cache ----
_article_cache: dict[str, dict] = {}   # url -> article dict (preserves insertion order in Python 3.7+)
_seen_urls: set[str] = set()           # fast dedup
_cache_lock = threading.Lock()
_save_counter = 0                      # throttle saves

_DATA_DIR = "/data" if os.path.isdir("/data") else os.path.dirname(os.path.abspath(__file__))
_CACHE_PATH = os.path.join(_DATA_DIR, "article_cache.json")


def save_cache():
    """Persist in-memory cache to disk (atomic write)."""
    global _save_counter
    try:
        with _cache_lock:
            data = list(_article_cache.values())
        tmp = _CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _CACHE_PATH)
        _save_counter = 0
    except Exception as e:
        print(f"[缓存] 保存失败: {e}")


def load_cache():
    """Restore cache from disk on startup."""
    if not os.path.exists(_CACHE_PATH):
        return 0
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return 0
        restored = 0
        with _cache_lock:
            for art in data:
                url = art.get("url", "")
                if url and url not in _seen_urls:
                    _seen_urls.add(url)
                    _article_cache[url] = art
                    restored += 1
        if restored > 0:
            print(f"[缓存] 从磁盘恢复了 {restored} 篇文章")
        return restored
    except Exception as e:
        print(f"[缓存] 加载失败: {e}")
        return 0


def is_in_cache(url):
    return url in _seen_urls


def add_to_cache(article):
    """Thread-safe add. Returns True if new, False if duplicate. Auto-saves every 50 articles."""
    global _save_counter
    url = article["url"]
    with _cache_lock:
        if url in _seen_urls:
            return False
        _seen_urls.add(url)
        _article_cache[url] = article
        _save_counter += 1
        result = True
    if _save_counter >= 50:
        save_cache()
    return result


def get_cache_size():
    with _cache_lock:
        return len(_article_cache)


def get_cache_stats():
    """Return {source_label: count} for all cached articles."""
    with _cache_lock:
        sources = {}
        for art in _article_cache.values():
            src = art.get("source_label") or art.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
        return sources


def evict_old_articles(months=3):
    """Remove articles older than N months from cache."""
    cutoff = datetime.now() - timedelta(days=months * 30)
    with _cache_lock:
        to_remove = []
        for url, art in _article_cache.items():
            d = art.get("date", "")
            if not d:
                continue
            try:
                s = str(d)[:10].replace(".", "-").strip()
                m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
                if m:
                    dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    if dt < cutoff:
                        to_remove.append(url)
            except Exception:
                pass
        for url in to_remove:
            del _article_cache[url]
            _seen_urls.discard(url)
        if to_remove:
            print(f"[memory] Evicted {len(to_remove)} old articles, cache size: {len(_article_cache)}")


def get_cached_articles(source=None, months=None):
    """Get articles from in-memory cache, optionally filtered by source and age."""
    from copy import deepcopy
    cutoff = datetime.now() - timedelta(days=months * 30) if months else None
    with _cache_lock:
        results = []
        for art in _article_cache.values():
            if source and art.get("source") != source:
                continue
            if cutoff:
                d = art.get("date", "")
                if not d:
                    continue
                try:
                    s = str(d)[:10].replace(".", "-").strip()
                    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
                    if m:
                        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                        if dt < cutoff:
                            continue
                except Exception:
                    continue
            results.append(deepcopy(art))
        return results


# ---- Date helpers ----

def _is_within_months(date_str, months=3):
    """Check if a date string is within the given number of months from now."""
    if not date_str:
        return False
    try:
        s = str(date_str)[:10].replace(".", "-").strip()
        for fmt in [r"(\d{4})-(\d{2})-(\d{2})", r"(\d{2})-(\d{2})-(\d{4})"]:
            m = re.match(fmt, s)
            if m:
                if fmt.startswith(r"(\d{2})"):
                    y, mo, d = int(m.group(3)), int(m.group(2)), int(m.group(1))
                else:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(y, mo, d)
                cutoff = datetime.now() - timedelta(days=months * 30)
                return dt >= cutoff
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
        if m:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            cutoff = datetime.now() - timedelta(days=months * 30)
            return dt >= cutoff
        return False
    except Exception:
        return False


# ---- Article parser ----

def quick_parse(site, url, session=None):
    """Extract title, date, content from an article page. Returns dict or None."""
    s = session or http_session
    verify = site.get("ssl_verify", True)
    try:
        resp = s.get(url, timeout=5, allow_redirects=True, verify=verify)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    sel = site["article_selectors"]

    # Title
    title = ""
    if sel.get("title"):
        t = soup.select_one(sel["title"])
        if t:
            title = t.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)
    if not title:
        return None

    # Date extraction -- 4-stage fallback
    date = ""
    text = soup.get_text()

    # Stage 1: <meta> tag dates (highest quality)
    for meta_sel in ["meta[property='article:published_time']", "meta[name='date']",
                      "meta[name='pubdate']", "meta[name='publish_date']"]:
        meta = soup.select_one(meta_sel)
        if meta:
            content = meta.get("content", "")
            if content:
                # Try YYYY-MM-DD from meta
                m = re.search(r"(\d{4}-\d{2}-\d{2})", content)
                if m:
                    date = m.group(1)
                    break
                # Try ISO format
                m = re.search(r"(\d{4}-\d{2}-\d{2})T", content)
                if m:
                    date = m.group(1)
                    break

    # Stage 2: Site-specific regex from config
    if not date:
        date_regex = sel.get("date_regex")
        date_regex_fb = sel.get("date_regex_fallback")
        for p in [date_regex, date_regex_fb]:
            if not p:
                continue
            m = re.search(p, text)
            if m:
                d = m.group(1)
                df = site.get("date_format", "ymd")
                if df == "ymd":
                    date = d
                elif df == "ymd_hms":
                    date = d[:10]
                elif df == "ymd_slash":
                    date = d.replace("/", "-")
                elif df == "dmY_dot":
                    parts = d.split(".")
                    if len(parts) == 3:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif df == "text":
                    try:
                        date = datetime.strptime(d, "%d %B %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        try:
                            date = datetime.strptime(d, "%d %b %Y").strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                break
        if date:
            pass  # already set

    # Stage 3: Generic fallback patterns
    if not date:
        for pattern in [
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{4}\.\d{2}\.\d{2})",
            r"(\d{4}/\d{2}/\d{2})",
            r"(\d{2}\.\d{2}\.\d{4})",
            r"(\d{2}/\d{2}/\d{4})",
            r"(\d{1,2}\s+\w+\s+\d{4})",
        ]:
            m = re.search(pattern, text)
            if m:
                d = m.group(1)
                if "-" in d and d[2] == "-":
                    parts = d.split("-")
                    if len(parts) == 3 and len(parts[0]) == 2:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif "." in d and len(d.split(".")[0]) == 2:
                    parts = d.split(".")
                    if len(parts) == 3:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif "." in d:
                    date = d.replace(".", "-")
                elif "/" in d and d[2] == "/":
                    parts = d.split("/")
                    if len(parts) == 3 and len(parts[0]) == 2:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif "/" in d:
                    date = d.replace("/", "-")
                elif " " in d:
                    try:
                        date = datetime.strptime(d, "%d %B %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        try:
                            date = datetime.strptime(d, "%d %b %Y").strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                else:
                    date = d
                break

    # Stage 4: Mongolian date fallback
    if not date:
        mn_months = {
            "нэгдүгээр": "01", "хоёрдугаар": "02", "гуравдугаар": "03",
            "дөрөвдүгээр": "04", "тавдугаар": "05", "зургаадугаар": "06",
            "долдугаар": "07", "долоодугаар": "07", "наймдугаар": "08",
            "есдүгээр": "09", "аравдугаар": "10",
            "арван нэгдүгээр": "11", "арван хоёрдугаар": "12",
        }
        m = re.search(r'(\d{4})\s*оны\s*(\d{1,2})\s*(?:дугаар|дүгээр|-р)\s*сарын\s*(\d{1,2})', text)
        if m:
            date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        else:
            mn_names = "|".join(mn_months.keys())
            m = re.search(rf'(\d{{4}})\s*оны\s*({mn_names})\s*сарын\s*(\d{{1,2}})', text)
            if m:
                mn = mn_months.get(m.group(2).lower(), "")
                if mn:
                    date = f"{m.group(1)}-{mn}-{m.group(3).zfill(2)}"

    # Content extraction -- 4-stage fallback
    content_parts = []
    if sel.get("content"):
        for p in soup.select(sel["content"]):
            txt = p.get_text(strip=True)
            if txt and len(txt) > 5:
                content_parts.append(txt)

    if not content_parts:
        main_content = None
        for container_sel in ["article", ".article-content", ".news-content", ".post-content",
                               ".content", ".entry-content", ".html-body", "#content",
                               ".story-content", ".field-body", ".read-content", "main",
                               "[role='main']", ".post-body", ".detail-content"]:
            main_content = soup.select_one(container_sel)
            if main_content:
                break
        if main_content:
            for p in main_content.find_all("p"):
                txt = p.get_text(strip=True)
                if txt and len(txt) > 20:
                    content_parts.append(txt)

    if not content_parts:
        body = soup.find("body")
        if body:
            for p in body.find_all("p"):
                txt = p.get_text(strip=True)
                if len(txt) > 40:
                    content_parts.append(txt)
            if content_parts:
                content_parts.sort(key=len, reverse=True)
                content_parts = content_parts[:5]

    content = "\n".join(content_parts[:10]) if content_parts else title

    return {
        "source": site["name"],
        "source_label": site["label"],
        "title": title,
        "content": content,
        "date": date,
        "category": "",
        "url": url,
    }


# ---- Crawl engine ----

def crawl_site(site, session=None, max_articles=200, months=3, max_seconds=None, max_pages=None):
    """Full-coverage crawl: paginate until articles are older than cutoff, or no more pages.

    Args:
        max_seconds: Per-site time limit in seconds (None = unlimited, for background crawler)
        max_pages: Max pages to crawl (None = 20 for full coverage, lower for live fetch)
    Returns (articles_list, new_count)."""
    s = session or http_session
    verify = site.get("ssl_verify", True)
    sel = site.get("list_selectors", {})
    paginate = site.get("paginate")
    news_list = site.get("news_list")
    t0 = time.time()

    new_count = 0
    articles = []
    seen_this_run = set()
    newly_parsed = []  # track for batch translation
    newest_date = ""   # track date range for logging
    oldest_date = ""

    pg_param = paginate.get("param", "page") if paginate else "page"
    pg_start = paginate.get("start", 1) if paginate else 1
    # Take the MINIMUM: explicit max_pages, site paginate.max, or default 20
    limit_from_site = paginate.get("max") if paginate else None
    if max_pages is not None:
        max_safe_pages = min(max_pages, limit_from_site) if limit_from_site else max_pages
    elif limit_from_site:
        max_safe_pages = limit_from_site
    else:
        max_safe_pages = 20
    cutoff_date = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")

    page = 0
    while page < max_safe_pages:
        if len(articles) >= max_articles:
            break
        if max_seconds and (time.time() - t0) > max_seconds:
            break

        # Build page URL
        if page == 0:
            listing_url = site["home"]
        elif paginate and news_list:
            try:
                listing_url = news_list.format(**{pg_param: pg_start + page})
            except (KeyError, ValueError):
                break
        else:
            break  # no pagination config, only homepage was crawled

        try:
            resp = s.get(listing_url, timeout=12, allow_redirects=True, verify=verify)
            if resp.status_code != 200:
                if page == 0:
                    page += 1
                    continue
                break
        except Exception:
            if page == 0:
                page += 1
                continue
            break

        parsed = BeautifulSoup(resp.text, "html.parser")
        links = parsed.select(sel.get("article_links", "a"))

        if not links:
            if page == 0:
                page += 1
                continue
            break  # no more articles on this page, end of pagination

        page_has_recent = False

        # Phase A: Build fetch queue, handle cached articles inline
        fetch_queue = []
        for a in links:
            if len(articles) >= max_articles:
                break
            if max_seconds and (time.time() - t0) > max_seconds:
                break
            href = a.get("href", "")
            m = re.search(sel.get("link_pattern", r".*"), href)
            if not m:
                continue
            identifier = m.group(1)

            article_url_tmpl = site.get("article_url")
            if article_url_tmpl:
                fmt_kwargs = {k: identifier for k in ["id", "slug", "path"]}
                used = {k: v for k, v in fmt_kwargs.items() if "{" + k + "}" in article_url_tmpl}
                if used:
                    art_url = article_url_tmpl.format(**used)
                else:
                    art_url = href if href.startswith("http") else f"https://{site['name']}{href}"
            else:
                art_url = href if href.startswith("http") else f"https://{site['name']}{href}"

            if art_url in seen_this_run:
                continue
            seen_this_run.add(art_url)

            if is_in_cache(art_url):
                with _cache_lock:
                    art = _article_cache.get(art_url)
                    if art:
                        articles.append(art)
                        if _is_within_months(art.get("date", ""), months):
                            page_has_recent = True
                continue

            fetch_queue.append(art_url)

        # Phase B: Concurrently fetch+parse all new articles
        if fetch_queue:
            workers = 5
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(quick_parse, site, url, s): url for url in fetch_queue}
                for future in concurrent.futures.as_completed(futures):
                    if len(articles) >= max_articles:
                        break
                    if max_seconds and (time.time() - t0) > max_seconds:
                        break
                    try:
                        art = future.result()
                    except Exception:
                        continue
                    if art and art["title"]:
                        d = art.get("date", "")
                        if d:
                            if not newest_date or d > newest_date:
                                newest_date = d
                            if not oldest_date or d < oldest_date:
                                oldest_date = d
                        added = add_to_cache(art)
                        articles.append(art)
                        if added:
                            new_count += 1
                            newly_parsed.append(art)
                        if _is_within_months(art.get("date", ""), months):
                            page_has_recent = True

        # Stop paginating if this page had zero recent articles (we've passed the 3-month window)
        if page > 0 and not page_has_recent:
            break

        page += 1

        if paginate and page > 0:
            time.sleep(0.15)

    # Save original Mongolian/Russian text before translating to Chinese,
    # so drug keyword matching (which uses Mongolian/Russian/English terms)
    # can still work after translation.
    if newly_parsed:
        for art in newly_parsed:
            art["_orig_title"] = art.get("title", "")
            art["_orig_content"] = art.get("content", "")

    # Batch-translate newly parsed articles to Chinese
    if newly_parsed:
        try:
            translated = translate_articles_batch(newly_parsed)
            if translated > 0:
                print(f"[翻译] {site['label']}: {translated}/{len(newly_parsed)} 篇已翻译为中文")
        except Exception as e:
            print(f"[翻译] {site['label']}: 失败 - {e}")

    return articles, new_count

# Auto-restore cache from disk on import
_load_result = load_cache()
