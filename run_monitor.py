"""
Headless monitor — runs a single price check cycle.
Used by GitHub Actions / cron / Docker.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Validate API key
if not os.environ.get("ANTHROPIC_API_KEY"):
    print("❌ ANTHROPIC_API_KEY not set")
    sys.exit(1)

import database as db
import monitor
import notifiers
import deal_hunter
import deal_scorer

db.init_db()

# ── 1. Price check cycle ────────────────────────────────────────────────────
print("🔄 Starting price check cycle...")
items = db.get_all_watch_items(enabled_only=True)

if items:
    print(f"Checking {len(items)} items...")
    monitor.run_cycle(items)
    print("✅ Price check done.")
else:
    print("No active watch items.")

# ── 2. Proactive deal hunting ───────────────────────────────────────────────
print("\n🔥 Starting deal hunt...")
try:
    found = deal_hunter.hunt_deals()  # uses top-4 sources by default
    if found and not (len(found) == 1 and "error" in found[0]):
        # Score and filter top deals
        top = deal_scorer.score_and_filter(found, min_score=7.5)
        print(f"Found {len(found)} deals, {len(top)} scored 7.5+")
        for deal in top:
            msg = deal_scorer.format_deal_alert(deal)
            title = f"🔥 דיל {deal.get('ai_grade','')}: {deal.get('destination','')}"
            notifiers.broadcast(title, msg)
            print(f"  → Alerted: {deal.get('destination','')} ${deal.get('price',0):.0f}")
    else:
        print("No deals found this cycle.")
except Exception as e:
    print(f"⚠️ Deal hunt error: {e}")

print("\n✅ All done.")
