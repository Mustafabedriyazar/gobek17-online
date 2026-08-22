# -*- coding: utf-8 -*-
"""Maintenance lane: durum makinesi, yol guvenligi, LKG, restart-safe resume."""
import json
import shutil
import tempfile
import types
from pathlib import Path

from g17cloud import ai_worker as aiw
from g17cloud import maintenance as M
from g17cloud import release_guard as RG
from g17cloud.release_guard import GuardFailure


def _cfg(tmp):
    return types.SimpleNamespace(
        state_dir=Path(tmp), work_dir=Path(tmp) / "work",
        repo="owner/game-repo", repo_dir=Path(tmp) / "work" / "repo",
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


# --------------------------------------------------------------- PREFLIGHT
def check_preflight_passes_when_valid():
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        wt = work_dir / "wt-t1"
        pf = RG.preflight(lane="release", repo="owner/game-repo", other_repo="owner/agent-repo",
                          branch="main", work_dir=work_dir, worktree_path=wt, repo_exists=False)
        assert pf["ok"] is True, pf
        assert pf["lane"] == "release"
        assert set(pf["checks"]) == set(RG.PREFLIGHT_CHECKS)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_preflight_stops_on_wrong_repo_release_lane():
    """release serit ajan reposunu hedeflerse (serit karisikligi) durur."""
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        wt = work_dir / "wt-t1"
        try:
            RG.preflight(lane="release", repo="owner/agent-repo", other_repo="owner/agent-repo",
                        branch="main", work_dir=work_dir, worktree_path=wt, repo_exists=False)
            raise AssertionError("yanlis repo kabul edildi")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "repo", ex.detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_preflight_stops_on_wrong_repo_maintenance_lane():
    """maintenance serit oyun reposunu hedeflerse (serit karisikligi) durur."""
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        wt = work_dir / "self-wt-t1"
        try:
            RG.preflight(lane="maintenance", repo="owner/game-repo", other_repo="owner/game-repo",
                        branch="main", work_dir=work_dir, worktree_path=wt, repo_exists=False)
            raise AssertionError("yanlis repo kabul edildi")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "repo", ex.detail
            assert ex.detail["lane"] == "maintenance"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_preflight_stops_on_wrong_branch():
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        wt = work_dir / "wt-t1"
        try:
            RG.preflight(lane="release", repo="owner/game-repo", other_repo="owner/agent-repo",
                        branch="main", work_dir=work_dir, worktree_path=wt, repo_exists=True,
                        current_branch=lambda: "feature-x", is_clean=lambda: True)
            raise AssertionError("yanlis branch kabul edildi")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "branch", ex.detail
            assert ex.detail["current"] == "feature-x", ex.detail
            assert ex.detail["expected"] == "main", ex.detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_preflight_stops_on_dirty_tree():
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        wt = work_dir / "wt-t1"
        try:
            RG.preflight(lane="release", repo="owner/game-repo", other_repo="owner/agent-repo",
                        branch="main", work_dir=work_dir, worktree_path=wt, repo_exists=True,
                        current_branch=lambda: "main", is_clean=lambda: False)
            raise AssertionError("kirli calisma agaci kabul edildi")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "clean", ex.detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_preflight_skips_git_checks_before_first_clone():
    """repo_exists=False -> henuz yerel state yok; branch/clean git CAGRISI YAPILMAZ."""
    def boom():
        raise AssertionError("gereksiz git cagrisi yapildi")
    pf = RG.preflight(lane="release", repo="owner/game-repo", other_repo="owner/agent-repo",
                      branch="main", work_dir="/tmp/g17pf-wd", worktree_path="/tmp/g17pf-wd/wt-t1",
                      repo_exists=False, current_branch=boom, is_clean=boom)
    assert pf["ok"] is True


def check_preflight_stops_on_worktree_outside_work_dir():
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        outside = Path(tmp) / "elsewhere" / "wt-t1"
        try:
            RG.preflight(lane="release", repo="owner/game-repo", other_repo="", branch="main",
                        work_dir=work_dir, worktree_path=outside, repo_exists=False)
            raise AssertionError("calisma dizini disindaki worktree kabul edildi")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "worktree", ex.detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_preflight_stops_on_wrong_worktree_prefix():
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        wt = work_dir / "self-wt-t1"          # maintenance oneki, lane=release
        try:
            RG.preflight(lane="release", repo="owner/game-repo", other_repo="", branch="main",
                        work_dir=work_dir, worktree_path=wt, repo_exists=False)
            raise AssertionError("yanlis onekli worktree kabul edildi")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "worktree", ex.detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_preflight_maintenance_lane_uses_self_wt_prefix():
    tmp = tempfile.mkdtemp(prefix="g17pf-")
    try:
        work_dir = Path(tmp) / "work"
        wt = work_dir / "self-wt-t1"
        pf = RG.preflight(lane="maintenance", repo="owner/agent-repo", other_repo="owner/game-repo",
                          branch="main", work_dir=work_dir, worktree_path=wt, repo_exists=False)
        assert pf["ok"] is True, pf
        assert pf["lane"] == "maintenance"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_maintenance_preflight_result_visible_in_task_record():
    """PREFLIGHT sonucu gorev kaydinda (ve dolayisiyla durum sorgusunda) gorunur olmali."""
    tmp = tempfile.mkdtemp(prefix="g17pfrec-")
    try:
        store = _FakeStore({"id": "t9", "task": "x", "build": "bakim", "result": {}})
        mp = _mp_stub(tmp, store)
        gh = _FakeGitPreflight(branch="main", clean=True)
        rec = mp._preflight("t9", store.get("t9"), gh)
        assert rec["result"]["preflight"]["ok"] is True

        # durum sorgusu (GET /tasks/:id) ayni kaliciligi tekrar okur
        again = store.get("t9")
        assert again["result"]["preflight"]["lane"] == "maintenance"
        assert [e for e in again["events"] if e["phase"] == "preflight"], "preflight olayi kaydedilmedi"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_maintenance_preflight_stops_on_dirty_tree_before_edit():
    tmp = tempfile.mkdtemp(prefix="g17pfdirty-")
    try:
        store = _FakeStore({"id": "t10", "task": "x", "build": "bakim", "result": {}})
        mp = _mp_stub(tmp, store)
        (mp.cfg.self_repo_dir / ".git").mkdir(parents=True)   # yerel repo zaten klonlu
        gh = _FakeGitPreflight(branch="main", clean=False)
        try:
            mp._preflight("t10", store.get("t10"), gh)
            raise AssertionError("kirli calisma agaci ile devam etti")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "clean", ex.detail
        assert "preflight" not in (store.get("t10").get("result") or {}), \
            "basarisiz PREFLIGHT sonuc yazmamali"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_maintenance_preflight_stops_on_wrong_branch_before_edit():
    tmp = tempfile.mkdtemp(prefix="g17pfbranch-")
    try:
        store = _FakeStore({"id": "t11", "task": "x", "build": "bakim", "result": {}})
        mp = _mp_stub(tmp, store)
        (mp.cfg.self_repo_dir / ".git").mkdir(parents=True)
        gh = _FakeGitPreflight(branch="some-other-branch", clean=True)
        try:
            mp._preflight("t11", store.get("t11"), gh)
            raise AssertionError("yanlis branch ile devam etti")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "branch", ex.detail
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_release_lane_preflight_passes_and_records():
    tmp = tempfile.mkdtemp(prefix="g17pfrel-")
    try:
        store = _FakeStore({"id": "r1", "task": "x", "build": "v171", "result": {}})
        pl = _release_pipeline_stub(tmp, store, gh=_FakeGitPreflight(branch="main", clean=True))
        rec = pl._preflight("r1", store.get("r1"))
        assert rec["result"]["preflight"]["ok"] is True
        assert rec["result"]["preflight"]["lane"] == "release"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_release_lane_preflight_stops_on_wrong_branch():
    tmp = tempfile.mkdtemp(prefix="g17pfrel2-")
    try:
        store = _FakeStore({"id": "r2", "task": "x", "build": "v171", "result": {}})
        cfg = _cfg(tmp)
        (Path(cfg.work_dir) / "repo" / ".git").mkdir(parents=True)
        pl = _release_pipeline_stub(tmp, store, gh=_FakeGitPreflight(branch="wrong", clean=True),
                                    cfg=cfg)
        try:
            pl._preflight("r2", store.get("r2"))
            raise AssertionError("yanlis branch ile devam etti")
        except GuardFailure as ex:
            assert ex.stage == "PREFLIGHT", ex.stage
            assert ex.detail["check"] == "branch", ex.detail
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


def _mp_stub(tmp, store):
    mp = M.MaintenancePipeline.__new__(M.MaintenancePipeline)
    mp.cfg = _cfg(tmp)
    mp.store = store
    mp.log = lambda *a: None
    return mp


def _release_pipeline_stub(tmp, store, gh, cfg=None):
    from g17cloud.pipeline import Pipeline
    pl = Pipeline.__new__(Pipeline)
    pl.cfg = cfg or _cfg(tmp)
    pl.store = store
    pl.log = lambda *a, **k: None
    pl.gh = gh
    return pl


class _FakeGitPreflight:
    """PREFLIGHT icin branch/temizlik durumunu tasiyan sahte git katmani."""

    def __init__(self, branch="main", clean=True):
        self.branch = branch
        self.clean = clean

    def _git(self, args, cwd=None):
        if len(args) >= 2 and args[0] == "rev-parse" and args[1] == "--abbrev-ref":
            return self.branch
        return ""

    def is_clean(self):
        return self.clean
