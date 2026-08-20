# G17MP/1 — v152 transport note

Transport/action envelope v151 ile uyumludur. Oyun-kural semantiği için `RULE_DELTA_v152.md` kanoniktir. Özellikle Sahte Okey, immutable meld ve side-take return davranışı server authority tarafından v152 motorunda uygulanır.

# OKEY17 / GÖBEK17 — G17MP/1 TABLE TRANSPORT BRIDGE (v152)

## Status
Implemented in `gobek17-151-table-transport-bridge` on top of the canonical v150 server-authoritative foundation.

v151 does **not** rewrite the OKEY17 gameplay engine. The v149/v150 canonical browser engine and the v148/v149 strategic bot block remain byte-identical. v151 connects the existing private-room table UI to the authoritative Node room service while keeping normal Quick/Salon offline play local and unchanged.

## Authority boundary
- The **server is the only gameplay mutation authority** in an active network room.
- The browser `E.st` object is only a presentation/calculation mirror hydrated from that seat's projected server snapshot.
- Online table actions never call the local mutation methods (`E.draw`, `E.take`, `E.open`, `E.process`, `E.discard`, `E.startHand`) as authority.
- Server action legality, turn ownership, penalties, hand ending and invariants remain canonical.
- After every committed human/bot action the authority runs `E.check()`.

## Seat perspective
The server keeps physical seats 0..3. Each device keeps the existing UI convention that **the local human is bottom/seat 0**.

Projection:

```text
localSeat = (serverSeat - selfServerSeat + 4) % 4
```

Therefore the local partner remains seat 2 in TEAM mode and turn direction is preserved visually. TEAM snapshots project to `[[0,2],[1,3]]` on every client.

## Hidden information
A network client receives identities only for:
- its own rack / pending tile,
- public melds,
- public current discard,
- public indicator/Okey information.

Opponent/partner racks are represented in the local presentation mirror only by private local placeholders derived from `rackCount`; those placeholder UIDs are **not supplied by the server**. Deck/discard history placeholders likewise expose counts, not hidden deck identities.

The server snapshot also exposes only sanitized public ledger records (`hand`, `type`, `source`, `target`, `amount`), never hidden tile identities.

## Private-room UI path
`ARKADAŞLA OYNA` → `ODA KUR` or `ODA KODU GİR` now uses `window.G17NET`.

- `ODA KUR`: creates a real TEAM/CASUAL authority room and joins the creator.
- `ODA KODU GİR`: joins an existing authority room.
- Waiting lobby shows actual seat occupancy 1/4..4/4.
- Room codes are displayed as `G17-XXXXXXXX`.
- When all four seats are occupied, the authority starts the match and all clients launch the existing table from their own projected snapshot.
- `DAVET` currently exposes/copies the room code; OS/share/deep-link provider integration is a later product layer.

## Online action bridge
The existing table controls delegate to the authority while `G17NET.active()` is true:

- deck → `DRAW`
- previous discard → `TAKE_DISCARD`
- side-pick penalty continuation → `TAKE_PENALTY`
- first open → `OPEN_ATTEMPT`
- later per opening → `OPEN`
- process/feed → `PROCESS`
- discard / finish tile → `DISCARD`
- end report continue → `NEXT_HAND`
- final report new game → `NEW_MATCH`

Drag-to-discard and drag-to-process restore the local visual tile to its pre-drag source before the request is sent. The authoritative snapshot then performs the visual reconciliation. This prevents speculative local state from becoming gameplay truth.

## Revision and idempotency safety
Each logical table action pins:
- one `clientActionId`, and
- the snapshot revision on which the user made the action.

If HTTP delivery has an unknown outcome (for example the server committed but the response was lost), the bridge reconnects and retries **the same action id with the same base revision**. The server's idempotency cache therefore returns the already committed result instead of applying the move twice.

`STALE_REV` is **not automatically replayed against newer state**. The current snapshot is accepted and the player may make a fresh decision. This prevents a delayed tap from silently becoming a move in a later game state.

## Reconnect / takeover
- SDK auth session is stored in `sessionStorage` for page reload recovery.
- Reload/reconnect reclaims the same room, seat and bearer token when still valid.
- SSE loss is detected server-side; after the grace period a disconnected seat becomes temporary bot-controlled.
- Reconnect disables bot control and returns a fresh per-seat snapshot.
- A newer connection lease replaces an older tab/device; the old connection receives `SESSION_REPLACED` for actions.
- TOURNAMENT keeps the v150/v146 90-second server-internal `FORFEIT_HAND` behavior. Casual/Ranked do not use tournament forfeit by default.

## Browser SDK
`multiplayer-client.js` exports `window.G17MP.Client`.

`multiplayer-bridge.js` exports `window.G17NET` and owns private-room UI/transport/presentation projection.

Endpoint selection order:
1. `?server=https://authority.example`
2. `localStorage.g17_mp_endpoint`
3. current `location.origin`

This allows one-host deployment or a static client pointing at a separate HTTPS authority host.

## Service worker boundary
`/v1/*` and `/health` bypass the PWA cache. `multiplayer-client.js` and `multiplayer-bridge.js` are cached static assets. API JSON and SSE must never be served from Cache Storage.

## Deployment boundary
A Netlify Drop is a static client and cannot execute `server/server.cjs` by itself.

For real multiplayer, deploy the included zero-runtime-dependency Node 18+ authority service on a Node-capable HTTPS host and either:
- serve the client from that same process, or
- point the static client to it using `?server=...` / `g17_mp_endpoint`.

Set `G17_ALLOWED_ORIGIN` to the real client origin in production.

## Deferred beyond v151
- persistent/distributed room registry (v151 registry is in-memory, single process),
- account auth/database,
- durable reconnect across server restarts,
- ranked queue/rating persistence,
- permanent partner persistence,
- tournament bracket service,
- chat/voice infrastructure,
- analytics/anti-collusion storage,
- multi-instance room routing/pub-sub.

These should be layered on the authority contract rather than reintroducing browser authority.
