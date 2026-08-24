# -*- coding: utf-8 -*-
"""G17 Cloud Agent — guvenli duzenleme cekirdegi.

KOK SORUN: AI, dosya iceriklerini hafizasindan TAHMIN ederek "old" metni
uretebilir; bu metin dosyanin GERCEK icerigiyle eslesmeyince edit dusurulur
ve gorev sessizce yariniz kalir. COZUM: her mutation oncesi dosya GERCEKTEN
okunur, SHA-256 ile durumu sabitlenir, tum edit kumesi ONCE BELLEKTE
dogrulanir (PLAN) ve ancak hepsi gecerliyse — yazmadan hemen once SHA
YENIDEN dogrulanarak (VERIFY) — diske ATOMIK olarak uygulanir. Herhangi bir
adimda hata olursa diskte KISMI degisiklik BIRAKILMAZ.

Akis: READ -> SHA -> PLAN -> VERIFY -> ATOMIK UYGULA
    plan_edits()  : READ + SHA + PLAN (diske HICBIR SEY yazmaz)
    apply_plan()  : VERIFY + ATOMIK UYGULA (hata olursa yazilanlar GERI ALINIR)
    safe_apply_edits(): ikisini sirayla cagiran kisa yol

Yol guvenligi (worktree disina / .git altina yazma engeli) ve edit alaninin
cozumlenmesi (path, yoksa file/filename) icin ai_worker.safe_join /
ai_worker.edit_path YENIDEN KULLANILIR — iki ayri guvenlik kurali kumesi
olusmasin diye. Hata siniflari da ai_worker.AIError/UnsafeEdit HIYERARSISINE
baglanir; boylece bu modulun hatalari mevcut "except AIError" / "except
UnsafeEdit" bloklariyla da yakalanabilir.
"""
import hashlib
from pathlib import Path

from .ai_worker import AIError, UnsafeEdit, edit_path, safe_join

MAX_EDIT_BYTES = 2 * 1024 * 1024


class EditAnchorMissing(AIError):
    """replace edit'inin "old" metni okunan dosya icinde HIC yok (EDIT_ANCHOR_MISSING)."""


class EditAnchorAmbiguous(AIError):
    """replace edit'inin "old" metni okunan dosyada BIRDEN FAZLA kez geciyor (EDIT_ANCHOR_AMBIGUOUS)."""


class EditTargetExists(AIError):
    """create edit'i icin hedef zaten var ve acikca overwrite izni verilmemis (EDIT_TARGET_EXISTS)."""


class StaleEdit(AIError):
    """Yazmadan hemen once yeniden hesaplanan SHA plandakiyle uyusmuyor — dosya
    plan ile uygulama arasinda disaridan degisti (STALE_EDIT). HICBIR SEY yazilmaz."""


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_sha(path):
    """Dosyayi GERCEKTEN okur ve (icerik, sha) dondurur. Dosya yoksa (None, None)."""
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace")
    return text, sha256_text(text)


def plan_edits(worktree, edits):
    """Bir edit kumesini ONCE BELLEKTE dogrular; DISKE HICBIR SEY YAZMAZ.

    Ayni dosyayi hedefleyen birden fazla edit SIRAYLA zincirlenir (ikinci
    edit'in "old" araması birincinin bellekteki sonucu uzerinde yapilir) —
    boylece tek bir edit kumesi icinde ayni dosyaya art arda yapilan
    duzenlemeler mevcut apply_edits davranisiyla AYNI sirayla islenir.
    "before"/"before_sha" HER ZAMAN dosyanin PLAN ANINDAKI GERCEK disk
    durumunu tutar — apply_plan bu degeri VERIFY icin kullanir.

    Donus: plan listesi (dict'ler): path, target, action, before,
    before_sha, after. Gecersiz bir edit varsa ILK hatada raise edilir
    (UnsafeEdit / AIError alt siniflari); bu fonksiyon disk yazmadigi icin
    hata aninda dosyalarda HICBIR degisiklik olmamis olur.
    """
    worktree = Path(worktree)
    order = []
    by_target = {}
    for ed in edits or []:
        if not isinstance(ed, dict):
            continue
        action = (ed.get("action") or "replace").lower()
        rel = edit_path(ed)
        target = safe_join(worktree, rel)
        key = str(target)

        if key in by_target:
            step = by_target[key]
            cur_text = step["after"]
        else:
            before, before_sha = _read_sha(target)
            step = {"path": rel, "target": target, "action": action,
                    "before": before, "before_sha": before_sha, "after": before}
            by_target[key] = step
            order.append(key)
            cur_text = before

        if action == "delete":
            step["action"] = "delete"
            step["after"] = None
            continue

        content = ed.get("new")
        if content is None:
            continue
        if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
            raise UnsafeEdit("cok buyuk duzenleme: %s" % rel)

        if action == "replace" and ed.get("old"):
            if cur_text is None:
                raise AIError("degistirilecek dosya yok: %s" % rel)
            old = ed["old"]
            count = cur_text.count(old)
            if count == 0:
                raise EditAnchorMissing(
                    "EDIT_ANCHOR_MISSING: eslesmeyen duzenleme (old bulunamadi): %s" % rel)
            if count > 1:
                raise EditAnchorAmbiguous(
                    "EDIT_ANCHOR_AMBIGUOUS: belirsiz duzenleme (old birden fazla): %s" % rel)
            step["after"] = cur_text.replace(old, content, 1)
            step["action"] = "replace"
        else:
            if action == "create" and cur_text is not None and not ed.get("overwrite"):
                raise EditTargetExists(
                    "EDIT_TARGET_EXISTS: hedef dosya zaten var (overwrite izni yok): %s" % rel)
            step["after"] = content
            step["action"] = action
    return [by_target[k] for k in order]


def apply_plan(plan):
    """Plani diske ATOMIK uygular.

    1) VERIFY: yazmadan ONCE HER dosyanin GUNCEL SHA'si yeniden okunup
       plandaki before_sha ile karsilastirilir; herhangi biri uyusmuyorsa
       STALE_EDIT ile durulur ve HICBIR dosyaya yazilmaz.
    2) ATOMIK UYGULA: dogrulama gectikten sonra sirayla yazilir; herhangi
       bir yazim sirasinda hata olursa o ana kadar yazilmis dosyalar
       plandaki ORIJINAL icerikleriyle (ya da hic yoktularsa silinerek)
       GERI ALINIR — diskte kismi degisiklik BIRAKILMAZ.

    Donus: degisen path'lerin sirali/tekil listesi.
    """
    for step in plan:
        _cur_text, cur_sha = _read_sha(step["target"])
        if cur_sha != step["before_sha"]:
            raise StaleEdit(
                "STALE_EDIT: dosya plan ile uygulama arasinda disaridan degisti: %s"
                % step["path"])

    written = []
    try:
        for step in plan:
            target = step["target"]
            if step["action"] == "delete":
                if target.is_file():
                    target.unlink()
                written.append(step)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(step["after"], encoding="utf-8")
            written.append(step)
    except Exception:
        _rollback(written)
        raise
    return sorted({step["path"] for step in plan})


def _rollback(written):
    """ATOMIK UYGULA sirasinda hata olursa YAZILMIS OLAN dosyalari plan
    ANINDAKI orijinal durumlarina geri dondurur (yoktularsa siler)."""
    for step in reversed(written):
        target = step["target"]
        try:
            if step["before"] is None:
                if target.is_file():
                    target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(step["before"], encoding="utf-8")
        except OSError:
            pass


def safe_apply_edits(worktree, edits):
    """plan_edits + apply_plan icin kisa yol. Ayni AIError/UnsafeEdit
    alt siniflarini firlatir; basarili donusu apply_edits ile AYNI
    bicimde (degisen path'lerin sirali listesi) verir."""
    plan = plan_edits(worktree, edits)
    return apply_plan(plan)
