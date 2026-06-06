# evaluate.py
# Measures how the framework performs. It reports four things:
#   1) ingestion rate, taken from the capture itself (rows per second)
#   2) storage size of each format and the compression ratio
#   3) query speed on jsonl vs parquet vs the duckdb database
#   4) worst case data loss from the 2 second recovery window
#
# Run it after you have a capture.jsonl, capture.parquet and market.duckdb:
#     python evaluate.py

import json
import os
import time

import duckdb

JSONL = "capture.jsonl"
GZ = "capture.jsonl.gz"
PARQUET = "capture.parquet"
DB_FILE = "market.duckdb"
FLUSH_SECONDS = 2.0   # matches recorder.py


def size(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def ingestion_rate():
    # work out rows per second from the timestamps already in the log
    times, rows = [], 0
    for line in open(JSONL):
        line = line.strip()
        if not line:
            continue
        times.append(json.loads(line)["wall_ms"])
        rows += 1
    if rows < 2:
        return rows, 0.0, 0.0
    span = (max(times) - min(times)) / 1000.0
    rate = rows / span if span > 0 else 0.0
    return rows, span, rate


def avg_query_time(con, query, runs=5):
    con.execute(query).fetchall()   # warm up run, not timed
    t0 = time.perf_counter()
    for _ in range(runs):
        con.execute(query).fetchall()
    return (time.perf_counter() - t0) / runs


def main():
    print("== 1. ingestion ==")
    rows, span, rate = ingestion_rate()
    print("  rows captured :", rows)
    print("  capture span  : %.1f sec" % span)
    print("  ingest rate   : %.1f rows/sec" % rate)

    print("\n== 2. storage ==")
    j, g, p, d = size(JSONL), size(GZ), size(PARQUET), size(DB_FILE)
    print("  jsonl    :", j, "bytes")
    print("  jsonl.gz :", g, "bytes")
    print("  parquet  :", p, "bytes")
    print("  duckdb   :", d, "bytes")
    if p:
        print("  parquet is %.1fx smaller than raw jsonl" % (j / p))

    print("\n== 3. query latency (same group-by, avg of 5 runs) ==")
    agg = "select ticker, count(*), avg(yes_ask - yes_bid) from %s group by ticker"
    con = duckdb.connect()
    print("  jsonl    : %.4f sec" % avg_query_time(con, agg % ("read_json_auto('%s')" % JSONL)))
    print("  parquet  : %.4f sec" % avg_query_time(con, agg % ("read_parquet('%s')" % PARQUET)))
    con.close()
    if os.path.exists(DB_FILE):
        dcon = duckdb.connect(DB_FILE)
        print("  duckdb   : %.4f sec" % avg_query_time(dcon, agg % "book_changes"))
        dcon.close()

    print("\n== 4. recovery ==")
    print("  flush window : %.1f sec" % FLUSH_SECONDS)
    print("  worst case loss on an abrupt kill: about %.0f rows" % (rate * FLUSH_SECONDS))


if __name__ == "__main__":
    main()
