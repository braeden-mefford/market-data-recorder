# fake_engine.py
# Pretends to be the live trading engine. It creates the shared-memory file and
# keeps changing the order books so the recorder has something to capture.
# In the real system this part already exists - I only built it so I can test
# the recorder without being on the production server.
#
# Run this FIRST, in its own terminal:
#     python fake_engine.py
# Leave it running and start recorder.py in another terminal.

import mmap
import random
import struct
import time

import shm_layout as L


def write_slot(mm, i, book):
    # write one market into its slot using the seqlock protocol
    base = L.slot_offset(i)

    # step 1: make seq odd so a reader knows we are in the middle of writing
    seq = struct.unpack_from(L.SEQ_FMT, mm, base)[0]
    seq_even = seq & ~1
    struct.pack_into(L.SEQ_FMT, mm, base, seq_even | 1)

    # build some fake depth - each level is one cent worse and a bit bigger
    yes_levels = []
    for lvl in range(L.NUM_LEVELS):
        px = round(max(0.01, book["bid"] - lvl * 0.01), 2)
        yes_levels += [px, float(100 + lvl * 50)]
    no_levels = []
    for lvl in range(L.NUM_LEVELS):
        px = round(min(0.99, book["ask"] + lvl * 0.01), 2)
        no_levels += [px, float(100 + lvl * 50)]

    ticker_bytes = book["ticker"].encode("ascii")[:L.TICKER_LEN]
    values = [ticker_bytes, book["bid"], book["ask"]] + yes_levels + no_levels
    struct.pack_into(L.FIELDS_FMT, mm, base + L.SEQ_SIZE, *values)

    # step 2: bump seq to the next even number = "done, safe to read"
    struct.pack_into(L.SEQ_FMT, mm, base, seq_even + 2)


def main():
    # make a zero filled file of the right size so we can memory map it
    with open(L.SHM_PATH, "wb") as f:
        f.write(b"\x00" * L.TOTAL_SIZE)

    f = open(L.SHM_PATH, "r+b")
    mm = mmap.mmap(f.fileno(), L.TOTAL_SIZE)

    # write the header (magic + slot count)
    struct.pack_into(L.HEADER_FMT, mm, 0, L.MAGIC, L.NUM_SLOTS)

    tickers = ["KXMLB-NYY", "KXMLB-BOS", "KXNBA-LAL", "KXNBA-BOS", "KXBTC-UP", "KXBTC-DN"]
    books = [{"ticker": t, "bid": 0.49, "ask": 0.51} for t in tickers]

    # write a starting state for every slot
    for i in range(L.NUM_SLOTS):
        write_slot(mm, i, books[i])

    print("fake engine running -> writing", L.SHM_PATH, "(ctrl-c to stop)")
    try:
        while True:
            # pick a random market and nudge its price a little (random walk)
            i = random.randrange(L.NUM_SLOTS)
            b = books[i]
            step = random.choice([-0.01, 0.0, 0.01])
            b["bid"] = round(min(0.98, max(0.01, b["bid"] + step)), 2)
            b["ask"] = round(min(0.99, max(b["bid"] + 0.01, b["ask"] + step)), 2)
            write_slot(mm, i, b)
            time.sleep(random.uniform(0.1, 0.3))
    except KeyboardInterrupt:
        print("\nstopping engine")
        mm.flush()
        mm.close()
        f.close()


if __name__ == "__main__":
    main()
