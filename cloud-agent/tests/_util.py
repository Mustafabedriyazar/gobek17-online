# -*- coding: utf-8 -*-
"""Test yardimcilari — stdlib disi bagimlilik YOK."""
import json, os, subprocess, sys, tempfile, types
from pathlib import Path

AGENT = Path(__file__).resolve().parent.parent      # cloud-agent/
GUARDS = AGENT / "guards"
if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))


def guards_py(script, args):
    p = subprocess.run([sys.executable, str(GUARDS / script)] + args,
                       capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


def stub_cfg():
    return types.SimpleNamespace(guards_dir=GUARDS)


def pipeline_stub():
    return types.SimpleNamespace(cfg=stub_cfg())


def make_app_tree(root, stamp="gobek17-171-x", semver="1.71.0", extras=None):
    """Gercek repo duzeni: kokte 3-file bootstrap, kaynak app/ altinda."""
    root = Path(root); app = root / "app"; (app / "server").mkdir(parents=True, exist_ok=True)
    (root / "bootstrap.cjs").write_text("console.log('boot');\n", encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"name": "b", "version": semver}) + "\n",
                                       encoding="utf-8")
    (app / "index.html").write_text('<script>var BUILD="%s";</script>\n' % stamp, encoding="utf-8")
    (app / "sw.js").write_text('var C="%s";\n' % stamp, encoding="utf-8")
    (app / "multiplayer-client.js").write_text("module.exports={build:'%s'};\n" % stamp,
                                               encoding="utf-8")
    (app / "multiplayer-bridge.js").write_text("module.exports={build:'%s'};\n" % stamp,
                                               encoding="utf-8")
    (app / "server.cjs").write_text("// entry\n", encoding="utf-8")
    (app / "server" / "server.cjs").write_text("const X={build:'%s'};\n" % stamp, encoding="utf-8")
    (app / "package.json").write_text(json.dumps({"name": "a", "version": semver}) + "\n",
                                      encoding="utf-8")
    (app / "server" / "package.json").write_text(json.dumps({"name": "s", "version": semver}) + "\n",
                                                 encoding="utf-8")
    for rel, body in (extras or {}).items():
        p = app / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def tmpdir():
    return tempfile.mkdtemp(prefix="g17t-")
