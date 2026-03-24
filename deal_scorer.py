"""
Deal Scorer — מערכת ניקוד חכמה לדילים.
מדרגת כל דיל 0-10 עם הסבר + שולחת התראה רק על הדילים שבאמת שווים.
"""
import json
from datetime import datetime
import anthropic


SCORE_PROMPT = """דרג את הדיל הבא בסקלה של 0-10 ותן ניתוח מפורט.

דיל:
- יעד: {destination}
- מחיר: {price} {currency}
- קטגוריה: {category}
- פרטים: {details}
- מקור: {source}

קריטריונים לניקוד:
• מחיר (0-4 נקודות): כמה זול ביחס לממוצע השוק?
• נדירות (0-2 נקודות): כמה קל למצוא דיל כזה?
• יעד (0-2 נקודות): כמה יעד פופולרי/מבוקש?
• תזמון (0-2 נקודות): האם הזמן מתאים? עונה?

החזר JSON:
{{
  "score": 8.5,
  "grade": "A+" / "A" / "B" / "C" / "D",
  "price_score": 3.5,
  "rarity_score": 1.5,
  "destination_score": 2.0,
  "timing_score": 1.5,
  "verdict": "🔥 דיל מטורף! / ✅ דיל טוב / ⚠️ סביר / ❌ לא שווה",
  "why": "הסבר בעברית",
  "action": "קנה עכשיו! / שקול / המתן לטוב יותר",
  "expires_soon": true/false,
  "comparable_price": 000,
  "saving_vs_normal": 000
}}"""


def score_deal(deal: dict) -> dict:
    """Score a single deal using Claude AI."""
    client = anthropic.Anthropic()
    prompt = SCORE_PROMPT.format(
        destination=deal.get("destination", ""),
        price=deal.get("price", 0),
        currency=deal.get("currency", "USD"),
        category=deal.get("category", deal.get("deal_type", "flight")),
        details=deal.get("details", deal.get("why_amazing", "")),
        source=deal.get("source", ""),
    )

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"score": 5.0, "verdict": "לא ניתן לנתח", "error": str(e)}
    return {}


def score_and_filter(deals: list[dict], min_score: float = 7.0) -> list[dict]:
    """Score all deals and return only those above min_score."""
    results = []
    for deal in deals:
        score_data = score_deal(deal)
        deal["ai_score"] = score_data.get("score", 0)
        deal["ai_verdict"] = score_data.get("verdict", "")
        deal["ai_action"] = score_data.get("action", "")
        deal["ai_why"] = score_data.get("why", "")
        deal["ai_grade"] = score_data.get("grade", "")
        deal["saving_vs_normal"] = score_data.get("saving_vs_normal", 0)
        if deal["ai_score"] >= min_score:
            results.append(deal)

    results.sort(key=lambda x: x["ai_score"], reverse=True)
    return results


DEAL_EMOJI = {
    "A+": "🔥🔥🔥",
    "A":  "🔥🔥",
    "B":  "✅",
    "C":  "⚠️",
    "D":  "❌",
}


def format_deal_alert(deal: dict) -> str:
    """Format a deal as an alert message."""
    grade = deal.get("ai_grade", "")
    emoji = DEAL_EMOJI.get(grade, "💰")
    lines = [
        f"{emoji} דיל {grade}: {deal.get('destination', '')}",
        f"💲 {deal.get('price', 0):.0f} {deal.get('currency', '')}",
    ]
    if deal.get("saving_vs_normal"):
        lines.append(f"💸 חיסכון: {deal['saving_vs_normal']:.0f}$")
    if deal.get("ai_why"):
        lines.append(f"💡 {deal['ai_why']}")
    if deal.get("ai_action"):
        lines.append(f"👉 {deal['ai_action']}")
    if deal.get("book_url"):
        lines.append(f"🔗 {deal['book_url']}")
    return "\n".join(lines)
