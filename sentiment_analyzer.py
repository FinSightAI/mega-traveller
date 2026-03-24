"""
Price Sentiment Analyzer v2 — scans live news for events that affect flight prices:
strikes, elections, wars, weather, local holidays, sporting events, etc.
"""
import json
import re
from datetime import datetime
import anthropic


SENTIMENT_PROMPT = """נתח את ההשפעה הצפויה של חדשות ואירועים על מחירי טיסות למסלול:
{origin} ↔ {destination}
תאריך טיסה: {travel_date}

חפש חדשות עדכניות על:
1. שביתות ועיצומים (חברות תעופה, שדות תעופה, מטפלים בקרקע)
2. אירועים פוליטיים (בחירות, מחאות, חוסר יציבות)
3. אסונות טבע ומזג אוויר קיצוני
4. אירועי ספורט ותרבות גדולים (אולימפיאדה, מונדיאל, פסטיבלים)
5. עונות תיירות ו-Peak Seasons
6. מצב כלכלי (מחיר דלק, שינויי מטבע)
7. פתיחת/סגירת נתיבים חדשים

החזר JSON:
{{
  "overall_sentiment": "bullish" / "bearish" / "neutral",
  "sentiment_score": 7.5,
  "price_impact": "rising" / "falling" / "stable",
  "impact_pct": 15,
  "confidence": "high" / "medium" / "low",
  "key_events": [
    {{
      "type": "strike" / "event" / "weather" / "political" / "seasonal" / "economic",
      "title": "כותרת האירוע בעברית",
      "impact": "positive" / "negative" / "neutral",
      "impact_on_price": "מעלה מחירים" / "מוריד מחירים" / "ניטרלי",
      "magnitude": "high" / "medium" / "low",
      "timeframe": "מיידי" / "שבועיים" / "חודש",
      "source": "שם המקור"
    }}
  ],
  "recommendation": "קנה עכשיו" / "המתן" / "לא ברור",
  "reasoning": "ניתוח מפורט בעברית (3-4 משפטים)",
  "best_booking_window": "מתי כדאי להזמין",
  "risk_level": "high" / "medium" / "low",
  "last_updated": "{now}"
}}"""


def analyze_sentiment(
    origin: str,
    destination: str,
    travel_date: str = "",
) -> dict:
    """
    Analyze news sentiment for a route and return price impact prediction.
    """
    client = anthropic.Anthropic()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    prompt = SENTIMENT_PROMPT.format(
        origin=origin,
        destination=destination,
        travel_date=travel_date or "לא צוין",
        now=now,
    )

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=3000,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            system=(
                "אתה אנליסט מחירי תעופה מומחה. "
                "נתח חדשות בזמן אמת והערך את השפעתן על מחירי טיסות. "
                "היה ספציפי ומבוסס על עובדות בלבד."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}


def format_sentiment(data: dict) -> dict:
    """Format sentiment data for display."""
    if not data or "error" in data:
        return {}

    sentiment = data.get("overall_sentiment", "neutral")
    impact = data.get("price_impact", "stable")

    return {
        "sentiment": sentiment,
        "sentiment_icon": {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(sentiment, "➡️"),
        "sentiment_color": {"bullish": "#ff4444", "bearish": "#00ff88", "neutral": "#aaaaaa"}.get(sentiment, "#aaa"),
        "price_impact": impact,
        "impact_icon": {"rising": "⬆️", "falling": "⬇️", "stable": "➡️"}.get(impact, "➡️"),
        "impact_pct": data.get("impact_pct", 0),
        "score": data.get("sentiment_score", 5),
        "confidence": data.get("confidence", "low"),
        "key_events": data.get("key_events", []),
        "recommendation": data.get("recommendation", "לא ברור"),
        "reasoning": data.get("reasoning", ""),
        "best_booking_window": data.get("best_booking_window", ""),
        "risk_level": data.get("risk_level", "medium"),
        "risk_color": {"high": "#ff4444", "medium": "#ffcc00", "low": "#00ff88"}.get(
            data.get("risk_level", "medium"), "#aaa"
        ),
    }
