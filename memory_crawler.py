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
import warnings
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
import requests
from bs4 import BeautifulSoup
from translate import translate_articles_batch
from drug_keywords import SITE_SEARCH_TERMS

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

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
    with _cache_lock:
        to_remove = []
        for url, art in _article_cache.items():
            d = art.get("date", "")
            if not d:
                continue  # keep articles without dates
            if not _is_within_months(d, months):
                to_remove.append(url)
        for url in to_remove:
            del _article_cache[url]
            _seen_urls.discard(url)
        if to_remove:
            print(f"[memory] Evicted {len(to_remove)} old articles, cache size: {len(_article_cache)}")


def get_cached_articles(source=None, months=None):
    """Get articles from in-memory cache, optionally filtered by source and age."""
    from copy import deepcopy
    with _cache_lock:
        results = []
        for art in _article_cache.values():
            if source and art.get("source") != source:
                continue
            if months and not _is_within_months(art.get("date", ""), months):
                continue
            results.append(deepcopy(art))
        return results


# ---- Date helpers ----

def _is_within_months(date_str, months=3):
    """Check if a date string is within the given number of months from now."""
    if not date_str:
        return False
    try:
        raw = str(date_str).strip()
        s = raw[:10].replace(".", "-").strip()

        # Numeric formats: YYYY-MM-DD, DD-MM-YYYY
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

        # DD.MM.YYYY
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
        if m:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            cutoff = datetime.now() - timedelta(days=months * 30)
            return dt >= cutoff

        # Text dates: "12 July 2026", "12 Jul 2026", "3 Jan 2026", etc.
        # Month name mapping (full + abbreviated, English + Russian)
        _MONTHS = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
            "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
            "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
            "янв": 1, "фев": 2, "мар": 3, "апр": 4, "июн": 6, "июл": 7, "авг": 8,
            "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
        }
        m = re.match(r"(\d{1,2})\s+([a-zA-Zа-яА-Я]+)\s*,?\s*(\d{4})", raw)
        if m:
            day = int(m.group(1))
            month_name = m.group(2).lower()
            year = int(m.group(3))
            mo = _MONTHS.get(month_name)
            if mo:
                dt = datetime(year, mo, day)
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

    # Fallback: if no date could be extracted from the article page, use today.
    # UNODC and similar sites don't render dates on article detail pages.
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

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
    if site.get("crawler_type") == "gia_api":
        return crawl_gia_api(site, session, max_articles, months, max_seconds)
    if site.get("crawler_type") == "police_search":
        return crawl_police_search(site, session, max_articles, months, max_seconds)
    if site.get("crawler_type") == "montsame_search":
        return crawl_montsame_search(site, session, max_articles, months, max_seconds)
    if site.get("crawler_type") == "keyword_search":
        return crawl_keyword_search(site, session, max_articles, months, max_seconds)
    return _crawl_site_html(site, session, max_articles, months, max_seconds, max_pages)


def _crawl_site_html(site, session=None, max_articles=200, months=3, max_seconds=None, max_pages=None):
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
                        # Drug pre-filter: skip articles with zero drug keywords
                        # to reduce noise from non-drug news sites
                        try:
                            from drug_keywords import score_article
                            art_score, _, _, _, _ = score_article(art.get("title",""), art.get("content",""), site.get("name",""))
                            if art_score == 0:
                                continue
                            art["_drug_score"] = art_score
                        except Exception:
                            pass
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


# ---- GIA API Crawler ----
# gia.gov.mn is a React SPA. The blog listing API requires auth (401),
# but the search endpoint is public and returns full article content.
# We search for common Mongolian letters to enumerate all blog articles,
# then deduplicate by ID and convert to standard format.

GIA_API_BASE = "https://gia.gov.mn/api/v1"
GIA_SEARCH_TERMS = [
    # Drug-specific terms FIRST — these run before the catch-all "а" to ensure
    # drug articles are always captured within the max_articles limit.
    "хар тамхи", "мансууруулах", "мансууруулах бодис",
    "наркотик", "психотроп", "сэтгэцэд нөлөөлөх",
    "кокаин", "героин", "марихуана", "метамфетамин", "экстази",
    "контрабанда", "хууль бус",
    "drug", "narcotic", "trafficking",
    # Catch-all letter — captures remaining articles (placed last so drug
    # terms run first and drug articles aren't pushed out by max_articles).
    "а",
]
GIA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gia.gov.mn",
}


def crawl_gia_api(site, session=None, max_articles=200, months=3, max_seconds=None):
    """
    Crawl gia.gov.mn blog articles via the search API.

    The blog listing API requires authentication, but the search endpoint
    is public. We search for common Mongolian letters/drug terms to
    enumerate all articles, deduplicate by ID, and add to cache.
    """
    s = session or requests.Session()
    s.headers.update(GIA_HEADERS)
    t0 = time.time()

    new_count = 0
    articles = []
    seen_ids = set()
    newly_parsed = []
    newest_date = ""
    oldest_date = ""

    for term in GIA_SEARCH_TERMS:
        if len(articles) >= max_articles:
            break
        if max_seconds and (time.time() - t0) > max_seconds:
            break

        try:
            resp = s.get(
                f"{GIA_API_BASE}/blog/search",
                params={"term": term, "language": "MN"},
                timeout=15,
                verify=False,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue

        if not isinstance(data, list):
            continue

        for item in data:
            if len(articles) >= max_articles:
                break
            if max_seconds and (time.time() - t0) > max_seconds:
                break

            bid = item.get("id")
            if not bid or bid in seen_ids:
                continue
            seen_ids.add(bid)

            title = (item.get("title") or "").strip()
            if not title:
                continue

            # Extract text from HTML content
            html_content = item.get("content") or ""
            try:
                text_content = BeautifulSoup(html_content, "html.parser").get_text(separator="\n", strip=True)
            except Exception:
                text_content = html_content

            # Parse ISO date
            raw_date = item.get("createdAt", "")
            date = ""
            if raw_date:
                m = re.match(r"(\d{4}-\d{2}-\d{2})", raw_date)
                if m:
                    date = m.group(1)

            lang = item.get("language", "MN")
            article_url = f"https://gia.gov.mn/blog/{bid}"

            art = {
                "source": site["name"],
                "source_label": site["label"],
                "title": title,
                "content": text_content,
                "date": date,
                "category": "",
                "url": article_url,
                "lang": lang.lower(),
            }

            if date:
                if not newest_date or date > newest_date:
                    newest_date = date
                if not oldest_date or date < oldest_date:
                    oldest_date = date

            added = add_to_cache(art)
            articles.append(art)
            if added:
                new_count += 1
                newly_parsed.append(art)

        time.sleep(0.1)

    # Save original text before translation
    if newly_parsed:
        for art in newly_parsed:
            art["_orig_title"] = art.get("title", "")
            art["_orig_content"] = art.get("content", "")

    # Batch-translate to Chinese
    if newly_parsed:
        try:
            translated = translate_articles_batch(newly_parsed)
            if translated > 0:
                print(f"[翻译] {site['label']}: {translated}/{len(newly_parsed)} 篇已翻译为中文")
        except Exception as e:
            print(f"[翻译] {site['label']}: 失败 - {e}")

    print(f"[GIA API] 搜索 {len(GIA_SEARCH_TERMS)} 个词 → {len(articles)} 篇文章, +{new_count} 新")
    return articles, new_count


# ---- Police.gov.mn Search Crawler ----
# police.gov.mn has a search endpoint that returns article IDs.
# The homepage only shows recent articles, but search gives access to the full archive.

def crawl_police_search(site, session=None, max_articles=200, months=3, max_seconds=None):
    """Crawl police.gov.mn via the search endpoint for drug-related articles."""
    s = session or requests.Session()
    s.headers.update(HEADERS)
    t0 = time.time()

    new_count = 0
    articles = []
    seen_ids = set()
    newly_parsed = []

    for term in SITE_SEARCH_TERMS:
        if len(articles) >= max_articles:
            break
        if max_seconds and (time.time() - t0) > max_seconds:
            break

        try:
            resp = s.get(
                f"{site['home']}?search={requests.utils.quote(term)}",
                timeout=15,
                verify=site.get("ssl_verify", True),
            )
            if resp.status_code != 200:
                continue
        except Exception:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a[href^='/a/']")
        ids = []
        for a in links:
            href = a.get("href", "")
            m = re.search(r"/a/(\d+)", href)
            if m:
                aid = m.group(1)
                if aid not in seen_ids:
                    seen_ids.add(aid)
                    ids.append(aid)

        for aid in ids:
            if len(articles) >= max_articles:
                break
            if max_seconds and (time.time() - t0) > max_seconds:
                break

            art_url = f"https://police.gov.mn/a/{aid}"
            art = quick_parse(site, art_url, s)
            if art and art["title"]:
                articles.append(art)
                added = add_to_cache(art)
                if added:
                    new_count += 1
                    newly_parsed.append(art)

        time.sleep(0.1)

    # Save original text before translation
    if newly_parsed:
        for art in newly_parsed:
            art["_orig_title"] = art.get("title", "")
            art["_orig_content"] = art.get("content", "")

    if newly_parsed:
        try:
            translated = translate_articles_batch(newly_parsed)
            if translated > 0:
                print(f"[翻译] {site['label']}: {translated}/{len(newly_parsed)} 篇已翻译为中文")
        except Exception as e:
            print(f"[翻译] {site['label']}: 失败 - {e}")

    print(f"[警察总局] 搜索 {len(SITE_SEARCH_TERMS)} 个词 → {len(articles)} 篇文章, +{new_count} 新")
    return articles, new_count


# ---- Montsame.mn Search Crawler ----
# montsame.mn has a search endpoint (?q=) that gives access to archive articles.

def crawl_montsame_search(site, session=None, max_articles=200, months=3, max_seconds=None):
    """Crawl montsame.mn via search endpoint for drug-related articles."""
    s = session or requests.Session()
    s.headers.update(HEADERS)
    t0 = time.time()

    new_count = 0
    articles = []
    seen_ids = set()
    newly_parsed = []

    for term in SITE_SEARCH_TERMS:
        if len(articles) >= max_articles:
            break
        if max_seconds and (time.time() - t0) > max_seconds:
            break

        try:
            news_list = site.get("news_list", "")
            search_url = news_list.format(term=requests.utils.quote(term))
            resp = s.get(search_url, timeout=15, verify=site.get("ssl_verify", True))
            if resp.status_code != 200:
                continue
        except Exception:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a[href*='/read/']")
        ids = []
        for a in links:
            href = a.get("href", "")
            m = re.search(r"/read/(\d+)", href)
            if m:
                aid = m.group(1)
                if aid not in seen_ids:
                    seen_ids.add(aid)
                    ids.append(aid)

        for aid in ids:
            if len(articles) >= max_articles:
                break
            if max_seconds and (time.time() - t0) > max_seconds:
                break

            art_url = f"https://montsame.mn/mn/read/{aid}"
            art = quick_parse(site, art_url, s)
            if art and art["title"]:
                articles.append(art)
                added = add_to_cache(art)
                if added:
                    new_count += 1
                    newly_parsed.append(art)

        time.sleep(0.1)

    if newly_parsed:
        for art in newly_parsed:
            art["_orig_title"] = art.get("title", "")
            art["_orig_content"] = art.get("content", "")

    if newly_parsed:
        try:
            translated = translate_articles_batch(newly_parsed)
            if translated > 0:
                print(f"[翻译] {site['label']}: {translated}/{len(newly_parsed)} 篇已翻译为中文")
        except Exception as e:
            print(f"[翻译] {site['label']}: 失败 - {e}")

    print(f"[蒙通社] 搜索 {len(SITE_SEARCH_TERMS)} 个词 → {len(articles)} 篇文章, +{new_count} 新")
    return articles, new_count


# ---- Generic Keyword Search Crawler ----
# For sites that have a search endpoint but no homepage listing of all articles.
# Each site config must provide: search_url (template with {term}), article_links selector,
# link_pattern regex, and article_url template with {id} or {path}.

def crawl_keyword_search(site, session=None, max_articles=200, months=3, max_seconds=None):
    """Generic keyword-based search crawler. Uses site['search_url'] template."""
    s = session or requests.Session()
    s.headers.update(HEADERS)
    t0 = time.time()

    new_count = 0
    articles = []
    seen_ids = set()
    newly_parsed = []
    search_url_tpl = site.get("search_url", "")
    if not search_url_tpl:
        print(f"[关键词搜索] {site['label']}: 未配置 search_url, 跳过")
        return [], 0

    terms = site.get("search_terms", SITE_SEARCH_TERMS)
    link_sel = site["list_selectors"].get("article_links", "a")
    link_pattern = site["list_selectors"].get("link_pattern", r"/(\d+)")
    art_url_tpl = site.get("article_url", "")

    for term in terms:
        if len(articles) >= max_articles:
            break
        if max_seconds and (time.time() - t0) > max_seconds:
            break

        try:
            url = search_url_tpl.format(term=requests.utils.quote(term))
            resp = s.get(url, timeout=15, verify=site.get("ssl_verify", True))
            if resp.status_code != 200:
                continue
        except Exception:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select(link_sel):
            href = a.get("href", "")
            m = re.search(link_pattern, href)
            if not m:
                continue
            aid = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
            if not aid or aid in seen_ids:
                continue
            seen_ids.add(aid)

            if len(articles) >= max_articles:
                break
            if max_seconds and (time.time() - t0) > max_seconds:
                break

            # Build article URL — auto-detect ID vs path vs full URL
            if aid.startswith("http"):
                art_url = aid
            elif aid.startswith("/") and "{path}" in art_url_tpl:
                art_url = art_url_tpl.format(path=aid)
            elif aid.startswith("/") and "{id}" in art_url_tpl:
                # Path matched but only {id} template — strip leading / and use as id
                art_url = art_url_tpl.format(id=aid.lstrip("/"))
            elif "{id}" in art_url_tpl:
                art_url = art_url_tpl.format(id=aid)
            elif "{path}" in art_url_tpl:
                art_url = art_url_tpl.format(path=aid)
            else:
                continue

            art = quick_parse(site, art_url, s)
            if art and art["title"]:
                articles.append(art)
                added = add_to_cache(art)
                if added:
                    new_count += 1
                    newly_parsed.append(art)

        time.sleep(0.1)

    if newly_parsed:
        for art in newly_parsed:
            art["_orig_title"] = art.get("title", "")
            art["_orig_content"] = art.get("content", "")

    if newly_parsed:
        try:
            translated = translate_articles_batch(newly_parsed)
            if translated > 0:
                print(f"[翻译] {site['label']}: {translated}/{len(newly_parsed)} 篇已翻译为中文")
        except Exception as e:
            print(f"[翻译] {site['label']}: 失败 - {e}")

    print(f"[关键词搜索] {site['label']}: {len(terms)} 个词 → {len(articles)} 篇文章, +{new_count} 新")
    return articles, new_count


# ---- RSS Feed Crawler ----
# For sites that provide RSS feeds (ikon.mn, unodc.org).

def crawl_rss(site, session=None, max_articles=200, months=3, max_seconds=None):
    """Crawl a site via its RSS feed. Parses XML, fetches full article content."""
    s = session or requests.Session()
    s.headers.update(HEADERS)
    t0 = time.time()

    rss_url = site.get("rss", "")
    if not rss_url:
        print(f"[RSS] {site['label']}: 未配置 RSS URL")
        return [], 0

    new_count = 0
    articles = []
    newly_parsed = []
    cutoff = datetime.now() - timedelta(days=months * 31)

    try:
        resp = s.get(rss_url, timeout=15, verify=site.get("ssl_verify", True))
        if resp.status_code != 200:
            print(f"[RSS] {site['label']}: HTTP {resp.status_code}")
            return [], 0
    except Exception as e:
        print(f"[RSS] {site['label']}: 获取失败 - {e}")
        return [], 0

    try:
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"[RSS] {site['label']}: XML 解析失败 - {e}")
        return [], 0

    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for item in items:
        if len(articles) >= max_articles:
            break
        if max_seconds and (time.time() - t0) > max_seconds:
            break

        # RSS 2.0 format
        link_el = item.find("link")
        link = ""
        if link_el is not None:
            link = (link_el.text or "").strip()
            if not link:
                link = link_el.get("href", "").strip()

        # Atom format fallback
        if not link:
            for lk in item.findall("{http://www.w3.org/2005/Atom}link"):
                href = lk.get("href", "")
                if href:
                    link = href
                    break

        if not link:
            continue

        # Date parsing
        pub_date = None
        for date_tag in ["pubDate", "{http://purl.org/dc/elements/1.1/}date",
                         "published", "{http://www.w3.org/2005/Atom}published",
                         "{http://www.w3.org/2005/Atom}updated"]:
            dt_el = item.find(date_tag)
            if dt_el is not None and dt_el.text:
                raw_date = dt_el.text.strip()
                try:
                    pub_date = parsedate_to_datetime(raw_date)
                    break
                except Exception:
                    # Malformed dates like "2026-07-23 12:01:51.02026-07-23 12:01:51.0"
                    m = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", raw_date)
                    if m:
                        try:
                            pub_date = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                            break
                        except Exception:
                            pass
                    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw_date)
                    if m:
                        try:
                            pub_date = datetime.strptime(m.group(1), "%Y-%m-%d")
                            break
                        except Exception:
                            pass
                    continue

        if pub_date and pub_date < cutoff:
            continue

        # Skip if already cached
        if is_in_cache(link):
            continue

        art = quick_parse(site, link, s)
        if art and art["title"]:
            if pub_date:
                art["date"] = pub_date.strftime("%Y-%m-%d %H:%M:%S")
            articles.append(art)
            added = add_to_cache(art)
            if added:
                new_count += 1
                newly_parsed.append(art)

        time.sleep(0.05)

    if newly_parsed:
        for art in newly_parsed:
            art["_orig_title"] = art.get("title", "")
            art["_orig_content"] = art.get("content", "")

    if newly_parsed:
        try:
            translated = translate_articles_batch(newly_parsed)
            if translated > 0:
                print(f"[翻译] {site['label']}: {translated}/{len(newly_parsed)} 篇已翻译为中文")
        except Exception as e:
            print(f"[翻译] {site['label']}: 失败 - {e}")

    print(f"[RSS] {site['label']}: {rss_url} → {len(articles)} 篇文章, +{new_count} 新")
    return articles, new_count


# Auto-restore cache from disk on import
_load_result = load_cache()
