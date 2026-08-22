#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — yerel/mock test paketi.

GERCEK GitHub'a veya production'a ASLA dokunmaz: origin yerel bare repo,
AI mock saglayici, health sahte okuyucu. Node gerekir (oyun testleri .cjs).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from g17cloud.ai_worker import (UnsafeEdit, apply_edits, parse_json_block,  # noqa: E402
                                route_provider, scrub_env)
from g17cloud.api import Service, make_handler  # noqa: E402
from g17cloud.config import Config  # noqa: E402
from g17cloud.github_core import ForbiddenGitOperation, GitHubCore  # noqa: E402
from g17cloud.production import ProductionController  # noqa: E402
from g17cloud.release_guard import GuardFailure  # noqa: E402
from g17cloud.store import ReleaseLock, TaskStore  # noqa: E402

PASS = FAIL = 0
OK, ER, DIM, Z = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    OK = ER = DIM = Z = ""


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
def t_routing():
    head("1) provider routing: buyuk is -> FABLE, cerrahi is -> OPUS")
    if route_provider("tum ranked sistemini yeniden yaz") == "fable":
        ok("buyuk kapsam FABLE'a yonlendi")
    else:
        bad("routing", "fable degil")
    if route_provider("ranked panelinde bug var, root cause bul") == "opus":
        ok("audit/debug OPUS'a yonlendi")
    else:
        bad("routing", "opus degil")
    if route_provider("herhangi bir sey", "fable") == "fable":
        ok("acik provider parametresi routing'i eziyor")
    else:
        bad("routing override", "")


def t_worktree_jail():
    head("2) AI worktree hapsi: disari yazma REDDEDILIR")
    d = Path(tempfile.mkdtemp())
    (d / "wt").mkdir()
    try:
        apply_edits(d / "wt", [{"path": "../../escape.txt", "action": "create", "new": "x"}])
        bad("path traversal", "izin verildi")
    except UnsafeEdit:
        ok("../ ile disari yazma reddedildi")
    try:
        apply_edits(d / "wt", [{"path": "/etc/passwd", "action": "create", "new": "x"}])
        bad("mutlak yol", "izin verildi")
    except UnsafeEdit:
        ok("mutlak yol reddedildi")
    try:
        apply_edits(d / "wt", [{"path": ".git/config", "action": "create", "new": "x"}])
        bad(".git yazimi", "izin verildi")
    except UnsafeEdit:
        ok(".git altina yazma reddedildi")
    changed = apply_edits(d / "wt", [{"path": "server/x.js", "action": "create", "new": "ok"}])
    if changed == ["server/x.js"] and (d / "wt" / "server" / "x.js").is_file():
        ok("worktree ICINDE yazma calisiyor")
    else:
        bad("izinli yazma", str(changed))
    shutil.rmtree(d, ignore_errors=True)


def t_credential_isolation():
    head("3) AI credential goremez")
    env = {"GITHUB_TOKEN": "gizli", "GH_TOKEN": "gizli", "RAILWAY_TOKEN": "gizli",
           "G17_API_TOKEN": "gizli", "PATH": "/bin"}
    clean = scrub_env(env)
    leaked = [k for k in ("GITHUB_TOKEN", "GH_TOKEN", "RAILWAY_TOKEN", "G17_API_TOKEN")
              if k in clean]
    if not leaked:
        ok("GitHub/Railway/API tokenlari AI ortamindan silindi")
    else:
        bad("credential izolasyonu", str(leaked))
    if clean.get("PATH") == "/bin":
        ok("zararsiz degiskenler korunuyor")
    else:
        bad("env", "PATH kayboldu")


def t_forbidden_git():
    head("4) force push / reset --hard KOD DUZEYINDE engelli")
    base, cfg, _ = make_env("forbidden")
    gh = GitHubCore(cfg)
    gh.clone_or_update()
    for args in (["push", "--force", "origin", "main"],
                 ["reset", "--hard", "HEAD~1"],
                 ["branch", "-D", "main"],
                 ["push", "origin", "--delete", "main"]):
        try:
            gh._git(args)
            bad("yasak islem", " ".join(args))
            break
        except ForbiddenGitOperation:
            pass
    else:
        ok("force/reset/branch-delete/push-delete hepsi engellendi")
    shutil.rmtree(base, ignore_errors=True)


def t_happy_path():
    head("5) TAM AKIS: task -> AI -> test -> guard -> commit -> push -> production")
    base, cfg, origin = make_env("happy")
    svc, rec = run_task(cfg, base, "fix")
    if rec["status"] == "success":
        ok("gorev SUCCESS")
    else:
        bad("tam akis", "%s / %s" % (rec["status"], rec["result"].get("reason")))
        return shutil.rmtree(base, ignore_errors=True)
    r = rec["result"]
    if r.get("commit") and r.get("push") == "PASS":
        ok("commit + push: %s" % r["commit"])
    else:
        bad("push", str(r))
    if git(["log", "-1", "--pretty=%s", "main"], origin).startswith("v171:"):
        ok("origin/main v171 commit'ini aldi")
    else:
        bad("origin", git(["log", "-1", "--pretty=%s", "main"], origin))
    if r.get("healthStamp", "").startswith("gobek17-171-"):
        ok("health damgasi uretildi: %s" % r["healthStamp"])
    else:
        bad("damga", str(r.get("healthStamp")))
    if r.get("sha256") and len(r["sha256"]) == 64:
        ok("artifact SHA256 uretildi")
    else:
        bad("artifact", "")
    if r.get("production") == "PASS":
        ok("production dogrulandi")
    else:
        bad("production", str(r.get("production")))
    shutil.rmtree(base, ignore_errors=True)


def t_secret_blocks():
    head("6) secret sizarsa release IPTAL, push YOK")
    base, cfg, origin = make_env("secret")
    before = git(["rev-list", "--count", "main"], origin)
    svc, rec = run_task(cfg, base, "secret")
    if rec["status"] == "failed" and rec["result"]["stage"] == "SECRET":
        ok("secret guard release'i iptal etti")
    else:
        bad("secret guard", "%s/%s" % (rec["status"], rec["result"].get("stage")))
    if git(["rev-list", "--count", "main"], origin) == before:
        ok("origin degismedi (push YOK)")
    else:
        bad("push", "origin degisti")
    blob = json.dumps(rec)
    if "ghp_AAAA" not in blob:
        ok("secret degeri task kaydina sizmadi")
    else:
        bad("secret sizintisi", "kayitta ham deger var")
    shutil.rmtree(base, ignore_errors=True)


def t_engine_guard():
    head("7) kanonik engine degisirse release IPTAL")
    base, cfg, origin = make_env("engine")
    before = git(["rev-list", "--count", "main"], origin)
    svc, rec = run_task(cfg, base, "engine")
    if rec["status"] == "failed" and rec["result"]["stage"] == "ENGINE_GUARD":
        ok("engine/bot guard release'i iptal etti")
    else:
        bad("engine guard", "%s/%s" % (rec["status"], rec["result"].get("stage")))
    if git(["rev-list", "--count", "main"], origin) == before:
        ok("origin degismedi")
    else:
        bad("push", "origin degisti")
    shutil.rmtree(base, ignore_errors=True)


def t_repair_loop():
    head("8) onarim dongusu: sinirli, sonsuz DEGIL")
    base, cfg, origin = make_env("repair")
    svc, rec = run_task(cfg, base, "repair")
    if rec["status"] == "success" and rec["attempts"] >= 1:
        ok("test FAIL -> AI onarimi -> PASS (%d tur)" % rec["attempts"])
    else:
        bad("repair", "%s attempts=%s" % (rec["status"], rec.get("attempts")))
    shutil.rmtree(base, ignore_errors=True)

    base, cfg, origin = make_env("repairfail")
    before = git(["rev-list", "--count", "main"], origin)
    svc, rec = run_task(cfg, base, "testfail")
    if rec["status"] == "failed" and rec["result"]["stage"] == "TEST_REPAIR":
        ok("3 turda duzelmedi -> DURDU (sonsuz retry yok)")
    else:
        bad("repair limit", "%s/%s" % (rec["status"], rec["result"].get("stage")))
    if rec["result"].get("detail", {}).get("attempts") == 3:
        ok("tam olarak 3 onarim denendi")
    else:
        bad("repair sayisi", str(rec["result"].get("detail")))
    if git(["rev-list", "--count", "main"], origin) == before:
        ok("test FAIL -> push YOK")
    else:
        bad("push", "origin degisti")
    shutil.rmtree(base, ignore_errors=True)


def t_sequential():
    head("9) ardisik build: v170 -> v172 RED, geri surum RED")
    base, cfg, origin = make_env("seq")
    svc, rec = run_task(cfg, base, "fix", build="v173")
    if rec["status"] == "failed" and rec["result"]["stage"] == "VERSION":
        ok("sira disi build reddedildi (v170 -> v173)")
    else:
        bad("sequential", "%s/%s" % (rec["status"], rec["result"].get("stage")))
    shutil.rmtree(base, ignore_errors=True)

    base, cfg, origin = make_env("seqback")
    svc, rec = run_task(cfg, base, "fix", build="v169")
    if rec["status"] == "failed" and rec["result"]["stage"] == "VERSION":
        ok("geri surum (rollback) reddedildi")
    else:
        bad("rollback", "%s/%s" % (rec["status"], rec["result"].get("stage")))
    shutil.rmtree(base, ignore_errors=True)


def t_release_lock():
    head("10) tek release kilidi: iki build ayni anda main'e cikamaz")
    base = Path(tempfile.mkdtemp())
    lock = ReleaseLock(base)
    if lock.acquire("t1", 171):
        ok("ilk release kilidi aldi")
    else:
        bad("kilit", "alinamadi")
    if not lock.acquire("t2", 172):
        ok("ikinci release REDDEDILDI (paralel main push yok)")
    else:
        bad("kilit", "ikinci de aldi")
    lock.release("t1")
    if lock.acquire("t2", 172):
        ok("birakildiktan sonra ikinci alabildi")
    else:
        bad("kilit", "release sonrasi alinamadi")
    lock.release("t2")
    shutil.rmtree(base, ignore_errors=True)


def t_persistence_recovery():
    head("11) restart kurtarma: yarim task kaybolmaz, push edilmis task korunur")
    base, cfg, origin = make_env("recover")
    store = TaskStore(cfg.state_dir)
    a = store.create("v171", "yarim kalan is")
    store.update(a["id"], status="running", phase="implement")
    b = store.create("v171", "push edilmis is")
    store.update(b["id"], status="running", phase="push",
                 result={"pushed": True, "commit": "abc1234"})
    svc = Service(cfg)
    svc.recover()
    ra, rb = svc.store.get(a["id"]), svc.store.get(b["id"])
    if ra["status"] == "queued":
        ok("yarim task yeniden kuyruga alindi")
    else:
        bad("recovery", ra["status"])
    if rb["status"] == "needs_review" and rb["phase"] == "RECOVERY_REQUIRES_REVIEW":
        ok("push edilmis task otomatik tekrarlanmadi (duplicate release yok)")
    else:
        bad("recovery review", "%s/%s" % (rb["status"], rb["phase"]))
    shutil.rmtree(base, ignore_errors=True)


def t_health_gate():
    head("12) production: beklenen damga gelmeden SUCCESS YOK")
    base, cfg, origin = make_env("health")
    svc, rec = run_task(cfg, base, "fix", health="TIMEOUT")
    if rec["status"] == "failed" and rec["result"]["stage"] == "PRODUCTION":
        ok("damga gelmedi -> SUCCESS verilmedi")
    else:
        bad("health gate", "%s/%s" % (rec["status"], rec["result"].get("stage")))
    if rec["result"].get("commit"):
        ok("commit KORUNDU (otomatik rollback yok)")
    else:
        bad("rollback", "commit kayboldu")
    shutil.rmtree(base, ignore_errors=True)

    # eski damga = "hala bekleniyor", FAIL degil
    seq = ["gobek17-170-eski", "gobek17-170-eski", "gobek17-171-yeni"]
    pc = ProductionController(Config(env={"G17_HEALTH_URL": "http://x/health",
                                          "RAILWAY_WAIT_SECONDS": "30",
                                          "HEALTH_POLL_SECONDS": "1"}))
    calls = {"n": 0}

    def opener(url):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return json.dumps({"ok": True, "build": seq[i]})

    res = pc.wait_for("gobek17-171-yeni", sleep=lambda s: None, opener=opener)
    if res["result"] == "PASS" and calls["n"] >= 3:
        ok("eski damga beklendi, yeni gelince PASS")
    else:
        bad("health polling", str(res))


def t_dry_run():
    head("13) dry-run / no-deploy: commit ve push YOK")
    base, cfg, origin = make_env("dry")
    before = git(["rev-list", "--count", "main"], origin)
    svc, rec = run_task(cfg, base, "fix", dry_run=True)
    if rec["status"] == "success" and rec["result"].get("push") == "SKIPPED":
        ok("dry-run: paket uretildi, push atlandi")
    else:
        bad("dry-run", "%s/%s" % (rec["status"], rec["result"].get("push")))
    if git(["rev-list", "--count", "main"], origin) == before:
        ok("origin degismedi")
    else:
        bad("dry-run push", "origin degisti")
    if rec["result"].get("sha256"):
        ok("dry-run yine de artifact + SHA uretti")
    else:
        bad("dry-run artifact", "")
    shutil.rmtree(base, ignore_errors=True)


def t_api():
    head("14) HTTP API: /health, yetki, POST /tasks, GET /tasks/:id")
    base, cfg, origin = make_env("api")
    os.environ["G17_MOCK_SCRIPT"] = str(mock_script(base, "fix"))
    svc = Service(cfg)
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    root = "http://127.0.0.1:%d" % port

    def call(path, method="GET", body=None, token="test-token"):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(root + path, data=data, method=method)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as ex:
            return ex.code, json.loads(ex.read().decode() or "{}")

    st, body = call("/health", token=None)
    if st == 200 and body.get("ok"):
        ok("/health kimlik istemeden calisiyor")
    else:
        bad("/health", str(body))
    st, _ = call("/status", token=None)
    if st == 401:
        ok("tokensiz /status REDDEDILDI (401)")
    else:
        bad("yetki", "st=%s" % st)
    st, _ = call("/tasks", "POST", {"build": "v171", "task": "x"}, token="yanlis")
    if st == 401:
        ok("yanlis token ile POST /tasks reddedildi")
    else:
        bad("yetki", "st=%s" % st)
    st, body = call("/tasks", "POST", {"build": "bozuk", "task": "x"})
    if st == 400:
        ok("gecersiz build 400 donuyor")
    else:
        bad("dogrulama", "st=%s" % st)
    st, body = call("/tasks", "POST",
                    {"build": "v171", "task": "ranked panelini duzelt",
                     "provider": "mock", "dryRun": True})
    if st == 202 and body.get("id"):
        ok("POST /tasks -> 202 + task id (%s)" % body["id"])
        tid = body["id"]
    else:
        bad("POST /tasks", str(body))
        tid = None
    st, body = call("/status")
    if st == 200 and "github" in body and "releaseLock" in body:
        ok("/status servis+github+lock ozeti donuyor")
    else:
        bad("/status", str(body)[:120])
    blob = json.dumps(body)
    if "test-token" not in blob:
        ok("/status API token'ini ifsa etmiyor")
    else:
        bad("sir sizintisi", "token /status'ta")
    if tid:
        svc.start_workers(1)
        for _ in range(120):
            rec = svc.store.get(tid)
            if rec["status"] in ("success", "failed"):
                break
            time.sleep(0.25)
        st, body = call("/tasks/%s" % tid)
        rec = body.get("task", {})
        if st == 200 and rec.get("status") == "success":
            ok("GET /tasks/:id gorevi cloud'da tamamlanmis gosteriyor")
        else:
            bad("task akisi", "%s / %s" % (rec.get("status"), rec.get("result", {}).get("reason")))
        if [e for e in rec.get("events", []) if e["phase"] == "root-cause"]:
            ok("faz gecisleri kaydedildi (root-cause dahil)")
        else:
            bad("faz kaydi", "olay yok")
    httpd.shutdown()
    shutil.rmtree(base, ignore_errors=True)


def t_no_repro():
    head("15) AI reproduce edemezse: genis refactor YOK, gorev durur")
    base, cfg, origin = make_env("norepro")
    before = git(["rev-list", "--count", "main"], origin)
    svc, rec = run_task(cfg, base, "norepro")
    if rec["status"] == "failed" and rec["result"]["stage"] == "REPRODUCE":
        ok("reproduce edilemedi -> durdu")
    else:
        bad("no-repro", "%s/%s" % (rec["status"], rec["result"].get("stage")))
    if git(["rev-list", "--count", "main"], origin) == before:
        ok("push YOK")
    else:
        bad("push", "origin degisti")
    shutil.rmtree(base, ignore_errors=True)


def t_ai_escape_via_pipeline():
    head("16) AI pipeline icinde disari yazmaya calisirsa gorev DUSER")
    base, cfg, origin = make_env("escape")
    before = git(["rev-list", "--count", "main"], origin)
    svc, rec = run_task(cfg, base, "escape")
    if rec["status"] == "failed":
        ok("kacis denemesi gorevi dusurdu (%s)" % rec["result"]["stage"])
    else:
        bad("kacis", rec["status"])
    if not (base / "escaped.txt").exists() and not Path("/tmp/escaped.txt").exists():
        ok("worktree disina dosya YAZILMADI")
    else:
        bad("kacis", "dosya olustu")
    if git(["rev-list", "--count", "main"], origin) == before:
        ok("push YOK")
    else:
        bad("push", "origin degisti")
    shutil.rmtree(base, ignore_errors=True)


def t_no_eval():
    head("17) AI ciktisi kabuk/kod olarak calistirilmiyor")
    src = ""
    for p in (ROOT / "g17cloud").glob("*.py"):
        src += p.read_text(encoding="utf-8")
    hits = [ln.strip() for ln in src.splitlines()
            if ("eval(" in ln or "exec(" in ln) and not ln.strip().startswith("#")]
    if not hits:
        ok("kaynakta eval()/exec() YOK")
    else:
        bad("eval", str(hits[:3]))
    if "shell=True" not in src:
        ok("subprocess shell=True kullanilmiyor")
    else:
        bad("shell", "shell=True var")
    try:
        parse_json_block("bunlar cop __import__('os').system('x')")
        bad("json parse", "cop kabul edildi")
    except Exception:
        ok("JSON olmayan AI ciktisi reddediliyor")



# ============================================================ v2.1 ABONELIK KIMLIGI
def t_subscription_auth():
    """API key ZORUNLU DEGIL; abonelik token'i ile calisir ve token SIZMAZ."""
    import importlib
    from g17cloud import config as _cfg
    head("18) abonelik kimligi: API key zorunlu degil, token sizmiyor")

    def mode(env):
        keys = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
        old = {k: os.environ.get(k) for k in keys}
        for k in keys:
            os.environ.pop(k, None)
        os.environ.update(env)
        try:
            importlib.reload(_cfg)
            c = _cfg.Config()
            return c.ai_auth_mode(), c
        finally:
            for k in keys:
                os.environ.pop(k, None)
                if old[k] is not None:
                    os.environ[k] = old[k]

    m, _ = mode({})
    ok("kimlik yoksa AI_UNAUTHENTICATED") if m == "AI_UNAUTHENTICATED" else bad("AI_UNAUTHENTICATED", m)

    # Sahte kimlikler CALISMA ANINDA birlestirilir: repoda token-SEKLINDE literal
    # kalmasin (bootstrap secret guard'i hakli olarak takiliyordu). Testin
    # gecerliligi degismez — degerler yine gercek desene sahip.
    SK = "sk-" + "ant-"
    OAT = SK + "oat01-SUBSCRIPTIONSECRET"
    KEY = SK + "APIKEYSECRET"
    m, c = mode({"CLAUDE_CODE_OAUTH_TOKEN": OAT})
    ok("abonelik token'i -> CLAUDE_SUBSCRIPTION_READY") if m == "CLAUDE_SUBSCRIPTION_READY" else bad("subscription ready", m)
    ok("claude config dizini kalici state altinda") if "claude" in c.claude_config_dir else bad("config dir", c.claude_config_dir)
    blob = json.dumps(c.public_dict(), ensure_ascii=False)
    ok("token public() ciktisinda GORUNMEZ") if "SUBSCRIPTIONSECRET" not in blob else bad("token sizinti", "public()")

    m, _ = mode({"ANTHROPIC_API_KEY": KEY})
    ok("api key -> ANTHROPIC_API_READY") if m == "ANTHROPIC_API_READY" else bad("api ready", m)
    m, _ = mode({"ANTHROPIC_API_KEY": SK + "A", "CLAUDE_CODE_OAUTH_TOKEN": SK + "oat01-B"})
    ok("ikisi de varsa API yolu tercih edilir") if m == "ANTHROPIC_API_READY" else bad("oncelik", m)

    from g17cloud.ai_worker import scrub_env, SECRET_ENV
    ok("oauth token varsayilan sir listesinde") if "CLAUDE_CODE_OAUTH_TOKEN" in SECRET_ENV else bad("SECRET_ENV", "oauth yok")
    cleaned = scrub_env({"CLAUDE_CODE_OAUTH_TOKEN": "x", "GITHUB_TOKEN": "y", "PATH": "/bin"})
    if "CLAUDE_CODE_OAUTH_TOKEN" not in cleaned and "GITHUB_TOKEN" not in cleaned:
        ok("scrub_env model+altyapi kimliklerini siliyor")
    else:
        bad("scrub_env", str(sorted(cleaned)))

    # Resmi dokuman: bare modu CLAUDE_CODE_OAUTH_TOKEN'i OKUMAZ.
    # Kullanilsaydi abonelik yolu sessizce bozulurdu.
    src = open(os.path.join(ROOT, "g17cloud", "ai_worker.py"), encoding="utf-8").read()
    j = src.find("subprocess.run(")
    call = src[j:j + 1500]
    ok("CLI cagrisinda --bare YOK (abonelik yolunu bozardi)") if "--bare" not in call else bad("--bare", "kullanilmis")


def main():
    if not shutil.which("node"):
        print("node gerekli"); return 1
    if not shutil.which("git"):
        print("git gerekli"); return 1
    for fn in (t_routing, t_worktree_jail, t_credential_isolation, t_forbidden_git,
               t_happy_path, t_secret_blocks, t_engine_guard, t_repair_loop,
               t_sequential, t_release_lock, t_persistence_recovery, t_health_gate,
               t_dry_run, t_api, t_no_repro, t_ai_escape_via_pipeline, t_no_eval,
               t_subscription_auth):
        try:
            fn()
        except Exception:
            import traceback
            bad(fn.__name__, traceback.format_exc(limit=4).splitlines()[-1])
    print("\n================================")
    print("CLOUD TOPLAM: %s%d PASS%s / %s%d FAIL%s" % (OK, PASS, Z, ER, FAIL, Z))
    print("================================")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
