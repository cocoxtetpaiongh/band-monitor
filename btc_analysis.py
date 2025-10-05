import json, time, statistics, requests
from datetime import datetime, timezone

# -------------------------------------------
# CONFIG
# -------------------------------------------
PAIR = "BTCUSDT"
INTERVAL = "5m"
LIMIT = 120
RETRIES = 3
RETRY_DELAY = 5

BINANCE_URLS = [
    "https://api1.binance.com/api/v3/klines",
    "https://api2.binance.com/api/v3/klines",
    "https://api3.binance.com/api/v3/klines",
    "https://api-gateway.binance.com/api/v3/klines",
    "https://api.binance.com/api/v3/klines"
]

# -------------------------------------------
# HELPERS
# -------------------------------------------
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def fetch_binance():
    params = {"symbol": PAIR, "interval": INTERVAL, "limit": LIMIT}
    for url in BINANCE_URLS:
        for attempt in range(1, RETRIES + 1):
            try:
                print(f"📡 Fetching from {url} (attempt {attempt})")
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, list) and len(data) >= 20:
                    print("✅ Binance data received.")
                    return data, "Binance"
                else:
                    raise ValueError("Invalid Binance response format")
            except Exception as e:
                print(f"⚠️ Error: {e}")
                if attempt < RETRIES:
                    time.sleep(RETRY_DELAY)
    return None, None

def fetch_coingecko_fallback():
    try:
        print("🪙 Falling back to CoinGecko...")
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        cg = requests.get(url, params={"vs_currency": "usd", "days": "1"}, timeout=10).json()
        prices = cg.get("prices", [])[-LIMIT:]
        if not prices:
            return None, None
        klines = [[0, 0, 0, 0, f"{p[1]}", "0"] for p in prices]
        print("✅ Using CoinGecko fallback data.")
        return klines, "CoinGecko"
    except Exception as e:
        print(f"❌ CoinGecko fallback failed: {e}")
        return None, None

def ema(series, period):
    k = 2 / (period + 1)
    e = sum(series[:period]) / period
    for p in series[period:]:
        e = p * k + e * (1 - k)
    return e

# -------------------------------------------
# MAIN COMPUTATION
# -------------------------------------------
def compute(data):
    closes = [float(c[4]) for c in data]
    vols = [float(c[5]) for c in data]

    # Bollinger Bands (20 SMA ± 2σ)
    sma20 = sum(closes[-20:]) / 20
    std20 = statistics.pstdev(closes[-20:])
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20
    safe_upper = upper * 1.005
    safe_lower = lower * 0.995

    # EMA 12 / EMA 26
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    trend = "UP" if ema12 > ema26 else "DOWN"

    # RVOL
    avg_vol20 = (sum(vols[-20:]) / 20) if sum(vols[-20:]) != 0 else 0.0
    rvol = (vols[-1] / avg_vol20) if avg_vol20 else 0.0

    last = closes[-1]
    cross = "ABOVE" if last > safe_upper else "BELOW" if last < safe_lower else "no cross"

    # Frequency of candles near bands (last 12 × 5min = 1h)
    width = upper - lower
    tol = width * 0.15
    recent = closes[-12:]
    freqU = round(sum(1 for c in recent if abs(upper - c) <= tol) / 12 * 100, 1)
    freqL = round(sum(1 for c in recent if abs(c - lower) <= tol) / 12 * 100, 1)

    # Prediction logic
    if cross == "ABOVE" and trend == "UP" and rvol >= 1.5:
        prediction, emoji = "UP (strong)", "🟢"
    elif cross == "BELOW" and trend == "DOWN" and rvol >= 1.5:
        prediction, emoji = "DOWN (strong)", "🔴"
    elif rvol < 0.8:
        prediction, emoji = f"Weak {trend} – Low Volume", "⚪"
    else:
        prediction, emoji = trend, "⚪"

    # Final result dictionary
    return {
        "time": utc_now(),
        "last": round(last, 2),
        "volume": round(vols[-1], 2),
        "rvol": round(rvol, 2),
        "sma20": round(sma20, 2),
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "safe_upper": round(safe_upper, 2),
        "safe_lower": round(safe_lower, 2),
        "ema12": round(ema12, 2),
        "ema26": round(ema26, 2),
        "trend": trend,
        "freq_upper": f"{freqU}%",
        "freq_lower": f"{freqL}%",
        "cross": cross,
        "prediction": prediction,
        "emoji": emoji
    }

# -------------------------------------------
# MAIN SCRIPT
# -------------------------------------------
def write_json(payload):
    with open("btc.json", "w") as f:
        json.dump(payload, f, indent=2)
    print("💾 btc.json written successfully.")

if __name__ == "__main__":
    print("🚀 Running BTC Band Monitor...")
    data, source = fetch_binance()
    if data is None:
        data, source = fetch_coingecko_fallback()

    if not data:
        payload = {
            "time": utc_now(),
            "error": "Failed to fetch market data.",
            "prediction": "no data",
            "emoji": "⚪",
            "source": source or "none"
        }
        write_json(payload)
        print(json.dumps(payload, indent=2))
        raise SystemExit(0)

    result = compute(data)
    result["source"] = source
    result["closes"] = [float(c[4]) for c in data][-20:]  # <-- for chart
    write_json(result)

    # Print summary log for GitHub Actions
    last = result["last"]
    msg = [
        f"{result['emoji']} BTC/USDT 5m — {result['prediction']}",
        f"Last: {last} | Trend: {result['trend']} | RVOL: {result['rvol']}",
        f"Safe Bands: {result['safe_lower']} – {result['safe_upper']}",
        f"Freq (1h): U {result['freq_upper']} · L {result['freq_lower']}",
        f"Source: {result['source']}"
    ]

    if result["cross"] in ("ABOVE", "BELOW"):
        msg.insert(1, f"Cross detected: {result['cross']} SAFE band")
        msg.append("Open ChatGPT for full analysis → "
                   "chat.openai.com/?model=gpt-5&prompt=Fetch+latest+BTC+5-min+Bollinger+analysis")

    print("\n".join(msg))
