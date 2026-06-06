# Market Data Recorder (CSIS 638 Prototype)

Small prototype of a market data capture layer. A trading engine keeps the
current order books for some markets in shared memory. This prototype is the
recording layer that reads that shared memory and saves it to disk so it can
be queried later.

The real engine runs on a server, so fake_engine.py stands in for it so the
whole thing can run on one laptop.

## Files

- shm_layout.py - the byte layout of the shared memory file (used by both the
  writer and the reader so they agree on the format)
- fake_engine.py - offline stand-in for the engine, writes made up order books
- live_engine.py - pulls real Kalshi order books over the REST API (read only)
- recorder.py - the main part, reads shared memory and logs each change to capture.jsonl
- make_parquet.py - turns capture.jsonl into capture.parquet (and a gzipped copy)
- build_db.py - loads the capture into a DuckDB database file with a real table
- compare.py - compares file size and query speed of JSONL vs Parquet
- evaluate.py - measures ingestion rate, storage, query speed, and recovery loss
- REALTIME.md - how the framework extends to true real-time collection

## Dataflow

```
  fake_engine.py (made up)   OR   live_engine.py (real Kalshi REST, read only)
       |  writes order books under a seqlock
       v
  market_shm.bin    (shared memory = a memory mapped file)
       |  recorder polls and notices which slots changed
       v
  recorder.py
       |  one JSON object per change (append only log)
       v
  capture.jsonl  --- make_parquet.py --->  capture.parquet
       |                                        |
       +---------------- compare.py ------------+
                 (size and query speed)
```

## How to run

Install the two libraries:

```
pip install -r requirements.txt
```

Open two terminals in this folder:

```
# terminal 1 - the engine that fills shared memory
python fake_engine.py        # made up data, no account needed
#   or, for real Kalshi data:
python live_engine.py        # needs a .env file (see below)

# terminal 2 - the recorder (let it run a few minutes)
python recorder.py
```

Stop the recorder with ctrl-c, then:

```
python make_parquet.py
python build_db.py
python compare.py
python evaluate.py
```

## Using real Kalshi data (live_engine.py)

Copy the example env file and fill it in:

```
copy .env.example .env
```

Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH (path to your RSA private key
.pem file). live_engine.py only sends GET requests, it reads order books and
never places a trade. The .env file and any .pem files are gitignored so the
key never gets committed.

## Database and data format

The recorder writes each order book change as one line of JSON to capture.jsonl.
Every line has the same flat fields, which is what makes it easy to query:

```
  wall_ms     when the recorder saw the change (unix milliseconds)
  ticker      market id
  seq         per market sequence number from shared memory
  yes_bid     best yes bid in dollars
  yes_ask     best yes ask in dollars
  yes_levels  top yes book levels, a json array of [price, size]
  no_levels   top no book levels, a json array of [price, size]
```

Because the file is newline delimited, every line is a complete record on its
own, so the file can be read one line at a time and appended to forever.

The database is DuckDB. build_db.py loads the captured data into a single
database file (market.duckdb) with a typed book_changes table. DuckDB is an
embedded column store, so there is no separate server to run and the database is
one portable file. It can read JSONL and Parquet directly, and it is fast at the
group-by and aggregate queries this market data needs. A row store like Postgres
was not needed here because the workload is append-only writes plus analytical
reads, not many small concurrent transactions.

## Real-time

REALTIME.md explains how this framework extends to true real-time (streaming)
collection, and why the prototype uses a simple engine in place of the
proprietary production one.

## Performance

evaluate.py measures the framework: ingestion rate, storage size and
compression, query speed across the three storage options, and the worst case
recovery loss.

## Concepts

- Shared memory with mmap: the recorder reads the engine's memory directly with
  no copy, using Python's mmap and struct.
- Seqlock: every slot has a counter that is odd while it is being written and
  even when it is done. The reader checks the counter before and after reading
  so it never saves a half written book.
- Append only log: changes are appended to a JSONL file, nothing is overwritten.
- Recovery window: the recorder calls fsync every 2 seconds, so an abrupt kill
  loses at most about 2 seconds of data and everything already flushed is fine.
- Row vs columnar storage: JSONL (row) vs Parquet (columnar and compressed),
  compared on file size and query speed with DuckDB.

## Recovery test

1. Run the engine and the recorder.
2. Kill the recorder hard (close the terminal) instead of using ctrl-c.
3. Open capture.jsonl. Every line up to the last flush is still complete and
   readable. At worst the very last line is cut off.

## Note

This is kept small on purpose: 6 markets, 5 price levels per side, fixed size
file. The production version is much bigger (about 50 levels, a hash table
index, more fields). The read path here (mmap, seqlock, detect change, log) is
the same idea you would point at the real shared memory file on the server.
