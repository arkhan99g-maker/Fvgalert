import os
import time
from datetime import datetime, timezone
import requests

MIN_GAP = 0.0            # chhote gap ignore karne ke liye (dollars), e.g. 0.5
MAX_AGE = 5400           # 90 min se purani candle par alert nahi (weekend/stale data)

BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TD_KEY = os.environ.get("TWELVE_API_KEY", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=20)
    r.raise_for_status()


def candles_twelvedata():
    """Spot XAU/USD, 1h candles (UTC)."""
    params = {
        "symbol": "XAU/USD",
        "interval": "1h",
        "outputsize": 12,
        "timezone": "UTC",
        "apikey": TD_KEY,
    }
    r = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=30)
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(f"TwelveData: {data.get('message', data)}")
    out = []
    for v in data["values"]:
        t = datetime.strptime(v["datetime"], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        ).timestamp()
        out.append(
            {"t": t, "o": float(v["open"]), "h": float(v["high"]),
             "l": float(v["low"]), "c": float(v["close"])}
        )
    out.sort(key=lambda c: c["t"])  # purani se nayi
    return out


def candles_yahoo():
    """Fallback: gold futures GC=F."""
    last_err = "unknown"
    for attempt in range(3):
        for host in ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]:
            url = f"https://{host}/v8/finance/chart/GC=F"
            try:
                r = requests.get(
                    url, params={"interval": "1h", "range": "5d"},
                    headers=HEADERS, timeout=30,
                )
                if r.status_code != 200:
                    last_err = f"{host} HTTP {r.status_code}"
                    continue
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                out = []
                for i, t in enumerate(res["timestamp"]):
                    o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
                    if None in (o, h, l, c):
                        continue
                    out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
                if out:
                    return out
            except Exception as e:
                last_err = f"{host} {type(e).__name__}: {e}"
        time.sleep(5)
    raise RuntimeError(f"Yahoo fetch failed: {last_err}")


def get_candles():
    if TD_KEY:
        try:
            return candles_twelvedata(), "XAUUSD (spot, TwelveData)"
        except Exception as e:
            print(f"TwelveData failed, using Yahoo: {e}")
            return candles_yahoo(), "GC=F (futures, Yahoo) - TwelveData fail"
    return candles_yahoo(), "GC=F (futures, Yahoo)"


def main():
    test = os.environ.get("TEST_MESSAGE") == "true"
    if test:
        send("✅ FVG bot connected. Test message successful.")

    candles, source = get_candles()
    now = time.time()
    closed = [c for c in candles if c["t"] + 3600 <= now]  # sirf band candles
    if len(closed) < 3:
        print("Not enough closed candles")
        return

    c1, c2, c3 = closed[-3], closed[-2], closed[-1]
    close_ts = c3["t"] + 3600
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(close_ts))
    stale = (now - close_ts) > MAX_AGE

    if stale:
        print("Latest candle is old (market closed?) - skipping FVG check")
    # Bullish FVG: candle1 high < candle3 low
    elif c3["l"] > c1["h"] and c3["l"] - c1["h"] > MIN_GAP:
        send(
            f"🟢 XAUUSD 1H Bullish FVG\n"
            f"Zone: {c1['h']:.2f} - {c3['l']:.2f}\n"
            f"Gap size: {c3['l'] - c1['h']:.2f}\n"
            f"Candle close: {when}\n"
            f"Source: {source}"
        )
        print("Bullish FVG sent")
    # Bearish FVG: candle1 low > candle3 high
    elif c1["l"] > c3["h"] and c1["l"] - c3["h"] > MIN_GAP:
        send(
            f"🔴 XAUUSD 1H Bearish FVG\n"
            f"Zone: {c3['h']:.2f} - {c1['l']:.2f}\n"
            f"Gap size: {c1['l'] - c3['h']:.2f}\n"
            f"Candle close: {when}\n"
            f"Source: {source}"
        )
        print("Bearish FVG sent")
    else:
        print("No FVG on latest candle")

    if test:
        note = "\n(Market band hai, candle purani hai)" if stale else ""
        send(
            f"ℹ️ Data OK ({source})\n"
            f"Latest closed 1H candle: {when}\n"
            f"High {c3['h']:.2f} / Low {c3['l']:.2f}{note}\n"
            f"(Test run mein FVG nahi bana to sirf yehi message aayega)"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            send(f"⚠️ FVG bot error: {type(e).__name__}: {e}"[:400])
        except Exception:
            pass
        raise
