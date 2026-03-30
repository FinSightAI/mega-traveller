"""
Kiwi / Tequila API Client — חיפוש טיסות עם מחירים אמיתיים.
מחזיר nomad fares, virtual interlining, מסלולים יצירתיים שGoogle Flights מפספס.
API Key: https://tequila.kiwi.com (חינמי עד 1000 req/day)
"""
import json
import os
import re
import urllib.request
import urllib.parse
from datetime import datetime
import ai_client

TEQUILA_BASE = "https://api.tequila.kiwi.com/v2"


def search_flights(
    origin: str,
    destination: str,
    date_from: str,
    date_to: str = "",
    return_from: str = "",
    return_to: str = "",
    adults: int = 1,
    max_stopovers: int = 2,
    currency: str = "USD",
    limit: int = 10,
    only_working_days: bool = False,
    price_to: int = 0,
) -> list:
    """
    מחפש טיסות דרך Kiwi Tequila API.
    אם אין API key — fallback ל-Claude web_search.
    """
    api_key = os.environ.get("KIWI_API_KEY", "")

    if api_key:
        return _search_tequila(
            api_key, origin, destination, date_from, date_to,
            return_from, return_to, adults, max_stopovers, currency, limit, price_to
        )
    else:
        return _search_claude(
            origin, destination, date_from, date_to,
            return_from, return_to, adults, currency
        )


def _search_tequila(api_key, origin, destination, date_from, date_to,
                     return_from, return_to, adults, max_stopovers, currency, limit, price_to):
    params = {
        "fly_from": origin,
        "fly_to": destination,
        "date_from": _fmt_date(date_from),
        "date_to": _fmt_date(date_to or date_from),
        "adults": adults,
        "max_stopovers": max_stopovers,
        "curr": currency,
        "limit": limit,
        "sort": "price",
        "asc": 1,
    }
    if return_from:
        params["return_from"] = _fmt_date(return_from)
        params["return_to"] = _fmt_date(return_to or return_from)
    if price_to:
        params["price_to"] = price_to

    url = f"{TEQUILA_BASE}/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"apikey": api_key})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return [{"error": str(e)}]

    results = []
    for flight in data.get("data", []):
        routes = flight.get("route", [])
        airlines = list({r.get("airline", "") for r in routes})
        results.append({
            "price": flight.get("price", 0),
            "currency": currency,
            "origin": flight.get("flyFrom", ""),
            "destination": flight.get("flyTo", ""),
            "departure": flight.get("local_departure", "")[:16],
            "arrival": flight.get("local_arrival", "")[:16],
            "duration_hours": round(flight.get("duration", {}).get("total", 0) / 3600, 1),
            "stops": len(routes) - 1,
            "airlines": airlines,
            "airline": airlines[0] if airlines else "",
            "booking_token": flight.get("booking_token", ""),
            "deep_link": flight.get("deep_link", ""),
            "nights_in_dest": flight.get("nightsInDest"),
            "quality": flight.get("quality", 0),
        })
    return results


def _search_claude(origin, destination, date_from, date_to, return_from, return_to, adults, currency):
    ret_info = f"\nתאריך חזרה: {return_from}" if return_from else ""
    prompt = f"""חפש טיסות ב-Kiwi.com ו-Google Flights:

מסלול: {origin} → {destination}
תאריך: {date_from}{(' עד ' + date_to) if date_to else ''}{ret_info}
נוסעים: {adults}
מטבע: {currency}

מצא את 5 האפשרויות הזולות ביותר. כלול גם virtual interlining ומסלולים יצירתיים.

לכל טיסה החזר JSON:
{{
  "price": 000, "currency": "{currency}",
  "origin": "{origin}", "destination": "{destination}",
  "departure": "YYYY-MM-DD HH:MM", "arrival": "YYYY-MM-DD HH:MM",
  "duration_hours": 0.0, "stops": 0,
  "airline": "שם חברה", "airlines": ["חברה1"],
  "deep_link": "", "notes": ""
}}

החזר JSON array."""

    try:
        text = ai_client.ask_with_search(prompt=prompt, max_tokens=2000)
        if text:
            return ai_client.extract_json_array(text)
    except Exception as e:
        return [{"error": str(e)}]
    return []


def book_flight(booking_token: str, passengers: list, currency: str = "USD") -> dict:
    """
    יצירת הזמנה דרך Tequila API.
    passengers = [{"name": "...", "surname": "...", "dob": "YYYY-MM-DD", ...}]
    """
    api_key = os.environ.get("KIWI_API_KEY", "")
    if not api_key:
        return {"error": "נדרש KIWI_API_KEY"}

    url = f"{TEQUILA_BASE}/booking"
    payload = {
        "booking_token": booking_token,
        "currency": currency,
        "passengers": passengers,
        "locale": "he",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"apikey": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _fmt_date(d: str) -> str:
    """Convert YYYY-MM-DD to DD/MM/YYYY for Tequila API."""
    if not d:
        return ""
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return d


def get_cheapest_month(origin: str, destination: str, year_month: str = "") -> list:
    """מצא את הימים הזולים ביותר בחודש."""
    from datetime import date, timedelta
    if not year_month:
        year_month = datetime.now().strftime("%Y-%m")
    year, month = map(int, year_month.split("-"))

    # Build date range
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    return search_flights(
        origin=origin,
        destination=destination,
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        limit=20,
    )
