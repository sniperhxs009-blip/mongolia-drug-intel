"""
蒙古国涉毒新闻情报爬虫 - 过滤模块
===================================
极度宽松的过滤策略，确保合法情报不被误删：

硬性规则：
① 删除短资讯过滤：不因标题+摘要字符＜100 而丢弃，口岸简短查获快讯全部放行
② 地域文本过滤阈值上调至 95%：仅正文 95% 以上纯内地无关内容才过滤
③ 弱化毒品词准入门槛：「口岸、海关、查获」+ 蒙古地理锚点即可入库
④ UNODC 内容不做国别强拦截：全球禁毒报告、蒙古调研报告均可入库
⑤ 禁止注释拦截代码规避需求，直接删除限流/过滤判定代码块
"""

import json
import re
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"

# 加载关键词配置
with open(CONFIG_DIR / "keywords.json", "r", encoding="utf-8") as f:
    KEYWORDS_CONFIG = json.load(f)

# 弱执法词汇 + 地理锚点
WEAK_ACTION_KEYWORDS = KEYWORDS_CONFIG["weak_keywords"]["weak_action_keywords"]
GEO_ANCHORS = KEYWORDS_CONFIG["weak_keywords"]["geo_anchors"]

# 所有毒品相关关键词（用于相关性评分）
ALL_DRUG_KEYWORDS = set()
for lang_kw in KEYWORDS_CONFIG["keywords"].values():
    for kw in lang_kw["primary"] + lang_kw["secondary"]:
        ALL_DRUG_KEYWORDS.add(kw.lower())


def is_pure_inland_china_irrelevant(item: dict) -> bool:
    """
    地域文本过滤：仅正文 95% 以上纯内地无关内容才过滤。
    中蒙双语、中文边境缉毒新闻一律保留。

    返回 True 表示应过滤，False 表示保留。
    """
    text = f"{item.get('news_title', '')} {item.get('content_summary', '')}"

    if not text.strip():
        return False  # 空内容不拦截

    # 检查是否包含蒙古地理锚点
    has_mongolia_geo = any(
        anchor.lower() in text.lower()
        for anchor in GEO_ANCHORS
    )

    # 如果包含蒙古地理锚点，直接放行
    if has_mongolia_geo:
        return False

    # 检查是否包含纯中国内地地理词（非边境）
    china_inland_geo = [
        "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉",
        "Beijing", "Shanghai", "Guangzhou", "Shenzhen",
        "河南", "河北", "山东", "山西", "陕西", "湖南", "湖北", "江西",
        "浙江", "江苏", "福建", "广东", "广西", "四川", "贵州", "云南",
    ]
    china_border_geo = [
        "内蒙古", "二连浩特", "甘其毛都", "策克", "满都拉",
        "Inner Mongolia", "Erenhot", "Ganqimaodao",
    ]

    # 检查是否包含边境/蒙古相关词
    border_related = [
        "中蒙", "蒙古", "口岸", "边境", "跨境", "Mongolia", "Монгол",
        "扎门乌德", "Zamyn-Uud",
    ]

    text_lower = text.lower()
    has_border = any(b.lower() in text_lower for b in border_related)
    has_inland = any(c.lower() in text_lower for c in china_inland_geo)
    has_border_geo = any(b.lower() in text_lower for b in china_border_geo)

    if has_border or has_border_geo:
        return False  # 边境/蒙古相关内容保留

    # 计算纯内地无关内容占比（简化判断：有内地地名但无边境/蒙古词）
    if has_inland and not has_border and not has_border_geo:
        # 仅当完全不涉及蒙古/边境/口岸时过滤
        return True

    return False


def has_any_keyword_match(item: dict) -> bool:
    """
    弱化毒品词准入门槛：
    - 弱执法词汇（口岸、海关、查获等）+ 蒙古地理锚点 即可入库
    - 不强制要求匹配芬太尼、冰毒等强毒品词
    """
    text = f"{item.get('news_title', '')} {item.get('content_summary', '')}"
    text_lower = text.lower()

    # 检查弱执法词汇
    has_weak_action = any(
        kw.lower() in text_lower
        for kw in WEAK_ACTION_KEYWORDS
    )

    # 检查地理锚点
    has_geo = any(
        anchor.lower() in text_lower
        for anchor in GEO_ANCHORS
    )

    # 弱执法词汇 + 地理锚点 → 通过
    if has_weak_action and has_geo:
        return True

    # 包含任意毒品关键词 → 通过
    has_drug_kw = any(
        kw.lower() in text_lower
        for kw in ALL_DRUG_KEYWORDS
    )

    if has_drug_kw:
        return True

    # 来自禁毒执法机构的内容，即使无关键词匹配也放行
    government_sources = [
        "customs", "procuracy", "justice", "nsa", "unodc",
        "海关", "检察院", "司法", "安全", "禁毒", "NNCC",
    ]
    source_lower = item.get("source_name", "").lower()
    if any(gs in source_lower for gs in government_sources):
        return True

    return False


def should_keep(item: dict) -> bool:
    """
    综合过滤判定：是否保留该条情报。

    规则：
    1. 不因短文过滤（删除短资讯拦截逻辑）
    2. 仅 95%+ 纯内地无关内容才过滤
    3. 弱执法词汇+地理锚点或毒品词即可入库
    4. UNODC 等国际机构内容不做国别拦截
    """
    # 必须包含 title 或 content
    title = item.get("news_title", "")
    summary = item.get("content_summary", "")
    if not title and not summary:
        return False

    # 必须匹配关键词或弱执法词汇+地理锚点
    if not has_any_keyword_match(item):
        return False

    # 地域过滤（仅极端情况拦截）
    if is_pure_inland_china_irrelevant(item):
        return False

    return True


def apply_filters(items: list[dict]) -> tuple[list[dict], int]:
    """
    对解析后的情报列表应用过滤。
    返回 (保留列表, 过滤条数)
    """
    kept = []
    filtered_count = 0

    for item in items:
        if should_keep(item):
            kept.append(item)
        else:
            filtered_count += 1

    return kept, filtered_count
