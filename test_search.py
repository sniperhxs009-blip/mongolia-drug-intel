"""Final wrap test"""
import json, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key] = val

from modules.search_engines import search_all_articles

articles = search_all_articles()

with open("deepseek_test_output.txt", "w", encoding="utf-8") as f:
    json.dump(articles, f, ensure_ascii=False, indent=2)

print(f"\n=== Total: {len(articles)} articles ===")
sources = {}
for a in articles:
    src = a.get('source_name', '?')
    sources[src] = sources.get(src, 0) + 1
print("Sources:", sources)

has_summary = sum(1 for a in articles if a.get('content_summary'))
print(f"Articles with summary: {has_summary}/{len(articles)}")

for i, a in enumerate(articles):
    title = a.get('news_title', '')[:100]
    url = a.get('source_url', '')[:90]
    summary = a.get('content_summary', '')[:80]
    print(f"{i+1}. [{a.get('source_name','')}] {title}")
    print(f"   {url}")
    if summary:
        print(f"   S: {summary}")
    print()
