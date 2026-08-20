# G17MP/1 — v154 Notu

`gobek17-154-atomic-meld-reflow` yalnız istemci presentation/geometry düzeltmesidir.

- G17MP/1 action adları ve envelope yapısı değişmedi.
- Server-authoritative gameplay semantiği v153 ile aynıdır.
- `server/engine-factory.cjs`, bot factory ve authority kodları v153 ile byte-identical tutulmuştur.
- Client bridge/SDK build etiketi ve PWA cache adı v154'e güncellenmiştir.
- Açılmış perin final engine sırası ve snapshot alanları (`openLen`, `processAdds`) değişmez; v154 yalnız bu authoritative sıranın ekrana atomik yerleşmesini sağlar.
