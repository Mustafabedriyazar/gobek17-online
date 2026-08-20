# G17MP/1 — v162 Production Hardening Delta

Protocol adı değişmedi: `G17MP/1`.

## Action envelope

Mevcut envelope korunur:
- `expectedRev`
- `clientActionId`
- `action`

v162 ek davranış:
- Server `clientActionId` için `SHA-256({expectedRev, action})` fingerprint tutar.
- Aynı logical retry aynı cached sonucu döndürür.
- Aynı id farklı fingerprint ile gelirse `ACTION_ID_REUSE_MISMATCH` döner.
- Idempotency kayıtlarının son bölümü room persistence içine yazıldığı için process restart sonrasında da duplicate commit engellenir.

## Join envelope

SDK join isteğine iki alan ekler:
- `clientToken`: client-generated güçlü seat bearer token
- `clientJoinId`: logical join id

Server yalnız token hash'ini saklar. Aynı join id + aynı token retry edilirse aynı seat döner; farklı token ile aynı join id `JOIN_ID_REUSE_MISMATCH` verir.

## Snapshot ordering

Snapshot alanlarına `eventSeq` eklendi. Browser projection:
1. düşük `rev` snapshot'ı reddeder,
2. eşit rev'de daha düşük `eventSeq` snapshot'ı reddeder,
3. eşit rev/event durumunda eski `serverTime` snapshot'ı reddeder.

Bu koruma HTTP action response ile SSE snapshot yarışında client state'in geriye gitmesini engeller.

## Connection replacement

Bir seat için yeni connection claim eski connection'ı replace eder. Eski SSE subscriber artık yeni private snapshot almaz ve eski connection id ile `/snapshot` veya `/action` kullanımı `SESSION_REPLACED` olur.

## Durable room state

Server state file şunları taşır:
- room/mode/context/revision,
- canonical engine transaction snapshot,
- seed commit/reveal audit,
- seat occupancy/name + hashed token,
- action idempotency tail,
- event sequence/history tail,
- counters/invariant metadata.

Runtime-only connection IDs ve subscriber objeleri persistence'a yazılmaz.
