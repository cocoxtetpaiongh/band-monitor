import requests, statistics, json, time
from datetime import datetime

def get_btc_data(retries=3, delay=5):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": "5m", "limit": 120}
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list) and len(data) >= 20:
                return data
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(delay)
    print("❌ Failed to fetch data after retries.")
    return []

def compute(data):
    closes = [float(c[4]) for c in data]
    vols   = [float(c[5]) for c in data]
    sma = sum(closes[-20:]) / 20
    std = statistics.pstdev(closes[-20:])
    upper, lower = sma + 2*std, sma - 2*std
    safeU, safeL = upper * 1.005, lower * 0.995

    def ema(period):
        k = 2 / (period + 1)
        e = sum(closes[:period]) / period
        for p in closes[period:]:
            e = p * k + e * (1 - k)
        return e

    ema12, ema26 = ema(12), ema(26)
    trend = "UP" if ema12 > ema26 else "DOWN"
    avg_vol20 = sum(vols[-20:]) / 20
    rvol = vols[-1] / avg_vol20 if avg_vol20 else 0
    last = closes[-1]

    cross = "ABOVE" if last > safeU else "BELOW" if last < safeL else "no cross"

    nearU = sum(1 for c in closes[-12:] if abs(upper - c) <= (upper - lower) * 0.15)
    nearL = sum(1 for c in closes[-12:] if abs(c - lower) <= (upper - lower) * 0.15)
    freqU, freqL = round(nearU / 12 * 100, 1), round(nearL / 12 * 100, 1)

    if cross == "ABOVE" and trend == "UP" and rvol >= 1.5:
        pred, emoji = "UP (strong)", "🟢"
    elif cross == "BELOW" and trend == "DOWN" and rvol >= 1.5:
        pred, emoji = "DOWN (strong)", "🔴"
    elif rvol < 0.8:
        pred, emoji = f"Weak {trend} – Low Volume", "⚪"
    else:
        pred, emoji = trend, "⚪"

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

if __name__ == "__main__":
    data = get_btc_data()
    if not data:
        fallback = {
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "error": "Failed to fetch Binance data.",
            "prediction": "no data",
            "emoji": "⚪"
        }
        print("⚠️ No data fetched, writing fallback JSON.")
        with open("btc.json", "w") as f:
            json.dump(fallback, f, indent=2)
    else:
        result = compute(data)
        with open("btc.json", "w") as f:
            json.dump(result, f, indent=2)
        print(json.dumps(result, indent=2))
