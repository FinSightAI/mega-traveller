"""
AI Trip Planner — powered by Gemini with Google Search.
"""
import re
import json
from datetime import datetime

import ai_client

_lang = "he"

PLANNER_PROMPT = """You are a professional trip planner. Plan a complete trip based on the following parameters.

Destination: {destination}
Origin: {origin}
Dates: {date_from} → {date_to} ({days} days)
Total budget: {budget} {currency}
Number of travelers: {travelers}
Style: {style}
Special preferences: {preferences}

Create a complete trip plan including:
1. Cost overview (flight, hotel, food, activities, transport)
2. Detailed daily itinerary
3. Specific recommendations (restaurants, attractions, neighborhoods)
4. Money-saving tips
5. Best booking times

Search for realistic current prices and build a detailed budget.

Return structured JSON:
{{
  "summary": "brief description",
  "total_estimated": 0000,
  "currency": "USD",
  "budget_breakdown": {{
    "flights": 000, "hotel": 000, "food": 000,
    "activities": 000, "transport": 000, "other": 000
  }},
  "daily_plan": [
    {{
      "day": 1, "date": "YYYY-MM-DD", "title": "day name",
      "activities": ["activity 1", "activity 2"],
      "meals": {{"breakfast": "", "lunch": "", "dinner": ""}},
      "accommodation": "hotel/apartment name",
      "estimated_cost": 000, "tips": "important tip"
    }}
  ],
  "best_deals": ["deal 1", "deal 2", "deal 3"],
  "booking_advice": "when and where to book",
  "warnings": ["important warning if any"]
}}"""


def plan_trip(
    destination: str,
    origin: str = "Tel Aviv",
    date_from: str = "",
    date_to: str = "",
    budget: float = 3000,
    currency: str = "USD",
    travelers: int = 2,
    style: str = "Balanced",
    preferences: str = "",
) -> dict:
    """Generate a complete trip plan using Gemini."""
    if not ai_client.is_configured():
        return {"error": "missing_api_key", "reason": "GEMINI_API_KEY not configured"}

    days = 7
    if date_from and date_to:
        try:
            d1 = datetime.strptime(date_from, "%Y-%m-%d")
            d2 = datetime.strptime(date_to, "%Y-%m-%d")
            days = (d2 - d1).days
        except ValueError:
            pass

    flex = "Flexible" if _lang == "en" else "גמיש"
    none_str = "None" if _lang == "en" else "אין"

    prompt = PLANNER_PROMPT.format(
        destination=destination, origin=origin,
        date_from=date_from or flex, date_to=date_to or flex,
        days=days, budget=budget, currency=currency,
        travelers=travelers, style=style,
        preferences=preferences or none_str,
    )
    if _lang == "en":
        prompt += "\n\nRespond in English."

    system = (
        "You are a professional trip planner with 20 years of experience. "
        "Always search for realistic, current prices before suggesting. "
        "Be specific with hotel names, restaurants and attractions."
        + (" Respond in English." if _lang == "en" else "")
    )

    text = ai_client.ask_with_search(prompt=prompt, system=system, max_tokens=4096)
    if not text:
        return {"error": "no_response", "summary": "Planning error" if _lang == "en" else "שגיאה בתכנון"}

    # Try JSON extraction
    for pattern in [r"```json\s*(\{.*?\})\s*```", r"```\s*(\{.*?\})\s*```"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return {"raw": text, "summary": "Plan created — see full text" if _lang == "en" else "תכנית נוצרה — ראה טקסט מלא"}


def quick_budget_estimate(destination: str, days: int, travelers: int, style: str) -> dict:
    """Quick budget estimate without full planning."""
    style_multiplier = {"תקציבי": 0.6, "מאוזן": 1.0, "לוקסוס": 2.2}.get(style, 1.0)
    base_daily = {"אירופה": 120, "אסיה": 70, "אמריקה": 150, "ים תיכון": 100, "default": 110}

    region_key = "default"
    for city in ["לונדון", "פריז", "ברצלונה", "רומא", "אמסטרדם", "ברלין"]:
        if city in destination:
            region_key = "אירופה"; break
    for city in ["בנגקוק", "טוקיו", "באלי", "סינגפור"]:
        if city in destination:
            region_key = "אסיה"; break
    for city in ["ניו יורק", "מיאמי", "לוס אנג'לס"]:
        if city in destination:
            region_key = "אמריקה"; break

    daily = base_daily[region_key] * style_multiplier * travelers
    total = daily * days + 400 * travelers
    return {
        "estimated_total": round(total), "per_day": round(daily),
        "per_person": round(total / travelers), "currency": "USD",
        "style": style, "includes_flights": True,
    }
