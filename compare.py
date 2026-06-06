# compare.py
# Compares the storage formats two ways:
#   1) file size  -> jsonl vs jsonl.gz vs parquet
#   2) query speed -> run the same aggregation on the raw jsonl and on the
#      parquet using DuckDB, and time it.


import os
import time

import duckdb

JSONL = "capture.jsonl"
GZ = "capture.jsonl.gz"
PARQUET = "capture.parquet"


def size(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def main():
    j, g, p = size(JSONL), size(GZ), size(PARQUET)
    print("file sizes (bytes):")
    print("  jsonl    ", j)
    print("  jsonl.gz ", g)
    print("  parquet  ", p)
    if p:
        print("  -> parquet is %.1fx smaller than raw jsonl" % (j / p))

    con = duckdb.connect()
    # same query both ways: rows + average spread per ticker
    q_parquet = ("select ticker, count(*) as n, avg(yes_ask - yes_bid) as spread "
                 "from read_parquet('%s') group by ticker order by ticker" % PARQUET)
    q_jsonl = ("select ticker, count(*) as n, avg(yes_ask - yes_bid) as spread "
               "from read_json_auto('%s') group by ticker order by ticker" % JSONL)

    print()
    for name, q in [("parquet", q_parquet), ("jsonl", q_jsonl)]:
        con.execute(q).fetchall()  # warm up run (not timed)
        t0 = time.perf_counter()
        for _ in range(5):
            con.execute(q).fetchall()
        avg = (time.perf_counter() - t0) / 5
        print("query on %-7s took %.4f sec (avg of 5 runs)" % (name, avg))

    print("\nsample result (from parquet):")
    for row in con.execute(q_parquet).fetchall():
        print("  ", row)


if __name__ == "__main__":
    main()
