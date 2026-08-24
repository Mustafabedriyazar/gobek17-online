# -*- coding: utf-8 -*-
"""INFRA-4 — altyapi kapilarinin KALICI kaniti (INFRA-1B/1C/1D/3 bugun eklendi).

Bu dosya, ayni surecte tekrar tekrar ihlal edilebilecek dort davranisi
kilitler:

  1) Pipeline.run() FINALLY icinde: basarili/basarisiz/istisna firlatan HER
     gorevden sonra kendi worktree'si (work_dir/wt-<id>) kalmaz (bkz.
     pipeline.py run() finally: gh.remove_worktree + aiw.cleanup_task_workspace).
  2) Ardisik gorev dongusunde worktree birikmez (dizin sayisi sifirda kalir).
  3) Gorev-oncesi orphan supurme (_sweep_stale_state_once), o an aktif olan
     gorevin worktree'sine DOKUNMAZ; yalnizca eslesmeyen orphan girdileri siler.
  4) POST /tasks disk kapisi (_disk_gate/_DISK_CRIT_FREE_PCT): bos alan esigin
     altindaysa gorev kuyruga ALINMADAN 507 INSUFFICIENT_WORKSPACE_DISK doner.
  5) Tek aktif gorev kilidi (Service._active_lock/_active_task_id): ikinci eş
     zamanli istek BUSY alir, paralel calismaz; gorev bitince kilit birakilir
     ve sonraki istek normal kabul edilir.

Gercek git/node/GitHub/Railway'e DOKUNMAZ: Pipeline gercek Config ile kurulur
(gercek guards_dir icin — bkz. _stamp_release/_py), ama gh/guard/ai katmanlari
GERCEK DOSYA SISTEMI yan etkili (worktree GERCEKTEN olusur/silinir) sahte
nesnelerle degistirilir. Kalip test_no_change_required.py / test_maintenance.py
ile ayni: Pipeline gercek constructor ile kurulup gh/guard/ai cagiran alanlari
sonradan sahte ile degistirilir.
"""
import json
import shutil
import sys
import tempfile
import threading
import time
import types
from collections import namedtuple
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent
for _p in (str(AGENT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from g17cloud import pipeline as P                          # noqa: E402
from g17cloud.api import Service, make_handler               # noqa: E402
from g17cloud.config import Config                            # noqa: E402
from g17cloud.pipeline import Pipeline                        # noqa: E402
from g17cloud.release_guard import GuardFailure                # noqa: E402
from g17cloud.store import ReleaseLock, TaskStore              # noqa: E402

import urllib.error   # noqa: E402
import urllib.request  # noqa: E402


# ============================================================ ortak yardimcilar
def _wt_entries(work_dir):
    """work_dir altinda kalan worktree benzeri dizinler (wt-*/self-wt-*)."""
    work_dir = Path(work_dir)
    if not work_dir.is_dir():
        return []
    return sorted(e.name for e in work_dir.iterdir()
                  if e.is_dir() and (e.name.startswith("wt-") or
                                      e.name.startswith("self-wt-")))


def _fake_pipeline_cfg(tmp, repo="owner/game-repo", self_repo="owner/agent-repo"):
    """GERCEK Config: guards_dir/state_dir/work_dir dogru turetilsin diye
    (bkz. pipeline._stamp_release -> release_guard._py, guards/version_guard.py
    calistirir). Repo GERCEK git DEGILDIR — gh katmani asagida sahte."""
    cfg = Config(env={
        "G17_STATE_DIR": str(Path(tmp) / "state"),
        "G17_WORK_DIR": str(Path(tmp) / "work"),
        "G17_REPO": repo, "G17_SELF_REPO": self_repo, "G17_BRANCH": "main",
        "G17_API_TOKEN": "test-token", "AI_PROVIDER": "mock",
        "MAX_AGENT_REPAIR_ATTEMPTS": "3", "TEST_TIMEOUT_SECONDS": "60",
    })
    cfg.ensure_dirs()
    return cfg


def _fake_pipeline(tmp, gh, guard, ai):
    """Pipeline GERCEK constructor ile kurulur (gercek ReleaseLock/TaskStore/
    guards_dir); yalniz git/AI cagiran katmanlar (gh/guard/ai) sahte ile
    degistirilir. Bkz. tests/test_no_change_required.py._release_pipeline."""
    cfg = _fake_pipeline_cfg(tmp)
    store = TaskStore(cfg.state_dir)
    lock = ReleaseLock(cfg.state_dir)
    pl = Pipeline(cfg, store, lock, log=lambda *a, **k: None)
    pl.gh = gh
    pl.guard = guard
    pl.ai = ai
    return pl, cfg, store


class _RealFsGH:
    """GERCEK DOSYA SISTEMI yan etkili sahte git katmani: worktree GERCEKTEN
    olusur/silinir (shutil ile), ama gercek git/GitHub'a HICBIR cagri gitmez."""

    def clone_or_update(self):
        return True

    def short_head(self):
        return "abc1234"

    def auth_status(self):
        return {"write": "OK"}

    def is_clean(self):
        return True

    def _git(self, args, cwd=None, check=True):
        return ""

    def make_worktree(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def remove_worktree(self, path):
        shutil.rmtree(str(path), ignore_errors=True)

    def commit(self, msg):
        return "deadbeef"

    def push(self):
        return True

    def staged_files(self):
        return []

    def diff_cached(self):
        return ""

    def wait_actions(self, sha, timeout=600):
        return {"result": "N/A", "runs": []}

    def head(self):
        return "deadbeef"


class _OkGuard:
    """Guard zincirinin TAMAMI PASS eder — gorev basariya kadar ilerler."""

    def discover_tests(self, rd, build):
        return []

    def block_hashes(self, wt):
        return {}

    def check_canonical(self, before, after):
        return {"status": "PASS"}

    def repo_build(self, repo_dir):
        return 170

    def check_sequential(self, cur, build):
        return {"current": cur, "target": build}

    def run_tests(self, wt, build):
        return {"ok": True, "summary": "0 fail", "failed": []}

    def verify_artifact(self, wt, build):
        return True

    def build_artifact(self, wt, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"PK\x03\x04fake")
        return {"path": str(dest), "sha256": "0" * 64}


class _FailGuard(_OkGuard):
    """Guard zincirinde DETERMINISTIK RED (GuardFailure) — istisna DEGIL."""

    def check_canonical(self, before, after):
        raise GuardFailure("ENGINE_GUARD", "kanonik blok degisti", {})


class _CrashGuard(_OkGuard):
    """Guard zincirinde BEKLENMEYEN istisna (GuardFailure DEGIL) — gorev
    Pipeline.run()'un genel 'except Exception' (INTERNAL) yoluna duser."""

    def check_sequential(self, cur, build):
        raise RuntimeError("beklenmeyen ic hata")


class _SuccessAI:
    """inspect fazinda reproduced:true, implement fazinda TEK dosyalik gercek
    bir edit dondurur (apply_edits GERCEKTEN calisir, worktree'ye yazar)."""

    def select(self, task, provider):
        return "mock"

    def call(self, provider, system, prompt, cwd=None):
        if "faz: inspect" in prompt:
            return ('{"reproduced": true, "rootCause": "rc", "files": [], '
                     '"minimalFix": "mf", "tests": [], "title": "t"}')
        if "faz: implement" in prompt:
            return json.dumps({"edits": [{"path": "server/x.txt", "action": "create",
                                          "new": "ok"}], "summary": "s"})
        return "{}"


# ================================================== 1/2/3) worktree TEMIZLIK garantisi
def check_worktree_removed_after_successful_task():
    tmp = tempfile.mkdtemp(prefix="g17infra4-ok-")
    try:
        pl, cfg, store = _fake_pipeline(tmp, _RealFsGH(), _OkGuard(), _SuccessAI())
        rec = store.create("v171", "basarili gorev", "mock", True, False, "fix")
        result = pl.run(rec["id"])
        assert result["status"] == "success", result
        assert _wt_entries(cfg.work_dir) == [], _wt_entries(cfg.work_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_worktree_removed_after_failed_task():
    tmp = tempfile.mkdtemp(prefix="g17infra4-fail-")
    try:
        pl, cfg, store = _fake_pipeline(tmp, _RealFsGH(), _FailGuard(), _SuccessAI())
        rec = store.create("v171", "basarisiz gorev", "mock", True, False, "fix")
        result = pl.run(rec["id"])
        assert result["status"] == "failed", result
        assert result["result"]["stage"] == "ENGINE_GUARD", result["result"]
        assert _wt_entries(cfg.work_dir) == [], _wt_entries(cfg.work_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_worktree_removed_after_task_raises_unexpected_exception():
    tmp = tempfile.mkdtemp(prefix="g17infra4-crash-")
    try:
        pl, cfg, store = _fake_pipeline(tmp, _RealFsGH(), _CrashGuard(), _SuccessAI())
        rec = store.create("v171", "cokerten gorev", "mock", True, False, "fix")
        result = pl.run(rec["id"])
        assert result["status"] == "failed", result
        assert result["result"]["stage"] == "INTERNAL", result["result"]
        assert _wt_entries(cfg.work_dir) == [], _wt_entries(cfg.work_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_ten_sequential_pipeline_runs_leave_zero_worktree_dirs():
    """En az on ardisik gorev (basarili/basarisiz/cokme karisik) sonrasi
    work_dir'de HICBIR worktree dizini kalmaz — birikme YOK."""
    tmp = tempfile.mkdtemp(prefix="g17infra4-seq-")
    try:
        variants = [_OkGuard, _FailGuard, _CrashGuard, _FailGuard, _OkGuard,
                    _CrashGuard, _OkGuard, _FailGuard, _CrashGuard, _OkGuard]
        assert len(variants) == 10
        work_dir = Path(tmp) / "work"
        for i, guard_cls in enumerate(variants):
            pl, cfg, store = _fake_pipeline(tmp, _RealFsGH(), guard_cls(), _SuccessAI())
            rec = store.create("v171", "seq-%d" % i, "mock", True, False, "fix")
            result = pl.run(rec["id"])
            assert result is not None, i
            entries = _wt_entries(work_dir)
            assert entries == [], ("gorev %d (%s) sonrasi worktree kaldi: %s"
                                   % (i, guard_cls.__name__, entries))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ========================================================== 3) orphan supurme
def check_orphan_sweep_preserves_active_task_worktree():
    """_sweep_stale_state_once: o an aktif olan gorevin worktree'sine
    DOKUNMAZ; yalnizca eslesmeyen wt-*/self-wt-* orphan girdileri siler."""
    tmp = tempfile.mkdtemp(prefix="g17infra4-orphan-")
    try:
        state_dir = Path(tmp) / "state"
        work_dir = Path(tmp) / "work"
        repo_dir = Path(tmp) / "repo"
        state_dir.mkdir()
        work_dir.mkdir()
        repo_dir.mkdir()

        task_id = "t_active123"
        active_wt = work_dir / ("wt-%s" % task_id)
        active_wt.mkdir()
        (active_wt / "marker.txt").write_text("bu gorevin aktif calisma alani",
                                               encoding="utf-8")
        orphan1 = work_dir / "wt-orphan-aaa"
        orphan1.mkdir()
        orphan2 = work_dir / "self-wt-orphan-bbb"
        orphan2.mkdir()
        unrelated = work_dir / "not-a-worktree"
        unrelated.mkdir()

        cfg = types.SimpleNamespace(state_dir=state_dir, work_dir=work_dir,
                                    repo_dir=repo_dir)
        gh = types.SimpleNamespace(_git=lambda *a, **k: "")
        events = []

        def ev(tid, phase, msg, **extra):
            events.append((tid, phase, msg))

        old_flag = P._state_sweep_done
        P._state_sweep_done = False
        try:
            P._sweep_stale_state_once(cfg, gh, ev, task_id)
        finally:
            P._state_sweep_done = old_flag

        assert active_wt.is_dir(), "aktif gorevin worktree'si supurmede silindi"
        assert (active_wt / "marker.txt").is_file(), "aktif worktree icerigi kayboldu"
        assert not orphan1.exists(), "orphan wt- dizini silinmedi"
        assert not orphan2.exists(), "orphan self-wt- dizini silinmedi"
        assert unrelated.is_dir(), "desene uymayan dizin yanlislikla silindi"
        assert events, "supurme hicbir olay yazmadi"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ========================================================== 4) disk kapisi
def check_disk_gate_rejects_task_below_threshold_and_does_not_queue():
    """POST /tasks: bos alan yuzdesi kritik esigin ALTINDAYSA 507
    INSUFFICIENT_WORKSPACE_DISK doner ve gorev KUYRUGA GIRMEZ."""
    tmp = tempfile.mkdtemp(prefix="g17infra4-disk-")
    try:
        cfg = _fake_pipeline_cfg(tmp)
        svc = Service(cfg)
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

        try:
            before = len(svc.store.list(limit=50))
            FakeUsage = namedtuple("FakeUsage", "total used free")
            real_disk_usage = shutil.disk_usage
            shutil.disk_usage = lambda path: FakeUsage(total=1000, used=990, free=10)
            try:
                st, body = call("/tasks", "POST",
                                {"build": "v171", "task": "disk kapisi testi"})
            finally:
                shutil.disk_usage = real_disk_usage

            assert st == 507, (st, body)
            assert body.get("code") == "INSUFFICIENT_WORKSPACE_DISK", body
            after = len(svc.store.list(limit=50))
            assert after == before, "reddedilen istek yine de gorev kaydi olusturdu"
        finally:
            httpd.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================== 5) tek aktif gorev kilidi
def check_second_submit_while_task_active_gets_busy_and_no_duplicate_record():
    tmp = tempfile.mkdtemp(prefix="g17infra4-busy-")
    try:
        cfg = _fake_pipeline_cfg(tmp)
        svc = Service(cfg)

        rec1, busy1 = svc.submit("v171", "birinci gorev", "mock", False, False, "fix")
        assert rec1 is not None and busy1 is None, (rec1, busy1)
        assert svc._active_task_id == rec1["id"]

        rec2, busy2 = svc.submit("v171", "ikinci gorev", "mock", False, False, "fix")
        assert rec2 is None, "aktif gorev varken ikinci istek kabul edildi"
        assert busy2 == rec1["id"], (busy2, rec1["id"])

        tasks = svc.store.list(limit=50)
        assert len(tasks) == 1, "reddedilen istek yine de kayit olusturdu: %s" % tasks

        svc._release_active(rec1["id"])
        assert svc._active_task_id is None

        rec3, busy3 = svc.submit("v171", "ucuncu gorev", "mock", False, False, "fix")
        assert rec3 is not None and busy3 is None, (rec3, busy3)
        assert rec3["id"] != rec1["id"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_concurrent_submits_accept_exactly_one_task():
    """Sekiz thread AYNI ANDA submit() cagirir: TAM OLARAK biri kazanir,
    digerleri BUSY alir ve hicbir kayit birakmaz (paralel gorev YOK)."""
    tmp = tempfile.mkdtemp(prefix="g17infra4-conc-")
    try:
        cfg = _fake_pipeline_cfg(tmp)
        svc = Service(cfg)
        results = []
        results_lock = threading.Lock()

        def attempt(i):
            rec, busy = svc.submit("v171", "concurrent-%d" % i, "mock", False, False, "fix")
            with results_lock:
                results.append((rec, busy))

        threads = [threading.Thread(target=attempt, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 8
        winners = [r for r, b in results if r is not None]
        assert len(winners) == 1, "birden fazla gorev ayni anda kabul edildi (%d)" % len(winners)
        winner_id = winners[0]["id"]
        losers = [b for r, b in results if r is None]
        assert len(losers) == 7
        assert all(b == winner_id for b in losers), losers
        assert len(svc.store.list(limit=50)) == 1, "reddedilen istekler kayit birakti"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_active_lock_released_after_task_completes_allows_next_task():
    """Gorev (gercek worker thread'i uzerinden) bittiginde aktif gorev kilidi
    birakilir ve sonraki gorev normal kabul edilir — worktree de kalmaz."""
    tmp = tempfile.mkdtemp(prefix="g17infra4-release-")
    try:
        cfg = _fake_pipeline_cfg(tmp)
        svc = Service(cfg)
        svc.pipeline.gh = _RealFsGH()
        svc.pipeline.guard = _OkGuard()
        svc.pipeline.ai = _SuccessAI()
        svc.start_workers(1)

        rec1, busy1 = svc.submit("v171", "ilk gorev", "mock", True, False, "fix")
        assert rec1 is not None and busy1 is None, (rec1, busy1)

        finished = None
        for _ in range(200):
            cur = svc.store.get(rec1["id"])
            if cur["status"] in ("success", "failed"):
                finished = cur
                break
            time.sleep(0.05)
        assert finished is not None, "gorev zaman asiminda bitmedi"
        assert finished["status"] == "success", finished

        for _ in range(100):
            if svc._active_task_id is None:
                break
            time.sleep(0.02)
        assert svc._active_task_id is None, "gorev bittikten sonra aktif gorev kilidi hala tutuluyor"

        rec2, busy2 = svc.submit("v172", "ikinci gorev", "mock", True, False, "fix")
        assert rec2 is not None and busy2 is None, (rec2, busy2)
        assert rec2["id"] != rec1["id"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
