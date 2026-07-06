import os
import re
import certifi
import airportsdata
import pycountry
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

API_KEY = os.getenv("SERPAPI_API_KEY")

# Default origin when user says only destination, e.g. "Japan trip"
DEFAULT_ORIGIN_IATA = os.getenv("DEFAULT_ORIGIN_IATA", "DEL")

BASE_URL = "https://serpapi.com/search"

AIRPORTS = airportsdata.load("IATA")


# ---------------------------------------------------------------------------
# Country / city resolution  (unchanged from original)
# ---------------------------------------------------------------------------

COUNTRY_ALIASES = {
    "usa": "US", "u.s.a": "US", "u.s.": "US", "america": "US",
    "united states": "US", "uk": "GB", "u.k.": "GB", "britain": "GB",
    "england": "GB", "uae": "AE", "dubai": "AE", "south korea": "KR",
    "korea": "KR", "russia": "RU", "vietnam": "VN", "bangladesh": "BD",
    "india": "IN", "japan": "JP", "china": "CN", "singapore": "SG",
    "malaysia": "MY", "thailand": "TH", "indonesia": "ID", "nepal": "NP",
    "qatar": "QA", "saudi arabia": "SA", "turkey": "TR", "canada": "CA",
    "australia": "AU", "germany": "DE", "france": "FR", "italy": "IT",
    "spain": "ES",
}

COUNTRY_MAIN_AIRPORT = {
    "BD": "DAC", "IN": "DEL", "JP": "NRT", "US": "JFK", "GB": "LHR",
    "AE": "DXB", "SG": "SIN", "MY": "KUL", "TH": "BKK", "ID": "CGK",
    "CN": "PEK", "KR": "ICN", "NP": "KTM", "QA": "DOH", "SA": "JED",
    "TR": "IST", "CA": "YYZ", "AU": "SYD", "DE": "FRA", "FR": "CDG",
    "IT": "FCO", "ES": "MAD",
}

CITY_MAIN_AIRPORT = {
    "dhaka": "DAC", "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM",
    "kolkata": "CCU", "chennai": "MAA", "bangalore": "BLR",
    "bengaluru": "BLR", "tokyo": "NRT", "osaka": "KIX", "kyoto": "KIX",
    "new york": "JFK", "london": "LHR", "dubai": "DXB",
    "singapore": "SIN", "kuala lumpur": "KUL", "bangkok": "BKK",
    "doha": "DOH", "istanbul": "IST", "toronto": "YYZ", "sydney": "SYD",
    "paris": "CDG", "rome": "FCO", "madrid": "MAD", "frankfurt": "FRA",
}


def clean_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    stop_words = [
        "flight", "flights", "ticket", "tickets", "trip", "travel",
        "plan", "complete", "days", "day", "including", "hotel",
        "hotels", "sightseeing", "under", "budget", "info", "information",
    ]
    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words).strip()


def country_name_to_code(text: str):
    text = clean_text(text)
    if text in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[text]
    try:
        return pycountry.countries.lookup(text).alpha_2
    except LookupError:
        pass
    for country in pycountry.countries:
        if country.name.lower() in text:
            return country.alpha_2
    for alias, code in COUNTRY_ALIASES.items():
        if alias in text:
            return code
    return None


def airport_country_matches(airport: dict, country_code: str) -> bool:
    airport_country = str(airport.get("country", "")).upper().strip()
    if airport_country == country_code:
        return True
    try:
        country = pycountry.countries.get(alpha_2=country_code)
        if country and airport_country.lower() == country.name.lower():
            return True
    except Exception:
        pass
    return False


def get_best_airport_for_country(country_code: str):
    preferred = COUNTRY_MAIN_AIRPORT.get(country_code)
    if preferred and preferred in AIRPORTS:
        return preferred
    candidates = []
    for iata, airport in AIRPORTS.items():
        if not iata:
            continue
        if airport_country_matches(airport, country_code):
            name = str(airport.get("name", "")).lower()
            city = str(airport.get("city", "")).lower()
            score = 0
            if "international" in name:
                score += 50
            if "intl" in name:
                score += 40
            if "capital" in name:
                score += 20
            if city:
                score += 5
            candidates.append((score, iata))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def resolve_location_to_iata(location: str):
    if not location:
        return None
    raw_location = location.strip()
    if re.fullmatch(r"[A-Za-z]{3}", raw_location):
        code = raw_location.upper()
        if code in AIRPORTS:
            return code
    location_clean = clean_text(raw_location)
    if not location_clean:
        return None
    if location_clean in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[location_clean]
    country_code = country_name_to_code(location_clean)
    if country_code:
        airport = get_best_airport_for_country(country_code)
        if airport:
            return airport
    city_matches = []
    for iata, airport in AIRPORTS.items():
        city = str(airport.get("city", "")).lower().strip()
        name = str(airport.get("name", "")).lower().strip()
        score = 0
        if city == location_clean:
            score += 100
        elif location_clean in city:
            score += 70
        if location_clean in name:
            score += 50
        # Only use "international" as a tie-breaker on top of a real match above -
        # applied unconditionally, it gave every airport on earth a nonzero score,
        # so an unresolvable phrase would silently return an arbitrary "* International
        # Airport" (whichever sorted last alphabetically by IATA code) instead of None.
        if score > 0 and "international" in name:
            score += 10
        if score > 0:
            city_matches.append((score, iata))
    if city_matches:
        city_matches.sort(reverse=True)
        return city_matches[0][1]
    return None


def find_location_mentions(query: str):
    q = query.lower()
    mentions = []
    for alias in COUNTRY_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", q):
            mentions.append(alias)
    for country in pycountry.countries:
        name = country.name.lower()
        if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", q):
            mentions.append(name)
    for city in CITY_MAIN_AIRPORT:
        if re.search(rf"\b{re.escape(city)}\b", q):
            mentions.append(city)
    unique_mentions = []
    for item in mentions:
        if item not in unique_mentions:
            unique_mentions.append(item)
    return unique_mentions


# ---------------------------------------------------------------------------
# Route parsing  (unchanged from original)
# ---------------------------------------------------------------------------

def parse_route(query: str):
    q = query.strip()
    q_lower = q.lower()

    global_keywords = [
        "all country", "all countries", "global flight", "global flights",
        "all flight", "all flights", "worldwide flight", "worldwide flights",
    ]
    if any(kw in q_lower for kw in global_keywords):
        return None, None

    codes = re.findall(r"\b[A-Z]{3}\b", q)
    if len(codes) >= 2:
        return codes[0].upper(), codes[1].upper()

    match = re.search(
        r"\bfrom\s+(.+?)\s+\bto\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at|and|next)\b|[.!?]|$)",
        q_lower,
    )
    if match:
        return resolve_location_to_iata(match.group(1)), resolve_location_to_iata(match.group(2))

    match = re.search(
        r"\bto\s+(.+?)\s+\bfrom\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at|and|next)\b|[.!?]|$)",
        q_lower,
    )
    if match:
        return resolve_location_to_iata(match.group(2)), resolve_location_to_iata(match.group(1))

    # Bounded "from X" / "to Y" — stop at the first stopword/punctuation like the
    # two-location patterns above, instead of swallowing the rest of the sentence.
    from_match = re.search(
        r"\bfrom\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at|and|next)\b|[.!?]|$)",
        q_lower,
    )
    to_match = re.search(
        r"\bto\s+(.+?)(?:\s+(?:on|for|under|including|with|in|at|and|next)\b|[.!?]|$)",
        q_lower,
    )

    dep_iata = resolve_location_to_iata(from_match.group(1)) if from_match else None
    arr_iata = resolve_location_to_iata(to_match.group(1)) if to_match else None

    if dep_iata or arr_iata:
        if dep_iata and arr_iata:
            return dep_iata, arr_iata

        # Only one side of "from"/"to" resolved. This is common for phrasing
        # like "<Destination> trip from <Origin>" (no "to" clause at all,
        # e.g. "Thailand trip from India") — the destination was already
        # mentioned earlier in the sentence, so look for another, different
        # location anywhere in the query before giving up on it.
        other_codes = []
        for mention in find_location_mentions(q):
            code = resolve_location_to_iata(mention)
            if code and code != dep_iata and code != arr_iata and code not in other_codes:
                other_codes.append(code)

        if dep_iata and not arr_iata and other_codes:
            return dep_iata, other_codes[0]
        if arr_iata and not dep_iata and other_codes:
            return other_codes[0], arr_iata

        return dep_iata, arr_iata

    mentions = find_location_mentions(q)
    if len(mentions) >= 2:
        return resolve_location_to_iata(mentions[0]), resolve_location_to_iata(mentions[1])
    if len(mentions) == 1:
        return DEFAULT_ORIGIN_IATA, resolve_location_to_iata(mentions[0])

    return None, None


# ---------------------------------------------------------------------------
# Date extraction  (new — SerpApi requires outbound_date)
# ---------------------------------------------------------------------------

# Regex patterns to detect explicit dates like "on July 15", "2026-07-15", "15 July"
_MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|september|"
    "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)

_DATE_PATTERNS = [
    # 2026-07-15 or 07/15/2026 or 15/07/2026
    re.compile(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b"),
    # "July 15" or "15 July" with optional year
    re.compile(
        rf"\b({_MONTH_NAMES})\s+(\d{{1,2}})(?:[a-z]{{0,2}})?(?:\s+(\d{{4}}))?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(\d{{1,2}})(?:[a-z]{{0,2}})?\s+({_MONTH_NAMES})(?:\s+(\d{{4}}))?\b",
        re.IGNORECASE,
    ),
]

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_RELATIVE = {
    "today": 0, "tomorrow": 1, "next week": 7, "next month": 30,
    "in a week": 7, "in two weeks": 14, "in a month": 30,
}


def parse_date(query: str) -> str:
    """
    Extracts a travel date from natural language and returns YYYY-MM-DD.
    Falls back to 7 days from today when nothing is found.
    """
    q = query.lower()
    today = datetime.today()

    # Relative keywords
    for phrase, delta in _RELATIVE.items():
        if phrase in q:
            return (today + timedelta(days=delta)).strftime("%Y-%m-%d")

    # "next <weekday>"
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, wd in enumerate(weekdays):
        if f"next {wd}" in q:
            days_ahead = (i - today.weekday() + 7) % 7 or 7
            return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    # YYYY-MM-DD or YYYY/MM/DD
    m = re.search(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b", query)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # MM/DD/YYYY or DD/MM/YYYY — assume MM/DD/YYYY for ambiguous cases
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", query)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # "July 15 2026" or "July 15"
    m = re.search(
        rf"\b({_MONTH_NAMES})\s+(\d{{1,2}})(?:[a-z]{{0,2}})?(?:\s+(\d{{4}}))?\b",
        query, re.IGNORECASE,
    )
    if m:
        month = _MONTH_MAP[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            dt = datetime(year, month, day)
            if dt < today:
                dt = dt.replace(year=dt.year + 1)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # "15 July 2026" or "15 July"
    m = re.search(
        rf"\b(\d{{1,2}})(?:[a-z]{{0,2}})?\s+({_MONTH_NAMES})(?:\s+(\d{{4}}))?\b",
        query, re.IGNORECASE,
    )
    if m:
        day = int(m.group(1))
        month = _MONTH_MAP[m.group(2).lower()]
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            dt = datetime(year, month, day)
            if dt < today:
                dt = dt.replace(year=dt.year + 1)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Default: 7 days from today
    return (today + timedelta(days=7)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _mins(minutes) -> str:
    if minutes is None:
        return "N/A"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


def format_flight_option(option: dict, index: int) -> str:
    price = option.get("price")
    price_text = f"${price:,}" if price else "N/A"
    total_dur = _mins(option.get("total_duration"))
    flight_type = option.get("type", "")

    carbon = option.get("carbon_emissions", {})
    carbon_text = ""
    if carbon:
        grams = carbon.get("this_flight")
        diff = carbon.get("difference_percent")
        if grams:
            kg = grams // 1000
            sign = f" ({'+' if diff > 0 else ''}{diff}% vs typical)" if diff is not None else ""
            carbon_text = f"\nCarbon: ~{kg} kg CO₂{sign}"

    segments = option.get("flights", [])
    seg_lines = []
    for seg in segments:
        dep = seg.get("departure_airport", {})
        arr = seg.get("arrival_airport", {})
        airline = seg.get("airline", "Unknown")
        flight_num = seg.get("flight_number", "")
        airplane = seg.get("airplane", "")
        dur = _mins(seg.get("duration"))
        legroom = seg.get("legroom", "")
        overnight = " 🌙 Overnight" if seg.get("overnight") else ""
        often_delayed = " ⚠️ Often delayed 30+ min" if seg.get("often_delayed_by_over_30_min") else ""

        seg_lines.append(
            f"  ✈  {airline} {flight_num} ({airplane})\n"
            f"     {dep.get('name','?')} ({dep.get('id','?')}) {dep.get('time','')}\n"
            f"     → {arr.get('name','?')} ({arr.get('id','?')}) {arr.get('time','')}\n"
            f"     Duration: {dur}  |  Legroom: {legroom}{overnight}{often_delayed}"
        )

    layovers = option.get("layovers", [])
    layover_lines = []
    for lv in layovers:
        overnight_lv = " (overnight)" if lv.get("overnight") else ""
        layover_lines.append(
            f"  ⏳ Layover at {lv.get('name','?')} ({lv.get('id','?')}): {_mins(lv.get('duration'))}{overnight_lv}"
        )

    # Interleave segments and layovers
    lines = []
    for i, seg_line in enumerate(seg_lines):
        lines.append(seg_line)
        if i < len(layover_lines):
            lines.append(layover_lines[i])

    extras = option.get("extensions", [])
    extras_text = f"\nExtras: {', '.join(extras)}" if extras else ""

    return (
        f"Option {index} | {flight_type} | Total: {total_dur} | Price: {price_text}"
        f"{carbon_text}{extras_text}\n"
        + "\n".join(lines)
    )


def format_price_insights(insights: dict) -> str:
    if not insights:
        return ""
    lowest = insights.get("lowest_price")
    level = insights.get("price_level", "")
    typical = insights.get("typical_price_range", [])

    parts = []
    if lowest:
        parts.append(f"Lowest available: ${lowest:,}")
    if level:
        parts.append(f"Price level: {level}")
    if typical and len(typical) == 2:
        parts.append(f"Typical range: ${typical[0]:,} – ${typical[1]:,}")

    return "💰 Price Insights: " + " | ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

def search_flights(query: str, limit: int = 5) -> str:
    if not API_KEY:
        return (
            "Flight API error: SERPAPI_API_KEY is missing.\n"
            "Please add this in your .env file:\n"
            "SERPAPI_API_KEY=your_api_key_here\n"
            "Get a free key (100 searches/month) at https://serpapi.com"
        )

    dep_iata, arr_iata = parse_route(query)
    outbound_date = parse_date(query)

    # SerpApi Google Flights requires BOTH departure_id and arrival_id.
    if not dep_iata and not arr_iata:
        return (
            "Please specify an origin and destination city or airport.\n"
            "Example: 'flights from Delhi to Tokyo next week'"
        )

    # If only destination was given, use the configured default origin.
    if not dep_iata:
        dep_iata = DEFAULT_ORIGIN_IATA

    # If origin was given but destination could not be resolved, ask the user.
    if not arr_iata:
        return (
            f"Could not determine the destination airport from your query.\n"
            "Please mention a specific city or airport code.\n"
            f"Example: 'flights from {dep_iata} to Tokyo'"
        )

    params = {
        "engine": "google_flights",
        "api_key": API_KEY,
        "departure_id": dep_iata,
        "arrival_id": arr_iata,
        "outbound_date": outbound_date,
        "type": "2",        # one-way; simpler for a travel planner agent
        "currency": "USD",
        "hl": "en",
        "sort_by": "1",     # top flights
    }

    try:
        response = requests.get(BASE_URL, params=params, timeout=30)
        data = response.json()
    except requests.exceptions.RequestException as e:
        return f"Flight API request failed: {e}"
    except ValueError:
        return "Flight API returned invalid JSON."

    # SerpApi error
    if "error" in data:
        return f"Flight API error: {data['error']}"

    best = data.get("best_flights", [])
    other = data.get("other_flights", [])
    all_flights = best + other

    if not all_flights:
        return (
            f"No flights found from {dep_iata} to {arr_iata or '(any)'} on {outbound_date}.\n"
            "Try a different date or route."
        )

    route_info = f"Flights from {dep_iata} to {arr_iata or '(any)'} on {outbound_date}"

    formatted = []
    for i, option in enumerate(all_flights[:limit], start=1):
        formatted.append(format_flight_option(option, i))

    price_line = format_price_insights(data.get("price_insights", {}))

    result = f"{route_info}\n\n" + "\n\n---\n\n".join(formatted)
    if price_line:
        result += f"\n\n{price_line}"

    return result


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(search_flights("Plan a 7 days Japan trip from India next month"))
    print("\n" + "=" * 80 + "\n")
    print(search_flights("flights from DEL to NRT on July 20"))