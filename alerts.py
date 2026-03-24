"""
Alert system: desktop + Telegram + ntfy.sh (push to phone) + log file.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

console = Console()
LOG_PATH = Path(__file__).parent / "alerts.log"

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── Notification config (read from .env) ───────────────────────────────────────

def _get_cfg() -> dict:
    """Read notification config from environment."""
    return {
        "telegram_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "ntfy_topic": os.environ.get("NTFY_TOPIC", ""),       # e.g. "megatraveller-abc123"
        "ntfy_server": os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
    }


# ── Channel: Desktop ───────────────────────────────────────────────────────────

def _desktop_notify(title: str, message: str):
    try:
        from plyer import notification
        notification.notify(
            title=title, message=message,
            app_name="MegaTraveller 🌍", timeout=10,
        )
    except Exception:
        pass


# ── Channel: Telegram ──────────────────────────────────────────────────────────

def _telegram_notify(title: str, message: str):
    cfg = _get_cfg()
    if not cfg["telegram_token"] or not cfg["telegram_chat_id"]:
        return
    try:
        import httpx
        text = f"*{title}*\n{message}"
        httpx.post(
            f"https://api.telegram.org/bot{cfg['telegram_token']}/sendMessage",
            json={
                "chat_id": cfg["telegram_chat_id"],
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
    except Exception as e:
        logging.warning(f"Telegram alert failed: {e}")


# ── Channel: ntfy.sh (free push to phone, no account needed) ──────────────────

def _ntfy_notify(title: str, message: str, urgency: str = "high"):
    cfg = _get_cfg()
    if not cfg["ntfy_topic"]:
        return
    try:
        import httpx
        httpx.post(
            f"{cfg['ntfy_server']}/{cfg['ntfy_topic']}",
            content=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": urgency,        # urgent / high / default / low / min
                "Tags": "money_with_wings,airplane",
            },
            timeout=10,
        )
    except Exception as e:
        logging.warning(f"ntfy alert failed: {e}")


# ── Public: test channels ──────────────────────────────────────────────────────

def test_notifications() -> dict:
    """Send test messages to all configured channels. Returns status dict."""
    status = {}
    title = "✈️ MegaTraveller - בדיקת התראות"
    msg = "ההתראות עובדות! 🎉"

    cfg = _get_cfg()

    # Desktop
    try:
        _desktop_notify(title, msg)
        status["desktop"] = "✅"
    except Exception as e:
        status["desktop"] = f"❌ {e}"

    # Telegram
    if cfg["telegram_token"] and cfg["telegram_chat_id"]:
        try:
            _telegram_notify(title, msg)
            status["telegram"] = "✅"
        except Exception as e:
            status["telegram"] = f"❌ {e}"
    else:
        status["telegram"] = "⚠️ לא מוגדר"

    # ntfy
    if cfg["ntfy_topic"]:
        try:
            _ntfy_notify(title, msg)
            status["ntfy"] = "✅"
        except Exception as e:
            status["ntfy"] = f"❌ {e}"
    else:
        status["ntfy"] = "⚠️ לא מוגדר"

    return status


def send_alert(alert_data: dict):
    """
    Sends a price alert via terminal + desktop notification + log.
    alert_data: result from database.check_price_drop()
    """
    if not alert_data.get("alert"):
        return

    item = alert_data["item"]
    new_price = alert_data["new_price"]
    alerts = alert_data["alerts"]

    # Build message
    category_emoji = {
        "flight": "✈️",
        "hotel": "🏨",
        "apartment": "🏠",
        "package": "📦",
    }.get(item["category"], "💰")

    title = f"{category_emoji} התראת מחיר: {item['name']}"

    lines = []
    for a in alerts:
        lines.append(a["message"])

    details_str = " | ".join(lines)
    full_msg = f"{details_str}\n🔗 חפש: {item['destination']}"

    # Rich terminal panel
    text = Text()
    text.append(f"\n{category_emoji}  {item['name']}\n", style="bold white")
    text.append(f"📍 {item['destination']}", style="cyan")
    if item.get("origin"):
        text.append(f" ← {item['origin']}", style="cyan")
    text.append("\n")

    for a in alerts:
        if a["type"] == "threshold":
            text.append(f"\n🎯 {a['message']}\n", style="bold green")
        elif a["type"] == "drop":
            text.append(f"\n📉 {a['message']}\n", style="bold yellow")

    text.append(f"\n💲 מחיר נוכחי: ", style="white")
    text.append(f"{new_price:.0f}", style="bold green")
    text.append(f"\n🕐 {datetime.now().strftime('%H:%M:%S')}", style="dim")

    panel = Panel(
        text,
        title=f"[bold red]🔔 התראה![/bold red]",
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(0, 2),
    )
    console.print(panel)

    # Desktop notification
    _desktop_notify(title, details_str)

    # All channels via notifiers hub
    import notifiers as _notifiers
    _notifiers.broadcast(title, full_msg)

    # Log
    log_entry = {
        "time": datetime.now().isoformat(),
        "item": item["name"],
        "category": item["category"],
        "destination": item["destination"],
        "price": new_price,
        "alerts": alerts,
    }
    logging.info(json.dumps(log_entry, ensure_ascii=False))


def notify_check_start(item_name: str, category: str):
    emoji = {
        "flight": "✈️", "hotel": "🏨",
        "apartment": "🏠", "package": "📦"
    }.get(category, "🔍")
    console.print(f"  {emoji} בודק: [bold]{item_name}[/bold]...", end=" ")


def notify_price_found(price: float, currency: str, source: str):
    console.print(
        f"[green]{price:.0f} {currency}[/green] [dim]({source})[/dim] ✓"
    )


def notify_no_price():
    console.print("[dim yellow]לא נמצא מחיר[/dim yellow]")


def notify_error(error: str):
    console.print(f"[red]שגיאה: {error[:60]}[/red]")
