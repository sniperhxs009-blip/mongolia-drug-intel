"""Test filter pipeline on a real article"""
import sys, io, requests
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from modules.parser import parse_article_html
from modules.filter_module import strict_filter, ai_classify, date_filter

url = 'https://see.mn/58337.html'
resp = requests.get(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://see.mn/'
}, timeout=15)

site = {'name': 'See.mn', 'language': 'mn', 'category_name': 'test'}
parsed = parse_article_html(resp.text, url, site)
if parsed:
    title = parsed['news_title']
    pub_date = parsed['publish_time']
    summary = parsed['content_summary']
    print(f'Title: {title[:80]}')
    print(f'Date: {pub_date}')
    print(f'Summary[:200]: {summary[:200]}')

    date_ok = date_filter(parsed, max_days=90)
    print(f'Date filter (90d): {date_ok}')

    result = ai_classify(parsed)
    print(f'Rule engine: pass={result["pass"]}, score={result["score"]}, reason={result["reason"]}')
    hits = result.get('hits', {})
    print(f'  Strong: {hits.get("strong", [])}')
    print(f'  Enforcement: {hits.get("enforcement", [])}')
    print(f'  Geo: {hits.get("geo", [])}')
    print(f'  Exclusion: {hits.get("exclusion", [])}')

    final = strict_filter(parsed)
    print(f'strict_filter: {final}')
else:
    print('PARSE FAILED')
