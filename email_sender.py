"""
Email push system for drug intelligence reports.
Uses SMTP with configurable server settings stored in JSON.
"""
import smtplib
import os
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from settings_store import get_email_recipients, get_smtp_config, get_latest_report
from memory_crawler import get_cached_articles
from drug_keywords import score_article, mentions_mongolia


def _get_drug_articles(limit=30, months=None):
    """In-memory drug article search using keyword scoring."""
    all_articles = get_cached_articles(months=months)
    scored = []
    for art in all_articles:
        title = art.get("_orig_title") or art.get("title", "")
        content = art.get("_orig_content") or art.get("content", "")
        score, t1, t2, t3, title_match = score_article(title, content, art.get("source"))
        if score >= 4 and mentions_mongolia(title, content):
            art = dict(art)
            art["drug_score"] = score
            art["matched_tier1"] = t1
            art["matched_tier2"] = t2
            art["matched_tier3"] = t3
            scored.append(art)
    scored.sort(key=lambda x: x.get("drug_score", 0), reverse=True)
    return scored[:limit], len(scored)


def send_drug_intel_email(dry_run=False):
    """
    Send drug intelligence email to all enabled recipients.
    Includes latest drug-related articles summary + latest report.

    Returns:
        dict with "sent": count, "errors": list of error messages
    """
    config = get_smtp_config()
    if not config.get("host") or not config.get("username"):
        return {"sent": 0, "errors": ["SMTP 未配置 (主机/用户名不能为空)"]}

    recipients = get_email_recipients(enabled_only=True)
    if not recipients:
        return {"sent": 0, "errors": ["没有启用的邮箱接收人"]}

    # Get drug articles
    articles, _ = _get_drug_articles(limit=30, months=None)

    # Get latest report
    report = get_latest_report()

    # Build email content
    html_body = _build_email_html(articles, report)
    subject = f"蒙古毒品情报推送 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    # Send to each recipient
    sent = 0
    errors = []

    for r in recipients:
        try:
            _send_one(config, r["email"], subject, html_body, dry_run)
            sent += 1
        except Exception as e:
            errors.append(f"{r['email']}: {e}")

    return {"sent": sent, "errors": errors}


def _send_via_resend(api_key, to_email, subject, html_body):
    """Send email via Resend HTTP API (works on Render free tier)."""
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Mongolia Drug Intel <noreply@mongolia-drug-intel.onrender.com>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        },
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise Exception(f"Resend API error: {resp.status_code} {resp.text}")


def _send_one(config, to_email, subject, html_body, dry_run=False):
    """Send a single email via SMTP or Resend API."""
    if dry_run:
        print(f"[邮件推送-测试] 收件人: {to_email}, 主题: {subject}")
        return

    # Prefer Resend HTTP API if key is set (works on Render free tier where SMTP is blocked)
    resend_key = os.environ.get("RESEND_API_KEY", "")
    if resend_key:
        _send_via_resend(resend_key, to_email, subject, html_body)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["username"]
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if config.get("use_tls", 1):
        server = smtplib.SMTP(config["host"], config["port"], timeout=30)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=30)

    server.login(config["username"], config["password"])
    server.sendmail(config["username"], [to_email], msg.as_string())
    server.quit()


def _build_email_html(articles, report):
    """Build HTML email body with articles summary and report link."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"></head>
<body style="font-family: 'Segoe UI', Arial, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px;">
<div style="max-width: 700px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 30px; border: 1px solid #334155;">

<h1 style="color: #38bdf8; border-bottom: 2px solid #38bdf8; padding-bottom: 10px; margin-top: 0;">
Mongolia Drug Intelligence 毒品情报推送
</h1>

<p style="color: #94a3b8; font-size: 14px;">推送时间: {now} | 系统自动生成</p>

<hr style="border-color: #334155; margin: 20px 0;">

<h2 style="color: #f87171;">涉毒文章摘要 ({len(articles)} 篇)</h2>
"""

    if articles:
        html += '<table style="width:100%; border-collapse:collapse; font-size:13px;">'
        html += '<tr style="background:#0f172a;"><th style="padding:8px;text-align:left;color:#38bdf8;">来源</th><th style="padding:8px;text-align:left;color:#38bdf8;">标题</th><th style="padding:8px;text-align:left;color:#38bdf8;">日期</th><th style="padding:8px;text-align:left;color:#38bdf8;">评分</th></tr>'
        for a in articles[:20]:
            title = (a.get("title") or "无标题")[:60]
            url = a.get("url", "#")
            src = a.get("source_label", a.get("source", ""))
            date = a.get("date", "")[:10]
            score = a.get("drug_score", 0)
            html += f'<tr style="border-bottom:1px solid #334155;">'
            html += f'<td style="padding:6px;">{src}</td>'
            html += f'<td style="padding:6px;"><a href="{url}" style="color:#e2e8f0;text-decoration:none;">{title}</a></td>'
            html += f'<td style="padding:6px;color:#94a3b8;">{date}</td>'
            html += f'<td style="padding:6px;color:#f87171;font-weight:bold;">{score}</td>'
            html += '</tr>'
        html += '</table>'
    else:
        html += '<p style="color:#94a3b8;">本期无涉毒文章</p>'

    html += '<hr style="border-color: #334155; margin: 20px 0;">'

    if report:
        html += f"""
<h2 style="color: #a78bfa;">最新研判报告</h2>
<p style="font-size:14px;">
报告时间: {report.get('created_at', '')}<br>
涵盖文章: {report.get('article_count', 0)} 篇<br>
<a href="http://127.0.0.1:8765/report/{report['id']}" style="color: #38bdf8;">点击查看完整报告 →</a>
</p>
"""
    else:
        html += '<p style="color:#94a3b8;">暂无研判报告。请登录系统生成。</p>'

    html += """
<hr style="border-color: #334155; margin: 20px 0;">
<p style="font-size:11px; color: #64748b; text-align: center;">
此邮件由 Mongolia Drug Intelligence System 自动发送。<br>
如需取消订阅，请联系系统管理员。
</p>
</div>
</body>
</html>"""
    return html


def send_instant_alert(drug_articles):
    """
    Send instant real-time alert for newly discovered drug articles.
    This is a lightweight, urgent notification — different from daily digest.
    """
    config = get_smtp_config()
    if not config.get("host") or not config.get("username"):
        return {"sent": 0, "errors": ["SMTP 未配置"]}

    recipients = get_email_recipients(enabled_only=True)
    if not recipients:
        return {"sent": 0, "errors": ["没有启用的邮箱接收人"]}

    if not drug_articles:
        return {"sent": 0, "errors": []}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    count = len(drug_articles)
    subject = f"🚨 实时预警: 发现 {count} 篇涉毒新闻 - {now_str}"

    # Build urgent alert HTML
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;">
<div style="max-width:650px;margin:0 auto;background:#1e293b;border-radius:12px;padding:24px;border:2px solid #ef4444;">

<div style="text-align:center;padding:16px;background:rgba(239,68,68,0.1);border-radius:10px;margin-bottom:20px;">
<h1 style="color:#ef4444;margin:0;font-size:22px;">🚨 涉毒新闻实时预警</h1>
<p style="color:#f87171;margin:8px 0 0;">系统自动监测到新的涉毒情报，请立即查阅</p>
<p style="color:#94a3b8;font-size:12px;">发现时间: {now_str} | 本期新增: {count} 篇</p>
</div>

<table style="width:100%;border-collapse:collapse;font-size:13px;">
<tr style="background:#0f172a;">
<th style="padding:10px 8px;text-align:left;color:#38bdf8;border-bottom:2px solid #334155;">来源</th>
<th style="padding:10px 8px;text-align:left;color:#38bdf8;border-bottom:2px solid #334155;">标题</th>
<th style="padding:10px 8px;text-align:left;color:#38bdf8;border-bottom:2px solid #334155;">日期</th>
<th style="padding:10px 8px;text-align:left;color:#38bdf8;border-bottom:2px solid #334155;">评分</th>
</tr>
"""

    for a in drug_articles[:30]:
        title = (a.get("title") or "无标题")[:80]
        url = a.get("url", "#")
        src = a.get("source_label", a.get("source", ""))
        date = (a.get("date") or "")[:10]
        score = a.get("drug_score", 0)
        types = ", ".join(a.get("drug_types", [])[:3])
        html += f"""<tr style="border-bottom:1px solid #334155;">
<td style="padding:8px;">{src}</td>
<td style="padding:8px;"><a href="{url}" style="color:#e2e8f0;text-decoration:none;">{title}</a>
<br><span style="font-size:10px;color:#fbbf24;">{types}</span></td>
<td style="padding:8px;color:#94a3b8;">{date}</td>
<td style="padding:8px;color:#ef4444;font-weight:bold;">{score}分</td>
</tr>"""

    html += """</table>

<hr style="border-color:#334155;margin:20px 0;">
<p style="text-align:center;">
<a href="http://127.0.0.1:8765" style="display:inline-block;padding:12px 28px;background:rgba(239,68,68,0.15);color:#f87171;border:1px solid rgba(239,68,68,0.3);border-radius:10px;text-decoration:none;font-weight:600;">查看全部情报 →</a>
</p>
<p style="font-size:11px;color:#64748b;text-align:center;margin-top:16px;">
此邮件由 Mongolia Drug Intelligence System 实时监控系统自动发送
</p>
</div>
</body>
</html>"""

    sent = 0
    errors = []
    for r in recipients:
        try:
            _send_one(config, r["email"], subject, html)
            sent += 1
        except Exception as e:
            errors.append(f"{r['email']}: {e}")

    return {"sent": sent, "errors": errors}


def test_smtp_connection(config=None):
    """Test SMTP connection and return (ok, message)."""
    if config is None:
        config = get_smtp_config()
    try:
        if config.get("use_tls", 1):
            server = smtplib.SMTP(config["host"], config["port"], timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=15)
        server.login(config["username"], config["password"])
        server.quit()
        return True, "连接成功"
    except Exception as e:
        return False, str(e)
