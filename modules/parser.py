"""
HTML 解析模块 v4.0 - 从文章详情页提取结构化情报
删除 script/style/noscript/header/nav/footer/aside，避免导航栏文本污染分类
"""

import re
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup, Tag

# 日期匹配
DATE_REGEXES = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "iso"),
    (re.compile(r"(\d{4})\s*[年./]\s*(\d{1,2})\s*[月./]\s*(\d{1,2})\s*[日]?"), "cn"),
    (re.compile(r"(\d{1,2})\s+(1[0-2]|0?[1-9])\s+[р]\s+(\d{4})"), "mn"),  # 蒙古日期
    (re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})"), "dot"),
    (re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})"), "slash"),
]

CONTENT_SELECTORS = [
    "article", ".article-content", ".post-content", ".entry-content",
    ".news-content", ".story-content", ".single-content", ".body-content",
    ".content-body", ".article-body", ".post-body", "main",
    "#content", ".content", "[role='main']",
]


def clean_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "lxml")
    for tag_name in ["script", "style", "noscript", "header", "nav", "footer", "aside"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()
    return soup


def extract_article_title(soup: BeautifulSoup) -> str:
    """提取文章标题"""
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if len(text) > 3:
            return text[:300]
    og = soup.find("meta", property="og:title")
    if og and og.get("content", "").strip():
        return og["content"].strip()[:300]
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        for sep in [" | ", " - ", " :: ", "｜"]:
            if sep in t:
                t = t.split(sep)[0]
        return t[:300]
    return ""


def extract_publish_date(soup: BeautifulSoup) -> str:
    """提取发布日期 YYYY-MM-DD"""
    # Meta 标签
    for meta_name in ["article:published_time", "date", "pubdate", "publish-date", "dc.date", "citation_date"]:
        meta = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
        if meta and meta.get("content"):
            d = _parse_date_str(meta["content"])
            if d:
                return d

    # time 标签
    for time_el in soup.find_all("time"):
        dt = time_el.get("datetime") or time_el.get_text(strip=True)
        if dt:
            d = _parse_date_str(dt)
            if d:
                return d

    # class 选择器
    for cls in [".date", ".time", ".publish-date", ".post-date", ".entry-date", ".article-date",
                "[class*='date']", "[class*='time']"]:
        try:
            for el in soup.select(cls):
                text = el.get_text(strip=True)
                if text:
                    d = _parse_date_str(text)
                    if d:
                        return d
        except Exception:
            continue

    # 全文正则
    text = soup.get_text()
    for regex, fmt in DATE_REGEXES:
        m = regex.search(text)
        if m:
            try:
                if fmt == "iso":
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                elif fmt == "cn":
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                elif fmt == "mn":
                    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
                elif fmt == "dot":
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                elif fmt == "slash":
                    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            except ValueError:
                continue

    return ""


def _parse_date_str(d: str) -> Optional[str]:
    """尝试解析各种日期字符串"""
    d = d.strip()
    if not d:
        return None
    for regex, fmt in DATE_REGEXES:
        m = regex.search(d)
        if m:
            try:
                if fmt == "iso":
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                elif fmt == "cn":
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                elif fmt == "dot":
                    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                elif fmt == "slash":
                    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            except ValueError:
                continue
    return None


def extract_content_summary(soup: BeautifulSoup, min_chars: int = 80) -> str:
    """从文章详情页提取正文摘要"""
    for selector in CONTENT_SELECTORS:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            if len(text) >= min_chars:
                return text[:500]

    body = soup.find("body")
    if body:
        text = body.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:500]

    return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))[:500]


def detect_language(text: str, site_lang: str) -> str:
    cyrillic = len(re.findall(r"[Ѐ-ӿ]", text))
    chinese = len(re.findall(r"[一-鿿]", text))
    latin = len(re.findall(r"[a-zA-Z]", text))
    total = max(cyrillic + chinese + latin, 1)
    if cyrillic / total > 0.3:
        return "mn"
    elif chinese / total > 0.3:
        return "zh"
    elif latin / total > 0.5:
        return "en"
    return site_lang


def detect_keyword_hit(text: str, keywords: list[str]) -> str:
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return kw
    return ""


def parse_article_html(html: str, article_url: str, site: dict) -> Optional[dict]:
    """
    解析文章详情页 HTML，提取所有情报字段。
    source_url 使用文章实际 URL。
    """
    if not html or len(html) < 200:
        return None

    soup = clean_html(html)
    title = extract_article_title(soup)
    summary = extract_content_summary(soup)
    full_text = f"{title} {summary}"
    pub_date = extract_publish_date(soup)
    lang = detect_language(full_text, site.get("language", "mn"))

    if not title and len(summary) < 30:
        return None

    return {
        "news_title": title or "(无标题)",
        "publish_time": pub_date,
        "source_url": article_url,
        "source_name": site.get("name", ""),
        "content_summary": summary,
        "language": lang,
        "keyword_hit": "",
        "crawl_time": datetime.now().isoformat(),
        "site_category": site.get("category_name", ""),
        "cn_title": "",
        "cn_summary": "",
    }


# 兼容旧接口
def parse_all_results(crawl_results: list[dict]) -> list[dict]:
    parsed = []
    for r in crawl_results:
        site = {"name": r.get("site_name", ""), "language": r.get("language", "mn"), "category_name": r.get("site_category_name", "")}
        item = parse_article_html(r.get("html", ""), r.get("fetch_url", ""), site)
        if item:
            parsed.append(item)
    return parsed


# 兼容旧接口
def parse_html_result(crawl_result: dict) -> Optional[dict]:
    site = {"name": crawl_result.get("site_name", ""), "language": crawl_result.get("language", "mn"), "category_name": crawl_result.get("site_category_name", "")}
    return parse_article_html(crawl_result.get("html", ""), crawl_result.get("fetch_url", ""), site)
