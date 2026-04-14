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
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

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


# ── App init ──────────────────────────────────────────────────────────────────
db.init_db()

app = FastAPI(title="Noded API", version="3.0")

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
    name: str
    category: str          # flight / hotel / apartment / package
    query: str
    destination: str
    origin: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    max_price: Optional[float] = None
    drop_pct: float = 10.0


@app.get("/api/watches")
async def list_watches(all: bool = False):
    items = db.get_all_watch_items(enabled_only=not all)
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
    messages: list[dict]    # [{"role": "user"|"model", "parts": [{"text": "..."}]}]
    system: str = ""
    web_search: bool = False


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
        text = reply or "⚠️ לא הצלחתי לקבל תשובה. בדוק שה-GEMINI_API_KEY מוגדר."
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
    result = await loop.run_in_executor(None, mod.analyze_price_dna)
    return result or {"summary": "No data yet"}


# ════════════════════════════════════════════════════════════
# DEAL HUNTER
# ════════════════════════════════════════════════════════════

class DealHuntQuery(BaseModel):
    origin: str
    budget: Optional[float] = None
    dates: Optional[str] = None
    preferences: str = ""


@app.post("/api/deal-hunter")
async def hunt_deals(body: DealHuntQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"Daily AI limit reached on {plan} plan. Upgrade at wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Find best flight deals from {body.origin}. Budget: {body.budget or 'any'}. Dates: {body.dates or 'flexible'}. {body.preferences}"
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1024))
    return {"result": result or "No deals found"}


# ════════════════════════════════════════════════════════════
# VISA CHECK
# ════════════════════════════════════════════════════════════

class VisaQuery(BaseModel):
    passport: str
    destination: str


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
    origin: str
    destination: str
    date: Optional[str] = None


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
        rates = await loop.run_in_executor(None, lambda: mod.get_rates("USD"))
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
    name: str
    watch_id: Optional[int] = None
    conditions: dict = {}


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


class AIQuery(BaseModel):
    text: str
    extra: Optional[str] = ""


@app.post("/api/wait-or-buy")
async def wait_or_buy(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Travel price analysis: {body.text}. Should the traveler buy now or wait? Analyze historical patterns, seasonality, current trends. Give a clear recommendation with reasoning. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/ai-opps")
async def ai_opportunities(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Find the best travel deals and opportunities right now for: {body.text or 'any destination'}. Focus on flash sales, error fares, last-minute deals. Be specific with prices and airlines. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1000))
    return {"result": result or ""}


@app.post("/api/surprise")
async def surprise_destination(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    budget = body.text or "500 USD"
    prefs = body.extra or ""
    prompt = f"Suggest 3 surprising, underrated travel destinations for budget {budget}. {prefs} Include: why it's special, best time to go, estimated flight cost. Make it exciting and unexpected. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/trip-planner")
async def trip_planner(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Create a detailed travel itinerary: {body.text}. Include: day-by-day plan, accommodation tips, must-see attractions, local food, transportation, estimated budget breakdown. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=1200))
    return {"result": result or ""}


@app.post("/api/multi-city")
async def multi_city(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Plan a multi-city route: {body.text}. Find the most cost-efficient order to visit these cities, best airlines for each leg, estimated prices. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=900))
    return {"result": result or ""}


@app.post("/api/stopovers")
async def stopovers(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Find free stopover opportunities for route: {body.text}. Which airlines offer free stopovers on this route? How much extra time is allowed? What to do during the stopover? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/flexible-dates")
async def flexible_dates(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Find cheapest travel dates for: {body.text}. Compare prices across different weeks/months. Identify the cheapest day of week to fly. Respond in Hebrew with a clear price comparison table."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/predict")
async def predict_price(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Price prediction for travel: {body.text}. Based on historical patterns, seasonality, current market trends — will prices go up or down in the next 2-4 weeks? Give a confidence score. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=700))
    return {"result": result or ""}


@app.post("/api/true-cost")
async def true_cost(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Calculate the true total cost of this trip: {body.text}. Break down: flights, accommodation, food, transport, activities, visas, travel insurance, luggage fees, airport transfers. Give realistic daily budget. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=900))
    return {"result": result or ""}


@app.post("/api/points-vs-cash")
async def points_vs_cash(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Points vs cash analysis for: {body.text}. Compare: cost in cash vs using miles/points, which loyalty programs have the best redemption value for this route, is it worth collecting points? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/deal-insights")
async def deal_insights_endpoint(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Deep deal analysis for: {body.text}. Identify patterns: best booking window, cheapest months, airline price strategies, hidden fees. Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/competitor")
async def competitor_check(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Compare prices across booking sites for: {body.text}. Check Google Flights, Kayak, Skyscanner, Kiwi, direct airline. Which site currently has the best price? Any exclusive deals? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/kiwi")
async def kiwi_search(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
    loop = asyncio.get_event_loop()
    prompt = f"Search Kiwi.com for: {body.text}. Find creative routes using Kiwi's virtual interlining — combinations of low-cost carriers that Kiwi connects. What are the cheapest options? Respond in Hebrew."
    result = await loop.run_in_executor(None, lambda: ai_client.ask(prompt=prompt, web_search=True, max_tokens=800))
    return {"result": result or ""}


@app.post("/api/rss")
async def rss_scan(body: AIQuery, request: Request):
    allowed, plan, _ = _check_ai_quota(request)
    if not allowed:
        raise HTTPException(429, f"הגעת למגבלת AI יומית ({plan}). שדרג ב-wizelife.ai")
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
    destination: str
    travel_date: str
    return_date: Optional[str] = None
    budget: float = 0
    travelers: int = 1

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
        "List top 3 hubs with estimated prices, savings%, and tips. Respond in Hebrew."
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
        prompt="What are the 5 cheapest positioning hubs from TLV? List city, airport code, price from TLV, best airline, and why it's good for positioning. Respond in Hebrew.",
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
        "verdict": f"✅ משתלם! חוסך ${net:.0f} נטו" if net > 0 else f"❌ לא משתלם — עלות הזמן (${time_cost:.0f}) גדולה מהחיסכון (${savings:.0f})",
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
