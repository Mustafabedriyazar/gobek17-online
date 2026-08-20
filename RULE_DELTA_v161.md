# OKEY17 / GÖBEK17 — KANONİK UI DELTA v161

**Taban:** `gobek17-160-end-overlay-priority`
**Build:** `gobek17-161-final-gameplay-ui-polish`
**Tür:** Presentation/UI polish. Canonical gameplay semantics unchanged.

## 1. Açılmış per okunabilirliği
- Açılmış per plakalarının derinlik/kontrastı artırıldı.
- Plakanın gerçek sol ve sağ endpoint'leri küçük ışık işaretleriyle görünür hale getirildi.
- İşlek sonrası endpoint/plaka reaksiyonu daha okunaklıdır.
- Gerçek `.tr.mld` düğümlerine transform veya geometry animasyonu eklenmedi; v154 atomic meld reflow ve v157 immutable meld body guard aynen korunur.

## 2. %15 büyük ıstaka polish
- Kanonik `78×108` rack tile ölçüsü değişmedi.
- Taş yüzü, temas gölgesi, seçim çerçevesi ve ahşap raf teması görsel olarak netleştirildi.
- `PITCH`, `SLOT0`, `ROWY` ve rack geometri değerleri değişmedi.

## 3. İşlek animasyonu
- İşlek sunum clone'una daha belirgin ışık izi ve landing okunabilirliği eklendi.
- Animasyon yalnız `.motion-flight.process-flight` sunum clone'unda çalışır.
- Açılmış gerçek per taşları animasyon/transform otoritesi almaz.

## 4. Ceza ekranı
- 3 saniyelik merkez ceza ekranının hiyerarşisi güçlendirildi: metal üst çizgi, iç çerçeve ve sebep rozeti.
- v159 FIFO ceza kuyruğu ve v160 end-overlay önceliği değişmedi.

## 5. Bitiş panosu
- `DEVAM ET / BAŞLAT` birincil aksiyonu daha belirgin hale getirildi.
- Buton sunumu kısa ve lokal animasyondur; end-flow mantığı değiştirilmedi.

## 6. Canlı Rapor
- Mini kart, ceza rakamları ve son olay satırının kontrastı/okunabilirliği artırıldı.
- Ledger, ceza hesapları ve multiplayer eşliği değişmedi.

## 7. Kural motoru
Bu build'de oyun motoru ve stratejik bot blokları v160 ile byte-identical kalmıştır.
