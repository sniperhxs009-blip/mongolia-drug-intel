"""Test See.mn sampling from Render perspective"""
import sys, io, asyncio, json
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import httpx
from modules.searcher import _get_drug_keywords

async def test():
    drug_kw = _get_drug_keywords()
    base_url = "https://see.mn"

    # 1. Check homepage
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, verify=False) as client:
        resp = await client.get(base_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://see.mn/",
        })
        print(f"Homepage status: {resp.status_code}, size: {len(resp.text)}")

        # 2. Find article IDs
        import re
        ids = re.findall(r'/(\d+)\.html', resp.text)
        print(f"Found {len(ids)} article IDs on homepage")
        if ids:
            ids_int = [int(i) for i in ids]
            print(f"ID range: {min(ids_int)} - {max(ids_int)}")

        # 3. Test a few article fetches
        test_ids = [58337, 60000, 61000, 62000]
        for aid in test_ids:
            url = f"{base_url}/{aid}.html"
            try:
                r = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "text/html",
                    "Referer": "https://see.mn/",
                }, timeout=8)
                if r.status_code == 200:
                    title_m = re.search(r'<title>(.*?)</title>', r.text[:2000], re.DOTALL)
                    title = title_m.group(1).strip() if title_m else "?"
                    title = re.sub(r'<[^>]+>', '', title)
                    is_drug = any(kw.lower() in title.lower() for kw in drug_kw)
                    print(f"  ID {aid}: 200, title={title[:60]}, drug_match={is_drug}")
                else:
                    print(f"  ID {aid}: {r.status_code}")
            except Exception as e:
                print(f"  ID {aid}: error - {e}")

asyncio.run(test())
