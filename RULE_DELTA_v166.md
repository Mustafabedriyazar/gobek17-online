# RULE DELTA v166 — Single-file Preview Safe

Parent: v165.

## Canonical gameplay
No gameplay-rule change. Engine and strategic bot blocks must remain byte-identical to v165.

## Presentation / delivery change
- `multiplayer-client.js` and `multiplayer-bridge.js` are embedded directly in `index.html`.
- Opening `index.html` from Android file providers (`content://`) or local file preview no longer depends on sibling JS loading.
- Private-room actions probe `/health/live` before showing account/room UI.
- If no real G17 authority server is reachable, the game remains usable offline and shows `ONLINE SUNUCU BAĞLI DEĞİL` for online-only features.
- Normal HTTP/HTTPS deployment and explicit `?server=https://...` backend selection remain supported.

This is a packaging/runtime-availability fix only.
