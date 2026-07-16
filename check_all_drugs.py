import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from drug_keywords import get_all_keywords, BOILERPLATE_KEYWORDS
from datetime import datetime, timedelta

conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row

keywords = get_all_keywords()
filtered_kw = [kw for kw in keywords if len(kw) >= 4 or kw.isupper()]

cutoff = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")

like_clauses = []
params = []
for kw in filtered_kw:
    like = f"%{kw}%"
    like_clauses.append("(title LIKE ? OR content LIKE ?)")
    params.extend([like, like])

where = " OR ".join(like_clauses)
query = f"SELECT * FROM articles WHERE ({where}) AND REPLACE(SUBSTR(date, 1, 10), '.', '-') >= ? ORDER BY date DESC"
rows = conn.execute(query, params + [cutoff]).fetchall()

print(f"Raw matches (no boilerplate filter): {len(rows)}")
print()

for r in rows:
    d = dict(r)
    title_lower = (d.get("title") or "").lower()
    content_lower = (d.get("content") or "").lower()
    matched = []
    specific = []
    boilerplate = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in title_lower or kw_lower in content_lower:
            matched.append(kw)
            if kw in BOILERPLATE_KEYWORDS:
                boilerplate.append(kw)
            else:
                specific.append(kw)

    title_match = any(kw.lower() in title_lower for kw in matched)
    is_csto = d.get('source') == 'odkb-csto.org'

    # Determine if it passes the filter
    if is_csto:
        passes = title_match or len(specific) > 0
    else:
        passes = title_match or len(specific) > 0 or len(matched) >= 2

    status = "PASS" if passes else "FILTERED"

    print(f"[{d['date']}] {d['source_label']}: {d['title'][:100]}")
    print(f"  {status} | Specific: {specific[:5]} | Boilerplate: {boilerplate[:5]} | Title match: {title_match}")
    print()

conn.close()
