# Real-Time Data Collection

## How the prototype collects data now

The recorder does not talk to any exchange. It only reads the shared memory
file and writes out what changed. Something else has to fill the shared memory.
In this prototype that is the engine:

- fake_engine.py makes up prices (offline demo)
- live_engine.py pulls real order books from Kalshi over the REST API about
  once a second

Polling REST once a second is close to real time but not truly live. Between
two polls the book can change several times, and the recorder only sees the
state at each poll, not every change in between.

## How it becomes real time

The key design choice is that the recorder is decoupled from the data source
through shared memory. The recorder reads slots and watches each slot's sequence
number. It does not care how those slots get filled. So making the system real
time only changes the engine. The recorder, the JSONL log, the DuckDB database,
and the queries all stay the same.

A real time engine would:

1. Open a WebSocket connection to the exchange instead of polling REST.
2. Subscribe to the order book delta channel for the markets we care about.
3. Apply the first snapshot to the shared memory slot, then apply each delta the
   moment it arrives (well under a second), bumping the slot's sequence number
   each time under the same seqlock.

Because the sequence number still changes on every update, recorder.py captures
every change with no modification. The recorder's poll interval can be lowered
so it keeps up with the faster updates.

## Why the prototype uses a simple engine

The production system this prototype is based on already collects data this way,
with a WebSocket feed writing into shared memory. That engine is proprietary, so
this class project uses a simple REST or synthetic engine in its place. The part
the project is about, the recording and storage layer, behaves the same either
way because it sits behind the shared memory boundary.
