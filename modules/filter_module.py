"""
AI 智能过滤模块 v4.0
====================
规则引擎模拟 AI 分类：区分毒品执法/走私/查获新闻 vs 普通医药监管网页。

核心逻辑：
  - 强毒品词（наркотик/мансууруулах/фентанил/毒品/heroin 等）→ 高置信度通过
  - 弱药字（эм/эмийн/drug/药品）→ 必须伴随执法动作词才通过
  - 排除词（副作用/疫苗/伦理投诉/注册/质量检测 等）→ 直接拒绝
  - 30 日内日期过滤
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

with open(CONFIG_DIR / "keywords.json", "r", encoding="utf-8") as f:
    KW = json.load(f)

# ============================================================
# 蒙古地理锚点
# ============================================================
GEO_ANCHORS = []
geo_data = KW.get("geo_anchors", {})
for group in geo_data.values():
    if isinstance(group, list):
        GEO_ANCHORS.extend(group)
GEO_ANCHORS = list(set(g.lower() for g in GEO_ANCHORS if g.strip()))

# ============================================================
# 强毒品关键词（毒品/缉毒/贩毒 强关联，命中即高置信度）
# ============================================================
STRONG_DRUG_WORDS = [
    # === 蒙语：明确的毒品/缉毒词汇 ===
    "мансууруулах", "мансууруулагч", "наркотик", "нарко",
    "фентанил", "метамфетамин", "героин", "опиум", "опиат",
    "экстази", "кокаин", "аннака",
    "хар тамхи", "мансуур",
    # 蒙语：明确的毒品查缉动作
    "баривчилгаа", "хураан авах", "хулгайлах",
    "мансууруулах бодис", "мансууруулах донтолт",
    "мансууруулах эсэргүүцэх", "мансууруулах урьдчилан сэргийлэх",
    "сэргээх төв",
    "мансууруулах бодисын",

    # === 中文：明确的毒品词汇 ===
    "毒品", "缉毒", "禁毒", "贩毒", "涉毒", "吸毒", "戒毒", "扫毒", "肃毒",
    "芬太尼", "冰毒", "海洛因", "鸦片", "大麻", "摇头丸", "可卡因",
    "合成毒品", "安纳咖", "甲基苯丙胺", "氯胺酮",
    "贩运毒品", "走私毒品", "毒品走私", "跨境贩毒",
    "制毒", "吸毒人员", "毒瘾", "戒毒所",
    "缉毒专项", "禁毒专项", "扫毒行动",

    # === 英文：明确的毒品/缉毒词汇 ===
    "narcotics", "narco", "fentanyl", "heroin", "cocaine",
    "methamphetamine", "meth", "opium", "ecstasy", "ketamine",
    "drug trafficking", "drug smuggling", "drug bust", "drug seizure",
    "drug enforcement", "drug raid", "drug arrest",
    "anti-narcotics", "drug cartel",
    "smuggling of narcotics", "narcotics control",
]

# ============================================================
# 执法/犯罪/口岸缉私 上下文词（必须搭配弱药字才通过）
# ============================================================
ENFORCEMENT_WORDS = [
    # 蒙语
    "баривчилгаа", "хураан", "хулгайлах", "мөрдөн байцаалт",
    "барих", "баригдсан", "шүүх", "хорих", "торгууль",
    "цагдаа", "прокурор", "аюулгүй байдлын газар",
    "хил", "гааль", "хилийн боомт",
    "хяналт", "шалгалт", "илрүүлэх", "нууц",
    # 中文
    "查获", "缴获", "抓捕", "捣毁", "走私", "贩运",
    "跨境", "边防", "口岸", "海关", "缉私", "查验",
    "刑侦", "专案", "联合办案", "堵截",
    "毒品犯罪", "涉毒案件", "制毒窝点",
    # 英文
    "seizure", "arrest", "smuggling", "trafficking", "bust",
    "crackdown", "investigation", "prosecution", "confiscate",
    "intercept", "police", "customs", "border",
    "criminal", "crime", "prison", "court", "sentence",
    "enforcement", "raid", "operation", "sting",
]

# ============================================================
# 排除词（医疗/药品监管/行政/疫苗/伦理 等非毒品内容）
# 命中任何一个 → 直接拒绝
# ============================================================
EXCLUSION_WORDS = [
    # === 蒙语排除词 ===
    # 药品副作用、不良反应
    "гаж нөлөө", "гаж нөлөөний", "гаж урвал",
    "вакцин", "вакцины", "коронавирус", "коронавирусээс", "ковид",
    "дархлаажуулалт", "вакцинжуулалт",
    # 药品注册、质量、实验室
    "бүртгэл", "бүртгүүлэх", "бүртгэгдсэн",
    "чанарын", "чанар", "лаборатори", "шинжилгээ",
    # 伦理投诉
    "ёс зүйн", "ёс зүй", "гомдол",
    # 培训、会议、教育
    "сургалт", "семинар", "хурал", "чуулган", "зөвлөгөөн",
    "сургалтын", "танхим",
    # 药品检测、许可
    "зөвшөөрөл", "тусгай зөвшөөрөл", "лиценз",
    "гэрчилгээ", "сертификат",
    # 维生素、保健
    "витамин", "хүнсний нэмэлт", "биологийн идэвхт",
    # 医药代表、广告
    "сурталчилгаа", "зар",
    # 非毒品行政
    "төрийн албан", "төрийн захиргаа", "нийтийн",

    # === 中文排除词 ===
    "副作用", "不良反应", "疫苗", "新冠", "冠状",
    "注册证", "质量检测", "药品注册", "GMP认证",
    "伦理投诉", "道德投诉", "培训", "研讨会",
    "维生素", "保健品", "医疗器械注册",
    # 纯医药行业新闻
    "药品招标", "药品采购", "医保", "基药目录",
    "药品说明书", "用药指南", "合理用药",

    # === 英文排除词 ===
    "side effect", "adverse reaction", "vaccine", "coronavirus", "covid",
    "registration certificate", "quality control", "quality assurance",
    "vitamin", "supplement", "dietary",
    "ethical complaint", "grievance",
    "training", "workshop", "seminar", "conference",
    "pharmaceutical industry", "drug registration", "medicine registration",
]

# ============================================================
# 弱药字（药品/medicine，需要执法上下文支持）
# 单独命中不算毒品相关
# ============================================================
WEAK_DRUG_WORDS = [
    "эм", "эмийн", "эмнэлгийн", "эмийг",
    "drug", "drugs", "pharmaceutical", "medicine", "medication",
    "substance", "substances",
    "药品", "药物", "医药", "药剂",
    "controlled substance", "psychotropic",
]


def _contains_any(text: str, keywords: list[str]) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def _count_hits(text: str, keywords: list[str]) -> int:
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw.lower() in text_lower)


def ai_classify(item: dict) -> dict:
    """
    AI 规则分类器：分析文章并返回分类结果。
    返回 { "pass": bool, "score": int, "reason": str }
    """
    title = item.get("news_title", "")
    summary = item.get("content_summary", "")
    source = item.get("source_name", "")
    # 用标题+摘要+来源做分类（不包含 source_url 避免 URL 噪音）
    text = f"{title} {summary} {source}"

    if not title.strip() and len(summary.strip()) < 30:
        return {"pass": False, "score": 0, "reason": "内容过短"}

    # === 第1步：排除词检查 ===
    exclusion_hits = [kw for kw in EXCLUSION_WORDS if kw.lower() in text.lower()]
    if exclusion_hits:
        # 但有强毒品词时覆盖排除（例如标题有"毒品"但内容有"药品注册"可能是正常新闻）
        has_strong_override = _contains_any(text, STRONG_DRUG_WORDS)
        if not has_strong_override:
            return {"pass": False, "score": -10, "reason": f"命中排除词: {exclusion_hits[:3]}"}

    # === 第2步：强毒品词评分 ===
    strong_hits = [kw for kw in STRONG_DRUG_WORDS if kw.lower() in text.lower()]
    strong_score = len(strong_hits) * 3

    # === 第3步：执法上下文评分 ===
    enforcement_hits = [kw for kw in ENFORCEMENT_WORDS if kw.lower() in text.lower()]
    enforcement_score = len(enforcement_hits) * 2

    # === 第4步：弱药字检查 ===
    weak_hits = [kw for kw in WEAK_DRUG_WORDS if kw.lower() in text.lower()]
    has_weak_drug = len(weak_hits) > 0

    # === 第5步：地理锚点评分 ===
    geo_hits = [kw for kw in GEO_ANCHORS if kw.lower() in text.lower()]
    geo_score = len(geo_hits) * 1

    # === 第6步：综合判定 ===
    total_score = strong_score + enforcement_score + geo_score

    # 情况A：有强毒品词 → 直接通过
    if strong_hits:
        # 强毒品词 + 地理锚点 = 极高置信度
        if geo_hits:
            return {"pass": True, "score": total_score, "reason": f"强毒品词+地理: {strong_hits[:2]}"}
        # 强毒品词 + 执法 = 高置信度
        if enforcement_hits:
            return {"pass": True, "score": total_score, "reason": f"强毒品词+执法: {strong_hits[:2]}"}
        # 仅有强毒品词但没有蒙古地理也没有执法上下文 → 降低门槛，但仍通过
        return {"pass": True, "score": total_score, "reason": f"强毒品词: {strong_hits[:2]}"}

    # 情况B：弱药字 + 执法上下文 + 地理锚点 → 通过
    if has_weak_drug and enforcement_hits and geo_hits:
        return {"pass": True, "score": total_score, "reason": f"药字+执法+地理: {enforcement_hits[:2]}"}

    # 情况C：弱药字 + 强执法上下文（2个以上执法词） + 地理 → 通过
    if has_weak_drug and len(enforcement_hits) >= 2 and geo_hits:
        return {"pass": True, "score": total_score, "reason": f"药字+强执法+地理: {enforcement_hits[:2]}"}

    # 情况D：执法 + 地理 + 组合检索词命中（如"扎门乌德 毒品查获"）
    if enforcement_hits and geo_hits and len(enforcement_hits) >= 2:
        return {"pass": True, "score": total_score, "reason": f"执法+地理组合: {enforcement_hits[:2]}"}

    # 情况E：弱药字但无执法也无地理 → 拒绝（纯医药内容）
    if has_weak_drug and not enforcement_hits and not geo_hits:
        return {"pass": False, "score": total_score, "reason": "纯医药词汇无执法/地理上下文"}

    # 情况F：弱药字 + 地理 但无执法 → 大概率是医药监管页面，拒绝
    if has_weak_drug and geo_hits and not enforcement_hits:
        return {"pass": False, "score": total_score, "reason": "医药词汇+地理但无执法动作"}

    # 默认：分数不够拒绝
    if total_score < 3:
        return {"pass": False, "score": total_score, "reason": f"综合评分不足 ({total_score})"}

    return {"pass": True, "score": total_score, "reason": f"综合通过 (得分{total_score})"}


def date_filter(item: dict, max_days: int = 30) -> bool:
    """
    日期过滤：只保留最近 N 天内的新闻。
    无日期的文章视作不合格。
    """
    pub_date_str = item.get("publish_time", "").strip()
    if not pub_date_str:
        return False

    try:
        pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
    except ValueError:
        return False

    cutoff = datetime.now() - timedelta(days=max_days)
    return pub_date >= cutoff


# ============================================================
# 对外接口
# ============================================================

def strict_filter(item: dict) -> bool:
    """AI 智能过滤：分类通过 + 日期在 30 天内"""
    if not date_filter(item, max_days=30):
        return False
    result = ai_classify(item)
    return result["pass"]


def should_keep(item: dict) -> bool:
    return strict_filter(item)


def has_any_keyword_match(item: dict) -> bool:
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
