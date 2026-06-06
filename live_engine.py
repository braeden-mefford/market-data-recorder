# live_engine.py
# Same job as fake_engine.py, but instead of making up prices it pulls REAL
# order books from Kalshi's REST API and writes them into the shared memory
# file. The recorder doesn't know the difference - it just reads the shm.
# Setup (one time):
#   1) copy .env.example to .env
#   2) put your Kalshi API key id and the path to your private key .pem in it
#   3) python live_engine.py
#
# Reads orderbooks for a handful of markets every ~1.5 seconds.

import base64
import mmap
import os
import struct
import time

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

import shm_layout as L

load_dotenv()

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
API_KEY_ID = os.getenv("KALSHI_API_KEY_ID", "")
PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH", "")
SERIES = os.getenv("KALSHI_SERIES", "KXMLBGAME")   # which series to capture

_session = requests.Session()
_private_key = None


def get_key():
    global _private_key
    if _private_key is None:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            _private_key = serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend())
    return _private_key


def sign(method, full_path, ts_ms):
    # Kalshi wants RSA-PSS / SHA256 over "<timestamp><METHOD><path>"
    msg = ("%d%s%s" % (ts_ms, method, full_path)).encode("utf-8")
    sig = get_key().sign(
        msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256())
    return base64.b64encode(sig).decode("utf-8")


def get(path, params=None):
    # path is like "/markets" (no /trade-api/v2 prefix)
    full_path = "/trade-api/v2" + path
    ts = int(time.time() * 1000)
    headers = {
        "KALSHI-ACCESS-KEY": API_KEY_ID,
        "KALSHI-ACCESS-SIGNATURE": sign("GET", full_path, ts),
        "KALSHI-ACCESS-TIMESTAMP": str(ts),
    }
    resp = _session.get(API_BASE + path, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def pick_markets():
    # grab open markets in the series and keep the first few that actually have
    # an order book with something in it
    r = get("/markets", params={"limit": 60, "status": "open", "series_ticker": SERIES})
    markets = r.get("markets", [])
    chosen = []
    for m in markets:
        t = m["ticker"]
        ob = get("/markets/" + t + "/orderbook", params={"depth": L.NUM_LEVELS})
        fp = ob.get("orderbook_fp") or {}
        if fp.get("yes_dollars") or fp.get("no_dollars"):
            chosen.append(t)
            print("  will capture", t)
        if len(chosen) >= L.NUM_SLOTS:
            break
        time.sleep(0.1)
    return chosen


def levels_best_first(rows):
    # Kalshi sends ascending price (best bid is the LAST one). flip it so the
    # best price is first, take the top NUM_LEVELS, pad with zeros if short.
    out = []
    for price_str, size_str in reversed(rows[-L.NUM_LEVELS:]):
        out += [float(price_str), float(size_str)]
    while len(out) < L.NUM_LEVELS * 2:
        out += [0.0, 0.0]
    return out


def write_slot(mm, i, ticker, fp):
    base = L.slot_offset(i)
    seq = struct.unpack_from(L.SEQ_FMT, mm, base)[0]
    seq_even = seq & ~1
    struct.pack_into(L.SEQ_FMT, mm, base, seq_even | 1)   # mark "writing"

    yes_rows = fp.get("yes_dollars") or []
    no_rows = fp.get("no_dollars") or []
    yes_bid = float(yes_rows[-1][0]) if yes_rows else 0.0
    best_no_bid = float(no_rows[-1][0]) if no_rows else 0.0
    yes_ask = round(1.0 - best_no_bid, 2) if no_rows else 0.0

    yes_levels = levels_best_first(yes_rows)
    no_levels = levels_best_first(no_rows)

    ticker_bytes = ticker.encode("ascii")[:L.TICKER_LEN]
    values = [ticker_bytes, yes_bid, yes_ask] + yes_levels + no_levels
    struct.pack_into(L.FIELDS_FMT, mm, base + L.SEQ_SIZE, *values)

    struct.pack_into(L.SEQ_FMT, mm, base, seq_even + 2)   # done


def main():
    if not API_KEY_ID or not PRIVATE_KEY_PATH:
        print("missing creds - copy .env.example to .env and fill it in")
        return

    print("finding markets in series", SERIES, "...")
    tickers = pick_markets()
    if not tickers:
        print("no markets with a book found, try a different KALSHI_SERIES")
        return

    # size the shm file for however many markets we found
    with open(L.SHM_PATH, "wb") as f:
        f.write(b"\x00" * L.TOTAL_SIZE)
    f = open(L.SHM_PATH, "r+b")
    mm = mmap.mmap(f.fileno(), L.TOTAL_SIZE)
    struct.pack_into(L.HEADER_FMT, mm, 0, L.MAGIC, len(tickers))

    print("live engine running -> writing real books to", L.SHM_PATH, "(ctrl-c to stop)")
    try:
        while True:
            for i, t in enumerate(tickers):
                try:
                    ob = get("/markets/" + t + "/orderbook", params={"depth": L.NUM_LEVELS})
                    fp = ob.get("orderbook_fp") or {}
                    write_slot(mm, i, t, fp)
                except Exception as e:
                    print("  problem reading", t, "->", e)
                time.sleep(0.15)   # be polite to the API
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nstopping live engine")
        mm.flush()
        mm.close()
        f.close()


if __name__ == "__main__":
    main()
