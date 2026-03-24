"""
Cost Calculator Suite:
  1. True Cost Calculator  — עלות אמיתית כולל מטען, ארוחות, הסעה, ביטוח
  2. Points vs Cash        — האם לממש נקודות/מיילים או לשלם במזומן?
  3. Multi-City Optimizer  — מה הסדר הכי זול לסיור מרובה ערים?
"""
import json
import re
import anthropic
from typing import Optional


# ── 1. True Cost Calculator ──────────────────────────────────────────────────

AIRLINE_BAGGAGE_FEES = {
    "Ryanair":    {"cabin": 0, "checked_10kg": 30, "checked_20kg": 55},
    "Wizz Air":   {"cabin": 0, "checked_20kg": 45, "checked_32kg": 65},
    "easyJet":    {"cabin": 0, "checked_15kg": 35, "checked_23kg": 55},
    "El Al":      {"cabin": 0, "checked_23kg": 0, "checked_32kg": 0},
    "Israir":     {"cabin": 0, "checked_15kg": 0},
    "Arkia":      {"cabin": 0, "checked_15kg": 0},
    "Lufthansa":  {"cabin": 0, "checked_23kg": 0},
    "KLM":        {"cabin": 0, "checked_23kg": 0},
    "TurkishAirlines": {"cabin": 0, "checked_23kg": 0},
}

AIRPORT_TRANSPORT = {
    "TLV": {"bus": 18, "shuttle": 50, "taxi": 180, "private": 250},
    "LHR": {"tube": 15, "express": 35, "taxi": 75},
    "CDG": {"rer": 12, "bus": 15, "taxi": 70},
    "AMS": {"train": 18, "bus": 7, "taxi": 60},
    "BCN": {"metro": 6, "bus": 6, "taxi": 45},
    "FCO": {"train": 14, "bus": 7, "taxi": 50},
    "BKK": {"airport_link": 8, "bus": 4, "taxi": 20},
    "DXB": {"metro": 3, "taxi": 25},
}


def calculate_true_cost(
    base_price: float,
    airline: str = "",
    checked_bags: int = 1,
    bag_weight: str = "23kg",
    needs_meals: bool = False,
    origin_airport: str = "TLV",
    dest_airport: str = "",
    transport_mode_origin: str = "taxi",
    transport_mode_dest: str = "taxi",
    travel_insurance: bool = True,
    travelers: int = 1,
    nights: int = 7,
) -> dict:
    """
    מחשב עלות אמיתית של טיסה.
    מחזיר פירוט מלא + השוואה לחברות מתחרות.
    """
    costs = {"base_flight": base_price * travelers}

    # Baggage
    airline_fees = AIRLINE_BAGGAGE_FEES.get(airline, {})
    bag_key = f"checked_{bag_weight}"
    bag_fee_per_person = airline_fees.get(bag_key, 0)
    if checked_bags > 0 and bag_fee_per_person == 0:
        bag_fee_per_person = 0  # included
    costs["baggage"] = bag_fee_per_person * checked_bags * travelers

    # Meals
    costs["meals"] = (12 * travelers) if needs_meals else 0

    # Airport transport origin
    origin_trans = AIRPORT_TRANSPORT.get(origin_airport, {})
    costs["transport_origin"] = origin_trans.get(transport_mode_origin, 50) * travelers

    # Airport transport destination
    dest_trans = AIRPORT_TRANSPORT.get(dest_airport, {})
    costs["transport_destination"] = dest_trans.get(transport_mode_dest, 40) * travelers

    # Insurance (~15-20 USD per person per week)
    costs["insurance"] = (18 * travelers * max(1, nights // 7)) if travel_insurance else 0

    # Seat selection (airlines like Ryanair charge)
    low_cost = airline in ["Ryanair", "Wizz Air", "easyJet"]
    costs["seat_selection"] = (12 * travelers) if low_cost else 0

    total = sum(costs.values())

    return {
        "breakdown": costs,
        "total": total,
        "per_person": total / max(travelers, 1),
        "base_pct": costs["base_flight"] / total * 100 if total else 0,
        "hidden_fees": total - costs["base_flight"],
        "airline": airline,
        "currency": "USD",
    }


# ── 2. Points vs Cash ────────────────────────────────────────────────────────

POINTS_VALUES = {
    # Program: (cents per point, name_he)
    "Matmid":      (1.2,  "מטמיד (אל-על)"),
    "Flying Blue": (1.1,  "Flying Blue (KLM/AF)"),
    "Miles&More":  (1.3,  "Miles&More (לופטהנזה)"),
    "TK Miles":    (1.0,  "Turkish Miles&Smiles"),
    "Avios":       (1.2,  "Avios (British)"),
    "SkyMiles":    (1.1,  "SkyMiles (Delta)"),
    "MileagePlus": (1.3,  "MileagePlus (United)"),
    "AAdvantage":  (1.4,  "AAdvantage (American)"),
    "Hilton":      (0.5,  "Hilton Honors"),
    "Marriott":    (0.7,  "Marriott Bonvoy"),
    "Cal Points":  (0.8,  "נקודות כ.א.ל"),
    "Max Points":  (0.8,  "נקודות מקס"),
    "Leumi Card":  (0.8,  "נקודות לאומי"),
    "Isracard":    (0.9,  "נקודות ישראכארד"),
}


def calculate_points_value(
    points: int,
    program: str,
    redemption_cash_value: float,
    currency: str = "USD",
) -> dict:
    """
    האם לממש נקודות או לשלם במזומן?
    מחשב ערך הנקודות ומשווה.
    """
    cpp, prog_name = POINTS_VALUES.get(program, (1.0, program))
    cash_value_of_points = points * (cpp / 100)  # convert cents per point to dollars

    # Convert to USD if needed (simplified)
    cash_value_usd = cash_value_of_points
    redemption_usd = redemption_cash_value

    is_worth_it = cash_value_usd >= redemption_usd * 0.85  # 15% buffer
    ratio = (cash_value_usd / redemption_usd * 100) if redemption_usd else 0

    recommendation = "מומלץ לממש" if is_worth_it else "עדיף לשלם במזומן"
    if ratio >= 120:
        recommendation = "🔥 ממש עכשיו — ערך מעולה!"
    elif ratio >= 100:
        recommendation = "✅ מומלץ לממש"
    elif ratio >= 80:
        recommendation = "🟡 בערך שווה — תלוי בהעדפה"
    else:
        recommendation = "❌ עדיף לשלם מזומן — חסוך נקודות לעסקה טובה יותר"

    return {
        "program": prog_name,
        "points": points,
        "cpp_cents": cpp,
        "cash_value_usd": round(cash_value_usd, 2),
        "redemption_value_usd": round(redemption_usd, 2),
        "ratio_pct": round(ratio, 1),
        "is_worth_it": is_worth_it,
        "recommendation": recommendation,
        "savings": round(cash_value_usd - redemption_usd, 2) if is_worth_it else 0,
    }


def find_best_redemption(points: int, program: str) -> dict:
    """איפה הכי כדאי לממש נקודות — AI מחפש."""
    client = anthropic.Anthropic()
    cpp, prog_name = POINTS_VALUES.get(program, (1.0, program))

    prompt = f"""יש לי {points:,} נקודות בתוכנית {prog_name}.
ערך ממוצע לנקודה: {cpp} סנט.
ערך כולל: ~${points * cpp / 100:.0f}

מצא את ה-3 דרכי המימוש הכי אטרקטיביות שייתנו לי ערך מעל 1.5 סנט לנקודה.
חפש דילים עכשויים, בונוסים מיוחדים, ותכניות העברה.

החזר JSON array:
{{
  "redemption_type": "טיסה/מלון/שדרוג/העברה",
  "description": "תיאור קצר",
  "cpp_value": 1.8,
  "total_value_usd": 000,
  "how_to": "איך לממש",
  "expires": "מתי פג תוקף (אם רלוונטי)",
  "difficulty": "קל/בינוני/מורכב",
  "tip": "טיפ חשוב"
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            return {"options": json.loads(arr.group(0)), "program": prog_name, "points": points}
    except Exception as e:
        return {"error": str(e)}
    return {}


# ── 3. Multi-City Route Optimizer ───────────────────────────────────────────

def optimize_multi_city(
    cities: list,
    origin: str = "TLV",
    start_date: str = "",
    days_per_city: Optional[dict] = None,
    budget: float = 5000,
) -> dict:
    """
    מוצא את הסדר הזול ביותר לביקור במספר ערים.
    cities = ["טוקיו", "בנגקוק", "באלי", "סינגפור"]
    """
    client = anthropic.Anthropic()
    days_info = ""
    if days_per_city:
        days_info = "\n".join(f"- {city}: {days} ימים" for city, days in days_per_city.items())
    else:
        days_info = f"~{14 // max(len(cities), 1)} ימים בכל עיר"

    cities_str = " → ".join(cities)

    prompt = f"""מטב מסלול מרובה ערים:

ערים לביקור: {cities_str}
מוצא: {origin}
{f"תאריך יציאה: {start_date}" if start_date else ""}
ימים בכל עיר:
{days_info}
תקציב כולל: ${budget:,}

מצא:
1. הסדר הזול ביותר לביקור בכל הערים
2. כמה עולה כל סדר אפשרי (Top 3)
3. האם Open-jaw (טיסה מחזירה ממדינה אחרת) יחסוך כסף?
4. האם יש Hub זול לחבר ביניהם?

החזר JSON:
{{
  "optimal_order": ["עיר1", "עיר2", "עיר3"],
  "optimal_price": 000,
  "direct_comparison": [
    {{"order": ["עיר1", "עיר2"], "price": 000, "currency": "USD", "notes": ""}},
  ],
  "savings_vs_worst": 000,
  "open_jaw_option": {{"description": "", "price": 000, "saves": 000}},
  "hub_tip": "",
  "booking_strategy": "איך להזמין בצורה הכי חכמה",
  "total_with_hotels": 000,
  "flight_legs": [
    {{"from": "XXX", "to": "YYY", "price": 000, "airline": ""}}
  ],
  "tips": ["טיפ 1", "טיפ 2"]
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            system="אתה מומחה ל-travel hacking ותכנון מסלולים. מצא תמיד את הדרך הזולה ביותר.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}
