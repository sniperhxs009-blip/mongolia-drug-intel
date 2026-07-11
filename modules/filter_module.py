"""
过滤模块 v3.0 - 严格模式
必须同时满足：蒙古地理锚点 + 毒品相关关键词，两者缺一不可
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

with open(CONFIG_DIR / "keywords.json", "r", encoding="utf-8") as f:
    KEYWORDS_CONFIG = json.load(f)

# 蒙古地理锚点（必须命中至少一个）
MONGOLIA_GEO_KEYWORDS = [
    # 蒙古相关
    "монгол", "Mongolia", "Mongol", "Монгол",
    "蒙古", "乌兰巴托", "Ulaanbaatar", "Улаанбаатар",
    # 中蒙口岸
    "扎门乌德", "Zamyn-Uud", "Замын-Үүд",
    "甘其毛都", "Ganqimaodao", "Ганцмод",
    "二连浩特", "Erenhot", "Эрээн",
    "策克", "Ceke",
    "满都拉", "Mandula", "Мандал",
    # 蒙古省份/城市
    "达尔汗", "Darkhan", "Дархан",
    "额尔登特", "Erdenet", "Эрдэнэт",
    "乔巴山", "Choibalsan", "Чойбалсан",
    "科布多", "Khovd", "Ховд",
    "巴彦洪戈尔", "Bayankhongor",
    # 边境相关
    "中蒙边境", "中蒙口岸",
    "Mongolia-China border",
    "хилийн", "хил",  # 蒙古语：边境
]

# 毒品相关关键词（必须命中至少一个）
DRUG_KEYWORDS = [
    # 中文毒品词
    "毒品", "缉毒", "禁毒", "贩毒", "涉毒", "吸毒", "戒毒",
    "芬太尼", "fentanyl", "фентанил",
    "冰毒", "methamphetamine", "метамфетамин",
    "海洛因", "heroin", "героин",
    "可卡因", "cocaine", "кокаин",
    "大麻", "cannabis", "marijuana", "хар тамхи", "марихуана",
    "鸦片", "opium", "опиум",
    "摇头丸", "ecstasy",
    "麻古", "麻果",
    "氯胺酮", "ketamine", "кетамин",
    "合成毒品", "synthetic drug", "синтетик",
    "易制毒", "precursor chemical",
    "精神药品", "psychotropic",
    "管制药品", "controlled substance",
    "麻醉药品", "narcotic", "наркотик",
    # 蒙语毒品词
    "мансууруулах", "мансууруулагч", "мансуур",
    "баривчилгаа",  # 查获（毒品语境）
    "хураан",  # 收缴
    # 英文毒品词
    "drug seizure", "drug trafficking", "drug smuggling",
    "narcotics", "narco",
    "opioid", "опиоид",
    "rehabilitation",  # 戒毒
    "drug law", "drug policy",
    "substance abuse",
    # 走私+毒品
    "走私毒品", "跨境毒品", "drug bust",
    "drug arrest", "drug raid",
    "drug enforcement",
    # 口岸查获（毒品语境需要配合蒙古地理词）
    "хил", "гааль",
]


def _text_contains_any(text: str, keywords: list[str]) -> bool:
    """检查文本是否包含任意关键词（不区分大小写）"""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def strict_filter(item: dict) -> bool:
    """
    严格过滤：必须同时满足两个条件
    1. 包含蒙古地理锚点
    2. 包含毒品相关关键词
    """
    text = f"{item.get('news_title', '')} {item.get('content_summary', '')} {item.get('source_name', '')}"
    if not text.strip():
        return False

    has_mongolia_geo = _text_contains_any(text, MONGOLIA_GEO_KEYWORDS)
    has_drug_keyword = _text_contains_any(text, DRUG_KEYWORDS)

    return has_mongolia_geo and has_drug_keyword


# 兼容旧接口
def has_any_keyword_match(item: dict) -> bool:
    return strict_filter(item)


def should_keep(item: dict) -> bool:
    return strict_filter(item)


def is_pure_inland_china_irrelevant(item: dict) -> bool:
    return not strict_filter(item)


def apply_filters(items: list[dict]) -> tuple[list[dict], int]:
    kept = []
    filtered = 0
    for item in items:
        if strict_filter(item):
            kept.append(item)
        else:
            filtered += 1
    return kept, filtered
