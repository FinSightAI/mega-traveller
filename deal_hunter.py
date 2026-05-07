import os
"""
Proactive Deal Hunter — ציד עסקאות אקטיבי.
סורק אתרי דילים, מכירות פלאש, טיסות שגיאה, ומחזיר את הזהב.
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
import ai_client

_lang = "he"

DB_PATH = Path(__file__).parent / "prices.db"

# ── Deal sources ───────────────────────────────────────────────────────────────
DEAL_SOURCES = {
    "secretflying":   "https://www.secretflying.com/posts/category/ex-israel/",
    "theflightdeal":  "https://www.theflightdeal.com",
    "elalspecials":   "https://www.elal.com/en/Promotions/Pages/default.aspx",
    "israir":         "https://www.israirairlines.com/en/promotions",
    "arkia":          "https://www.arkia.com/en/deals",
    "ryanair_il":     "https://www.ryanair.com/en/cheap-flights",
    "wizzair_il":     "https://wizzair.com/en-gb/flights/special-offers",
    "kayak_explore":  "https://www.kayak.com/explore/TLV",
}

HUNT_PROMPT = """You are a professional deal hunter. Scan the following websites and find the 5 best deals departing from Israel.

Focus on deals departing from TLV/SDV/ETH.
Look for: unusually low prices, error fares, flash sales, time-limited promotions.

For each deal return:
{
  "origin": "TLV",
  "destination": "city name",
  "destination_code": "XXX",
  "price": 000,
  "currency": "USD",
  "deal_type": "error_fare" / "flash_sale" / "promo" / "regular_cheap",
  "airline": "airline name",
  "dates": "possible dates",
  "urgency": "immediate" / "today" / "this_week",
  "discount_pct": 00,
  "source": "website name",
  "why_amazing": "why this deal is amazing",
  "book_url": "booking URL if known",
  "expires": "when it expires if known"
}

Return JSON array only. Be very accurate — only realistic and current deals."""


def ensure_deals_table():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                origin       TEXT,
                destination  TEXT,
                price        REAL,
                currency     TEXT,
                deal_type    TEXT,
                airline      TEXT,
                dates        TEXT,
                urgency      TEXT,
                discount_pct REAL,
                source       TEXT,
                why_amazing  TEXT,
                book_url     TEXT,
                expires      TEXT,
                score        REAL DEFAULT 0,
                found_at     TEXT NOT NULL,
                seen         INTEGER DEFAULT 0
            )
        """)


def hunt_deals(sources: Optional[list] = None) -> list[dict]:
    """
    Actively hunt for deals from Israeli airports.
    Uses AI with web search to scan deal sites.
    """
    ensure_deals_table()
    if not ai_client.is_configured():
        return [{"error": "missing_api_key", "reason": "GEMINI_API_KEY not configured"}]

    if sources is None:
        sources = list(DEAL_SOURCES.values())[:4]  # Top 4 by default

    sources_str = "\n".join(f"- {url}" for url in sources)
    prompt = f"סרוק את האתרים הבאים:\n{sources_str}\n\n{HUNT_PROMPT}"

    try:
        text = ai_client.ask_with_search(
            prompt=prompt,
            system=(
                "You are an aggressive deal hunter. "
                "Scan every site thoroughly. "
                "Find deals others will miss. "
                "Always look for error fares — these are gold."
                + (" Respond in English. Use English for all text fields in the JSON." if _lang == "en" else "")
            ),
            max_tokens=4096,
        )

        if not text:
            return []

        arr_match = re.search(r"\[.*\]", text, re.DOTALL)
        if not arr_match:
            return []

        deals = json.loads(arr_match.group(0))
        now = datetime.now().isoformat()

        saved = []
        with sqlite3.connect(DB_PATH) as conn:
            for d in deals:
                if not d.get("price") or not d.get("destination"):
                    continue
                score = _score_deal(d)
                d["score"] = score
                d["found_at"] = now
                conn.execute("""
                    INSERT INTO deals
                    (origin, destination, price, currency, deal_type, airline,
                     dates, urgency, discount_pct, source, why_amazing,
                     book_url, expires, score, found_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    d.get("origin", "TLV"),
                    d.get("destination", ""),
                    d.get("price", 0),
                    d.get("currency", "USD"),
                    d.get("deal_type", "promo"),
                    d.get("airline", ""),
                    d.get("dates", ""),
                    d.get("urgency", "this_week"),
                    d.get("discount_pct", 0),
                    d.get("source", ""),
                    d.get("why_amazing", ""),
                    d.get("book_url", ""),
                    d.get("expires", ""),
                    score,
                    now,
                ))
                saved.append(d)

        saved.sort(key=lambda x: x.get("score", 0), reverse=True)
        return saved

    except Exception as e:
        return [{"error": str(e)}]


def get_recent_deals(limit: int = 20, min_score: float = 0) -> list[dict]:
    """Get recently found deals from DB."""
    ensure_deals_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM deals
            WHERE score >= ?
            ORDER BY score DESC, found_at DESC
            LIMIT ?
        """, (min_score, limit)).fetchall()
    return [dict(r) for r in rows]


def get_expiring_deals(hours_ahead: float = 2.0) -> list[dict]:
    """
    Return deals whose 'expires' field is within the next `hours_ahead` hours.
    Deals with 'expires' like 'היום', 'today', 'בעוד שעה', 'in 1 hour' are included.
    """
    ensure_deals_table()
    from datetime import timedelta
    now = datetime.now()
    cutoff = now + timedelta(hours=hours_ahead)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM deals
            WHERE expires IS NOT NULL AND expires != ''
            ORDER BY score DESC
        """).fetchall()

    expiring = []
    for row in rows:
        d = dict(row)
        expires_str = (d.get("expires") or "").lower().strip()
        if not expires_str:
            continue

        # Try to parse ISO datetime
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                exp_dt = datetime.strptime(expires_str[:16], fmt[:len(expires_str[:16])])
                if now <= exp_dt <= cutoff:
                    d["expires_in_minutes"] = int((exp_dt - now).total_seconds() / 60)
                    expiring.append(d)
                break
            except ValueError:
                continue
        else:
            # Fuzzy keywords: "היום", "today", "בעוד שעה", "flash"
            urgent_keywords = ["היום", "today", "בעוד שעה", "in 1 hour", "flash", "עכשיו", "now", "tonight"]
            if any(kw in expires_str for kw in urgent_keywords):
                d["expires_in_minutes"] = 60
                expiring.append(d)

    return expiring


def get_top_deals_today(limit: int = 5) -> list[dict]:
    """Get today's best deals."""
    ensure_deals_table()
    today = datetime.now().strftime("%Y-%m-%d")
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM deals
            WHERE found_at >= ?
            ORDER BY score DESC LIMIT ?
        """, (today, limit)).fetchall()
    return [dict(r) for r in rows]


def _score_deal(deal: dict) -> float:
    """Score a deal 0-10."""
    score = 5.0

    # Deal type bonus
    type_bonus = {
        "error_fare": 3.0,
        "flash_sale": 2.0,
        "promo": 1.0,
        "regular_cheap": 0.0,
    }
    score += type_bonus.get(deal.get("deal_type", ""), 0)

    # Discount bonus
    disc = deal.get("discount_pct", 0)
    if disc >= 50:
        score += 2.0
    elif disc >= 30:
        score += 1.0
    elif disc >= 15:
        score += 0.5

    # Urgency bonus
    urgency_bonus = {"immediate": 1.5, "today": 1.0, "this_week": 0.0}
    score += urgency_bonus.get(deal.get("urgency", ""), 0)

    # Price sanity check
    price = deal.get("price", 999)
    if price < 100:
        score += 1.5  # Suspiciously cheap = likely error fare
    elif price < 200:
        score += 1.0

    return min(10.0, score)
