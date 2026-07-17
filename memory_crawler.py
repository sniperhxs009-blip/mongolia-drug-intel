"""
Unified in-memory crawler for Mongolian news sites.
Articles are cached in memory only -- no SQLite or file storage.
Thread-safe. Used by auto-crawler, live fetch, drug filter, and index search.
"""
import re
import time
import threading
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

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


def is_in_cache(url):
    return url in _seen_urls


def add_to_cache(article):
    """Thread-safe add. Returns True if new, False if duplicate."""
    url = article["url"]
    with _cache_lock:
        if url in _seen_urls:
            return False
        _seen_urls.add(url)
        _article_cache[url] = article
        return True


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
        resp = s.get(url, timeout=15, allow_redirects=True, verify=verify)
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

def crawl_site(site, session=None, max_articles=200, months=3):
    """Full-coverage crawl: paginate until articles are older than cutoff, or no more pages.
    Returns (articles_list, new_count)."""
    s = session or http_session
    verify = site.get("ssl_verify", True)
    sel = site.get("list_selectors", {})
    paginate = site.get("paginate")
    news_list = site.get("news_list")

    new_count = 0
    articles = []
    seen_this_run = set()

    pg_param = paginate.get("param", "page") if paginate else "page"
    pg_start = paginate.get("start", 1) if paginate else 1
    max_safe_pages = 30

    page = 0
    while page < max_safe_pages:
        if len(articles) >= max_articles:
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
            resp = s.get(listing_url, timeout=20, allow_redirects=True, verify=verify)
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

        for a in links:
            if len(articles) >= max_articles:
                break

            href = a.get("href", "")
            m = re.search(sel.get("link_pattern", r".*"), href)
            if not m:
                continue
            identifier = m.group(1)

            # Build article URL
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

            # Check in-memory cache
            if is_in_cache(art_url):
                with _cache_lock:
                    art = _article_cache.get(art_url)
                    if art:
                        articles.append(art)
                        if _is_within_months(art.get("date", ""), months):
                            page_has_recent = True
                continue

            # Fetch and parse new article
            art = quick_parse(site, art_url, s)
            if art and art["title"]:
                add_to_cache(art)
                articles.append(art)
                new_count += 1
                if _is_within_months(art.get("date", ""), months):
                    page_has_recent = True

            time.sleep(0.1)

        # Stop paginating if this page had zero recent articles (we've passed the 3-month window)
        if page > 0 and not page_has_recent:
            break

        page += 1

        if paginate and page > 0:
            time.sleep(0.3)

    return articles, new_count
