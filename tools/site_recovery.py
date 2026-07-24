"""
Site recovery probe — tries alternative approaches to access previously inaccessible sites.
Usage: python tools/site_recovery.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup

USER_AGENTS = {
    "chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "firefox": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "edge": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
}

RECOVERY_TARGETS = [
    {
        "name": "olloo.mn",
        "urls": [
            "https://olloo.mn/",
            "https://olloo.mn/news",
            "https://olloo.mn/news/",
            "https://olloo.mn/category/news",
            "https://www.olloo.mn/",
            "http://olloo.mn/",
            "https://olloo.mn/mn/",
            "https://olloo.mn/home",
        ],
        "expected_selectors": [
            "a[href*='/news/']", "a[href*='/article/']", "a[href*='/post/']",
            "h2 a", "h3 a", ".news-item a", ".article-item a", ".title a",
        ],
    },
    {
        "name": "mojha.gov.mn",
        "urls": [
            "https://mojha.gov.mn/",
            "https://mojha.gov.mn/news",
            "https://mojha.gov.mn/mn/news",
            "https://www.mojha.gov.mn/",
            "http://mojha.gov.mn/",
        ],
        "expected_selectors": [
            "a[href*='/news/']", "a[href*='/post/']", "a[href*='/article/']",
            "a[href*='/a/']", "h2 a", "h3 a",
        ],
    },
    {
        "name": "intr.gov.mn",
        "urls": [
            "https://intr.gov.mn/",
            "https://intr.gov.mn/news",
            "https://intr.gov.mn/mn/news",
            "https://www.intr.gov.mn/",
            "http://intr.gov.mn/",
        ],
        "expected_selectors": [
            "a[href*='/news/']", "a[href*='/post/']", "a[href*='/article/']",
            "a[href*='/a/']", "h2 a", "h3 a",
        ],
    },
    {
        "name": "customs.gov.mn",
        "urls": [
            "https://customs.gov.mn/",
            "https://customs.gov.mn/mn/",
            "https://customs.gov.mn/home",
            "https://www.customs.gov.mn/",
            "http://customs.gov.mn/",
        ],
        "expected_selectors": [
            "a[href*='/news/']", "a[href*='/post/']", "a[href*='/a/']",
        ],
    },
    {
        "name": "news.mn",
        "urls": [
            "https://news.mn/",
            "https://www.news.mn/",
            "http://news.mn/",
            "https://news.mn/news",
        ],
        "expected_selectors": [
            "a[href*='/news/']", "a[href*='/post/']", "a[href*='/article/']",
        ],
    },
    {
        "name": "prokuror.mn",
        "urls": [
            "https://prokuror.mn/",
            "https://www.prokuror.mn/",
            "http://prokuror.mn/",
            "https://prokuror.mn/news",
        ],
        "expected_selectors": [
            "a[href*='/news/']", "a[href*='/post/']", "a[href*='/a/']",
        ],
    },
]


def probe_site(target):
    """Try all URL + User-Agent combinations for a target site."""
    name = target["name"]
    print(f"\n{'='*60}")
    print(f"Recovery Probe: {name}")
    print(f"{'='*60}")

    best = None

    for url in target["urls"]:
        for ua_name, ua_string in USER_AGENTS.items():
            try:
                headers = {"User-Agent": ua_string}
                resp = requests.get(url, headers=headers, timeout=15,
                                   allow_redirects=True, verify=False)
                status = resp.status_code
                size = len(resp.text)

                if status != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                link_counts = {}
                for sel in target["expected_selectors"]:
                    links = soup.select(sel)
                    if links:
                        link_counts[sel] = len(links)

                total_links = sum(link_counts.values())
                if total_links > 0:
                    result = {
                        "url": url, "ua": ua_name, "size": size,
                        "links": total_links, "selectors": link_counts,
                    }
                    if best is None or total_links > best["links"]:
                        best = result
                    print(f"  [HIT] {url} [{ua_name}] status={status} links={total_links} {dict(link_counts)}")
                elif total_links == 0 and status == 200:
                    # Check if it's JS SPA (no meaningful links at all)
                    text_len = len(soup.get_text(strip=True))
                    all_links = len(soup.find_all("a"))
                    if all_links == 0:
                        print(f"  [SPA] {url} [{ua_name}] 0 links (JS-rendered SPA, text={text_len} chars)")
                    else:
                        # Has links but not matching expected patterns
                        samples = [a.get("href", "")[:80] for a in soup.find_all("a")[:5]]
                        print(f"  [??]  {url} [{ua_name}] {all_links} links but 0 match. Samples: {samples}")

            except requests.exceptions.SSLError:
                pass  # Don't log every SSL failure
            except requests.exceptions.ConnectionError:
                pass
            except Exception as e:
                pass

    if best:
        print(f"\n  >> BEST: {best['url']} [{best['ua']}] → {best['links']} links")
        print(f"  >> Can be recovered! Add to sites.py with this URL + User-Agent.")
        return True
    else:
        print(f"\n  >> UNRECOVERABLE: No working combination found for {name}")
        return False


def main():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    recovered = []
    still_dead = []

    for target in RECOVERY_TARGETS:
        ok = probe_site(target)
        if ok:
            recovered.append(target["name"])
        else:
            still_dead.append(target["name"])

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Recoverable: {recovered if recovered else 'None'}")
    print(f"Still dead:  {still_dead if still_dead else 'None'}")

    if recovered:
        print("\nTo recover, add to sites.py with the best URL + crawler_type.")
    if still_dead:
        print("\nStill-dead sites may need:")
        print("  - Browser F12 inspection to find real API endpoints")
        print("  - Selenium/Playwright for JS rendering")
        print("  - Contacting site admin")


if __name__ == "__main__":
    main()
