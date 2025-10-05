# btc_analysis.py
import json, time, statistics, requests
from datetime import datetime, timezone

PAIR = "BTCUSDT"
INTERVAL = "5m"
LIMIT = 120

BINANCE_URLS = [
    "https://api1.binance.com/api/v3/klines",
    "https://api2.binance.com/api/v3/klines",
    "https://api3.binance.com/api/v3/klines",
    "https://api-gateway.binance.com/api/v3/klines",
    "https://api.binance.com/api/v3/klines",  # last
]
RETRIES = 3
RETRY_DELAY = 5  # seconds

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def fetch_binance():
    params = {"symbol": PAIR, "interval": INTERVAL, "limit": LIMIT}
    for url in BINANCE_URLS:
        for attempt in range(1, RETRIES + 1):
            try:
                print(f"📡 {url} (attempt {attempt})")
                r = requests.get(url, params=params, timeout=12)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, list) and len(data) >= 20:
                    return data, "Binance"
                raise ValueError("Unexpected response format")
            except Exception as e:
                print(f"  ⚠️  {e}")
                if attempt < RETRIES:
                    time.sleep(RETRY_DELAY)
    return None, None

def fetch_coingecko_fallback():
    """CoinGecko fallback: build pseudo-klines from 5m price points."""
    try:
        print("🪙 Falling back to CoinGecko…")
        cg = requests.get(
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
            params={"vs_currency": "usd", "days": "1"},
            timeout=12,
        ).json()
        prices = cg.get("prices", [])[-LIMIT:]  # [ [ts_ms, price], ... ]
        if not prices:
            return None, None
        # build pseudo kline arrays like Binance: open, high, low, close, volume
        # we only have close; use close as open/high/low and volume=0
        klines = []
        for p in prices:
            close = float(p[1])
            # shape similar to Binance kline (we only use index 4 close, 5 volume)
            klines.append([0, 0, 0, 0, f"{close}", "0"])
        return klines, "CoinGecko"
    except Exception as e:
        print(f"  ❌ CoinGecko fallback failed: {e}")
        return None, None

def ema(series, period):
    k = 2 / (period + 1)
    e = sum(series[:period]) / period
    for price in series[period:]:
        e = price * k + e * (1 - k)
    return e

def compute(data):
    closes = [float(c[4]) for c in data]
    vols   = [float(c[5]) for c in data]

    sma20 = sum(closes[-20:]) / 20
    std20 = statistics.pstdev(closes[-20:])
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20

    # safe margins ±0.5%
    safe_upper = upper * 1.005
    safe_lower = lower * 0.995

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    trend = "UP" if ema12 > ema26 else "DOWN"

    avg_vol20 = (sum(vols[-20:]) / 20) if sum(vols[-20:]) != 0 else 0.0
    rvol = (vols[-1] / avg_vol20) if avg_vol20 else 0.0

    last = closes[-1]
    cross = "ABOVE" if last > safe_upper else "BELOW" if last < safe_lower else "no cross"

    # last hour (12 x 5m) near-band frequency
    width = (upper - lower)
    tol = width * 0.15
    recent = closes[-12:]
    freqU = round(sum(1 for c in recent if abs(upper - c) <= tol) / 12 * 100, 1)
    freqL = round(sum(1 for c in recent if abs(c - lower) <= tol) / 12 * 100, 1)

    # prediction & emoji
    if cross == "ABOVE" and trend == "UP" and rvol >= 1.5:
        prediction, emoji = "UP (strong)", "🟢"
    elif cross == "BELOW" and trend == "DOWN" and rvol >= 1.5:
        prediction, emoji = "DOWN (strong)", "🔴"
    elif rvol < 0.8:
        prediction, emoji = f"Weak {trend} – Low Volume", "⚪"
    else:
        prediction, emoji = trend, "⚪"

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
        "emoji": emoji,
    }

def write_json(payload):
    with open("btc.json", "w") as f:
        json.dump(payload, f, indent=2)
    print("💾 Wrote btc.json")

if __name__ == "__main__":
    print("🚀 Starting BTC 5-minute analysis…")
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
    write_json(result)

    # Console message for logs / notifications
    last = result["last"]
    su, sl = result["safe_upper"], result["safe_lower"]
    msg_lines = [
        f"{result['emoji']} {PAIR} 5m — {result['prediction']}",
        f"Last: {last}  |  Trend: {result['trend']}  |  RVOL: {result['rvol']}",
        f"Safe Bands: {sl} – {su}",
        f"Freq near bands (1h): U {result['freq_upper']}  L {result['freq_lower']}",
        f"Source: {result['source']}",
    ]

    if result["cross"] in ("ABOVE", "BELOW"):
        msg_lines.insert(1, f"Cross: {result['cross']} SAFE band")
        msg_lines.append(
            'Open ChatGPT for full analysis → '
            'chat.openai.com/?model=gpt-5&prompt=Fetch+latest+BTC+5-min+Bollinger+analysis'
        )

    print("\n".join(msg_lines))
