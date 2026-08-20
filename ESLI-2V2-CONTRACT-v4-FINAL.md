# OKEY17 / GÖBEK17 — EŞLİ 2v2 KURAL SÖZLEŞMESİ v4 FINAL

**Durum:** KİLİTLİ / v146 uygulama sözleşmesi  
**Kanonik taban:** `gobek17-145-visual-hierarchy-overlay`  
**Hedef build:** `gobek17-146-esli-2v2-team-engine`  
**Etiketler:** `[E]` motor · `[S]` sunucu/servis · `[P]` sunum  

Bu belge v3'ü ve önceki eşli taslaklarını supersede eder. Yalnız `[E]` maddeleri v146 istemci/motor build'ine uygulanır. `[S]` maddeleri ağ katmanı gelene kadar yalnız sözleşme olarak saklanır. `CFG.TEAMS = null` bireysel yolunun davranışı v145 ile korunur.

## 1. Takım kuruluşu ve konfigürasyon [E]

- Takım A = koltuk `0 + 2`; Takım B = koltuk `1 + 3`.
- Eşler karşılıklı oturur. Yan yana veya başka eşleşme kabul edilmez.
- Geçerli takım konfigürasyonunun normalize edilmiş tek biçimi `[[0,2],[1,3]]`'tür.
- Takım içi sıra ve iki takımın sırası normalize edilebilir: `[[2,0],[3,1]]` ve `[[1,3],[0,2]]` geçerlidir.
- `null` = bilinçli bireysel mod.
- **Non-null fakat bozuk `CFG.TEAMS` bireysele fallback yapmaz.** `newGame/start` atomik olarak `INVALID_TEAMS` ile RED olur; mevcut `st` ve seed değişmez.
- Aktif maçın takım modu state-owned snapshot'tır. Maç başladıktan sonra yalnız `CFG.TEAMS` değiştirerek canlı maç modu değiştirilemez.
- Eşli modda dağıtım, tur yönü, Büyük/Normal El döngüsü, gösterge/Okey ve 106 taş sistemi değişmez.

## 2. Açılış ve tür kilidi [E]

- Her oyuncu kendi açılışını kendisi yapar.
- SERİ minimum 51; ÇİFT minimum 52.
- Katlamalı eşik global mevcut kuralıyla aynıdır; eşin açmış olması ücretsiz/muaf açılış sağlamaz.
- Tür kilidi **oyuncu bazlıdır**. Aynı takımda bir oyuncu SERİ, eşi ÇİFT açabilir.
- SERİ açan oyuncu daha sonra kendi adına yeni ÇİFT per açamaz; ÇİFT açan kendi adına yeni SERİ per açamaz.
- Eşin perine işleme/yedirme oyuncunun `openingType` değerini değiştirmez.

## 3. İşleme / yedirme ortak önkoşulları [E]

Aşağıdaki mevcut v145 önkoşulları hem SERİ hem ÇİFT işleme yolunda aynen zorunludur:

- ilk turda işleme yok,
- oyuncu önce açmış olmalı,
- oyuncu o tur taş çekmiş olmalı,
- işleme sonrası elde son atılacak en az 1 taş kalmalı,
- pending/yandan alınan taş mevcut motorun kullanım ve ceza şartlarına tabidir,
- illegal işlem state mutate etmez.

### 3.1 SERİ per işleme [E]

- Bir hamlede bir SERİ pere en fazla `MAX_REAL_PER_PROCESS = 1` gerçek taş işlenebilir.
- RENKSİZ SERİ PER maksimum 4 taştır.
- RENKLİ PER maksimum 5 taştır; 5+1 yalnız legal atomik 3+3 split oluşabiliyorsa kabul edilir, aksi RED.
- Rakip takım perine işlenen taşın temsil değeri ×10 ceza per sahibine yazılır.
- Eşin SERİ perine legal işleme **0 ceza**dır.
- Eşli mod, SERİ için 2 gerçek taş boşaltma istisnası üretmez.

### 3.2 ÇİFT alanına işleme [E]

- Bu yol SERİ yolundaki `MAX_REAL_PER_PROCESS=1` sınırından ayrıdır.
- Tam **2 taş** seçilmelidir ve ikisi legal bir ÇİFT olmalıdır.
- 1 veya 3 taş RED; legal olmayan iki taş RED.
- İşlem mevcut çiftin üçüncü taşı olmaz; hedef oyuncu adına yeni bir ÇİFT per oluşturur.
- Rakip ÇİFT alanına legal çift: `sayı × 20` ceza hedef/per sahibine. Örnek `13-13 => +260`.
- Eşin ÇİFT alanına legal çift: **0 ceza**.
- Eşin alanına yaratılan yeni perin sahibi eştir.
- İşleyenin `openingType` değeri değişmez. SERİ açmış oyuncu eşinin ÇİFT alanına işlem yapabilir; bu kendi adına ÇİFT per açma sayılmaz.
- Kendi ÇİFT alanına `İŞLE/YEDİR` yasaktır; kendi yeni çiftleri `PER AÇ ÇİFT` yolundan açılır.
- Eşe çift işledikten sonra oyuncunun kendi tür kilidi aynen devam eder.

## 4. El sonu / partner muafiyeti [E]

- Bir oyuncu gerçek bitiş yaptığında el derhal kapanır.
- Ayrı “birlikte bitirme” bonusu/çarpanı yoktur.
- Gerçek bitiş yapan oyuncunun partneri **yalnız kapanış cezasından muaftır** (`ORTAK MUAF`).
- Partnerin o el içinde önceden oluşmuş ceza defteri silinmez.
- Partner açık ve elinde gerçek Okey/wildcard tutuyorsa kanonik `OKEY_HELD_END +500` uygulanır; ardından kapanış cezası 0 kalır.
- Kazanan bonusu yalnız gerçek bitirene yazılır: Normal `−100`, Büyük El `−200`.
- Partner ayrıca kazanan bonusu almaz.
- Rakiplerin açmayan/açık kapanış cezaları kişi bazında kanonik formülle aynen uygulanır.

## 5. KAFA ve özel bitişler [E]

- Eşli KAFA yalnız **rakip takımın iki oyuncusuna** bakar.
- Kazananın partnerinin açmış veya açmamış olması KAFA'yı bozmaz.
- İki rakip de açmamışsa KAFA ×2.
- Rakiplerden biri açmışsa KAFA yok.
- ÇİFTTEN / OKEYLE / KAFA birleşik çarpan mantığı mevcut `2^n` düzeniyle devam eder: ×2 / ×4 / ×8.
- Özel bitiş çarpanları önceki işleme, yandan alma ve büyük ceza defterini yeniden çarpmaz; yalnız kanonik kapanış cezası katmanına uygulanır.

## 6. Takım puanlama modeli M1 [E] + [P]

Kişisel ceza defteri kaldırılmaz veya ortak haneye dönüştürülmez.

```text
teamTotalPenalty = player[a].totalPenalty + player[b].totalPenalty
teamNaturalHandWins = player[a].handWins + player[b].handWins
teamHandWins = teamNaturalHandWins + team.forfeitHandWins
teamBigWins = player[a].bigWins + player[b].bigWins
teamMajorCount = player[a].majorCount + player[b].majorCount
```

- `team.forfeitHandWins` takım seviyesinde ayrı tutulur; hiçbir oyuncunun kişisel `handWins` değerini kirletmez.
- Rapor takım satırını ve altında bireysel kırılımı ayrı okuyabilir.

## 7. Eşli maç sonucu ve tie-break [E]

İki takım şu sırayla karşılaştırılır:

1. `teamTotalPenalty` artan — daha düşük üstte.
2. `teamHandWins` azalan — daha çok üstte.
3. `teamBigWins` azalan.
4. `teamMajorCount` artan — daha az +500 büyük ceza üstte.
5. Hepsi eşitse mod katmanı karar verir.

- Casual eşli: tam eşitlik = **BERABERE / ortak sıra**.
- Eşli Ranked `[S]`: tam eşitlik = rating sistemine **draw**.
- Turnuva `[S]`: tam eşitlik = **Sudden Death Normal El**, eşitlik sürerse tekrarlanır; turnuvada ortak şampiyonluk yoktur.
- Maç normal ana akışta 3. Büyük El sonunda biter.

## 8. Turnuva reconnect ve FORFEIT_HAND [S] + [E]

### 8.1 Kapsam

- `FORFEIT_HAND` **yalnız turnuva** bağlamında kullanılabilir.
- Casual ve Ranked'da varsayılan: bot koltuğu devralır ve eli tamamlar; 90 saniye aşımı otomatik `FORFEIT_HAND` yaratmaz.
- Ranked abandonment/MMR/queue cezası ileride server katmanının ayrı konusudur.

### 8.2 Reconnect

- Bağlantı kopunca oyun donmaz; server botu koltuğu geçici devralır.
- Botun hamlelerinden doğan cezalar devraldığı oyuncunun kişisel defterine yazılır.
- Oyuncu 90 saniye içinde geri dönerse koltuğunu geri alır.

### 8.3 Turnuva timeout

90 saniye dolduğunda server aynı el için **bir kez** `FORFEIT_HAND` yayınlar.

Motor davranışı:

- event idempotenttir; aynı el için ikinci event state değiştirmez,
- `winner = null`, `reason = "FORFEIT"`,
- kaçan takımın iki oyuncusu normal el sonu cezasını yer: açmayan Normal +500 / Büyük +1000; açık ise Σ×5 / Σ×10,
- kaçan takım için partner muafiyeti yoktur,
- kaçan takım açık oyuncularında elde Okey varsa kanonik +500 ayrıca korunur,
- her iki takımın olaydan **önceki ceza defteri aynen korunur**,
- rakip takım için yeni kapanış cezası 0'dır,
- gerçek bitiren olmadığı için `−100/−200` kazanan bonusu yoktur,
- KAFA / ÇİFTTEN / OKEYLE özel bitiş çarpanı yoktur,
- hiçbir oyuncuya kişisel `handWin` yazılmaz,
- kazanan takım için yalnız `team.forfeitHandWins += 1`,
- el bir kez kapanır; ikinci doğal `endHand` çalıştırılmaz,
- sonraki el normal akış ve 106 taş invariantıyla başlar.

## 9. Kalıcı eş / Eş Ligi [S]

- Kalıcı eş karşılıklı davet ile kurulur; hesap başına tek kalıcı eş.
- Ayrılık sonrası ilk sürüm yeni kalıcı eş kurma beklemesi 24 saat; server config ile 72 saate çıkarılabilir.
- Kalıcı çift `EŞLİ RANKED / EŞ LİGİ` tablosuna yazılır.
- Bireysel Ranked ayrı leaderboard'dur.
- Kalıcı çift ve rastgele eş sonuçları aynı leaderboard'a karıştırılmaz.
- Kalıcı eş profili/uyum XP/rozet sunum-meta katmanıdır; v146 motor kuralı değildir.

## 10. Ses ve anti-collusion [S]

- Eşli normal, Eşli Ranked ve Eşli turnuva: yalnız partner ses kanalı.
- Bireysel 4'lü ve 1v1: rakiple özel ses kanalı yok; hazır ifadeler kullanılabilir.
- Salon/lobi sohbeti oyun dışı ayrı katmandır.
- Ses kaydedilmez veya hamle hilesi için analiz edilmez; şikâyet/voice-right sistemi server politikasıdır.
- Anti-collusion: risk skoru → ödül/chip transfer dondurma → şüpheli eşleşmeleri ayırma → inceleme → geçici yasak → kalıcı yasak.
- Gizli rank düşürme yoktur.
- Aynı IP/ağ/cihaz tek başına suç kanıtı değildir.
- Kalıcı eş anti-collusion sisteminden muaf değildir.

## 11. v146 regresyon kilitleri [E]

Aşağıdakiler build promotion için zorunludur:

- `CFG.TEAMS=null` ile bireysel v145 sonuçları değişmemeli.
- 106 fiziksel taş, duplicate UID 0, lost UID 0.
- duplicate meld ID 0, illegal meld 0.
- illegal action state mutation 0.
- turn ownership korunmalı.
- v142/v145 pair/grid presentation korumaları korunmalı: `syncMeldTileFace`, `canonicalizeMeldTile`, `meldVisualAudit`, gerçek meld üzerinde motion-land yok.
- Eşli SERIES yedirme ve PAIR yedirme hedef/ceza/owner testleri ayrı çalışmalı.
- Team final iki takım satırı + oyuncu kırılımı üretmeli.
- FORFEIT event injection testleri: tournament-only, idempotence, prior-ledger preservation, no personal handWin pollution, next-hand continuity.
- Bireysel ve eşli mod ayrı stres testinden geçmeli.
- Guard FAIL ise build kanonik ilan edilmez.

## 12. v146 kapsam dışı

v146 eşli çekirdek motoru aşağıdakileri tahmin ederek doldurmaz:

- renk çarpanları,
- çiçek kuralı,
- ekonomi/chip fiyat dengesi,
- gerçek backend/matchmaking,
- gerçek reconnect socket protokolü,
- voice altyapısı,
- anti-collusion servis uygulaması,
- kalıcı eş veritabanı,
- Ranked rating formülü,
- turnuva bracket servisi.

Bunlar kendi sözleşmeleriyle sonraki katmanlarda uygulanır.
