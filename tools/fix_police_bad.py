import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from db import DB_PATH, init_db
from multi_crawler import crawl_site
from sites import SITES

init_db()
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Delete police articles with bad content
bad = conn.execute("SELECT id, title, url FROM articles WHERE source='police.gov.mn' AND length(content) < 100").fetchall()
print(f"Bad police articles: {len(bad)}")
for r in bad:
    print(f"  {r['title'][:80]}")
    conn.execute("DELETE FROM articles WHERE id=?", (r['id'],))
    conn.execute("DELETE FROM articles_fts WHERE rowid=?", (r['id'],))
conn.commit()
conn.close()

# Re-crawl police
police = next(s for s in SITES if s['name'] == 'police.gov.mn')
crawl_site(police, max_articles=30, days_filter=30)
