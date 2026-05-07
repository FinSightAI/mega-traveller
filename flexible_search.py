"""
Flexible date search — מצא את היום/שבוע הכי זול לטוס.
משתמש ב-Amadeus Fare Calendar ו-AI לניתוח.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

import amadeus_client
import ai_client


def search_cheapest_days(
    origin: str,
    destination: str,
    month: str,          # "2026-05"
    trip_duration: int = 7,
    top_n: int = 5,
) -> list[dict]:
    """
    Search all departure dates in a month and return the cheapest options.
    Returns list sorted by price.
    """
    year, mon = map(int, month.split("-"))
    # Build list of dates in the month
    start = datetime(year, mon, 1)
    end = datetime(year, mon + 1, 1) if mon < 12 else datetime(year + 1, 1, 1)

    dates = []
    d = start
    while d < end:
        dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    results = []

    if amadeus_client.is_configured():
        # Use Amadeus for accurate pricing
        for dep_date in dates:
            ret_date = (
                datetime.strptime(dep_date, "%Y-%m-%d") + timedelta(days=trip_duration)
            ).strftime("%Y-%m-%d")

            flights = amadeus_client.search_flights(
                origin=origin,
                destination=destination,
                departure_date=dep_date,
                return_date=ret_date,
                max_results=1,
            )
            if flights:
                best = flights[0]
                results.append({
                    "date": dep_date,
                    "return_date": ret_date,
                    "price": best["price"],
                    "currency": best["currency"],
                    "details": best.get("details", ""),
                    "deal_quality": best.get("deal_quality", ""),
                })
    else:
        # Fallback: use AI to estimate (less accurate)
        results = _ai_estimate_month(origin, destination, month, trip_duration)

    results.sort(key=lambda x: x["price"])
    return results[:top_n]


def get_price_calendar(
    origin: str,
    destination: str,
    month: str,
) -> dict[str, Optional[float]]:
    """
    Return a dict of date → price for the entire month.
    Used to render the calendar heatmap.
    """
    year, mon = map(int, month.split("-"))
    start = datetime(year, mon, 1)
    end = datetime(year, mon + 1, 1) if mon < 12 else datetime(year + 1, 1, 1)

    calendar = {}
    d = start
    while d < end:
        calendar[d.strftime("%Y-%m-%d")] = None
        d += timedelta(days=1)

    if not amadeus_client.is_configured():
        return calendar

    for date_str in list(calendar.keys()):
        flights = amadeus_client.search_flights(
            origin=origin,
            destination=destination,
            departure_date=date_str,
            max_results=1,
        )
        if flights:
            calendar[date_str] = flights[0]["price"]

    return calendar


def _ai_estimate_month(
    origin: str, destination: str, month: str, duration: int
) -> list[dict]:
    """Fallback: ask AI to estimate cheapest dates."""
    try:
        prompt = (
            f"מתי הכי זול לטוס מ-{origin} ל-{destination} בחודש {month}? "
            f"טיול של {duration} ימים.\n"
            "תן 5 תאריכים עם הערכת מחיר בדולרים.\n"
            "החזר JSON: [{\"date\": \"YYYY-MM-DD\", \"price\": 000, \"currency\": \"USD\", "
            "\"details\": \"הסבר קצר\", \"deal_quality\": \"good\"}]"
        )
        text = ai_client.ask_with_search(prompt=prompt, max_tokens=512)
        if text:
            return ai_client.extract_json_array(text)
    except Exception:
        pass
    return []


def search_around_date(
    origin: str,
    destination: str,
    date: str,          # "YYYY-MM-DD" — the center date
    window: int = 3,    # ±N days
    adults: int = 1,
    currency: str = "USD",
) -> list[dict]:
    """
    Search ±window days around a specific date and return sorted by price.
    E.g. date="2026-05-15", window=3 → checks May 12–18 (7 dates).
    """
    from datetime import datetime, timedelta
    base = datetime.strptime(date[:10], "%Y-%m-%d")
    dates = [
        (base + timedelta(days=delta)).strftime("%Y-%m-%d")
        for delta in range(-window, window + 1)
    ]

    results = []

    if amadeus_client.is_configured():
        for dep_date in dates:
            flights = amadeus_client.search_flights(
                origin=origin,
                destination=destination,
                departure_date=dep_date,
                max_results=1,
            )
            if flights:
                best = flights[0]
                delta_days = (datetime.strptime(dep_date, "%Y-%m-%d") - base).days
                results.append({
                    "date": dep_date,
                    "price": best["price"],
                    "currency": best.get("currency", currency),
                    "details": best.get("details", ""),
                    "deal_quality": best.get("deal_quality", ""),
                    "delta_days": delta_days,
                    "label": ("📌 בקשתך" if delta_days == 0 else
                              f"{'➕' if delta_days > 0 else '➖'}{abs(delta_days)}d"),
                })
    else:
        # AI fallback
        dates_str = ", ".join(dates)
        prompt = (
            f"חפש מחירי טיסות מ-{origin} ל-{destination} בתאריכים: {dates_str}.\n"
            f"לכל תאריך תן את המחיר הזול ביותר.\n"
            "החזר JSON array:\n"
            '[{"date": "YYYY-MM-DD", "price": 0, "currency": "USD", "details": "", "deal_quality": "good"}]'
        )
        try:
            text = ai_client.ask_with_search(prompt=prompt, max_tokens=800)
            if text:
                raw = ai_client.extract_json_array(text)
                for i, r in enumerate(raw):
                    if r.get("date") and r.get("price"):
                        dep_date = r["date"]
                        try:
                            delta_days = (datetime.strptime(dep_date, "%Y-%m-%d") - base).days
                        except Exception:
                            delta_days = i - window
                        r["delta_days"] = delta_days
                        r["label"] = ("📌 בקשתך" if delta_days == 0 else
                                      f"{'➕' if delta_days > 0 else '➖'}{abs(delta_days)}d")
                        results.append(r)
        except Exception:
            pass

    results.sort(key=lambda x: x.get("price", 999_999))
    return results
