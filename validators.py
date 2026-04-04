"""
Validators for destinations and airport codes.
Validates IATA codes and city/country names entered in the app.
"""
import re

# Common IATA airport codes → city name
IATA_AIRPORTS = {
    # Israel
    "TLV": "Tel Aviv",
    "SDV": "Tel Aviv (Sde Dov)",
    "ETH": "Eilat",
    "VDA": "Eilat (Ramon)",
    # Europe
    "LHR": "London Heathrow",
    "LGW": "London Gatwick",
    "STN": "London Stansted",
    "CDG": "Paris Charles de Gaulle",
    "ORY": "Paris Orly",
    "AMS": "Amsterdam",
    "FRA": "Frankfurt",
    "MUC": "Munich",
    "MAD": "Madrid",
    "BCN": "Barcelona",
    "FCO": "Rome Fiumicino",
    "CIA": "Rome Ciampino",
    "MXP": "Milan Malpensa",
    "BGY": "Milan Bergamo",
    "VCE": "Venice",
    "ATH": "Athens",
    "SKG": "Thessaloniki",
    "IST": "Istanbul",
    "SAW": "Istanbul Sabiha",
    "ZRH": "Zurich",
    "VIE": "Vienna",
    "PRG": "Prague",
    "BUD": "Budapest",
    "WAW": "Warsaw",
    "KRK": "Krakow",
    "CPH": "Copenhagen",
    "ARN": "Stockholm",
    "OSL": "Oslo",
    "HEL": "Helsinki",
    "LIS": "Lisbon",
    "OPO": "Porto",
    "DUB": "Dublin",
    "BRU": "Brussels",
    "GVA": "Geneva",
    "NCE": "Nice",
    "MRS": "Marseille",
    "LYS": "Lyon",
    "TLS": "Toulouse",
    "EDI": "Edinburgh",
    "MAN": "Manchester",
    "BHX": "Birmingham",
    "SVO": "Moscow Sheremetyevo",
    "DME": "Moscow Domodedovo",
    "LED": "St. Petersburg",
    "BEG": "Belgrade",
    "ZAG": "Zagreb",
    "LJU": "Ljubljana",
    "SOF": "Sofia",
    "OTP": "Bucharest",
    "CLJ": "Cluj-Napoca",
    "KIV": "Chisinau",
    "RIX": "Riga",
    "TLL": "Tallinn",
    "VNO": "Vilnius",
    "DUS": "Dusseldorf",
    "CGN": "Cologne",
    "HAM": "Hamburg",
    "TXL": "Berlin Tegel",
    "BER": "Berlin Brandenburg",
    "NUE": "Nuremberg",
    "STR": "Stuttgart",
    "PMI": "Palma de Mallorca",
    "IBZ": "Ibiza",
    "AGP": "Malaga",
    "ALC": "Alicante",
    "SVQ": "Seville",
    "VLC": "Valencia",
    "BIO": "Bilbao",
    "HER": "Heraklion",
    "RHO": "Rhodes",
    "CFU": "Corfu",
    "MLA": "Malta",
    "TIA": "Tirana",
    "OHD": "Ohrid",
    "LCA": "Larnaca",
    "PFO": "Paphos",
    # Americas
    "JFK": "New York JFK",
    "LGA": "New York LaGuardia",
    "EWR": "Newark",
    "LAX": "Los Angeles",
    "ORD": "Chicago O'Hare",
    "MDW": "Chicago Midway",
    "MIA": "Miami",
    "FLL": "Fort Lauderdale",
    "SFO": "San Francisco",
    "SEA": "Seattle",
    "DFW": "Dallas",
    "IAH": "Houston",
    "BOS": "Boston",
    "DCA": "Washington DC",
    "IAD": "Washington Dulles",
    "ATL": "Atlanta",
    "YYZ": "Toronto",
    "YVR": "Vancouver",
    "YUL": "Montreal",
    "GRU": "São Paulo",
    "GIG": "Rio de Janeiro",
    "EZE": "Buenos Aires",
    "BOG": "Bogotá",
    "LIM": "Lima",
    "SCL": "Santiago",
    "MEX": "Mexico City",
    "CUN": "Cancun",
    # Asia & Middle East
    "DXB": "Dubai",
    "AUH": "Abu Dhabi",
    "DOH": "Doha",
    "BAH": "Bahrain",
    "RUH": "Riyadh",
    "CAI": "Cairo",
    "AMM": "Amman",
    "BEY": "Beirut",
    "MCT": "Muscat",
    "KWI": "Kuwait",
    "NBO": "Nairobi",
    "ADD": "Addis Ababa",
    "LHR": "London",
    "BKK": "Bangkok",
    "DMK": "Bangkok Don Mueang",
    "CNX": "Chiang Mai",
    "HKT": "Phuket",
    "KUL": "Kuala Lumpur",
    "SIN": "Singapore",
    "CGK": "Jakarta",
    "DPS": "Bali",
    "MNL": "Manila",
    "TPE": "Taipei",
    "HKG": "Hong Kong",
    "PEK": "Beijing",
    "PVG": "Shanghai",
    "CAN": "Guangzhou",
    "ICN": "Seoul",
    "NRT": "Tokyo Narita",
    "HND": "Tokyo Haneda",
    "KIX": "Osaka",
    "NGO": "Nagoya",
    "BOM": "Mumbai",
    "DEL": "New Delhi",
    "BLR": "Bangalore",
    "MAA": "Chennai",
    "CCU": "Kolkata",
    "HYD": "Hyderabad",
    "CMB": "Colombo",
    "KTM": "Kathmandu",
    "DAC": "Dhaka",
    "RGN": "Yangon",
    # Africa
    "JNB": "Johannesburg",
    "CPT": "Cape Town",
    "DUR": "Durban",
    "LOS": "Lagos",
    "ACC": "Accra",
    "CMN": "Casablanca",
    "TUN": "Tunis",
    "ALG": "Algiers",
    "DAR": "Dar es Salaam",
    # Australia/Pacific
    "SYD": "Sydney",
    "MEL": "Melbourne",
    "BNE": "Brisbane",
    "PER": "Perth",
    "AKL": "Auckland",
    "CHC": "Christchurch",
}

# Common city/country names that are valid destinations (lowercase for comparison)
KNOWN_CITIES = {
    # Israel
    "תל אביב", "ירושלים", "חיפה", "אילת", "נתניה", "באר שבע", "רחובות",
    # Hebrew countries
    "ספרד", "צרפת", "איטליה", "גרמניה", "אנגליה", "יוון", "טורקיה", "פורטוגל",
    "הולנד", "בלגיה", "שוויץ", "אוסטריה", "פולין", "צ'כיה", "הונגריה", "קרואטיה",
    "ארה\"ב", "אמריקה", "קנדה", "ברזיל", "ארגנטינה", "מקסיקו",
    "תאילנד", "יפן", "סין", "הודו", "אינדונזיה", "מלזיה", "סינגפור",
    "אמירויות", "דובאי", "קטר", "בחריין", "ירדן", "לבנון", "מצרים",
    "דרום אפריקה", "מרוקו", "תוניסיה",
    "אוסטרליה", "ניו זילנד",
    # English cities
    "barcelona", "madrid", "paris", "london", "rome", "milan", "athens",
    "amsterdam", "berlin", "vienna", "prague", "budapest", "warsaw",
    "lisbon", "porto", "dublin", "brussels", "zurich", "geneva",
    "istanbul", "dubai", "doha", "cairo", "amman", "bangkok", "singapore",
    "tokyo", "beijing", "shanghai", "hong kong", "mumbai", "delhi",
    "new york", "los angeles", "miami", "chicago", "san francisco",
    "toronto", "sydney", "melbourne", "auckland",
    "nice", "florence", "venice", "naples", "palermo",
    "seville", "valencia", "malaga", "ibiza", "mallorca",
    "thessaloniki", "heraklion", "rhodes", "mykonos", "santorini",
    "stockholm", "oslo", "copenhagen", "helsinki",
    "edinburgh", "manchester", "birmingham",
    "seoul", "taipei", "bali", "phuket", "chiang mai",
    "nairobi", "cape town", "johannesburg", "casablanca",
    "cancun", "mexico city", "buenos aires", "rio de janeiro", "sao paulo",
    "moscow", "st. petersburg",
    "zagreb", "split", "dubrovnik", "sofia", "bucharest", "riga", "tallinn",
    "nicosia", "larnaca", "paphos",
    "eilat", "tel aviv", "jerusalem", "haifa",
    # English countries
    "spain", "france", "italy", "germany", "england", "uk", "greece",
    "turkey", "portugal", "netherlands", "belgium", "switzerland", "austria",
    "poland", "czech republic", "hungary", "croatia", "serbia", "bulgaria",
    "romania", "ukraine", "russia",
    "usa", "united states", "canada", "brazil", "argentina", "mexico",
    "thailand", "japan", "china", "india", "indonesia", "malaysia",
    "uae", "qatar", "bahrain", "jordan", "egypt", "israel",
    "south africa", "morocco", "kenya",
    "australia", "new zealand",
    "cyprus", "malta", "albania",
}


def validate_iata(code: str) -> tuple[bool, str]:
    """
    Validate an IATA airport code.
    Returns (is_valid, message).
    """
    if not code:
        return True, ""  # empty is OK (optional field)

    code = code.strip().upper()

    # Must be exactly 3 letters
    if not re.match(r'^[A-Z]{3}$', code):
        return False, f'קוד שדה תעופה "{code}" אינו תקין — חייב להיות 3 אותיות (למשל TLV, BCN)'

    if code in IATA_AIRPORTS:
        return True, f"✓ {IATA_AIRPORTS[code]}"

    # 3-letter code format is valid even if not in our list
    return True, f"✓ {code} (קוד שדה תעופה)"


def validate_destination(dest: str) -> tuple[bool, str]:
    """
    Validate a destination (city, country, or IATA code).
    Returns (is_valid, message).
    """
    if not dest:
        return False, "יעד הוא שדה חובה"

    dest = dest.strip()

    if len(dest) < 2:
        return False, "יעד חייב להכיל לפחות 2 תווים"

    if len(dest) > 100:
        return False, "יעד ארוך מדי"

    # Check if it looks like an IATA code (3 uppercase letters)
    if re.match(r'^[A-Z]{3}$', dest.upper()):
        ok, msg = validate_iata(dest)
        return ok, msg

    # Check known cities/countries
    dest_lower = dest.lower().strip()
    if dest_lower in KNOWN_CITIES:
        return True, ""

    # Allow any reasonable destination string (letters, spaces, hyphens, apostrophes)
    # Block clearly invalid inputs: only numbers, special chars, etc.
    if re.match(r'^[\d\s\-_.!@#$%^&*()]+$', dest):
        return False, f'"{dest}" לא נראה כיעד תקין — הזן שם עיר, מדינה, או קוד שדה תעופה (כגון TLV)'

    # If it has at least some letters, accept it
    if re.search(r'[a-zA-Z\u0590-\u05FF\u0600-\u06FF]', dest):
        return True, ""

    return False, f'"{dest}" לא נראה כיעד תקין — הזן שם עיר, מדינה, או קוד שדה תעופה'


def validate_origin(origin: str, category: str = "flight") -> tuple[bool, str]:
    """
    Validate an origin field.
    For flights, prefer IATA codes. For hotels/apartments, city names are fine.
    Returns (is_valid, message).
    """
    if not origin:
        return True, ""  # origin is optional

    origin = origin.strip()

    if len(origin) < 2:
        return False, "עיר מוצא חייבת להכיל לפחות 2 תווים"

    if len(origin) > 100:
        return False, "עיר מוצא ארוכה מדי"

    # For flights, check if it's a valid IATA code or city
    if category == "flight":
        upper = origin.upper()
        if re.match(r'^[A-Z]{3}$', upper):
            ok, msg = validate_iata(upper)
            if ok:
                return True, msg
            return False, f'קוד שדה תעופה "{upper}" לא מוכר — נסה TLV, SDV, ETH'

        # Accept city names for flights too
        if origin.lower() in KNOWN_CITIES:
            return True, ""

        # Warn (but don't block) if it doesn't look like an IATA code for flights
        if len(origin) == 3 and origin.isalpha():
            return True, f"טיפ: עבור טיסות מומלץ להשתמש בקוד IATA (למשל TLV)"

    return validate_destination(origin)


def suggest_iata(text: str) -> list[str]:
    """
    Suggest IATA codes based on partial city name or code.
    Returns list of "CODE — City" strings.
    """
    if not text or len(text) < 2:
        return []

    text_upper = text.upper().strip()
    text_lower = text.lower().strip()

    suggestions = []

    # Exact code match first
    if text_upper in IATA_AIRPORTS:
        suggestions.append(f"{text_upper} — {IATA_AIRPORTS[text_upper]}")
        return suggestions

    # Code prefix match
    for code, city in IATA_AIRPORTS.items():
        if code.startswith(text_upper):
            suggestions.append(f"{code} — {city}")

    # City name match
    for code, city in IATA_AIRPORTS.items():
        if text_lower in city.lower() and f"{code} — {city}" not in suggestions:
            suggestions.append(f"{code} — {city}")

    return suggestions[:8]  # max 8 suggestions
