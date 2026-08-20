# OKEY17 / GÖBEK17 — KANONİK KURAL / UI DELTA v155

**Taban:** `gobek17-154-atomic-meld-reflow`
**Build:** `gobek17-155-live-side-take-penalty-notify`

## Yandan taş x10 ceza — anlık ekran bildirimi

Bu build motor kurallarını değiştirmez; v153/v154 side-take semantics korunur.

Yeni UI davranışı:
- `DISCARD_TAKEN_USED`, `DISCARD_TAKE_UNUSED`, `DISCARD_TAKE_KEPT` cezaları oluştuğu anda
  cezayı yiyen oyuncunun tarafında anlık görsel bildirim çıkar.
- Bildirim yaklaşık **3 saniye** görünür ve sonra otomatik kaybolur.
- Metin örnekleri:
  - `YANDAN AÇTI · x10`
  - `SOLA GERİ VERDİ · x10`
  - `ELİNDE TUTTU · x10`
- Canlı Rapor mini kartı aynı anda pulse alır.
- Canlı Rapor feed'i eş zamanlı güncellenir ve son 3 ceza hareketini gösterir.

## Not
- Bu delta presentation/UI katmanıdır; canonical oyun motoru, açık per kuralları ve side-take ceza semantiği değişmez.
