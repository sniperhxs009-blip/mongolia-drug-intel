import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row
total = conn.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
empty = conn.execute('SELECT COUNT(*) FROM articles WHERE length(content) < 100 OR content = title').fetchone()[0]
print(f'Total: {total}, Empty/short content: {empty} ({100*empty/total:.0f}%)')
print()
print('Content length by source:')
for r in conn.execute('SELECT source_label, COUNT(*) as cnt, AVG(length(content)) as avg_len, MIN(length(content)) as min_len, MAX(length(content)) as max_len FROM articles GROUP BY source_label ORDER BY avg_len ASC').fetchall():
    flag = ' *** EMPTY ***' if r['avg_len'] < 150 else ''
    print(f"  {r['source_label']}: {r['cnt']} articles, avg {r['avg_len']:.0f} chars, min {r['min_len']}, max {r['max_len']}{flag}")
conn.close()
