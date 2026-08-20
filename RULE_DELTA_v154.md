# OKEY17 / GÖBEK17 — KANONİK DELTA v154

**Taban:** `gobek17-153-side-take-keep-or-return`  
**Build:** `gobek17-154-atomic-meld-reflow`

## Amaç

v154 bir **presentation/geometry düzeltmesidir**. Oyun motoru, bot mantığı ve v152/v153'te kilitlenen oyun kuralları değişmez.

## Açılmış per — atomik geometry

- Gerçek `.tr.mld` taşları artık `left/top/width/height` geometry transition taşımaz.
- `flowZone()` bir işlek sonrası per alanının ölçek kademesini veya satırını değiştirdiğinde bütün gerçek per taşları **aynı karede son koordinatlarına** yerleşir.
- Sinematik işlek hareketi korunur; hareket yalnız `motion-flight` presentation clone üzerinde oynar.
- Bir per alan sınırına sığmadığında mevcut `flowZone()` paketleme otoritesi perin tamamını uygun satıra/ölçeğe taşır; per kendi içinde bölünmez ve taşlar farklı geometry zamanlarında hareket etmez.

## Kök neden

v153'te `.tr` sınıfı `left/top` için 160 ms transition taşıyordu. Alan sınırı aşıldığında örneğin 47×65 taş kademesinden 40×56 kademesine geçişte `width/height` anında değişirken eski taşların `left/top` konumları transition ile geriden geliyordu; yeni işlenen taş ise final koordinatında doğuyordu. Bu, özellikle Android/düşük FPS cihazlarda perin kısa süre üst üste veya yamuk görünmesine neden oluyordu.

## Korunan kurallar

- Açılmış per immutable: sökme, taşıma, yeniden sıralama, split yok.
- Bir SERİ pere toplam en fazla 2 işlek (`processAdds <= 2`).
- v153 yandan taş kuralı aynen korunur: alınan taşın değeri ×10 ceza; alınan taş sağa atılamaz; kullan / sola geri ver / ıstakada tut + başka taş at yolları geçerlidir.
- Sahte Okey düz Okey kimliği kuralı değişmez.
