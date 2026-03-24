"""
Unified notification hub.
Channels: WhatsApp (Twilio), Email (SMTP), Discord (Webhook), Telegram, ntfy.sh, Desktop.
"""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import httpx

logger = logging.getLogger(__name__)


# ── WhatsApp via Twilio ────────────────────────────────────────────────────────

def send_whatsapp(title: str, message: str) -> bool:
    sid   = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_ = os.environ.get("TWILIO_WHATSAPP_FROM", "")   # whatsapp:+14155238886
    to    = os.environ.get("WHATSAPP_TO", "")             # whatsapp:+972501234567

    if not all([sid, token, from_, to]):
        return False
    try:
        from twilio.rest import Client
        client = Client(sid, token)
        body = f"*{title}*\n{message}"
        client.messages.create(body=body, from_=from_, to=to)
        return True
    except Exception as e:
        logger.warning(f"WhatsApp failed: {e}")
        return False


# ── Email via SMTP ─────────────────────────────────────────────────────────────

def send_email(title: str, message: str) -> bool:
    host     = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port     = int(os.environ.get("SMTP_PORT", "587"))
    user     = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    to       = os.environ.get("ALERT_EMAIL", "")

    if not all([user, password, to]):
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"]    = user
        msg["To"]      = to

        html = f"""
        <div dir="rtl" style="font-family:Arial;max-width:500px;margin:auto;
             background:#1a1a2e;color:#eee;padding:24px;border-radius:12px;">
          <h2 style="color:#00d4ff">✈️ MegaTraveller</h2>
          <h3>{title}</h3>
          <p style="font-size:16px">{message.replace(chr(10),'<br>')}</p>
          <hr style="border-color:#333">
          <small style="color:#888">MegaTraveller Price Monitor</small>
        </div>"""

        msg.attach(MIMEText(message, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(user, to, msg.as_string())
        return True
    except Exception as e:
        logger.warning(f"Email failed: {e}")
        return False


# ── Discord Webhook ────────────────────────────────────────────────────────────

def send_discord(title: str, message: str) -> bool:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        return False
    try:
        payload = {
            "embeds": [{
                "title": title,
                "description": message,
                "color": 0x00d4ff,
                "footer": {"text": "MegaTraveller 🌍"},
            }]
        }
        r = httpx.post(webhook, json=payload, timeout=10)
        return r.status_code in (200, 204)
    except Exception as e:
        logger.warning(f"Discord failed: {e}")
        return False


# ── Telegram ───────────────────────────────────────────────────────────────────

def send_telegram(title: str, message: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False
    try:
        text = f"*{title}*\n{message}"
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"Telegram failed: {e}")
        return False


# ── ntfy.sh ────────────────────────────────────────────────────────────────────

def send_ntfy(title: str, message: str, priority: str = "high") -> bool:
    topic  = os.environ.get("NTFY_TOPIC", "")
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
    if not topic:
        return False
    try:
        r = httpx.post(
            f"{server}/{topic}",
            content=message.encode("utf-8"),
            headers={
                "Title":    title,
                "Priority": priority,
                "Tags":     "money_with_wings,airplane",
            },
            timeout=10,
        )
        return r.status_code == 200
    except Exception as e:
        logger.warning(f"ntfy failed: {e}")
        return False


# ── Desktop ────────────────────────────────────────────────────────────────────

def send_desktop(title: str, message: str) -> bool:
    try:
        from plyer import notification
        notification.notify(title=title, message=message,
                            app_name="MegaTraveller ✈️", timeout=10)
        return True
    except Exception:
        return False


# ── Send to ALL configured channels ───────────────────────────────────────────

def broadcast(title: str, message: str) -> dict[str, bool]:
    """Send to every configured channel. Returns {channel: success}."""
    results = {}
    results["desktop"]   = send_desktop(title, message)
    results["ntfy"]      = send_ntfy(title, message)
    results["telegram"]  = send_telegram(title, message)
    results["whatsapp"]  = send_whatsapp(title, message)
    results["email"]     = send_email(title, message)
    results["discord"]   = send_discord(title, message)
    return results


def test_all() -> dict[str, str]:
    """Send test message to all channels. Returns {channel: status_str}."""
    title = "✈️ MegaTraveller — בדיקת התראות"
    msg   = "ההתראות עובדות! 🎉\nתכונה זו תישלח בכל פעם שמחיר יורד."
    raw   = broadcast(title, msg)

    configured = {
        "desktop":  True,
        "ntfy":     bool(os.environ.get("NTFY_TOPIC")),
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "whatsapp": bool(os.environ.get("TWILIO_ACCOUNT_SID")),
        "email":    bool(os.environ.get("SMTP_USER")),
        "discord":  bool(os.environ.get("DISCORD_WEBHOOK_URL")),
    }

    status = {}
    for ch, ok in raw.items():
        if not configured[ch]:
            status[ch] = "⚠️ לא מוגדר"
        elif ok:
            status[ch] = "✅ נשלח"
        else:
            status[ch] = "❌ שגיאה"
    return status
