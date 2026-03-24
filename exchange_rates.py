"""
Exchange rate monitor — שערי חליפין ועדכונים.
משתמש ב-Open Exchange Rates API (חינמי) + התראה כשהשקל חזק.
"""
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
import httpx

DB_PATH = Path(__file__).parent / "prices.db"

# Free API — no key required for basic rates
FREE_RATE_URL = "https://open.er-api.com/v6/latest/{base}"

# With API key (openexchangerates.org — free plan)
PAID_RATE_URL = "https://openexchangerates.org/api/latest.json"


def ensure_table():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_rates (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                base       TEXT NOT NULL,
                target     TEXT NOT NULL,
                rate       REAL NOT NULL,
                checked_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                base        TEXT NOT NULL,
                target      TEXT NOT NULL,
                threshold   REAL NOT NULL,
                direction   TEXT NOT NULL,
                enabled     INTEGER DEFAULT 1,
                created_at  TEXT NOT NULL
            )
        """)


def fetch_rates(base: str = "USD") -> dict[str, float]:
    """Fetch current exchange rates. Returns {currency: rate}."""
    api_key = os.environ.get("OPENEXCHANGERATES_KEY", "")

    try:
        if api_key:
            r = httpx.get(
                PAID_RATE_URL,
                params={"app_id": api_key, "base": base},
                timeout=10,
            )
            data = r.json()
            return data.get("rates", {})
        else:
            r = httpx.get(FREE_RATE_URL.format(base=base), timeout=10)
            data = r.json()
            return data.get("rates", {})
    except Exception:
        return {}


def get_rate(base: str, target: str) -> float | None:
    """Get current rate between two currencies."""
    rates = fetch_rates(base)
    return rates.get(target)


def save_rate(base: str, target: str, rate: float):
    ensure_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO exchange_rates (base, target, rate, checked_at) VALUES (?,?,?,?)",
            (base, target, rate, datetime.now().isoformat())
        )


def get_rate_history(base: str, target: str, limit: int = 30) -> list[dict]:
    ensure_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM exchange_rates
               WHERE base=? AND target=?
               ORDER BY checked_at DESC LIMIT ?""",
            (base, target, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def add_rate_alert(base: str, target: str, threshold: float, direction: str):
    """
    direction: "above" (התראה כשמעל) | "below" (התראה כשמתחת)
    """
    ensure_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO rate_alerts (base, target, threshold, direction, created_at)
               VALUES (?,?,?,?,?)""",
            (base, target, threshold, direction, datetime.now().isoformat())
        )


def check_rate_alerts() -> list[dict]:
    """Check all active rate alerts. Returns triggered ones."""
    ensure_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        alerts = conn.execute(
            "SELECT * FROM rate_alerts WHERE enabled=1"
        ).fetchall()

    triggered = []
    for alert in alerts:
        alert = dict(alert)
        rate = get_rate(alert["base"], alert["target"])
        if rate is None:
            continue

        fired = (
            (alert["direction"] == "below" and rate <= alert["threshold"]) or
            (alert["direction"] == "above" and rate >= alert["threshold"])
        )
        if fired:
            triggered.append({
                **alert,
                "current_rate": rate,
                "message": (
                    f"שער {alert['base']}/{alert['target']}: "
                    f"{rate:.4f} "
                    f"({'מתחת' if alert['direction']=='below' else 'מעל'} "
                    f"ל-{alert['threshold']:.4f})"
                ),
            })
            save_rate(alert["base"], alert["target"], rate)

    return triggered


POPULAR_PAIRS = [
    ("USD", "ILS", "דולר → שקל"),
    ("EUR", "ILS", "יורו → שקל"),
    ("GBP", "ILS", "פאונד → שקל"),
    ("USD", "EUR", "דולר → יורו"),
    ("USD", "THB", "דולר → בהט (תאילנד)"),
]
