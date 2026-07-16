import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row

# Show all police articles with content previews
rows = conn.execute("SELECT title, content, date FROM articles WHERE source='police.gov.mn' ORDER BY date DESC").fetchall()
print(f"Police articles: {len(rows)}")
for r in rows:
    d = dict(r)
    content = d.get('content', '')
    print(f"\n[{d['date']}] {d['title'][:120]}")
    print(f"  Content ({len(content)} chars): {content[:250]}")

# Also check if any article mentions specific drug slang
print("\n\n=== Searching for drug slang in all articles ===")
slang = ['чихэр', 'өвс', 'ногоон', 'ундаа', 'гурил', 'давс', 'заль', 'хими', 'тариа', 'хар тамхи']
for term in slang:
    cnt = conn.execute("SELECT COUNT(*) FROM articles WHERE content LIKE ? OR title LIKE ?", (f'%{term}%', f'%{term}%')).fetchone()[0]
    if cnt > 0:
        rows = conn.execute("SELECT title, source_label, date FROM articles WHERE content LIKE ? OR title LIKE ?", (f'%{term}%', f'%{term}%')).fetchall()
        for r in rows:
            print(f"  '{term}': [{r['date']}] {r['source_label']}: {r['title'][:100]}")

conn.close()
