# -*- coding: utf-8 -*-
"""safe_edit cekirdegi: READ - SHA - PLAN - VERIFY - ATOMIK UYGULA.

Hata enjeksiyonuyla kanitlar:
  * bayat SHA ile yazim yapilamaz
  * olmayan anchor yazamaz ve dosya degismez
  * birden fazla eslesen anchor yazamaz ve dosya degismez
  * okuma ile yazma arasinda dosya disaridan degistirilirse uzerine yazilamaz
  * cok dosyali edit kumesinde biri basarisiz olursa diskte kismi degisiklik kalmaz
  * basarili tek edit dogru sekilde uygulanir
"""
import shutil
from pathlib import Path
from _util import tmpdir


def check_successful_single_edit_applied_correctly():
    from g17cloud.safe_edit import safe_apply_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        changed = safe_apply_edits(wt, [{"path": "server/x.js", "action": "create",
                                         "new": "console.log(1);\n"}])
        assert changed == ["server/x.js"], changed
        assert (wt / "server" / "x.js").read_text(encoding="utf-8") == "console.log(1);\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_successful_replace_edit_applied_correctly():
    from g17cloud.safe_edit import safe_apply_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("hello world\n", encoding="utf-8")
        changed = safe_apply_edits(wt, [{"path": "a.txt", "action": "replace",
                                         "old": "hello", "new": "goodbye"}])
        assert changed == ["a.txt"], changed
        assert f.read_text(encoding="utf-8") == "goodbye world\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_missing_anchor_raises_and_file_unchanged():
    from g17cloud.safe_edit import EditAnchorMissing, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("original content\n", encoding="utf-8")
        try:
            plan_edits(wt, [{"path": "a.txt", "action": "replace",
                             "old": "bu metin dosyada yok", "new": "x"}])
            raise AssertionError("olmayan anchor plan asamasinda kabul edildi")
        except EditAnchorMissing:
            pass
        assert f.read_text(encoding="utf-8") == "original content\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_ambiguous_anchor_raises_and_file_unchanged():
    from g17cloud.safe_edit import EditAnchorAmbiguous, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("dup dup dup\n", encoding="utf-8")
        try:
            plan_edits(wt, [{"path": "a.txt", "action": "replace",
                             "old": "dup", "new": "x"}])
            raise AssertionError("belirsiz anchor plan asamasinda kabul edildi")
        except EditAnchorAmbiguous:
            pass
        assert f.read_text(encoding="utf-8") == "dup dup dup\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_stale_sha_blocks_apply_and_file_keeps_external_change():
    from g17cloud.safe_edit import StaleEdit, apply_plan, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("hello world\n", encoding="utf-8")
        plan = plan_edits(wt, [{"path": "a.txt", "action": "replace",
                                "old": "hello", "new": "goodbye"}])
        # dosya PLAN sonrasi, UYGULAMA oncesi DISARIDAN degisti
        f.write_text("disaridan degistirildi\n", encoding="utf-8")
        try:
            apply_plan(plan)
            raise AssertionError("bayat SHA ile yazim engellenmedi")
        except StaleEdit:
            pass
        assert f.read_text(encoding="utf-8") == "disaridan degistirildi\n", (
            "STALE_EDIT sonrasi dosya planin 'after' icerigiyle ezilmis")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_external_delete_between_plan_and_apply_blocks_write():
    from g17cloud.safe_edit import StaleEdit, apply_plan, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("hello world\n", encoding="utf-8")
        plan = plan_edits(wt, [{"path": "a.txt", "action": "replace",
                                "old": "hello", "new": "goodbye"}])
        f.unlink()  # okuma ile yazma arasinda dosya disaridan SILINDI
        try:
            apply_plan(plan)
            raise AssertionError("okuma-yazma arasi disaridan silme engellenmedi")
        except StaleEdit:
            pass
        assert not f.exists(), "STALE_EDIT sonrasi dosya yeniden yaratilmis olmamali"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_multi_file_edit_set_partial_failure_leaves_no_change_on_disk():
    from g17cloud.safe_edit import plan_edits, apply_plan
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        a = wt / "a.txt"; a.write_text("A1\n", encoding="utf-8")
        # b.txt YOLUNU BILEREK bir DIZIN yapiyoruz: plan asamasinda dosya
        # olarak mevcut degil (before=None, before_sha=None) — VERIFY bunu
        # yakalamaz (dizin varligi sha ile izlenmez) ama ATOMIK UYGULA
        # asamasinda write_text bir dizine yazamayacagi icin patlar; bu da
        # gercek dunyada "ikinci dosya beklenmedik sekilde basarisiz oldu"
        # senaryosunu simule eder.
        b_dir = wt / "b.txt"; b_dir.mkdir()
        plan = plan_edits(wt, [
            {"path": "a.txt", "action": "replace", "old": "A1", "new": "A2"},
            {"path": "b.txt", "action": "create", "new": "B icerik\n"},
        ])
        try:
            apply_plan(plan)
            raise AssertionError("ikinci dosyadaki yazim hatasi yutuldu")
        except Exception as ex:
            assert not isinstance(ex, AssertionError), ex
        # ilk dosya BASARIYLA yazilmisti ama ikinci basarisiz oldu -> GERI ALINMALI
        assert a.read_text(encoding="utf-8") == "A1\n", (
            "cok dosyali kumede kismi basarisizlik sonrasi ilk dosya GERI ALINMADI")
        assert b_dir.is_dir(), "ikinci hedef beklenmedik sekilde degisti"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_create_without_overwrite_permission_rejected_when_target_exists():
    from g17cloud.safe_edit import EditTargetExists, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("mevcut\n", encoding="utf-8")
        try:
            plan_edits(wt, [{"path": "a.txt", "action": "create", "new": "yeni"}])
            raise AssertionError("izinsiz overwrite plan asamasinda kabul edildi")
        except EditTargetExists:
            pass
        assert f.read_text(encoding="utf-8") == "mevcut\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_safe_edit_errors_are_catchable_as_ai_error():
    from g17cloud.ai_worker import AIError
    from g17cloud.safe_edit import EditAnchorAmbiguous, EditAnchorMissing, StaleEdit, EditTargetExists
    assert issubclass(EditAnchorMissing, AIError)
    assert issubclass(EditAnchorAmbiguous, AIError)
    assert issubclass(StaleEdit, AIError)
    assert issubclass(EditTargetExists, AIError)
