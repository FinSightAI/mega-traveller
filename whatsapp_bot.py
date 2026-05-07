"""
WhatsApp Bot — בוט ווטסאפ לחיפוש טיסות בשיחה.
מבוסס על Twilio WhatsApp API + Claude AI.
משתמש שולח: "TLV NYC 15/06" → בוט מחפש ומחזיר דילים.
"""
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "prices.db"

COMMANDS = {
    "עזרה": "help",
    "help": "help",
    "היסטוריה": "history",
    "history": "history",
    "מחירים": "watchlist",
    "watchlist": "watchlist",
    "דיל": "deals",
    "deals": "deals",
    "ביטול": "cancel",
    "stop": "cancel",
}

WELCOME_MSG = """✈️ ברוך הבא ל-Noded Bot!

שלח לי:
• *TLV NYC 15/06* — חפש טיסות
• *דיל TLV BKK* — מצא דילים
• *מחירים* — הצג רשימת מעקב
• *עזרה* — הצג עזרה"""

HELP_MSG = """📖 *פקודות זמינות:*

✈️ *חיפוש טיסה:*
`TLV NYC 15/06` — טיסה חד-כיוונית
`TLV NYC 15/06 30/06` — טיסה הלוך-חזור

🔥 *חיפוש דילים:*
`דיל TLV BKK` — דילים למסלול
`דיל ישראל` — דילים מישראל

📊 *ניהול:*
`מחירים` — רשימת מעקב
`היסטוריה` — 5 חיפושים אחרונים

❓ `עזרה` — הצג הודעה זו"""


def ensure_wa_table():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                phone       TEXT NOT NULL,
                direction   TEXT NOT NULL,
                message     TEXT NOT NULL,
                intent      TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_sessions (
                phone       TEXT PRIMARY KEY,
                state       TEXT DEFAULT 'idle',
                context     TEXT DEFAULT '{}',
                updated_at  TEXT NOT NULL
            )
        """)


def log_message(phone: str, direction: str, message: str, intent: str = ""):
    ensure_wa_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO wa_messages (phone, direction, message, intent, created_at)
            VALUES (?,?,?,?,?)
        """, (phone, direction, message, intent, datetime.now().isoformat()))


def get_session(phone: str) -> dict:
    ensure_wa_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM wa_sessions WHERE phone=?", (phone,)
        ).fetchone()
    if row:
        d = dict(row)
        try:
            d["context"] = json.loads(d.get("context", "{}"))
        except Exception:
            d["context"] = {}
        return d
    return {"phone": phone, "state": "idle", "context": {}}


def update_session(phone: str, state: str, context: Optional[dict] = None):
    ensure_wa_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO wa_sessions (phone, state, context, updated_at)
            VALUES (?,?,?,?)
        """, (phone, state, json.dumps(context or {}), datetime.now().isoformat()))


def parse_flight_query(text: str) -> Optional[dict]:
    """
    פרס בקשת טיסה:
    "TLV NYC 15/06" → {origin, dest, date_out}
    "TLV NYC 15/06 30/06" → {origin, dest, date_out, date_return}
    """
    parts = text.upper().split()
    if len(parts) < 3:
        return None

    codes = [p for p in parts if re.match(r'^[A-Z]{3}$', p)]
    dates = re.findall(r'\b(\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?)\b', text)

    if len(codes) < 2 or not dates:
        return None

    origin, dest = codes[0], codes[1]

    year = datetime.now().year

    def parse_date(d: str) -> str:
        parts_d = re.split(r'[/.-]', d)
        if len(parts_d) == 2:
            day, month = parts_d
            return f"{year}-{int(month):02d}-{int(day):02d}"
        elif len(parts_d) == 3:
            day, month, yr = parts_d
            if len(yr) == 2:
                yr = "20" + yr
            return f"{yr}-{int(month):02d}-{int(day):02d}"
        return d

    result = {
        "origin": origin,
        "destination": dest,
        "date_out": parse_date(dates[0]),
    }
    if len(dates) >= 2:
        result["date_return"] = parse_date(dates[1])

    return result


def search_flights_for_wa(query: dict) -> str:
    """חפש טיסות ובנה תגובת WhatsApp."""
    try:
        import kiwi_client
        origin = query["origin"]
        dest = query["destination"]
        date_out = query["date_out"]
        date_return = query.get("date_return", "")

        results = kiwi_client.search_flights(
            origin=origin,
            destination=dest,
            date_from=date_out,
            return_from=date_return,
            limit=5,
        )

        if not results or "error" in results[0]:
            return "❌ לא נמצאו טיסות. נסה תאריך אחר."

        lines = [f"✈️ *{origin} → {dest}*\n_{date_out}_\n"]
        for i, f in enumerate(results[:5], 1):
            price = f.get("price", "?")
            airline = f.get("airline", "")
            stops = f.get("stops", 0)
            dep = f.get("departure", "")[:16]
            dur = f.get("duration_hours", 0)
            stop_txt = "ישיר" if stops == 0 else f"{stops} עצירות"
            lines.append(
                f"{i}. *${price}* — {airline}\n"
                f"   {dep} | {stop_txt} | {dur}ש׳"
            )

        if results and results[0].get("deep_link"):
            lines.append(f"\n🔗 {results[0]['deep_link']}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ שגיאה בחיפוש: {str(e)[:100]}"


def get_deals_for_wa(origin: str = "TLV") -> str:
    """מצא דילים חמים לתצוגת WhatsApp."""
    try:
        import rss_scanner
        deals = rss_scanner.get_unseen_deals(min_score=5.0)
        if not deals:
            deals = rss_scanner.get_recent_rss_deals(limit=5, min_score=4.0)

        if not deals:
            return "🔥 אין דילים חמים כרגע. נסה שוב מאוחר יותר."

        lines = ["🔥 *דילים חמים עכשיו:*\n"]
        for d in deals[:5]:
            title = d.get("title", "")[:60]
            price = d.get("price")
            src = d.get("source", "")
            price_txt = f"${price:.0f}" if price else ""
            lines.append(f"• {title} {price_txt} [{src}]")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ שגיאה: {str(e)[:100]}"


def get_watchlist_for_wa(phone: str) -> str:
    """מצא watch items לפי phone (אם משויך)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            items = conn.execute("""
                SELECT wi.*, ph.price as last_price
                FROM watch_items wi
                LEFT JOIN price_history ph ON ph.watch_id = wi.id
                WHERE ph.id = (
                    SELECT MAX(id) FROM price_history WHERE watch_id = wi.id
                )
                ORDER BY wi.created_at DESC LIMIT 5
            """).fetchall()

        if not items:
            return "📋 רשימת המעקב ריקה.\nהוסף טיסות באפליקציה."

        lines = ["📋 *רשימת המעקב שלך:*\n"]
        for item in items:
            name = item["name"] or f"{item['origin']}→{item['destination']}"
            price = item["last_price"]
            price_txt = f"${price:.0f}" if price else "אין מחיר"
            lines.append(f"• {name}: {price_txt}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ שגיאה: {str(e)[:100]}"


def process_incoming_message(phone: str, message: str) -> str:
    """
    עבד הודעה נכנסת — הלב של הבוט.
    מחזיר תגובה לשלוח למשתמש.
    """
    log_message(phone, "in", message)
    text = message.strip()

    # Check simple commands
    cmd = COMMANDS.get(text.lower(), "")
    if cmd == "help":
        log_message(phone, "out", HELP_MSG, "help")
        return HELP_MSG

    if cmd == "history":
        ensure_wa_table()
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT message FROM wa_messages
                WHERE phone=? AND direction='in' AND intent='flight_search'
                ORDER BY created_at DESC LIMIT 5
            """, (phone,)).fetchall()
        if not rows:
            return "📜 אין היסטוריית חיפושים עדיין."
        lines = ["📜 *5 חיפושים אחרונים:*\n"]
        lines += [f"• {r[0]}" for r in rows]
        reply = "\n".join(lines)
        log_message(phone, "out", reply, "history")
        return reply

    if cmd == "watchlist":
        reply = get_watchlist_for_wa(phone)
        log_message(phone, "out", reply, "watchlist")
        return reply

    # Deal search: "דיל TLV BKK"
    if text.lower().startswith("דיל") or text.lower().startswith("deal"):
        reply = get_deals_for_wa()
        log_message(phone, "out", reply, "deals")
        return reply

    # Flight search: "TLV NYC 15/06"
    query = parse_flight_query(text)
    if query:
        log_message(phone, "in", text, "flight_search")
        reply = search_flights_for_wa(query)
        log_message(phone, "out", reply, "flight_result")
        return reply

    # First message / greeting
    greetings = ["היי", "הי", "שלום", "hello", "hi", "hey", "start", "התחל"]
    if text.lower() in greetings:
        log_message(phone, "out", WELCOME_MSG, "welcome")
        return WELCOME_MSG

    # Fallback
    fallback = (
        "🤷 לא הבנתי.\n\n"
        "נסה:\n"
        "• *TLV NYC 15/06* — חפש טיסה\n"
        "• *דיל* — מצא דילים\n"
        "• *עזרה* — פקודות"
    )
    log_message(phone, "out", fallback, "unknown")
    return fallback


def send_whatsapp_message(to_phone: str, message: str) -> dict:
    """
    שלח הודעת WhatsApp דרך Twilio API.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not account_sid or not auth_token:
        return {"error": "חסרים פרטי Twilio"}

    if not to_phone.startswith("whatsapp:"):
        to_phone = f"whatsapp:{to_phone}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = urllib.parse.urlencode({
        "From": from_number,
        "To": to_phone,
        "Body": message,
    }).encode()

    req = urllib.request.Request(url, data=data, method="POST")
    import base64
    credentials = base64.b64encode(
        f"{account_sid}:{auth_token}".encode()
    ).decode()
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def handle_twilio_webhook(form_data: dict) -> str:
    """
    מעבד webhook מ-Twilio ומחזיר TwiML response.
    form_data = {Body: ..., From: ..., To: ...}
    """
    phone = form_data.get("From", "")
    message = form_data.get("Body", "")

    if not phone or not message:
        return "<Response></Response>"

    reply = process_incoming_message(phone, message)

    # TwiML response
    safe_reply = reply.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{safe_reply}</Message>
</Response>"""


def test_bot(phone: str = "+972501234567") -> list:
    """בדיקת הבוט עם שאלות לדוגמה."""
    test_messages = [
        "היי",
        "TLV NYC 15/06",
        "TLV LON 10/07 20/07",
        "דיל",
        "עזרה",
    ]
    results = []
    for msg in test_messages:
        reply = process_incoming_message(phone, msg)
        results.append({"input": msg, "reply": reply[:200]})
    return results


def get_stats() -> dict:
    """סטטיסטיקות בוט."""
    ensure_wa_table()
    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM wa_messages").fetchone()[0]
        users = conn.execute(
            "SELECT COUNT(DISTINCT phone) FROM wa_messages WHERE direction='in'"
        ).fetchone()[0]
        today = conn.execute("""
            SELECT COUNT(*) FROM wa_messages
            WHERE direction='in' AND date(created_at) = date('now')
        """).fetchone()[0]
        searches = conn.execute("""
            SELECT COUNT(*) FROM wa_messages
            WHERE intent='flight_search'
        """).fetchone()[0]
    return {
        "total_messages": total,
        "unique_users": users,
        "messages_today": today,
        "flight_searches": searches,
    }
