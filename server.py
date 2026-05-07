"""
Noded — FastAPI backend
Replaces Streamlit. All Python logic stays in existing modules.
"""
import os
import json
import asyncio
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from collections import defaultdict

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import re

import database as db
import ai_client
import agent as price_agent
import wizelife_auth

# ── Optional modules (lazy — imported on first use, not at startup) ───────────
def _try_import(name):
    try:
        import importlib
        return importlib.import_module(name)
    except Exception:
        return None

_optional_cache: dict = {}
def _lazy(name):
    if name not in _optional_cache:
        _optional_cache[name] = _try_import(name)
    return _optional_cache[name]

# Aliases used in endpoints
def price_dna_mod():   return _lazy("price_dna")
def exchange_mod():    return _lazy("exchange_rates")

# ── AI Rate limiting (plan-aware, daily) ─────────────────────────────────────
_AI_DAILY_LIMITS = {"free": 5, "pro": 20, "yolo": 40}
_ai_usage: dict[str, dict] = defaultdict(lambda: {"date": "", "count": 0})

def _get_plan_from_request(request: Request) -> tuple[str, str]:
    """Returns (plan, key) where key is uid or IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            import httpx
            r = httpx.post(
                f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/getAccountInfo?key={wizelife_auth._FIREBASE_API_KEY}",
                json={"idToken": token}, timeout=4,
            )
            uid = r.json().get("users", [{}])[0].get("localId", "")
            if uid:
                plan = wizelife_auth.get_plan(uid, token)
                return plan, f"uid:{uid}"
        except Exception:
            pass
    ip = request.client.host if request.client else "unknown"
    return "free", f"ip:{ip}"

def _check_ai_quota(request: Request) -> tuple[bool, str, str]:
    """Returns (allowed, plan, key). Raises nothing."""
    plan, key = _get_plan_from_request(request)
    today = str(date.today())
    entry = _ai_usage[key]
    if entry["date"] != today:
        entry["date"] = today
        entry["count"] = 0
    limit = _AI_DAILY_LIMITS.get(plan, 5)
    if entry["count"] >= limit:
        return False, plan, key
    entry["count"] += 1
    return True, plan, key


# ── Validation helpers ────────────────────────────────────────────────────────
_VALID_CATEGORIES = {"flight", "hotel", "apartment", "package"}
_VALID_LANGS      = {"he", "en", "pt", "es"}
_DATE_RE          = re.compile(r"^\d{4}-\d{2}-\d{2}$")

def _check_date(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not _DATE_RE.match(v):
        raise ValueError("date must be YYYY-MM-DD")
    return v

def _clean_lang(v: Optional[str]) -> str:
    return v if v in _VALID_LANGS else "he"


# ── App init ──────────────────────────────────────────────────────────────────
db.init_db()

app = FastAPI(title="Noded API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://wizelife.ai", "https://finsightai.github.io", "https://travel.wizelife.ai", "https://wizetravel-next.vercel.app", "http://localhost:3000", "http://localhost:3001", "http://localhost:8080"],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/manifest.json")
async def manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
async def service_worker():
    return FileResponse("static/sw.js", media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})

@app.get("/")
async def root():
    return FileResponse("public/index.html")


@app.get("/health")
async def health():
    return {"ok": True, "version": "3.0"}


# ════════════════════════════════════════════════════════════
# WATCH ITEMS
# ════════════════════════════════════════════════════════════

class WatchItemIn(BaseModel):
    name: str        = Field(..., min_length=1, max_length=200)
    category: str    # flight / hotel / apartment / package
    query: str       = Field(..., min_length=1, max_length=500)
    destination: str = Field(..., min_length=1, max_length=100)
    origin: Optional[str] = Field(None, max_length=100)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    max_price: Optional[float] = Field(None, gt=0)
    drop_pct: float  = Field(10.0, ge=1.0, le=90.0)

    @field_validator("category")
    @classmethod
    def val_category(cls, v: str) -> str:
        if v not in _VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(_VALID_CATEGORIES)}")
        return v

    @field_validator("date_from", "date_to")
    @classmethod
    def val_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date(v)

    @field_validator("name", "query", "destination")
    @classmethod
    def no_html(cls, v: str) -> str:
        if re.search(r"[<>\"'`]", v):
            raise ValueError("field contains disallowed characters")
        return v.strip()


@app.get("/api/watches")
async def list_watches(all: bool = False, limit: int = 200, offset: int = 0):
    limit  = max(1, min(limit, 500))
    offset = max(0, offset)
    items = db.get_all_watch_items(enabled_only=not all)
    items = items[offset: offset + limit]
    for item in items:
        last = db.get_last_price(item["id"])
        item["last_price"] = last
        low  = db.get_lowest_price(item["id"])
        item["lowest_price"] = low
    return items


@app.post("/api/watches", status_code=201)
async def create_watch(item: WatchItemIn):
    wi = db.WatchItem(
        id=None,
        name=item.name,
        category=item.category,
        query=item.query,
        destination=item.destination,
        origin=item.origin,
        date_from=item.date_from,
        date_to=item.date_to,
        max_price=item.max_price,
        drop_pct=item.drop_pct,
    )
    new_id = db.add_watch_item(wi)
    return {"id": new_id}


@app.delete("/api/watches/{watch_id}")
async def delete_watch(watch_id: int):
    db.delete_watch_item(watch_id)
    return {"ok": True}


@app.patch("/api/watches/{watch_id}/toggle")
async def toggle_watch(watch_id: int, enabled: bool = True):
    db.toggle_watch_item(watch_id, enabled)
    return {"ok": True}


@app.post("/api/watches/{watch_id}/check")
async def check_price(watch_id: int, background_tasks: BackgroundTasks):
    items = db.get_all_watch_items(enabled_only=False)
    item  = next((i for i in items if i["id"] == watch_id), None)
    if not item:
        raise HTTPException(404, "Watch item not found")

    def _run_check():
        result = price_agent.search_price(item["query"])
        if result.get("found") and result.get("price"):
            record = db.PriceRecord(
                id=None,
                watch_id=watch_id,
                price=result["price"],
                currency=result.get("currency", "USD"),
                source=result.get("source", "AI"),
                details=json.dumps(result),
            )
            db.save_price(record)

    background_tasks.add_task(_run_check)
    return {"ok": True, "message": "Price check started"}


# ════════════════════════════════════════════════════════════
# PRICE HISTORY
# ════════════════════════════════════════════════════════════

@app.get("/api/prices/{watch_id}")
async def price_history(watch_id: int, limit: int = 60):
    return db.get_price_history(watch_id, limit)


@app.get("/api/prices/{watch_id}/stats")
async def price_stats(watch_id: int):
    history = db.get_price_history(watch_id, 100)
    if not history:
        return {}
    prices = [h["price"] for h in history]
    return {
        "count":   len(prices),
        "current": prices[0],
        "lowest":  min(prices),
        "highest": max(prices),
        "avg":     round(sum(prices) / len(prices), 2),
        "currency": history[0]["currency"],
    }


# ════════════════════════════════════════════════════════════
# AI CHAT (streaming)
# ════════════════════════════════════════════════════════════

class ChatMsg(BaseModel):
    messages: list[dict] = Field(..., max_length=100)  # [{"role": "user"|"model", "parts": [{"text": "..."}]}]
    system: str          = Field("", max_length=1000)
    web_search: bool     = False

    @field_validator("messages")
    @classmethod
    def val_messages(cls, v: list) -> list:
        if not v:
            raise ValueError("messages must not be empty")
        last = v[-1]
        if not isinstance(last, dict) or "parts" not in last:
            raise ValueError("last message must have 'parts'")
        text = last.get("parts", [{}])[0].get("text", "")
        if len(text) > 4000:
            raise ValueError("message text too long (max 4000 chars)")
        return v


@app.post("/api/ai/chat")
async def ai_chat(body: ChatMsg, request: Request):
    allowed, plan, key = _check_ai_quota(request)
    if not allowed:
        limit = _AI_DAILY_LIMITS.get(plan, 5)
        raise HTTPException(429, f"Daily AI limit reached ({limit}/day on {plan} plan). Upgrade at wizelife.ai")

    history  = body.messages[:-1]
    last_msg = body.messages[-1]["parts"][0]["text"] if body.messages else ""

    async def stream():
        loop = asyncio.get_event_loop()
        reply = await loop.run_in_executor(
            None,
            lambda: ai_client.chat_turn(
                history=history,
                user_message=last_msg,
                system=body.system,
                web_search=body.web_search,
            )
        )
        text = reply or "⚠️ Could not get a response. Please check that the GEMINI_API_KEY is configured."
        # Stream word by word for effect
        for word in text.split(" "):
            yield f"data: {json.dumps({'text': word + ' '})}\n\n"
            await asyncio.sleep(0.01)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/api/ai/quick")
async def ai_quick(body: dict, request: Request):
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "prompt required")
    allowed, plan, key = _check_ai_quota(request)
    if not allowed:
        limit = _AI_DAILY_LIMITS.get(plan, 5)
        raise HTTPException(429, f"Daily AI limit reached ({limit}/day on {plan} plan). Upgrade at wizelife.ai")
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, max_tokens=512))
    return {"text": result or ""}


# ════════════════════════════════════════════════════════════
# PRICE DNA
# ════════════════════════════════════════════════════════════

@app.get("/api/price-dna")
async def get_price_dna():
    mod = price_dna_mod()
    if not mod:
        return {"error": "Module not available"}
    loop   = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, mod.get_ai_price_dna)
    return result or {"summary": "No data yet"}


# ════════════════════════════════════════════════════════════
# DEAL HUNTER
# ════════════════════════════════════════════════════════════

class DealHuntQuery(BaseModel):
    origin:      str           = Field(..., min_length=1, max_length=100)
    budget:      Optional[float] = Field(None, gt=0)
    dates:       Optional[str] = Field(None, max_length=200)
    preferences: str           = Field("", max_length=500)
    lang:        Optional[str] = "he"

    @field_validator("lang")
    @classmethod
    def val_lang(cls, v: Optional[str]) -> str:
        return _clean_lang(v)


@app.post("/api/deal-hunter")
async def hunt_deals(body: DealHuntQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"Daily AI limit reached on {plan} plan. Upgrade at wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Find best flight deals from {body.origin}. Budget: {body.budget or 'any'}. Dates: {body.dates or 'flexible'}. {body.preferences} {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1024))
    return {"result": result or "No deals found"}


# ════════════════════════════════════════════════════════════
# VISA CHECK
# ════════════════════════════════════════════════════════════

class VisaQuery(BaseModel):
    passport:    str = Field(..., min_length=2, max_length=100)
    destination: str = Field(..., min_length=2, max_length=100)


@app.post("/api/visa-check")
async def check_visa(body: VisaQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"Daily AI limit reached on {plan} plan. Upgrade at wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Visa requirements for {body.passport} passport holder traveling to {body.destination}. Include: visa required? cost? processing time? on-arrival available?"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=512))
    return {"result": result or ""}


# ════════════════════════════════════════════════════════════
# HIDDEN CITY
# ════════════════════════════════════════════════════════════

class HiddenCityQuery(BaseModel):
    origin:      str           = Field(..., min_length=2, max_length=10)
    destination: str           = Field(..., min_length=2, max_length=10)
    date:        Optional[str] = None

    @field_validator("date")
    @classmethod
    def val_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date(v)


@app.post("/api/hidden-city")
async def hidden_city_search(body: HiddenCityQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"Daily AI limit reached on {plan} plan. Upgrade at wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Find hidden city ticketing opportunities from {body.origin} to {body.destination} on {body.date or 'any date'}. Look for flights where {body.destination} is a layover in a cheaper itinerary."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


# ════════════════════════════════════════════════════════════
# EXCHANGE RATES
# ════════════════════════════════════════════════════════════

@app.get("/api/exchange-rates")
async def get_exchange_rates():
    mod = exchange_mod()
    if not mod:
        return {"rates": {}}
    try:
        loop  = asyncio.get_event_loop()
        rates = await loop.run_in_executor(None, lambda: mod.fetch_rates("USD"))
        return {"base": "USD", "rates": rates or {}}
    except Exception as e:
        return {"base": "USD", "rates": {}, "error": str(e)}


# ════════════════════════════════════════════════════════════
# ALERTS
# ════════════════════════════════════════════════════════════

@app.get("/api/alerts")
async def list_alerts():
    with db.get_db() as conn:
        rows = conn.execute("SELECT * FROM alert_rules ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


class AlertIn(BaseModel):
    name:       str          = Field(..., min_length=1, max_length=200)
    watch_id:   Optional[int] = Field(None, gt=0)
    conditions: dict         = Field(default_factory=dict)


@app.post("/api/alerts", status_code=201)
async def create_alert(body: AlertIn):
    with db.get_db() as conn:
        cur = conn.execute(
            "INSERT INTO alert_rules (name, watch_id, conditions, enabled, created_at) VALUES (?,?,?,1,?)",
            (body.name, body.watch_id, json.dumps(body.conditions), datetime.now().isoformat())
        )
        return {"id": cur.lastrowid}


@app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    with db.get_db() as conn:
        conn.execute("DELETE FROM alert_rules WHERE id=?", (alert_id,))
    return {"ok": True}


# ════════════════════════════════════════════════════════════
# EXPORT
# ════════════════════════════════════════════════════════════

@app.get("/api/export/csv")
async def export_csv():
    import csv, io
    items   = db.get_all_watch_items(enabled_only=False)
    output  = io.StringIO()
    writer  = csv.writer(output)
    writer.writerow(["ID", "Name", "Category", "Destination", "Origin", "Date From", "Date To", "Last Price", "Currency", "Created"])
    for item in items:
        last = db.get_last_price(item["id"])
        writer.writerow([
            item["id"], item["name"], item["category"],
            item["destination"], item.get("origin", ""),
            item.get("date_from", ""), item.get("date_to", ""),
            last["price"] if last else "", last["currency"] if last else "",
            item["created_at"][:10],
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=noded-export.csv"}
    )


@app.get("/api/export/excel")
async def export_excel():
    """Excel export of all watches and prices."""
    import exporters
    try:
        data = exporters.export_excel()
        return StreamingResponse(
            iter([data]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=noded-export.xlsx"}
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/weather")
async def weather(city: str, date: Optional[str] = None):
    """Weather forecast/climate for a destination. Open-Meteo (no key, free, ECMWF+GFS).
    If date within 16 days → forecast. If date further out → climate normals (monthly avg)."""
    import httpx
    from datetime import date as _date_cls
    try:
        # 1) Geocode city name to lat/lon
        async with httpx.AsyncClient(timeout=10) as client:
            geo_res = await client.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json")
            geo_data = geo_res.json()
            if not geo_data.get("results"):
                return JSONResponse({"error": f"city '{city}' not found"}, status_code=404)
            loc = geo_data["results"][0]
            lat, lon = loc["latitude"], loc["longitude"]
            country = loc.get("country", "")

            # 2) Decide forecast vs climate
            target_dt = None
            try:
                if date:
                    target_dt = _date_cls.fromisoformat(date)
            except: pass

            today = _date_cls.today()
            days_out = (target_dt - today).days if target_dt else 0

            if target_dt and 0 <= days_out <= 15:
                # Forecast (next 16 days)
                fc_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,uv_index_max&timezone=auto&forecast_days=16"
                fc_res = await client.get(fc_url)
                fc_data = fc_res.json()
                daily = fc_data.get("daily", {})
                # Pick the target day
                idx = days_out
                return {
                    "city": city, "country": country, "date": date,
                    "type": "forecast",
                    "temp_max": daily.get("temperature_2m_max", [None])[idx] if idx < len(daily.get("temperature_2m_max", [])) else None,
                    "temp_min": daily.get("temperature_2m_min", [None])[idx] if idx < len(daily.get("temperature_2m_min", [])) else None,
                    "precip_mm": daily.get("precipitation_sum", [None])[idx] if idx < len(daily.get("precipitation_sum", [])) else None,
                    "weather_code": daily.get("weather_code", [None])[idx] if idx < len(daily.get("weather_code", [])) else None,
                    "uv": daily.get("uv_index_max", [None])[idx] if idx < len(daily.get("uv_index_max", [])) else None,
                    "all_days": daily,
                }
            else:
                # Climate normal (monthly averages — for far-future dates)
                month = target_dt.month if target_dt else today.month
                year = today.year
                start = f"{year}-{month:02d}-01"
                end = f"{year}-{month:02d}-28"
                cl_url = f"https://climate-api.open-meteo.com/v1/climate?latitude={lat}&longitude={lon}&start_date={start}&end_date={end}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&models=MRI_AGCM3_2_S&temporal_resolution=monthly"
                cl_res = await client.get(cl_url)
                cl_data = cl_res.json()
                # Fallback: just call regular forecast for current week
                fc_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code&timezone=auto&forecast_days=7"
                fc_res = await client.get(fc_url)
                fc_data = fc_res.json()
                return {
                    "city": city, "country": country, "date": date, "month": month,
                    "type": "climate",
                    "climate_normal": cl_data.get("daily", {}),
                    "current_week": fc_data.get("daily", {}),
                }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/events")
async def events(city: str, date: Optional[str] = None, types: Optional[str] = None):
    """Multi-source event aggregator with attribution.
    Sources: Resident Advisor (electronic/clubs), Bandsintown (DJ tours),
             Ticketmaster (concerts/sports), Eventbrite (festivals/culture),
             Skiddle (UK clubs), Gemini fallback.
    Returns: { events: [{name, date, venue, type, source, url, ...}], sources_used: [...] }
    """
    import httpx, ai_client, json as _json, re as _re
    from datetime import datetime, timedelta

    target = None
    try:
        if date:
            target = datetime.fromisoformat(date)
    except: pass
    if not target:
        target = datetime.now() + timedelta(days=30)

    start_iso = target.replace(hour=0, minute=0, second=0).isoformat()
    end_iso = (target + timedelta(days=7)).replace(hour=23, minute=59).isoformat()
    date_str = target.strftime("%Y-%m-%d")

    all_events = []
    sources_used = []
    sources_failed = []

    async with httpx.AsyncClient(timeout=15) as client:

        # ── 1. Resident Advisor (electronic / clubs) — GraphQL scrape ──
        async def fetch_ra():
            try:
                # Get RA city ID
                area_query = {
                    "operationName": "GET_AREA_BY_NAME",
                    "variables": {"areaName": city},
                    "query": "query GET_AREA_BY_NAME($areaName: String!) { areas(filter: { name: { eq: $areaName } }) { id name urlName country { name } } }"
                }
                area_res = await client.post("https://ra.co/graphql", json=area_query, headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://ra.co/",
                })
                areas = area_res.json().get("data", {}).get("areas", [])
                if not areas: return []
                area_id = areas[0]["id"]
                # Get events for area
                ev_query = {
                    "operationName": "GET_EVENT_LISTINGS",
                    "variables": {
                        "filters": {"areas": {"eq": int(area_id)}, "listingDate": {"gte": start_iso, "lte": end_iso}},
                        "filterOptions": {"genre": True}, "pageSize": 20, "page": 1,
                    },
                    "query": "query GET_EVENT_LISTINGS($filters: FilterInputDtoInput, $filterOptions: FilterOptionsInputDtoInput, $page: Int, $pageSize: Int) { eventListings(filters: $filters, filterOptions: $filterOptions, pageSize: $pageSize, page: $page) { data { id event { id title date startTime venue { name } artists { name } contentUrl } } } }"
                }
                ev_res = await client.post("https://ra.co/graphql", json=ev_query, headers={
                    "Content-Type": "application/json", "User-Agent": "Mozilla/5.0", "Referer": "https://ra.co/",
                })
                listings = ev_res.json().get("data", {}).get("eventListings", {}).get("data", [])
                out = []
                for item in listings[:15]:
                    e = item.get("event", {})
                    artists = ", ".join([a.get("name","") for a in (e.get("artists") or [])[:3]])
                    out.append({
                        "name": e.get("title","Unknown"),
                        "date": e.get("date",""),
                        "venue": (e.get("venue") or {}).get("name",""),
                        "type": "electronic",
                        "artists": artists,
                        "url": "https://ra.co" + (e.get("contentUrl") or ""),
                        "source": "Resident Advisor",
                        "verified": True,
                    })
                return out
            except Exception as e:
                sources_failed.append(f"RA: {str(e)[:60]}")
                return []

        # ── 2. Bandsintown (DJ tours / live music) ──
        async def fetch_bandsintown():
            app_id = os.environ.get("BANDSINTOWN_APP_ID")
            if not app_id: return []
            try:
                # Bandsintown is artist-centric; need to search by city via venues endpoint
                # Free API doesn't support city search directly. Use trending artists in city.
                res = await client.get(
                    f"https://rest.bandsintown.com/artists/topartists.json",
                    params={"app_id": app_id, "location": city}
                )
                if res.status_code != 200: return []
                # Top artists' upcoming events
                artists = res.json()[:5] if isinstance(res.json(), list) else []
                out = []
                for a in artists:
                    name = a.get("name")
                    if not name: continue
                    ev_res = await client.get(
                        f"https://rest.bandsintown.com/artists/{name}/events",
                        params={"app_id": app_id, "date": "upcoming"}
                    )
                    if ev_res.status_code != 200: continue
                    for e in (ev_res.json() or [])[:3]:
                        venue = e.get("venue", {})
                        if venue.get("city","").lower() != city.lower(): continue
                        out.append({
                            "name": f"{name} live",
                            "date": e.get("datetime","")[:10],
                            "venue": venue.get("name",""),
                            "type": "concert",
                            "artists": name,
                            "url": e.get("url",""),
                            "source": "Bandsintown",
                            "verified": True,
                        })
                return out
            except Exception as e:
                sources_failed.append(f"Bandsintown: {str(e)[:60]}")
                return []

        # ── 3. Ticketmaster (concerts + sports + theater) ──
        async def fetch_ticketmaster():
            key = os.environ.get("TICKETMASTER_API_KEY")
            if not key: return []
            try:
                params = {
                    "apikey": key, "city": city, "size": 20,
                    "startDateTime": start_iso[:19] + "Z",
                    "endDateTime": end_iso[:19] + "Z",
                    "sort": "date,asc",
                }
                res = await client.get("https://app.ticketmaster.com/discovery/v2/events.json", params=params)
                if res.status_code != 200: return []
                events_data = res.json().get("_embedded", {}).get("events", [])
                out = []
                for e in events_data[:15]:
                    venue = (e.get("_embedded",{}).get("venues",[{}]) or [{}])[0]
                    classifications = e.get("classifications",[{}])[0] if e.get("classifications") else {}
                    seg = (classifications.get("segment") or {}).get("name","")
                    out.append({
                        "name": e.get("name","Unknown"),
                        "date": e.get("dates",{}).get("start",{}).get("localDate",""),
                        "venue": venue.get("name",""),
                        "type": seg.lower() if seg else "event",
                        "url": e.get("url",""),
                        "source": "Ticketmaster",
                        "verified": True,
                    })
                return out
            except Exception as e:
                sources_failed.append(f"Ticketmaster: {str(e)[:60]}")
                return []

        # ── 4. Eventbrite (festivals / culture) ──
        async def fetch_eventbrite():
            token = os.environ.get("EVENTBRITE_TOKEN")
            if not token: return []
            try:
                # Eventbrite v3 API requires geocoding the city
                geo = (await client.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1")).json()
                if not geo.get("results"): return []
                loc = geo["results"][0]
                res = await client.get(
                    "https://www.eventbriteapi.com/v3/events/search/",
                    params={
                        "location.latitude": loc["latitude"], "location.longitude": loc["longitude"],
                        "location.within": "25km",
                        "start_date.range_start": start_iso[:19] + "Z",
                        "start_date.range_end": end_iso[:19] + "Z",
                        "expand": "venue",
                    },
                    headers={"Authorization": f"Bearer {token}"}
                )
                if res.status_code != 200: return []
                events_data = res.json().get("events", [])
                out = []
                for e in events_data[:15]:
                    out.append({
                        "name": (e.get("name") or {}).get("text","Unknown"),
                        "date": (e.get("start") or {}).get("local","")[:10],
                        "venue": ((e.get("venue") or {}).get("name") or ""),
                        "type": "festival",
                        "url": e.get("url",""),
                        "source": "Eventbrite",
                        "verified": True,
                    })
                return out
            except Exception as e:
                sources_failed.append(f"Eventbrite: {str(e)[:60]}")
                return []

        # ── 5. Skiddle (UK clubs / underground) ──
        async def fetch_skiddle():
            key = os.environ.get("SKIDDLE_API_KEY")
            if not key: return []
            try:
                params = {
                    "api_key": key, "keyword": city,
                    "minDate": start_iso[:10], "maxDate": end_iso[:10],
                    "limit": 15,
                }
                res = await client.get("https://www.skiddle.com/api/v1/events/", params=params)
                if res.status_code != 200: return []
                data = res.json().get("results", [])
                out = []
                for e in data[:15]:
                    out.append({
                        "name": e.get("eventname","Unknown"),
                        "date": e.get("date",""),
                        "venue": (e.get("venue") or {}).get("name",""),
                        "type": "club",
                        "url": e.get("link",""),
                        "source": "Skiddle",
                        "verified": True,
                    })
                return out
            except Exception as e:
                sources_failed.append(f"Skiddle: {str(e)[:60]}")
                return []

        # ── 6. Gemini fallback (Instagram/Facebook public posts via Google Search) ──
        async def fetch_gemini():
            try:
                prompt = (
                    f"List underground music events, DJ sets, and parties in {city} around {date_str}. "
                    f"Search Instagram/Facebook posts of clubs and promoters in that city. "
                    f"Focus on: techno/house/electronic underground parties, club nights, DJ residencies. "
                    f"Return JSON: {{\"events\":[{{\"name\":\"...\",\"date\":\"...\",\"venue\":\"...\",\"type\":\"underground\",\"artists\":\"...\",\"url\":\"...\"}}]}}. "
                    f"Set verified=false for each. ONLY JSON."
                )
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1500))
                m = _re.search(r'\{[\s\S]*\}', result or "")
                if m:
                    try:
                        data = _json.loads(m.group())
                        events = data.get("events", [])
                        for e in events:
                            e["source"] = "Gemini (verify)"
                            e["verified"] = False
                        return events[:10]
                    except: pass
                return []
            except Exception as e:
                sources_failed.append(f"Gemini: {str(e)[:60]}")
                return []

        # Run all sources in parallel
        results = await asyncio.gather(
            fetch_ra(), fetch_bandsintown(), fetch_ticketmaster(),
            fetch_eventbrite(), fetch_skiddle(), fetch_gemini(),
            return_exceptions=True
        )
        source_names = ["RA","Bandsintown","Ticketmaster","Eventbrite","Skiddle","Gemini"]
        for i, r in enumerate(results):
            if isinstance(r, Exception): continue
            if r:
                all_events.extend(r)
                sources_used.append(source_names[i])

    # Filter by types if requested (comma-separated: electronic,concert,festival,sports,...)
    if types:
        wanted = set(t.strip().lower() for t in types.split(","))
        all_events = [e for e in all_events if (e.get("type","").lower() in wanted or e.get("source","").lower() in wanted)]

    # Sort by date
    all_events.sort(key=lambda x: x.get("date",""))

    return {
        "city": city, "date": date,
        "events": all_events,
        "sources_used": sources_used,
        "sources_failed": sources_failed,
        "total": len(all_events),
    }


@app.post("/api/where-to-go")
async def where_to_go(body: dict):
    """Smart 'where should I travel?' agent.
    Body: {
      origin: 'TLV',
      depart: 'YYYY-MM-DD',
      return: 'YYYY-MM-DD',
      budget: 1500,            # USD total per person
      days: 7,                 # trip length
      candidates?: ['LIS','BCN','LON','...'],  # optional, else AI suggests
      preferences?: 'beach,nightlife',         # optional vibe
      lang?: 'he'/'en'
    }
    Returns ranked destinations by overall value score."""
    import httpx, ai_client
    import json as _json, re as _re
    origin = body.get("origin", "TLV")
    depart = body.get("depart")
    ret = body.get("return")
    budget = float(body.get("budget", 1500))
    days = int(body.get("days", 7))
    candidates = body.get("candidates", [])
    preferences = body.get("preferences", "")
    lang = body.get("lang", "en")

    # Step 1: if no candidates, ask AI for 8 destinations matching budget+vibe
    if not candidates:
        suggest_prompt = (
            f"Suggest 8 international travel destinations (city codes) for a {days}-day trip "
            f"from {origin} with budget ${budget} per person. "
            f"{('Preferences: ' + preferences + '.') if preferences else ''} "
            f"Return JSON: {{\"codes\": [\"LIS\",\"BCN\",...]}}. ONLY JSON."
        )
        loop = asyncio.get_event_loop()
        s = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=suggest_prompt, web_search=False, max_tokens=300))
        m = _re.search(r'\{[\s\S]*\}', s or "")
        if m:
            try: candidates = _json.loads(m.group()).get("codes", [])
            except: pass
        if not candidates:
            candidates = ["LIS","BCN","BUD","ATH","IST","BKK","TBS","KUT"]

    # Step 2: in parallel — fetch flight price + hotel price + weather for each
    amadeus_id = os.environ.get("AMADEUS_CLIENT_ID")
    amadeus_secret = os.environ.get("AMADEUS_CLIENT_SECRET")

    # Get one shared Amadeus token for all parallel calls
    amadeus_token = None
    if amadeus_id and amadeus_secret:
        try:
            async with httpx.AsyncClient(timeout=10) as _c:
                tok = (await _c.post("https://test.api.amadeus.com/v1/security/oauth2/token",
                    headers={"Content-Type":"application/x-www-form-urlencoded"},
                    content=f"grant_type=client_credentials&client_id={amadeus_id}&client_secret={amadeus_secret}")).json()
                amadeus_token = tok.get("access_token")
        except: pass

    async def score_one(code: str):
        info = {"code": code, "flight_price_usd": None, "weather": None, "city_name": code, "hotel_median_usd": None, "hotel_count": 0}
        async with httpx.AsyncClient(timeout=15) as client:
            # ── Flight price ──
            if amadeus_token and depart:
                try:
                    params = f"originLocationCode={origin}&destinationLocationCode={code}&departureDate={depart}&adults=1&max=1&currencyCode=USD"
                    if ret: params += f"&returnDate={ret}"
                    offers = (await client.get(f"https://test.api.amadeus.com/v2/shopping/flight-offers?{params}",
                        headers={"Authorization": f"Bearer {amadeus_token}"})).json()
                    if offers.get("data"):
                        info["flight_price_usd"] = float(offers["data"][0]["price"]["total"])
                except Exception: pass

            # ── Hotel median price ──
            if amadeus_token and depart:
                try:
                    # Step A: list hotels by city
                    hotels_list = (await client.get(
                        f"https://test.api.amadeus.com/v1/reference-data/locations/hotels/by-city?cityCode={code}",
                        headers={"Authorization": f"Bearer {amadeus_token}"}
                    )).json()
                    hotel_ids = [h["hotelId"] for h in (hotels_list.get("data") or [])[:20] if h.get("hotelId")]
                    if hotel_ids:
                        # Step B: get offers
                        check_in = depart
                        check_out = ret or depart
                        params2 = {
                            "hotelIds": ",".join(hotel_ids[:15]),
                            "checkInDate": check_in,
                            "checkOutDate": check_out,
                            "adults": "1",
                            "currency": "USD",
                            "bestRateOnly": "true",
                        }
                        offers2 = (await client.get(
                            "https://test.api.amadeus.com/v3/shopping/hotel-offers",
                            params=params2,
                            headers={"Authorization": f"Bearer {amadeus_token}"}
                        )).json()
                        prices = []
                        for entry in (offers2.get("data") or []):
                            for offer in (entry.get("offers") or []):
                                p = (offer.get("price") or {}).get("total")
                                if p:
                                    try: prices.append(float(p))
                                    except: pass
                        if prices:
                            prices.sort()
                            mid = prices[len(prices)//2]
                            # Convert total stay to per-night
                            from datetime import date as _date_cls
                            try:
                                nights = max(1, (_date_cls.fromisoformat(check_out) - _date_cls.fromisoformat(check_in)).days)
                            except:
                                nights = 1
                            info["hotel_median_usd"] = round(mid / nights, 0)
                            info["hotel_count"] = len(prices)
                            info["hotel_min_usd"] = round(min(prices) / nights, 0)
                            info["hotel_max_usd"] = round(max(prices) / nights, 0)
                except Exception: pass

            # ── Weather (Open-Meteo) ──
            try:
                geo = (await client.get(f"https://geocoding-api.open-meteo.com/v1/search?name={code}&count=1&language=en&format=json")).json()
                if geo.get("results"):
                    loc = geo["results"][0]
                    info["city_name"] = loc.get("name", code)
                    info["country"] = loc.get("country", "")
                    lat, lon = loc["latitude"], loc["longitude"]
                    fc = (await client.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=auto&forecast_days=7")).json()
                    daily = fc.get("daily", {})
                    if daily.get("temperature_2m_max"):
                        info["weather"] = {
                            "avg_high": round(sum(daily["temperature_2m_max"]) / len(daily["temperature_2m_max"]), 1),
                            "avg_low": round(sum(daily["temperature_2m_min"]) / len(daily["temperature_2m_min"]), 1),
                            "rainy_days": sum(1 for p in daily.get("precipitation_sum", []) if p > 1),
                        }
            except Exception: pass
        return info

    results = await asyncio.gather(*[score_one(c) for c in candidates[:10]])

    # Step 3: AI estimates daily costs + vibe for each
    cities_str = ", ".join([r.get("city_name", r["code"]) for r in results])
    lang_inst = "Respond in Hebrew." if lang == "he" else "Respond in English."
    cost_prompt = (
        f"For each city: {cities_str}. "
        f"Provide: 1) daily traveler cost USD (mid-range, all-in: hotel+food+transport+activities), "
        f"2) vibe in one short phrase, 3) safety 1-10, 4) value score 1-10. "
        f"Format JSON: {{\"cities\": [{{\"city\":\"...\", \"daily_cost\":N, \"vibe\":\"...\", \"safety\":N, \"value\":N}}]}}. "
        f"ONLY JSON. {lang_inst}"
    )
    loop = asyncio.get_event_loop()
    ai_resp = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=cost_prompt, web_search=True, max_tokens=1500))
    ai_data = {}
    m = _re.search(r'\{[\s\S]*\}', ai_resp or "")
    if m:
        try: ai_data = _json.loads(m.group())
        except: pass

    # Step 4: Compute final score per city — use REAL hotel data when available
    ranked = []
    for r in results:
        ai_match = next((a for a in ai_data.get("cities", []) if a.get("city","").lower() in r["city_name"].lower() or r["city_name"].lower() in a.get("city","").lower()), {})
        flight = r.get("flight_price_usd")
        # Use real hotel median when present, fallback to AI estimate
        hotel_per_night = r.get("hotel_median_usd")
        ai_daily = ai_match.get("daily_cost", 0)
        # Real daily = real hotel + (AI daily - assumed AI hotel ~50%)
        # If we have hotel data, calculate: hotel + ~50% extra for food/transport/activities
        if hotel_per_night:
            real_daily = round(hotel_per_night * 1.5, 0)  # hotel + 50% buffer
            daily = real_daily
            data_source = "real (hotel) + estimate (food/activities)"
        else:
            daily = ai_daily
            data_source = "AI estimate"

        total_cost = (flight or 0) + (daily * days)
        within_budget = total_cost > 0 and total_cost <= budget
        leftover = budget - total_cost if total_cost > 0 else 0
        value = ai_match.get("value", 5)
        if total_cost == 0:
            score = 0
        elif total_cost <= budget:
            score = round(value * 10 + (leftover / budget) * 30, 1)
        else:
            score = round(value * 5 - ((total_cost - budget) / budget) * 30, 1)
        ranked.append({
            **r,
            "daily_cost": daily,
            "ai_daily_estimate": ai_daily,
            "vibe": ai_match.get("vibe", ""),
            "safety": ai_match.get("safety", 0),
            "value": value,
            "total_cost": round(total_cost, 0) if total_cost > 0 else None,
            "within_budget": within_budget,
            "leftover": round(leftover, 0) if leftover else None,
            "score": score,
            "cost_source": data_source,
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return {"origin": origin, "budget": budget, "days": days, "ranked": ranked}


@app.get("/api/best-time-to-book")
async def best_time_to_book(origin: str, destination: str, depart_month: Optional[str] = None):
    """When is the cheapest time to book/fly a route.
    Returns: { months: [{month, avg_price, sample_date}], best_month, best_advance_days }
    Uses Amadeus Flight Inspiration Search + flexible-dates aggregator."""
    import httpx
    from datetime import date as _date, timedelta as _td
    amadeus_id = os.environ.get("AMADEUS_CLIENT_ID")
    amadeus_secret = os.environ.get("AMADEUS_CLIENT_SECRET")
    if not (amadeus_id and amadeus_secret):
        return JSONResponse({"error": "AMADEUS keys missing"}, status_code=500)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            tok = (await client.post("https://test.api.amadeus.com/v1/security/oauth2/token",
                headers={"Content-Type":"application/x-www-form-urlencoded"},
                content=f"grant_type=client_credentials&client_id={amadeus_id}&client_secret={amadeus_secret}")).json()
            token = tok.get("access_token")
            if not token:
                return JSONResponse({"error": "Amadeus auth failed"}, status_code=500)

            # Sample 12 months ahead, one date per month (15th)
            today = _date.today()
            results = []
            for i in range(0, 12):
                m_date = today.replace(day=15) + _td(days=i*30)
                ret_date = m_date + _td(days=7)
                try:
                    params = {
                        "originLocationCode": origin.upper(),
                        "destinationLocationCode": destination.upper(),
                        "departureDate": m_date.isoformat(),
                        "returnDate": ret_date.isoformat(),
                        "adults": "1", "max": "5", "currencyCode": "USD",
                    }
                    r = await client.get("https://test.api.amadeus.com/v2/shopping/flight-offers",
                        params=params, headers={"Authorization": f"Bearer {token}"})
                    data = r.json()
                    if data.get("data"):
                        prices = [float(o["price"]["total"]) for o in data["data"][:5]]
                        avg = sum(prices) / len(prices)
                        results.append({
                            "month": m_date.strftime("%Y-%m"),
                            "month_name": m_date.strftime("%b %Y"),
                            "avg_price": round(avg, 0),
                            "min_price": round(min(prices), 0),
                            "sample_date": m_date.isoformat(),
                            "samples": len(prices),
                        })
                except Exception: continue

            # Best month (lowest avg)
            if not results:
                return {"months": [], "error": "no data found for route"}
            best = min(results, key=lambda x: x["avg_price"])
            avg_overall = sum(r["avg_price"] for r in results) / len(results)
            savings_pct = round((avg_overall - best["avg_price"]) / avg_overall * 100, 1) if avg_overall > 0 else 0

            return {
                "origin": origin, "destination": destination,
                "months": results,
                "best_month": best,
                "avg_overall": round(avg_overall, 0),
                "savings_pct_vs_avg": savings_pct,
                "advice_advance_weeks": "6-8",
                "advice_day_of_week": "Tuesday-Wednesday",
            }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/costs")
async def destination_costs(city: str, lang: Optional[str] = "en"):
    """Cost of living + travel costs for destination — Numbeo-based.
    Falls back to AI estimate if Numbeo key missing."""
    import httpx, ai_client
    numbeo_key = os.environ.get("NUMBEO_API_KEY")

    if numbeo_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Numbeo cost-of-living indices
                r = await client.get(f"https://www.numbeo.com/api/city_prices?api_key={numbeo_key}&query={city}")
                if r.status_code == 200:
                    data = r.json()
                    prices = data.get("prices", [])
                    # Group by category
                    grouped = {}
                    for p in prices:
                        cat = p.get("item_id_category", {}).get("name", "Other")
                        grouped.setdefault(cat, []).append({
                            "name": p.get("item_name"),
                            "avg": p.get("average_price"),
                            "currency": p.get("currency"),
                        })
                    return {"city": city, "source": "Numbeo", "categories": grouped, "raw": data}
        except Exception: pass

    # Fallback: AI estimate
    lang_inst = "Respond in Hebrew." if lang == "he" else "Respond in English."
    prompt = (
        f"Provide typical costs for tourists in {city} in USD. "
        f"Cover: 1) Hotels (3*/4*/5* per night), 2) Meals (cheap/midrange/fine dining), "
        f"3) Transport (single ticket, day pass, taxi 5km, Uber average), "
        f"4) Drinks (coffee, beer at bar, water bottle), "
        f"5) Activities (museum entry, day tour, club entry). "
        f"Format JSON: {{\"hotels\":{{\"3star\":N,\"4star\":N,\"5star\":N}}, "
        f"\"meals\":{{\"cheap\":N,\"midrange\":N,\"luxury\":N}}, "
        f"\"transport\":{{\"single\":N,\"day_pass\":N,\"taxi_5km\":N,\"uber\":N}}, "
        f"\"drinks\":{{\"coffee\":N,\"beer\":N,\"water\":N}}, "
        f"\"activities\":{{\"museum\":N,\"day_tour\":N,\"club\":N}}}}. "
        f"ONLY JSON. {lang_inst}"
    )
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1000))
    import json as _json, re as _re
    m = _re.search(r'\{[\s\S]*\}', result or "")
    if m:
        try:
            return {"city": city, "source": "AI estimate", "data": _json.loads(m.group())}
        except: pass
    return {"city": city, "source": "AI estimate", "raw": result}


@app.post("/api/destination/compare")
async def destination_compare(body: dict):
    """Compare multiple destinations side-by-side (weather + AI summary).
    body: { cities: ["Lisbon", "Barcelona", ...], date?: "YYYY-MM-DD", lang?: "he"/"en" }
    """
    import httpx
    import ai_client
    cities = body.get("cities", [])
    date = body.get("date")
    lang = body.get("lang", "en")
    if not cities or not isinstance(cities, list):
        return JSONResponse({"error": "missing cities array"}, status_code=400)

    async def fetch_one(city: str):
        result = {"city": city, "weather": None, "summary": None}
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                geo = (await client.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json")).json()
                if geo.get("results"):
                    loc = geo["results"][0]
                    lat, lon = loc["latitude"], loc["longitude"]
                    result["country"] = loc.get("country", "")
                    fc = (await client.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code&timezone=auto&forecast_days=7")).json()
                    daily = fc.get("daily", {})
                    if daily.get("temperature_2m_max"):
                        result["weather"] = {
                            "avg_high": sum(daily["temperature_2m_max"]) / len(daily["temperature_2m_max"]),
                            "avg_low": sum(daily["temperature_2m_min"]) / len(daily["temperature_2m_min"]),
                            "total_precip": sum(daily.get("precipitation_sum", [0])),
                            "code": daily["weather_code"][0] if daily.get("weather_code") else None,
                        }
            except Exception:
                pass
        return result

    weather_results = await asyncio.gather(*[fetch_one(c) for c in cities])

    # AI summary in parallel (cost of living, vibe, best season)
    lang_inst = "Respond in Hebrew." if lang == "he" else "Respond in English."
    ai_prompt = (
        f"Compare these destinations: {', '.join(cities)}. "
        f"For each, provide: 1) approx daily traveler cost (USD budget+midrange+luxury), "
        f"2) vibe/atmosphere in 1 short sentence, 3) best time of year to visit, "
        f"4) top 1 must-see attraction, 5) safety rating 1-10. "
        f"Format JSON: {{\"comparison\": [{{\"city\":\"...\", \"daily_cost\":{{\"budget\":N, \"mid\":N, \"luxury\":N}}, \"vibe\":\"...\", \"best_season\":\"...\", \"top_attraction\":\"...\", \"safety\":N}}]}}. "
        f"Return ONLY valid JSON, no markdown. {lang_inst}"
    )
    loop = asyncio.get_event_loop()
    ai_result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=ai_prompt, web_search=True, max_tokens=2000))
    import json as _json, re as _re
    ai_data = {"comparison": []}
    if ai_result:
        m = _re.search(r'\{[\s\S]*\}', ai_result)
        if m:
            try: ai_data = _json.loads(m.group())
            except: pass

    # Merge weather + AI
    merged = []
    for w in weather_results:
        ai_match = next((c for c in ai_data.get("comparison", []) if c.get("city", "").lower() in w["city"].lower() or w["city"].lower() in c.get("city", "").lower()), {})
        merged.append({**w, **ai_match})

    return {"cities": merged, "raw_ai": ai_result if not ai_data.get("comparison") else None}


@app.get("/api/expiring-deals")
async def expiring_deals(hours_ahead: float = 3.0):
    """Deals that are about to expire."""
    import deal_hunter as dh
    try:
        deals = dh.get_expiring_deals(hours_ahead=hours_ahead)
        return {"deals": deals, "hours_ahead": hours_ahead}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/insights/patterns")
async def insights_patterns():
    """Pattern analysis from local DB (best day, best hour, top destinations)."""
    import deal_insights
    try:
        patterns = deal_insights.get_deal_patterns()
        return patterns
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/calendar")
async def price_calendar(body: dict):
    """Visual price calendar — wraps flexible_dates and returns daily prices."""
    import flexible_search
    try:
        origin = body.get("origin") or body.get("from")
        destination = body.get("destination") or body.get("to")
        month = body.get("month")  # YYYY-MM
        if not origin or not destination or not month:
            return JSONResponse({"error": "missing origin/destination/month"}, status_code=400)
        year, mon = map(int, month.split("-"))
        result = flexible_search.find_cheapest_days(origin, destination, year=year, month=mon)
        return {"calendar": result, "origin": origin, "destination": destination, "month": month}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ════════════════════════════════════════════════════════════
# SETTINGS (env-based)
# ════════════════════════════════════════════════════════════

SETTINGS_KEYS = [
    "GEMINI_API_KEY", "AMADEUS_CLIENT_ID", "AMADEUS_CLIENT_SECRET",
    "KIWI_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "NTFY_TOPIC", "NTFY_SERVER",
]

@app.get("/api/settings")
async def get_settings():
    return {
        k: ("***" if os.environ.get(k) else "") for k in SETTINGS_KEYS
    }


@app.post("/api/settings")
async def save_settings(body: dict):
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    for key, value in body.items():
        if key not in SETTINGS_KEYS or not value or value == "***":
            continue
        if not isinstance(value, str) or len(value) > 500 or "\n" in value or "\r" in value:
            continue
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}")
        os.environ[key] = value
    env_path.write_text("\n".join(lines) + "\n")
    return {"ok": True}


# ════════════════════════════════════════════════════════════
# SENTIMENT / NEWS
# ════════════════════════════════════════════════════════════

@app.get("/api/sentiment")
async def get_sentiment(request: Request, destination: str = ""):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"Daily AI limit reached on {plan} plan. Upgrade at wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Travel sentiment for {destination or 'popular destinations'}: prices trending up or down? Any major disruptions or great deals in the last 48 hours? Be concise."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=600))
    return {"result": result or ""}


# ════════════════════════════════════════════════════════════
# AI TOOLS — all plan-gated
# ════════════════════════════════════════════════════════════

def _ai_post(prompt: str, web: bool = False, tokens: int = 800) -> str:
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as ex:
        fut = ex.submit(ai_client.ask, prompt=prompt, web_search=web, max_tokens=tokens)
        return fut.result() or ""


def _quota_exceeded_msg(plan: str) -> str:
    limit = _AI_DAILY_LIMITS.get(plan, 5)
    return f"Daily AI limit reached ({limit}/day on {plan} plan). Upgrade at wizelife.ai"


def _lang_instruction(lang: str) -> str:
    instructions = {
        "he": "Respond in Hebrew.",
        "pt": "Respond in Portuguese.",
        "es": "Respond in Spanish.",
    }
    return instructions.get(lang, "")


class AIQuery(BaseModel):
    text:  str           = Field(..., max_length=1000)
    extra: Optional[str] = Field("", max_length=500)
    lang:  Optional[str] = "he"

    @field_validator("lang")
    @classmethod
    def val_lang(cls, v: Optional[str]) -> str:
        return _clean_lang(v)

    @field_validator("text")
    @classmethod
    def val_text(cls, v: str) -> str:
        return v.strip()


@app.post("/api/wait-or-buy")
async def wait_or_buy(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Travel price analysis: {body.text}. Should the traveler buy now or wait? Analyze historical patterns, seasonality, current trends. Give a clear recommendation with reasoning. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/ai-opps")
async def ai_opportunities(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Find the best travel deals and opportunities right now for: {body.text or 'any destination'}. Focus on flash sales, error fares, last-minute deals. Be specific with prices and airlines. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1000))
    return {"result": result or ""}


@app.post("/api/surprise")
async def surprise_destination(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    budget = body.text or "500 USD"
    prefs = body.extra or ""
    prompt = f"Suggest 3 surprising, underrated travel destinations for budget {budget}. {prefs} Include: why it's special, best time to go, estimated flight cost. Make it exciting and unexpected. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/trip-planner")
async def trip_planner(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Create a detailed travel itinerary: {body.text}. Include: day-by-day plan, accommodation tips, must-see attractions, local food, transportation, estimated budget breakdown. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1200))
    return {"result": result or ""}


@app.post("/api/multi-city")
async def multi_city(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Plan a multi-city route: {body.text}. Find the most cost-efficient order to visit these cities, best airlines for each leg, estimated prices. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=900))
    return {"result": result or ""}


@app.post("/api/stopovers")
async def stopovers(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Find free stopover opportunities for route: {body.text}. Which airlines offer free stopovers on this route? How much extra time is allowed? What to do during the stopover? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/flexible-dates")
async def flexible_dates(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Find cheapest travel dates for: {body.text}. Compare prices across different weeks/months. Identify the cheapest day of week to fly. {_lang_instruction(body.lang or 'he')} Include a clear price comparison table."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/predict")
async def predict_price(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Price prediction for travel: {body.text}. Based on historical patterns, seasonality, current market trends — will prices go up or down in the next 2-4 weeks? Give a confidence score. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=700))
    return {"result": result or ""}


@app.post("/api/true-cost")
async def true_cost(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Calculate the true total cost of this trip: {body.text}. Break down: flights, accommodation, food, transport, activities, visas, travel insurance, luggage fees, airport transfers. Give realistic daily budget. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=900))
    return {"result": result or ""}


@app.post("/api/points-vs-cash")
async def points_vs_cash(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Points vs cash analysis for: {body.text}. Compare: cost in cash vs using miles/points, which loyalty programs have the best redemption value for this route, is it worth collecting points? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/deal-insights")
async def deal_insights_endpoint(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Deep deal analysis for: {body.text}. Identify patterns: best booking window, cheapest months, airline price strategies, hidden fees. {_lang_instruction(body.lang or 'he')}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/competitor")
async def competitor_check(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Compare prices across booking sites for: {body.text}. Check Google Flights, Kayak, Skyscanner, Kiwi, direct airline. Which site currently has the best price? Any exclusive deals? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/kiwi")
async def kiwi_search(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    prompt = f"Search Kiwi.com for: {body.text}. Find creative routes using Kiwi's virtual interlining — combinations of low-cost carriers that Kiwi connects. What are the cheapest options? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/rss")
async def rss_scan(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, _quota_exceeded_msg(plan))
    loop = asyncio.get_event_loop()
    dest = body.text or "general travel"
    prompt = f"Find the latest travel deal alerts and discussions from Reddit (r/churning, r/solotravel, r/flights), travel blogs, and deal sites for: {dest}. What are people talking about right now? Any hot deals? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=900))
    return {"result": result or ""}


# ════════════════════════════════════════════════════════════
# TELEGRAM BOT
# ════════════════════════════════════════════════════════════

def tg_mod():   return _lazy("telegram_bot")

@app.post("/api/telegram/test")
async def telegram_test(body: dict):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN") or body.get("token", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")   or body.get("chat_id", "")
    if not token or not chat_id:
        raise HTTPException(400, "token and chat_id required")
    mod = tg_mod()
    if not mod:
        raise HTTPException(500, "telegram_bot module not available")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: mod.test_connection(token, chat_id))

@app.post("/api/telegram/send")
async def telegram_send(body: dict):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN") or body.get("token", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")   or body.get("chat_id", "")
    msg     = body.get("message", "")
    if not token or not chat_id or not msg:
        raise HTTPException(400, "token, chat_id and message required")
    mod = tg_mod()
    if not mod:
        raise HTTPException(500, "telegram_bot module not available")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: mod.send_message(token, chat_id, msg))

@app.get("/api/telegram/info")
async def telegram_info():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"ok": False, "error": "No token configured"}
    mod = tg_mod()
    if not mod:
        return {"ok": False, "error": "module unavailable"}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: mod.get_bot_info(token))

@app.get("/api/telegram/chat-id")
async def telegram_chat_id():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise HTTPException(400, "No token configured")
    mod = tg_mod()
    if not mod:
        raise HTTPException(500, "module unavailable")
    loop = asyncio.get_event_loop()
    updates = await loop.run_in_executor(None, lambda: mod.get_updates(token))
    found   = mod.extract_chat_id(updates)
    return {"chat_id": found}


# ════════════════════════════════════════════════════════════
# AUTO-BOOK
# ════════════════════════════════════════════════════════════

def ab_mod(): return _lazy("auto_book")

@app.get("/api/auto-book/rules")
async def get_ab_rules():
    mod = ab_mod()
    if not mod:
        return []
    mod.ensure_auto_book_table()
    return mod.get_rules(enabled_only=False) or []

class AutoBookRule(BaseModel):
    name: str
    origin: str = "TLV"
    destination: str
    max_price: float
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    mode: str = "notify"

@app.post("/api/auto-book/rules", status_code=201)
async def add_ab_rule(body: AutoBookRule):
    mod = ab_mod()
    if not mod:
        raise HTTPException(500, "auto_book module not available")
    mod.ensure_auto_book_table()
    rule_id = mod.add_rule(
        name=body.name, origin=body.origin, destination=body.destination,
        max_price=body.max_price, date_from=body.date_from,
        date_to=body.date_to, mode=body.mode,
    )
    return {"id": rule_id}

@app.delete("/api/auto-book/rules/{rule_id}")
async def delete_ab_rule(rule_id: int):
    mod = ab_mod()
    if not mod:
        raise HTTPException(500, "auto_book module not available")
    mod.delete_rule(rule_id)
    return {"ok": True}

@app.patch("/api/auto-book/rules/{rule_id}/toggle")
async def toggle_ab_rule(rule_id: int, enabled: bool = True):
    mod = ab_mod()
    if not mod:
        raise HTTPException(500, "auto_book module not available")
    mod.toggle_rule(rule_id, enabled)
    return {"ok": True}

@app.get("/api/auto-book/log")
async def get_ab_log():
    mod = ab_mod()
    if not mod:
        return []
    return mod.get_booking_log(limit=20) or []

class PassengerConfig(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    passport: str = ""
    dob: str = ""

@app.post("/api/auto-book/passenger")
async def save_passenger(body: PassengerConfig):
    mod = ab_mod()
    if not mod:
        raise HTTPException(500, "auto_book module not available")
    mod.save_passenger_config(body.dict())
    return {"ok": True}


# ════════════════════════════════════════════════════════════
# POSITIONING
# ════════════════════════════════════════════════════════════

def pos_mod(): return _lazy("positioning")

class PositioningQuery(BaseModel):
    destination: str           = Field(..., min_length=2, max_length=10)
    travel_date: str
    return_date: Optional[str] = None
    budget:      float         = Field(0.0, ge=0)
    travelers:   int           = Field(1, ge=1, le=9)
    lang:        Optional[str] = "he"

    @field_validator("travel_date", "return_date")
    @classmethod
    def val_date(cls, v: Optional[str]) -> Optional[str]:
        return _check_date(v)

    @field_validator("lang")
    @classmethod
    def val_lang(cls, v: Optional[str]) -> str:
        return _clean_lang(v)

@app.post("/api/positioning")
async def find_positioning(body: PositioningQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, "Daily AI limit reached")
    mod = pos_mod()
    loop = asyncio.get_event_loop()
    if mod:
        opps = await loop.run_in_executor(
            None,
            lambda: mod.find_positioning_opportunities(
                destination=body.destination, travel_date=body.travel_date,
                return_date=body.return_date or "", budget=body.budget,
                travelers=body.travelers,
            )
        )
        return {"opportunities": opps or []}
    # AI fallback
    prompt = (
        f"Find positioning flight opportunities from TLV to {body.destination} on {body.travel_date}. "
        f"Budget: ${body.budget or 'any'}. Is it cheaper to fly TLV→Hub→{body.destination}? "
        f"List top 3 hubs with estimated prices, savings%, and tips. {_lang_instruction(body.lang or 'he')}"
    )
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=900))
    return {"opportunities": [], "ai_result": result or ""}

@app.get("/api/positioning/routes")
async def positioning_routes(request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, "Daily AI limit reached")
    mod = pos_mod()
    loop = asyncio.get_event_loop()
    if mod:
        routes = await loop.run_in_executor(None, mod.get_cheapest_tlv_positioning_routes)
        return {"routes": routes or []}
    result = await loop.run_in_executor(None, lambda: ai_client.ask(
        prompt="What are the 5 cheapest positioning hubs from TLV? List city, airport code, price from TLV, best airline, and why it's good for positioning.",
        web_search=True, max_tokens=600
    ))
    return {"routes": [], "ai_result": result or ""}

class ROIQuery(BaseModel):
    tlv_to_hub: float
    hub_to_dest: float
    direct_price: float
    extra_time_hours: float = 6
    hourly_rate: float = 20

@app.post("/api/positioning/roi")
async def positioning_roi(body: ROIQuery):
    mod = pos_mod()
    if mod:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: mod.calculate_positioning_roi(
                tlv_to_hub=body.tlv_to_hub, hub_to_dest=body.hub_to_dest,
                direct_price=body.direct_price, extra_time_hours=body.extra_time_hours,
                hourly_rate=body.hourly_rate,
            )
        )
        return result or {}
    total      = body.tlv_to_hub + body.hub_to_dest
    savings    = body.direct_price - total
    time_cost  = body.extra_time_hours * body.hourly_rate
    net        = savings - time_cost
    return {
        "gross_savings": round(savings, 2),
        "gross_savings_pct": round(savings / body.direct_price * 100, 1) if body.direct_price else 0,
        "time_cost": round(time_cost, 2),
        "net_savings": round(net, 2),
        "verdict": f"✅ Worth it! Net savings ${net:.0f}" if net > 0 else f"❌ Not worth it — time cost (${time_cost:.0f}) exceeds savings (${savings:.0f})",
    }


# ════════════════════════════════════════════════════════════
# WHATSAPP BOT
# ════════════════════════════════════════════════════════════

def wa_mod(): return _lazy("whatsapp_bot")

@app.post("/api/whatsapp/test")
async def whatsapp_test(body: dict):
    msg = body.get("message", "")
    if not msg:
        raise HTTPException(400, "message required")
    mod = wa_mod()
    if not mod:
        raise HTTPException(500, "whatsapp_bot module not available")
    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(None, lambda: mod.process_incoming_message("test_user", msg))
    return {"reply": reply}

@app.post("/api/whatsapp/send")
async def whatsapp_send(body: dict):
    to  = body.get("to", "")
    msg = body.get("message", "")
    if not to or not msg:
        raise HTTPException(400, "to and message required")
    mod = wa_mod()
    if not mod:
        raise HTTPException(500, "whatsapp_bot module not available")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: mod.send_whatsapp_message(to, msg))

@app.get("/api/whatsapp/stats")
async def whatsapp_stats():
    mod = wa_mod()
    if not mod:
        return {"total_messages": 0, "unique_users": 0, "messages_today": 0, "flight_searches": 0}
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, mod.get_stats) or {}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
