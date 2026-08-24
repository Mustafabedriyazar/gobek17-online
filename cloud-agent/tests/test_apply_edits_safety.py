# -*- coding: utf-8 -*-
"""apply_edits artik safe_edit cekirdegini (READ-SHA-PLAN-VERIFY-ATOMIK
UYGULA) kullaniyor mu? Bu dosya FAZ B DILIM 2'nin TEK konusu olan baglantiyi
dogrudan g17cloud.ai_worker.apply_edits uzerinden kanitlar (safe_edit'in
kendisi zaten test_safe_edit.py'de kanitlandi).

Kanit:
  * gecerli tek create edit dogru uygulanir (temel davranis regresyonu)
  * olmayan anchor'li replace: apply_edits ARTIK safe_edit.EditAnchorMissing
    firlatir (eski govde yalnizca genel AIError firlatirdi) VE dosya degismez
  * birden fazla eslesen anchor'li replace: apply_edits ARTIK
    safe_edit.EditAnchorAmbiguous firlatir VE dosya degismez
  * cok dosyali kumede ikinci edit hatali oldugunda: birinci dosya diskte
    DEGISMEMIS kalir (eski govde bunu SAGLAMAZDI — ilk dosyayi yazip
    ikincide patlardi, kismi degisiklik birakirdi)
"""
import shutil
from pathlib import Path
from _util import tmpdir


def check_valid_single_create_edit_applied_correctly():
    from g17cloud.ai_worker import apply_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        changed = apply_edits(wt, [{"path": "server/x.js", "action": "create",
                                    "new": "console.log(1);\n"}])
        assert changed == ["server/x.js"], changed
        assert (wt / "server" / "x.js").read_text(encoding="utf-8") == "console.log(1);\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_missing_anchor_raises_safe_edit_error_and_file_unchanged():
    from g17cloud.ai_worker import apply_edits
    from g17cloud.safe_edit import EditAnchorMissing
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("orijinal icerik\n", encoding="utf-8")
        try:
            apply_edits(wt, [{"path": "a.txt", "action": "replace",
                              "old": "bu metin dosyada yok", "new": "x"}])
            raise AssertionError("olmayan anchor apply_edits tarafindan kabul edildi")
        except EditAnchorMissing:
            pass
        assert f.read_text(encoding="utf-8") == "orijinal icerik\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_ambiguous_anchor_raises_safe_edit_error_and_file_unchanged():
    from g17cloud.ai_worker import apply_edits
    from g17cloud.safe_edit import EditAnchorAmbiguous
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("dup dup dup\n", encoding="utf-8")
        try:
            apply_edits(wt, [{"path": "a.txt", "action": "replace",
                              "old": "dup", "new": "x"}])
            raise AssertionError("belirsiz anchor apply_edits tarafindan kabul edildi")
        except EditAnchorAmbiguous:
            pass
        assert f.read_text(encoding="utf-8") == "dup dup dup\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_multi_file_edit_set_second_edit_invalid_leaves_first_file_unchanged():
    from g17cloud.ai_worker import AIError, apply_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        a = wt / "a.txt"; a.write_text("A1\n", encoding="utf-8")
        b = wt / "b.txt"; b.write_text("B1\n", encoding="utf-8")
        try:
            apply_edits(wt, [
                {"path": "a.txt", "action": "replace", "old": "A1", "new": "A2"},
                {"path": "b.txt", "action": "replace", "old": "BU YOK", "new": "B2"},
            ])
            raise AssertionError("ikinci edit'teki anchor hatasi yutuldu")
        except AIError:
            pass
        assert a.read_text(encoding="utf-8") == "A1\n", (
            "cok dosyali kumede ikinci edit hatali oldugunda ilk dosya "
            "diskte DEGISMEMIS kalmali (apply_edits safe_edit cekirdegine "
            "baglanmamis olabilir)")
        assert b.read_text(encoding="utf-8") == "B1\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)
