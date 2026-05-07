import os
"""
Personal Price DNA — הדפוסים האישיים שלך במחירי טיסות.
מנתח את כל ההיסטוריה שלך ובונה פרופיל: מתי זול, מתי יקר, מה התבנית.
"""
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import ai_client

_lang = "he"

DB_PATH = Path(__file__).parent / "prices.db"


def _load_all_history() -> list:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT ph.price, ph.currency, ph.checked_at,
                       wi.origin, wi.destination, wi.name
                FROM price_history ph
                JOIN watch_items wi ON ph.watch_id = wi.id
                ORDER BY ph.checked_at DESC
            """).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def generate_price_dna(watch_id: int = None) -> dict:
    """
    בנה DNA מחירים מלא — ניתוח סטטיסטי + AI.
    watch_id=None → כל ההיסטוריה.
    """
    if watch_id:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT ph.*, wi.origin, wi.destination, wi.name
                FROM price_history ph
                JOIN watch_items wi ON ph.watch_id = wi.id
                WHERE ph.watch_id = ?
                ORDER BY ph.checked_at DESC
            """, (watch_id,)).fetchall()
        history = [dict(r) for r in rows]
    else:
        history = _load_all_history()

    if len(history) < 5:
        return {"error": "Need at least 5 price checks to analyze" if _lang == "en" else "צריך לפחות 5 בדיקות מחיר לניתוח"}

    prices = [r["price"] for r in history]
    currency = history[0].get("currency", "USD")

    # Seasonal patterns
    monthly = defaultdict(list)
    weekly = defaultdict(list)
    hourly = defaultdict(list)
    dow_map = (
        {"Monday": "Monday", "Tuesday": "Tuesday", "Wednesday": "Wednesday",
         "Thursday": "Thursday", "Friday": "Friday", "Saturday": "Saturday", "Sunday": "Sunday"}
        if _lang == "en" else
        {"Monday": "שני", "Tuesday": "שלישי", "Wednesday": "רביעי",
         "Thursday": "חמישי", "Friday": "שישי", "Saturday": "שבת", "Sunday": "ראשון"}
    )

    month_he = (
        {1: "January", 2: "February", 3: "March", 4: "April",
         5: "May", 6: "June", 7: "July", 8: "August",
         9: "September", 10: "October", 11: "November", 12: "December"}
        if _lang == "en" else
        {1: "ינואר", 2: "פברואר", 3: "מרץ", 4: "אפריל",
         5: "מאי", 6: "יוני", 7: "יולי", 8: "אוגוסט",
         9: "ספטמבר", 10: "אוקטובר", 11: "נובמבר", 12: "דצמבר"}
    )

    for r in history:
        try:
            dt = datetime.fromisoformat(r["checked_at"][:19])
            monthly[month_he[dt.month]].append(r["price"])
            weekly[dow_map.get(dt.strftime("%A"), dt.strftime("%A"))].append(r["price"])
            hourly[dt.hour].append(r["price"])
        except Exception:
            pass

    # Compute averages
    month_avg = {m: sum(p)/len(p) for m, p in monthly.items() if p}
    week_avg = {d: sum(p)/len(p) for d, p in weekly.items() if p}
    hour_avg = {h: sum(p)/len(p) for h, p in hourly.items() if p}

    best_month = min(month_avg, key=month_avg.get) if month_avg else None
    worst_month = max(month_avg, key=month_avg.get) if month_avg else None
    best_dow = min(week_avg, key=week_avg.get) if week_avg else None
    best_hour = min(hour_avg, key=hour_avg.get) if hour_avg else None

    # Price trajectory (last 30 checks)
    recent = prices[:30]
    trend = "stable"
    if len(recent) >= 3:
        first_half = sum(recent[len(recent)//2:]) / (len(recent)//2)
        second_half = sum(recent[:len(recent)//2]) / (len(recent)//2)
        chg = (second_half - first_half) / first_half * 100
        trend = "rising" if chg > 3 else ("falling" if chg < -3 else "stable")

    # Volatility
    if len(prices) >= 2:
        import statistics
        volatility = statistics.stdev(prices) / (sum(prices)/len(prices)) * 100
    else:
        volatility = 0

    # Price buckets (distribution)
    min_p, max_p = min(prices), max(prices)
    bucket_size = (max_p - min_p) / 5 if max_p > min_p else 1
    buckets = defaultdict(int)
    for p in prices:
        bucket = int((p - min_p) / bucket_size)
        buckets[min(bucket, 4)] += 1

    return {
        "total_checks": len(history),
        "price_range": {"min": min_p, "max": max_p, "avg": sum(prices)/len(prices)},
        "currency": currency,
        "current_price": prices[0],
        "trend": trend,
        "volatility_pct": round(volatility, 1),
        "best_month": best_month,
        "worst_month": worst_month,
        "best_day_of_week": best_dow,
        "best_hour": best_hour,
        "month_avg": {m: round(v, 0) for m, v in sorted(month_avg.items())},
        "week_avg": {d: round(v, 0) for d, v in week_avg.items()},
        "hour_avg": {f"{h:02d}:00": round(v, 0) for h, v in sorted(hour_avg.items())},
        "potential_savings": round(max_p - min_p, 0),
        "potential_savings_pct": round((max_p - min_p) / max_p * 100, 1) if max_p else 0,
        "price_now_vs_avg": round((prices[0] - sum(prices)/len(prices)) / (sum(prices)/len(prices)) * 100, 1),
    }


def get_ai_price_dna(watch_id: int = None) -> dict:
    """AI מנתח את ה-DNA ומוציא insights אישיים."""
    dna = generate_price_dna(watch_id)
    if "error" in dna:
        return dna

    if not ai_client.is_configured():
        return {"error": "missing_api_key", "reason": "GEMINI_API_KEY not configured"}

    prompt = f"""נתח את ה-DNA המחירי הזה ותן המלצות אישיות:

{json.dumps(dna, ensure_ascii=False, indent=2)}

ספק:
1. מה הדפוס המרכזי? (מתי כדאי לקנות)
2. האם המחיר הנוכחי טוב?
3. מה ה-sweet spot להזמנה?
4. תחזית לחודשיים הקרובים
5. פעולות קונקרטיות שכדאי לעשות עכשיו

החזר JSON:
{{
  "verdict": "קנה עכשיו / המתן / מחיר הוגן",
  "verdict_emoji": "🟢/🔴/🟡",
  "confidence": "גבוה/בינוני/נמוך",
  "main_pattern": "תיאור הדפוס המרכזי",
  "best_booking_window": "מתי הכי כדאי",
  "forecast_2months": "תחזית בהתבסס על עונתיות",
  "actions": ["פעולה 1", "פעולה 2"],
  "savings_tip": "איך לחסוך מקסימום",
  "price_now_assessment": "יקר/זול/הוגן ביחס לממוצע"
}}"""

    try:
        text = ai_client.ask(
            prompt=prompt,
            system="You are a flight price analyst. Analyze patterns and give data-driven recommendations." + (" Respond in English. Use English for all text fields in the JSON." if _lang == "en" else ""),
            max_tokens=1500,
        )
        if text:
            result = ai_client.extract_json(text)
            if result and "found" not in result:
                result["dna"] = dna
                return result
    except Exception as e:
        return {"error": str(e), "dna": dna}
    return {"dna": dna}


def find_personal_sweet_spot(watch_id: int) -> dict:
    """
    מה ה-sweet spot האישי שלך — כמה שבועות לפני הטיסה הכי כדאי לקנות?
    מבוסס על ההיסטוריה שלך בפועל.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            item = conn.execute(
                "SELECT * FROM watch_items WHERE id=?", (watch_id,)
            ).fetchone()
            history = conn.execute("""
                SELECT price, checked_at FROM price_history
                WHERE watch_id=? ORDER BY checked_at
            """, (watch_id,)).fetchall()

        if not item or len(history) < 5:
            return {}

        prices = [r["price"] for r in history]
        dates = [datetime.fromisoformat(r["checked_at"][:19]) for r in history]

        # Find the minimum price date
        min_idx = prices.index(min(prices))
        min_date = dates[min_idx]

        # If we know the travel date
        travel_date_str = dict(item).get("date_from", "")
        if travel_date_str:
            try:
                travel_dt = datetime.fromisoformat(travel_date_str[:10])
                days_before = (travel_dt - min_date).days
                weeks_before = days_before // 7
                return {
                    "min_price": prices[min_idx],
                    "min_price_date": min_date.strftime("%d/%m/%Y"),
                    "days_before_travel": days_before,
                    "weeks_before_travel": weeks_before,
                    "sweet_spot": f"{weeks_before} {'weeks before the flight' if _lang == 'en' else 'שבועות לפני הטיסה'}",
                    "current_price": prices[-1],
                    "is_past_sweet_spot": datetime.now() > min_date,
                }
            except Exception:
                pass

        # Without travel date — find lowest in first/mid/late period
        n = len(prices)
        thirds = [
            ("Early (4+ months)" if _lang == "en" else "מוקדם (4+ חודשים)", min(prices[:n//3])),
            ("Mid (2-4 months)" if _lang == "en" else "אמצע (2-4 חודשים)", min(prices[n//3:2*n//3])),
            ("Late (0-2 months)" if _lang == "en" else "מאוחר (0-2 חודשים)", min(prices[2*n//3:])),
        ]
        best_period = min(thirds, key=lambda x: x[1])
        return {
            "best_period": best_period[0],
            "best_period_price": best_period[1],
            "all_periods": {t[0]: t[1] for t in thirds},
            "min_price": min(prices),
            "max_price": max(prices),
        }
    except Exception as e:
        return {"error": str(e)}
