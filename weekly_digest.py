"""
Weekly Digest — סיכום שבועי חכם.
מייצר סיכום של ירידות מחיר, דילים, והמלצות לשבוע הבא.
שולח דרך כל ערוצי ההתראה המוגדרים.
"""
import json
from datetime import datetime, timedelta
import database as db
import ai_client
import notifiers


def generate_digest(lang: str = "he") -> dict:
    """
    Generate a weekly digest with price movements, top deals, and recommendations.
    Returns dict with: subject, summary, top_deals, price_movements, recommendations, raw_text
    """
    if not ai_client.is_configured():
        return {"error": "GEMINI_API_KEY not configured"}

    # Gather data from the last 7 days
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    items = db.get_all_watch_items(enabled_only=False)

    watch_summary = []
    for item in items[:15]:  # limit to 15 items
        history = db.get_price_history(item["id"], limit=10)
        if not history:
            continue
        prices = [r["price"] for r in history]
        latest = prices[0]
        oldest = prices[-1]
        change = ((latest - oldest) / oldest * 100) if oldest else 0
        watch_summary.append({
            "name": item["name"],
            "destination": item["destination"],
            "category": item["category"],
            "current_price": latest,
            "currency": history[0].get("currency", "USD"),
            "change_pct": round(change, 1),
            "max_price": item.get("max_price"),
            "records": len(history),
        })

    # Recent deals found
    try:
        import deal_hunter
        recent_deals = deal_hunter.get_top_deals_today(limit=5)
    except Exception:
        recent_deals = []

    prompt = f"""Create a weekly travel price digest in {'Hebrew' if lang == 'he' else 'English'}.

Watch items and price changes this week:
{json.dumps(watch_summary, ensure_ascii=False, indent=2)}

Top deals found recently:
{json.dumps([{k: v for k, v in d.items() if k in ['destination','price','currency','deal_type','why_amazing']} for d in recent_deals[:3]], ensure_ascii=False, indent=2)}

Create a digest with:
1. Executive summary (2-3 sentences)
2. Top 3 price movements (biggest drops)
3. Best deal of the week
4. 2-3 actionable recommendations for next week

Return JSON:
{{
  "subject": "email/notification subject line",
  "summary": "2-3 sentence executive summary",
  "top_movements": [
    {{"name": "...", "change_pct": -15.5, "current_price": 250, "currency": "USD", "verdict": "כדאי לקנות עכשיו"}}
  ],
  "best_deal": {{"destination": "...", "price": 0, "currency": "USD", "why": "..."}},
  "recommendations": ["המלצה 1", "המלצה 2"],
  "emoji_summary": "one line with emojis summarizing the week"
}}"""

    try:
        text = ai_client.ask(prompt=prompt, max_tokens=1500)
        if not text:
            return {"error": "No AI response"}
        match = __import__('re').search(r'\{.*\}', text, __import__('re').DOTALL)
        if not match:
            return {"error": "Could not parse digest", "raw_text": text}
        result = json.loads(match.group(0))
        result["generated_at"] = datetime.now().isoformat()
        result["raw_text"] = text
        return result
    except Exception as e:
        return {"error": str(e)}


def send_digest(lang: str = "he") -> dict:
    """
    Generate and send the weekly digest via all configured channels.
    Returns dict with send results per channel.
    """
    digest = generate_digest(lang=lang)
    if "error" in digest:
        return {"error": digest["error"]}

    subject = digest.get("subject", "📊 סיכום שבועי — Noded")

    # Build message body
    lines = [
        f"✈️ {digest.get('emoji_summary', '')}",
        "",
        digest.get("summary", ""),
        "",
    ]

    top = digest.get("top_movements", [])
    if top:
        lines.append("📊 תנועות מחיר:")
        for m in top[:3]:
            arrow = "📉" if m.get("change_pct", 0) < 0 else "📈"
            lines.append(f"  {arrow} {m.get('name','')} — {m.get('current_price',0):.0f} {m.get('currency','')} ({m.get('change_pct',0):+.1f}%)")
            if m.get("verdict"):
                lines.append(f"     → {m['verdict']}")

    best = digest.get("best_deal", {})
    if best:
        lines.append("")
        lines.append(f"🏆 דיל השבוע: {best.get('destination','')} — {best.get('price',0):.0f} {best.get('currency','')}")
        lines.append(f"   {best.get('why','')}")

    recs = digest.get("recommendations", [])
    if recs:
        lines.append("")
        lines.append("💡 המלצות לשבוע הבא:")
        for r in recs:
            lines.append(f"  • {r}")

    message = "\n".join(lines)

    results = notifiers.send_alert(title=subject, message=message)
    results["digest"] = digest
    return results
