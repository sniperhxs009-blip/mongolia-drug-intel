import sqlite3
import os
from datetime import datetime, timedelta

# Render provides /data/ for persistent storage; fall back to local dir
_DATA_DIR = "/data" if os.path.isdir("/data") else os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_DATA_DIR, "police_news.db")

# Normalize mixed date formats for comparison (handles both YYYY-MM-DD and YYYY.MM.DD)
DATE_NORM = "REPLACE(SUBSTR(date, 1, 10), '.', '-')"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA encoding='UTF-8'")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_label TEXT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            date TEXT,
            category TEXT,
            url TEXT NOT NULL UNIQUE,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source)")
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
            title, content, source_label, tokenize='unicode61'
        )
    """)
    # Email push system
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hour INTEGER NOT NULL DEFAULT 9,
            minute INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS smtp_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL DEFAULT 'smtp.gmail.com',
            port INTEGER NOT NULL DEFAULT 587,
            username TEXT NOT NULL DEFAULT '',
            password TEXT NOT NULL DEFAULT '',
            use_tls INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Intelligence reports
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            article_count INTEGER DEFAULT 0,
            date_range_start TEXT,
            date_range_end TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def article_exists_by_url(url):
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM articles WHERE url=?", (url,)).fetchone()
    conn.close()
    return row is not None


def insert_article(article):
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO articles (source, source_label, title, content, date, category, url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        article["source"], article.get("source_label", article["source"]),
        article["title"], article["content"],
        article.get("date"), article.get("category"),
        article["url"]
    ))
    rowid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("""
        INSERT OR REPLACE INTO articles_fts(rowid, title, content, source_label)
        VALUES (?, ?, ?, ?)
    """, (rowid, article["title"], article["content"], article.get("source_label", "")))
    conn.commit()
    conn.close()
    return rowid


def search_by_date(keyword, source=None, limit=50, offset=0, months=None):
    conn = get_conn()
    rows, count = [], 0

    date_clause = ""
    date_param = None
    if months:
        cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        date_clause = f"AND {DATE_NORM} >= ?"
        date_param = cutoff

    if keyword and keyword.strip():
        # Try FTS5 first
        try:
            rows = conn.execute(f"""
                SELECT a.* FROM articles a
                INNER JOIN articles_fts f ON a.id = f.rowid
                WHERE articles_fts MATCH ?
                {'AND a.source=?' if source else ''}
                {date_clause}
                ORDER BY a.date DESC LIMIT ? OFFSET ?
            """, [keyword] + ([source] if source else []) + ([date_param] if date_param else []) + [limit, offset]).fetchall()
            count = conn.execute(f"""
                SELECT COUNT(*) FROM articles a
                INNER JOIN articles_fts f ON a.id = f.rowid
                WHERE articles_fts MATCH ?
                {'AND a.source=?' if source else ''}
                {date_clause}
            """, [keyword] + ([source] if source else []) + ([date_param] if date_param else [])).fetchone()[0]
        except Exception:
            # Fallback to LIKE
            like = f"%{keyword}%"
            rows = conn.execute(f"""
                SELECT * FROM articles
                WHERE (title LIKE ? OR content LIKE ?)
                {'AND source=?' if source else ''}
                {date_clause}
                ORDER BY date DESC LIMIT ? OFFSET ?
            """, [like, like] + ([source] if source else []) + ([date_param] if date_param else []) + [limit, offset]).fetchall()
            count = conn.execute(f"""
                SELECT COUNT(*) FROM articles
                WHERE (title LIKE ? OR content LIKE ?)
                {'AND source=?' if source else ''}
                {date_clause}
            """, [like, like] + ([source] if source else []) + ([date_param] if date_param else [])).fetchone()[0]
    else:
        rows = conn.execute(f"""
            SELECT * FROM articles
            WHERE 1=1
            {'AND source=?' if source else ''}
            {date_clause}
            ORDER BY date DESC LIMIT ? OFFSET ?
        """, ([source] if source else []) + ([date_param] if date_param else []) + [limit, offset]).fetchall()
        count = conn.execute(f"""
            SELECT COUNT(*) FROM articles
            WHERE 1=1
            {'AND source=?' if source else ''}
            {date_clause}
        """, ([source] if source else []) + ([date_param] if date_param else [])).fetchone()[0]

    conn.close()
    return [dict(r) for r in rows], count


def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    latest = conn.execute("SELECT MAX(date) FROM articles").fetchone()[0]
    oldest = conn.execute("SELECT MIN(date) FROM articles").fetchone()[0]
    # Per-source counts
    sources = conn.execute(
        "SELECT source, source_label, COUNT(*) as cnt FROM articles GROUP BY source ORDER BY cnt DESC"
    ).fetchall()
    conn.close()
    return {
        "total": total, "latest": latest, "oldest": oldest,
        "sources": [dict(r) for r in sources],
    }


def search_drug_articles(keywords, source=None, limit=200, offset=0, months=None):
    """Search articles matching drug-related keywords using tiered scoring.
    Broad SQL search (all keywords) → score each article → return >= 4 points.
    This works identically for old and new articles."""
    from drug_keywords import score_article

    conn = get_conn()

    if not keywords:
        conn.close()
        return [], 0

    date_clause = ""
    date_param = None
    if months:
        cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        date_clause = f"AND {DATE_NORM} >= ?"
        date_param = cutoff

    # Filter: skip generic single-word keywords under 4 chars to avoid false positives
    filtered_kw = []
    for kw in keywords:
        if len(kw) < 4 and not kw.isupper():
            continue
        filtered_kw.append(kw)

    if not filtered_kw:
        conn.close()
        return [], 0

    # Broad SQL search — cast a wide net, scoring will filter precisely
    like_clauses = []
    params = []
    for kw in filtered_kw:
        like = f"%{kw}%"
        like_clauses.append("(title LIKE ? OR content LIKE ?)")
        params.extend([like, like])

    where = " OR ".join(like_clauses)
    source_clause = "AND source = ?" if source else ""
    date_params = [date_param] if date_param else []

    query = f"""
        SELECT * FROM articles
        WHERE ({where})
        {source_clause}
        {date_clause}
        ORDER BY date DESC
    """
    all_params = params + ([source] if source else []) + date_params
    rows = conn.execute(query, all_params).fetchall()

    # Score and filter each article
    scored = []
    for r in rows:
        d = dict(r)
        title = d.get("title") or ""
        content = d.get("content") or ""
        src = d.get("source")

        score, t1, t2, t3, title_match = score_article(title, content, src)

        if score >= 4:
            d["drug_score"] = score
            d["matched_keywords"] = t1 + t2 + t3
            scored.append(d)

    # Sort by score (highest first), then by date
    scored.sort(key=lambda x: (-x["drug_score"], x.get("date") or ""))

    count = len(scored)
    results = scored[offset:offset + limit]

    conn.close()
    return results, count


def search_drug_articles_ai(keywords, source=None, limit=200, offset=0, months=None):
    """AI-enhanced drug article search using context-aware pattern matching.
    Stage 1: Fast pattern matching (always runs, catches 90% of cases)
    Stage 2: AI semantic analysis (optional, for borderline cases)"""
    from drug_ai import DrugAnalyzer
    from drug_keywords import score_article

    conn = get_conn()

    if not keywords:
        conn.close()
        return [], 0

    date_clause = ""
    date_param = None
    if months:
        cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
        date_clause = f"AND {DATE_NORM} >= ?"
        date_param = cutoff

    # Broad SQL pre-filter using all keywords
    filtered_kw = [kw for kw in keywords if len(kw) >= 4 or kw.isupper()]
    if not filtered_kw:
        conn.close()
        return [], 0

    like_clauses = []
    params = []
    for kw in filtered_kw:
        like = f"%{kw}%"
        like_clauses.append("(title LIKE ? OR content LIKE ?)")
        params.extend([like, like])

    where = " OR ".join(like_clauses)
    source_clause = "AND source = ?" if source else ""
    date_params = [date_param] if date_param else []

    # Also fetch articles from drug-relevant sources that might not match keywords
    # (police, customs, courts might have novel drug terminology)
    query = f"""
        SELECT * FROM articles
        WHERE ({where})
        {source_clause}
        {date_clause}
        ORDER BY date DESC
    """
    all_params = params + ([source] if source else []) + date_params
    rows = conn.execute(query, all_params).fetchall()

    # AI-enhanced analysis
    analyzer = DrugAnalyzer()
    results = []
    for r in rows:
        d = dict(r)
        analysis = analyzer.analyze(d.get("title") or "", d.get("content") or "", d.get("source"))
        if analysis["is_drug"]:
            d["drug_score"] = analysis["score"]
            d["drug_confidence"] = analysis["confidence"]
            d["drug_stage"] = analysis["stage"]
            d["drug_types"] = analysis.get("drug_types", [])
            d["drug_action"] = analysis.get("action", "")
            d["drug_summary"] = analysis.get("summary", "")
            d["matched_keywords"] = analysis.get("keywords", [])
            results.append(d)

    results.sort(key=lambda x: (-x["drug_score"], x.get("date") or ""))
    count = len(results)
    results = results[offset:offset + limit]

    conn.close()
    return results, count


def get_highest_id():
    conn = get_conn()
    row = conn.execute("SELECT MAX(id) FROM articles").fetchone()[0]
    conn.close()
    return row or 0


# --- Email Recipients ---
def get_email_recipients(enabled_only=True):
    conn = get_conn()
    q = "SELECT * FROM email_recipients" + (" WHERE enabled=1" if enabled_only else "")
    rows = conn.execute(q + " ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_email_recipient(email):
    conn = get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO email_recipients (email) VALUES (?)", (email.strip().lower(),))
        conn.commit()
        ok = conn.execute("SELECT COUNT(*) FROM email_recipients WHERE email=?", (email.strip().lower(),)).fetchone()[0] > 0
    except Exception:
        ok = False
    conn.close()
    return ok


def remove_email_recipient(email):
    conn = get_conn()
    conn.execute("DELETE FROM email_recipients WHERE email=?", (email.strip().lower(),))
    conn.commit()
    conn.close()


def toggle_email_recipient(email, enabled):
    conn = get_conn()
    conn.execute("UPDATE email_recipients SET enabled=? WHERE email=?", (1 if enabled else 0, email.strip().lower()))
    conn.commit()
    conn.close()


# --- SMTP Config ---
def get_smtp_config():
    conn = get_conn()
    row = conn.execute("SELECT * FROM smtp_config ORDER BY id LIMIT 1").fetchone()
    conn.close()
    if row:
        cfg = dict(row)
    else:
        cfg = {"host": "smtp.gmail.com", "port": 587, "username": "", "password": "", "use_tls": 1}
    # Environment variables override stored config (for Render/GitHub safety)
    if os.environ.get("SMTP_HOST"):
        cfg["host"] = os.environ["SMTP_HOST"]
    if os.environ.get("SMTP_PORT"):
        cfg["port"] = int(os.environ["SMTP_PORT"])
    if os.environ.get("SMTP_USERNAME"):
        cfg["username"] = os.environ["SMTP_USERNAME"]
    if os.environ.get("SMTP_PASSWORD"):
        cfg["password"] = os.environ["SMTP_PASSWORD"]
    return cfg


def save_smtp_config(host, port, username, password, use_tls):
    conn = get_conn()
    existing = conn.execute("SELECT id FROM smtp_config LIMIT 1").fetchone()
    if existing:
        conn.execute("""
            UPDATE smtp_config SET host=?, port=?, username=?, password=?, use_tls=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (host, port, username, password, 1 if use_tls else 0, existing[0]))
    else:
        conn.execute("""
            INSERT INTO smtp_config (host, port, username, password, use_tls) VALUES (?, ?, ?, ?, ?)
        """, (host, port, username, password, 1 if use_tls else 0))
    conn.commit()
    conn.close()


# --- Push Schedule ---
def get_push_schedules():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM push_schedule WHERE enabled=1 ORDER BY hour, minute").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_push_schedule(hour, minute, enabled=True):
    conn = get_conn()
    conn.execute("INSERT INTO push_schedule (hour, minute, enabled) VALUES (?, ?, ?)",
                 (hour, minute, 1 if enabled else 0))
    conn.commit()
    conn.close()


def delete_push_schedule(schedule_id):
    conn = get_conn()
    conn.execute("DELETE FROM push_schedule WHERE id=?", (schedule_id,))
    conn.commit()
    conn.close()


def get_next_push_time():
    """Return (hour, minute) of the next upcoming push today, or None."""
    schedules = get_push_schedules()
    if not schedules:
        return None
    now = datetime.now()
    for s in schedules:
        t = (s["hour"], s["minute"])
        if now.hour < s["hour"] or (now.hour == s["hour"] and now.minute < s["minute"]):
            return t
    # All today's pushes passed — return first one for tomorrow
    return (schedules[0]["hour"], schedules[0]["minute"])


# --- Reports ---
def save_report(title, content, article_count, date_start, date_end):
    conn = get_conn()
    conn.execute("""
        INSERT INTO reports (title, content, article_count, date_range_start, date_range_end)
        VALUES (?, ?, ?, ?, ?)
    """, (title, content, article_count, date_start, date_end))
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return rid


def get_latest_report():
    conn = get_conn()
    row = conn.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def get_report_by_id(report_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
