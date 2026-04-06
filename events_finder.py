"""
Events at Destination — מוצא אירועים (קונצרטים, פסטיבלים, ספורט, כנסים)
בתקופת הנסיעה שעשויים להשפיע על מחירים.
"""
import json
import re
from typing import Optional
import ai_client

_lang = "he"

_PROMPT = """Search the web and find events happening in {destination} between {date_from} and {date_to}.

Look for:
- Concerts and music festivals
- Sports events (Champions League, F1, Olympics, local leagues)
- Cultural festivals and national holidays
- Large conferences and trade shows
- Any events that cause hotel/flight prices to spike

For each event return:
{{
  "name": "event name",
  "date": "YYYY-MM-DD",
  "category": "concert|festival|sports|conference|holiday|other",
  "price_impact": "high|medium|low",
  "emoji": "🎵|🏆|🎪|💼|🎉",
  "note": "short note about price impact"
}}

Return a JSON array. If no significant events found, return [].
Be accurate — only real upcoming events. Today is {today}."""


def get_events(destination: str, date_from: str, date_to: str = "") -> list[dict]:
    """
    Find events at destination during travel dates using AI web search.
    Returns list of event dicts.
    """
    if not ai_client.is_configured():
        return []
    if not destination or not date_from:
        return []

    import datetime
    today = datetime.date.today().isoformat()
    date_range = f"{date_from} to {date_to}" if date_to else f"around {date_from}"

    prompt = _PROMPT.format(
        destination=destination,
        date_from=date_from,
        date_to=date_to or date_from,
        today=today,
    )
    if _lang == "he":
        prompt += "\n\nFor the 'note' field, write in Hebrew."

    system = (
        "You are an expert travel researcher. "
        "Find real, verified events happening at the destination during the given dates. "
        "Focus on events that significantly affect travel prices (high demand periods). "
        "Be concise and accurate."
    )

    text = ai_client.ask_with_search(prompt=prompt, system=system, max_tokens=1500)
    if not text:
        return []

    try:
        arr_match = re.search(r"\[.*\]", text, re.DOTALL)
        if arr_match:
            events = json.loads(arr_match.group(0))
            # Sort by price impact then date
            impact_order = {"high": 0, "medium": 1, "low": 2}
            events.sort(key=lambda e: (
                impact_order.get(e.get("price_impact", "low"), 2),
                e.get("date", "")
            ))
            return events[:8]
    except (json.JSONDecodeError, ValueError):
        pass
    return []


def format_impact_label(impact: str, lang: str = "he") -> str:
    labels = {
        "high":   ("🔴 השפעה גבוהה על מחירים", "🔴 High price impact"),
        "medium": ("🟡 השפעה בינונית", "🟡 Medium impact"),
        "low":    ("🟢 השפעה נמוכה", "🟢 Low impact"),
    }
    pair = labels.get(impact, ("⚪ לא ידוע", "⚪ Unknown"))
    return pair[0] if lang == "he" else pair[1]
