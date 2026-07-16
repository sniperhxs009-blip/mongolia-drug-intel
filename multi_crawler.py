"""
Multi-source crawler for Mongolian news sites.
Usage:
  python multi_crawler.py                  # crawl all sites (latest articles)
  python multi_crawler.py --site=ikon.mn   # crawl single site
  python multi_crawler.py --days=30        # crawl last 30 days
  python multi_crawler.py --update         # quick update (latest only)
"""
import requests
import time
import re
import sys
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from db import init_db, article_exists_by_url, insert_article, get_stats
from sites import SITES, INACCESSIBLE

# Fix Windows console encoding for Mongolian Cyrillic
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Suppress SSL warnings for sites with broken certificates
import urllib3
urllib3.disable_warnings()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn-MN,mn;q=0.9,en;q=0.8,ru;q=0.7",
}
session = requests.Session()
session.headers.update(HEADERS)


def parse_date(date_text, date_format, regex, regex_fallback):
    """Parse date string from various formats into YYYY-MM-DD."""
    if not date_text:
        return ""
    for pattern in [regex, regex_fallback]:
        if not pattern:
            continue
        m = re.search(pattern, date_text)
        if m:
            dt = m.group(1)
            if date_format == "ymd":
                return dt  # already YYYY-MM-DD
            elif date_format == "ymd_hms":
                return dt[:10]  # YYYY-MM-DD HH:MM:SS -> YYYY-MM-DD
            elif date_format == "ymd_slash":
                return dt.replace("/", "-")  # YYYY/MM/DD -> YYYY-MM-DD
            elif date_format == "dmY_dot":
                parts = dt.split(".")
                if len(parts) == 3:
                    return f"{parts[2]}-{parts[1]}-{parts[0]}"  # DD.MM.YYYY -> YYYY-MM-DD
            elif date_format == "text":
                try:
                    parsed = datetime.strptime(dt, "%d %B %Y")
                    return parsed.strftime("%Y-%m-%d")
                except ValueError:
                    pass
    return ""


def fetch_page(url, max_retries=2, verify=True):
    """Fetch a URL with retries."""
    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=30, allow_redirects=True, verify=verify)
            if resp.status_code == 403:
                # Try with different user agent
                session.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                resp = session.get(url, timeout=30, allow_redirects=True, verify=verify)
                session.headers.update(HEADERS)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except requests.ConnectionError:
            time.sleep(3 * (attempt + 1))
        except Exception as e:
            if attempt >= max_retries - 1:
                return None
            time.sleep(2)
    return None


def scrape_listing_page(site, url):
    """Scrape a listing page to find article links."""
    resp = fetch_page(url, verify=site.get("ssl_verify", True))
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    selectors = site["list_selectors"]
    links = []

    for a in soup.select(selectors["article_links"]):
        href = a.get("href", "")
        m = re.search(selectors["link_pattern"], href)
        if not m:
            continue

        identifier = m.group(1)
        if "article_url" in site:
            try:
                article_url = site["article_url"].format(id=identifier)
            except KeyError:
                try:
                    article_url = site["article_url"].format(slug=identifier)
                except KeyError:
                    article_url = site["article_url"].format(path=identifier)
        else:
            article_url = href if href.startswith("http") else f"https://{site['name']}{href}"

        # Try to get title from the listing
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            title = a.get("title", "").strip()
        if not title or len(title) < 5:
            img = a.find("img")
            if img:
                title = img.get("alt", "").strip()

        # Try to get date from nearby elements
        date_str = ""
        parent = a.parent
        for _ in range(5):
            if not parent:
                break
            for selector in [selectors.get("date_nearby_selector"), "time", "span.date", ".date", "small"]:
                if not selector:
                    continue
                try:
                    date_el = parent.select_one(selector)
                    if date_el:
                        date_str = date_el.get_text(strip=True)
                        break
                except Exception:
                    pass
            if date_str:
                break
            parent = parent.parent if hasattr(parent, "parent") else None

        links.append({
            "url": article_url,
            "title": title,
            "date_hint": date_str,
            "identifier": identifier,
        })

    # Deduplicate by URL
    seen = set()
    unique = []
    for link in links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique.append(link)
    return unique


def scrape_article_page(site, url, title_hint=""):
    """Scrape an article detail page."""
    resp = fetch_page(url, verify=site.get("ssl_verify", True))
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    sel = site["article_selectors"]

    # Title
    title = ""
    if sel.get("title"):
        title_el = soup.select_one(sel["title"])
        if title_el:
            title = title_el.get_text(strip=True)
    if not title:
        title = title_hint
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # Date
    date = ""
    if sel.get("date"):
        date_els = [s.strip() for s in sel["date"].split(",")]
        for date_sel in date_els:
            try:
                date_el = soup.select_one(date_sel)
                if date_el:
                    date_text = date_el.get_text(strip=True)
                    date = parse_date(date_text, site["date_format"], sel["date_regex"], sel["date_regex_fallback"])
                    if date:
                        break
            except Exception:
                pass
    if not date:
        # Search whole page for date pattern
        text = soup.get_text()
        date = parse_date(text, site["date_format"], sel["date_regex"], sel["date_regex_fallback"])

    # Content - try specified selectors first, then fallback to generic p
    content_parts = []
    if sel.get("content"):
        for p in soup.select(sel["content"]):
            txt = p.get_text(strip=True)
            if txt and len(txt) > 5:
                content_parts.append(txt)

    # If primary selectors failed, try finding main content container
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

    # If still nothing, use body p but only paragraphs with substantial text
    if not content_parts:
        body = soup.find("body")
        if body:
            for p in body.find_all("p"):
                txt = p.get_text(strip=True)
                if len(txt) > 40:  # filter nav/footer short text
                    content_parts.append(txt)

    # Last resort: try div tags too (some sites use div-based layout)
    if not content_parts:
        body = soup.find("body")
        if body:
            for tag in body.find_all(["div", "section"]):
                # Only get leaf-level divs (no nested divs) with substantial text
                if tag.find(["div", "section"]):
                    continue
                txt = tag.get_text(strip=True)
                if len(txt) > 60:
                    content_parts.append(txt)
            if content_parts:
                # Sort by length, take the longest ones (most likely article content)
                content_parts.sort(key=len, reverse=True)
                content_parts = content_parts[:5]

    content = "\n".join(content_parts[:15]) if content_parts else title

    # Category
    category = ""
    if sel.get("category"):
        try:
            cat_el = soup.select_one(sel["category"])
            if cat_el:
                category = cat_el.get_text(strip=True)
        except Exception:
            pass

    return {
        "source": site["name"],
        "source_label": site["label"],
        "title": title,
        "content": content,
        "date": date,
        "category": category,
        "url": url,
    }


def crawl_site(site, max_articles=100, days_filter=None):
    """Crawl a single site."""
    label = site["label"]
    print(f"\n{'='*50}")
    print(f"  {label} ({site['name']})")
    print(f"{'='*50}")

    if site.get("requires_js"):
        print(f"  [SKIP] Requires JavaScript rendering")
        return 0

    # Get listing URLs to scrape
    list_urls = [site["home"]]
    if "news_list" in site:
        list_urls.append(site["news_list"].format(page=1, cat=""))

    # Also check category pages if pagination
    if site.get("paginate"):
        pg = site["paginate"]
        for page in range(pg.get("start", 1), min(pg.get("max", 10), 10) + 1):
            list_urls.append(site["news_list"].format(page=page, cat=""))

    # Collect article links from listing pages
    all_links = []
    for list_url in list_urls[:5]:  # limit listing pages
        print(f"  Fetching listing: {list_url}")
        links = scrape_listing_page(site, list_url)
        print(f"  Found {len(links)} article links")
        all_links.extend(links)
        time.sleep(0.5)

    # Deduplicate
    seen = set()
    unique_links = []
    for l in all_links:
        if l["url"] not in seen:
            seen.add(l["url"])
            unique_links.append(l)
    print(f"  Total unique articles: {len(unique_links)}")

    # Fetch article details
    fetched = 0
    cutoff_date = None
    if days_filter:
        cutoff_date = (datetime.now() - timedelta(days=days_filter)).strftime("%Y-%m-%d")

    for i, link in enumerate(unique_links[:max_articles]):
        if article_exists_by_url(link["url"]):
            print(f"  [{i+1}/{min(len(unique_links), max_articles)}] EXISTS: {link['title'][:50]}")
            continue

        article = scrape_article_page(site, link["url"], link.get("title", ""))
        if not article or not article["title"]:
            print(f"  [{i+1}/{min(len(unique_links), max_articles)}] FAILED: {link['url']}")
            continue

        # Apply date filter
        if cutoff_date and article["date"]:
            if article["date"] < cutoff_date:
                print(f"  [{i+1}/{min(len(unique_links), max_articles)}] OLD ({article['date']}): {article['title'][:50]}")
                continue

        insert_article(article)
        fetched += 1
        date_str = article.get("date", "no date")
        print(f"  [{i+1}/{min(len(unique_links), max_articles)}] OK ({date_str}): {article['title'][:50]}")
        time.sleep(0.3)

    print(f"  Site done. Fetched: {fetched}")
    return fetched


def crawl_all(max_per_site=100, days_filter=None, target_sites=None):
    """Crawl all configured sites."""
    init_db()

    total = 0
    for site in SITES:
        if target_sites and site["name"] not in target_sites:
            continue
        try:
            n = crawl_site(site, max_articles=max_per_site, days_filter=days_filter)
            total += n
        except Exception as e:
            print(f"  [ERROR] {site['name']}: {e}")

    stats = get_stats()
    print(f"\n{'='*50}")
    print(f"ALL DONE. Total fetched: {total}")
    print(f"Database: {stats['total']} articles from {len(stats.get('sources', []))} sources")
    for s in stats.get("sources", []):
        print(f"  {s['source_label']}: {s['cnt']} articles")
    return total


def update_all():
    """Quick update - fetch only newest from each site."""
    return crawl_all(max_per_site=30, days_filter=7)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=str, help="Single site name to crawl")
    parser.add_argument("--days", type=int, default=None, help="Days filter (e.g. 30 for last month)")
    parser.add_argument("--max", type=int, default=100, help="Max articles per site")
    parser.add_argument("--update", action="store_true", help="Quick update mode")
    parser.add_argument("--list", action="store_true", help="List available sites")
    args = parser.parse_args()

    if args.list:
        for s in SITES:
            js = " [JS required]" if s.get("requires_js") else ""
            print(f"  {s['name']} - {s['label']}{js}")
        print("\nInaccessible:")
        for s in INACCESSIBLE:
            print(f"  {s['name']} - {s['reason']}")
        sys.exit(0)

    if args.update:
        update_all()
    elif args.site:
        site = next((s for s in SITES if s["name"] == args.site), None)
        if site:
            crawl_site(site, max_articles=args.max or 200, days_filter=args.days)
        else:
            print(f"Site '{args.site}' not found.")
    else:
        crawl_all(max_per_site=args.max or 100, days_filter=args.days)
