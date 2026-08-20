# OKEY17 / GÖBEK17 — KANONİK DELTA v162

**Taban:** `gobek17-161-final-gameplay-ui-polish`
**Build:** `gobek17-162-multiplayer-production-hardening`

## Gameplay

Bu build yeni masa kuralı eklemez ve mevcut gameplay semantiğini değiştirmez. v161 ve önceki kanonik kurallar aynen korunur.

## Multiplayer / backend hardening

- Tek-node oda/maç state'i JSON tabanlı atomik persistence ile Node restart sonrasında geri yüklenir.
- Restore sırasında canonical engine invariant kontrolü zorunludur.
- Restart sonrası oyunculara reconnect için recovery grace verilir; dönmeyen koltuklarda mevcut bot takeover davranışı devreye girer.
- Seat bearer token'ları diskte yalnız SHA-256 hash olarak saklanır.
- `clientActionId` idempotency cache'i restart sonrasında da korunur.
- Aynı `clientActionId` farklı action/revision fingerprint'i ile tekrar kullanılırsa `ACTION_ID_REUSE_MISMATCH` RED.
- Join akışı `clientJoinId + client-generated token` ile idempotenttir; kaybolan HTTP join cevabı aynı kimlikle güvenle retry edilebilir.
- Replaced connection/SSE eski private snapshot'ları alamaz; `/snapshot` da aktif connection claim ile korunur.
- Snapshot'lara monotonic `eventSeq` eklenmiştir. Client daha eski rev/event/time snapshot'larını reddeder.
- HTTP action çağrılarında 12 saniye client timeout vardır; belirsiz teslimat table bridge tarafından aynı action id + aynı base rev ile retry edilir.
- Inactive rooms TTL ile temizlenir.

## Deployment boundary

v162 **single-process / single-node durable authority** seviyesidir. Persistent disk/volume gerekir. Çoklu replica, distributed room routing, Redis/Postgres coordination, account identity ve managed deployment sonraki altyapı katmanıdır.
