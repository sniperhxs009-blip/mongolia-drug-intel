"""
AI-powered drug intelligence analysis report generator.
Uses DeepSeek API to produce comprehensive, professional reports.
"""
import os
import json
import requests
from datetime import datetime

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"


def generate_intelligence_report(drug_articles, ai_ready=True):
    """
    Generate a comprehensive intelligence analysis report from drug-related articles.

    Args:
        drug_articles: list of dicts with keys: title, url, source_label, date, content,
                       drug_score, drug_confidence, drug_types, drug_action, drug_summary, matched_keywords

    Returns:
        dict with title, content (HTML), article_count, date_start, date_end
    """
    if not DEEPSEEK_API_KEY:
        return _fallback_report(drug_articles)

    if not drug_articles:
        return {
            "title": "蒙古毒品情报综合分析研判报告",
            "content": "<p>当前数据库中没有找到涉毒文章，无法生成报告。</p>",
            "article_count": 0,
            "date_start": "",
            "date_end": "",
        }

    # Summarize articles for the prompt (keep it within token limits)
    summaries = []
    for i, a in enumerate(drug_articles[:80]):  # Cap at 80 articles to stay within context
        date_str = a.get("date", "未知")
        source = a.get("source_label", a.get("source", "未知"))
        title = a.get("title", "无标题")[:120]
        url = a.get("url", "")
        snippet = (a.get("content", "") or "")[:300]
        score = a.get("drug_score", 0)
        drug_types = ", ".join(a.get("drug_types", [])[:5]) if a.get("drug_types") else "未分类"
        keywords = ", ".join(a.get("matched_keywords", [])[:5]) if a.get("matched_keywords") else ""
        action = a.get("drug_action", "")

        summaries.append(
            f"[{i+1}] 日期:{date_str} | 来源:{source} | 类型:{drug_types} | 评分:{score}\n"
            f"标题: {title}\n"
            f"URL: {url}\n"
            f"关键词: {keywords}\n"
            f"行为: {action}\n"
            f"摘要: {snippet}\n"
        )

    article_text = "\n".join(summaries)

    dates = [a.get("date", "") for a in drug_articles if a.get("date")]
    dates.sort()
    date_start = dates[0] if dates else ""
    date_end = dates[-1] if dates else ""

    prompt = f"""你是一位资深的情报分析专家，专门负责蒙古国及周边地区的毒品情报分析工作。

请根据以下 {len(drug_articles)} 条涉毒新闻情报数据，撰写一份详尽、专业、逻辑严谨的综合情报研判分析报告。

报告必须以中文撰写，使用以下结构（Markdown 格式）：

# 蒙古国毒品情报综合分析研判报告

> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
> 数据范围: {date_start} 至 {date_end}
> 分析文章数: {len(drug_articles)} 篇

## 一、总体概述
- 对本报告期内的毒品形势进行总体描述（2-3段）
- 概括毒品活动的总体趋势、主要特点

## 二、关键发现
- 列举 5-8 条最重要的发现
- 每条用编号列出，包含具体数据和来源

## 三、来源分布分析
- 分析不同新闻来源的报道数量和侧重点
- 官方来源（警察总局、法医总局、检察总署等）vs 媒体来源的对比

## 四、时间线分析
- 按时间顺序梳理重要事件
- 标注事件发生的时间节点
- 分析事件之间的关联性

## 五、毒品类型分析
- 涉及哪些毒品类型（如冰毒、大麻、海洛因等）
- 各类型出现的频次和趋势
- 是否有新型毒品出现

## 六、重点事件详情
- 选取 5-10 个最重要的具体事件
- 每个事件包含：来源网站名称、网址链接、发布时间、事件摘要、情报价值评估

## 七、趋势研判
- 基于现有数据预测未来发展趋势
- 分析毒品走私路线、手法变化
- 评估执法打击效果

## 八、建议措施
- 针对发现的问题提出具体可行的建议
- 包括执法层面、政策层面、国际合作层面

## 九、信息来源清单
- 列出所有引用的文章，格式：序号. [来源名称] 标题 (发布日期) - URL

要求：
1. 报告必须详细、专业，不少于 3000 字
2. 每个分析结论必须有数据支撑
3. 引用文章时必须标注来源网站名称、URL链接和发布时间
4. 逻辑分析必须严谨合理，避免主观臆断
5. 使用情报分析专业术语
6. 第六条"重点事件详情"中每个事件必须包含完整的来源信息和URL链接

---
情报数据:
{article_text}
"""

    try:
        resp = requests.post(
            f"{DEEPSEEK_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 8192,
            },
            timeout=180,
        )

        if resp.status_code == 200:
            data = resp.json()
            report_md = data["choices"][0]["message"]["content"]
            report_html = _md_to_html(report_md)
            return {
                "title": "蒙古国毒品情报综合分析研判报告",
                "content": report_html,
                "article_count": len(drug_articles),
                "date_start": date_start,
                "date_end": date_end,
            }
        else:
            return _fallback_report(drug_articles)
    except Exception as e:
        print(f"[报告生成] API 调用失败: {e}")
        return _fallback_report(drug_articles)


def _md_to_html(md_text):
    """Simple Markdown to HTML converter for report display."""
    import re

    lines = md_text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        # Headers
        if stripped.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h1 class="report-h1">{stripped[2:]}</h1>')
        elif stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h2 class="report-h2">{stripped[3:]}</h2>')
        elif stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<h3 class="report-h3">{stripped[4:]}</h3>')
        elif stripped.startswith("> "):
            html_parts.append(f'<blockquote class="report-quote">{stripped[2:]}</blockquote>')
        elif re.match(r'^\d+\.\s', stripped):
            if not in_list:
                html_parts.append('<ol class="report-ol">')
                in_list = True
            m_ol = re.match(r'^\d+\.\s', stripped)
            html_parts.append(f"<li>{stripped[m_ol.end():]}</li>")
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append('<ul class="report-ul">')
                in_list = True
            html_parts.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Auto-link URLs
            text = re.sub(r'(https?://[^\s\)\]]+)', r'<a href="\1" target="_blank">\1</a>', stripped)
            # Bold
            text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            html_parts.append(f"<p>{text}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _fallback_report(drug_articles):
    """Generate a basic report without AI."""
    if not drug_articles:
        return {
            "title": "蒙古毒品情报综合分析研判报告",
            "content": "<p>当前数据库中没有找到涉毒文章，无法生成报告。</p>",
            "article_count": 0,
            "date_start": "",
            "date_end": "",
        }

    dates = [a.get("date", "") for a in drug_articles if a.get("date")]
    dates.sort()

    sources = {}
    drug_types = {}
    for a in drug_articles:
        src = a.get("source_label", a.get("source", "未知"))
        sources[src] = sources.get(src, 0) + 1
        for t in a.get("drug_types", []):
            drug_types[t] = drug_types.get(t, 0) + 1

    html = '<div class="report-fallback">'
    html += '<h1>蒙古国毒品情报综合分析研判报告</h1>'
    html += f'<blockquote>生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")} | 分析文章数: {len(drug_articles)} 篇</blockquote>'

    html += '<h2>总体概述</h2>'
    html += f'<p>本报告期内共收录涉毒相关文章 {len(drug_articles)} 篇，来自 {len(sources)} 个不同来源。</p>'

    html += '<h2>来源分布</h2><ul>'
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        html += f'<li><strong>{src}</strong>: {cnt} 篇</li>'
    html += '</ul>'

    if drug_types:
        html += '<h2>毒品类型分布</h2><ul>'
        for t, cnt in sorted(drug_types.items(), key=lambda x: -x[1]):
            html += f'<li><strong>{t}</strong>: {cnt} 次</li>'
        html += '</ul>'

    html += '<h2>文章列表</h2><ol>'
    for a in drug_articles[:50]:
        title = a.get("title", "无标题")
        url = a.get("url", "")
        date = a.get("date", "")
        source = a.get("source_label", a.get("source", ""))
        score = a.get("drug_score", 0)
        html += f'<li>[{source}] <a href="{url}" target="_blank">{title}</a> ({date}) - 评分:{score}</li>'
    html += '</ol>'

    html += '<p style="color:#f87171;margin-top:20px;">注意: DeepSeek API 未启用，此为基础版报告。设置 DEEPSEEK_API_KEY 可生成 AI 专业研判报告。</p>'
    html += '</div>'

    return {
        "title": "蒙古国毒品情报综合分析研判报告",
        "content": html,
        "article_count": len(drug_articles),
        "date_start": dates[0] if dates else "",
        "date_end": dates[-1] if dates else "",
    }
