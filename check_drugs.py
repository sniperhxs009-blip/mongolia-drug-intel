import sys; sys.stdout.reconfigure(encoding='utf-8')
from db import init_db, search_drug_articles
from drug_keywords import get_all_keywords

init_db()
keywords = get_all_keywords()
results, count = search_drug_articles(keywords, limit=200, months=6)

# Count actual CSTO matches vs non-CSTO
csto_count = sum(1 for r in results if r.get('source') == 'odkb-csto.org')
non_csto = count - csto_count

print(f"Drug-related articles (6 months): {count} total ({csto_count} CSTO, {non_csto} other)")
print()

for r in results:
    d = dict(r)
    print(f"[{d['date']}] {d['source_label']}: {d['title'][:120]}")
    matched = d.get("matched_keywords", [])
    print(f"  Matched ({len(matched)}): {', '.join(matched[:10])}")
    print()
