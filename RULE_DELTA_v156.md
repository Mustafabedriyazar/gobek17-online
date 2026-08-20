# OKEY17 / GÖBEK17 — UI DELTA v156

**Taban:** `gobek17-155-live-side-take-penalty-notify`
**Build:** `gobek17-156-penalty-screen-live-sync`

## Ayrı ceza ekranı

v155'teki küçük oyuncu-yanı ceza bildirimi yeterince belirgin olmadığı için ana bildirim yolu değiştirilmiştir.

- İşlek (`PROCESS`) cezası oluştuğunda ortada ayrı, büyük ceza ekranı açılır.
- Çift işlek (`PROCESS_PAIR`) cezası aynı ayrı ekranda `×20` işaretiyle görünür.
- Yandan taş x10 cezaları (`DISCARD_TAKEN_USED`, `DISCARD_TAKE_UNUSED`, `DISCARD_TAKE_KEPT`) da aynı büyük ekranı kullanır.
- Ekranda cezayı yiyen oyuncunun adı, ceza tutarı ve ceza sebebi gösterilir.
- Masa arka planı belirgin biçimde kararır.
- Ekran tam 3 saniye sonra otomatik kapanır.
- Alt süre çubuğu 3 saniyelik kapanışı görsel olarak gösterir.
- Canlı Rapor mini kartı aynı anda pulse alır.
- Canlı Rapor ceza feed'i aynı motor LED olayı üzerinden eş zamanlı güncellenir.

Motor kuralları değiştirilmemiştir.
