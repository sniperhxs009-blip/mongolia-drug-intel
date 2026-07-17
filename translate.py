"""
Batch Chinese translation using DeepSeek API.
Caches results in-memory to avoid re-translating.
"""
import os
import json
import hashlib
import time
import requests

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# Fallback: read from local apikey.txt (gitignored, for local dev)
if not DEEPSEEK_API_KEY:
    _key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apikey.txt")
    if os.path.exists(_key_file):
        with open(_key_file, "r") as f:
            DEEPSEEK_API_KEY = f.read().strip()
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
TRANSLATE_PROXY = os.environ.get("TRANSLATE_PROXY", os.environ.get("HTTPS_PROXY", os.environ.get("HTTP_PROXY", "")))

_translation_cache = {}


def _is_already_chinese(text):
    """Heuristic: if >15% of chars are CJK, assume already Chinese."""
    if not text:
        return False
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    return cjk / max(len(text), 1) > 0.15


def translate_articles_batch(articles):
    """Translate titles and first 300 chars of content for a list of article dicts (in-place).
    Skips articles whose titles are already Chinese. Returns count of translated articles."""
    if not articles or not DEEPSEEK_API_KEY:
        return 0

    texts = []
    indices = []
    for i, a in enumerate(articles):
        title = a.get("title", "")
        if not title or _is_already_chinese(title):
            continue
        texts.append(title)
        content = a.get("content", "")
        texts.append(content[:300] if content else "")
        indices.append(i)

    if not texts:
        return 0

    translated = batch_translate(texts, max_texts=25)
    count = 0
    for idx_in_list, art_idx in enumerate(indices):
        ti = idx_in_list * 2
        if ti < len(translated) and translated[ti]:
            articles[art_idx]["title"] = translated[ti]
            count += 1
        if ti + 1 < len(translated) and translated[ti + 1]:
            articles[art_idx]["content"] = translated[ti + 1]
    return count


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
        if chunk_start + max_texts < len(to_translate):
            time.sleep(2)  # avoid rate limiting between chunks

    return results


def _translate_chunk(chunk, results):
    """Translate a chunk of texts in one API call. Uses JSON for reliable parsing."""
    indices = [c[0] for c in chunk]
    texts = [c[1] for c in chunk]

    prompt = (
        f"Translate the following {len(texts)} texts to Simplified Chinese (简体中文). "
        f"Return ONLY a JSON array of {len(texts)} strings, nothing else. "
        f"Each element is the translation of the corresponding text. "
        f"Example format: [\"翻译1\", \"翻译2\", \"翻译3\"]\n\n"
        f"Texts to translate:\n"
    )
    for j, t in enumerate(texts):
        prompt += f"[{j}]: {t}\n"

    try:
        kwargs = {}
        if TRANSLATE_PROXY:
            kwargs["proxies"] = {"https": TRANSLATE_PROXY, "http": TRANSLATE_PROXY}
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
            timeout=60,
            **kwargs,
        )

        if resp.status_code == 200:
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            # Extract JSON array from response (handle markdown code blocks)
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            try:
                parts = json.loads(raw)
            except json.JSONDecodeError:
                # Try to extract array from text
                import re as _re
                m = _re.search(r"\[.*\]", raw, _re.DOTALL)
                if m:
                    try:
                        parts = json.loads(m.group())
                    except json.JSONDecodeError:
                        parts = []
                else:
                    parts = []

            if isinstance(parts, list) and len(parts) > 0:
                for i, idx in enumerate(indices):
                    if i < len(parts) and parts[i] and isinstance(parts[i], str):
                        clean = parts[i].strip()
                        results[idx] = clean
                        cache_key = hashlib.md5(texts[i].encode()).hexdigest()
                        _translation_cache[cache_key] = clean
                    else:
                        results[idx] = texts[i]
            else:
                for i, idx in enumerate(indices):
                    results[idx] = texts[i]
        else:
            for i, idx in enumerate(indices):
                results[idx] = texts[i]
    except Exception:
        # On failure, return originals for this chunk
        for i, idx in enumerate(indices):
            results[idx] = texts[i]
