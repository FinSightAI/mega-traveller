"""
WizeLife Firebase Auth — for Mega Traveller (Streamlit).
Uses Firebase REST API + Firestore REST API (no firebase-admin needed).
"""
import os
import httpx
from typing import Optional

_FIREBASE_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "AIzaSyDuzJHOMe89YmEFpKlaTgxT40BCNhK6PU0")
_FIRESTORE_BASE   = "https://firestore.googleapis.com/v1/projects/finzilla-7f1f9/databases/(default)/documents"


def sign_in(email: str, password: str) -> dict:
    """
    Sign in with email + password.
    Returns: { "ok": True, "uid": str, "id_token": str, "email": str }
             { "ok": False, "error": str }
    """
    try:
        r = httpx.post(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={_FIREBASE_API_KEY}",
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=8,
        )
        data = r.json()
        if "idToken" not in data:
            msg = data.get("error", {}).get("message", "AUTH_ERROR")
            if "INVALID_PASSWORD" in msg or "EMAIL_NOT_FOUND" in msg or "INVALID_LOGIN_CREDENTIALS" in msg:
                return {"ok": False, "error": "אימייל או סיסמה שגויים"}
            return {"ok": False, "error": "שגיאת כניסה — נסה שוב"}
        return {
            "ok": True,
            "uid": data["localId"],
            "id_token": data["idToken"],
            "email": data["email"],
        }
    except Exception as e:
        return {"ok": False, "error": f"שגיאת חיבור: {str(e)[:60]}"}


def get_plan(uid: str, id_token: str) -> str:
    """
    Read user's plan from Firestore.
    Returns 'free', 'pro', or 'yolo'.
    """
    try:
        r = httpx.get(
            f"{_FIRESTORE_BASE}/users/{uid}",
            headers={"Authorization": f"Bearer {id_token}"},
            timeout=5,
        )
        if not r.is_success:
            return "free"
        fields = r.json().get("fields", {})
        return fields.get("plan", {}).get("stringValue", "free")
    except Exception:
        return "free"


def sync_cross_app_data(id_token: str, app_id: str, app_name: str, summary: str) -> bool:
    """Push a summary to WizeLife cross-app AI (Yolo plan only)."""
    if not id_token or not summary:
        return False
    try:
        r = httpx.post(
            "https://us-central1-finzilla-7f1f9.cloudfunctions.net/syncCrossAppData",
            headers={
                "Authorization": f"Bearer {id_token}",
                "Content-Type": "application/json",
            },
            json={"data": {"appId": app_id, "appName": app_name, "summary": summary}},
            timeout=5,
        )
        return r.is_success
    except Exception:
        return False


def refresh_token(refresh_tok: str) -> Optional[str]:
    """Exchange a refresh token for a fresh ID token (call before token expiry ~1hr)."""
    try:
        r = httpx.post(
            f"https://securetoken.googleapis.com/v1/token?key={_FIREBASE_API_KEY}",
            json={"grant_type": "refresh_token", "refresh_token": refresh_tok},
            timeout=8,
        )
        return r.json().get("id_token")
    except Exception:
        return None
