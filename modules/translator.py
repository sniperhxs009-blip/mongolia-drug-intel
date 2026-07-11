"""
情报翻译模块 v2.0
=================
- deep-translator (Google Translate 免费接口)
- URL 级持久化翻译缓存，避免重复翻译
- 超长文本自动分段翻译，避免截断
- 协程并发锁，防止触发限流
"""

import asyncio
import json
import re
from pathlib import Path

from modules.logger import get_logger

log = get_logger("translator")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TRANSLATION_CACHE_FILE = DATA_DIR / ".translation_cache.json"

# 翻译并发锁（最多同时 3 个翻译请求）
_translate_semaphore = asyncio.Semaphore(3)
# 翻译缓存 {url: {"cn_title": str, "cn_summary": str}}
_cache: dict[str, dict] = {}
_cache_loaded = False
# 单段最大字符数（超过则分段翻译）
MAX_SEGMENT_LENGTH = 1500


def _load_cache():
    global _cache, _cache_loaded
    if _cache_loaded:
        return
    try:
        if TRANSLATION_CACHE_FILE.exists():
            with open(TRANSLATION_CACHE_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
            log.info("翻译缓存加载: %d 条", len(_cache))
    except Exception:
        pass
    _cache_loaded = True


def _save_cache():
    try:
        with open(TRANSLATION_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False)
    except Exception as e:
        log.warning("翻译缓存保存失败: %s", e)


def _cache_key(item: dict) -> str:
    """基于 URL 生成缓存键"""
    return item.get("source_url", "")


def _get_cached(cache_key: str) -> dict | None:
    _load_cache()
    return _cache.get(cache_key)


def _set_cache(cache_key: str, data: dict):
    _load_cache()
    _cache[cache_key] = data
    _save_cache()


def detect_need_translation(text: str) -> bool:
    """检测文本是否需要翻译（非中文则需要）"""
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    if total_chars == 0:
        return False
    return chinese_chars / total_chars < 0.5


def _split_long_text(text: str, max_len: int = MAX_SEGMENT_LENGTH) -> list[str]:
    """将长文本按句子边界分割为多个段落"""
    if len(text) <= max_len:
        return [text]

    segments = []
    # 按句子分隔符拆分
    parts = re.split(r'(?<=[。！？\.\!\?\n])', text)
    current = ""
    for part in parts:
        if len(current) + len(part) > max_len and current:
            segments.append(current.strip())
            current = part
        else:
            current += part
    if current.strip():
        segments.append(current.strip())
    return segments if segments else [text]


def translate_text_sync(text: str, source: str = "auto", target: str = "zh-CN") -> str:
    """
    同步翻译文本，支持超长文本自动分段翻译。
    """
    if not text or not text.strip():
        return text
    if not detect_need_translation(text):
        return text

    try:
        from deep_translator import GoogleTranslator

        segments = _split_long_text(text)
        if len(segments) == 1:
            translator = GoogleTranslator(source=source, target=target)
            result = translator.translate(text)
            return result if result else text

        # 分段翻译
        results = []
        translator = GoogleTranslator(source=source, target=target)
        for i, seg in enumerate(segments):
            try:
                r = translator.translate(seg)
                results.append(r if r else seg)
            except Exception:
                results.append(seg)
        return " ".join(results)

    except Exception:
        return text


async def translate_text(text: str, source: str = "auto", target: str = "zh-CN") -> str:
    """异步翻译文本（带并发控制）"""
    if not text or not text.strip():
        return text
    if not detect_need_translation(text):
        return text

    async with _translate_semaphore:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, translate_text_sync, text, source, target)
            return result
        except Exception:
            return text


async def translate_article(item: dict) -> dict:
    """
    翻译情报的标题和摘要为中文，按 URL 缓存避免重复翻译。
    """
    cache_key = _cache_key(item)

    # 检查缓存
    cached = _get_cached(cache_key)
    if cached:
        item["cn_title"] = cached.get("cn_title", item.get("news_title", ""))
        item["cn_summary"] = cached.get("cn_summary", item.get("content_summary", ""))
        return item

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

    # 写入缓存
    if cache_key:
        _set_cache(cache_key, {"cn_title": item["cn_title"], "cn_summary": item["cn_summary"]})

    return item
