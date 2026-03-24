"""
Positioning Flight Optimizer — האם כדאי לטוס מנמל תעופה אחר?
לפעמים TLV→AMS→NYC זול מ-TLV→NYC ישיר, אפילו כשמחשבים כרטיס ל-AMS.
מחשב: עלות positioning + טיסה ראשית vs ישיר מ-TLV.
"""
import json
import re
from typing import Optional
import anthropic

POSITIONING_AIRPORTS = [
    {"code": "AMS", "city": "אמסטרדם", "country": "הולנד", "hub_score": 9},
    {"code": "LHR", "city": "לונדון", "country": "בריטניה", "hub_score": 10},
    {"code": "CDG", "city": "פריז", "country": "צרפת", "hub_score": 9},
    {"code": "FRA", "city": "פרנקפורט", "country": "גרמניה", "hub_score": 9},
    {"code": "MAD", "city": "מדריד", "country": "ספרד", "hub_score": 8},
    {"code": "BCN", "city": "ברצלונה", "country": "ספרד", "hub_score": 7},
    {"code": "FCO", "city": "רומא", "country": "איטליה", "hub_score": 7},
    {"code": "MUC", "city": "מינכן", "country": "גרמניה", "hub_score": 8},
    {"code": "ZRH", "city": "ציריך", "country": "שוויץ", "hub_score": 8},
    {"code": "IST", "city": "איסטנבול", "country": "טורקיה", "hub_score": 9},
    {"code": "DXB", "city": "דובאי", "country": "איחוד האמירויות", "hub_score": 10},
    {"code": "DOH", "city": "דוחא", "country": "קטאר", "hub_score": 9},
    {"code": "CPH", "city": "קופנהגן", "country": "דנמרק", "hub_score": 7},
    {"code": "VIE", "city": "וינה", "country": "אוסטריה", "hub_score": 7},
    {"code": "ATH", "city": "אתונה", "country": "יוון", "hub_score": 6},
    {"code": "BUD", "city": "בודפשט", "country": "הונגריה", "hub_score": 5},
    {"code": "WRO", "city": "ורוצלאב", "country": "פולין", "hub_score": 4},
    {"code": "KTW", "city": "קטוביצה", "country": "פולין", "hub_score": 4},
    {"code": "NYO", "city": "שטוקהולם סקבסטה", "country": "שוודיה", "hub_score": 4},
]

# TLV connections — which airports have cheap/frequent flights from TLV
TLV_CONNECTIONS = {
    "AMS": {"avg_price": 180, "frequency": "daily", "airlines": ["KL", "EL"]},
    "LHR": {"avg_price": 190, "frequency": "daily", "airlines": ["BA", "EL", "LY"]},
    "CDG": {"avg_price": 175, "frequency": "daily", "airlines": ["AF", "EL"]},
    "FRA": {"avg_price": 185, "frequency": "daily", "airlines": ["LH", "EL"]},
    "MAD": {"avg_price": 170, "frequency": "daily", "airlines": ["IB", "VY", "EL"]},
    "BCN": {"avg_price": 145, "frequency": "daily", "airlines": ["VY", "EL"]},
    "FCO": {"avg_price": 155, "frequency": "daily", "airlines": ["AZ", "EL", "FR"]},
    "MUC": {"avg_price": 180, "frequency": "daily", "airlines": ["LH", "EL"]},
    "ZRH": {"avg_price": 195, "frequency": "daily", "airlines": ["LX", "EL"]},
    "IST": {"avg_price": 120, "frequency": "multiple daily", "airlines": ["TK", "PC"]},
    "DXB": {"avg_price": 135, "frequency": "multiple daily", "airlines": ["EK", "FZ"]},
    "DOH": {"avg_price": 140, "frequency": "multiple daily", "airlines": ["QR"]},
    "CPH": {"avg_price": 200, "frequency": "daily", "airlines": ["SK", "EL"]},
    "VIE": {"avg_price": 160, "frequency": "daily", "airlines": ["OS", "EL"]},
    "ATH": {"avg_price": 130, "frequency": "daily", "airlines": ["A3", "EL"]},
    "BUD": {"avg_price": 85, "frequency": "daily", "airlines": ["W6"]},
    "WRO": {"avg_price": 75, "frequency": "3x week", "airlines": ["W6", "FR"]},
    "KTW": {"avg_price": 70, "frequency": "3x week", "airlines": ["W6"]},
    "NYO": {"avg_price": 110, "frequency": "weekly", "airlines": ["FR"]},
}


def find_positioning_opportunities(
    destination: str,
    travel_date: str,
    return_date: str = "",
    budget: float = 0,
    travelers: int = 1,
) -> list:
    """
    מוצא הזדמנויות positioning:
    האם כדאי לטוס תחילה לאמסטרדם/לונדון ומשם לטוס לyyyy?
    """
    client = anthropic.Anthropic()

    hubs_str = "\n".join(
        f"- {a['code']} ({a['city']}, {a['country']}) — "
        f"מ-TLV בכ-${TLV_CONNECTIONS.get(a['code'], {}).get('avg_price', 200)}"
        for a in POSITIONING_AIRPORTS[:12]
    )

    prompt = f"""מצא הזדמנויות Positioning Flights:

יעד סופי: {destination}
תאריך יציאה: {travel_date}
{f"תאריך חזרה: {return_date}" if return_date else ""}
נוסעים: {travelers}
{f"תקציב: ${budget}" if budget else ""}

מוצא: TLV (תל אביב)

שדות תעופה להתחשב בהם:
{hubs_str}

הטריק: לפעמים TLV→HUB→{destination} עולה פחות מ-TLV→{destination} ישיר,
אפילו כשמחשבים את כרטיס ה-positioning TLV→HUB.

עבור כל הזדמנות:
1. מחיר TLV→{destination} ישיר (או עם עצירה רגילה)
2. מחיר TLV→HUB (low-cost / ULCC)
3. מחיר HUB→{destination}
4. סך הכל עלות positioning vs ישיר
5. האם משתלם?

שקול גם:
- טיסות WizzAir/Ryanair/easyJet לפולין/הונגריה ומשם long-haul
- עצירות אסטרטגיות בדובאי/איסטנבול
- lowcost אמריקאים (Southwest, JetBlue) מאירופה ל-US

לכל הזדמנות:
{{
  "positioning_airport": "XXX",
  "positioning_city": "עיר",
  "tlv_to_hub_price": 000,
  "hub_to_dest_price": 000,
  "total_positioning": 000,
  "direct_tlv_to_dest": 000,
  "savings": 000,
  "savings_pct": 0.0,
  "currency": "USD",
  "positioning_airline": "חברה",
  "main_airline": "חברה",
  "extra_travel_time_hours": 0,
  "overnight_needed": false,
  "worth_it": true/false,
  "why": "הסבר",
  "tips": "טיפים",
  "deep_link": ""
}}

החזר JSON array. כלול רק הזדמנויות עם חיסכון של 10%+ אחרי כל הוצאות."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            thinking={"type": "adaptive"},
            tools=[
                {"type": "web_search_20260209", "name": "web_search"},
                {"type": "web_fetch_20260209", "name": "web_fetch"},
            ],
            system=(
                "אתה מומחה ל-positioning flights ו-travel hacking. "
                "מצא הזדמנויות אמיתיות שרוב האנשים מפספסים. "
                "התמקד בחברות low-cost אירופאיות ושדות תעופה קטנים."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            results = json.loads(arr.group(0))
            return sorted(results, key=lambda x: x.get("savings", 0), reverse=True)
    except Exception as e:
        return [{"error": str(e)}]
    return []


def analyze_overnight_positioning(
    hub: str,
    destination: str,
    travel_date: str,
) -> dict:
    """
    מנתח האם שווה ללון בעיר הביניים — אולי לבקר שם גם?
    """
    client = anthropic.Anthropic()

    hub_info = next((a for a in POSITIONING_AIRPORTS if a["code"] == hub), {})
    hub_city = hub_info.get("city", hub)

    prompt = f"""ניתח אסטרטגיית positioning עם לינה:

מוצא: TLV
עצירה: {hub} ({hub_city})
יעד: {destination}
תאריך: {travel_date}

שאלות:
1. מה עלות לינה ל-1 לילה ב-{hub_city}?
2. האם כדאי להשתמש בזה לבקר ב-{hub_city} ליום-יומיים?
3. מה המחיר הכולל עם לינה?
4. האם זה עדיין משתלם לעומת ישיר?
5. מה הדברים הכי שווים לעשות ב-{hub_city} בלילה אחד?

החזר JSON:
{{
  "hub_city": "{hub_city}",
  "accommodation_price": 000,
  "accommodation_type": "hostel/hotel/airbnb",
  "total_with_overnight": 000,
  "vs_direct": 000,
  "still_saves": 000,
  "worth_adding_night": true/false,
  "top_activities": ["פעילות 1", "פעילות 2", "פעילות 3"],
  "best_area_to_stay": "שכונה/אזור",
  "pro_tips": "טיפים"
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
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


def get_cheapest_tlv_positioning_routes(month: str = "") -> list:
    """
    מה הנתיבי positioning הזולים ביותר מ-TLV — לאן כדאי לטוס כ-positioning?
    """
    client = anthropic.Anthropic()

    airports_str = ", ".join(
        f"{a['code']} ({a['city']})"
        for a in POSITIONING_AIRPORTS
        if a["code"] in TLV_CONNECTIONS
    )

    prompt = f"""מצא את הנתיבי positioning הזולים ביותר מ-TLV:

שדות תעופה רלוונטיים: {airports_str}
{f"חודש: {month}" if month else ""}

מצא:
1. הטיסות הזולות ביותר מ-TLV לכל אחד מהשדות האלה
2. דגש על: Wizz Air, Ryanair, easyJet, TUI fly
3. כולל מועדים גמישים

לכל נתיב:
{{
  "airport": "XXX",
  "city": "עיר",
  "price_from": 00,
  "airline": "חברה",
  "best_date": "תאריך",
  "is_llc": true,
  "why_good_positioning": "מה הגישה שלו ליעדים אחרים"
}}

החזר JSON array ממוין לפי מחיר."""

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
            return json.loads(arr.group(0))
    except Exception as e:
        return [{"error": str(e)}]
    return []


def calculate_positioning_roi(
    tlv_to_hub: float,
    hub_to_dest: float,
    direct_price: float,
    extra_time_hours: float = 6,
    hourly_rate: float = 20,
) -> dict:
    """
    חישוב ROI של positioning — כולל עלות זמן.
    hourly_rate = כמה שעה שלך שווה בדולר
    """
    total_positioning = tlv_to_hub + hub_to_dest
    savings = direct_price - total_positioning
    savings_pct = (savings / direct_price * 100) if direct_price > 0 else 0

    time_cost = extra_time_hours * hourly_rate
    net_savings = savings - time_cost
    roi = (net_savings / total_positioning * 100) if total_positioning > 0 else 0

    return {
        "total_positioning_cost": round(total_positioning, 2),
        "direct_cost": round(direct_price, 2),
        "gross_savings": round(savings, 2),
        "gross_savings_pct": round(savings_pct, 1),
        "time_cost": round(time_cost, 2),
        "net_savings": round(net_savings, 2),
        "roi_pct": round(roi, 1),
        "worth_it": net_savings > 0 and savings_pct > 8,
        "verdict": (
            "🟢 כדאי מאוד!" if net_savings > 100
            else "🟡 כדאי בינוני" if net_savings > 0
            else "🔴 לא משתלם"
        ),
    }
