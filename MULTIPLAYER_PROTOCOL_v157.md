# G17MP/1 — v157 protocol delta

Build: `gobek17-157-immutable-meld-body-guard`

G17MP/1 envelope / revision / idempotency semantics are unchanged.

## New authoritative action

`BAD_PROCESS_ATTEMPT`

Payload:
- `uid`: attempted tile UID
- `meldId`: immutable opened meld id
- `reason`: client-visible diagnostic text

Server behavior:
- validates active ACTION turn, opened player, drawn tile state, tile ownership/pending ownership, and meld existence;
- commits `BAD_PROCESS_ATTEMPT` penalty to the acting player for represented tile value ×10;
- does not mutate the meld or move the attempted tile;
- increments room revision through the normal authoritative action pipeline;
- ledger snapshot contains `{type:"BAD_PROCESS_ATTEMPT", source, target, amount}`.

The client is never authoritative for this penalty while a private-room server session is active.
