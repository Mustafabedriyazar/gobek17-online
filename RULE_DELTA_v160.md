# OKEY17 / GÖBEK17 — KANONİK UI / END-FLOW DELTA v160

**Taban:** `gobek17-159-conflict-guard-hardening`
**Build:** `gobek17-160-end-overlay-priority`

## El sonu ekranı mutlak öncelik

v160 oyun kurallarını değiştirmez. El `handOver` olduğunda bitiş raporu ekranı artık tüm transient ceza katmanlarından önceliklidir.

- El bittiği anda aktif merkezi ceza ekranı kapatılır.
- Bekleyen ceza ekranı FIFO kuyruğu temizlenir.
- Eski büyük-ceza flash katmanı kapatılır.
- Canlı Rapor pulse durumu temizlenir.
- `endOverlay` z-index 170 → 260 yapıldı.
- `notifyPenaltyEvent()` el bittikten veya bitiş panosu açıldıktan sonra yeni transient ceza ekranı başlatmaz.
- Bitiş raporundaki ceza verisi korunur; yalnız transient ekranın raporu örtmesi engellenir.

## DEVAM ET / BAŞLAT

- Normal el sonu: `DEVAM ET` → sonraki ele geçer.
- Maç sonu: `BAŞLAT` → yeni oyunu başlatır.
