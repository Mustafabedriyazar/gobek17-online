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
