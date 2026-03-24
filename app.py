"""
MegaTraveller 🌍 - Web UI (Streamlit)
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

load_dotenv(Path(__file__).parent / ".env")

import database as db
import agent
import monitor
import notifiers
import exchange_rates as fx
import exporters
import flexible_search
import price_predictor
import trip_planner
import deal_hunter
import smart_search
import deal_scorer
import competitor_check
import sentiment_analyzer
import visa_check
import stopover_finder
import cost_calculator
import deal_insights
import telegram_bot

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MegaTraveller ✈️",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

db.init_db()


def _save_env(key: str, value: str):
    """Append or update a key in the .env file."""
    env_path = Path(__file__).parent / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n")
    os.environ[key] = value

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
  }
  [data-testid="stSidebar"] {
    background: rgba(15,12,41,0.95);
  }
  .metric-card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
  }
  .alert-box {
    background: rgba(255, 75, 75, 0.15);
    border: 1px solid rgba(255, 75, 75, 0.5);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }
  .deal-excellent { color: #00ff88; font-weight: bold; }
  .deal-good      { color: #88ff44; }
  .deal-average   { color: #ffcc00; }
  .deal-poor      { color: #ff4444; }
  h1, h2, h3 { color: white !important; }
  .stButton button {
    background: linear-gradient(90deg, #667eea, #764ba2);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
  }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
if "monitor_running" not in st.session_state:
    st.session_state.monitor_running = False
if "alerts_log" not in st.session_state:
    st.session_state.alerts_log = []
if "checking" not in st.session_state:
    st.session_state.checking = False


# ── Helpers ────────────────────────────────────────────────────────────────────
CAT_EMOJI = {"flight": "✈️", "hotel": "🏨", "apartment": "🏠", "package": "📦"}
DEAL_COLOR = {
    "excellent": "#00ff88", "good": "#88ff44",
    "average": "#ffcc00", "poor": "#ff4444", "unknown": "#aaaaaa"
}


def fmt_price(price, currency=""):
    if price is None:
        return "—"
    return f"{price:,.0f} {currency}".strip()


def price_chart(watch_id: int, name: str):
    history = db.get_price_history(watch_id, limit=30)
    if len(history) < 2:
        return None

    history = list(reversed(history))
    dates = [r["checked_at"][:16].replace("T", " ") for r in history]
    prices = [r["price"] for r in history]
    currency = history[-1]["currency"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        mode="lines+markers",
        name="מחיר",
        line=dict(color="#667eea", width=2.5),
        marker=dict(size=7, color="#764ba2"),
        fill="tozeroy",
        fillcolor="rgba(102,126,234,0.1)",
    ))

    # Annotate min/max
    min_p, max_p = min(prices), max(prices)
    min_i, max_i = prices.index(min_p), prices.index(max_p)
    fig.add_annotation(x=dates[min_i], y=min_p, text=f"⬇ {fmt_price(min_p, currency)}",
                       font=dict(color="#00ff88", size=11), showarrow=True, arrowcolor="#00ff88")
    fig.add_annotation(x=dates[max_i], y=max_p, text=f"⬆ {fmt_price(max_p, currency)}",
                       font=dict(color="#ff4444", size=11), showarrow=True, arrowcolor="#ff4444")

    fig.update_layout(
        title=dict(text=f"📈 {name}", font=dict(color="white", size=14)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.03)",
        font=dict(color="#cccccc"),
        height=250,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(showgrid=False, tickfont=dict(size=9)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)",
                   title=f"מחיר ({currency})"),
        showlegend=False,
    )
    return fig


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ✈️ MegaTraveller")
    st.markdown("*סוכן מחירי נסיעות חכם*")
    st.divider()

    page = st.radio(
        "ניווט",
        [
            "🏠 לוח בקרה",
            "➕ הוסף מעקב",
            "🌟 הזדמנויות AI",
            "🔥 ציד דילים",
            "🎲 הפתיעני",
            "🛠️ כלים חכמים",
            "📊 היסטוריית מחירים",
            "🎯 כללי התראה",
            "🔍 השוואת אתרים",
            "📰 סנטימנט & חדשות",
            "⏰ דילים שפגים",
            "🛂 בדיקת ויזה",
            "📅 תאריכים גמישים",
            "📈 חיזוי מחיר",
            "🗺️ תכנן טיול",
            "🌍 מסלול מרובה ערים",
            "🔁 עצירות חינם",
            "💰 עלות אמיתית",
            "💳 נקודות vs מזומן",
            "📊 תובנות ודפוסים",
            "🤖 בוט טלגרם",
            "💱 שערי חליפין",
            "📥 ייצוא נתונים",
            "⚙️ הגדרות",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    # Monitor toggle
    if not st.session_state.monitor_running:
        if st.button("▶ הפעל ניטור אוטומטי", use_container_width=True):
            monitor.start_background_monitor(interval=3600)
            st.session_state.monitor_running = True
            st.rerun()
    else:
        st.success("🟢 ניטור פעיל")
        if st.button("⏹ עצור ניטור", use_container_width=True):
            monitor.stop_background_monitor()
            st.session_state.monitor_running = False
            st.rerun()

    st.divider()

    # API key status
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and api_key.startswith("sk-"):
        st.success("🔑 API Key מוגדר")
    else:
        st.error("❌ חסר ANTHROPIC_API_KEY")
        st.caption("הוסף ל-.env")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Dashboard
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 לוח בקרה":

    # Auto-refresh every 60s when monitor is running
    if st.session_state.monitor_running:
        st_autorefresh(interval=60_000, key="dashboard_refresh")

    st.title("🌍 לוח בקרה")

    items = db.get_all_watch_items(enabled_only=False)

    # ── Top metrics ────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    active = sum(1 for i in items if i["enabled"])
    with_price = sum(1 for i in items if db.get_last_price(i["id"]))
    alerts_today = 0  # could read from log

    with col1:
        st.metric("סה״כ מעקבים", len(items))
    with col2:
        st.metric("פעילים", active)
    with col3:
        st.metric("עם מחיר", with_price)
    with col4:
        monitor_status = "🟢 פועל" if st.session_state.monitor_running else "🔴 כבוי"
        st.metric("ניטור", monitor_status)

    st.divider()

    if not items:
        st.info("אין פריטים עדיין. לחץ **'➕ הוסף מעקב'** בתפריט השמאלי.")
    else:
        # ── Items grid ─────────────────────────────────────────────────────────
        for item in items:
            last = db.get_last_price(item["id"])
            lowest = db.get_lowest_price(item["id"])
            history = db.get_price_history(item["id"], limit=30)

            with st.expander(
                f"{CAT_EMOJI.get(item['category'], '🔍')} **{item['name']}** "
                f"{'🟢' if item['enabled'] else '🔴'}",
                expanded=(len(items) == 1),
            ):
                left, right = st.columns([1, 2])

                with left:
                    # Info
                    st.markdown(f"**יעד:** {item['destination']}")
                    if item.get("origin"):
                        st.markdown(f"**מוצא:** {item['origin']}")
                    if item.get("date_from"):
                        st.markdown(f"**תאריכים:** {item['date_from']} → {item.get('date_to', '')}")

                    st.divider()

                    if last:
                        price_color = "#00ff88" if (lowest and last["price"] == lowest["price"]) else "#ffffff"
                        st.markdown(
                            f"<h2 style='color:{price_color};margin:0'>"
                            f"{fmt_price(last['price'], last['currency'])}</h2>"
                            f"<small style='color:#aaa'>מחיר נוכחי | {last['checked_at'][11:16]}</small>",
                            unsafe_allow_html=True,
                        )
                        if lowest and lowest["price"] < last["price"]:
                            savings = last["price"] - lowest["price"]
                            st.caption(f"⬇ מינימום: {fmt_price(lowest['price'], lowest['currency'])} (חסכון {savings:.0f})")
                        if item["max_price"]:
                            diff = last["price"] - item["max_price"]
                            if diff <= 0:
                                st.success(f"🎯 מתחת ליעד! ({fmt_price(item['max_price'])})")
                            else:
                                st.caption(f"🎯 יעד: {fmt_price(item['max_price'])} (עוד {diff:.0f})")
                    else:
                        st.markdown("*אין מחיר עדיין*")

                    st.divider()

                    # Action buttons
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("🔍 בדוק", key=f"check_{item['id']}"):
                            with st.spinner("מחפש מחיר..."):
                                result = agent.search_price(item)
                                if result.get("found"):
                                    price = float(result["price"])
                                    rec = db.PriceRecord(
                                        id=None, watch_id=item["id"],
                                        price=price,
                                        currency=result.get("currency", "USD"),
                                        source=result.get("source", "web"),
                                        details=json.dumps({
                                            "details": result.get("details", ""),
                                            "deal_quality": result.get("deal_quality", ""),
                                        }, ensure_ascii=False),
                                    )
                                    db.save_price(rec)
                                    alert_data = db.check_price_drop(item["id"], price)
                                    if alert_data["alert"]:
                                        for a in alert_data["alerts"]:
                                            st.warning(f"🔔 {a['message']}")
                                    st.success(f"✅ {fmt_price(price, result.get('currency',''))}")
                                    st.rerun()
                                else:
                                    st.error(result.get("reason", "לא נמצא"))
                    with b2:
                        enabled_label = "⏸" if item["enabled"] else "▶"
                        if st.button(enabled_label, key=f"tog_{item['id']}"):
                            db.toggle_watch_item(item["id"], not item["enabled"])
                            st.rerun()
                    with b3:
                        if st.button("🗑", key=f"del_{item['id']}"):
                            db.delete_watch_item(item["id"])
                            st.rerun()

                with right:
                    # Price chart
                    fig = price_chart(item["id"], item["name"])
                    if fig:
                        st.plotly_chart(fig, use_container_width=True, key=f"chart_{item['id']}")
                    else:
                        st.info("📊 גרף יופיע לאחר 2+ בדיקות מחיר")

                    # Last details
                    if last:
                        try:
                            details_obj = json.loads(last.get("details", "{}"))
                            detail_str = details_obj.get("details", "")
                            deal_q = details_obj.get("deal_quality", "")
                            if detail_str:
                                dq_color = DEAL_COLOR.get(deal_q, "#aaa")
                                st.markdown(
                                    f"<small style='color:#aaa'>{detail_str[:120]}</small> "
                                    f"<span style='color:{dq_color}'>{deal_q}</span>",
                                    unsafe_allow_html=True,
                                )
                        except Exception:
                            pass

                    # AI analysis
                    if len(history) >= 2:
                        if st.button("🤖 ניתוח AI", key=f"anal_{item['id']}"):
                            with st.spinner("מנתח..."):
                                analysis = agent.analyze_deal(item, history)
                            st.info(f"💡 {analysis}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Add Item
# ══════════════════════════════════════════════════════════════════════════════
elif page == "➕ הוסף מעקב":
    st.title("➕ הוסף פריט למעקב")

    with st.form("add_item_form"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("שם הפריט *", placeholder="טיסה לברצלונה")
            category = st.selectbox(
                "קטגוריה *",
                ["flight", "hotel", "apartment", "package"],
                format_func=lambda x: f"{CAT_EMOJI[x]} {x}",
            )
            destination = st.text_input("יעד *", placeholder="ברצלונה")
            origin = st.text_input("עיר מוצא", placeholder="TLV (לטיסות)")

        with col2:
            date_from = st.date_input("תאריך התחלה", value=None)
            date_to = st.date_input("תאריך סיום", value=None)
            max_price = st.number_input(
                "מחיר יעד (התרע כשיורד אל/מתחת)", min_value=0.0, value=0.0, step=10.0
            )
            drop_pct = st.slider("התרע בירידה של %", 5, 50, 10)

        custom_query = st.text_area(
            "שאילתה מותאמת אישית (אופציונלי)",
            placeholder="מצא טיסה זולה מ-TLV לברצלונה בתחילת מאי, כולל מזוודה",
            height=80,
        )

        check_now = st.checkbox("בדוק מחיר מיד לאחר הוספה", value=True)
        submitted = st.form_submit_button("➕ הוסף", use_container_width=True)

    if submitted:
        if not name or not destination:
            st.error("שם ויעד הם שדות חובה")
        else:
            item = db.WatchItem(
                id=None,
                name=name,
                category=category,
                query=custom_query or "",
                destination=destination,
                origin=origin or None,
                date_from=str(date_from) if date_from else None,
                date_to=str(date_to) if date_to else None,
                max_price=max_price if max_price > 0 else None,
                drop_pct=float(drop_pct),
            )
            new_id = db.add_watch_item(item)
            st.success(f"✅ נוסף! (ID: {new_id})")

            if check_now:
                items_all = db.get_all_watch_items(enabled_only=False)
                item_dict = next((i for i in items_all if i["id"] == new_id), None)
                if item_dict:
                    with st.spinner("🔍 מחפש מחיר..."):
                        result = agent.search_price(item_dict)

                    if result.get("found"):
                        price = float(result["price"])
                        rec = db.PriceRecord(
                            id=None, watch_id=new_id,
                            price=price,
                            currency=result.get("currency", "USD"),
                            source=result.get("source", "web"),
                            details=json.dumps({
                                "details": result.get("details", ""),
                                "deal_quality": result.get("deal_quality", ""),
                                "notes": result.get("notes", ""),
                            }, ensure_ascii=False),
                        )
                        db.save_price(rec)
                        dq = result.get("deal_quality", "")
                        dq_color = DEAL_COLOR.get(dq, "#aaa")
                        st.markdown(
                            f"### 💰 מחיר שנמצא: "
                            f"**{fmt_price(price, result.get('currency',''))}**"
                        )
                        st.markdown(
                            f"<span style='color:{dq_color}'>⭐ {dq}</span> | "
                            f"מקור: {result.get('source', '')}",
                            unsafe_allow_html=True,
                        )
                        if result.get("details"):
                            st.caption(result["details"][:200])
                    else:
                        st.warning(f"לא נמצא מחיר: {result.get('reason', '')}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Smart Opportunities
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🌟 הזדמנויות AI":
    st.title("🌟 הזדמנויות חכמות")
    st.caption("Claude מחפש את הדילים הטובים ביותר עבורך")

    with st.form("opp_form"):
        dests = st.text_input(
            "יעדים לחיפוש (מופרד בפסיקים)",
            placeholder="לונדון, פריז, ברצלונה, אמסטרדם",
            value="לונדון, פריז, ברצלונה",
        )
        categories_sel = st.multiselect(
            "סוגי מוצרים",
            ["טיסות", "מלונות", "חבילות"],
            default=["טיסות", "מלונות", "חבילות"],
        )
        search_btn = st.form_submit_button("🔍 חפש הזדמנויות", use_container_width=True)

    if search_btn:
        dest_list = [d.strip() for d in dests.split(",") if d.strip()]
        with st.spinner("🤖 Claude מחפש הזדמנויות... (עשוי לקחת 30-60 שניות)"):
            opps = agent.smart_search_opportunities(dest_list)

        if not opps:
            st.warning("לא נמצאו הזדמנויות כרגע. נסה שוב מאוחר יותר.")
        else:
            st.success(f"נמצאו {len(opps)} הזדמנויות! 🎉")
            st.divider()

            cols = st.columns(min(len(opps), 3))
            for i, opp in enumerate(opps[:3]):
                urgency = opp.get("urgency", "medium")
                urg_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(urgency, "⚪")
                cat_emoji = {"flight": "✈️", "hotel": "🏨", "package": "📦"}.get(
                    opp.get("type", ""), "🌍"
                )

                with cols[i % len(cols)]:
                    with st.container():
                        st.markdown(
                            f"### {cat_emoji} {opp.get('destination', '')}"
                        )
                        st.markdown(
                            f"**💰 {fmt_price(opp.get('price'), opp.get('currency', ''))}**"
                        )
                        st.markdown(opp.get("deal", ""))
                        st.markdown(
                            f"💡 *{opp.get('why_good', '')}*"
                        )
                        st.markdown(f"{urg_color} דחיפות: **{urgency}**")

                        if st.button(f"➕ הוסף למעקב", key=f"add_opp_{i}"):
                            new_item = db.WatchItem(
                                id=None,
                                name=f"{cat_emoji} {opp.get('destination', '')}",
                                category=opp.get("type", "package"),
                                query=opp.get("deal", ""),
                                destination=opp.get("destination", ""),
                                origin="TLV",
                                date_from=None, date_to=None,
                                max_price=opp.get("price"),
                                drop_pct=10.0,
                            )
                            db.add_watch_item(new_item)
                            st.success("נוסף!")

            if len(opps) > 3:
                with st.expander(f"עוד {len(opps)-3} הזדמנויות"):
                    for opp in opps[3:]:
                        st.markdown(
                            f"**{opp.get('destination')}** — "
                            f"{fmt_price(opp.get('price'), opp.get('currency', ''))} | "
                            f"{opp.get('deal', '')}"
                        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Deal Hunter
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔥 ציד דילים":
    st.title("🔥 ציד דילים — Error Fares & Flash Sales")
    st.caption("סורק secretflying, El Al, Israir, Arkia, Ryanair, WizzAir — מחפש שגיאות מחיר ומבצעי פלאש")

    GRADE_COLOR = {"A+": "#00ff88", "A": "#44ff88", "B": "#88ff44", "C": "#ffcc00", "D": "#ff4444"}
    URGENCY_ICON = {"immediate": "🚨", "today": "⚡", "this_week": "📅"}

    tab1, tab2 = st.tabs(["🔍 ציד חדש", "📋 דילים שנמצאו"])

    with tab1:
        st.markdown("בחר אתרי מקור לסריקה:")
        sources_selected = {}
        src_cols = st.columns(4)
        for i, (name, url) in enumerate(deal_hunter.DEAL_SOURCES.items()):
            with src_cols[i % 4]:
                sources_selected[name] = st.checkbox(name, value=(i < 4), key=f"src_{name}")

        selected_urls = [deal_hunter.DEAL_SOURCES[k] for k, v in sources_selected.items() if v]

        if st.button("🔥 צוד דילים עכשיו!", use_container_width=True, type="primary"):
            if not selected_urls:
                st.error("בחר לפחות מקור אחד")
            else:
                with st.spinner(f"🤖 Claude סורק {len(selected_urls)} אתרים... (30-90 שניות)"):
                    found = deal_hunter.hunt_deals(selected_urls)

                if not found or (len(found) == 1 and "error" in found[0]):
                    err = found[0].get("error", "") if found else ""
                    st.warning(f"לא נמצאו דילים. {err}")
                else:
                    st.success(f"🎉 נמצאו {len(found)} דילים!")
                    for d in found:
                        grade = d.get("ai_grade", d.get("deal_type", ""))
                        gcolor = GRADE_COLOR.get(grade, "#aaa")
                        urgency = URGENCY_ICON.get(d.get("urgency", ""), "📅")
                        with st.container():
                            book_link = f'<br><a href="{d["book_url"]}" target="_blank">🔗 הזמן</a>' if d.get("book_url") else ""
                            st.markdown(
                                f"<div style='background:rgba(255,255,255,0.04);border-radius:10px;"
                                f"padding:12px 16px;margin-bottom:8px;border-left:3px solid {gcolor}'>"
                                f"<b style='color:{gcolor}'>{urgency} {d.get('destination','')} "
                                f"({d.get('destination_code','')})</b> — "
                                f"<b>${d.get('price', 0):.0f}</b> | {d.get('airline','')} | "
                                f"<span style='color:#aaa'>{d.get('dates','')}</span><br>"
                                f"<small>{d.get('why_amazing', d.get('why_cheap',''))}</small>"
                                f"{book_link}"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

    with tab2:
        min_score_filter = st.slider("ציון מינימלי", 0.0, 10.0, 5.0, 0.5)
        recent = deal_hunter.get_recent_deals(limit=50, min_score=min_score_filter)

        if not recent:
            st.info("אין דילים שמורים עדיין. לחץ 'צוד דילים' כדי להתחיל.")
        else:
            st.caption(f"מציג {len(recent)} דילים (מינימום ציון {min_score_filter})")

            # Score leaderboard with AI scoring
            if st.button("🤖 נקד דילים עם AI", key="ai_score_btn"):
                with st.spinner("מנקד..."):
                    scored = deal_scorer.score_and_filter(recent, min_score=0)
                recent = scored if scored else recent

            for d in recent:
                score = d.get("score", d.get("ai_score", 0))
                grade = d.get("ai_grade", "")
                gcolor = GRADE_COLOR.get(grade, "#667eea")
                score_bar = "█" * int(score) + "░" * (10 - int(score))
                urgency = URGENCY_ICON.get(d.get("urgency", ""), "📅")

                with st.expander(
                    f"{urgency} **{d.get('destination','')}** — "
                    f"${d.get('price', 0):.0f} | ציון: {score:.1f}/10 {grade}"
                ):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(f"**חברה:** {d.get('airline','')}")
                        st.markdown(f"**תאריכים:** {d.get('dates','')}")
                        st.markdown(f"**סוג:** {d.get('deal_type','')}")
                        st.markdown(f"**מקור:** {d.get('source','')}")
                        why = d.get("ai_why") or d.get("why_amazing", "")
                        if why:
                            st.info(f"💡 {why}")
                        action = d.get("ai_action", "")
                        if action:
                            st.markdown(f"👉 **{action}**")
                    with c2:
                        st.markdown(
                            f"<div style='text-align:center'>"
                            f"<h2 style='color:{gcolor};margin:0'>{score:.1f}</h2>"
                            f"<small style='color:{gcolor}'>{grade}</small><br>"
                            f"<span style='color:#aaa;font-size:10px'>{score_bar}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        if d.get("book_url"):
                            st.link_button("🔗 הזמן", d["book_url"])
                        if d.get("expires"):
                            st.caption(f"⏰ פג תוקף: {d['expires']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Surprise Me
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🎲 הפתיעני":
    st.title("🎲 הפתיעני — מצא את הדסטינציה הכי שווה")
    st.caption("הכנס תקציב ותאריכים — Claude ימצא את היעד הכי שווה שאולי לא חשבת עליו")

    with st.form("surprise_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            budget = st.number_input("תקציב לאדם ($)", value=800, min_value=200, step=50)
            currency = st.selectbox("מטבע", ["USD", "EUR", "ILS"])
        with c2:
            from_date = st.date_input("תאריך יציאה", value=None)
            to_date = st.date_input("תאריך חזרה", value=None)
        with c3:
            duration = st.slider("ימי טיול", 3, 21, 7)
            style = st.selectbox("סגנון", ["כל סגנון", "תקציבי", "רומנטי", "הרפתקאות", "תרבות", "טבע", "לוקסוס"])

        interests = st.text_input("תחומי עניין", placeholder="אוכל, היסטוריה, שפת ים, הייקינג...")
        surprise_btn = st.form_submit_button("🎲 הפתיעני!", use_container_width=True, type="primary")

    if surprise_btn:
        from_str = str(from_date) if from_date else ""
        to_str = str(to_date) if to_date else ""

        with st.spinner("🤖 Claude מחפש את הדסטינציות הכי שוות עבורך... (30-60 שניות)"):
            results = smart_search.surprise_me(
                budget=budget,
                currency=currency,
                from_date=from_str,
                to_date=to_str,
                duration_days=duration,
                style=style,
                interests=interests,
            )

        if not results or (len(results) == 1 and "error" in results[0]):
            err = results[0].get("error", "") if results else ""
            st.error(f"לא נמצאו תוצאות. {err}")
        else:
            st.success(f"🎉 נמצאו {len(results)} יעדים מדהימים!")
            st.divider()

            for i, dest in enumerate(results):
                gem_badge = "💎 Hidden Gem!" if dest.get("hidden_gem") else ""
                quality = dest.get("deal_quality", "")
                q_color = {"excellent": "#00ff88", "good": "#88ff44", "average": "#ffcc00"}.get(quality, "#aaa")
                surprise = dest.get("surprise_factor", 0)

                with st.container():
                    medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][min(i, 4)]
                    st.markdown(
                        f"<div style='background:rgba(255,255,255,0.04);border-radius:12px;"
                        f"padding:16px 20px;margin-bottom:12px;"
                        f"border:1px solid rgba(255,255,255,0.08)'>"
                        f"<h3 style='margin:0;color:white'>{medal} {dest.get('destination','')}"
                        f" <small style='color:#aaa'>({dest.get('destination_code','')})</small>"
                        f" {gem_badge}</h3>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    c1, c2, c3 = st.columns([2, 1, 1])
                    with c1:
                        st.markdown(f"**💡 {dest.get('why_amazing', '')}**")
                        highlights = dest.get("highlights", [])
                        if highlights:
                            st.markdown(" | ".join(f"✨ {h}" for h in highlights[:3]))
                        if dest.get("best_time_to_book"):
                            st.caption(f"📅 מתי להזמין: {dest['best_time_to_book']}")
                    with c2:
                        st.metric("סה״כ לאדם", f"${dest.get('total_price', 0):,}")
                        st.caption(f"✈️ טיסה: ${dest.get('flight_price', 0):,}")
                        st.caption(f"🏨 מלון/לילה: ${dest.get('hotel_price_night', 0):,}")
                    with c3:
                        st.markdown(
                            f"<div style='text-align:center;padding:10px'>"
                            f"<span style='font-size:2em'>{'⭐' * min(int(surprise/2), 5)}</span><br>"
                            f"<span style='color:{q_color}'>{quality}</span><br>"
                            f"<small>Surprise: {surprise}/10</small>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button("➕ הוסף למעקב", key=f"add_surprise_{i}"):
                            new_item = db.WatchItem(
                                id=None,
                                name=f"🎲 {dest.get('destination','')}",
                                category="package",
                                query=dest.get("why_amazing", ""),
                                destination=dest.get("destination", ""),
                                origin="TLV",
                                date_from=from_str or None,
                                date_to=to_str or None,
                                max_price=dest.get("total_price"),
                                drop_pct=10.0,
                            )
                            db.add_watch_item(new_item)
                            st.success("נוסף למעקב! ✅")

                    st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Smart Tools
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🛠️ כלים חכמים":
    st.title("🛠️ כלים חכמים")
    st.caption("חיפוש מתקדם: Split Ticket, שדות תעופה קרובים, Last Minute, יום זול בשבוע, חבילה vs. עצמאי")

    tool_tab = st.tabs([
        "✂️ Split Ticket",
        "🏙️ שדות תעופה",
        "⏰ Last Minute",
        "📆 יום זול",
        "📦 חבילה vs. עצמאי",
        "📅 מתי להזמין",
    ])

    # ── Split Ticket ────────────────────────────────────────────────────────
    with tool_tab[0]:
        st.subheader("✂️ Split Ticket — הלוך-חזור vs. שני כרטיסים נפרדים")
        st.caption("לפעמים שני כרטיסים חד-כיווניים זולים יותר מהלוך-חזור")

        with st.form("split_form"):
            sc1, sc2 = st.columns(2)
            with sc1:
                split_origin = st.text_input("מוצא", value="TLV")
                split_dest = st.text_input("יעד", placeholder="LHR")
            with sc2:
                split_out = st.date_input("תאריך יציאה", key="split_out")
                split_ret = st.date_input("תאריך חזרה", key="split_ret")
            split_btn = st.form_submit_button("✂️ השווה", use_container_width=True, type="primary")

        if split_btn and split_dest:
            with st.spinner("🤖 Claude משווה מחירים... (30-60 שניות)"):
                result = smart_search.check_split_ticket(
                    origin=split_origin,
                    destination=split_dest,
                    outbound_date=str(split_out),
                    return_date=str(split_ret),
                )

            if "error" in result:
                st.error(result["error"])
            else:
                rec = result.get("recommendation", "")
                savings = result.get("savings", 0)

                c1, c2, c3 = st.columns(3)
                c1.metric("הלוך-חזור", f"${result.get('roundtrip_price', 0):,}")
                c2.metric(
                    "שני חד-כיווניים",
                    f"${result.get('split_total', 0):,}",
                    delta=f"-${savings:,.0f}" if savings > 0 else f"+${-savings:,.0f}",
                    delta_color="normal" if savings > 0 else "inverse",
                )
                c3.metric("חיסכון", f"${savings:,.0f} ({result.get('savings_pct', 0):.1f}%)")

                st.divider()
                if rec == "split":
                    st.success(f"✅ **Split Ticket משתלם!** חסכון של ${savings:,.0f}")
                else:
                    st.info(f"ℹ️ **הלוך-חזור עדיף** במקרה זה")

                st.markdown(f"**נימוק:** {result.get('reasoning', '')}")

                lc1, lc2 = st.columns(2)
                with lc1:
                    if result.get("book_out_url"):
                        st.link_button("✈️ הזמן יציאה", result["book_out_url"])
                with lc2:
                    if result.get("book_return_url"):
                        st.link_button("✈️ הזמן חזרה", result["book_return_url"])

    # ── Nearby Airports ─────────────────────────────────────────────────────
    with tool_tab[1]:
        st.subheader("🏙️ השווה שדות תעופה — TLV / SDV / ETH / HFA")
        st.caption("לפעמים טיסה מאילת או חיפה זולה יותר מנתב\"ג")

        with st.form("nearby_form"):
            na_c1, na_c2, na_c3 = st.columns(3)
            with na_c1:
                na_dest = st.text_input("יעד", placeholder="ATH, FCO, BCN...")
            with na_c2:
                na_date = st.date_input("תאריך יציאה", key="na_date")
            with na_c3:
                na_ret = st.date_input("תאריך חזרה (אופציונלי)", value=None, key="na_ret")
            na_btn = st.form_submit_button("🔍 השווה", use_container_width=True, type="primary")

        if na_btn and na_dest:
            with st.spinner("🤖 Claude בודק כל שדות התעופה..."):
                airports = smart_search.check_nearby_airports(
                    destination=na_dest,
                    date=str(na_date),
                    return_date=str(na_ret) if na_ret else "",
                )

            if not airports:
                st.warning("לא נמצאו תוצאות. ודא שהיעד נכון.")
            else:
                cheapest = airports[0]
                st.success(f"🏆 הכי זול: **{cheapest['airport_name']}** — ${cheapest['price']:,}")
                st.divider()

                for ap in airports:
                    is_best = ap == cheapest
                    color = "#00ff88" if is_best else "#cccccc"
                    savings_vs_best = ap["price"] - cheapest["price"]
                    st.markdown(
                        f"<div style='padding:10px;margin-bottom:6px;"
                        f"background:rgba(255,255,255,{'0.08' if is_best else '0.03'});"
                        f"border-radius:8px;border-left:3px solid {color}'>"
                        f"<b style='color:{color}'>{ap['airport_code']} — {ap['airport_name']}</b>"
                        f"  <span style='float:right;color:{color}'>${ap['price']:,}</span><br>"
                        f"<small style='color:#aaa'>{ap.get('airline','')} "
                        f"{'(הכי זול ✅)' if is_best else f'(+${savings_vs_best:,})'}"
                        f"{'  ' + ap.get('notes','') if ap.get('notes') else ''}</small>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    # ── Last Minute ─────────────────────────────────────────────────────────
    with tool_tab[2]:
        st.subheader("⏰ Last Minute — דילים לשבוע הקרוב")
        st.caption("חברות תעופה מוכרות כרטיסים ריקים בזול ברגע האחרון")

        with st.form("lm_form"):
            lm_c1, lm_c2, lm_c3 = st.columns(3)
            with lm_c1:
                lm_origin = st.text_input("מוצא", value="TLV")
            with lm_c2:
                lm_days = st.slider("כמה ימים קדימה", 3, 14, 7)
            with lm_c3:
                lm_max = st.number_input("מחיר מקסימלי ($)", value=300, min_value=50, step=50)
            lm_btn = st.form_submit_button("⏰ מצא Last Minute", use_container_width=True, type="primary")

        if lm_btn:
            with st.spinner(f"🤖 Claude מחפש דילי last-minute ל-{lm_days} הימים הקרובים..."):
                deals = smart_search.find_last_minute_deals(
                    origin=lm_origin,
                    days_ahead=lm_days,
                    max_price=lm_max,
                )

            if not deals:
                st.info(f"לא נמצאו דילים מתחת ל-${lm_max}. נסה להגדיל את המחיר המקסימלי.")
            else:
                st.success(f"🎉 נמצאו {len(deals)} דילי last-minute!")
                import pandas as pd
                df = pd.DataFrame(deals)
                display_cols = [c for c in ["destination", "departure_date", "price", "airline", "seats_left", "deal_type", "why_cheap"] if c in df.columns]
                st.dataframe(df[display_cols] if display_cols else df, use_container_width=True, hide_index=True)

                for d in deals[:3]:
                    with st.expander(f"✈️ {d.get('destination','')} — ${d.get('price',0):,} ({d.get('departure_date','')})"):
                        st.markdown(f"**חברה:** {d.get('airline','')}")
                        st.markdown(f"**סיבת הזול:** {d.get('why_cheap','')}")
                        if d.get("seats_left"):
                            st.warning(f"⚠️ נותרו {d['seats_left']} מקומות!")
                        if d.get("book_by"):
                            st.caption(f"⏰ הזמן עד: {d['book_by']}")

    # ── Cheapest Day ─────────────────────────────────────────────────────────
    with tool_tab[3]:
        st.subheader("📆 איזה יום בשבוע הכי זול?")
        st.caption("ניתוח ממוצע מחירים לפי יום שבוע — תחסוך עד 30%")

        with st.form("cheap_day_form"):
            cd_c1, cd_c2, cd_c3 = st.columns(3)
            with cd_c1:
                cd_origin = st.text_input("מוצא", value="TLV")
            with cd_c2:
                cd_dest = st.text_input("יעד", placeholder="BCN")
            with cd_c3:
                cd_month = st.text_input("חודש (YYYY-MM)", value=datetime.now().strftime("%Y-%m"))
            cd_btn = st.form_submit_button("📆 נתח ימים", use_container_width=True, type="primary")

        if cd_btn and cd_dest:
            with st.spinner("🤖 Claude מנתח מחירים לפי ימי שבוע..."):
                result = smart_search.find_cheapest_day_of_week(
                    origin=cd_origin,
                    destination=cd_dest,
                    month=cd_month,
                )

            if "error" in result:
                st.error(result["error"])
            elif not result:
                st.warning("לא נמצאו נתונים")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("יום הכי זול", result.get("cheapest_day", ""))
                c2.metric("יום הכי יקר", result.get("most_expensive_day", ""))
                c3.metric(
                    "חיסכון פוטנציאלי",
                    f"${result.get('savings_by_day', 0):,}",
                    delta=f"-{result.get('savings_pct', 0):.0f}%",
                )

                st.info(f"💡 {result.get('tip', '')}")
                if result.get("best_time"):
                    st.caption(f"⏰ שעה מומלצת: {result['best_time']}")

                # Ranking chart
                ranking = result.get("days_ranking", [])
                if ranking:
                    fig = go.Figure(go.Bar(
                        x=[r["day"] for r in ranking],
                        y=[r["avg_price"] for r in ranking],
                        marker_color=["#00ff88" if r["day"] == result.get("cheapest_day") else "#667eea" for r in ranking],
                        text=[f"${r['avg_price']:,}" for r in ranking],
                        textposition="outside",
                    ))
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                        font=dict(color="#ccc"), height=300,
                        margin=dict(l=10, r=10, t=10, b=10),
                    )
                    st.plotly_chart(fig, use_container_width=True)

    # ── Package vs. Separate ─────────────────────────────────────────────────
    with tool_tab[4]:
        st.subheader("📦 חבילה מאורגנת vs. הזמנה עצמאית")
        st.caption("מחשב אם Gulliver/IsraFlight/Dan זול יותר מלהזמין לבד")

        with st.form("pkg_form"):
            pk_c1, pk_c2 = st.columns(2)
            with pk_c1:
                pk_origin = st.text_input("מוצא", value="TLV")
                pk_dest = st.text_input("יעד", placeholder="פראג")
                pk_travelers = st.number_input("נוסעים", value=2, min_value=1, max_value=10)
            with pk_c2:
                pk_from = st.date_input("תאריך יציאה", key="pk_from")
                pk_to = st.date_input("תאריך חזרה", key="pk_to")
            pk_btn = st.form_submit_button("📦 השווה", use_container_width=True, type="primary")

        if pk_btn and pk_dest:
            with st.spinner("🤖 Claude משווה חבילה vs. עצמאי... (30-60 שניות)"):
                result = smart_search.compare_package_vs_separate(
                    origin=pk_origin,
                    destination=pk_dest,
                    date_from=str(pk_from),
                    date_to=str(pk_to),
                    travelers=pk_travelers,
                )

            if "error" in result:
                st.error(result["error"])
            elif not result:
                st.warning("לא נמצאו נתונים")
            else:
                rec = result.get("recommendation", "")
                pkg_price = result.get("package_price", 0)
                sep_price = result.get("separate_total", 0)
                saving_pkg = result.get("savings_with_package", 0)
                saving_sep = result.get("savings_with_separate", 0)

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric(
                        f"📦 חבילה ({result.get('package_provider', '')})",
                        f"${pkg_price:,}",
                        delta=f"-${saving_pkg:,}" if saving_pkg > 0 else None,
                    )
                    includes = result.get("package_includes", [])
                    if includes:
                        st.caption("כולל: " + " | ".join(includes[:3]))
                with c2:
                    st.metric(
                        "🎒 הזמנה עצמאית",
                        f"${sep_price:,}",
                        delta=f"-${saving_sep:,}" if saving_sep > 0 else None,
                    )
                    st.caption(
                        f"✈️ טיסה: ${result.get('separate_flight',0):,} | "
                        f"🏨 מלון: ${result.get('separate_hotel_total',0):,}"
                    )
                with c3:
                    winner = "📦 חבילה" if rec == "package" else "🎒 עצמאי"
                    st.markdown(
                        f"<div style='text-align:center;padding:20px;background:rgba(0,255,136,0.1);"
                        f"border-radius:10px;border:1px solid #00ff88'>"
                        f"<h3 style='color:#00ff88;margin:0'>✅ {winner}</h3>"
                        f"<small>המומלץ</small></div>",
                        unsafe_allow_html=True,
                    )

                st.markdown(f"**נימוק:** {result.get('reasoning', '')}")

                tips = result.get("tips", [])
                if tips:
                    st.subheader("💡 טיפים")
                    for tip in tips:
                        st.markdown(f"• {tip}")

    # ── Best Time to Book ────────────────────────────────────────────────────
    with tool_tab[5]:
        st.subheader("📅 מתי הכי כדאי להזמין?")
        st.caption("ניתוח נתוני עבר: כמה שבועות לפני הטיסה המחיר הכי נמוך?")

        with st.form("btb_form"):
            btb_c1, btb_c2, btb_c3 = st.columns(3)
            with btb_c1:
                btb_origin = st.text_input("מוצא", value="TLV")
            with btb_c2:
                btb_dest = st.text_input("יעד", placeholder="NYC, BKK, LON...")
            with btb_c3:
                btb_month = st.text_input("חודש נסיעה (אופציונלי)", placeholder="יולי 2025")
            btb_btn = st.form_submit_button("📅 נתח", use_container_width=True, type="primary")

        if btb_btn and btb_dest:
            with st.spinner("🤖 Claude מנתח דפוסי מחיר היסטוריים..."):
                result = smart_search.best_time_to_book(btb_origin, btb_dest, btb_month)

            if "error" in result:
                st.error(result["error"])
            elif not result:
                st.warning("לא נמצאו נתונים")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("⭐ זמן מיטבי", f"{result.get('optimal_weeks_before', '?')} שבועות לפני")
                c2.metric("💰 חיסכון פוטנציאלי", f"{result.get('potential_savings_pct', 0)}%")
                c3.metric("⚠️ הגרוע ביותר", result.get("worst_time", ""))

                st.success(f"**כלל אצבע:** {result.get('rule_of_thumb', '')}")

                if result.get("seasonal_advice"):
                    st.info(f"📆 {result['seasonal_advice']}")
                if result.get("last_minute_exception"):
                    st.caption(f"🎲 חריג: {result['last_minute_exception']}")
                if result.get("tip"):
                    st.info(f"💡 {result['tip']}")

                # Price curve chart
                curve = result.get("price_curve", [])
                if curve:
                    optimal_w = result.get("optimal_weeks_before", 0)
                    xs = [p.get("label", str(p.get("weeks_before", ""))) for p in curve]
                    ys = [p.get("relative_price", 1.0) for p in curve]
                    colors = ["#00ff88" if p.get("weeks_before") == optimal_w else "#667eea" for p in curve]

                    fig = go.Figure(go.Bar(
                        x=xs, y=ys,
                        marker_color=colors,
                        text=[f"{y:.0%}" for y in ys],
                        textposition="outside",
                    ))
                    fig.add_hline(y=1.0, line_dash="dot", line_color="#00ff88",
                                  annotation_text="מחיר מיטבי")
                    fig.update_layout(
                        title=dict(text="📉 מחיר יחסי לפי זמן הזמנה (1.0 = הכי זול)", font=dict(color="white", size=13)),
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                        font=dict(color="#ccc"), height=300,
                        margin=dict(l=10, r=10, t=40, b=10),
                        yaxis=dict(tickformat=".0%", gridcolor="rgba(255,255,255,0.08)"),
                        xaxis=dict(showgrid=False),
                    )
                    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Competitor Comparison
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 השוואת אתרים":
    st.title("🔍 השוואת אתרים — Kayak vs. Expedia vs. Google Flights")
    st.caption("אותה טיסה, 5 אתרים שונים — מי הכי זול?")

    with st.form("comp_form"):
        cc1, cc2 = st.columns(2)
        with cc1:
            comp_origin = st.text_input("מוצא", value="TLV")
            comp_dest = st.text_input("יעד *", placeholder="NYC, LON, BKK...")
            comp_travelers = st.number_input("נוסעים", value=1, min_value=1, max_value=9)
        with cc2:
            comp_out = st.date_input("תאריך יציאה")
            comp_ret = st.date_input("תאריך חזרה (ריק = חד-כיווני)", value=None)
            comp_cat = st.selectbox("סוג", ["flight", "hotel"],
                                     format_func=lambda x: "✈️ טיסה" if x == "flight" else "🏨 מלון")
        comp_btn = st.form_submit_button("🔍 השווה בכל האתרים", use_container_width=True, type="primary")

    if comp_btn and comp_dest:
        with st.spinner("🤖 Claude מחפש בכל האתרים בו-זמנית... (60-90 שניות)"):
            results = competitor_check.compare_prices(
                origin=comp_origin,
                destination=comp_dest,
                date_out=str(comp_out),
                date_return=str(comp_ret) if comp_ret else "",
                travelers=comp_travelers,
                category=comp_cat,
            )

        if not results or (len(results) == 1 and "error" in results[0]):
            err = results[0].get("error", "") if results else ""
            st.error(f"לא נמצאו תוצאות. {err}")
        else:
            cheapest = results[0]
            st.success(
                f"🏆 הכי זול: **{cheapest.get('site','')}** — "
                f"${cheapest.get('price',0):,} {cheapest.get('currency','')}"
            )
            st.divider()

            # Visual comparison bars
            max_price = max(r.get("price", 1) for r in results)
            for i, r in enumerate(results):
                price = r.get("price", 0)
                bar_pct = price / max_price if max_price else 1
                is_best = i == 0
                color = "#00ff88" if is_best else "#667eea"
                savings = price - cheapest["price"]

                st.markdown(
                    f"<div style='margin-bottom:10px'>"
                    f"<div style='display:flex;justify-content:space-between;margin-bottom:3px'>"
                    f"<b style='color:{'#00ff88' if is_best else 'white'}'>"
                    f"{'🏆 ' if is_best else ''}{r.get('site','')}</b>"
                    f"<span style='color:{color}'>${price:,}"
                    f"{'' if is_best else f' (+${savings:,})'}</span>"
                    f"</div>"
                    f"<div style='background:rgba(255,255,255,0.1);border-radius:4px;height:8px'>"
                    f"<div style='background:{color};width:{bar_pct*100:.0f}%;height:100%;border-radius:4px'></div>"
                    f"</div>"
                    f"<small style='color:#aaa'>{r.get('airline','')} | "
                    + ("✈️ ישיר" if r.get('stops') == 0 else f"{r.get('stops',0)} עצירות")
                    + f" | {r.get('duration_hours',0):.1f}h | {r.get('notes','')[:60]}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if r.get("url"):
                    st.link_button(f"🔗 הזמן ב-{r['site']}", r["url"])
                st.markdown("")

            # Summary table
            import pandas as pd
            st.divider()
            with st.expander("📋 טבלת השוואה"):
                df_cols = ["site", "price", "currency", "airline", "stops", "duration_hours", "notes"]
                df = pd.DataFrame([{c: r.get(c, "") for c in df_cols} for r in results])
                df.columns = ["אתר", "מחיר", "מטבע", "חברה", "עצירות", "שעות טיסה", "הערות"]
                st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Sentiment Analyzer
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📰 סנטימנט & חדשות":
    st.title("📰 ניתוח סנטימנט — חדשות שמשפיעות על מחירים")
    st.caption("Claude סורק חדשות: שביתות, בחירות, מזג אוויר, אירועים — ומנבא השפעה על מחירי טיסות")

    with st.form("sent_form"):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            sent_origin = st.text_input("מוצא", value="TLV")
        with sc2:
            sent_dest = st.text_input("יעד *", placeholder="לונדון, NYC, בנגקוק...")
        with sc3:
            sent_date = st.text_input("תאריך טיסה מתוכנן", placeholder="יולי 2025")
        sent_btn = st.form_submit_button("📰 נתח חדשות & סנטימנט", use_container_width=True, type="primary")

    if sent_btn and sent_dest:
        with st.spinner("🤖 Claude סורק חדשות ומנתח השפעות... (30-60 שניות)"):
            raw = sentiment_analyzer.analyze_sentiment(sent_origin, sent_dest, sent_date)
            fmt = sentiment_analyzer.format_sentiment(raw)

        if not fmt or "error" in raw:
            st.error(raw.get("error", "לא ניתן לנתח"))
        else:
            # Main verdict
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:2.5em'>{fmt['sentiment_icon']}</div>"
                    f"<b style='color:{fmt['sentiment_color']}'>{fmt['sentiment'].upper()}</b><br>"
                    f"<small>סנטימנט שוק</small></div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:2em'>{fmt['impact_icon']}</div>"
                    f"<b>{'מחירים עולים' if fmt['price_impact']=='rising' else 'מחירים יורדים' if fmt['price_impact']=='falling' else 'יציב'}</b><br>"
                    f"<span style='color:#00ff88'>{fmt['impact_pct']:+.0f}%</span> צפוי"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with c3:
                risk_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fmt["risk_level"], "⚪")
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:2em'>{risk_icon}</div>"
                    f"<b style='color:{fmt['risk_color']}'>סיכון {fmt['risk_level']}</b><br>"
                    f"<small>רמת אי-וודאות</small></div>",
                    unsafe_allow_html=True,
                )
            with c4:
                conf_color = {"high": "#00ff88", "medium": "#ffd93d", "low": "#ff6b6b"}.get(fmt["confidence"], "#aaa")
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:1.5em'>🎯</div>"
                    f"<b style='color:{conf_color}'>{fmt['recommendation']}</b><br>"
                    f"<small>ביטחון: {fmt['confidence']}</small></div>",
                    unsafe_allow_html=True,
                )

            st.divider()

            # Reasoning
            st.markdown(f"### 💡 ניתוח\n{fmt['reasoning']}")
            if fmt.get("best_booking_window"):
                st.success(f"📅 **מתי להזמין:** {fmt['best_booking_window']}")

            # Key events
            events = fmt.get("key_events", [])
            if events:
                st.divider()
                st.subheader(f"📌 {len(events)} אירועים מרכזיים")
                event_type_icons = {
                    "strike": "✊", "event": "🎭", "weather": "🌩️",
                    "political": "🏛️", "seasonal": "📅", "economic": "💹",
                }
                impact_colors = {"negative": "#ff4444", "positive": "#00ff88", "neutral": "#aaaaaa"}
                magnitude_labels = {"high": "השפעה גבוהה", "medium": "בינונית", "low": "נמוכה"}

                for ev in events:
                    ev_icon = event_type_icons.get(ev.get("type", ""), "📌")
                    ev_color = impact_colors.get(ev.get("impact", "neutral"), "#aaa")
                    ev_mag = magnitude_labels.get(ev.get("magnitude", ""), "")
                    st.markdown(
                        f"<div style='padding:10px;margin-bottom:6px;"
                        f"background:rgba(255,255,255,0.04);border-radius:8px;"
                        f"border-left:3px solid {ev_color}'>"
                        f"<b>{ev_icon} {ev.get('title','')}</b>"
                        f"<span style='float:right;color:{ev_color}'>{ev.get('impact_on_price','')}</span><br>"
                        f"<small style='color:#aaa'>{ev_mag} | {ev.get('timeframe','')} | {ev.get('source','')}</small>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            # Score gauge
            score = fmt.get("score", 5)
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "ציון סנטימנט (0=זול, 10=יקר)", "font": {"color": "white"}},
                gauge={
                    "axis": {"range": [0, 10], "tickcolor": "#aaa"},
                    "bar": {"color": "#667eea"},
                    "steps": [
                        {"range": [0, 3], "color": "rgba(0,255,136,0.2)"},
                        {"range": [3, 7], "color": "rgba(255,204,0,0.2)"},
                        {"range": [7, 10], "color": "rgba(255,75,75,0.2)"},
                    ],
                    "threshold": {"line": {"color": "white", "width": 2}, "value": score},
                },
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#ccc"),
                height=220, margin=dict(l=20, r=20, t=40, b=20),
            )
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Deal Expiry Tracker
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⏰ דילים שפגים":
    st.title("⏰ דילים שפגים בקרוב")
    st.caption("התראות על דילים שעומדים לפוג — כדי שלא תפספס")

    if st.session_state.monitor_running:
        st_autorefresh(interval=300_000, key="expiry_refresh")  # refresh every 5 min

    hours_window = st.slider("הצג דילים שפגים בתוך כמה שעות", 1, 24, 3)

    expiring = deal_hunter.get_expiring_deals(hours_ahead=hours_window)

    col_exp, col_all = st.columns([1, 1])
    with col_exp:
        st.metric("דילים שפגים בקרוב", len(expiring), delta=None)
    with col_all:
        all_deals = deal_hunter.get_recent_deals(limit=200, min_score=0)
        st.metric("סה״כ דילים במאגר", len(all_deals))

    st.divider()

    if not expiring:
        st.success(f"✅ אין דילים שפגים בתוך {hours_window} השעות הקרובות")
        st.caption("הרץ 'ציד דילים' כדי לאסוף דילים חדשים עם תאריך תפוגה")
    else:
        st.warning(f"⚠️ {len(expiring)} דיל/ים פגים בתוך {hours_window} שעות!")
        for d in expiring:
            mins = d.get("expires_in_minutes", 60)
            urgency_color = "#ff4444" if mins <= 30 else "#ffcc00" if mins <= 60 else "#ffa500"
            time_str = f"~{mins} דקות" if mins < 120 else f"~{mins//60} שעות"

            st.markdown(
                f"<div style='background:rgba(255,75,75,0.1);border:1px solid {urgency_color};"
                f"border-radius:10px;padding:14px 18px;margin-bottom:10px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<b style='font-size:1.1em'>✈️ {d.get('destination','')} ({d.get('destination_code','')})</b>"
                f"<b style='color:{urgency_color}'>⏰ פג בעוד {time_str}</b>"
                f"</div>"
                f"<span style='font-size:1.4em;color:#00ff88'>${d.get('price',0):,.0f}</span>"
                f" | {d.get('airline','')} | ציון: {d.get('score',0):.1f}/10<br>"
                f"<small style='color:#aaa'>{d.get('why_amazing','')[:100]}</small><br>"
                f"<small>פג: {d.get('expires','')}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )
            bc1, bc2 = st.columns(2)
            if d.get("book_url"):
                with bc1:
                    st.link_button("🔗 הזמן עכשיו!", d["book_url"])
            with bc2 if d.get("book_url") else bc1:
                if st.button("📲 שלח התראה", key=f"alert_exp_{d.get('id',0)}"):
                    import notifiers
                    msg = deal_scorer.format_deal_alert(d)
                    notifiers.broadcast(f"⏰ דיל פג בעוד {time_str}!", msg)
                    st.success("נשלחה התראה!")

    # All deals with expiry
    st.divider()
    with st.expander("📋 כל הדילים עם תאריך תפוגה"):
        deals_with_expiry = [d for d in all_deals if d.get("expires")]
        if not deals_with_expiry:
            st.info("אין דילים עם תאריך תפוגה מוגדר")
        else:
            import pandas as pd
            df = pd.DataFrame(deals_with_expiry)
            cols = [c for c in ["destination", "price", "airline", "deal_type", "expires", "score"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Visa Check
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🛂 בדיקת ויזה":
    st.title("🛂 בדיקת ויזה — דרכון ישראלי")
    st.caption("בדוק דרישות כניסה לכל יעד עבור בעלי דרכון ישראלי")

    STATUS_ICONS = {
        "visa_free": ("✅", "#00ff88", "ללא ויזה"),
        "visa_on_arrival": ("🟡", "#ffd93d", "ויזה בהגעה"),
        "e_visa": ("🔵", "#74b9ff", "eVisa"),
        "visa_required": ("🔴", "#ff6b6b", "ויזה נדרשת"),
        "not_allowed": ("⛔", "#ff0000", "כניסה אסורה"),
    }

    # Quick multi-check or single destination
    vc_tab1, vc_tab2 = st.tabs(["🔍 יעד אחד", "📋 בדיקה מרובה"])

    with vc_tab1:
        with st.form("visa_single"):
            vc_dest = st.text_input("יעד *", placeholder="תאילנד, יפן, ארה״ב, מרוקו...")
            vc_btn = st.form_submit_button("🛂 בדוק ויזה", use_container_width=True, type="primary")

        if vc_btn and vc_dest:
            with st.spinner(f"🤖 Claude בודק דרישות כניסה ל{vc_dest}..."):
                result = visa_check.check_visa(vc_dest)

            if "error" in result:
                st.error(result["error"])
            else:
                status = result.get("status", "")
                cfg = visa_check.get_status_config(status)

                # Big status banner
                st.markdown(
                    f"<div style='text-align:center;padding:24px;margin-bottom:20px;"
                    f"background:rgba(255,255,255,0.05);border-radius:14px;"
                    f"border:2px solid {cfg['color']}'>"
                    f"<div style='font-size:3em'>{cfg['icon']}</div>"
                    f"<h2 style='color:{cfg['color']};margin:8px 0'>{cfg['label']}</h2>"
                    f"<h3 style='color:white;margin:0'>{result.get('destination','')}</h3>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Details grid
                dc1, dc2, dc3 = st.columns(3)
                with dc1:
                    st.metric("תקופת שהות מקס׳", f"{result.get('max_stay_days', '?')} ימים")
                with dc2:
                    cost = result.get("visa_cost_usd", 0)
                    st.metric("עלות ויזה", f"${cost}" if cost else "חינם")
                with dc3:
                    proc = result.get("processing_days", 0)
                    st.metric("זמן עיבוד", f"{proc} ימים" if proc else "מיידי")

                st.divider()

                reqs = result.get("requirements", [])
                notes = result.get("important_notes", [])
                rc1, rc2 = st.columns(2)
                with rc1:
                    if reqs:
                        st.subheader("📄 מסמכים נדרשים")
                        for r in reqs:
                            st.markdown(f"• {r}")
                with rc2:
                    if notes:
                        st.subheader("⚠️ הערות חשובות")
                        for n in notes:
                            st.warning(n)

                if result.get("embassy_info"):
                    st.info(f"🏛️ **שגרירות:** {result['embassy_info']}")

                conf_color = {"high": "#00ff88", "medium": "#ffd93d", "low": "#ff6b6b"}.get(
                    result.get("confidence", "low"), "#aaa"
                )
                st.caption(
                    f"<span style='color:{conf_color}'>מקור: {result.get('source','')} | "
                    f"עדכון: {result.get('last_updated','')} | ביטחון: {result.get('confidence','')}</span>"
                    f"<br><small>⚠️ המידע לצורך הכוונה בלבד. בדוק תמיד מול משרד החוץ לפני נסיעה.</small>",
                    unsafe_allow_html=True,
                )

    with vc_tab2:
        st.caption("בדוק מספר יעדים בו-זמנית")
        multi_dests = st.text_area(
            "יעדים (כל יעד בשורה)",
            placeholder="תאילנד\nיפן\nארה״ב\nמרוקו\nהודו",
            height=150,
        )
        if st.button("🛂 בדוק הכל", use_container_width=True, type="primary", key="visa_multi_btn"):
            dest_list = [d.strip() for d in multi_dests.splitlines() if d.strip()]
            if not dest_list:
                st.error("הכנס לפחות יעד אחד")
            else:
                results_multi = []
                progress = st.progress(0)
                for i, dest in enumerate(dest_list):
                    with st.spinner(f"בודק {dest}..."):
                        r = visa_check.check_visa(dest)
                        r["destination_query"] = dest
                        results_multi.append(r)
                    progress.progress((i + 1) / len(dest_list))

                st.success(f"✅ נבדקו {len(results_multi)} יעדים")
                st.divider()

                # Group by status
                groups = {"visa_free": [], "visa_on_arrival": [], "e_visa": [], "visa_required": [], "not_allowed": []}
                for r in results_multi:
                    s = r.get("status", "visa_required")
                    groups.get(s, groups["visa_required"]).append(r)

                for status_key, items_list in groups.items():
                    if not items_list:
                        continue
                    cfg = visa_check.get_status_config(status_key)
                    st.markdown(
                        f"<h3 style='color:{cfg['color']}'>{cfg['icon']} {cfg['label']} ({len(items_list)})</h3>",
                        unsafe_allow_html=True,
                    )
                    for r in items_list:
                        stay = r.get("max_stay_days", "?")
                        cost = r.get("visa_cost_usd", 0)
                        st.markdown(
                            f"**{r.get('destination', r.get('destination_query',''))}** — "
                            f"{stay} ימים"
                            f"{f' | ${cost}' if cost else ''}"
                        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Settings
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ הגדרות":
    st.title("⚙️ הגדרות")

    # ── API Key ────────────────────────────────────────────────────────────────
    st.subheader("🔑 Claude API Key")
    api_key_val = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key_val:
        st.success(f"מוגדר ✅  (sk-ant-...{api_key_val[-6:]})")
    else:
        new_key = st.text_input("הכנס Anthropic API Key", type="password")
        if st.button("שמור API Key") and new_key:
            _save_env("ANTHROPIC_API_KEY", new_key)
            st.success("נשמר! רענן את הדף.")

    st.divider()

    # ── Notifications ──────────────────────────────────────────────────────────
    st.subheader("🔔 ערוצי התראה")

    st.markdown("""
כשמחיר יורד, ה-agent שולח התראה בכל הערוצים המוגדרים.
ניתן להגדיר כמה ערוצים שרוצים במקביל.
""")

    # ntfy.sh ──────────────────────────────────────────────────────────────────
    with st.expander("📱 **ntfy.sh** — פוש לנייד (חינמי, מומלץ!)", expanded=True):
        st.markdown("""
**הכי קל להגדיר — ללא חשבון:**

1. הורד את אפליקציית **ntfy** לנייד:
   - [iOS (App Store)](https://apps.apple.com/us/app/ntfy/id1625396347)
   - [Android (Google Play)](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. פתח את האפליקציה → Subscribe to topic
3. הזן שם נושא ייחודי (לדוגמה: `megatraveller-שמך123`)
4. הכנס את אותו נושא כאן 👇
""")

        ntfy_topic = os.environ.get("NTFY_TOPIC", "")
        col1, col2 = st.columns([3, 1])
        with col1:
            new_ntfy = st.text_input(
                "ntfy Topic", value=ntfy_topic,
                placeholder="megatraveller-abc123",
                label_visibility="collapsed",
            )
        with col2:
            if st.button("שמור", key="save_ntfy") and new_ntfy:
                _save_env("NTFY_TOPIC", new_ntfy)
                st.success("✅")
                st.rerun()

        if ntfy_topic:
            st.success(f"מוגדר: ntfy.sh/{ntfy_topic}")

    # Telegram ─────────────────────────────────────────────────────────────────
    with st.expander("✈️ **Telegram** — הודעות לטלגרם"):
        st.markdown("""
**הגדרת בוט Telegram:**

1. פתח טלגרם → חפש **@BotFather**
2. שלח `/newbot` → בחר שם → קבל **Token**
3. פתח את הבוט שיצרת → שלח לו הודעה כלשהי
4. גש לכתובת:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   מצא את `"chat":{"id":...}` — זה ה-**Chat ID**
""")

        tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

        new_tg_token = st.text_input(
            "Bot Token", value=tg_token, type="password",
            placeholder="123456789:ABCdef...",
        )
        new_tg_chat = st.text_input(
            "Chat ID", value=tg_chat,
            placeholder="123456789",
        )
        if st.button("שמור Telegram", key="save_tg"):
            if new_tg_token:
                _save_env("TELEGRAM_BOT_TOKEN", new_tg_token)
            if new_tg_chat:
                _save_env("TELEGRAM_CHAT_ID", new_tg_chat)
            st.success("✅ נשמר! רענן.")

        if tg_token and tg_chat:
            st.success("Telegram מוגדר ✅")

    # ── Amadeus API ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader("✈️ Amadeus API — מחירים רשמיים")
    st.markdown("""
**API רשמי של חברות תעופה ומלונות — מדויק פי 10 מחיפוש רגיל.**

**הרשמה חינמית (2,000 קריאות/חודש):**
1. גש ל-[developers.amadeus.com](https://developers.amadeus.com)
2. לחץ **Register** → צור חשבון חינמי
3. לחץ **Create new app** → קבל **Client ID** ו-**Client Secret**
4. הכנס כאן 👇
""")

    am_id = os.environ.get("AMADEUS_CLIENT_ID", "")
    am_secret = os.environ.get("AMADEUS_CLIENT_SECRET", "")

    col1, col2 = st.columns(2)
    with col1:
        new_am_id = st.text_input("Client ID", value=am_id, placeholder="abc123...")
    with col2:
        new_am_secret = st.text_input("Client Secret", value=am_secret,
                                       type="password", placeholder="xyz789...")

    colA, colB = st.columns(2)
    with colA:
        if st.button("💾 שמור Amadeus", key="save_am") and new_am_id:
            _save_env("AMADEUS_CLIENT_ID", new_am_id)
            _save_env("AMADEUS_CLIENT_SECRET", new_am_secret)
            load_dotenv(Path(__file__).parent / ".env", override=True)
            st.success("✅ נשמר!")
    with colB:
        if st.button("🧪 בדוק חיבור Amadeus", key="test_am"):
            import amadeus_client
            load_dotenv(Path(__file__).parent / ".env", override=True)
            with st.spinner("בודק..."):
                result = amadeus_client.test_connection()
            if result["ok"]:
                st.success(result.get("message", "✅ מחובר"))
            else:
                st.error(result.get("error", "שגיאה"))

    if am_id and am_secret:
        st.success("Amadeus מוגדר ✅ — טיסות ומלונות יחפשו דרך API רשמי")
    else:
        st.info("ללא Amadeus — המחירים יחפשו דרך Claude web search (פחות מדויק)")

    # Test all ──────────────────────────────────────────────────────────────────
    st.divider()
    if st.button("🧪 שלח הודעת בדיקה לכל הערוצים", use_container_width=True):
        with st.spinner("שולח..."):
            import alerts as alerts_module
            # Reload env
            load_dotenv(Path(__file__).parent / ".env", override=True)
            status = alerts_module.test_notifications()
        for channel, result in status.items():
            st.markdown(f"**{channel}**: {result}")

    st.divider()

    # ── Monitor ────────────────────────────────────────────────────────────────
    st.subheader("🔄 ניטור אוטומטי")
    st.info(
        "הניטור הרציף בודק את כל הפריטים הפעילים בצורה אוטומטית.\n\n"
        "⚠️ כל בדיקה משתמשת ב-Claude API (עלות כ-$0.01-0.05 לפריט).\n"
        "מומלץ להגדיר מרווח של 60+ דקות."
    )

    st.divider()
    st.subheader("📊 סטטיסטיקות DB")
    items_all = db.get_all_watch_items(enabled_only=False)
    total_records = 0
    for it in items_all:
        hist = db.get_price_history(it["id"], limit=1000)
        total_records += len(hist)

    c1, c2, c3 = st.columns(3)
    c1.metric("פריטי מעקב", len(items_all))
    c2.metric("רשומות מחיר", total_records)
    db_size = Path("prices.db").stat().st_size // 1024 if Path("prices.db").exists() else 0
    c3.metric("גודל DB", f"{db_size} KB")

    st.divider()
    st.subheader("🗑 ניהול נתונים")
    if st.button("מחק את כל הנתונים", type="secondary"):
        if st.session_state.get("confirm_delete"):
            import sqlite3
            with db.get_db() as conn:
                conn.executescript("DELETE FROM price_records; DELETE FROM watch_items;")
            st.success("נמחק הכל")
            st.session_state.confirm_delete = False
        else:
            st.session_state.confirm_delete = True
            st.warning("לחץ שוב לאישור מחיקה")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Price History
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 היסטוריית מחירים":
    import pandas as pd

    st.title("📊 היסטוריית מחירים")
    st.caption("גרפים מפורטים, השוואת פריטים, סטטיסטיקות ומגמות")

    items = db.get_all_watch_items(enabled_only=False)
    if not items:
        st.info("הוסף פריטים ובדוק מחירים כדי לראות היסטוריה.")
    else:
        item_map = {f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']} ({i['destination']})": i for i in items}

        # ── Controls ────────────────────────────────────────────────────────
        ctrl1, ctrl2, ctrl3 = st.columns([3, 1, 1])
        with ctrl1:
            selected_names = st.multiselect(
                "בחר פריטים להשוואה",
                list(item_map.keys()),
                default=list(item_map.keys())[:1],
            )
        with ctrl2:
            history_limit = st.selectbox("רשומות", [30, 60, 100, 200, 500], index=1)
        with ctrl3:
            chart_type = st.selectbox("סוג גרף", ["קו", "עמודות", "קו + נקודות"])

        if not selected_names:
            st.info("בחר לפחות פריט אחד")
            st.stop()

        selected_items = [item_map[n] for n in selected_names]

        # ── Stats cards ─────────────────────────────────────────────────────
        st.divider()
        stat_cols = st.columns(len(selected_items))
        for col, item in zip(stat_cols, selected_items):
            stats = db.get_price_stats(item["id"])
            last = db.get_last_price(item["id"])
            if not stats or not last:
                col.info(f"{item['name']}: אין נתונים")
                continue

            trend = stats.get("trend", "stable")
            trend_icon = "📈" if trend == "rising" else "📉" if trend == "falling" else "➡️"
            trend_pct = stats.get("trend_pct", 0)
            currency = last["currency"]

            with col:
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<b>{CAT_EMOJI.get(item['category'],'')}{item['name']}</b><br>"
                    f"<span style='font-size:1.6em;color:#00ff88'>{last['price']:,.0f} {currency}</span><br>"
                    f"<small>מינימום: {stats['min_price']:,.0f} | מקסימום: {stats['max_price']:,.0f}</small><br>"
                    f"<small>ממוצע: {stats['avg_price']:,.0f} | {stats['total_checks']} בדיקות</small><br>"
                    f"<span style='color:{'#ff4444' if trend=='rising' else '#00ff88' if trend=='falling' else '#aaa'}'>"
                    f"{trend_icon} מגמה: {trend_pct:+.1f}%</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # ── Main chart ──────────────────────────────────────────────────────
        st.divider()
        COLORS = ["#667eea", "#00ff88", "#ff6b6b", "#ffd93d", "#a29bfe", "#fd79a8"]
        fig = go.Figure()

        all_histories = {}
        for i, item in enumerate(selected_items):
            history = db.get_price_history(item["id"], limit=history_limit)
            if not history:
                continue
            history = list(reversed(history))
            all_histories[item["name"]] = history

            xs = [r["checked_at"][:16].replace("T", " ") for r in history]
            ys = [r["price"] for r in history]
            color = COLORS[i % len(COLORS)]

            if chart_type == "עמודות":
                fig.add_trace(go.Bar(x=xs, y=ys, name=item["name"], marker_color=color))
            elif chart_type == "קו":
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, name=item["name"],
                    mode="lines",
                    line=dict(color=color, width=2.5),
                    fill="tozeroy" if len(selected_items) == 1 else None,
                    fillcolor=f"rgba{tuple(list(bytes.fromhex(color[1:])) + [26])}" if len(selected_items) == 1 else None,
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, name=item["name"],
                    mode="lines+markers",
                    line=dict(color=color, width=2),
                    marker=dict(size=6, color=color),
                ))

            # Mark all-time low
            if ys:
                min_y = min(ys)
                min_x = xs[ys.index(min_y)]
                fig.add_annotation(
                    x=min_x, y=min_y,
                    text=f"⬇ {min_y:,.0f}",
                    font=dict(color="#00ff88", size=10),
                    showarrow=True, arrowcolor="#00ff88", arrowsize=0.8,
                )

        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.03)",
            font=dict(color="#cccccc"),
            height=400,
            margin=dict(l=10, r=10, t=20, b=10),
            xaxis=dict(showgrid=False, tickfont=dict(size=9)),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="white")),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Moving average overlay (single item) ────────────────────────────
        if len(selected_items) == 1 and all_histories:
            hist = list(all_histories.values())[0]
            if len(hist) >= 5:
                prices_series = pd.Series([r["price"] for r in hist])
                ma = prices_series.rolling(window=min(5, len(hist))).mean()
                xs = [r["checked_at"][:16].replace("T", " ") for r in hist]

                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=xs, y=prices_series.tolist(),
                    name="מחיר", mode="lines",
                    line=dict(color="#667eea", width=2),
                    fill="tozeroy", fillcolor="rgba(102,126,234,0.08)",
                ))
                fig2.add_trace(go.Scatter(
                    x=xs, y=ma.tolist(),
                    name="ממוצע נע (5)", mode="lines",
                    line=dict(color="#ffd93d", width=1.5, dash="dot"),
                ))
                fig2.update_layout(
                    title=dict(text="📉 ממוצע נע", font=dict(color="white", size=13)),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                    font=dict(color="#ccc"), height=220,
                    margin=dict(l=10, r=10, t=35, b=10),
                    legend=dict(bgcolor="rgba(0,0,0,0)"),
                )
                st.plotly_chart(fig2, use_container_width=True)

        # ── Raw data table ──────────────────────────────────────────────────
        with st.expander("📋 טבלת נתונים גולמיים"):
            for item in selected_items:
                history = db.get_price_history(item["id"], limit=history_limit)
                if not history:
                    continue
                st.markdown(f"**{item['name']}**")
                df = pd.DataFrame(history)
                display_cols = [c for c in ["checked_at", "price", "currency", "source"] if c in df.columns]
                df["checked_at"] = df["checked_at"].str[:16].str.replace("T", " ")
                st.dataframe(df[display_cols], use_container_width=True, hide_index=True, height=200)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Alert Rules
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🎯 כללי התראה":
    st.title("🎯 כללי התראה חכמים")
    st.caption("הגדר תנאים מורכבים: התרע רק כשמחיר מתחת ל-X + ירידה של Y% + ביום מסוים")

    items = db.get_all_watch_items(enabled_only=False)

    tab_new, tab_list = st.tabs(["➕ כלל חדש", "📋 כללים קיימים"])

    # ── New Rule Form ────────────────────────────────────────────────────────
    with tab_new:
        with st.form("rule_form"):
            st.subheader("הגדרת כלל חדש")

            rule_name = st.text_input(
                "שם הכלל *",
                placeholder="טיסה זולה לאירופה בסוף שבוע",
            )

            # Which item
            item_options = {"כל הפריטים": None}
            item_options.update({
                f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']}": i["id"]
                for i in items
            })
            rule_item = st.selectbox("החל על", list(item_options.keys()))

            st.divider()
            st.markdown("**תנאים** (כל תנאי שמסומן חייב להתקיים):")

            rc1, rc2 = st.columns(2)
            with rc1:
                use_max_price = st.checkbox("מחיר מקסימלי")
                max_price_val = st.number_input("מחיר עד ($)", value=400, min_value=0, step=10,
                                                 disabled=not use_max_price)

                use_drop = st.checkbox("ירידת מחיר מינימלית")
                min_drop_val = st.slider("ירידה מינימלית (%)", 5, 60, 15,
                                          disabled=not use_drop)

                use_quality = st.checkbox("איכות דיל מינימלית")
                quality_val = st.selectbox(
                    "איכות מינימלית",
                    ["average", "good", "excellent"],
                    format_func=lambda x: {"average": "⚠️ סביר", "good": "✅ טוב", "excellent": "🔥 מעולה"}[x],
                    disabled=not use_quality,
                )

            with rc2:
                use_days = st.checkbox("ימי שבוע ספציפיים")
                days_options = {
                    "ראשון": 6, "שני": 0, "שלישי": 1,
                    "רביעי": 2, "חמישי": 3, "שישי": 4, "שבת": 5,
                }
                selected_days = st.multiselect(
                    "ימים",
                    list(days_options.keys()),
                    default=["שישי", "שבת"],
                    disabled=not use_days,
                )

                use_airlines = st.checkbox("סנן לפי חברת תעופה")
                airlines_include_str = st.text_input(
                    "חברות מועדפות (מופרד בפסיקים)",
                    placeholder="El Al, Ryanair, EasyJet",
                    disabled=not use_airlines,
                )
                airlines_exclude_str = st.text_input(
                    "חברות לחסימה (מופרד בפסיקים)",
                    placeholder="",
                    disabled=not use_airlines,
                )

                use_score = st.checkbox("ציון AI מינימלי")
                min_score_val = st.slider("ציון מינימלי (0-10)", 0.0, 10.0, 7.0, 0.5,
                                           disabled=not use_score)

            rule_submit = st.form_submit_button("➕ הוסף כלל", use_container_width=True, type="primary")

        if rule_submit:
            if not rule_name:
                st.error("הכנס שם לכלל")
            else:
                conditions = {}
                if use_max_price:
                    conditions["max_price"] = max_price_val
                if use_drop:
                    conditions["min_drop_pct"] = min_drop_val
                if use_quality:
                    conditions["min_deal_quality"] = quality_val
                if use_days and selected_days:
                    conditions["days_of_week"] = [days_options[d] for d in selected_days]
                if use_airlines:
                    inc = [a.strip() for a in airlines_include_str.split(",") if a.strip()]
                    exc = [a.strip() for a in airlines_exclude_str.split(",") if a.strip()]
                    if inc:
                        conditions["airlines_include"] = inc
                    if exc:
                        conditions["airlines_exclude"] = exc
                if use_score:
                    conditions["min_ai_score"] = min_score_val

                watch_id = item_options[rule_item]
                rule_id = db.add_alert_rule(rule_name, conditions, watch_id)

                st.success(f"✅ כלל '{rule_name}' נוסף! (ID: {rule_id})")

                # Preview
                cond_summary = []
                if "max_price" in conditions:
                    cond_summary.append(f"מחיר ≤ ${conditions['max_price']}")
                if "min_drop_pct" in conditions:
                    cond_summary.append(f"ירידה ≥ {conditions['min_drop_pct']}%")
                if "min_deal_quality" in conditions:
                    cond_summary.append(f"איכות ≥ {conditions['min_deal_quality']}")
                if "days_of_week" in conditions:
                    day_names = {6:"א׳",0:"ב׳",1:"ג׳",2:"ד׳",3:"ה׳",4:"ו׳",5:"ש׳"}
                    cond_summary.append("ימים: " + ", ".join(day_names.get(d,"?") for d in conditions["days_of_week"]))
                if "airlines_include" in conditions:
                    cond_summary.append("חברות: " + ", ".join(conditions["airlines_include"]))
                if "min_ai_score" in conditions:
                    cond_summary.append(f"ציון ≥ {conditions['min_ai_score']}")

                if cond_summary:
                    st.info("תנאים: " + " | ".join(cond_summary))
                else:
                    st.warning("לא הוגדרו תנאים — הכלל יופעל תמיד")

    # ── Existing Rules List ──────────────────────────────────────────────────
    with tab_list:
        all_rules = db.get_alert_rules()

        if not all_rules:
            st.info("אין כללים עדיין. צור כלל ב-'כלל חדש'.")
        else:
            st.caption(f"{len(all_rules)} כללים מוגדרים")

            # Item name lookup
            item_names_by_id = {i["id"]: i["name"] for i in items}
            day_names = {6: "א׳", 0: "ב׳", 1: "ג׳", 2: "ד׳", 3: "ה׳", 4: "ו׳", 5: "ש׳"}
            quality_labels = {"average": "⚠️ סביר", "good": "✅ טוב", "excellent": "🔥 מעולה"}

            for rule in all_rules:
                cond = rule["conditions"]
                is_enabled = bool(rule["enabled"])
                status_icon = "🟢" if is_enabled else "🔴"

                # Build readable summary
                tags = []
                if "max_price" in cond:
                    tags.append(f"💲≤${cond['max_price']}")
                if "min_drop_pct" in cond:
                    tags.append(f"📉≥{cond['min_drop_pct']}%")
                if "days_of_week" in cond:
                    tags.append("📅" + ",".join(day_names.get(d, "?") for d in cond["days_of_week"]))
                if "min_deal_quality" in cond:
                    tags.append(quality_labels.get(cond["min_deal_quality"], cond["min_deal_quality"]))
                if "airlines_include" in cond:
                    tags.append("✈️" + "+".join(cond["airlines_include"][:2]))
                if "min_ai_score" in cond:
                    tags.append(f"⭐≥{cond['min_ai_score']}")

                applies_to = item_names_by_id.get(rule.get("watch_id")) or "כל הפריטים"
                last_t = rule.get("last_triggered", "")
                last_t_str = f"הופעל: {last_t[:16].replace('T',' ')}" if last_t else "לא הופעל עדיין"

                with st.expander(
                    f"{status_icon} **{rule['name']}** | {applies_to} | {' '.join(tags) or 'ללא תנאים'}"
                ):
                    lc1, lc2, lc3 = st.columns(3)

                    with lc1:
                        st.markdown(f"**פריט:** {applies_to}")
                        st.markdown(f"**נוצר:** {rule['created_at'][:10]}")
                        st.caption(last_t_str)

                    with lc2:
                        st.markdown("**תנאים:**")
                        if not cond:
                            st.caption("ללא תנאים — מופעל תמיד")
                        for k, v in cond.items():
                            labels = {
                                "max_price": "💲 מחיר מקסימלי",
                                "min_drop_pct": "📉 ירידה מינימלית",
                                "min_deal_quality": "⭐ איכות מינימלית",
                                "days_of_week": "📅 ימי שבוע",
                                "airlines_include": "✈️ חברות מועדפות",
                                "airlines_exclude": "🚫 חברות חסומות",
                                "min_ai_score": "🤖 ציון AI מינימלי",
                            }
                            display_v = v
                            if k == "days_of_week":
                                display_v = ", ".join(day_names.get(d, "?") for d in v)
                            elif k == "min_deal_quality":
                                display_v = quality_labels.get(v, v)
                            st.caption(f"{labels.get(k, k)}: **{display_v}**")

                    with lc3:
                        toggle_label = "⏸ השבת" if is_enabled else "▶ הפעל"
                        if st.button(toggle_label, key=f"tog_rule_{rule['id']}"):
                            db.toggle_alert_rule(rule["id"], not is_enabled)
                            st.rerun()
                        if st.button("🗑 מחק", key=f"del_rule_{rule['id']}"):
                            db.delete_alert_rule(rule["id"])
                            st.rerun()

            # Test rules
            st.divider()
            st.subheader("🧪 בדוק כלל")
            st.caption("הדמה של כלל מול מחיר קיים")
            if items:
                test_item_name = st.selectbox(
                    "פריט לבדיקה",
                    [f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']}" for i in items],
                    key="test_rule_item",
                )
                test_item = items[[f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']}" for i in items].index(test_item_name)]
                test_price = st.number_input("מחיר לבדיקה ($)", value=300, min_value=0, step=10)
                if st.button("🧪 בדוק", key="run_rule_test"):
                    matches = db.evaluate_alert_rules(test_item["id"], float(test_price), {})
                    if matches:
                        for m in matches:
                            st.success(f"✅ כלל '{m['rule_name']}' **יופעל** — {m['message']}")
                    else:
                        st.info("אף כלל לא יופעל למחיר זה")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Flexible Dates
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📅 תאריכים גמישים":
    st.title("📅 מצא את הפלייט הכי זול בחודש")
    st.caption("חיפוש כל תאריכי החודש ומציאת הכי זול")

    with st.form("flex_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            origin_flex = st.text_input("מוצא", value="TLV")
        with c2:
            dest_flex = st.text_input("יעד", placeholder="לונדון")
        with c3:
            month_flex = st.text_input("חודש (YYYY-MM)", value=datetime.now().strftime("%Y-%m"))

        duration_flex = st.slider("משך הטיול (ימים)", 3, 21, 7)
        submitted_flex = st.form_submit_button("🔍 חפש", use_container_width=True)

    if submitted_flex and dest_flex:
        with st.spinner(f"בודק כל תאריכי {month_flex}... (עשוי לקחת כמה דקות)"):
            results = flexible_search.search_cheapest_days(
                origin=origin_flex,
                destination=dest_flex,
                month=month_flex,
                trip_duration=duration_flex,
            )

        if not results:
            st.warning("לא נמצאו תוצאות. ודא שה-Amadeus API מוגדר.")
        else:
            st.success(f"נמצאו {len(results)} אפשרויות!")

            # Winner
            best = results[0]
            st.markdown(
                f"### 🏆 הכי זול: "
                f"**{best['price']:.0f} {best['currency']}**"
                f" — {best['date']}"
            )
            if best.get("return_date"):
                st.caption(f"חזרה: {best['return_date']} | {best.get('details','')}")

            # Table
            import pandas as pd
            df = pd.DataFrame(results)
            df["מחיר"] = df["price"].apply(lambda p: f"{p:.0f}")
            df["תאריך יציאה"] = df["date"]
            df["תאריך חזרה"] = df.get("return_date", "")
            df["איכות"] = df.get("deal_quality", "")
            st.dataframe(
                df[["תאריך יציאה", "תאריך חזרה", "מחיר", "איכות"]],
                use_container_width=True, hide_index=True
            )

            # Bar chart
            fig = go.Figure(go.Bar(
                x=[r["date"] for r in results],
                y=[r["price"] for r in results],
                marker_color=["#00ff88" if i == 0 else "#667eea" for i in range(len(results))],
                text=[f"{r['price']:.0f}" for r in results],
                textposition="outside",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(255,255,255,0.03)",
                font=dict(color="#ccc"),
                height=300,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
            )
            st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Price Prediction
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 חיזוי מחיר":
    st.title("📈 חיזוי מחיר — AI")
    st.caption("Claude מנתח היסטוריה ומחזיר: לקנות עכשיו או להמתין?")

    items = db.get_all_watch_items(enabled_only=False)
    if not items:
        st.info("הוסף פריטים ובדוק מחירים קודם כדי לקבל חיזויים.")
    else:
        item_names = {f"{i['name']} ({i['destination']})": i for i in items}
        selected_name = st.selectbox("בחר פריט לניתוח", list(item_names.keys()))
        item = item_names[selected_name]
        history = db.get_price_history(item["id"], limit=50)

        if len(history) < 3:
            st.warning(f"צריך לפחות 3 בדיקות מחיר. כרגע יש {len(history)}.")
        else:
            if st.button("🤖 נתח עכשיו", use_container_width=True):
                with st.spinner("Claude מנתח מגמות שוק..."):
                    pred = price_predictor.predict_price(item, history)
                    fmt = price_predictor.format_prediction(pred)

                if "error" in (pred or {}):
                    st.error(pred["error"])
                else:
                    # Main verdict
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("מגמה", f"{fmt['icon']} {fmt['trend']}")
                    with col2:
                        delta = fmt.get("trend_pct", 0)
                        st.metric("שינוי צפוי", f"{delta:+.1f}%")
                    with col3:
                        st.metric("דחיפות (1-10)", fmt.get("urgency", "?"))

                    # Recommendation box
                    color_map = {"green": "success", "orange": "warning", "blue": "info"}
                    box_fn = getattr(st, color_map.get(fmt["color"], "info"))
                    box_fn(f"**{fmt['recommendation']}** | {fmt['confidence']}")

                    # Reasoning
                    st.markdown(f"**💡 ניתוח:**\n{fmt['reasoning']}")

                    # Price forecasts
                    if fmt.get("predicted_7d") or fmt.get("predicted_30d"):
                        c1, c2 = st.columns(2)
                        with c1:
                            if fmt.get("predicted_7d"):
                                st.metric("חיזוי 7 ימים", f"{fmt['predicted_7d']:.0f}")
                        with c2:
                            if fmt.get("predicted_30d"):
                                st.metric("חיזוי 30 ימים", f"{fmt['predicted_30d']:.0f}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Trip Planner
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ תכנן טיול":
    st.title("🗺️ תכנן טיול מלא עם AI")
    st.caption("Claude יתכנן עבורך טיול מלא — יעד, תקציב, לוח זמנים")

    with st.form("trip_form"):
        c1, c2 = st.columns(2)
        with c1:
            tp_dest = st.text_input("יעד *", placeholder="טוקיו, יפן")
            tp_origin = st.text_input("מוצא", value="תל אביב")
            tp_from = st.date_input("תאריך יציאה", value=None)
            tp_to = st.date_input("תאריך חזרה", value=None)
        with c2:
            tp_budget = st.number_input("תקציב כולל ($)", value=3000, step=500)
            tp_travelers = st.number_input("מספר נוסעים", value=2, min_value=1, max_value=10)
            tp_style = st.selectbox("סגנון", ["תקציבי", "מאוזן", "לוקסוס"])
            tp_prefs = st.text_area("העדפות מיוחדות", placeholder="אוכל טבעוני, הימנע מטיסות לילה, אוהב טבע...")

        tp_submit = st.form_submit_button("🗺️ תכנן טיול!", use_container_width=True)

    if tp_submit and tp_dest:
        # Quick estimate first
        est = trip_planner.quick_budget_estimate(tp_dest, 7, tp_travelers, tp_style)
        st.info(
            f"**הערכה מהירה:** ~${est['estimated_total']:,} | "
            f"${est['per_day']:,}/יום | ${est['per_person']:,}/אדם"
        )

        with st.spinner("Claude מתכנן את הטיול שלך... (30-60 שניות)"):
            plan = trip_planner.plan_trip(
                destination=tp_dest,
                origin=tp_origin,
                date_from=str(tp_from) if tp_from else "",
                date_to=str(tp_to) if tp_to else "",
                budget=tp_budget,
                travelers=tp_travelers,
                style=tp_style,
                preferences=tp_prefs,
            )

        if "raw" in plan:
            st.markdown(plan["raw"])
        elif "error" in plan:
            st.error(plan["error"])
        else:
            st.success(plan.get("summary", "התכנית מוכנה!"))

            # Budget breakdown
            if "budget_breakdown" in plan:
                st.subheader("💰 פירוט תקציב")
                bd = plan["budget_breakdown"]
                cols = st.columns(len(bd))
                labels = {"flights": "✈️ טיסות", "hotel": "🏨 מלון", "food": "🍽️ אוכל",
                          "activities": "🎭 פעילויות", "transport": "🚌 תחבורה", "other": "📦 אחר"}
                for col, (k, v) in zip(cols, bd.items()):
                    col.metric(labels.get(k, k), f"${v:,}")

            total = plan.get("total_estimated", 0)
            if total:
                st.metric("סה״כ משוער", f"${total:,}")

            # Daily plan
            if "daily_plan" in plan:
                st.subheader("📅 תכנית יומית")
                for day in plan["daily_plan"]:
                    with st.expander(
                        f"יום {day.get('day','')} — {day.get('title','')} "
                        f"(${day.get('estimated_cost', 0):,})"
                    ):
                        if day.get("activities"):
                            st.markdown("**פעילויות:** " + " | ".join(day["activities"]))
                        meals = day.get("meals", {})
                        if any(meals.values()):
                            st.markdown(
                                f"🍳 {meals.get('breakfast','')} | "
                                f"🥗 {meals.get('lunch','')} | "
                                f"🍽️ {meals.get('dinner','')}"
                            )
                        if day.get("accommodation"):
                            st.markdown(f"🛏️ **לינה:** {day['accommodation']}")
                        if day.get("tips"):
                            st.info(f"💡 {day['tips']}")

            # Best deals & advice
            if plan.get("best_deals"):
                st.subheader("🔥 הדילים הכי טובים")
                for deal in plan["best_deals"]:
                    st.markdown(f"• {deal}")

            if plan.get("booking_advice"):
                st.subheader("📌 מתי להזמין")
                st.info(plan["booking_advice"])

            if plan.get("warnings"):
                for w in plan["warnings"]:
                    st.warning(f"⚠️ {w}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Exchange Rates
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💱 שערי חליפין":
    st.title("💱 שערי חליפין")
    st.caption("עקוב אחרי שערי חליפין וקבל התראה כשהשקל חזק")

    fx.ensure_table()

    # Current rates
    st.subheader("📊 שערים נוכחיים")
    if st.button("🔄 רענן שערים"):
        rates = fx.fetch_rates("USD")
        if rates:
            with db.get_db() as conn:
                for base, target, _ in fx.POPULAR_PAIRS:
                    if target in rates:
                        rate_val = rates[target]
                        fx.save_rate(base, target, rate_val)
            st.success("עודכן!")
        else:
            st.error("לא ניתן לטעון שערים")

    cols = st.columns(len(fx.POPULAR_PAIRS))
    for col, (base, target, label) in zip(cols, fx.POPULAR_PAIRS):
        hist = fx.get_rate_history(base, target, limit=2)
        if hist:
            current = hist[0]["rate"]
            prev = hist[1]["rate"] if len(hist) > 1 else current
            delta = ((current - prev) / prev * 100) if prev else 0
            col.metric(label, f"{current:.4f}", f"{delta:+.2f}%")
        else:
            col.metric(label, "—")

    st.divider()

    # Rate alert
    st.subheader("🔔 הוסף התראת שער")
    with st.form("rate_alert_form"):
        ra_c1, ra_c2, ra_c3, ra_c4 = st.columns(4)
        with ra_c1:
            ra_base = st.text_input("מטבע בסיס", value="USD")
        with ra_c2:
            ra_target = st.text_input("מטבע יעד", value="ILS")
        with ra_c3:
            ra_threshold = st.number_input("ספסף", value=3.50, step=0.01, format="%.4f")
        with ra_c4:
            ra_dir = st.selectbox("כיוון", ["below", "above"],
                                  format_func=lambda x: "מתחת ל" if x == "below" else "מעל ל")
        if st.form_submit_button("➕ הוסף התראה"):
            fx.add_rate_alert(ra_base, ra_target, ra_threshold, ra_dir)
            st.success(f"✅ התראה נוספה: {ra_base}/{ra_target} {ra_dir} {ra_threshold}")

    # Rate history chart for USD/ILS
    hist = fx.get_rate_history("USD", "ILS", limit=30)
    if len(hist) >= 2:
        hist_rev = list(reversed(hist))
        fig = go.Figure(go.Scatter(
            x=[r["checked_at"][:16] for r in hist_rev],
            y=[r["rate"] for r in hist_rev],
            mode="lines+markers",
            line=dict(color="#667eea", width=2),
            fill="tozeroy", fillcolor="rgba(102,126,234,0.1)",
        ))
        fig.update_layout(
            title="USD/ILS — היסטוריה",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
            font=dict(color="#ccc"), height=250,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Export
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📥 ייצוא נתונים":
    st.title("📥 ייצוא נתונים")

    items = db.get_all_watch_items(enabled_only=False)
    if not items:
        st.info("אין נתונים לייצוא.")
    else:
        st.subheader("📊 ייצוא Excel — כל הפריטים")
        st.caption("קובץ Excel מעוצב עם גרפים ו-color coding לפי מחיר")
        if st.button("📊 הורד Excel", use_container_width=True):
            with st.spinner("יוצר קובץ Excel..."):
                xlsx_bytes = exporters.export_excel()
            st.download_button(
                label="⬇️ הורד MegaTraveller.xlsx",
                data=xlsx_bytes,
                file_name=f"MegaTraveller_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.divider()
        st.subheader("📄 ייצוא CSV — פריט יחיד")
        item_names = {f"{i['name']} ({i['destination']})": i for i in items}
        sel = st.selectbox("בחר פריט", list(item_names.keys()))
        item = item_names[sel]

        csv_str = exporters.export_csv(item["id"])
        st.download_button(
            label="⬇️ הורד CSV",
            data=csv_str.encode("utf-8-sig"),
            file_name=f"{item['name']}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Multi-City Route Optimizer
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🌍 מסלול מרובה ערים":
    st.title("🌍 מטב מסלול מרובה ערים")
    st.caption("מה הסדר הזול ביותר לביקור בכמה ערים? Claude מחשב את כל הקומבינציות.")

    with st.form("multicity_form"):
        c1, c2 = st.columns(2)
        with c1:
            mc_origin = st.text_input("עיר מוצא", value="תל אביב (TLV)")
            mc_cities_raw = st.text_area(
                "ערים לביקור (שורה לכל עיר)",
                placeholder="טוקיו\nבנגקוק\nבאלי\nסינגפור",
                height=120,
            )
            mc_start = st.date_input("תאריך יציאה")
        with c2:
            mc_budget = st.number_input("תקציב כולל ($)", value=5000, step=500)
            mc_days_raw = st.text_area(
                "ימים בכל עיר (שורה לכל עיר, לפי סדר למעלה)",
                placeholder="3\n4\n4\n3",
                height=120,
            )
        mc_submit = st.form_submit_button("🔍 מצא מסלול זול ביותר", use_container_width=True)

    if mc_submit and mc_cities_raw.strip():
        cities = [c.strip() for c in mc_cities_raw.strip().splitlines() if c.strip()]
        days_list = [d.strip() for d in mc_days_raw.strip().splitlines() if d.strip()]
        days_per_city = {}
        for i, city in enumerate(cities):
            try:
                days_per_city[city] = int(days_list[i])
            except (IndexError, ValueError):
                days_per_city[city] = 3

        st.info(f"מחשב {len(cities)} ערים: {' → '.join(cities)}")

        with st.spinner("Claude מחשב את כל הקומבינציות האפשריות..."):
            result = cost_calculator.optimize_multi_city(
                cities=cities,
                origin=mc_origin,
                start_date=str(mc_start),
                days_per_city=days_per_city,
                budget=mc_budget,
            )

        if "error" in result:
            st.error(result["error"])
        else:
            # Winner
            optimal = result.get("optimal_order", cities)
            opt_price = result.get("optimal_price", 0)
            savings = result.get("savings_vs_worst", 0)

            st.success(f"✅ הסדר האופטימלי חוסך **${savings:,}** לעומת הגרוע ביותר!")

            st.markdown(
                f"### 🏆 הסדר המומלץ: "
                + " → ".join(f"**{c}**" for c in optimal)
                + f"  |  ${opt_price:,}"
            )

            # Compare all orders
            comparisons = result.get("direct_comparison", [])
            if comparisons:
                st.subheader("📊 השוואת סדרים")
                for i, comp in enumerate(comparisons):
                    color = "#00ff88" if i == 0 else "#667eea"
                    order_str = " → ".join(comp.get("order", []))
                    price = comp.get("price", 0)
                    notes = comp.get("notes", "")
                    st.markdown(
                        f"<div style='background:rgba(255,255,255,0.05);padding:10px;"
                        f"border-radius:8px;margin:4px 0;border-left:3px solid {color}'>"
                        f"{'🏆' if i==0 else str(i+1)+'.'} <b>{order_str}</b> — "
                        f"<span style='color:{color}'>${price:,}</span>"
                        + (f"<br><small style='color:#aaa'>{notes}</small>" if notes else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )

            # Open-jaw option
            oj = result.get("open_jaw_option", {})
            if oj and oj.get("price"):
                st.divider()
                st.subheader("✈️ אפשרות Open-Jaw")
                c1, c2 = st.columns(2)
                c1.info(f"**{oj.get('description','')}**\n\n${oj.get('price',0):,}")
                if oj.get("saves", 0) > 0:
                    c2.success(f"חוסך **${oj['saves']:,}** לעומת Round-Trip")

            # Flight legs
            legs = result.get("flight_legs", [])
            if legs:
                st.divider()
                st.subheader("🗓️ רגלי הטיסה")
                cols = st.columns(len(legs))
                for col, leg in zip(cols, legs):
                    col.metric(
                        f"{leg.get('from','')} → {leg.get('to','')}",
                        f"${leg.get('price',0):,}",
                        leg.get("airline", ""),
                    )

            # Strategy
            if result.get("booking_strategy"):
                st.divider()
                st.info(f"📌 **אסטרטגיית הזמנה:** {result['booking_strategy']}")

            # Tips
            tips = result.get("tips", [])
            if tips:
                st.subheader("💡 טיפים")
                for tip in tips:
                    st.markdown(f"• {tip}")

            if result.get("hub_tip"):
                st.success(f"🔗 **Hub tip:** {result['hub_tip']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Stopover Finder
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔁 עצירות חינם":
    st.title("🔁 מצא עצירות חינם (Stopovers)")
    st.caption("Emirates → דובאי, Icelandair → רייקיאוויק, Turkish → איסטנבול. שני יעדים במחיר אחד!")

    with st.form("stopover_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            so_origin = st.text_input("מוצא", value="TLV")
        with c2:
            so_dest = st.text_input("יעד סופי *", placeholder="טוקיו, ניו-יורק...")
        with c3:
            so_days = st.slider("מקסימום ימי עצירה", 1, 7, 3)
        c4, c5 = st.columns(2)
        with c4:
            so_out = st.date_input("תאריך יציאה")
        with c5:
            so_ret = st.date_input("תאריך חזרה (אופציונלי)", value=None)
        so_submit = st.form_submit_button("🔍 מצא stopovers", use_container_width=True)

    if so_submit and so_dest:
        with st.spinner("מחפש stopovers אטרקטיביים..."):
            options = stopover_finder.find_stopovers(
                origin=so_origin,
                destination=so_dest,
                date_out=str(so_out),
                date_return=str(so_ret) if so_ret else "",
                max_stopover_days=so_days,
            )

        if not options or "error" in (options[0] if options else {}):
            st.warning("לא נמצאו stopovers. נסה יעד אחר.")
        else:
            st.success(f"נמצאו {len(options)} אפשרויות stopover!")

            for opt in options:
                score = stopover_finder.get_stopover_value_score(opt)
                is_free = opt.get("is_free_stopover", False)
                color = "#00ff88" if is_free else "#667eea"
                badge = "🆓 FREE STOPOVER" if is_free else "💰 תוספת מחיר"
                savings = opt.get("savings_vs_direct", 0) or 0
                extra = opt.get("extra_cost_vs_direct", 0) or 0

                price_delta = savings if savings > 0 else -extra
                delta_text = (
                    f"חוסך **${savings:,}**" if savings > 0
                    else (f"תוספת ${extra:,}" if extra > 0 else "אותו מחיר")
                )

                with st.container():
                    st.markdown(
                        f"<div style='background:rgba(255,255,255,0.06);border-radius:12px;"
                        f"padding:16px;margin:8px 0;border-left:4px solid {color}'>",
                        unsafe_allow_html=True,
                    )
                    hc1, hc2, hc3 = st.columns([3, 2, 1])
                    with hc1:
                        st.markdown(
                            f"### ✈️ {opt.get('airline','')} — {opt.get('stopover_city','')}"
                        )
                        st.markdown(f"**{badge}** | {delta_text} | {so_origin}→{opt.get('stopover_code','')}→{so_dest}")
                    with hc2:
                        st.metric(
                            "מחיר עם Stopover",
                            f"${opt.get('price_with_stopover',0):,}",
                            f"vs ישיר ${opt.get('price_direct',0):,}",
                        )
                    with hc3:
                        st.metric("ניקוד ערך", f"{score:.1f}/10")
                    st.markdown("</div>", unsafe_allow_html=True)

                highlights = opt.get("stopover_highlights", [])
                if highlights:
                    st.markdown("**🌟 מה לעשות ב" + opt.get('stopover_city','') + ":** " + " | ".join(highlights))

                cols_info = st.columns(3)
                cols_info[0].caption(f"⏱ {opt.get('stopover_days_min',0)}-{opt.get('stopover_days_max',3)} ימי עצירה")
                cols_info[1].caption(f"👥 מתאים ל: {opt.get('best_for','')}")
                visa_icon = "❌ נדרשת ויזה" if opt.get("visa_needed") else "✅ ללא ויזה"
                cols_info[2].caption(visa_icon)

                if opt.get("tip"):
                    st.info(f"💡 {opt['tip']}")
                if opt.get("booking_url"):
                    st.link_button(f"🔗 הזמן עכשיו", opt["booking_url"])
                st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: True Cost Calculator
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💰 עלות אמיתית":
    st.title("💰 מחשבון עלות אמיתית")
    st.caption("Ryanair ב-€49 עם מטען = לפעמים יקר יותר מ-El Al. תראה את המחיר האמיתי.")

    tab1, tab2 = st.tabs(["🧳 עלות אמיתית", "💳 נקודות vs מזומן"])

    with tab1:
        with st.form("truecost_form"):
            c1, c2 = st.columns(2)
            with c1:
                tc_price = st.number_input("מחיר בסיס ($)", value=200, step=10)
                tc_airline = st.selectbox("חברת תעופה", [
                    "El Al", "Israir", "Arkia", "Ryanair", "Wizz Air",
                    "easyJet", "Lufthansa", "KLM", "TurkishAirlines", "אחר",
                ])
                tc_bags = st.number_input("מספר מזוודות", value=1, min_value=0, max_value=5)
                tc_bag_weight = st.selectbox("משקל מזוודה", ["10kg", "15kg", "20kg", "23kg", "32kg"])
            with c2:
                tc_meals = st.checkbox("צריך לקנות ארוחות?", value=False)
                tc_insurance = st.checkbox("ביטוח נסיעות", value=True)
                tc_nights = st.number_input("מספר לילות", value=7, min_value=1)
                tc_travelers = st.number_input("מספר נוסעים", value=2, min_value=1)
                tc_origin_airport = st.selectbox("שדה תעופה מוצא", ["TLV", "אחר"])
                tc_transport = st.selectbox("הגעה לנמל תעופה", ["taxi", "bus", "shuttle", "train"])

            tc_submit = st.form_submit_button("💰 חשב עלות אמיתית", use_container_width=True)

        if tc_submit:
            result = cost_calculator.calculate_true_cost(
                base_price=tc_price,
                airline=tc_airline,
                checked_bags=tc_bags,
                bag_weight=tc_bag_weight,
                needs_meals=tc_meals,
                origin_airport=tc_origin_airport,
                transport_mode_origin=tc_transport,
                travel_insurance=tc_insurance,
                travelers=tc_travelers,
                nights=tc_nights,
            )
            bd = result["breakdown"]
            total = result["total"]
            hidden = result["hidden_fees"]
            hidden_pct = hidden / total * 100 if total else 0

            # Summary
            col1, col2, col3 = st.columns(3)
            col1.metric("💰 עלות אמיתית", f"${total:,.0f}")
            col2.metric("👤 לאדם", f"${result['per_person']:,.0f}")
            col3.metric("🙈 עמלות נסתרות", f"${hidden:,.0f}", f"{hidden_pct:.0f}% מהסכום")

            if hidden_pct > 30:
                st.warning(f"⚠️ {hidden_pct:.0f}% מהמחיר הוא עמלות נסתרות! מחיר הבסיס מטעה.")
            elif hidden_pct > 15:
                st.info(f"ℹ️ {hidden_pct:.0f}% עמלות נוספות על מחיר הבסיס.")
            else:
                st.success(f"✅ מחיר הבסיס מייצג היטב — רק {hidden_pct:.0f}% תוספות.")

            # Breakdown chart
            labels = {
                "base_flight": "✈️ טיסה",
                "baggage": "🧳 מטען",
                "meals": "🍽️ ארוחות",
                "transport_origin": "🚗 הסעה לנמל",
                "transport_destination": "🚕 הסעה ביעד",
                "insurance": "🛡️ ביטוח",
                "seat_selection": "💺 בחירת מושב",
            }
            fig = go.Figure(go.Bar(
                x=[labels.get(k, k) for k, v in bd.items() if v > 0],
                y=[v for v in bd.values() if v > 0],
                marker_color=["#667eea" if k == "base_flight" else "#ff6b6b"
                               for k, v in bd.items() if v > 0],
                text=[f"${v:,.0f}" for v in bd.values() if v > 0],
                textposition="outside",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                font=dict(color="#ccc"), height=300,
                margin=dict(l=10, r=10, t=20, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("💳 האם לממש נקודות?")
        with st.form("points_form"):
            p1, p2, p3 = st.columns(3)
            with p1:
                pt_program = st.selectbox("תוכנית נאמנות", list(cost_calculator.POINTS_VALUES.keys()))
            with p2:
                pt_points = st.number_input("כמות נקודות", value=50000, step=1000)
            with p3:
                pt_cash = st.number_input("מחיר במזומן ($)", value=500, step=50)
            pt_submit = st.form_submit_button("🔍 חשב", use_container_width=True)

        if pt_submit:
            res = cost_calculator.calculate_points_value(
                points=pt_points,
                program=pt_program,
                redemption_cash_value=pt_cash,
            )
            col1, col2, col3 = st.columns(3)
            col1.metric("ערך הנקודות", f"${res['cash_value_usd']:,.0f}")
            col2.metric("מחיר מזומן", f"${res['redemption_value_usd']:,.0f}")
            ratio = res["ratio_pct"]
            delta_val = res["cash_value_usd"] - res["redemption_value_usd"]
            col3.metric("יחס", f"{ratio:.0f}%", f"{delta_val:+.0f}$")

            if ratio >= 120:
                st.success(f"🔥 {res['recommendation']}")
            elif ratio >= 100:
                st.success(f"✅ {res['recommendation']}")
            elif ratio >= 80:
                st.warning(f"🟡 {res['recommendation']}")
            else:
                st.error(f"❌ {res['recommendation']}")

            # Gauge
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=ratio,
                number={"suffix": "%"},
                gauge={
                    "axis": {"range": [0, 200]},
                    "bar": {"color": "#667eea"},
                    "steps": [
                        {"range": [0, 80], "color": "rgba(255,75,75,0.3)"},
                        {"range": [80, 100], "color": "rgba(255,200,0,0.3)"},
                        {"range": [100, 200], "color": "rgba(0,255,136,0.3)"},
                    ],
                    "threshold": {"line": {"color": "#fff", "width": 2}, "value": 100},
                },
                title={"text": "ערך הנקודות vs מזומן"},
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#ccc"), height=250,
                margin=dict(l=30, r=30, t=40, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("🔍 מצא את המימוש הכי טוב לנקודות שלך")
        with st.form("best_redeem_form"):
            br_program = st.selectbox("תוכנית", list(cost_calculator.POINTS_VALUES.keys()), key="br_prog")
            br_points = st.number_input("נקודות", value=100000, step=5000, key="br_pts")
            br_submit = st.form_submit_button("🤖 מצא הזדמנויות מימוש", use_container_width=True)

        if br_submit:
            with st.spinner("Claude מחפש את הדרכים הכי משתלמות..."):
                res = cost_calculator.find_best_redemption(br_points, br_program)

            options = res.get("options", [])
            if options:
                for opt in options:
                    cpp = opt.get("cpp_value", 0)
                    color = "#00ff88" if cpp >= 1.5 else "#ffcc00"
                    st.markdown(
                        f"<div style='background:rgba(255,255,255,0.06);padding:12px;"
                        f"border-radius:8px;margin:6px 0;border-left:3px solid {color}'>"
                        f"<b>{opt.get('redemption_type','')}: {opt.get('description','')}</b><br>"
                        f"💰 ערך: <span style='color:{color}'>{cpp:.1f}¢/נקודה</span> | "
                        f"${opt.get('total_value_usd',0):,} | {opt.get('difficulty','')}<br>"
                        f"📋 {opt.get('how_to','')}"
                        + (f"<br>💡 {opt['tip']}" if opt.get('tip') else "")
                        + "</div>",
                        unsafe_allow_html=True,
                    )
            elif "error" in res:
                st.error(res["error"])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Deal Insights & Patterns
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 תובנות ודפוסים":
    st.title("📊 תובנות ודפוסים מהדאטה שלך")
    st.caption("מה ה-DB לימד אותנו — מתי יוצאים דילים, לאיזה יעדים, ומה הזמן הכי טוב לסרוק.")

    patterns = deal_insights.get_deal_patterns()

    if patterns.get("empty"):
        st.info(patterns["message"])
        st.stop()

    # Header metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("סה״כ דילים נצפו", patterns["total_deals"])
    col2.metric("ניקוד ממוצע", f"{patterns['avg_score']:.1f}/10")
    if patterns.get("best_day"):
        col3.metric("יום הדילים הכי טוב", patterns["best_day"]["name"])
    if patterns.get("best_hour") is not None:
        col4.metric("שעה הכי טובה לסרוק", f"{patterns['best_hour']:02d}:00")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📅 תזמון", "✈️ יעדים וחברות", "🤖 ניתוח AI"])

    with tab1:
        # Day of week chart
        day_scores = patterns.get("day_scores", {})
        if day_scores:
            st.subheader("📅 איכות דילים לפי יום בשבוע")
            fig = go.Figure(go.Bar(
                x=list(day_scores.keys()),
                y=list(day_scores.values()),
                marker_color=[
                    "#00ff88" if v == max(day_scores.values()) else "#667eea"
                    for v in day_scores.values()
                ],
                text=[f"{v:.1f}" for v in day_scores.values()],
                textposition="outside",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                font=dict(color="#ccc"), height=300,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

            if patterns.get("best_day") and patterns.get("worst_day"):
                c1, c2 = st.columns(2)
                c1.success(
                    f"✅ **הכי טוב:** יום {patterns['best_day']['name']} "
                    f"(ניקוד {patterns['best_day']['avg_score']})"
                )
                c2.error(
                    f"❌ **הכי גרוע:** יום {patterns['worst_day']['name']} "
                    f"(ניקוד {patterns['worst_day']['avg_score']})"
                )

        # Hour chart
        hour_scores = patterns.get("hour_scores", {})
        if hour_scores:
            st.subheader("⏰ איכות דילים לפי שעה")
            fig2 = go.Figure(go.Scatter(
                x=list(hour_scores.keys()),
                y=list(hour_scores.values()),
                mode="lines+markers",
                line=dict(color="#667eea", width=2),
                fill="tozeroy",
                fillcolor="rgba(102,126,234,0.15)",
            ))
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                font=dict(color="#ccc"), height=250,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        # Top destinations
        top_dest = patterns.get("top_destinations", [])
        if top_dest:
            st.subheader("✈️ יעדים עם הכי הרבה דילים")
            fig3 = go.Figure(go.Bar(
                x=[d["destination"] for d in top_dest],
                y=[d["cnt"] for d in top_dest],
                marker_color="#764ba2",
                text=[f"{d['cnt']}\n${d.get('avg_price',0):.0f}" for d in top_dest],
                textposition="outside",
            ))
            fig3.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                font=dict(color="#ccc"), height=280,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig3, use_container_width=True)

        # Deal types
        deal_types = patterns.get("deal_types", {})
        if deal_types:
            st.subheader("🏷️ סוגי דילים")
            type_labels = {
                "error_fare": "💎 שגיאת מחיר",
                "flash_sale": "⚡ מכירת פלאש",
                "promo": "🏷️ מבצע",
                "regular_cheap": "💰 זול",
            }
            fig4 = go.Figure(go.Pie(
                labels=[type_labels.get(k, k) for k in deal_types],
                values=list(deal_types.values()),
                hole=0.4,
                marker=dict(colors=["#00ff88", "#ffcc00", "#667eea", "#ff6b6b"]),
            ))
            fig4.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#ccc"), height=250,
                margin=dict(l=10, r=10, t=10, b=10),
            )
            st.plotly_chart(fig4, use_container_width=True)

        # Top airlines
        top_air = patterns.get("top_airlines", [])
        if top_air:
            st.subheader("✈️ חברות תעופה")
            for a in top_air:
                st.markdown(f"• **{a['airline']}** — {a['cnt']} דילים | ממוצע ${a.get('avg_price',0):.0f}")

    with tab3:
        st.subheader("🤖 ניתוח AI — מה ה-DB מלמד אותנו?")
        if st.button("🤖 ניתח עם Claude", use_container_width=True):
            with st.spinner("Claude מנתח את הדאטה שלך..."):
                ai = deal_insights.get_ai_insights()

            if "error" in ai:
                st.error(ai["error"])
            else:
                if ai.get("key_patterns"):
                    st.subheader("🔍 דפוסים מרכזיים")
                    for p in ai["key_patterns"]:
                        st.markdown(f"• {p}")

                if ai.get("strategy"):
                    st.subheader("🎯 אסטרטגיה מומלצת")
                    st.info(ai["strategy"])

                if ai.get("add_to_watchlist"):
                    st.subheader("📌 כדאי להוסיף לרשימת המעקב")
                    cols = st.columns(len(ai["add_to_watchlist"]))
                    for col, dest in zip(cols, ai["add_to_watchlist"]):
                        col.success(f"✈️ {dest}")

                if ai.get("action_items"):
                    st.subheader("✅ פעולות מומלצות")
                    for act in ai["action_items"]:
                        st.markdown(f"• {act}")

                if ai.get("savings_potential"):
                    st.metric("💰 פוטנציאל חיסכון", ai["savings_potential"])

        # Recent top deals from DB
        recent = patterns.get("recent_top", [])
        if recent:
            st.divider()
            st.subheader("🏆 הדילים הכי טובים שנצפו")
            for d in recent:
                score = d.get("score", 0)
                score_bar = "🟩" * int(score / 2) + "⬜" * (5 - int(score / 2))
                st.markdown(
                    f"**{d.get('destination','')}** | ${d.get('price',0):,} | "
                    f"{d.get('airline','')} | {d.get('deal_type','')} | "
                    f"{score_bar} {score:.1f}"
                )
                if d.get("why_amazing"):
                    st.caption(d["why_amazing"])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Telegram Bot
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🤖 בוט טלגרם":
    st.title("🤖 הגדרת בוט Telegram")
    st.caption("קבל התראות חכמות ישירות ל-Telegram — דילים, ירידות מחיר, שביתות, דילים שפגים.")

    # Current status
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    if tg_token and tg_chat:
        st.success(f"✅ בוט מחובר | Chat ID: {tg_chat}")
        bot_info = telegram_bot.get_bot_info(tg_token)
        if bot_info.get("ok"):
            bname = bot_info["result"].get("username", "")
            st.caption(f"Bot: @{bname}")
    else:
        st.warning("⚠️ בוט לא מוגדר — הגדר token ו-chat_id למטה")

    st.divider()

    # Setup guide
    with st.expander("📖 איך מגדירים בוט Telegram? (3 שלבים)", expanded=not bool(tg_token)):
        st.markdown("""
**שלב 1 — צור בוט:**
1. פתח Telegram וחפש `@BotFather`
2. שלח `/newbot`
3. בחר שם ו-username לבוט
4. קבל את ה-**Bot Token** (נראה כך: `123456:ABC-DEF...`)

**שלב 2 — מצא את ה-Chat ID שלך:**
1. שלח הודעה לבוט שיצרת
2. לחץ "קבל Chat ID" למטה — המערכת תמצא אותו אוטומטית

**שלב 3 — שמור ובדוק:**
1. הכנס Token ו-Chat ID למטה
2. לחץ "בדוק חיבור"
3. אם הכל תקין — תקבל הודעת אישור ב-Telegram!
        """)

    st.divider()

    # Configuration
    with st.form("tg_config_form"):
        new_token = st.text_input(
            "Bot Token",
            value=tg_token,
            type="password",
            placeholder="123456789:ABCdefGHI...",
        )
        new_chat = st.text_input(
            "Chat ID",
            value=tg_chat,
            placeholder="-100123456789",
        )
        c1, c2 = st.columns(2)
        save_btn = c1.form_submit_button("💾 שמור", use_container_width=True)
        test_btn = c2.form_submit_button("📨 בדוק חיבור", use_container_width=True)

    if save_btn and new_token and new_chat:
        _save_env("TELEGRAM_BOT_TOKEN", new_token)
        _save_env("TELEGRAM_CHAT_ID", new_chat)
        st.success("✅ נשמר! הפעל מחדש את האפליקציה להפעלת השינויים.")

    if test_btn and new_token and new_chat:
        with st.spinner("שולח הודעת בדיקה..."):
            res = telegram_bot.test_connection(new_token, new_chat)
        if res.get("ok"):
            st.success("✅ הודעת בדיקה נשלחה! בדוק את Telegram.")
        else:
            st.error(f"❌ שגיאה: {res.get('error', 'לא ידוע')}")

    st.divider()

    # Auto-detect chat ID
    if tg_token:
        st.subheader("🔍 זיהוי אוטומטי של Chat ID")
        st.caption("שלח הודעה לבוט שלך ב-Telegram, ואז לחץ כאן למציאת ה-ID שלך.")
        if st.button("🔍 קבל Chat ID", use_container_width=True):
            updates = telegram_bot.get_updates(tg_token)
            found_id = telegram_bot.extract_chat_id(updates)
            if found_id:
                st.success(f"✅ Chat ID שלך: **{found_id}**")
                st.code(found_id)
            else:
                st.warning("לא נמצאו הודעות. ודא ששלחת הודעה לבוט תחילה.")

    st.divider()

    # Alert settings
    st.subheader("⚙️ הגדרות התראות")
    st.caption("בחר אילו התראות לקבל ב-Telegram")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**✈️ מחירים**")
        st.checkbox("ירידת מחיר בטיסות", value=True, key="tg_price_drop")
        st.checkbox("מחיר נמוך היסטורי", value=True, key="tg_price_low")
        st.checkbox("עלייה חדה במחיר", value=False, key="tg_price_rise")
    with col2:
        st.markdown("**🔥 דילים**")
        st.checkbox("דיל חדש (ציד דילים)", value=True, key="tg_new_deal")
        st.checkbox("דיל עומד לפוג", value=True, key="tg_expiry")
        st.checkbox("שגיאת מחיר", value=True, key="tg_error_fare")

    st.divider()

    # Send test deal
    st.subheader("📨 שלח התראה ידנית")
    with st.form("tg_manual_form"):
        msg_text = st.text_area("הודעה", placeholder="כתוב הודעה לשלוח לבוט...", height=80)
        manual_submit = st.form_submit_button("📨 שלח עכשיו")

    if manual_submit and msg_text and tg_token and tg_chat:
        res = telegram_bot.send_message(tg_token, tg_chat, msg_text)
        if res.get("ok"):
            st.success("✅ נשלח!")
        else:
            st.error(f"❌ {res.get('error','שגיאה')}")
