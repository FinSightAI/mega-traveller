"""
Background price monitoring loop.
Checks all enabled watch items and sends alerts on price drops.
"""
import json
import time
import threading
from datetime import datetime

from rich.console import Console
from rich.rule import Rule

import database as db
import agent
import alerts

console = Console()

# Interval between full monitoring cycles (seconds)
DEFAULT_INTERVAL = 3600  # 1 hour
_stop_event = threading.Event()


def check_item(item: dict) -> bool:
    """
    Check price for a single watch item.
    Returns True if price was found and saved.
    """
    alerts.notify_check_start(item["name"], item["category"])

    result = agent.search_price(item)

    if not result.get("found"):
        reason = result.get("reason", "unknown")
        alerts.notify_no_price()
        return False

    price = float(result["price"])
    currency = result.get("currency", "USD")
    source = result.get("source", "web")
    details_obj = {
        "details": result.get("details", ""),
        "deal_quality": result.get("deal_quality", ""),
        "notes": result.get("notes", ""),
    }

    # Save to DB
    record = db.PriceRecord(
        id=None,
        watch_id=item["id"],
        price=price,
        currency=currency,
        source=source,
        details=json.dumps(details_obj, ensure_ascii=False),
    )
    db.save_price(record)

    alerts.notify_price_found(price, currency, source)

    # Check standard price-drop alerts
    alert_data = db.check_price_drop(item["id"], price)
    if alert_data["alert"]:
        alerts.send_alert(alert_data)

    # Check custom alert rules
    triggered_rules = db.evaluate_alert_rules(item["id"], price, result)
    for rule_match in triggered_rules:
        import notifiers
        title = f"🎯 כלל התראה: {item['name']}"
        msg = (
            f"{rule_match['message']}\n"
            f"💲 מחיר: {price:.0f} {currency}\n"
            f"📍 {item['destination']}"
        )
        notifiers.broadcast(title, msg)
        console.print(f"  [yellow]🎯 כלל '{rule_match['rule_name']}' הופעל[/yellow]")

    return True


def run_cycle(items=None):
    """Run one full monitoring cycle over all (or given) watch items."""
    if items is None:
        items = db.get_all_watch_items(enabled_only=True)

    if not items:
        console.print("[dim]אין פריטים לניטור. הוסף דרך התפריט הראשי.[/dim]")
        return

    console.print(Rule(
        f"[bold cyan]🔄 סבב ניטור | {datetime.now().strftime('%H:%M:%S')}[/bold cyan]",
        style="cyan"
    ))

    for item in items:
        try:
            check_item(item)
        except Exception as e:
            alerts.notify_error(str(e))

        # Small delay between items to avoid rate limits
        time.sleep(2)

    console.print(Rule("[dim]סבב הסתיים[/dim]", style="dim"))


def start_background_monitor(interval: int = DEFAULT_INTERVAL):
    """
    Start the monitoring loop in a background thread.
    Returns the thread.
    """
    _stop_event.clear()

    def loop():
        console.print(f"\n[green]🚀 מנטור פועל כל {interval//60} דקות[/green]\n")
        while not _stop_event.is_set():
            run_cycle()
            # Wait for interval or until stopped
            _stop_event.wait(timeout=interval)

    t = threading.Thread(target=loop, daemon=True, name="price-monitor")
    t.start()
    return t


def stop_background_monitor():
    """Signal the background monitor to stop."""
    _stop_event.set()
