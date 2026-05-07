import os
"""
Price Sentiment Analyzer v2 — scans live news for events that affect flight prices:
strikes, elections, wars, weather, local holidays, sporting events, etc.
"""
import json
import re
from datetime import datetime
import ai_client

_lang = "he"

SENTIMENT_PROMPT = """Analyze the expected impact of news and events on flight prices for the route:
{origin} ↔ {destination}
Travel date: {travel_date}

Search for recent news about:
1. Strikes and labor actions (airlines, airports, ground handlers)
2. Political events (elections, protests, instability)
3. Natural disasters and extreme weather
4. Major sports and cultural events (Olympics, World Cup, festivals)
5. Tourism seasons and Peak Seasons
6. Economic factors (fuel prices, currency changes)
7. Opening/closing of new routes

Return JSON:
{{
  "overall_sentiment": "bullish" / "bearish" / "neutral",
  "sentiment_score": 7.5,
  "price_impact": "rising" / "falling" / "stable",
  "impact_pct": 15,
  "confidence": "high" / "medium" / "low",
  "key_events": [
    {{
      "type": "strike" / "event" / "weather" / "political" / "seasonal" / "economic",
      "title": "event title",
      "impact": "positive" / "negative" / "neutral",
      "impact_on_price": "raises prices" / "lowers prices" / "neutral",
      "magnitude": "high" / "medium" / "low",
      "timeframe": "immediate" / "two weeks" / "one month",
      "source": "source name"
    }}
  ],
  "recommendation": "buy now" / "wait" / "unclear",
  "reasoning": "detailed analysis (3-4 sentences)",
  "best_booking_window": "when to book",
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
    if not ai_client.is_configured():
        return {"error": "missing_api_key", "reason": "GEMINI_API_KEY not configured"}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    prompt = SENTIMENT_PROMPT.format(
        origin=origin,
        destination=destination,
        travel_date=travel_date or ("Not specified" if _lang == "en" else "לא צוין"),
        now=now,
    )

    try:
        text = ai_client.ask_with_search(
            prompt=prompt,
            system=(
                "You are an expert flight price analyst. "
                "Analyze real-time news and assess their impact on flight prices. "
                "Be specific and fact-based only."
                + (" Respond in English. Use English for all text fields in the JSON." if _lang == "en" else "")
            ),
            max_tokens=3000,
        )
        if text:
            result = ai_client.extract_json(text)
            if result and "found" not in result:
                return result
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
        "recommendation": data.get("recommendation", "unclear" if _lang == "en" else "לא ברור"),
        "reasoning": data.get("reasoning", ""),
        "best_booking_window": data.get("best_booking_window", ""),
        "risk_level": data.get("risk_level", "medium"),
        "risk_color": {"high": "#ff4444", "medium": "#ffcc00", "low": "#00ff88"}.get(
            data.get("risk_level", "medium"), "#aaa"
        ),
    }
