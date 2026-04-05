"""
AI price prediction — powered by Gemini.
"""
import json
import re
from datetime import datetime
from typing import Optional

import ai_client

_lang = "he"

PREDICTION_PROMPT = """You are an expert in travel price analysis. Analyze the following data and predict where the price is heading.

Item: {name} | {category} | {destination}
Travel dates: {dates}
Price history (most recent first):
{history}

Average: {avg:.0f} | Minimum: {min_p:.0f} | Maximum: {max_p:.0f} | Current: {current:.0f}

Perform deep analysis:
1. Trend (rising/falling/stable)
2. Seasonality (is this peak season?)
3. How much time until travel?
4. Recommendation: buy now / wait / fair price

Return JSON:
{{
  "trend": "rising" | "falling" | "stable",
  "trend_pct": 5.2,
  "recommendation": "buy_now" | "wait" | "fair_price",
  "confidence": "high" | "medium" | "low",
  "predicted_price_7d": 000,
  "predicted_price_30d": 000,
  "reasoning": "detailed explanation (3-4 sentences)",
  "urgency_score": 8
}}"""


def predict_price(item: dict, history: list) -> Optional[dict]:
    """Predict whether price will go up or down."""
    if len(history) < 3:
        return None
    if not ai_client.is_configured():
        return {"error": "missing_api_key", "reasoning": "GEMINI_API_KEY not configured"}

    prices = [r["price"] for r in history]
    avg = sum(prices) / len(prices)
    current = prices[0]

    history_str = "\n".join(
        f"  {r['checked_at'][:16]}: {r['price']:.0f} {r['currency']}"
        for r in history[:15]
    )
    dates = item.get("date_from", "")
    if dates and item.get("date_to"):
        dates += f" → {item['date_to']}"

    prompt = PREDICTION_PROMPT.format(
        name=item["name"], category=item["category"],
        destination=item["destination"],
        dates=dates or ("Not specified" if _lang == "en" else "לא צוין"),
        history=history_str, avg=avg,
        min_p=min(prices), max_p=max(prices), current=current,
    )
    if _lang == "en":
        prompt += "\n\nRespond in English."

    text = ai_client.ask_with_search(prompt=prompt, max_tokens=1024)
    if not text:
        return None

    result = ai_client.extract_json(text)
    if result.get("found") is False and "reason" in result:
        return None

    result["analyzed_at"] = datetime.now().isoformat()
    result["current_price"] = current
    return result


def wait_probability(item: dict, history: list) -> dict:
    """
    Calculate the probability the price will drop in the next 7 days.
    Uses statistical analysis of historical data + AI reasoning.
    Returns dict with drop_prob (0-1), trend, verdict, badge.
    """
    if len(history) < 2:
        return {"drop_prob": None, "verdict": "insufficient_data", "badge": "❓"}

    prices = [r["price"] for r in history]
    current = prices[0]
    avg = sum(prices) / len(prices)
    min_p = min(prices)
    max_p = max(prices)
    price_range = max_p - min_p if max_p != min_p else 1

    # Linear trend over last N points
    n = min(len(prices), 10)
    recent = prices[:n]
    if n >= 2:
        slope = (recent[-1] - recent[0]) / (n - 1)
    else:
        slope = 0

    # Statistical drop probability
    # How often did price go down in consecutive pairs?
    drops = sum(1 for a, b in zip(prices, prices[1:]) if a < b)
    total_pairs = len(prices) - 1
    historical_drop_rate = drops / total_pairs if total_pairs > 0 else 0.5

    # Adjust by current position in range (if near top → more likely to drop)
    position_in_range = (current - min_p) / price_range  # 0=at min, 1=at max
    position_boost = position_in_range * 0.3  # 0 to +0.3

    # Slope adjustment (falling trend → more likely to keep falling)
    slope_factor = -slope / (avg * 0.1) if avg > 0 else 0
    slope_factor = max(-0.2, min(0.2, slope_factor))

    drop_prob = min(0.95, max(0.05, historical_drop_rate + position_boost + slope_factor))

    # Verdict
    days_to_travel = None
    if item.get("date_from"):
        try:
            from datetime import date
            days_to_travel = (date.fromisoformat(item["date_from"]) - date.today()).days
        except Exception:
            pass

    # Override: if travel is very soon, buying urgency overrides stats
    if days_to_travel is not None and days_to_travel < 14:
        verdict = "buy_now"
        badge = "🔥 קנה עכשיו" if _lang == "he" else "🔥 Buy Now"
        drop_prob = max(0.05, drop_prob - 0.3)  # less likely to wait when close
    elif drop_prob >= 0.65:
        verdict = "wait"
        badge = "⏳ כדאי לחכות" if _lang == "he" else "⏳ Worth waiting"
    elif drop_prob <= 0.35:
        verdict = "buy_now"
        badge = "✅ קנה עכשיו" if _lang == "he" else "✅ Buy now"
    else:
        verdict = "uncertain"
        badge = "🤔 לא ברור" if _lang == "he" else "🤔 Uncertain"

    # Current vs average
    vs_avg_pct = ((current - avg) / avg * 100) if avg > 0 else 0

    return {
        "drop_prob": round(drop_prob, 2),
        "verdict": verdict,
        "badge": badge,
        "slope": round(slope, 1),
        "trend": "falling" if slope < -1 else "rising" if slope > 1 else "stable",
        "vs_avg_pct": round(vs_avg_pct, 1),
        "current": current,
        "avg": round(avg, 0),
        "min_p": min_p,
        "max_p": max_p,
        "days_to_travel": days_to_travel,
        "data_points": len(prices),
    }


def format_prediction(pred: dict) -> dict:
    """Format prediction for display."""
    if not pred or "error" in pred:
        return {"text": "Cannot analyze" if _lang == "en" else "לא ניתן לנתח", "color": "gray", "icon": "❓"}

    trend = pred.get("trend", "stable")
    rec = pred.get("recommendation", "fair_price")
    confidence = pred.get("confidence", "low")

    icons = {"rising": "📈", "falling": "📉", "stable": "➡️"}
    colors = {"buy_now": "green", "wait": "orange", "fair_price": "blue"}
    rec_text = {
        "buy_now": "🔥 Buy Now!" if _lang == "en" else "🔥 קנה עכשיו!",
        "wait": "⏳ Wait" if _lang == "en" else "⏳ המתן",
        "fair_price": "✅ Fair Price" if _lang == "en" else "✅ מחיר הוגן",
    }
    conf_text = {
        "high": "High confidence" if _lang == "en" else "ביטחון גבוה",
        "medium": "Medium confidence" if _lang == "en" else "ביטחון בינוני",
        "low": "Low confidence" if _lang == "en" else "ביטחון נמוך",
    }

    return {
        "icon": icons.get(trend, "➡️"),
        "trend": trend,
        "color": colors.get(rec, "gray"),
        "recommendation": rec_text.get(rec, rec),
        "confidence": conf_text.get(confidence, confidence),
        "reasoning": pred.get("reasoning", ""),
        "predicted_7d": pred.get("predicted_price_7d"),
        "predicted_30d": pred.get("predicted_price_30d"),
        "urgency": pred.get("urgency_score", 5),
        "trend_pct": pred.get("trend_pct", 0),
    }
