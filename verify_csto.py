import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from drug_keywords import get_all_keywords

conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row

# Check CSTO content uniqueness by comparing first 100 chars
csto = conn.execute("SELECT title, content, date FROM articles WHERE source='odkb-csto.org' ORDER BY date DESC").fetchall()
print(f"CSTO articles: {len(csto)}")
contents = [dict(r) for r in csto]
# Check if all contents start the same
first_chars = [c['content'][:100] for c in contents]
unique_starts = set(first_chars)
print(f"Unique content starts: {len(unique_starts)} out of {len(contents)}")
if len(unique_starts) < len(contents):
    print("*** CONTENT STILL DUPLICATED! ***")
    from collections import Counter
    for start, cnt in Counter(first_chars).most_common(5):
        print(f"  '{start[:80]}...' appears {cnt} times")
else:
    print("Content looks diverse!")

# Show content previews for first few
for c in contents[:5]:
    print(f"\n[{c['date']}] {c['title'][:100]}")
    print(f"  Content: {c['content'][:200]}")
    print(f"  Length: {len(c['content'])}")

# Drug check
keywords = get_all_keywords()
filtered_kw = [kw for kw in keywords if len(kw) >= 4 or kw.isupper()]
like_clauses = []
params = []
for kw in filtered_kw:
    like = f"%{kw}%"
    like_clauses.append("(title LIKE ? OR content LIKE ?)")
    params.extend([like, like])

where = " OR ".join(like_clauses)
query = f"SELECT * FROM articles WHERE ({where}) ORDER BY date DESC"
rows = conn.execute(query, params).fetchall()
print(f"\n=== DRUG MATCHES: {len(rows)} total ===")
for r in rows:
    d = dict(r)
    title_lower = (d.get("title") or "").lower()
    content_lower = (d.get("content") or "").lower()
    matched = []
    for kw in keywords:
        if kw.lower() in title_lower or kw.lower() in content_lower:
            matched.append(kw)
    # Show title match vs content match
    title_matches = [kw for kw in matched if kw.lower() in title_lower]
    print(f"\n[{d['date']}] {d['source_label']}: {d['title'][:100]}")
    if title_matches:
        print(f"  TITLE matches: {', '.join(title_matches[:5])}")
    content_only = [kw for kw in matched if kw not in title_matches]
    if content_only:
        print(f"  CONTENT only: {', '.join(content_only[:8])}")

conn.close()
