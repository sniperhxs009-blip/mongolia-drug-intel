import sys; sys.stdout.reconfigure(encoding='utf-8')
import sqlite3

conn = sqlite3.connect('police_news.db')
conn.row_factory = sqlite3.Row

# Precise drug-related terms - only terms that specifically mean drugs/narcotics
precise_terms = [
    # Direct drug references (Mongolian)
    'мансууруулах',     # narcotic (stem) - appears in "мансууруулах эм/бодис"
    'хар тамхи',        # drugs (literally "black tobacco")
    'нарко',            # narco stem
    'сэтгэцэд нөлөөлөх', # psychoactive
    'сэтгэцэд нөлөөт',   # psychoactive (variant)
    # Drug names
    'марихуан', 'каннабис', 'гашиш',
    'кокаин', 'героин', 'опиум', 'опий',
    'метамфетамин', 'амфетамин', 'экстази',
    'фентанил', 'кетамин', 'морфин',
    'эфедрин', 'эфедрон', 'мефедрон',
    'метадон', 'дезоморфин',
    'ЛСД', 'МДМА', 'ГХБ', 'ПХП', 'КНБ',
    # English
    'heroin', 'cocaine', 'cannabis', 'marijuana',
    'methamphetamine', 'fentanyl', 'opium',
    'narcotic', 'drug trafficking', 'drug seizure',
    # Russian
    'наркотик', 'кокаин', 'героин',
    # Actions specific to drug enforcement
    'хураан ав',        # seized/confiscated
    'илрүүл',           # detected (in context of drugs)
    'контрабанд',       # contraband
    'хууль бусаар тээвэрлэх', # illegal transport
    # Drug prevention/treatment
    'донтолт', 'донтох', # addiction
    'сэргийл',          # prevention (in drug context)
]

rows = conn.execute("SELECT * FROM articles WHERE length(content) > 100 ORDER BY date DESC").fetchall()

print(f"Scanning {len(rows)} articles for precise drug terms...\n")

found = []
for r in rows:
    text = ((r['title'] or '') + ' ' + (r['content'] or '')).lower()
    title_text = (r['title'] or '').lower()

    matched = []
    title_matched = []
    for term in precise_terms:
        if term.lower() in text:
            matched.append(term)
            if term.lower() in title_text:
                title_matched.append(term)

    if matched:
        found.append((r, matched, title_matched))

print(f"Articles with drug-related content: {len(found)}\n")
for r, matched, title_matched in found:
    d = dict(r)
    print(f"[{d['date']}] {d['source_label']}")
    print(f"  Title: {d['title'][:120]}")
    print(f"  Content matches: {matched}")
    if title_matched:
        print(f"  *** TITLE matches: {title_matched} ***")
    # Show context
    text = ((d['title'] or '') + ' ' + (d['content'] or '')).lower()
    for m in matched[:3]:
        idx = text.find(m.lower())
        if idx >= 0:
            ctx = text[max(0,idx-40):idx+len(m)+40]
            print(f"  '{m}' context: ...{ctx}...")
    print()

conn.close()
