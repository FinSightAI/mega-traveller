"""
Noded 🌍 - Web UI (Streamlit)
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

load_dotenv(Path(__file__).parent / ".env")

# Load Streamlit Cloud secrets into env vars
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str) and _k not in os.environ:
            os.environ[_k] = _v
except Exception:
    pass

import translations as i18n

import database as db
import agent
import ai_client
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
import kiwi_client
import validators
import nl_parser
import weekly_digest
import events_finder
import hidden_city
import rss_scanner
import auto_book
import price_dna
import positioning
import whatsapp_bot

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Noded 🧳",
    page_icon="🧳",
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

# ── PWA (installable on Android / iPhone / Desktop) ───────────────────────────

def _inject_pwa():
    components.html("""
<script>
(function() {
  var doc = window.parent.document;
  if (doc.querySelector('link[rel="manifest"]')) return;

  // Manifest — makes app installable
  var manifest = {
    "name": "Noded — מעקב מחירי טיול",
    "short_name": "Noded",
    "description": "מעקב חכם אחר מחירי טיסות ומלונות",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0e1117",
    "theme_color": "#667eea",
    "orientation": "any",
    "icons": [
      {
        "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'%3E%3Crect width='192' height='192' rx='32' fill='%23667eea'/%3E%3Ctext x='96' y='130' font-size='110' text-anchor='middle'%3E%F0%9F%A7%B3%3C/text%3E%3C/svg%3E",
        "sizes": "192x192",
        "type": "image/svg+xml",
        "purpose": "any maskable"
      },
      {
        "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'%3E%3Crect width='512' height='512' rx='80' fill='%23667eea'/%3E%3Ctext x='256' y='360' font-size='300' text-anchor='middle'%3E%F0%9F%A7%B3%3C/text%3E%3C/svg%3E",
        "sizes": "512x512",
        "type": "image/svg+xml",
        "purpose": "any maskable"
      }
    ]
  };

  var blob = new Blob([JSON.stringify(manifest)], {type: 'application/manifest+json'});
  var url  = URL.createObjectURL(blob);
  var link = doc.createElement('link');
  link.rel  = 'manifest';
  link.href = url;
  doc.head.appendChild(link);

  // iOS / Android meta tags
  [
    ['mobile-web-app-capable',          'yes'],
    ['apple-mobile-web-app-capable',    'yes'],
    ['apple-mobile-web-app-title',      'Noded'],
    ['apple-mobile-web-app-status-bar-style', 'black-translucent'],
    ['theme-color',                     '#667eea'],
    ['application-name',                'Noded'],
  ].forEach(function(pair) {
    if (!doc.querySelector('meta[name="' + pair[0] + '"]')) {
      var m = doc.createElement('meta');
      m.name = pair[0]; m.content = pair[1];
      doc.head.appendChild(m);
    }
  });

  // Request browser notification permission
  if ('Notification' in window.parent) {
    if (window.parent.Notification.permission === 'default') {
      // Show subtle permission banner after 3 seconds
      setTimeout(function() {
        if (window.parent.Notification.permission === 'default') {
          window.parent.Notification.requestPermission();
        }
      }, 3000);
    }
  }

  // Expose global helper so Streamlit custom components can trigger notifications
  window.parent.nodedNotify = function(title, body, icon) {
    if (window.parent.Notification && window.parent.Notification.permission === 'granted') {
      new window.parent.Notification(title, {
        body: body || '',
        icon: icon || 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">✈️</text></svg>',
        badge: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🔔</text></svg>',
        tag: 'noded-alert',
        requireInteraction: false,
      });
    }
  };
})();
</script>
""", height=0)

# ── Custom CSS (injected after lang is known) ──────────────────────────────────
def _inject_css(rtl: bool):
    d = "rtl" if rtl else "ltr"
    ta = "right" if rtl else "left"

    sidebar_pos = """
      section[data-testid="stSidebar"] {
        right: 0 !important;
        left: unset !important;
        transition: transform 0.3s ease-in-out, width 0.3s ease-in-out !important;
        overflow: hidden !important;       /* outer: clip during collapse animation */
      }
      section[data-testid="stSidebar"] > div:first-child,
      section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
      section[data-testid="stSidebar"] .stSidebarContent {{
        border-left: 1px solid rgba(102,126,234,0.2) !important;
        border-right: none !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        max-height: 100vh !important;
      }}
      /* Scrollbar inside sidebar */
      section[data-testid="stSidebar"] *::-webkit-scrollbar,
      section[data-testid="stSidebar"] > div:first-child::-webkit-scrollbar {{
        width: 4px !important;
      }}
      section[data-testid="stSidebar"] *::-webkit-scrollbar-thumb,
      section[data-testid="stSidebar"] > div:first-child::-webkit-scrollbar-thumb {{
        background: rgba(102,126,234,0.35) !important;
        border-radius: 3px !important;
      }}
      /* Collapsed state: ensure sidebar is fully off-screen to the right */
      [data-testid="stSidebarCollapsedControl"] ~ section[data-testid="stSidebar"],
      section[data-testid="stSidebar"][class*="collapsed"],
      section[data-testid="stSidebar"][aria-expanded="false"] {
        transform: translateX(110%) !important;
      }
    """ if rtl else ""

    st.markdown(f"""
<style>
  /* ── Direction ── */
  html, body {{ direction: {d} !important; }}
  [data-testid="stAppViewContainer"],
  [data-testid="stAppViewBlockContainer"],
  [data-testid="stVerticalBlock"],
  .block-container {{ overflow: visible !important; }}

  p, h1, h2, h3, h4, h5, h6,
  li, td, th, caption, label, span, small, strong, em, b, i,
  div, section, article, aside, header, footer,
  input, textarea, select,
  [data-testid], [data-baseweb],
  .stMarkdown, .stText, .stAlert,
  .element-container, .block-container {{
    text-align: {ta} !important;
  }}

  [data-testid="stMetricValue"],
  [data-testid="stMetricLabel"],
  [data-testid="stMetricDelta"],
  [data-testid="stMetric"],
  button, [data-testid="stButton"] > button,
  .metric-card,
  [data-testid="stImage"],
  [data-testid="stPlotlyChart"],
  [data-testid="stDataFrame"] {{
    text-align: center !important;
  }}

  [data-testid="stSidebar"],
  [data-testid="stSidebar"] * {{
    direction: {d} !important;
    text-align: {ta} !important;
  }}

  {sidebar_pos}

  input, textarea, select {{
    direction: {d} !important;
    text-align: {ta} !important;
  }}
  input::placeholder, textarea::placeholder {{
    text-align: {ta} !important;
  }}

  /* ── Aurora background ── */
  [data-testid="stAppViewContainer"] {{
    background: linear-gradient(135deg, #0a0a1a 0%, #0d1b2e 40%, #1a0a2e 70%, #0a1a1a 100%) !important;
  }}
  [data-testid="stAppViewContainer"]::before {{
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
      radial-gradient(ellipse at 20% 50%, rgba(102,126,234,0.07) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 20%, rgba(118,75,162,0.07) 0%, transparent 60%),
      radial-gradient(ellipse at 60% 80%, rgba(0,200,150,0.04) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
  }}

  /* ── Sidebar glass ── */
  [data-testid="stSidebar"] {{
    background: rgba(10,10,30,0.88) !important;
    backdrop-filter: blur(20px) !important;
    border-right: 1px solid rgba(102,126,234,0.2) !important;
  }}

  /* ── Expanders → glass cards ── */
  [data-testid="stExpander"] {{
    background: rgba(255,255,255,0.04) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    border-radius: 16px !important;
    margin-bottom: 10px !important;
    transition: border-color 0.3s, box-shadow 0.3s !important;
  }}
  [data-testid="stExpander"]:hover {{
    border-color: rgba(102,126,234,0.35) !important;
    box-shadow: 0 8px 32px rgba(102,126,234,0.12) !important;
  }}

  /* ── Metrics glass ── */
  [data-testid="stMetric"] {{
    background: rgba(255,255,255,0.04) !important;
    backdrop-filter: blur(10px) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    padding: 12px 16px !important;
    transition: transform 0.2s, box-shadow 0.2s !important;
  }}
  [data-testid="stMetric"]:hover {{
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 20px rgba(102,126,234,0.18) !important;
  }}
  [data-testid="stMetricValue"] {{
    color: #a78bfa !important;
    font-size: 1.8rem !important;
    font-weight: 700 !important;
  }}

  /* ── Buttons ── */
  .stButton button {{
    background: linear-gradient(135deg, #667eea, #764ba2) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: opacity 0.2s, transform 0.15s, box-shadow 0.2s !important;
    box-shadow: 0 4px 15px rgba(102,126,234,0.28) !important;
  }}
  .stButton button:hover {{
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(102,126,234,0.42) !important;
  }}
  .stButton button:active {{
    transform: translateY(0) !important;
  }}

  /* ── Inputs glass ── */
  [data-testid="stTextInput"] input,
  [data-testid="stNumberInput"] input,
  [data-testid="stTextArea"] textarea {{
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    color: white !important;
  }}
  [data-testid="stTextInput"] input:focus,
  [data-testid="stTextArea"] textarea:focus {{
    border-color: rgba(102,126,234,0.6) !important;
    box-shadow: 0 0 0 2px rgba(102,126,234,0.18) !important;
  }}

  /* ── Progress bar gradient ── */
  [data-testid="stProgressBar"] > div > div {{
    background: linear-gradient(90deg, #667eea, #00ff88) !important;
    border-radius: 4px !important;
  }}

  /* ── Price drop pulse animation ── */
  @keyframes priceDrop {{
    0%   {{ box-shadow: 0 0 0 0 rgba(0,255,136,0.5); }}
    70%  {{ box-shadow: 0 0 0 10px rgba(0,255,136,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(0,255,136,0); }}
  }}
  .price-drop-pulse {{ animation: priceDrop 1.5s ease-out 3; border-radius: 8px; }}

  /* ── Divider ── */
  hr {{ border-color: rgba(255,255,255,0.07) !important; }}

  /* ── Typography ── */
  h1 {{ color: white !important; font-weight: 700 !important; }}
  h2 {{ color: #e2d9f3 !important; font-weight: 600 !important; }}
  h3 {{ color: #c4b5fd !important; }}

  /* ── Alert boxes ── */
  [data-testid="stAlert"] {{
    background: rgba(255,255,255,0.04) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    backdrop-filter: blur(8px) !important;
  }}

  /* ── Scrollbar ── */
  ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
  ::-webkit-scrollbar-track {{ background: rgba(255,255,255,0.02); }}
  ::-webkit-scrollbar-thumb {{ background: rgba(102,126,234,0.4); border-radius: 3px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: rgba(102,126,234,0.65); }}

  /* ── Deal colors ── */
  .deal-excellent {{ color: #00ff88; font-weight: bold; }}
  .deal-good      {{ color: #88ff44; }}
  .deal-average   {{ color: #ffcc00; }}
  .deal-poor      {{ color: #ff4444; }}

  /* ── Alert box legacy ── */
  .alert-box {{
    background: rgba(255,75,75,0.12);
    border: 1px solid rgba(255,75,75,0.4);
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 8px;
  }}

  /* ── Chat messages ── */
  [data-testid="stChatMessage"] {{
    background: rgba(255,255,255,0.03) !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
  }}

  /* ── Hide Streamlit chrome ── */
  #MainMenu,
  .stMainMenu,
  [data-testid="stMainMenu"]             {{ display: none !important; }}

  /* Toolbar: Share / Manage app / Edit / star */
  [data-testid="stToolbar"],
  [data-testid="stAppToolbar"],
  [data-testid="stToolbarActions"],
  [data-testid="stHeader"] [data-testid="stToolbar"],
  header [data-testid="stToolbar"]       {{ display: none !important; }}

  /* Top header bar (contains the toolbar) */
  [data-testid="stHeader"]               {{ display: none !important; }}

  /* Footer / "Made with Streamlit" */
  footer,
  [data-testid="stBottom"]              {{ visibility: hidden !important; height: 0 !important; }}

  /* Deploy / status */
  [data-testid="stDeployButton"],
  .stDeployButton,
  [data-testid="stDecoration"],
  [data-testid="stStatusWidget"]        {{ display: none !important; }}
</style>
""", unsafe_allow_html=True)

    # RTL: flip sidebar collapse direction so it slides off to the RIGHT
    if rtl:
        components.html("""
<script>
(function() {
  if (window.parent.__sidebarRtlFixed) return;
  window.parent.__sidebarRtlFixed = true;

  function attachObserver() {
    var doc = window.parent.document;
    var sidebar = doc.querySelector('[data-testid="stSidebar"]');
    if (!sidebar) { setTimeout(attachObserver, 300); return; }

    var _skip = false;

    function fixTransform() {
      if (_skip) return;
      var t = sidebar.style.transform || '';
      if (!t) return;
      // Flip any negative translateX to positive (collapse to right, not left)
      var fixed = t.replace(/translateX\(\s*(-[\d.]+\s*(?:px|rem|%|vw)?)\s*\)/,
        function(_, v) { return 'translateX(' + v.replace('-', '') + ')'; }
      );
      if (fixed !== t) {
        _skip = true;
        sidebar.style.transform = fixed;
        // Also ensure overflow hidden so content doesn't bleed
        sidebar.style.overflow = 'hidden';
        setTimeout(function(){ _skip = false; }, 50);
      }
    }

    var obs = new MutationObserver(fixTransform);
    obs.observe(sidebar, { attributes: true, attributeFilter: ['style', 'class'] });

    // Also watch the inner container
    var inner = sidebar.querySelector('[data-testid="stSidebarContent"], div');
    if (inner) {
      obs.observe(inner, { attributes: true, attributeFilter: ['style'] });
    }

    fixTransform(); // run once immediately

    // ── Fix sidebar scroll (parent frame) ──────────────────────────────────
    function fixSidebarScroll() {
      var sb = doc.querySelector('[data-testid="stSidebar"]');
      if (!sb) return;
      // Allow scroll on every possible inner container
      [sb,
       sb.querySelector('[data-testid="stSidebarContent"]'),
       sb.querySelector('div'),
       sb.firstElementChild,
      ].forEach(function(el) {
        if (!el) return;
        el.style.setProperty('overflow-y', 'auto', 'important');
        el.style.setProperty('overflow-x', 'hidden', 'important');
        el.style.setProperty('max-height', '100vh', 'important');
      });
    }
    fixSidebarScroll();
    setTimeout(fixSidebarScroll, 1000);
  }

  // ── Hide Streamlit chrome from parent frame ────────────────────────────────
  function hideChrome() {
    var doc = window.parent.document;
    // Hide by data-testid / id / class
    var selectors = [
      '[data-testid="stHeader"]',
      '[data-testid="stToolbar"]',
      '[data-testid="stAppToolbar"]',
      '[data-testid="stToolbarActions"]',
      '[data-testid="stDeployButton"]',
      '[data-testid="stDecoration"]',
      '[data-testid="stStatusWidget"]',
      '[data-testid="stBottom"]',
      '[data-testid="stBottomBlockContainer"]',
      '[data-testid="manage-app-button"]',
      '[data-testid="stToolbarActionButtonTooltip"]',
      '#MainMenu',
      '.stDeployButton',
      '.stBottom',
      'footer',
    ];
    selectors.forEach(function(sel) {
      doc.querySelectorAll(sel).forEach(function(el) {
        el.style.setProperty('display', 'none', 'important');
      });
    });
    // Also hide any element whose text contains "Manage app" or "Share"
    var keywords = ['Manage app', 'Share', 'Edit'];
    doc.querySelectorAll('button, a, div[role="button"]').forEach(function(el) {
      var txt = el.innerText && el.innerText.trim();
      if (txt && keywords.some(function(k) { return txt === k; })) {
        var parent = el.closest('[class*="toolbar"], [class*="Toolbar"], [class*="bottom"], [class*="Bottom"], [class*="manage"], [class*="Manage"]') || el;
        parent.style.setProperty('display', 'none', 'important');
      }
    });
  }

  // MutationObserver to catch dynamically added chrome elements
  function watchChrome() {
    var doc = window.parent.document;
    var obs = new MutationObserver(function() { hideChrome(); });
    obs.observe(doc.body, { childList: true, subtree: true });
  }

  function init() {
    hideChrome();
    attachObserver();
    try { watchChrome(); } catch(e) {}
  }
  if (document.readyState === 'complete') { init(); }
  else { window.addEventListener('load', init); }
  setTimeout(hideChrome, 500);
  setTimeout(hideChrome, 1500);
  setTimeout(hideChrome, 3000);
  setTimeout(hideChrome, 6000);
})();
</script>
""", height=0)

# ── Session state ──────────────────────────────────────────────────────────────
if "monitor_running" not in st.session_state:
    st.session_state.monitor_running = False
if "alerts_log" not in st.session_state:
    st.session_state.alerts_log = []
if "checking" not in st.session_state:
    st.session_state.checking = False
if "lang" not in st.session_state:
    st.session_state.lang = "he"
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "chat_open" not in st.session_state:
    st.session_state.chat_open = False

# Convenience shortcut
_lang = st.session_state.lang
_rtl = _lang == "he"

# Sync language to all AI modules
for _mod in [agent, sentiment_analyzer, price_predictor, smart_search,
             trip_planner, deal_hunter, visa_check, competitor_check,
             deal_insights, price_dna, positioning]:
    _mod._lang = _lang


def _t(he: str, en: str = "") -> str:
    """Inline bilingual helper: returns English when lang=en, Hebrew otherwise."""
    return en if (_lang == "en" and en) else he


def _browser_notify(title: str, body: str):
    """Trigger a browser Web Notification via a zero-height HTML component."""
    safe_title = title.replace("`", "'").replace("\n", " ")
    safe_body = body.replace("`", "'").replace("\n", " ")
    components.html(
        f"""<script>
(function(){{
  var t = `{safe_title}`;
  var b = `{safe_body}`;
  if (Notification.permission === "granted") {{
    new Notification(t, {{body: b, icon: "✈️"}});
  }} else if (Notification.permission !== "denied") {{
    Notification.requestPermission().then(function(p) {{
      if (p === "granted") new Notification(t, {{body: b, icon: "✈️"}});
    }});
  }}
}})();
</script>""",
        height=0,
    )


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
        name=_t("מחיר", "Price"),
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
                   title=_t(f"מחיר ({currency})", f"Price ({currency})")),
        showlegend=False,
    )
    return fig


def sparkline(watch_id: int):
    """Tiny 7-day trend chart for watch cards."""
    history = db.get_price_history(watch_id, limit=7)
    if len(history) < 2:
        return None
    history = list(reversed(history))
    prices = [r["price"] for r in history]
    first, last_p = prices[0], prices[-1]
    if last_p < first:
        color = "#00ff88"
    elif last_p > first:
        color = "#ff4444"
    else:
        color = "#aaaaaa"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(prices))),
        y=prices,
        mode="lines",
        line=dict(color=color, width=1.5),
        showlegend=False,
    ))
    fig.update_layout(
        height=60,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def _booking_links(item: dict) -> dict:
    """Generate deep links to booking sites with pre-filled parameters."""
    import urllib.parse
    dest = item.get("destination", "")
    origin = item.get("origin", "TLV")
    date_from = item.get("date_from", "")
    date_to = item.get("date_to", "")
    category = item.get("category", "flight")
    links = {}

    if category == "flight":
        links["🔍 Google Flights"] = (
            f"https://www.google.com/travel/flights?q={urllib.parse.quote(f'Flights from {origin} to {dest}')}"
            + (f"&departure_date={date_from}" if date_from else "")
        )
        links["🛫 Kayak"] = (
            f"https://www.kayak.com/flights/{origin}-{dest[:3].upper()}"
            + (f"/{date_from}" if date_from else "")
            + (f"/{date_to}" if date_to else "")
        )
        links["🌐 Skyscanner"] = (
            f"https://www.skyscanner.net/transport/flights/{origin.lower()}/{dest[:4].lower()}/"
            + (date_from.replace("-", "")[:6] if date_from else "")
        )
        links["✈️ Israir"] = "https://www.israirairlines.com/"
        links["🇮🇱 Arkia"] = "https://www.arkia.com/"

    elif category == "hotel":
        links["🏨 Booking.com"] = (
            f"https://www.booking.com/search.html?ss={urllib.parse.quote(dest)}"
            + (f"&checkin={date_from}&checkout={date_to}" if date_from else "")
        )
        links["🏩 Hotels.com"] = f"https://www.hotels.com/search.do?q-destination={urllib.parse.quote(dest)}"
        links["🌍 Expedia"] = f"https://www.expedia.com/Hotel-Search?destination={urllib.parse.quote(dest)}"

    elif category == "apartment":
        links["🏠 Airbnb"] = (
            f"https://www.airbnb.com/s/{urllib.parse.quote(dest)}/homes"
            + (f"?checkin={date_from}&checkout={date_to}" if date_from and date_to else "")
        )
        links["🏡 Vrbo"] = f"https://www.vrbo.com/search?destination={urllib.parse.quote(dest)}"

    elif category == "package":
        links["📦 Expedia"] = f"https://www.expedia.com/Vacation-Packages?destination={urllib.parse.quote(dest)}"
        links["🌍 Booking.com"] = f"https://www.booking.com/search.html?ss={urllib.parse.quote(dest)}"
        links["🇮🇱 Gulliver"] = "https://www.gulliver.co.il/"

    return links


def _ai_daily_summary(items_list: list) -> str:
    """Generate a one-line AI summary of current deals."""
    import time as _time
    cache = st.session_state.get("ai_summary_cache")
    if cache and (_time.time() - cache["ts"]) < 1800:
        return cache["text"]

    if not ai_client.is_configured() or not items_list:
        return ""

    # Build quick data snapshot
    snippets = []
    for it in items_list[:8]:
        last = db.get_last_price(it["id"])
        if last:
            snippets.append(f"{it['name']}: {last['price']:.0f} {last['currency']}")
    if not snippets:
        return ""

    lang_instruction = "Respond in English." if _lang == "en" else "השב בעברית."
    prompt = (
        f"Travel price tracker data:\n" + "\n".join(snippets) +
        f"\n\nWrite ONE short sentence (max 15 words) summarizing the best deal or overall situation. "
        f"Be specific with destination and price. {lang_instruction}"
    )
    try:
        text = ai_client.ask(prompt=prompt, max_tokens=80) or ""
        st.session_state["ai_summary_cache"] = {"ts": _time.time(), "text": text}
        return text
    except Exception:
        return ""


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    # Language selector (top of sidebar)
    lang_choice = st.radio(
        i18n.t("lang_label", _lang),
        ["🇮🇱 עברית", "🇺🇸 English"],
        index=0 if _lang == "he" else 1,
        horizontal=True,
        label_visibility="collapsed",
    )
    new_lang = "he" if "עברית" in lang_choice else "en"
    if new_lang != st.session_state.lang:
        st.session_state.lang = new_lang
        st.rerun()

    st.markdown(f"## ✈️ Noded")
    st.markdown(f"*{i18n.t('tagline', _lang)}*")
    st.divider()

    # Page navigation in current language
    _pages = i18n.get_pages(_lang)
    _nav_default = 0
    if "nav_page" in st.session_state:
        _target = st.session_state.pop("nav_page")
        if _target in _pages:
            _nav_default = _pages.index(_target)
    page_display = st.radio(
        i18n.t("nav_label", _lang),
        _pages,
        index=_nav_default,
        label_visibility="collapsed",
    )
    # Normalize to Hebrew page name for routing (all page== checks use Hebrew)
    if _lang == "en":
        page = i18n.EN_TO_HE_PAGE.get(page_display, page_display)
    else:
        page = page_display

    st.divider()

    # Monitor toggle
    if not st.session_state.monitor_running:
        if st.button(i18n.t("start_monitor", _lang), use_container_width=True):
            monitor.start_background_monitor(interval=3600)
            st.session_state.monitor_running = True
            st.rerun()
    else:
        st.success(i18n.t("monitor_active", _lang))
        if st.button(i18n.t("stop_monitor", _lang), use_container_width=True):
            monitor.stop_background_monitor()
            st.session_state.monitor_running = False
            st.rerun()

    if st.button("🔔 " + _t("הפעל התראות דפדפן", "Enable Browser Notifications"), key="enable_notif"):
        components.html("<script>Notification.requestPermission();</script>", height=0)
        st.success(_t("✅ בקשת הרשאה נשלחה", "✅ Permission requested"))

    st.divider()

    # API key status
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        st.success(i18n.t("api_key_ok", _lang))
    else:
        st.error(i18n.t("api_key_missing", _lang))
        st.caption(i18n.t("api_key_hint", _lang))

    # Kiwi real-price indicator
    if kiwi_client.is_configured():
        st.success(_t("✈️ Kiwi — מחירים אמיתיים", "✈️ Kiwi — Real prices"))
    else:
        st.warning(_t("⚠️ Kiwi API חסר — מחירים מוערכים", "⚠️ No Kiwi API — estimated prices"))
        st.caption(_t("הוסף KIWI_API_KEY בהגדרות", "Add KIWI_API_KEY in Settings"))

    st.divider()
    st.markdown(f"#### {_t('📉 ירידות אחרונות', '📉 Recent Drops')}")
    _all_items = db.get_all_watch_items(enabled_only=False)
    _feed_entries = []
    for _fi in _all_items:
        _fh = db.get_price_history(_fi["id"], limit=3)
        for _fr in _fh:
            _feed_entries.append({"name": _fi["name"], "price": _fr["price"],
                                   "currency": _fr.get("currency", ""), "time": _fr["checked_at"]})
    # sort by time descending, take top 5
    _feed_entries.sort(key=lambda x: x["time"], reverse=True)
    for _fe in _feed_entries[:5]:
        _ftime = _fe["time"][11:16]
        st.markdown(
            f"<div style='font-size:12px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.07)'>"
            f"✈️ <b>{_fe['name'][:18]}</b><br>"
            f"<span style='color:#00ff88;font-size:14px'>{fmt_price(_fe['price'], _fe['currency'])}</span> "
            f"<span style='color:#888;font-size:10px'>{_ftime}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
    if not _feed_entries:
        st.caption(_t("אין נתונים עדיין", "No data yet"))

# ── Inject CSS (after lang is determined) ──────────────────────────────────────
_inject_css(_rtl)
_inject_pwa()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Dashboard
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 לוח בקרה":

    # Live price ticker — auto-refresh every 30s
    _ticker_watches = db.get_all_watch_items(enabled_only=True)
    _ticker_items = []
    for _tw in _ticker_watches[:12]:
        _tlast = db.get_last_price(_tw["id"])
        _thist = db.get_price_history(_tw["id"], limit=10)
        if _tlast:
            _tavg = sum(r["price"] for r in _thist) / len(_thist) if _thist else _tlast["price"]
            _tdelta = _tlast["price"] - _tavg
            _tarrow = "🔴▲" if _tdelta > _tavg * 0.05 else ("🟢▼" if _tdelta < -_tavg * 0.05 else "⚪")
            _thot = " 🔥" if _tlast["price"] < _tavg * 0.80 else ""
            _ticker_items.append(
                f"{_tarrow} <b>{_tw['destination']}</b> ${_tlast['price']:.0f}{_thot}"
            )
    if _ticker_items:
        _ticker_html = "&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;".join(_ticker_items)
        st.markdown(
            f"<div style='background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.08);"
            f"border-radius:8px;padding:8px 16px;overflow:hidden;white-space:nowrap;"
            f"font-size:13px;margin-bottom:8px'>"
            f"<marquee behavior='scroll' direction='left' scrollamount='3'>"
            f"{_ticker_html}"
            f"</marquee></div>",
            unsafe_allow_html=True,
        )
        st_autorefresh(interval=30_000, key="ticker_refresh")
    elif st.session_state.monitor_running:
        st_autorefresh(interval=60_000, key="dashboard_refresh")

    st.title(_t("🌍 לוח בקרה", "🌍 Dashboard"))

    # AI daily summary
    if items := db.get_all_watch_items(enabled_only=False):
        _summary = _ai_daily_summary(items)
        if _summary:
            st.markdown(
                f"<div style='background:linear-gradient(90deg,rgba(102,126,234,0.15),rgba(118,75,162,0.15));"
                f"border:1px solid rgba(102,126,234,0.3);border-radius:10px;padding:10px 16px;margin-bottom:12px'>"
                f"🤖 <em>{_summary}</em></div>",
                unsafe_allow_html=True
            )
    items = db.get_all_watch_items(enabled_only=False)

    # ── Top metrics ────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    active = sum(1 for i in items if i["enabled"])
    with_price = sum(1 for i in items if db.get_last_price(i["id"]))
    alerts_today = 0  # could read from log

    with col1:
        st.metric(_t("סה״כ מעקבים", "Total Watches"), len(items))
    with col2:
        st.metric(_t("פעילים", "Active"), active)
    with col3:
        st.metric(_t("עם מחיר", "With Price"), with_price)
    with col4:
        monitor_status = _t("🟢 פועל", "🟢 Running") if st.session_state.monitor_running else _t("🔴 כבוי", "🔴 Stopped")
        st.metric(_t("ניטור", "Monitor"), monitor_status)

    st.divider()

    # ── Deal Score Leaderboard ────────────────────────────────────────────────
    if items:
        with st.expander(_t("🏆 לידרבורד — הדילים הכי שווים עכשיו", "🏆 Leaderboard — Best Deals Right Now"), expanded=False):
            _scores = []
            for _li in items:
                _ll = db.get_last_price(_li["id"])
                if not _ll:
                    continue
                _lhist = db.get_price_history(_li["id"], limit=20)
                _prices = [r["price"] for r in _lhist]
                _cur = _ll["price"]
                # Score components (0-100)
                _price_score = 50  # default
                if len(_prices) >= 2:
                    _avg = sum(_prices) / len(_prices)
                    _min_p = min(_prices)
                    _rng = max(_avg - _min_p, 1)
                    _price_score = max(0, min(100, int(100 * (_avg - _cur) / _rng)))
                _target_score = 0
                if _li.get("max_price") and _li["max_price"] > 0:
                    _gap_pct = (_cur - _li["max_price"]) / _li["max_price"]
                    _target_score = max(0, min(100, int(100 * (1 - _gap_pct))))
                _final_score = int(_price_score * 0.6 + _target_score * 0.4)
                _scores.append({
                    "item": _li, "score": _final_score,
                    "price": _cur, "currency": _ll["currency"]
                })

            _scores.sort(key=lambda x: x["score"], reverse=True)

            for _rank, _s in enumerate(_scores[:10], 1):
                _bar_color = "#00ff88" if _s["score"] >= 70 else "#ffcc00" if _s["score"] >= 40 else "#ff4444"
                _medal = "🥇" if _rank == 1 else "🥈" if _rank == 2 else "🥉" if _rank == 3 else f"{_rank}."
                _sc1, _sc2, _sc3 = st.columns([0.5, 3, 1])
                with _sc1:
                    st.markdown(f"**{_medal}**")
                with _sc2:
                    st.markdown(f"{CAT_EMOJI.get(_s['item']['category'],'✈️')} **{_s['item']['name']}** — {_s['item']['destination']}")
                    st.progress(_s["score"] / 100)
                with _sc3:
                    st.markdown(
                        f"<div style='text-align:center'>"
                        f"<span style='color:{_bar_color};font-size:22px;font-weight:bold'>{_s['score']}</span>"
                        f"<br><small style='color:#aaa'>{fmt_price(_s['price'], _s['currency'])}</small></div>",
                        unsafe_allow_html=True
                    )

    if not items:
        st.markdown(f"## {_t('ברוכים הבאים ל-Noded! 🎉', 'Welcome to Noded! 🎉')}")
        st.markdown(_t("כמה צעדים פשוטים כדי להתחיל:", "Just a few steps to get started:"))
        ow1, ow2, ow3 = st.columns(3)
        with ow1:
            st.info(f"**{_t('שלב 1', 'Step 1')}**\n\n✈️ {_t('הוסף מעקב', 'Add a watch')}\n\n{_t('הגדר יעד, תאריכים ומחיר מקסימלי.', 'Set destination, dates and max price.')}")
        with ow2:
            st.info(f"**{_t('שלב 2', 'Step 2')}**\n\n🤖 {_t('AI מחפש מחירים', 'AI searches prices')}\n\n{_t('הסוכן בודק עבורך בזמן אמת.', 'The agent checks prices for you in real time.')}")
        with ow3:
            st.info(f"**{_t('שלב 3', 'Step 3')}**\n\n🔔 {_t('קבל התראות', 'Get alerts')}\n\n{_t('תקבל עדכון כשהמחיר יורד.', 'Get notified when the price drops.')}")
        st.write("")
        if st.button(f"➕ {_t('הוסף מעקב ראשון', 'Add First Watch')}", type="primary", use_container_width=True):
            st.session_state["nav_page"] = _t("➕ הוסף מעקב", "➕ Add Watch")
            st.rerun()
    else:
        # ── Search & filter ────────────────────────────────────────────────
        _fcol1, _fcol2, _fcol3 = st.columns([3, 1, 1])
        with _fcol1:
            _search = st.text_input(
                _t("🔍 חפש מעקב...", "🔍 Search watches..."),
                key="dash_search", label_visibility="collapsed",
                placeholder=_t("חפש לפי שם, יעד...", "Search by name, destination...")
            )
        with _fcol2:
            _cat_filter = st.selectbox(
                _t("קטגוריה", "Category"),
                ["all", "flight", "hotel", "apartment", "package"],
                format_func=lambda x: _t("הכל", "All") if x == "all" else f"{CAT_EMOJI.get(x,'')} {x}",
                key="dash_cat", label_visibility="collapsed"
            )
        with _fcol3:
            _sort_by = st.selectbox(
                _t("מיין", "Sort"),
                ["name", "price", "target"],
                format_func=lambda x: {
                    "name": _t("שם", "Name"),
                    "price": _t("מחיר", "Price"),
                    "target": _t("יעד %", "Target %")
                }[x],
                key="dash_sort", label_visibility="collapsed"
            )

        # Apply search & filter
        _filtered = items
        if _search:
            _s = _search.lower()
            _filtered = [i for i in _filtered if _s in i["name"].lower() or _s in i["destination"].lower()]
        if _cat_filter != "all":
            _filtered = [i for i in _filtered if i["category"] == _cat_filter]

        # Apply sort
        if _sort_by == "price":
            def _price_key(i):
                l = db.get_last_price(i["id"])
                return l["price"] if l else 9999999
            _filtered = sorted(_filtered, key=_price_key)
        elif _sort_by == "target":
            def _target_key(i):
                l = db.get_last_price(i["id"])
                if l and i.get("max_price") and i["max_price"] > 0:
                    return (l["price"] - i["max_price"]) / i["max_price"]
                return 0
            _filtered = sorted(_filtered, key=_target_key)

        if _search or _cat_filter != "all":
            st.caption(_t(f"מציג {len(_filtered)} מתוך {len(items)}", f"Showing {len(_filtered)} of {len(items)}"))

        # ── Items grid ─────────────────────────────────────────────────────────
        for item in _filtered:
            last = db.get_last_price(item["id"])
            lowest = db.get_lowest_price(item["id"])
            history = db.get_price_history(item["id"], limit=30)

            # Hot Deal badge — price < 80% of historical average
            _hot_badge = ""
            _is_hot = False
            if last and len(history) >= 3:
                _hist_avg = sum(r["price"] for r in history) / len(history)
                if last["price"] < _hist_avg * 0.80:
                    _pct_below = int((1 - last["price"] / _hist_avg) * 100)
                    _hot_badge = f" 🔥 HOT -{_pct_below}%"
                    _is_hot = True
                elif last["price"] < _hist_avg * 0.90:
                    _hot_badge = " 🟡 GOOD"
            _price_badge = f" | ${last['price']:.0f}" if last else ""

            with st.expander(
                f"{CAT_EMOJI.get(item['category'], '🔍')} **{item['name']}**{_price_badge}{_hot_badge} "
                f"{'🟢' if item['enabled'] else '🔴'}",
                expanded=(len(items) == 1),
            ):
                left, right = st.columns([1, 2])

                with left:
                    # Info
                    st.markdown(f"**{_t('יעד', 'Dest')}:** {item['destination']}")
                    if item.get("origin"):
                        st.markdown(f"**{_t('מוצא', 'Origin')}:** {item['origin']}")
                    if item.get("date_from"):
                        st.markdown(f"**{_t('תאריכים', 'Dates')}:** {item['date_from']} → {item.get('date_to', '')}")

                    st.divider()

                    spark = sparkline(item["id"])
                    if spark:
                        st.plotly_chart(spark, use_container_width=True, key=f"spark_{item['id']}", config={"displayModeBar": False})

                    if last:
                        price_color = "#00ff88" if (lowest and last["price"] == lowest["price"]) else "#ffffff"
                        st.markdown(
                            f"<h2 style='color:{price_color};margin:0'>"
                            f"{fmt_price(last['price'], last['currency'])}</h2>"
                            f"<small style='color:#aaa'>{_t('מחיר נוכחי', 'Current price')} | {last['checked_at'][11:16]}</small>",
                            unsafe_allow_html=True,
                        )
                        if lowest and lowest["price"] < last["price"]:
                            savings = last["price"] - lowest["price"]
                            st.caption(f"⬇ {_t('מינימום', 'Min')}: {fmt_price(lowest['price'], lowest['currency'])} ({_t('חסכון', 'saving')} {savings:.0f})")
                        if item["max_price"] and item["max_price"] > 0:
                            diff = last["price"] - item["max_price"]
                            if diff <= 0:
                                st.success(f"🎯 {_t('מתחת ליעד!', 'Below target!')} ({fmt_price(item['max_price'])})")
                                st.progress(1.0)
                            else:
                                # progress = how close we are (0=far, 1=reached)
                                # Use highest seen price as baseline if available
                                _highest = db.get_price_history(item["id"], limit=30)
                                _max_seen = max((r["price"] for r in _highest), default=last["price"]) if _highest else last["price"]
                                _range = max(_max_seen - item["max_price"], 1)
                                _progress = max(0.0, min(1.0, 1.0 - (last["price"] - item["max_price"]) / _range))
                                st.caption(f"🎯 {_t('יעד', 'Target')}: {fmt_price(item['max_price'])} · {_t('עוד', 'gap')} {diff:.0f}")
                                st.progress(_progress)
                    else:
                        st.markdown(f"*{_t('אין מחיר עדיין', 'No price yet')}*")

                    st.divider()

                    # Action buttons
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button(_t("🔍 בדוק", "🔍 Check"), key=f"check_{item['id']}"):
                            with st.spinner(_t("מחפש מחיר...", "Searching price...")):
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
                                            _browser_notify(
                                                f"✈️ Noded — {item['name']}",
                                                a["message"],
                                            )
                                    st.success(f"✅ {fmt_price(price, result.get('currency',''))}")
                                    st.rerun()
                                else:
                                    st.error(result.get("reason", _t("לא נמצא", "Not found")))
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
                        st.info(_t("📊 גרף יופיע לאחר 2+ בדיקות מחיר", "📊 Chart will appear after 2+ price checks"))

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

                    # Book Now deep links
                    _blinks = _booking_links(item)
                    if _blinks:
                        st.markdown(f"**{_t('🔗 הזמן עכשיו', '🔗 Book Now')}**")
                        _bl_cols = st.columns(min(len(_blinks), 3))
                        for _bli, (_bln, _blu) in enumerate(_blinks.items()):
                            with _bl_cols[_bli % 3]:
                                st.markdown(
                                    f"<a href='{_blu}' target='_blank' style='"
                                    f"display:block;text-align:center;padding:6px 4px;"
                                    f"background:rgba(102,126,234,0.15);border:1px solid rgba(102,126,234,0.35);"
                                    f"border-radius:8px;color:#a78bfa;text-decoration:none;"
                                    f"font-size:11px;font-weight:600;margin:2px;"
                                    f"transition:background 0.2s'>{_bln}</a>",
                                    unsafe_allow_html=True
                                )
                        st.write("")

                    # Buy Now? quick verdict
                    if len(history) >= 2:
                        _wp_key = f"wp_{item['id']}"
                        _wp_cached = st.session_state.get(_wp_key)
                        if _wp_cached:
                            _wp = _wp_cached
                            _vcolor = {"buy_now": "#00cc66", "wait": "#f59e0b", "uncertain": "#6b7280"}.get(_wp["verdict"], "#6b7280")
                            st.markdown(
                                f"<div style='background:rgba(0,0,0,0.25);border-left:4px solid {_vcolor};"
                                f"padding:8px 12px;border-radius:6px;margin:6px 0'>"
                                f"<b style='color:{_vcolor}'>{_wp['badge']}</b><br>"
                                f"<small style='color:#aaa'>"
                                f"{_t('סיכוי לירידה','Drop chance')}: {int(_wp['drop_prob']*100)}% · "
                                f"{_t('מגמה','Trend')}: {_wp['trend']} · "
                                f"vs avg: {_wp['vs_avg_pct']:+.0f}%"
                                f"</small></div>",
                                unsafe_allow_html=True,
                            )
                        btn_label = _t("🛒 לקנות עכשיו?", "🛒 Buy now?")
                        if st.button(btn_label, key=f"buynow_{item['id']}"):
                            with st.spinner(_t("מנתח...", "Analyzing...")):
                                _wp_result = price_predictor.wait_probability(item, history)
                            st.session_state[_wp_key] = _wp_result
                            st.rerun()

                    # AI analysis
                    if len(history) >= 2:
                        if st.button(_t("🤖 ניתוח AI", "🤖 AI Analysis"), key=f"anal_{item['id']}"):
                            with st.spinner(_t("מנתח...", "Analyzing...")):
                                analysis = agent.analyze_deal(item, history)
                            st.info(f"💡 {analysis}")

                    # Events at destination
                    _ev_key = f"events_{item['id']}"
                    _ev_cached = st.session_state.get(_ev_key)
                    if _ev_cached is not None:
                        if _ev_cached:
                            st.markdown(f"**🎫 {_t('אירועים ביעד', 'Events at destination')}:**")
                            for _ev in _ev_cached:
                                _imp_color = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}.get(
                                    _ev.get("price_impact", "low"), "#888"
                                )
                                st.markdown(
                                    f"<div style='border-left:3px solid {_imp_color};"
                                    f"padding:6px 10px;margin:4px 0;background:rgba(0,0,0,0.2);border-radius:4px'>"
                                    f"{_ev.get('emoji','🎫')} <b>{_ev.get('name','')}</b> "
                                    f"<span style='color:#aaa;font-size:12px'>{_ev.get('date','')}</span><br>"
                                    f"<span style='color:{_imp_color};font-size:11px'>"
                                    f"{events_finder.format_impact_label(_ev.get('price_impact','low'), _lang)}</span>"
                                    f" <span style='color:#ccc;font-size:11px'>— {_ev.get('note','')}</span>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )
                        else:
                            st.caption(_t("✅ לא נמצאו אירועים גדולים בתקופה זו", "✅ No major events found for this period"))
                    if item.get("date_from"):
                        if st.button(_t("🎫 אירועים ביעד", "🎫 Events at destination"), key=f"ev_btn_{item['id']}"):
                            with st.spinner(_t("מחפש אירועים...", "Finding events...")):
                                _ev_result = events_finder.get_events(
                                    item["destination"],
                                    item.get("date_from", ""),
                                    item.get("date_to", ""),
                                )
                            st.session_state[_ev_key] = _ev_result
                            st.rerun()

                    # Auto-renew: suggest new dates if watch has expired
                    _date_to_str = item.get("date_to", "")
                    _watch_expired = False
                    if _date_to_str:
                        try:
                            from datetime import date as _date_cls2
                            _watch_expired = _date_cls2.fromisoformat(_date_to_str) < _date_cls2.today()
                        except Exception:
                            pass
                    if _watch_expired:
                        st.warning(_t(
                            f"⏰ המעקב פג ב-{_date_to_str}",
                            f"⏰ Watch expired on {_date_to_str}",
                        ))
                        if st.button(_t("🔄 חדש תאריכים (AI)", "🔄 Renew dates (AI)"), key=f"renew_{item['id']}"):
                            with st.spinner(_t("AI מחפש תאריכים דומים...", "AI finding similar dates...")):
                                _renew_prompt = (
                                    f"A travel watch for {item.get('destination')} from {item.get('origin','TLV')} "
                                    f"expired on {_date_to_str}. "
                                    f"Suggest 3 new date ranges (date_from, date_to) for similar travel in the next 3-6 months "
                                    f"from today ({__import__('datetime').date.today()}). "
                                    f"Return JSON array: [{{\"date_from\":\"YYYY-MM-DD\",\"date_to\":\"YYYY-MM-DD\",\"label\":\"...\"}}]. "
                                    + ("Respond in Hebrew." if _lang == "he" else "")
                                )
                                try:
                                    _renew_text = ai_client.ask(_renew_prompt, max_tokens=400)
                                    import re as _re2
                                    _arr_match = _re2.search(r'\[.*\]', _renew_text, _re2.DOTALL)
                                    if _arr_match:
                                        _suggestions = json.loads(_arr_match.group(0))
                                        st.session_state[f"renew_suggestions_{item['id']}"] = _suggestions
                                except Exception as _ex:
                                    st.error(str(_ex))

                    _renew_suggs = st.session_state.get(f"renew_suggestions_{item['id']}", [])
                    if _renew_suggs:
                        st.markdown(_t("**📅 תאריכים מוצעים:**", "**📅 Suggested dates:**"))
                        for _sug in _renew_suggs:
                            _sug_label = _sug.get("label", f"{_sug.get('date_from','')} → {_sug.get('date_to','')}")
                            if st.button(f"✅ {_sug_label}", key=f"apply_renew_{item['id']}_{_sug.get('date_from','')}"):
                                db.update_watch_dates(item["id"], _sug["date_from"], _sug.get("date_to",""))
                                del st.session_state[f"renew_suggestions_{item['id']}"]
                                st.success(_t("✅ תאריכים עודכנו!", "✅ Dates updated!"))
                                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Add Item
# ══════════════════════════════════════════════════════════════════════════════
elif page == "➕ הוסף מעקב":
    st.title(_t("➕ הוסף פריט למעקב", "➕ Add Watch Item"))

    # ── Natural Language Input ──────────────────────────────────────────────────
    with st.expander(_t("🗣️ הוסף בשפה טבעית (AI)", "🗣️ Add in natural language (AI)"), expanded=False):
        st.caption(_t(
            'דוגמאות: "טיסה לברצלונה במאי עד 400 דולר" | "מלון בלונדון ב-15 ביוני, תקציב 200$"',
            'Examples: "flight to Barcelona in May up to $400" | "hotel in London June 15, $200 budget"',
        ))
        nl_input = st.text_input(
            _t("תאר את המעקב שלך:", "Describe your watch:"),
            placeholder=_t("טיסה לטוקיו בספטמבר עד 800 דולר", "flight to Tokyo in September up to $800"),
            key="nl_input_field",
        )
        nl_btn = st.button(_t("🤖 נתח ומלא", "🤖 Parse & fill"), key="nl_parse_btn")

    if nl_btn and nl_input:
        with st.spinner(_t("🤖 מנתח...", "🤖 Parsing...")):
            _nl_result = nl_parser.parse_watch_request(nl_input)

        if "error" in _nl_result:
            st.error(f"שגיאה: {_nl_result['error']}")
        else:
            st.session_state["nl_prefill"] = _nl_result
            _conf = _nl_result.get("confidence", 0)
            st.success(
                f"✅ {_t('זוהה', 'Detected')}: **{_nl_result.get('name','')}** "
                f"→ {_nl_result.get('destination','')} | {_nl_result.get('date_from','')} — {_nl_result.get('date_to','')} | "
                f"max ${_nl_result.get('max_price','?')}  _(confidence: {_conf:.0%})_"
            )
            if _nl_result.get("notes"):
                st.caption(f"📝 {_nl_result['notes']}")
            st.info(_t("הטופס למטה מולא אוטומטית — בדוק ולחץ הוסף", "Form below was pre-filled — review and click Add"))

    # Pre-fill from NL parse
    _pf = st.session_state.get("nl_prefill", {})

    with st.form("add_item_form"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input(_t("שם הפריט *", "Item name *"), value=_pf.get("name",""), placeholder=_t("טיסה לברצלונה", "Flight to Barcelona"))
            _cat_opts = ["flight", "hotel", "apartment", "package"]
            _cat_default = _cat_opts.index(_pf["category"]) if _pf.get("category") in _cat_opts else 0
            category = st.selectbox(
                _t("קטגוריה *", "Category *"),
                _cat_opts,
                index=_cat_default,
                format_func=lambda x: f"{CAT_EMOJI[x]} {x}",
            )
            destination = st.text_input(
                _t("יעד *", "Destination *"),
                value=_pf.get("destination", ""),
                placeholder=_t("ברצלונה / BCN / Spain", "Barcelona / BCN / Spain"),
                help=_t("שם עיר, מדינה, או קוד IATA של שדה תעופה (3 אותיות)", "City name, country, or 3-letter IATA airport code"),
            )
            origin = st.text_input(
                _t("עיר מוצא / קוד IATA", "Origin city / IATA code"),
                value=_pf.get("origin", ""),
                placeholder=_t("TLV", "TLV"),
                help=_t("קוד IATA של שדה תעופה (TLV, SDV, ETH) או שם עיר", "IATA airport code (TLV, SDV, ETH) or city name"),
            )

        with col2:
            _pf_date_from = None
            _pf_date_to = None
            try:
                from datetime import date as _date_cls
                if _pf.get("date_from"):
                    _pf_date_from = _date_cls.fromisoformat(_pf["date_from"])
                if _pf.get("date_to"):
                    _pf_date_to = _date_cls.fromisoformat(_pf["date_to"])
            except Exception:
                pass
            date_from = st.date_input(_t("תאריך התחלה", "Start date"), value=_pf_date_from)
            date_to = st.date_input(_t("תאריך סיום", "End date"), value=_pf_date_to)
            max_price = st.number_input(
                _t("מחיר יעד (התרע כשיורד אל/מתחת)", "Target price (alert when drops to/below)"),
                min_value=0.0, value=float(_pf.get("max_price") or 0), step=10.0,
            )
            drop_pct = st.slider(_t("התרע בירידה של %", "Alert on % drop"), 5, 50, 10)

        custom_query = st.text_area(
            _t("שאילתה מותאמת אישית (אופציונלי)", "Custom query (optional)"),
            placeholder=_t("מצא טיסה זולה מ-TLV לברצלונה בתחילת מאי, כולל מזוודה", "Find cheap flight from TLV to Barcelona early May, with luggage"),
            height=80,
        )

        check_now = st.checkbox(_t("בדוק מחיר מיד לאחר הוספה", "Check price immediately after adding"), value=True)
        submitted = st.form_submit_button(_t("➕ הוסף", "➕ Add"), use_container_width=True)

    if submitted:
        # Validate fields
        _errors = []
        if not name:
            _errors.append(_t("שם הפריט הוא שדה חובה", "Item name is required"))
        dest_ok, dest_msg = validators.validate_destination(destination)
        if not dest_ok:
            _errors.append(dest_msg)
        origin_ok, origin_msg = validators.validate_origin(origin, category)
        if not origin_ok:
            _errors.append(origin_msg)

        if _errors:
            for _e in _errors:
                st.error(_e)
            # Show IATA suggestions on error
            if destination and not dest_ok:
                _suggs = validators.suggest_iata(destination)
                if _suggs:
                    st.info(_t("💡 אולי התכוונת ל: ", "💡 Did you mean: ") + " · ".join(_suggs[:5]))
            if origin and not origin_ok:
                _suggs_o = validators.suggest_iata(origin)
                if _suggs_o:
                    st.info(_t("💡 קודי IATA: ", "💡 IATA codes: ") + " · ".join(_suggs_o[:5]))
        else:
            # Show info hints (non-blocking)
            if dest_ok and dest_msg:
                st.info(dest_msg)
            if origin_ok and origin_msg and "טיפ" in origin_msg:
                st.info(origin_msg)
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
            st.success(f"✅ {_t('נוסף!', 'Added!')} (ID: {new_id})")

            if check_now:
                items_all = db.get_all_watch_items(enabled_only=False)
                item_dict = next((i for i in items_all if i["id"] == new_id), None)
                if item_dict:
                    with st.spinner(_t("🔍 מחפש מחיר...", "🔍 Searching price...")):
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
                            f"### 💰 {_t('מחיר שנמצא:', 'Price found:')} "
                            f"**{fmt_price(price, result.get('currency',''))}**"
                        )
                        st.markdown(
                            f"<span style='color:{dq_color}'>⭐ {dq}</span> | "
                            f"{_t('מקור', 'Source')}: {result.get('source', '')}",
                            unsafe_allow_html=True,
                        )
                        if result.get("details"):
                            st.caption(result["details"][:200])
                    else:
                        st.warning(f"{_t('לא נמצא מחיר:', 'Price not found:')} {result.get('reason', '')}")


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# PAGE: AI Travel Agent Chat
# ══════════════════════════════════════════════════════════════════════════════
elif page in ("💬 סוכן נסיעות AI", "💬 AI Travel Agent"):
    st.title(_t("💬 סוכן נסיעות AI", "💬 AI Travel Agent"))
    st.caption(_t(
        "שוחח עם סוכן AI שמכיר את כל המעקבים, הדילים והמחירים שלך",
        "Chat with an AI agent that knows all your watches, deals and prices",
    ))

    # ── Build context snapshot from DB ──────────────────────────────────────
    def _agent_context() -> str:
        watches = db.get_all_watch_items(enabled_only=False)
        deals = deal_hunter.get_recent_deals(limit=10, min_score=6)
        lines = ["=== USER'S ACTIVE WATCHES ==="]
        for w in watches[:15]:
            hist = db.get_price_history(w["id"], limit=3)
            last_price = f"${hist[0]['price']:.0f}" if hist else "no price yet"
            lines.append(
                f"• {w['name']}: {w.get('origin','TLV')}→{w['destination']} "
                f"[{w.get('date_from','')}–{w.get('date_to','')}] "
                f"max=${w.get('max_price') or '?'} | last={last_price}"
            )
        if deals:
            lines.append("\n=== RECENT DEALS (score≥6) ===")
            for d in deals[:5]:
                lines.append(
                    f"• {d.get('destination')} ${d.get('price',0):.0f} "
                    f"({d.get('deal_type','')}, score {d.get('score',0):.1f}/10) — {d.get('why_amazing','')[:80]}"
                )
        lines.append(f"\nToday: {__import__('datetime').date.today()}")
        lines.append(f"User language: {_lang}")
        return "\n".join(lines)

    _AGENT_SYSTEM = (
        "You are a world-class AI travel agent assistant integrated into Noded — "
        "a personal travel price monitoring app. "
        "You have access to the user's active price watches, recent deals, and price history (provided in context). "
        "You can help with: planning trips, finding best dates/prices, explaining deals, "
        "suggesting destinations, calculating costs, giving visa tips, comparing airlines, "
        "and anything travel-related. "
        "Be conversational, specific, and proactive. Use emojis naturally. "
        "When the user asks to search for flights or prices, give realistic estimates and explain how to find them. "
        "When you recommend a specific action (like 'add a watch for this route'), "
        "say so clearly so the user knows what to do in the app. "
        "If the user writes in Hebrew, respond in Hebrew. If English, respond in English. "
        "Never make up specific prices as facts — say 'approximately' or 'typically'. "
        "Always be honest when you don't know something."
    )

    # ── Session state init ───────────────────────────────────────────────────
    if "agent_history" not in st.session_state:
        st.session_state["agent_history"] = []
    if "agent_context_snapshot" not in st.session_state:
        st.session_state["agent_context_snapshot"] = _agent_context()

    # ── Toolbar ──────────────────────────────────────────────────────────────
    tc1, tc2, tc3 = st.columns([2, 1, 1])
    with tc1:
        _use_search = st.toggle(
            _t("🌐 חיפוש אינטרנט", "🌐 Web search"),
            value=True,
            help=_t("מאפשר לסוכן לחפש מחירים עדכניים ברשת", "Lets the agent search the web for live prices"),
            key="agent_web_search",
        )
    with tc2:
        if st.button(_t("🔄 רענן הקשר", "🔄 Refresh context"), key="agent_refresh_ctx"):
            st.session_state["agent_context_snapshot"] = _agent_context()
            st.toast(_t("הקשר עודכן!", "Context refreshed!"))
    with tc3:
        if st.button(_t("🗑 נקה שיחה", "🗑 Clear chat"), key="agent_clear"):
            st.session_state["agent_history"] = []
            st.rerun()

    # ── Suggested starters ───────────────────────────────────────────────────
    if not st.session_state["agent_history"]:
        st.markdown(_t("**💡 דוגמאות לשאלות:**", "**💡 Try asking:**"))
        starters_he = [
            "תכנן לי שבוע בגיאורגיה עם תקציב 1500$",
            "מה הדיל הכי טוב שיש לי עכשיו?",
            "מתי הכי זול לטוס לבנקוק מתל אביב?",
            "תסביר לי את הדילים שיש לי",
            "תמצא לי חלופות זולות לרומא בספטמבר",
        ]
        starters_en = [
            "Plan me a week in Georgia with a $1500 budget",
            "What's my best deal right now?",
            "When's the cheapest time to fly from TLV to Bangkok?",
            "Explain the deals I have",
            "Find me cheap alternatives to Rome in September",
        ]
        starters = starters_he if _lang == "he" else starters_en
        scols = st.columns(len(starters))
        for _si, (_sc, _sq) in enumerate(zip(scols, starters)):
            with _sc:
                if st.button(_sq, key=f"starter_{_si}", use_container_width=True):
                    st.session_state["_agent_pending"] = _sq
                    st.rerun()

    # ── Render existing conversation ─────────────────────────────────────────
    for msg in st.session_state["agent_history"]:
        role = "user" if msg["role"] == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg["parts"][0]["text"])

    # ── Handle pending starter click ─────────────────────────────────────────
    _pending = st.session_state.pop("_agent_pending", None)

    # ── Chat input ───────────────────────────────────────────────────────────
    _user_input = st.chat_input(
        _t("שאל אותי כל דבר על נסיעות...", "Ask me anything about travel..."),
        key="agent_chat_input",
    ) or _pending

    if _user_input:
        # Show user message immediately
        with st.chat_message("user"):
            st.markdown(_user_input)

        # Build full prompt: context snapshot + user message
        _ctx = st.session_state["agent_context_snapshot"]
        _full_prompt = f"[CONTEXT]\n{_ctx}\n\n[USER MESSAGE]\n{_user_input}"

        # Stream-like thinking indicator
        with st.chat_message("assistant"):
            with st.spinner(_t("חושב...", "Thinking...")):
                _reply = ai_client.chat_turn(
                    history=st.session_state["agent_history"],
                    user_message=_full_prompt,
                    system=_AGENT_SYSTEM,
                    max_tokens=2048,
                    web_search=_use_search,
                )
            if _reply:
                st.markdown(_reply)
            else:
                _reply = _t(
                    "⚠️ לא הצלחתי לקבל תשובה. בדוק שה-GEMINI_API_KEY מוגדר.",
                    "⚠️ Could not get a response. Check that GEMINI_API_KEY is set.",
                )
                st.warning(_reply)

        # Append to history (store original user text, not the prompt+context)
        st.session_state["agent_history"].append(
            {"role": "user", "parts": [{"text": _user_input}]}
        )
        st.session_state["agent_history"].append(
            {"role": "model", "parts": [{"text": _reply}]}
        )

        # Keep history manageable (last 20 turns = 10 exchanges)
        if len(st.session_state["agent_history"]) > 20:
            st.session_state["agent_history"] = st.session_state["agent_history"][-20:]


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Worth Waiting?
# ══════════════════════════════════════════════════════════════════════════════
elif page in ("🔮 כדאי לחכות?", "🔮 Worth Waiting?"):
    st.title(_t("🔮 כדאי לחכות?", "🔮 Worth Waiting?"))
    st.caption(_t(
        "AI מנתח את היסטוריית המחירים שלך ומחליט: לקנות עכשיו או לחכות?",
        "AI analyzes your price history and decides: buy now or wait?",
    ))

    _all_watches = db.get_all_watch_items(enabled_only=False)
    _active = [w for w in _all_watches if w.get("enabled")]

    if not _active:
        st.info(_t("אין מעקבים פעילים. הוסף מעקב ראשון!", "No active watches. Add your first watch!"))
    else:
        # Analyze all button
        ww_col1, ww_col2 = st.columns([2, 1])
        with ww_col1:
            _analyze_all = st.button(
                _t("🔮 נתח את כל המעקבים", "🔮 Analyze all watches"),
                type="primary", use_container_width=True, key="ww_all",
            )
        with ww_col2:
            _min_data = st.number_input(
                _t("מינ' נקודות נתונים", "Min data points"),
                min_value=2, max_value=20, value=2, key="ww_min_data",
            )

        if _analyze_all:
            _ww_results = {}
            _prog = st.progress(0)
            for _wi, _w in enumerate(_active):
                _hist = db.get_price_history(_w["id"], limit=30)
                if len(_hist) >= _min_data:
                    _ww_results[_w["id"]] = price_predictor.wait_probability(_w, _hist)
                _prog.progress((_wi + 1) / len(_active))
            st.session_state["ww_results"] = _ww_results
            _prog.empty()
            st.rerun()

        _ww_results = st.session_state.get("ww_results", {})

        # Summary row
        if _ww_results:
            _buy_now_count = sum(1 for r in _ww_results.values() if r["verdict"] == "buy_now")
            _wait_count = sum(1 for r in _ww_results.values() if r["verdict"] == "wait")
            _unsure_count = sum(1 for r in _ww_results.values() if r["verdict"] == "uncertain")
            sm1, sm2, sm3 = st.columns(3)
            sm1.metric("✅ " + _t("קנה עכשיו", "Buy now"), _buy_now_count)
            sm2.metric("⏳ " + _t("כדאי לחכות", "Worth waiting"), _wait_count)
            sm3.metric("🤔 " + _t("לא ברור", "Uncertain"), _unsure_count)
            st.divider()

        # Per-watch cards
        for _w in _active:
            _hist = db.get_price_history(_w["id"], limit=30)
            _wp = _ww_results.get(_w["id"])

            with st.expander(
                f"{'🔮' if _wp else '⬜'} **{_w['name']}** — "
                f"{_w.get('origin','TLV')}→{_w['destination']} "
                + (f"| {_wp['badge']}" if _wp else _t("(לא נותח)", "(not analyzed)")),
                expanded=bool(_wp),
            ):
                wc1, wc2 = st.columns([3, 2])
                with wc1:
                    if len(_hist) < _min_data:
                        st.warning(_t(
                            f"צריך לפחות {_min_data} בדיקות מחיר לניתוח (יש {len(_hist)})",
                            f"Need at least {_min_data} price checks to analyze (have {len(_hist)})",
                        ))
                    else:
                        if not _wp:
                            if st.button(
                                _t("🔮 נתח", "🔮 Analyze"),
                                key=f"ww_single_{_w['id']}",
                            ):
                                _wp = price_predictor.wait_probability(_w, _hist)
                                _cur = st.session_state.get("ww_results", {})
                                _cur[_w["id"]] = _wp
                                st.session_state["ww_results"] = _cur
                                st.rerun()
                        else:
                            _vcolor = {
                                "buy_now": "#00cc66",
                                "wait": "#f59e0b",
                                "uncertain": "#888",
                            }.get(_wp["verdict"], "#888")
                            _drop_pct = int(_wp["drop_prob"] * 100)

                            # Big verdict badge
                            st.markdown(
                                f"<div style='background:rgba(0,0,0,0.3);border:2px solid {_vcolor};"
                                f"border-radius:12px;padding:16px;text-align:center;margin-bottom:12px'>"
                                f"<div style='font-size:2rem'>{_wp['badge']}</div>"
                                f"<div style='color:{_vcolor};font-size:1.2rem;font-weight:bold;margin:4px 0'>"
                                f"{_t('סיכוי לירידת מחיר','Chance of price drop')}: {_drop_pct}%</div>"
                                f"<div style='background:rgba(255,255,255,0.1);border-radius:8px;height:8px;margin:8px 0'>"
                                f"<div style='background:{_vcolor};width:{_drop_pct}%;height:100%;border-radius:8px'></div>"
                                f"</div></div>",
                                unsafe_allow_html=True,
                            )

                            # Stats grid
                            s1, s2, s3 = st.columns(3)
                            s1.metric(
                                _t("מחיר נוכחי", "Current"), f"${_wp['current']:.0f}",
                                delta=f"{_wp['vs_avg_pct']:+.0f}% vs avg",
                                delta_color="inverse",
                            )
                            s2.metric(_t("ממוצע", "Average"), f"${_wp['avg']:.0f}")
                            s3.metric(
                                _t("מגמה", "Trend"),
                                {"falling": "📉 " + _t("יורד","Falling"),
                                 "rising": "📈 " + _t("עולה","Rising"),
                                 "stable": "➡️ " + _t("יציב","Stable")}.get(_wp["trend"], _wp["trend"])
                            )

                            if _wp.get("days_to_travel") is not None:
                                _dtc = _wp["days_to_travel"]
                                if _dtc < 0:
                                    st.caption(_t("⚠️ תאריך הנסיעה עבר", "⚠️ Travel date has passed"))
                                else:
                                    st.caption(f"✈️ {_t('עד הנסיעה','Days to travel')}: **{_dtc}** {_t('ימים','days')}")

                with wc2:
                    # Mini price chart
                    if len(_hist) >= 2:
                        _fig_ww = price_chart(_w["id"], _w["name"])
                        if _fig_ww:
                            _fig_ww.update_layout(height=180, margin=dict(t=20, b=10, l=10, r=10))
                            st.plotly_chart(_fig_ww, use_container_width=True, key=f"ww_chart_{_w['id']}")

                    # Deep AI prediction button
                    if _hist and len(_hist) >= 3:
                        if st.button(
                            _t("🤖 ניתוח עמוק (AI+web)", "🤖 Deep analysis (AI+web)"),
                            key=f"ww_deep_{_w['id']}",
                        ):
                            with st.spinner(_t("AI מנתח...", "AI analyzing...")):
                                _deep = price_predictor.predict_price(_w, _hist)
                            if _deep:
                                _fmt = price_predictor.format_prediction(_deep)
                                st.info(
                                    f"{_fmt['icon']} **{_fmt['recommendation']}** "
                                    f"({_fmt['confidence']})\n\n{_fmt['reasoning']}"
                                )
                                if _fmt.get("predicted_7d"):
                                    st.caption(
                                        f"📅 7d: ${_fmt['predicted_7d']:.0f} · "
                                        f"30d: ${_fmt.get('predicted_30d', 0):.0f}"
                                    )


# PAGE: Smart Opportunities
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🌟 הזדמנויות AI":
    st.title(_t("🌟 הזדמנויות חכמות", "🌟 Smart Opportunities"))
    st.caption(_t("Claude מחפש את הדילים הטובים ביותר עבורך", "Claude finds the best deals for you"))

    with st.form("opp_form"):
        dests = st.text_input(
            _t("יעדים לחיפוש (מופרד בפסיקים)", "Destinations to search (comma separated)"),
            placeholder=_t("לונדון, פריז, ברצלונה, אמסטרדם", "London, Paris, Barcelona, Amsterdam"),
            value=_t("לונדון, פריז, ברצלונה", "London, Paris, Barcelona"),
        )
        categories_sel = st.multiselect(
            _t("סוגי מוצרים", "Product types"),
            [_t("טיסות", "Flights"), _t("מלונות", "Hotels"), _t("חבילות", "Packages")],
            default=[_t("טיסות", "Flights"), _t("מלונות", "Hotels"), _t("חבילות", "Packages")],
        )
        search_btn = st.form_submit_button(_t("🔍 חפש הזדמנויות", "🔍 Search Opportunities"), use_container_width=True)

    if search_btn:
        dest_list = [d.strip() for d in dests.split(",") if d.strip()]
        with st.spinner(_t("🤖 Claude מחפש הזדמנויות... (עשוי לקחת 30-60 שניות)", "🤖 Claude searching opportunities... (may take 30-60 seconds)")):
            opps = agent.smart_search_opportunities(dest_list)

        if not opps:
            st.warning(_t("לא נמצאו הזדמנויות כרגע. נסה שוב מאוחר יותר.", "No opportunities found right now. Try again later."))
        else:
            st.success(f"{_t('נמצאו', 'Found')} {len(opps)} {_t('הזדמנויות!', 'opportunities!')} 🎉")
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
                        st.markdown(f"{urg_color} {_t('דחיפות', 'Urgency')}: **{urgency}**")

                        if st.button(_t("➕ הוסף למעקב", "➕ Add to watchlist"), key=f"add_opp_{i}"):
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
                            st.success(_t("נוסף!", "Added!"))

            if len(opps) > 3:
                with st.expander(f"{_t('עוד', 'More')} {len(opps)-3} {_t('הזדמנויות', 'opportunities')}"):
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
    st.title(_t("🔥 ציד דילים — Error Fares & Flash Sales", "🔥 Deal Hunter — Error Fares & Flash Sales"))
    st.caption(_t("סורק secretflying, El Al, Israir, Arkia, Ryanair, WizzAir — מחפש שגיאות מחיר ומבצעי פלאש", "Scans secretflying, El Al, Israir, Arkia, Ryanair, WizzAir — finds error fares and flash sales"))

    GRADE_COLOR = {"A+": "#00ff88", "A": "#44ff88", "B": "#88ff44", "C": "#ffcc00", "D": "#ff4444"}
    URGENCY_ICON = {"immediate": "🚨", "today": "⚡", "this_week": "📅"}

    tab1, tab2 = st.tabs([_t("🔍 ציד חדש", "🔍 New Hunt"), _t("📋 דילים שנמצאו", "📋 Found Deals")])

    with tab1:
        st.markdown(_t("בחר אתרי מקור לסריקה:", "Select source sites to scan:"))
        sources_selected = {}
        src_cols = st.columns(4)
        for i, (name, url) in enumerate(deal_hunter.DEAL_SOURCES.items()):
            with src_cols[i % 4]:
                sources_selected[name] = st.checkbox(name, value=(i < 4), key=f"src_{name}")

        selected_urls = [deal_hunter.DEAL_SOURCES[k] for k, v in sources_selected.items() if v]

        if st.button(_t("🔥 צוד דילים עכשיו!", "🔥 Hunt Deals Now!"), use_container_width=True, type="primary"):
            if not selected_urls:
                st.error(_t("בחר לפחות מקור אחד", "Select at least one source"))
            else:
                with st.spinner(f"🤖 Claude {_t('סורק', 'scanning')} {len(selected_urls)} {_t('אתרים... (30-90 שניות)', 'sites... (30-90 seconds)')}"):
                    found = deal_hunter.hunt_deals(selected_urls)

                if not found or (len(found) == 1 and "error" in found[0]):
                    err = found[0].get("error", "") if found else ""
                    st.warning(f"{_t('לא נמצאו דילים.', 'No deals found.')} {err}")
                else:
                    st.success(f"🎉 {_t('נמצאו', 'Found')} {len(found)} {_t('דילים!', 'deals!')}")
                    for d in found:
                        if not isinstance(d, dict):
                            continue
                        grade = d.get("ai_grade", d.get("deal_type", ""))
                        gcolor = GRADE_COLOR.get(grade, "#aaa")
                        urgency = URGENCY_ICON.get(d.get("urgency", ""), "📅")
                        with st.container():
                            book_link = f'<br><a href="{d["book_url"]}" target="_blank">🔗 {_t("הזמן", "Book")}</a>' if d.get("book_url") else ""
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
        min_score_filter = st.slider(_t("ציון מינימלי", "Minimum score"), 0.0, 10.0, 5.0, 0.5)
        recent = deal_hunter.get_recent_deals(limit=50, min_score=min_score_filter)

        if not recent:
            st.info(_t("אין דילים שמורים עדיין. לחץ 'צוד דילים' כדי להתחיל.", "No saved deals yet. Click 'Hunt Deals' to start."))
        else:
            st.caption(f"{_t('מציג', 'Showing')} {len(recent)} {_t('דילים (מינימום ציון', 'deals (min score')} {min_score_filter})")

            # Score leaderboard with AI scoring
            if st.button(_t("🤖 נקד דילים עם AI", "🤖 Score Deals with AI"), key="ai_score_btn"):
                with st.spinner(_t("מנקד...", "Scoring...")):
                    scored = deal_scorer.score_and_filter(recent, min_score=0)
                recent = scored if scored else recent

            for d in recent:
                if not isinstance(d, dict):
                    continue
                score = d.get("score", d.get("ai_score", 0))
                grade = d.get("ai_grade", "")
                gcolor = GRADE_COLOR.get(grade, "#667eea")
                score_bar = "█" * int(score) + "░" * (10 - int(score))
                urgency = URGENCY_ICON.get(d.get("urgency", ""), "📅")

                with st.expander(
                    f"{urgency} **{d.get('destination','')}** — "
                    f"${d.get('price', 0):.0f} | {_t('ציון', 'Score')}: {score:.1f}/10 {grade}"
                ):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown(f"**{_t('חברה', 'Airline')}:** {d.get('airline','')}")
                        st.markdown(f"**{_t('תאריכים', 'Dates')}:** {d.get('dates','')}")
                        st.markdown(f"**{_t('סוג', 'Type')}:** {d.get('deal_type','')}")
                        st.markdown(f"**{_t('מקור', 'Source')}:** {d.get('source','')}")
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
                            st.link_button(_t("🔗 הזמן", "🔗 Book"), d["book_url"])
                        if d.get("expires"):
                            st.caption(f"⏰ {_t('פג תוקף', 'Expires')}: {d['expires']}")
                        explain_key = f"explain_score_{d.get('id', d.get('destination',''))}_{score}"
                        if st.button(_t("📖 למה הציון הזה?", "📖 Why this score?"), key=explain_key):
                            with st.spinner(_t("Claude מנתח...", "Claude analyzing...")):
                                explain_prompt = (
                                    f"Deal: {d.get('destination')} from {d.get('origin','TLV')}, "
                                    f"price ${d.get('price',0)}, type {d.get('deal_type','')}, "
                                    f"discount {d.get('discount_pct',0)}%, urgency {d.get('urgency','')}, "
                                    f"score {score}/10. "
                                    f"Explain in 2-3 sentences why this score, what makes it good/bad, "
                                    f"and whether the user should act now. "
                                    + ("Respond in Hebrew." if _lang == "he" else "Respond in English.")
                                )
                                try:
                                    explanation = ai_client.ask(explain_prompt, max_tokens=300)
                                    st.markdown(f"**🤖 AI:** {explanation}")
                                except Exception as ex:
                                    st.error(str(ex))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Surprise Me
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🎲 הפתיעני":
    st.title(_t("🎲 הפתיעני — מצא את הדסטינציה הכי שווה", "🎲 Surprise Me — Find the Best Destination"))
    st.caption(_t("הכנס תקציב ותאריכים — Claude ימצא את היעד הכי שווה שאולי לא חשבת עליו", "Enter budget and dates — Claude will find the best destination you might not have thought of"))

    with st.form("surprise_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            budget = st.number_input(_t("תקציב לאדם ($)", "Budget per person ($)"), value=800, min_value=200, step=50)
            currency = st.selectbox(_t("מטבע", "Currency"), ["USD", "EUR", "ILS"])
        with c2:
            from_date = st.date_input(_t("תאריך יציאה", "Departure date"), value=None)
            to_date = st.date_input(_t("תאריך חזרה", "Return date"), value=None)
        with c3:
            duration = st.slider(_t("ימי טיול", "Trip days"), 3, 21, 7)
            style = st.selectbox(_t("סגנון", "Style"), [_t("כל סגנון", "Any style"), _t("תקציבי", "Budget"), _t("רומנטי", "Romantic"), _t("הרפתקאות", "Adventure"), _t("תרבות", "Culture"), _t("טבע", "Nature"), _t("לוקסוס", "Luxury")])

        interests = st.text_input(_t("תחומי עניין", "Interests"), placeholder=_t("אוכל, היסטוריה, שפת ים, הייקינג...", "Food, history, beach, hiking..."))
        surprise_btn = st.form_submit_button(_t("🎲 הפתיעני!", "🎲 Surprise Me!"), use_container_width=True, type="primary")

    if surprise_btn:
        from_str = str(from_date) if from_date else ""
        to_str = str(to_date) if to_date else ""

        with st.spinner(_t("🤖 Claude מחפש את הדסטינציות הכי שוות עבורך... (30-60 שניות)", "🤖 Claude finding the best destinations for you... (30-60 seconds)")):
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
            st.error(f"{_t('לא נמצאו תוצאות.', 'No results found.')} {err}")
        else:
            st.success(f"🎉 {_t('נמצאו', 'Found')} {len(results)} {_t('יעדים מדהימים!', 'amazing destinations!')}")
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
                            st.caption(f"📅 {_t('מתי להזמין', 'Best time to book')}: {dest['best_time_to_book']}")
                    with c2:
                        st.metric(_t("סה״כ לאדם", "Total per person"), f"${dest.get('total_price', 0):,}")
                        st.caption(f"✈️ {_t('טיסה', 'Flight')}: ${dest.get('flight_price', 0):,}")
                        st.caption(f"🏨 {_t('מלון/לילה', 'Hotel/night')}: ${dest.get('hotel_price_night', 0):,}")
                    with c3:
                        st.markdown(
                            f"<div style='text-align:center;padding:10px'>"
                            f"<span style='font-size:2em'>{'⭐' * min(int(surprise/2), 5)}</span><br>"
                            f"<span style='color:{q_color}'>{quality}</span><br>"
                            f"<small>Surprise: {surprise}/10</small>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(_t("➕ הוסף למעקב", "➕ Add to watchlist"), key=f"add_surprise_{i}"):
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
                            st.success(_t("נוסף למעקב! ✅", "Added to watchlist! ✅"))

                    st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Smart Tools
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🛠️ כלים חכמים":
    st.title(_t("🛠️ כלים חכמים", "🛠️ Smart Tools"))
    st.caption(_t("חיפוש מתקדם: Split Ticket, שדות תעופה קרובים, Last Minute, יום זול בשבוע, חבילה vs. עצמאי", "Advanced search: Split Ticket, nearby airports, Last Minute, cheapest day, package vs. independent"))

    tool_tab = st.tabs([
        "✂️ Split Ticket",
        _t("🏙️ שדות תעופה", "🏙️ Airports"),
        "⏰ Last Minute",
        _t("📆 יום זול", "📆 Cheapest Day"),
        _t("📦 חבילה vs. עצמאי", "📦 Package vs. Independent"),
        _t("📅 מתי להזמין", "📅 When to Book"),
    ])

    # ── Split Ticket ────────────────────────────────────────────────────────
    with tool_tab[0]:
        st.subheader(_t("✂️ Split Ticket — הלוך-חזור vs. שני כרטיסים נפרדים", "✂️ Split Ticket — Round-trip vs. two one-ways"))
        st.caption(_t("לפעמים שני כרטיסים חד-כיווניים זולים יותר מהלוך-חזור", "Sometimes two one-way tickets are cheaper than a round-trip"))

        with st.form("split_form"):
            sc1, sc2 = st.columns(2)
            with sc1:
                split_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
                split_dest = st.text_input(_t("יעד", "Destination"), placeholder="LHR")
            with sc2:
                split_out = st.date_input(_t("תאריך יציאה", "Departure date"), key="split_out")
                split_ret = st.date_input(_t("תאריך חזרה", "Return date"), key="split_ret")
            split_btn = st.form_submit_button(_t("✂️ השווה", "✂️ Compare"), use_container_width=True, type="primary")

        if split_btn and split_dest:
            with st.spinner(_t("🤖 Claude משווה מחירים... (30-60 שניות)", "🤖 Claude comparing prices... (30-60 seconds)")):
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
                c1.metric(_t("הלוך-חזור", "Round-trip"), f"${result.get('roundtrip_price', 0):,}")
                c2.metric(
                    _t("שני חד-כיווניים", "Two one-ways"),
                    f"${result.get('split_total', 0):,}",
                    delta=f"-${savings:,.0f}" if savings > 0 else f"+${-savings:,.0f}",
                    delta_color="normal" if savings > 0 else "inverse",
                )
                c3.metric(_t("חיסכון", "Savings"), f"${savings:,.0f} ({result.get('savings_pct', 0):.1f}%)")

                st.divider()
                if rec == "split":
                    st.success(f"✅ **{_t('Split Ticket משתלם!', 'Split Ticket wins!')}** {_t('חסכון של', 'Saving')} ${savings:,.0f}")
                else:
                    st.info(f"ℹ️ **{_t('הלוך-חזור עדיף', 'Round-trip is better')}** {_t('במקרה זה', 'in this case')}")

                st.markdown(f"**{_t('נימוק', 'Reasoning')}:** {result.get('reasoning', '')}")

                lc1, lc2 = st.columns(2)
                with lc1:
                    if result.get("book_out_url"):
                        st.link_button(_t("✈️ הזמן יציאה", "✈️ Book outbound"), result["book_out_url"])
                with lc2:
                    if result.get("book_return_url"):
                        st.link_button(_t("✈️ הזמן חזרה", "✈️ Book return"), result["book_return_url"])

    # ── Nearby Airports ─────────────────────────────────────────────────────
    with tool_tab[1]:
        st.subheader(_t("🏙️ השווה שדות תעופה — TLV / SDV / ETH / HFA", "🏙️ Compare Airports — TLV / SDV / ETH / HFA"))
        st.caption(_t("לפעמים טיסה מאילת או חיפה זולה יותר מנתב\"ג", "Sometimes flying from Eilat or Haifa is cheaper than Ben Gurion"))

        with st.form("nearby_form"):
            na_c1, na_c2, na_c3 = st.columns(3)
            with na_c1:
                na_dest = st.text_input(_t("יעד", "Destination"), placeholder="ATH, FCO, BCN...")
            with na_c2:
                na_date = st.date_input(_t("תאריך יציאה", "Departure date"), key="na_date")
            with na_c3:
                na_ret = st.date_input(_t("תאריך חזרה (אופציונלי)", "Return date (optional)"), value=None, key="na_ret")
            na_btn = st.form_submit_button(_t("🔍 השווה", "🔍 Compare"), use_container_width=True, type="primary")

        if na_btn and na_dest:
            with st.spinner(_t("🤖 Claude בודק כל שדות התעופה...", "🤖 Claude checking all airports...")):
                airports = smart_search.check_nearby_airports(
                    destination=na_dest,
                    date=str(na_date),
                    return_date=str(na_ret) if na_ret else "",
                )

            if not airports:
                st.warning(_t("לא נמצאו תוצאות. ודא שהיעד נכון.", "No results found. Check the destination."))
            else:
                cheapest = airports[0]
                st.success(f"🏆 {_t('הכי זול', 'Cheapest')}: **{cheapest['airport_name']}** — ${cheapest['price']:,}")
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
                        f"{'(' + _t('הכי זול', 'Cheapest') + ' ✅)' if is_best else f'(+${savings_vs_best:,})'}"
                        f"{'  ' + ap.get('notes','') if ap.get('notes') else ''}</small>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    # ── Last Minute ─────────────────────────────────────────────────────────
    with tool_tab[2]:
        st.subheader(_t("⏰ Last Minute — דילים לשבוע הקרוב", "⏰ Last Minute — Deals for the Coming Week"))
        st.caption(_t("חברות תעופה מוכרות כרטיסים ריקים בזול ברגע האחרון", "Airlines sell empty seats cheap at the last minute"))

        with st.form("lm_form"):
            lm_c1, lm_c2, lm_c3 = st.columns(3)
            with lm_c1:
                lm_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
            with lm_c2:
                lm_days = st.slider(_t("כמה ימים קדימה", "Days ahead"), 3, 14, 7)
            with lm_c3:
                lm_max = st.number_input(_t("מחיר מקסימלי ($)", "Max price ($)"), value=300, min_value=50, step=50)
            lm_btn = st.form_submit_button(_t("⏰ מצא Last Minute", "⏰ Find Last Minute"), use_container_width=True, type="primary")

        if lm_btn:
            with st.spinner(f"🤖 Claude {_t('מחפש דילי last-minute ל', 'searching last-minute deals for the next')}-{lm_days} {_t('הימים הקרובים...', 'days...')}"):
                deals = smart_search.find_last_minute_deals(
                    origin=lm_origin,
                    days_ahead=lm_days,
                    max_price=lm_max,
                )

            if not deals:
                st.info(f"{_t('לא נמצאו דילים מתחת ל', 'No deals found below')}-${lm_max}. {_t('נסה להגדיל את המחיר המקסימלי.', 'Try increasing the max price.')}")
            else:
                st.success(f"🎉 {_t('נמצאו', 'Found')} {len(deals)} {_t('דילי last-minute!', 'last-minute deals!')}")
                import pandas as pd
                df = pd.DataFrame(deals)
                display_cols = [c for c in ["destination", "departure_date", "price", "airline", "seats_left", "deal_type", "why_cheap"] if c in df.columns]
                st.dataframe(df[display_cols] if display_cols else df, use_container_width=True, hide_index=True)

                for d in deals[:3]:
                    if not isinstance(d, dict): continue
                    with st.expander(f"✈️ {d.get('destination','')} — ${d.get('price',0):,} ({d.get('departure_date','')})"):
                        st.markdown(f"**{_t('חברה', 'Airline')}:** {d.get('airline','')}")
                        st.markdown(f"**{_t('סיבת הזול', 'Why cheap')}:** {d.get('why_cheap','')}")
                        if d.get("seats_left"):
                            st.warning(f"⚠️ {_t('נותרו', 'Only')} {d['seats_left']} {_t('מקומות!', 'seats left!')}")
                        if d.get("book_by"):
                            st.caption(f"⏰ {_t('הזמן עד', 'Book by')}: {d['book_by']}")

    # ── Cheapest Day ─────────────────────────────────────────────────────────
    with tool_tab[3]:
        st.subheader(_t("📆 איזה יום בשבוע הכי זול?", "📆 Which day of the week is cheapest?"))
        st.caption(_t("ניתוח ממוצע מחירים לפי יום שבוע — תחסוך עד 30%", "Average price analysis by weekday — save up to 30%"))

        with st.form("cheap_day_form"):
            cd_c1, cd_c2, cd_c3 = st.columns(3)
            with cd_c1:
                cd_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
            with cd_c2:
                cd_dest = st.text_input(_t("יעד", "Destination"), placeholder="BCN")
            with cd_c3:
                cd_month = st.text_input(_t("חודש (YYYY-MM)", "Month (YYYY-MM)"), value=datetime.now().strftime("%Y-%m"))
            cd_btn = st.form_submit_button(_t("📆 נתח ימים", "📆 Analyze Days"), use_container_width=True, type="primary")

        if cd_btn and cd_dest:
            with st.spinner(_t("🤖 Claude מנתח מחירים לפי ימי שבוע...", "🤖 Claude analyzing prices by weekday...")):
                result = smart_search.find_cheapest_day_of_week(
                    origin=cd_origin,
                    destination=cd_dest,
                    month=cd_month,
                )

            if "error" in result:
                st.error(result["error"])
            elif not result:
                st.warning(_t("לא נמצאו נתונים", "No data found"))
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric(_t("יום הכי זול", "Cheapest day"), result.get("cheapest_day", ""))
                c2.metric(_t("יום הכי יקר", "Most expensive day"), result.get("most_expensive_day", ""))
                c3.metric(
                    _t("חיסכון פוטנציאלי", "Potential savings"),
                    f"${result.get('savings_by_day', 0):,}",
                    delta=f"-{result.get('savings_pct', 0):.0f}%",
                )

                st.info(f"💡 {result.get('tip', '')}")
                if result.get("best_time"):
                    st.caption(f"⏰ {_t('שעה מומלצת', 'Recommended time')}: {result['best_time']}")

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
        st.subheader(_t("📦 חבילה מאורגנת vs. הזמנה עצמאית", "📦 Package vs. Independent Booking"))
        st.caption(_t("מחשב אם Gulliver/IsraFlight/Dan זול יותר מלהזמין לבד", "Calculates if Gulliver/IsraFlight/Dan is cheaper than booking independently"))

        with st.form("pkg_form"):
            pk_c1, pk_c2 = st.columns(2)
            with pk_c1:
                pk_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
                pk_dest = st.text_input(_t("יעד", "Destination"), placeholder=_t("פראג", "Prague"))
                pk_travelers = st.number_input(_t("נוסעים", "Travelers"), value=2, min_value=1, max_value=10)
            with pk_c2:
                pk_from = st.date_input(_t("תאריך יציאה", "Departure date"), key="pk_from")
                pk_to = st.date_input(_t("תאריך חזרה", "Return date"), key="pk_to")
            pk_btn = st.form_submit_button(_t("📦 השווה", "📦 Compare"), use_container_width=True, type="primary")

        if pk_btn and pk_dest:
            with st.spinner(_t("🤖 Claude משווה חבילה vs. עצמאי... (30-60 שניות)", "🤖 Claude comparing package vs. independent... (30-60 seconds)")):
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
                st.warning(_t("לא נמצאו נתונים", "No data found"))
            else:
                rec = result.get("recommendation", "")
                pkg_price = result.get("package_price", 0)
                sep_price = result.get("separate_total", 0)
                saving_pkg = result.get("savings_with_package", 0)
                saving_sep = result.get("savings_with_separate", 0)

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric(
                        f"📦 {_t('חבילה', 'Package')} ({result.get('package_provider', '')})",
                        f"${pkg_price:,}",
                        delta=f"-${saving_pkg:,}" if saving_pkg > 0 else None,
                    )
                    includes = result.get("package_includes", [])
                    if includes:
                        st.caption(_t("כולל", "Includes") + ": " + " | ".join(includes[:3]))
                with c2:
                    st.metric(
                        _t("🎒 הזמנה עצמאית", "🎒 Independent booking"),
                        f"${sep_price:,}",
                        delta=f"-${saving_sep:,}" if saving_sep > 0 else None,
                    )
                    st.caption(
                        f"✈️ {_t('טיסה', 'Flight')}: ${result.get('separate_flight',0):,} | "
                        f"🏨 {_t('מלון', 'Hotel')}: ${result.get('separate_hotel_total',0):,}"
                    )
                with c3:
                    winner = _t("📦 חבילה", "📦 Package") if rec == "package" else _t("🎒 עצמאי", "🎒 Independent")
                    st.markdown(
                        f"<div style='text-align:center;padding:20px;background:rgba(0,255,136,0.1);"
                        f"border-radius:10px;border:1px solid #00ff88'>"
                        f"<h3 style='color:#00ff88;margin:0'>✅ {winner}</h3>"
                        f"<small>{_t('המומלץ', 'Recommended')}</small></div>",
                        unsafe_allow_html=True,
                    )

                st.markdown(f"**{_t('נימוק', 'Reasoning')}:** {result.get('reasoning', '')}")

                tips = result.get("tips", [])
                if tips:
                    st.subheader(_t("💡 טיפים", "💡 Tips"))
                    for tip in tips:
                        st.markdown(f"• {tip}")

    # ── Best Time to Book ────────────────────────────────────────────────────
    with tool_tab[5]:
        st.subheader(_t("📅 מתי הכי כדאי להזמין?", "📅 When is the best time to book?"))
        st.caption(_t("ניתוח נתוני עבר: כמה שבועות לפני הטיסה המחיר הכי נמוך?", "Historical data analysis: how many weeks before the flight is the price lowest?"))

        with st.form("btb_form"):
            btb_c1, btb_c2, btb_c3 = st.columns(3)
            with btb_c1:
                btb_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
            with btb_c2:
                btb_dest = st.text_input(_t("יעד", "Destination"), placeholder="NYC, BKK, LON...")
            with btb_c3:
                btb_month = st.text_input(_t("חודש נסיעה (אופציונלי)", "Travel month (optional)"), placeholder=_t("יולי 2025", "July 2025"))
            btb_btn = st.form_submit_button(_t("📅 נתח", "📅 Analyze"), use_container_width=True, type="primary")

        if btb_btn and btb_dest:
            with st.spinner(_t("🤖 Claude מנתח דפוסי מחיר היסטוריים...", "🤖 Claude analyzing historical price patterns...")):
                result = smart_search.best_time_to_book(btb_origin, btb_dest, btb_month)

            if "error" in result:
                st.error(result["error"])
            elif not result:
                st.warning(_t("לא נמצאו נתונים", "No data found"))
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric(_t("⭐ זמן מיטבי", "⭐ Optimal time"), f"{result.get('optimal_weeks_before', '?')} {_t('שבועות לפני', 'weeks before')}")
                c2.metric(_t("💰 חיסכון פוטנציאלי", "💰 Potential savings"), f"{result.get('potential_savings_pct', 0)}%")
                c3.metric(_t("⚠️ הגרוע ביותר", "⚠️ Worst time"), result.get("worst_time", ""))

                st.success(f"**{_t('כלל אצבע', 'Rule of thumb')}:** {result.get('rule_of_thumb', '')}")

                if result.get("seasonal_advice"):
                    st.info(f"📆 {result['seasonal_advice']}")
                if result.get("last_minute_exception"):
                    st.caption(f"🎲 {_t('חריג', 'Exception')}: {result['last_minute_exception']}")
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
                                  annotation_text=_t("מחיר מיטבי", "Optimal price"))
                    fig.update_layout(
                        title=dict(text=_t("📉 מחיר יחסי לפי זמן הזמנה (1.0 = הכי זול)", "📉 Relative price by booking time (1.0 = cheapest)"), font=dict(color="white", size=13)),
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
    st.title(_t("🔍 השוואת אתרים — Kayak vs. Expedia vs. Google Flights", "🔍 Site Comparison — Kayak vs. Expedia vs. Google Flights"))
    st.caption(_t("אותה טיסה, 5 אתרים שונים — מי הכי זול?", "Same flight, 5 different sites — who's cheapest?"))

    with st.form("comp_form"):
        cc1, cc2 = st.columns(2)
        with cc1:
            comp_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
            comp_dest = st.text_input(_t("יעד *", "Destination *"), placeholder="NYC, LON, BKK...")
            comp_travelers = st.number_input(_t("נוסעים", "Travelers"), value=1, min_value=1, max_value=9)
        with cc2:
            comp_out = st.date_input(_t("תאריך יציאה", "Departure date"))
            comp_ret = st.date_input(_t("תאריך חזרה (ריק = חד-כיווני)", "Return date (empty = one-way)"), value=None)
            comp_cat = st.selectbox(_t("סוג", "Type"), ["flight", "hotel"],
                                     format_func=lambda x: _t("✈️ טיסה", "✈️ Flight") if x == "flight" else _t("🏨 מלון", "🏨 Hotel"))
        comp_btn = st.form_submit_button(_t("🔍 השווה בכל האתרים", "🔍 Compare all sites"), use_container_width=True, type="primary")

    if comp_btn and comp_dest:
        with st.spinner(_t("🤖 Claude מחפש בכל האתרים בו-זמנית... (60-90 שניות)", "🤖 Claude searching all sites simultaneously... (60-90 seconds)")):
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
            st.error(f"{_t('לא נמצאו תוצאות.', 'No results found.')} {err}")
        else:
            cheapest = results[0]
            st.success(
                f"🏆 {_t('הכי זול', 'Cheapest')}: **{cheapest.get('site','')}** — "
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
                    + (_t("✈️ ישיר", "✈️ Direct") if r.get('stops') == 0 else _t(f"{r.get('stops',0)} עצירות", f"{r.get('stops',0)} stop(s)"))
                    + f" | {r.get('duration_hours',0):.1f}h | {r.get('notes','')[:60]}</small>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if r.get("url"):
                    st.link_button(f"🔗 {_t('הזמן ב', 'Book at')}-{r['site']}", r["url"])
                st.markdown("")

            # Summary table
            import pandas as pd
            st.divider()
            with st.expander(_t("📋 טבלת השוואה", "📋 Comparison table")):
                df_cols = ["site", "price", "currency", "airline", "stops", "duration_hours", "notes"]
                df = pd.DataFrame([{c: r.get(c, "") for c in df_cols} for r in results])
                df.columns = [_t("אתר", "Site"), _t("מחיר", "Price"), _t("מטבע", "Currency"), _t("חברה", "Airline"), _t("עצירות", "Stops"), _t("שעות טיסה", "Flight hours"), _t("הערות", "Notes")]
                st.dataframe(df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Sentiment Analyzer
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📰 סנטימנט & חדשות":
    st.title(_t("📰 ניתוח סנטימנט — חדשות שמשפיעות על מחירים", "📰 Sentiment Analysis — News Affecting Prices"))
    st.caption(_t("Claude סורק חדשות: שביתות, בחירות, מזג אוויר, אירועים — ומנבא השפעה על מחירי טיסות", "Claude scans news: strikes, elections, weather, events — and predicts impact on flight prices"))

    with st.form("sent_form"):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            sent_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
        with sc2:
            sent_dest = st.text_input(_t("יעד *", "Destination *"), placeholder=_t("לונדון, NYC, בנגקוק...", "London, NYC, Bangkok..."))
        with sc3:
            sent_date = st.text_input(_t("תאריך טיסה מתוכנן", "Planned flight date"), placeholder=_t("יולי 2025", "July 2025"))
        sent_btn = st.form_submit_button(_t("📰 נתח חדשות & סנטימנט", "📰 Analyze News & Sentiment"), use_container_width=True, type="primary")

    if sent_btn and sent_dest:
        with st.spinner(_t("🤖 Claude סורק חדשות ומנתח השפעות... (30-60 שניות)", "🤖 Claude scanning news and analyzing impacts... (30-60 seconds)")):
            raw = sentiment_analyzer.analyze_sentiment(sent_origin, sent_dest, sent_date)
            fmt = sentiment_analyzer.format_sentiment(raw)

        if not fmt or "error" in raw:
            st.error(raw.get("error", _t("לא ניתן לנתח", "Cannot analyze")))
        else:
            # Main verdict
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:2.5em'>{fmt['sentiment_icon']}</div>"
                    f"<b style='color:{fmt['sentiment_color']}'>{fmt['sentiment'].upper()}</b><br>"
                    f"<small>{_t('סנטימנט שוק', 'Market sentiment')}</small></div>",
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:2em'>{fmt['impact_icon']}</div>"
                    f"<b>{_t('מחירים עולים', 'Prices rising') if fmt['price_impact']=='rising' else _t('מחירים יורדים', 'Prices falling') if fmt['price_impact']=='falling' else _t('יציב', 'Stable')}</b><br>"
                    f"<span style='color:#00ff88'>{fmt['impact_pct']:+.0f}%</span> {_t('צפוי', 'expected')}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with c3:
                risk_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(fmt["risk_level"], "⚪")
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:2em'>{risk_icon}</div>"
                    f"<b style='color:{fmt['risk_color']}'>{_t('סיכון', 'Risk')} {fmt['risk_level']}</b><br>"
                    f"<small>{_t('רמת אי-וודאות', 'Uncertainty level')}</small></div>",
                    unsafe_allow_html=True,
                )
            with c4:
                conf_color = {"high": "#00ff88", "medium": "#ffd93d", "low": "#ff6b6b"}.get(fmt["confidence"], "#aaa")
                st.markdown(
                    f"<div class='metric-card'>"
                    f"<div style='font-size:1.5em'>🎯</div>"
                    f"<b style='color:{conf_color}'>{fmt['recommendation']}</b><br>"
                    f"<small>{_t('ביטחון', 'Confidence')}: {fmt['confidence']}</small></div>",
                    unsafe_allow_html=True,
                )

            st.divider()

            # Reasoning
            st.markdown(f"### 💡 {_t('ניתוח', 'Analysis')}\n{fmt['reasoning']}")
            if fmt.get("best_booking_window"):
                st.success(f"📅 **{_t('מתי להזמין', 'When to book')}:** {fmt['best_booking_window']}")

            # Key events
            events = fmt.get("key_events", [])
            if events:
                st.divider()
                st.subheader(f"📌 {len(events)} {_t('אירועים מרכזיים', 'key events')}")
                event_type_icons = {
                    "strike": "✊", "event": "🎭", "weather": "🌩️",
                    "political": "🏛️", "seasonal": "📅", "economic": "💹",
                }
                impact_colors = {"negative": "#ff4444", "positive": "#00ff88", "neutral": "#aaaaaa"}
                magnitude_labels = {"high": _t("השפעה גבוהה", "High impact"), "medium": _t("בינונית", "Medium"), "low": _t("נמוכה", "Low")}

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
                title={"text": _t("ציון סנטימנט (0=זול, 10=יקר)", "Sentiment score (0=cheap, 10=expensive)"), "font": {"color": "white"}},
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
    st.title(_t("⏰ דילים שפגים בקרוב", "⏰ Expiring Deals"))
    st.caption(_t("התראות על דילים שעומדים לפוג — כדי שלא תפספס", "Alerts for deals about to expire — so you don't miss out"))

    if st.session_state.monitor_running:
        st_autorefresh(interval=300_000, key="expiry_refresh")  # refresh every 5 min

    hours_window = st.slider(_t("הצג דילים שפגים בתוך כמה שעות", "Show deals expiring within how many hours"), 1, 24, 3)

    expiring = deal_hunter.get_expiring_deals(hours_ahead=hours_window)

    col_exp, col_all = st.columns([1, 1])
    with col_exp:
        st.metric(_t("דילים שפגים בקרוב", "Deals expiring soon"), len(expiring), delta=None)
    with col_all:
        all_deals = deal_hunter.get_recent_deals(limit=200, min_score=0)
        st.metric(_t("סה״כ דילים במאגר", "Total deals in database"), len(all_deals))

    st.divider()

    if not expiring:
        st.success(f"✅ {_t('אין דילים שפגים בתוך', 'No deals expiring within')} {hours_window} {_t('השעות הקרובות', 'hours')}")
        st.caption(_t("הרץ 'ציד דילים' כדי לאסוף דילים חדשים עם תאריך תפוגה", "Run 'Deal Hunter' to collect new deals with expiry dates"))
    else:
        st.warning(f"⚠️ {len(expiring)} {_t('דיל/ים פגים בתוך', 'deal(s) expiring within')} {hours_window} {_t('שעות!', 'hours!')}")
        for d in expiring:
            mins = d.get("expires_in_minutes", 60)
            urgency_color = "#ff4444" if mins <= 30 else "#ffcc00" if mins <= 60 else "#ffa500"
            time_str = f"~{mins} {_t('דקות', 'minutes')}" if mins < 120 else f"~{mins//60} {_t('שעות', 'hours')}"

            st.markdown(
                f"<div style='background:rgba(255,75,75,0.1);border:1px solid {urgency_color};"
                f"border-radius:10px;padding:14px 18px;margin-bottom:10px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<b style='font-size:1.1em'>✈️ {d.get('destination','')} ({d.get('destination_code','')})</b>"
                f"<b style='color:{urgency_color}'>⏰ {_t('פג בעוד', 'Expires in')} {time_str}</b>"
                f"</div>"
                f"<span style='font-size:1.4em;color:#00ff88'>${d.get('price',0):,.0f}</span>"
                f" | {d.get('airline','')} | {_t('ציון', 'Score')}: {d.get('score',0):.1f}/10<br>"
                f"<small style='color:#aaa'>{d.get('why_amazing','')[:100]}</small><br>"
                f"<small>{_t('פג', 'Expires')}: {d.get('expires','')}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )
            bc1, bc2 = st.columns(2)
            if d.get("book_url"):
                with bc1:
                    st.link_button(_t("🔗 הזמן עכשיו!", "🔗 Book Now!"), d["book_url"])
            with bc2 if d.get("book_url") else bc1:
                if st.button(_t("📲 שלח התראה", "📲 Send Alert"), key=f"alert_exp_{d.get('id',0)}"):
                    import notifiers
                    msg = deal_scorer.format_deal_alert(d)
                    notifiers.broadcast(f"⏰ {_t('דיל פג בעוד', 'Deal expires in')} {time_str}!", msg)
                    st.success(_t("נשלחה התראה!", "Alert sent!"))

    # All deals with expiry
    st.divider()
    with st.expander(_t("📋 כל הדילים עם תאריך תפוגה", "📋 All deals with expiry date")):
        deals_with_expiry = [d for d in all_deals if d.get("expires")]
        if not deals_with_expiry:
            st.info(_t("אין דילים עם תאריך תפוגה מוגדר", "No deals with expiry date defined"))
        else:
            import pandas as pd
            df = pd.DataFrame(deals_with_expiry)
            cols = [c for c in ["destination", "price", "airline", "deal_type", "expires", "score"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Visa Check
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🛂 בדיקת ויזה":
    st.title(_t("🛂 בדיקת ויזה — דרכון ישראלי", "🛂 Visa Check — Israeli Passport"))
    st.caption(_t("בדוק דרישות כניסה לכל יעד עבור בעלי דרכון ישראלי", "Check entry requirements for every destination for Israeli passport holders"))

    STATUS_ICONS = {
        "visa_free": ("✅", "#00ff88", _t("ללא ויזה", "Visa-free")),
        "visa_on_arrival": ("🟡", "#ffd93d", _t("ויזה בהגעה", "Visa on arrival")),
        "e_visa": ("🔵", "#74b9ff", "eVisa"),
        "visa_required": ("🔴", "#ff6b6b", _t("ויזה נדרשת", "Visa required")),
        "not_allowed": ("⛔", "#ff0000", _t("כניסה אסורה", "Entry not allowed")),
    }

    # Quick multi-check or single destination
    vc_tab1, vc_tab2 = st.tabs([_t("🔍 יעד אחד", "🔍 Single destination"), _t("📋 בדיקה מרובה", "📋 Multiple check")])

    with vc_tab1:
        with st.form("visa_single"):
            vc_dest = st.text_input(_t("יעד *", "Destination *"), placeholder=_t("תאילנד, יפן, ארה״ב, מרוקו...", "Thailand, Japan, USA, Morocco..."))
            vc_btn = st.form_submit_button(_t("🛂 בדוק ויזה", "🛂 Check Visa"), use_container_width=True, type="primary")

        if vc_btn and vc_dest:
            with st.spinner(f"🤖 Claude {_t('בודק דרישות כניסה ל', 'checking entry requirements for')}{vc_dest}..."):
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
                    st.metric(_t("תקופת שהות מקס׳", "Max stay"), f"{result.get('max_stay_days', '?')} {_t('ימים', 'days')}")
                with dc2:
                    cost = result.get("visa_cost_usd", 0)
                    st.metric(_t("עלות ויזה", "Visa cost"), f"${cost}" if cost else _t("חינם", "Free"))
                with dc3:
                    proc = result.get("processing_days", 0)
                    st.metric(_t("זמן עיבוד", "Processing time"), f"{proc} {_t('ימים', 'days')}" if proc else _t("מיידי", "Immediate"))

                st.divider()

                reqs = result.get("requirements", [])
                notes = result.get("important_notes", [])
                rc1, rc2 = st.columns(2)
                with rc1:
                    if reqs:
                        st.subheader(_t("📄 מסמכים נדרשים", "📄 Required Documents"))
                        for r in reqs:
                            st.markdown(f"• {r}")
                with rc2:
                    if notes:
                        st.subheader(_t("⚠️ הערות חשובות", "⚠️ Important Notes"))
                        for n in notes:
                            st.warning(n)

                if result.get("embassy_info"):
                    st.info(f"🏛️ **{_t('שגרירות', 'Embassy')}:** {result['embassy_info']}")

                conf_color = {"high": "#00ff88", "medium": "#ffd93d", "low": "#ff6b6b"}.get(
                    result.get("confidence", "low"), "#aaa"
                )
                st.caption(
                    f"<span style='color:{conf_color}'>{_t('מקור', 'Source')}: {result.get('source','')} | "
                    f"{_t('עדכון', 'Updated')}: {result.get('last_updated','')} | {_t('ביטחון', 'Confidence')}: {result.get('confidence','')}</span>"
                    f"<br><small>⚠️ {_t('המידע לצורך הכוונה בלבד. בדוק תמיד מול משרד החוץ לפני נסיעה.', 'Information for guidance only. Always verify with the Foreign Ministry before travel.')}</small>",
                    unsafe_allow_html=True,
                )

    with vc_tab2:
        st.caption(_t("בדוק מספר יעדים בו-זמנית", "Check multiple destinations simultaneously"))
        multi_dests = st.text_area(
            _t("יעדים (כל יעד בשורה)", "Destinations (one per line)"),
            placeholder=_t("תאילנד\nיפן\nארה״ב\nמרוקו\nהודו", "Thailand\nJapan\nUSA\nMorocco\nIndia"),
            height=150,
        )
        if st.button(_t("🛂 בדוק הכל", "🛂 Check All"), use_container_width=True, type="primary", key="visa_multi_btn"):
            dest_list = [d.strip() for d in multi_dests.splitlines() if d.strip()]
            if not dest_list:
                st.error(_t("הכנס לפחות יעד אחד", "Enter at least one destination"))
            else:
                results_multi = []
                progress = st.progress(0)
                for i, dest in enumerate(dest_list):
                    with st.spinner(f"{_t('בודק', 'Checking')} {dest}..."):
                        r = visa_check.check_visa(dest)
                        r["destination_query"] = dest
                        results_multi.append(r)
                    progress.progress((i + 1) / len(dest_list))

                st.success(f"✅ {_t('נבדקו', 'Checked')} {len(results_multi)} {_t('יעדים', 'destinations')}")
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
                            f"{stay} {_t('ימים', 'days')}"
                            f"{f' | ${cost}' if cost else ''}"
                        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Settings
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ הגדרות":
    st.title(_t("⚙️ הגדרות", "⚙️ Settings"))

    # ── API Key ────────────────────────────────────────────────────────────────
    st.subheader(_t("🔑 מפתח Gemini API", "🔑 Gemini API Key"))
    api_key_val = os.environ.get("GEMINI_API_KEY", "")
    if api_key_val:
        st.success(f"{_t('מוגדר', 'Configured')} ✅  (AIza...{api_key_val[-6:]})")
    else:
        new_key = st.text_input(_t("הכנס Gemini API Key", "Enter Gemini API Key"), type="password")
        if st.button(_t("שמור API Key", "Save API Key")) and new_key:
            _save_env("GEMINI_API_KEY", new_key)
            st.success(_t("נשמר! רענן את הדף.", "Saved! Refresh the page."))

    # ── Kiwi API (real flight prices) ──────────────────────────────────────────
    st.subheader(_t("✈️ Kiwi API — מחירי טיסות אמיתיים", "✈️ Kiwi API — Real Flight Prices"))
    st.markdown(_t(
        "Kiwi Tequila API מחזיר מחירים **אמיתיים** לטיסות — לא הערכות AI. "
        "חינמי עד 1,000 בקשות ביום.",
        "Kiwi Tequila API returns **real** flight prices — not AI estimates. "
        "Free up to 1,000 requests/day.",
    ))

    _kiwi_key = os.environ.get("KIWI_API_KEY", "")
    if _kiwi_key:
        st.success(_t("✅ Kiwi API מוגדר — מחירים אמיתיים פעילים!", "✅ Kiwi API configured — real prices active!"))
        if st.button(_t("🗑 הסר Kiwi Key", "🗑 Remove Kiwi Key"), key="remove_kiwi"):
            _save_env("KIWI_API_KEY", "")
            st.rerun()
    else:
        st.info(_t(
            "**איך מקבלים API Key (חינם):**\n\n"
            "1. לך ל-[tequila.kiwi.com](https://tequila.kiwi.com)\n"
            "2. הירשם (חינמי)\n"
            "3. צור חשבון → קבל **API Key**\n"
            "4. הכנס כאן:",
            "**How to get an API Key (free):**\n\n"
            "1. Go to [tequila.kiwi.com](https://tequila.kiwi.com)\n"
            "2. Sign up (free)\n"
            "3. Create account → get your **API Key**\n"
            "4. Enter it here:",
        ))
        _new_kiwi = st.text_input(
            _t("Kiwi API Key", "Kiwi API Key"),
            type="password",
            placeholder="your-kiwi-api-key",
            key="kiwi_key_input",
        )
        if st.button(_t("💾 שמור Kiwi Key", "💾 Save Kiwi Key"), key="save_kiwi") and _new_kiwi:
            _save_env("KIWI_API_KEY", _new_kiwi)
            st.success(_t("✅ נשמר! כל בדיקות הטיסות יחזירו עכשיו מחירים אמיתיים.", "✅ Saved! All flight checks will now return real prices."))
            st.rerun()

        # Test button even without key
        if st.button(_t("🧪 בדוק חיבור", "🧪 Test connection"), key="test_kiwi"):
            _test_key = _new_kiwi or _kiwi_key
            if not _test_key:
                st.warning(_t("הכנס API Key תחילה", "Enter API Key first"))
            else:
                with st.spinner(_t("בודק...", "Testing...")):
                    import urllib.request as _ur, urllib.parse as _up
                    _turl = (
                        "https://api.tequila.kiwi.com/v2/search?"
                        + _up.urlencode({"fly_from": "TLV", "fly_to": "BCN",
                                         "date_from": "01/09/2025", "date_to": "30/09/2025",
                                         "limit": 1, "curr": "USD"})
                    )
                    try:
                        _treq = _ur.Request(_turl, headers={"apikey": _test_key})
                        with _ur.urlopen(_treq, timeout=10) as _tr:
                            _td = __import__("json").loads(_tr.read())
                        if _td.get("data"):
                            _fp = _td["data"][0]
                            st.success(_t(
                                f"✅ עובד! TLV→BCN = ${_fp.get('price',0):.0f} ({_fp.get('airlines',['?'])[0] if isinstance(_fp.get('airlines'), list) else '?'})",
                                f"✅ Working! TLV→BCN = ${_fp.get('price',0):.0f} ({_fp.get('airlines',['?'])[0] if isinstance(_fp.get('airlines'), list) else '?'})",
                            ))
                        else:
                            st.warning(_t("מחובר אבל אין תוצאות", "Connected but no results"))
                    except Exception as _te:
                        st.error(f"❌ {_te}")

    st.divider()

    # ── Notifications ──────────────────────────────────────────────────────────
    st.subheader(_t("🔔 ערוצי התראה", "🔔 Notification Channels"))

    st.markdown(_t("""
כשמחיר יורד, ה-agent שולח התראה בכל הערוצים המוגדרים.
ניתן להגדיר כמה ערוצים שרוצים במקביל.
""", """
When a price drops, the agent sends an alert on all configured channels.
You can configure multiple channels simultaneously.
"""))

    # ntfy.sh ──────────────────────────────────────────────────────────────────
    with st.expander(_t("📱 **ntfy.sh** — פוש לנייד (חינמי, מומלץ!)", "📱 **ntfy.sh** — Push to mobile (free, recommended!)"), expanded=True):
        st.markdown(_t("""
**הכי קל להגדיר — ללא חשבון:**

1. הורד את אפליקציית **ntfy** לנייד:
   - [iOS (App Store)](https://apps.apple.com/us/app/ntfy/id1625396347)
   - [Android (Google Play)](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. פתח את האפליקציה → Subscribe to topic
3. הזן שם נושא ייחודי (לדוגמה: `megatraveller-שמך123`)
4. הכנס את אותו נושא כאן 👇
""", """
**Easiest to set up — no account needed:**

1. Download the **ntfy** app on your phone:
   - [iOS (App Store)](https://apps.apple.com/us/app/ntfy/id1625396347)
   - [Android (Google Play)](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. Open the app → Subscribe to topic
3. Enter a unique topic name (e.g. `noded-yourname123`)
4. Enter that same topic below 👇
"""))

        ntfy_topic = os.environ.get("NTFY_TOPIC", "")
        col1, col2 = st.columns([3, 1])
        with col1:
            new_ntfy = st.text_input(
                "ntfy Topic", value=ntfy_topic,
                placeholder="megatraveller-abc123",
                label_visibility="collapsed",
            )
        with col2:
            if st.button(_t("שמור", "Save"), key="save_ntfy") and new_ntfy:
                _save_env("NTFY_TOPIC", new_ntfy)
                st.success("✅")
                st.rerun()

        if ntfy_topic:
            st.success(f"{_t('מוגדר', 'Configured')}: ntfy.sh/{ntfy_topic}")

    # Browser Push ─────────────────────────────────────────────────────────────
    with st.expander(_t("🌐 **התראות בדפדפן**", "🌐 **Browser Notifications**"), expanded=False):
        st.markdown(_t("""
**התראות ישירות בדפדפן — כשהאפליקציה פתוחה:**

לחץ על הכפתור ואפשר התראות. הדפדפן ישאל אותך לאשר.
""", """
**Direct browser notifications — while the app is open:**

Click the button and allow notifications. The browser will ask you to confirm.
"""))
        components.html("""
<div style="font-family:sans-serif;padding:4px 0">
<button id="enable-push-btn" onclick="requestPushPermission()" style="
  background:linear-gradient(135deg,#667eea,#764ba2);
  color:white;border:none;padding:10px 20px;
  border-radius:8px;cursor:pointer;font-size:14px">
  🔔 אפשר התראות בדפדפן
</button>
<span id="push-status" style="margin-left:12px;font-size:13px;color:#aaa"></span>
<script>
function requestPushPermission() {
  var btn = document.getElementById('enable-push-btn');
  var status = document.getElementById('push-status');
  var doc = window.parent.document;
  if (!('Notification' in window.parent)) {
    status.textContent = '❌ הדפדפן לא תומך בהתראות';
    status.style.color = '#ff6b6b';
    return;
  }
  if (window.parent.Notification.permission === 'granted') {
    status.textContent = '✅ התראות מופעלות!';
    status.style.color = '#00ff88';
    new window.parent.Notification('Noded ✈️', {body: 'התראות מופעלות!', tag: 'noded-test'});
    return;
  }
  window.parent.Notification.requestPermission().then(function(perm) {
    if (perm === 'granted') {
      status.textContent = '✅ התראות מופעלות!';
      status.style.color = '#00ff88';
      new window.parent.Notification('Noded ✈️', {body: 'ירידת מחירים תופיע כאן!', tag: 'noded-test'});
    } else {
      status.textContent = '❌ ההרשאה נדחתה';
      status.style.color = '#ff6b6b';
    }
  });
}
// Auto-check current status
(function() {
  var status = document.getElementById('push-status');
  if (!('Notification' in window.parent)) {
    status.textContent = '❌ לא נתמך';
    return;
  }
  var p = window.parent.Notification.permission;
  if (p === 'granted') { status.textContent = '✅ מופעל'; status.style.color='#00ff88'; }
  else if (p === 'denied') { status.textContent = '❌ חסום בהגדרות הדפדפן'; status.style.color='#ff6b6b'; }
  else { status.textContent = '⏳ ממתין לאישור'; status.style.color='#f5a623'; }
})();
</script>
</div>
""", height=60)
        st.caption(_t(
            "💡 להתראות גם כשהאפליקציה סגורה — השתמש ב-ntfy.sh למעלה",
            "💡 For alerts even when the app is closed — use ntfy.sh above",
        ))

    # Weekly Digest ────────────────────────────────────────────────────────────
    with st.expander(_t("📧 **סיכום שבועי** — דוח AI על מחירים ודילים", "📧 **Weekly Digest** — AI price & deal report")):
        st.markdown(_t(
            "קבל סיכום שבועי עם AI: תנועות מחירים, הדיל הכי טוב, המלצות לשבוע הבא.",
            "Get a weekly AI-generated summary: price movements, best deal, recommendations for the coming week.",
        ))
        wd_col1, wd_col2 = st.columns(2)
        with wd_col1:
            if st.button(_t("📊 הצג סיכום עכשיו", "📊 Generate digest now"), key="show_digest"):
                with st.spinner(_t("מייצר סיכום עם AI...", "Generating digest with AI...")):
                    try:
                        digest = weekly_digest.generate_digest(_lang)
                        st.session_state["last_digest"] = digest
                    except Exception as e:
                        st.error(str(e))
        with wd_col2:
            if st.button(_t("📤 שלח סיכום (Telegram/ntfy)", "📤 Send digest (Telegram/ntfy)"), key="send_digest"):
                with st.spinner(_t("שולח...", "Sending...")):
                    try:
                        result = weekly_digest.send_digest(_lang)
                        if result.get("ok"):
                            st.success(_t("✅ הסיכום נשלח!", "✅ Digest sent!"))
                        else:
                            st.warning(_t("⚠️ " + result.get("error","שגיאה"), "⚠️ " + result.get("error","Error")))
                    except Exception as e:
                        st.error(str(e))

        if "last_digest" in st.session_state:
            d = st.session_state["last_digest"]
            st.markdown(f"### {d.get('subject','')}")
            st.markdown(d.get("summary",""))
            if d.get("top_movements"):
                st.markdown(_t("**📈 תנועות מחירים:**", "**📈 Price movements:**"))
                for m in d["top_movements"]:
                    st.markdown(f"- {m}")
            if d.get("best_deal"):
                st.info(f"🏆 {d['best_deal']}")
            if d.get("recommendations"):
                st.markdown(_t("**💡 המלצות:**", "**💡 Recommendations:**"))
                for r in d["recommendations"]:
                    st.markdown(f"- {r}")

    # Telegram ─────────────────────────────────────────────────────────────────
    with st.expander(_t("✈️ **Telegram** — הודעות לטלגרם", "✈️ **Telegram** — Telegram messages")):
        st.markdown(_t("""
**הגדרת בוט Telegram:**

1. פתח טלגרם → חפש **@BotFather**
2. שלח `/newbot` → בחר שם → קבל **Token**
3. פתח את הבוט שיצרת → שלח לו הודעה כלשהי
4. גש לכתובת:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   מצא את `"chat":{"id":...}` — זה ה-**Chat ID**
""", """
**Setting up a Telegram bot:**

1. Open Telegram → search for **@BotFather**
2. Send `/newbot` → choose a name → get your **Token**
3. Open the bot you created → send it any message
4. Go to:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Find `"chat":{"id":...}` — that's your **Chat ID**
"""))

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
        if st.button(_t("שמור Telegram", "Save Telegram"), key="save_tg"):
            if new_tg_token:
                _save_env("TELEGRAM_BOT_TOKEN", new_tg_token)
            if new_tg_chat:
                _save_env("TELEGRAM_CHAT_ID", new_tg_chat)
            st.success(f"✅ {_t('נשמר! רענן.', 'Saved! Refresh.')}")

        if tg_token and tg_chat:
            st.success(f"Telegram {_t('מוגדר', 'configured')} ✅")

    # ── Amadeus API ────────────────────────────────────────────────────────────
    st.divider()
    st.subheader(_t("✈️ Amadeus API — מחירים רשמיים", "✈️ Amadeus API — Official prices"))
    st.markdown(_t("""
**API רשמי של חברות תעופה ומלונות — מדויק פי 10 מחיפוש רגיל.**

**הרשמה חינמית (2,000 קריאות/חודש):**
1. גש ל-[developers.amadeus.com](https://developers.amadeus.com)
2. לחץ **Register** → צור חשבון חינמי
3. לחץ **Create new app** → קבל **Client ID** ו-**Client Secret**
4. הכנס כאן 👇
""", """
**Official airline & hotel API — 10x more accurate than regular search.**

**Free registration (2,000 calls/month):**
1. Go to [developers.amadeus.com](https://developers.amadeus.com)
2. Click **Register** → create a free account
3. Click **Create new app** → get your **Client ID** and **Client Secret**
4. Enter them below 👇
"""))

    am_id = os.environ.get("AMADEUS_CLIENT_ID", "")
    am_secret = os.environ.get("AMADEUS_CLIENT_SECRET", "")

    col1, col2 = st.columns(2)
    with col1:
        new_am_id = st.text_input(_t("מזהה לקוח", "Client ID"), value=am_id, placeholder="abc123...")
    with col2:
        new_am_secret = st.text_input(_t("סיסמת לקוח", "Client Secret"), value=am_secret,
                                       type="password", placeholder="xyz789...")

    colA, colB = st.columns(2)
    with colA:
        if st.button(_t("💾 שמור Amadeus", "💾 Save Amadeus"), key="save_am") and new_am_id:
            _save_env("AMADEUS_CLIENT_ID", new_am_id)
            _save_env("AMADEUS_CLIENT_SECRET", new_am_secret)
            load_dotenv(Path(__file__).parent / ".env", override=True)
            st.success("✅ " + _t("נשמר!", "Saved!"))
    with colB:
        if st.button(_t("🧪 בדוק חיבור Amadeus", "🧪 Test Amadeus connection"), key="test_am"):
            import amadeus_client
            load_dotenv(Path(__file__).parent / ".env", override=True)
            with st.spinner(_t("בודק...", "Testing...")):
                result = amadeus_client.test_connection()
            if result["ok"]:
                st.success(result.get("message", _t("✅ מחובר", "✅ Connected")))
            else:
                st.error(result.get("error", _t("שגיאה", "Error")))

    if am_id and am_secret:
        st.success(_t("Amadeus מוגדר ✅ — טיסות ומלונות יחפשו דרך API רשמי", "Amadeus configured ✅ — flights and hotels will search via official API"))
    else:
        st.info(_t("ללא Amadeus — המחירים יחפשו דרך Claude web search (פחות מדויק)", "Without Amadeus — prices will search via Claude web search (less accurate)"))

    # Test all ──────────────────────────────────────────────────────────────────
    st.divider()
    if st.button(_t("🧪 שלח הודעת בדיקה לכל הערוצים", "🧪 Send test message to all channels"), use_container_width=True):
        with st.spinner(_t("שולח...", "Sending...")):
            import alerts as alerts_module
            # Reload env
            load_dotenv(Path(__file__).parent / ".env", override=True)
            status = alerts_module.test_notifications()
        for channel, result in status.items():
            st.markdown(f"**{channel}**: {result}")

    st.divider()

    # ── Monitor ────────────────────────────────────────────────────────────────
    st.subheader(_t("🔄 ניטור אוטומטי", "🔄 Automatic Monitor"))
    st.info(
        _t(
            "הניטור הרציף בודק את כל הפריטים הפעילים בצורה אוטומטית.\n\n"
            "⚠️ כל בדיקה משתמשת ב-Claude API (עלות כ-$0.01-0.05 לפריט).\n"
            "מומלץ להגדיר מרווח של 60+ דקות.",
            "Continuous monitoring checks all active items automatically.\n\n"
            "⚠️ Each check uses the Claude API (cost ~$0.01-0.05 per item).\n"
            "Recommended interval: 60+ minutes."
        )
    )

    st.divider()
    st.subheader(_t("📊 סטטיסטיקות DB", "📊 DB Statistics"))
    items_all = db.get_all_watch_items(enabled_only=False)
    total_records = 0
    for it in items_all:
        hist = db.get_price_history(it["id"], limit=1000)
        total_records += len(hist)

    c1, c2, c3 = st.columns(3)
    c1.metric(_t("פריטי מעקב", "Watch items"), len(items_all))
    c2.metric(_t("רשומות מחיר", "Price records"), total_records)
    db_size = Path("prices.db").stat().st_size // 1024 if Path("prices.db").exists() else 0
    c3.metric(_t("גודל DB", "DB size"), f"{db_size} KB")

    st.divider()
    st.subheader(_t("🗑 ניהול נתונים", "🗑 Data Management"))
    if st.button(_t("מחק את כל הנתונים", "Delete all data"), type="secondary"):
        if st.session_state.get("confirm_delete"):
            import sqlite3
            with db.get_db() as conn:
                conn.executescript("DELETE FROM price_records; DELETE FROM watch_items;")
            st.success(_t("נמחק הכל", "All data deleted"))
            st.session_state.confirm_delete = False
        else:
            st.session_state.confirm_delete = True
            st.warning(_t("לחץ שוב לאישור מחיקה", "Click again to confirm deletion"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Price History
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 היסטוריית מחירים":
    import pandas as pd

    st.title(_t("📊 היסטוריית מחירים", "📊 Price History"))
    st.caption(_t("גרפים מפורטים, השוואת פריטים, סטטיסטיקות ומגמות", "Detailed charts, item comparison, statistics and trends"))

    items = db.get_all_watch_items(enabled_only=False)
    if not items:
        st.info(_t("הוסף פריטים ובדוק מחירים כדי לראות היסטוריה.", "Add items and check prices to see history."))
    else:
        item_map = {f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']} ({i['destination']})": i for i in items}

        # ── Controls ────────────────────────────────────────────────────────
        ctrl1, ctrl2, ctrl3 = st.columns([3, 1, 1])
        with ctrl1:
            selected_names = st.multiselect(
                _t("בחר פריטים להשוואה", "Select items to compare"),
                list(item_map.keys()),
                default=list(item_map.keys())[:1],
            )
        with ctrl2:
            history_limit = st.selectbox(_t("רשומות", "Records"), [30, 60, 100, 200, 500], index=1)
        with ctrl3:
            chart_type = st.selectbox(_t("סוג גרף", "Chart type"), [_t("קו", "Line"), _t("עמודות", "Bar"), _t("קו + נקודות", "Line + Points")])

        if not selected_names:
            st.info(_t("בחר לפחות פריט אחד", "Select at least one item"))
            st.stop()

        selected_items = [item_map[n] for n in selected_names]

        # ── Stats cards ─────────────────────────────────────────────────────
        st.divider()
        stat_cols = st.columns(len(selected_items))
        for col, item in zip(stat_cols, selected_items):
            stats = db.get_price_stats(item["id"])
            last = db.get_last_price(item["id"])
            if not stats or not last:
                col.info(f"{item['name']}: {_t('אין נתונים', 'No data')}")
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
                    f"<small>{_t('מינימום', 'Min')}: {stats['min_price']:,.0f} | {_t('מקסימום', 'Max')}: {stats['max_price']:,.0f}</small><br>"
                    f"<small>{_t('ממוצע', 'Avg')}: {stats['avg_price']:,.0f} | {stats['total_checks']} {_t('בדיקות', 'checks')}</small><br>"
                    f"<span style='color:{'#ff4444' if trend=='rising' else '#00ff88' if trend=='falling' else '#aaa'}'>"
                    f"{trend_icon} {_t('מגמה', 'Trend')}: {trend_pct:+.1f}%</span>"
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

            if chart_type == _t("עמודות", "Bar"):
                fig.add_trace(go.Bar(x=xs, y=ys, name=item["name"], marker_color=color))
            elif chart_type == _t("קו", "Line"):
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
                    name=_t("מחיר", "Price"), mode="lines",
                    line=dict(color="#667eea", width=2),
                    fill="tozeroy", fillcolor="rgba(102,126,234,0.08)",
                ))
                fig2.add_trace(go.Scatter(
                    x=xs, y=ma.tolist(),
                    name=_t("ממוצע נע (5)", "Moving avg (5)"), mode="lines",
                    line=dict(color="#ffd93d", width=1.5, dash="dot"),
                ))
                fig2.update_layout(
                    title=dict(text=_t("📉 ממוצע נע", "📉 Moving Average"), font=dict(color="white", size=13)),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
                    font=dict(color="#ccc"), height=220,
                    margin=dict(l=10, r=10, t=35, b=10),
                    legend=dict(bgcolor="rgba(0,0,0,0)"),
                )
                st.plotly_chart(fig2, use_container_width=True)

        # ── Raw data table ──────────────────────────────────────────────────
        with st.expander(_t("📋 טבלת נתונים גולמיים", "📋 Raw data table")):
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
    st.title(_t("🎯 כללי התראה חכמים", "🎯 Smart Alert Rules"))
    st.caption(_t("הגדר תנאים מורכבים: התרע רק כשמחיר מתחת ל-X + ירידה של Y% + ביום מסוים", "Set complex conditions: alert only when price below X + drop of Y% + on a specific day"))

    items = db.get_all_watch_items(enabled_only=False)

    tab_new, tab_list = st.tabs([_t("➕ כלל חדש", "➕ New Rule"), _t("📋 כללים קיימים", "📋 Existing Rules")])

    # ── New Rule Form ────────────────────────────────────────────────────────
    with tab_new:
        with st.form("rule_form"):
            st.subheader(_t("הגדרת כלל חדש", "Define New Rule"))

            rule_name = st.text_input(
                _t("שם הכלל *", "Rule name *"),
                placeholder=_t("טיסה זולה לאירופה בסוף שבוע", "Cheap flight to Europe on weekend"),
            )

            # Which item
            item_options = {_t("כל הפריטים", "All items"): None}
            item_options.update({
                f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']}": i["id"]
                for i in items
            })
            rule_item = st.selectbox(_t("החל על", "Apply to"), list(item_options.keys()))

            st.divider()
            st.markdown(f"**{_t('תנאים', 'Conditions')}** ({_t('כל תנאי שמסומן חייב להתקיים', 'all checked conditions must be met')}):")

            rc1, rc2 = st.columns(2)
            with rc1:
                use_max_price = st.checkbox(_t("מחיר מקסימלי", "Maximum price"))
                max_price_val = st.number_input(_t("מחיר עד ($)", "Price up to ($)"), value=400, min_value=0, step=10,
                                                 disabled=not use_max_price)

                use_drop = st.checkbox(_t("ירידת מחיר מינימלית", "Minimum price drop"))
                min_drop_val = st.slider(_t("ירידה מינימלית (%)", "Minimum drop (%)"), 5, 60, 15,
                                          disabled=not use_drop)

                use_quality = st.checkbox(_t("איכות דיל מינימלית", "Minimum deal quality"))
                quality_val = st.selectbox(
                    _t("איכות מינימלית", "Minimum quality"),
                    ["average", "good", "excellent"],
                    format_func=lambda x: {"average": _t("⚠️ סביר", "⚠️ Fair"), "good": _t("✅ טוב", "✅ Good"), "excellent": _t("🔥 מעולה", "🔥 Excellent")}[x],
                    disabled=not use_quality,
                )

            with rc2:
                use_days = st.checkbox(_t("ימי שבוע ספציפיים", "Specific weekdays"))
                days_options = {
                    _t("ראשון", "Sunday"): 6, _t("שני", "Monday"): 0, _t("שלישי", "Tuesday"): 1,
                    _t("רביעי", "Wednesday"): 2, _t("חמישי", "Thursday"): 3, _t("שישי", "Friday"): 4, _t("שבת", "Saturday"): 5,
                }
                selected_days = st.multiselect(
                    _t("ימים", "Days"),
                    list(days_options.keys()),
                    default=[_t("שישי", "Friday"), _t("שבת", "Saturday")],
                    disabled=not use_days,
                )

                use_airlines = st.checkbox(_t("סנן לפי חברת תעופה", "Filter by airline"))
                airlines_include_str = st.text_input(
                    _t("חברות מועדפות (מופרד בפסיקים)", "Preferred airlines (comma separated)"),
                    placeholder="El Al, Ryanair, EasyJet",
                    disabled=not use_airlines,
                )
                airlines_exclude_str = st.text_input(
                    _t("חברות לחסימה (מופרד בפסיקים)", "Blocked airlines (comma separated)"),
                    placeholder="",
                    disabled=not use_airlines,
                )

                use_score = st.checkbox(_t("ציון AI מינימלי", "Minimum AI score"))
                min_score_val = st.slider(_t("ציון מינימלי (0-10)", "Minimum score (0-10)"), 0.0, 10.0, 7.0, 0.5,
                                           disabled=not use_score)

            rule_submit = st.form_submit_button(_t("➕ הוסף כלל", "➕ Add Rule"), use_container_width=True, type="primary")

        if rule_submit:
            if not rule_name:
                st.error(_t("הכנס שם לכלל", "Enter a rule name"))
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

                st.success(f"✅ {_t('כלל', 'Rule')} '{rule_name}' {_t('נוסף!', 'added!')} (ID: {rule_id})")

                # Preview
                cond_summary = []
                if "max_price" in conditions:
                    cond_summary.append(f"{_t('מחיר', 'Price')} ≤ ${conditions['max_price']}")
                if "min_drop_pct" in conditions:
                    cond_summary.append(f"{_t('ירידה', 'Drop')} ≥ {conditions['min_drop_pct']}%")
                if "min_deal_quality" in conditions:
                    cond_summary.append(f"{_t('איכות', 'Quality')} ≥ {conditions['min_deal_quality']}")
                if "days_of_week" in conditions:
                    day_names = ({6:"א׳",0:"ב׳",1:"ג׳",2:"ד׳",3:"ה׳",4:"ו׳",5:"ש׳"} if _lang=="he"
                                 else {6:"Sun",0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat"})
                    cond_summary.append(_t("ימים", "Days") + ": " + ", ".join(day_names.get(d,"?") for d in conditions["days_of_week"]))
                if "airlines_include" in conditions:
                    cond_summary.append(_t("חברות", "Airlines") + ": " + ", ".join(conditions["airlines_include"]))
                if "min_ai_score" in conditions:
                    cond_summary.append(f"{_t('ציון', 'Score')} ≥ {conditions['min_ai_score']}")

                if cond_summary:
                    st.info(_t("תנאים", "Conditions") + ": " + " | ".join(cond_summary))
                else:
                    st.warning(_t("לא הוגדרו תנאים — הכלל יופעל תמיד", "No conditions defined — rule will always trigger"))

    # ── Existing Rules List ──────────────────────────────────────────────────
    with tab_list:
        all_rules = db.get_alert_rules()

        if not all_rules:
            st.info(_t("אין כללים עדיין. צור כלל ב-'כלל חדש'.", "No rules yet. Create a rule in 'New Rule'."))
        else:
            st.caption(f"{len(all_rules)} {_t('כללים מוגדרים', 'rules defined')}")

            # Item name lookup
            item_names_by_id = {i["id"]: i["name"] for i in items}
            day_names = ({6: "א׳", 0: "ב׳", 1: "ג׳", 2: "ד׳", 3: "ה׳", 4: "ו׳", 5: "ש׳"} if _lang=="he"
                         else {6: "Sun", 0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat"})
            quality_labels = {"average": _t("⚠️ סביר", "⚠️ Fair"), "good": _t("✅ טוב", "✅ Good"), "excellent": _t("🔥 מעולה", "🔥 Excellent")}

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

                applies_to = item_names_by_id.get(rule.get("watch_id")) or _t("כל הפריטים", "All items")
                last_t = rule.get("last_triggered", "")
                last_t_str = f"{_t('הופעל', 'Triggered')}: {last_t[:16].replace('T',' ')}" if last_t else _t("לא הופעל עדיין", "Never triggered")

                with st.expander(
                    f"{status_icon} **{rule['name']}** | {applies_to} | {' '.join(tags) or _t('ללא תנאים', 'No conditions')}"
                ):
                    lc1, lc2, lc3 = st.columns(3)

                    with lc1:
                        st.markdown(f"**{_t('פריט', 'Item')}:** {applies_to}")
                        st.markdown(f"**{_t('נוצר', 'Created')}:** {rule['created_at'][:10]}")
                        st.caption(last_t_str)

                    with lc2:
                        st.markdown(f"**{_t('תנאים', 'Conditions')}:**")
                        if not cond:
                            st.caption(_t("ללא תנאים — מופעל תמיד", "No conditions — always triggers"))
                        for k, v in cond.items():
                            labels = {
                                "max_price": _t("💲 מחיר מקסימלי", "💲 Max price"),
                                "min_drop_pct": _t("📉 ירידה מינימלית", "📉 Min drop"),
                                "min_deal_quality": _t("⭐ איכות מינימלית", "⭐ Min quality"),
                                "days_of_week": _t("📅 ימי שבוע", "📅 Weekdays"),
                                "airlines_include": _t("✈️ חברות מועדפות", "✈️ Preferred airlines"),
                                "airlines_exclude": _t("🚫 חברות חסומות", "🚫 Blocked airlines"),
                                "min_ai_score": _t("🤖 ציון AI מינימלי", "🤖 Min AI score"),
                            }
                            display_v = v
                            if k == "days_of_week":
                                display_v = ", ".join(day_names.get(d, "?") for d in v)
                            elif k == "min_deal_quality":
                                display_v = quality_labels.get(v, v)
                            st.caption(f"{labels.get(k, k)}: **{display_v}**")

                    with lc3:
                        toggle_label = _t("⏸ השבת", "⏸ Disable") if is_enabled else _t("▶ הפעל", "▶ Enable")
                        if st.button(toggle_label, key=f"tog_rule_{rule['id']}"):
                            db.toggle_alert_rule(rule["id"], not is_enabled)
                            st.rerun()
                        if st.button(_t("🗑 מחק", "🗑 Delete"), key=f"del_rule_{rule['id']}"):
                            db.delete_alert_rule(rule["id"])
                            st.rerun()

            # Test rules
            st.divider()
            st.subheader(_t("🧪 בדוק כלל", "🧪 Test Rule"))
            st.caption(_t("הדמה של כלל מול מחיר קיים", "Simulate a rule against an existing price"))
            if items:
                test_item_name = st.selectbox(
                    _t("פריט לבדיקה", "Item to test"),
                    [f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']}" for i in items],
                    key="test_rule_item",
                )
                test_item = items[[f"{CAT_EMOJI.get(i['category'],'🔍')} {i['name']}" for i in items].index(test_item_name)]
                test_price = st.number_input(_t("מחיר לבדיקה ($)", "Test price ($)"), value=300, min_value=0, step=10)
                if st.button(_t("🧪 בדוק", "🧪 Test"), key="run_rule_test"):
                    matches = db.evaluate_alert_rules(test_item["id"], float(test_price), {})
                    if matches:
                        for m in matches:
                            st.success(f"✅ {_t('כלל', 'Rule')} '{m['rule_name']}' **{_t('יופעל', 'will trigger')}** — {m['message']}")
                    else:
                        st.info(_t("אף כלל לא יופעל למחיר זה", "No rule will trigger for this price"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Price Calendar Heatmap
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📆 לוח מחירים":
    st.title(_t("📆 לוח מחירים — חום לפי מחיר", "📆 Price Calendar — Heat by Price"))
    st.caption(_t("ימים ירוקים = זול, אדומים = יקר. לחץ על תאריך להזמנה.", "Green days = cheap, red = expensive. Click a date to book."))

    with st.form("cal_form"):
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            cal_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
        with cc2:
            cal_dest = st.text_input(_t("יעד", "Destination"), placeholder="LON, BCN, NYC...")
        with cc3:
            cal_month = st.text_input(_t("חודש (YYYY-MM)", "Month (YYYY-MM)"), value=datetime.now().strftime("%Y-%m"))
        cal_submit = st.form_submit_button(_t("📆 הצג לוח", "📆 Show calendar"), use_container_width=True)

    if cal_submit and cal_dest:
        with st.spinner(_t("🔍 טוען מחירים לכל ימי החודש...", "🔍 Loading prices for all days of the month...")):
            cal_data = flexible_search.get_price_calendar(
                origin=cal_origin,
                destination=cal_dest,
                month=cal_month,
            )

        prices_only = [v for v in cal_data.values() if v is not None]
        if not prices_only:
            st.warning(_t("לא נמצאו מחירים. ודא שה-Amadeus API מוגדר.", "No prices found. Make sure Amadeus API is configured."))
        else:
            import calendar as _cal
            year, mon = map(int, cal_month.split("-"))
            month_name = _cal.month_name[mon]

            min_p, max_p = min(prices_only), max(prices_only)
            avg_p = sum(prices_only) / len(prices_only)
            best_date = min(cal_data, key=lambda d: cal_data[d] if cal_data[d] else float("inf"))

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric(_t("🟢 הכי זול", "🟢 Cheapest"), f"${min_p:.0f}", best_date)
            col_m2.metric(_t("📊 ממוצע", "📊 Average"), f"${avg_p:.0f}")
            col_m3.metric(_t("🔴 הכי יקר", "🔴 Most expensive"), f"${max_p:.0f}")

            st.divider()

            # Build Plotly calendar heatmap
            import pandas as pd
            dates = list(cal_data.keys())
            prices = [cal_data[d] for d in dates]

            # Create week-grid layout
            from datetime import date as _dt, timedelta as _td
            first_day = _dt(year, mon, 1)
            first_weekday = first_day.weekday()  # 0=Mon

            # Pad with None for alignment
            all_cells = [None] * first_weekday + prices
            while len(all_cells) % 7:
                all_cells.append(None)
            all_dates_padded = [None] * first_weekday + dates
            while len(all_dates_padded) % 7:
                all_dates_padded.append(None)

            weeks = [all_cells[i:i+7] for i in range(0, len(all_cells), 7)]
            weeks_dates = [all_dates_padded[i:i+7] for i in range(0, len(all_dates_padded), 7)]
            day_names = [_t("ב׳","Mon"), _t("ג׳","Tue"), _t("ד׳","Wed"), _t("ה׳","Thu"), _t("ו׳","Fri"), _t("ש׳","Sat"), _t("א׳","Sun")]

            # Color scale: green (cheap) → yellow → red (expensive)
            def _price_color(p, mn, mx):
                if p is None:
                    return "rgba(0,0,0,0)"
                t = (p - mn) / (mx - mn) if mx != mn else 0.5
                r = int(255 * t)
                g = int(255 * (1 - t))
                return f"rgb({r},{g},60)"

            # Render as HTML grid
            html_rows = []
            html_rows.append(
                "<table style='border-collapse:collapse;width:100%;font-family:sans-serif'>"
                "<tr>" +
                "".join(f"<th style='padding:4px 8px;color:#888;font-size:12px;text-align:center'>{d}</th>" for d in day_names) +
                "</tr>"
            )
            for week_prices, week_dates in zip(weeks, weeks_dates):
                html_rows.append("<tr>")
                for p, d in zip(week_prices, week_dates):
                    if p is None or d is None:
                        html_rows.append("<td style='padding:4px'></td>")
                    else:
                        bg = _price_color(p, min_p, max_p)
                        day_num = d.split("-")[2].lstrip("0")
                        is_best = d == best_date
                        border = "2px solid #fff" if is_best else "1px solid rgba(255,255,255,0.1)"
                        html_rows.append(
                            f"<td style='padding:4px;text-align:center'>"
                            f"<div style='background:{bg};border:{border};border-radius:8px;"
                            f"padding:8px 4px;min-width:40px;cursor:pointer' "
                            f"title='{d}: ${p:.0f}'>"
                            f"<div style='font-size:13px;color:rgba(0,0,0,0.8);font-weight:bold'>{day_num}</div>"
                            f"<div style='font-size:11px;color:rgba(0,0,0,0.7)'>${p:.0f}</div>"
                            f"{'<div style=&quot;font-size:10px&quot;>🏆</div>' if is_best else ''}"
                            f"</div></td>"
                        )
                html_rows.append("</tr>")
            html_rows.append("</table>")
            html_rows.append(
                "<div style='margin-top:8px;font-size:12px;color:#888'>"
                "🟢 זול &nbsp;&nbsp; 🟡 ממוצע &nbsp;&nbsp; 🔴 יקר"
                "</div>"
            )

            components.html("\n".join(html_rows), height=len(weeks) * 70 + 60, scrolling=False)

            st.divider()
            # Cheapest 5 days
            sorted_dates = sorted([(d, p) for d, p in cal_data.items() if p], key=lambda x: x[1])
            st.subheader(_t("🏆 5 הימים הכי זולים", "🏆 5 Cheapest Days"))
            _cols = st.columns(min(5, len(sorted_dates)))
            for i, (d, p) in enumerate(sorted_dates[:5]):
                _cols[i].metric(d, f"${p:.0f}", f"-${avg_p - p:.0f} vs avg")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Flexible Dates
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📅 תאריכים גמישים":
    st.title(_t("📅 תאריכים גמישים", "📅 Flexible Dates"))
    st.caption(_t("מצא את הפלייט הזול ביותר — סביב תאריך מסוים, או בכל החודש", "Find the cheapest flight — around a specific date or across a whole month"))

    flex_tab1, flex_tab2 = st.tabs([
        _t("📅 ±ימים סביב תאריך", "📅 ±Days around a date"),
        _t("🗓️ כל החודש", "🗓️ Whole month"),
    ])

    with flex_tab1:
        st.subheader(_t("מצא את היום הזול בסביבה", "Find the cheapest day nearby"))
        with st.form("flex_around_form"):
            fa1, fa2, fa3 = st.columns(3)
            with fa1:
                fa_origin = st.text_input(_t("מוצא", "Origin"), value="TLV", key="fa_origin")
            with fa2:
                fa_dest = st.text_input(_t("יעד", "Destination"), placeholder=_t("לונדון / LHR", "London / LHR"), key="fa_dest")
            with fa3:
                fa_window = st.slider(_t("חלון ±ימים", "Window ±days"), 1, 7, 3, key="fa_window")
            fa_date = st.date_input(_t("תאריך מבוקש", "Requested date"), key="fa_date")
            fa_submit = st.form_submit_button(_t("🔍 חפש ±ימים", "🔍 Search ±days"), use_container_width=True)

        if fa_submit and fa_dest:
            with st.spinner(_t(f"בודק {2*fa_window+1} תאריכים...", f"Checking {2*fa_window+1} dates...")):
                fa_results = flexible_search.search_around_date(
                    origin=fa_origin,
                    destination=fa_dest,
                    date=str(fa_date),
                    window=fa_window,
                )

            if not fa_results:
                st.warning(_t("לא נמצאו תוצאות.", "No results found."))
            else:
                cheapest = fa_results[0]
                original = next((r for r in fa_results if r.get("delta_days") == 0), None)
                st.markdown(f"### 🏆 {_t('הכי זול', 'Cheapest')}: **{cheapest['date']}**  —  {cheapest['price']:.0f} {cheapest['currency']}")
                if original and original["date"] != cheapest["date"]:
                    savings = original["price"] - cheapest["price"]
                    st.success(f"💰 {_t('חיסכון לעומת התאריך המקורי', 'Savings vs original date')}: **{savings:.0f} {cheapest['currency']}**")

                # Bar chart
                bar_colors = ["#00ff88" if r["date"] == cheapest["date"] else ("#f5a623" if r.get("delta_days") == 0 else "#667eea") for r in fa_results]
                fig = go.Figure(go.Bar(
                    x=[f"{r['label']}<br>{r['date']}" for r in fa_results],
                    y=[r["price"] for r in fa_results],
                    marker_color=bar_colors,
                    text=[f"{r['price']:.0f}" for r in fa_results],
                    textposition="outside",
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(255,255,255,0.03)",
                    font=dict(color="#ccc"),
                    height=320,
                    margin=dict(l=10, r=10, t=10, b=30),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.08)"),
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption(_t("🟢 הכי זול  🟠 תאריך מבוקש  🔵 שאר התאריכים", "🟢 Cheapest  🟠 Requested date  🔵 Other dates"))

                import pandas as pd
                df = pd.DataFrame(fa_results)
                st.dataframe(
                    df[["date", "label", "price", "currency", "deal_quality"]].rename(columns={
                        "date": _t("תאריך", "Date"),
                        "label": _t("הפרש", "Offset"),
                        "price": _t("מחיר", "Price"),
                        "currency": _t("מטבע", "Currency"),
                        "deal_quality": _t("איכות", "Quality"),
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

    with flex_tab2:
        st.subheader(_t("כל תאריכי החודש", "All dates in the month"))
        with st.form("flex_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                origin_flex = st.text_input(_t("מוצא", "Origin"), value="TLV")
            with c2:
                dest_flex = st.text_input(_t("יעד", "Destination"), placeholder=_t("לונדון", "London"))
            with c3:
                month_flex = st.text_input(_t("חודש (YYYY-MM)", "Month (YYYY-MM)"), value=datetime.now().strftime("%Y-%m"))

            duration_flex = st.slider(_t("משך הטיול (ימים)", "Trip duration (days)"), 3, 21, 7)
            submitted_flex = st.form_submit_button(_t("🔍 חפש", "🔍 Search"), use_container_width=True)

        if submitted_flex and dest_flex:
            with st.spinner(f"{_t('בודק כל תאריכי', 'Checking all dates of')} {month_flex}..."):
                results = flexible_search.search_cheapest_days(
                    origin=origin_flex,
                    destination=dest_flex,
                    month=month_flex,
                    trip_duration=duration_flex,
                )

            if not results:
                st.warning(_t("לא נמצאו תוצאות. ודא שה-Amadeus API מוגדר.", "No results found. Make sure the Amadeus API is configured."))
            else:
                st.success(f"{_t('נמצאו', 'Found')} {len(results)} {_t('אפשרויות!', 'options!')}")

                best = results[0]
                st.markdown(
                    f"### 🏆 {_t('הכי זול', 'Cheapest')}: "
                    f"**{best['price']:.0f} {best['currency']}**"
                    f" — {best['date']}"
                )
                if best.get("return_date"):
                    st.caption(f"{_t('חזרה', 'Return')}: {best['return_date']} | {best.get('details','')}")

                import pandas as pd
                df = pd.DataFrame(results)
                price_col = _t("מחיר", "Price")
                dep_col = _t("תאריך יציאה", "Departure")
                ret_col = _t("תאריך חזרה", "Return")
                qual_col = _t("איכות", "Quality")
                df[price_col] = df["price"].apply(lambda p: f"{p:.0f}")
                df[dep_col] = df["date"]
                df[ret_col] = df.get("return_date", "")
                df[qual_col] = df.get("deal_quality", "")
                st.dataframe(
                    df[[dep_col, ret_col, price_col, qual_col]],
                    use_container_width=True, hide_index=True
                )

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
    st.title(_t("📈 חיזוי מחיר — AI", "📈 Price Prediction — AI"))
    st.caption(_t("Claude מנתח היסטוריה ומחזיר: לקנות עכשיו או להמתין?", "Claude analyzes history and returns: buy now or wait?"))

    items = db.get_all_watch_items(enabled_only=False)
    if not items:
        st.info(_t("הוסף פריטים ובדוק מחירים קודם כדי לקבל חיזויים.", "Add items and check prices first to get predictions."))
    else:
        item_names = {f"{i['name']} ({i['destination']})": i for i in items}
        selected_name = st.selectbox(_t("בחר פריט לניתוח", "Select item to analyze"), list(item_names.keys()))
        item = item_names[selected_name]
        history = db.get_price_history(item["id"], limit=50)

        if len(history) < 3:
            st.warning(f"{_t('צריך לפחות 3 בדיקות מחיר. כרגע יש', 'Need at least 3 price checks. Currently have')} {len(history)}.")
        else:
            if st.button(_t("🤖 נתח עכשיו", "🤖 Analyze Now"), use_container_width=True):
                with st.spinner(_t("Claude מנתח מגמות שוק...", "Claude analyzing market trends...")):
                    pred = price_predictor.predict_price(item, history)
                    fmt = price_predictor.format_prediction(pred)

                if "error" in (pred or {}):
                    st.error(pred["error"])
                else:
                    # Main verdict
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(_t("מגמה", "Trend"), f"{fmt['icon']} {fmt['trend']}")
                    with col2:
                        delta = fmt.get("trend_pct", 0)
                        st.metric(_t("שינוי צפוי", "Expected change"), f"{delta:+.1f}%")
                    with col3:
                        st.metric(_t("דחיפות (1-10)", "Urgency (1-10)"), fmt.get("urgency", "?"))

                    # Recommendation box
                    color_map = {"green": "success", "orange": "warning", "blue": "info"}
                    box_fn = getattr(st, color_map.get(fmt["color"], "info"))
                    box_fn(f"**{fmt['recommendation']}** | {fmt['confidence']}")

                    # Reasoning
                    st.markdown(f"**💡 {_t('ניתוח', 'Analysis')}:**\n{fmt['reasoning']}")

                    # Price forecasts
                    if fmt.get("predicted_7d") or fmt.get("predicted_30d"):
                        c1, c2 = st.columns(2)
                        with c1:
                            if fmt.get("predicted_7d"):
                                st.metric(_t("חיזוי 7 ימים", "7-day forecast"), f"{fmt['predicted_7d']:.0f}")
                        with c2:
                            if fmt.get("predicted_30d"):
                                st.metric(_t("חיזוי 30 ימים", "30-day forecast"), f"{fmt['predicted_30d']:.0f}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Trip Planner
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ תכנן טיול":
    st.title(_t("🗺️ תכנן טיול מלא עם AI", "🗺️ Plan a Full Trip with AI"))
    st.caption(_t("Claude יתכנן עבורך טיול מלא — יעד, תקציב, לוח זמנים", "Claude will plan a full trip for you — destination, budget, schedule"))

    with st.form("trip_form"):
        c1, c2 = st.columns(2)
        with c1:
            tp_dest = st.text_input(_t("יעד *", "Destination *"), placeholder=_t("טוקיו, יפן", "Tokyo, Japan"))
            tp_origin = st.text_input(_t("מוצא", "Origin"), value=_t("תל אביב", "Tel Aviv"))
            tp_from = st.date_input(_t("תאריך יציאה", "Departure date"), value=None)
            tp_to = st.date_input(_t("תאריך חזרה", "Return date"), value=None)
        with c2:
            tp_budget = st.number_input(_t("תקציב כולל ($)", "Total budget ($)"), value=3000, step=500)
            tp_travelers = st.number_input(_t("מספר נוסעים", "Number of travelers"), value=2, min_value=1, max_value=10)
            tp_style = st.selectbox(_t("סגנון", "Style"), [_t("תקציבי", "Budget"), _t("מאוזן", "Balanced"), _t("לוקסוס", "Luxury")])
            tp_prefs = st.text_area(_t("העדפות מיוחדות", "Special preferences"), placeholder=_t("אוכל טבעוני, הימנע מטיסות לילה, אוהב טבע...", "Vegan food, avoid night flights, love nature..."))

        tp_submit = st.form_submit_button(_t("🗺️ תכנן טיול!", "🗺️ Plan Trip!"), use_container_width=True)

    if tp_submit and tp_dest:
        # Quick estimate first
        est = trip_planner.quick_budget_estimate(tp_dest, 7, tp_travelers, tp_style)
        st.info(
            f"**{_t('הערכה מהירה', 'Quick estimate')}:** ~${est['estimated_total']:,} | "
            f"${est['per_day']:,}/{_t('יום', 'day')} | ${est['per_person']:,}/{_t('אדם', 'person')}"
        )

        with st.spinner(_t("Claude מתכנן את הטיול שלך... (30-60 שניות)", "Claude planning your trip... (30-60 seconds)")):
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
            st.success(plan.get("summary", _t("התכנית מוכנה!", "Plan is ready!")))

            # Budget breakdown
            if "budget_breakdown" in plan:
                st.subheader(_t("💰 פירוט תקציב", "💰 Budget Breakdown"))
                bd = plan["budget_breakdown"]
                cols = st.columns(len(bd))
                labels = {"flights": _t("✈️ טיסות", "✈️ Flights"), "hotel": _t("🏨 מלון", "🏨 Hotel"), "food": _t("🍽️ אוכל", "🍽️ Food"),
                          "activities": _t("🎭 פעילויות", "🎭 Activities"), "transport": _t("🚌 תחבורה", "🚌 Transport"), "other": _t("📦 אחר", "📦 Other")}
                for col, (k, v) in zip(cols, bd.items()):
                    col.metric(labels.get(k, k), f"${v:,}")

            total = plan.get("total_estimated", 0)
            if total:
                st.metric(_t("סה״כ משוער", "Total estimate"), f"${total:,}")

            # Daily plan
            if "daily_plan" in plan:
                st.subheader(_t("📅 תכנית יומית", "📅 Daily Plan"))
                for day in plan["daily_plan"]:
                    with st.expander(
                        f"{_t('יום', 'Day')} {day.get('day','')} — {day.get('title','')} "
                        f"(${day.get('estimated_cost', 0):,})"
                    ):
                        if day.get("activities"):
                            st.markdown(f"**{_t('פעילויות', 'Activities')}:** " + " | ".join(day["activities"]))
                        meals = day.get("meals", {})
                        if any(meals.values()):
                            st.markdown(
                                f"🍳 {meals.get('breakfast','')} | "
                                f"🥗 {meals.get('lunch','')} | "
                                f"🍽️ {meals.get('dinner','')}"
                            )
                        if day.get("accommodation"):
                            st.markdown(f"🛏️ **{_t('לינה', 'Accommodation')}:** {day['accommodation']}")
                        if day.get("tips"):
                            st.info(f"💡 {day['tips']}")

            # Best deals & advice
            if plan.get("best_deals"):
                st.subheader(_t("🔥 הדילים הכי טובים", "🔥 Best Deals"))
                for deal in plan["best_deals"]:
                    st.markdown(f"• {deal}")

            if plan.get("booking_advice"):
                st.subheader(_t("📌 מתי להזמין", "📌 When to Book"))
                st.info(plan["booking_advice"])

            if plan.get("warnings"):
                for w in plan["warnings"]:
                    st.warning(f"⚠️ {w}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Exchange Rates
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💱 שערי חליפין":
    st.title(_t("💱 שערי חליפין", "💱 Exchange Rates"))
    st.caption(_t("עקוב אחרי שערי חליפין וקבל התראה כשהשקל חזק", "Track exchange rates and get an alert when the shekel is strong"))

    fx.ensure_table()

    # Current rates
    st.subheader(_t("📊 שערים נוכחיים", "📊 Current Rates"))
    if st.button(_t("🔄 רענן שערים", "🔄 Refresh Rates")):
        rates = fx.fetch_rates("USD")
        if rates:
            with db.get_db() as conn:
                for base, target, _ in fx.POPULAR_PAIRS:
                    if target in rates:
                        rate_val = rates[target]
                        fx.save_rate(base, target, rate_val)
            st.success(_t("עודכן!", "Updated!"))
        else:
            st.error(_t("לא ניתן לטעון שערים", "Cannot load rates"))

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
    st.subheader(_t("🔔 הוסף התראת שער", "🔔 Add Rate Alert"))
    with st.form("rate_alert_form"):
        ra_c1, ra_c2, ra_c3, ra_c4 = st.columns(4)
        with ra_c1:
            ra_base = st.text_input(_t("מטבע בסיס", "Base currency"), value="USD")
        with ra_c2:
            ra_target = st.text_input(_t("מטבע יעד", "Target currency"), value="ILS")
        with ra_c3:
            ra_threshold = st.number_input(_t("ספסף", "Threshold"), value=3.50, step=0.01, format="%.4f")
        with ra_c4:
            ra_dir = st.selectbox(_t("כיוון", "Direction"), ["below", "above"],
                                  format_func=lambda x: _t("מתחת ל", "Below") if x == "below" else _t("מעל ל", "Above"))
        if st.form_submit_button(_t("➕ הוסף התראה", "➕ Add Alert")):
            fx.add_rate_alert(ra_base, ra_target, ra_threshold, ra_dir)
            st.success(f"✅ {_t('התראה נוספה', 'Alert added')}: {ra_base}/{ra_target} {ra_dir} {ra_threshold}")

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
            title=_t("USD/ILS — היסטוריה", "USD/ILS — History"),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(255,255,255,0.03)",
            font=dict(color="#ccc"), height=250,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Export
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📥 ייצוא נתונים":
    st.title(_t("📥 ייצוא נתונים", "📥 Export Data"))

    items = db.get_all_watch_items(enabled_only=False)
    if not items:
        st.info(_t("אין נתונים לייצוא.", "No data to export."))
    else:
        st.subheader(_t("📊 ייצוא Excel — כל הפריטים", "📊 Export Excel — All Items"))
        st.caption(_t("קובץ Excel מעוצב עם גרפים ו-color coding לפי מחיר", "Formatted Excel file with charts and color coding by price"))
        if st.button(_t("📊 הורד Excel", "📊 Download Excel"), use_container_width=True):
            with st.spinner(_t("יוצר קובץ Excel...", "Creating Excel file...")):
                xlsx_bytes = exporters.export_excel()
            st.download_button(
                label=_t("⬇️ הורד Noded.xlsx", "⬇️ Download Noded.xlsx"),
                data=xlsx_bytes,
                file_name=f"Noded_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        st.divider()
        st.subheader(_t("📄 ייצוא CSV — פריט יחיד", "📄 Export CSV — Single Item"))
        item_names = {f"{i['name']} ({i['destination']})": i for i in items}
        sel = st.selectbox(_t("בחר פריט", "Select item"), list(item_names.keys()))
        item = item_names[sel]

        csv_str = exporters.export_csv(item["id"])
        st.download_button(
            label=_t("⬇️ הורד CSV", "⬇️ Download CSV"),
            data=csv_str.encode("utf-8-sig"),
            file_name=f"{item['name']}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Multi-City Route Optimizer
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🌍 מסלול מרובה ערים":
    st.title(_t("🌍 מטב מסלול מרובה ערים", "🌍 Multi-City Route Optimizer"))
    st.caption(_t("מה הסדר הזול ביותר לביקור בכמה ערים? Claude מחשב את כל הקומבינציות.", "What is the cheapest order to visit multiple cities? Claude computes all combinations."))

    with st.form("multicity_form"):
        c1, c2 = st.columns(2)
        with c1:
            mc_origin = st.text_input(_t("עיר מוצא", "Origin city"), value=_t("תל אביב (TLV)", "Tel Aviv (TLV)"))
            mc_cities_raw = st.text_area(
                _t("ערים לביקור (שורה לכל עיר)", "Cities to visit (one per line)"),
                placeholder=_t("טוקיו\nבנגקוק\nבאלי\nסינגפור", "Tokyo\nBangkok\nBali\nSingapore"),
                height=120,
            )
            mc_start = st.date_input(_t("תאריך יציאה", "Departure date"))
        with c2:
            mc_budget = st.number_input(_t("תקציב כולל ($)", "Total budget ($)"), value=5000, step=500)
            mc_days_raw = st.text_area(
                _t("ימים בכל עיר (שורה לכל עיר, לפי סדר למעלה)", "Days per city (one per line, same order as above)"),
                placeholder="3\n4\n4\n3",
                height=120,
            )
        mc_submit = st.form_submit_button(_t("🔍 מצא מסלול זול ביותר", "🔍 Find Cheapest Route"), use_container_width=True)

    if mc_submit and mc_cities_raw.strip():
        cities = [c.strip() for c in mc_cities_raw.strip().splitlines() if c.strip()]
        days_list = [d.strip() for d in mc_days_raw.strip().splitlines() if d.strip()]
        days_per_city = {}
        for i, city in enumerate(cities):
            try:
                days_per_city[city] = int(days_list[i])
            except (IndexError, ValueError):
                days_per_city[city] = 3

        st.info(f"{_t('מחשב', 'Computing')} {len(cities)} {_t('ערים', 'cities')}: {' → '.join(cities)}")

        with st.spinner(_t("Claude מחשב את כל הקומבינציות האפשריות...", "Claude computing all possible combinations...")):
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

            st.success(f"✅ {_t('הסדר האופטימלי חוסך', 'The optimal order saves')} **${savings:,}** {_t('לעומת הגרוע ביותר!', 'vs the worst order!')}")

            st.markdown(
                f"### 🏆 {_t('הסדר המומלץ', 'Recommended order')}: "
                + " → ".join(f"**{c}**" for c in optimal)
                + f"  |  ${opt_price:,}"
            )

            # Compare all orders
            comparisons = result.get("direct_comparison", [])
            if comparisons:
                st.subheader(_t("📊 השוואת סדרים", "📊 Order Comparison"))
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
                st.subheader(_t("✈️ אפשרות Open-Jaw", "✈️ Open-Jaw Option"))
                c1, c2 = st.columns(2)
                c1.info(f"**{oj.get('description','')}**\n\n${oj.get('price',0):,}")
                if oj.get("saves", 0) > 0:
                    c2.success(f"{_t('חוסך', 'Saves')} **${oj['saves']:,}** {_t('לעומת Round-Trip', 'vs Round-Trip')}")

            # Flight legs
            legs = result.get("flight_legs", [])
            if legs:
                st.divider()
                st.subheader(_t("🗓️ רגלי הטיסה", "🗓️ Flight Legs"))
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
                st.info(f"📌 **{_t('אסטרטגיית הזמנה', 'Booking strategy')}:** {result['booking_strategy']}")

            # Tips
            tips = result.get("tips", [])
            if tips:
                st.subheader(_t("💡 טיפים", "💡 Tips"))
                for tip in tips:
                    st.markdown(f"• {tip}")

            if result.get("hub_tip"):
                st.success(f"🔗 **Hub tip:** {result['hub_tip']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Stopover Finder
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔁 עצירות חינם":
    st.title(_t("🔁 מצא עצירות חינם (Stopovers)", "🔁 Find Free Stopovers"))
    st.caption(_t("Emirates → דובאי, Icelandair → רייקיאוויק, Turkish → איסטנבול. שני יעדים במחיר אחד!", "Emirates → Dubai, Icelandair → Reykjavik, Turkish → Istanbul. Two destinations for the price of one!"))

    with st.form("stopover_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            so_origin = st.text_input(_t("מוצא", "Origin"), value="TLV")
        with c2:
            so_dest = st.text_input(_t("יעד סופי *", "Final destination *"), placeholder=_t("טוקיו, ניו-יורק...", "Tokyo, New York..."))
        with c3:
            so_days = st.slider(_t("מקסימום ימי עצירה", "Max stopover days"), 1, 7, 3)
        c4, c5 = st.columns(2)
        with c4:
            so_out = st.date_input(_t("תאריך יציאה", "Departure date"))
        with c5:
            so_ret = st.date_input(_t("תאריך חזרה (אופציונלי)", "Return date (optional)"), value=None)
        so_submit = st.form_submit_button(_t("🔍 מצא stopovers", "🔍 Find stopovers"), use_container_width=True)

    if so_submit and so_dest:
        with st.spinner(_t("מחפש stopovers אטרקטיביים...", "Searching attractive stopovers...")):
            options = stopover_finder.find_stopovers(
                origin=so_origin,
                destination=so_dest,
                date_out=str(so_out),
                date_return=str(so_ret) if so_ret else "",
                max_stopover_days=so_days,
            )

        if not options or "error" in (options[0] if options else {}):
            st.warning(_t("לא נמצאו stopovers. נסה יעד אחר.", "No stopovers found. Try a different destination."))
        else:
            st.success(f"{_t('נמצאו', 'Found')} {len(options)} {_t('אפשרויות stopover!', 'stopover options!')}")

            for opt in options:
                score = stopover_finder.get_stopover_value_score(opt)
                is_free = opt.get("is_free_stopover", False)
                color = "#00ff88" if is_free else "#667eea"
                badge = "🆓 FREE STOPOVER" if is_free else _t("💰 תוספת מחיר", "💰 Extra cost")
                savings = opt.get("savings_vs_direct", 0) or 0
                extra = opt.get("extra_cost_vs_direct", 0) or 0

                price_delta = savings if savings > 0 else -extra
                delta_text = (
                    f"{_t('חוסך', 'Saves')} **${savings:,}**" if savings > 0
                    else (f"{_t('תוספת', 'Extra')} ${extra:,}" if extra > 0 else _t("אותו מחיר", "Same price"))
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
                            _t("מחיר עם Stopover", "Price with Stopover"),
                            f"${opt.get('price_with_stopover',0):,}",
                            f"vs {_t('ישיר', 'direct')} ${opt.get('price_direct',0):,}",
                        )
                    with hc3:
                        st.metric(_t("ניקוד ערך", "Value score"), f"{score:.1f}/10")
                    st.markdown("</div>", unsafe_allow_html=True)

                highlights = opt.get("stopover_highlights", [])
                if highlights:
                    st.markdown(f"**🌟 {_t('מה לעשות ב', 'What to do in')}" + opt.get('stopover_city','') + ":** " + " | ".join(highlights))

                cols_info = st.columns(3)
                cols_info[0].caption(f"⏱ {opt.get('stopover_days_min',0)}-{opt.get('stopover_days_max',3)} {_t('ימי עצירה', 'stopover days')}")
                cols_info[1].caption(f"👥 {_t('מתאים ל', 'Best for')}: {opt.get('best_for','')}")
                visa_icon = _t("❌ נדרשת ויזה", "❌ Visa required") if opt.get("visa_needed") else _t("✅ ללא ויזה", "✅ Visa-free")
                cols_info[2].caption(visa_icon)

                if opt.get("tip"):
                    st.info(f"💡 {opt['tip']}")
                if opt.get("booking_url"):
                    st.link_button(_t("🔗 הזמן עכשיו", "🔗 Book Now"), opt["booking_url"])
                st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: True Cost Calculator
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💰 עלות אמיתית":
    st.title(_t("💰 מחשבון עלות אמיתית", "💰 True Cost Calculator"))
    st.caption(_t("Ryanair ב-€49 עם מטען = לפעמים יקר יותר מ-El Al. תראה את המחיר האמיתי.", "Ryanair at €49 with luggage = sometimes more expensive than El Al. See the true price."))

    tab1, tab2 = st.tabs([_t("🧳 עלות אמיתית", "🧳 True Cost"), _t("💳 נקודות vs מזומן", "💳 Points vs Cash")])

    with tab1:
        with st.form("truecost_form"):
            c1, c2 = st.columns(2)
            with c1:
                tc_price = st.number_input(_t("מחיר בסיס ($)", "Base price ($)"), value=200, step=10)
                tc_airline = st.selectbox(_t("חברת תעופה", "Airline"), [
                    "El Al", "Israir", "Arkia", "Ryanair", "Wizz Air",
                    "easyJet", "Lufthansa", "KLM", "TurkishAirlines", _t("אחר", "Other"),
                ])
                tc_bags = st.number_input(_t("מספר מזוודות", "Number of bags"), value=1, min_value=0, max_value=5)
                tc_bag_weight = st.selectbox(_t("משקל מזוודה", "Bag weight"), ["10kg", "15kg", "20kg", "23kg", "32kg"])
            with c2:
                tc_meals = st.checkbox(_t("צריך לקנות ארוחות?", "Need to buy meals?"), value=False)
                tc_insurance = st.checkbox(_t("ביטוח נסיעות", "Travel insurance"), value=True)
                tc_nights = st.number_input(_t("מספר לילות", "Number of nights"), value=7, min_value=1)
                tc_travelers = st.number_input(_t("מספר נוסעים", "Number of travelers"), value=2, min_value=1)
                tc_origin_airport = st.selectbox(_t("שדה תעופה מוצא", "Departure airport"), ["TLV", _t("אחר", "Other")])
                tc_transport = st.selectbox(_t("הגעה לנמל תעופה", "Transport to airport"), ["taxi", "bus", "shuttle", "train"])

            tc_submit = st.form_submit_button(_t("💰 חשב עלות אמיתית", "💰 Calculate True Cost"), use_container_width=True)

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
            col1.metric(_t("💰 עלות אמיתית", "💰 True cost"), f"${total:,.0f}")
            col2.metric(_t("👤 לאדם", "👤 Per person"), f"${result['per_person']:,.0f}")
            col3.metric(_t("🙈 עמלות נסתרות", "🙈 Hidden fees"), f"${hidden:,.0f}", f"{hidden_pct:.0f}% {_t('מהסכום', 'of total')}")

            if hidden_pct > 30:
                st.warning(f"⚠️ {hidden_pct:.0f}% {_t('מהמחיר הוא עמלות נסתרות! מחיר הבסיס מטעה.', 'of the price is hidden fees! The base price is misleading.')}")
            elif hidden_pct > 15:
                st.info(f"ℹ️ {hidden_pct:.0f}% {_t('עמלות נוספות על מחיר הבסיס.', 'additional fees on top of the base price.')}")
            else:
                st.success(f"✅ {_t('מחיר הבסיס מייצג היטב — רק', 'Base price is representative — only')} {hidden_pct:.0f}% {_t('תוספות.', 'extras.')}")

            # Breakdown chart
            labels = {
                "base_flight": _t("✈️ טיסה", "✈️ Flight"),
                "baggage": _t("🧳 מטען", "🧳 Luggage"),
                "meals": _t("🍽️ ארוחות", "🍽️ Meals"),
                "transport_origin": _t("🚗 הסעה לנמל", "🚗 Transfer to airport"),
                "transport_destination": _t("🚕 הסעה ביעד", "🚕 Transfer at destination"),
                "insurance": _t("🛡️ ביטוח", "🛡️ Insurance"),
                "seat_selection": _t("💺 בחירת מושב", "💺 Seat selection"),
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
        st.subheader(_t("💳 האם לממש נקודות?", "💳 Should I Redeem Points?"))
        with st.form("points_form"):
            p1, p2, p3 = st.columns(3)
            with p1:
                pt_program = st.selectbox(_t("תוכנית נאמנות", "Loyalty program"), list(cost_calculator.POINTS_VALUES.keys()))
            with p2:
                pt_points = st.number_input(_t("כמות נקודות", "Number of points"), value=50000, step=1000)
            with p3:
                pt_cash = st.number_input(_t("מחיר במזומן ($)", "Cash price ($)"), value=500, step=50)
            pt_submit = st.form_submit_button(_t("🔍 חשב", "🔍 Calculate"), use_container_width=True)

        if pt_submit:
            res = cost_calculator.calculate_points_value(
                points=pt_points,
                program=pt_program,
                redemption_cash_value=pt_cash,
            )
            col1, col2, col3 = st.columns(3)
            col1.metric(_t("ערך הנקודות", "Points value"), f"${res['cash_value_usd']:,.0f}")
            col2.metric(_t("מחיר מזומן", "Cash price"), f"${res['redemption_value_usd']:,.0f}")
            ratio = res["ratio_pct"]
            delta_val = res["cash_value_usd"] - res["redemption_value_usd"]
            col3.metric(_t("יחס", "Ratio"), f"{ratio:.0f}%", f"{delta_val:+.0f}$")

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
                title={"text": _t("ערך הנקודות vs מזומן", "Points value vs Cash")},
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#ccc"), height=250,
                margin=dict(l=30, r=30, t=40, b=10),
            )
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader(_t("🔍 מצא את המימוש הכי טוב לנקודות שלך", "🔍 Find the Best Redemption for Your Points"))
        with st.form("best_redeem_form"):
            br_program = st.selectbox(_t("תוכנית", "Program"), list(cost_calculator.POINTS_VALUES.keys()), key="br_prog")
            br_points = st.number_input(_t("נקודות", "Points"), value=100000, step=5000, key="br_pts")
            br_submit = st.form_submit_button(_t("🤖 מצא הזדמנויות מימוש", "🤖 Find Redemption Opportunities"), use_container_width=True)

        if br_submit:
            with st.spinner(_t("Claude מחפש את הדרכים הכי משתלמות...", "Claude finding the most valuable redemptions...")):
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
                        f"💰 {_t('ערך', 'Value')}: <span style='color:{color}'>{cpp:.1f}¢/{_t('נקודה', 'point')}</span> | "
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
    st.title(_t("📊 תובנות ודפוסים מהדאטה שלך", "📊 Insights & Patterns from Your Data"))
    st.caption(_t("מה ה-DB לימד אותנו — מתי יוצאים דילים, לאיזה יעדים, ומה הזמן הכי טוב לסרוק.", "What the DB taught us — when deals appear, to which destinations, and the best time to scan."))

    patterns = deal_insights.get_deal_patterns()

    if patterns.get("empty"):
        st.info(patterns["message"])
        st.stop()

    # Header metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(_t("סה״כ דילים נצפו", "Total deals seen"), patterns["total_deals"])
    col2.metric(_t("ניקוד ממוצע", "Average score"), f"{patterns['avg_score']:.1f}/10")
    if patterns.get("best_day"):
        col3.metric(_t("יום הדילים הכי טוב", "Best deals day"), patterns["best_day"]["name"])
    if patterns.get("best_hour") is not None:
        col4.metric(_t("שעה הכי טובה לסרוק", "Best hour to scan"), f"{patterns['best_hour']:02d}:00")

    st.divider()

    tab1, tab2, tab3 = st.tabs([_t("📅 תזמון", "📅 Timing"), _t("✈️ יעדים וחברות", "✈️ Destinations & Airlines"), _t("🤖 ניתוח AI", "🤖 AI Analysis")])

    with tab1:
        # Day of week chart
        day_scores = patterns.get("day_scores", {})
        if day_scores:
            st.subheader(_t("📅 איכות דילים לפי יום בשבוע", "📅 Deal quality by day of week"))
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
                    f"✅ **{_t('הכי טוב', 'Best')}:** {_t('יום', 'Day')} {patterns['best_day']['name']} "
                    f"({_t('ניקוד', 'Score')} {patterns['best_day']['avg_score']})"
                )
                c2.error(
                    f"❌ **{_t('הכי גרוע', 'Worst')}:** {_t('יום', 'Day')} {patterns['worst_day']['name']} "
                    f"({_t('ניקוד', 'Score')} {patterns['worst_day']['avg_score']})"
                )

        # Hour chart
        hour_scores = patterns.get("hour_scores", {})
        if hour_scores:
            st.subheader(_t("⏰ איכות דילים לפי שעה", "⏰ Deal quality by hour"))
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
            st.subheader(_t("✈️ יעדים עם הכי הרבה דילים", "✈️ Top destinations by deal count"))
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
            st.subheader(_t("🏷️ סוגי דילים", "🏷️ Deal types"))
            type_labels = {
                "error_fare": _t("💎 שגיאת מחיר", "💎 Error fare"),
                "flash_sale": _t("⚡ מכירת פלאש", "⚡ Flash sale"),
                "promo": _t("🏷️ מבצע", "🏷️ Promo"),
                "regular_cheap": _t("💰 זול", "💰 Cheap"),
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
            st.subheader(_t("✈️ חברות תעופה", "✈️ Airlines"))
            for a in top_air:
                st.markdown(f"• **{a['airline']}** — {a['cnt']} {_t('דילים', 'deals')} | {_t('ממוצע', 'avg')} ${a.get('avg_price',0):.0f}")

    with tab3:
        st.subheader(_t("🤖 ניתוח AI — מה ה-DB מלמד אותנו?", "🤖 AI Analysis — What does your data tell us?"))
        if st.button(_t("🤖 ניתח עם Claude", "🤖 Analyze with Claude"), use_container_width=True):
            with st.spinner(_t("Claude מנתח את הדאטה שלך...", "Claude is analyzing your data...")):
                ai = deal_insights.get_ai_insights()

            if "error" in ai:
                st.error(ai["error"])
            else:
                if ai.get("key_patterns"):
                    st.subheader(_t("🔍 דפוסים מרכזיים", "🔍 Key Patterns"))
                    for p in ai["key_patterns"]:
                        st.markdown(f"• {p}")

                if ai.get("strategy"):
                    st.subheader(_t("🎯 אסטרטגיה מומלצת", "🎯 Recommended Strategy"))
                    st.info(ai["strategy"])

                if ai.get("add_to_watchlist"):
                    st.subheader(_t("📌 כדאי להוסיף לרשימת המעקב", "📌 Add to Watchlist"))
                    cols = st.columns(len(ai["add_to_watchlist"]))
                    for col, dest in zip(cols, ai["add_to_watchlist"]):
                        col.success(f"✈️ {dest}")

                if ai.get("action_items"):
                    st.subheader(_t("✅ פעולות מומלצות", "✅ Recommended Actions"))
                    for act in ai["action_items"]:
                        st.markdown(f"• {act}")

                if ai.get("savings_potential"):
                    st.metric(_t("💰 פוטנציאל חיסכון", "💰 Savings Potential"), ai["savings_potential"])

        # Recent top deals from DB
        recent = patterns.get("recent_top", [])
        if recent:
            st.divider()
            st.subheader(_t("🏆 הדילים הכי טובים שנצפו", "🏆 Best Deals Seen"))
            for d in recent:
                if not isinstance(d, dict): continue
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
    st.title(_t("🤖 הגדרת בוט Telegram", "🤖 Telegram Bot Setup"))
    st.caption(_t("קבל התראות חכמות ישירות ל-Telegram — דילים, ירידות מחיר, שביתות, דילים שפגים.", "Get smart alerts directly to Telegram — deals, price drops, strikes, expiring deals."))

    # Current status
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    if tg_token and tg_chat:
        st.success(f"✅ {_t('בוט מחובר', 'Bot connected')} | Chat ID: {tg_chat}")
        bot_info = telegram_bot.get_bot_info(tg_token)
        if bot_info.get("ok"):
            bname = bot_info["result"].get("username", "")
            st.caption(f"Bot: @{bname}")
    else:
        st.warning(_t("⚠️ בוט לא מוגדר — הגדר token ו-chat_id למטה", "⚠️ Bot not configured — set token and chat_id below"))

    st.divider()

    # Setup guide
    with st.expander(_t("📖 איך מגדירים בוט Telegram? (3 שלבים)", "📖 How to set up a Telegram bot? (3 steps)"), expanded=not bool(tg_token)):
        st.markdown(_t("""
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
        """, """
**Step 1 — Create a bot:**
1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Choose a name and username for the bot
4. Receive the **Bot Token** (looks like: `123456:ABC-DEF...`)

**Step 2 — Find your Chat ID:**
1. Send a message to the bot you created
2. Click "Get Chat ID" below — the system will find it automatically

**Step 3 — Save and test:**
1. Enter Token and Chat ID below
2. Click "Test Connection"
3. If everything works — you'll receive a confirmation message on Telegram!
        """))

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
        save_btn = c1.form_submit_button(_t("💾 שמור", "💾 Save"), use_container_width=True)
        test_btn = c2.form_submit_button(_t("📨 בדוק חיבור", "📨 Test Connection"), use_container_width=True)

    if save_btn and new_token and new_chat:
        _save_env("TELEGRAM_BOT_TOKEN", new_token)
        _save_env("TELEGRAM_CHAT_ID", new_chat)
        st.success(_t("✅ נשמר! הפעל מחדש את האפליקציה להפעלת השינויים.", "✅ Saved! Restart the app to apply changes."))

    if test_btn and new_token and new_chat:
        with st.spinner(_t("שולח הודעת בדיקה...", "Sending test message...")):
            res = telegram_bot.test_connection(new_token, new_chat)
        if res.get("ok"):
            st.success(_t("✅ הודעת בדיקה נשלחה! בדוק את Telegram.", "✅ Test message sent! Check Telegram."))
        else:
            st.error(f"❌ {_t('שגיאה', 'Error')}: {res.get('error', _t('לא ידוע', 'Unknown'))}")

    st.divider()

    # Auto-detect chat ID
    if tg_token:
        st.subheader(_t("🔍 זיהוי אוטומטי של Chat ID", "🔍 Auto-Detect Chat ID"))
        st.caption(_t("שלח הודעה לבוט שלך ב-Telegram, ואז לחץ כאן למציאת ה-ID שלך.", "Send a message to your bot on Telegram, then click here to find your ID."))
        if st.button(_t("🔍 קבל Chat ID", "🔍 Get Chat ID"), use_container_width=True):
            updates = telegram_bot.get_updates(tg_token)
            found_id = telegram_bot.extract_chat_id(updates)
            if found_id:
                st.success(f"✅ {_t('Chat ID שלך', 'Your Chat ID')}: **{found_id}**")
                st.code(found_id)
            else:
                st.warning(_t("לא נמצאו הודעות. ודא ששלחת הודעה לבוט תחילה.", "No messages found. Make sure you sent a message to the bot first."))

    st.divider()

    # Alert settings
    st.subheader(_t("⚙️ הגדרות התראות", "⚙️ Alert Settings"))
    st.caption(_t("בחר אילו התראות לקבל ב-Telegram", "Choose which alerts to receive on Telegram"))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(_t("**✈️ מחירים**", "**✈️ Prices**"))
        st.checkbox(_t("ירידת מחיר בטיסות", "Flight price drop"), value=True, key="tg_price_drop")
        st.checkbox(_t("מחיר נמוך היסטורי", "Historical low price"), value=True, key="tg_price_low")
        st.checkbox(_t("עלייה חדה במחיר", "Sharp price rise"), value=False, key="tg_price_rise")
    with col2:
        st.markdown(_t("**🔥 דילים**", "**🔥 Deals**"))
        st.checkbox(_t("דיל חדש (ציד דילים)", "New deal (deal hunter)"), value=True, key="tg_new_deal")
        st.checkbox(_t("דיל עומד לפוג", "Deal about to expire"), value=True, key="tg_expiry")
        st.checkbox(_t("שגיאת מחיר", "Error fare"), value=True, key="tg_error_fare")

    st.divider()

    # Send test deal
    st.subheader(_t("📨 שלח התראה ידנית", "📨 Send Manual Alert"))
    with st.form("tg_manual_form"):
        msg_text = st.text_area(_t("הודעה", "Message"), placeholder=_t("כתוב הודעה לשלוח לבוט...", "Write a message to send to the bot..."), height=80)
        manual_submit = st.form_submit_button(_t("📨 שלח עכשיו", "📨 Send Now"))

    if manual_submit and msg_text and tg_token and tg_chat:
        res = telegram_bot.send_message(tg_token, tg_chat, msg_text)
        if res.get("ok"):
            st.success(_t("✅ נשלח!", "✅ Sent!"))
        else:
            st.error(f"❌ {res.get('error', _t('שגיאה', 'Error'))}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Kiwi Flight Search
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Kiwi טיסות":
    st.title(_t("🔍 חיפוש טיסות Kiwi / Tequila", "🔍 Kiwi / Tequila Flight Search"))
    st.caption(_t("מחירים אמיתיים, virtual interlining, מסלולים יצירתיים שGoogle Flights מפספס.", "Real prices, virtual interlining, creative routes that Google Flights misses."))

    kiwi_key = os.environ.get("KIWI_API_KEY", "")
    if kiwi_key:
        st.success(_t("✅ Kiwi API Key מוגדר — מחירים אמיתיים", "✅ Kiwi API Key configured — real prices"))
    else:
        st.info(_t("ℹ️ ללא API Key — משתמש ב-Claude web search (פחות מדויק). הוסף KIWI_API_KEY ל-.env לתוצאות מדויקות.", "ℹ️ No API Key — using Claude web search (less accurate). Add KIWI_API_KEY to .env for precise results."))

    st.divider()

    with st.form("kiwi_search_form"):
        c1, c2 = st.columns(2)
        k_origin = c1.text_input(_t("מוצא (IATA)", "Origin (IATA)"), value="TLV", max_chars=3).upper()
        k_dest = c2.text_input(_t("יעד (IATA)", "Destination (IATA)"), value="", placeholder="NYC / BKK / LON", max_chars=3).upper()

        c3, c4 = st.columns(2)
        k_date_out = c3.date_input(_t("תאריך יציאה", "Departure date"))
        k_date_back = c4.date_input(_t("תאריך חזרה (אופציונלי)", "Return date (optional)"), value=None)

        c5, c6, c7 = st.columns(3)
        k_adults = c5.number_input(_t("נוסעים", "Passengers"), min_value=1, max_value=9, value=1)
        k_stops = c6.number_input(_t("עצירות מקס", "Max stops"), min_value=0, max_value=3, value=2)
        k_currency = c7.selectbox(_t("מטבע", "Currency"), ["USD", "EUR", "ILS"], index=0)

        k_price_max = st.number_input(_t("מחיר מקסימלי (0 = ללא הגבלה)", "Max price (0 = no limit)"), min_value=0, value=0)

        k_submit = st.form_submit_button(_t("🔍 חפש טיסות", "🔍 Search Flights"), use_container_width=True)

    if k_submit and k_dest:
        with st.spinner(_t("מחפש טיסות...", "Searching flights...")):
            flights = kiwi_client.search_flights(
                origin=k_origin,
                destination=k_dest,
                date_from=str(k_date_out),
                date_to=str(k_date_out),
                return_from=str(k_date_back) if k_date_back else "",
                adults=int(k_adults),
                max_stopovers=int(k_stops),
                currency=k_currency,
                limit=10,
                price_to=int(k_price_max) if k_price_max > 0 else 0,
            )

        if not flights:
            st.warning(_t("לא נמצאו טיסות.", "No flights found."))
        elif "error" in (flights[0] if flights else {}):
            st.error(f"{_t('שגיאה', 'Error')}: {flights[0]['error']}")
        else:
            st.success(f"✅ {_t('נמצאו', 'Found')} {len(flights)} {_t('טיסות', 'flights')}")
            for f in flights:
                price = f.get("price", 0)
                airline = f.get("airline", "")
                stops = f.get("stops", 0)
                dep = f.get("departure", "")
                arr = f.get("arrival", "")
                dur = f.get("duration_hours", 0)
                stop_txt = _t("✈️ ישיר", "✈️ Direct") if stops == 0 else f"{stops} {_t('עצירות', 'stops')}"
                deep_link = f.get("deep_link", "")

                with st.container():
                    cols = st.columns([1, 2, 2, 1, 1])
                    cols[0].metric(_t("מחיר", "Price"), f"${price:,.0f}")
                    cols[1].write(f"**{airline}** | {stop_txt}")
                    cols[2].write(f"🛫 {dep[:16]}\n🛬 {arr[:16]}")
                    cols[3].write(f"⏱ {dur}{_t('ש׳', 'h')}")
                    if deep_link:
                        cols[4].markdown(f"[{_t('הזמן', 'Book')}]({deep_link})")
                    st.divider()

    st.divider()
    st.subheader(_t("📅 חודש זול — מתי הכי זול לטוס?", "📅 Cheapest Month — When is the cheapest to fly?"))
    with st.form("kiwi_month_form"):
        cm1, cm2 = st.columns(2)
        m_origin = cm1.text_input(_t("מוצא", "Origin"), value="TLV", max_chars=3).upper()
        m_dest = cm2.text_input(_t("יעד", "Destination"), placeholder="NYC", max_chars=3).upper()
        m_month = st.text_input(_t("חודש (YYYY-MM)", "Month (YYYY-MM)"), placeholder="2025-08")
        m_submit = st.form_submit_button(_t("📅 מצא ימים זולים", "📅 Find Cheap Days"))

    if m_submit and m_dest:
        with st.spinner(_t("סורק את כל החודש...", "Scanning the entire month...")):
            results = kiwi_client.get_cheapest_month(m_origin, m_dest, m_month)
        if results and "error" not in (results[0] if results else {}):
            st.write(f"**{len(results)} {_t('אפשרויות — ממוין לפי מחיר', 'options — sorted by price')}:**")
            for r in results[:10]:
                st.write(f"📅 {r.get('departure','')[:10]} — **${r.get('price',0):,.0f}** | {r.get('airline','')} | {r.get('stops',0)} {_t('עצירות', 'stops')}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Hidden City
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🕵️ Hidden City":
    st.title("🕵️ Hidden City Ticketing")
    st.caption(_t("מוצא כרטיסים זולים יותר דרך יעד ביניים — חוסך 20-50%.", "Find cheaper tickets via an intermediate destination — saves 20-50%."))

    with st.expander(_t("⚠️ חשוב לדעת לפני השימוש", "⚠️ Important to know before using"), expanded=True):
        st.warning(hidden_city.get_risks_explanation())

    st.divider()

    tab1, tab2 = st.tabs(["🕵️ Hidden City", "🔄 Throwaway Ticketing"])

    with tab1:
        st.subheader(_t("מצא הזדמנויות Hidden City", "Find Hidden City Opportunities"))
        with st.form("hc_form"):
            hc1, hc2 = st.columns(2)
            hc_origin = hc1.text_input(_t("מוצא", "Origin"), value="TLV", max_chars=3).upper()
            hc_real_dest = hc2.text_input(_t("יעד אמיתי", "Real destination"), placeholder="LHR / AMS / JFK", max_chars=3).upper()
            hc3, hc4 = st.columns(2)
            hc_date_out = hc3.date_input(_t("תאריך יציאה", "Departure date"), key="hc_out")
            hc_date_ret = hc4.date_input(_t("תאריך חזרה (אופציונלי)", "Return date (optional)"), value=None, key="hc_ret")
            hc_submit = st.form_submit_button(_t("🔍 חפש הזדמנויות", "🔍 Search Opportunities"), use_container_width=True)

        if hc_submit and hc_real_dest:
            with st.spinner(_t("מחפש hidden city deals... (עשוי לקחת כ-30 שניות)", "Searching hidden city deals... (may take ~30 seconds)")):
                deals = hidden_city.find_hidden_city_deals(
                    origin=hc_origin,
                    real_destination=hc_real_dest,
                    date_out=str(hc_date_out),
                    date_return=str(hc_date_ret) if hc_date_ret else "",
                )

            if not deals:
                st.info(_t("לא נמצאו הזדמנויות hidden city לנתיב זה.", "No hidden city opportunities found for this route."))
            elif "error" in (deals[0] if deals else {}):
                st.error(f"{_t('שגיאה', 'Error')}: {deals[0]['error']}")
            else:
                st.success(f"✅ {_t('נמצאו', 'Found')} {len(deals)} {_t('הזדמנויות', 'opportunities')}!")
                for d in deals:
                    savings = d.get("savings", 0)
                    savings_pct = d.get("savings_pct", 0)
                    color = "🟢" if savings_pct > 25 else "🟡"
                    with st.expander(f"{color} {d.get('route','')} — {_t('חיסכון', 'Saving')} ${savings:,.0f} ({savings_pct:.0f}%)", expanded=savings_pct > 20):
                        c1, c2, c3 = st.columns(3)
                        c1.metric(_t("מחיר hidden", "Hidden price"), f"${d.get('price_hidden',0):,.0f}")
                        c2.metric(_t("מחיר ישיר", "Direct price"), f"${d.get('price_direct',0):,.0f}")
                        c3.metric(_t("חיסכון", "Saving"), f"${savings:,.0f}")
                        st.write(f"**{_t('חברה', 'Airline')}:** {d.get('airline','')}")
                        st.write(f"**{_t('למה עובד', 'Why it works')}:** {d.get('why_works','')}")
                        st.write(f"**{_t('סיכון', 'Risk')}:** {d.get('risk_level','')}")
                        st.warning(f"⚠️ {d.get('warning','')}")
                        if d.get("deep_link"):
                            st.markdown(f"[{_t('הזמן כ-', 'Book as going to ')}{d.get('book_as_if_going_to','')}]({d.get('deep_link','')})")

    with tab2:
        st.subheader(_t("🔄 Throwaway Ticketing — הלוך-חזור זול מ-One Way?", "🔄 Throwaway Ticketing — Round-trip cheaper than One Way?"))
        with st.form("ta_form"):
            ta1, ta2 = st.columns(2)
            ta_origin = ta1.text_input(_t("מוצא", "Origin"), value="TLV", max_chars=3).upper()
            ta_dest = ta2.text_input(_t("יעד", "Destination"), placeholder="NYC", max_chars=3).upper()
            ta_date = st.date_input(_t("תאריך יציאה", "Departure date"), key="ta_date")
            ta_submit = st.form_submit_button(_t("🔍 בדוק", "🔍 Check"), use_container_width=True)

        if ta_submit and ta_dest:
            with st.spinner(_t("משווה מחירים...", "Comparing prices...")):
                result = hidden_city.find_throwaway_ticketing(
                    ta_origin, ta_dest, str(ta_date)
                )

            if result and "error" not in result:
                c1, c2, c3 = st.columns(3)
                c1.metric("One Way", f"${result.get('oneway_price',0):,.0f}")
                c2.metric("Round Trip", f"${result.get('roundtrip_price',0):,.0f}")
                saves = result.get("throwaway_saves", 0)
                c3.metric(_t("חיסכון", "Saving"), f"${saves:,.0f}", delta=f"{saves:+.0f}" if saves else None)

                if result.get("throwaway_worthwhile"):
                    st.success(f"✅ {result.get('recommendation','')}")
                else:
                    st.info(f"ℹ️ {result.get('recommendation','')}")
                if result.get("risk"):
                    st.warning(f"⚠️ {result['risk']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: RSS & Reddit Scanner
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📡 RSS & Reddit":
    st.title("📡 RSS & Reddit Real-Time Scanner")
    st.caption(_t("סורק Secret Flying, TheFlightDeal, Fly4Free, FlyerTalk ו-Reddit בזמן אמת.", "Scans Secret Flying, TheFlightDeal, Fly4Free, FlyerTalk and Reddit in real time."))

    col_scan1, col_scan2 = st.columns(2)
    if col_scan1.button(_t("🔄 סרוק RSS עכשיו", "🔄 Scan RSS Now"), use_container_width=True):
        with st.spinner(_t("סורק RSS feeds...", "Scanning RSS feeds...")):
            new_deals = rss_scanner.scan_rss_feeds()
        st.success(f"✅ {_t('נמצאו', 'Found')} {len(new_deals)} {_t('דילים חדשים', 'new deals')}")
        st.session_state["rss_scanned"] = True

    if col_scan2.button(_t("🔴 חפש ב-Reddit", "🔴 Search Reddit"), use_container_width=True):
        with st.spinner(_t("מחפש ב-Reddit... (עשוי לקחת 30 שניות)", "Searching Reddit... (may take 30 seconds)")):
            reddit_deals = rss_scanner.scan_reddit_deals()
        if reddit_deals and "error" not in (reddit_deals[0] if reddit_deals else {}):
            st.success(f"✅ {_t('נמצאו', 'Found')} {len(reddit_deals)} {_t('דילים מ-Reddit', 'deals from Reddit')}")
        else:
            st.warning(_t("לא נמצאו דילים חדשים ב-Reddit.", "No new deals found on Reddit."))

    st.divider()

    min_score = st.slider(_t("ציון מינימלי", "Minimum score"), 0.0, 10.0, 5.0, 0.5)
    deals = rss_scanner.get_recent_rss_deals(limit=50, min_score=min_score)

    if not deals:
        st.info(_t("אין דילים במסד הנתונים. לחץ 'סרוק RSS עכשיו' להתחלה.", "No deals in database. Click 'Scan RSS Now' to start."))
    else:
        st.write(f"**{len(deals)} {_t('דילים', 'deals')} ({_t('ציון', 'score')} ≥ {min_score}):**")

        unseen = rss_scanner.get_unseen_deals(min_score=6.0)
        if unseen:
            st.markdown(f"### 🔥 {_t('חדשים — לא נצפו', 'New — Unseen')}")
            for d in unseen[:5]:
                score = d.get("score", 0)
                color = "🔴" if score >= 8 else "🟠" if score >= 6 else "🟡"
                with st.expander(f"{color} [{score:.1f}] {d.get('title','')[:80]}", expanded=score >= 8):
                    st.write(d.get("description", "")[:300])
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**{_t('מקור', 'Source')}:** {d.get('source','')}")
                    if d.get("price"):
                        c2.metric(_t("מחיר", "Price"), f"${d['price']:.0f}")
                    c3.write(f"**{_t('ציון', 'Score')}:** {score:.1f}/10")
                    if d.get("url"):
                        st.markdown(f"[🔗 {_t('לדיל המלא', 'Full deal')}]({d['url']})")
                    if st.button(_t("✓ סמן כנצפה", "✓ Mark as seen"), key=f"seen_{d['id']}"):
                        rss_scanner.mark_seen(d["id"])
                        st.rerun()
            st.divider()

        st.markdown(f"### 📋 {_t('כל הדילים', 'All Deals')}")
        for d in deals:
            score = d.get("score", 0)
            icon = "🔴" if score >= 8 else "🟠" if score >= 6 else "🟡"
            title = d.get("title", "")[:70]
            source = d.get("source", "")
            price = d.get("price")
            price_txt = f" | ${price:.0f}" if price else ""
            with st.expander(f"{icon} {title}{price_txt} [{source}]"):
                st.write(d.get("description", "")[:400])
                if d.get("url"):
                    st.markdown(f"[🔗 {_t('לדיל', 'Deal')}]({d['url']})")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Auto-Book
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚡ Auto-Book":
    st.title("⚡ Auto-Book Engine")
    st.caption(_t("הגדר כלל: 'אם TLV→BKK < $350 — שלח התראה ופתח browser'", "Set a rule: 'If TLV→BKK < $350 — send alert and open browser'"))

    tab_rules, tab_log, tab_passenger = st.tabs([_t("📋 כללים", "📋 Rules"), _t("📜 לוג", "📜 Log"), _t("👤 פרטי נוסע", "👤 Passenger Details")])

    with tab_rules:
        st.subheader(_t("➕ הוסף כלל חדש", "➕ Add New Rule"))
        auto_book.ensure_auto_book_table()

        with st.form("ab_add_rule"):
            ab1, ab2 = st.columns(2)
            ab_name = ab1.text_input(_t("שם הכלל", "Rule name"), placeholder=_t("TLV-NYC זול", "Cheap TLV-NYC"))
            ab_mode = ab2.selectbox(_t("מצב", "Mode"), ["notify", "open_browser", "auto_fill"],
                                     format_func=lambda x: {"notify": _t("📲 התראה בלבד", "📲 Alert only"), "open_browser": _t("🌐 פתח browser", "🌐 Open browser"), "auto_fill": _t("🤖 מלא אוטומטית", "🤖 Auto-fill")}[x])
            ab3, ab4, ab5 = st.columns(3)
            ab_origin = ab3.text_input(_t("מוצא", "Origin"), value="TLV", max_chars=3).upper()
            ab_dest = ab4.text_input(_t("יעד", "Destination"), placeholder="NYC", max_chars=3).upper()
            ab_max_price = ab5.number_input(_t("מחיר מקסימלי ($)", "Max price ($)"), min_value=50, value=400)

            ab6, ab7 = st.columns(2)
            ab_date_from = ab6.text_input(_t("תאריך מ- (YYYY-MM-DD)", "Date from (YYYY-MM-DD)"), placeholder="2025-06-01")
            ab_date_to = ab7.text_input(_t("תאריך עד (YYYY-MM-DD)", "Date to (YYYY-MM-DD)"), placeholder="2025-09-01")

            ab_submit = st.form_submit_button(_t("➕ הוסף כלל", "➕ Add Rule"), use_container_width=True)

        if ab_submit and ab_name and ab_dest:
            rule_id = auto_book.add_rule(
                name=ab_name, origin=ab_origin, destination=ab_dest,
                max_price=ab_max_price, date_from=ab_date_from,
                date_to=ab_date_to, mode=ab_mode,
            )
            st.success(f"✅ {_t('כלל', 'Rule')} #{rule_id} {_t('נוסף', 'added')}!")
            st.rerun()

        st.divider()
        st.subheader(_t("📋 כללים פעילים", "📋 Active Rules"))
        rules = auto_book.get_rules(enabled_only=False)
        if not rules:
            st.info(_t("אין כללים. הוסף כלל למעלה.", "No rules. Add a rule above."))
        else:
            for rule in rules:
                enabled = bool(rule.get("enabled", 1))
                icon = "🟢" if enabled else "⚫"
                triggered = rule.get("trigger_count", 0)
                with st.expander(f"{icon} {rule['name']} — {rule['origin']}→{rule['destination']} < ${rule['max_price']}"):
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**{_t('מצב', 'Mode')}:** {rule.get('mode','notify')}")
                    c2.metric(_t("הופעל", "Triggered"), f"{triggered}x")
                    c3.write(f"**{_t('נוצר', 'Created')}:** {rule.get('created_at','')[:10]}")
                    if rule.get("triggered_at"):
                        st.write(f"**{_t('הופעל לאחרונה', 'Last triggered')}:** {rule['triggered_at'][:16]}")

                    btn1, btn2 = st.columns(2)
                    if btn1.button(_t("🔄 הפעל/כבה", "🔄 Enable/Disable"), key=f"toggle_{rule['id']}"):
                        auto_book.toggle_rule(rule["id"], not enabled)
                        st.rerun()
                    if btn2.button(_t("🗑 מחק", "🗑 Delete"), key=f"del_rule_{rule['id']}"):
                        auto_book.delete_rule(rule["id"])
                        st.rerun()

    with tab_log:
        st.subheader(_t("📜 לוג הזמנות", "📜 Booking Log"))
        log = auto_book.get_booking_log(limit=20)
        if not log:
            st.info(_t("אין רשומות בלוג עדיין.", "No log entries yet."))
        else:
            for entry in log:
                st.write(f"**{entry.get('rule_name','')}** | {entry.get('action','')} | {entry.get('booked_at','')[:16]}")
                if entry.get("deal_json"):
                    try:
                        deal = json.loads(entry["deal_json"])
                        st.json(deal)
                    except Exception:
                        pass
                st.divider()

    with tab_passenger:
        st.subheader(_t("👤 פרטי נוסע לאוטו-מילוי", "👤 Passenger Details for Auto-fill"))
        st.caption(_t("פרטים אלו ישמשו למילוי אוטומטי בטפסי הזמנה (auto_fill mode)", "These details will be used for auto-filling booking forms (auto_fill mode)"))

        with st.form("passenger_form"):
            p1, p2 = st.columns(2)
            p_first = p1.text_input(_t("שם פרטי", "First name"), value=os.environ.get("PASSENGER_FIRST_NAME", ""))
            p_last = p2.text_input(_t("שם משפחה", "Last name"), value=os.environ.get("PASSENGER_LAST_NAME", ""))
            p3, p4 = st.columns(2)
            p_email = p3.text_input(_t("אימייל", "Email"), value=os.environ.get("PASSENGER_EMAIL", ""))
            p_phone = p4.text_input(_t("טלפון", "Phone"), value=os.environ.get("PASSENGER_PHONE", ""))
            p5, p6 = st.columns(2)
            p_passport = p5.text_input(_t("מספר דרכון", "Passport number"), value=os.environ.get("PASSENGER_PASSPORT", ""), type="password")
            p_dob = p6.text_input(_t("תאריך לידה (YYYY-MM-DD)", "Date of birth (YYYY-MM-DD)"), value=os.environ.get("PASSENGER_DOB", ""))
            p_submit = st.form_submit_button(_t("💾 שמור", "💾 Save"), use_container_width=True)

        if p_submit:
            auto_book.save_passenger_config({
                "first_name": p_first, "last_name": p_last,
                "email": p_email, "phone": p_phone,
                "passport": p_passport, "dob": p_dob,
            })
            st.success(_t("✅ נשמר ב-.env", "✅ Saved to .env"))

        playwright_ok = auto_book.check_playwright_installed()
        if playwright_ok:
            st.success(_t("✅ Playwright מותקן — auto_fill mode זמין", "✅ Playwright installed — auto_fill mode available"))
        else:
            st.warning(_t("⚠️ Playwright לא מותקן. הרץ: `pip install playwright && playwright install chromium`", "⚠️ Playwright not installed. Run: `pip install playwright && playwright install chromium`"))


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Price DNA
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🧬 Price DNA":
    st.title(_t("🧬 Price DNA — פרופיל מחירים אישי", "🧬 Price DNA — Personal Price Profile"))
    st.caption(_t("מנתח את כל ההיסטוריה שלך ובונה פרופיל: מתי זול, מתי יקר, מה התבנית.", "Analyzes your entire history and builds a profile: when it's cheap, when it's expensive, what the pattern is."))

    watch_items = db.get_watch_items()
    _all_history_label = _t("כל ההיסטוריה", "All History")
    options = [_all_history_label] + [f"{w['name'] or w['origin']+'→'+w['destination']} (#{w['id']})" for w in watch_items]

    selected = st.selectbox(_t("בחר מסלול לניתוח", "Select route to analyze"), options)
    watch_id = None
    if selected != _all_history_label:
        import re as _re
        m = _re.search(r'#(\d+)', selected)
        if m:
            watch_id = int(m.group(1))

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(_t("🧬 נתח DNA (סטטיסטי)", "🧬 Analyze DNA (Statistical)"), use_container_width=True):
            with st.spinner(_t("מנתח היסטוריה...", "Analyzing history...")):
                dna = price_dna.generate_price_dna(watch_id)
            if "error" in dna:
                st.warning(dna["error"])
            else:
                st.session_state["price_dna_result"] = dna

    with col_b:
        if st.button(_t("🤖 AI Price DNA (עמוק יותר)", "🤖 AI Price DNA (Deeper)"), use_container_width=True):
            with st.spinner(_t("Claude מנתח DNA... (30-60 שניות)", "Claude analyzing DNA... (30-60 seconds)")):
                ai_result = price_dna.get_ai_price_dna(watch_id)
            if "error" in ai_result:
                st.error(ai_result["error"])
            else:
                st.session_state["ai_price_dna"] = ai_result
                if "dna" in ai_result:
                    st.session_state["price_dna_result"] = ai_result["dna"]

    dna_data = st.session_state.get("price_dna_result")
    if dna_data and "error" not in dna_data:
        st.divider()
        currency = dna_data.get("currency", "USD")
        price_range = dna_data.get("price_range", {})
        current = dna_data.get("current_price", 0)
        avg = price_range.get("avg", 0)
        vs_avg = dna_data.get("price_now_vs_avg", 0)

        st.subheader(_t("📊 סטטיסטיקות מחיר", "📊 Price Statistics"))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(_t("מינימום", "Minimum"), f"${price_range.get('min',0):,.0f}")
        m2.metric(_t("מקסימום", "Maximum"), f"${price_range.get('max',0):,.0f}")
        m3.metric(_t("ממוצע", "Average"), f"${avg:,.0f}")
        delta_color = "inverse" if vs_avg > 0 else "normal"
        m4.metric(_t("מחיר עכשיו vs ממוצע", "Price now vs average"), f"{vs_avg:+.1f}%")

        col1, col2, col3 = st.columns(3)
        col1.info(f"📅 **{_t('חודש זול', 'Cheapest month')}:** {dna_data.get('best_month','?')}")
        col2.warning(f"📅 **{_t('חודש יקר', 'Most expensive month')}:** {dna_data.get('worst_month','?')}")
        col3.success(f"📆 **{_t('יום זול', 'Cheapest day')}:** {dna_data.get('best_day_of_week','?')}")

        trend = dna_data.get("trend", "stable")
        vol = dna_data.get("volatility_pct", 0)
        trend_icon = "📈" if trend == "rising" else "📉" if trend == "falling" else "➡️"
        st.write(f"{trend_icon} **{_t('טרנד', 'Trend')}:** {trend} | **{_t('תנודתיות', 'Volatility')}:** {vol:.1f}%")

        savings = dna_data.get("potential_savings", 0)
        savings_pct = dna_data.get("potential_savings_pct", 0)
        st.success(f"💰 **{_t('חיסכון פוטנציאלי', 'Potential savings')}:** ${savings:,.0f} ({savings_pct:.1f}%)")

        if dna_data.get("month_avg"):
            st.subheader(_t("📅 ממוצע חודשי", "📅 Monthly Average"))
            month_data = dna_data["month_avg"]
            fig = go.Figure(go.Bar(
                x=list(month_data.keys()),
                y=list(month_data.values()),
                marker_color=["#00ff88" if v == min(month_data.values()) else "#ff4444" if v == max(month_data.values()) else "#667eea" for v in month_data.values()]
            ))
            fig.update_layout(template="plotly_dark", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    ai_dna = st.session_state.get("ai_price_dna")
    if ai_dna and "error" not in ai_dna:
        st.divider()
        st.subheader(_t("🤖 ניתוח AI", "🤖 AI Analysis"))

        verdict = ai_dna.get("verdict", "")
        emoji = ai_dna.get("verdict_emoji", "")
        confidence = ai_dna.get("confidence", "")

        if "קנה" in verdict or "🟢" in emoji:
            st.success(f"{emoji} **{verdict}** | {_t('ביטחון', 'Confidence')}: {confidence}")
        elif "המתן" in verdict or "🔴" in emoji:
            st.error(f"{emoji} **{verdict}** | {_t('ביטחון', 'Confidence')}: {confidence}")
        else:
            st.warning(f"{emoji} **{verdict}** | {_t('ביטחון', 'Confidence')}: {confidence}")

        st.write(f"**{_t('דפוס מרכזי', 'Main pattern')}:** {ai_dna.get('main_pattern','')}")
        st.write(f"**{_t('מתי לקנות', 'When to buy')}:** {ai_dna.get('best_booking_window','')}")
        st.write(f"**{_t('תחזית 2 חודשים', '2-month forecast')}:** {ai_dna.get('forecast_2months','')}")
        st.write(f"**{_t('טיפ חיסכון', 'Savings tip')}:** {ai_dna.get('savings_tip','')}")

        actions = ai_dna.get("actions", [])
        if actions:
            st.write(f"**{_t('פעולות מומלצות', 'Recommended actions')}:**")
            for action in actions:
                st.write(f"• {action}")

    if watch_id:
        st.divider()
        st.subheader(_t("🎯 Sweet Spot אישי", "🎯 Personal Sweet Spot"))
        if st.button(_t("מצא Sweet Spot", "Find Sweet Spot")):
            spot = price_dna.find_personal_sweet_spot(watch_id)
            if spot and "error" not in spot:
                if "sweet_spot" in spot:
                    st.success(f"✅ **Sweet Spot:** {spot['sweet_spot']}")
                    col1, col2 = st.columns(2)
                    col1.metric(_t("מחיר מינימלי", "Minimum price"), f"${spot.get('min_price',0):,.0f}")
                    col2.metric(_t("תאריך", "Date"), spot.get("min_price_date",""))
                    if spot.get("is_past_sweet_spot"):
                        st.warning(_t("⚠️ עברת את ה-sweet spot — קנה כמה שקודם!", "⚠️ You've passed the sweet spot — buy as soon as possible!"))
                elif "best_period" in spot:
                    st.info(f"**{_t('תקופה מומלצת', 'Recommended period')}:** {spot.get('best_period','')}")
                    st.write(f"**{_t('מחיר באותה תקופה', 'Price in that period')}:** ${spot.get('best_period_price',0):,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Positioning
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ Positioning":
    st.title("🗺️ Positioning Flight Optimizer")
    st.caption(_t("האם כדאי לטוס תחילה לאמסטרדם/לונדון ומשם לכיוון היעד? לפעמים שווה 40% פחות!", "Is it worth flying first to Amsterdam/London and then to your destination? Sometimes saves 40%!"))

    st.divider()

    with st.form("pos_form"):
        p1, p2 = st.columns(2)
        pos_dest = p1.text_input(_t("יעד סופי (IATA)", "Final destination (IATA)"), placeholder="JFK / BKK / LAX").upper()
        pos_date = p2.date_input(_t("תאריך יציאה", "Departure date"))
        p3, p4 = st.columns(2)
        pos_ret = p3.date_input(_t("תאריך חזרה (אופציונלי)", "Return date (optional)"), value=None)
        pos_travelers = p4.number_input(_t("נוסעים", "Passengers"), min_value=1, max_value=9, value=1)
        pos_budget = st.number_input(_t("תקציב ($, 0 = ללא הגבלה)", "Budget ($, 0 = no limit)"), min_value=0, value=0)
        pos_submit = st.form_submit_button(_t("🔍 מצא הזדמנויות Positioning", "🔍 Find Positioning Opportunities"), use_container_width=True)

    if pos_submit and pos_dest:
        with st.spinner(_t("מחפש הזדמנויות positioning... (עשוי לקחת 30-60 שניות)", "Searching positioning opportunities... (may take 30-60 seconds)")):
            opps = positioning.find_positioning_opportunities(
                destination=pos_dest,
                travel_date=str(pos_date),
                return_date=str(pos_ret) if pos_ret else "",
                budget=float(pos_budget) if pos_budget else 0,
                travelers=int(pos_travelers),
            )

        if not opps:
            st.info(_t("לא נמצאו הזדמנויות positioning לנתיב זה.", "No positioning opportunities found for this route."))
        elif "error" in (opps[0] if opps else {}):
            st.error(f"{_t('שגיאה', 'Error')}: {opps[0]['error']}")
        else:
            st.success(f"✅ {_t('נמצאו', 'Found')} {len(opps)} {_t('הזדמנויות', 'opportunities')}!")
            for opp in opps:
                savings = opp.get("savings", 0)
                savings_pct = opp.get("savings_pct", 0)
                hub = opp.get("positioning_airport", "")
                hub_city = opp.get("positioning_city", hub)
                color = "🟢" if savings_pct > 20 else "🟡"
                worth_it = opp.get("worth_it", False)

                with st.expander(f"{color} {_t('דרך', 'Via')} {hub_city} ({hub}) — {_t('חיסכון', 'Saving')} ${savings:,.0f} ({savings_pct:.0f}%)", expanded=worth_it):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("TLV→" + hub, f"${opp.get('tlv_to_hub_price',0):,.0f}")
                    c2.metric(hub + "→" + pos_dest, f"${opp.get('hub_to_dest_price',0):,.0f}")
                    c3.metric(_t("סה״כ vs ישיר", "Total vs Direct"), f"${opp.get('total_positioning',0):,.0f} vs ${opp.get('direct_tlv_to_dest',0):,.0f}")

                    st.write(f"**{_t('חברת positioning', 'Positioning airline')}:** {opp.get('positioning_airline','')}")
                    st.write(f"**{_t('זמן נסיעה נוסף', 'Extra travel time')}:** {opp.get('extra_travel_time_hours',0)} {_t('שעות', 'hours')}")
                    if opp.get("overnight_needed"):
                        st.info(_t("🌙 דורש לינה בעיר הביניים", "🌙 Requires overnight stay in the connecting city"))
                    st.write(f"**{_t('למה משתלם', 'Why it works')}:** {opp.get('why','')}")
                    st.write(f"**{_t('טיפים', 'Tips')}:** {opp.get('tips','')}")

                    if worth_it and opp.get("overnight_needed"):
                        if st.button(f"🌙 {_t('ניתוח לינה ב-', 'Overnight analysis in ')}{hub_city}", key=f"overnight_{hub}"):
                            with st.spinner(_t("מנתח אפשרות לינה...", "Analyzing overnight option...")):
                                ov_analysis = positioning.analyze_overnight_positioning(hub, pos_dest, str(pos_date))
                            if ov_analysis and "error" not in ov_analysis:
                                st.write(f"**{_t('עלות לינה', 'Accommodation cost')}:** ${ov_analysis.get('accommodation_price',0):,.0f} ({ov_analysis.get('accommodation_type','')})")
                                st.write(f"**{_t('שווה להוסיף לינה?', 'Worth adding overnight?')}** {_t('✅ כן', '✅ Yes') if ov_analysis.get('worth_adding_night') else _t('❌ לא', '❌ No')}")
                                activities = ov_analysis.get("top_activities", [])
                                if activities:
                                    st.write(f"**{_t('מה לעשות בלילה אחד', 'What to do in one night')}:**")
                                    for act in activities:
                                        st.write(f"• {act}")

    st.divider()
    st.subheader(_t("✈️ נתיבי Positioning הזולים ביותר מ-TLV", "✈️ Cheapest Positioning Routes from TLV"))
    if st.button(_t("🔍 מצא נתיבי positioning זולים", "🔍 Find cheap positioning routes"), use_container_width=True):
        with st.spinner(_t("בודק מחירים...", "Checking prices...")):
            cheap_routes = positioning.get_cheapest_tlv_positioning_routes()
        if cheap_routes and "error" not in (cheap_routes[0] if cheap_routes else {}):
            for r in cheap_routes[:10]:
                st.write(f"✈️ **{r.get('city','')} ({r.get('airport','')})** — {_t('מ-', 'from $')}{r.get('price_from',0)} | {r.get('airline','')} | {r.get('why_good_positioning','')}")

    st.divider()
    st.subheader(_t("🧮 מחשבון ROI", "🧮 ROI Calculator"))
    with st.form("roi_form"):
        r1, r2, r3 = st.columns(3)
        roi_tlv_hub = r1.number_input("TLV→Hub ($)", min_value=0, value=80)
        roi_hub_dest = r2.number_input("Hub→Dest ($)", min_value=0, value=350)
        roi_direct = r3.number_input(_t("ישיר מ-TLV ($)", "Direct from TLV ($)"), min_value=0, value=600)
        r4, r5 = st.columns(2)
        roi_extra_time = r4.number_input(_t("זמן נוסף (שעות)", "Extra time (hours)"), min_value=0.0, value=6.0)
        roi_hourly = r5.number_input(_t("שווי שעה שלך ($)", "Your hourly rate ($)"), min_value=0, value=20)
        roi_calc = st.form_submit_button(_t("🧮 חשב ROI", "🧮 Calculate ROI"))

    if roi_calc:
        roi = positioning.calculate_positioning_roi(
            tlv_to_hub=roi_tlv_hub,
            hub_to_dest=roi_hub_dest,
            direct_price=roi_direct,
            extra_time_hours=roi_extra_time,
            hourly_rate=roi_hourly,
        )
        st.write(roi.get("verdict", ""))
        c1, c2, c3 = st.columns(3)
        c1.metric(_t("חיסכון גולמי", "Gross savings"), f"${roi.get('gross_savings',0):,.0f} ({roi.get('gross_savings_pct',0):.1f}%)")
        c2.metric(_t("עלות זמן", "Time cost"), f"${roi.get('time_cost',0):,.0f}")
        c3.metric(_t("חיסכון נטו", "Net savings"), f"${roi.get('net_savings',0):,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: WhatsApp Bot
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💬 WhatsApp Bot":
    st.title(_t("💬 WhatsApp Bot — חיפוש טיסות בוואטסאפ", "💬 WhatsApp Bot — Flight Search via WhatsApp"))
    st.caption(_t("שלח 'TLV NYC 15/06' בוואטסאפ וקבל מחירים תוך שניות.", "Send 'TLV NYC 15/06' on WhatsApp and get prices within seconds."))

    tab_setup, tab_test, tab_stats = st.tabs([_t("⚙️ הגדרות Twilio", "⚙️ Twilio Settings"), _t("🧪 בדיקה", "🧪 Testing"), _t("📊 סטטיסטיקות", "📊 Statistics")])

    with tab_setup:
        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        twilio_from = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

        if twilio_sid and twilio_token:
            st.success(_t("✅ Twilio מחובר", "✅ Twilio connected"))
        else:
            st.warning(_t("⚠️ Twilio לא מוגדר", "⚠️ Twilio not configured"))

        with st.expander(_t("📖 איך מגדירים Twilio WhatsApp Sandbox?", "📖 How to set up Twilio WhatsApp Sandbox?"), expanded=not bool(twilio_sid)):
            st.markdown(_t("""
**שלב 1 — צור חשבון Twilio:**
1. עבור ל-twilio.com והרשם (חינם)
2. קבל **Account SID** ו-**Auth Token** מלוח הבקרה

**שלב 2 — הפעל WhatsApp Sandbox:**
1. ב-Twilio Console → Messaging → Try it Out → Send a WhatsApp message
2. עקוב אחרי ההוראות לחיבור ה-Sandbox
3. שמור את מספר ה-Sandbox (בד"כ +14155238886)

**שלב 3 — הגדר Webhook:**
1. הרץ את האפליקציה עם ngrok: `ngrok http 8501`
2. הגדר את כתובת ה-webhook ל: `https://YOUR_NGROK/whatsapp_webhook`

**פקודות בוואטסאפ:**
- `TLV NYC 15/06` — חפש טיסה
- `דיל` — דילים חמים
- `מחירים` — רשימת מעקב
- `עזרה` — עזרה
            """, """
**Step 1 — Create a Twilio account:**
1. Go to twilio.com and sign up (free)
2. Get **Account SID** and **Auth Token** from the dashboard

**Step 2 — Enable WhatsApp Sandbox:**
1. In Twilio Console → Messaging → Try it Out → Send a WhatsApp message
2. Follow the instructions to connect the Sandbox
3. Save the Sandbox number (usually +14155238886)

**Step 3 — Set up Webhook:**
1. Run the app with ngrok: `ngrok http 8501`
2. Set the webhook URL to: `https://YOUR_NGROK/whatsapp_webhook`

**WhatsApp commands:**
- `TLV NYC 15/06` — Search flight
- `deal` — Hot deals
- `prices` — Watchlist
- `help` — Help
            """))

        with st.form("wa_config_form"):
            new_sid = st.text_input(_t("מזהה חשבון", "Account SID"), value=twilio_sid, type="password")
            new_auth = st.text_input(_t("אסימון אימות", "Auth Token"), value=twilio_token, type="password")
            new_from = st.text_input(_t("מספר WhatsApp שולח", "WhatsApp From Number"), value=twilio_from)
            wa_save = st.form_submit_button(_t("💾 שמור", "💾 Save"), use_container_width=True)

        if wa_save and new_sid and new_auth:
            _save_env("TWILIO_ACCOUNT_SID", new_sid)
            _save_env("TWILIO_AUTH_TOKEN", new_auth)
            _save_env("TWILIO_WHATSAPP_FROM", new_from)
            st.success(_t("✅ נשמר! הפעל מחדש.", "✅ Saved! Restart the app."))

    with tab_test:
        st.subheader(_t("🧪 בדיקת הבוט", "🧪 Bot Testing"))
        test_msg = st.text_input(_t("שלח הודעה לבוט", "Send a message to the bot"), placeholder="TLV NYC 15/06 / deal / help")
        if st.button(_t("📨 שלח", "📨 Send")) and test_msg:
            reply = whatsapp_bot.process_incoming_message("test_user", test_msg)
            st.text_area(_t("תגובת הבוט:", "Bot reply:"), value=reply, height=200)

        st.divider()
        st.subheader(_t("🔄 הרץ סדרת בדיקות", "🔄 Run Test Suite"))
        if st.button(_t("הרץ בדיקות אוטומטיות", "Run automatic tests")):
            results = whatsapp_bot.test_bot()
            for r in results:
                with st.expander(f"📩 Input: {r['input']}"):
                    st.write(r["reply"])

        st.divider()
        st.subheader(_t("📤 שלח הודעה אמיתית", "📤 Send Real Message"))
        with st.form("wa_send_form"):
            wa_to = st.text_input(_t("לאן לשלוח", "Send to"), placeholder="+972501234567")
            wa_msg = st.text_area(_t("הודעה", "Message"), placeholder="Hello! This is Noded...", height=80)
            wa_send = st.form_submit_button(_t("📤 שלח WhatsApp", "📤 Send WhatsApp"))

        if wa_send and wa_to and wa_msg:
            if os.environ.get("TWILIO_ACCOUNT_SID"):
                result = whatsapp_bot.send_whatsapp_message(wa_to, wa_msg)
                if "error" not in result:
                    st.success(_t("✅ נשלח!", "✅ Sent!"))
                else:
                    st.error(f"❌ {result['error']}")
            else:
                st.error(_t("❌ הגדר Twilio קודם", "❌ Configure Twilio first"))

    with tab_stats:
        stats = whatsapp_bot.get_stats()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(_t("סה״כ הודעות", "Total messages"), stats.get("total_messages", 0))
        m2.metric(_t("משתמשים", "Users"), stats.get("unique_users", 0))
        m3.metric(_t("היום", "Today"), stats.get("messages_today", 0))
        m4.metric(_t("חיפושי טיסות", "Flight searches"), stats.get("flight_searches", 0))

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL: AI Chat Assistant (floating, all pages)
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
_chat_label = _t("💬 שאל את ה-AI", "💬 Ask AI")
with st.expander(_chat_label, expanded=st.session_state.chat_open):
    st.caption(_t(
        "שאל כל שאלה על טיסות, מלונות, מחירים או תכנון טיול",
        "Ask anything about flights, hotels, prices or trip planning"
    ))

    # Show chat history
    for _cm in st.session_state.chat_messages[-6:]:  # last 6 messages
        with st.chat_message(_cm["role"]):
            st.markdown(_cm["content"])

    # Input
    _chat_input = st.chat_input(_t("כתוב שאלה...", "Type a question..."), key="global_chat")
    if _chat_input:
        st.session_state.chat_messages.append({"role": "user", "content": _chat_input})
        st.session_state.chat_open = True

        if ai_client.is_configured():
            # Build context from current watches
            _watch_ctx = ""
            _ctx_items = db.get_all_watch_items(enabled_only=False)
            if _ctx_items:
                _ctx_lines = []
                for _ci in _ctx_items[:5]:
                    _cl = db.get_last_price(_ci["id"])
                    _cp = f"{_cl['price']:.0f} {_cl['currency']}" if _cl else _t("אין מחיר", "no price")
                    _ctx_lines.append(f"- {_ci['name']} → {_ci['destination']}: {_cp}")
                _watch_ctx = _t("המעקבים הפעילים שלי:\n", "My active watches:\n") + "\n".join(_ctx_lines) + "\n\n"

            _lang_instr = "Respond in English." if _lang == "en" else "השב בעברית."
            _sys = (
                f"You are a smart travel assistant for an Israeli travel price tracker app. "
                f"Help with flights, hotels, prices, visa info, trip planning. Be concise (2-4 sentences). "
                f"{_lang_instr}\n\n{_watch_ctx}"
            )

            # Build prompt from last 6 turns
            _history = st.session_state.chat_messages[-6:]
            _prompt = "\n".join(
                f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
                for m in _history
            )

            with st.spinner(_t("חושב...", "Thinking...")):
                try:
                    _reply = ai_client.ask(prompt=_prompt, system=_sys, max_tokens=300) or ""
                    st.session_state.chat_messages.append({"role": "assistant", "content": _reply})
                except Exception as _ce:
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": _t(f"שגיאה: {str(_ce)[:80]}", f"Error: {str(_ce)[:80]}")
                    })
            st.rerun()
        else:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": _t("חסר GEMINI_API_KEY", "Missing GEMINI_API_KEY")
            })
            st.rerun()

    if st.session_state.chat_messages:
        if st.button(_t("🗑 נקה שיחה", "🗑 Clear chat"), key="clear_chat"):
            st.session_state.chat_messages = []
            st.rerun()
