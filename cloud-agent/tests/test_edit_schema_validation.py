# -*- coding: utf-8 -*-
"""AI edit girdilerinin sema dogrulamasi (AI_EDIT_SCHEMA_INVALID).

KOK SORUN: AI'nin dondurdugu bir edit kaydinda path/old/new gibi metin
beklenen bir alan sozluk olarak gelirse, o deger kullanilmadan once
deterministik olarak dogrulanmadigi surece asagi akiste dogrudan metin
islemine (.startswith/.encode/.count) tabi tutulup INTERNAL AttributeError
ile cokerdi. Bu dosya:
  * path sozluk gelince fail-closed (cokme YOK) oldugunu
  * old sozluk gelince fail-closed oldugunu
  * bilinen tasiyici anahtarli (text/content/value) sozlukten metnin
    guvenle cikarilip islemin NORMAL devam ettigini
  * liste gelince str() ile ZORLA donusum YAPILMADIGINI (fail-closed)
  * tamamen metin alanli normal edit'in bugunku gibi calistigini
kanitlar.
"""
import shutil
from pathlib import Path
from _util import tmpdir


def check_dict_path_field_fails_closed_without_crash():
    from g17cloud.safe_edit import EditSchemaInvalid, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        try:
            plan_edits(wt, [{"path": {"unexpected": "shape"}, "action": "create",
                             "new": "x"}])
            raise AssertionError("sozluk path plan asamasinda kabul edildi")
        except EditSchemaInvalid as ex:
            assert "AI_EDIT_SCHEMA_INVALID" in str(ex)
            assert "shape" not in str(ex)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_dict_old_field_fails_closed_without_crash():
    from g17cloud.safe_edit import EditSchemaInvalid, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("hello world\n", encoding="utf-8")
        try:
            plan_edits(wt, [{"path": "a.txt", "action": "replace",
                             "old": {"unexpected": "hello"}, "new": "goodbye"}])
            raise AssertionError("sozluk old plan asamasinda kabul edildi")
        except EditSchemaInvalid as ex:
            assert "AI_EDIT_SCHEMA_INVALID" in str(ex)
        assert f.read_text(encoding="utf-8") == "hello world\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_known_carrier_key_dict_is_extracted_and_edit_proceeds():
    from g17cloud.safe_edit import safe_apply_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        f = wt / "a.txt"; f.write_text("hello world\n", encoding="utf-8")
        changed = safe_apply_edits(wt, [{"path": "a.txt", "action": "replace",
                                         "old": {"text": "hello"},
                                         "new": {"content": "goodbye"}}])
        assert changed == ["a.txt"], changed
        assert f.read_text(encoding="utf-8") == "goodbye world\n"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_list_field_is_not_stringified_and_fails_closed():
    from g17cloud.safe_edit import EditSchemaInvalid, plan_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        try:
            plan_edits(wt, [{"path": "a.txt", "action": "create",
                             "new": ["not", "a", "string"]}])
            raise AssertionError("liste alan str() ile zorla metne cevrildi")
        except EditSchemaInvalid as ex:
            assert "list" in str(ex)
        assert not (wt / "a.txt").exists()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_fully_text_edit_behaves_exactly_as_before():
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


def check_schema_invalid_is_catchable_as_ai_error():
    from g17cloud.ai_worker import AIError
    from g17cloud.safe_edit import EditSchemaInvalid
    assert issubclass(EditSchemaInvalid, AIError)
