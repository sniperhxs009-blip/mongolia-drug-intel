"""
JSON-based settings persistence for email, SMTP, push schedules, and reports.
Replaces db.py's settings-related functions. Thread-safe with file locking.
"""
import json
import os
import threading

_DATA_DIR = "/data" if os.path.isdir("/data") else os.path.dirname(os.path.abspath(__file__))
_SETTINGS_PATH = os.path.join(_DATA_DIR, "settings.json")
_REPORTS_PATH = os.path.join(_DATA_DIR, "reports.json")

_settings_lock = threading.Lock()
_reports_lock = threading.Lock()

_DEFAULT_SETTINGS = {
    "email_recipients": [],
    "smtp_config": {
        "host": "smtp.gmail.com",
        "port": 587,
        "username": "",
        "password": "",
        "use_tls": True,
    },
    "push_schedules": [],
    "_next_schedule_id": 1,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
}


def _read_settings():
    with _settings_lock:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in _DEFAULT_SETTINGS.items():
                    if k not in data:
                        data[k] = v
                return data
        return dict(_DEFAULT_SETTINGS)


def _write_settings(data):
    tmp = _SETTINGS_PATH + ".tmp"
    with _settings_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _SETTINGS_PATH)


def _read_reports():
    with _reports_lock:
        if os.path.exists(_REPORTS_PATH):
            with open(_REPORTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return []


def _write_reports(data):
    tmp = _REPORTS_PATH + ".tmp"
    with _reports_lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _REPORTS_PATH)


# --- Email Recipients ---

def get_email_recipients(enabled_only=True):
    data = _read_settings()
    recips = data.get("email_recipients", [])
    # Merge recipients from EMAIL_RECIPIENTS env var (comma-separated, survives Render sleep)
    env_emails = os.environ.get("EMAIL_RECIPIENTS", "")
    if env_emails:
        for e in env_emails.split(","):
            e = e.strip().lower()
            if e and "@" in e and not any(r["email"] == e for r in recips):
                recips.append({"email": e, "enabled": True})
    if enabled_only:
        return [r for r in recips if r.get("enabled", True)]
    return recips


def add_email_recipient(email):
    data = _read_settings()
    recips = data["email_recipients"]
    if any(r["email"] == email for r in recips):
        return False
    recips.append({"email": email, "enabled": True})
    _write_settings(data)
    return True


def remove_email_recipient(email):
    data = _read_settings()
    before = len(data["email_recipients"])
    data["email_recipients"] = [r for r in data["email_recipients"] if r["email"] != email]
    if len(data["email_recipients"]) != before:
        _write_settings(data)
        return True
    return False


def toggle_email_recipient(email, enabled):
    data = _read_settings()
    for r in data["email_recipients"]:
        if r["email"] == email:
            r["enabled"] = enabled
            _write_settings(data)
            return True
    return False


# --- SMTP Config ---

def get_smtp_config():
    data = _read_settings()
    cfg = dict(data["smtp_config"])
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
    data = _read_settings()
    data["smtp_config"] = {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "use_tls": bool(use_tls),
    }
    _write_settings(data)


# --- Push Schedules ---

def get_push_schedules():
    data = _read_settings()
    return [s for s in data.get("push_schedules", []) if s.get("enabled", True)]


def save_push_schedule(hour, minute, enabled=True):
    data = _read_settings()
    sid = data["_next_schedule_id"]
    data["_next_schedule_id"] += 1
    data["push_schedules"].append({
        "id": sid,
        "hour": int(hour),
        "minute": int(minute),
        "enabled": bool(enabled),
    })
    _write_settings(data)
    return sid


def delete_push_schedule(schedule_id):
    data = _read_settings()
    before = len(data["push_schedules"])
    data["push_schedules"] = [s for s in data["push_schedules"] if s["id"] != int(schedule_id)]
    if len(data["push_schedules"]) != before:
        _write_settings(data)
        return True
    return False


def get_next_push_time():
    from datetime import datetime, timedelta
    schedules = get_push_schedules()
    if not schedules:
        return None
    now = datetime.now()
    for s in sorted(schedules, key=lambda x: (x["hour"], x["minute"])):
        t = now.replace(hour=s["hour"], minute=s["minute"], second=0, microsecond=0)
        if t > now:
            return t
    first = min(schedules, key=lambda x: (x["hour"], x["minute"]))
    t = now.replace(hour=first["hour"], minute=first["minute"], second=0, microsecond=0) + timedelta(days=1)
    return t


# --- Reports ---

def save_report(title, content, article_count, date_range_start, date_range_end):
    from datetime import datetime
    reports = _read_reports()
    rid = 1
    if reports:
        rid = max(r.get("id", 0) for r in reports) + 1
    report = {
        "id": rid,
        "title": title,
        "content": content,
        "article_count": article_count,
        "date_range_start": date_range_start,
        "date_range_end": date_range_end,
        "created_at": datetime.now().isoformat(),
    }
    reports.append(report)
    _write_reports(reports)
    return rid


def get_latest_report():
    reports = _read_reports()
    if not reports:
        return None
    return max(reports, key=lambda r: r.get("id", 0))


def get_report_by_id(report_id):
    reports = _read_reports()
    for r in reports:
        if r.get("id") == int(report_id):
            return r
    return None


# --- Telegram Config ---

def get_telegram_config():
    data = _read_settings()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", data.get("telegram_bot_token", ""))
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", data.get("telegram_chat_id", ""))
    return {"bot_token": token, "chat_id": chat_id}


def save_telegram_config(bot_token, chat_id):
    data = _read_settings()
    data["telegram_bot_token"] = bot_token
    data["telegram_chat_id"] = chat_id
    _write_settings(data)


# --- Migration ---

def migrate_from_sqlite():
    """One-time migration: read settings from old SQLite DB into JSON files."""
    if os.path.exists(_SETTINGS_PATH):
        # Check if settings.json only has defaults (empty email, empty smtp user, no schedules)
        data = _read_settings()
        has_real_data = (
            len(data.get("email_recipients", [])) > 0 or
            data.get("smtp_config", {}).get("username", "") != "" or
            len(data.get("push_schedules", [])) > 0
        )
        if has_real_data:
            return
    base = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base, "police_news.db")
    if not os.path.exists(db_path):
        db_path = os.path.join(base, "police_news.db.archive")
    if not os.path.exists(db_path):
        return
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Migrate email recipients
        rows = conn.execute("SELECT email, enabled FROM email_recipients").fetchall()
        data = _read_settings()
        for r in rows:
            if not any(e["email"] == r["email"] for e in data["email_recipients"]):
                data["email_recipients"].append({"email": r["email"], "enabled": bool(r["enabled"])})

        # Migrate SMTP config
        row = conn.execute("SELECT * FROM smtp_config LIMIT 1").fetchone()
        if row:
            data["smtp_config"] = {
                "host": row["host"] or "smtp.gmail.com",
                "port": int(row["port"] or 587),
                "username": row["username"] or "",
                "password": row["password"] or "",
                "use_tls": bool(row["use_tls"]) if row["use_tls"] is not None else True,
            }

        # Migrate push schedules
        rows = conn.execute("SELECT * FROM push_schedule WHERE enabled=1").fetchall()
        for r in rows:
            data["push_schedules"].append({
                "id": data["_next_schedule_id"],
                "hour": r["hour"],
                "minute": r["minute"],
                "enabled": True,
            })
            data["_next_schedule_id"] += 1

        _write_settings(data)

        # Migrate reports
        rows = conn.execute("SELECT * FROM reports ORDER BY id").fetchall()
        reports = []
        for r in rows:
            reports.append({
                "id": r["id"],
                "title": r["title"],
                "content": r["content"],
                "article_count": r["article_count"],
                "date_range_start": r["date_range_start"],
                "date_range_end": r["date_range_end"],
                "created_at": r["created_at"],
            })
        if reports:
            _write_reports(reports)

        conn.close()
        print("[settings_store] Migrated settings from police_news.db to JSON files")
    except Exception as e:
        print(f"[settings_store] Migration skipped: {e}")
