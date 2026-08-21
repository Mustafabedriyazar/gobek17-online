# G17 CLOUD AGENT v2

Bulutta sürekli çalışan release ajanı. **Telefon gerekmiyor.** Termux, GitHub web arayüzü
ve Railway Deploy butonu günlük akıştan çıktı.

Tek yaptığın: doğal dille görev vermek.

```bash
curl -X POST https://<agent-adresin>/tasks \
  -H "Authorization: Bearer $G17_API_TOKEN" \
  -H "content-type: application/json" \
  -d '{"build":"v171","task":"Ranked maç sonunda rating panelindeki hatayı düzelt ve yayınla"}'
```

Dönen `id` ile durumu izlersin; gerisi bulutta akar:

```
TASK → clone/worktree → AI inspect → reproduce → root cause → fix → repair loop
     → tests → guards → vXXX artifact → commit/push → Actions → Railway → production health
```

---

## MİMARİ — 5 PARÇA

| # | Parça | Sorumluluk | Dosya |
|---|-------|-----------|-------|
| 1 | **Cloud Controller** | HTTP API, kuyruk, kalıcı durum, kilit | `api.py`, `store.py`, `__main__.py` |
| 2 | **GitHub Core** | clone/worktree/commit/push, Actions, PR, release | `github_core.py` |
| 3 | **AI Worker** | Fable/Opus/Claude soyutlaması, routing, repair loop | `ai_worker.py` |
| 4 | **Release Guard** | diff → secret → engine/bot SHA → test → sıra → artifact | `release_guard.py`, `guards/` |
| 5 | **Production Controller** | Railway auto-deploy sonrası health doğrulaması | `production.py` |

`pipeline.py` bu beşini sırayla yürütür. **AI hiçbir aşamada git push edemez** — commit/push
yalnızca deterministik GitHub Core'da, guard'lar PASS verdikten sonra çalışır.

---

## API

| Uç | İş |
|----|-----|
| `POST /tasks` | `{build, task, provider?, dryRun?, noDeploy?}` → `202 {id}` |
| `GET /tasks/:id` | görev durumu + faz geçişleri |
| `GET /tasks` | son görevler |
| `GET /status` | servis, GitHub, production özeti (sır içermez) |
| `GET /health` | canlılık (kimlik istemez) |

`/health` dışındaki **tüm** uçlar `Authorization: Bearer $G17_API_TOKEN` ister.
`G17_API_TOKEN` tanımlı değilse servis ayağa kalkar ama `/health` dışındaki her istek
**401** döner — yani token'sız hiçbir görev alınamaz. (Servisin tümden açılmaması yerine
bu tercih edildi: platformun healthcheck'i yeşil kalır, crash-loop olmaz.)

### provider seçimi

```json
{"build":"v171","task":"...","provider":"fable"}
```

- `fable` — büyük, geniş kapsamlı işler (çok dosyalı değişiklik, yeniden yazım)
- `opus` — audit, debugging, küçük/orta hassas işler
- verilmezse görev metninden otomatik seçilir

---

## KURULUM (Railway, ikinci servis)

Production servisine **dokunulmaz**; bu ayrı bir servistir.

1. Bu klasörü repoya koy (örn. `cloud-agent/`) ve main'e gönder.
2. Railway → aynı proje → **New Service → GitHub Repo** → `Mustafabedriyazar/gobek17-online`
3. Service Settings → **Root Directory** = `cloud-agent`
4. **Volume** ekle → mount path `/data` (kalıcı durum; yoksa restart'ta görevler kaybolur)
5. Variables → `.env.example` içindekileri doldur (en azından `G17_API_TOKEN`,
   `GITHUB_TOKEN` veya GitHub App üçlüsü, `ANTHROPIC_API_KEY`)
6. Deploy. `GET /health` 200 dönüyorsa hazır.

Docker imajı stdlib + git + node içerir; `pip install` adımı yoktur.

---

## GÜVENLİK MODELİ

**Kimlik ayrımı.** AI kodu değiştirir, Release Guard karar verir, GitHub Core yetkili
işlemi yapar. AI süreci token taşıyan ortam değişkenleri olmadan başlatılır —
GitHub ve Railway kimlik bilgilerini **hiç görmez**.

**AI'nın yapamadıkları.** git push/force-push/reset/branch delete yok. AI çıktısı
kabuk olarak çalıştırılmaz (`eval`/`exec` yok, `shell=True` yok); yalnızca yapılandırılmış
düzenleme listesi kabul edilir ve her yol worktree içine hapsedilir — `../` denemesi görevi düşürür.

**Release iptali.** Şunlardan biri olursa production'a hiçbir şey gitmez:
secret sızıntısı, kanonik engine/bot SHA'sının beklenmedik değişimi, test FAIL,
sıra dışı build, worktree kaçışı, reproduce edilememesi.

**Kilit.** Aynı anda birden çok AI araştırma görevi koşabilir, ama **iki build aynı anda
main'e çıkamaz** — release kilidi kalıcıdır ve servis restart'ında sahipsiz kalmaz.

**Sürüm.** v170 → v171 → v172. Geri sürüme otomatik dönüş **yasak**.

**Onarım.** Test FAIL olursa AI en fazla 3 tur dener. Sonsuz retry yok.

---

## RESTART DAYANIKLILIĞI

Görev durumu her faz geçişinde diske yazılır. Servis yeniden başlarsa yarım kalan görevler
`INTERRUPTED` olarak işaretlenir; commit oluşmuş ama push olmamışsa duplicate release
üretilmez, kaldığı yerden devam eder. Belirsiz durumda otomatik tahmin yapmaz.

---

## TESTLER

```bash
python3 tests/test_cloud.py
```

Gerçek git repoları, gerçek HTTP (loopback) ve mock AI ile uçtan uca çalışır.
Gerçek GitHub'a veya production'a dokunmaz.
