import requests
import time
import re
import sys
from bs4 import BeautifulSoup
from db import init_db, article_exists, insert_article, get_highest_id

BASE_URL = "https://police.gov.mn"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en;q=0.9",
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch_homepage_ids():
    """Scrape article IDs from the homepage."""
    ids = set()
    for attempt in range(3):
        try:
            resp = session.get(f"{BASE_URL}/home", timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for link in soup.find_all("a", href=True):
                m = re.match(r"/a/(\d+)", link["href"])
                if m:
                    ids.add(int(m.group(1)))
            return ids
        except Exception:
            time.sleep(2 ** attempt)
    return ids


def probe_latest_id(start_id, probe_range=300):
    """Quickly probe to find the latest existing article ID."""
    for offset in range(probe_range, -1, -15):
        probe = start_id + offset
        try:
            resp = session.head(f"{BASE_URL}/a/{probe}", timeout=10)
            if resp.status_code == 200:
                for fine in range(probe + 15, probe - 20, -1):
                    try:
                        resp2 = session.head(f"{BASE_URL}/a/{fine}", timeout=10)
                        if resp2.status_code == 200:
                            return fine
                    except Exception:
                        pass
                    time.sleep(0.3)  # Be gentle
        except Exception:
            pass
        time.sleep(0.3)
    return start_id


def parse_article(article_id, html):
    """Extract article data from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Title: h2.article-view-name (NOT h1 on this site)
    title = ""
    title_el = soup.find("h2", class_="article-view-name")
    if title_el:
        title = title_el.get_text(strip=True)
    if not title:
        # Fallback: use the <title> tag
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # Date: span.date
    date = ""
    date_el = soup.find("span", class_="date")
    if date_el:
        m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", date_el.get_text())
        if m:
            date = m.group(1)
    if not date:
        m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", html)
        if m:
            date = m.group(1)

    # Content: inside <article> tag within div.article-view-main
    content_parts = []
    main_area = soup.find("article")
    if main_area:
        # Skip the back/header area with the title and date
        for p in main_area.find_all("p"):
            txt = p.get_text(strip=True)
            if txt and len(txt) > 5:
                content_parts.append(txt)
    if not content_parts:
        # Fallback: get meta description
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="description")
        if meta and meta.get("content"):
            content_parts = [meta["content"]]
    content = "\n".join(content_parts) if content_parts else title

    # Category from breadcrumb
    category = ""
    breadcrumb = soup.find("ul", class_="uk-breadcrumb")
    if breadcrumb:
        lis = breadcrumb.find_all("li")
        if len(lis) >= 2:
            category = lis[-1].get_text(strip=True)

    # Images
    images = []
    article_area = soup.find("article") or soup
    for img in article_area.find_all("img", src=True):
        src = img["src"]
        if "/resource/policenew/" in src and not src.endswith("_s.jpg"):
            full_url = src if src.startswith("http") else f"{BASE_URL}{src}"
            images.append(full_url)

    return {
        "id": article_id,
        "title": title,
        "content": content,
        "date": date,
        "category": category,
        "image_urls": "|".join(images),
        "url": f"{BASE_URL}/a/{article_id}",
    }


def crawl_article(article_id, max_retries=2):
    """Fetch and save a single article."""
    if article_exists(article_id):
        return None

    for attempt in range(max_retries):
        try:
            resp = session.get(f"{BASE_URL}/a/{article_id}", timeout=30)
            if resp.status_code == 404:
                return False
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            break
        except requests.ConnectionError:
            time.sleep(3 * (attempt + 1))
        except requests.RequestException:
            return False
    else:
        return False

    try:
        article = parse_article(article_id, resp.text)
        if article["title"]:
            insert_article(article)
            return True
    except Exception:
        pass
    return False


def crawl(max_articles=None, start_id=None):
    """Crawl articles starting from the latest ID and working backwards."""
    init_db()
    stored_max = get_highest_id()

    print("Discovering latest article ID...")
    if start_id:
        latest_id = start_id
    else:
        homepage_ids = fetch_homepage_ids()
        latest_id = max(homepage_ids) if homepage_ids else (stored_max + 1000)
        print(f"  Homepage max: {latest_id}")
        probe = probe_latest_id(latest_id, 200)
        if probe > latest_id:
            latest_id = probe

    print(f"Latest: {latest_id} | Stored: {stored_max} | To fetch: {latest_id - stored_max}")

    if latest_id <= stored_max:
        print("Already up to date.")
        return 0

    fetched = 0
    consecutive_404 = 0

    for article_id in range(latest_id, stored_max, -1):
        if max_articles and fetched >= max_articles:
            break
        if consecutive_404 > 400:
            print(f"\n400 consecutive missing. Gap at ID {article_id}. Stopping.")
            break

        result = crawl_article(article_id)
        if result is True:
            fetched += 1
            consecutive_404 = 0
            if fetched % 20 == 0:
                print(f"  [{fetched} OK, ID: {article_id}]")
        elif result is None:
            pass  # Already exists
        else:
            consecutive_404 += 1

        # Rate limiting - gentle to the server
        delay = 0.5 if result is True else 0.15
        time.sleep(delay)

    print(f"Done. {fetched} new articles. DB total exists up to ID: {get_highest_id()}")
    return fetched


def update():
    """Quick update: fetch only the newest articles."""
    init_db()
    homepage_ids = fetch_homepage_ids()
    stored_max = get_highest_id()

    if not homepage_ids:
        print("Failed to fetch homepage.")
        return 0

    latest_id = max(homepage_ids)
    probe = probe_latest_id(stored_max, 200)
    latest_id = max(latest_id, probe)

    if latest_id <= stored_max:
        print(f"Up to date. Stored: {stored_max}, Site: {latest_id}")
        return 0

    print(f"Update: fetching IDs {stored_max + 1} to {latest_id}")
    fetched = 0
    for article_id in range(stored_max + 1, latest_id + 1):
        result = crawl_article(article_id)
        if result is True:
            fetched += 1
        time.sleep(0.3)

    print(f"Update done. {fetched} new articles.")
    return fetched


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "update":
            update()
        elif sys.argv[1] == "test":
            crawl(max_articles=5)
        elif sys.argv[1].isdigit():
            crawl(start_id=int(sys.argv[1]))
        else:
            print("Usage: python crawler.py [update|test|<start_id>]")
    else:
        crawl()
