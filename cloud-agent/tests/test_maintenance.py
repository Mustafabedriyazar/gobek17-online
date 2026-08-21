# -*- coding: utf-8 -*-
"""Maintenance lane: durum makinesi, yol guvenligi, LKG, restart-safe resume."""
import json
import shutil
import tempfile
import types
from pathlib import Path

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
