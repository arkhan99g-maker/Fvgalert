import os
import time
import requests

SYMBOL = "XAUUSD=X"      # Yahoo Finance spot gold
INTERVAL = "1h"
MIN_GAP = 0.0            # chhote gap ignore karne ke liye (dollars), e.g. 0.5

BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg}, timeout=20)
    r.raise_for_status()


def get_candles():
    last_err = "unknown"
    for attempt in range(3):
        for host in HOSTS:
            url = f"https://{host}/v8/finance/chart/{SYMBOL}"
            params = {"interval": INTERVAL, "range": "5d"}
            try:
                r = requests.get(url, params=params, headers=HEADERS, timeout=30)
                if r.status_code != 200:
                    last_err = f"{host} HTTP {r.status_code}"
                    print(last_err)
                    continue
                res = r.json()["chart"]["result"][0]
                ts = res["timestamp"]
                q = res["indicators"]["quote"][0]
                candles = []
                for i, t in enumerate(ts):
                    o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
                    if None in (o, h, l, c):
                        continue
                    candles.append({"t": t, "o": o, "h": h, "l": l, "c": c})
                if candles:
                    return candles
                last_err = f"{host} returned no candles"
            except Exception as e:
                last_err = f"{host} {type(e).__name__}: {e}"
                print(last_err)
        time.sleep(5)
    raise RuntimeError(f"Data fetch failed: {last_err}")


def main():
    if os.environ.get("TEST_MESSAGE") == "true":
        send("✅ FVG bot connected. Test message successful.")

    candles = get_candles()
    now = time.time()
    # sirf band (closed) candles lein
    closed = [c for c in candles if c["t"] + 3600 <= now]
    if len(closed) < 3:
        print("Not enough closed candles")
        return

    c1, c2, c3 = closed[-3], closed[-2], closed[-1]
    when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(c3["t"] + 3600))

    # Bullish FVG: candle1 high < candle3 low
    if c3["l"] > c1["h"] and c3["l"] - c1["h"] > MIN_GAP:
        send(
            f"🟢 XAUUSD 1H Bullish FVG\n"
            f"Zone: {c1['h']:.2f} - {c3['l']:.2f}\n"
            f"Gap size: {c3['l'] - c1['h']:.2f}\n"
            f"Candle close: {when}"
        )
        print("Bullish FVG sent")

    # Bearish FVG: candle1 low > candle3 high
    elif c1["l"] > c3["h"] and c1["l"] - c3["h"] > MIN_GAP:
        send(
            f"🔴 XAUUSD 1H Bearish FVG\n"
            f"Zone: {c3['h']:.2f} - {c1['l']:.2f}\n"
            f"Gap size: {c1['l'] - c3['h']:.2f}\n"
            f"Candle close: {when}"
        )
        print("Bearish FVG sent")
    else:
        print("No FVG on latest candle")

    if os.environ.get("TEST_MESSAGE") == "true":
        send(
            f"ℹ️ Data OK. Latest closed 1H candle: {when}\n"
            f"High {c3['h']:.2f} / Low {c3['l']:.2f}\n"
            f"(Is test run mein FVG nahi bana to sirf yehi message aayega)"
        )


if _name_ == "_main_":
    try:
        main()
    except Exception as e:
        try:
            send(f"⚠️ FVG bot error: {type(e).__name__}: {e}"[:400])
        except Exception:
            pass
        raise
