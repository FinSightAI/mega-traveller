"""
Claude-powered price search agent.
Strategy:
  1. Amadeus API (רשמי, מדויק) — לטיסות ומלונות
  2. Claude + web_search (fallback) — לכל השאר / אם Amadeus לא מוגדר
"""
import json
import re
import os
from datetime import datetime
from typing import Optional

import anthropic
import amadeus_client

# ── Claude client ──────────────────────────────────────────────────────────────
_client: Optional[anthropic.Anthropic] = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
    return _client


# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """אתה סוכן מחירי נסיעות מקצועי. תפקידך למצוא את המחירים הטובים ביותר לטיסות, מלונות, דירות וחבילות נופש.

כשמחפשים מחיר:
1. חפש באינטרנט מחירים עדכניים
2. בדוק מספר מקורות (Google Flights, Booking.com, Airbnb, Kayak וכו')
3. מצא את המחיר הטוב ביותר הזמין

תמיד החזר JSON תקני בפורמט:
{
  "found": true/false,
  "price": 123.45,
  "currency": "USD" / "ILS" / "EUR" וכו',
  "source": "שם האתר / מקור",
  "details": "תיאור הדיל - חברת תעופה / מלון / וכו'",
  "deal_quality": "excellent" / "good" / "average" / "poor",
  "notes": "הערות חשובות"
}

אם לא מוצאים מחיר, החזר {"found": false, "reason": "סיבה"}

היה מדויק! מחירים ריאליים בלבד. אל תמציא מחירים."""


def build_search_prompt(item: dict) -> str:
    """Build a search prompt from a watch item."""
    category = item["category"]
    destination = item["destination"]
    origin = item.get("origin", "")
    date_from = item.get("date_from", "")
    date_to = item.get("date_to", "")
    custom_query = item.get("query", "")

    today = datetime.now().strftime("%Y-%m-%d")

    if custom_query:
        base = custom_query
    elif category == "flight":
        base = f"טיסה מ-{origin} ל-{destination}"
        if date_from:
            base += f" בתאריך {date_from}"
        if date_to:
            base += f" חזרה {date_to}"
    elif category == "hotel":
        base = f"מלון ב{destination}"
        if date_from:
            base += f" צ'ק-אין {date_from}"
        if date_to:
            base += f" צ'ק-אאוט {date_to}"
    elif category == "apartment":
        base = f"דירה להשכרה ב{destination}"
        if date_from:
            base += f" מ-{date_from}"
        if date_to:
            base += f" עד {date_to}"
    elif category == "package":
        base = f"חבילת נופש ל{destination}"
        if origin:
            base += f" מ{origin}"
        if date_from:
            base += f" {date_from}"
    else:
        base = f"מחיר {destination}"

    return (
        f"מצא את המחיר הטוב ביותר עבור: {base}\n"
        f"(בדיקה בתאריך: {today})\n\n"
        f"חפש מחירים ריאליים ועדכניים. "
        f"בדוק Google Flights, Booking.com, Airbnb, Kayak, Skyscanner, "
        f"ואתרים ישראלים כמו Gulliver, Israir, Arkia.\n\n"
        f"החזר JSON בפורמט המדויק שהוגדר."
    )


def search_price(item: dict) -> dict:
    """
    Find current price for a watch item.
    Strategy: Amadeus first (accurate) → Claude web search (fallback).
    """
    category = item["category"]
    destination = item["destination"]
    origin = item.get("origin", "TLV")
    date_from = item.get("date_from")
    date_to = item.get("date_to")

    # ── Try Amadeus first ──────────────────────────────────────────────────────
    if amadeus_client.is_configured():
        if category == "flight" and date_from:
            results = amadeus_client.search_flights(
                origin=origin,
                destination=destination,
                departure_date=date_from,
                return_date=date_to,
                max_results=3,
            )
            if results:
                best = results[0]
                best["amadeus"] = True
                return best

        elif category == "hotel" and date_from and date_to:
            results = amadeus_client.search_hotels(
                city=destination,
                check_in=date_from,
                check_out=date_to,
                max_results=3,
            )
            if results:
                best = results[0]
                best["amadeus"] = True
                return best

    # ── Fallback: Claude + web search ─────────────────────────────────────────
    return _claude_web_search(item)


def _claude_web_search(item: dict) -> dict:
    """
    Use Claude Opus 4.6 with web search to find the current price for a watch item.
    Returns a dict with price info or error.
    """
    client = get_client()
    prompt = build_search_prompt(item)
    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the final text response
        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text += block.text

        # Parse JSON from the response
        return _extract_json(result_text)

    except anthropic.RateLimitError:
        return {"found": False, "error": "rate_limit", "reason": "Rate limit"}
    except anthropic.APIError as e:
        return {"found": False, "error": "api_error", "reason": str(e)[:100]}
    except Exception as e:
        return {"found": False, "error": "unknown", "reason": str(e)[:100]}


def _extract_json(text: str) -> dict:
    """Extract JSON object from Claude's response text."""
    # Try to find JSON block
    patterns = [
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
        r"(\{[^{}]*\"found\"[^{}]*\})",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                continue

    # Try to find the last JSON-like object
    try:
        # Find the last { ... } block
        start = text.rfind("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: try to extract price with regex
    price_match = re.search(r"\b(\d{2,6}(?:[.,]\d{1,2})?)\b", text)
    if price_match:
        try:
            price = float(price_match.group(1).replace(",", ""))
            if 10 < price < 100000:
                return {
                    "found": True,
                    "price": price,
                    "currency": "USD",
                    "source": "web search",
                    "details": text[:200],
                    "deal_quality": "unknown",
                    "notes": "",
                }
        except ValueError:
            pass

    return {"found": False, "reason": "Could not parse price from response"}


def analyze_deal(item: dict, price_history: list) -> str:
    """
    Use Claude to analyze whether this is a good deal based on price history.
    """
    client = get_client()

    if len(price_history) < 2:
        return "אין מספיק היסטוריה לניתוח"

    prices = [r["price"] for r in price_history[:20]]
    avg = sum(prices) / len(prices)
    minimum = min(prices)
    maximum = max(prices)
    current = prices[0]

    prompt = f"""נתח האם זה עסקה טובה:
- פריט: {item['name']} ({item['category']}) ל{item['destination']}
- מחיר נוכחי: {current}
- ממוצע (עד 20 מדידות): {avg:.0f}
- מינימום שנראה: {minimum}
- מקסימום שנראה: {maximum}

תן המלצה קצרה (2-3 משפטים) בעברית: האם לקנות עכשיו? למה?"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text.strip()
    except Exception:
        pass

    return f"מחיר נוכחי {current:.0f} לעומת ממוצע {avg:.0f}"


def smart_search_opportunities(destinations: list[str]) -> list[dict]:
    """
    Ask Claude to proactively find good travel deals to a list of destinations.
    Returns a list of opportunity dicts.
    """
    client = get_client()

    dest_str = ", ".join(destinations)
    prompt = f"""מצא 3 הזדמנויות טיול מצוינות עכשיו לאחד מהיעדים הבאים: {dest_str}

חפש:
- טיסות זולות
- מלונות במבצע
- חבילות נופש

לכל הזדמנות החזר JSON:
{{
  "destination": "...",
  "type": "flight/hotel/package",
  "deal": "תיאור הדיל",
  "price": 000,
  "currency": "USD",
  "why_good": "למה זה מצוין עכשיו",
  "urgency": "high/medium/low"
}}

החזר רשימת JSON: [{{}}, {{}}, ...]"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system="אתה מומחה נסיעות שמחפש הזדמנויות מחיר. חפש תמיד מחירים ריאליים.",
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text += block.text

        # Extract JSON array
        arr_match = re.search(r"\[.*\]", result_text, re.DOTALL)
        if arr_match:
            return json.loads(arr_match.group(0))

    except Exception:
        pass

    return []
