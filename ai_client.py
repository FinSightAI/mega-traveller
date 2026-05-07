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

        config_kwargs = {
            "max_output_tokens": max_tokens,
        }
        if system:
            config_kwargs["system_instruction"] = system
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
