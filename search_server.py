from flask import Flask, request, render_template_string, jsonify, redirect, Response
from settings_store import (get_email_recipients, add_email_recipient, remove_email_recipient,
    toggle_email_recipient, get_smtp_config, save_smtp_config, get_push_schedules,
    save_push_schedule, delete_push_schedule, get_next_push_time,
    save_report, get_latest_report, get_report_by_id, migrate_from_sqlite)
import memory_crawler
from memory_crawler import (crawl_site as mc_crawl_site, get_cached_articles,
    get_cache_size, get_cache_stats, is_in_cache, add_to_cache,
    _article_cache, _seen_urls, _cache_lock, _is_within_months, quick_parse, http_session)
from sites import SITES
from drug_keywords import get_all_keywords, match_drug_keywords, score_article
from global_search import global_drug_search
from translate import batch_translate, translate_articles_batch, DEEPSEEK_API_KEY
from report_generator import generate_intelligence_report
from email_sender import send_drug_intel_email, send_instant_alert, test_smtp_connection
import requests
import re
import time
import threading
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

app = Flask(__name__)

# --- Auto-crawler daemon starter (works for both `python search_server.py` and gunicorn) ---
_crawler_thread_started = False


def _start_crawler_thread():
    global _crawler_thread_started
    if _crawler_thread_started:
        return
    _crawler_thread_started = True
    t = threading.Thread(target=_auto_crawl_loop, daemon=True, name="auto-crawler")
    t.start()
    print("[启动] 后台自动爬虫线程已启动")


@app.errorhandler(500)
def _handle_500(e):
    import traceback
    tb = traceback.format_exc()
    return f"<pre>500 Error:\n{tb}</pre>", 500


@app.before_request
def _ensure_crawler_running():
    """Start crawler thread on first HTTP request (handles gunicorn import case)."""
    _start_crawler_thread()


# --- Auto-crawler background thread ---
_auto_crawler = {
    "running": False,
    "last_crawl": None,         # datetime
    "last_crawl_count": 0,      # new articles found in last crawl
    "next_crawl": None,         # datetime
    "interval_minutes": int(os.environ.get("AUTO_CRAWL_INTERVAL", "720")),
    "current_site": "",         # which site is being crawled now
    "total_new_today": 0,       # total new articles found today
    "last_alert_time": None,    # last instant alert datetime
    "alert_count_today": 0,     # number of instant alerts sent today
    "last_push_time": None,     # last email push datetime
    "is_crawling": False,       # prevent concurrent crawls
    "crawl_lock": threading.Lock(),
}

def _auto_crawl_loop():
    """Background daemon: crawl every N hours, push drug intel email after each cycle.
    Works independently of browser — server process must be running."""
    from drug_ai import DrugAnalyzer

    _auto_crawler["running"] = True
    crawl_interval = _auto_crawler["interval_minutes"] * 60
    analyzer = DrugAnalyzer()
    all_keywords = get_all_keywords()

    time.sleep(30)  # Initial delay to let server start

    session = requests.Session()
    session.headers.update(memory_crawler.HEADERS)

    while True:
        now = datetime.now()

        with _auto_crawler["crawl_lock"]:
            if _auto_crawler["is_crawling"]:
                skip = True
            else:
                _auto_crawler["is_crawling"] = True
                skip = False
            _auto_crawler["next_crawl"] = now + timedelta(seconds=crawl_interval)
            _auto_crawler["current_site"] = ""

        if skip:
            # Sleep in small increments, checking if crawl finished
            for _ in range(crawl_interval // 30):
                time.sleep(30)
            continue

        pre_count = get_cache_size()
        total_new = 0

        for site in SITES:
            if site.get("requires_js"):
                continue
            _auto_crawler["current_site"] = site["label"]
            try:
                arts, new_count = mc_crawl_site(site, session, max_articles=200, months=3,
                                                   max_seconds=60, max_pages=20)
                total_new += new_count
                if new_count > 0:
                    print(f"[实时监控] {site['label']}: +{new_count} 篇新文章")
            except Exception as e:
                print(f"[实时监控] {site['label']}: 错误 - {e}")
            time.sleep(0.5)

        _auto_crawler["last_crawl"] = datetime.now()
        _auto_crawler["last_crawl_count"] = total_new
        _auto_crawler["total_new_today"] += total_new
        _auto_crawler["current_site"] = ""
        print(f"[实时监控] 爬取完成: +{total_new} 篇新文章, 共 {len(SITES)} 个站点")

        # ---- Instant Drug Alert (if new articles found) ----
        if total_new > 0:
            try:
                with _cache_lock:
                    cache_values = list(_article_cache.values())
                    new_articles = cache_values[pre_count:] if pre_count < len(cache_values) else []

                if new_articles:
                    drug_hits = []
                    for d in new_articles:
                        title = d.get("_orig_title") or d.get("title") or ""
                        content = d.get("_orig_content") or d.get("content") or ""
                        text = (title + " " + content).lower()
                        kw_match = any(kw.lower() in text for kw in all_keywords if len(kw) >= 3)
                        if not kw_match:
                            continue
                        analysis = analyzer.analyze(title, content, d.get("source"))
                        if analysis["is_drug"]:
                            d["drug_score"] = analysis["score"]
                            d["drug_confidence"] = analysis["confidence"]
                            d["drug_types"] = analysis.get("drug_types", [])
                            d["drug_action"] = analysis.get("action", "")
                            d["matched_keywords"] = analysis.get("keywords", [])
                            drug_hits.append(d)

                    if drug_hits:
                        drug_hits.sort(key=lambda x: -x["drug_score"])
                        print(f"[实时预警] 发现 {len(drug_hits)} 篇涉毒文章，立即推送!")
                        try:
                            result = send_instant_alert(drug_hits)
                            _auto_crawler["last_alert_time"] = datetime.now()
                            _auto_crawler["alert_count_today"] += 1
                            print(f"[实时预警] 推送完成: {result['sent']} 封成功")
                        except Exception as e:
                            print(f"[实时预警] 推送失败: {e}")
            except Exception as e:
                print(f"[实时预警] 分析失败: {e}")

        # ---- Email Digest Push (after every crawl cycle) ----
        print(f"[定时推送] 爬取完成，发送涉毒情报邮件...")
        try:
            result = send_drug_intel_email()
            _auto_crawler["last_push_time"] = datetime.now()
            print(f"[定时推送] 发送完成: {result['sent']} 封成功, {len(result.get('errors', []))} 个错误")
        except Exception as e:
            print(f"[定时推送] 失败: {e}")

        with _auto_crawler["crawl_lock"]:
            _auto_crawler["is_crawling"] = False

        # ---- Sleep until next crawl ----
        print(f"[实时监控] 下次爬取: {(datetime.now() + timedelta(seconds=crawl_interval)).strftime('%Y-%m-%d %H:%M:%S')}")
        for _ in range(crawl_interval // 30):
            time.sleep(30)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>蒙古国毒品新闻搜集研判系统</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
  --bg: #060b14;
  --surface: rgba(15, 23, 42, 0.7);
  --surface-hover: rgba(20, 30, 55, 0.85);
  --border: rgba(56, 189, 248, 0.12);
  --accent: #38bdf8;
  --accent2: #818cf8;
  --accent3: #22d3ee;
  --text: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --glow: 0 0 20px rgba(56, 189, 248, 0.15), 0 0 60px rgba(56, 189, 248, 0.05);
  --glow-strong: 0 0 30px rgba(56, 189, 248, 0.3), 0 0 80px rgba(56, 189, 248, 0.1);
  --gradient-1: linear-gradient(135deg, #0ea5e9, #6366f1);
  --gradient-2: linear-gradient(135deg, #06b6d4, #8b5cf6);
  --gradient-3: linear-gradient(135deg, #3b82f6, #a855f7);
  --radius: 12px;
  --radius-lg: 16px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
}

/* Animated Background Grid */
.bg-grid {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  animation: gridDrift 20s linear infinite;
}
@keyframes gridDrift {
  0% { background-position: 0 0, 0 0; }
  100% { background-position: 60px 60px, 60px 60px; }
}

.bg-orb {
  position: fixed; border-radius: 50%; filter: blur(120px); opacity: 0.08; z-index: 0; pointer-events: none;
}
.bg-orb-1 { top: -200px; left: -100px; width: 600px; height: 600px; background: #3b82f6; animation: orbFloat 8s ease-in-out infinite; }
.bg-orb-2 { bottom: -200px; right: -100px; width: 500px; height: 500px; background: #8b5cf6; animation: orbFloat 12s ease-in-out infinite reverse; }
.bg-orb-3 { top: 40%; left: 50%; width: 400px; height: 400px; background: #06b6d4; animation: orbFloat 10s ease-in-out infinite; }
@keyframes orbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -30px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
}

/* Scan Line Effect */
.scan-line {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(56, 189, 248, 0.008) 2px, rgba(56, 189, 248, 0.008) 4px);
}

/* Top Progress Bar */
.progress-bar-wrap {
  position: fixed; top: 0; left: 0; width: 100%; height: 2px; z-index: 100; background: rgba(255,255,255,0.03);
}
.progress-bar-fill {
  height: 100%; background: var(--gradient-1); border-radius: 0 2px 2px 0;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 0 12px rgba(56, 189, 248, 0.5);
}
.progress-bar-fill.active {
  animation: progressPulse 2s ease-in-out infinite;
}
@keyframes progressPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Header */
.header {
  position: relative; z-index: 2;
  padding: 40px 20px 30px; text-align: center;
}
.header::after {
  content: ''; position: absolute; bottom: 0; left: 50%; transform: translateX(-50%);
  width: 120px; height: 2px;
  background: var(--gradient-1); border-radius: 1px;
}
.header h1 {
  font-size: 32px; font-weight: 800; letter-spacing: -0.5px;
  background: var(--gradient-2);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 8px;
}
.header .subtitle {
  font-size: 13px; color: var(--text-secondary); font-weight: 400;
}
.header .subtitle span {
  color: var(--accent); font-weight: 600;
}

.container { max-width: 960px; margin: 0 auto; padding: 0 16px 40px; position: relative; z-index: 2; }

/* Search Box */
.search-box {
  display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap;
  background: var(--surface); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  padding: 16px; border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--glow);
}
.search-box input {
  flex: 1; min-width: 200px; padding: 12px 16px;
  background: rgba(15, 23, 42, 0.8); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  font-size: 14px; outline: none; font-family: inherit;
  transition: all 0.3s;
}
.search-box input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.1), 0 0 15px rgba(56, 189, 248, 0.1);
}
.search-box input::placeholder { color: var(--text-muted); }
.search-box select {
  padding: 12px 14px;
  background: rgba(15, 23, 42, 0.8); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  font-size: 13px; cursor: pointer; outline: none; font-family: inherit;
  min-width: 130px;
  transition: all 0.3s;
}
.search-box select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.1);
}
.search-box select option { background: #0f172a; color: #e2e8f0; }

.btn {
  padding: 12px 20px; border: 1px solid transparent; border-radius: 10px;
  font-size: 13px; cursor: pointer; font-weight: 600; font-family: inherit;
  white-space: nowrap; transition: all 0.3s;
}
.btn-search { background: rgba(56, 189, 248, 0.15); color: var(--accent); border-color: rgba(56, 189, 248, 0.3); }
.btn-search:hover { background: rgba(56, 189, 248, 0.25); box-shadow: 0 0 25px rgba(56, 189, 248, 0.2); transform: translateY(-1px); }
.btn-live { background: rgba(34, 197, 94, 0.15); color: #4ade80; border-color: rgba(34, 197, 94, 0.3); }
.btn-live:hover { background: rgba(34, 197, 94, 0.25); box-shadow: 0 0 25px rgba(34, 197, 94, 0.2); transform: translateY(-1px); }
.btn-drugs { background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: rgba(239, 68, 68, 0.3); }
.btn-drugs:hover { background: rgba(239, 68, 68, 0.25); box-shadow: 0 0 25px rgba(239, 68, 68, 0.2); transform: translateY(-1px); }
.btn-global { background: rgba(13, 148, 136, 0.15); color: #2dd4bf; border-color: rgba(13, 148, 136, 0.3); }
.btn-global:hover { background: rgba(13, 148, 136, 0.25); box-shadow: 0 0 25px rgba(13, 148, 136, 0.2); transform: translateY(-1px); }

/* Stats Bar */
.stats-bar {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px; flex-wrap: wrap;
}
.stat-card {
  background: var(--surface); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px 20px; display: flex; align-items: center; gap: 12px;
  box-shadow: var(--glow);
}
.stat-icon {
  width: 40px; height: 40px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.stat-icon.blue { background: rgba(56, 189, 248, 0.15); }
.stat-icon.green { background: rgba(34, 197, 94, 0.15); }
.stat-icon.purple { background: rgba(147, 51, 234, 0.15); }
.stat-value {
  font-size: 28px; font-weight: 800; letter-spacing: -1px;
  background: var(--gradient-1); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent; background-clip: text;
}
.stat-label { font-size: 11px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }

/* Results */
.results { display: flex; flex-direction: column; gap: 14px; }

.card {
  position: relative;
  background: var(--surface); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  padding: 20px 22px; border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--glow);
  overflow: hidden;
}
.card::before {
  content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 0;
  background: var(--gradient-1); border-radius: 0 3px 3px 0;
  transition: height 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.card:hover::before { height: 100%; }
.card:hover {
  border-color: rgba(56, 189, 248, 0.25);
  box-shadow: var(--glow-strong);
  transform: translateX(3px) translateY(-1px);
}
.card h3 { font-size: 15px; margin-bottom: 8px; line-height: 1.4; font-weight: 600; }
.card h3 a { color: var(--text); text-decoration: none; transition: color 0.2s; }
.card h3 a:hover { color: var(--accent); }
.card .meta {
  font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;
  display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
}
.card .meta .pub-date {
  font-weight: 600; color: var(--accent);
  background: rgba(56, 189, 248, 0.1); padding: 2px 8px; border-radius: 6px;
}
.card .source-tag {
  display: inline-block; padding: 3px 10px; border-radius: 6px;
  font-weight: 600; font-size: 10px; letter-spacing: 0.3px;
}
.card .snippet {
  font-size: 12px; color: var(--text-secondary); line-height: 1.5;
  overflow: hidden; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.drug-badge {
  display: inline-block; padding: 3px 10px; border-radius: 6px;
  font-weight: 600; font-size: 10px; letter-spacing: 0.3px;
}

/* Empty State */
.empty { text-align: center; padding: 100px 20px; }
.empty .icon {
  font-size: 64px; margin-bottom: 16px;
  background: var(--gradient-2); -webkit-background-clip: text;
  -webkit-text-fill-color: transparent; background-clip: text;
}
.empty p { color: var(--text-secondary); font-size: 14px; }
.empty p strong { color: var(--accent); }

/* Loading */
.loading { text-align: center; padding: 60px 20px; }
.loading-spinner {
  width: 48px; height: 48px; margin: 0 auto 16px;
  border: 2px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading p { color: var(--text-secondary); font-size: 13px; }

/* Loading overlay */
.loading-overlay {
  display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(6, 11, 20, 0.85); backdrop-filter: blur(4px);
  z-index: 9999; flex-direction: column; align-items: center; justify-content: center;
}
.loading-overlay.show { display: flex; }
.loading-overlay .spinner-ring {
  width: 50px; height: 50px;
  border: 3px solid rgba(56, 189, 248, 0.15);
  border-top-color: #38bdf8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.loading-overlay .loading-msg {
  color: #e2e8f0; font-size: 16px; font-weight: 600; margin-top: 20px;
}
.loading-overlay .loading-sub {
  color: #64748b; font-size: 12px; margin-top: 6px;
}
.loading-overlay .loading-bar-wrap {
  width: 280px; height: 3px; background: rgba(56, 189, 248, 0.1);
  border-radius: 2px; margin-top: 24px; overflow: hidden;
}
.loading-overlay .loading-bar-inner {
  height: 100%; width: 30%; background: linear-gradient(90deg, #38bdf8, #818cf8);
  border-radius: 2px;
  animation: loadingSlide 1.5s ease-in-out infinite;
}
@keyframes loadingSlide {
  0% { width: 0%; margin-left: 0; }
  50% { width: 60%; margin-left: 20%; }
  100% { width: 0%; margin-left: 100%; }
}

/* Pagination */
.pagination { display: flex; justify-content: center; gap: 8px; margin-top: 24px; }
.pagination a {
  padding: 10px 18px; border-radius: 10px; text-decoration: none;
  color: var(--accent); font-size: 13px; font-weight: 600;
  background: var(--surface); border: 1px solid var(--border);
  transition: all 0.3s;
}
.pagination a:hover {
  border-color: rgba(56, 189, 248, 0.4);
  box-shadow: 0 0 15px rgba(56, 189, 248, 0.15);
}
.pagination span.active {
  padding: 10px 18px; border-radius: 10px;
  background: rgba(56, 189, 248, 0.15); color: var(--accent);
  border: 1px solid rgba(56, 189, 248, 0.3); font-size: 13px; font-weight: 600;
}

@media (max-width: 640px) {
  .header h1 { font-size: 22px; }
  .search-box { padding: 12px; gap: 6px; }
  .btn { padding: 10px 14px; font-size: 12px; }
  .stats-bar { flex-direction: column; align-items: stretch; }
  .stat-card { justify-content: center; }
  .card { padding: 14px 16px; }
}
</style>
</head>
<body>

<div class="bg-grid"></div>
<div class="bg-orb bg-orb-1"></div>
<div class="bg-orb bg-orb-2"></div>
<div class="bg-orb bg-orb-3"></div>
<div class="scan-line"></div>

<div class="progress-bar-wrap">
  <div class="progress-bar-fill {{ 'active' if loading else '' }}" style="width: {{ progress }}%"></div>
</div>

<!-- Loading Overlay -->
<div id="loading-overlay" class="loading-overlay show">
  <div class="spinner-ring"></div>
  <div id="loading-msg" class="loading-msg">正在处理...</div>
  <div class="loading-sub">请稍候</div>
  <div class="loading-bar-wrap"><div class="loading-bar-inner"></div></div>
</div>

<div class="header">
  <h1>蒙古国毒品新闻搜集研判系统</h1>
  <p class="subtitle">AI 驱动的蒙古毒品情报多源搜索系统
  {% if ai_enabled %}
  <span style="display:inline-block;background:rgba(34,197,94,0.2);color:#4ade80;border:1px solid rgba(34,197,94,0.3);padding:2px 10px;border-radius:12px;font-size:12px;margin-left:8px;">自动翻译已启用</span>
  {% else %}
  <span style="display:inline-block;background:rgba(239,68,68,0.2);color:#f87171;border:1px solid rgba(239,68,68,0.3);padding:2px 10px;border-radius:12px;font-size:12px;margin-left:8px;" title="设置 DEEPSEEK_API_KEY 环境变量以启用 AI 翻译">翻译未启用</span>
  {% endif %}
  </p>
</div>

<div class="container">
  <form class="search-box" method="GET">
    <select name="source" id="source-select">
      <option value="">全部来源</option>
      {% for s in all_sources %}
      <option value="{{ s.name }}" {% if current_source==s.name %}selected{% endif %}>{{ s.label }}</option>
      {% endfor %}
    </select>
    <input type="hidden" name="page" value="1">
    <button type="button" id="btn-live" class="btn btn-live" onclick="startLiveFetch()">实时抓取</button>
    <button type="submit" name="action" value="drugs" class="btn btn-drugs">毒品新闻</button>
    <button type="submit" name="action" value="global" class="btn btn-global" title="从全球互联网搜索蒙古毒品相关新闻">🌐 全球搜索</button>
    <a href="/report" class="btn" style="background:rgba(245,158,11,0.15);color:#fbbf24;border-color:rgba(245,158,11,0.3);text-decoration:none;display:inline-block;line-height:1.4;">📋 研判报告</a>
    <a href="/settings" class="btn" style="background:rgba(148,163,184,0.1);color:#94a3b8;border-color:rgba(148,163,184,0.2);text-decoration:none;display:inline-block;line-height:1.4;">⚙️ 设置</a>
  </form>

  {% if query or results %}
  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-icon blue">📊</div>
      <div>
        <div class="stat-value">{{ total_results }}</div>
        <div class="stat-label">搜索结果</div>
      </div>
    </div>
    <div class="stat-card">
      <div class="stat-icon purple">🔍</div>
      <div>
        <div class="stat-value">{{ all_sources|length }}</div>
        <div class="stat-label">监控来源</div>
      </div>
    </div>
    {% if crawler.running %}
    <div class="stat-card" style="border-color:rgba(239,68,68,0.3);">
      <div class="stat-icon green" style="position:relative;">
        <span style="font-size:12px;">🔄</span>
        <span style="position:absolute;bottom:2px;right:2px;width:6px;height:6px;background:#ef4444;border-radius:50%;animation:progressPulse 1s ease-in-out infinite;"></span>
      </div>
      <div>
        <div class="stat-value" style="font-size:13px;background:linear-gradient(135deg,#ef4444,#f87171);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">
          {% if crawler.current_site %}
          实时监控中: {{ crawler.current_site }}
          {% elif crawler.last_crawl %}
          上次扫描: {{ crawler.last_crawl.strftime('%H:%M:%S') }}
          {% else %}
          启动中...
          {% endif %}
        </div>
        <div class="stat-label" style="color:#f87171;">
          实时监控 · 每{{ "%.0f"|format(crawler.interval_h) }}小时
          {% if crawler.alert_count > 0 %}
          · 今日预警 {{ crawler.alert_count }} 次
          {% endif %}
        </div>
      </div>
    </div>
    {% endif %}
  </div>
  {% endif %}

  <!-- Live Fetch Progress -->
  <div id="live-progress" style="display:none;margin:20px 0;padding:16px 20px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);">
    <div style="display:flex;align-items:center;gap:12px;">
      <div id="live-spinner" style="width:20px;height:20px;border:2px solid rgba(56,189,248,0.2);border-top-color:#38bdf8;border-radius:50%;animation:spin 0.8s linear infinite;"></div>
      <div>
        <span id="live-status" style="color:#38bdf8;font-weight:600;">正在连接...</span>
        <span id="live-count" style="color:var(--text-secondary);margin-left:8px;font-size:13px;"></span>
      </div>
      <button type="button" onclick="stopLiveFetch()" style="margin-left:auto;background:rgba(239,68,68,0.1);color:#f87171;border:1px solid rgba(239,68,68,0.2);border-radius:6px;padding:4px 12px;cursor:pointer;font-size:12px;">停止</button>
    </div>
  </div>
  <style>@keyframes spin { to { transform:rotate(360deg); } }</style>

  <!-- Live Results Container -->
  <div id="live-results" style="display:none;"></div>

  {% if loading %}
  <div class="loading">
    <div class="loading-spinner"></div>
    <p>正在从所有来源抓取最新情报...</p>
  </div>
  {% endif %}

  {% if results %}
  <div class="results">
    {% for r in results %}
    <div class="card">
      <h3><a href="{{ r.url }}" target="_blank">{{ r.title or '(无标题)' }}</a></h3>
      <div class="meta">
        <span class="pub-date">{{ r.date or '' }}</span>
        <span class="source-tag" style="background:{{ source_colors.get(r.source, 'rgba(56,189,248,0.1)') }};color:{{ source_text_colors.get(r.source, '#38bdf8') }}">{{ r.source_label or r.source }}</span>
        {% if r.category %}<span style="font-size:10px;color:var(--text-muted)">{{ r.category }}</span>{% endif %}
        {% if r.matched_keywords %}
        <span class="drug-badge" style="background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.2);">🎯 {{ r.drug_score }}分 | {{ (r.matched_keywords or [])[:2]|join(', ') }}</span>
        {% endif %}
        {% if r.drug_stage %}
        <span class="drug-badge" style="background:rgba(147,51,234,0.15);color:#a78bfa;border:1px solid rgba(147,51,234,0.2);">🤖 {{ r.drug_stage }} | {{ r.drug_confidence }}</span>
        {% endif %}
        {% if r.drug_types %}
        <span class="drug-badge" style="background:rgba(34,197,94,0.15);color:#4ade80;border:1px solid rgba(34,197,94,0.2);">{{ (r.drug_types or [])[:3]|join(', ') }}</span>
        {% endif %}
        {% if r.drug_action %}
        <span style="font-size:10px;color:var(--accent2);font-weight:600;">{{ r.drug_action }}</span>
        {% endif %}
      </div>
      <div class="snippet">{{ (r.content or '')[:250] }}{% if (r.content or '')|length > 250 %}...{% endif %}</div>
    </div>
    {% endfor %}
  </div>

  <div class="pagination">
    {% if page > 1 %}
    <a href="?source={{ current_source or '' }}&page={{ page - 1 }}&action={{ request.args.get('action','') }}">← 上一页</a>
    {% endif %}
    <span class="active">第 {{ page }} 页</span>
    {% if page * per_page < total_results %}
    <a href="?source={{ current_source or '' }}&page={{ page + 1 }}&action={{ request.args.get('action','') }}">下一页 →</a>
    {% endif %}
  </div>

  {% elif query %}
  <div class="empty">
    <div class="icon">🔎</div>
    <p>未找到与 "<strong>{{ query }}</strong>" 相关的结果</p>
  </div>
  {% else %}
  <div class="empty">
    <div class="icon">🛰️</div>
    <p>点击<strong>实时抓取</strong>按钮获取最新情报（近3个月）</p>
  </div>
  {% endif %}
</div>

<script>
let liveEventSource = null;
let liveArticleCount = 0;

// Loading overlay for search/filter buttons
(function() {
  const overlay = document.getElementById('loading-overlay');
  const msg = document.getElementById('loading-msg');
  // Set message based on current action
  const params = new URLSearchParams(window.location.search);
  const action = params.get('action') || '';
  const labels = {
    'drugs': '正在搜索毒品相关新闻...',
'global': '正在全球互联网搜索蒙古毒品情报...',
  };
  if (labels[action]) {
    msg.textContent = labels[action];
  }

  // Hide overlay when page is fully loaded
  function hideOverlay() {
    overlay.classList.remove('show');
  }
  if (document.readyState === 'complete') {
    hideOverlay();
  } else {
    window.addEventListener('load', hideOverlay);
  }

  // Show overlay on form submit - force render before navigating
  var form = document.querySelector('.search-box');
  if (form) {
    form.addEventListener('submit', function(e) {
      var btn = e.submitter;
      if (!btn || btn.id === 'btn-live') return;
      e.preventDefault();
      if (btn.value) {
        msg.textContent = labels[btn.value] || '正在加载...';
      }
      overlay.classList.add('show');
      // Remove any stale hidden action input from previous submits
      var oldAction = form.querySelector('input[name="action"]');
      if (oldAction) oldAction.remove();
      // Force browser to render the overlay before submitting
      requestAnimationFrame(function() {
        requestAnimationFrame(function() {
          var input = document.createElement('input');
          input.type = 'hidden';
          input.name = 'action';
          input.value = btn.value;
          form.appendChild(input);
          form.submit();
        });
      });
    });
  }

  // Source filter change
  var sourceSelect = document.getElementById('source-select');
  if (sourceSelect) {
    sourceSelect.addEventListener('change', function() {
      var oldAction = this.form.querySelector('input[name="action"]');
      if (oldAction) oldAction.remove();
      msg.textContent = '正在筛选...';
      overlay.classList.add('show');
      this.form.submit();
    });
  }
})();

function startLiveFetch() {
  // Reset
  liveArticleCount = 0;
  document.getElementById('live-results').innerHTML = '';
  document.getElementById('live-results').style.display = 'block';
  document.getElementById('live-progress').style.display = 'block';
  document.getElementById('live-status').textContent = '正在连接...';
  document.getElementById('live-count').textContent = '';
  document.getElementById('btn-live').disabled = true;

  // Hide static results if any
  const staticResults = document.querySelector('.results');
  if (staticResults) staticResults.style.display = 'none';

  liveEventSource = new EventSource('/api/live-stream');

  liveEventSource.addEventListener('site_start', function(e) {
    const data = JSON.parse(e.data);
    document.getElementById('live-status').textContent = '正在抓取: ' + data.site;
  });

  liveEventSource.addEventListener('site_error', function(e) {
    const data = JSON.parse(e.data);
    console.log('Site error:', data.site, data.error);
  });

  liveEventSource.addEventListener('site_done', function(e) {
    const data = JSON.parse(e.data);
    document.getElementById('live-count').textContent = '已抓取 ' + liveArticleCount + ' 条';
  });

  liveEventSource.addEventListener('done', function(e) {
    const data = JSON.parse(e.data);
    document.getElementById('live-status').textContent = '抓取完成';
    document.getElementById('live-count').textContent = '共 ' + data.total + ' 条新闻';
    document.getElementById('live-spinner').style.display = 'none';
    document.getElementById('btn-live').disabled = false;
    liveEventSource.close();
    liveEventSource = null;
  });

  liveEventSource.onmessage = function(e) {
    const art = JSON.parse(e.data);
    liveArticleCount++;
    document.getElementById('live-count').textContent = '已抓取 ' + liveArticleCount + ' 条';
    appendArticleCard(art);
  };

  liveEventSource.onerror = function(e) {
    if (liveEventSource && liveEventSource.readyState === EventSource.CLOSED) {
      document.getElementById('live-status').textContent = '连接中断';
      document.getElementById('live-spinner').style.display = 'none';
      document.getElementById('btn-live').disabled = false;
    }
  };
}

function stopLiveFetch() {
  if (liveEventSource) {
    liveEventSource.close();
    liveEventSource = null;
  }
  document.getElementById('live-status').textContent = '已停止';
  document.getElementById('live-spinner').style.display = 'none';
  document.getElementById('btn-live').disabled = false;
}

function appendArticleCard(art) {
  const container = document.getElementById('live-results');
  const card = document.createElement('div');
  card.className = 'card';
  card.style.animation = 'fadeIn 0.3s ease';

  const date = art.date || '';
  const sourceLabel = art.source_label || art.source || '';
  const content = (art.content || '').substring(0, 250);
  const more = (art.content || '').length > 250 ? '...' : '';

  card.innerHTML =
    '<h3><a href="' + art.url + '" target="_blank">' + (art.title || '') + '</a></h3>' +
    '<div class="meta">' +
      '<span class="pub-date">' + date + '</span>' +
      '<span class="source-tag" style="background:rgba(56,189,248,0.1);color:#38bdf8">' + sourceLabel + '</span>' +
    '</div>' +
    '<div class="snippet">' + content + more + '</div>';

  container.insertBefore(card, container.firstChild);
}
</script>

</body>
</html>
"""

REPORT_PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>情报研判报告 - 蒙古国毒品新闻搜集研判系统</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
  --bg: #060b14;
  --surface: rgba(15, 23, 42, 0.7);
  --border: rgba(56, 189, 248, 0.12);
  --accent: #38bdf8;
  --text: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --glow: 0 0 20px rgba(56, 189, 248, 0.15);
  --gradient-1: linear-gradient(135deg, #0ea5e9, #6366f1);
  --gradient-2: linear-gradient(135deg, #06b6d4, #8b5cf6);
  --radius: 12px;
  --radius-lg: 16px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh; overflow-x: hidden;
}

.bg-grid {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  animation: gridDrift 20s linear infinite;
}
@keyframes gridDrift {
  0% { background-position: 0 0, 0 0; }
  100% { background-position: 60px 60px, 60px 60px; }
}

.bg-orb {
  position: fixed; border-radius: 50%; filter: blur(120px); opacity: 0.08; z-index: 0; pointer-events: none;
}
.bg-orb-1 { top: -200px; left: -100px; width: 600px; height: 600px; background: #3b82f6; animation: orbFloat 8s ease-in-out infinite; }
.bg-orb-2 { bottom: -200px; right: -100px; width: 500px; height: 500px; background: #8b5cf6; animation: orbFloat 12s ease-in-out infinite reverse; }
@keyframes orbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -30px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
}

.scan-line {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(56, 189, 248, 0.008) 2px, rgba(56, 189, 248, 0.008) 4px);
}

.header {
  position: relative; z-index: 2;
  padding: 30px 20px 20px; text-align: center;
}
.header h1 {
  font-size: 28px; font-weight: 800; letter-spacing: -0.5px;
  background: var(--gradient-2);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}

.container { max-width: 900px; margin: 0 auto; padding: 0 16px 40px; position: relative; z-index: 2; }

.toolbar {
  display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap;
}
.btn {
  padding: 10px 18px; border: 1px solid transparent; border-radius: 10px;
  font-size: 13px; cursor: pointer; font-weight: 600; font-family: inherit;
  text-decoration: none; display: inline-block; transition: all 0.3s;
}
.btn-amber { background: rgba(245,158,11,0.15); color: #fbbf24; border-color: rgba(245,158,11,0.3); }
.btn-amber:hover { background: rgba(245,158,11,0.25); box-shadow: 0 0 25px rgba(245,158,11,0.2); }
.btn-accent { background: rgba(56,189,248,0.15); color: #38bdf8; border-color: rgba(56,189,248,0.3); }
.btn-accent:hover { background: rgba(56,189,248,0.25); box-shadow: 0 0 25px rgba(56,189,248,0.2); }

.loading { text-align: center; padding: 60px 20px; }
.loading-spinner {
  width: 48px; height: 48px; margin: 0 auto 16px;
  border: 2px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.report-card {
  background: var(--surface); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 30px; box-shadow: var(--glow);
}

/* Report Content Styles */
.report-card h1 { font-size: 22px; color: #fbbf24; margin-bottom: 8px; border-bottom: 2px solid rgba(245,158,11,0.3); padding-bottom: 12px; }
.report-card h2 { font-size: 18px; color: #38bdf8; margin: 24px 0 12px; padding-left: 12px; border-left: 3px solid #38bdf8; }
.report-card h3 { font-size: 15px; color: #a78bfa; margin: 16px 0 8px; }
.report-card p { font-size: 14px; color: #cbd5e1; line-height: 1.7; margin-bottom: 10px; }
.report-card blockquote { border-left: 3px solid #f59e0b; padding: 8px 16px; margin: 12px 0; background: rgba(245,158,11,0.05); border-radius: 0 8px 8px 0; color: #94a3b8; font-size: 13px; }
.report-card ul, .report-card ol { margin: 8px 0 12px 20px; color: #cbd5e1; font-size: 14px; line-height: 1.7; }
.report-card li { margin-bottom: 4px; }
.report-card a { color: #38bdf8; text-decoration: underline; }
.report-card strong { color: #f87171; }

.empty { text-align: center; padding: 100px 20px; }
.empty .icon { font-size: 64px; margin-bottom: 16px; }
.empty p { color: var(--text-secondary); font-size: 14px; }
</style>
</head>
<body>

<div class="bg-grid"></div>
<div class="bg-orb bg-orb-1"></div>
<div class="bg-orb bg-orb-2"></div>
<div class="scan-line"></div>

<!-- Loading Overlay -->
<div id="loading-overlay" class="loading-overlay show">
  <div class="spinner-ring"></div>
  <div id="loading-msg" class="loading-msg">正在处理...</div>
  <div class="loading-sub">请稍候</div>
  <div class="loading-bar-wrap"><div class="loading-bar-inner"></div></div>
</div>

<div class="header">
  <h1>蒙古国毒品新闻搜集研判系统</h1>
</div>

<div class="container">
  <div class="toolbar">
    <a href="/" class="btn btn-accent">← 返回首页</a>
    <button class="btn btn-amber" onclick="generateReport()">🔄 生成新报告</button>
  </div>

  <div id="loading" class="loading" style="display:none;">
    <div class="loading-spinner"></div>
    <p>正在生成研判报告，AI 正在分析所有涉毒数据，请耐心等待...</p>
  </div>

  {% if report %}
  <div class="report-card">
    {{ report.content|safe }}
  </div>
  {% else %}
  <div class="empty">
    <div class="icon">📋</div>
    <p>暂无研判报告</p>
    <p style="margin-top:8px;">点击 "生成新报告" 按钮，AI 将自动分析所有涉毒数据并生成专业报告</p>
  </div>
  {% endif %}
</div>

<script>
async function generateReport() {
  if (!confirm('生成报告需要 1-3 分钟，AI 将深度分析所有涉毒情报数据，确定继续？')) return;
  document.getElementById('loading').style.display = 'block';
  try {
    const resp = await fetch('/api/generate-report', { method: 'POST' });
    const data = await resp.json();
    if (data.ok) {
      location.href = '/report/' + data.report_id;
    } else {
      alert('生成失败: ' + (data.error || '未知错误'));
      document.getElementById('loading').style.display = 'none';
    }
  } catch (e) {
    alert('请求失败: ' + e.message);
    document.getElementById('loading').style.display = 'none';
  }
}
</script>
</body>
</html>
"""

SETTINGS_PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>系统设置 - 蒙古国毒品新闻搜集研判系统</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
  --bg: #060b14;
  --surface: rgba(15, 23, 42, 0.7);
  --border: rgba(56, 189, 248, 0.12);
  --accent: #38bdf8;
  --accent2: #818cf8;
  --text: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --glow: 0 0 20px rgba(56, 189, 248, 0.15);
  --gradient-1: linear-gradient(135deg, #0ea5e9, #6366f1);
  --gradient-2: linear-gradient(135deg, #06b6d4, #8b5cf6);
  --radius: 12px;
  --radius-lg: 16px;
  --danger: #ef4444;
  --success: #22c55e;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh; overflow-x: hidden;
}

.bg-grid {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 0;
  background-image:
    linear-gradient(rgba(56, 189, 248, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(56, 189, 248, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  animation: gridDrift 20s linear infinite;
}
@keyframes gridDrift {
  0% { background-position: 0 0, 0 0; }
  100% { background-position: 60px 60px, 60px 60px; }
}

.scan-line {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(56, 189, 248, 0.008) 2px, rgba(56, 189, 248, 0.008) 4px);
}

.header {
  position: relative; z-index: 2; padding: 30px 20px 20px; text-align: center;
}
.header h1 {
  font-size: 28px; font-weight: 800; letter-spacing: -0.5px;
  background: var(--gradient-2);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}

.container { max-width: 800px; margin: 0 auto; padding: 0 16px 40px; position: relative; z-index: 2; }

.section {
  background: var(--surface); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border); border-radius: var(--radius-lg);
  padding: 24px; margin-bottom: 20px; box-shadow: var(--glow);
}
.section h2 {
  font-size: 17px; color: var(--accent); margin-bottom: 16px;
  padding-bottom: 10px; border-bottom: 1px solid var(--border);
}

.btn {
  padding: 10px 18px; border: 1px solid transparent; border-radius: 10px;
  font-size: 13px; cursor: pointer; font-weight: 600; font-family: inherit;
  text-decoration: none; display: inline-block; transition: all 0.3s; color: #fff;
}
.btn-accent { background: rgba(56,189,248,0.15); color: #38bdf8; border-color: rgba(56,189,248,0.3); }
.btn-accent:hover { background: rgba(56,189,248,0.25); box-shadow: 0 0 25px rgba(56,189,248,0.2); }
.btn-success { background: rgba(34,197,94,0.15); color: #4ade80; border-color: rgba(34,197,94,0.3); }
.btn-success:hover { background: rgba(34,197,94,0.25); box-shadow: 0 0 25px rgba(34,197,94,0.2); }
.btn-danger { background: rgba(239,68,68,0.15); color: #f87171; border-color: rgba(239,68,68,0.3); }
.btn-danger:hover { background: rgba(239,68,68,0.25); }
.btn-amber { background: rgba(245,158,11,0.15); color: #fbbf24; border-color: rgba(245,158,11,0.3); }
.btn-amber:hover { background: rgba(245,158,11,0.25); }

input, select {
  padding: 10px 14px; background: rgba(15, 23, 42, 0.8); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px;
  font-size: 13px; outline: none; font-family: inherit; transition: all 0.3s;
}
input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(56,189,248,0.1); }
input::placeholder { color: var(--text-muted); }

.form-row { display: flex; gap: 10px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
.form-row input { flex: 1; min-width: 150px; }
.form-row label { font-size: 13px; color: var(--text-secondary); min-width: 60px; }

.email-list { margin-top: 12px; }
.email-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-radius: 10px; margin-bottom: 6px;
  background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border);
}
.email-item .email { font-size: 14px; font-weight: 500; }
.email-item .badge {
  font-size: 10px; padding: 3px 8px; border-radius: 6px; font-weight: 600;
}
.badge-on { background: rgba(34,197,94,0.15); color: #4ade80; }
.badge-off { background: rgba(239,68,68,0.15); color: #f87171; }

.schedule-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border-radius: 10px; margin-bottom: 6px;
  background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border);
}
.schedule-time { font-size: 16px; font-weight: 700; color: var(--accent); }

.msg { padding: 10px 16px; border-radius: 10px; margin: 10px 0; font-size: 13px; display: none; }
.msg-ok { background: rgba(34,197,94,0.1); color: #4ade80; border: 1px solid rgba(34,197,94,0.2); }
.msg-err { background: rgba(239,68,68,0.1); color: #f87171; border: 1px solid rgba(239,68,68,0.2); }

@media (max-width: 640px) {
  .form-row { flex-direction: column; align-items: stretch; }
}
</style>
</head>
<body>

<div class="bg-grid"></div>
<div class="scan-line"></div>

<div class="header">
  <h1>系统设置</h1>
</div>

<div class="container">
  <a href="/" class="btn btn-accent" style="margin-bottom:16px;">← 返回首页</a>

  <!-- Email Recipients -->
  <div class="section">
    <h2>📧 邮件推送接收人</h2>
    <div class="form-row">
      <input type="email" id="new-email" placeholder="输入邮箱地址...">
      <button class="btn btn-success" onclick="addEmail()">添加邮箱</button>
    </div>
    <div class="email-list" id="email-list">
      {% for r in recipients %}
      <div class="email-item">
        <span class="email">{{ r.email }}</span>
        <span class="badge {% if r.enabled %}badge-on{% else %}badge-off{% endif %}">{{ '启用' if r.enabled else '停用' }}</span>
        <button class="btn btn-danger" style="padding:6px 12px;font-size:11px;" onclick="removeEmail('{{ r.email }}')">删除</button>
      </div>
      {% endfor %}
      {% if not recipients %}
      <p style="color:var(--text-muted);font-size:13px;">尚未添加邮箱接收人</p>
      {% endif %}
    </div>
  </div>

  <!-- SMTP Config -->
  <div class="section">
    <h2>🔧 SMTP 邮件服务器配置</h2>
    <div class="form-row">
      <label>服务器</label><input id="smtp-host" placeholder="smtp.gmail.com" value="{{ smtp.host }}">
      <label>端口</label><input id="smtp-port" type="number" placeholder="587" value="{{ smtp.port }}" style="max-width:100px;">
    </div>
    <div class="form-row">
      <label>用户名</label><input id="smtp-user" placeholder="your@gmail.com" value="{{ smtp.username }}">
    </div>
    <div class="form-row">
      <label>密码</label><input id="smtp-pass" type="password" placeholder="应用专用密码" value="{{ smtp.password }}">
      <span style="font-size:10px;color:var(--text-muted);">Gmail 需使用应用专用密码</span>
    </div>
    <div class="form-row">
      <button class="btn btn-accent" onclick="saveSmtp()">保存配置</button>
      <button class="btn btn-success" onclick="testSmtp()">测试连接</button>
      <span id="smtp-msg" class="msg"></span>
    </div>
  </div>

  <!-- Push Schedule -->
  <div class="section">
    <h2>⏰ 推送时间设置</h2>
    <div class="form-row">
      <select id="push-hour">
        {% for h in range(0,24) %}
        <option value="{{ h }}">{{ '%02d' % h }}</option>
        {% endfor %}
      </select>
      <span>:</span>
      <select id="push-minute">
        {% for m in range(0,60,5) %}
        <option value="{{ m }}">{{ '%02d' % m }}</option>
        {% endfor %}
      </select>
      <button class="btn btn-accent" onclick="addSchedule()">添加推送时间</button>
    </div>
    <div id="schedule-list" style="margin-top:12px;">
      {% for s in schedules %}
      <div class="schedule-item">
        <span class="schedule-time">{{ '%02d:%02d' % (s.hour, s.minute) }}</span>
        <span style="font-size:11px;color:var(--text-muted);">每天</span>
        <button class="btn btn-danger" style="padding:6px 12px;font-size:11px;" onclick="deleteSchedule({{ s.id }})">删除</button>
      </div>
      {% endfor %}
      {% if not schedules %}
      <p style="color:var(--text-muted);font-size:13px;">尚未设置推送时间（默认每天早上 9:00）</p>
      {% endif %}
    </div>
    <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border);">
      <button class="btn btn-amber" onclick="sendNow()">📨 立即推送测试</button>
      <span id="send-msg" class="msg"></span>
    </div>
  </div>
</div>

<script>
function showMsg(id, ok, text) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'msg ' + (ok ? 'msg-ok' : 'msg-err');
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 4000);
}

async function addEmail() {
  const email = document.getElementById('new-email').value.trim();
  if (!email) return;
  const resp = await fetch('/api/email/add', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({email})
  });
  const data = await resp.json();
  if (data.ok) location.reload();
  else alert(data.error || '添加失败');
}

async function removeEmail(email) {
  if (!confirm('确定删除 ' + email + ' ?')) return;
  await fetch('/api/email/remove', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({email})
  });
  location.reload();
}

async function saveSmtp() {
  const host = document.getElementById('smtp-host').value.trim();
  const port = parseInt(document.getElementById('smtp-port').value) || 587;
  const username = document.getElementById('smtp-user').value.trim();
  const password = document.getElementById('smtp-pass').value;
  const resp = await fetch('/api/email/smtp', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({host, port, username, password, use_tls: true})
  });
  const data = await resp.json();
  showMsg('smtp-msg', data.ok, data.ok ? '配置已保存' : '保存失败');
}

async function testSmtp() {
  const host = document.getElementById('smtp-host').value.trim();
  const port = parseInt(document.getElementById('smtp-port').value) || 587;
  const username = document.getElementById('smtp-user').value.trim();
  const password = document.getElementById('smtp-pass').value;
  const resp = await fetch('/api/email/test', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({host, port, username, password, use_tls: true})
  });
  const data = await resp.json();
  showMsg('smtp-msg', data.ok, data.message);
}

async function addSchedule() {
  const hour = parseInt(document.getElementById('push-hour').value);
  const minute = parseInt(document.getElementById('push-minute').value);
  await fetch('/api/schedule/add', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({hour, minute})
  });
  location.reload();
}

async function deleteSchedule(id) {
  if (!confirm('确定删除此推送时间？')) return;
  await fetch('/api/schedule/delete', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({id})
  });
  location.reload();
}

async function sendNow() {
  if (!confirm('立即向所有启用的邮箱推送涉毒情报？')) return;
  document.getElementById('send-msg').textContent = '正在发送...';
  document.getElementById('send-msg').className = 'msg';
  document.getElementById('send-msg').style.display = 'block';
  const resp = await fetch('/api/email/send-now', { method: 'POST' });
  const data = await resp.json();
  showMsg('send-msg', data.ok, '发送完成: ' + data.sent + ' 封成功' + (data.errors.length > 0 ? ', ' + data.errors.length + ' 个错误' : ''));
}
</script>
</body>
</html>
"""

SOURCE_COLORS = {
    "police.gov.mn": "rgba(56,189,248,0.15)",
    "nfa.gov.mn": "rgba(251,146,60,0.15)",
    "ncmh.gov.mn": "rgba(34,197,94,0.15)",
    "ikon.mn": "rgba(168,85,247,0.15)",
    "shuum.mn": "rgba(239,68,68,0.15)",
    "odkb-csto.org": "rgba(45,212,191,0.15)",
    "montsame.mn": "rgba(250,204,21,0.15)",
    "unodc.org": "rgba(236,72,153,0.15)",
    "mojha.gov.mn": "rgba(59,130,246,0.15)",
    "nema.gov.mn": "rgba(245,158,11,0.15)",
    "moe.gov.mn": "rgba(99,102,241,0.15)",
    "moh.gov.mn": "rgba(14,165,233,0.15)",
    "prokuror.mn": "rgba(220,38,38,0.15)",
    "gogo.mn": "rgba(16,185,129,0.15)",
    "unuudur.mn": "rgba(249,115,22,0.15)",
    "olloo.mn": "rgba(139,92,246,0.15)",
    "intr.gov.mn": "rgba(2,132,199,0.15)",
}
SOURCE_TEXT_COLORS = {
    "police.gov.mn": "#38bdf8",
    "nfa.gov.mn": "#fb923c",
    "ncmh.gov.mn": "#4ade80",
    "ikon.mn": "#a855f7",
    "shuum.mn": "#f87171",
    "odkb-csto.org": "#2dd4bf",
    "montsame.mn": "#facc15",
    "unodc.org": "#f472b6",
    "mojha.gov.mn": "#60a5fa",
    "nema.gov.mn": "#fbbf24",
    "moe.gov.mn": "#818cf8",
    "moh.gov.mn": "#38bdf8",
    "prokuror.mn": "#fca5a5",
    "gogo.mn": "#34d399",
    "unuudur.mn": "#fdba74",
    "olloo.mn": "#a78bfa",
    "intr.gov.mn": "#38bdf8",
}


def translate_results(results):
    """Batch-translate titles and snippets of results to Chinese (in-place)."""
    if not results:
        return
    # Collect titles and snippets
    texts = []
    for r in results:
        texts.append(r.get("title", ""))
        snippet = r.get("content", "")
        texts.append(snippet[:200] if snippet else "")
    # Batch translate
    translated = batch_translate(texts, max_texts=25)
    # Apply back
    for i, r in enumerate(results):
        r["title"] = translated[i * 2] if i * 2 < len(translated) else r.get("title", "")
        snippet = r.get("content", "")
        if snippet:
            r["content"] = translated[i * 2 + 1] if i * 2 + 1 < len(translated) else snippet[:200]


def _is_within_months(date_str, months=3):
    """Check if a date string is within the given number of months from now.
    Returns False for empty, unparseable, or out-of-range dates."""
    if not date_str:
        return False
    try:
        s = str(date_str)[:10].replace(".", "-").strip()
        # Try multiple date formats
        for fmt in [r"(\d{4})-(\d{2})-(\d{2})", r"(\d{2})-(\d{2})-(\d{4})"]:
            m = re.match(fmt, s)
            if m:
                if fmt.startswith(r"(\d{2})"):
                    y, mo, d = int(m.group(3)), int(m.group(2)), int(m.group(1))
                else:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(y, mo, d)
                cutoff = datetime.now() - timedelta(days=months * 30)
                return dt >= cutoff
        # Also try "DD.MM.YYYY" format
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
        if m:
            dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            cutoff = datetime.now() - timedelta(days=months * 30)
            return dt >= cutoff
        return False  # Unrecognized format, exclude
    except Exception:
        return False


def quick_parse(site, url, session=None):
    """Quick parse for live fetch - extract title, date from an article page."""
    s = session or http_session
    verify = site.get("ssl_verify", True)
    try:
        resp = s.get(url, timeout=15, allow_redirects=True, verify=verify)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    sel = site["article_selectors"]

    title = ""
    if sel.get("title"):
        t = soup.select_one(sel["title"])
        if t:
            title = t.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)
    if not title:
        return None

    date = ""
    text = soup.get_text()
    for fmt, regex, fb in [
        (site["date_format"], sel["date_regex"], sel["date_regex_fallback"])
    ]:
        for p in [regex, fb]:
            if not p:
                continue
            m = re.search(p, text)
            if m:
                d = m.group(1)
                if site["date_format"] == "ymd":
                    date = d
                elif site["date_format"] == "ymd_hms":
                    date = d[:10]
                elif site["date_format"] == "ymd_slash":
                    date = d.replace("/", "-")
                elif site["date_format"] == "dmY_dot":
                    parts = d.split(".")
                    if len(parts) == 3:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif site["date_format"] == "text":
                    try:
                        date = datetime.strptime(d, "%d %B %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        try:
                            date = datetime.strptime(d, "%d %b %Y").strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                break
        if date:
            break

    # Generic fallback: try common date patterns if site-specific ones failed
    if not date:
        for pattern in [
            r"(\d{4}-\d{2}-\d{2})",           # 2026-07-15
            r"(\d{4}\.\d{2}\.\d{2})",          # 2026.07.15
            r"(\d{4}/\d{2}/\d{2})",            # 2026/07/15
            r"(\d{2}\.\d{2}\.\d{4})",           # 15.07.2026
            r"(\d{2}/\d{2}/\d{4})",             # 15/07/2026
            r"(\d{1,2}\s+\w+\s+\d{4})",         # 15 July 2026
        ]:
            m = re.search(pattern, text)
            if m:
                d = m.group(1)
                if "-" in d and d[2] == "-":   # DD-MM-YYYY
                    parts = d.split("-")
                    if len(parts) == 3 and len(parts[0]) == 2:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif "." in d and len(d.split(".")[0]) == 2:  # DD.MM.YYYY
                    parts = d.split(".")
                    if len(parts) == 3:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif "." in d:                  # YYYY.MM.DD
                    date = d.replace(".", "-")
                elif "/" in d and d[2] == "/":  # DD/MM/YYYY
                    parts = d.split("/")
                    if len(parts) == 3 and len(parts[0]) == 2:
                        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
                elif "/" in d:                  # YYYY/MM/DD
                    date = d.replace("/", "-")
                elif " " in d:                  # text date "15 July 2026"
                    try:
                        date = datetime.strptime(d, "%d %B %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        try:
                            date = datetime.strptime(d, "%d %b %Y").strftime("%Y-%m-%d")
                        except ValueError:
                            pass
                else:
                    date = d  # YYYY-MM-DD
                break

    # Mongolian date fallback: "2026 оны 7 дугаар сарын 15" or "2026 оны долдугаар сарын 14"
    if not date:
        mn_months = {
            "нэгдүгээр": "01", "хоёрдугаар": "02", "гуравдугаар": "03",
            "дөрөвдүгээр": "04", "тавдугаар": "05", "зургаадугаар": "06",
            "долдугаар": "07", "долоодугаар": "07", "наймдугаар": "08",
            "есдүгээр": "09", "аравдугаар": "10",
            "арван нэгдүгээр": "11", "арван хоёрдугаар": "12",
        }
        m = re.search(r'(\d{4})\s*оны\s*(\d{1,2})\s*(?:дугаар|дүгээр|-р)\s*сарын\s*(\d{1,2})', text)
        if m:
            date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
        else:
            mn_names = "|".join(mn_months.keys())
            m = re.search(rf'(\d{{4}})\s*оны\s*({mn_names})\s*сарын\s*(\d{{1,2}})', text)
            if m:
                mn = mn_months.get(m.group(2).lower(), "")
                if mn:
                    date = f"{m.group(1)}-{mn}-{m.group(3).zfill(2)}"

    content_parts = []
    if sel.get("content"):
        for p in soup.select(sel["content"]):
            txt = p.get_text(strip=True)
            if txt and len(txt) > 5:
                content_parts.append(txt)

    # Fallback: try finding main content container
    if not content_parts:
        main_content = None
        for container_sel in ["article", ".article-content", ".news-content", ".post-content",
                               ".content", ".entry-content", ".html-body", "#content",
                               ".story-content", ".field-body", ".read-content", "main",
                               "[role='main']", ".post-body", ".detail-content"]:
            main_content = soup.select_one(container_sel)
            if main_content:
                break
        if main_content:
            for p in main_content.find_all("p"):
                txt = p.get_text(strip=True)
                if txt and len(txt) > 20:
                    content_parts.append(txt)

    # Last resort: body p with length filter
    if not content_parts:
        body = soup.find("body")
        if body:
            for p in body.find_all("p"):
                txt = p.get_text(strip=True)
                if len(txt) > 40:
                    content_parts.append(txt)

    # Final fallback: try div tags (some pages use div-based layout)
    if not content_parts:
        body = soup.find("body")
        if body:
            for tag in body.find_all(["div", "section"]):
                if tag.find(["div", "section"]):
                    continue
                txt = tag.get_text(strip=True)
                if len(txt) > 60:
                    content_parts.append(txt)
            if content_parts:
                content_parts.sort(key=len, reverse=True)
                content_parts = content_parts[:5]

    content = "\n".join(content_parts[:10]) if content_parts else title

    return {
        "source": site["name"],
        "source_label": site["label"],
        "title": title,
        "content": content,
        "date": date,
        "category": "",
        "url": url,
    }


def live_fetch_site(site, max_arts=200, months=3):
    """Live fetch from a single site via in-memory crawl engine. No DB."""
    if site.get("requires_js"):
        return [], 0
    try:
        arts, new_count = mc_crawl_site(site, max_articles=max_arts, months=months,
                                        max_seconds=30, max_pages=8)
        arts.sort(key=lambda x: x.get("date") or "0000-00-00", reverse=True)
        return arts, new_count
    except Exception:
        return [], 0


@app.route("/")
def index():
    # Lazy crawl trigger: if last crawl was > interval hours ago, trigger crawl in background
    # This ensures Render free tier wakes up and crawls on first visit after sleep
    last = _auto_crawler["last_crawl"]
    interval_seconds = _auto_crawler["interval_minutes"] * 60
    if last and (datetime.now() - last).total_seconds() > interval_seconds and not _auto_crawler["is_crawling"]:
        print("[懒触发] 距上次爬取超过间隔，后台触发爬取...")
        threading.Thread(target=_trigger_crawl_job, daemon=True).start()

    query = request.args.get("q", "").strip()
    source_filter = request.args.get("source", "").strip()
    action = request.args.get("action", "search")
    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page

    all_sources = SITES
    total_live = 0
    cache_total = get_cache_size()
    progress = min(100, int(cache_total / 500 * 100))

    if action == "live":
        target = [s for s in SITES if s["name"] == source_filter] if source_filter else SITES
        all_results = []
        for site in target:
            arts, n = live_fetch_site(site, max_arts=30)
            all_results.extend(arts)
            total_live += n
        all_results.sort(key=lambda x: x.get("date") or "0000-00-00", reverse=True)
        count = len(all_results)
        results = all_results[offset:offset + per_page]
        cache_total = get_cache_size()  # Refresh
    elif action == "drugs":
        keywords = get_all_keywords()
        sf = source_filter if source_filter else None
        # In-memory drug filter
        all_articles = get_cached_articles(source=sf, months=3)
        scored = []
        for art in all_articles:
            title = art.get("_orig_title") or art.get("title") or ""
            content = art.get("_orig_content") or art.get("content") or ""
            sc, t1, t2, t3, tm = score_article(title, content, art.get("source"))
            if sc >= 4:
                art["drug_score"] = sc
                art["matched_keywords"] = t1 + t2 + t3
                scored.append(art)
        scored.sort(key=lambda x: (-x["drug_score"], x.get("date") or ""))
        count = len(scored)
        results = scored[offset:offset + per_page]
        query = "[毒品新闻筛选]"
    elif action == "global":
        results, count = global_drug_search(max_per_query=10, total_timeout=40)
        results = results[offset:offset + per_page]
        query = "[全球毒品搜索]"
    else:
        sf = source_filter if source_filter else None
        all_articles = get_cached_articles(source=sf, months=3)
        if query:
            qlower = query.lower()
            all_articles = [a for a in all_articles
                          if qlower in (a.get("title") or "").lower()
                          or qlower in (a.get("content") or "").lower()]
        all_articles.sort(key=lambda x: x.get("date") or "0000-00-00", reverse=True)
        count = len(all_articles)
        results = all_articles[offset:offset + per_page]

    # Build stats dict for template compatibility
    cache_sources = get_cache_stats()
    stats = {"total": cache_total, "sources": [{"source_label": k, "cnt": v} for k, v in sorted(cache_sources.items(), key=lambda x: -x[1])]}

    source_colors = SOURCE_COLORS
    source_text_colors = SOURCE_TEXT_COLORS

    if results:
        translate_results(results)

    crawler_status = {
        "running": _auto_crawler["running"],
        "last_crawl": _auto_crawler["last_crawl"],
        "last_count": _auto_crawler["last_crawl_count"],
        "next_crawl": _auto_crawler["next_crawl"],
        "current_site": _auto_crawler["current_site"],
        "interval_h": _auto_crawler["interval_minutes"] / 60,
        "last_push": _auto_crawler["last_push_time"],
        "is_crawling": _auto_crawler["is_crawling"],
    }

    return render_template_string(
        TEMPLATE,
        query=query,
        results=results,
        total_results=count,
        page=page,
        per_page=per_page,
        stats=stats,
        all_sources=all_sources,
        current_source=source_filter,
        source_colors=source_colors,
        source_text_colors=source_text_colors,
        progress=progress,
        loading=False,
        crawler=crawler_status,
        ai_enabled=bool(DEEPSEEK_API_KEY),
    )


@app.route("/api/health")
def api_health():
    """Health check for Render Cron keep-alive + trigger crawl if needed."""
    # Ensure auto-crawler is running (gunicorn doesn't call main())
    if not _auto_crawler["running"]:
        t = threading.Thread(target=_auto_crawl_loop, daemon=True, name="auto-crawler")
        t.start()
    total = get_cache_size()
    return jsonify({
        "ok": True,
        "total_articles": total,
        "crawler_running": _auto_crawler["running"],
        "last_crawl": _auto_crawler["last_crawl"].isoformat() if _auto_crawler["last_crawl"] else None,
        "interval_minutes": _auto_crawler["interval_minutes"],
    })


# ===================== Live Stream (SSE) =====================

@app.route("/api/live-stream")
def api_live_stream():
    """SSE endpoint: pushes cached articles instantly, then crawls for new ones."""
    source_filter = request.args.get("source", "")
    target = [s for s in SITES if s["name"] == source_filter] if source_filter else SITES

    def generate():
        import json as _json
        total = 0
        pushed_urls = set()

        # Phase 1: Push cached articles instantly (within 3 months, by source)
        for site in target:
            if site.get("requires_js"):
                continue
            label = site.get("label", site["name"])
            yield f"event: site_start\ndata: {_json.dumps({'site': label, 'phase': 'cache'})}\n\n"

            cached = get_cached_articles(source=site["name"], months=3)
            site_count = 0
            for art in cached:
                url = art.get("url", "")
                if url in pushed_urls:
                    continue
                pushed_urls.add(url)
                site_count += 1
                total += 1
                art["source_label"] = label
                art["source"] = site["name"]
                art_json = {}
                for k, v in art.items():
                    art_json[k] = v.isoformat() if hasattr(v, "isoformat") else str(v) if v is not None else ""
                yield f"data: {_json.dumps(art_json, ensure_ascii=False)}\n\n"

            yield f"event: site_done\ndata: {_json.dumps({'site': label, 'count': site_count, 'phase': 'cache'})}\n\n"
            time.sleep(0.1)

        # Phase 2: Crawl for new articles
        for site in target:
            if site.get("requires_js"):
                continue
            label = site.get("label", site["name"])
            yield f"event: site_start\ndata: {_json.dumps({'site': label, 'phase': 'crawl'})}\n\n"

            try:
                arts, _ = mc_crawl_site(site, max_articles=60, months=3,
                                        max_seconds=30, max_pages=5)
            except Exception as e:
                yield f"event: site_error\ndata: {_json.dumps({'site': label, 'error': str(e)})}\n\n"
                continue

            site_count = 0
            for art in arts:
                url = art.get("url", "")
                if url in pushed_urls:
                    continue
                pushed_urls.add(url)
                art["source_label"] = label
                art["source"] = site["name"]
                if not _is_within_months(art.get("date"), 3):
                    continue
                site_count += 1
                total += 1
                art_json = {}
                for k, v in art.items():
                    art_json[k] = v.isoformat() if hasattr(v, "isoformat") else str(v) if v is not None else ""
                yield f"data: {_json.dumps(art_json, ensure_ascii=False)}\n\n"
                time.sleep(0.03)

            yield f"event: site_done\ndata: {_json.dumps({'site': label, 'count': site_count, 'phase': 'crawl'})}\n\n"
            time.sleep(0.2)

        yield f"event: done\ndata: {_json.dumps({'total': total})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )



def view_report():
    """Display the latest intelligence report."""
    report = get_latest_report()
    cache_total = get_cache_size()
    cache_sources = get_cache_stats()
    stats = {"total": cache_total, "sources": [{"source_label": k, "cnt": v} for k, v in sorted(cache_sources.items(), key=lambda x: -x[1])]}
    progress = min(100, int(stats.get("total", 0) / 500 * 100))
    return render_template_string(
        REPORT_PAGE,
        report=report,
        stats=stats,
        progress=progress,
    )


@app.route("/report/<int:report_id>")
def view_report_by_id(report_id):
    """Display a specific report by ID."""
    report = get_report_by_id(report_id)
    cache_total = get_cache_size()
    stats = {"total": cache_total, "sources": []}
    progress = min(100, int(cache_total / 500 * 100))
    return render_template_string(
        REPORT_PAGE,
        report=report,
        stats=stats,
        progress=progress,
    )


@app.route("/api/generate-report", methods=["POST"])
def api_generate_report():
    """Generate a new drug intelligence report from in-memory cache."""
    from drug_ai import DrugAnalyzer
    all_articles = get_cached_articles(months=3)
    analyzer = DrugAnalyzer()
    drug_articles = []
    for art in all_articles:
        title = art.get("title") or ""
        content = art.get("content") or ""
        analysis = analyzer.analyze(title, content, art.get("source"))
        if analysis["is_drug"]:
            art["drug_score"] = analysis["score"]
            art["drug_confidence"] = analysis["confidence"]
            art["drug_stage"] = analysis["stage"]
            art["drug_types"] = analysis.get("drug_types", [])
            art["drug_action"] = analysis.get("action", "")
            art["matched_keywords"] = analysis.get("keywords", [])
            drug_articles.append(art)
    drug_articles.sort(key=lambda x: -x.get("drug_score", 0))
    report = generate_intelligence_report(drug_articles)
    save_report(report["title"], report["content"], report["article_count"],
                report["date_start"], report["date_end"])
    saved = get_latest_report()
    return jsonify({"ok": True, "report_id": saved["id"] if saved else None,
                    "article_count": report["article_count"]})


@app.route("/api/report/<int:report_id>")
def api_get_report(report_id):
    """Get report content as JSON."""
    report = get_report_by_id(report_id)
    if report:
        return jsonify({"ok": True, "report": report})
    return jsonify({"ok": False, "error": "报告不存在"})


# ===================== Email Config Routes =====================

@app.route("/api/email/add", methods=["POST"])
def api_email_add():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "无效的邮箱地址"})
    ok = add_email_recipient(email)
    return jsonify({"ok": ok, "error": "" if ok else "邮箱已存在或添加失败"})


@app.route("/api/email/remove", methods=["POST"])
def api_email_remove():
    data = request.get_json()
    email = (data.get("email") or "").strip().lower()
    remove_email_recipient(email)
    return jsonify({"ok": True})


@app.route("/api/email/list")
def api_email_list():
    recipients = get_email_recipients(enabled_only=False)
    return jsonify({"ok": True, "recipients": recipients})


@app.route("/api/email/smtp", methods=["POST"])
def api_email_smtp():
    data = request.get_json()
    save_smtp_config(
        host=data.get("host", "smtp.gmail.com"),
        port=int(data.get("port", 587)),
        username=data.get("username", ""),
        password=data.get("password", ""),
        use_tls=data.get("use_tls", True),
    )
    return jsonify({"ok": True})


@app.route("/api/email/smtp/get")
def api_email_smtp_get():
    config = get_smtp_config()
    # Hide password in response
    config["password"] = "***" if config.get("password") else ""
    return jsonify({"ok": True, "config": config})


@app.route("/api/email/test", methods=["POST"])
def api_email_test():
    data = request.get_json() or {}
    config = {
        "host": data.get("host", ""),
        "port": int(data.get("port", 587)),
        "username": data.get("username", ""),
        "password": data.get("password", ""),
        "use_tls": data.get("use_tls", True),
    }
    if not config["host"] or not config["username"]:
        # Use saved config
        config = get_smtp_config()
    ok, msg = test_smtp_connection(config)
    return jsonify({"ok": ok, "message": msg})


def _trigger_crawl_job():
    """Shared crawl+push job used by both lazy trigger and /api/trigger-crawl."""
    try:
        with _auto_crawler["crawl_lock"]:
            if _auto_crawler["is_crawling"]:
                return
            _auto_crawler["is_crawling"] = True

        from drug_ai import DrugAnalyzer
        analyzer = DrugAnalyzer()
        session = requests.Session()
        session.headers.update(memory_crawler.HEADERS)

        pre_count = get_cache_size()
        total_new = 0

        for site in SITES:
            if site.get("requires_js"):
                continue
            try:
                arts, new_count = mc_crawl_site(site, session, max_articles=200, months=3,
                                                   max_seconds=60, max_pages=20)
                total_new += new_count
            except Exception as e:
                print(f"[触发爬取] {site['label']}: 错误 - {e}")
            time.sleep(0.5)

        _auto_crawler["last_crawl"] = datetime.now()
        _auto_crawler["last_crawl_count"] = total_new
        _auto_crawler["total_new_today"] += total_new
        print(f"[触发爬取] 完成: +{total_new} 篇新文章")

        # Send email after crawl
        print(f"[触发推送] 发送涉毒情报邮件...")
        result = send_drug_intel_email()
        _auto_crawler["last_push_time"] = datetime.now()
        print(f"[触发推送] 完成: {result['sent']} 封成功")

    except Exception as e:
        print(f"[触发爬取] 错误: {e}")
    finally:
        with _auto_crawler["crawl_lock"]:
            _auto_crawler["is_crawling"] = False


@app.route("/api/email/send-now", methods=["POST"])
def api_email_send_now():
    result = send_drug_intel_email(dry_run=False)
    return jsonify({"ok": result["sent"] > 0, "sent": result["sent"], "errors": result["errors"]})


@app.route("/api/trigger-crawl", methods=["POST", "GET"])
def api_trigger_crawl():
    """Manually trigger a crawl + email push. Used by external cron/ping services."""
    last = _auto_crawler["last_crawl"]
    min_interval = _auto_crawler["interval_minutes"] * 60 // 2
    if last and (datetime.now() - last).total_seconds() < min_interval:
        remaining = int(min_interval - (datetime.now() - last).total_seconds())
        return jsonify({"ok": False, "message": f"距离上次爬取不到{remaining // 60}分钟，跳过"})

    if _auto_crawler["is_crawling"]:
        return jsonify({"ok": False, "message": "爬取正在进行中"})

    threading.Thread(target=_trigger_crawl_job, daemon=True).start()
    return jsonify({"ok": True, "message": "爬取已触发，完成后将自动推送邮件"})


@app.route("/api/crawler-status")
def api_crawler_status():
    """Return current crawler status for the frontend."""
    last = _auto_crawler["last_crawl"]
    next_crawl = _auto_crawler["next_crawl"]
    return jsonify({
        "running": _auto_crawler["running"],
        "is_crawling": _auto_crawler["is_crawling"],
        "last_crawl": str(last) if last else None,
        "next_crawl": str(next_crawl) if next_crawl else None,
        "last_count": _auto_crawler["last_crawl_count"],
        "last_push": str(_auto_crawler["last_push_time"]) if _auto_crawler["last_push_time"] else None,
        "interval_hours": _auto_crawler["interval_minutes"] / 60,
        "current_site": _auto_crawler["current_site"],
    })


# ===================== Schedule Routes =====================

@app.route("/api/schedule/list")
def api_schedule_list():
    schedules = get_push_schedules()
    return jsonify({"ok": True, "schedules": schedules})


@app.route("/api/schedule/add", methods=["POST"])
def api_schedule_add():
    data = request.get_json()
    hour = int(data.get("hour", 9))
    minute = int(data.get("minute", 0))
    save_push_schedule(hour, minute)
    return jsonify({"ok": True})


@app.route("/api/schedule/delete", methods=["POST"])
def api_schedule_delete():
    data = request.get_json()
    delete_push_schedule(int(data.get("id", 0)))
    return jsonify({"ok": True})


# ===================== Settings Page =====================

@app.route("/settings")
def settings_page():
    cache_total = get_cache_size()
    cache_sources = get_cache_stats()
    stats = {"total": cache_total, "sources": [{"source_label": k, "cnt": v} for k, v in sorted(cache_sources.items(), key=lambda x: -x[1])]}
    progress = min(100, int(stats.get("total", 0) / 500 * 100))
    recipients = get_email_recipients(enabled_only=False)
    smtp = get_smtp_config()
    schedules = get_push_schedules()
    return render_template_string(
        SETTINGS_PAGE,
        stats=stats,
        progress=progress,
        recipients=recipients,
        smtp=smtp,
        schedules=schedules,
    )


def main():
    import webbrowser

    # Run settings migration from old SQLite DB (idempotent — only if JSON has no real data)
    migrate_from_sqlite()

    # Translate any cached articles that aren't already Chinese (catch-up from previous runs)
    with _cache_lock:
        existing = list(_article_cache.values())
    if existing:
        try:
            n = translate_articles_batch(existing)
            if n > 0:
                print(f"[启动] 已为 {n} 篇缓存文章补翻译为中文")
        except Exception as e:
            print(f"[启动] 补翻译失败: {e}")

    # Start auto-crawler daemon thread
    _start_crawler_thread()
    ai_enabled = bool(DEEPSEEK_API_KEY)
    interval_m = _auto_crawler["interval_minutes"]
    print("=" * 55)
    print("蒙古多源新闻搜索服务器")
    print(f"来源: {len(SITES)} 个站点已配置")
    print(f"DeepSeek AI: {'已启用' if ai_enabled else '未启用 (请设置 DEEPSEEK_API_KEY)'}")
    print(f"自动抓取: 每 {interval_m // 60} 小时 (首次 30 秒后)")
    print(f"邮件推送: 每次爬取完成后自动发送")
    port = int(os.environ.get("PORT", 8765))
    host = "0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1"
    if host == "0.0.0.0":
        print(f"Render 模式: 0.0.0.0:{port}")
    else:
        print("打开 http://127.0.0.1:8765")
    print("=" * 55)
    if host == "127.0.0.1":
        threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
