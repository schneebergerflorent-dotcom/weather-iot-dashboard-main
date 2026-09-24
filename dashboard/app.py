"""
Streamlit cloud dashboard — Weather IoT project (Atmospheric Intelligence theme)
Calls the Flask middleware; never touches BigQuery directly.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
import api_client as api

# ── Lausanne background photo ─────────────────────────────────────────────────
_PHOTO_PATH = Path(__file__).parent / "static" / "lausanne.jpg"


def _lausanne_bg() -> str:
    """Return static-file URL if the photo exists, else empty string."""
    return "app/static/lausanne.jpg" if _PHOTO_PATH.exists() else ""

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Indoor Climate Pro",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load fonts via <link> tags (more reliable than @import in injected <style>) ─
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# ── Global CSS — Atmospheric Intelligence ─────────────────────────────────────
st.markdown("""
<style>
.material-symbols-outlined {
  font-family: 'Material Symbols Outlined';
  font-weight: normal;
  font-style: normal;
  font-size: 28px;
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  display: inline-block;
  white-space: nowrap;
  direction: ltr;
  font-feature-settings: 'liga';
  -webkit-font-smoothing: antialiased;
}

html {
    font-size: 20px !important;
}
html, body, [class*="css"], p, div, span, h1, h2, h3, h4, h5, h6 {
    font-family: 'Space Grotesk', sans-serif !important;
}

/* ── Background ── */
.stApp {
    background: linear-gradient(135deg, #1a1f2e 0%, #1e1b4b 50%, #4c1d95 100%);
    min-height: 100vh;
}
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
}

/* ── Alert banners — high-contrast on dark bg ── */
div[data-testid="stAlert"] {
    border-radius: 12px !important;
    background: rgba(255, 80, 80, 0.18) !important;
    border: 1px solid rgba(255, 100, 100, 0.35) !important;
}
div[data-testid="stAlert"] p,
div[data-testid="stAlert"] span,
div[data-testid="stAlert"] div,
div[data-testid="stAlert"] strong {
    color: #ffdad6 !important;
    font-weight: 500 !important;
}
div[data-testid="stAlert"][kind="warning"],
div[data-testid="stAlert"][data-baseweb="notification"][kind="warning"] {
    background: rgba(245, 158, 11, 0.18) !important;
    border: 1px solid rgba(245, 158, 11, 0.35) !important;
}
div[data-testid="stAlert"][kind="warning"] p,
div[data-testid="stAlert"][kind="warning"] span {
    color: #fde68a !important;
}
/* Streamlit wraps alerts differently across versions */
.stAlert > div { border-radius: 12px !important; }

/* ── Metric cards ── */
.metric-card {
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.15);
    box-shadow: inset 2px 2px 4px rgba(255,255,255,0.04);
    border-radius: 16px;
    padding: 22px 20px 18px;
    margin-bottom: 6px;
    overflow: hidden;
    transition: all 0.3s ease;
}
.metric-card:hover {
    background: rgba(255,255,255,0.09);
    border-color: rgba(255,255,255,0.28);
}
.metric-icon-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 14px;
}
.metric-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 10px currentColor;
    margin-top: 6px;
}
.metric-label {
    font-size: 0.63rem;
    color: #c7c4d7;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 5px;
    font-weight: 500;
}
.metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: #e0e3e5;
    line-height: 1.1;
    letter-spacing: -0.02em;
}
.metric-unit {
    font-size: 0.8rem;
    font-weight: 400;
    opacity: 0.72;
}
.metric-status {
    font-size: 0.6rem;
    font-weight: 600;
    margin-top: 10px;
    display: flex;
    align-items: center;
    gap: 5px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Section title ── */
.section-title {
    font-size: 0.58rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: #c7c4d7;
    margin: 0 0 14px 0;
    display: flex;
    align-items: center;
    gap: 10px;
    opacity: 0.65;
}
.section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(to right, rgba(255,255,255,0.18) 0%, transparent 100%);
}

/* ── Info caption (timestamp / pressure) ── */
.info-caption {
    font-size: 0.72rem;
    color: rgba(199,196,215,0.75);
    margin: 6px 0 16px 0;
    padding: 8px 14px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 8px;
    display: inline-block;
    letter-spacing: 0.01em;
}

/* ── Outdoor atmospheric panel ── */
.outdoor-panel {
    position: relative;
    min-height: 460px;
    border-radius: 20px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.15);
    box-shadow: inset 2px 2px 4px rgba(255,255,255,0.04);
    margin-bottom: 8px;
}
.outdoor-panel-bg {
    position: absolute;
    inset: 0;
    background: linear-gradient(145deg, #0f0c29 0%, #302b63 45%, #24243e 100%);
}
.outdoor-panel-photo {
    position: absolute;
    inset: 0;
    background-size: cover;
    background-position: center 60%;
    opacity: 0.75;
}
.outdoor-panel-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(
        to top,
        rgba(10,8,30,0.96) 0%,
        rgba(10,8,30,0.45) 45%,
        rgba(30,27,75,0.1) 100%
    );
}
.outdoor-panel-content {
    position: relative;
    z-index: 10;
    min-height: 460px;
    padding: 32px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    box-sizing: border-box;
}
.outdoor-layout {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 28px;
    align-items: flex-end;
}
.outdoor-location {
    font-size: 0.68rem;
    color: #c0c1ff;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 500;
    margin: 0 0 10px 0;
    display: flex;
    align-items: center;
    gap: 6px;
}
.outdoor-temp {
    font-size: 5rem;
    font-weight: 700;
    color: #ffffff;
    line-height: 1;
    letter-spacing: -0.04em;
    margin: 0;
}
.outdoor-condition {
    font-size: 1.25rem;
    color: rgba(255,255,255,0.8);
    font-weight: 600;
    margin-top: 6px;
    text-transform: capitalize;
}
.outdoor-chips {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.outdoor-chip {
    background: rgba(255,255,255,0.1);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 14px;
    padding: 12px 18px;
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 155px;
}
.chip-icon { font-size: 1.25rem; }
.chip-label {
    font-size: 0.58rem;
    color: rgba(255,255,255,0.5);
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin: 0;
}
.chip-value {
    font-size: 0.92rem;
    font-weight: 700;
    color: #ffffff;
    margin: 0;
}

/* ── Forecast individual card ── */
.fc-card {
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 16px;
    padding: 20px 10px 18px;
    text-align: center;
    transition: all 0.3s ease;
    margin-bottom: 6px;
    min-height: 190px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.fc-card:hover {
    background: rgba(255,255,255,0.09);
    border-color: rgba(255,255,255,0.28);
    transform: translateY(-3px);
}
.fc-day {
    font-size: 0.62rem;
    font-weight: 700;
    color: #c7c4d7;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 12px;
}
.fc-icon-ring {
    width: 54px;
    height: 54px;
    background: rgba(192,193,255,0.08);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 0 auto 10px;
    border: 1px solid rgba(192,193,255,0.18);
    font-size: 1.6rem;
    line-height: 1;
}
.fc-temp { font-size: 0.9rem; font-weight: 700; color: #e0e3e5; margin: 4px 0; }
.fc-pop { font-size: 0.62rem; color: #c0c1ff; font-weight: 600; margin-top: 4px; }
.fc-desc { font-size: 0.56rem; color: #c7c4d7; margin-top: 4px; line-height: 1.4; opacity: 0.6; }

/* ── Stat tiles (Analytics) ── */
.stat-tile {
    background: rgba(255,255,255,0.05);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.15);
    box-shadow: inset 2px 2px 4px rgba(255,255,255,0.04);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 6px;
    transition: all 0.3s ease;
}
.stat-tile:hover { background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.28); }
.stat-icon-row { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.stat-label { font-size: 0.58rem; font-weight: 500; color: #c7c4d7; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 5px; }
.stat-value { font-size: 1.65rem; font-weight: 700; color: #e0e3e5; line-height: 1.1; letter-spacing: -0.02em; }
.stat-unit { font-size: 0.78rem; font-weight: 400; opacity: 0.68; }

/* ── Chart wrapper ── */
.chart-glass {
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 18px;
    padding: 22px 18px 8px;
    margin-bottom: 8px;
}
.chart-title { font-size: 1.05rem; font-weight: 600; color: #e0e3e5; margin: 0 0 2px 0; }
.chart-sub { font-size: 0.7rem; color: #c7c4d7; opacity: 0.6; margin: 0 0 12px 0; }
.chart-legend { display: flex; gap: 18px; margin-bottom: 10px; }
.legend-item { display: flex; align-items: center; gap: 7px; font-size: 0.72rem; font-weight: 500; color: #c7c4d7; }
.legend-bar { width: 22px; height: 3px; border-radius: 2px; display: inline-block; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 14px !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary span { color: #c7c4d7 !important; }

/* ── Streamlit chrome ── */
footer, #MainMenu, header { visibility: hidden; }
hr { border-color: rgba(255,255,255,0.08) !important; }

/* ── Explicit font-size overrides for Streamlit native elements ── */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span:not(.material-symbols-outlined) { font-size: 1rem !important; }
[data-testid="stSelectbox"] > label,
[data-testid="stRadio"] > label { font-size: 0.75rem !important; }
div[data-baseweb="select"] span,
div[data-baseweb="select"] div { font-size: 1rem !important; }
[data-testid="stCaption"] { font-size: 0.8rem !important; }
[data-testid="stMarkdownContainer"] p { font-size: 1rem !important; }
[data-testid="stDataFrame"] * { font-size: 0.9rem !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: rgba(11,15,16,0.96) !important;
    backdrop-filter: blur(30px) !important;
    border-right: 1px solid rgba(255,255,255,0.07) !important;
}
[data-testid="stSidebar"] * { font-family: 'Space Grotesk', sans-serif !important; }
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label { color: #c7c4d7 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 { color: #c0c1ff !important; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.07) !important; }

/* Sidebar brand block */
.sb-brand { padding: 8px 4px 16px; }
.sb-brand-title {
    font-size: 1.35rem;
    font-weight: 700;
    color: #c0c1ff;
    margin: 0 0 3px 0;
    line-height: 1.2;
}
.sb-brand-sub {
    font-size: 0.65rem;
    color: rgba(199,196,215,0.45);
    margin: 0;
    letter-spacing: 0.04em;
}

/* Sidebar nav — style radio as icon links */
[data-testid="stSidebar"] [data-testid="stRadio"] > label { display: none !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
    flex-direction: column !important;
    gap: 2px !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
    padding: 11px 14px !important;
    border-radius: 8px !important;
    border-left: 2px solid transparent !important;
    transition: all 0.15s !important;
    cursor: pointer !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    background: rgba(255,255,255,0.05) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"][aria-checked="true"] {
    background: rgba(192,193,255,0.1) !important;
    border-left-color: #c0c1ff !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[aria-checked="true"] p {
    color: #c0c1ff !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p { font-size: 0.88rem !important; }

/* Sidebar refresh button */
[data-testid="stSidebar"] .stButton button {
    background: rgba(192,193,255,0.1) !important;
    border: 1px solid rgba(192,193,255,0.22) !important;
    color: #c0c1ff !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    transition: all 0.2s !important;
    letter-spacing: 0.02em !important;
}
[data-testid="stSidebar"] .stButton button:hover {
    background: rgba(192,193,255,0.18) !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] label {
    color: rgba(199,196,215,0.55) !important;
    font-size: 0.62rem !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}
</style>
""", unsafe_allow_html=True)

# ── Timezone ──────────────────────────────────────────────────────────────────
_TZ_CH = ZoneInfo("Europe/Zurich")

# ── Palette ────────────────────────────────────────────────────────────────────
C_PRIMARY   = "#c0c1ff"
C_SECONDARY = "#ddb7ff"
C_TERTIARY  = "#3cddc7"
C_ERROR     = "#ffb4ab"
C_SURFACE   = "#c7c4d7"


# ── Domain helpers ─────────────────────────────────────────────────────────────
def _hum_color(v):
    if v is None: return C_SURFACE
    return C_ERROR if (v < 40 or v > 70) else C_TERTIARY

def _tvoc_color(v):
    if v is None: return C_SURFACE
    if v < 250:   return C_TERTIARY
    if v < 1000:  return "#f59e0b"
    return C_ERROR

def _eco2_color(v):
    if v is None: return C_SURFACE
    if v < 800:   return C_TERTIARY
    if v < 1200:  return "#f59e0b"
    return C_ERROR

def _status(dot_color):
    if dot_color == C_TERTIARY: return ("check_circle", "Optimal",  C_TERTIARY)
    if dot_color == C_ERROR:    return ("warning",      "Alert",    C_ERROR)
    return ("radio_button_unchecked", "Monitor", "#f59e0b")


def fmt(v, d=1, fb="--"):
    return fb if v is None else f"{v:.{d}f}"


def _weather_emoji(desc):
    d = (desc or "").lower()
    if "thunder" in d:             return "⛈️"
    if "drizzle" in d:             return "🌦️"
    if "rain" in d:                return "🌧️"
    if "snow" in d:                return "❄️"
    if "sleet" in d or "ice" in d: return "🌨️"
    if "fog" in d or "mist" in d:  return "🌫️"
    if "haze" in d or "smoke" in d: return "🌫️"
    if "clear" in d:               return "☀️"
    if "few cloud" in d:           return "🌤️"
    if "scattered" in d:           return "⛅"
    if "cloud" in d or "overcast" in d: return "☁️"
    return "🌡️"


def _weather_ms_icon(desc):
    d = (desc or "").lower()
    if "thunder" in d:              return "thunderstorm"
    if "drizzle" in d:              return "grain"
    if "rain" in d:                 return "rainy"
    if "snow" in d:                 return "cloudy_snowing"
    if "sleet" in d or "ice" in d:  return "weather_mix"
    if "fog" in d or "mist" in d:   return "foggy"
    if "haze" in d or "smoke" in d: return "foggy"
    if "clear" in d:                return "sunny"
    if "few cloud" in d:            return "partly_cloudy_day"
    if "scattered" in d:            return "partly_cloudy_day"
    if "cloud" in d or "overcast" in d: return "cloud"
    return "partly_cloudy_day"


# ── HTML helpers ───────────────────────────────────────────────────────────────
def metric_card(icon_label, icon_color, label, value, unit, dot_color):
    return f"""<div class="metric-card">
  <div class="metric-icon-row">
    <span style="font-size:0.68rem;font-weight:800;color:{icon_color};text-transform:uppercase;letter-spacing:0.13em;">{icon_label}</span>
    <span class="metric-dot" style="color:{dot_color};background:{dot_color};"></span>
  </div>
  <div class="metric-value">{value}<span class="metric-unit"> {unit}</span></div>
</div>"""


def stat_tile(ms_icon, icon_color, label, value, unit):
    return f"""<div class="stat-tile">
  <div class="stat-icon-row">
    <span style="font-size:0.68rem;font-weight:800;color:{icon_color};text-transform:uppercase;letter-spacing:0.13em;">{label}</span>
  </div>
  <div class="stat-value">{value}<span class="stat-unit"> {unit}</span></div>
</div>"""


def fc_card(day_label, emoji, temp_max, temp_min, pop, desc):
    pop_html = f'<div class="fc-pop">💧 {pop}%</div>' if pop > 5 else ""
    return f"""<div class="fc-card">
  <div class="fc-day">{day_label}</div>
  <div class="fc-icon-ring">
    <span style="font-size:1.9rem;line-height:1;">{emoji}</span>
  </div>
  <div class="fc-temp">↑{temp_max:.0f}℃ ↓{temp_min:.0f}℃</div>
  {pop_html}
  <div class="fc-desc">{desc[:24]}</div>
</div>"""


def outdoor_panel(temp, desc, city, humidity, wind_speed, feels_like, bg_url=""):
    if bg_url:
        photo_el = (
            f'<img src="{bg_url}" '
            f'style="position:absolute;inset:0;width:100%;height:100%;'
            f'object-fit:cover;object-position:center 60%;opacity:0.75;z-index:1;" />'
        )
    else:
        photo_el = '<div class="outdoor-panel-photo"></div>'
    emoji = _weather_emoji(desc)
    return f"""
<div class="outdoor-panel">
  <div class="outdoor-panel-bg"></div>
  {photo_el}
  <div class="outdoor-panel-overlay"></div>
  <div class="outdoor-panel-content">
    <div class="outdoor-layout">
      <div>
        <p class="outdoor-location" style="font-size:1rem;letter-spacing:0.18em;">
          {city.upper() if city else "OUTDOOR"}
        </p>
        <div class="outdoor-temp">{temp}°C</div>
        <div class="outdoor-condition">{desc.capitalize()}</div>
      </div>
      <div class="outdoor-chips">
        <div class="outdoor-chip">
          <div>
            <p style="font-size:0.68rem;font-weight:800;color:#c0c1ff;text-transform:uppercase;letter-spacing:0.13em;margin:0 0 4px 0;">Wind</p>
            <p class="chip-value">{wind_speed} m/s</p>
          </div>
        </div>
        <div class="outdoor-chip">
          <div>
            <p style="font-size:0.68rem;font-weight:800;color:#ddb7ff;text-transform:uppercase;letter-spacing:0.13em;margin:0 0 4px 0;">Feels Like</p>
            <p class="chip-value">{feels_like}°C</p>
          </div>
        </div>
        <div class="outdoor-chip">
          <div>
            <p style="font-size:0.68rem;font-weight:800;color:#3cddc7;text-transform:uppercase;letter-spacing:0.13em;margin:0 0 4px 0;">Humidity</p>
            <p class="chip-value">{humidity}%</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>"""


# ── Cached data loaders ────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_snapshot(city=None):    return api.get_snapshot(city=city)

@st.cache_data(ttl=120)
def load_history(hours, limit=800):
    return api.get_history(hours=hours, limit=limit)

@st.cache_data(ttl=120)
def load_stats(hours):
    return api.get_stats(hours=hours)

@st.cache_data(ttl=600)
def load_forecast(city=None):
    return api.get_forecast(days=5, city=city)


# ── Plotly dark glass theme ────────────────────────────────────────────────────
_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=8, r=8, t=10, b=4),
    xaxis=dict(
        showgrid=False,
        color="#c7c4d7",
        tickfont=dict(size=10, family="Space Grotesk"),
        linecolor="rgba(255,255,255,0.08)",
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="rgba(255,255,255,0.06)",
        color="#c7c4d7",
        tickfont=dict(size=10, family="Space Grotesk"),
    ),
    showlegend=False,
    hovermode="x unified",
    hoverlabel=dict(
        bgcolor="rgba(20,20,40,0.95)",
        bordercolor="rgba(255,255,255,0.2)",
        font=dict(size=12, color="#e0e3e5", family="Space Grotesk"),
    ),
    font=dict(family="Space Grotesk", color="#e0e3e5"),
)

_LAYOUT_DUAL = {
    **_LAYOUT,
    "yaxis2": dict(
        showgrid=False,
        color="#c7c4d7",
        tickfont=dict(size=10, family="Space Grotesk"),
        overlaying="y",
        side="right",
    ),
    "showlegend": True,
    "legend": dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(size=11, family="Space Grotesk", color="#c7c4d7"),
        bgcolor="rgba(0,0,0,0)",
        borderwidth=0,
    ),
}

_LAYOUT_AQ = {**_LAYOUT, "margin": dict(l=64, r=12, t=14, b=4)}


# ════════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div class="sb-brand">
        <p class="sb-brand-title">Weather Monitor</p>
        <p class="sb-brand-sub">V2.4.1 · Active</p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    page = st.radio(
        "Navigation",
        ["Live Dashboard", "History & Analytics"],
        label_visibility="collapsed",
    )

    st.divider()

    SWISS_CITIES = [
        "Lausanne", "Zürich", "Geneva", "Bern", "Basel",
        "Lucerne", "Lugano", "Zermatt", "Interlaken", "St. Gallen",
    ]
    selected_city = st.selectbox("OUTDOOR LOCATION", SWISS_CITIES, index=0)

    st.divider()

    HOURS_OPTS = {
        6: "Last 6 hours", 24: "Last 24 hours",
        48: "Last 48 hours", 168: "Last 7 days", 720: "Last 30 days",
    }
    hours_key = st.selectbox(
        "TIME WINDOW",
        list(HOURS_OPTS.keys()),
        index=1,
        format_func=lambda h: HOURS_OPTS[h],
    )

    st.divider()

    if st.button("↻  Refresh Sensors", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"Local  {datetime.now(_TZ_CH).strftime('%H:%M:%S')}")


# ════════════════════════════════════════════════════════════════════════════════
# PAGE 1 — LIVE DASHBOARD
# ════════════════════════════════════════════════════════════════════════════════
if "Dashboard" in page:
    with ThreadPoolExecutor(max_workers=2) as _pool:
        _snap_f = _pool.submit(load_snapshot, selected_city)
        _fore_f = _pool.submit(load_forecast, selected_city)
        snap, err = _snap_f.result()
        _forecast_prefetch = _fore_f.result()

    if err:
        st.error(f"🚨 Cannot reach the API: {err}")
        st.stop()

    indoor  = snap.get("indoor")  or {}
    alerts  = snap.get("alerts")  or []
    outdoor = snap.get("outdoor") or {}

    # ── Alerts ────────────────────────────────────────────────────────────────
    for alert in alerts:
        msg = alert.get("message", "")
        if alert.get("severity") == "danger":
            st.error(f"🚨 **{msg}**")
        else:
            st.warning(f"⚠️ {msg}")

    # ── Indoor metric cards ────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Indoor Conditions</div>', unsafe_allow_html=True)

    temp = indoor.get("indoor_temp")
    hum  = indoor.get("indoor_humidity")
    tvoc = indoor.get("indoor_tvoc_ppb")
    eco2 = indoor.get("indoor_eco2_ppm")
    pres = indoor.get("indoor_pressure")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(metric_card("Temperature",  C_PRIMARY,   "Temperature",     fmt(temp),    "°C",  C_PRIMARY),  unsafe_allow_html=True)
    with c2:
        hc = _hum_color(hum)
        st.markdown(metric_card("Humidity",     C_SECONDARY, "Humidity",        fmt(hum, 0),  "%",   hc),         unsafe_allow_html=True)
    with c3:
        tc = _tvoc_color(tvoc)
        st.markdown(metric_card("Air Quality-TVOC",  C_TERTIARY,  "Air Quality TVOC",fmt(tvoc, 0), "ppb", tc),     unsafe_allow_html=True)
    with c4:
        ec = _eco2_color(eco2)
        st.markdown(metric_card("Air Quality-CO₂",  C_PRIMARY,   "CO₂ Levels",      fmt(eco2, 0), "ppm", ec),     unsafe_allow_html=True)

    # Info caption (timestamp + pressure) — visible white text
    ts = indoor.get("timestamp", "")
    parts = []
    if ts:
        try:
            _ts_utc = datetime.fromisoformat(ts[:19]).replace(tzinfo=timezone.utc)
            _ts_local = _ts_utc.astimezone(_TZ_CH)
            parts.append(f"Last reading: {_ts_local.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            parts.append(f"Last reading: {ts[:19].replace('T',' ')} UTC")
    if pres:
        parts.append(f"Pressure: {pres:.1f} hPa")
    if parts:
        st.markdown(f'<div class="info-caption">🕐 {"&nbsp;&nbsp;·&nbsp;&nbsp;".join(parts)}</div>', unsafe_allow_html=True)
        st.caption("Times shown in Europe/Zurich local time (CEST UTC+2 in summer, CET UTC+1 in winter)")

    st.divider()

    # ── Outdoor atmospheric panel (full width) ─────────────────────────────────
    st.markdown('<div class="section-title">Outdoor Now</div>', unsafe_allow_html=True)
    _bg = _lausanne_bg()
    if outdoor:
        st.markdown(outdoor_panel(
            temp       = outdoor.get("temp", "--"),
            desc       = outdoor.get("description", ""),
            city       = outdoor.get("city", ""),
            humidity   = outdoor.get("humidity", "--"),
            wind_speed = outdoor.get("wind_speed", "--"),
            feels_like = outdoor.get("feels_like", "--"),
            bg_url     = _bg,
        ), unsafe_allow_html=True)
    else:
        st.info("Outdoor data unavailable.")

    st.divider()

    # ── 5-Day Forecast — each card in its own column ───────────────────────────
    st.markdown('<div class="section-title">5-Day Forecast</div>', unsafe_allow_html=True)
    forecast, ferr = _forecast_prefetch

    if ferr or not forecast:
        st.info("Forecast unavailable.")
    else:
        cols = st.columns(len(forecast))
        for col, day in zip(cols, forecast):
            try:
                label = datetime.strptime(day["date"], "%Y-%m-%d").strftime("%a").upper()
            except Exception:
                label = day["date"][-5:]

            with col:
                st.markdown(fc_card(
                    day_label = label,
                    emoji     = _weather_emoji(day.get("description", "")),
                    temp_max  = day.get("temp_max", 0),
                    temp_min  = day.get("temp_min", 0),
                    pop       = day.get("pop", 0),
                    desc      = day.get("description", ""),
                ), unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════════
# PAGE 2 — HISTORY & ANALYTICS
# ════════════════════════════════════════════════════════════════════════════════
else:
    with ThreadPoolExecutor(max_workers=2) as _pool:
        _hist_f  = _pool.submit(load_history, hours_key)
        _stats_f = _pool.submit(load_stats, hours_key)
        history, herr = _hist_f.result()
        stats,   serr = _stats_f.result()

    if herr:
        st.error(f"🚨 Could not load history: {herr}")
        st.stop()

    rows = (history or {}).get("data", [])
    if not rows:
        st.info("No data in this time window. Try expanding the range.")
        st.stop()

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_convert(_TZ_CH).dt.tz_localize(None)
    df = df.sort_values("timestamp")

    chart_config = dict(displayModeBar=False)

    # ── Summary stat tiles ─────────────────────────────────────────────────────
    st.markdown(
        f'<div class="section-title">Summary — {HOURS_OPTS[hours_key]}</div>',
        unsafe_allow_html=True,
    )
    s = (stats or {}).get("stats", {}) if not serr else {}
    t1, t2, t3, t4 = st.columns(4)
    with t1: st.markdown(stat_tile("device_thermostat", C_PRIMARY,   "Avg Temp",    fmt(s.get("avg_temp")),     "°C"),  unsafe_allow_html=True)
    with t2: st.markdown(stat_tile("trending_up",       C_ERROR,     "Max Temp",    fmt(s.get("max_temp")),     "°C"),  unsafe_allow_html=True)
    with t3: st.markdown(stat_tile("trending_down",     C_TERTIARY,  "Min Temp",    fmt(s.get("min_temp")),     "°C"),  unsafe_allow_html=True)
    with t4: st.markdown(stat_tile("humidity_mid",      C_SECONDARY, "Avg Humidity",fmt(s.get("avg_humidity")), "%"),   unsafe_allow_html=True)

    u1, u2, u3 = st.columns(3)
    with u1: st.markdown(stat_tile("trending_down",     C_TERTIARY,  "Min Humidity",fmt(s.get("min_humidity")), "%"),   unsafe_allow_html=True)
    with u2: st.markdown(stat_tile("air",               C_TERTIARY,  "Max TVOC",    fmt(s.get("max_tvoc"), 0),  "ppb"), unsafe_allow_html=True)
    with u3: st.markdown(stat_tile("co2",               C_PRIMARY,   "Max eCO₂",    fmt(s.get("max_eco2"), 0),  "ppm"), unsafe_allow_html=True)

    st.divider()

    # ── Atmospheric Trends — combined Temp + Humidity ──────────────────────────
    has_temp = "indoor_temp" in df and df["indoor_temp"].notna().any()
    has_hum  = "indoor_humidity" in df and df["indoor_humidity"].notna().any()

    if has_temp or has_hum:
        st.markdown("""
        <div class="chart-glass">
          <div class="chart-title">Atmospheric Trends</div>
          <div class="chart-sub">Sensor telemetry over selected period</div>
          <div class="chart-legend">
            <span class="legend-item">
              <span class="legend-bar" style="background:#c0c1ff;box-shadow:0 0 6px rgba(192,193,255,0.7);"></span>Temperature (°C)
            </span>
            <span class="legend-item">
              <span class="legend-bar" style="background:#4ade80;box-shadow:0 0 6px rgba(74,222,128,0.7);"></span>Humidity (%)
            </span>
          </div>
        </div>""", unsafe_allow_html=True)

        fig = go.Figure()
        if has_temp:
            fig.add_trace(go.Scatter(
                x=df["timestamp"], y=df["indoor_temp"],
                mode="lines", name="Temp (°C)", yaxis="y",
                line=dict(color=C_PRIMARY, width=2.5),
                fill="tozeroy", fillcolor="rgba(192,193,255,0.06)",
            ))
        if has_hum:
            fig.add_trace(go.Scatter(
                x=df["timestamp"], y=df["indoor_humidity"],
                mode="lines", name="Humidity (%)", yaxis="y2",
                line=dict(color="#4ade80", width=2.5),
                fill="tozeroy", fillcolor="rgba(74,222,128,0.04)",
            ))
        fig.update_layout(height=300, **{**_LAYOUT_DUAL, "showlegend": False})
        st.plotly_chart(fig, use_container_width=True, config=chart_config)

    st.divider()

    # ── Air Quality ────────────────────────────────────────────────────────────
    has_tvoc = "indoor_tvoc_ppb" in df and df["indoor_tvoc_ppb"].notna().any()
    has_eco2 = "indoor_eco2_ppm" in df and df["indoor_eco2_ppm"].notna().any()

    if has_tvoc or has_eco2:
        st.markdown('<div class="section-title">Air Quality</div>', unsafe_allow_html=True)
        ac1, ac2 = st.columns(2, gap="medium")

        if has_tvoc:
            with ac1:
                st.markdown("""<div class="chart-glass">
                  <div class="chart-title">TVOC</div>
                  <div class="chart-sub">Total volatile organic compounds (ppb)</div>
                </div>""", unsafe_allow_html=True)
                fig = go.Figure()
                fig.add_hrect(y0=0,    y1=250,  fillcolor="rgba(60,221,199,0.05)",  line_width=0)
                fig.add_hrect(y0=250,  y1=1000, fillcolor="rgba(245,158,11,0.05)",  line_width=0)
                fig.add_hrect(y0=1000, y1=5000, fillcolor="rgba(255,180,171,0.05)", line_width=0)
                fig.add_hline(
                    y=1000, line_dash="dot", line_color=C_ERROR,
                    annotation_text="Alert 1000 ppb",
                    annotation_font_size=10,
                    annotation_font_color=C_ERROR,
                )
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["indoor_tvoc_ppb"],
                    mode="lines", name="TVOC",
                    line=dict(color=C_TERTIARY, width=2.5),
                    fill="tozeroy", fillcolor="rgba(60,221,199,0.07)",
                ))
                fig.update_layout(height=260, **_LAYOUT_AQ)
                fig.update_yaxes(title_text="TVOC (ppb)", title_font=dict(size=11, color="#c7c4d7"), title_standoff=8)
                st.plotly_chart(fig, use_container_width=True, config=chart_config)

        if has_eco2:
            with ac2:
                st.markdown("""<div class="chart-glass">
                  <div class="chart-title">eCO₂</div>
                  <div class="chart-sub">Equivalent CO₂ concentration (ppm)</div>
                </div>""", unsafe_allow_html=True)
                fig = go.Figure()
                fig.add_hline(
                    y=1200, line_dash="dot", line_color=C_ERROR,
                    annotation_text="Alert 1200 ppm",
                    annotation_font_size=10,
                    annotation_font_color=C_ERROR,
                )
                fig.add_trace(go.Scatter(
                    x=df["timestamp"], y=df["indoor_eco2_ppm"],
                    mode="lines", name="eCO₂",
                    line=dict(color=C_SECONDARY, width=2.5),
                    fill="tozeroy", fillcolor="rgba(221,183,255,0.07)",
                ))
                fig.update_layout(height=260, **_LAYOUT_AQ)
                fig.update_yaxes(title_text="CO₂ (ppm)", title_font=dict(size=11, color="#c7c4d7"), title_standoff=8)
                st.plotly_chart(fig, use_container_width=True, config=chart_config)

    st.divider()

    # ── Atmospheric Pressure ───────────────────────────────────────────────────
    has_pres = "indoor_pressure" in df and df["indoor_pressure"].notna().any()
    if has_pres:
        st.markdown('<div class="section-title">Atmospheric Pressure</div>', unsafe_allow_html=True)
        st.markdown("""<div class="chart-glass">
          <div class="chart-title">Indoor Pressure</div>
          <div class="chart-sub">Barometric pressure over selected period (hPa)</div>
        </div>""", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["timestamp"], y=df["indoor_pressure"],
            mode="lines", name="Pressure (hPa)",
            line=dict(color=C_SECONDARY, width=2.5),
            fill="tozeroy", fillcolor="rgba(221,183,255,0.06)",
        ))
        fig.update_layout(height=240, **_LAYOUT)
        fig.update_yaxes(title_text="hPa", title_font=dict(size=11, color="#c7c4d7"), title_standoff=8)
        st.plotly_chart(fig, use_container_width=True, config=chart_config)
        st.divider()

    # ── Sensor Event Logs ──────────────────────────────────────────────────────
    with st.expander("📋  Sensor Event Logs"):
        show_cols = [c for c in [
            "timestamp", "indoor_temp", "indoor_humidity",
            "indoor_pressure", "indoor_tvoc_ppb", "indoor_eco2_ppm",
            "motion_detected", "source",
        ] if c in df.columns]
        st.dataframe(
            df[show_cols].sort_values("timestamp", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("All times shown in Europe/Zurich local time (CEST UTC+2 in summer, CET UTC+1 in winter)")
