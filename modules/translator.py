"""
情报翻译模块 - 将蒙语/英语内容翻译为中文
使用 deep-translator (Google Translate 免费接口)
"""

import asyncio
import re


def detect_need_translation(text: str) -> bool:
    """检测文本是否需要翻译（非中文则需要）"""
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    if total_chars == 0:
        return False
    return chinese_chars / total_chars < 0.5


def translate_text_sync(text: str, source: str = "auto", target: str = "zh-CN") -> str:
    """
    同步翻译文本（用于在 async 上下文中使用 run_in_executor）
    """
    if not text or not text.strip():
        return text
    if not detect_need_translation(text):
        return text
    try:
        from deep_translator import GoogleTranslator
        # 限制文本长度避免翻译 API 报错
        truncated = text[:1500]
        result = GoogleTranslator(source=source, target=target).translate(truncated)
        return result if result else text
    except Exception:
        # 翻译失败返回原文
        return text


async def translate_text(text: str, source: str = "auto", target: str = "zh-CN") -> str:
    """异步翻译文本"""
    if not text or not text.strip():
        return text
    if not detect_need_translation(text):
        return text
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, translate_text_sync, text, source, target)
        return result
    except Exception:
        return text


async def translate_article(item: dict) -> dict:
    """
    翻译情报的标题和摘要为中文。
    添加 cn_title 和 cn_summary 字段。
    """
    title = item.get("news_title", "")
    summary = item.get("content_summary", "")

    # 翻译标题
    if title and detect_need_translation(title):
        cn_title = await translate_text(title)
        item["cn_title"] = cn_title
    else:
        item["cn_title"] = title

    # 翻译摘要
    if summary and detect_need_translation(summary):
        cn_summary = await translate_text(summary)
        item["cn_summary"] = cn_summary
    else:
        item["cn_summary"] = summary

    return item
