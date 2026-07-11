"""
蒙古国涉毒新闻情报爬虫 - HTML 解析模块
========================================
从原始 HTML 中提取新闻标题、发布时间、正文摘要等结构化字段。

DOM 清洗规则（精简原则）：
- 仅删除 script、style、noscript 三类无用标签
- 保留 header、nav、aside、footer（蒙古媒体侧边栏/页脚缉毒快讯不丢失）
- 禁止过度清洗页面
"""

import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup, Tag

# 日期匹配模式（支持多种格式）
DATE_PATTERNS = [
    # ISO 格式: 2024-12-01, 2024-12-01T10:30:00
    (re.compile(r"(\d{4}-\d{2}-\d{2})"), "%Y-%m-%d"),
    # 蒙古/中文日期: 2024年12月01日
    (re.compile(r"(\d{4})\s*[年./]\s*(\d{1,2})\s*[月./]\s*(\d{1,2})\s*[日]?"), None),
    # 英文日期: Dec 01, 2024 / December 01, 2024 / 01 Dec 2024
    (re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})"), None),
    # 点分隔: 2024.12.01
    (re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})"), None),
    # 斜杠: 12/01/2024
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), None),
]

# 蒙古语月份映射
MN_MONTHS = {
    "1-р": 1, "2-р": 2, "3-р": 3, "4-р": 4, "5-р": 5, "6-р": 6,
    "7-р": 7, "8-р": 8, "9-р": 9, "10-р": 10, "11-р": 11, "12-р": 12,
}

# 英文月份缩写映射
EN_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# time 标签选择器
TIME_SELECTORS = [
    "time", "[datetime]",
    ".date", ".time", ".publish-date", ".post-date", ".entry-date",
    ".article-date", ".news-date", ".created-date",
    "meta[property='article:published_time']",
    "meta[name='date']",
    "meta[name='pubdate']",
    "[class*='date']", "[class*='time']",
]

# 正文容器选择器
CONTENT_SELECTORS = [
    "article", ".article", ".post", ".news", ".content",
    ".entry-content", ".post-content", ".article-content",
    ".news-content", ".story-content", ".body-content",
    "main", "#content", "#main", ".main-content",
    "[role='main']",
]


def clean_html(html: str) -> BeautifulSoup:
    """
    DOM 清洗：仅删除 script、style、noscript 三类标签。
    保留 header、nav、aside、footer 及其内部缉毒快讯。
    """
    soup = BeautifulSoup(html, "lxml")

    # 仅删除三类无用标签
    for tag_name in ["script", "style", "noscript"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    return soup


def extract_title(soup: BeautifulSoup) -> str:
    """提取新闻标题，优先级：h1 > og:title > title 标签"""
    # 优先取 h1
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)[:300]

    # og:title meta
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content", "").strip():
        return og_title["content"].strip()[:300]

    # title 标签
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        t = title_tag.get_text(strip=True)
        # 去除常见站点后缀
        for sep in [" | ", " - ", " :: ", "｜", " — "]:
            if sep in t:
                t = t.split(sep)[0]
        return t[:300]

    return ""


def extract_publish_time(soup: BeautifulSoup, html: str) -> Optional[str]:
    """
    提取发布日期，返回 YYYY-MM-DD 格式。
    优先级：meta 标签 > time 标签 > 文本正则匹配
    """

    def parse_date_str(d: str) -> Optional[str]:
        """将各种日期字符串统一为 YYYY-MM-DD"""
        d = d.strip()
        if not d:
            return None

        # 尝试 ISO 格式
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # 尝试中文/蒙古日期格式
        m = re.match(r"(\d{4})\s*[年./]\s*(\d{1,2})\s*[月./]\s*(\d{1,2})", d)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        # 尝试点分隔
        m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", d)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        # 尝试英文日期
        m = re.match(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]+(\d{4})", d, re.IGNORECASE)
        if m:
            month = EN_MONTHS.get(m.group(2).lower()[:3], 1)
            return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"

        return None

    # 1. meta 标签
    for meta_name in ["article:published_time", "date", "pubdate", "publish-date", "dc.date"]:
        meta = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
        if meta and meta.get("content"):
            parsed = parse_date_str(meta["content"])
            if parsed:
                return parsed

    # 2. time 标签
    for selector in TIME_SELECTORS:
        if selector.startswith(".") or selector.startswith("[") or selector.startswith("meta"):
            # CSS 选择器，用 select
            try:
                elements = soup.select(selector)
            except Exception:
                continue
        else:
            elements = soup.find_all(selector.replace("[", "").replace("]", "").replace("meta", "").strip() or "time")

        for el in elements:
            if isinstance(el, Tag):
                dt = el.get("datetime") or el.get_text(strip=True)
                if dt:
                    parsed = parse_date_str(dt)
                    if parsed:
                        return parsed

    # 3. 正文正则匹配
    text = soup.get_text()
    for pattern, fmt in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                if fmt:
                    dt = datetime.strptime(m.group(1), fmt)
                    return dt.strftime("%Y-%m-%d")
                elif len(m.groups()) == 3:
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                elif len(m.groups()) == 2:
                    # 少量情况
                    pass
            except ValueError:
                continue

    return None


def extract_content_summary(soup: BeautifulSoup, min_chars: int = 80) -> str:
    """
    提取正文摘要，不少于 80 字。
    优先从正文容器提取，回退到全文纯文本。
    """
    # 尝试从正文容器提取
    for selector in CONTENT_SELECTORS:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator=" ", strip=True)
            if len(text) >= min_chars:
                return text[:500]

    # 回退：从 body 提取纯文本，排除明显的导航文本
    body = soup.find("body")
    if body:
        # 尝试移除明显的导航/页脚噪音后取正文
        text = body.get_text(separator=" ", strip=True)
        # 清理多余空白
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500]

    # 最后回退
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500]


def detect_language(text: str, site_lang: str) -> str:
    """
    检测语种标签。
    返回: mn(蒙语) / zh(中文) / en(英文)
    """
    # 蒙古语西里尔字母范围
    cyrillic_count = len(re.findall(r"[Ѐ-ӿ]", text))
    # 中文字符
    chinese_count = len(re.findall(r"[一-鿿]", text))
    # 英文字符（拉丁字母为主）
    latin_count = len(re.findall(r"[a-zA-Z]", text))

    total = cyrillic_count + chinese_count + latin_count or 1

    if cyrillic_count / total > 0.3:
        return "mn"
    elif chinese_count / total > 0.3:
        return "zh"
    elif latin_count / total > 0.5:
        return "en"

    # 默认使用站点配置的语种
    return site_lang


def find_keyword_hit(text: str, keywords: list[str]) -> str:
    """
    在文本中查找命中的关键词。
    返回第一个匹配到的关键词，未匹配返回空字符串。
    """
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return kw
    return ""


def parse_html_result(crawl_result: dict) -> Optional[dict]:
    """
    解析单个抓取结果，提取结构化字段。
    返回包含所有情报字段的字典，或 None（解析失败时）。
    """
    html = crawl_result.get("html", "")
    if not html or len(html) < 100:
        return None

    soup = clean_html(html)

    # 提取各字段
    title = extract_title(soup)
    publish_time = extract_publish_time(soup, html)
    source_url = crawl_result.get("fetch_url", "")
    source_name = crawl_result.get("site_name", "")
    content_summary = extract_content_summary(soup)
    site_lang = crawl_result.get("language", "mn")

    # 语种检测
    full_text = f"{title} {content_summary}"
    language = detect_language(full_text, site_lang)

    # 关键词命中检测
    keyword = crawl_result.get("keyword", "")

    # 跳过明显无效的解析结果
    if not title and len(content_summary) < 20:
        return None

    return {
        "news_title": title or "(无标题)",
        "publish_time": publish_time or "",
        "source_url": source_url,
        "source_name": source_name,
        "content_summary": content_summary,
        "language": language,
        "keyword_hit": keyword,
        "crawl_time": crawl_result.get("fetch_time", datetime.now().isoformat()),
        "site_category": crawl_result.get("site_category_name", ""),
    }


def parse_all_results(crawl_results: list[dict]) -> list[dict]:
    """批量解析所有抓取结果，返回结构化情报列表"""
    parsed = []
    for result in crawl_results:
        try:
            item = parse_html_result(result)
            if item:
                parsed.append(item)
        except Exception:
            # 单条解析失败不影响整体
            continue
    return parsed
