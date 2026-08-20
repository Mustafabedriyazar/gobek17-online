# GÖBEK17 — G17MP/1 v159 compatibility note

G17MP/1 action names and request envelopes are unchanged.

## Snapshot ledger addition

Each item in `snapshot.ledger` now carries the canonical penalty ordinal:

`{ hand, ord, type, source, target, amount }`

`ord` is backward-compatible additive metadata. It is used by the browser bridge to distinguish repeated penalties with otherwise identical values and to detect exactly which events are new when the server's rolling ledger window advances.

## Client presentation behavior

The table transport bridge compares the previous and current authoritative ledger windows. Newly committed entries are seat-mapped and sent into the same penalty notification UI used by local presentation mode. Existing ledger history is not replayed on initial connection/reconnect.

No gameplay authority moves to the client; the server remains authoritative.
