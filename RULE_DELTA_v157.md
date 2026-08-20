# OKEY17 / GÖBEK17 — KANONİK KURAL DELTA v157

**Taban:** `gobek17-156-penalty-screen-live-sync`
**Build:** `gobek17-157-immutable-meld-body-guard`

## 1. Açılmış per gövdesi tam dokunulmaz

- Açılmış perin mevcut taşları v152 kuralı gereği değişmez.
- Bu koruma artık yalnız sol/sağ endpoint kontrolüyle sınırlı değildir; perin **tüm görsel gövdesi** PROCESS intent alanıdır.
- Bir taş perin arasına, üstüne veya legal olmayan ucuna bırakılırsa FREE grid taşına dönüşemez.
- Okey/joker perin içinde bir değeri temsil ediyor olsa bile sonradan doğal taşla değiştirilmez.
- Örnek: mavi `10-11-Okey(12)-13` açılmışsa mavi `12` perin ortasına konulamaz; per aynen kalır.

## 2. Hatalı işlek cezası

- Açılmış pere illegal işlek bırakma denemesi `BAD_PROCESS_ATTEMPT` olarak kaydedilir.
- Denemeyi yapan oyuncu, denediği taşın temsil edilen değeri ×10 kadar **kendi ceza hanesine** ceza yer.
- Örnek: mavi 12 illegal olarak perin ortasına bırakılırsa **120 ceza**.
- Taş kaynağında kalır; per taşları ve sırası değişmez; tur otomatik bitmez.
- v156 ayrı ceza ekranı aynı anda `HATALI İŞLEK · TAŞ ×10` olarak görünür ve Canlı Rapor ledger'ına düşer.

## 3. Izgara / per güvenlik zarfı

- FREE board yerleştirme sistemi artık yalnız meld taş AABB'lerini değil, açılmış perin plaka + küçük çevre güvenlik zarfını da obstacle kabul eder.
- Böylece serbest taşlar perin hemen üstüne/altına veya plaka içine yapışıp yamuk bir birleşim görüntüsü oluşturamaz.
- Grid kareleri hâlâ yalnız görsel lattice'dir; taşlar karelere zorla snap edilmez ve taş boyutu grid karesine göre değiştirilmez.

## 4. Değişmeyen kurallar

- Açılmış perler bölünmez / yeniden sıralanmaz / taşları sökülmez.
- SERİ pere açılıştan sonra toplam en fazla 2 işlek eklenebilir.
- Legal işleme yalnız gerçek sol/sağ endpoint üzerinden yapılır.
- v153 yandan taş ×10 kuralları ve v156 3 saniyelik ayrı ceza ekranı korunur.
