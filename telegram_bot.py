"""
Telegram Bot Manager — ניהול התראות Telegram חכמות.
שולח התראות פרואקטיביות: ירידת מחיר, דיל חדש, שביתות, שערי חליפין.
"""
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
    """שלח הודעה ל-Telegram."""
    if not token or not chat_id:
        return {"ok": False, "error": "חסרים token או chat_id"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"ok": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def test_connection(token: str, chat_id: str) -> dict:
    """בדוק חיבור ל-Telegram."""
    result = send_message(
        token, chat_id,
        "✅ <b>MegaTraveller מחובר!</b>\n\n"
        "🌍 אני אשלח לך התראות על:\n"
        "• ✈️ ירידות מחיר בטיסות\n"
        "• 🔥 דילים חמים ומבצעים\n"
        "• ⚠️ שביתות ועיכובים\n"
        "• 💱 שינויי שערי חליפין\n"
        "• ⏰ דילים שעומדים לפוג\n\n"
        f"⏱ {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    return result


def format_price_alert(item_name: str, destination: str, old_price: float,
                        new_price: float, currency: str, pct: float) -> str:
    direction = "⬇️" if new_price < old_price else "⬆️"
    emoji = "🔥" if pct < -10 else ("📉" if new_price < old_price else "📈")
    return (
        f"{emoji} <b>עדכון מחיר — {item_name}</b>\n\n"
        f"📍 יעד: {destination}\n"
        f"💰 מחיר חדש: <b>{new_price:,.0f} {currency}</b>\n"
        f"📊 מחיר קודם: {old_price:,.0f} {currency}\n"
        f"{direction} שינוי: <b>{pct:+.1f}%</b>\n\n"
        f"⏱ {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )


def format_deal_alert(deal: dict) -> str:
    score = deal.get("score", 0)
    score_stars = "⭐" * min(int(score / 2), 5)
    urgency_map = {
        "immediate": "🚨 <b>עכשיו</b>",
        "today": "⚡ <b>היום</b>",
        "this_week": "📅 השבוע",
    }
    urgency_text = urgency_map.get(deal.get("urgency", ""), "")
    deal_type_map = {
        "error_fare": "💎 שגיאת מחיר",
        "flash_sale": "⚡ מכירת פלאש",
        "promo": "🏷️ מבצע",
        "regular_cheap": "💰 זול",
    }
    dtype = deal_type_map.get(deal.get("deal_type", ""), "")

    text = (
        f"🎯 <b>דיל חדש נמצא!</b> {score_stars}\n\n"
        f"✈️ {deal.get('origin','TLV')} → <b>{deal.get('destination','')}</b>\n"
        f"💰 <b>{deal.get('price', 0):,.0f} {deal.get('currency','USD')}</b>\n"
        f"🏷️ {dtype}  {urgency_text}\n"
        f"✈️ {deal.get('airline','')}\n"
        f"📅 {deal.get('dates','')}\n\n"
    )

    if deal.get("why_amazing"):
        text += f"💡 {deal['why_amazing']}\n\n"

    if deal.get("book_url"):
        text += f"🔗 <a href=\"{deal['book_url']}\">להזמנה</a>\n"

    if deal.get("expires"):
        text += f"\n⏰ פג תוקף: {deal['expires']}"

    return text


def format_sentiment_alert(origin: str, destination: str, sentiment: dict) -> str:
    impact = sentiment.get("price_impact", "stable")
    emoji = {"rising": "📈", "falling": "📉", "stable": "➡️"}.get(impact, "➡️")
    rec = sentiment.get("recommendation", "")

    text = (
        f"{emoji} <b>התראת שוק — {origin}→{destination}</b>\n\n"
        f"📊 מגמה: {sentiment.get('overall_sentiment','')}\n"
        f"💰 השפעה על מחירים: <b>{impact}</b> ({sentiment.get('impact_pct',0):+.0f}%)\n"
        f"🎯 המלצה: <b>{rec}</b>\n\n"
    )

    events = sentiment.get("key_events", [])[:2]
    if events:
        text += "📰 אירועים רלוונטיים:\n"
        for ev in events:
            text += f"• {ev.get('title','')}\n"

    return text


def format_expiry_alert(deal: dict) -> str:
    minutes = deal.get("expires_in_minutes", 60)
    return (
        f"⏰ <b>דיל עומד לפוג בעוד {minutes} דקות!</b>\n\n"
        f"✈️ {deal.get('origin','TLV')} → <b>{deal.get('destination','')}</b>\n"
        f"💰 <b>{deal.get('price', 0):,.0f} {deal.get('currency','USD')}</b>\n"
        f"✈️ {deal.get('airline','')}\n"
        f"💡 {deal.get('why_amazing','')}\n\n"
        f"⚡ <b>הזמן עכשיו לפני שיפוג!</b>"
    )


def get_bot_info(token: str) -> dict:
    """קבל מידע על הבוט."""
    if not token:
        return {}
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {}


def get_updates(token: str, offset: int = 0) -> list:
    """קבל עדכונים אחרונים (לזיהוי chat_id)."""
    if not token:
        return []
    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data.get("result", [])
    except Exception:
        return []


def extract_chat_id(updates: list) -> str:
    """חלץ chat_id מעדכונים."""
    if not updates:
        return ""
    for update in reversed(updates):
        msg = update.get("message") or update.get("channel_post", {})
        chat = msg.get("chat", {})
        if chat.get("id"):
            return str(chat["id"])
    return ""
