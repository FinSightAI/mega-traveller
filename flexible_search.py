"""
Flexible date search — מצא את היום/שבוע הכי זול לטוס.
משתמש ב-Amadeus Fare Calendar ו-Claude לניתוח.
"""
import os
from datetime import datetime, timedelta
from typing import Optional

import amadeus_client


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
        # Fallback: use Claude to estimate (less accurate)
        results = _claude_estimate_month(origin, destination, month, trip_duration)

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


def _claude_estimate_month(
    origin: str, destination: str, month: str, duration: int
) -> list[dict]:
    """Fallback: ask Claude to estimate cheapest dates."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        prompt = (
            f"מתי הכי זול לטוס מ-{origin} ל-{destination} בחודש {month}? "
            f"טיול של {duration} ימים.\n"
            "תן 5 תאריכים עם הערכת מחיר בדולרים.\n"
            "החזר JSON: [{\"date\": \"YYYY-MM-DD\", \"price\": 000, \"currency\": \"USD\", "
            "\"details\": \"הסבר קצר\", \"deal_quality\": \"good\"}]"
        )
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=512,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        import json, re
        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            return json.loads(arr.group(0))
    except Exception:
        pass
    return []
