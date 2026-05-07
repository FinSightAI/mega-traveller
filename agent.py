"""
Price search agent — powered by Gemini (free tier) with Google Search.
Fallback: Amadeus API for flights/hotels.
"""
import os
import re
from datetime import datetime
from typing import Optional

import ai_client
import amadeus_client
import kiwi_client

_lang = "he"

SYSTEM_PROMPT = """You are a professional travel price agent. Find the best prices for flights, hotels, apartments and vacation packages.

When searching for a price:
1. Search the internet for current prices
2. Check multiple sources (Google Flights, Booking.com, Airbnb, Kayak, etc.)
3. Find the best available price

Always return valid JSON in this format:
{
  "found": true/false,
  "price": 123.45,
  "currency": "USD" / "ILS" / "EUR",
  "source": "website name",
  "details": "deal description",
  "deal_quality": "excellent" / "good" / "average" / "poor",
  "notes": "important notes"
}

If no price found, return {"found": false, "reason": "reason"}
Be accurate! Realistic prices only. Do not invent prices."""


def build_search_prompt(item: dict) -> str:
    category = item["category"]
    destination = item["destination"]
    origin = item.get("origin", "")
    date_from = item.get("date_from", "")
    date_to = item.get("date_to", "")
    custom_query = item.get("query", "")
    today = datetime.now().strftime("%Y-%m-%d")

    if custom_query:
        base = custom_query
    elif category == "flight":
        base = f"Flight from {origin} to {destination}"
        if date_from:
            base += f" on {date_from}"
        if date_to:
            base += f" return {date_to}"
    elif category == "hotel":
        base = f"Hotel in {destination}"
        if date_from:
            base += f" check-in {date_from}"
        if date_to:
            base += f" check-out {date_to}"
    elif category == "apartment":
        base = f"Apartment rental in {destination}"
        if date_from:
            base += f" from {date_from}"
        if date_to:
            base += f" to {date_to}"
    elif category == "package":
        base = f"Vacation package to {destination}"
        if origin:
            base += f" from {origin}"
        if date_from:
            base += f" {date_from}"
    else:
        base = f"Price for {destination}"

    lang_note = " Respond in English." if _lang == "en" else " השב בעברית."
    return (
        f"Find the best price for: {base}\n"
        f"(Check date: {today})\n\n"
        f"Search for realistic, current prices. "
        f"Check Google Flights, Booking.com, Airbnb, Kayak, Skyscanner, "
        f"and Israeli sites like Gulliver, Israir, Arkia.\n\n"
        f"Return JSON in the exact format specified.{lang_note}"
    )


def search_price(item: dict) -> dict:
    """Find current price. Strategy: Kiwi → Amadeus → Gemini AI fallback."""
    category = item["category"]
    destination = item["destination"]
    origin = item.get("origin", "TLV")
    date_from = item.get("date_from")
    date_to = item.get("date_to")
    travelers = item.get("travelers", 1)

    # ── 1. Kiwi Tequila API (real prices, flights only) ────────────────────────
    if category == "flight" and date_from and kiwi_client.is_configured():
        results = kiwi_client.search_flights(
            origin=origin,
            destination=destination,
            date_from=date_from,
            date_to=date_from,           # search window: same day
            return_from=date_to or "",
            return_to=date_to or "",
            adults=travelers or 1,
            currency="USD",
            limit=5,
        )
        # Filter out error results
        real = [r for r in results if r.get("price") and not r.get("error")]
        if real:
            best = sorted(real, key=lambda r: r["price"])[0]
            return {
                "found": True,
                "price": best["price"],
                "currency": best.get("currency", "USD"),
                "source": f"Kiwi.com — {best.get('airline', '')}",
                "details": (
                    f"{best.get('departure', '')[:10]} · "
                    f"{best.get('stops', 0)} stops · "
                    f"{best.get('duration_hours', 0)}h"
                ),
                "deal_quality": "real_price",
                "deep_link": best.get("deep_link", ""),
                "booking_token": best.get("booking_token", ""),
                "kiwi": True,
            }

    # ── 2. Amadeus ─────────────────────────────────────────────────────────────
    if amadeus_client.is_configured():
        if category == "flight" and date_from:
            results = amadeus_client.search_flights(
                origin=origin, destination=destination,
                departure_date=date_from, return_date=date_to, max_results=3,
            )
            if results:
                best = results[0]
                best["amadeus"] = True
                return best

        elif category == "hotel" and date_from and date_to:
            results = amadeus_client.search_hotels(
                city=destination, check_in=date_from,
                check_out=date_to, max_results=3,
            )
            if results:
                best = results[0]
                best["amadeus"] = True
                return best

    # ── Fallback: Gemini + Google Search ──────────────────────────────────────
    if not ai_client.is_configured():
        return {"found": False, "error": "no_api_key", "reason": "GEMINI_API_KEY not configured"}

    prompt = build_search_prompt(item)
    system = SYSTEM_PROMPT + (" Respond in English." if _lang == "en" else " השב בעברית.")
    text = ai_client.ask_with_search(prompt=prompt, system=system, max_tokens=1024)

    if text is None:
        return {"found": False, "error": "rate_limit", "reason": "Gemini quota reached"}

    return ai_client.extract_json(text)


def analyze_deal(item: dict, price_history: list) -> str:
    """Use Gemini to analyze whether this is a good deal."""
    if not ai_client.is_configured():
        return "GEMINI_API_KEY not configured"
    if len(price_history) < 2:
        return "Not enough history to analyze"

    prices = [r["price"] for r in price_history[:20]]
    avg = sum(prices) / len(prices)
    current = prices[0]

    lang_note = "in English" if _lang == "en" else "in Hebrew"
    prompt = (
        f"Analyze whether this is a good deal:\n"
        f"- Item: {item['name']} ({item['category']}) to {item['destination']}\n"
        f"- Current price: {current}\n"
        f"- Average (up to 20 measurements): {avg:.0f}\n"
        f"- Minimum seen: {min(prices)}\n"
        f"- Maximum seen: {max(prices)}\n\n"
        f"Give a short recommendation (2-3 sentences) {lang_note}: Should I buy now? Why?"
    )
    result = ai_client.ask(prompt=prompt, max_tokens=256)
    return result or f"Current price {current:.0f} vs average {avg:.0f}"


def smart_search_opportunities(destinations: list) -> list:
    """Ask Gemini to proactively find good travel deals."""
    if not ai_client.is_configured():
        return []

    dest_str = ", ".join(destinations)
    prompt = (
        f"Find 3 excellent travel opportunities right now to one of these destinations: {dest_str}\n\n"
        f"Search for cheap flights, hotels on sale, vacation packages.\n\n"
        f'For each return JSON: {{"destination":"...","type":"flight/hotel/package",'
        f'"deal":"description","price":000,"currency":"USD","why_good":"reason","urgency":"high/medium/low"}}\n\n'
        f"Return JSON list: [{{...}}, {{...}}, ...]"
    )
    lang_system = "You are a travel expert searching for price opportunities." + (
        " Respond in English." if _lang == "en" else ""
    )
    text = ai_client.ask_with_search(prompt=prompt, system=lang_system, max_tokens=2048)
    return ai_client.extract_json_array(text or "")
