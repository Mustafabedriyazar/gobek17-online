# G17MP/1 v166 Transport Delivery Note

The G17MP/1 wire protocol and server-authoritative action semantics are unchanged from v165.

v166 changes how the browser transport is delivered and gated:

1. SDK and table bridge are inlined into `index.html`, so Android `content://` preview does not lose the bridge.
2. `file:`, `content:` and other non-HTTP(S) preview contexts have no implicit authority endpoint.
3. Create/join UI requires a successful G17 `/health/live` probe. Failure produces an explicit offline-server modal and does not block offline gameplay.
4. HTTP(S) deployments continue to use explicit `?server=`, saved endpoint, or same-origin authority in that order.

No action payload, revision, fencing, account, reconnect, chat or moderation protocol rule changed.
