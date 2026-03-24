"""
Hidden City Ticketing Finder — מוצא כרטיסים זולים יותר דרך יעד ביניים.

הטריק: TLV→NYC עם עצירה ב-LHR לפעמים זול מ-TLV→LHR ישיר.
תורד ב-LHR ותפסיד את הרגל הבאה — חוסך 20-50%.

⚠️ חוקי אך מנוגד לתנאי שימוש של חברות תעופה.
   מתאים לטיסות ללא מטען מסוחר, כרטיסים חד-כיווניים.
"""
import json
import re
import anthropic

MAJOR_HUBS = [
    ("LHR", "לונדון"),
    ("AMS", "אמסטרדם"),
    ("FRA", "פרנקפורט"),
    ("CDG", "פריז"),
    ("IST", "איסטנבול"),
    ("DXB", "דובאי"),
    ("DOH", "דוחא"),
    ("JFK", "ניו-יורק"),
    ("EWR", "ניו-ג׳רזי"),
    ("ORD", "שיקגו"),
    ("LAX", "לוס אנג׳לס"),
    ("BKK", "בנגקוק"),
    ("SIN", "סינגפור"),
    ("HKG", "הונג קונג"),
    ("NRT", "טוקיו"),
    ("GRU", "סאו פאולו"),
]


def find_hidden_city_deals(
    origin: str,
    real_destination: str,
    date_out: str,
    date_return: str = "",
) -> list:
    """
    מוצא hidden city opportunities.
    מחפש טיסות origin → final_dest שעוברות דרך real_destination
    ובודק אם הן זולות מ-origin → real_destination ישיר.
    """
    client = anthropic.Anthropic()

    hubs_str = ", ".join(f"{code} ({name})" for code, name in MAJOR_HUBS)

    prompt = f"""מצא הזדמנויות Hidden City Ticketing:

יעד אמיתי שאני רוצה להגיע אליו: {real_destination}
מוצא: {origin}
תאריך: {date_out}
{f"חזרה: {date_return}" if date_return else ""}

שדות תעופה Hub גדולים: {hubs_str}

הטריק: לפעמים טיסה {origin}→FINAL_DEST שעוברת דרך {real_destination}
זולה יותר מ-{origin}→{real_destination} ישיר. אני יורד ב-{real_destination} ולא ממשיך.

בדוק:
1. מה מחיר {origin}→{real_destination} ישיר?
2. חפש טיסות {origin}→[יעד כלשהו] שעוברות דרך {real_destination}
3. אם יש טיסה {origin}→{real_destination}→ANYWHERE שזולה יותר — זו הזדמנות!

גם בדוק ההפך: האם {origin}→{real_destination} כ-stopover ממסלול אחר?

לכל הזדמנות:
{{
  "real_destination": "{real_destination}",
  "final_destination": "YYY",
  "route": "{origin}→{real_destination}→YYY",
  "price_hidden": 000,
  "price_direct": 000,
  "savings": 000,
  "savings_pct": 0.0,
  "currency": "USD",
  "airline": "",
  "warning": "לא מומלץ עם מטען מסוחר",
  "risk_level": "נמוך/בינוני/גבוה",
  "why_works": "הסבר",
  "book_as_if_going_to": "YYY",
  "deep_link": ""
}}

החזר JSON array. כלול רק הזדמנויות אמיתיות עם חיסכון של 15%+."""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            system=(
                "אתה מומחה ל-travel hacking ו-hidden city ticketing. "
                "מצא הזדמנויות אמיתיות עם חיסכון משמעותי. "
                "תמיד ציין את הסיכונים בבירור."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            results = json.loads(arr.group(0))
            return sorted(results, key=lambda x: x.get("savings_pct", 0), reverse=True)
    except Exception as e:
        return [{"error": str(e)}]
    return []


def find_throwaway_ticketing(
    origin: str,
    destination: str,
    date_out: str,
) -> dict:
    """
    Throwaway Ticketing — לפעמים round-trip זול מ-one-way.
    מזמין הלוך-חזור ומשתמש רק בחלק הראשון.
    """
    client = anthropic.Anthropic()

    prompt = f"""בדוק: האם round-trip זול יותר מ-one-way?

מסלול: {origin} → {destination}
תאריך: {date_out}

בדוק:
1. מחיר one-way {origin}→{destination}
2. מחיר round-trip {origin}↔{destination} (חזרה כעבור שבוע)
3. האם round-trip + השלכת הרגל החוזרת = חיסכון?

החזר JSON:
{{
  "oneway_price": 000,
  "roundtrip_price": 000,
  "currency": "USD",
  "throwaway_saves": 000,
  "throwaway_worthwhile": true/false,
  "recommendation": "...",
  "risk": "...",
  "airline": ""
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


RISKS_AND_RULES = """
⚠️ חוקי אך מנוגד לתנאי שימוש:
• חברות יכולות לבטל כרטיסים / חשבונות frequent flyer
• **אסור עם מטען מסוחר** — יעלה לך ליעד הסופי
• לא מתאים לטיסות עם חיבור קצר
• המחיר יכול להשתנות לפני רכישה
• מתאים לכרטיסים חד-כיווניים בלבד

✅ הכי בטוח:
• חברה לו-קוסט (Ryanair, Wizz) — פחות מפקחות
• מטען יד בלבד
• תשלום במזומן / כרטיס שאינו קשור לחשבון frequent flyer
"""

def get_risks_explanation() -> str:
    return RISKS_AND_RULES
