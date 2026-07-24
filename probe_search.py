"""
Search endpoint probe tool v2 — differential verification.
Uses two unrelated queries to confirm the search endpoint actually filters results.
Usage: python probe_search.py [site_name]
"""
import requests
import sys
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "mn,en;q=0.9,ru;q=0.7",
}

DRUG_QUERY = "хар тамхи"
CONTROL_QUERY = "хөл бөмбөг"  # "football" — unrelated, serves as control

SITES_TO_PROBE = [
    {
        "name": "ikon.mn",
        "base": "https://ikon.mn",
        "patterns": [
            "/search?q={term}",
            "/search/{term}",
            "/search/?q={term}",
            "/?q={term}",
            "/search?keyword={term}",
        ],
        "result_selector": "a[href^='/n/']",
    },
    {
        "name": "gogo.mn",
        "base": "https://gogo.mn",
        "patterns": [
            "/search?q={term}",
            "/search/{term}",
            "/search/?q={term}",
            "/?q={term}",
        ],
        "result_selector": "a[href*='/r/']",
    },
    {
        "name": "shuum.mn",
        "base": "https://shuum.mn",
        "patterns": [
            "/search?q={term}",
            "/search/{term}",
            "/search/?q={term}",
            "/?s={term}",
        ],
        "result_selector": "a[href*='/news-detail/']",
    },
    {
        "name": "unuudur.mn",
        "base": "https://unuudur.mn",
        "patterns": [
            "/search?q={term}",
            "/search/{term}",
            "/search/?q={term}",
            "/?q={term}",
            "/as/niitlel?search={term}",
        ],
        "result_selector": "a[href*='/a/']",
    },
    {
        "name": "olloo.mn",
        "base": "https://olloo.mn",
        "patterns": [
            "/search?q={term}",
            "/search/{term}",
            "/?s={term}",
            "/news/search?q={term}",
        ],
        "result_selector": "a[href*='/news/'], a[href*='/article/']",
    },
]


def probe_site_v2(site):
    """Differential probe: two different queries must produce different results."""
    print(f"\n{'='*60}")
    print(f"Probing: {site['name']}")
    print(f"{'='*60}")

    session = requests.Session()
    session.headers.update(HEADERS)
    confirmed = []

    for pattern in site["patterns"]:
        url_a = site["base"] + pattern.format(term=requests.utils.quote(DRUG_QUERY))
        url_b = site["base"] + pattern.format(term=requests.utils.quote(CONTROL_QUERY))

        try:
            resp_a = session.get(url_a, timeout=15, allow_redirects=True)
            resp_b = session.get(url_b, timeout=15, allow_redirects=True)

            if resp_a.status_code != 200 and resp_b.status_code != 200:
                print(f"  [NO] {url_a} — 两次请求均非 200")
                continue

            soup_a = BeautifulSoup(resp_a.text, "html.parser")
            soup_b = BeautifulSoup(resp_b.text, "html.parser")

            links_a = {a.get("href", "") for a in soup_a.select(site["result_selector"])}
            links_b = {a.get("href", "") for a in soup_b.select(site["result_selector"])}

            if not links_a and not links_b:
                print(f"  [NO] {url_a} — 两次查询都没有结果")
                continue

            if links_a == links_b:
                intersection = len(links_a)
                print(f"  [假阳性] {url_a}")
                print(f"       两个完全不同的搜索词返回了一模一样的 {intersection} 个链接")
                print(f"       该接口没有真正执行搜索（大概率返回首页/固定列表）")
                continue

            # Differential confirmed: results differ
            only_drug = links_a - links_b
            only_ctrl = links_b - links_a
            common = links_a & links_b
            print(f"  [真实可用] {url_a}")
            print(f"       毒品词={len(links_a)}篇, 足球词={len(links_b)}篇")
            print(f"       仅毒品: {len(only_drug)}, 仅足球: {len(only_ctrl)}, 共同: {len(common)}")
            if only_drug:
                print(f"       毒品专属链接样例:")
                for href in list(only_drug)[:3]:
                    print(f"         -> {href[:100]}")
            confirmed.append({
                "pattern": pattern,
                "url": url_a,
                "drug_count": len(links_a),
                "ctrl_count": len(links_b),
                "drug_only": len(only_drug),
            })

        except requests.exceptions.SSLError:
            print(f"  [NO] {url_a} — SSL Error")
        except requests.exceptions.ConnectionError:
            print(f"  [NO] {url_a} — Connection Error")
        except requests.exceptions.Timeout:
            print(f"  [NO] {url_a} — Timeout")
        except Exception as e:
            print(f"  [NO] {url_a} — {type(e).__name__}: {e}")

    if confirmed:
        best = max(confirmed, key=lambda x: x["drug_only"])
        print(f"\n  >> 最佳: {best['pattern']} (毒品专属结果: {best['drug_only']})")
        print(f"  >> 在 sites.py search_url 中使用: {best['pattern']}")
    else:
        print(f"\n  >> 未找到真实可用的搜索接口")
        print(f"  >> 建议: 打开浏览器 F12 → Network，在站内搜索框手动搜'{DRUG_QUERY}'")
        print(f"  >> 抓取真实请求的 URL/方法/参数后更新站点配置")

    return confirmed


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else None

    total_confirmed = 0
    total_false_pos = 0

    for site in SITES_TO_PROBE:
        if target and site["name"] != target:
            continue
        confirmed = probe_site_v2(site)
        total_confirmed += len(confirmed)
        if not confirmed:
            total_false_pos += 1

    print(f"\n{'='*60}")
    print(f"汇总: {total_confirmed} 个确认可用的搜索接口, {total_false_pos} 个站点无可用搜索")
    print(f"{'='*60}")

    if total_false_pos > 0:
        print("\n无可用搜索的站点需要人工浏览器抓包:")
        print("  1. 打开浏览器 F12 → Network 面板")
        print(f"  2. 在站内搜索框输入 '{DRUG_QUERY}'")
        print("  3. 查看发出的实际请求（可能是 POST JSON API）")
        print("  4. 把请求 URL、method、参数贴给我来写解析代码")


if __name__ == "__main__":
    main()
