# GÖBEK17 / G17MP/1 — v165 Recovery, Chat, Profile Ops Delta

**Parent:** v164 account/security/moderation
**Build:** `gobek17-165-recovery-chat-profile-ops`

Gameplay action names and canonical engine semantics are unchanged.

## Account recovery

Registration returns eight one-time backup recovery codes. Only account-bound SHA-256 recovery hashes are persisted.

New endpoints:

- `POST /v1/auth/recover` — `{username,recoveryCode,newPassword}`
- `POST /v1/auth/password` — authenticated password change
- `POST /v1/auth/recovery-codes` — authenticated code rotation

Successful recovery/password change revokes old account sessions. Recovery rotates the backup code set.

## Server-authoritative chat

New seat-authenticated endpoint:

- `POST /v1/rooms/:roomId/chat` — `{text,kind}`

Requirements:

- valid active seat bearer,
- current `X-G17-Connection` claim,
- live game-ban check,
- server-enforced mute check,
- per-account/IP chat rate limit.

The server owns sender seat/name/timestamp; client-supplied identity fields are ignored. Text is control-character stripped, whitespace-normalized and capped at 180 characters. Rolling chat history is persisted with the room and delivered in ordered snapshots as:

```json
{"chat":{"seq":12,"messages":[...]}}
```

A chat-only state change advances `eventSeq` but does not mutate the canonical gameplay `rev` or engine state.

Admin:

- `POST /v1/admin/mod/chat-delete`

Player reports now accept category `CHAT` and optional `messageId`.

## Player profile / stats / wallet foundation

New endpoints:

- `GET /v1/profile/me`
- `POST /v1/profile/me`
- `GET /v1/players/:publicId/profile`

Private owner profile includes wallet; public profile omits wallet.

Completed matches are written once to account statistics using an idempotent match key. Retried snapshots/actions cannot double-count a completed match.

Admin wallet operation:

- `POST /v1/admin/mod/wallet`

It accepts `txId`, `chipsDelta`, `gemsDelta`, `reason`; the same `txId` cannot apply twice. v165 intentionally does **not** invent a gameplay chip/gem settlement formula.

## Client storage

v165 account/room session keys migrate to `*_v165`. Seat bearer remains sessionStorage-only; localStorage keeps only the non-secret room resume hint. Legacy v164 non-secret hints can be used once for migration and are then scrubbed.
