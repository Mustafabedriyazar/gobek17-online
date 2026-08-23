#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kapi regresyon testi — testleri kasitli FAIL eden bir gorev calistirir ve
dogrular: gorev status'u 'failed' olur VE origin fikstur reposunun HEAD'i
gorev oncesiyle ayni kalir (commit/push YOK).

Fikstur (make_project/make_env/mock_script/run_task) tests/test_cloud.py
icindeki kaliplarla BIREBIR aynidir; GERCEK GitHub'a veya production'a
ASLA dokunmaz: origin yerel bare repo, AI mock saglayici.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from g17cloud.api import Service  # noqa: E402
from g17cloud.config import Config  # noqa: E402

PASS = FAIL = 0
OK, ER, Z = "\033[32m", "\033[31m", "\033[0m"
if not sys.stdout.isatty():
    OK = ER = Z = ""


def ok(msg):
    global PASS
    PASS += 1
    print(" %sPASS%s  %s" % (OK, Z, msg))


def bad(msg, detail=""):
    global FAIL
    FAIL += 1
    print(" %sFAIL%s  %s — %s" % (ER, Z, msg, detail))


def head(t):
    print("\n--- %s" % t)


def git(args, cwd, check=True):
    p = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), p.stderr))
    return p.stdout.strip()


# ---------------------------------------------------------------- sahte proje
def make_project(dst: Path, build: int, slug: str, engine_body="CANONICAL-ENGINE-BODY",
                 fix_flag=False):
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "server").mkdir(exist_ok=True)
    stamp = "gobek17-%d-%s" % (build, slug)
    semver = "1.%d.0" % build
    (dst / "package.json").write_text(json.dumps(
        {"name": "gobek17-online", "version": semver, "main": "server.cjs",
         "scripts": {"start": "node server.cjs"}}, indent=2), encoding="utf-8")
    (dst / "server" / "package.json").write_text(json.dumps(
        {"name": "authority", "version": semver,
         "scripts": {"test": "node test-authority.cjs"}}, indent=2), encoding="utf-8")
    (dst / "index.html").write_text(
        '<!doctype html><script>var BUILD="%s";\n'
        "/*OKEY17-BAS*/\nvar E={body:'%s'};\n/*OKEY17-SON*/\n"
        "var EBOT=(function(){return{v:1}})();\n/*MASTER17-BAS*/\n</script>"
        % (stamp, engine_body), encoding="utf-8")
    (dst / "sw.js").write_text('var C="%s";' % stamp, encoding="utf-8")
    # GERCEK repo sekli: bootstrap ".gobek17-app/server.cjs" calistirir, bu yuzden
    # app zip KOKUNDE server.cjs olmak ZORUNDA (apply_artifact bunu dogruluyor).
    (dst / "server.cjs").write_text(
        "'use strict';\n// Railway girisi — kanonik otorite server/server.cjs\n"
        "module.exports=require('./server/server.cjs');\n", encoding="utf-8")
    (dst / "server" / "server.cjs").write_text(
        "'use strict';\nmodule.exports={build:'%s'};\n" % stamp, encoding="utf-8")
    (dst / "server" / "engine-factory.cjs").write_text(
        "// canonical engine factory\nmodule.exports={};\n", encoding="utf-8")
    (dst / "server" / "bot-factory.cjs").write_text(
        "// canonical bot factory\nmodule.exports={};\n", encoding="utf-8")
    (dst / "server" / "test-authority.cjs").write_text(
        "const fs=require('fs');\n"
        "if(!fs.existsSync(__dirname+'/ranked-fix.flag')){\n"
        "  console.error('ranked panel regression');process.exit(1);}\n"
        "console.log('authority OK');\n", encoding="utf-8")
    if fix_flag:
        (dst / "server" / "ranked-fix.flag").write_text("", encoding="utf-8")
    return dst


def make_env(name, build=170, slug="production-ranked-flow"):
    """Yerel bare origin + klonlanabilir repo + izole state."""
    base = Path(tempfile.mkdtemp(prefix="g17cloud-%s-" % name))
    origin = base / "origin.git"
    seed = base / "seed"
    git(["init", "-q", "--bare", str(origin)], base)
    make_project(seed, build, slug, fix_flag=False)
    git(["init", "-q", str(seed)], base)
    git(["symbolic-ref", "HEAD", "refs/heads/main"], seed)
    git(["add", "-A"], seed)
    git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
         "v%d: seed" % build], seed)
    git(["remote", "add", "origin", str(origin)], seed)
    git(["push", "-q", "origin", "main"], seed)
    state = base / "state"
    cfg = Config(env={
        "G17_STATE_DIR": str(state), "G17_WORK_DIR": str(base / "work"),
        "G17_REPO": str(origin), "G17_BRANCH": "main",
        "AI_PROVIDER": "mock", "MAX_AGENT_REPAIR_ATTEMPTS": "3",
        "TEST_TIMEOUT_SECONDS": "60", "RAILWAY_WAIT_SECONDS": "6",
        "HEALTH_POLL_SECONDS": "1", "G17_API_TOKEN": "test-token",
        "G17_PROD_BASE": "http://127.0.0.1:1",
    })
    cfg.ensure_dirs()
    return base, cfg, origin


def mock_script(base: Path, mode="fix"):
    """AI mock: faz'a gore JSON dondurur. Kabuk olarak ASLA calistirilmaz."""
    p = base / ("mock-%s.sh" % mode)
    p.write_text(r'''#!/bin/sh
prompt=$(cat)
case "$prompt" in
  *"faz: inspect"*)
    case "%MODE%" in
      norepro) echo '{"reproduced":false,"rootCause":"kanit yok","files":[],"minimalFix":"","tests":[]}' ;;
      *) echo '{"reproduced":true,"rootCause":"rankedResult snapshotta tasinmiyor","files":["server/ranked-fix.flag"],"minimalFix":"flag ekle","tests":["test-authority.cjs"],"title":"ranked result transport"}' ;;
    esac ;;
  *"faz: implement"*)
    case "%MODE%" in
      escape)  echo '{"edits":[{"path":"../../../escaped.txt","action":"create","new":"disari"}],"summary":"kacis"}' ;;
      secret)  echo '{"edits":[{"path":"server/ranked-fix.flag","action":"create","new":""},{"path":"server/cfg.js","action":"create","new":"const t=\\"%FAKETOKEN%\\";"}],"summary":"secret"}' ;;
      engine)  echo '{"edits":[{"path":"server/ranked-fix.flag","action":"create","new":""},{"path":"index.html","action":"replace","old":"CANONICAL-ENGINE-BODY","new":"HACKED-ENGINE-BODY"}],"summary":"engine"}' ;;
      testfail) echo '{"edits":[{"path":"server/noop.txt","action":"create","new":"x"}],"summary":"duzelmedi"}' ;;
      repair)  echo '{"edits":[{"path":"server/eksik.txt","action":"create","new":"x"}],"summary":"ilk deneme eksik"}' ;;
      nochange) echo '{"edits":[],"summary":"bos"}' ;;
      *)       echo '{"edits":[{"path":"server/ranked-fix.flag","action":"create","new":""}],"summary":"flag eklendi"}' ;;
    esac ;;
  *"faz: repair"*)
    case "%MODE%" in
      testfail) echo '{"edits":[{"path":"server/noop2.txt","action":"create","new":"x"}],"summary":"hala yok"}' ;;
      repair)  echo '{"edits":[{"path":"server/ranked-fix.flag","action":"create","new":""}],"summary":"onarildi"}' ;;
      *)       echo '{"edits":[],"summary":"yok"}' ;;
    esac ;;
  *) echo '{}' ;;
esac
'''.replace("%MODE%", mode).replace("%FAKETOKEN%", "ghp_" + "A" * 36), encoding="utf-8")
    p.chmod(0o755)
    return p


def run_task(cfg, base, mode, build="v171", provider="mock", **kw):
    os.environ["G17_MOCK_SCRIPT"] = str(mock_script(base, mode))
    svc = Service(cfg)
    rec = svc.store.create(build, "ranked panelini duzelt", provider,
                           kw.get("dry_run", False), kw.get("no_deploy", False),
                           kw.get("task_mode", "fix"))
    svc.pipeline.prod.wait_for = lambda stamp, **k: {
        "result": kw.get("health", "PASS"), "seen": stamp, "waited": 0}
    svc.pipeline.gh.wait_actions = lambda sha, **k: {
        "result": kw.get("actions", "N/A"), "runs": []}
    return svc, svc.pipeline.run(rec["id"])


# ================================================================ testler
def t_gate_blocks_on_test_failure():
    head("1) test FAIL -> gorev 'failed' VE origin HEAD degismedi (commit/push YOK)")
    base, cfg, origin = make_env("gateblock")
    before_head = git(["rev-parse", "main"], origin)
    svc, rec = run_task(cfg, base, "testfail")
    if rec["status"] == "failed":
        ok("gorev status 'failed'")
    else:
        bad("gorev status", rec["status"])
    after_head = git(["rev-parse", "main"], origin)
    if after_head == before_head:
        ok("origin fikstur reposunun HEAD'i degismedi (commit/push YOK)")
    else:
        bad("origin HEAD", "onceki=%s sonraki=%s" % (before_head, after_head))
    shutil.rmtree(base, ignore_errors=True)


def main():
    if not shutil.which("node"):
        print("node gerekli"); return 1
    if not shutil.which("git"):
        print("git gerekli"); return 1
    for fn in (t_gate_blocks_on_test_failure,):
        try:
            fn()
        except Exception:
            import traceback
            bad(fn.__name__, traceback.format_exc(limit=4).splitlines()[-1])
    print("\n================================")
    print("GATE BLOCK TOPLAM: %s%d PASS%s / %s%d FAIL%s" % (OK, PASS, Z, ER, FAIL, Z))
    print("================================")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
