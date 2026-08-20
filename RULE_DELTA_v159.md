# OKEY17 / GÖBEK17 — v159 CONFLICT GUARD HARDENING

**Parent canonical:** `gobek17-158-rack-plus15.zip`  
**Build:** `gobek17-159-conflict-guard-hardening`

v159 is a hardening/regression build. It does **not** change canonical gameplay rules.

## Fix 1 — canonical build/cache identity

v158 had been promoted from its preview package, but the internal `BUILD`, service-worker cache namespace, and multiplayer client/bridge build labels still contained `gobek17-158-rack-plus15-preview`.

v159 normalizes all active build/cache labels to `gobek17-159-conflict-guard-hardening`.

## Fix 2 — penalty screen cannot overwrite a simultaneous second penalty

A single logical action can create more than one penalty. Example:
- a side-taken tile is processed into an opponent meld;
- the meld owner receives the PROCESS penalty;
- the taker also receives the side-take ×10 self-penalty.

Before v159, the second notification replaced the first central penalty screen immediately.

v159 makes the central penalty screen queued:
- each supported penalty receives its own full 3-second presentation;
- a second penalty waits instead of overwriting the first;
- Live Report is updated immediately for all ledger entries even while a screen is queued.

Supported events remain:
`PROCESS`, `PROCESS_PAIR`, `BAD_PROCESS_ATTEMPT`, `DISCARD_TAKEN_USED`, `DISCARD_TAKE_UNUSED`, `DISCARD_TAKE_KEPT`.

## Fix 3 — server-authoritative multiplayer penalty UI sync

The server-authoritative bridge hydrated the canonical penalty ledger into the browser mirror, but new remote ledger entries were not independently forwarded into the penalty-screen notification pipeline.

v159 adds snapshot-ledger delta detection and forwards only newly committed penalty events to the same UI notification pipeline.

For exact de-duplication, the authoritative snapshot ledger now includes the canonical `ord` field from each engine penalty entry. This prevents two visually identical penalties from being mistaken for the same event when the rolling 50-entry ledger window advances.

## UI cleanup

The stale hint `Peri büyütmek için per taşına basılı tut` was removed because opened meld long-press mutation/zoom authority was removed in v152. The replacement hint states the current rule: processing is endpoint-only and opened melds do not change.

## Preserved rules

All v158 and earlier canonical rules remain unchanged, including:
- opened meld immutability;
- no Okey/joker replacement inside an opened meld;
- illegal middle process = represented tile ×10 self-penalty;
- maximum two processed tiles per opened series meld;
- v153 side-take keep/return semantics;
- v156 separate 3-second penalty screen;
- v158 +15% rack tile geometry.
