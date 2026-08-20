# OKEY17 / GÖBEK17 — KANONİK KURAL DELTA v152

**Taban:** `gobek17-151-table-transport-bridge`  
**Build:** `gobek17-152-standard-fake-okey-immutable-meld-side-take`  
**Durum:** v152 ile yürürlükte. Bu belge yalnız aşağıdaki üç alanda önceki davranışı değiştirir; diğer kanonik kurallar korunur.

## 1. Sahte Okey — tek, düz-Okey otoritesi

- NORMAL ve BÜYÜK EL dahil **her elde numaralı gösterge** açılır.
- Gerçek Okey = göstergenin aynı renkte bir sonraki sayısıdır (`13 -> 1` yalnız Okey kimliği hesaplamasında; perlerde 13→1 seri wrap hâlâ yoktur).
- **Sahte Okey ★ hiçbir durumda wildcard/joker değildir.**
- Sahte Okey, per/puan/çift hesabında gerçek Okey'in **renk+sayı kimliğini doğal taş gibi** temsil eder; görsel yüzü ★ kalır.
- Örnek: gösterge siyah 4 → gerçek Okey siyah 5 → Sahte Okey ★ = per hesabında doğal siyah 5. Siyah `4-★-6` geçerli RENKLİ PER'dir.
- Eski `BIG_FAKE` ve `FAKE_INDICATOR_BIG` yolları tamamen kaldırılmıştır.
- Karıştırılmış destede gösterge seçilirken Sahte Okey gelirse Sahte Okey destede kalır; üstten ilk numaralı taş gösterge yapılır. Böylece her elde Okey kimliği nettir.

## 2. Açılmış perler immutable — bölme/taşıma yok

- Yere açılmış bir perin mevcut taşları **sökülemez, yeniden sıralanamaz, başka pere taşınamaz ve per bölünemez**.
- İlk açılıştaki motor sırası bir kez normalize edilir; daha sonra aynı sıra korunur.
- SERİ pere işleme yalnız **gerçek sol veya sağ endpoint** üzerinden yapılır. Orta gövdeye insertion yoktur.
- Bir SERİ pere, açıldığı andan itibaren **toplam en fazla 2 taş** işlenebilir (`processAdds <= 2`). Bu iki taş aynı uçtan veya iki ayrı uçtan gelebilir; legal ardışıklık şartı değişmez.
- Örnek: mavi `4-5-6-7-8` + mavi `9` → tek per `4-5-6-7-8-9`; **3+3 split yoktur**. Sonra mavi `10` işlenebilir; üçüncü işleme RED.
- RENKSİZ SERİ PER'in kanonik max 4 sınırı korunur.
- ÇİFT işleme ayrı kanonik yoldur: legal iki taşla yeni ÇİFT per yaratır; mevcut çifte üçüncü tek taş eklemez.
- UI'da açılmış per için long-press zoom/reposition otoritesi kaldırılmıştır. Drag işlem hedefi yalnız sol/sağ uç hotspotudur. Illegal üçüncü/orta işlem denemesi FREE board'a düşmez; taş kaynağına geri döner.

## 3. Yandan alınan taş — alan oyuncunun cezası ve iade

Yandan taş alan oyuncu için tek pending-taş otoritesi:

### Başarılı kullanım
- Yandan alınan taş legal bir **AÇ / yeni PER / İŞLE-YEDİR** hamlesinde kullanılırsa hamle gerçekleşir.
- Alan oyuncu taşın temsil edilen değeri ×10 kadar **kendi ceza hanesine** ceza yer.
- Taşı atan/kaynak oyuncuya bu yandan-alma cezası yazılmaz.

### Kullanamama / vazgeçme / başka taş atmaya çalışma
- Pending taş rack'e kalıcı olarak geçirilmez.
- Alan oyuncu aynı `değer ×10` cezayı **kendisi** yer.
- Alınan aynı fiziksel taş kaynak oyuncunun discard/atış alanına geri konur (`by=source`, audit için `returnedBy=taker`).
- Alan oyuncunun normal rack taşı atılmaz; tur doğrudan sonraki oyuncuya geçer.
- `TAKE_CANCEL` cezasız kaçış değildir; aynı return+penalty transaction'ını çalıştırır.
- İşlem atomiktir: pending temizlenir, kaynak atış alanı restore edilir, `hasDrawn=false`, turn advance yapılır.

## 4. Multiplayer eşliği

G17MP/1 action adları değişmedi. Server-authoritative motor bu v152 kurallarını uygular. Snapshot'ta açılmış perler ayrıca `openLen` ve `processAdds` alanlarını taşır. Client yalnız presentation mirror'dır; legal/illegal karar yine server'dadır.

## 5. Supersede listesi

Bu v152 delta aşağıdaki eski davranışları geçersiz kılar:

- Büyük El'de Sahte Okey ★ wildcard / Okey gösterme özel yolu.
- Sahte göstergenin ayrı wildcard modu.
- 5'li RENKLİ PER + 6. taşta 3+3 split.
- Açılmış perin long-press ile görsel yer değiştirme/zoom otoritesi.
- Kullanılmayan yandan taşın alan oyuncunun rack'inde tutulup ayrıca normal taş atılması.
- Başarılı yandan kullanım cezasının kaynak oyuncuya yazılması.
