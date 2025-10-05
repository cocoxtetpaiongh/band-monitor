import requests, statistics, json, time
from datetime import datetime

# -----------------------------------------------
# CONFIGURATION
# -----------------------------------------------
PAIR = "BTCUSDT"
INTERVAL = "5m"
LIMIT = 120
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# -----------------------------------------------
# FETCH DATA
# -----------------------------------------------
def get_btc_data():
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": PAIR, "interval": INTERVAL, "limit": LIMIT}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"📡 Fetching Binance data (attempt {attempt})...")
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and len(data) >= 20:
                print(f"✅ Received {len(data)} candles.")
                return data
            else:
                raise ValueError("Unexpected response format.")
        except Exception as e:
            print(f"⚠️ Error fetching data: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
    print("❌ Failed to fetch data after retries.")
    return []

# -----------------------------------------------
# COMPUTE INDICATORS
# -----------------------------------------------
def compute(data):
    closes = [float(c[4]) for c in data]
    vols   = [float(c[5]) for c in data]

    # --- Bollinger Bands (20 SMA ± 2 std)
    sma = sum(closes[-20:]) / 20
    std = statistics.pstdev(closes[-20:])
    upper, lower = sma + 2 * std, sma - 2 * std
    safeU, safeL = upper * 1.005, lower * 0.995

    # --- EMAs
    def ema(period):
        k = 2 / (period + 1)
        e = sum(closes[:period]) / period
        for p in closes[period:]:
            e = p * k + e * (1 - k)
        return e

    ema12, ema26 = ema(12), ema(26)
    trend = "UP" if ema12 > ema26 else "DOWN"

    # --- RVOL
    avg_vol20 = sum(vols[-20:]) / 20
    rvol = vols[-1] / avg_vol20 if avg_vol20 else 0
    last = closes[-1]

    # --- Cross detection
    cross = "ABOVE" if last > safeU else "BELOW" if last < safeL else "no cross"

    # --- Frequency near bands (last 12 candles = 1h)
    nearU = sum(1 for c in closes[-12:] if abs(upper - c) <= (upper - lower) * 0.15)
    nearL = sum(1 for c in closes[-12:] if abs(c - lower) <= (upper - lower) * 0.15)
    freqU, freqL = round(nearU / 12 * 100, 1), round(nearL / 12 * 100, 1)

    # --- Prediction logic
    if cross == "ABOVE" and trend == "UP" and rvol >= 1.5:
        pred, emoji = "UP (strong)", "🟢"
    elif cross == "BELOW" and trend == "DOWN" and rvol >= 1.5:
        pred, emoji = "DOWN (strong)", "🔴"
    elif rvol < 0.8:
        pred, emoji = f"Weak {trend} – Low Volume", "⚪"
    else:
        pred, emoji = trend, "⚪"

    # --- Build result
    return {
        "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "last": round(last, 2),
        "volume": round(vols[-1], 2),
        "rvol": round(rvol, 2),
        "sma20": round(sma, 2),
        "upper": round(upper, 2),
        "lower": round(lower, 2),
        "safe_upper": round(safeU, 2),
        "safe_lower": round(safeL, 2),
        "ema12": round(ema12, 2),
        "ema26": round(ema26, 2),
        "trend": trend,
        "freq_upper": f"{freqU}%",
        "freq_lower": f"{freqL}%",
        "cross": cross,
        "prediction": pred,
        "emoji": emoji
    }

# -----------------------------------------------
# MAIN EXECUTION
# -----------------------------------------------
if __name__ == "__main__":
    print("🚀 Starting BTC analysis script...")
    data = get_btc_data()
    if not data:
        fallback = {
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "error": "Failed to fetch Binance data.",
            "prediction": "no data",
            "emoji": "⚪"
        }
        with open("btc.json", "w") as f:
            json.dump(fallback, f, indent=2)
        print("⚠️ No data fetched, wrote fallback JSON.")
    else:
        result = compute(data)
        with open("btc.json", "w") as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2))
        print("✅ btc.json written successfully.")
