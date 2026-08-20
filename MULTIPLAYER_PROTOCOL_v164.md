# G17MP/1 — v164 Account / Security / Moderation Delta

**Parent:** v163 Production Runtime Foundation  
**Build:** `gobek17-164-account-security-moderation`

v164 does **not** change canonical gameplay actions or snapshot game semantics. It adds an account-authenticated platform boundary around room admission and a secure recovery/moderation path.

## 1. Account authentication

Production defaults to `G17_AUTH_MODE=required`.

Endpoints:

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `GET /v1/auth/me`
- `POST /v1/auth/logout`

Passwords are stored only as salted `scrypt` hashes. Access/refresh credentials are random opaque tokens; only SHA-256 token hashes are persisted.

Refresh is rotating: consuming a refresh token invalidates that refresh token and its paired previous access session.

## 2. Account bearer vs seat bearer

Before joining a room, `Authorization: Bearer <account-access-token>` authorizes room create/join/reclaim operations.

After joining, normal G17MP gameplay transport continues to use the per-room **seat bearer token**. Seat bearer tokens are still hashed at rest.

Authenticated join binds the seat to:

- internal `accountId` (never emitted as public lobby identity),
- public opaque `playerId`,
- server-owned account display name.

The client-supplied room name is ignored for authenticated players.

## 3. Secure seat reclaim

`POST /v1/rooms/:roomId/reclaim`

Requires account auth and body:

```json
{"clientToken":"<new-client-generated-seat-secret>"}
```

If that account already owns a seat in the room, authority rotates the seat token and returns the private snapshot. The old seat bearer stops authenticating immediately.

The browser bridge stores the active seat secret only in `sessionStorage`; `localStorage` stores only a non-secret resume hint. Legacy v162/v163 localStorage seat secrets are removed on v164 startup.

## 4. Moderation

Authenticated report:

`POST /v1/mod/report`

```json
{
  "roomId":"AB12CD34",
  "reportedSeat":1,
  "category":"HARASSMENT",
  "note":"optional note"
}
```

The reporter must occupy that room and the target must be another authenticated seat.

Admin endpoints require `X-G17-Admin-Token`:

- `GET /v1/admin/mod/reports`
- `POST /v1/admin/mod/sanction`
- `POST /v1/admin/mod/clear`

A live game ban is checked on protected room operations, not just login. Applying a ban revokes account access/refresh sessions.

`muteUntil` is stored as moderation metadata only; v164 does not claim server-side chat-mute enforcement because chat transport is not yet server authoritative.

## 5. Production guards

Production readiness rejects:

- auth modes other than `required`,
- password minimum below 10,
- moderation enabled without a 32+ character admin secret,
- all pre-existing v163 unsafe runtime conditions.

## 6. Compatibility

Existing G17MP gameplay action names remain unchanged. Room state remains compatible with previous `G17ROOM/2`; v164 adds optional seat `accountId` / `publicId` fields. Guest seats remain supported only in non-production optional-auth mode.
