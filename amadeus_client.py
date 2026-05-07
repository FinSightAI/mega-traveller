"""
Amadeus API client — הAPI הרשמי של חברות תעופה ומלונות.
מספק מחירי טיסות ומלונות מדויקים ב-real-time.

הרשמה חינמית: https://developers.amadeus.com
"""
import os
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)

# City name → IATA code (נסיעות נפוצות מישראל)
CITY_TO_IATA = {
    # ישראל
    "תל אביב": "TLV", "tlv": "TLV", "tel aviv": "TLV",
    "ירושלים": "TLV",  # nearest airport
    # אירופה
    "לונדון": "LON", "london": "LON",
    "פריז": "CDG", "paris": "CDG",
    "ברצלונה": "BCN", "barcelona": "BCN",
    "מדריד": "MAD", "madrid": "MAD",
    "רומא": "FCO", "rome": "FCO",
    "מילאנו": "MXP", "milan": "MXP",
    "אמסטרדם": "AMS", "amsterdam": "AMS",
    "ברלין": "BER", "berlin": "BER",
    "וינה": "VIE", "vienna": "VIE",
    "פראג": "PRG", "prague": "PRG",
    "בודפשט": "BUD", "budapest": "BUD",
    "ורשה": "WAW", "warsaw": "WAW",
    "אתונה": "ATH", "athens": "ATH",
    "ליסבון": "LIS", "lisbon": "LIS",
    "דובאי": "DXB", "dubai": "DXB",
    "איסטנבול": "IST", "istanbul": "IST",
    "ניקוסיה": "LCA", "לרנקה": "LCA",
    "קפריסין": "LCA",
    # אסיה
    "בנגקוק": "BKK", "bangkok": "BKK",
    "טוקיו": "TYO", "tokyo": "TYO",
    "בייג'ינג": "PEK", "beijing": "PEK",
    "סינגפור": "SIN", "singapore": "SIN",
    "מומבאי": "BOM", "mumbai": "BOM",
    # אמריקה
    "ניו יורק": "JFK", "new york": "JFK",
    "לוס אנג'לס": "LAX", "los angeles": "LAX",
    "מיאמי": "MIA", "miami": "MIA",
    "שיקגו": "ORD", "chicago": "ORD",
    # אפריקה
    "קהיר": "CAI", "cairo": "CAI",
    "קיב": "KBP", "kyiv": "KBP",
}


def _to_iata(city: str) -> Optional[str]:
    """Convert city name to IATA code."""
    if not city:
        return None
    c = city.strip().lower()
    # Direct match
    code = CITY_TO_IATA.get(c)
    if code:
        return code
    # If it's already a 3-letter code
    if len(city.strip()) == 3 and city.strip().isupper():
        return city.strip()
    # Partial match
    for key, val in CITY_TO_IATA.items():
        if c in key or key in c:
            return val
    return None


def _get_amadeus():
    """Create Amadeus client from env vars. Returns None if not configured."""
    key = os.environ.get("AMADEUS_CLIENT_ID", "")
    secret = os.environ.get("AMADEUS_CLIENT_SECRET", "")
    if not key or not secret:
        return None
    try:
        from amadeus import Client, ResponseError
        return Client(
            client_id=key,
            client_secret=secret,
            # hostname="production"  # uncomment for production
        )
    except Exception as e:
        logger.warning(f"Amadeus init failed: {e}")
        return None


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,        # YYYY-MM-DD
    return_date: Optional[str] = None,
    adults: int = 1,
    max_results: int = 5,
) -> list[dict]:
    """
    Search flights via Amadeus Flight Offers Search API.
    Returns list of offer dicts, sorted by price.
    """
    amadeus = _get_amadeus()
    if not amadeus:
        return []

    origin_code = _to_iata(origin) or origin.upper()[:3]
    dest_code = _to_iata(destination) or destination.upper()[:3]

    try:
        from amadeus import ResponseError
        params = {
            "originLocationCode": origin_code,
            "destinationLocationCode": dest_code,
            "departureDate": departure_date,
            "adults": adults,
            "max": max_results,
            "currencyCode": "USD",
        }
        if return_date:
            params["returnDate"] = return_date

        response = amadeus.shopping.flight_offers_search.get(**params)
        offers = response.data

        results = []
        for offer in offers:
            price = float(offer["price"]["grandTotal"])
            currency = offer["price"]["currency"]

            # Extract flight info
            itineraries = offer.get("itineraries", [])
            segments = []
            for itin in itineraries:
                for seg in itin.get("segments", []):
                    segments.append({
                        "from": seg["departure"]["iataCode"],
                        "to": seg["arrival"]["iataCode"],
                        "carrier": seg.get("carrierCode", ""),
                        "depart": seg["departure"]["at"][:16],
                        "arrive": seg["arrival"]["at"][:16],
                        "duration": itin.get("duration", ""),
                    })

            # Airline names from first segment
            carrier = segments[0]["carrier"] if segments else ""
            stops = max(0, len(segments) - 2)
            stop_str = "ישיר" if stops == 0 else f"{stops} עצירות"

            details = (
                f"{carrier} | {stop_str} | "
                f"{departure_date}"
                + (f" → {return_date}" if return_date else "")
            )

            results.append({
                "found": True,
                "price": price,
                "currency": currency,
                "source": "Amadeus (רשמי)",
                "details": details,
                "deal_quality": _rate_flight_price(price, origin_code, dest_code),
                "notes": f"נמצאו {len(offers)} טיסות",
                "raw_segments": segments,
            })

        results.sort(key=lambda x: x["price"])
        return results

    except Exception as e:
        logger.warning(f"Amadeus flight search failed: {e}")
        return []


def search_hotels(
    city: str,
    check_in: str,    # YYYY-MM-DD
    check_out: str,   # YYYY-MM-DD
    adults: int = 2,
    max_results: int = 5,
) -> list[dict]:
    """
    Search hotels via Amadeus Hotel Search API.
    Returns list of offer dicts, sorted by price.
    """
    amadeus = _get_amadeus()
    if not amadeus:
        return []

    city_code = _to_iata(city) or city.upper()[:3]

    try:
        # Step 1: Get hotel list for city
        hotels_response = amadeus.reference_data.locations.hotels.by_city.get(
            cityCode=city_code
        )
        hotel_ids = [h["hotelId"] for h in hotels_response.data[:20]]

        if not hotel_ids:
            return []

        # Step 2: Get offers for those hotels
        offers_response = amadeus.shopping.hotel_offers_search.get(
            hotelIds=",".join(hotel_ids[:10]),
            checkInDate=check_in,
            checkOutDate=check_out,
            adults=adults,
            currencyCode="USD",
        )

        results = []
        for hotel_offer in offers_response.data[:max_results]:
            hotel = hotel_offer.get("hotel", {})
            offers = hotel_offer.get("offers", [])
            if not offers:
                continue

            best_offer = min(offers, key=lambda o: float(o["price"]["total"]))
            price = float(best_offer["price"]["total"])
            currency = best_offer["price"]["currency"]
            hotel_name = hotel.get("name", "מלון")
            rating = hotel.get("rating", "")
            stars = "⭐" * int(rating) if rating else ""

            nights = (
                datetime.strptime(check_out, "%Y-%m-%d") -
                datetime.strptime(check_in, "%Y-%m-%d")
            ).days
            per_night = price / nights if nights > 0 else price

            results.append({
                "found": True,
                "price": price,
                "currency": currency,
                "source": "Amadeus (רשמי)",
                "details": f"{hotel_name} {stars} | {per_night:.0f}/לילה | {nights} לילות",
                "deal_quality": _rate_hotel_price(per_night),
                "notes": f"סה\"כ {price:.0f} {currency} ל-{nights} לילות",
            })

        results.sort(key=lambda x: x["price"])
        return results

    except Exception as e:
        logger.warning(f"Amadeus hotel search failed: {e}")
        return []


def is_configured() -> bool:
    """Check if Amadeus credentials are set."""
    return bool(
        os.environ.get("AMADEUS_CLIENT_ID") and
        os.environ.get("AMADEUS_CLIENT_SECRET")
    )


def test_connection() -> dict:
    """Test Amadeus API connection. Returns status dict."""
    if not is_configured():
        return {"ok": False, "error": "לא מוגדר — הוסף AMADEUS_CLIENT_ID ו-AMADEUS_CLIENT_SECRET"}

    amadeus = _get_amadeus()
    if not amadeus:
        return {"ok": False, "error": "שגיאת אתחול"}

    try:
        # Simple test: search flights TLV→LON next month
        next_month = datetime.now().replace(day=1).strftime("%Y-%m-28")
        results = search_flights("TLV", "LON", next_month, max_results=1)
        if results:
            return {"ok": True, "message": f"✅ מחובר! דוגמה: {results[0]['price']} USD TLV→LON"}
        return {"ok": True, "message": "✅ מחובר (אין תוצאות לבדיקה)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _rate_flight_price(price: float, origin: str, dest: str) -> str:
    """Rate a flight price as excellent/good/average/poor."""
    # Rough benchmarks from TLV
    benchmarks = {
        ("TLV", "LON"): 400, ("TLV", "CDG"): 350, ("TLV", "BCN"): 320,
        ("TLV", "JFK"): 700, ("TLV", "BKK"): 600, ("TLV", "DXB"): 200,
        ("TLV", "ATH"): 200, ("TLV", "IST"): 150, ("TLV", "AMS"): 350,
    }
    benchmark = benchmarks.get((origin, dest), 400)
    ratio = price / benchmark
    if ratio < 0.7:
        return "excellent"
    elif ratio < 0.9:
        return "good"
    elif ratio < 1.2:
        return "average"
    return "poor"


def _rate_hotel_price(price_per_night: float) -> str:
    """Rate a hotel price per night."""
    if price_per_night < 60:
        return "excellent"
    elif price_per_night < 120:
        return "good"
    elif price_per_night < 200:
        return "average"
    return "poor"
