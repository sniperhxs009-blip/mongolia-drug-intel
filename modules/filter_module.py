"""
过滤模块 v3.1 - 从 keywords.json 动态加载全量关键词
必须同时满足：蒙古地理锚点 + 毒品/缉毒相关关键词
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

with open(CONFIG_DIR / "keywords.json", "r", encoding="utf-8") as f:
    KW = json.load(f)

# 蒙古地理锚点（从 JSON 动态加载）
GEO_ANCHORS = []
geo_data = KW.get("geo_anchors", {})
for group in geo_data.values():
    if isinstance(group, list):
        GEO_ANCHORS.extend(group)

# 毒品关键词（从 JSON 的 drug_keywords_full 加载所有语种）
DRUG_KEYWORDS = []
drug_data = KW.get("drug_keywords_full", {})
for lang_words in drug_data.values():
    if isinstance(lang_words, list):
        DRUG_KEYWORDS.extend(lang_words)

# 也加入各语种 primary + secondary 以及分类中的词
for lang, lang_data in KW.get("keywords", {}).items():
    for key in ("primary", "secondary"):
        words = lang_data.get(key, [])
        if isinstance(words, list):
            DRUG_KEYWORDS.extend(words)
    for cat_name, cat_data in lang_data.get("categories", {}).items():
        words = cat_data.get("words", [])
        if isinstance(words, list):
            DRUG_KEYWORDS.extend(words)
    combined = lang_data.get("combined_phrases", [])
    if isinstance(combined, list):
        DRUG_KEYWORDS.extend(combined)

# 去重
GEO_ANCHORS = list(set(g.lower() for g in GEO_ANCHORS if g.strip()))
DRUG_KEYWORDS = list(set(d.lower() for d in DRUG_KEYWORDS if d.strip()))


def _contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def strict_filter(item: dict) -> bool:
    """
    严格过滤：必须同时满足
    1. 命中蒙古地理锚点
    2. 命中毒品/缉毒关键词
    """
    text = f"{item.get('news_title', '')} {item.get('content_summary', '')} {item.get('source_name', '')} {item.get('site_category', '')}"
    if not text.strip():
        return False

    has_geo = _contains_any(text, GEO_ANCHORS)
    has_drug = _contains_any(text, DRUG_KEYWORDS)

    return has_geo and has_drug


# 兼容旧接口
def has_any_keyword_match(item: dict) -> bool:
    return strict_filter(item)


def should_keep(item: dict) -> bool:
    return strict_filter(item)


def is_pure_inland_china_irrelevant(item: dict) -> bool:
    return not strict_filter(item)


def apply_filters(items: list[dict]) -> tuple[list[dict], int]:
    kept, filtered = [], 0
    for item in items:
        if strict_filter(item):
            kept.append(item)
        else:
            filtered += 1
    return kept, filtered
