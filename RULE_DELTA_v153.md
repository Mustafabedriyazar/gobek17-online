# OKEY17 / GÖBEK17 — KANONİK KURAL DELTA v153

**Taban:** `gobek17-152-standard-fake-okey-immutable-meld-side-take.zip`  
**Build:** `gobek17-153-side-take-keep-or-return`

## Yandan taş — tek ceza, üç legal çözüm

Yandan alınan taş için alan oyuncu **her durumda taşın temsil edilen değeri ×10 ceza** yer.

1. **Kullanma:** Taş legal SERİ/ÇİFT açılışında, yeni PER'de veya legal İŞLE/YEDİR hamlesinde kullanılır. Taş pending'den çıkar, hamleye girer ve alan oyuncuya değer×10 ceza yazılır.
2. **Geri verme:** Oyuncu taşı solundaki/kaynak oyuncunun atış alanına geri verir. Aynı fiziksel taş kaynak atışına döner, alan oyuncu değer×10 ceza yer ve tur biter.
3. **Istakada tutma + başka taş atma:** Yandan alınan taş pending'den rack/ıstakaya kalıcı geçer. Alan oyuncu yine değer×10 ceza yer ve **başka bir rack taşı** sağa atar.

### Kesin yasak

- **Yandan alınan taşın kendisi sağa atılamaz.** `DISCARD` action'ı pending taşın UID'si ile gelirse motor hamleyi reddeder ve state'i değiştirmez.
- Bu reddedilmiş deneme ayrıca yeni ceza üretmez; ceza, oyuncu taşı kullanma / geri verme / ıstakada tutup başka taş atma yollarından biriyle çözdüğünde tek kez uygulanır.
- `TAKE_CANCEL` cezasız kaçış değildir; geri verme + değer×10 ceza yoludur.

## Önceki v152 kuralları korunur

- Açılmış perler immutable; taş sökme, yeniden sıralama, bölme yok.
- SERİ pere açıldıktan sonra toplam en fazla 2 işlek eklenir (`processAdds <= 2`).
- Sahte Okey düz Okey kimliğiyle doğal taş gibi davranır; wildcard değildir.
- Server-authoritative G17MP/1 action adları değişmez.
