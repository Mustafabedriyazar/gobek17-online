# GÖBEK17 G17MP/1 — v153 side-take semantics

Protocol envelope and action names remain compatible with v152.

## Changed DISCARD semantics while `self.pending` exists

- `DISCARD { uid: pending.uid }` => **RED**. The side-taken tile cannot be thrown to the right.
- `DISCARD { uid: <another rack tile> }` => server atomically:
  1. moves the pending side-taken tile into the taker's rack,
  2. charges the taker `tileValue × 10`,
  3. clears pending,
  4. discards the requested normal rack tile,
  5. advances the turn normally.
- `TAKE_PENALTY` / `TAKE_CANCEL` => pending tile returns to source discard, taker pays the same `tileValue × 10`, turn ends.
- Legal OPEN / PROCESS use of pending remains unchanged: pending is consumed by the legal move and taker pays the same `tileValue × 10`.

No new network action type is required. Snapshots continue to expose the pending tile only to the owning seat; after keep+discard it appears as a normal rack tile.
