# shm_layout.py
# This is the shared definition of the little shared-memory file that both
# the fake engine (writer) and the recorder (reader) use. I split it out so
# the two programs can't disagree about the byte offsets.
#
# It is WAY smaller than the real production shm on purpose - this is just a
# class prototype. Real one has ~50 price levels and a hash table index, here
# I keep 5 levels per side and just loop over the slots.

import struct

SHM_PATH = "market_shm.bin"   # on the real server this would be /dev/shm/...

MAGIC = 0x4B534831     # just a number so the reader can check the file is ours
NUM_SLOTS = 6          # how many markets we pretend to track
TICKER_LEN = 64        # real kalshi tickers run ~30 chars, 24 was too short
NUM_LEVELS = 5         # order book depth we keep per side

# header at the very front of the file = magic number + how many slots
HEADER_FMT = "<II"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# the seq counter sits in its own 8 bytes at the front of each slot. it has to
# be separate so we can do the "seqlock" trick (write it odd, write the data,
# write it even again).
SEQ_FMT = "<Q"
SEQ_SIZE = struct.calcsize(SEQ_FMT)   # 8 bytes

# everything else in a slot: the ticker, best bid/ask, then 5 yes levels and
# 5 no levels, each level is a (price, size) pair of doubles.
FIELDS_FMT = "<" + str(TICKER_LEN) + "s" + " dd" + " dd" * NUM_LEVELS + " dd" * NUM_LEVELS
FIELDS_SIZE = struct.calcsize(FIELDS_FMT)

SLOT_SIZE = SEQ_SIZE + FIELDS_SIZE
TOTAL_SIZE = HEADER_SIZE + NUM_SLOTS * SLOT_SIZE


def slot_offset(i):
    # byte offset where slot i starts
    return HEADER_SIZE + i * SLOT_SIZE
