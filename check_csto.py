import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row

# Show CSTO articles and where drug keywords appear
rows = conn.execute("SELECT title, content, date FROM articles WHERE source='odkb-csto.org' ORDER BY date DESC").fetchall()
for r in rows:
    d = dict(r)
    print(f"[{d['date']}] {d['title'][:120]}")
    # Show first 300 chars of content
    content = d.get('content', '')
    print(f"  Content preview: {content[:300]}")
    print(f"  Content length: {len(content)}")
    # Search where keywords appear
    import re
    for kw in ['наркотик', 'антинаркотической', 'прекурсоров']:
        idx = content.lower().find(kw.lower())
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(content), idx + len(kw) + 40)
            print(f"  '{kw}' context: ...{content[start:end]}...")
    print()
conn.close()
