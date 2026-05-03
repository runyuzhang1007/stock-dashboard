#!/usr/bin/env python3
"""Stock Analysis Dashboard Generator — tabbed redesign."""

import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import json, requests, io, re
from datetime import datetime

TICKERS = ["SPY", "AAPL", "META", "GOOG", "MSFT", "NVDA", "TSM", "LLY", "AMD", "MU", "TSLA"]
COLORS  = ["#00d4ff","#ff6b6b","#ffd93d","#6bcb77","#ff922b","#a29bfe","#fd79a8","#55efc4","#e17055","#74b9ff","#b2f2bb"]

DARK = dict(paper_bgcolor="#161b22", plot_bgcolor="#0d1117",
            font=dict(color="#c9d1d9", size=12),
            margin=dict(l=50, r=20, t=35, b=40), autosize=True)

def mk(fig, height=380):
    fig.update_layout(**DARK, height=height)
    fig.update_xaxes(gridcolor="#21262d", zerolinecolor="#30363d")
    fig.update_yaxes(gridcolor="#21262d", zerolinecolor="#30363d")
    return fig.to_html(full_html=False, include_plotlyjs=False,
                       config={"responsive": True, "displayModeBar": False})

# ── helpers ─────────────────────────────────────────────────────────────────
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
eps_history = {}
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
    sp_rsi = {}
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
        status = "No data"
    elif above and float(price) >= above:
        status = f"TRIGGERED above ${above}"
    elif below and float(price) <= below:
        status = f"TRIGGERED below ${below}"
    else:
        status = "No trigger"
    alert_rows.append({
        "Ticker": sym, "Current Price ($)": price,
        "Alert Above ($)": above or "—", "Alert Below ($)": below or "—",
        "Status": status,
    })
    print(f"  {sym}: ${price}  → {status}")
alert_df = pd.DataFrame(alert_rows)

# ══════════════════════════════════════════════════════════════════════════════
# 5. RHINOFINANCE YOUTUBE VIDEOS
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Fetching RhinoFinance YouTube videos ──────────────────")
yt_videos = []
try:
    yt_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    yt_r = requests.get("https://www.youtube.com/@RhinoFinance/videos", headers=yt_headers, timeout=45)
    yt_m = re.search(r'var ytInitialData\s*=\s*(\{.+?\});</script>', yt_r.text, re.DOTALL)
    yt_data = json.loads(yt_m.group(1))
    for tab in yt_data["contents"]["twoColumnBrowseResultsRenderer"]["tabs"]:
        tr = tab.get("tabRenderer", {})
        if tr.get("title") == "Videos":
            for item in tr["content"]["richGridRenderer"]["contents"]:
                vr = item.get("richItemRenderer", {}).get("content", {}).get("videoRenderer", {})
                if not vr: continue
                vid_id = vr.get("videoId", "")
                yt_videos.append({
                    "vid_id":    vid_id,
                    "title":     vr.get("title", {}).get("runs", [{}])[0].get("text", ""),
                    "published": vr.get("publishedTimeText", {}).get("simpleText", ""),
                    "views":     vr.get("viewCountText", {}).get("simpleText", "N/A"),
                    "duration":  vr.get("lengthText", {}).get("simpleText", ""),
                    "url":       f"https://www.youtube.com/watch?v={vid_id}",
                })
            break
    print(f"  Fetched {len(yt_videos)} videos")
except Exception as e:
    print(f"  YouTube fetch failed: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# 6. BUILD DASHBOARD — TABBED REDESIGN
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Building tabbed dashboard ─────────────────────────────")

now_str = datetime.now().strftime("%B %d, %Y  %H:%M")

# ── Chart: 1Y Performance ─────────────────────────────────────────────────────
fig_perf = go.Figure()
for i, sym in enumerate(TICKERS):
    h = hist_data[sym]
    fig_perf.add_trace(go.Scatter(
        x=h.index, y=h.values, name=sym,
        line=dict(color=COLORS[i], width=2),
        hovertemplate=f"<b>{sym}</b><br>%{{x|%b %d}}<br>%{{y:.1f}}<extra></extra>"
    ))
fig_perf.update_layout(
    title="1-Year Normalized Price Performance (Base = 100)",
    legend=dict(bgcolor="rgba(22,27,34,0.8)", bordercolor="#30363d", borderwidth=1)
)
ch_perf = mk(fig_perf, height=420)

# ── Chart: RSI ────────────────────────────────────────────────────────────────
rsi_colors = ["#ff6b6b" if v>70 else "#ffd93d" if v<30 else "#74b9ff" for v in df["RSI (14)"]]
fig_rsi = go.Figure()
fig_rsi.add_trace(go.Bar(
    x=df["Ticker"], y=df["RSI (14)"],
    marker_color=rsi_colors,
    text=df["RSI (14)"].astype(str), textposition="outside",
    hovertemplate="<b>%{x}</b><br>RSI: %{y}<extra></extra>",
))
fig_rsi.add_hline(y=70, line_dash="dash", line_color="#ff6b6b", annotation_text="Overbought 70")
fig_rsi.add_hline(y=30, line_dash="dash", line_color="#6bcb77", annotation_text="Oversold 30")
fig_rsi.update_layout(title="RSI (14-day)", showlegend=False)
ch_rsi = mk(fig_rsi)

# ── Chart: Value vs Momentum Scatter ──────────────────────────────────────────
fig_scatter = go.Figure()
fig_scatter.add_trace(go.Scatter(
    x=df["Value Score"], y=df["Momentum Score"],
    mode="markers+text", text=df["Ticker"], textposition="top center",
    marker=dict(size=df["Composite Score"]/3+12,
                color=df["Composite Score"],
                colorscale=[[0,"#ff6b6b"],[0.5,"#ffd93d"],[1,"#6bcb77"]],
                showscale=True,
                colorbar=dict(title="Composite"),
                line=dict(width=1, color="white")),
    hovertemplate="<b>%{text}</b><br>Value: %{x:.1f}<br>Momentum: %{y:.1f}<extra></extra>",
))
fig_scatter.add_vline(x=50, line_dash="dot", line_color="rgba(255,255,255,0.15)")
fig_scatter.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.15)")
fig_scatter.update_layout(title="Value vs Momentum", showlegend=False)
ch_scatter = mk(fig_scatter)

# ── Chart: Multi-timeframe Returns ────────────────────────────────────────────
fig_returns = go.Figure()
for col_, lbl, clr in [("1W Return (%)","1W","#a29bfe"),("1M Return (%)","1M","#6bcb77"),
                        ("3M Return (%)","3M","#ffd93d"),("6M Return (%)","6M","#ff922b")]:
    fig_returns.add_trace(go.Bar(
        name=lbl, x=df["Ticker"], y=pd.to_numeric(df[col_], errors="coerce"),
        marker_color=clr,
        hovertemplate=f"<b>%{{x}}</b><br>{lbl}: %{{y:.1f}}%<extra></extra>",
    ))
fig_returns.update_layout(title="Multi-Timeframe Returns (%)", barmode="group")
ch_returns = mk(fig_returns)

# ── Chart: Volume Ratio ────────────────────────────────────────────────────────
vr = pd.to_numeric(df["Vol Ratio (vs 1M)"], errors="coerce")
vr_colors = ["#ff6b6b" if v>1.5 else "#6bcb77" if v<0.7 else "#74b9ff" for v in vr]
fig_vol = go.Figure()
fig_vol.add_trace(go.Bar(
    x=df["Ticker"], y=vr, marker_color=vr_colors,
    text=(vr.round(2).astype(str)+"x"), textposition="outside",
    hovertemplate="<b>%{x}</b><br>Vol Ratio: %{y:.2f}x<extra></extra>",
))
fig_vol.add_hline(y=1.0, line_dash="dash", line_color="rgba(255,255,255,0.25)", annotation_text="Avg")
fig_vol.update_layout(title="Volume Ratio (Today vs 1M Avg)", showlegend=False)
ch_vol = mk(fig_vol)

# ── Chart: EPS Actual vs Estimate ─────────────────────────────────────────────
fig_eps = go.Figure()
for i, sym in enumerate(TICKERS):
    if sym == "SPY": continue
    edf = eps_history.get(sym, pd.DataFrame())
    if edf.empty: continue
    fig_eps.add_trace(go.Scatter(
        x=edf["Quarter"], y=edf["Actual"],
        name=sym, line=dict(color=COLORS[i], width=2),
        mode="lines+markers", marker=dict(size=6),
        hovertemplate=f"<b>{sym}</b><br>%{{x}}<br>Actual EPS: $%{{y:.2f}}<extra></extra>",
        legendgroup=sym,
    ))
    fig_eps.add_trace(go.Scatter(
        x=edf["Quarter"], y=edf["Estimate"],
        name=sym+" Est", line=dict(color=COLORS[i], width=1, dash="dot"),
        mode="lines", opacity=0.5,
        hovertemplate=f"<b>{sym} Est</b><br>%{{x}}<br>Estimate: $%{{y:.2f}}<extra></extra>",
        legendgroup=sym, showlegend=False,
    ))
fig_eps.update_layout(
    title="Quarterly EPS — Actual vs Estimate",
    legend=dict(bgcolor="rgba(22,27,34,0.8)", bordercolor="#30363d", borderwidth=1)
)
ch_eps = mk(fig_eps, height=380)

# ── Chart: EPS Surprise ────────────────────────────────────────────────────────
surp_tickers, surp_vals, surp_colors = [], [], []
for sym in TICKERS:
    if sym == "SPY": continue
    edf = eps_history.get(sym, pd.DataFrame())
    if edf.empty or edf["Surprise"].isna().all(): continue
    val = float(edf["Surprise"].dropna().iloc[-1])
    surp_tickers.append(sym)
    surp_vals.append(round(val, 2))
    surp_colors.append("#6bcb77" if val >= 0 else "#ff6b6b")
fig_surp = go.Figure()
fig_surp.add_trace(go.Bar(
    x=surp_tickers, y=surp_vals, marker_color=surp_colors,
    text=[f"{v:+.1f}%" for v in surp_vals], textposition="outside",
    hovertemplate="<b>%{x}</b><br>EPS Surprise: %{y:+.2f}%<extra></extra>",
))
fig_surp.add_hline(y=0, line_dash="solid", line_color="rgba(255,255,255,0.3)")
fig_surp.update_layout(title="Latest Quarter EPS Surprise (%)", showlegend=False)
ch_surp = mk(fig_surp)

# ── Chart: S&P 500 Overbought ──────────────────────────────────────────────────
fig_ob = go.Figure()
fig_ob.add_trace(go.Bar(
    x=top_overbought["RSI"], y=top_overbought["Ticker"],
    orientation="h",
    marker=dict(color=top_overbought["RSI"],
                colorscale=[[0,"#ffd93d"],[1,"#ff6b6b"]], showscale=False),
    text=top_overbought["RSI"].astype(str), textposition="outside",
    hovertemplate="<b>%{y}</b><br>RSI: %{x}<extra></extra>",
))
fig_ob.add_vline(x=70, line_dash="dash", line_color="#ff6b6b", annotation_text="Overbought 70")
fig_ob.update_layout(title="Top 10 S&P 500 Overbought (RSI)", showlegend=False)
ch_ob = mk(fig_ob)

# ── Chart: S&P 500 Oversold ────────────────────────────────────────────────────
fig_os = go.Figure()
fig_os.add_trace(go.Bar(
    x=top_oversold["RSI"], y=top_oversold["Ticker"],
    orientation="h",
    marker=dict(color=top_oversold["RSI"],
                colorscale=[[0,"#6bcb77"],[1,"#ffd93d"]], showscale=False),
    text=top_oversold["RSI"].astype(str), textposition="outside",
    hovertemplate="<b>%{y}</b><br>RSI: %{x}<extra></extra>",
))
fig_os.add_vline(x=30, line_dash="dash", line_color="#6bcb77", annotation_text="Oversold 30")
fig_os.update_layout(title="Top 10 S&P 500 Oversold (RSI)", showlegend=False)
ch_os = mk(fig_os)

# ── Summary cards HTML ─────────────────────────────────────────────────────────
SIG_COLOR = {
    "BULLISH": "#6bcb77",
    "BEARISH": "#ff6b6b",
    "CAUTION – Overbought": "#ffd93d",
    "BUY WATCH – Oversold Dip": "#00d4ff",
    "HOLD / NEUTRAL": "#8b949e",
}

rank_rows_html = ""
for _, row in df_sorted.iterrows():
    sig_color = SIG_COLOR.get(row["Signal"], "#8b949e")
    bar_w = int(row["Composite Score"])
    try:
        ret_f = float(row["1D Return (%)"])
    except (ValueError, TypeError):
        ret_f = 0.0
    ret_color = "#6bcb77" if ret_f >= 0 else "#ff6b6b"
    rank_rows_html += (
        f'<tr>'
        f'<td>#{row["Rank"]}</td>'
        f'<td style="color:#c9d1d9;font-weight:600">{row["Ticker"]}</td>'
        f'<td>'
        f'<div style="background:#21262d;border-radius:4px;height:12px;width:100px;overflow:hidden;display:inline-block;vertical-align:middle">'
        f'<div style="background:#6bcb77;height:12px;width:{bar_w}%"></div></div>'
        f' <span style="font-size:11px;color:#8b949e">{row["Composite Score"]}</span>'
        f'</td>'
        f'<td><span style="color:{sig_color};font-size:11px">{row["Signal"]}</span></td>'
        f'<td style="color:#c9d1d9">${row["Price ($)"]}</td>'
        f'<td style="color:{ret_color}">{row["1D Return (%)"]}</td>'
        f'<td style="color:#8b949e">RSI {row["RSI (14)"]}</td>'
        f'</tr>'
    )

alert_rows_html = ""
for _, row in alert_df.iterrows():
    triggered = "TRIGGERED" in str(row["Status"])
    row_bg = 'background:#3d1a1a;' if triggered else ''
    status_color = "#ff6b6b" if "above" in str(row["Status"]) else ("#6bcb77" if "below" in str(row["Status"]) else "#8b949e")
    alert_rows_html += (
        f'<tr style="{row_bg}">'
        f'<td style="color:#c9d1d9;font-weight:600">{row["Ticker"]}</td>'
        f'<td style="color:#c9d1d9">${row["Current Price ($)"]}</td>'
        f'<td style="color:#8b949e">${row["Alert Above ($)"]}</td>'
        f'<td style="color:#8b949e">${row["Alert Below ($)"]}</td>'
        f'<td style="color:{status_color}">{row["Status"]}</td>'
        f'</tr>'
    )

earn_rows_html = ""
for _, row in earn_df.iterrows():
    earn_rows_html += (
        f'<tr>'
        f'<td style="color:#c9d1d9;font-weight:600">{row["Ticker"]}</td>'
        f'<td style="color:#8b949e;font-size:11px">{row["Company"]}</td>'
        f'<td style="color:#ffd93d">{row["Next Earnings"]}</td>'
        f'<td style="color:#c9d1d9">{row["EPS Estimate"]}</td>'
        f'<td style="color:#8b949e">{row["EPS Last (TTM)"]}</td>'
        f'</tr>'
    )

# Ticker topbar
topbar_items = ""
for _, row in df.iterrows():
    try:
        ret_f = float(row["1D Return (%)"])
    except (ValueError, TypeError):
        ret_f = 0.0
    clr = "#6bcb77" if ret_f >= 0 else "#ff6b6b"
    arrow = "▲" if ret_f >= 0 else "▼"
    topbar_items += (
        f'<span class="tick">'
        f'<b style="color:#c9d1d9">{row["Ticker"]}</b>'
        f'<span style="color:#c9d1d9">${row["Price ($)"]}</span>'
        f'<span style="color:{clr}">{arrow} {abs(ret_f):.2f}%</span>'
        f'</span>'
    )

# YouTube cards grid
yt_cards_html = ""
for v in yt_videos[:12]:
    vid_id = v.get("vid_id", "")
    thumb = f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg" if vid_id else ""
    safe_title = v["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    yt_cards_html += (
        f'<a class="yt-card" href="{v["url"]}" target="_blank" rel="noopener">'
        f'<img src="{thumb}" alt="{safe_title}" loading="lazy">'
        f'<div class="yt-info">'
        f'<div class="yt-title">{safe_title}</div>'
        f'<div class="yt-meta">{v["published"]} &nbsp;·&nbsp; {v["views"]} &nbsp;·&nbsp; {v["duration"]}</div>'
        f'</div>'
        f'</a>'
    )
if not yt_cards_html:
    yt_cards_html = '<p style="color:#8b949e;padding:20px">YouTube data unavailable — will retry next refresh.</p>'

# EPS/Earnings metrics table
eps_cols = ["EPS (TTM)", "EPS Forward", "EPS Growth YoY (%)", "PEG Ratio", "P/E Ratio", "Profit Margin (%)"]
earn_rich = earn_df.merge(df[["Ticker"] + eps_cols], on="Ticker", how="left")
eps_th = "".join(f"<th>{c}</th>" for c in earn_rich.columns)
eps_rows_html = ""
for _, row in earn_rich.iterrows():
    eps_rows_html += "<tr>" + "".join(f"<td>{row[c]}</td>" for c in earn_rich.columns) + "</tr>"

# ── Final HTML ─────────────────────────────────────────────────────────────────
HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace;font-size:13px}}
#topbar{{position:sticky;top:0;z-index:100;background:#161b22;border-bottom:1px solid #30363d;
  padding:5px 12px;display:flex;align-items:center;overflow-x:auto;white-space:nowrap;gap:0}}
.tick{{display:inline-flex;flex-direction:column;align-items:center;min-width:72px;padding:2px 8px;
  border-right:1px solid #21262d;font-size:11px;line-height:1.4}}
#tabnav{{background:#161b22;border-bottom:1px solid #30363d;padding:0 12px;
  display:flex;overflow-x:auto;white-space:nowrap}}
.tc{{padding:10px 18px;cursor:pointer;color:#8b949e;border:none;background:none;
  border-bottom:2px solid transparent;font-size:13px;font-weight:500;transition:color .15s}}
.tc:hover{{color:#c9d1d9}}
.tc.active{{color:#58a6ff;border-bottom-color:#58a6ff}}
.tab{{display:none;padding:14px 12px 50px}}
.tab.active{{display:block}}
.cbox{{background:#161b22;border:1px solid #21262d;border-radius:8px;margin-bottom:14px;
  padding:4px;overflow:hidden}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;margin-bottom:14px}}
.card h3{{font-size:11px;color:#8b949e;margin-bottom:10px;text-transform:uppercase;letter-spacing:.06em}}
table.dt{{width:100%;border-collapse:collapse}}
table.dt th{{background:#21262d;color:#8b949e;text-align:left;padding:6px 8px;
  font-size:11px;text-transform:uppercase;letter-spacing:.04em;white-space:nowrap}}
table.dt td{{padding:6px 8px;border-bottom:1px solid #21262d;font-size:12px;color:#c9d1d9}}
table.dt tr:hover td{{background:#21262d40}}
#rbar{{position:fixed;bottom:0;left:0;right:0;background:#161b22;border-top:1px solid #30363d;
  padding:5px 16px;font-size:11px;color:#8b949e;display:flex;justify-content:space-between;
  align-items:center;z-index:200}}
#rbar a{{color:#58a6ff;cursor:pointer;margin-left:12px;text-decoration:none}}
#countdown{{color:#ffd93d;font-weight:bold}}
.yt-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.yt-card{{background:#0d1117;border:1px solid #21262d;border-radius:8px;overflow:hidden;
  text-decoration:none;color:#c9d1d9;display:flex;flex-direction:column;
  transition:border-color .15s,transform .15s}}
.yt-card:hover{{border-color:#58a6ff;transform:translateY(-2px)}}
.yt-card img{{width:100%;aspect-ratio:16/9;object-fit:cover;background:#21262d;display:block}}
.yt-info{{padding:10px 10px 12px}}
.yt-title{{font-size:12px;font-weight:600;color:#c9d1d9;line-height:1.4;margin-bottom:5px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.yt-meta{{font-size:11px;color:#8b949e}}
@media(max-width:700px){{
  .g2{{grid-template-columns:1fr}}
  .yt-grid{{grid-template-columns:1fr 1fr}}
}}
@media(max-width:480px){{
  .yt-grid{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>

<div id="topbar">
  <span style="color:#58a6ff;font-size:12px;margin-right:10px;flex-shrink:0">📊</span>
  {topbar_items}
  <span style="margin-left:auto;padding-left:12px;color:#8b949e;font-size:11px;flex-shrink:0">{now_str}</span>
</div>

<div id="tabnav">
  <button class="tc active" onclick="showTab(this,'overview')">Overview</button>
  <button class="tc" onclick="showTab(this,'technical')">Technical</button>
  <button class="tc" onclick="showTab(this,'fundamentals')">Fundamentals</button>
  <button class="tc" onclick="showTab(this,'sp500')">S&amp;P 500</button>
  <button class="tc" onclick="showTab(this,'rhino')">RhinoFinance</button>
</div>

<!-- ══ OVERVIEW ══ -->
<div class="tab active" id="overview">
  <div class="g2">
    <div class="card">
      <h3>Rankings &amp; Signals</h3>
      <div style="overflow-x:auto">
        <table class="dt">
          <thead><tr><th>#</th><th>Ticker</th><th>Score</th><th>Signal</th><th>Price</th><th>1D%</th><th>RSI</th></tr></thead>
          <tbody>{rank_rows_html}</tbody>
        </table>
      </div>
    </div>
    <div>
      <div class="card">
        <h3>Price Alerts</h3>
        <div style="overflow-x:auto">
          <table class="dt">
            <thead><tr><th>Ticker</th><th>Price</th><th>Above</th><th>Below</th><th>Status</th></tr></thead>
            <tbody>{alert_rows_html}</tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <h3>Upcoming Earnings</h3>
        <div style="overflow-x:auto">
          <table class="dt">
            <thead><tr><th>Ticker</th><th>Company</th><th>Next Date</th><th>EPS Est</th><th>EPS Last</th></tr></thead>
            <tbody>{earn_rows_html}</tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
  <div class="cbox">{ch_perf}</div>
</div>

<!-- ══ TECHNICAL ══ -->
<div class="tab" id="technical">
  <div class="g2">
    <div class="cbox">{ch_rsi}</div>
    <div class="cbox">{ch_scatter}</div>
  </div>
  <div class="g2">
    <div class="cbox">{ch_returns}</div>
    <div class="cbox">{ch_vol}</div>
  </div>
</div>

<!-- ══ FUNDAMENTALS ══ -->
<div class="tab" id="fundamentals">
  <div class="g2">
    <div class="cbox">{ch_eps}</div>
    <div class="cbox">{ch_surp}</div>
  </div>
  <div class="card">
    <h3>Earnings &amp; EPS Metrics</h3>
    <div style="overflow-x:auto">
      <table class="dt">
        <thead><tr>{eps_th}</tr></thead>
        <tbody>{eps_rows_html}</tbody>
      </table>
    </div>
  </div>
</div>

<!-- ══ S&P 500 ══ -->
<div class="tab" id="sp500">
  <div class="g2">
    <div class="cbox">{ch_ob}</div>
    <div class="cbox">{ch_os}</div>
  </div>
</div>

<!-- ══ RHINOFINANCE ══ -->
<div class="tab" id="rhino">
  <div class="card">
    <h3>事业环球财经 · RhinoFinance — Latest Videos</h3>
    <div class="yt-grid">{yt_cards_html}</div>
  </div>
</div>

<div id="rbar">
  <span>Last updated: <b style="color:#c9d1d9">{now_str}</b></span>
  <span>
    Auto-refresh in <span id="countdown">300</span>s
    <a onclick="location.reload()">🔄 Refresh Now</a>
  </span>
</div>

<script>
function showTab(btn, name) {{
  document.querySelectorAll('.tc').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById(name).classList.add('active');
  btn.classList.add('active');
  setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
}}
var secs = 300;
setInterval(function() {{
  secs--;
  document.getElementById('countdown').textContent = secs;
  if (secs <= 0) location.reload();
}}, 1000);
</script>
</body>
</html>"""

with open("stock_dashboard.html", "w") as f:
    f.write(HTML)

print("\n✅  stock_dashboard.html saved (tabbed redesign)")
print(f"   Tickers scanned:   {len(df)}")
print(f"   S&P 500 scanned:   {len(sp_rsi)}")
print(f"   Alerts checked:    {len(alert_df)}")
print(f"   Earnings fetched:  {len(earn_df)}")
print(f"   EPS history:       {sum(1 for v in eps_history.values() if not v.empty)} tickers")
print(f"   YouTube videos:    {len(yt_videos)}")
