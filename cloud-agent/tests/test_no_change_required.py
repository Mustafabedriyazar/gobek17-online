# -*- coding: utf-8 -*-
"""NO_CHANGE_REQUIRED: chore modunda bos edit listesi GECERLI sonuctur.

Kural HER IKI SERITTE de aynidir (pipeline.py = release, maintenance.py =
maintenance): AI implement/duzenleme fazinda hicbir edit onermezse VE gorev
mode='chore' ise, gorev basarisizlik DEGIL, NO_CHANGE_REQUIRED ile basariyla
kapanir; commit/push cagrilmaz. mode='feature'/'fix' icin bos edit listesi
gorevi HALA dusurur (eski davranis degismedi).

Bu dosya gercek git/node calistirmaz — Pipeline/MaintenancePipeline
__new__ ile insa edilir ve gh/ai/guard sahte (fake) nesnelerle degistirilir
(bkz. test_maintenance.py._pipeline / _release_pipeline_stub). commit/push
sahteleri cagrilirlarsa AssertionError firlatir — boylece "commit/push
cagrilmadi" iddiasi gercekten dogrulanir, sadece varsayilmaz.
"""
import shutil
import tempfile
import types
from pathlib import Path

from g17cloud.maintenance import MaintenancePipeline
from g17cloud.pipeline import Pipeline
from g17cloud.store import TaskStore


def _release_cfg(tmp):
    return types.SimpleNamespace(
        state_dir=Path(tmp) / "state", work_dir=Path(tmp) / "work",
        repo="owner/game-repo", repo_dir=Path(tmp) / "work" / "repo",
        self_repo="owner/agent-repo", self_repo_dir=Path(tmp) / "work" / "self-repo",
        branch="main", test_timeout=60, auto_deploy=True)


def _maint_cfg(tmp):
    return types.SimpleNamespace(
        state_dir=Path(tmp) / "state", work_dir=Path(tmp) / "work",
        repo="owner/game-repo", repo_dir=Path(tmp) / "work" / "repo",
        self_repo="owner/agent-repo", self_repo_dir=Path(tmp) / "work" / "self-repo",
        branch="main", test_timeout=60,
        ai_auth_mode=lambda: "ANTHROPIC_API_READY")


class _FakeAI:
    """inspect fazinda reproduced:true, implement fazinda VERILEN edits'i dondurur."""

    def __init__(self, edits):
        self.edits = edits

    def select(self, task, provider):
        return "mock"

    def call(self, provider, system, prompt, cwd=None):
        if "faz: inspect" in prompt:
            return ('{"reproduced": true, "rootCause": "rc", "files": [], '
                     '"minimalFix": "mf", "tests": [], "title": "t"}')
        if "faz: implement" in prompt:
            import json
            return json.dumps({"edits": self.edits, "summary": "s"})
        return "{}"


class _FakeMaintAI:
    def __init__(self, edits):
        self.edits = edits

    def select(self, task, provider):
        return "mock"

    def call(self, provider, system, prompt, cwd=None):
        import json
        return json.dumps({"rootCause": "rc", "edits": self.edits})


class _NoCommitGH:
    """Release seridi sahte git katmani. commit/push cagrilirsa gorev DUSER."""

    def clone_or_update(self):
        return True

    def short_head(self):
        return "abc1234"

    def auth_status(self):
        return {"write": "OK"}

    def is_clean(self):
        return True

    def _git(self, args, cwd=None):
        return ""

    def make_worktree(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def remove_worktree(self, path):
        pass

    def commit(self, msg):
        raise AssertionError("commit cagrilmamaliydi (NO_CHANGE_REQUIRED)")

    def push(self):
        raise AssertionError("push cagrilmamaliydi (NO_CHANGE_REQUIRED)")


class _NoCommitMaintGH:
    """Maintenance seridi sahte git katmani. commit/push cagrilirsa gorev DUSER."""

    def clone_or_update(self):
        return True

    def head(self):
        return "d" * 40

    def is_clean(self):
        return True

    def _git(self, args, cwd=None):
        return ""

    def make_worktree(self, path):
        path = Path(path)
        (path / "cloud-agent").mkdir(parents=True, exist_ok=True)
        return path

    def remove_worktree(self, path):
        pass

    def commit(self, msg):
        raise AssertionError("commit cagrilmamaliydi (NO_CHANGE_REQUIRED)")

    def push(self):
        raise AssertionError("push cagrilmamaliydi (NO_CHANGE_REQUIRED)")


class _FakeGuard:
    """release: repo_context/before_hashes icin yeterli; commit sonrasi guard'lar
    bu senaryoda hic cagrilmamali — yine de savunma icin firlatan stublar birakildi."""

    def block_hashes(self, wt):
        return {}

    def discover_tests(self, rd, build):
        return []

    def run_tests(self, wt, build):
        raise AssertionError("test kosucusu cagrilmamaliydi (NO_CHANGE_REQUIRED)")


class _FakeMaintGuard:
    def run_self_tests(self, wt):
        raise AssertionError("self-test cagrilmamaliydi (NO_CHANGE_REQUIRED)")

    def check_secrets(self, diff, wt):
        raise AssertionError("secret guard cagrilmamaliydi (NO_CHANGE_REQUIRED)")


def _release_pipeline(tmp, edits, mode):
    cfg = _release_cfg(tmp)
    store = TaskStore(cfg.state_dir)
    pl = Pipeline.__new__(Pipeline)
    pl.cfg = cfg
    pl.store = store
    pl.lock = None
    pl.log = lambda *a, **k: None
    pl.gh = _NoCommitGH()
    pl.guard = _FakeGuard()
    pl.ai = _FakeAI(edits)
    pl.prod = None
    rec = store.create("v171", "bakim kontrolu", mode=mode)
    return pl.run(rec["id"])


def _maint_pipeline(tmp, edits, mode):
    cfg = _maint_cfg(tmp)
    store = TaskStore(cfg.state_dir)
    mp = MaintenancePipeline.__new__(MaintenancePipeline)
    mp.cfg = cfg
    mp.store = store
    mp.lock = None
    mp.log = lambda *a, **k: None
    mp.gh = lambda: _NoCommitMaintGH()
    mp.guard = _FakeMaintGuard()
    mp.ai = _FakeMaintAI(edits)
    rec = store.create("bakim", "bakim kontrolu", mode=mode)
    return mp.run(rec["id"])


# ------------------------------------------------------------ maintenance seridi
def check_chore_mode_empty_edits_closes_success_maintenance_lane():
    tmp = tempfile.mkdtemp(prefix="g17ncr-maint-")
    try:
        rec = _maint_pipeline(tmp, [], "chore")
        assert rec["status"] == "success", rec
        assert rec["result"]["outcome"] == "NO_CHANGE_REQUIRED", rec["result"]
        assert rec["result"]["push"] == "SKIPPED", rec["result"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_feature_mode_empty_edits_drops_task_maintenance_lane():
    tmp = tempfile.mkdtemp(prefix="g17ncr-maintfail-")
    try:
        rec = _maint_pipeline(tmp, [], "feature")
        assert rec["status"] == "failed", rec
        assert rec["result"]["failStage"] == "EDIT", rec["result"]
        assert rec["result"].get("outcome") != "NO_CHANGE_REQUIRED", rec["result"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ release seridi
def check_chore_mode_empty_edits_closes_success_release_lane():
    tmp = tempfile.mkdtemp(prefix="g17ncr-rel-")
    try:
        rec = _release_pipeline(tmp, [], "chore")
        assert rec["status"] == "success", rec
        assert rec["result"]["outcome"] == "NO_CHANGE_REQUIRED", rec["result"]
        assert rec["result"]["push"] == "SKIPPED", rec["result"]
        assert rec["result"]["production"] == "UNCHANGED", rec["result"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_fix_mode_empty_edits_drops_task_release_lane():
    tmp = tempfile.mkdtemp(prefix="g17ncr-relfail-")
    try:
        rec = _release_pipeline(tmp, [], "fix")
        assert rec["status"] == "failed", rec
        assert rec["result"]["stage"] == "IMPLEMENT", rec["result"]
        assert rec["result"].get("outcome") != "NO_CHANGE_REQUIRED", rec["result"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_feature_mode_empty_edits_drops_task_release_lane():
    tmp = tempfile.mkdtemp(prefix="g17ncr-relfail2-")
    try:
        rec = _release_pipeline(tmp, [], "feature")
        assert rec["status"] == "failed", rec
        assert rec["result"]["stage"] == "IMPLEMENT", rec["result"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
