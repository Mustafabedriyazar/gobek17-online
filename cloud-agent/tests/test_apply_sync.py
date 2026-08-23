# -*- coding: utf-8 -*-
"""do_apply bootstrap modu repodaki app/ agacini da guncellemeli.

21 Agustos regresyonu: repoya yalniz 3 dosya yaziliyordu; app/ eski kaliyor,
bir sonraki gorev ESKI kaynaktan basliyordu (sessiz is kaybi).
"""
import json, shutil
from pathlib import Path
from _util import guards_py, make_app_tree, pipeline_stub, tmpdir


def _repo_at_old_version(dest):
    dest = Path(dest); (dest / "app" / "server").mkdir(parents=True, exist_ok=True)
    (dest / "bootstrap.cjs").write_text("eski\n", encoding="utf-8")
    (dest / "gobek17-app.zip").write_text("eski\n", encoding="utf-8")
    (dest / "package.json").write_text(json.dumps({"name": "b", "version": "1.70.0"}) + "\n",
                                       encoding="utf-8")
    (dest / "app" / "index.html").write_text("ESKI\n", encoding="utf-8")
    (dest / "app" / "server" / "server.cjs").write_text("ESKI\n", encoding="utf-8")
    return dest


def check_app_tree_is_synced_to_repo():
    d = tmpdir()
    try:
        wt = make_app_tree(Path(d) / "wt")
        from g17cloud.pipeline import Pipeline
        Pipeline.repackage_app(pipeline_stub(), wt, 171)
        repo = _repo_at_old_version(Path(d) / "repo")
        rc, out, err = guards_py("apply_artifact.py", [
            "apply", "--src", str(wt), "--dest", str(repo),
            "--backup", str(Path(d) / "bk"), "--manifest", str(Path(d) / "m.json"),
            "--mode", "auto", "--version", "1.71.0"])
        assert rc == 0, (err or out)[:300]
        idx = (repo / "app" / "index.html").read_text(encoding="utf-8")
        srv = (repo / "app" / "server" / "server.cjs").read_text(encoding="utf-8")
        assert "ESKI" not in idx, "repo app/index.html guncellenmedi"
        assert "ESKI" not in srv, "repo app/server/server.cjs guncellenmedi"
        assert json.loads((repo / "package.json").read_text())["version"] == "1.71.0"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_apply_reports_app_tree_count():
    d = tmpdir()
    try:
        wt = make_app_tree(Path(d) / "wt")
        from g17cloud.pipeline import Pipeline
        Pipeline.repackage_app(pipeline_stub(), wt, 171)
        repo = _repo_at_old_version(Path(d) / "repo")
        rc, out, err = guards_py("apply_artifact.py", [
            "apply", "--src", str(wt), "--dest", str(repo),
            "--backup", str(Path(d) / "bk"), "--manifest", str(Path(d) / "m.json"),
            "--mode", "auto", "--version", "1.71.0"])
        assert rc == 0, (err or out)[:300]
        man = json.loads((Path(d) / "m.json").read_text(encoding="utf-8"))
        assert "appTree" in man, "manifest'te appTree raporu yok"
        assert man["appTree"]["synced"] > 0, man["appTree"]
    finally:
        shutil.rmtree(d, ignore_errors=True)


# =========================================================== onarim turu edit dogrulamasi
# Onarim turundan (repair) donen "edits" listesinde path'i bos/eksik olan
# girdiler YOK SAYILIR; ilk uygulama (implement) turundeki dogrulama
# davranisi (bos path -> UnsafeEdit) DEGISMEZ.

def check_split_repair_edits_ignores_blank_or_missing_path():
    from g17cloud.ai_worker import split_repair_edits
    edits = [
        {"path": "", "action": "create", "new": "x"},
        {"path": "   ", "action": "create", "new": "x"},
        {"action": "create", "new": "eksik path anahtari"},
        "gecersiz-girdi",
        {"path": "server/ok.txt", "action": "create", "new": "hello"},
    ]
    valid, ignored = split_repair_edits(edits)
    assert ignored == 4, ignored
    assert [e["path"] for e in valid] == ["server/ok.txt"], valid


def check_repair_edit_with_blank_path_ignored_valid_applied():
    from g17cloud.ai_worker import apply_edits, split_repair_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        edits = [{"path": "", "action": "create", "new": "yok sayilmali"},
                 {"path": "server/ok.txt", "action": "create", "new": "hello"}]
        valid, ignored = split_repair_edits(edits)
        assert ignored == 1, ignored
        changed = apply_edits(wt, valid)
        assert changed == ["server/ok.txt"], changed
        assert (wt / "server" / "ok.txt").read_text(encoding="utf-8") == "hello"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_implement_phase_still_rejects_blank_path():
    """Ilk uygulama turu apply_edits'i DOGRUDAN cagirir — bu davranis degismez."""
    from g17cloud.ai_worker import UnsafeEdit, apply_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        try:
            apply_edits(wt, [{"path": "", "action": "create", "new": "x"}])
            raise AssertionError("bos path implement turunde kabul edildi")
        except UnsafeEdit:
            pass
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_apply_repair_edits_applies_valid_and_reports_ignored_count():
    from g17cloud.pipeline import apply_repair_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        rep = {"edits": [{"path": "", "action": "create", "new": "yok sayilmali"},
                         {"path": "server/y.txt", "action": "create", "new": "z"}],
              "summary": "kismen gecerli"}
        changed, total, this_round = apply_repair_edits(wt, rep, 1, 3, 0)
        assert changed == ["server/y.txt"], changed
        assert this_round == 1, this_round
        assert total == 1, total
        assert (wt / "server" / "y.txt").is_file()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_apply_repair_edits_stops_when_all_edits_invalid():
    from g17cloud.pipeline import apply_repair_edits
    from g17cloud.release_guard import GuardFailure
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        rep = {"edits": [{"action": "create", "new": "path yok"},
                         {"path": "   ", "action": "create", "new": "bos path"}],
              "summary": "hicbiri gecerli degil"}
        try:
            apply_repair_edits(wt, rep, 2, 3, 0)
            raise AssertionError("tum girdiler gecersizken gorev durmadi")
        except GuardFailure as ex:
            assert ex.stage == "REPAIR_INVALID_EDITS", ex.stage
            assert "2" in ex.reason, ex.reason  # kac girdi yok sayildi
            assert "2/3" in ex.reason, ex.reason  # deneme sayaci
            assert ex.detail.get("ignoredRepairEdits") == 2, ex.detail
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_apply_repair_edits_ignored_total_accumulates_across_rounds():
    from g17cloud.pipeline import apply_repair_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        rep1 = {"edits": [{"path": "", "new": "x"},
                          {"path": "server/a.txt", "action": "create", "new": "a"}]}
        _, total1, _ = apply_repair_edits(wt, rep1, 1, 3, 0)
        assert total1 == 1, total1
        rep2 = {"edits": [{"path": "", "new": "x"},
                          {"path": "server/b.txt", "action": "create", "new": "b"}]}
        _, total2, _ = apply_repair_edits(wt, rep2, 2, 3, total1)
        assert total2 == 2, total2
    finally:
        shutil.rmtree(d, ignore_errors=True)
