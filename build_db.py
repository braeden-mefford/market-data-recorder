# build_db.py
# Loads the captured data into a DuckDB database file (market.duckdb) with a
# real table, so it can be queried like a normal database. DuckDB is an embedded
# column store, so there is no server to set up and the whole database is one
# file on disk.
#
#     python build_db.py

import duckdb

DB_FILE = "market.duckdb"
PARQUET = "capture.parquet"


def main():
    con = duckdb.connect(DB_FILE)

    # define the table explicitly so the schema is clear
    con.execute("drop table if exists book_changes")
    con.execute("""
        create table book_changes (
            wall_ms    bigint,    -- when the recorder saw the change (unix ms)
            ticker     varchar,   -- market id
            seq        bigint,    -- per market sequence number from shared memory
            yes_bid    double,    -- best yes bid in dollars
            yes_ask    double,    -- best yes ask in dollars
            yes_levels varchar,   -- top yes book levels as a json array
            no_levels  varchar    -- top no book levels as a json array
        )
    """)
    con.execute("insert into book_changes select * from read_parquet('%s')" % PARQUET)

    n = con.execute("select count(*) from book_changes").fetchone()[0]
    print("loaded", n, "rows into", DB_FILE, "table book_changes")

    # a couple of example queries so the database is actually used
    print("\nupdates per market:")
    for row in con.execute(
        "select ticker, count(*) as updates "
        "from book_changes group by ticker order by ticker").fetchall():
        print("  ", row)

    print("\naverage spread per market (in cents):")
    for row in con.execute(
        "select ticker, round(avg(yes_ask - yes_bid) * 100, 2) as spread_cents "
        "from book_changes group by ticker order by ticker").fetchall():
        print("  ", row)

    con.close()


if __name__ == "__main__":
    main()
