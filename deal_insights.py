"""
Deal Insights & Pattern Learning — למד מהיסטוריית הדילים.
מנתח את ה-DB ומוצא דפוסים: מתי יוצאים דילים, לאיזה יעדים, באיזה שעות.
"""
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
import anthropic

DB_PATH = Path(__file__).parent / "prices.db"


def _get_db_stats() -> dict:
    """שולף סטטיסטיקות גולמיות מה-DB."""
    stats = {
        "total_deals": 0,
        "by_destination": [],
        "by_airline": [],
        "by_day_of_week": defaultdict(list),
        "by_hour": defaultdict(list),
        "by_deal_type": Counter(),
        "avg_score": 0,
        "price_ranges": [],
        "recent_top": [],
    }

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            # Total
            row = conn.execute("SELECT COUNT(*) as c, AVG(score) as avg FROM deals").fetchone()
            if row:
                stats["total_deals"] = row["c"]
                stats["avg_score"] = round(row["avg"] or 0, 2)

            # By destination
            rows = conn.execute("""
                SELECT destination, COUNT(*) as cnt, AVG(price) as avg_price,
                       MIN(price) as min_price
                FROM deals GROUP BY destination ORDER BY cnt DESC LIMIT 10
            """).fetchall()
            stats["by_destination"] = [dict(r) for r in rows]

            # By airline
            rows = conn.execute("""
                SELECT airline, COUNT(*) as cnt, AVG(price) as avg_price
                FROM deals WHERE airline != ''
                GROUP BY airline ORDER BY cnt DESC LIMIT 8
            """).fetchall()
            stats["by_airline"] = [dict(r) for r in rows]

            # By day of week and hour
            rows = conn.execute(
                "SELECT found_at, price, score FROM deals WHERE found_at IS NOT NULL"
            ).fetchall()
            for row in rows:
                try:
                    dt = datetime.fromisoformat(row["found_at"][:19])
                    dow = dt.strftime("%A")  # Monday, Tuesday...
                    stats["by_day_of_week"][dow].append(row["score"] or 0)
                    stats["by_hour"][dt.hour].append(row["score"] or 0)
                except Exception:
                    pass

            # By deal type
            rows = conn.execute(
                "SELECT deal_type, COUNT(*) as cnt FROM deals GROUP BY deal_type"
            ).fetchall()
            for row in rows:
                stats["by_deal_type"][row["deal_type"]] = row["cnt"]

            # Recent top 5
            rows = conn.execute("""
                SELECT destination, price, currency, airline, deal_type, score,
                       discount_pct, found_at, why_amazing
                FROM deals ORDER BY score DESC, found_at DESC LIMIT 5
            """).fetchall()
            stats["recent_top"] = [dict(r) for r in rows]

    except Exception:
        pass

    return stats


def get_deal_patterns() -> dict:
    """
    מנתח דפוסים מהיסטוריית הדילים ומחזיר insights.
    """
    stats = _get_db_stats()

    if stats["total_deals"] == 0:
        return {"empty": True, "message": "אין עדיין דילים ב-DB. הפעל ציד דילים קודם."}

    # Best day of week
    day_avg = {
        day: sum(scores) / len(scores)
        for day, scores in stats["by_day_of_week"].items()
        if scores
    }
    best_day = max(day_avg, key=day_avg.get) if day_avg else None
    worst_day = min(day_avg, key=day_avg.get) if day_avg else None

    # Best hour
    hour_avg = {
        h: sum(scores) / len(scores)
        for h, scores in stats["by_hour"].items()
        if scores
    }
    best_hour = max(hour_avg, key=hour_avg.get) if hour_avg else None

    # Most deal-rich destination
    top_dest = stats["by_destination"][0]["destination"] if stats["by_destination"] else None

    day_names_he = {
        "Monday": "שני", "Tuesday": "שלישי", "Wednesday": "רביעי",
        "Thursday": "חמישי", "Friday": "שישי", "Saturday": "שבת", "Sunday": "ראשון"
    }

    return {
        "total_deals": stats["total_deals"],
        "avg_score": stats["avg_score"],
        "best_day": {
            "name": day_names_he.get(best_day, best_day),
            "avg_score": round(day_avg.get(best_day, 0), 2),
        } if best_day else None,
        "worst_day": {
            "name": day_names_he.get(worst_day, worst_day),
            "avg_score": round(day_avg.get(worst_day, 0), 2),
        } if worst_day else None,
        "best_hour": best_hour,
        "top_destinations": stats["by_destination"][:5],
        "top_airlines": stats["by_airline"][:5],
        "deal_types": dict(stats["by_deal_type"]),
        "recent_top": stats["recent_top"],
        "day_scores": {day_names_he.get(d, d): round(v, 2) for d, v in day_avg.items()},
        "hour_scores": {f"{h:02d}:00": round(v, 2) for h, v in sorted(hour_avg.items())},
    }


def get_ai_insights() -> dict:
    """
    שולח את הסטטיסטיקות ל-Claude לניתוח עמוק.
    מחזיר המלצות ואסטרטגיה.
    """
    stats = _get_db_stats()
    if stats["total_deals"] == 0:
        return {"error": "אין נתונים לניתוח"}

    client = anthropic.Anthropic()

    # Prepare compact summary for Claude
    summary = {
        "total_deals": stats["total_deals"],
        "avg_score": stats["avg_score"],
        "top_destinations": stats["by_destination"][:5],
        "top_airlines": stats["by_airline"][:5],
        "deal_types": dict(stats["by_deal_type"]),
        "recent_top": stats["recent_top"][:3],
    }

    prompt = f"""נתח את דפוסי הדילים הבאים מהמערכת שלי:

{json.dumps(summary, ensure_ascii=False, indent=2)}

תן:
1. מה הדפוסים הכי מעניינים שאתה רואה?
2. אילו יעדים מופיעים הכי הרבה ולמה?
3. אסטרטגיה: מה כדאי לי לעשות כדי לחסוך יותר?
4. מה חסר במעקב שלי (יעדים שכדאי להוסיף)?
5. מתי כדאי לבדוק דילים מחדש?

החזר JSON:
{{
  "key_patterns": ["דפוס 1", "דפוס 2", "דפוס 3"],
  "hot_destinations": ["יעד 1", "יעד 2"],
  "strategy": "אסטרטגיה מומלצת בפסקה",
  "add_to_watchlist": ["יעד לעקוב 1", "יעד לעקוב 2"],
  "best_scan_time": "מתי לסרוק",
  "savings_potential": "כמה % אפשר לחסוך",
  "action_items": ["פעולה 1", "פעולה 2", "פעולה 3"]
}}"""

    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            thinking={"type": "adaptive"},
            system="אתה אנליסט נסיעות. נתח דפוסי דילים ותן המלצות מעשיות.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        return {"error": str(e)}
    return {}


def get_price_history_stats(watch_id: int) -> dict:
    """סטטיסטיקות מחיר לפריט ספציפי."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT price, checked_at FROM price_history
                WHERE watch_id = ? ORDER BY checked_at DESC LIMIT 100
            """, (watch_id,)).fetchall()

        if not rows:
            return {}

        prices = [r["price"] for r in rows]
        dates = [r["checked_at"] for r in rows]

        # Weekly avg
        weekly = defaultdict(list)
        for r in rows:
            try:
                dt = datetime.fromisoformat(r["checked_at"][:19])
                week = dt.strftime("%Y-W%U")
                weekly[week].append(r["price"])
            except Exception:
                pass

        return {
            "min": min(prices),
            "max": max(prices),
            "avg": sum(prices) / len(prices),
            "current": prices[0],
            "total_checks": len(prices),
            "trend_7d": _calc_trend(prices[:7]),
            "trend_30d": _calc_trend(prices[:30]),
            "weekly_avg": {w: sum(p) / len(p) for w, p in sorted(weekly.items())[-8:]},
            "best_month": _find_best_month(rows),
        }
    except Exception:
        return {}


def _calc_trend(prices: list) -> str:
    if len(prices) < 2:
        return "stable"
    change = (prices[0] - prices[-1]) / prices[-1] * 100
    if change > 3:
        return "rising"
    elif change < -3:
        return "falling"
    return "stable"


def _find_best_month(rows: list) -> str:
    monthly = defaultdict(list)
    for r in rows:
        try:
            dt = datetime.fromisoformat(r["checked_at"][:19])
            monthly[dt.strftime("%B")].append(r["price"])
        except Exception:
            pass
    if not monthly:
        return ""
    best = min(monthly, key=lambda m: sum(monthly[m]) / len(monthly[m]))
    month_he = {
        "January": "ינואר", "February": "פברואר", "March": "מרץ",
        "April": "אפריל", "May": "מאי", "June": "יוני",
        "July": "יולי", "August": "אוגוסט", "September": "ספטמבר",
        "October": "אוקטובר", "November": "נובמבר", "December": "דצמבר",
    }
    return month_he.get(best, best)
