"""Delete articles with empty/short content, then re-crawl to get proper content."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from db import DB_PATH, init_db
from multi_crawler import crawl_all

init_db()
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Find articles where content is essentially just the title (empty content)
total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
empty = conn.execute(
    "SELECT COUNT(*) FROM articles WHERE length(content) < 100 OR content = title"
).fetchone()[0]

print(f"Total articles: {total}")
print(f"Articles with empty/short content: {empty} ({100*empty/total:.0f}%)")

if empty > 0:
    # Show what will be deleted by source
    by_source = conn.execute("""
        SELECT source_label, COUNT(*) as cnt
        FROM articles
        WHERE length(content) < 100 OR content = title
        GROUP BY source_label
        ORDER BY cnt DESC
    """).fetchall()
    print("\nArticles to delete by source:")
    for r in by_source:
        print(f"  {r['source_label']}: {r['cnt']}")

    conn.execute("DELETE FROM articles WHERE length(content) < 100 OR content = title")
    conn.execute("DELETE FROM articles_fts WHERE rowid NOT IN (SELECT id FROM articles)")
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    print(f"\nDeleted {empty} articles. Remaining: {remaining}")

conn.close()

# Now re-crawl all sites
print("\n" + "="*60)
print("RE-CRAWLING ALL SITES WITH FIXED CONTENT SELECTORS...")
print("="*60)
crawl_all(max_per_site=50, days_filter=180)
