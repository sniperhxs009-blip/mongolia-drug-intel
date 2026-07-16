import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from collections import Counter

conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row

# Get ALL articles
rows = conn.execute("SELECT * FROM articles WHERE length(content) > 100 ORDER BY date DESC").fetchall()

# Expanded drug-related search terms
terms = [
    # Core drug terms
    'мансууруулах', 'нарко', 'drug', 'тамхи', 'бодис',
    # Drug slang/alternative terms
    'сэтгэцэд нөлөөлөх', 'сэтгэцэд нөлөөт', 'психотроп',
    # Crime/enforcement terms that might accompany drug news
    'хураан ав', 'баривчил', 'илрүүл', 'саатуул',
    'контрабанд', 'хууль бус', 'хууль бусаар', 'наймаа',
    'гэмт хэрэг', 'эрүүгийн', 'мөрдөн', 'шалга',
    # Specific operations
    'ажиллагаа', 'операц', 'устга',
    # International
    'seizure', 'trafficking', 'cocaine', 'heroin', 'cannabis',
    'meth', 'fentanyl', 'opium', 'poppy', 'hashish',
    # Russian
    'изъят', 'конфиск', 'задержан', 'прекурсор',
    'наркотик', 'наркотиков', 'кокаин', 'героин',
    # Mongolian specific
    'хар тамхи', 'мансуур', 'өвс', 'чихэр', 'ундаа',
]

print("=== Scanning all articles for drug-related terms ===\n")
found_any = 0
for r in rows:
    text = ((r['title'] or '') + ' ' + (r['content'] or '')).lower()
    matches = []
    for term in terms:
        if term.lower() in text:
            matches.append(term)
    if matches:
        found_any += 1
        print(f"[{r['date']}] {r['source_label']}: {r['title'][:100]}")
        print(f"  Terms found: {', '.join(matches)}")
        # Show context around key matches
        for m in matches[:3]:
            idx = text.find(m.lower())
            if idx >= 0:
                ctx = text[max(0,idx-30):idx+len(m)+30]
                print(f"  '{m}' context: ...{ctx}...")
        print()

print(f"\nTotal articles with any drug-related term: {found_any}/{len(rows)}")

# Also show unique words that appear near drug terms
print("\n=== Most common words in articles that mention 'мансууруулах' or 'нарко' ===")
drug_words = Counter()
for r in rows:
    text = ((r['title'] or '') + ' ' + (r['content'] or '')).lower()
    if 'мансууруулах' in text or 'нарко' in text:
        words = text.split()
        for w in words:
            if len(w) > 5:
                drug_words[w] += 1

for word, cnt in drug_words.most_common(50):
    print(f"  {word}: {cnt}")

conn.close()
