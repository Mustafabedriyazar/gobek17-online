# -*- coding: utf-8 -*-
"""_stamp_release kapsami version_guard kapsamiyla AYNI olmali.

21 Agustos regresyonu: damgalama yalnizca atama bicimini degistiriyordu;
guard ise damgayi dosyanin her yerinde ariyordu -> "KARISIK surum damgalari".
"""
import shutil
from pathlib import Path
from _util import guards_py, make_app_tree, pipeline_stub, tmpdir


def _stamp_and_pack(root, build, stamp):
    from g17cloud.pipeline import Pipeline
    st = pipeline_stub()
    edits = Pipeline._stamp_release(st, root, build, stamp)
    Pipeline.repackage_app(st, root, build)
    return edits


def check_stamp_covers_non_assignment_occurrences():
    d = tmpdir()
    try:
        root = make_app_tree(d, stamp="gobek17-170-x", semver="1.70.0")
        p = root / "app" / "server" / "server.cjs"
        p.write_text(p.read_text(encoding="utf-8") +
                     '// paket adi: gobek17-170-x\nconst ALT = "gobek17-170-x";\n',
                     encoding="utf-8")
        _stamp_and_pack(root, 171, "gobek17-171-y")
        rc, out, err = guards_py("version_guard.py", ["verify", str(root), "171"])
        assert rc == 0, "atama disi damga kaldi: %s" % (err or out)[:300]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_stamp_rewrites_all_canon_files():
    d = tmpdir()
    try:
        root = make_app_tree(d, stamp="gobek17-170-x", semver="1.70.0")
        _stamp_and_pack(root, 171, "gobek17-171-y")
        for rel in ("index.html", "sw.js", "multiplayer-client.js",
                    "multiplayer-bridge.js", "server/server.cjs"):
            txt = (root / "app" / rel).read_text(encoding="utf-8")
            assert "gobek17-170-" not in txt, "eski damga kaldi: %s" % rel
            assert "gobek17-171-y" in txt, "yeni damga yok: %s" % rel
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_docs_are_not_stamped():
    d = tmpdir()
    try:
        root = make_app_tree(d, stamp="gobek17-170-x", semver="1.70.0",
                             extras={"RULE_DELTA_v170.md": "tarihsel: gobek17-170-x\n"})
        _stamp_and_pack(root, 171, "gobek17-171-y")
        doc = (root / "app" / "RULE_DELTA_v170.md").read_text(encoding="utf-8")
        assert "gobek17-170-x" in doc, "tarihsel dokuman DEGISTIRILDI"
    finally:
        shutil.rmtree(d, ignore_errors=True)
