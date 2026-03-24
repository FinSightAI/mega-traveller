"""
Smart Search Engine — חיפוש חכם מורכב.
  • Split ticketing — שני כרטיסים חד-כיווניים במקום הלוך-חזור
  • Nearby airports — האם SDV/ETH זולים יותר?
  • "הפתיעני" — הדסטינציה הכי שווה לתקציב שלך
  • Package vs. separate — מה יותר משתלם?
  • Last-minute — מצא דיל לשבוע הבא
  • Off-peak day — באיזה יום בשבוע הכי זול?
"""
import json
import re
from datetime import datetime, timedelta
import anthropic

IL_AIRPORTS = [
    ("TLV", "נתב\"ג - תל אביב"),
    ("SDV", "שדה דב - תל אביב"),
    ("ETH", "אילת"),
    ("HFA", "חיפה"),
]


def surprise_me(
    budget: float,
    currency: str = "USD",
    from_date: str = "",
    to_date: str = "",
    duration_days: int = 7,
    style: str = "כל סגנון",
    interests: str = "",
) -> list[dict]:
    """
    "הפתיעני" — מצא את הדסטינציה הכי שווה לתקציב ולתאריכים.
    Returns top 5 destinations with deal info.
    """
    client = anthropic.Anthropic()

    from_date = from_date or datetime.now().strftime("%Y-%m-%d")
    to_date = to_date or (
        datetime.strptime(from_date, "%Y-%m-%d") + timedelta(days=duration_days)
    ).strftime("%Y-%m-%d")

    prompt = f"""מצא את 5 הדסטינציות הכי שוות לתקציב הבא:

תקציב: {budget} {currency} לאדם (כולל טיסה + לינה)
מוצא: TLV (ישראל)
תאריכים: {from_date} → {to_date} ({duration_days} ימים)
סגנון: {style}
תחומי עניין: {interests or 'הכל'}

חפש מחירים אמיתיים. מצא גם יעדים שאנשים לא חושבים עליהם.

לכל יעד:
{{
  "destination": "שם עיר + מדינה",
  "destination_code": "XXX",
  "total_price": 000,
  "flight_price": 000,
  "hotel_price_night": 000,
  "currency": "USD",
  "why_amazing": "למה זה שווה במיוחד עכשיו (2-3 משפטים)",
  "highlights": ["דבר מגניב 1", "דבר מגניב 2", "דבר מגניב 3"],
  "best_time_to_book": "מתי להזמין",
  "hidden_gem": true/false,
  "deal_quality": "excellent/good/average",
  "surprise_factor": 8
}}

החזר JSON array מ-5 יעדים."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            system="אתה מומחה לטיולים חכמים ותקציביים. תמיד חפש הזדמנויות שאחרים מפספסים.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            results = json.loads(arr.group(0))
            results.sort(key=lambda x: x.get("surprise_factor", 0), reverse=True)
            return results
    except Exception as e:
        return [{"error": str(e)}]
    return []


def check_split_ticket(
    origin: str,
    destination: str,
    outbound_date: str,
    return_date: str,
) -> dict:
    """
    Check if two one-way tickets are cheaper than a round trip.
    """
    client = anthropic.Anthropic()

    prompt = f"""השווה: הלוך-חזור vs. שני כרטיסים חד-כיווניים.

מסלול: {origin} ↔ {destination}
יציאה: {outbound_date}
חזרה: {return_date}

בדוק:
1. מחיר הלוך-חזור (round trip)
2. מחיר כרטיס חד-כיווני {origin}→{destination} ({outbound_date})
3. מחיר כרטיס חד-כיווני {destination}→{origin} ({return_date})
4. סכום שני החד-כיווניים

האם split ticketing משתלם? בכמה?

החזר JSON:
{{
  "roundtrip_price": 000,
  "oneway_out": 000,
  "oneway_return": 000,
  "split_total": 000,
  "currency": "USD",
  "savings": 000,
  "savings_pct": 0.0,
  "recommendation": "roundtrip" / "split",
  "reasoning": "הסבר",
  "book_out_url": "",
  "book_return_url": ""
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}


def check_nearby_airports(
    destination: str,
    date: str,
    return_date: str = "",
) -> list[dict]:
    """
    Check prices from all Israeli airports for a given destination.
    Returns comparison list sorted by price.
    """
    client = anthropic.Anthropic()

    airports_str = ", ".join(f"{code} ({name})" for code, name in IL_AIRPORTS)
    prompt = f"""השווה מחירי טיסות מכל שדות התעופה בישראל ל-{destination}.

שדות תעופה: {airports_str}
תאריך יציאה: {date}
{f"תאריך חזרה: {return_date}" if return_date else ""}

לכל שדה תעופה:
{{
  "airport_code": "TLV",
  "airport_name": "נתב\"ג",
  "price": 000,
  "currency": "USD",
  "airline": "שם חברה",
  "available": true/false,
  "notes": "הערות"
}}

החזר JSON array."""

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
            results = json.loads(arr.group(0))
            return sorted(
                [r for r in results if r.get("available") and r.get("price")],
                key=lambda x: x["price"]
            )
    except Exception:
        pass
    return []


def find_cheapest_day_of_week(
    origin: str,
    destination: str,
    month: str,
) -> dict:
    """Find which day of the week is cheapest to fly this route."""
    client = anthropic.Anthropic()

    prompt = f"""באיזה יום בשבוע הכי זול לטוס מ-{origin} ל-{destination} בחודש {month}?

בדוק את ממוצע המחירים לפי ימי שבוע (א-ז).
גם: האם יש הפרש בין בוקר/ערב?

החזר JSON:
{{
  "cheapest_day": "שלישי",
  "cheapest_day_avg": 000,
  "most_expensive_day": "שישי",
  "most_expensive_day_avg": 000,
  "savings_by_day": 000,
  "savings_pct": 0.0,
  "best_time": "בוקר מוקדם",
  "days_ranking": [
    {{"day": "ראשון", "avg_price": 000}},
    ...
  ],
  "tip": "טיפ מעשי בעברית"
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}


def compare_package_vs_separate(
    origin: str,
    destination: str,
    date_from: str,
    date_to: str,
    travelers: int = 2,
) -> dict:
    """Compare package deal vs. booking flight + hotel separately."""
    client = anthropic.Anthropic()

    prompt = f"""השווה: חבילה מאורגנת vs. הזמנה עצמאית.

מסלול: {origin} → {destination}
תאריכים: {date_from} → {date_to}
נוסעים: {travelers}

בדוק:
1. מחיר חבילה מאורגנת (Gulliver, IsraFlight, Dan, Club Med וכו')
2. טיסה בנפרד + מלון בנפרד (Booking.com / Airbnb)
3. מה כולל כל אפשרות

החזר JSON:
{{
  "package_price": 000,
  "package_includes": ["מה כולל"],
  "package_provider": "שם ספק",
  "separate_flight": 000,
  "separate_hotel_total": 000,
  "separate_total": 000,
  "currency": "USD",
  "savings_with_package": 000,
  "savings_with_separate": 000,
  "recommendation": "package" / "separate",
  "reasoning": "הסבר מפורט",
  "tips": ["טיפ 1", "טיפ 2"]
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}


def find_last_minute_deals(
    origin: str = "TLV",
    days_ahead: int = 7,
    max_price: float = 300,
) -> list[dict]:
    """Find last-minute deals departing in the next X days."""
    client = anthropic.Anthropic()

    from_date = datetime.now().strftime("%Y-%m-%d")
    to_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    prompt = f"""מצא דילי last-minute מ-{origin} שמתאימים לטיסה בשבוע הקרוב.

תאריכים אפשריים: {from_date} עד {to_date}
מחיר מקסימלי: ${max_price}
חפש טיסות ריקות שחברות תעופה מוכרות בזול כדי למלא אותן.

לכל דיל:
{{
  "destination": "עיר + מדינה",
  "destination_code": "XXX",
  "departure_date": "YYYY-MM-DD",
  "price": 000,
  "currency": "USD",
  "airline": "חברה",
  "seats_left": 0,
  "deal_type": "last_minute" / "standby" / "flash",
  "why_cheap": "למה זול",
  "book_by": "מתי צריך להזמין"
}}

החזר JSON array."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            results = json.loads(arr.group(0))
            return [r for r in results if r.get("price", 999) <= max_price]
    except Exception:
        pass
    return []


def best_time_to_book(
    origin: str,
    destination: str,
    travel_month: str = "",
) -> dict:
    """
    Analyze historical booking patterns and find the optimal booking window:
    how many weeks before departure gives the cheapest price.
    """
    client = anthropic.Anthropic()

    prompt = f"""נתח: מתי הכי כדאי לקנות כרטיס טיסה למסלול הבא?

מסלול: {origin} → {destination}
{f"חודש נסיעה מתוכנן: {travel_month}" if travel_month else ""}

על בסיס נתונים היסטוריים ומחקרים:
1. כמה שבועות לפני הטיסה הכי זול לקנות?
2. מה קורה למחיר ב-24-48 שעות אחרונות?
3. האם יש הבדל בין עונות שונות?
4. מה ה-sweet spot המומלץ?

החזר JSON:
{{
  "optimal_weeks_before": 8,
  "optimal_days_range": "49-63",
  "price_curve": [
    {{"weeks_before": 26, "relative_price": 1.2, "label": "26 שבועות"}},
    {{"weeks_before": 16, "relative_price": 1.1, "label": "16 שבועות"}},
    {{"weeks_before": 8,  "relative_price": 1.0, "label": "8 שבועות ✅"}},
    {{"weeks_before": 4,  "relative_price": 1.15, "label": "4 שבועות"}},
    {{"weeks_before": 2,  "relative_price": 1.3,  "label": "2 שבועות"}},
    {{"weeks_before": 1,  "relative_price": 1.5,  "label": "שבוע אחרון"}},
    {{"weeks_before": 0,  "relative_price": 1.8,  "label": "יום-יומיים"}}
  ],
  "potential_savings_pct": 30,
  "worst_time": "שבוע לפני",
  "best_time": "6-8 שבועות לפני",
  "seasonal_advice": "בעונת קיץ הזמן 3 חודשים מראש",
  "last_minute_exception": "האם יש מקרים שלאחרונה דווקא זול?",
  "rule_of_thumb": "כלל אצבע פשוט בעברית",
  "tip": "טיפ נוסף מעשי"
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}
