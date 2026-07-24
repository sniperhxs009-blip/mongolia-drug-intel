"""
Deep historical backfill tool for Mongolia drug news archive.
Crawls far back in time (configurable months/years) for each site.

Usage:
  python tools/backfill_deep.py                    # Backfill all sites, 12 months
  python tools/backfill_deep.py --site police.gov.mn --months 24
  python tools/backfill_deep.py --dry-run           # Show what would be crawled
  python tools/backfill_deep.py --site gogo.mn --months 6 --terms "хар тамхи,кокаин"
"""
import sys
import os
import time
import argparse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from memory_crawler import (
    crawl_site, get_cache_size, _article_cache, _seen_urls, _cache_lock,
    HEADERS,
)
from drug_keywords import SITE_SEARCH_TERMS
from sites import SITES, INACCESSIBLE


def backfill_site(site, months=12, max_articles=500, max_seconds=300, extra_terms=None):
    """Deep backfill a single site, going back `months` months."""
    print(f"\n{'='*60}")
    print(f"[回填] {site['label']} ({site['name']}) — 回溯 {months} 个月")
    print(f"{'='*60}")

    pre_count = get_cache_size()
    t0 = time.time()

    # For search-based sites, customize search terms
    if extra_terms:
        site = dict(site)
        site["search_terms"] = extra_terms

    try:
        articles, new_count = crawl_site(
            site, max_articles=max_articles, months=months,
            max_seconds=max_seconds, max_pages=30,
        )
        elapsed = time.time() - t0
        post_count = get_cache_size()
        print(f"[回填] {site['label']}: {new_count} 新文章, 耗时 {elapsed:.0f}s, "
              f"缓存 {pre_count} → {post_count}")
        return new_count
    except Exception as e:
        print(f"[回填] {site['label']}: 错误 - {e}")
        return 0


def backfill_all(months=12, dry_run=False, max_per_site=500, max_seconds_per_site=300):
    """Backfill all active sites."""
    accessible = [s for s in SITES if not s.get("requires_js")]
    inaccessible_names = {i["name"] for i in INACCESSIBLE}

    total = 0
    print(f"[回填] 共 {len(accessible)} 个活跃站点, {len(INACCESSIBLE)} 个不可访问")
    print(f"[回填] 参数: months={months}, max_per_site={max_per_site}, "
          f"max_seconds_per_site={max_seconds_per_site}")

    if dry_run:
        print("\n[试运行] 以下站点将被回填:")
        for site in accessible:
            ctype = site.get("crawler_type", "html")
            print(f"  - {site['label']} ({site['name']}) [{ctype}]")
        print(f"\n[试运行] 跳过站点:")
        for inc in INACCESSIBLE:
            print(f"  - {inc['name']}: {inc['reason']}")
        return 0

    for site in accessible:
        if site["name"] in inaccessible_names:
            print(f"[回填] 跳过 {site['label']} — 已知不可访问")
            continue
        n = backfill_site(site, months=months, max_articles=max_per_site,
                          max_seconds=max_seconds_per_site)
        total += n
        time.sleep(0.5)

    print(f"\n[回填] 全部完成: +{total} 篇历史文章")
    return total


def main():
    parser = argparse.ArgumentParser(description="Deep historical backfill for Mongolia drug news")
    parser.add_argument("--site", type=str, default=None, help="Site name (e.g. police.gov.mn)")
    parser.add_argument("--months", type=int, default=12, help="Months back to crawl")
    parser.add_argument("--max", type=int, default=500, help="Max articles per site")
    parser.add_argument("--timeout", type=int, default=300, help="Max seconds per site")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without crawling")
    parser.add_argument("--terms", type=str, default=None,
                        help="Comma-separated extra search terms for keyword_search sites")
    parser.add_argument("--all", action="store_true", default=True,
                        help="Backfill all accessible sites (default)")
    args = parser.parse_args()

    extra_terms = None
    if args.terms:
        extra_terms = [t.strip() for t in args.terms.split(",") if t.strip()]

    if args.site:
        site = next((s for s in SITES if s["name"] == args.site), None)
        if not site:
            print(f"Site '{args.site}' not found in SITES. Available:")
            for s in SITES:
                print(f"  - {s['name']} ({s['label']})")
            return 1
        if args.dry_run:
            print(f"[试运行] {site['label']}: months={args.months}, max={args.max}")
            return 0
        backfill_site(site, months=args.months, max_articles=args.max,
                      max_seconds=args.timeout, extra_terms=extra_terms)
    else:
        backfill_all(months=args.months, dry_run=args.dry_run,
                     max_per_site=args.max, max_seconds_per_site=args.timeout)

    return 0


if __name__ == "__main__":
    sys.exit(main())
