# recorder.py
# This is the actual recording layer for my project. It attaches to the shared
# memory the engine is writing, watches for changes, and writes every change
# out to a JSONL file (one json object per line = a log).
#
# Start fake_engine.py or live_engine.py first
import json
import mmap
import os
import struct
import time

import shm_layout as L

OUT_FILE = "capture.jsonl"
POLL_SECONDS = 0.05     # how often we scan the slots for changes
FLUSH_SECONDS = 2.0     # how often we force the file down to disk (fsync)


def read_slot(mm, i):
    # seqlock read. returns (seq, fields tuple) or (None, None) if the writer
    # kept changing the slot while we were trying to read it.
    base = L.slot_offset(i)
    for _ in range(100):
        s1 = struct.unpack_from(L.SEQ_FMT, mm, base)[0]
        if s1 & 1:
            continue  # odd seq = engine is writing right now, try again
        fields = struct.unpack_from(L.FIELDS_FMT, mm, base + L.SEQ_SIZE)
        s2 = struct.unpack_from(L.SEQ_FMT, mm, base)[0]
        if s1 == s2:
            return s1, fields  # seq didn't move, so the read is clean
    return None, None


def unpack_fields(fields):
    # turn the raw struct tuple into nice python values
    ticker = fields[0].split(b"\x00", 1)[0].decode("ascii", "replace")
    yes_bid = fields[1]
    yes_ask = fields[2]
    rest = fields[3:]  
    yes_levels = [[rest[k], rest[k + 1]] for k in range(0, 10, 2)]
    no_levels = [[rest[k], rest[k + 1]] for k in range(10, 20, 2)]
    return ticker, yes_bid, yes_ask, yes_levels, no_levels


def main():
    # the engine has to be running already so the file exists
    if not os.path.exists(L.SHM_PATH):
        print("can't find", L.SHM_PATH, "- start fake_engine.py or live_engine.py first")
        return

    f = open(L.SHM_PATH, "r+b")
    mm = mmap.mmap(f.fileno(), L.TOTAL_SIZE)
    magic, num_slots = struct.unpack_from(L.HEADER_FMT, mm, 0)
    if magic != L.MAGIC:
        print("that file isn't ours, magic =", magic)
        return
    print("recorder attached, slots =", num_slots, "-> writing", OUT_FILE)

    last_seq = {}          # remember the last seq we saved per slot
    out = open(OUT_FILE, "a")   # append mode so we never overwrite old data
    rows = 0
    last_flush = time.time()

    try:
        while True:
            for i in range(num_slots):
                seq, fields = read_slot(mm, i)
                if seq is None:
                    continue
                if last_seq.get(i) == seq:
                    continue  # this market hasn't changed since last time
                last_seq[i] = seq

                ticker, yb, ya, yl, nl = unpack_fields(fields)
                row = {
                    "wall_ms": int(time.time() * 1000),
                    "ticker": ticker,
                    "seq": seq,
                    "yes_bid": yb,
                    "yes_ask": ya,
                    "yes_levels": yl,
                    "no_levels": nl,
                }
                out.write(json.dumps(row) + "\n")
                rows += 1

            # every couple seconds, force what we have to disk. this is the
            # "recovery window" - if we get killed, we only lose stuff written
            # since the last fsync, everything before it is safe on disk.
            if time.time() - last_flush > FLUSH_SECONDS:
                out.flush()
                os.fsync(out.fileno())
                last_flush = time.time()
                print("captured", rows, "rows so far")

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nstopping recorder - flushing", rows, "rows")
        out.flush()
        os.fsync(out.fileno())
        out.close()


if __name__ == "__main__":
    main()
