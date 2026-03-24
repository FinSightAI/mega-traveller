#!/usr/bin/env python3
"""
MegaTraveller 🌍 - סוכן מחירי נסיעות חכם
מנטר טיסות, מלונות, דירות וחבילות בזמן אמת ומתריע על הזדמנויות מחיר.
"""
import os
import sys
import json
import time
import threading
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.text import Text
from rich.rule import Rule
from rich import box

# Load .env for API key
load_dotenv(Path(__file__).parent / ".env")

import database as db
import agent
import monitor
import alerts

console = Console()

# ── Branding ───────────────────────────────────────────────────────────────────
BANNER = """
[bold cyan]
  __  __                  _____                    _ _
 |  \/  | ___  __ _  __ |_   _| __ __ ___   _____| | | ___ _ __
 | |\/| |/ _ \/ _` |/ _` || || '__/ _` \ \ / / _ \ | |/ _ \ '__|
 | |  | |  __/ (_| | (_| || || | | (_| |\ V /  __/ | |  __/ |
 |_|  |_|\___|\__, |\__,_||_||_|  \__,_| \_/ \___|_|_|\___|_|
              |___/
[/bold cyan]
[dim]✈️  סוכן מחירי נסיעות חכם | מופעל על ידי Claude Opus 4.6  🌍[/dim]
"""

# ── Category helpers ───────────────────────────────────────────────────────────
CATEGORIES = {
    "1": ("flight", "✈️ טיסה"),
    "2": ("hotel", "🏨 מלון"),
    "3": ("apartment", "🏠 דירה"),
    "4": ("package", "📦 חבילה"),
}

DEAL_COLORS = {
    "excellent": "bold green",
    "good": "green",
    "average": "yellow",
    "poor": "red",
    "unknown": "dim",
}


# ── Helper UI ──────────────────────────────────────────────────────────────────
def check_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        console.print(Panel(
            "[bold red]❌ מפתח ANTHROPIC_API_KEY לא הוגדר!\n\n[/bold red]"
            "הוסף קובץ [bold].env[/bold] עם:\n"
            "[cyan]ANTHROPIC_API_KEY=sk-ant-...[/cyan]\n\n"
            "או הגדר משתנה סביבה:\n"
            "[cyan]export ANTHROPIC_API_KEY=sk-ant-...[/cyan]",
            title="⚠️ שגיאת הגדרה",
            border_style="red",
        ))
        sys.exit(1)


def render_watch_table(items: list[dict]):
    if not items:
        console.print("[dim]אין פריטים ברשימת המעקב[/dim]")
        return

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="cyan",
        title="📋 רשימת מעקב",
        title_style="bold white",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("שם", min_width=18)
    table.add_column("קטגוריה", width=10)
    table.add_column("יעד", min_width=12)
    table.add_column("תאריכים", min_width=14)
    table.add_column("מחיר נוכחי", justify="right", width=12)
    table.add_column("מחיר יעד", justify="right", width=10)
    table.add_column("מצב", width=6)

    for item in items:
        last = db.get_last_price(item["id"])
        price_str = f"{last['price']:.0f} {last['currency']}" if last else "-"

        cat_emoji = {
            "flight": "✈️", "hotel": "🏨",
            "apartment": "🏠", "package": "📦"
        }.get(item["category"], "🔍")

        dates = ""
        if item.get("date_from"):
            dates = item["date_from"]
        if item.get("date_to"):
            dates += f" - {item['date_to']}"

        max_p = f"{item['max_price']:.0f}" if item["max_price"] else "-"
        status = "[green]✓[/green]" if item["enabled"] else "[dim]✗[/dim]"

        table.add_row(
            str(item["id"]),
            item["name"],
            f"{cat_emoji} {item['category']}",
            item["destination"],
            dates or "-",
            price_str,
            max_p,
            status,
        )

    console.print(table)


def render_price_history(item: dict):
    history = db.get_price_history(item["id"], limit=10)
    if not history:
        console.print("[dim]אין היסטוריית מחירים עדיין[/dim]")
        return

    table = Table(
        box=box.SIMPLE,
        title=f"📈 היסטוריית מחירים: {item['name']}",
        title_style="bold white",
    )
    table.add_column("תאריך", style="dim")
    table.add_column("מחיר", justify="right")
    table.add_column("מטבע")
    table.add_column("מקור")
    table.add_column("פרטים")

    prices = [r["price"] for r in history]
    min_p = min(prices)
    max_p = max(prices)

    for r in history:
        price = r["price"]
        color = "green" if price == min_p else ("red" if price == max_p else "white")
        marker = " ⬇️ min" if price == min_p else (" ⬆️ max" if price == max_p else "")

        details_obj = {}
        try:
            details_obj = json.loads(r["details"])
        except Exception:
            pass
        detail_str = details_obj.get("details", "")[:40]

        checked = r["checked_at"][:16].replace("T", " ")
        table.add_row(
            checked,
            f"[{color}]{price:.0f}{marker}[/{color}]",
            r["currency"],
            r["source"][:20],
            detail_str,
        )

    console.print(table)

    # Smart analysis
    if len(history) >= 2:
        console.print("\n[bold]🤖 ניתוח חכם:[/bold]")
        with console.status("[cyan]מנתח...[/cyan]"):
            analysis = agent.analyze_deal(item, history)
        console.print(Panel(analysis, border_style="dim cyan", padding=(0, 2)))


# ── Menus ──────────────────────────────────────────────────────────────────────
def menu_add_item():
    """Wizard to add a new watch item."""
    console.print(Rule("[bold]➕ הוסף פריט חדש[/bold]"))

    # Category
    console.print("\n[bold]בחר קטגוריה:[/bold]")
    for k, (_, label) in CATEGORIES.items():
        console.print(f"  {k}. {label}")
    cat_choice = Prompt.ask("בחירה", choices=list(CATEGORIES.keys()), default="1")
    category, cat_label = CATEGORIES[cat_choice]

    name = Prompt.ask(f"שם לפריט (לדוגמה: {cat_label} לפריז)")
    destination = Prompt.ask("יעד")
    origin = ""
    if category in ("flight", "package"):
        origin = Prompt.ask("עיר מוצא", default="TLV")

    date_from = Prompt.ask("תאריך התחלה (YYYY-MM-DD)", default="")
    date_to = Prompt.ask("תאריך סיום (YYYY-MM-DD)", default="")
    max_price = Prompt.ask("מחיר יעד (התרע כשיורד אל/מתחת)", default="")
    drop_pct = Prompt.ask("התרע בירידה של % מהמחיר הקודם", default="10")

    custom_query = Prompt.ask(
        "שאילתה מותאמת אישית (אופציונלי, ריק = אוטומטי)", default=""
    )

    item = db.WatchItem(
        id=None,
        name=name,
        category=category,
        query=custom_query,
        destination=destination,
        origin=origin or None,
        date_from=date_from or None,
        date_to=date_to or None,
        max_price=float(max_price) if max_price else None,
        drop_pct=float(drop_pct) if drop_pct else 10.0,
    )
    new_id = db.add_watch_item(item)
    console.print(f"\n[green]✅ הפריט נוסף (ID: {new_id})[/green]")

    if Confirm.ask("בדוק מחיר עכשיו?", default=True):
        item_dict = db.get_all_watch_items(enabled_only=False)
        item_dict = next((i for i in item_dict if i["id"] == new_id), None)
        if item_dict:
            with console.status("[cyan]מחפש מחיר...[/cyan]"):
                monitor.check_item(item_dict)


def menu_view_items():
    """View all watch items and optionally drill into one."""
    items = db.get_all_watch_items(enabled_only=False)
    render_watch_table(items)

    if not items:
        return

    choice = Prompt.ask(
        "\nהזן ID פריט לפרטים נוספים (Enter לחזרה)", default=""
    )
    if choice:
        try:
            iid = int(choice)
            item = next((i for i in items if i["id"] == iid), None)
            if item:
                render_price_history(item)
            else:
                console.print("[red]פריט לא נמצא[/red]")
        except ValueError:
            pass


def menu_check_now():
    """Trigger an immediate price check cycle."""
    items = db.get_all_watch_items(enabled_only=True)
    if not items:
        console.print("[yellow]אין פריטים פעילים[/yellow]")
        return

    render_watch_table(items)
    choice = Prompt.ask(
        "הזן ID לבדיקה אחת, או Enter לבדיקת הכול", default=""
    )
    if choice:
        try:
            iid = int(choice)
            item = next((i for i in items if i["id"] == iid), None)
            if item:
                monitor.check_item(item)
            else:
                console.print("[red]פריט לא נמצא[/red]")
        except ValueError:
            pass
    else:
        monitor.run_cycle(items)


def menu_smart_opportunities():
    """Ask Claude to proactively find good deals."""
    console.print(Rule("[bold]🌟 הזדמנויות חכמות[/bold]"))
    dests = Prompt.ask("לאיזה יעדים לחפש? (מופרד בפסיקים)", default="לונדון, פריז, ברצלונה")
    dest_list = [d.strip() for d in dests.split(",")]

    with console.status("[cyan]Claude מחפש הזדמנויות מיוחדות...[/cyan]"):
        opps = agent.smart_search_opportunities(dest_list)

    if not opps:
        console.print("[yellow]לא נמצאו הזדמנויות כרגע[/yellow]")
        return

    for opp in opps:
        urgency_color = {"high": "red", "medium": "yellow", "low": "green"}.get(
            opp.get("urgency", ""), "white"
        )
        urgency_icon = {"high": "🔥", "medium": "⚡", "low": "💡"}.get(
            opp.get("urgency", ""), "💰"
        )

        panel_text = Text()
        panel_text.append(f"{opp.get('deal', '')}\n", style="white")
        panel_text.append(f"\n💰 מחיר: ", style="dim")
        panel_text.append(
            f"{opp.get('price', '?')} {opp.get('currency', '')}",
            style="bold green"
        )
        panel_text.append(f"\n💡 למה מצוין: {opp.get('why_good', '')}", style="dim")
        panel_text.append(
            f"\n{urgency_icon} דחיפות: ", style="dim"
        )
        panel_text.append(opp.get("urgency", ""), style=urgency_color)

        cat_emoji = {"flight": "✈️", "hotel": "🏨", "package": "📦"}.get(
            opp.get("type", ""), "🌍"
        )

        console.print(Panel(
            panel_text,
            title=f"[bold]{cat_emoji} {opp.get('destination', '')}[/bold]",
            border_style=urgency_color,
            padding=(0, 2),
        ))

    if Confirm.ask("\nהוסף אחת מההזדמנויות לרשימת המעקב?", default=False):
        menu_add_item()


def menu_manage_items():
    """Delete or toggle items."""
    items = db.get_all_watch_items(enabled_only=False)
    if not items:
        console.print("[dim]אין פריטים[/dim]")
        return

    render_watch_table(items)
    iid_str = Prompt.ask("הזן ID לניהול")
    try:
        iid = int(iid_str)
        item = next((i for i in items if i["id"] == iid), None)
        if not item:
            console.print("[red]לא נמצא[/red]")
            return

        action = Prompt.ask(
            f"מה לעשות עם [bold]{item['name']}[/bold]?",
            choices=["toggle", "delete", "cancel"],
            default="cancel"
        )
        if action == "toggle":
            db.toggle_watch_item(iid, not item["enabled"])
            state = "הופעל" if not item["enabled"] else "הושבת"
            console.print(f"[green]{state}[/green]")
        elif action == "delete":
            if Confirm.ask(f"[red]מחק לצמיתות?[/red]", default=False):
                db.delete_watch_item(iid)
                console.print("[red]נמחק[/red]")
    except ValueError:
        pass


def menu_start_monitor():
    """Start the background monitor."""
    interval = IntPrompt.ask(
        "כל כמה דקות לבדוק?", default=60
    )
    t = monitor.start_background_monitor(interval * 60)
    console.print(
        f"\n[bold green]✅ מנטור פועל ברקע כל {interval} דקות[/bold green]\n"
        "[dim]לחץ Enter לחזרה לתפריט (הניטור ימשיך)[/dim]"
    )
    input()


# ── Main ────────────────────────────────────────────────────────────────────────
def main():
    check_api_key()
    db.init_db()

    console.print(BANNER)
    console.print(
        "[dim]הסוכן משתמש בחיפוש אינטרנט חי דרך Claude כדי לאתר מחירים עדכניים.[/dim]\n"
    )

    MENU = {
        "1": ("➕ הוסף פריט למעקב", menu_add_item),
        "2": ("📋 צפה ברשימת המעקב", menu_view_items),
        "3": ("🔍 בדוק מחיר עכשיו", menu_check_now),
        "4": ("🌟 הזדמנויות חכמות (AI)", menu_smart_opportunities),
        "5": ("⚙️  נהל פריטים", menu_manage_items),
        "6": ("🔄 הפעל ניטור רציף", menu_start_monitor),
        "0": ("❌ יציאה", None),
    }

    while True:
        console.print(Rule("[bold cyan]תפריט ראשי[/bold cyan]", style="cyan"))
        for k, (label, _) in MENU.items():
            console.print(f"  [bold cyan]{k}[/bold cyan]. {label}")

        choice = Prompt.ask("\n[bold]בחר אפשרות[/bold]", choices=list(MENU.keys()))

        if choice == "0":
            console.print("\n[bold]להתראות! ✈️[/bold]\n")
            monitor.stop_background_monitor()
            break

        _, func = MENU[choice]
        if func:
            try:
                func()
            except KeyboardInterrupt:
                console.print("\n[yellow]בוטל[/yellow]")
            except Exception as e:
                console.print(f"\n[red]שגיאה: {e}[/red]")

        console.print()


if __name__ == "__main__":
    main()
