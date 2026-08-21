# -*- coding: utf-8 -*-
"""version_guard: surum matematigi ve karisik damga tespiti."""
import json, shutil, sys
from pathlib import Path
from _util import guards_py, make_app_tree, tmpdir, GUARDS

sys.path.insert(0, str(GUARDS))
import version_guard as VG


def check_semver_mapping():
    assert VG.build_to_semver(169) == "1.69.0", VG.build_to_semver(169)
    assert VG.build_to_semver(171) == "1.71.0", VG.build_to_semver(171)
    assert VG.build_to_semver(200) == "2.0.0", VG.build_to_semver(200)
    assert VG.build_to_semver(271) == "2.71.0", VG.build_to_semver(271)


def check_canon_list_is_seven():
    assert len(VG.CANON) == 7, VG.CANON
    for rel in ("package.json", "server/package.json", "sw.js", "server/server.cjs",
                "index.html", "multiplayer-client.js", "multiplayer-bridge.js"):
        assert rel in VG.CANON, rel


def check_mixed_stamps_rejected():
    d = tmpdir()
    try:
        root = make_app_tree(d, stamp="gobek17-171-x", semver="1.71.0")
        # kanonik dosyalardan BIRINE eski damga sizdir (bugunku gercek hata)
        p = root / "app" / "index.html"
        p.write_text(p.read_text(encoding="utf-8") + "// eski: gobek17-170-x\n",
                     encoding="utf-8")
        _repack(root, 171)
        rc, out, err = guards_py("version_guard.py", ["verify", str(root), "171"])
        assert rc == VG.EXIT_VERSION, "karisik damga tespit EDILMEDI (rc=%s)" % rc
        assert "KARISIK" in (err + out), (err + out)[:200]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_clean_tree_passes():
    d = tmpdir()
    try:
        root = make_app_tree(d, stamp="gobek17-171-x", semver="1.71.0")
        _repack(root, 171)
        rc, out, err = guards_py("version_guard.py", ["verify", str(root), "171"])
        assert rc == 0, "temiz agac REDDEDILDI: %s" % (err or out)[:300]
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _repack(root, build):
    from g17cloud.pipeline import Pipeline
    from _util import pipeline_stub
    Pipeline.repackage_app(pipeline_stub(), root, build)
