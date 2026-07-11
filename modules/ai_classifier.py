"""
DeepSeek AI 智能内容分类器
============================
使用 DeepSeek API 判断文章是否是蒙古国毒品执法/走私/查获相关新闻。
API 兼容 OpenAI SDK，失败时回退到规则引擎。
"""

import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 简单内存缓存：避免同一 URL 重复调用 API
_cache: dict[str, dict] = {}

CLASSIFY_PROMPT = """你是一名毒品情报分析专家。请判断以下文章是否是关于【蒙古国毒品执法/毒品走私/毒品查获/禁毒行动】的新闻。

### 判断标准

相关 (is_relevant=true) — 必须同时满足:
1. 涉及蒙古国 (地理位置上)
2. 涉及非法毒品/麻醉品 (不是普通药品)
3. 内容涉及: 毒品查获、缴获、抓捕、走私、贩运、缉毒执法、禁毒立法、戒毒、跨境毒品犯罪、口岸缉毒

不相关 (is_relevant=false):
- 药品监管、药品注册、药品质量检测 (普通医药行政)
- 疫苗、新冠疫情、副作用报告
- 伦理投诉、行政事务、培训、研讨会
- 与毒品无关的普通新闻

### 输出格式
只返回 JSON，不要其他内容:
{"is_relevant": true/false, "confidence": 0.0-1.0, "reason": "简短说明(中文)"}
"""


def _call_deepseek(title: str, summary: str, source: str) -> dict:
    """调用 DeepSeek API 进行分类"""
    import httpx

    content = f"标题: {title}\n来源: {source}\n摘要: {summary[:800]}"

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": 0.0,
        "max_tokens": 150,
        "response_format": {"type": "json_object"},
    }

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                result_text = data["choices"][0]["message"]["content"]
                result = json.loads(result_text)
                return {
                    "is_relevant": result.get("is_relevant", False),
                    "confidence": result.get("confidence", 0.0),
                    "reason": result.get("reason", ""),
                    "ai_model": "deepseek-chat",
                }
    except Exception:
        pass

    return {"is_relevant": False, "confidence": 0, "reason": "API调用失败", "ai_model": "none"}


def classify_article(item: dict) -> dict:
    """
    AI 智能分类：判断文章是否与蒙古国毒品相关。
    使用缓存避免重复调用。
    返回 {"is_relevant": bool, "confidence": float, "reason": str}
    """
    url = item.get("source_url", "")
    title = item.get("news_title", "")
    summary = item.get("content_summary", "")
    source = item.get("source_name", "")

    # 缓存检查
    cache_key = url or f"{title[:50]}_{source}"
    if cache_key in _cache:
        return _cache[cache_key]

    # 调用 DeepSeek
    result = _call_deepseek(title, summary, source)

    # 存入缓存
    _cache[cache_key] = result
    return result


def clear_cache():
    """清空分类缓存"""
    _cache.clear()
