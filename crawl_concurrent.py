"""
Concurrent article fetching for memory_crawler.
Uses ThreadPoolExecutor to fetch multiple articles in parallel within a site.
"""
import concurrent.futures

# Number of concurrent article fetches per site
MAX_WORKERS = 5


def crawl_site_concurrent(site, session=None, max_articles=200, months=3,
                          max_seconds=None, max_pages=None):
    """
    Optimized crawl using concurrent article fetching.
    Same interface as crawl_site() but much faster (5x on multi-article pages).
    """
    import time, re
    from datetime import datetime, timedelta
    import requests
    from bs4 import BeautifulSoup
    from translate import translate_articles_batch

    from memory_crawler import (
        http_session, HEADERS, is_in_cache, add_to_cache, _is_within_months,
        quick_parse, _cache_lock
    )

    s = session or http_session
    verify = site.get("ssl_verify", True)
    sel = site.get("list_selectors", {})
    paginate = site.get("paginate")
    news_list = site.get("news_list")
    t0 = time.time()

    new_count = 0
    articles = []
    seen_this_run = set()
    newly_parsed = []
    newest_date = ""
    oldest_date = ""

    pg_param = paginate.get("param", "page") if paginate else "page"
    pg_start = paginate.get("start", 1) if paginate else 1
    max_safe_pages = max_pages if max_pages is not None else 20
    cutoff_date = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")

    page = 0
    while page < max_safe_pages:
        if len(articles) >= max_articles:
            break
        if max_seconds and (time.time() - t0) > max_seconds:
            break

        if page == 0:
            listing_url = site["home"]
        elif paginate and news_list:
            try:
                listing_url = news_list.format(**{pg_param: pg_start + page})
            except (KeyError, ValueError):
                break
        else:
            break

        try:
            resp = s.get(listing_url, timeout=15, allow_redirects=True, verify=verify)
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
            break

        page_has_recent = False

        # Build list of article URLs to fetch (filter duplicates/cached)
        fetch_queue = []
        for a in links:
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

            # Check cache - add directly if cached
            if is_in_cache(art_url):
                with _cache_lock:
                    art = _article_cache.get(art_url)
                    if art:
                        articles.append(art)
                        seen_this_run.add(art_url)
                        if _is_within_months(art.get("date", ""), months):
                            page_has_recent = True
                continue

            seen_this_run.add(art_url)
            fetch_queue.append((art_url, a))

        # Concurrently fetch all new article URLs
        if fetch_queue:
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(quick_parse, site, url, s): url
                    for url, _ in fetch_queue
                }
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
                        add_to_cache(art)
                        articles.append(art)
                        new_count += 1
                        newly_parsed.append(art)
                        if _is_within_months(art.get("date", ""), months):
                            page_has_recent = True

        if page > 0 and not page_has_recent:
            break

        page += 1
        if paginate and page > 0:
            time.sleep(0.2)

    # Save originals + translate
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

    if newest_date:
        nd = str(newest_date)[:10]
        od = str(oldest_date)[:10] if oldest_date else nd
        print(f"[爬取] {site['label']}: {new_count} 篇新增, 日期范围 {od} ~ {nd}, 截止线 {cutoff_date}")

    return articles, new_count
