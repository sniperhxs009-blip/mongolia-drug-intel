"""
Batch Chinese translation using DeepSeek API.
Caches results in-memory to avoid re-translating.
"""
import os
import json
import hashlib
import requests

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

_translation_cache = {}


def _is_already_chinese(text):
    """Heuristic: if >15% of chars are CJK, assume already Chinese."""
    if not text:
        return False
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    return cjk / max(len(text), 1) > 0.15


def batch_translate(texts, max_texts=30):
    """
    Translate a list of texts to Chinese.
    Returns a list of translated strings (same order).
    Skips texts that are already Chinese or empty.
    Uses in-memory cache.
    """
    if not DEEPSEEK_API_KEY:
        return list(texts)

    results = list(texts)
    to_translate = []  # (index, text) pairs

    for i, text in enumerate(texts):
        if not text or not text.strip():
            continue
        if _is_already_chinese(text):
            continue
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in _translation_cache:
            results[i] = _translation_cache[cache_key]
        else:
            to_translate.append((i, text))

    if not to_translate:
        return results

    # Batch into chunks of max_texts
    for chunk_start in range(0, len(to_translate), max_texts):
        chunk = to_translate[chunk_start:chunk_start + max_texts]
        _translate_chunk(chunk, results)

    return results


def _translate_chunk(chunk, results):
    """Translate a chunk of texts in one API call."""
    indices = [c[0] for c in chunk]
    texts = [c[1] for c in chunk]

    separator = "\n<<<SEP>>>\n"
    prompt = (
        f"Translate each of the following {len(texts)} texts to Simplified Chinese (简体中文). "
        f"Return exactly {len(texts)} translations separated by '{separator}'. "
        f"Do NOT include the separator in the translations themselves. "
        f"Return ONLY the translations, no numbering, no explanation:\n\n"
        + separator.join(texts)
    )

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
                "temperature": 0.1,
                "max_tokens": 4096,
            },
            timeout=45,
        )

        if resp.status_code == 200:
            data = resp.json()
            translated_text = data["choices"][0]["message"]["content"]
            parts = translated_text.split(separator)
            # Clean up whitespace
            parts = [p.strip() for p in parts]

            for idx, part in zip(indices, parts):
                if part:
                    clean = part.strip()
                    results[idx] = clean
                    cache_key = hashlib.md5(texts[indices.index(idx)].encode()).hexdigest()
                    _translation_cache[cache_key] = clean
                else:
                    results[idx] = texts[indices.index(idx)]

            # If count mismatch, fill remaining with originals
            if len(parts) < len(indices):
                for i in range(len(parts), len(indices)):
                    results[indices[i]] = texts[i]
    except Exception:
        # On failure, return originals for this chunk
        for i, idx in enumerate(indices):
            results[idx] = texts[i]
