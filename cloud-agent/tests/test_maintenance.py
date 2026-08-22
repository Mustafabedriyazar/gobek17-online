# -*- coding: utf-8 -*-
"""Maintenance lane: durum makinesi, yol guvenligi, LKG, restart-safe resume."""
import json
import shutil
import tempfile
import types
from pathlib import Path

from g17cloud import ai_worker as aiw
from g17cloud import maintenance as M


def _cfg(tmp):
    return types.SimpleNamespace(
        state_dir=Path(tmp), work_dir=Path(tmp) / "work",
        self_repo="owner/agent-repo", self_repo_dir=Path(tmp) / "work" / "self-repo",
        branch="main", test_timeout=60,
        ai_auth_mode=lambda: "ANTHROPIC_API_READY")


def check_lane_detection():
    for b in ("bakim", "BAKIM", "maintenance", " Self ", "agent"):
        assert M.is_maintenance(b), b
    for b in ("v171", "171", "", None, "v1", "release"):
        assert not M.is_maintenance(b), b


def check_state_order_is_complete():
    order = [M.PREPARED, M.SELF_UPDATE_PENDING, M.PUSHED,
             M.RESTARTED, M.HEALTH_VERIFIED, M.DONE]
    assert len(set(order)) == 6, order
    for s in (M.SELF_UPDATE_PENDING, M.PUSHED, M.RESTARTED, M.HEALTH_VERIFIED):
        assert s in M.NO_REDO_STATES, s
    # PREPARED tekrar edilebilir olmali: henuz push yok, is guvenle yenilenir.
    assert M.PREPARED not in M.NO_REDO_STATES
    assert M.DONE not in M.NO_REDO_STATES


def check_paths_restricted_to_agent():
    M.MaintenancePipeline.check_paths(["cloud-agent/g17cloud/api.py",
                                       "cloud-agent/tests/test_x.py"])
    for bad in (".github/workflows/x.yml", "app/index.html", "bootstrap.cjs",
                "cloud-agent/../app/x.js", "package.json"):
        try:
            M.MaintenancePipeline.check_paths([bad])
        except M.SelfEditError:
            continue
        raise AssertionError("izin verilmemeliydi: %s" % bad)


def check_last_known_good_roundtrip():
    tmp = tempfile.mkdtemp(prefix="g17lkg-")
    try:
        cfg = _cfg(tmp)
        assert M.read_last_known_good(cfg) is None
        M.write_last_known_good(cfg, "a" * 40, "test")
        got = M.read_last_known_good(cfg)
        assert got["sha"] == "a" * 40, got
        assert got["note"] == "test"
        # ikinci yazim ustune yazar
        M.write_last_known_good(cfg, "b" * 40)
        assert M.read_last_known_good(cfg)["sha"] == "b" * 40
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_resume_never_completes_without_remote_commit():
    """Push basarisizsa gorev DONE gorunmemeli — en kritik guvence."""
    tmp = tempfile.mkdtemp(prefix="g17rs-")
    try:
        store = _FakeStore({"id": "t1", "task": "x", "build": "bakim",
                            "result": {"selfState": M.PUSHED,
                                       "expectedCommit": "c" * 40}})
        mp = _pipeline(tmp, store, remote_has=False)
        mp.resume("t1")
        rec = store.get("t1")
        assert rec["status"] == "failed", rec["status"]
        assert rec["result"]["selfState"] != M.DONE
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_resume_needs_health_before_done():
    tmp = tempfile.mkdtemp(prefix="g17rh-")
    try:
        store = _FakeStore({"id": "t2", "task": "x", "build": "bakim",
                            "result": {"selfState": M.PUSHED,
                                       "expectedCommit": "d" * 40}})
        mp = _pipeline(tmp, store, remote_has=True, healthy=False)
        mp.resume("t2")
        rec = store.get("t2")
        assert rec["status"] == "failed", rec["status"]
        assert rec["result"]["selfState"] == M.RESTARTED, rec["result"]["selfState"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_resume_reaches_done_when_verified():
    tmp = tempfile.mkdtemp(prefix="g17rd-")
    try:
        store = _FakeStore({"id": "t3", "task": "x", "build": "bakim",
                            "result": {"selfState": M.PUSHED,
                                       "expectedCommit": "e" * 40}})
        mp = _pipeline(tmp, store, remote_has=True, healthy=True)
        mp.resume("t3")
        rec = store.get("t3")
        assert rec["status"] == "success", rec["status"]
        assert rec["result"]["selfState"] == M.DONE
        assert rec["result"]["health"] == "PASS"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------ calisma alani izolasyonu
def check_clean_install_leftovers_removes_known_worktree_leftovers():
    """GOREV BASI HAZIRLIK: onceki turdan kalmis worktree/tarama artiklari silinir."""
    tmp = tempfile.mkdtemp(prefix="g17install-")
    try:
        root = Path(tmp)
        for keep in ("g17cloud", "guards", "tests"):
            (root / keep).mkdir()
            (root / keep / "marker.py").write_text("x", encoding="utf-8")
        (root / "wt-t_old1").mkdir()
        (root / "wt-t_old1" / "junk.txt").write_text("x", encoding="utf-8")
        (root / "self-wt-t_old2").mkdir()
        (root / "gobek17-app.zip").write_text("x", encoding="utf-8")

        removed = aiw.clean_install_leftovers(root=root)

        assert set(removed) == {"wt-t_old1", "self-wt-t_old2", "gobek17-app.zip"}, removed
        assert not (root / "wt-t_old1").exists()
        assert not (root / "self-wt-t_old2").exists()
        assert not (root / "gobek17-app.zip").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_clean_install_leftovers_never_touches_unrelated_files():
    """ALLOWLIST disi HICBIR SEYE dokunulmaz — Procfile/README/kaynak dahil."""
    tmp = tempfile.mkdtemp(prefix="g17install2-")
    try:
        root = Path(tmp)
        for keep in ("g17cloud", "guards", "tests"):
            (root / keep).mkdir()
            (root / keep / "marker.py").write_text("kaynak", encoding="utf-8")
        (root / "Procfile").write_text("web: python -m g17cloud", encoding="utf-8")
        (root / "requirements.txt").write_text("x", encoding="utf-8")
        (root / "README.md").write_text("x", encoding="utf-8")
        (root / ".git").mkdir()

        removed = aiw.clean_install_leftovers(root=root)

        assert removed == [], removed
        for keep in ("g17cloud", "guards", "tests"):
            assert (root / keep / "marker.py").read_text(encoding="utf-8") == "kaynak"
        assert (root / "Procfile").exists()
        assert (root / "requirements.txt").exists()
        assert (root / "README.md").exists()
        assert (root / ".git").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_cleanup_task_workspace_is_isolated_per_task():
    tmp = tempfile.mkdtemp(prefix="g17wsiso-")
    try:
        cfg = _cfg(tmp)
        (cfg.work_dir / "wt-t1").mkdir(parents=True)
        (cfg.work_dir / "wt-t1" / "x.txt").write_text("t1 uretimi", encoding="utf-8")
        (cfg.work_dir / "self-wt-t1").mkdir(parents=True)
        (cfg.work_dir / "wt-t2").mkdir(parents=True)
        (cfg.work_dir / "wt-t2" / "y.txt").write_text("t2 kendi is", encoding="utf-8")

        removed = aiw.cleanup_task_workspace(cfg, "t1")

        assert not (cfg.work_dir / "wt-t1").exists(), "t1 gecici alani kalmis"
        assert not (cfg.work_dir / "self-wt-t1").exists(), "t1 worktree kaydi kalmis"
        assert (cfg.work_dir / "wt-t2").exists(), "baska gorevin alani yanlislikla silindi"
        assert (cfg.work_dir / "wt-t2" / "y.txt").read_text(encoding="utf-8") == "t2 kendi is"
        assert len(removed) == 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_cleanup_task_workspace_never_touches_persistent_state_dir():
    tmp = tempfile.mkdtemp(prefix="g17wspersist-")
    try:
        cfg = _cfg(tmp)
        (cfg.state_dir / "tasks").mkdir(parents=True)
        (cfg.state_dir / "tasks" / "t1.json").write_text('{"id":"t1"}', encoding="utf-8")
        (cfg.state_dir / "artifacts").mkdir(parents=True)
        (cfg.state_dir / "artifacts" / "v1.zip").write_text("art", encoding="utf-8")
        (cfg.work_dir / "wt-t1").mkdir(parents=True)

        aiw.cleanup_task_workspace(cfg, "t1")

        assert (cfg.state_dir / "tasks" / "t1.json").is_file(), "kalici gorev kaydi silindi"
        assert (cfg.state_dir / "artifacts" / "v1.zip").is_file(), "kalici artifact silindi"
        assert not (cfg.work_dir / "wt-t1").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ yardimci
class _FakeStore:
    def __init__(self, rec):
        self.rec = dict(rec)
        self.rec.setdefault("status", "running")
        self.rec.setdefault("events", [])

    def get(self, tid):
        return dict(self.rec) if tid == self.rec["id"] else None

    def update(self, tid, **f):
        res = f.pop("result", None)
        if res is not None:
            self.rec["result"] = res
        self.rec.update(f)
        return dict(self.rec)

    def event(self, tid, phase, msg, **extra):
        self.rec.setdefault("events", []).append({"phase": phase, "message": msg})


def _pipeline(tmp, store, remote_has=True, healthy=True):
    cfg = _cfg(tmp)
    mp = M.MaintenancePipeline.__new__(M.MaintenancePipeline)
    mp.cfg = cfg
    mp.store = store
    mp.lock = None
    mp.log = lambda *a: None
    mp.gh = lambda: _FakeGH()
    mp.remote_has = lambda gh, sha: remote_has
    mp.health_ok = lambda: healthy
    return mp


class _FakeGH:
    def clone_or_update(self):
        return True
