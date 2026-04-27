"""
Fetches data from Stockbee Market Monitor and Relative Strength Google Sheets.
Run this script manually or via Windows Task Scheduler after market close (~4:30 PM ET).
"""

import os
import io
import json
import re
import requests
import pandas as pd
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TOKEN_PATH = "credentials/token.json"
OAUTH_CLIENT_PATH = "credentials/oauth_client.json"


def get_credentials():
    # When running on Streamlit Cloud, credentials are injected via env var
    token_json_env = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_json_env and not os.path.exists(TOKEN_PATH):
        os.makedirs("credentials", exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(token_json_env)

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(OAUTH_CLIENT_PATH):
                raise FileNotFoundError(
                    f"OAuth client file not found at '{OAUTH_CLIENT_PATH}'. "
                    "Please follow the setup instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs("credentials", exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def fetch_stockbee():
    print("Fetching Stockbee Market Monitor...")
    url = (
        f"https://docs.google.com/spreadsheets/d/"
        f"{config.STOCKBEE_SHEET_ID}/export?format=csv"
    )
    # Row 0 is a merged group-label row; row 1 has the real column names
    df = pd.read_csv(url, header=1)
    df.columns = df.columns.str.strip().str.replace(r"\s+", " ", regex=True)
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    df = df.sort_values("Date", ascending=False).reset_index(drop=True)

    # Clean S&P column (remove commas from numbers like "7,163.69")
    if "S&P" in df.columns:
        df["S&P"] = df["S&P"].astype(str).str.replace(",", "").str.strip()
        df["S&P"] = pd.to_numeric(df["S&P"], errors="coerce")

    os.makedirs(config.DATA_DIR, exist_ok=True)
    df.to_json(f"{config.DATA_DIR}/stockbee.json", orient="records", date_format="iso")
    print(f"  Stockbee: {len(df)} rows saved.")
    return df


def fetch_relative_strength():
    print("Fetching Relative Strength sheet...")
    creds = get_credentials()
    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    sheets_api = service.spreadsheets()

    # Find tab name matching the gid
    meta = sheets_api.get(spreadsheetId=config.RS_SHEET_ID).execute()
    tab_name = None
    for sheet in meta["sheets"]:
        if str(sheet["properties"]["sheetId"]) == config.RS_SHEET_GID:
            tab_name = sheet["properties"]["title"]
            break

    if not tab_name:
        raise ValueError(
            f"Could not find a sheet tab with gid={config.RS_SHEET_GID}. "
            "Check that RS_SHEET_GID in config.py is correct."
        )

    result = sheets_api.values().get(
        spreadsheetId=config.RS_SHEET_ID,
        range=tab_name,
    ).execute()

    values = result.get("values", [])
    if len(values) < 2:
        raise ValueError("RS sheet appears to be empty or has no data rows.")

    headers = values[0]
    # The first two columns have no header — name them Rank and Ticker
    if headers[0] == "":
        headers[0] = "Rank"
    if len(headers) > 1 and headers[1] == "":
        headers[1] = "Ticker"

    rows = values[1:]
    # Pad short rows so they align with headers
    padded = [row + [""] * (len(headers) - len(row)) for row in rows]
    df = pd.DataFrame(padded, columns=headers)

    os.makedirs(config.DATA_DIR, exist_ok=True)
    df.to_json(f"{config.DATA_DIR}/relative_strength.json", orient="records")
    print(f"  Relative Strength: {len(df)} rows saved.")
    return df


def fetch_aaii():
    print("Fetching AAII Investor Sentiment...")
    xls_url = "https://www.aaii.com/files/surveys/sentiment.xls"
    xls_path = f"{config.DATA_DIR}/sentiment_raw.xls"
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    os.makedirs(config.DATA_DIR, exist_ok=True)
    try:
        resp = requests.get(xls_url, headers={"User-Agent": ua}, timeout=30)
        resp.raise_for_status()
        if b"Pardon Our Interruption" in resp.content or resp.headers.get("Content-Type", "").startswith("text/html"):
            raise ValueError("AAII site returned bot-detection page.")
        with open(xls_path, "wb") as f:
            f.write(resp.content)
        print(f"  Downloaded {len(resp.content):,} bytes.")
    except Exception as e:
        if os.path.exists(xls_path):
            print(f"  Download failed ({e}). Using cached file: {xls_path}")
        else:
            raise

    # Row 3 (0-indexed) is the real header; row 4 is blank — skip it
    df = pd.read_excel(xls_path, header=3, skiprows=[4])
    df.columns = [str(c).strip() for c in df.columns]

    df = df.rename(columns={"Date": "Date"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    # Values are decimals (0.46 = 46%) — convert to percentages
    for col in ["Bullish", "Neutral", "Bearish", "Spread"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            if df[col].dropna().abs().median() < 1.5:
                df[col] = (df[col] * 100).round(1)
            else:
                df[col] = df[col].round(1)

    if "Spread" not in df.columns and "Bullish" in df.columns and "Bearish" in df.columns:
        df["Spread"] = (df["Bullish"] - df["Bearish"]).round(1)

    df = df[["Date"] + [c for c in ["Bullish", "Neutral", "Bearish", "Spread"] if c in df.columns]]
    df = df.sort_values("Date", ascending=False).reset_index(drop=True)

    df.to_json(f"{config.DATA_DIR}/aaii.json", orient="records", date_format="iso")
    print(f"  AAII Sentiment: {len(df)} rows saved.")
    return df


def fetch_naaim():
    print("Fetching NAAIM Exposure Index...")
    page_url = "https://naaim.org/programs/naaim-exposure-index/"
    xlsx_path = f"{config.DATA_DIR}/naaim_raw.xlsx"
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

    os.makedirs(config.DATA_DIR, exist_ok=True)

    # Find the latest xlsx link on the NAAIM page
    page_resp = requests.get(page_url, headers={"User-Agent": ua}, timeout=30)
    page_resp.raise_for_status()
    xlsx_urls = re.findall(r'https://naaim\.org[^\s"\']*\.xlsx', page_resp.text)
    if not xlsx_urls:
        raise ValueError("Could not find xlsx download link on NAAIM page.")
    xlsx_url = xlsx_urls[0]
    print(f"  Found: {xlsx_url.split('/')[-1]}")

    # Download
    resp = requests.get(xlsx_url, headers={"User-Agent": ua}, timeout=30)
    resp.raise_for_status()
    with open(xlsx_path, "wb") as f:
        f.write(resp.content)
    print(f"  Downloaded {len(resp.content):,} bytes.")

    # Parse — row 0 is the header
    df = pd.read_excel(xlsx_path, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    # Keep key columns
    keep = ["Date", "NAAIM Number", "Mean/Average", "S&P 500"]
    df = df[[c for c in keep if c in df.columns]]
    for col in df.columns:
        if col != "Date":
            df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

    df = df.sort_values("Date", ascending=False).reset_index(drop=True)
    df.to_json(f"{config.DATA_DIR}/naaim.json", orient="records", date_format="iso")
    print(f"  NAAIM: {len(df)} rows saved.")
    return df


def fetch_breadth():
    print("Fetching S5TW / S5FI breadth indicators...")
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    frames = {}
    for sym in ["S5TW", "S5FI"]:
        data = tv.get_hist(sym, "INDEX", interval=Interval.in_daily, n_bars=5000)
        if data is None:
            raise ValueError(f"tvDatafeed returned no data for {sym}.")
        data = data.reset_index()[["datetime", "close"]].rename(
            columns={"datetime": "Date", "close": sym}
        )
        data["Date"] = pd.to_datetime(data["Date"]).dt.tz_localize(None).dt.normalize()
        data[sym] = pd.to_numeric(data[sym], errors="coerce").round(2)
        frames[sym] = data.set_index("Date")
        print(f"  {sym}: {len(data)} rows.")

    df = frames["S5TW"].join(frames["S5FI"], how="outer").reset_index()
    df = df.sort_values("Date", ascending=False).reset_index(drop=True)

    os.makedirs(config.DATA_DIR, exist_ok=True)
    df.to_json(f"{config.DATA_DIR}/breadth.json", orient="records", date_format="iso")
    print(f"  Breadth: {len(df)} rows saved.")
    return df


def _wl_paths(key):
    """Return data-file paths for a given watchlist key."""
    d = config.DATA_DIR
    if key == "market":
        return dict(watchlist=f"{d}/watchlist.json",
                    snapshot=f"{d}/watchlist_snapshot.json",
                    history=f"{d}/rsi_history.json",
                    rrg=f"{d}/rrg.json")
    return dict(watchlist=f"{d}/watchlist_{key}.json",
                snapshot=f"{d}/watchlist_{key}_snapshot.json",
                history=f"{d}/rsi_history_{key}.json",
                rrg=f"{d}/rrg_{key}.json")


def backfill_rsi_history(history_path, tickers):
    """Seed an rsi_history file with daily RSI rankings from Jan 2, 2026.
    Skips if the file already has ≥ 80 records.
    """
    import yfinance as yf

    if os.path.exists(history_path):
        with open(history_path) as f:
            existing = json.load(f)
        if len(existing) >= 80:
            return

    if not tickers:
        return

    print(f"  Backfilling RSI history ({history_path})...")
    # Oct 2025 start → ~60 trading-day warmup before Jan 2, 2026
    raw = yf.download(tickers, start="2025-10-01", progress=False,
                      group_by="ticker", auto_adjust=True)

    def _get(ticker):
        if len(tickers) == 1:
            return raw.copy()
        try:
            return raw[ticker].copy()
        except KeyError:
            return pd.DataFrame()

    def _rsi(close, period=14):
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
        return (100 - 100 / (1 + gain / loss.replace(0, float("nan")))).round(2)

    rsi_series = {}
    for ticker in tickers:
        try:
            df = _get(ticker).dropna(subset=["Close"])
            if len(df) < 20:
                continue
            rsi_series[ticker] = _rsi(df["Close"])
        except Exception as e:
            print(f"  Backfill {ticker}: {e}")

    if not rsi_series:
        return

    cutoff = pd.Timestamp("2026-01-02")
    all_dates = set()
    for s in rsi_series.values():
        for d in s.index:
            if pd.Timestamp(d) >= cutoff:
                all_dates.add(pd.Timestamp(d).normalize())

    history = []
    for date in sorted(all_dates):
        day_records = []
        for ticker, rsi in rsi_series.items():
            idx = rsi.index.normalize()
            mask = idx == date
            if mask.any() and not pd.isna(rsi[mask].iloc[0]):
                day_records.append({"Ticker": ticker, "RSI": float(rsi[mask].iloc[0])})
        if not day_records:
            continue
        day_records.sort(key=lambda x: x["RSI"], reverse=True)
        date_str = date.strftime("%Y-%m-%d")
        for rank, rec in enumerate(day_records, 1):
            history.append({"Date": date_str, "Ticker": rec["Ticker"],
                            "RSI": rec["RSI"], "Rank": rank})

    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(history_path, "w") as f:
        json.dump(history, f)

    unique_dates = len(set(r["Date"] for r in history))
    print(f"  Backfilled {unique_dates} trading days ({len(history)} records).")


def fetch_watchlist(key="market", default_tickers=None):
    """Fetch snapshot, history, and RRG for one RSI tracker.

    key            – "market" | "elite8" | "theme" (drives file names)
    default_tickers – fallback tickers if no saved watchlist file exists
    """
    import yfinance as yf
    from datetime import timedelta

    if default_tickers is None:
        default_tickers = config.WATCHLIST

    paths = _wl_paths(key)
    print(f"Fetching Watchlist [{key}]...")

    # Read saved watchlist or fall back to default
    if os.path.exists(paths["watchlist"]):
        with open(paths["watchlist"]) as f:
            tickers = json.load(f)
    else:
        tickers = default_tickers

    if not tickers:
        print(f"  [{key}] watchlist is empty.")
        return

    # Backfill history if this is a fresh tracker
    backfill_rsi_history(paths["history"], tickers)

    # Always include SPY for RRG benchmark (deduplicate)
    download_tickers = list(dict.fromkeys(tickers + ["SPY"]))

    # 500 days gives enough runway for 50-SMA + 1-year high
    start = (datetime.now() - timedelta(days=500)).strftime("%Y-%m-%d")
    raw = yf.download(download_tickers, start=start, progress=False,
                      group_by="ticker", auto_adjust=True)

    def _get(ticker):
        if len(download_tickers) == 1:
            return raw.copy()
        try:
            return raw[ticker].copy()
        except KeyError:
            return pd.DataFrame()

    def _rsi(close, period=14):
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
        return (100 - 100 / (1 + gain / loss.replace(0, float("nan")))).round(2)

    def _atr(high, low, close, period=14):
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low  - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.ewm(alpha=1/period, adjust=False).mean()

    # ── Snapshot ─────────────────────────────────────────────────────────────
    snapshots = []
    for ticker in tickers:
        try:
            df = _get(ticker).dropna(subset=["Close"])
            if len(df) < 52:
                continue
            c, h, lo = df["Close"], df["High"], df["Low"]
            rsi   = _rsi(c)
            ema10 = c.ewm(span=10, adjust=False).mean()
            ema20 = c.ewm(span=20, adjust=False).mean()
            sma50 = c.rolling(50).mean()
            atr14 = _atr(h, lo, c)
            last_c, prev_c = float(c.iloc[-1]), float(c.iloc[-2])
            last_sma50 = float(sma50.iloc[-1])
            last_atr   = float(atr14.iloc[-1])
            snapshots.append({
                "Ticker":   ticker,
                "Date":     df.index[-1].strftime("%Y-%m-%d"),
                "Close":    round(last_c, 2),
                "Chg%":     round((last_c - prev_c) / prev_c * 100, 2),
                "RSI":      round(float(rsi.iloc[-1]), 2),
                "EMA10":    round(float(ema10.iloc[-1]), 2),
                "EMA20":    round(float(ema20.iloc[-1]), 2),
                "SMA50":    round(last_sma50, 2),
                "ATR14":    round(last_atr, 2),
                "AbvEMA10": last_c > float(ema10.iloc[-1]),
                "AbvEMA20": last_c > float(ema20.iloc[-1]),
                "AbvSMA50": last_c > last_sma50,
                "ATR_Dist": round((last_c - last_sma50) / last_atr, 2) if last_atr else None,
                "Corr1Y%":  round((last_c - float(c.tail(252).max())) / float(c.tail(252).max()) * 100, 2),
            })
        except Exception as e:
            print(f"  {ticker}: {e}")

    if not snapshots:
        raise ValueError(f"[{key}] No valid data fetched.")

    snapshots.sort(key=lambda x: x["RSI"], reverse=True)
    for i, s in enumerate(snapshots):
        s["Rank"] = i + 1

    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(paths["snapshot"], "w") as f:
        json.dump(snapshots, f)

    # ── History (YTD, deduplicate today) ─────────────────────────────────────
    today_str = datetime.now().strftime("%Y-%m-%d")
    ytd_start = f"{datetime.now().year}-01-01"
    history = []
    if os.path.exists(paths["history"]):
        with open(paths["history"]) as f:
            history = json.load(f)
    history = [h for h in history
               if h.get("Date") != today_str and h.get("Date", "") >= ytd_start]
    for s in snapshots:
        history.append({"Date": today_str, "Ticker": s["Ticker"],
                        "RSI": s["RSI"], "Rank": s["Rank"]})
    with open(paths["history"], "w") as f:
        json.dump(history, f)

    # ── RRG vs SPY ────────────────────────────────────────────────────────────
    rrg_records = []
    try:
        spy_close = _get("SPY").dropna(subset=["Close"])["Close"]
        for ticker in tickers:
            if ticker == "SPY":
                continue
            try:
                df = _get(ticker).dropna(subset=["Close"])
                if len(df) < 60:
                    continue
                merged = (df["Close"].rename(ticker).to_frame()
                          .join(spy_close.rename("SPY"), how="inner").dropna())
                rs       = merged[ticker] / merged["SPY"]
                rs_ratio = (rs / rs.rolling(10, min_periods=5).mean()) * 100
                rs_mom   = (rs_ratio / rs_ratio.shift(5)) * 100
                trail_df = (pd.DataFrame({"RS_Ratio": rs_ratio, "RS_Momentum": rs_mom})
                            .tail(10).dropna().reset_index())
                if trail_df.empty:
                    continue
                dc = trail_df.columns[0]
                rrg_records.append({
                    "Ticker": ticker,
                    "trail": [{"Date": str(r[dc])[:10],
                               "RS_Ratio": round(float(r["RS_Ratio"]), 4),
                               "RS_Momentum": round(float(r["RS_Momentum"]), 4)}
                              for _, r in trail_df.iterrows()],
                })
            except Exception as e:
                print(f"  RRG {ticker}: {e}")
    except Exception as e:
        print(f"  RRG SPY benchmark: {e}")

    with open(paths["rrg"], "w") as f:
        json.dump(rrg_records, f)
    print(f"  [{key}] snapshot={len(snapshots)}  RRG={len(rrg_records)}  history={len(history)} records.")
    return snapshots


def fetch_vix():
    print("Fetching VIX history...")
    import yfinance as yf
    df = yf.download("^VIX", start="1990-01-01", progress=False)
    if df.empty:
        raise ValueError("yfinance returned empty VIX data.")

    # Flatten multi-level columns
    df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    df = df.reset_index()
    df = df.rename(columns={"Date": "Date", "Close": "Close", "High": "High", "Low": "Low", "Open": "Open"})
    df["Date"] = pd.to_datetime(df["Date"])
    for col in ["Close", "High", "Low", "Open"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(2)
    df = df[["Date"] + [c for c in ["Close", "High", "Low", "Open"] if c in df.columns]]
    df = df.sort_values("Date", ascending=False).reset_index(drop=True)

    os.makedirs(config.DATA_DIR, exist_ok=True)
    df.to_json(f"{config.DATA_DIR}/vix.json", orient="records", date_format="iso")
    print(f"  VIX: {len(df)} rows saved.")
    return df


def main():
    timestamp = datetime.now()
    print(f"\n=== Market Dashboard Data Fetch — {timestamp.strftime('%Y-%m-%d %H:%M')} ===\n")
    errors = []

    try:
        fetch_stockbee()
    except Exception as e:
        errors.append(f"Stockbee fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_relative_strength()
    except Exception as e:
        errors.append(f"RS fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_aaii()
    except Exception as e:
        errors.append(f"AAII fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_naaim()
    except Exception as e:
        errors.append(f"NAAIM fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_vix()
    except Exception as e:
        errors.append(f"VIX fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_breadth()
    except Exception as e:
        errors.append(f"Breadth fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_watchlist("market",  config.WATCHLIST)
    except Exception as e:
        errors.append(f"Watchlist [market] fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_watchlist("elite8",  config.WATCHLIST_ELITE8)
    except Exception as e:
        errors.append(f"Watchlist [elite8] fetch failed: {e}")
        print(f"  ERROR: {e}")

    try:
        fetch_watchlist("theme",   config.WATCHLIST_THEME)
    except Exception as e:
        errors.append(f"Watchlist [theme] fetch failed: {e}")
        print(f"  ERROR: {e}")

    # Always save a timestamp so the dashboard can show when data was last attempted
    meta = {
        "timestamp": timestamp.isoformat(),
        "errors": errors,
    }
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(f"{config.DATA_DIR}/last_updated.json", "w") as f:
        json.dump(meta, f)

    if errors:
        print(f"\nCompleted with {len(errors)} error(s). Check messages above.")
    else:
        print("\nAll data fetched successfully.")


if __name__ == "__main__":
    main()
