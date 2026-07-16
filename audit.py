"""Full audit: why so few drug-related articles?"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from drug_keywords import get_all_keywords

conn = sqlite3.connect("police_news.db")
conn.row_factory = sqlite3.Row

# 1. Check content quality
empty_content = conn.execute(
    "SELECT COUNT(*) FROM articles WHERE content = title OR length(content) < 100"
).fetchone()[0]
total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
print(f"=== CONTENT QUALITY ===")
print(f"Articles with empty/short content (=title only): {empty_content}/{total}")

# 2. Content length distribution
lengths = conn.execute("""
    SELECT source_label,
           COUNT(*) as cnt,
           AVG(length(content)) as avg_len,
           MIN(length(content)) as min_len,
           MAX(length(content)) as max_len
    FROM articles
    GROUP BY source_label
    ORDER BY avg_len ASC
""").fetchall()
print(f"\n=== CONTENT LENGTH BY SOURCE ===")
for r in lengths:
    flag = " *** EMPTY ***" if r['avg_len'] < 150 else ""
    print(f"  {r['source_label']}: {r['cnt']} articles, avg {r['avg_len']:.0f} chars, min {r['min_len']}, max {r['max_len']}{flag}")

# 3. Search for broader drug terms manually
print(f"\n=== BROAD DRUG TERM SEARCH (anywhere in text) ===")
broad_terms = [
    "хар тамхи", "мансууруулах", "нарко", "narcotic", "drug",
    "контрабанд", "хууль бус", "гаали", "хураан ав",
    "сэтгэцэд нөлөөлөх", "сэтгэцэд нөлөөт",
    "гэмт хэрэг", "эрүүгийн",
    "незаконн", "прекурсор", "психотроп",
    "изъят", "конфиск",
    "марихуан", "каннабис", "кокаин", "опи",
    "фентанил", "метамфетамин", "амфетамин",
    "чихэр",  # slang for pills in Mongolia
]
for term in broad_terms:
    cnt = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE title LIKE ? OR content LIKE ?",
        (f"%{term}%", f"%{term}%")
    ).fetchone()[0]
    if cnt > 0:
        print(f"  '{term}': {cnt} articles")

# 4. Show what police.gov.mn articles are about (most likely to have drug content)
print(f"\n=== POLICE.GOV.MN RECENT ARTICLES ===")
police = conn.execute(
    "SELECT title, date FROM articles WHERE source='police.gov.mn' ORDER BY date DESC LIMIT 15"
).fetchall()
for r in police:
    print(f"  [{r['date']}] {r['title'][:120]}")

# 5. Check ODKB articles for drug terms
print(f"\n=== ODKB ARTICLES WITH DRUG TERMS ===")
odkb = conn.execute(
    "SELECT title, content, date FROM articles WHERE source='odkb-csto.org' AND "
    "(title LIKE '%нарко%' OR content LIKE '%нарко%' OR "
    "title LIKE '%drug%' OR content LIKE '%drug%' OR "
    "title LIKE '%narcotic%' OR content LIKE '%narcotic%' OR "
    "title LIKE '%контрабанд%' OR content LIKE '%контрабанд%')"
).fetchall()
print(f"  Found: {len(odkb)}")
for r in odkb:
    print(f"  [{r['date']}] {r['title'][:120]}")
    print(f"    Content: {r['content'][:200]}")

# 6. Check NEMA articles
print(f"\n=== NEMA ARTICLES WITH DRUG/POTENTIAL TERMS ===")
nema = conn.execute(
    "SELECT title, date FROM articles WHERE source='nema.gov.mn' AND "
    "(title LIKE '%аюул%' OR title LIKE '%осол%' OR title LIKE '%хэрэг%' OR "
    "title LIKE '%хууль%' OR title LIKE '%эрсдэл%')"
    "ORDER BY date DESC LIMIT 10"
).fetchall()
print(f"  Found: {len(nema)}")
for r in nema:
    print(f"  [{r['date']}] {r['title'][:120]}")

# 7. Full text search for any drug-related content in all articles
print(f"\n=== FULL SCAN: ANY ARTICLE WITH DRUG HINTS ===")
# Get ALL articles with any content
rows = conn.execute("SELECT * FROM articles WHERE length(content) > 100 ORDER BY date DESC").fetchall()
keywords = get_all_keywords()
found = 0
for r in rows:
    text = ((r['title'] or '') + ' ' + (r['content'] or '')).lower()
    for kw in keywords:
        if len(kw) >= 4 and kw.lower() in text:
            found += 1
            print(f"  [{r['date']}] {r['source_label']}: {r['title'][:100]}")
            print(f"    Keyword: '{kw}'")
            break

if found == 0:
    print("  NONE FOUND - articles truly don't contain drug keywords!")
    print(f"  Checked {len(rows)} articles with actual content against {len(keywords)} keywords")

conn.close()
