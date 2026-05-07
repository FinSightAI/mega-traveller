"""
Natural Language Watch Parser — הוסף מעקב בשפה טבעית.
"תוסיף טיסה לברצלונה במאי עד 400 דולר" → WatchItem fields dict.
"""
import json
import re
from datetime import datetime
import ai_client


def parse_watch_request(text: str) -> dict:
    """
    Parse a natural language watch request into WatchItem fields.
    Returns dict with keys: name, category, destination, origin,
    date_from, date_to, max_price, drop_pct, query, confidence, notes.
    Returns {"error": ...} on failure.
    """
    if not ai_client.is_configured():
        return {"error": "GEMINI_API_KEY not configured"}

    text = str(text)[:500]  # cap input size

    now = datetime.now()
    current_year = now.year
    current_month = now.month

    prompt = f"""Parse this travel watch request into structured fields.
Today's date: {now.strftime("%Y-%m-%d")}

User request: "{text}"

Return a JSON object with these fields:
{{
  "name": "short descriptive name for the watch item",
  "category": "flight" | "hotel" | "apartment" | "package",
  "destination": "city or country name in English",
  "origin": "origin city or IATA code (default TLV for flights)",
  "date_from": "YYYY-MM-DD or null",
  "date_to": "YYYY-MM-DD or null",
  "max_price": number or null,
  "drop_pct": number (default 10),
  "query": "refined search query in English",
  "confidence": 0.0-1.0,
  "notes": "what you assumed or inferred"
}}

Rules:
- If user says "במאי" or "in May" → date_from="{current_year}-05-01", date_to="{current_year}-05-31"
- If month already passed, use next year
- If user says "עד X דולר" or "up to $X" → max_price=X
- If no origin mentioned and category is flight → origin="TLV"
- Return ONLY the JSON object, no other text"""

    try:
        text_resp = ai_client.ask(prompt=prompt, max_tokens=600)
        if not text_resp:
            return {"error": "No response from AI"}
        # Extract JSON
        match = re.search(r'\{.*\}', text_resp, re.DOTALL)
        if not match:
            return {"error": "Could not parse AI response"}
        result = json.loads(match.group(0))
        return result
    except Exception as e:
        return {"error": str(e)}


# Month name → number mapping (Hebrew + English)
_MONTH_MAP = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "אפריל": 4, "מאי": 5, "יוני": 6,
    "יולי": 7, "אוגוסט": 8, "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
