"""
AI price prediction — האם המחיר יעלה או ירד?
Claude מנתח היסטוריה, עונתיות ומגמות שוק.
"""
import json
from datetime import datetime
from typing import Optional
import anthropic


PREDICTION_PROMPT = """אתה מומחה לניתוח מחירי נסיעות. נתח את הנתונים הבאים וחזה לאן המחיר הולך.

פריט: {name} | {category} | {destination}
תאריכי נסיעה: {dates}
היסטוריית מחירים (מהאחרון לראשון):
{history}

ממוצע: {avg:.0f} | מינימום: {min_p:.0f} | מקסימום: {max_p:.0f} | נוכחי: {current:.0f}

בצע ניתוח מעמיק:
1. מגמה (עולה/יורדת/יציבה)
2. עונתיות (האם זה עונת שיא?)
3. כמה זמן עד לנסיעה?
4. המלצה: לקנות עכשיו / להמתין / מחיר סביר

החזר JSON:
{{
  "trend": "rising" | "falling" | "stable",
  "trend_pct": 5.2,
  "recommendation": "buy_now" | "wait" | "fair_price",
  "confidence": "high" | "medium" | "low",
  "predicted_price_7d": 000,
  "predicted_price_30d": 000,
  "reasoning": "הסבר מפורט בעברית (3-4 משפטים)",
  "urgency_score": 8
}}"""


def predict_price(item: dict, history: list[dict]) -> Optional[dict]:
    """
    Predict whether price will go up or down.
    Returns prediction dict or None if not enough data.
    """
    if len(history) < 3:
        return None

    prices = [r["price"] for r in history]
    avg = sum(prices) / len(prices)
    current = prices[0]

    history_str = "\n".join(
        f"  {r['checked_at'][:16]}: {r['price']:.0f} {r['currency']}"
        for r in history[:15]
    )

    dates = ""
    if item.get("date_from"):
        dates = item["date_from"]
        if item.get("date_to"):
            dates += f" → {item['date_to']}"

    prompt = PREDICTION_PROMPT.format(
        name=item["name"],
        category=item["category"],
        destination=item["destination"],
        dates=dates or "לא צוין",
        history=history_str,
        avg=avg,
        min_p=min(prices),
        max_p=max(prices),
        current=current,
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )

        text = "".join(b.text for b in response.content if b.type == "text")

        import re
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group(0))
            result["analyzed_at"] = datetime.now().isoformat()
            result["current_price"] = current
            return result

    except Exception as e:
        return {"error": str(e), "reasoning": "שגיאה בניתוח"}

    return None


def format_prediction(pred: dict) -> dict:
    """Format prediction for display."""
    if not pred or "error" in pred:
        return {"text": "לא ניתן לנתח", "color": "gray", "icon": "❓"}

    trend = pred.get("trend", "stable")
    rec = pred.get("recommendation", "fair_price")
    confidence = pred.get("confidence", "low")

    icons = {"rising": "📈", "falling": "📉", "stable": "➡️"}
    colors = {"buy_now": "green", "wait": "orange", "fair_price": "blue"}
    rec_text = {
        "buy_now": "🔥 קנה עכשיו!",
        "wait": "⏳ המתן",
        "fair_price": "✅ מחיר הוגן",
    }
    conf_text = {"high": "ביטחון גבוה", "medium": "ביטחון בינוני", "low": "ביטחון נמוך"}

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
