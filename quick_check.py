import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row
bad = conn.execute("SELECT title, length(content) as l, content FROM articles WHERE source='police.gov.mn' AND length(content) < 100").fetchall()
print(f'Bad police articles remaining: {len(bad)}')
for r in bad:
    print(f"  {r['title'][:80]}: {r['l']} chars")
    print(f"    -> {r['content'][:150]}")

# Also total quality check
total = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
empty = conn.execute('SELECT COUNT(*) FROM articles WHERE length(content) < 100 OR content = title').fetchone()[0]
print(f'\nTotal: {total}, Empty/short: {empty} ({100*empty/total:.0f}%)')
conn.close()
