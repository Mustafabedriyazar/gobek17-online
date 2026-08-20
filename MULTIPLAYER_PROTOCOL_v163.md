# G17MP/1 — v163 Production Runtime Delta

Base: v162. Gameplay action names and canonical rule semantics are unchanged.

## Redis room ownership

Optional `G17_STORE=redis` mode stores authoritative room snapshots in shared Redis. Each room is controlled by one leased owner instance. Ownership uses a monotonic fencing token; a stale owner cannot save after a newer owner acquires the room.

Non-owner response:

```json
{
  "ok": false,
  "err": "ROOM_OWNER_MISMATCH",
  "ownerUrl": "https://authority-a.example",
  "ownerInstanceId": "authority-a"
}
```

The v163 SDK retries once against `ownerUrl` and persists the new endpoint for reconnect.

## Failover

After lease expiry another instance may:

1. acquire a newer fence,
2. load `G17ROOM/2` room state from Redis,
3. restore the engine,
4. run canonical engine invariant validation,
5. give disconnected seats the existing reconnect grace,
6. fall back to the existing bot takeover behavior when required.

## Durability ordering

In Redis mode room broadcast is deferred while a mutating join/action/disconnect transaction is being persisted. The authoritative room state is fenced and written before the deferred local snapshot broadcast is flushed.

## Operations

New runtime endpoints:

- `/health/live`
- `/health/ready`
- `/metrics`

Protocol discovery exposes the v163 runtime feature list. Revision lock, `clientActionId`, fingerprint mismatch protection, `eventSeq`, hidden-rack projection, reconnect semantics, and v162 idempotent join remain unchanged.
