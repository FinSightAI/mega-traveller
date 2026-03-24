"""
Auto-Book Engine — הזמנה אוטומטית כשמחיר מגיע לסף.

שלבים:
  1. הגדר כלל: "אם TLV→BKK < $350 — הזמן!"
  2. המערכת עוקבת ברקע
  3. כשמחיר מגיע לסף — שולחת התראת Telegram + פותחת browser
  4. אישור ב-Telegram → ממשיכה להזמין
  5. (מצב מלא) ממלאת פרטי נוסע + עוצרת לפני תשלום

⚠️ מצב תשלום מלא דורש Playwright + כרטיס אשראי מוגדר.
"""
import json
import os
import sqlite3
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "prices.db"


def ensure_auto_book_table():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_book_rules (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                origin       TEXT,
                destination  TEXT,
                max_price    REAL NOT NULL,
                currency     TEXT DEFAULT 'USD',
                max_stops    INTEGER DEFAULT 1,
                date_from    TEXT,
                date_to      TEXT,
                travelers    INTEGER DEFAULT 1,
                mode         TEXT DEFAULT 'notify',
                enabled      INTEGER DEFAULT 1,
                triggered_at TEXT,
                trigger_count INTEGER DEFAULT 0,
                created_at   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auto_book_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id     INTEGER,
                deal_json   TEXT,
                action      TEXT,
                result      TEXT,
                booked_at   TEXT
            )
        """)


def add_rule(
    name: str,
    origin: str,
    destination: str,
    max_price: float,
    currency: str = "USD",
    max_stops: int = 1,
    date_from: str = "",
    date_to: str = "",
    travelers: int = 1,
    mode: str = "notify",  # notify | open_browser | auto_fill
) -> int:
    ensure_auto_book_table()
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("""
            INSERT INTO auto_book_rules
            (name, origin, destination, max_price, currency, max_stops,
             date_from, date_to, travelers, mode, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (name, origin, destination, max_price, currency, max_stops,
               date_from, date_to, travelers, mode, now))
        return cur.lastrowid


def get_rules(enabled_only: bool = True) -> list:
    ensure_auto_book_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        q = "SELECT * FROM auto_book_rules"
        if enabled_only:
            q += " WHERE enabled=1"
        q += " ORDER BY created_at DESC"
        return [dict(r) for r in conn.execute(q).fetchall()]


def delete_rule(rule_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM auto_book_rules WHERE id=?", (rule_id,))


def toggle_rule(rule_id: int, enabled: bool):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE auto_book_rules SET enabled=? WHERE id=?",
                     (1 if enabled else 0, rule_id))


def check_rules_against_price(
    origin: str,
    destination: str,
    price: float,
    currency: str,
    deal: dict = None,
) -> list:
    """
    בדוק כמה שניות אחרי עדכון מחיר — האם מחיר חדש מפעיל כלל?
    מחזיר רשימת כללים שהופעלו.
    """
    rules = get_rules(enabled_only=True)
    triggered = []
    for rule in rules:
        if rule["origin"].upper() != origin.upper():
            continue
        if rule["destination"].upper() not in (destination.upper(), "*", ""):
            continue
        if price <= rule["max_price"]:
            triggered.append(rule)
    return triggered


def trigger_rule(rule: dict, deal: dict, flight_url: str = ""):
    """
    הפעל כלל — שלח התראה ו/או פתח browser.
    """
    mode = rule.get("mode", "notify")
    now = datetime.now().isoformat()

    # Log
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            UPDATE auto_book_rules
            SET triggered_at=?, trigger_count=trigger_count+1
            WHERE id=?
        """, (now, rule["id"]))
        conn.execute("""
            INSERT INTO auto_book_log (rule_id, deal_json, action, booked_at)
            VALUES (?,?,?,?)
        """, (rule["id"], json.dumps(deal), mode, now))

    # Build message
    price = deal.get("price", rule["max_price"])
    orig = deal.get("origin", rule["origin"])
    dest = deal.get("destination", rule["destination"])
    url = flight_url or deal.get("deep_link", deal.get("book_url", ""))

    msg = (
        f"🚨 AUTO-BOOK ALERT!\n\n"
        f"✈️ {orig} → {dest}\n"
        f"💰 ${price:,.0f} (סף: ${rule['max_price']:,.0f})\n"
        f"⏰ {datetime.now().strftime('%d/%m %H:%M')}\n"
    )
    if url:
        msg += f"\n🔗 {url}"

    # Send Telegram
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        try:
            import telegram_bot
            telegram_bot.send_message(tg_token, tg_chat, msg)
        except Exception:
            pass

    # Open browser
    if mode in ("open_browser", "auto_fill") and url:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    # Auto-fill with Playwright
    if mode == "auto_fill" and url:
        _auto_fill_browser(url, rule, deal)

    return {"triggered": True, "mode": mode, "message": msg}


def _auto_fill_browser(url: str, rule: dict, deal: dict):
    """
    נסה למלא פרטי נוסע אוטומטית עם Playwright.
    עוצר לפני תשלום ושולח screenshot ל-Telegram.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return  # Playwright not installed

    passenger = _get_passenger_config()
    if not passenger:
        return

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, slow_mo=500)
            page = browser.new_page()
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Try to fill common form fields
            _try_fill(page, '[name="firstName"], [name="first_name"], #firstName', passenger.get("first_name", ""))
            _try_fill(page, '[name="lastName"], [name="last_name"], #lastName', passenger.get("last_name", ""))
            _try_fill(page, '[name="email"], #email', passenger.get("email", ""))
            _try_fill(page, '[name="phone"], #phone', passenger.get("phone", ""))

            # Screenshot before payment
            screenshot = page.screenshot(full_page=False)
            _send_screenshot_telegram(screenshot)

            # Keep browser open for manual completion
            page.wait_for_timeout(120000)  # 2 minutes
            browser.close()
    except Exception:
        pass


def _try_fill(page, selector: str, value: str):
    if not value:
        return
    for sel in selector.split(", "):
        try:
            el = page.query_selector(sel.strip())
            if el:
                el.fill(value)
                return
        except Exception:
            pass


def _send_screenshot_telegram(screenshot_bytes: bytes):
    import urllib.request
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
        return
    try:
        import io
        url = f"https://api.telegram.org/bot{tg_token}/sendPhoto"
        boundary = "----FormBoundary"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            f"{tg_chat}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="booking.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + screenshot_bytes + f"\r\n--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _get_passenger_config() -> dict:
    """קרא פרטי נוסע מ-.env"""
    return {
        "first_name": os.environ.get("PASSENGER_FIRST_NAME", ""),
        "last_name": os.environ.get("PASSENGER_LAST_NAME", ""),
        "email": os.environ.get("PASSENGER_EMAIL", ""),
        "phone": os.environ.get("PASSENGER_PHONE", ""),
        "passport": os.environ.get("PASSENGER_PASSPORT", ""),
        "dob": os.environ.get("PASSENGER_DOB", ""),
        "nationality": os.environ.get("PASSENGER_NATIONALITY", "IL"),
    }


def save_passenger_config(data: dict):
    """שמור פרטי נוסע ל-.env"""
    env_path = Path(__file__).parent / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    mapping = {
        "first_name": "PASSENGER_FIRST_NAME",
        "last_name": "PASSENGER_LAST_NAME",
        "email": "PASSENGER_EMAIL",
        "phone": "PASSENGER_PHONE",
        "passport": "PASSENGER_PASSPORT",
        "dob": "PASSENGER_DOB",
        "nationality": "PASSENGER_NATIONALITY",
    }

    for key, env_key in mapping.items():
        if key in data:
            updated = False
            for i, line in enumerate(lines):
                if line.startswith(f"{env_key}="):
                    lines[i] = f"{env_key}={data[key]}"
                    updated = True
                    break
            if not updated:
                lines.append(f"{env_key}={data[key]}")
            os.environ[env_key] = data[key]

    env_path.write_text("\n".join(lines) + "\n")


def get_booking_log(limit: int = 20) -> list:
    ensure_auto_book_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT l.*, r.name as rule_name, r.origin, r.destination, r.max_price
            FROM auto_book_log l
            LEFT JOIN auto_book_rules r ON l.rule_id = r.id
            ORDER BY l.booked_at DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def check_playwright_installed() -> bool:
    try:
        import playwright
        return True
    except ImportError:
        return False
