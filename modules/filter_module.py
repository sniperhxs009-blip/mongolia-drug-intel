"""
AI 智能过滤模块 v5.1
====================
规则引擎 + DeepSeek AI 双重分类：区分毒品执法/走私/查获新闻 vs 普通新闻。

核心逻辑：
  - 所有关键词从 config/keywords.json 动态加载，代码内保留硬编码回退
  - 硬性门禁：必须命中至少 1 个强毒品词或弱药字，否则一律拒绝
  - 排除词覆盖：命中 ≥2 个强毒品词时排除词不拦截（解决藏毒包装含疫苗/药品字样误删）
  - 强毒品词 → 直接通过；弱药字 → 必须伴随执法动作词 + 地理锚点
  - DeepSeek AI 优先，失败后 5 分钟冷却自动重试
  - 30 日内日期过滤
  - 统一日志输出过滤命中详情
"""

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from modules.logger import get_logger

log = get_logger("filter")

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

# ============================================================
# 关键词动态加载（优先从 keywords.json，失败回退硬编码默认值）
# ============================================================

# --- 硬编码默认值（作为 keywords.json 不可用时的回退） ---

_DEFAULT_STRONG_DRUG = [
    "мансууруулах", "мансууруулагч", "наркотик", "нарко",
    "фентанил", "метамфетамин", "героин", "опиум", "опиат",
    "экстази", "кокаин", "аннака", "хар тамхи", "мансуур",
    "баривчилгаа", "хураан авах", "хулгайлах",
    "мансууруулах бодис", "мансууруулах донтолт",
    "мансууруулах эсэргүүцэх", "мансууруулах урьдчилан сэргийлэх",
    "сэргээх төв", "мансууруулах бодисын",
    "мансууруулах бодисын наймаа", "мансууруулах бодис худалдаалах", "хар тамхины наймаа",
    "毒品", "缉毒", "禁毒", "贩毒", "涉毒", "吸毒", "戒毒", "扫毒", "肃毒",
    "芬太尼", "冰毒", "海洛因", "鸦片", "大麻", "摇头丸", "可卡因",
    "合成毒品", "安纳咖", "甲基苯丙胺", "氯胺酮",
    "贩运毒品", "走私毒品", "毒品走私", "跨境贩毒",
    "制毒", "吸毒人员", "毒瘾", "戒毒所", "毒贩",
    "缉毒专项", "禁毒专项", "扫毒行动",
    "narcotics", "narco", "narcotic", "fentanyl", "heroin", "cocaine",
    "methamphetamine", "meth", "opium", "ecstasy", "ketamine",
    "drug trafficking", "drug smuggling", "drug bust", "drug seizure",
    "drug enforcement", "drug raid", "drug arrest", "drug lord", "drug dealer",
    "anti-narcotics", "drug cartel",
    "smuggling of narcotics", "narcotics control",
]

_DEFAULT_ENFORCEMENT = [
    "баривчилгаа", "хураан", "хулгайлах", "мөрдөн байцаалт",
    "барих", "баригдсан", "шүүх", "хорих", "торгууль",
    "цагдаа", "прокурор", "аюулгүй байдлын газар",
    "илрүүлэх", "нууц", "хууль бус", "гэмт хэрэг",
    "зохион байгуулалттай гэмт хэрэг",
    "查获", "缴获", "抓捕", "捣毁", "走私", "贩运",
    "缉私", "刑侦", "专案", "联合办案", "堵截",
    "毒品犯罪", "涉毒案件", "制毒窝点", "贩毒团伙",
    "seizure", "arrest", "smuggling", "trafficking", "bust",
    "crackdown", "investigation", "prosecution", "confiscate",
    "intercept", "police", "criminal", "crime", "prison", "court", "sentence",
    "enforcement", "raid", "operation", "sting",
]

_DEFAULT_EXCLUSION = [
    "гаж нөлөө", "гаж нөлөөний", "гаж урвал",
    "вакцин", "вакцины", "коронавирус", "коронавирусээс", "ковид",
    "дархлаажуулалт", "вакцинжуулалт",
    "бүртгэл", "бүртгүүлэх", "бүртгэгдсэн",
    "чанарын", "чанар", "лаборатори", "шинжилгээ",
    "ёс зүйн", "ёс зүй", "гомдол",
    "сургалт", "семинар", "хурал", "чуулган", "зөвлөгөөн",
    "сургалтын", "танхим",
    "зөвшөөрөл", "тусгай зөвшөөрөл", "лиценз",
    "гэрчилгээ", "сертификат",
    "витамин", "хүнсний нэмэлт", "биологийн идэвхт",
    "сурталчилгаа", "зар",
    "төрийн албан", "төрийн захиргаа", "нийтийн",
            "наадам", "баяр наадмын", "хурдан морь", "бөхийн",
            "ёслол", "мэндчилгээ", "цэнгэлдэх", "уралдаан",
    "副作用", "不良反应", "疫苗", "新冠", "冠状",
    "注册证", "质量检测", "药品注册", "GMP认证",
    "伦理投诉", "道德投诉", "培训", "研讨会",
    "维生素", "保健品", "医疗器械注册",
    "药品招标", "药品采购", "医保", "基药目录",
    "药品说明书", "用药指南", "合理用药",
    "side effect", "adverse reaction", "vaccine", "coronavirus", "covid",
    "registration certificate", "quality control", "quality assurance",
    "vitamin", "supplement", "dietary",
    "ethical complaint", "grievance",
    "training", "workshop", "seminar", "conference",
    "pharmaceutical industry", "drug registration", "medicine registration",
]

_DEFAULT_WEAK_DRUG = [
    "эм", "эмийн", "эмнэлгийн", "эмийг",
    "drug", "drugs", "pharmaceutical", "medicine", "medication",
    "substance", "substances",
    "药品", "药物", "医药", "药剂",
    "controlled substance", "psychotropic",
]

_DEFAULT_SUPPORTING_DRUG = [
    "rehabilitation", "rehab", "addiction", "addict", "detox",
    "treatment center", "treatment programme", "treatment program",
    "drug abuse", "substance abuse", "drug dependence", "drug dependent",
    "needle exchange", "harm reduction", "overdose",
    "сэргээх", "донтолт", "донтсон", "эмчилгээ",
    "戒毒", "康复治疗", "吸毒矫治", "社区戒毒", "自愿戒毒",
    "强制隔离戒毒", "禁毒宣传", "戒毒所", "戒毒治疗",
]

_DEFAULT_GEO_ANCHORS = [
    "монгол", "mongolia", "mongolian", "mongol", "монгол",
    "蒙古", "乌兰巴托", "ulaanbaatar", "ulan bator", "улаанбаатар",
    "蒙古国首都", "蒙俄边境", "扎门乌德", "zamyn-uud", "замын-Үүд",
    "甘其毛都", "ganqimaodao", "gashuunsukhait", "гашуун сухайт",
    "二连浩特", "erenhot", "эРээн", "策克", "ceke", "цэк",
    "满都拉", "mandula", "мандал", "珠恩嘎达布其", "阿尔山",
    "中蒙边境", "中蒙口岸", "陆路口岸", "mongolia-china border",
    "达尔汗", "darkhan", "дархан", "额尔登特", "erdenet", "эрдэнэт",
    "乔巴山", "choibalsan", "чойбалсан",
]


def _load_keywords():
    """从 keywords.json 动态加载关键词列表，失败时回退硬编码默认值"""
    try:
        with open(CONFIG_DIR / "keywords.json", "r", encoding="utf-8") as f:
            kw = json.load(f)
    except Exception:
        log.warning("keywords.json 加载失败，使用硬编码默认值")
        return _DEFAULT_STRONG_DRUG, _DEFAULT_ENFORCEMENT, _DEFAULT_EXCLUSION, _DEFAULT_WEAK_DRUG, _DEFAULT_GEO_ANCHORS, _DEFAULT_SUPPORTING_DRUG

    fk = kw.get("filter_keywords", {})

    # 加载强毒品词
    strong = []
    sd = fk.get("strong_drug_words", {})
    for lang_list in sd.values():
        if isinstance(lang_list, list):
            strong.extend(lang_list)
    if not strong:
        strong = _DEFAULT_STRONG_DRUG

    # 加载执法词
    enforcement = []
    ed = fk.get("enforcement_words", {})
    for lang_list in ed.values():
        if isinstance(lang_list, list):
            enforcement.extend(lang_list)
    if not enforcement:
        enforcement = _DEFAULT_ENFORCEMENT

    # 加载排除词
    exclusion = []
    xd = fk.get("exclusion_words", {})
    for lang_list in xd.values():
        if isinstance(lang_list, list):
            exclusion.extend(lang_list)
    if not exclusion:
        exclusion = _DEFAULT_EXCLUSION

    # 加载弱药字
    weak = []
    wd = fk.get("weak_drug_words", {})
    for lang_list in wd.values():
        if isinstance(lang_list, list):
            weak.extend(lang_list)
    if not weak:
        weak = _DEFAULT_WEAK_DRUG

    # 加载毒品上下文词（康复/治疗/成瘾等）
    supporting = []
    supd = fk.get("supporting_drug_words", {})
    for lang_list in supd.values():
        if isinstance(lang_list, list):
            supporting.extend(lang_list)
    if not supporting:
        supporting = _DEFAULT_SUPPORTING_DRUG

    # 加载地理锚点
    geo = []
    gd = kw.get("geo_anchors", {})
    for group in gd.values():
        if isinstance(group, list):
            geo.extend(group)
    if not geo:
        geo = _DEFAULT_GEO_ANCHORS
    geo = list(set(g.lower() for g in geo if g.strip()))

    log.info("关键词动态加载完成: 强毒品=%d 执法=%d 排除=%d 弱药=%d 上下文=%d 地理=%d",
             len(strong), len(enforcement), len(exclusion), len(weak), len(supporting), len(geo))
    return strong, enforcement, exclusion, weak, geo, supporting


# 模块加载时初始化
STRONG_DRUG_WORDS, ENFORCEMENT_WORDS, EXCLUSION_WORDS, WEAK_DRUG_WORDS, GEO_ANCHORS, SUPPORTING_DRUG_WORDS = _load_keywords()

# 排除词覆盖阈值：命中 ≥ 此数量的强毒品词时不拦截排除词
EXCLUSION_OVERRIDE_THRESHOLD = 2


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
    规则分类器：分析文章并返回分类结果。
    返回 { "pass": bool, "score": int, "reason": str, "hits": dict }
    """
    title = item.get("news_title", "")
    summary = item.get("content_summary", "")
    source = item.get("source_name", "")
    url = item.get("source_url", "")
    # 只用标题+摘要做关键词匹配，来源名不参与（避免"中国国家禁毒委员会办公室"
    # 之类的机构名本身含"禁毒"导致所有该源文章全通过）
    text = f"{title} {summary}"

    if not title.strip() and len(summary.strip()) < 30:
        log.debug("内容过短，拒绝: %s", title[:50])
        return {"pass": False, "score": 0, "reason": "内容过短", "hits": {}}

    # === 第1步：排除词检查（≥2 强毒品词时覆盖排除） ===
    exclusion_hits = [kw for kw in EXCLUSION_WORDS if kw.lower() in text.lower()]

    # 先检查强毒品词命中数，用于覆盖判断
    strong_hits_pre = [kw for kw in STRONG_DRUG_WORDS if kw.lower() in text.lower()]

    if exclusion_hits and len(strong_hits_pre) < EXCLUSION_OVERRIDE_THRESHOLD:
        log.info("FILTER-REJECT | 排除词: %s | %s", exclusion_hits[:3], url[:80])
        return {
            "pass": False, "score": -10,
            "reason": f"命中排除词: {exclusion_hits[:3]}",
            "hits": {"exclusion": exclusion_hits[:5]},
        }

    # === 第2步：强毒品词评分 ===
    strong_hits = strong_hits_pre  # 复用上面已计算的
    strong_score = len(strong_hits) * 3

    # === 第3步：执法上下文评分 ===
    enforcement_hits = [kw for kw in ENFORCEMENT_WORDS if kw.lower() in text.lower()]
    enforcement_score = len(enforcement_hits) * 2

    # === 第3.5步：毒品上下文词评分（康复/治疗/成瘾等） ===
    supporting_hits = [kw for kw in SUPPORTING_DRUG_WORDS if kw.lower() in text.lower()]
    supporting_score = len(supporting_hits) * 2
    has_drug_context = bool(supporting_hits)

    # === 第4步：弱药字检查 ===
    weak_hits_list = [kw for kw in WEAK_DRUG_WORDS if kw.lower() in text.lower()]
    has_weak_drug = len(weak_hits_list) > 0

    # === 第5步：地理锚点评分 ===
    geo_hits = [kw for kw in GEO_ANCHORS if kw.lower() in text.lower()]
    geo_score = len(geo_hits) * 1

    total_score = strong_score + enforcement_score + supporting_score + geo_score

    # 组装命中详情
    hit_detail = {
        "strong": strong_hits[:5],
        "enforcement": enforcement_hits[:5],
        "supporting": supporting_hits[:3],
        "weak": weak_hits_list[:3],
        "geo": geo_hits[:5],
        "exclusion_override": len(exclusion_hits) > 0 and len(strong_hits) >= EXCLUSION_OVERRIDE_THRESHOLD,
    }

    # === 第6步：综合判定 ===
    # 硬性门禁1：必须命中至少 1 个强毒品词或 1 个弱药字
    has_any_drug_word = bool(strong_hits) or has_weak_drug
    if not has_any_drug_word:
        log.debug("FILTER-REJECT | 无毒品词 | %s", url[:80])
        return {"pass": False, "score": total_score, "reason": "无任何毒品/药物相关关键词", "hits": hit_detail}

    # 硬性门禁2：必须命中至少 1 个蒙古地理锚点（所有情况都需要）
    if not geo_hits:
        log.debug("FILTER-REJECT | 无蒙古地理锚点 | %s", url[:80])
        return {"pass": False, "score": total_score, "reason": "无蒙古地理锚点", "hits": hit_detail}

    # 情况A：有强毒品词 + 地理 → 通过
    if strong_hits:
        log.info("FILTER-PASS | 强毒品+地理 | 词=%s 得分=%d | %s", strong_hits[:2], total_score, url[:80])
        return {"pass": True, "score": total_score, "reason": f"强毒品词+地理: {strong_hits[:2]}", "hits": hit_detail}

    # 情况B：弱药字 + 执法上下文 + 地理锚点 → 通过
    if has_weak_drug and enforcement_hits:
        log.info("FILTER-PASS | 药+执法+地理 | 执法=%s 得分=%d | %s", enforcement_hits[:2], total_score, url[:80])
        return {"pass": True, "score": total_score, "reason": f"药字+执法+地理: {enforcement_hits[:2]}", "hits": hit_detail}

    # 情况C：弱药字 + 毒品上下文词（康复/治疗/成瘾）+ 地理 → 通过
    if has_weak_drug and has_drug_context:
        log.info("FILTER-PASS | 药+上下文+地理 | 上下文=%s 得分=%d | %s", supporting_hits[:2], total_score, url[:80])
        return {"pass": True, "score": total_score, "reason": f"药字+毒品上下文+地理: {supporting_hits[:2]}", "hits": hit_detail}

    # 情况D：弱药字 + 地理 但无执法也无上下文 → 医药监管页面，拒绝
    if has_weak_drug and not enforcement_hits and not has_drug_context:
        log.debug("FILTER-REJECT | 医药+地理无执法 | %s", url[:80])
        return {"pass": False, "score": total_score, "reason": "医药词汇+地理但无毒品上下文", "hits": hit_detail}

    log.debug("FILTER-REJECT | 评分不足(%d) | %s", total_score, url[:80])
    return {"pass": False, "score": total_score, "reason": f"评分不足 ({total_score})", "hits": hit_detail}


def _parse_flexible_date(date_str: str) -> Optional[datetime]:
    """灵活日期解析，支持 RSS/Atom/ISO/中文/蒙文等多种格式"""
    from email.utils import parsedate_to_datetime as email_parse
    date_str = date_str.strip()
    if not date_str:
        return None

    # 1. YYYY-MM-DD
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        pass

    # 2. ISO 8601: 2026-07-14T10:30:00+08:00
    try:
        return datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass

    # 3. RFC 2822: Mon, 14 Jul 2026 10:30:00 +0800 (RSS pubDate)
    try:
        dt = email_parse(date_str)
        return dt.replace(tzinfo=None)  # 转为无时区，与 datetime.now() 对齐
    except Exception:
        pass

    # 4. 中文/蒙文: 2026年7月14日 / 2026.07.14 / 14/07/2026
    for pat, fmt in [
        (r'(\d{4})\s*[年./]\s*(\d{1,2})\s*[月./]\s*(\d{1,2})', 'ymd'),
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'dmy'),
        (r'(\d{4})\.(\d{1,2})\.(\d{1,2})', 'ymd'),
    ]:
        m = re.search(pat, date_str)
        if m:
            try:
                if fmt == 'ymd':
                    return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                continue

    return None


def date_filter(item: dict, max_days: int = 30) -> bool:
    """日期过滤：只保留最近 N 天内的新闻。支持多种日期格式。"""
    pub_date_str = item.get("publish_time", "").strip()
    pub_date = _parse_flexible_date(pub_date_str)
    if not pub_date:
        return False
    cutoff = datetime.now() - timedelta(days=max_days)
    return pub_date >= cutoff


# ============================================================
# AI 优先过滤（DeepSeek 为主，规则引擎为 fallback）
# ============================================================

def _check_with_ai(item: dict) -> dict:
    """使用 DeepSeek AI 进行智能分类，连续失败 3 次后进入 5 分钟冷却，到期自动重试"""
    import modules.ai_classifier as aic

    try:
        if not aic._ai_available:
            if time.time() - aic._ai_fail_time > aic._AI_COOLDOWN_SECONDS:
                log.info("DeepSeek API 冷却期结束，重置计数器并重新尝试")
                aic._ai_available = True
                aic._ai_fail_count = 0
            else:
                return ai_classify(item)

        result = aic.classify_article(item)
        if result.get("ai_model") == "none":
            aic._ai_fail_count += 1
            log.warning("DeepSeek API 调用失败 (%d/%d)", aic._ai_fail_count, aic._AI_MAX_CONSECUTIVE_FAILS)
            if aic._ai_fail_count >= aic._AI_MAX_CONSECUTIVE_FAILS:
                aic._ai_available = False
                aic._ai_fail_time = time.time()
                log.warning("DeepSeek API 连续失败 %d 次，进入 %ds 冷却期", aic._ai_fail_count, aic._AI_COOLDOWN_SECONDS)
            return ai_classify(item)
        # 成功调用，重置失败计数
        aic._ai_fail_count = 0
        return {
            "pass": result.get("is_relevant", False),
            "score": int(result.get("confidence", 0) * 10),
            "reason": f"DeepSeek: {result.get('reason', '')}",
            "hits": {},
        }
    except Exception as e:
        log.error("DeepSeek 异常: %s", e)
        aic._ai_fail_count += 1
        if aic._ai_fail_count >= aic._AI_MAX_CONSECUTIVE_FAILS:
            aic._ai_available = False
            aic._ai_fail_time = time.time()
        return ai_classify(item)


def strict_filter(item: dict) -> bool:
    """AI 智能过滤：日期 90 天内 + DeepSeek AI 分类"""
    if not date_filter(item, max_days=90):
        return False
    result = _check_with_ai(item)
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
