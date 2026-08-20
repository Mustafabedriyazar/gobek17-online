# OKEY17 / GÖBEK17 — KANONİK DELTA v163

**Base:** `gobek17-162-multiplayer-production-hardening`
**Build:** `gobek17-163-production-runtime-foundation`

v163 introduces **no gameplay-rule change**.

Preserved unchanged:

- opened meld immutability,
- maximum two processed additions per series meld,
- illegal middle/body process ×10 penalty,
- side-take ×10 semantics,
- central penalty screen / Live Report behavior,
- end-overlay priority,
- +15% rack geometry,
- final UI polish,
- canonical match/end engine and bot strategy.

v163 changes only multiplayer/runtime infrastructure: optional Redis shared state, fenced room ownership, owner-aware retry, production runtime guards, health/readiness/metrics, and deployment packaging.
