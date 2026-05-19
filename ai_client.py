"""
Unified AI client — Gemini (free) with web search.
Drop-in replacement for direct Anthropic calls across the project.

Usage:
    from ai_client import ask, ask_with_search

    text = ask(system="You are...", prompt="Find price for...")
    text = ask_with_search(system="...", prompt="...")
"""
import os
import json
import re
from typing import Optional

_client = None

# ── Affiliate / monetization instruction ──────────────────────────────────────
# Appended to system prompts (or user prompts) on AI routes that surface
# destination / hotel / flight / activity recommendations. The marker `529725`
# is our Travelpayouts affiliate ID. Routes that return pure facts (visa rules,
# math, error messages, conversational replies) intentionally skip this.
AFFILIATE_INSTRUCTION = (
    "\n\nAFFILIATE LINKS — when suggesting destinations, hotels, or flights, "
    "ALWAYS include a markdown link with the Travelpayouts affiliate marker:\n"
    "- Hotels: [\U0001F3E8 Find hotels in <CITY> →]"
    "(https://search.hotellook.com/?marker=529725&destination=<CITY>&utm_source=wizetravel)\n"
    "- Flights: [✈️ Find flights to <CITY> →]"
    "(https://www.aviasales.com/search/<IATA>?marker=529725) where <IATA> is the 3-letter airport code\n"
    "- Activities: [\U0001F3AB Things to do in <CITY> →]"
    "(https://www.tiqets.com/en/?marker=529725&utm_source=wizetravel) (skip if uncertain)\n\n"
    "ALWAYS URL-encode city names with spaces (use %20 or +).\n"
    "Place affiliate links naturally within recommendations, not in a separate \"Links\" section.\n"
    "Don't include affiliate links in: replies that are pure facts (e.g. visa requirements), "
    "replies that are conversational (\"good morning\"), error messages."
)


def with_affiliate(system_prompt: str = "") -> str:
    """Append the affiliate-link instruction to a system prompt.
    Use on AI routes that surface destination / hotel / flight / activity suggestions.
    Safe to call with an empty string."""
    return (system_prompt or "") + AFFILIATE_INSTRUCTION


# Phase 1 + 2 anti-hallucination guardrails — prepended to every system prompt
# via ask(). Kills creative drift from default Gemini temp (~0.7) and forces
# the model to admit uncertainty rather than invent flight prices / hotel
# rates / visa rules that may be wrong.
ANTI_HALLUCINATION_PREFIX = """🛑 ANTI-HALLUCINATION GUARDRAILS (must follow):

1. NEVER state a specific flight price, hotel rate, visa rule, schedule, or date without grounding it in either:
   (a) The web_search result returned in this same turn, OR
   (b) Data explicitly provided in the user's question.
   If neither is available, say "I don't know — please check on Aviasales/Hotellook/government site" + provide the affiliate link.
2. Banned hedge words (any language): approximately / around / probably / I believe / generally / as far as I know / בערך / סביב / לרוב / aproximadamente / cerca de / alrededor. Use exact numbers from sources, or admit ignorance.
3. Every numerical claim must include a source tag: [web-search 2026-{date}], [user input], or [Travelpayouts 2026].
4. If confidence < 70%, prefix the response with "⚠️".
5. End travel advice with: "ℹ️ Prices/rules change daily. Verify before booking."

"""


# ── Per-session daily rate limiting ───────────────────────────────────────────
import time as _time

_AI_DAILY_LIMITS = {"free": 5, "pro": 20, "yolo": 40}
_rate_store: dict = {}  # session_id → {"date": "YYYY-MM-DD", "count": int}


def _get_session_id() -> str:
    """Return Streamlit session ID, or 'global' outside Streamlit."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        return ctx.session_id if ctx else "global"
    except Exception:
        return "global"


def _get_plan_from_session() -> str:
    """Read plan from Streamlit session state if available."""
    try:
        import streamlit as _st
        return _st.session_state.get("wizelife_plan", "free")
    except Exception:
        return "free"


def _check_rate_limit() -> tuple[bool, str]:
    """Returns (allowed, reason). reason is non-empty when denied."""
    sid = _get_session_id()
    if sid == "global":
        # No Streamlit session — running under FastAPI (server.py handles quota)
        return True, ""
    plan  = _get_plan_from_session()
    limit = _AI_DAILY_LIMITS.get(plan, _AI_DAILY_LIMITS["free"])
    today = _time.strftime("%Y-%m-%d")
    entry = _rate_store.get(sid, {"date": "", "count": 0})
    if entry["date"] != today:
        entry = {"date": today, "count": 0}
    if entry["count"] >= limit:
        upgrade = (
            " שדרג ל-Pro (wizelife.ai) ל-20 ביום." if plan == "free"
            else " שדרג ל-YOLO ל-40 ביום." if plan == "pro"
            else ""
        )
        return False, f"הגעת למגבלת {limit} שאלות AI יומיות.{upgrade}"
    entry["count"] += 1
    _rate_store[sid] = entry
    return True, ""


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        _client = genai.Client(api_key=api_key)
        return _client
    except ImportError:
        return None


def ask(
    prompt: str,
    system: str = "",
    web_search: bool = False,
    max_tokens: int = 2048,
) -> Optional[str]:
    """
    Send a prompt to Gemini and return the text response.
    Returns None if no API key or on error.
    """
    allowed, reason = _check_rate_limit()
    if not allowed:
        print(f"[ai_client] Rate limit: {reason}")
        try:
            import streamlit as _st
            _st.session_state["ai_rate_limit_reason"] = reason
        except Exception:
            pass
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        from google.genai import types

        # Phase 1 + 2 anti-hallucination: deterministic decoding + always
        # prepend the guardrails prefix to whatever system prompt the caller
        # supplied. Safe — if caller already includes anti-hallucination, the
        # prefix just reinforces. Cost: ~200 extra tokens per request.
        guarded_system = ANTI_HALLUCINATION_PREFIX + (system or "")

        config_kwargs = {
            "max_output_tokens": max_tokens,
            "temperature": 0,
            "top_p": 0.1,
            "system_instruction": guarded_system,
        }
        if web_search:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        config = types.GenerateContentConfig(**config_kwargs)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config,
        )
        return response.text

    except Exception as e:
        err = str(e)
        if "quota" in err.lower() or "429" in err:
            return None  # rate limit — caller handles
        print(f"[ai_client] Error: {err[:120]}")
        return None


def ask_with_search(prompt: str, system: str = "", max_tokens: int = 2048) -> Optional[str]:
    """Convenience wrapper: ask() with web search enabled."""
    return ask(prompt=prompt, system=system, web_search=True, max_tokens=max_tokens)


def is_configured() -> bool:
    """Returns True if GEMINI_API_KEY is set."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def extract_json(text: str) -> dict:
    """Extract the first JSON object from a text response."""
    if not text:
        return {"found": False, "reason": "empty response"}

    patterns = [
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
        r"(\{[^{}]*\"found\"[^{}]*\})",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            try:
                return json.loads(matches[-1])
            except json.JSONDecodeError:
                continue

    # Last-resort: find last {...} block
    try:
        start = text.rfind("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    return {"found": False, "reason": "could not parse JSON from response"}


def chat_turn(
    history: list,
    user_message: str,
    system: str = "",
    max_tokens: int = 4096,
    web_search: bool = False,
) -> Optional[str]:
    """
    Multi-turn chat using Gemini.
    history: list of {"role": "user"|"model", "parts": [{"text": "..."}]}
    Returns assistant reply text, or None on error.
    """
    allowed, reason = _check_rate_limit()
    if not allowed:
        print(f"[ai_client] Rate limit: {reason}")
        try:
            import streamlit as _st
            _st.session_state["ai_rate_limit_reason"] = reason
        except Exception:
            pass
        return None

    client = _get_client()
    if client is None:
        return None
    try:
        from google.genai import types

        # Build contents: history + new user message
        contents = list(history) + [{"role": "user", "parts": [{"text": user_message}]}]

        config_kwargs: dict = {"max_output_tokens": max_tokens}
        if system:
            config_kwargs["system_instruction"] = system
        if web_search:
            config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]

        config = types.GenerateContentConfig(**config_kwargs)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        )
        return response.text
    except Exception as e:
        print(f"[ai_client.chat_turn] Error: {str(e)[:120]}")
        return None


def extract_json_array(text: str) -> list:
    """Extract the first JSON array from a text response."""
    if not text:
        return []
    try:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        pass
    return []
