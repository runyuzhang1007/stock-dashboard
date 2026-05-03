#!/usr/bin/env python3
"""Stock Analysis Dashboard Generator — run manually or via cron."""

import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json, sys, requests, io
from datetime import datetime

TICKERS = ["SPY", "AAPL", "META", "GOOG", "MSFT", "NVDA", "TSM", "LLY", "AMD", "MU", "TSLA"]
COLORS  = ["#00d4ff","#ff6b6b","#ffd93d","#6bcb77","#ff922b","#a29bfe","#fd79a8","#55efc4","#e17055","#74b9ff","#b2f2bb"]

# ── helpers ────────────────────────────────────────────────────────────────────
def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))

def pct_return(hist, days):
    if len(hist) < days + 1: return None
    return round((hist["Close"].iloc[-1] / hist["Close"].iloc[-days] - 1) * 100, 2)

def avg_vol(hist, days):
    return round(hist["Volume"].iloc[-days:].mean() / 1e6, 2)

def fmt(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "N/A"
    return round(v, d)

def bil(v): return round(v / 1e9, 2) if v else "N/A"

def norm(series, invert=False):
    s = pd.to_numeric(series, errors="coerce")
    mn, mx = s.min(), s.max()
    if mx == mn: return pd.Series([50.0] * len(s), index=s.index)
    n = (s - mn) / (mx - mn) * 100
    return (100 - n) if invert else n

# ══════════════════════════════════════════════════════════════════════════════
# 1. MAIN TICKERS — fetch data
# ══════════════════════════════════════════════════════════════════════════════
print("── Fetching main tickers ─────────────────────────────────")
rows, hist_data = [], {}
for sym in TICKERS:
    print(f"  {sym}...", end=" ", flush=True)
    t    = yf.Ticker(sym)
    info = t.info
    hist = t.history(period="2y")
    c    = hist["Close"]

    sma20  = round(c.rolling(20).mean().iloc[-1], 2)
    sma50  = round(c.rolling(50).mean().iloc[-1], 2)
    sma200 = round(c.rolling(200).mean().iloc[-1], 2)
    price  = round(c.iloc[-1], 2)
    vs50   = round((price / sma50  - 1) * 100, 2)
    vs200  = round((price / sma200 - 1) * 100, 2)
    ma_sig = "Golden Cross" if sma50 > sma200 else "Death Cross"
    rsi14  = round(calc_rsi(c, 14).iloc[-1], 1)

    r1d  = pct_return(hist, 1);  r1w  = pct_return(hist, 5)
    r1m  = pct_return(hist, 21); r3m  = pct_return(hist, 63)
    r6m  = pct_return(hist, 126);r1y  = pct_return(hist, 252)

    pe     = info.get("trailingPE")
    margin = (info.get("profitMargins") or 0) * 100
    hi52   = info.get("fiftyTwoWeekHigh")
    lo52   = info.get("fiftyTwoWeekLow")
    pct_hi = round((price / hi52 - 1) * 100, 1) if hi52 else None

    rows.append({
        "Ticker": sym, "Company": info.get("shortName","N/A"),
        "Sector": info.get("sector","N/A"), "Price ($)": price,
        "52W High ($)": fmt(hi52), "52W Low ($)": fmt(lo52),
        "% From 52W High": fmt(pct_hi),
        "1D Return (%)": fmt(r1d), "1W Return (%)": fmt(r1w),
        "1M Return (%)": fmt(r1m), "3M Return (%)": fmt(r3m),
        "6M Return (%)": fmt(r6m), "1Y Return (%)": fmt(r1y),
        "SMA 20": sma20, "SMA 50": sma50, "SMA 200": sma200,
        "vs SMA50 (%)": vs50, "vs SMA200 (%)": vs200, "MA Signal": ma_sig,
        "RSI (14)": rsi14,
        "RSI Signal": "Overbought" if rsi14>70 else ("Oversold" if rsi14<30 else "Neutral"),
        "Vol Today (M)":  round(hist["Volume"].iloc[-1]/1e6, 2),
        "Vol Avg 1W (M)": avg_vol(hist,5),  "Vol Avg 1M (M)": avg_vol(hist,21),
        "Vol Avg 3M (M)": avg_vol(hist,63),
        "Vol Ratio (vs 1M)": round(hist["Volume"].iloc[-1]/hist["Volume"].iloc[-21:].mean(), 2),
        "Market Cap ($B)": bil(info.get("marketCap")),
        "P/E Ratio": fmt(pe), "EPS (TTM)": fmt(info.get("trailingEps")),
        "EPS Forward": fmt(info.get("forwardEps")),
        "EPS Growth YoY (%)": fmt((info.get("earningsGrowth") or 0) * 100),
        "Revenue Growth YoY (%)": fmt((info.get("revenueGrowth") or 0) * 100),
        "PEG Ratio": fmt(info.get("pegRatio")),
        "Revenue ($B)": bil(info.get("totalRevenue")),
        "Profit Margin (%)": fmt(margin),
        "Dividend Yield (%)": round((info.get("dividendYield") or 0)*100, 2),
        "Beta": fmt(info.get("beta")),
    })
    hist_1y = t.history(period="1y")["Close"]
    hist_data[sym] = (hist_1y / hist_1y.iloc[0] * 100).round(2)
    print("ok")

df = pd.DataFrame(rows)

# scores
pe_s  = norm(df["P/E Ratio"],        invert=True)
mg_s  = norm(df["Profit Margin (%)"])
hi_s  = norm(df["% From 52W High"],  invert=True)
df["Value Score"]    = (pe_s*0.4 + mg_s*0.4 + hi_s*0.2).round(1)
df["Momentum Score"] = (norm(df["1M Return (%)"])*0.25 + norm(df["3M Return (%)"])*0.35 +
                        norm(df["6M Return (%)"])*0.25 + norm(df["1Y Return (%)"])*0.15).round(1)
df["Composite Score"]= (df["Value Score"]*0.4 + df["Momentum Score"]*0.6).round(1)
df["Rank"]           = df["Composite Score"].rank(ascending=False).astype(int)

def signal(r):
    rsi_ = pd.to_numeric(r["RSI (14)"], errors="coerce")
    comp = pd.to_numeric(r["Composite Score"], errors="coerce")
    vs2  = pd.to_numeric(r["vs SMA200 (%)"], errors="coerce")
    if rsi_ > 70: return "CAUTION – Overbought"
    if rsi_ < 35 and comp > 50: return "BUY WATCH – Oversold Dip"
    if r["MA Signal"] == "Golden Cross" and vs2 > 0 and comp > 60: return "BULLISH"
    if r["MA Signal"] == "Death Cross": return "BEARISH"
    return "HOLD / NEUTRAL"
df["Signal"] = df.apply(signal, axis=1)
df_sorted = df.sort_values("Rank")
df.to_csv("stock_analysis.csv", index=False)

# ══════════════════════════════════════════════════════════════════════════════
# 1b. QUARTERLY EPS HISTORY
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Fetching quarterly EPS history ────────────────────────")
eps_history = {}   # sym -> DataFrame(date, estimate, actual, surprise_pct)
for sym in TICKERS:
    try:
        t = yf.Ticker(sym)
        ed = t.get_earnings_dates(limit=8)
        if ed is None or ed.empty:
            raise ValueError("no data")
        ed = ed.dropna(subset=["Reported EPS"]).copy()
        ed.index = pd.to_datetime(ed.index).tz_localize(None)
        ed = ed.sort_index()
        ed["Quarter"] = ed.index.to_period("Q").astype(str)
        ed["Estimate"] = pd.to_numeric(ed["EPS Estimate"], errors="coerce")
        ed["Actual"]   = pd.to_numeric(ed["Reported EPS"], errors="coerce")
        ed["Surprise"] = pd.to_numeric(ed.get("Surprise(%)", pd.Series(dtype=float)), errors="coerce")
        eps_history[sym] = ed[["Quarter","Estimate","Actual","Surprise"]].tail(6)
        latest = ed.iloc[-1]
        print(f"  {sym}: last Q={latest['Quarter']}  actual={latest['Actual']}  "
              f"surprise={latest['Surprise']}%")
    except Exception as e:
        print(f"  {sym}: {e}")
        eps_history[sym] = pd.DataFrame(columns=["Quarter","Estimate","Actual","Surprise"])

# ══════════════════════════════════════════════════════════════════════════════
# 2. S&P 500 OVERBOUGHT / OVERSOLD SCAN
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Scanning S&P 500 RSI ──────────────────────────────────")
try:
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    resp = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=headers, timeout=15)
    sp500_df = pd.read_html(io.StringIO(resp.text))[0]
    sp_tickers = sp500_df["Symbol"].str.replace(".", "-", regex=False).tolist()
    print(f"  Downloading {len(sp_tickers)} tickers (batch)...")
    sp_prices = yf.download(sp_tickers, period="1mo", auto_adjust=True,
                            progress=False, threads=True)["Close"]
    sp_rsi = {}
    for sym in sp_prices.columns:
        s = sp_prices[sym].dropna()
        if len(s) >= 15:
            r = calc_rsi(s, 14)
            if not r.empty and not np.isnan(r.iloc[-1]):
                sp_rsi[sym] = round(float(r.iloc[-1]), 1)
    rsi_series   = pd.Series(sp_rsi).dropna()
    top_overbought = rsi_series.nlargest(10).reset_index()
    top_overbought.columns = ["Ticker", "RSI"]
    top_oversold   = rsi_series.nsmallest(10).reset_index()
    top_oversold.columns = ["Ticker", "RSI"]
    print(f"  Scanned {len(sp_rsi)} stocks — found "
          f"{(rsi_series>70).sum()} overbought, {(rsi_series<30).sum()} oversold")
except Exception as e:
    print(f"  S&P 500 scan failed: {e}")
    top_overbought = pd.DataFrame({"Ticker": ["N/A"]*10, "RSI": [0]*10})
    top_oversold   = pd.DataFrame({"Ticker": ["N/A"]*10, "RSI": [0]*10})

# ══════════════════════════════════════════════════════════════════════════════
# 3. EARNINGS CALENDAR
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Fetching earnings calendars ───────────────────────────")
earnings_rows = []
for sym in TICKERS:
    try:
        t    = yf.Ticker(sym)
        info = t.info
        # upcoming earnings date
        ed = info.get("earningsTimestamp") or info.get("earningsDate")
        if isinstance(ed, (int, float)):
            ed = datetime.fromtimestamp(ed).strftime("%Y-%m-%d")
        elif isinstance(ed, list) and ed:
            ed = datetime.fromtimestamp(ed[0]).strftime("%Y-%m-%d")
        elif ed is None:
            ed = "N/A"

        eps_est  = info.get("earningsEstimate") or info.get("epsForward") or "N/A"
        rev_est  = bil(info.get("revenueEstimate")) if info.get("revenueEstimate") else "N/A"
        eps_last = fmt(info.get("trailingEps"))

        earnings_rows.append({
            "Ticker": sym,
            "Company": info.get("shortName","N/A"),
            "Next Earnings": ed,
            "EPS Estimate": fmt(eps_est) if eps_est != "N/A" else "N/A",
            "EPS Last (TTM)": eps_last,
            "Rev Estimate ($B)": rev_est,
        })
        print(f"  {sym}: {ed}")
    except Exception as e:
        print(f"  {sym}: error – {e}")
        earnings_rows.append({"Ticker": sym, "Company": "N/A",
                               "Next Earnings": "N/A", "EPS Estimate": "N/A",
                               "EPS Last (TTM)": "N/A", "Rev Estimate ($B)": "N/A"})
earn_df = pd.DataFrame(earnings_rows)

# ══════════════════════════════════════════════════════════════════════════════
# 4. PRICE ALERTS
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Checking price alerts ─────────────────────────────────")
with open("alerts.json") as f:
    alert_cfg = json.load(f)

alert_rows = []
prices_now = dict(zip(df["Ticker"], df["Price ($)"]))
for sym, levels in alert_cfg.items():
    price = prices_now.get(sym, "N/A")
    above = levels.get("above")
    below = levels.get("below")
    if price == "N/A":
        status = "❓ No data"
    elif above and float(price) >= above:
        status = f"🔴 TRIGGERED — above ${above}"
    elif below and float(price) <= below:
        status = f"🟢 TRIGGERED — below ${below}"
    else:
        status = "✅ No trigger"
    alert_rows.append({
        "Ticker": sym, "Current Price ($)": price,
        "Alert Above ($)": above or "—", "Alert Below ($)": below or "—",
        "Status": status,
    })
    print(f"  {sym}: ${price}  → {status}")
alert_df = pd.DataFrame(alert_rows)

# ══════════════════════════════════════════════════════════════════════════════
# 5. BUILD DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Building dashboard ────────────────────────────────────")

fig = make_subplots(
    rows=6, cols=2,
    subplot_titles=(
        "📈 1-Year Normalized Price Performance (Base = 100)",
        "🏆 Composite Score Ranking",
        "⚡ RSI (14-day) — Your Watchlist",
        "🔵 Value vs Momentum Scatter",
        "📊 Multi-Timeframe Returns (%)",
        "🔊 Volume Ratio Today vs 1-Month Avg",
        "🔥 Top 10 S&P 500 Overbought (RSI)",
        "💎 Top 10 S&P 500 Oversold (RSI)",
        "📉 Quarterly EPS — Actual vs Estimate",
        "🎯 Latest Quarter EPS Surprise (%)",
        "📅 Earnings Calendar",
        "🚨 Price Alerts",
    ),
    specs=[
        [{"type": "xy"},    {"type": "xy"}],
        [{"type": "xy"},    {"type": "xy"}],
        [{"type": "xy"},    {"type": "xy"}],
        [{"type": "xy"},    {"type": "xy"}],
        [{"type": "xy"},    {"type": "xy"}],
        [{"type": "table"}, {"type": "table"}],
    ],
    vertical_spacing=0.08,
    horizontal_spacing=0.08,
    row_heights=[0.22, 0.17, 0.15, 0.15, 0.17, 0.14],
)

# ── Row 1 Left: 1Y performance ─────────────────────────────────────────────
for i, sym in enumerate(TICKERS):
    h = hist_data[sym]
    fig.add_trace(go.Scatter(
        x=h.index, y=h.values, name=sym,
        line=dict(color=COLORS[i], width=2),
        hovertemplate=f"<b>{sym}</b><br>%{{x|%b %d}}<br>%{{y:.1f}}<extra></extra>"
    ), row=1, col=1)

# ── Row 1 Right: Composite score bar ──────────────────────────────────────
fig.add_trace(go.Bar(
    x=df_sorted["Composite Score"], y=df_sorted["Ticker"],
    orientation="h",
    marker=dict(color=df_sorted["Composite Score"],
                colorscale=[[0,"#ff6b6b"],[0.5,"#ffd93d"],[1,"#6bcb77"]],
                showscale=False),
    text=[f"{v}  #{r}" for v,r in zip(df_sorted["Composite Score"],df_sorted["Rank"])],
    textposition="outside",
    hovertemplate="<b>%{y}</b><br>Score: %{x}<extra></extra>",
    showlegend=False,
), row=1, col=2)

# ── Row 2 Left: RSI bar ────────────────────────────────────────────────────
rsi_colors = ["#ff6b6b" if v>70 else "#ffd93d" if v<30 else "#74b9ff" for v in df["RSI (14)"]]
fig.add_trace(go.Bar(
    x=df["Ticker"], y=df["RSI (14)"],
    marker_color=rsi_colors,
    text=df["RSI (14)"].astype(str), textposition="outside",
    hovertemplate="<b>%{x}</b><br>RSI: %{y}<extra></extra>",
    showlegend=False,
), row=2, col=1)
for lvl, lbl, clr in [(70,"Overbought","#ff6b6b"),(30,"Oversold","#6bcb77")]:
    fig.add_hline(y=lvl, line_dash="dash", line_color=clr,
                  annotation_text=lbl, annotation_position="right", row=2, col=1)

# ── Row 2 Right: Value vs Momentum scatter ─────────────────────────────────
fig.add_trace(go.Scatter(
    x=df["Value Score"], y=df["Momentum Score"],
    mode="markers+text", text=df["Ticker"], textposition="top center",
    marker=dict(size=df["Composite Score"]/3+12,
                color=df["Composite Score"],
                colorscale=[[0,"#ff6b6b"],[0.5,"#ffd93d"],[1,"#6bcb77"]],
                showscale=True,
                colorbar=dict(title="Composite", x=1.02, len=0.2, y=0.58),
                line=dict(width=1, color="white")),
    hovertemplate="<b>%{text}</b><br>Value: %{x:.1f}<br>Momentum: %{y:.1f}<extra></extra>",
    showlegend=False,
), row=2, col=2)
fig.add_vline(x=50, line_dash="dot", line_color="rgba(255,255,255,0.15)", row=2, col=2)
fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.15)", row=2, col=2)

# ── Row 3 Left: Multi-timeframe returns ────────────────────────────────────
for col_, lbl, clr in [("1W Return (%)","1W","#a29bfe"),("1M Return (%)","1M","#6bcb77"),
                        ("3M Return (%)","3M","#ffd93d"),("6M Return (%)","6M","#ff922b")]:
    fig.add_trace(go.Bar(
        name=lbl, x=df["Ticker"], y=pd.to_numeric(df[col_], errors="coerce"),
        marker_color=clr,
        hovertemplate=f"<b>%{{x}}</b><br>{lbl}: %{{y:.1f}}%<extra></extra>",
    ), row=3, col=1)

# ── Row 3 Right: Volume ratio ──────────────────────────────────────────────
vr = pd.to_numeric(df["Vol Ratio (vs 1M)"], errors="coerce")
vr_colors = ["#ff6b6b" if v>1.5 else "#6bcb77" if v<0.7 else "#74b9ff" for v in vr]
fig.add_trace(go.Bar(
    x=df["Ticker"], y=vr, marker_color=vr_colors,
    text=(vr.round(2).astype(str)+"x"), textposition="outside",
    hovertemplate="<b>%{x}</b><br>Vol Ratio: %{y:.2f}x<extra></extra>",
    showlegend=False,
), row=3, col=2)
fig.add_hline(y=1.0, line_dash="dash", line_color="rgba(255,255,255,0.25)",
              annotation_text="Avg", row=3, col=2)

# ── Row 4 Left: Top 10 Overbought S&P 500 ─────────────────────────────────
fig.add_trace(go.Bar(
    x=top_overbought["RSI"], y=top_overbought["Ticker"],
    orientation="h",
    marker=dict(color=top_overbought["RSI"],
                colorscale=[[0,"#ffd93d"],[1,"#ff6b6b"]], showscale=False),
    text=top_overbought["RSI"].astype(str), textposition="outside",
    hovertemplate="<b>%{y}</b><br>RSI: %{x}<extra></extra>",
    showlegend=False,
), row=4, col=1)
fig.add_vline(x=70, line_dash="dash", line_color="#ff6b6b",
              annotation_text="Overbought 70", row=4, col=1)

# ── Row 4 Right: Top 10 Oversold S&P 500 ──────────────────────────────────
fig.add_trace(go.Bar(
    x=top_oversold["RSI"], y=top_oversold["Ticker"],
    orientation="h",
    marker=dict(color=top_oversold["RSI"],
                colorscale=[[0,"#6bcb77"],[1,"#ffd93d"]], showscale=False),
    text=top_oversold["RSI"].astype(str), textposition="outside",
    hovertemplate="<b>%{y}</b><br>RSI: %{x}<extra></extra>",
    showlegend=False,
), row=4, col=2)
fig.add_vline(x=30, line_dash="dash", line_color="#6bcb77",
              annotation_text="Oversold 30", row=4, col=2)

# ── Row 5 Left: Quarterly EPS Actual vs Estimate lines ────────────────────
for i, sym in enumerate(TICKERS):
    if sym == "SPY": continue
    edf = eps_history.get(sym, pd.DataFrame())
    if edf.empty: continue
    fig.add_trace(go.Scatter(
        x=edf["Quarter"], y=edf["Actual"],
        name=sym, line=dict(color=COLORS[i], width=2),
        mode="lines+markers", marker=dict(size=6),
        hovertemplate=f"<b>{sym}</b><br>%{{x}}<br>Actual EPS: $%{{y:.2f}}<extra></extra>",
        legendgroup=sym, showlegend=False,
    ), row=5, col=1)
    fig.add_trace(go.Scatter(
        x=edf["Quarter"], y=edf["Estimate"],
        name=sym+" Est", line=dict(color=COLORS[i], width=1, dash="dot"),
        mode="lines", opacity=0.5,
        hovertemplate=f"<b>{sym} Est</b><br>%{{x}}<br>Estimate: $%{{y:.2f}}<extra></extra>",
        legendgroup=sym, showlegend=False,
    ), row=5, col=1)

# ── Row 5 Right: Latest quarter EPS surprise % ────────────────────────────
surp_tickers, surp_vals, surp_colors = [], [], []
for sym in TICKERS:
    if sym == "SPY": continue
    edf = eps_history.get(sym, pd.DataFrame())
    if edf.empty or edf["Surprise"].isna().all(): continue
    val = float(edf["Surprise"].dropna().iloc[-1])
    surp_tickers.append(sym)
    surp_vals.append(round(val, 2))
    surp_colors.append("#6bcb77" if val >= 0 else "#ff6b6b")

fig.add_trace(go.Bar(
    x=surp_tickers, y=surp_vals,
    marker_color=surp_colors,
    text=[f"{v:+.1f}%" for v in surp_vals], textposition="outside",
    hovertemplate="<b>%{x}</b><br>EPS Surprise: %{y:+.2f}%<extra></extra>",
    showlegend=False,
), row=5, col=2)
fig.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.3)", row=5, col=2)

# ── Row 6 Left: Earnings calendar table ───────────────────────────────────
# Enrich earnings table with EPS columns from df
eps_cols = ["EPS (TTM)", "EPS Forward", "EPS Growth YoY (%)", "PEG Ratio"]
earn_rich = earn_df.merge(df[["Ticker"] + eps_cols], on="Ticker", how="left")

fig.add_trace(go.Table(
    header=dict(
        values=["<b>"+c+"</b>" for c in earn_rich.columns],
        fill_color="#21262d", font=dict(color="#c9d1d9", size=11),
        line_color="#30363d", align="left",
    ),
    cells=dict(
        values=[earn_rich[c] for c in earn_rich.columns],
        fill_color=[["#161b22" if i%2==0 else "#0d1117" for i in range(len(earn_rich))]],
        font=dict(color="#c9d1d9", size=11),
        line_color="#30363d", align="left",
    ),
), row=6, col=1)

# ── Row 6 Right: Alerts table ──────────────────────────────────────────────
fig.add_trace(go.Table(
    header=dict(
        values=["<b>"+c+"</b>" for c in alert_df.columns],
        fill_color="#21262d", font=dict(color="#c9d1d9", size=11),
        line_color="#30363d", align="left",
    ),
    cells=dict(
        values=[alert_df[c] for c in alert_df.columns],
        fill_color=[["#161b22"]*len(alert_df)]*4 +
                   [[("#3d1a1a" if "TRIGGERED" in str(s) else "#161b22") for s in alert_df["Status"]]],
        font=dict(color="#c9d1d9", size=11),
        line_color="#30363d", align="left",
    ),
), row=6, col=2)

# ── Global layout ──────────────────────────────────────────────────────────
now_str = datetime.now().strftime("%B %d, %Y  %H:%M")
fig.update_layout(
    title=dict(
        text=f"Stock Analysis Dashboard  ·  {now_str}",
        font=dict(size=20, color="white"), x=0.5,
    ),
    paper_bgcolor="#0d1117",
    plot_bgcolor="#161b22",
    font=dict(color="#c9d1d9", size=12),
    height=2100,
    barmode="group",
    legend=dict(bgcolor="rgba(22,27,34,0.8)", bordercolor="#30363d", borderwidth=1,
                x=0.01, y=0.99, font=dict(size=10)),
    margin=dict(l=60, r=80, t=100, b=60),
)
fig.update_xaxes(gridcolor="#21262d", zerolinecolor="#30363d")
fig.update_yaxes(gridcolor="#21262d", zerolinecolor="#30363d")

# ── Auto-refresh JS injection ──────────────────────────────────────────────
AUTO_REFRESH_JS = """
<style>
  #refresh-bar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
    background: #161b22; border-bottom: 1px solid #30363d;
    display: flex; align-items: center; justify-content: space-between;
    padding: 6px 20px; font-family: monospace; font-size: 13px; color: #8b949e;
  }
  #refresh-bar a { color:#58a6ff; cursor:pointer; text-decoration:none; margin-left:16px; }
  #countdown { color:#ffd93d; font-weight:bold; }
</style>
<div id="refresh-bar">
  <span>📊 Stock Dashboard &nbsp;·&nbsp; Last updated: <b style="color:#c9d1d9">""" + now_str + """</b></span>
  <span>
    Auto-refresh in <span id="countdown">300</span>s
    <a onclick="location.reload()">🔄 Refresh Now</a>
    <a href="alerts.json" target="_blank">⚙️ Edit Alerts</a>
  </span>
</div>
<script>
  var secs = 300;
  setInterval(function() {
    secs--;
    document.getElementById('countdown').textContent = secs;
    if (secs <= 0) location.reload();
  }, 1000);
</script>
"""

html_out = fig.to_html(include_plotlyjs="cdn", full_html=True)
html_out = html_out.replace("<body>", "<body>" + AUTO_REFRESH_JS)
with open("stock_dashboard.html", "w") as f:
    f.write(html_out)

print("\n✅  stock_dashboard.html saved")
print(f"   Tickers scanned:   {len(df)}")
print(f"   S&P 500 scanned:   {len(sp_rsi) if 'sp_rsi' in dir() else 'N/A'}")
print(f"   Alerts checked:    {len(alert_df)}")
print(f"   Earnings fetched:  {len(earn_df)}")
print(f"   EPS history:       {sum(1 for v in eps_history.values() if not v.empty)} tickers")
