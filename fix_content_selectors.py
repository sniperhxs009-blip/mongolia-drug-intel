"""Test article page structure for each site to find correct content selectors."""
import requests
from bs4 import BeautifulSoup
import urllib3
urllib3.disable_warnings()

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "mn-MN,mn;q=0.9,en;q=0.8",
})
session.verify = False

tests = [
    {
        "name": "警察总局",
        "url": "https://police.gov.mn/a/8155",
        "content_selectors": [
            "article p", ".article-content p", ".article-view-content p",
            ".uk-article p", ".content p", "p",
        ]
    },
    {
        "name": "蒙通社",
        "url": "https://montsame.mn/mn/read/404745",
        "content_selectors": [
            "article p", ".article-body p", ".read-content p",
            ".news-content p", ".content p", "p",
        ]
    },
    {
        "name": "Ikon新闻",
        "url": "https://ikon.mn/n/3ozw",
        "content_selectors": [
            "article p", ".article-content p", ".news-content p",
            ".content p", ".post-content p", "p",
        ]
    },
    {
        "name": "UNODC",
        "url": "https://www.unodc.org/unodc/frontpage/2026/July/unodc-executive-director-addresses-the-economic-and-social-council-on-the-world-drug-report-2026.html",
        "content_selectors": [
            "article p", ".story-content p", ".field-body p",
            ".content p", ".article-content p", "p",
        ]
    },
    {
        "name": "Shuum新闻",
        "url": "https://shuum.mn/news-detail/26909",
        "content_selectors": [
            "article p", ".news-content p", ".post-body p",
            ".content p", ".detail-content p", "p",
        ]
    },
]

for test in tests:
    print(f"\n{'='*60}")
    print(f"  {test['name']}: {test['url']}")
    print(f"{'='*60}")
    try:
        r = session.get(test["url"], timeout=20)
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")

        for sel in test["content_selectors"]:
            els = soup.select(sel)
            if els:
                total = sum(len(e.get_text(strip=True)) for e in els)
                # Get actual text from first few elements
                texts = [e.get_text(strip=True) for e in els[:3] if len(e.get_text(strip=True)) > 20]
                if texts:
                    print(f"  SELECTOR '{sel}': {len(els)} elements, ~{total} chars total")
                    for t in texts:
                        print(f"    -> {t[:150]}")
                    break  # found working selector
        else:
            print(f"  NO WORKING SELECTOR FOUND!")
            # Show page structure
            body = soup.find("body")
            if body:
                for tag in body.find_all(["div", "article", "section"]):
                    cls = " ".join(tag.get("class", []))
                    txt = tag.get_text(strip=True)
                    if len(txt) > 200 and len(txt) < 5000:
                        if any(k in cls.lower() for k in ["content", "article", "post", "news", "story", "body", "detail", "read", "entry"]):
                            print(f"    Possible: <{tag.name} class='{cls}'> ({len(txt)} chars)")
                            print(f"      -> {txt[:200]}")

    except Exception as e:
        print(f"  ERROR: {e}")
