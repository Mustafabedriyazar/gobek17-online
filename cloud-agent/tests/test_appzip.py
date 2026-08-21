# -*- coding: utf-8 -*-
"""app zip uretimi: app/ duzeni farkindaligi + dokuman haric tutma."""
import json, shutil, zipfile
from pathlib import Path
from _util import guards_py, make_app_tree, pipeline_stub, tmpdir

DOCS = {
    "RULE_DELTA_v170.md": "x\n",
    "QA_GUARD_REPORT_v166_SINGLE_FILE_PREVIEW.txt": "x\n",
    "MULTIPLAYER_PROTOCOL_v169.md": "x\n",
    "README_DEPLOY_v169.md": "x\n",
    "ESLI-2V2-CONTRACT-v4-FINAL.md": "x\n",
    ".gitignore": "x\n",
    "server/test-v170-ranked-flow.cjs": "x\n",
}


def check_make_app_zip_accepts_bootstrap_root():
    """build_artifact worktree KOKUNU verir; kokte server.cjs yoktur, app/ vardir."""
    d = tmpdir()
    try:
        root = make_app_tree(d)
        out = Path(d) / "art.zip"
        rc, so, se = guards_py("apply_artifact.py",
                               ["appzip", "--src", str(root), "--out", str(out)])
        assert rc == 0, "appzip worktree kokunde FAIL: %s" % (se or so)[:300]
        names = zipfile.ZipFile(out).namelist()
        assert "server.cjs" in names or "server/server.cjs" in names, names[:20]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_repackage_excludes_docs_and_tests():
    d = tmpdir()
    try:
        root = make_app_tree(d, extras=DOCS)
        from g17cloud.pipeline import Pipeline
        Pipeline.repackage_app(pipeline_stub(), root, 171)
        names = set(zipfile.ZipFile(root / "gobek17-app.zip").namelist())
        for bad in ("RULE_DELTA_v170.md", "MULTIPLAYER_PROTOCOL_v169.md",
                    "README_DEPLOY_v169.md", "ESLI-2V2-CONTRACT-v4-FINAL.md",
                    ".gitignore", "server/test-v170-ranked-flow.cjs",
                    "QA_GUARD_REPORT_v166_SINGLE_FILE_PREVIEW.txt"):
            assert bad not in names, "dokuman/test zip'e girdi: %s" % bad
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_repackage_keeps_runtime_entry():
    """bootstrap zip KOKUNDE server.cjs calistirir — asla dislanmamali."""
    d = tmpdir()
    try:
        root = make_app_tree(d, extras=DOCS)
        from g17cloud.pipeline import Pipeline
        Pipeline.repackage_app(pipeline_stub(), root, 171)
        names = set(zipfile.ZipFile(root / "gobek17-app.zip").namelist())
        for need in ("server.cjs", "index.html", "sw.js", "package.json",
                     "server/server.cjs", "server/package.json",
                     "multiplayer-client.js", "multiplayer-bridge.js"):
            assert need in names, "runtime dosyasi zip'te YOK: %s" % need
    finally:
        shutil.rmtree(d, ignore_errors=True)
