"""
Price history database using SQLite.
Tracks all price checks and detects drops.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

DB_PATH = Path(__file__).parent / "prices.db"


@dataclass
class WatchItem:
    id: Optional[int]
    name: str
    category: str          # flight / hotel / apartment / package
    query: str             # natural language search query
    destination: str
    origin: Optional[str]  # for flights
    date_from: Optional[str]
    date_to: Optional[str]
    max_price: Optional[float]   # alert if price <= this
    drop_pct: float = 10.0       # alert if drops by this % from last seen
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class PriceRecord:
    id: Optional[int]
    watch_id: int
    price: float
    currency: str
    source: str
    details: str          # JSON with extra info
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS watch_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                category    TEXT NOT NULL,
                query       TEXT NOT NULL,
                destination TEXT NOT NULL,
                origin      TEXT,
                date_from   TEXT,
                date_to     TEXT,
                max_price   REAL,
                drop_pct    REAL DEFAULT 10.0,
                enabled     INTEGER DEFAULT 1,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS price_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id    INTEGER NOT NULL REFERENCES watch_items(id),
                price       REAL NOT NULL,
                currency    TEXT NOT NULL DEFAULT 'USD',
                source      TEXT NOT NULL,
                details     TEXT NOT NULL DEFAULT '{}',
                checked_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_price_watch ON price_records(watch_id, checked_at);

            CREATE TABLE IF NOT EXISTS alert_rules (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL,
                watch_id        INTEGER,
                conditions      TEXT NOT NULL DEFAULT '{}',
                enabled         INTEGER DEFAULT 1,
                last_triggered  TEXT,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (watch_id) REFERENCES watch_items(id)
            );
        """)


def add_watch_item(item: WatchItem) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO watch_items
               (name, category, query, destination, origin, date_from, date_to,
                max_price, drop_pct, enabled, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (item.name, item.category, item.query, item.destination, item.origin,
             item.date_from, item.date_to, item.max_price, item.drop_pct,
             1 if item.enabled else 0, item.created_at)
        )
        return cur.lastrowid


def get_all_watch_items(enabled_only=True) -> list[dict]:
    with get_db() as conn:
        q = "SELECT * FROM watch_items"
        if enabled_only:
            q += " WHERE enabled=1"
        q += " ORDER BY created_at DESC"
        return [dict(row) for row in conn.execute(q).fetchall()]


def delete_watch_item(watch_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM price_records WHERE watch_id=?", (watch_id,))
        conn.execute("DELETE FROM watch_items WHERE id=?", (watch_id,))


def toggle_watch_item(watch_id: int, enabled: bool):
    with get_db() as conn:
        conn.execute("UPDATE watch_items SET enabled=? WHERE id=?",
                     (1 if enabled else 0, watch_id))


def save_price(record: PriceRecord) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO price_records
               (watch_id, price, currency, source, details, checked_at)
               VALUES (?,?,?,?,?,?)""",
            (record.watch_id, record.price, record.currency,
             record.source, record.details, record.checked_at)
        )
        return cur.lastrowid


def get_price_history(watch_id: int, limit=50) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM price_records
               WHERE watch_id=?
               ORDER BY checked_at DESC LIMIT ?""",
            (watch_id, limit)
        ).fetchall()
        return [dict(row) for row in rows]


def get_last_price(watch_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM price_records
               WHERE watch_id=?
               ORDER BY checked_at DESC LIMIT 1""",
            (watch_id,)
        ).fetchone()
        return dict(row) if row else None


def get_lowest_price(watch_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            """SELECT * FROM price_records
               WHERE watch_id=?
               ORDER BY price ASC LIMIT 1""",
            (watch_id,)
        ).fetchone()
        return dict(row) if row else None


def check_price_drop(watch_id: int, new_price: float) -> dict:
    """
    Returns alert info if new_price triggers an alert.
    Checks both max_price threshold and % drop.
    """
    with get_db() as conn:
        item = conn.execute(
            "SELECT * FROM watch_items WHERE id=?", (watch_id,)
        ).fetchone()
        if not item:
            return {"alert": False}

        item = dict(item)
        alerts = []

        # Check max_price threshold
        if item["max_price"] and new_price <= item["max_price"]:
            alerts.append({
                "type": "threshold",
                "message": f"מחיר {new_price:.0f} ≤ יעד {item['max_price']:.0f}!",
            })

        # Check % drop from last seen price
        last = get_last_price(watch_id)
        if last:
            last_price = last["price"]
            if last_price > 0:
                drop_pct = (last_price - new_price) / last_price * 100
                if drop_pct >= item["drop_pct"]:
                    alerts.append({
                        "type": "drop",
                        "message": f"ירידת מחיר {drop_pct:.1f}%! ({last_price:.0f} → {new_price:.0f})",
                        "drop_pct": drop_pct,
                        "last_price": last_price,
                    })

        return {
            "alert": len(alerts) > 0,
            "alerts": alerts,
            "item": item,
            "new_price": new_price,
        }


# ── Alert Rules ────────────────────────────────────────────────────────────────

def add_alert_rule(name: str, conditions: dict, watch_id: Optional[int] = None) -> int:
    """Add a new alert rule. watch_id=None means applies to all items."""
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO alert_rules (name, watch_id, conditions, enabled, created_at)
               VALUES (?,?,?,1,?)""",
            (name, watch_id, json.dumps(conditions, ensure_ascii=False),
             datetime.now().isoformat())
        )
        return cur.lastrowid


def get_alert_rules(watch_id: Optional[int] = None) -> list:
    """Get rules that apply to a specific item or to all items (watch_id=None)."""
    with get_db() as conn:
        if watch_id is not None:
            rows = conn.execute(
                "SELECT * FROM alert_rules WHERE (watch_id=? OR watch_id IS NULL) AND enabled=1 ORDER BY created_at DESC",
                (watch_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alert_rules ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r["conditions"] = json.loads(r.get("conditions") or "{}")
            result.append(r)
        return result


def delete_alert_rule(rule_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))


def toggle_alert_rule(rule_id: int, enabled: bool):
    with get_db() as conn:
        conn.execute("UPDATE alert_rules SET enabled=? WHERE id=?",
                     (1 if enabled else 0, rule_id))


def mark_rule_triggered(rule_id: int):
    with get_db() as conn:
        conn.execute("UPDATE alert_rules SET last_triggered=? WHERE id=?",
                     (datetime.now().isoformat(), rule_id))


def evaluate_alert_rules(watch_id: int, new_price: float, price_result: dict) -> list:
    """
    Evaluate all matching alert rules for a new price.
    Returns list of triggered rules with their match reason.
    price_result: the dict returned by agent.search_price()
    """
    from datetime import datetime as dt
    rules = get_alert_rules(watch_id)
    triggered = []

    for rule in rules:
        cond = rule["conditions"]
        reasons = []

        # 1. Max price threshold
        max_p = cond.get("max_price")
        if max_p and new_price > max_p:
            continue  # price too high for this rule
        if max_p:
            reasons.append(f"מחיר {new_price:.0f} ≤ {max_p:.0f}")

        # 2. Minimum % drop from last price
        min_drop = cond.get("min_drop_pct", 0)
        if min_drop > 0:
            last = get_last_price(watch_id)
            if last:
                drop = (last["price"] - new_price) / last["price"] * 100
                if drop < min_drop:
                    continue
                reasons.append(f"ירידה {drop:.1f}% ≥ {min_drop}%")

        # 3. Days of week (0=Mon, 6=Sun)
        days = cond.get("days_of_week")
        if days:
            today_dow = dt.now().weekday()
            if today_dow not in days:
                continue
            day_names = ["ב׳","ג׳","ד׳","ה׳","ו׳","ש׳","א׳"]
            reasons.append(f"יום {day_names[today_dow]}")

        # 4. Deal quality filter
        min_quality = cond.get("min_deal_quality", "")
        quality_rank = {"excellent": 3, "good": 2, "average": 1, "poor": 0, "": 0}
        result_quality = price_result.get("deal_quality", "")
        if min_quality and quality_rank.get(result_quality, 0) < quality_rank.get(min_quality, 0):
            continue

        # 5. Airline whitelist
        airlines_include = cond.get("airlines_include", [])
        if airlines_include:
            result_airline = price_result.get("airline", "") or price_result.get("details", "")
            if not any(a.lower() in result_airline.lower() for a in airlines_include):
                continue
            reasons.append(f"חברה: {result_airline[:30]}")

        # 6. Airline blacklist
        airlines_exclude = cond.get("airlines_exclude", [])
        if airlines_exclude:
            result_airline = price_result.get("airline", "") or price_result.get("details", "")
            if any(a.lower() in result_airline.lower() for a in airlines_exclude):
                continue

        # 7. Min AI score
        min_score = cond.get("min_ai_score", 0)
        if min_score > 0:
            ai_score = price_result.get("ai_score", 0)
            if ai_score < min_score:
                continue
            reasons.append(f"AI ציון {ai_score:.1f}")

        # Rule matched!
        mark_rule_triggered(rule["id"])
        triggered.append({
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "reasons": reasons,
            "message": f"כלל '{rule['name']}' התממש: " + " | ".join(reasons) if reasons else rule["name"],
        })

    return triggered


def get_price_stats(watch_id: int) -> dict:
    """Return min/max/avg and recent trend for a watch item."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT
                MIN(price) as min_price,
                MAX(price) as max_price,
                AVG(price) as avg_price,
                COUNT(*) as total_checks,
                MIN(checked_at) as first_check,
                MAX(checked_at) as last_check
            FROM price_records WHERE watch_id=?
        """, (watch_id,)).fetchone()
        if not row or not row["total_checks"]:
            return {}
        stats = dict(row)

        # Trend: compare last 3 vs previous 3
        recent = conn.execute("""
            SELECT price FROM price_records WHERE watch_id=?
            ORDER BY checked_at DESC LIMIT 6
        """, (watch_id,)).fetchall()
        prices = [r["price"] for r in recent]
        if len(prices) >= 4:
            avg_recent = sum(prices[:3]) / 3
            avg_prev = sum(prices[3:]) / max(len(prices[3:]), 1)
            stats["trend_pct"] = (avg_recent - avg_prev) / avg_prev * 100 if avg_prev else 0
            stats["trend"] = "rising" if stats["trend_pct"] > 2 else "falling" if stats["trend_pct"] < -2 else "stable"
        else:
            stats["trend_pct"] = 0
            stats["trend"] = "stable"

        return stats
