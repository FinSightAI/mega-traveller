"""
Stopover Deals Finder — מוצא עצירות חינם ו-stopovers שמציעות חברות תעופה.
Emirates → Dubai, Icelandair → Reykjavik, Turkish → Istanbul, Qatar → Doha, etc.
לפעמים שווה יותר מלטוס ישיר — שני יעדים במחיר אחד.
"""
import json
import re
import anthropic


STOPOVER_AIRLINES = [
    ("Emirates", "Dubai", "DXB"),
    ("Icelandair", "Reykjavik", "KEF"),
    ("Turkish Airlines", "Istanbul", "IST"),
    ("Qatar Airways", "Doha", "DOH"),
    ("Etihad", "Abu Dhabi", "AUH"),
    ("Singapore Airlines", "Singapore", "SIN"),
    ("Finnair", "Helsinki", "HEL"),
    ("Ethiopian Airlines", "Addis Ababa", "ADD"),
]


def find_stopovers(
    origin: str,
    destination: str,
    date_out: str,
    date_return: str = "",
    max_stopover_days: int = 3,
) -> list:
    """
    מוצא אפשרויות stopover בדרך ליעד.
    מחזיר רשימה ממוינת לפי ערך (חיסכון + יעד בונוס).
    """
    client = anthropic.Anthropic()

    airlines_str = "\n".join(
        f"- {a} דרך {city} ({code})"
        for a, city, code in STOPOVER_AIRLINES
    )

    prompt = f"""מצא אפשרויות stopover מעניינות למסלול: {origin} → {destination}

תאריך יציאה: {date_out}
{f"תאריך חזרה: {date_return}" if date_return else ""}
מקסימום ימי עצירה: {max_stopover_days}

חברות תעופה שמציעות stopovers ידועים:
{airlines_str}

לכל אפשרות stopover, חשב:
1. מחיר הטיסה דרך העצירה vs. טיסה ישירה ל-{destination}
2. האם ניתן להוסיף עצירה ב-{date_out} ללא עלות נוספת?
3. כמה ימים ניתן להישאר בעיר הביניים?
4. מה מעניין לעשות בעיר הביניים?

לכל אפשרות החזר JSON:
{{
  "airline": "שם חברה",
  "stopover_city": "עיר",
  "stopover_code": "XXX",
  "stopover_days_min": 0,
  "stopover_days_max": 3,
  "price_with_stopover": 000,
  "price_direct": 000,
  "currency": "USD",
  "savings_vs_direct": 000,
  "extra_cost_vs_direct": 000,
  "is_free_stopover": true,
  "booking_url": "",
  "stopover_highlights": ["אטרקציה 1", "אטרקציה 2", "אטרקציה 3"],
  "best_for": "קצר/ארוך/משפחות/זוגות",
  "visa_needed": true/false,
  "tip": "טיפ חשוב"
}}

החזר JSON array. כלול רק אפשרויות ריאליות ומעניינות."""

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
                "אתה מומחה ל-travel hacking ו-stopovers. "
                "תמיד מחפש את הדרך הכי חכמה לטוס ולחסוך כסף. "
                "תן מידע ספציפי ומעשי."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            results = json.loads(arr.group(0))
            # Sort: free stopovers first, then by savings
            results.sort(
                key=lambda x: (
                    not x.get("is_free_stopover", False),
                    -(x.get("savings_vs_direct", 0) or 0),
                )
            )
            return results
    except Exception as e:
        return [{"error": str(e)}]
    return []


def get_stopover_value_score(option: dict) -> float:
    """0-10 ניקוד ערך של stopover."""
    score = 5.0
    if option.get("is_free_stopover"):
        score += 3.0
    savings = option.get("savings_vs_direct", 0) or 0
    if savings > 200:
        score += 2.0
    elif savings > 100:
        score += 1.0
    elif savings > 0:
        score += 0.5
    highlights = len(option.get("stopover_highlights", []))
    score += min(highlights * 0.3, 1.0)
    if not option.get("visa_needed", True):
        score += 0.5
    return min(10.0, score)
