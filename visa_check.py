"""
Visa Requirements Checker — checks entry requirements for Israeli passport holders.
"""
import json
import re
import anthropic

VISA_PROMPT = """בדוק את דרישות הכניסה לבעלי דרכון ישראלי למדינה/עיר: {destination}

אנא ספק מידע מדויק ועדכני על:
1. האם נדרשת ויזה?
2. האם יש Visa On Arrival?
3. האם יש eVisa (ויזה אלקטרונית)?
4. תקופת שהות מקסימלית ללא ויזה
5. עלות ויזה (אם נדרשת)
6. זמן עיבוד הויזה
7. מסמכים נדרשים
8. הערות חשובות (כולל האם ישראל שהיחסים עם המדינה)

החזר JSON:
{{
  "destination": "שם המדינה/עיר",
  "country_code": "XX",
  "visa_required": true/false,
  "visa_on_arrival": true/false,
  "e_visa": true/false,
  "visa_free": true/false,
  "max_stay_days": 0,
  "visa_cost_usd": 0,
  "processing_days": 0,
  "status": "visa_free" / "visa_on_arrival" / "e_visa" / "visa_required" / "not_allowed",
  "status_label": "תווית בעברית",
  "requirements": ["מסמך 1", "מסמך 2"],
  "important_notes": ["הערה חשובה 1", "הערה חשובה 2"],
  "embassy_info": "מידע על שגרירות/קונסוליה",
  "last_updated": "YYYY-MM",
  "confidence": "high" / "medium" / "low",
  "source": "מקור המידע"
}}

שים לב: מידע עדכני לשנת 2025-2026. אם אין קשרים דיפלומטיים עם ישראל, ציין זאת."""


def check_visa(destination: str, passport: str = "Israeli") -> dict:
    """
    Check visa requirements for the given destination for Israeli passport holders.
    """
    client = anthropic.Anthropic()

    prompt = VISA_PROMPT.format(destination=destination)

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            system="אתה מומחה לדרישות כניסה ודרכונים. ספק מידע מדויק ועדכני בלבד.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}


def check_multiple(destinations: list) -> list:
    """Check visa requirements for multiple destinations at once."""
    results = []
    for dest in destinations:
        result = check_visa(dest)
        result["destination_query"] = dest
        results.append(result)
    return results


STATUS_CONFIG = {
    "visa_free":       {"icon": "✅", "color": "#00ff88", "label": "ללא ויזה"},
    "visa_on_arrival": {"icon": "🟡", "color": "#ffd93d", "label": "ויזה בהגעה"},
    "e_visa":          {"icon": "🔵", "color": "#74b9ff", "label": "eVisa"},
    "visa_required":   {"icon": "🔴", "color": "#ff6b6b", "label": "ויזה נדרשת"},
    "not_allowed":     {"icon": "⛔", "color": "#ff0000", "label": "כניסה אסורה"},
}


def get_status_config(status: str) -> dict:
    return STATUS_CONFIG.get(status, {"icon": "❓", "color": "#aaa", "label": "לא ידוע"})
