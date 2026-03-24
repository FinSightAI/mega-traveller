"""
AI Trip Planner — תכנון טיול מלא עם Claude.
תקציב, יעד, ימים → תכנית מפורטת עם מחירים.
"""
import json
import re
from datetime import datetime
import anthropic


PLANNER_PROMPT = """אתה מתכנן טיולים מקצועי. תכנן טיול מלא לפי הפרמטרים הבאים.

יעד: {destination}
מוצא: {origin}
תאריכים: {date_from} → {date_to} ({days} ימים)
תקציב כולל: {budget} {currency}
מספר נוסעים: {travelers}
סגנון: {style}
העדפות מיוחדות: {preferences}

צור תכנית טיול מלאה הכוללת:
1. סקירת עלויות (טיסה, מלון, אוכל, פעילויות, תחבורה)
2. תכנית יומית מפורטת
3. המלצות ספציפיות (מסעדות, אטרקציות, שכונות)
4. טיפים לחיסכון
5. זמני ההזמנה הטובים ביותר

חפש מחירים ריאליים עדכניים ובנה תקציב מפורט.

החזר JSON מובנה:
{{
  "summary": "תיאור קצר",
  "total_estimated": 0000,
  "currency": "USD",
  "budget_breakdown": {{
    "flights": 000,
    "hotel": 000,
    "food": 000,
    "activities": 000,
    "transport": 000,
    "other": 000
  }},
  "daily_plan": [
    {{
      "day": 1,
      "date": "YYYY-MM-DD",
      "title": "שם היום",
      "activities": ["פעילות 1", "פעילות 2"],
      "meals": {{"breakfast": "", "lunch": "", "dinner": ""}},
      "accommodation": "שם מלון/דירה",
      "estimated_cost": 000,
      "tips": "טיפ חשוב"
    }}
  ],
  "best_deals": ["דיל 1", "דיל 2", "דיל 3"],
  "booking_advice": "מתי ואיפה להזמין",
  "warnings": ["אזהרה חשובה אם יש"]
}}"""


def plan_trip(
    destination: str,
    origin: str = "תל אביב",
    date_from: str = "",
    date_to: str = "",
    budget: float = 3000,
    currency: str = "USD",
    travelers: int = 2,
    style: str = "מאוזן",          # תקציבי / מאוזן / לוקסוס
    preferences: str = "",
) -> dict:
    """Generate a complete trip plan using Claude."""

    # Calculate days
    days = 7
    if date_from and date_to:
        try:
            d1 = datetime.strptime(date_from, "%Y-%m-%d")
            d2 = datetime.strptime(date_to, "%Y-%m-%d")
            days = (d2 - d1).days
        except ValueError:
            pass

    prompt = PLANNER_PROMPT.format(
        destination=destination,
        origin=origin,
        date_from=date_from or "גמיש",
        date_to=date_to or "גמיש",
        days=days,
        budget=budget,
        currency=currency,
        travelers=travelers,
        style=style,
        preferences=preferences or "אין",
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            system=(
                "אתה מתכנן טיולים מקצועי עם ניסיון של 20 שנה. "
                "תמיד חפש מחירים ריאליים עדכניים לפני שאתה מציע. "
                "היה ספציפי עם שמות מלונות, מסעדות ואטרקציות."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        text = "".join(b.text for b in response.content if b.type == "text")

        # Extract JSON
        patterns = [
            r"```json\s*(\{.*?\})\s*```",
            r"```\s*(\{.*?\})\s*```",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass

        # Try raw JSON
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        # Return raw text if JSON parsing fails
        return {"raw": text, "summary": "תכנית נוצרה — ראה טקסט מלא"}

    except Exception as e:
        return {"error": str(e), "summary": "שגיאה בתכנון"}


def quick_budget_estimate(
    destination: str, days: int, travelers: int, style: str
) -> dict:
    """Quick budget estimate without full planning."""
    style_multiplier = {"תקציבי": 0.6, "מאוזן": 1.0, "לוקסוס": 2.2}.get(style, 1.0)

    # Base daily costs per person (USD) by style
    base_daily = {
        "אירופה": 120, "אסיה": 70, "אמריקה": 150,
        "ים תיכון": 100, "default": 110,
    }

    region_key = "default"
    eu = ["לונדון", "פריז", "ברצלונה", "רומא", "אמסטרדם", "ברלין"]
    asia = ["בנגקוק", "טוקיו", "באלי", "סינגפור"]
    us = ["ניו יורק", "מיאמי", "לוס אנג'לס"]

    for city in eu:
        if city in destination:
            region_key = "אירופה"
            break
    for city in asia:
        if city in destination:
            region_key = "אסיה"
            break
    for city in us:
        if city in destination:
            region_key = "אמריקה"
            break

    daily = base_daily[region_key] * style_multiplier * travelers
    total = daily * days + 400 * travelers  # + flights estimate

    return {
        "estimated_total": round(total),
        "per_day": round(daily),
        "per_person": round(total / travelers),
        "currency": "USD",
        "style": style,
        "includes_flights": True,
    }
