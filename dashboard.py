import os
import json
import subprocess
import sys
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime
import config

st.set_page_config(
    page_title="Market Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject Google credentials from Streamlit Secrets when running on the cloud
try:
    _token = st.secrets.get("GOOGLE_TOKEN_JSON")
    if _token and not os.environ.get("GOOGLE_TOKEN_JSON"):
        os.environ["GOOGLE_TOKEN_JSON"] = _token
except Exception:
    pass

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
* { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }

[data-testid="stAppViewContainer"] { background: #f5f5f7; }
[data-testid="stHeader"] { background: transparent; border-bottom: 1px solid rgba(0,0,0,0.08); }
[data-testid="stMainBlockContainer"] { padding-top: 1.5rem; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid rgba(0,0,0,0.08);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.06em;
    text-transform: uppercase; color: rgba(0,0,0,0.48);
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.9rem !important; font-weight: 500 !important;
    color: #1d1d1f !important; padding: 6px 0 !important;
}
[data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p {
    font-size: 0.9rem; font-weight: 500; color: #1d1d1f; letter-spacing: 0;
    text-transform: none;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 18px;
    padding: 18px 22px !important;
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.72rem !important; font-weight: 600 !important;
    letter-spacing: 0.04em; text-transform: uppercase; color: rgba(0,0,0,0.48) !important;
}
[data-testid="stMetricValue"] > div {
    font-size: 1.75rem !important; font-weight: 700 !important; color: #1d1d1f !important;
}

/* Section headings (#### in markdown) */
h4 {
    font-size: 1.05rem !important; font-weight: 600 !important;
    letter-spacing: -0.374px; color: #1d1d1f !important;
    margin-top: 1.6rem !important; margin-bottom: 0.5rem !important;
}

/* Divider */
hr { border-color: rgba(0,0,0,0.08) !important; margin: 0.5rem 0 !important; }

/* Buttons */
.stButton > button {
    border: none !important; color: #ffffff !important;
    background: #0066cc !important; border-radius: 980px !important;
    font-weight: 600 !important; font-size: 0.85rem !important;
    transition: opacity 0.15s ease !important;
}
.stButton > button:hover { opacity: 0.85 !important; }
.stButton > button:active { transform: scale(0.95) !important; }

/* Search input */
[data-testid="stTextInput"] input {
    background: #ffffff !important; border-color: rgba(0,0,0,0.08) !important;
    border-radius: 10px; color: #1d1d1f !important;
}

/* Dataframe container */
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }

/* Caption text */
[data-testid="stCaptionContainer"] p { color: rgba(0,0,0,0.48) !important; font-size: 0.78rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Column display names for Stockbee table ──────────────────────────────────
STOCKBEE_RENAME = {
    "Number of stocks up 4% plus today":           "Up 4%+",
    "Number of stocks down 4% plus today":         "Down 4%+",
    "5 day ratio":                                 "5D Ratio",
    "10 day ratio":                                "10D Ratio",
    "Number of stocks up 25% plus in a quarter":   "Up 25%+ Qtr",
    "Number of stocks down 25% + in a quarter":    "Dn 25%+ Qtr",
    "Number of stocks up 25% + in a month":        "Up 25%+ Mo",
    "Number of stocks down 25% + in a month":      "Dn 25%+ Mo",
    "Number of stocks up 50% + in a month":        "Up 50%+ Mo",
    "Number of stocks down 50% + in a month":      "Dn 50%+ Mo",
    "Number of stocks up 13% + in 34 days":        "Up 13%+ 34D",
    "Number of stocks down 13% + in 34 days":      "Dn 13%+ 34D",
    "Worden Common stock universe":                "Universe",
}

# Column definitions shown as "?" tooltips in the breadth table
COLUMN_HELP = {
    "Up 4%+":      "Stocks that rose ≥4% today. High values = broad buying pressure.",
    "Down 4%+":    "Stocks that fell ≥4% today. High values = broad selling pressure.",
    "5D Ratio":    "5-day cumulative (Up 4%+) ÷ (Down 4%+). Above 2 = bullish, below 0.5 = bearish.",
    "10D Ratio":   "10-day cumulative (Up 4%+) ÷ (Down 4%+). Longer-term breadth trend.",
    "Up 25%+ Qtr": "Stocks up ≥25% over the past quarter. Measures intermediate-term momentum.",
    "Dn 25%+ Qtr": "Stocks down ≥25% over the past quarter.",
    "Up 25%+ Mo":  "Stocks up ≥25% in the past month. Short-term momentum leaders.",
    "Dn 25%+ Mo":  "Stocks down ≥25% in the past month.",
    "Up 50%+ Mo":  "Stocks up ≥50% in the past month. Extreme momentum — can signal excess.",
    "Dn 50%+ Mo":  "Stocks down ≥50% in the past month. Extreme washout — can signal a bottom.",
    "Up 13%+ 34D": "Stocks up ≥13% in 34 days. Worden intermediate-term breadth indicator.",
    "Dn 13%+ 34D": "Stocks down ≥13% in 34 days.",
    "Universe":    "Total stocks in the Worden Common Stock Universe.",
    "T2108":       "% of stocks above their 40-day MA. ≤20% = oversold (historically a bullish setup).",
    "S&P":         "S&P 500 closing price.",
    "10D Score":   "Rolling 10-day breadth score: +2 extreme up day, +1 up day, −1 down day, −2 extreme down day.",
}

# Shared rangeselector buttons for all time-series charts
def _rangeselector(active="1Y"):
    labels = ["1M", "3M", "6M", "1Y", "3Y", "All"]
    buttons = [
        dict(count=1,  label="1M",  step="month", stepmode="backward"),
        dict(count=3,  label="3M",  step="month", stepmode="backward"),
        dict(count=6,  label="6M",  step="month", stepmode="backward"),
        dict(count=1,  label="1Y",  step="year",  stepmode="backward"),
        dict(count=3,  label="3Y",  step="year",  stepmode="backward"),
        dict(step="all", label="All"),
    ]
    return dict(
        buttons=buttons,
        activecolor="#0066cc",
        bgcolor="rgba(0,0,0,0.04)",
        bordercolor="rgba(0,0,0,0.08)",
        borderwidth=1,
        font=dict(size=11),
        x=1, xanchor="right", y=1.04, yanchor="bottom",
    )


# Shared Plotly layout base
_PLOT_BASE = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#1d1d1f", size=12,
              family="system-ui, -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif"),
    xaxis=dict(gridcolor="rgba(0,0,0,0.06)", showline=False, zeroline=False),
    yaxis=dict(gridcolor="rgba(0,0,0,0.06)", showline=False, zeroline=False),
    legend=dict(orientation="h", y=1.1, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    margin=dict(l=10, r=10, t=48, b=10),
    hoverlabel=dict(bgcolor="#ffffff", bordercolor="rgba(0,0,0,0.08)", font_color="#1d1d1f"),
)


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_data():
    stockbee_df = pd.DataFrame()
    rs_df = pd.DataFrame()
    last_updated = "Never"
    fetch_errors = []

    sb_path   = f"{config.DATA_DIR}/stockbee.json"
    rs_path   = f"{config.DATA_DIR}/relative_strength.json"
    meta_path = f"{config.DATA_DIR}/last_updated.json"

    if os.path.exists(sb_path):
        stockbee_df = pd.read_json(sb_path)
        stockbee_df["Date"] = pd.to_datetime(stockbee_df["Date"], unit="ms", errors="coerce")
        stockbee_df = stockbee_df.sort_values("Date", ascending=False).reset_index(drop=True)

    if os.path.exists(rs_path):
        rs_df = pd.read_json(rs_path, dtype=False)

    aaii_df = pd.DataFrame()
    aaii_path = f"{config.DATA_DIR}/aaii.json"
    if os.path.exists(aaii_path):
        aaii_df = pd.read_json(aaii_path, dtype=False)
        if "Date" in aaii_df.columns:
            aaii_df["Date"] = pd.to_datetime(aaii_df["Date"], unit="ms", errors="coerce")
            aaii_df = aaii_df.sort_values("Date", ascending=False).reset_index(drop=True)

    naaim_df = pd.DataFrame()
    naaim_path = f"{config.DATA_DIR}/naaim.json"
    if os.path.exists(naaim_path):
        naaim_df = pd.read_json(naaim_path, dtype=False)
        if "Date" in naaim_df.columns:
            naaim_df["Date"] = pd.to_datetime(naaim_df["Date"], unit="ms", errors="coerce")
            naaim_df = naaim_df.sort_values("Date", ascending=False).reset_index(drop=True)

    snap_list = []
    snap_path = f"{config.DATA_DIR}/watchlist_snapshot.json"
    if os.path.exists(snap_path):
        with open(snap_path) as f:
            snap_list = json.load(f)

    rsi_history = []
    rsi_hist_path = f"{config.DATA_DIR}/rsi_history.json"
    if os.path.exists(rsi_hist_path):
        with open(rsi_hist_path) as f:
            rsi_history = json.load(f)

    rrg_data = []
    rrg_path = f"{config.DATA_DIR}/rrg.json"
    if os.path.exists(rrg_path):
        with open(rrg_path) as f:
            rrg_data = json.load(f)

    def _load_tracker(key):
        d = config.DATA_DIR
        if key == "market":
            sp, hp, rp = f"{d}/watchlist_snapshot.json", f"{d}/rsi_history.json", f"{d}/rrg.json"
        else:
            sp, hp, rp = (f"{d}/watchlist_{key}_snapshot.json",
                          f"{d}/rsi_history_{key}.json",
                          f"{d}/rrg_{key}.json")
        snap = json.load(open(sp)) if os.path.exists(sp) else []
        hist = json.load(open(hp)) if os.path.exists(hp) else []
        rrg  = json.load(open(rp)) if os.path.exists(rp) else []
        return snap, hist, rrg

    snap_elite8, hist_elite8, rrg_elite8 = _load_tracker("elite8")
    snap_theme,  hist_theme,  rrg_theme  = _load_tracker("theme")

    vix_df = pd.DataFrame()
    vix_path = f"{config.DATA_DIR}/vix.json"
    if os.path.exists(vix_path):
        vix_df = pd.read_json(vix_path, dtype=False)
        if "Date" in vix_df.columns:
            vix_df["Date"] = pd.to_datetime(vix_df["Date"], unit="ms", errors="coerce")
            vix_df = vix_df.sort_values("Date", ascending=False).reset_index(drop=True)

    breadth_df = pd.DataFrame()
    breadth_path = f"{config.DATA_DIR}/breadth.json"
    if os.path.exists(breadth_path):
        breadth_df = pd.read_json(breadth_path, dtype=False)
        if "Date" in breadth_df.columns:
            breadth_df["Date"] = pd.to_datetime(breadth_df["Date"], unit="ms", errors="coerce")
            breadth_df = breadth_df.sort_values("Date", ascending=False).reset_index(drop=True)

    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        ts = datetime.fromisoformat(meta["timestamp"])
        last_updated = ts.strftime("%b %d, %Y  %H:%M")
        fetch_errors = meta.get("errors", [])

    return (stockbee_df, rs_df, aaii_df, naaim_df, vix_df, breadth_df,
            snap_list, rsi_history, rrg_data,
            snap_elite8, hist_elite8, rrg_elite8,
            snap_theme,  hist_theme,  rrg_theme,
            last_updated, fetch_errors)


def add_rolling_score(df: pd.DataFrame) -> pd.DataFrame:
    """Compute a 10-day rolling score from Up/Down 4%+ breadth readings."""
    up_col = "Number of stocks up 4% plus today"
    dn_col = "Number of stocks down 4% plus today"
    if up_col not in df.columns or dn_col not in df.columns:
        return df

    temp = df.sort_values("Date").copy()

    def daily_score(row):
        up = _to_num(row.get(up_col))
        dn = _to_num(row.get(dn_col))
        if up is None or dn is None:
            return 0
        if up >= config.UP4_EXTREME:    return 2
        if up > dn:                     return 1
        if dn >= config.DOWN4_EXTREME:  return -2
        if dn > up:                     return -1
        return 0

    temp["10D Score"] = (
        temp.apply(daily_score, axis=1)
            .rolling(10, min_periods=1)
            .sum()
            .astype(int)
    )
    return temp.sort_values("Date", ascending=False).reset_index(drop=True)


def trigger_fetch():
    subprocess.run(
        [sys.executable, "fetch_data.py"],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    st.cache_data.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _to_num(val):
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _series(df, col):
    raw = df.get(col)
    if raw is None:
        return [None] * len(df)
    s = pd.to_numeric(raw, errors="coerce")
    return [None if pd.isna(v) else float(v) for v in s]


def _fmt(val, fmt, fallback="—"):
    v = _to_num(val)
    return fallback if v is None else fmt.format(v)


def metric_card(label, value, color="neutral"):
    palettes = {
        "dark_green": ("#c8e6c9", "#1b5e20"),
        "green":      ("#e8f5e9", "#2e7d32"),
        "neutral":    ("#ffffff", "#1d1d1f"),
        "red":        ("#ffebee", "#c62828"),
        "dark_red":   ("#ffcdd2", "#b71c1c"),
    }
    bg, txt = palettes.get(color, palettes["neutral"])
    border = "rgba(0,0,0,0.08)" if color == "neutral" else f"{palettes.get(color, palettes['neutral'])[1]}33"
    return (
        f'<div style="background:{bg}; border:1px solid {border}; border-radius:18px; '
        f'padding:18px 22px;">'
        f'<p style="font-size:0.72rem; font-weight:600; letter-spacing:0.04em; '
        f'text-transform:uppercase; color:{txt}; opacity:0.6; margin:0 0 6px 0;">{label}</p>'
        f'<p style="font-size:1.75rem; font-weight:700; color:{txt}; margin:0;">{value}</p>'
        f'</div>'
    )


# ── Signal banner ─────────────────────────────────────────────────────────────
def render_signal_banner(today_row):
    r5   = _to_num(today_row.get("5 day ratio"))
    r10  = _to_num(today_row.get("10 day ratio"))
    t208 = _to_num(today_row.get("T2108"))

    ratios = [v for v in [r5, r10] if v is not None]
    avg    = sum(ratios) / len(ratios) if ratios else None

    if avg is None:
        return

    if avg >= 4:
        label, color, icon = "STRONG BULLISH", "#1b5e20", "🟢"
        desc = "Broad participation — majority of signals strongly favour buyers."
    elif avg >= 2:
        label, color, icon = "BULLISH", "#2e7d32", "🟢"
        desc = "Breadth is constructive — market internals favour the upside."
    elif avg <= 0.5:
        label, color, icon = "STRONG BEARISH", "#b71c1c", "🔴"
        desc = "Sellers in control — breadth readings at extreme lows."
    elif avg <= 1:
        label, color, icon = "BEARISH", "#c62828", "🔴"
        desc = "Breadth is deteriorating — caution advised."
    else:
        label, color, icon = "NEUTRAL / MIXED", "#b8860b", "🟡"
        desc = "No clear directional edge — watch for a breakout in breadth."

    r5_str   = _fmt(r5,   "{:.2f}")
    r10_str  = _fmt(r10,  "{:.2f}")
    t208_str = _fmt(t208, "{:.1f}%")

    st.markdown(f"""
<div style="background:{color}12; border-left:4px solid {color}; border-radius:8px;
     padding:14px 22px; margin:4px 0 16px; display:flex; align-items:center; gap:18px;">
  <div style="font-size:1.6rem; line-height:1">{icon}</div>
  <div>
    <div style="font-size:0.68rem; font-weight:800; letter-spacing:0.1em;
         color:{color}; text-transform:uppercase; margin-bottom:2px;">Market Regime</div>
    <div style="font-size:1.1rem; font-weight:700; color:#1d1d1f; margin-bottom:2px;">{label}</div>
    <div style="font-size:0.78rem; color:rgba(0,0,0,0.48);">{desc}</div>
  </div>
  <div style="margin-left:auto; text-align:right; font-size:0.8rem; color:rgba(0,0,0,0.48); line-height:2;">
    5D Ratio &nbsp;<b style="color:#1d1d1f">{r5_str}</b><br>
    10D Ratio &nbsp;<b style="color:#1d1d1f">{r10_str}</b><br>
    T2108 &nbsp;<b style="color:#1d1d1f">{t208_str}</b>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Styling helpers ───────────────────────────────────────────────────────────
def style_stockbee(df: pd.DataFrame):
    display = df.rename(columns=STOCKBEE_RENAME).copy()
    if "Date" in display.columns:
        display["Date"] = display["Date"].dt.strftime("%Y-%m-%d")

    ratio_cols = [c for c in ["5D Ratio", "10D Ratio"] if c in display.columns]
    t2108_cols = [c for c in ["T2108"] if c in display.columns]
    sp_cols    = [c for c in ["S&P"] if c in display.columns]
    score_cols = [c for c in ["10D Score"] if c in display.columns]
    int_cols   = [c for c in display.columns
                  if c not in ("Date", "10D Score") + tuple(ratio_cols + t2108_cols + sp_cols)]

    # Convert to numeric
    for col in int_cols + ratio_cols + t2108_cols + sp_cols:
        display[col] = pd.to_numeric(
            display[col].astype(str).str.replace(",", ""), errors="coerce"
        )

    # Rule 1: Up vs Down comparison for each breadth pair
    # (up_col, dn_col, extreme_up, extreme_dn)
    PAIRS = [
        ("Up 4%+",      "Down 4%+",    config.UP4_EXTREME,  config.DOWN4_EXTREME),
        ("Up 25%+ Qtr", "Dn 25%+ Qtr", None, None),
        ("Up 25%+ Mo",  "Dn 25%+ Mo",  None, None),
        ("Up 13%+ 34D", "Dn 13%+ 34D", None, None),
    ]

    def color_breadth(row):
        styles = pd.Series("", index=row.index)
        for up_col, dn_col, up_ext, dn_ext in PAIRS:
            if up_col not in row.index or dn_col not in row.index:
                continue
            up, dn = row[up_col], row[dn_col]
            if pd.isna(up) or pd.isna(dn):
                continue
            if up_ext is not None and up >= up_ext:
                styles[up_col] = "background-color: #c8e6c9; color: #1b5e20; font-weight: 700"
            elif up > dn:
                styles[up_col] = "background-color: #e8f5e9; color: #2e7d32"
            if dn_ext is not None and dn >= dn_ext:
                styles[dn_col] = "background-color: #ffcdd2; color: #b71c1c; font-weight: 700"
            elif dn > up:
                styles[dn_col] = "background-color: #ffebee; color: #c62828"
        return styles

    # Rule 2: 5D and 10D Ratio — green if > 2, red if < 0.5
    def color_ratio(val):
        if pd.isna(val): return ""
        if val > 2:   return "background-color: #e8f5e9; color: #2e7d32; font-weight: 600"
        if val < 0.5: return "background-color: #ffebee; color: #c62828; font-weight: 600"
        return ""

    # Rule 3: Up 50%+ Mo — red if >= 20 (extreme momentum, caution signal)
    def color_up50(val):
        if pd.isna(val): return ""
        if val >= 20: return "background-color: #ffebee; color: #c62828; font-weight: 600"
        return ""

    # Rule 4: Dn 50%+ Mo — green if >= 20 (extreme washout, contrarian buy signal)
    def color_dn50(val):
        if pd.isna(val): return ""
        if val >= 20: return "background-color: #e8f5e9; color: #2e7d32; font-weight: 600"
        return ""

    # Rule 5: T2108 — dark green if <= 10, green if <= 20 (oversold = contrarian bullish)
    def color_t2108(val):
        if pd.isna(val): return ""
        if val <= 10: return "background-color: #c8e6c9; color: #1b5e20; font-weight: 700"
        if val <= 20: return "background-color: #e8f5e9; color: #2e7d32"
        return ""

    # White base for all cells
    styled = display.style.set_properties(**{
        "background-color": "#ffffff",
        "color": "#1d1d1f",
    })

    styled = styled.apply(color_breadth, axis=1)

    for col in ratio_cols:
        styled = styled.map(color_ratio, subset=[col])

    for col in [c for c in ["Up 50%+ Mo"] if c in display.columns]:
        styled = styled.map(color_up50, subset=[col])

    for col in [c for c in ["Dn 50%+ Mo"] if c in display.columns]:
        styled = styled.map(color_dn50, subset=[col])

    for col in t2108_cols:
        styled = styled.map(color_t2108, subset=[col])

    # Rule 6: 10D Score
    def color_score(val):
        if pd.isna(val): return ""
        if val > 10:  return "background-color: #c8e6c9; color: #1b5e20; font-weight: 700"
        if val > 0:   return "background-color: #e8f5e9; color: #2e7d32"
        if val < -10: return "background-color: #ffcdd2; color: #b71c1c; font-weight: 700"
        if val < 0:   return "background-color: #ffebee; color: #c62828"
        return ""

    for col in score_cols:
        styled = styled.map(color_score, subset=[col])

    # Number formatting
    fmt_dict = {col: "{:,.0f}" for col in int_cols if col != "Date"}
    fmt_dict.update({col: "{:.2f}" for col in ratio_cols})
    fmt_dict.update({col: "{:.1f}%" for col in t2108_cols})
    fmt_dict.update({col: "{:,.2f}" for col in sp_cols})
    fmt_dict.update({col: "{:+.0f}" for col in score_cols})
    if fmt_dict:
        styled = styled.format(fmt_dict, na_rep="—")

    return styled




# ── Chart builders ────────────────────────────────────────────────────────────
def chart_ratios(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Date"], y=_series(df_plot, "5 day ratio"),
        name="5-Day Ratio", line=dict(color="#2196F3", width=2.5),
    ))
    fig.add_trace(go.Scatter(
        x=df_plot["Date"], y=_series(df_plot, "10 day ratio"),
        name="10-Day Ratio", line=dict(color="#FF9800", width=2.5),
    ))
    for y, color, label in [
        (4,   "#1b5e20", "4 — Extreme Bullish"),
        (2,   "#2e7d32", "2 — Bullish"),
        (1,   "#c62828", "1 — Bearish"),
        (0.5, "#b71c1c", "0.5 — Extreme Bearish"),
    ]:
        fig.add_hline(y=y, line_dash="dot", line_color=color,
                      annotation_text=label, annotation_position="left",
                      annotation_font=dict(size=10, color=color))
    fig.update_layout(
        title=dict(text="5-Day & 10-Day Breadth Ratio", font=dict(size=13)),
        height=360,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k != "xaxis"},
    )
    return fig


def chart_breadth_bars(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_plot["Date"], y=_series(df_plot, "Number of stocks up 4% plus today"),
        name="Up 4%+", marker_color="#388e3c", marker_line_width=0,
    ))
    fig.add_trace(go.Bar(
        x=df_plot["Date"], y=_series(df_plot, "Number of stocks down 4% plus today"),
        name="Down 4%+", marker_color="#c62828", marker_line_width=0,
    ))
    fig.add_hline(y=400, line_dash="dot", line_color="rgba(0,0,0,0.3)",
                  annotation_text="400 Extreme", annotation_font=dict(size=10))
    fig.update_layout(
        title=dict(text="Stocks Up / Down 4%+", font=dict(size=13)),
        barmode="group", height=320,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k != "xaxis"},
    )
    return fig


def chart_t2108(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Date"], y=_series(df_plot, "T2108"),
        fill="tozeroy", name="T2108",
        line=dict(color="#AB47BC", width=2),
        fillcolor="rgba(171,71,188,0.15)",
    ))
    fig.add_hline(y=config.T2108_OVERBOUGHT, line_dash="dot", line_color="#1b5e20",
                  annotation_text=f"{config.T2108_OVERBOUGHT} Overbought",
                  annotation_font=dict(size=10, color="#1b5e20"))
    fig.add_hline(y=config.T2108_OVERSOLD, line_dash="dot", line_color="#b71c1c",
                  annotation_text=f"{config.T2108_OVERSOLD} Oversold",
                  annotation_font=dict(size=10, color="#b71c1c"))
    fig.update_layout(
        title=dict(text="T2108 — % Stocks Above 40-Day MA", font=dict(size=13)),
        height=300,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)", range=[0, 100], showline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis")},
    )
    return fig


def chart_10d_score(df: pd.DataFrame):
    if "10D Score" not in df.columns:
        return None
    df_plot = df.sort_values("Date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Date"], y=_series(df_plot, "10D Score"),
        fill="tozeroy", name="10D Score",
        line=dict(color="#0066cc", width=2),
        fillcolor="rgba(0,102,204,0.12)",
    ))
    fig.add_hline(y=0,   line_color="rgba(0,0,0,0.25)", line_width=1)
    fig.add_hline(y=10,  line_dash="dot", line_color="rgba(0,100,0,0.4)",
                  annotation_text="+10", annotation_font=dict(size=10))
    fig.add_hline(y=-10, line_dash="dot", line_color="rgba(180,0,0,0.4)",
                  annotation_text="−10", annotation_font=dict(size=10))
    fig.update_layout(
        title=dict(text="10-Day Rolling Breadth Score", font=dict(size=13)),
        height=320,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k != "xaxis"},
    )
    return fig


def chart_aaii_sentiment(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    fig = go.Figure()
    for col, color, name in [
        ("Bullish", "#2e7d32", "Bullish %"),
        ("Neutral", "#f59e0b", "Neutral %"),
        ("Bearish", "#c62828", "Bearish %"),
    ]:
        if col in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot["Date"], y=_series(df_plot, col),
                name=name, line=dict(color=color, width=2),
            ))
    fig.add_hline(y=50, line_dash="dot", line_color="rgba(0,0,0,0.2)",
                  annotation_text="50%", annotation_font=dict(size=10))
    fig.update_layout(
        title=dict(text="AAII Sentiment — Bullish / Neutral / Bearish", font=dict(size=13)),
        height=340,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        yaxis=dict(ticksuffix="%", range=[0, 80], gridcolor="rgba(0,0,0,0.06)", showline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis")},
    )
    return fig


def chart_aaii_spread(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    if "Spread" not in df_plot.columns:
        return None
    scores = _series(df_plot, "Spread")
    colors = [
        "#1b5e20" if (v is not None and v < -20) else
        "#81c784" if (v is not None and v < 0)   else
        "#e57373" if (v is not None and v > 20)  else
        "#ef9a9a" if (v is not None and v > 0)   else
        "#cccccc"
        for v in scores
    ]
    fig = go.Figure(go.Bar(
        x=df_plot["Date"].tolist(), y=scores,
        marker_color=colors, marker_line_width=0, name="Bull-Bear Spread",
    ))
    fig.add_hline(y=0,   line_color="rgba(0,0,0,0.25)", line_width=1)
    fig.add_hline(y=20,  line_dash="dot", line_color="rgba(180,0,0,0.35)",
                  annotation_text="+20 caution", annotation_font=dict(size=10))
    fig.add_hline(y=-20, line_dash="dot", line_color="rgba(0,100,0,0.35)",
                  annotation_text="−20 contrarian buy", annotation_font=dict(size=10))
    fig.update_layout(
        title=dict(text="Bull-Bear Spread (Bullish% − Bearish%)", font=dict(size=13)),
        height=320,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k != "xaxis"},
    )
    return fig


def chart_naaim(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    col = "NAAIM Number" if "NAAIM Number" in df_plot.columns else "Mean/Average"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Date"], y=_series(df_plot, col),
        fill="tozeroy", name="NAAIM Number",
        line=dict(color="#0066cc", width=2),
        fillcolor="rgba(0,102,204,0.10)",
    ))
    fig.add_hline(y=100, line_dash="dot", line_color="rgba(180,0,0,0.35)",
                  annotation_text="100 — Fully Long", annotation_font=dict(size=10, color="#c62828"))
    fig.add_hline(y=0, line_color="rgba(0,0,0,0.2)", line_width=1)
    fig.update_layout(
        title=dict(text="NAAIM Exposure Index", font=dict(size=13)),
        height=360,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)", showline=False, zeroline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis")},
    )
    return fig


def chart_vix(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    close = _series(df_plot, "Close")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Date"].tolist(), y=close,
        fill="tozeroy", name="VIX Close",
        line=dict(color="#0066cc", width=1.5),
        fillcolor="rgba(0,102,204,0.10)",
    ))
    for y, color, label in [
        (40, "#b71c1c", "40 — Panic"),
        (30, "#e53935", "30 — High Fear"),
        (20, "#ff7043", "20 — Elevated"),
        (12, "rgba(0,0,0,0.48)", "12 — Complacency"),
    ]:
        fig.add_hline(y=y, line_dash="dot", line_color=color,
                      annotation_text=label, annotation_position="right",
                      annotation_font=dict(size=10, color=color))
    fig.update_layout(
        title=dict(text="CBOE VIX", font=dict(size=13)),
        height=380,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)", showline=False, zeroline=False),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis")},
    )
    return fig


def chart_breadth_combined(df: pd.DataFrame):
    df_plot = df.sort_values("Date")
    fig = go.Figure()
    for sym, color, name in [
        ("S5TW", "#2e7d32", "S5TW — % Above 50-Week MA"),
        ("S5FI", "#c62828", "S5FI — % Above 200-Day MA"),
    ]:
        if sym in df_plot.columns:
            fig.add_trace(go.Scatter(
                x=df_plot["Date"].tolist(), y=_series(df_plot, sym),
                name=name, line=dict(color=color, width=2),
            ))
    for y, lc, label in [
        (90, "#1b5e20", "90 — Overbought"),
        (10, "#b71c1c", "10 — Oversold"),
    ]:
        fig.add_hline(y=y, line_dash="dot", line_color=lc,
                      annotation_text=label, annotation_position="right",
                      annotation_font=dict(size=10, color=lc))
    fig.update_layout(
        title=dict(text="S5TW & S5FI — % of S&P 500 Above Key Moving Averages", font=dict(size=13)),
        height=400,
        xaxis=dict(rangeselector=_rangeselector(), gridcolor="rgba(0,0,0,0.06)",
                   showline=False, zeroline=False),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)", showline=False, zeroline=False,
                   range=[0, 100], ticksuffix="%"),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis")},
    )
    return fig


def chart_rank_heatmap(history: list):
    if not history:
        return None
    import numpy as np
    df = pd.DataFrame(history)
    df["Date"] = pd.to_datetime(df["Date"])

    tickers = sorted(df["Ticker"].unique())
    dates   = sorted(df["Date"].unique())
    n = len(tickers)

    z, hover = [], []
    for ticker in tickers:
        sub = df[df["Ticker"] == ticker].set_index("Date")
        row_z, row_h = [], []
        for d in dates:
            if d in sub.index:
                r   = sub.loc[d, "Rank"]
                rsi = sub.loc[d, "RSI"]
                row_z.append(r)
                row_h.append(f"<b>{ticker}</b><br>{d.strftime('%b %d')}<br>Rank {r}  ·  RSI {rsi:.1f}")
            else:
                row_z.append(None)
                row_h.append("")
        z.append(row_z)
        hover.append(row_h)

    # Colour bands: Rank 1-3 dark green → light green → yellow → dark red
    cs = [
        [0.00, "#1b5e20"],
        [0.13, "#1b5e20"],
        [0.20, "#66bb6a"],
        [0.47, "#66bb6a"],
        [0.53, "#fff176"],
        [0.73, "#ffa726"],
        [0.80, "#ef9a9a"],
        [1.00, "#b71c1c"],
    ]

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[d.strftime("%b %d") for d in dates],
        y=tickers,
        zmin=1, zmax=n,
        colorscale=cs,
        showscale=True,
        colorbar=dict(
            title=dict(text="Rank", side="right"),
            tickvals=[1, round(n * 0.25), round(n * 0.5), round(n * 0.75), n],
            thickness=12, len=0.8,
        ),
        hoverinfo="text",
        text=hover,
    ))
    fig.update_layout(
        title=dict(text="RSI Rank History — Daily Heatmap (Rank 1 = Strongest RSI)", font=dict(size=13)),
        height=max(320, 30 * n + 80),
        xaxis=dict(showgrid=False, showline=False, tickangle=-45, tickfont=dict(size=10)),
        yaxis=dict(showgrid=False, showline=False, autorange="reversed"),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis")},
    )
    return fig


def chart_rrg(rrg_data: list):
    if not rrg_data:
        return None

    COLORS = [
        "#0066cc","#e53935","#2e7d32","#f59e0b","#7b1fa2",
        "#00838f","#d84315","#37474f","#ad1457","#558b2f",
        "#1565c0","#6a1520","#4e342e","#00695c","#ff6f00","#c2185b",
    ]

    all_x, all_y = [], []
    for rec in rrg_data:
        for pt in rec["trail"]:
            if pt["RS_Ratio"] and pt["RS_Momentum"]:
                all_x.append(pt["RS_Ratio"])
                all_y.append(pt["RS_Momentum"])
    if not all_x:
        return None

    cx, cy = 100.0, 100.0
    pad    = 0.5
    half_x = max(abs(max(all_x) - cx), abs(min(all_x) - cx)) + pad
    half_y = max(abs(max(all_y) - cy), abs(min(all_y) - cy)) + pad
    half   = max(half_x, half_y, 1.5)
    xmin, xmax = cx - half, cx + half
    ymin, ymax = cy - half, cy + half

    fig = go.Figure()

    # Quadrant background fills
    for x0, x1, y0, y1, fill, label, lx, ly in [
        (cx, xmax, cy,   ymax, "rgba(46,125,50,0.07)",  "Leading",   cx + half*0.55, cy + half*0.8),
        (cx, xmax, ymin, cy,   "rgba(255,193,7,0.07)",  "Weakening", cx + half*0.55, cy - half*0.8),
        (xmin, cx, ymin, cy,   "rgba(198,40,40,0.07)",  "Lagging",   cx - half*0.55, cy - half*0.8),
        (xmin, cx, cy,   ymax, "rgba(33,150,243,0.07)", "Improving", cx - half*0.55, cy + half*0.8),
    ]:
        fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                      fillcolor=fill, line_width=0, layer="below")
        fig.add_annotation(x=lx, y=ly, text=f"<b>{label}</b>",
                           showarrow=False, font=dict(size=11, color="rgba(0,0,0,0.28)"),
                           xanchor="center")

    # Centre crosshairs
    fig.add_hline(y=cy, line_color="rgba(0,0,0,0.18)", line_width=1)
    fig.add_vline(x=cx, line_color="rgba(0,0,0,0.18)", line_width=1)

    # Ticker trails + current dots
    for i, rec in enumerate(rrg_data):
        trail = rec["trail"]
        if not trail:
            continue
        color  = COLORS[i % len(COLORS)]
        xs     = [pt["RS_Ratio"]    for pt in trail]
        ys     = [pt["RS_Momentum"] for pt in trail]
        dates  = [pt["Date"]        for pt in trail]
        ticker = rec["Ticker"]

        # Dotted trail line (includes last point so it connects to the dot)
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines",
            line=dict(color=color, width=1.5, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
        ))
        # Current position
        fig.add_trace(go.Scatter(
            x=[xs[-1]], y=[ys[-1]],
            mode="markers+text",
            name=ticker,
            marker=dict(color=color, size=10, line=dict(color="#ffffff", width=1.5)),
            text=[ticker],
            textposition="top center",
            textfont=dict(size=10, color=color),
            hovertemplate=(
                f"<b>{ticker}</b><br>"
                f"Date: {dates[-1]}<br>"
                f"RS-Ratio: %{{x:.2f}}<br>"
                f"RS-Momentum: %{{y:.2f}}<extra></extra>"
            ),
        ))

    fig.update_layout(
        title=dict(text="Relative Rotation Graph (RRG) — vs SPY  ·  dotted trail = last 10 days", font=dict(size=13)),
        height=520,
        xaxis=dict(
            title=dict(text="RS-Ratio  (>100 = outperforming SPY)", font=dict(size=11)),
            range=[xmin, xmax], gridcolor="rgba(0,0,0,0.06)",
            showline=False, zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="RS-Momentum  (>100 = strengthening)", font=dict(size=11)),
            range=[ymin, ymax], gridcolor="rgba(0,0,0,0.06)",
            showline=False, zeroline=False,
        ),
        legend=dict(
            orientation="v", x=1.02, y=1,
            bgcolor="rgba(0,0,0,0)", font=dict(size=10),
        ),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis", "legend")},
    )
    return fig


def chart_aaii_overview(df: pd.DataFrame):
    """Horizontal stacked bar chart: recent weeks + historical benchmarks."""
    if df.empty or not all(c in df.columns for c in ["Bullish", "Neutral", "Bearish"]):
        return None

    df_s = df.sort_values("Date").copy()
    for col in ["Bullish", "Neutral", "Bearish"]:
        df_s[col] = pd.to_numeric(df_s[col], errors="coerce")
    df_s = df_s.dropna(subset=["Bullish", "Neutral", "Bearish"])
    if df_s.empty:
        return None

    last4 = df_s.tail(4).reset_index(drop=True)

    cutoff = df_s["Date"].max() - pd.Timedelta(days=365)
    df_1yr = df_s[df_s["Date"] >= cutoff]
    if df_1yr.empty:
        df_1yr = df_s

    bull_hi_row = df_1yr.loc[df_1yr["Bullish"].idxmax()]
    neut_hi_row = df_1yr.loc[df_1yr["Neutral"].idxmax()]
    bear_hi_row = df_1yr.loc[df_1yr["Bearish"].idxmax()]

    bh = round(float(bull_hi_row["Bullish"]), 1)
    nh = round(float(neut_hi_row["Neutral"]), 1)
    rh = round(float(bear_hi_row["Bearish"]), 1)
    bh_d = bull_hi_row["Date"].strftime("%b %d")
    nh_d = neut_hi_row["Date"].strftime("%b %d")
    rh_d = bear_hi_row["Date"].strftime("%b %d")

    avg_b = round(float(df_s["Bullish"].mean()), 1)
    avg_n = round(float(df_s["Neutral"].mean()), 1)
    avg_r = round(float(df_s["Bearish"].mean()), 1)

    # Build rows bottom-to-top (Plotly horizontal bars render bottom→top)
    y_labels, b_vals, n_vals, r_vals = [], [], [], []

    for lbl, bv, nv, rv in [
        (f"  Bearish High  ({rh_d})", 0,     0,     rh),
        (f"  Neutral High  ({nh_d})", 0,     nh,    0),
        (f"  Bullish High  ({bh_d})", bh,    0,     0),
        ("  Historical Average",       avg_b, avg_n, avg_r),
    ]:
        y_labels.append(lbl); b_vals.append(bv); n_vals.append(nv); r_vals.append(rv)

    # Blank separator row
    y_labels.append(""); b_vals.append(0); n_vals.append(0); r_vals.append(0)

    # Recent weeks (oldest first = lower in chart)
    for _, row in last4.iterrows():
        y_labels.append(row["Date"].strftime("%b %d"))
        b_vals.append(float(row["Bullish"]))
        n_vals.append(float(row["Neutral"]))
        r_vals.append(float(row["Bearish"]))

    def inside_text(v):
        return f"{v:.1f}%" if v > 3 else ""

    fig = go.Figure()
    for name, vals, color in [
        ("Bullish", b_vals, "#388e3c"),
        ("Neutral", n_vals, "#9e9e9e"),
        ("Bearish", r_vals, "#e53935"),
    ]:
        fig.add_trace(go.Bar(
            name=name, y=y_labels, x=vals, orientation="h",
            marker=dict(color=color),
            text=[inside_text(v) for v in vals],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(size=11, color="white"),
        ))

    # Section header annotations
    for anchor_y, label in [
        ("  Historical Average",              "HISTORICAL VIEW"),
        (last4.iloc[0]["Date"].strftime("%b %d"), "SENTIMENT VOTES"),
    ]:
        fig.add_annotation(
            x=0, xref="paper", y=anchor_y, yref="y",
            text=f"<b>{label}</b>",
            showarrow=False, xanchor="left", yanchor="bottom",
            font=dict(size=9, color="#0066cc"),
            yshift=16,
        )

    fig.update_layout(
        barmode="stack",
        height=420,
        xaxis=dict(
            range=[0, 101], ticksuffix="%",
            gridcolor="rgba(0,0,0,0.07)", showline=False, zeroline=False,
        ),
        yaxis=dict(showline=False, gridcolor="rgba(0,0,0,0)", automargin=True),
        **{k: v for k, v in _PLOT_BASE.items() if k not in ("xaxis", "yaxis")},
    )
    return fig




# ── Main app ──────────────────────────────────────────────────────────────────
def main():
    (stockbee_df, rs_df, aaii_df, naaim_df, vix_df, breadth_df,
     snap_list, rsi_history, rrg_data,
     snap_elite8, hist_elite8, rrg_elite8,
     snap_theme,  hist_theme,  rrg_theme,
     last_updated, fetch_errors) = load_data()

    # ── Header row ──
    col_logo, col_meta, col_btn = st.columns([4, 3, 1])
    with col_logo:
        st.markdown(
            "<h1 style='margin:0; font-size:1.6rem; font-weight:800; "
            "letter-spacing:-0.01em; color:#1d1d1f;'>📈 Market Dashboard</h1>",
            unsafe_allow_html=True,
        )
    with col_meta:
        st.markdown(
            f"<p style='margin:6px 0 0; font-size:0.8rem; color:rgba(0,0,0,0.48);'>"
            f"Last updated &nbsp;·&nbsp; <b style='color:#1d1d1f'>{last_updated}</b></p>",
            unsafe_allow_html=True,
        )
        for err in fetch_errors:
            st.warning(err)
    with col_btn:
        if st.button("⟳  Refresh", use_container_width=True):
            with st.spinner("Fetching data…"):
                trigger_fetch()
            st.rerun()

    st.divider()

    with st.sidebar:
        st.markdown("Navigation")
        page = st.radio(
            "", ["📊  Market Monitor", "📰  AAII Sentiment",
                 "📡  NAAIM Exposure", "😱  VIX", "📶  Breadth (S5TW/S5FI)",
                 "🏆  RSI Tracker – Market & Sector",
                 "💎  RSI Tracker – Elite 8",
                 "🎯  RSI Tracker – Theme"],
            label_visibility="collapsed",
        )

    # ── RSI Tracker shared render helper ─────────────────────────────────────
    def render_rsi_tracker(key, heading, snap, history, rrg, default_tickers):
        st.markdown(
            f"<h1 style='margin:0; font-size:1.4rem; font-weight:800; color:#1d1d1f;'>"
            f"{heading}</h1>",
            unsafe_allow_html=True,
        )
        st.caption("Daily RSI rankings, key moving averages, and distance from highs for your watchlist.")
        st.divider()

        # Watchlist manager
        if key == "market":
            wl_file = f"{config.DATA_DIR}/watchlist.json"
        else:
            wl_file = f"{config.DATA_DIR}/watchlist_{key}.json"
        current_wl = json.load(open(wl_file)) if os.path.exists(wl_file) else default_tickers

        with st.expander("⚙️  Manage Watchlist", expanded=False):
            new_wl_text = st.text_area(
                "One ticker per line:",
                value="\n".join(current_wl),
                height=180,
                label_visibility="collapsed",
                key=f"wl_text_{key}",
            )
            if st.button("💾  Save & Refresh Data", key=f"wl_save_{key}"):
                new_tickers = [t.strip().upper() for t in new_wl_text.splitlines() if t.strip()]
                if new_tickers:
                    os.makedirs(config.DATA_DIR, exist_ok=True)
                    with open(wl_file, "w") as f:
                        json.dump(new_tickers, f)
                    with st.spinner("Fetching updated watchlist data…"):
                        subprocess.run(
                            [sys.executable, "-c",
                             f"from fetch_data import fetch_watchlist; fetch_watchlist('{key}')"],
                            cwd=os.path.dirname(os.path.abspath(__file__)),
                        )
                    st.cache_data.clear()
                    st.rerun()

        if not snap:
            st.info("No data yet — click **⟳ Refresh** or save your watchlist above.")
            return

        # Snapshot table
        snap_df = pd.DataFrame(snap)
        flag = lambda v: "▲" if v else "▼"
        disp = pd.DataFrame({
            "Rank":     snap_df["Rank"],
            "Ticker":   snap_df["Ticker"],
            "Close":    snap_df["Close"],
            "Chg%":     snap_df["Chg%"],
            "RSI":      snap_df["RSI"],
            ">EMA10":   snap_df["AbvEMA10"].map(flag),
            ">EMA20":   snap_df["AbvEMA20"].map(flag),
            ">SMA50":   snap_df["AbvSMA50"].map(flag),
            "ATR Dist": snap_df["ATR_Dist"],
            "Corr 1Y%": snap_df["Corr1Y%"],
        })

        def style_snap(df):
            s = df.style.set_properties(**{"background-color": "#ffffff", "color": "#1d1d1f"})
            def rc(v):
                if pd.isna(v): return ""
                if v >= 70: return "background-color:#c8e6c9;color:#1b5e20;font-weight:700"
                if v >= 60: return "background-color:#e8f5e9;color:#2e7d32"
                if v <= 30: return "background-color:#ffcdd2;color:#b71c1c;font-weight:700"
                if v <= 40: return "background-color:#ffebee;color:#c62828"
                return ""
            def cc(v):
                if pd.isna(v): return ""
                return "color:#2e7d32;font-weight:600" if v > 0 else "color:#c62828;font-weight:600" if v < 0 else ""
            def fc(v):
                return "color:#2e7d32;font-weight:700" if v == "▲" else "color:#c62828;font-weight:700" if v == "▼" else ""
            def ac(v):
                if pd.isna(v): return ""
                if v >= 3:  return "color:#2e7d32;font-weight:600"
                if v >= 1:  return "color:#2e7d32"
                if v <= -3: return "color:#b71c1c;font-weight:600"
                if v <= -1: return "color:#c62828"
                return ""
            def xc(v):
                if pd.isna(v): return ""
                if v >= -5:  return "color:#2e7d32;font-weight:600"
                if v >= -10: return "color:#2e7d32"
                if v <= -30: return "color:#b71c1c;font-weight:600"
                if v <= -20: return "color:#c62828"
                return ""
            s = s.map(rc, subset=["RSI"])
            s = s.map(cc, subset=["Chg%"])
            s = s.map(fc, subset=[">EMA10", ">EMA20", ">SMA50"])
            s = s.map(ac, subset=["ATR Dist"])
            s = s.map(xc, subset=["Corr 1Y%"])
            s = s.format({"Close": "{:.2f}", "Chg%": "{:+.2f}%", "RSI": "{:.1f}",
                          "ATR Dist": "{:+.2f}x", "Corr 1Y%": "{:.1f}%"}, na_rep="—")
            return s

        date_str = snap_df["Date"].iloc[0] if not snap_df.empty else "—"
        st.markdown(f"#### Snapshot — {date_str}")
        st.caption("RSI: 🟢 ≥70 overbought · 🔴 ≤30 oversold  ·  ▲/▼ = above/below MA  ·  "
                   "ATR Dist = (Close − SMA50) ÷ ATR14  ·  Corr 1Y% = drawdown from 1-yr high")
        st.dataframe(style_snap(disp), use_container_width=True,
                     height=min(48 * len(disp) + 38, 600), hide_index=True)

        # Rank Heatmap
        if history:
            st.markdown("#### RSI Rank History — Heatmap")
            st.caption("🟩 Rank 1–3 dark green · light green 4–8 · yellow 9–12 · 🟥 red 13+  ·  Hover for rank & RSI")
            all_t_h = sorted({r["Ticker"] for r in history})
            all_d_h = sorted({r["Date"]   for r in history})
            hc1, hc2 = st.columns([2, 3])
            with hc1:
                p_opts = {"Last 20 days": 20, "Last 40 days": 40, "All YTD": len(all_d_h)}
                h_per = st.selectbox("Period", list(p_opts.keys()), index=0, key=f"hm_per_{key}")
            with hc2:
                h_t = st.multiselect("Tickers", all_t_h, default=all_t_h, key=f"hm_t_{key}")
            cut = set(all_d_h[-p_opts[h_per]:])
            hm_fig = chart_rank_heatmap([r for r in history if r["Ticker"] in h_t and r["Date"] in cut])
            if hm_fig:
                st.plotly_chart(hm_fig, use_container_width=True)

        # RRG
        if rrg:
            st.markdown("#### Relative Rotation Graph")
            st.caption("Relative strength vs SPY (x-axis) · momentum of that strength (y-axis)  ·  "
                       "Leading → Weakening → Lagging → Improving = clockwise rotation")
            all_t_r = [rec["Ticker"] for rec in rrg]
            rc1, rc2 = st.columns([2, 3])
            with rc1:
                trail = st.slider("Trail length (days)", 3, 20, 10, key=f"rrg_trail_{key}")
            with rc2:
                r_t = st.multiselect("Tickers", all_t_r, default=all_t_r, key=f"rrg_t_{key}")
            rrg_fig = chart_rrg([{**rec, "trail": rec["trail"][-trail:]}
                                  for rec in rrg if rec["Ticker"] in r_t])
            if rrg_fig:
                st.plotly_chart(rrg_fig, use_container_width=True)

    # ── Page 1: Market Monitor ────────────────────────────────────────────────
    if page == "📊  Market Monitor":
        if stockbee_df.empty:
            st.info("No data yet — click **Refresh** to pull data from the source.")
        else:
            today = stockbee_df.iloc[0]

            # Signal banner
            render_signal_banner(today)

            # Metric cards — same colour rules as the breadth table
            up4  = _to_num(today.get("Number of stocks up 4% plus today"))
            dn4  = _to_num(today.get("Number of stocks down 4% plus today"))
            r5   = _to_num(today.get("5 day ratio"))
            r10  = _to_num(today.get("10 day ratio"))
            t208 = _to_num(today.get("T2108"))

            # Up 4%+ colour
            if up4 is not None and up4 >= config.UP4_EXTREME:
                up4_col = "dark_green"
            elif up4 is not None and dn4 is not None and up4 > dn4:
                up4_col = "green"
            elif up4 is not None and dn4 is not None and dn4 > up4:
                up4_col = "red"
            else:
                up4_col = "neutral"

            # Down 4%+ colour
            if dn4 is not None and dn4 >= config.DOWN4_EXTREME:
                dn4_col = "dark_red"
            elif up4 is not None and dn4 is not None and dn4 > up4:
                dn4_col = "red"
            elif up4 is not None and dn4 is not None and up4 > dn4:
                dn4_col = "green"
            else:
                dn4_col = "neutral"

            # Ratio colours
            r5_col  = "green" if r5  is not None and r5  > 2 else "red" if r5  is not None and r5  < 0.5 else "neutral"
            r10_col = "green" if r10 is not None and r10 > 2 else "red" if r10 is not None and r10 < 0.5 else "neutral"

            # T2108 colour
            t208_col = "dark_green" if t208 is not None and t208 <= 10 else "green" if t208 is not None and t208 <= 20 else "neutral"

            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.markdown(metric_card("Up 4%+",    f"{int(up4):,}"  if up4  is not None else "—", up4_col),  unsafe_allow_html=True)
            with m2:
                st.markdown(metric_card("Down 4%+",  f"{int(dn4):,}"  if dn4  is not None else "—", dn4_col),  unsafe_allow_html=True)
            with m3:
                st.markdown(metric_card("5D Ratio",  f"{r5:.2f}"      if r5   is not None else "—", r5_col),   unsafe_allow_html=True)
            with m4:
                st.markdown(metric_card("10D Ratio", f"{r10:.2f}"     if r10  is not None else "—", r10_col),  unsafe_allow_html=True)
            with m5:
                st.markdown(metric_card("T2108",     f"{t208:.1f}%"   if t208 is not None else "—", t208_col), unsafe_allow_html=True)

            st.markdown("#### Breadth History — All Sessions")
            st.caption(
                "Up/Down pairs: green = Up dominant · red = Down dominant · dark = extreme (≥ 400)  ·  "
                "10D Score: rolling 10-day sum (+2 dark green, +1 green, −1 red, −2 dark red)"
            )

            display_df = add_rolling_score(stockbee_df)
            col_config = {
                col: st.column_config.Column(help=tip)
                for col, tip in COLUMN_HELP.items()
            }
            st.dataframe(
                style_stockbee(display_df),
                column_config=col_config,
                use_container_width=True,
                height=520,
                hide_index=True,
            )

            st.markdown("#### Breadth Charts")
            st.plotly_chart(chart_t2108(stockbee_df), use_container_width=True)
            score_fig = chart_10d_score(display_df)
            if score_fig:
                st.plotly_chart(score_fig, use_container_width=True)

    # ── Page 3: AAII Sentiment ────────────────────────────────────────────────
    elif page == "📰  AAII Sentiment":
        st.markdown(
            "<h1 style='margin:0; font-size:1.4rem; font-weight:800; color:#1d1d1f;'>"
            "📰 AAII Investor Sentiment</h1>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Weekly survey of individual investors. "
            "Historically a contrarian indicator — extreme bearishness often precedes rallies."
        )
        st.divider()

        if aaii_df.empty:
            st.info("No AAII data yet — click **⟳ Refresh** to fetch.")
        else:
            latest = aaii_df.iloc[0]
            bull  = _to_num(latest.get("Bullish"))
            bear  = _to_num(latest.get("Bearish"))
            neut  = _to_num(latest.get("Neutral"))
            sprd  = _to_num(latest.get("Spread"))

            # Overview chart — recent weeks vs historical benchmarks
            overview_fig = chart_aaii_overview(aaii_df)
            if overview_fig:
                st.plotly_chart(overview_fig, use_container_width=True)

            st.markdown("#### Latest Reading")
            date_str = latest["Date"].strftime("%b %d, %Y") if pd.notna(latest.get("Date")) else "—"
            st.markdown(
                f"<p style='font-size:0.8rem; color:rgba(0,0,0,0.48); margin-bottom:12px;'>"
                f"Survey week ending <b style='color:#1d1d1f'>{date_str}</b></p>",
                unsafe_allow_html=True,
            )

            # Contrarian colour logic
            bull_col = "red"    if bull is not None and bull > 50 else \
                       "green"  if bull is not None and bull < 25 else "neutral"
            bear_col = "green"  if bear is not None and bear > 50 else \
                       "dark_green" if bear is not None and bear > 60 else \
                       "red"    if bear is not None and bear < 20 else "neutral"
            sprd_col = "dark_green" if sprd is not None and sprd < -20 else \
                       "green"      if sprd is not None and sprd < 0  else \
                       "red"        if sprd is not None and sprd > 20 else "neutral"

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.markdown(metric_card("Bullish",       f"{bull:.1f}%" if bull is not None else "—", bull_col), unsafe_allow_html=True)
            with m2:
                st.markdown(metric_card("Bearish",       f"{bear:.1f}%" if bear is not None else "—", bear_col), unsafe_allow_html=True)
            with m3:
                st.markdown(metric_card("Neutral",       f"{neut:.1f}%" if neut is not None else "—", "neutral"), unsafe_allow_html=True)
            with m4:
                sign = "+" if sprd is not None and sprd > 0 else ""
                st.markdown(metric_card("Bull-Bear Spread", f"{sign}{sprd:.1f}%" if sprd is not None else "—", sprd_col), unsafe_allow_html=True)

            st.markdown("#### Sentiment History")
            st.caption(
                "Bullish >50% = contrarian caution (too much optimism)  ·  "
                "Bearish >50% = contrarian buy signal (extreme pessimism)"
            )
            st.plotly_chart(chart_aaii_sentiment(aaii_df), use_container_width=True)

            fig_sprd = chart_aaii_spread(aaii_df)
            if fig_sprd:
                st.plotly_chart(fig_sprd, use_container_width=True)

            st.markdown("#### Survey Data — All Weeks")
            disp = aaii_df.copy()
            disp["Date"] = disp["Date"].dt.strftime("%Y-%m-%d")
            for col in ["Bullish", "Bearish", "Neutral", "Spread"]:
                if col in disp.columns:
                    disp[col] = pd.to_numeric(disp[col], errors="coerce")
            st.dataframe(
                disp.style.format(
                    {c: "{:.1f}%" for c in ["Bullish", "Bearish", "Neutral", "Spread"] if c in disp.columns},
                    na_rep="—",
                ).set_properties(**{"background-color": "#ffffff", "color": "#1d1d1f"}),
                use_container_width=True,
                height=400,
                hide_index=True,
            )

    # ── Page 7: RSI Tracker – Market & Sector ────────────────────────────────
    elif page == "🏆  RSI Tracker – Market & Sector":
        render_rsi_tracker("market", "🏆 RSI Tracker – Market &amp; Sector",
                           snap_list, rsi_history, rrg_data, config.WATCHLIST)

    # ── Page 8: RSI Tracker – Elite 8 ────────────────────────────────────────
    elif page == "💎  RSI Tracker – Elite 8":
        render_rsi_tracker("elite8", "💎 RSI Tracker – Elite 8",
                           snap_elite8, hist_elite8, rrg_elite8, config.WATCHLIST_ELITE8)

    # ── Page 9: RSI Tracker – Theme ──────────────────────────────────────────
    elif page == "🎯  RSI Tracker – Theme":
        render_rsi_tracker("theme", "🎯 RSI Tracker – Theme",
                           snap_theme, hist_theme, rrg_theme, config.WATCHLIST_THEME)

    # ── Page 5: VIX ──────────────────────────────────────────────────────────
    elif page == "😱  VIX":
        st.markdown(
            "<h1 style='margin:0; font-size:1.4rem; font-weight:800; color:#1d1d1f;'>"
            "😱 CBOE Volatility Index (VIX)</h1>",
            unsafe_allow_html=True,
        )
        st.caption(
            "The VIX measures expected 30-day volatility of the S&P 500. "
            "Spikes above 30 signal fear; readings below 15 indicate complacency."
        )
        st.divider()

        if vix_df.empty:
            st.info("No VIX data yet — click **⟳ Refresh** to fetch.")
        else:
            latest = vix_df.iloc[0]
            vix_now  = _to_num(latest.get("Close"))
            vix_high = _to_num(latest.get("High"))
            vix_low  = _to_num(latest.get("Low"))
            date_str = latest["Date"].strftime("%b %d, %Y") if pd.notna(latest.get("Date")) else "—"

            # 1-year stats
            cutoff_1y = vix_df["Date"].max() - pd.Timedelta(days=365)
            df_1y = vix_df[vix_df["Date"] >= cutoff_1y]
            vix_1y_high = round(float(df_1y["Close"].max()), 2) if not df_1y.empty else None
            vix_1y_low  = round(float(df_1y["Close"].min()), 2) if not df_1y.empty else None
            vix_1y_avg  = round(float(df_1y["Close"].mean()), 2) if not df_1y.empty else None

            # Colour: red = fear (>30), orange = elevated (>20), blue = normal
            if vix_now is not None:
                if vix_now >= 40:   vc = "dark_red"
                elif vix_now >= 30: vc = "red"
                elif vix_now >= 20: vc = "neutral"
                else:               vc = "green"
            else:
                vc = "neutral"

            st.markdown(
                f"<p style='font-size:0.8rem; color:rgba(0,0,0,0.48); margin-bottom:12px;'>"
                f"As of <b style='color:#1d1d1f'>{date_str}</b></p>",
                unsafe_allow_html=True,
            )

            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.markdown(metric_card("VIX Close",    f"{vix_now:.2f}"   if vix_now  is not None else "—", vc),       unsafe_allow_html=True)
            with c2:
                st.markdown(metric_card("Day High",     f"{vix_high:.2f}"  if vix_high is not None else "—", "neutral"), unsafe_allow_html=True)
            with c3:
                st.markdown(metric_card("Day Low",      f"{vix_low:.2f}"   if vix_low  is not None else "—", "neutral"), unsafe_allow_html=True)
            with c4:
                st.markdown(metric_card("1-Yr High",    f"{vix_1y_high:.2f}" if vix_1y_high is not None else "—", "neutral"), unsafe_allow_html=True)
            with c5:
                st.markdown(metric_card("1-Yr Avg",     f"{vix_1y_avg:.2f}"  if vix_1y_avg  is not None else "—", "neutral"), unsafe_allow_html=True)

            st.markdown("#### VIX Chart")
            st.plotly_chart(chart_vix(vix_df), use_container_width=True)

            st.markdown("#### VIX Regimes")
            st.caption("Colour bands: 🔵 <20 Normal · 🟠 20–30 Elevated · 🔴 30–40 High Fear · ⬛ ≥40 Panic")

            st.markdown("#### Historical Data")
            disp = vix_df.head(252).copy()
            disp["Date"] = disp["Date"].dt.strftime("%Y-%m-%d")
            for col in ["Close", "High", "Low", "Open"]:
                if col in disp.columns:
                    disp[col] = pd.to_numeric(disp[col], errors="coerce")
            st.dataframe(
                disp.style.format(
                    {c: "{:.2f}" for c in ["Close", "High", "Low", "Open"] if c in disp.columns},
                    na_rep="—",
                ).set_properties(**{"background-color": "#ffffff", "color": "#1d1d1f"}),
                use_container_width=True,
                height=400,
                hide_index=True,
            )

    # ── Page 6: Breadth (S5TW / S5FI) ────────────────────────────────────────
    elif page == "📶  Breadth (S5TW/S5FI)":
        st.markdown(
            "<h1 style='margin:0; font-size:1.4rem; font-weight:800; color:#1d1d1f;'>"
            "📶 Market Breadth — S5TW &amp; S5FI</h1>",
            unsafe_allow_html=True,
        )
        st.caption(
            "S5TW: % of S&P 500 stocks above their 50-week MA  ·  "
            "S5FI: % of S&P 500 stocks above their 200-day MA  ·  "
            "Source: TradingView (INDEX)"
        )
        st.divider()

        if breadth_df.empty:
            st.info("No breadth data yet — click **⟳ Refresh** to fetch.")
        else:
            latest = breadth_df.iloc[0]
            s5tw = _to_num(latest.get("S5TW"))
            s5fi = _to_num(latest.get("S5FI"))
            date_str = latest["Date"].strftime("%b %d, %Y") if pd.notna(latest.get("Date")) else "—"

            def breadth_color(v):
                if v is None: return "neutral"
                if v >= 70:   return "dark_green"
                if v >= 50:   return "green"
                if v <= 30:   return "dark_red"
                if v <= 50:   return "red"
                return "neutral"

            st.markdown(
                f"<p style='font-size:0.8rem; color:rgba(0,0,0,0.48); margin-bottom:12px;'>"
                f"As of <b style='color:#1d1d1f'>{date_str}</b></p>",
                unsafe_allow_html=True,
            )

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(metric_card(
                    "S5TW — % Above 50-Week MA",
                    f"{s5tw:.1f}%" if s5tw is not None else "—",
                    breadth_color(s5tw),
                ), unsafe_allow_html=True)
            with c2:
                st.markdown(metric_card(
                    "S5FI — % Above 200-Day MA",
                    f"{s5fi:.1f}%" if s5fi is not None else "—",
                    breadth_color(s5fi),
                ), unsafe_allow_html=True)

            st.markdown("#### S5TW & S5FI")
            st.plotly_chart(chart_breadth_combined(breadth_df), use_container_width=True)

            st.markdown("#### Historical Data")
            disp = breadth_df.head(252).copy()
            disp["Date"] = disp["Date"].dt.strftime("%Y-%m-%d")
            for col in ["S5TW", "S5FI"]:
                if col in disp.columns:
                    disp[col] = pd.to_numeric(disp[col], errors="coerce")
            st.dataframe(
                disp.style.format(
                    {c: "{:.2f}%" for c in ["S5TW", "S5FI"] if c in disp.columns},
                    na_rep="—",
                ).set_properties(**{"background-color": "#ffffff", "color": "#1d1d1f"}),
                use_container_width=True,
                height=400,
                hide_index=True,
            )

    # ── Page 4: NAAIM Exposure ────────────────────────────────────────────────
    elif page == "📡  NAAIM Exposure":
        st.markdown(
            "<h1 style='margin:0; font-size:1.4rem; font-weight:800; color:#1d1d1f;'>"
            "📡 NAAIM Exposure Index</h1>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Weekly survey of active money managers' equity market exposure. "
            "High readings = aggressive positioning; low readings = defensive."
        )
        st.divider()

        if naaim_df.empty:
            st.info("No NAAIM data yet — click **⟳ Refresh** to fetch.")
        else:
            col = "NAAIM Number" if "NAAIM Number" in naaim_df.columns else "Mean/Average"
            latest = naaim_df.iloc[0]
            current_val = _to_num(latest.get(col))
            date_str = latest["Date"].strftime("%b %d, %Y") if pd.notna(latest.get("Date")) else "—"

            # Last completed quarter average
            latest_date = naaim_df["Date"].max()
            cur_q = (latest_date.month - 1) // 3
            cur_year = latest_date.year
            if cur_q == 0:
                lq_start = datetime(cur_year - 1, 10, 1)
                lq_end   = datetime(cur_year - 1, 12, 31)
                lq_label = f"Q4 {cur_year - 1}"
            else:
                lq_start = datetime(cur_year, (cur_q - 1) * 3 + 1, 1)
                lq_end   = datetime(cur_year, cur_q * 3, 30)
                lq_label = f"Q{cur_q} {cur_year}"

            lq_mask = (naaim_df["Date"] >= lq_start) & (naaim_df["Date"] <= lq_end)
            lq_avg = naaim_df.loc[lq_mask, col].mean()
            lq_avg = round(float(lq_avg), 2) if pd.notna(lq_avg) else None

            # Colour logic: >75 = bullish (red = overextended), <25 = bearish (green = oversold)
            if current_val is not None:
                if current_val >= 90:
                    naaim_col = "dark_red"
                elif current_val >= 75:
                    naaim_col = "red"
                elif current_val <= 10:
                    naaim_col = "dark_green"
                elif current_val <= 25:
                    naaim_col = "green"
                else:
                    naaim_col = "neutral"
            else:
                naaim_col = "neutral"

            st.markdown(
                f"<p style='font-size:0.8rem; color:rgba(0,0,0,0.48); margin-bottom:12px;'>"
                f"Posted <b style='color:#1d1d1f'>{date_str}</b></p>",
                unsafe_allow_html=True,
            )

            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(metric_card(
                    "NAAIM Number",
                    f"{current_val:.2f}" if current_val is not None else "—",
                    naaim_col,
                ), unsafe_allow_html=True)
            with m2:
                st.markdown(metric_card(
                    f"Last Quarter Avg ({lq_label})",
                    f"{lq_avg:.2f}" if lq_avg is not None else "—",
                    "neutral",
                ), unsafe_allow_html=True)
            with m3:
                sp = _to_num(latest.get("S&P 500"))
                st.markdown(metric_card(
                    "S&P 500",
                    f"{sp:,.2f}" if sp is not None else "—",
                    "neutral",
                ), unsafe_allow_html=True)

            st.markdown("#### NAAIM Number — Historical")
            st.plotly_chart(chart_naaim(naaim_df), use_container_width=True)

            st.markdown("#### Survey Data — All Weeks")
            disp = naaim_df.copy()
            disp["Date"] = disp["Date"].dt.strftime("%Y-%m-%d")
            st.dataframe(
                disp.style.set_properties(**{"background-color": "#ffffff", "color": "#1d1d1f"}),
                use_container_width=True,
                height=400,
                hide_index=True,
            )


main()
