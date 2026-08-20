# GÖBEK17 v167 — GitHub/Vercel deploy root

This repository root is deployable as a plain Node.js HTTP server on Vercel.

- `server.cjs` starts the canonical authority in `server/server.cjs`.
- `index.html` includes the multiplayer client/bridge and defaults to `https://gobek17-online.vercel.app` when opened locally.
- Closed-beta defaults: one replica, file/ephemeral persistence, required username/password auth, registration enabled, moderation disabled.
- For durable production, set Redis and security environment variables from `server/.env.example` and v163–v166 protocol docs.

Important: Vercel ephemeral filesystem is not durable. Accounts/rooms can reset between instances until Redis is configured.
