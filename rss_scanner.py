"""
RSS & Reddit Real-Time Deal Scanner — סורק דילים בזמן אמת.
מקורות: Secret Flying, TheFlightDeal, Reddit r/shoestring, Flyertalk, FlyerTalk mistake fares.
שומר לDB ושולח התראות מיידיות.
"""
import json
import re
import sqlite3
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import anthropic

DB_PATH = Path(__file__).parent / "prices.db"

RSS_FEEDS = [
    {
        "name": "Secret Flying — Israel",
        "url": "https://www.secretflying.com/posts/category/ex-israel/feed/",
        "type": "secretflying",
    },
    {
        "name": "Secret Flying — Global",
        "url": "https://www.secretflying.com/feed/",
        "type": "secretflying",
    },
    {
        "name": "The Flight Deal",
        "url": "https://www.theflightdeal.com/feed/",
        "type": "theflightdeal",
    },
    {
        "name": "Fly4Free",
        "url": "https://fly4free.com/feed/",
        "type": "fly4free",
    },
    {
        "name": "FlyerTalk Deals",
        "url": "https://www.flyertalk.com/forum/external/rss/236.xml",
        "type": "flyertalk",
    },
]

REDDIT_SUBS = [
    "shoestring",
    "solotravel",
    "churning",
    "travel",
    "flights",
]

IL_KEYWORDS = [
    "israel", "tel aviv", "tlv", "elal", "el al", "israir",
    "ישראל", "תל אביב", "נתבג", "נתב\"ג",
]

DEAL_KEYWORDS = [
    "mistake fare", "error fare", "flash sale", "deal", "cheap",
    "under $", "under €", "from $", "from €", "sale",
    "שגיאת מחיר", "דיל", "מבצע", "זול",
]


def ensure_rss_table():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_deals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source       TEXT,
                title        TEXT,
                description  TEXT,
                url          TEXT UNIQUE,
                published    TEXT,
                origin       TEXT,
                destination  TEXT,
                price        REAL,
                currency     TEXT,
                deal_type    TEXT DEFAULT 'rss',
                score        REAL DEFAULT 0,
                found_at     TEXT,
                seen         INTEGER DEFAULT 0
            )
        """)


def _fetch_url(url: str, timeout: int = 10) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MegaTraveller/1.0 (travel deal aggregator)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _parse_rss(xml_text: str) -> list:
    items = []
    try:
        root = ET.fromstring(xml_text)
        # Handle both RSS and Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                items.append({
                    "title": title,
                    "description": re.sub(r"<[^>]+>", " ", desc)[:500],
                    "url": link,
                    "published": pub,
                })
        else:
            for entry in root.findall("atom:entry", ns) or root.findall("entry"):
                title = entry.findtext("title") or ""
                summary = entry.findtext("summary") or ""
                link_el = entry.find("link")
                link = link_el.get("href", "") if link_el is not None else ""
                pub = entry.findtext("published") or entry.findtext("updated") or ""
                items.append({
                    "title": title.strip(),
                    "description": re.sub(r"<[^>]+>", " ", summary)[:500],
                    "url": link,
                    "published": pub,
                })
    except Exception:
        pass
    return items


def _score_rss_item(title: str, desc: str) -> float:
    text = (title + " " + desc).lower()
    score = 3.0
    if any(k in text for k in ["mistake fare", "error fare", "שגיאת מחיר"]):
        score += 4.0
    elif any(k in text for k in ["flash sale", "מכירת פלאש"]):
        score += 2.5
    if any(k in text for k in IL_KEYWORDS):
        score += 1.5
    # Price extraction — lower = better score bonus
    prices = re.findall(r"[$€£](\d{2,4})", text)
    if prices:
        min_price = min(int(p) for p in prices)
        if min_price < 100:
            score += 2.0
        elif min_price < 200:
            score += 1.0
    if any(k in text for k in ["one way", "one-way", "חד כיווני"]):
        score += 0.5
    return min(10.0, score)


def _extract_price(text: str):
    matches = re.findall(r"[$€£]\s*(\d{2,4})", text)
    if matches:
        return float(min(int(m) for m in matches))
    return None


def _extract_route(text: str):
    codes = re.findall(r"\b([A-Z]{3})\b", text)
    origin, destination = "", ""
    if len(codes) >= 2:
        # Filter out common non-airport codes
        skip = {"USD", "EUR", "GBP", "ILS", "ONE", "WAY", "FOR", "THE", "AND"}
        airport_codes = [c for c in codes if c not in skip]
        if airport_codes:
            origin = airport_codes[0]
            destination = airport_codes[-1] if len(airport_codes) > 1 else ""
    return origin, destination


def scan_rss_feeds(feeds: list = None) -> list:
    """סרוק feeds ושמור דילים חדשים ל-DB."""
    ensure_rss_table()
    feeds = feeds or RSS_FEEDS
    saved = []
    now = datetime.now().isoformat()

    for feed in feeds:
        xml_text = _fetch_url(feed["url"])
        if not xml_text:
            continue
        items = _parse_rss(xml_text)

        with sqlite3.connect(DB_PATH) as conn:
            for item in items:
                if not item.get("url") or not item.get("title"):
                    continue
                score = _score_rss_item(item["title"], item["description"])
                if score < 3.5:
                    continue

                price = _extract_price(item["title"] + " " + item["description"])
                origin, destination = _extract_route(item["title"] + " " + item["description"])

                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO rss_deals
                        (source, title, description, url, published, origin,
                         destination, price, currency, score, found_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        feed["name"], item["title"], item["description"],
                        item["url"], item["published"],
                        origin, destination, price, "USD", score, now,
                    ))
                    saved.append({
                        "source": feed["name"],
                        "title": item["title"],
                        "url": item["url"],
                        "score": score,
                        "price": price,
                        "origin": origin,
                        "destination": destination,
                    })
                except sqlite3.IntegrityError:
                    pass  # Already exists

    saved.sort(key=lambda x: x.get("score", 0), reverse=True)
    return saved


def scan_reddit_deals(subreddits: list = None, keywords: list = None) -> list:
    """סרוק Reddit לדילים חמים באמצעות Claude web_search."""
    client = anthropic.Anthropic()
    subs = subreddits or REDDIT_SUBS[:3]
    kws = keywords or ["deal", "mistake fare", "cheap flight", "error fare"]

    subs_str = " OR ".join(f"r/{s}" for s in subs)
    kws_str = " OR ".join(f'"{k}"' for k in kws[:4])

    prompt = f"""חפש דילי טיסות חמים ב-Reddit:
חפש ב: {subs_str}
מילות מפתח: {kws_str}
תאריך: מה-7 ימים האחרונים בלבד

מצא את ה-5 הפוסטים הכי אטרקטיביים עם מחירים ספציפיים.

לכל פוסט:
{{
  "subreddit": "r/shoestring",
  "title": "כותרת הפוסט",
  "url": "https://reddit.com/...",
  "price": 000,
  "currency": "USD",
  "origin": "XXX",
  "destination": "YYY",
  "deal_type": "mistake_fare/flash_sale/deal",
  "upvotes_approx": 000,
  "posted_hours_ago": 0,
  "summary": "תיאור קצר"
}}

החזר JSON array."""

    ensure_rss_table()
    try:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2000,
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        arr = re.search(r"\[.*\]", text, re.DOTALL)
        if arr:
            results = json.loads(arr.group(0))
            now = datetime.now().isoformat()
            with sqlite3.connect(DB_PATH) as conn:
                for r in results:
                    score = 6.0
                    if r.get("deal_type") == "mistake_fare":
                        score = 9.0
                    elif r.get("deal_type") == "flash_sale":
                        score = 7.5
                    if r.get("price", 999) < 150:
                        score += 1.0
                    try:
                        conn.execute("""
                            INSERT OR IGNORE INTO rss_deals
                            (source, title, description, url, origin, destination,
                             price, currency, deal_type, score, found_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        """, (
                            r.get("subreddit", "Reddit"),
                            r.get("title", ""),
                            r.get("summary", ""),
                            r.get("url", ""),
                            r.get("origin", ""),
                            r.get("destination", ""),
                            r.get("price"),
                            r.get("currency", "USD"),
                            r.get("deal_type", "deal"),
                            min(10.0, score),
                            now,
                        ))
                    except sqlite3.IntegrityError:
                        pass
            return sorted(results, key=lambda x: x.get("upvotes_approx", 0), reverse=True)
    except Exception as e:
        return [{"error": str(e)}]
    return []


def get_recent_rss_deals(limit: int = 30, min_score: float = 4.0) -> list:
    ensure_rss_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM rss_deals
            WHERE score >= ?
            ORDER BY score DESC, found_at DESC LIMIT ?
        """, (min_score, limit)).fetchall()
    return [dict(r) for r in rows]


def get_unseen_deals(min_score: float = 6.0) -> list:
    ensure_rss_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM rss_deals
            WHERE seen = 0 AND score >= ?
            ORDER BY score DESC LIMIT 10
        """, (min_score,)).fetchall()
    return [dict(r) for r in rows]


def mark_seen(deal_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE rss_deals SET seen=1 WHERE id=?", (deal_id,))
