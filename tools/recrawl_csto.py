import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from db import DB_PATH, init_db
from multi_crawler import crawl_site
from sites import SITES

init_db()
conn = sqlite3.connect(DB_PATH)

# Delete CSTO articles
conn.execute("DELETE FROM articles WHERE source='odkb-csto.org'")
conn.execute("DELETE FROM articles_fts WHERE rowid NOT IN (SELECT id FROM articles)")
conn.commit()
remaining = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
print(f"Deleted CSTO articles. Remaining: {remaining}")
conn.close()

# Re-crawl CSTO
csto = next(s for s in SITES if s['name'] == 'odkb-csto.org')
crawl_site(csto, max_articles=30)
