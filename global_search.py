"""
Global internet search for Mongolia drug-related news.
Uses Google News RSS (free, no API key) with multi-language queries.
Results go through DrugAnalyzer (Stage 1 + DeepSeek AI) for quality filtering.
"""
import requests
import re
import time
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from drug_ai import DrugAnalyzer

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,mn;q=0.7,ru;q=0.6",
}

SEARCH_QUERIES = [
    # === English — broad coverage (18 queries) ===
    ("Mongolia drug trafficking", "en"),
    ("Mongolia narcotics seizure", "en"),
    ("Mongolia drug smuggling", "en"),
    ("Mongolian drug smuggler", "en"),
    ("Mongolia methamphetamine", "en"),
    ("Ulaanbaatar drug arrest", "en"),
    ("Ulaanbaatar drug bust", "en"),
    ("Mongolia cocaine seizure", "en"),
    ("Mongolia heroin trafficking", "en"),
    ("Mongolia cannabis marijuana", "en"),
    ("Mongolia fentanyl", "en"),
    ("Mongolia ecstasy MDMA", "en"),
    ("Mongolia drug cartel", "en"),
    ("Mongolia drug court sentenced", "en"),
    ("Mongolia opium poppy cultivation", "en"),
    ("Mongolia synthetic drug laboratory", "en"),
    ("Mongolia drug overdose death", "en"),
    ("Mongolia precursor chemical seizure", "en"),
    # === Russian — expanded (12 queries) ===
    ("Монголия наркотики", "ru"),
    ("Монголия контрабанда наркотиков", "ru"),
    ("Монголия изъятие наркотиков", "ru"),
    ("Монголия наркокурьер", "ru"),
    ("Монголия наркотрафик", "ru"),
    ("Монголия нарколаборатория", "ru"),
    ("Монголия кокаин героин", "ru"),
    ("Монголия метамфетамин лаборатория", "ru"),
    ("Монголия опий мак", "ru"),
    ("Монголия психотропные вещества", "ru"),
    ("Монголия незаконный оборот наркотиков", "ru"),
    ("Монголия арест наркотики граница", "ru"),
    # === Mongolian — expanded (12 queries) ===
    ("Монгол хар тамхи", "mn"),
    ("Монгол мансууруулах бодис", "mn"),
    ("Монгол хил гааль хар тамхи", "mn"),
    ("Улаанбаатар хар тамхи", "mn"),
    ("Монгол хар тамхи баривчилсан", "mn"),
    ("Монгол мансууруулах эм хууль бус", "mn"),
    ("Монгол психотроп бодис", "mn"),
    ("Монгол хар тамхины наймаачин", "mn"),
    ("Монгол нууц лаборатори хар тамхи", "mn"),
    ("Монгол гааль хар тамхи илрүүлсэн", "mn"),
    ("Монгол хар тамхи хэрэглэсэн баривчилсан", "mn"),
    ("Монгол синтетик мансууруулах бодис", "mn"),
]

MONGOLIA_TERMS = [
    "mongolia", "mongolian",
    "ulaanbaatar", "ulan bator",
    "монголия", "монголии", "монголию", "монгольский",
    "монгол", "монголын", "монголд", "улаанбаатар",
]
MONGOLIA_FALSE = ["mongols bikie", "mongols mc", "mongol empire", "mongol invasion"]
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"

# Title words that obviously suggest drug content — triggers full fetch + AI regardless of Stage 1 score
TITLE_DRUG_SIGNALS = [
    "weed", "cannabis", "marijuana", "hashish", "hash",
    "heroin", "cocaine", "crack", "meth", "ice", "ecstasy", "mdma", "lsd",
    "fentanyl", "opium", "opioid", "amphetamine", "methamphetamine",
    "narcotic", "drug traffick", "drug smuggl", "drug seiz", "drug bust",
    "drug cartel", "drug dealer", "drug arrest", "drug lord",
    "наркотик", "наркотрафик", "наркокурьер", "кокаин", "героин",
    "марихуан", "каннабис", "гашиш", "амфетамин", "метамфетамин",
    "хар тамхи", "мансууруулах",
]

# 6-month cutoff date
SIX_MONTHS_AGO = datetime.now(timezone.utc) - timedelta(days=180)


def _parse_rss_date(date_str):
    """Parse RSS pubDate to datetime. Returns None if unparseable or too old."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def _clean_google_url(url):
    m = re.search(r'url=([^&]+)', url)
    if m:
        return requests.utils.unquote(m.group(1))
    return url


def search_google_news(query, hl="en", count=10):
    """Search Google News RSS and return list of article dicts."""
    results = []
    try:
        rss_url = f"https://news.google.com/rss/search?q={quote(query)}&hl={hl}&gl=US&ceid=US:{hl}"
        resp = requests.get(rss_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results

        root = ET.fromstring(resp.content)
        for i, item in enumerate(root.findall(".//item")):
            if i >= count:
                break
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            source = item.findtext("source", "").strip()
            desc = item.findtext("description", "").strip()

            if not title or not link:
                continue

            real_url = _clean_google_url(link)

            if not source and " - " in title:
                parts = title.rsplit(" - ", 1)
                if len(parts) == 2:
                    source = parts[1].strip()
                    title = parts[0].strip()

            if desc:
                try:
                    desc = BeautifulSoup(desc, "html.parser").get_text(" ", strip=True)
                except Exception:
                    pass

            results.append({
                "title": title,
                "url": real_url,
                "date": pub_date,
                "source": source or urlparse(real_url).netloc,
                "source_label": source or urlparse(real_url).netloc.replace("www.", ""),
                "snippet": desc,
            })
    except Exception:
        pass

    return results


def search_ddg_news(query, count=20):
    """Fallback: DuckDuckGo Lite HTML search."""
    results = []
    try:
        params = {"q": f"{query} news", "s": 0}
        resp = requests.get(DDG_LITE_URL, params=params, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "html.parser")
        for row in soup.select("table.table tr"):
            link_el = row.select_one("a.result-link")
            if not link_el:
                continue
            href = link_el.get("href", "")
            title = link_el.get_text(strip=True)
            snippet_el = row.select_one("td.result-snippet")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            if not title or not href:
                continue

            domain = urlparse(href).netloc.replace("www.", "")
            results.append({
                "title": title,
                "url": href,
                "date": "",
                "source": domain,
                "source_label": domain,
                "snippet": snippet,
            })
    except Exception:
        pass

    return results


def fetch_article_content(url, max_length=2500):
    """Fetch and extract text content from an external article URL. Fast path."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6, allow_redirects=True,
                          verify=True)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text[:300000], "html.parser")

        for tag in soup.select("script, style, nav, footer, header, aside, .sidebar, .comments, .ad"):
            if tag:
                tag.decompose()

        content_parts = []
        for sel in ["article p", ".article-body p", ".story-body p", ".post-content p",
                     ".entry-content p", ".article-content p", "main p", ".news-content p"]:
            for p in soup.select(sel):
                txt = p.get_text(strip=True)
                if len(txt) > 30:
                    content_parts.append(txt)
            if len(content_parts) >= 3:
                break

        if not content_parts:
            body = soup.find("body")
            if body:
                for p in body.find_all("p"):
                    txt = p.get_text(strip=True)
                    if len(txt) > 40:
                        content_parts.append(txt)

        content = "\n".join(content_parts[:10])
        return content[:max_length] if content else soup.get_text(" ", strip=True)[:max_length]
    except Exception:
        return ""


def _is_mongolia_related(title, snippet):
    """Check if article is actually about Mongolia, not just mentioning it in passing."""
    text = (title + " " + snippet).lower()
    # Exclude false Mongolia matches (biker gang "Mongols", etc.)
    for false_term in MONGOLIA_FALSE:
        if false_term in text:
            return False
    return any(term in text for term in MONGOLIA_TERMS)


def global_drug_search(max_per_query=10, total_timeout=50):
    """
    Global drug news search with DeepSeek AI:
    1. Google News RSS → Mongolia relevance filter → 6-month date filter
    2. DeepSeek AI analysis on title+snippet (Stage 1 + Stage 2)
    3. Full content fetch only for borderline cases
    Returns only AI-confirmed drug articles from last 6 months.
    """
    analyzer = DrugAnalyzer()
    all_articles = []
    seen_urls = set()
    start_time = time.time()

    for query, hl in SEARCH_QUERIES:
        if time.time() - start_time > total_timeout:
            break

        articles = search_google_news(query, hl=hl, count=max_per_query)
        # Always supplement with DDG results (different sources, better coverage)
        ddg_results = search_ddg_news(query, count=max_per_query)
        existing_urls = {a["url"] for a in articles}
        articles += [a for a in ddg_results if a["url"] not in existing_urls]

        for art in articles:
            if time.time() - start_time > total_timeout:
                break

            url = art["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Date filter: last 6 months only
            pub_dt = _parse_rss_date(art.get("date", ""))
            if pub_dt and pub_dt < SIX_MONTHS_AGO:
                continue

            # Mongolia relevance check
            if not _is_mongolia_related(art["title"], art.get("snippet", "")):
                continue

            # Run through AI analyzer (Stage 1 + DeepSeek Stage 2)
            text_for_analysis = art["title"] + " " + art.get("snippet", "")
            analysis = analyzer.analyze(art["title"], text_for_analysis, art.get("source"))

            # Fetch full content when snippet is too short, score is borderline,
            # or title contains obvious drug words that keywords might miss
            snippet_len = len(text_for_analysis)
            title_has_drug_signal = any(
                s in art["title"].lower() for s in TITLE_DRUG_SIGNALS
            )
            needs_content = (
                analysis["score"] < 25
                and analysis.get("stage") != "ai"
                and (analysis["score"] >= 3 or snippet_len < 500 or title_has_drug_signal)
            )
            if needs_content:
                content = fetch_article_content(url, max_length=2000)
                if content and len(content) > len(text_for_analysis):
                    analysis = analyzer.analyze(art["title"], content, art.get("source"))

            # Must be AI-confirmed drug article
            if not analysis["is_drug"]:
                continue

            art["content"] = text_for_analysis[:400]
            art["drug_score"] = analysis["score"]
            art["drug_confidence"] = analysis["confidence"]
            art["drug_stage"] = analysis["stage"]
            art["drug_types"] = analysis.get("drug_types", [])
            art["drug_action"] = analysis.get("action", "")
            art["drug_summary"] = analysis.get("summary", "")
            art["matched_keywords"] = analysis.get("keywords", [])
            all_articles.append(art)

        time.sleep(0.3)

    deduped = _deduplicate_by_title(all_articles)
    deduped.sort(key=lambda x: (-x["drug_score"], x.get("date") or ""))
    return deduped, len(deduped)


def _deduplicate_by_title(articles, threshold=0.85):
    """Remove near-duplicate articles by title similarity."""
    if len(articles) <= 1:
        return articles

    kept = []
    for art in articles:
        t1 = art["title"].lower().strip()
        is_dup = False
        for k in kept:
            t2 = k["title"].lower().strip()
            if t1 == t2:
                is_dup = True
                break
            # Simple overlap check for long titles
            if len(t1) > 20 and len(t2) > 20:
                shorter = min(t1, t2, key=len)
                longer = max(t1, t2, key=len)
                if shorter in longer or longer in shorter:
                    is_dup = True
                    break
        if not is_dup:
            kept.append(art)

    return kept
