"""
Drug-related keyword scoring system for Mongolian news filtering.

Design: Three-tier keyword scoring ensures sustainability.
- TIER 1 (3 pts): Specific drug names/substances — unambiguous signal
- TIER 2 (2 pts): Drug-specific multi-word phrases — strong context
- TIER 3 (1 pt):  Context words — weak signal, only meaningful alongside TIER 1/2
- Title bonus: +2 pts if any keyword matches in the title
- Threshold: >= 4 points → drug-related article

To add new keywords: just append to the appropriate tier list below.
The scoring function automatically weights them correctly for all sources.
"""

import re


# === TIER 1: Specific drug names (3 points each) ===
# These are unambiguous — if an article mentions heroin, it IS drug-related.
TIER1_KEYWORDS = [
    # Mongolian drug names
    "марихуана", "каннабис", "гашиш",
    "метамфетамин", "амфетамин", "экстази",
    "фентанил", "карфентанил", "метилфентанил", "фуранилфентанил",
    "кетамин", "псилоцибин", "мескалин",
    "мефедрон", "метилэфедрон", "меткатинон", "катинон", "эфедрон",
    "морфин", "кодеин", "метадон", "дезоморфин",
    "триазолам", "флунитразепам", "диазепам", "алпразолам", "клоназепам", "фенобарбитал",
    "фентермин", "фенциклидин",
    "эфедрин", "псевдоэфедрин",

    # Annaka specific
    "анага бодис", "кофеин натри бензоат", "аннака",

    # Russian drug names
    "кокаин", "героин", "опиум", "опий",
    "конопля", "гашишное масло", "маковая соломка",

    # English drug names
    "heroin", "cocaine", "crack", "cannabis", "marijuana", "hashish",
    "methamphetamine", "crystal meth", "amphetamine",
    "fentanyl", "carfentanil", "methylfentanyl", "furanylfentanyl",
    "ketamine", "psilocybin", "mescaline",
    "mephedrone", "methcathinone", "cathinone",
    "morphine", "codeine", "methadone",
    # Street names / slang
    "weed", "pot", "dope", "meth", "ice", "molly", "shrooms", "magic mushrooms",
    "ecstasy", "crank", "speed",

    # Abbreviations (always uppercase for disambiguation)
    "ЛСД", "МДМА", "ГХБ", "ПХП", "КНБ",
    "LSD", "MDMA", "PCP", "GHB", "4-MEC", "4MEC",
]

# === TIER 2: Drug-specific phrases (2 points each) ===
# Multi-word phrases that strongly indicate drug context, not general crime.
TIER2_KEYWORDS = [
    # Mongolian drug phrases
    "хар тамхи",                    # "black tobacco" = drugs
    "мансууруулах эм",              # narcotic drug
    "мансууруулах бодис",           # narcotic substance
    "сэтгэцэд нөлөөлөх бодис",     # psychoactive substance
    "сэтгэцэд нөлөөт бодис",       # psychoactive substance (alt)
    "мансууруулах бодисын наймаа", # narcotics trafficking
    "хил хар тамхины наймаа",      # cross-border drug trade
    "хар тамхины хямдрал",         # drug crackdown
    "хар тамхи хадгалсан",         # drug possession
    "хар тамхи худалдсан",         # drug sale
    "хар тамхины бүлэглэл",        # drug gang
    "нууц лаборатори",              # secret lab
    "газрын тосны эфир",           # petroleum ether (extraction solvent)

    # Russian drug-specific phrases
    "наркотрафик",                  # drug trafficking
    "наркокурьер",                  # drug courier
    "наркомафия",                   # drug mafia
    "наркопритон",                  # drug den
    "нарколаборатория",             # drug lab
    "наркозависимость",             # drug addiction
    "наркосодержащих",              # narcotic-containing
    "трансграничная контрабанда наркотиков",  # cross-border drug smuggling
    "изъятие наркотиков",           # drug seizure
    "прекурсоры наркотиков",        # drug precursors

    # English drug-specific
    "drug trafficking",             # drug trafficking
    "drug seizure",                 # drug seizure
    "cross-border drug trafficking", # cross-border drug trafficking
    "anti-narcotics operation",      # anti-narcotics operation
    "drug precursor chemicals",      # drug precursor chemicals
    "Mongolia drug seizure",         # Mongolia drug seizure
    "Mongolia customs bust",         # Mongolia customs bust
    "opium poppy",                   # opium poppy
    "cannabis flower",               # cannabis flower
    "hash oil",                      # hash oil
]

# === TIER 3: Context words (1 point each) ===
# These are drug-related but can appear in non-drug contexts (CSTO boilerplate,
# general crime reports, etc.). Only counted when TIER 1/2 keywords also match.
TIER3_KEYWORDS = [
    # Narcotics stems (appear in CSTO boilerplate)
    "наркотик", "наркотиков", "наркотические", "наркотический", "нарко",
    "антинаркотической", "антинаркотическ",
    "антинаркотическая операция", "антинаркотической операции",
    "психотропных", "психотропные", "психотропные вещества",
    "прекурсоров", "прекурсоры",
    "незаконного оборота", "незаконный оборот",
    "подконтрольных веществ", "запрещенных веществ",

    # Drug-related actions (can appear in non-drug crime contexts)
    "контрабанда", "контрабанды",
    "хураан авсан", "хураан ав",
    "изъято", "конфисковано",

    # Generic drug terms (Mongolian)
    "мансууруулах",                 # "narcotic" stem
    "сэтгэцэд нөлөөлөх",           # "psychoactive" stem
    "сэтгэцэд нөлөөт",             # "psychoactive" stem (alt)
    "донтолт", "донтох",           # addiction
    "наркотический", "наркотические",

    # English generic
    "narcotic", "narcotics", "drug", "precursor",
    "UNODC", "Interpol",

    # General crime terms (only meaningful alongside drug terms)
    "хууль бус импорт", "хууль бусаар тээвэрлэх",
    "эрүүгийн хэрэг",
    "химийн прекурсор",
    "галлюциноген",
    "снотворное", "тайвшруулагч", "нойрсуулагч",
]


# Short English keywords that require word boundaries to avoid false positives.
# E.g. "ice" should NOT match "police", "meth" should NOT match "method".
WORD_BOUNDARY_KEYWORDS = {"weed", "pot", "dope", "meth", "ice", "molly", "crack", "speed", "crank"}


def _contains_keyword(text, keyword):
    """Check if keyword is in text. Short English words use word boundaries."""
    if keyword.lower() in WORD_BOUNDARY_KEYWORDS:
        return bool(re.search(r'\b' + re.escape(keyword) + r'\b', text))
    return keyword.lower() in text.lower()



def get_all_keywords():
    """Flat list of all keywords for broad DB search."""
    all_kw = set()
    all_kw.update(TIER1_KEYWORDS)
    all_kw.update(TIER2_KEYWORDS)
    all_kw.update(TIER3_KEYWORDS)
    return list(all_kw)


def score_article(title, content, source=None):
    """
    Score an article for drug relevance. Returns (score, matched_tier1, matched_tier2, matched_tier3, title_match).

    Threshold: >= 4 points = drug-related article.

    This is the core function — it works identically for old and new articles,
    and automatically adapts when new keywords are added to the tier lists.
    """
    text = ((title or '') + ' ' + (content or '')).lower()
    title_lower = (title or '').lower()

    matched_t1 = [kw for kw in TIER1_KEYWORDS if _contains_keyword(text, kw)]
    matched_t2 = [kw for kw in TIER2_KEYWORDS if _contains_keyword(text, kw)]
    matched_t3 = [kw for kw in TIER3_KEYWORDS if _contains_keyword(text, kw)]

    # Title match check
    title_match = any(
        _contains_keyword(title_lower, kw)
        for kw in TIER1_KEYWORDS + TIER2_KEYWORDS + TIER3_KEYWORDS
    )

    # Calculate score
    score = 0
    score += len(matched_t1) * 3
    score += len(matched_t2) * 2

    # TIER 3 only counts if TIER 1 or 2 also matched (prevents boilerplate-only matches)
    has_strong_signal = len(matched_t1) > 0 or len(matched_t2) > 0
    if has_strong_signal:
        score += len(matched_t3) * 1

    # Title bonus
    if title_match:
        score += 2

    return score, matched_t1, matched_t2, matched_t3, title_match


def is_drug_article(title, content, source=None):
    """Returns True if the article passes the drug relevance threshold."""
    score, _, _, _, _ = score_article(title, content, source)
    return score >= 4


def match_drug_keywords(text):
    """Check if text contains any drug-related keywords. Returns matched categories."""
    if not text:
        return []
    text_lower = text.lower()
    matched = []
    all_kw = get_all_keywords()
    for kw in all_kw:
        if _contains_keyword(text_lower, kw):
            matched.append(kw)
    return matched
