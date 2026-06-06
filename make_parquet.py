# make_parquet.py
# Takes the capture.jsonl that the recorder wrote and turns it into a Parquet
# file (columnar + compressed). Also makes a gzipped copy of the jsonl so I
# can compare the three sizes later.

import gzip
import json

import pyarrow as pa
import pyarrow.parquet as pq

IN_FILE = "capture.jsonl"
PARQUET_FILE = "capture.parquet"
GZIP_FILE = "capture.jsonl.gz"


def main():
    wall_ms, ticker, seq, yes_bid, yes_ask, yes_levels, no_levels = [], [], [], [], [], [], []

    with open(IN_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            wall_ms.append(r["wall_ms"])
            ticker.append(r["ticker"])
            seq.append(r["seq"])
            yes_bid.append(r["yes_bid"])
            yes_ask.append(r["yes_ask"])
            # keep the depth as a json string so the table stays flat/simple
            yes_levels.append(json.dumps(r["yes_levels"]))
            no_levels.append(json.dumps(r["no_levels"]))

    table = pa.table({
        "wall_ms": wall_ms,
        "ticker": ticker,
        "seq": seq,
        "yes_bid": yes_bid,
        "yes_ask": yes_ask,
        "yes_levels": yes_levels,
        "no_levels": no_levels,
    })
    pq.write_table(table, PARQUET_FILE, compression="zstd")
    print("wrote", PARQUET_FILE, "with", table.num_rows, "rows")

    # gzip the original jsonl so we have a compressed row-format to compare to
    with open(IN_FILE, "rb") as fin, gzip.open(GZIP_FILE, "wb") as fout:
        fout.writelines(fin)
    print("wrote", GZIP_FILE)


if __name__ == "__main__":
    main()
