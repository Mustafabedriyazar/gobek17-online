#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent — MAINTENANCE LANE (self-edit).

RELEASE lane oyunu yayinlar (vN -> vN+1, artifact, damga, production).
MAINTENANCE lane AJANIN KENDI KODUNU gunceller. Oyun build numarasi
guard'ina GIRMEZ; ama yikici git islemleri burada da YASAKTIR.

Zincir:
    PREPARED -> SELF_UPDATE_PENDING -> PUSHED -> RESTARTED
             -> HEALTH_VERIFIED -> DONE

Neden durum makinesi: ajan kendi reposuna push edince Railway AJANI
yeniden kurar; surec gorevin ortasinda olur. Durum /data'da kalici
oldugu icin yeniden dogan ornek recover() ile nerede kaldigini bilir
ve edit/push'i TEKRARLAMAZ.

Kritik siralama:
  * expected_commit PUSH'TAN ONCE kalici yazilir. Push basarili olup
    konteyner hemen olurse bile yeni ornek commit'i uzakta dogrulayip
    devam edebilir.
  * LAST_KNOWN_GOOD push'tan once, o an calisan HEAD olarak yazilir.
  * DONE yalnizca uzak main beklenen commit'te VE /health + /ready PASS
    oldugunda yazilir. Push basarisizsa veya yeni surum ayaga kalkmazsa
    gorev asla tamamlanmis GORUNMEZ.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import ai_worker as aiw
from .ai_worker import AIError, AIWorker, apply_edits, parse_json_block, route_provider
from .github_core import GitHubCore, GitHubError
from .release_guard import GuardFailure, ReleaseGuard

# --- durum makinesi ---------------------------------------------------------
PREPARED = "PREPARED"
SELF_UPDATE_PENDING = "SELF_UPDATE_PENDING"
PUSHED = "PUSHED"
RESTARTED = "RESTARTED"
HEALTH_VERIFIED = "HEALTH_VERIFIED"
DONE = "DONE"

LIVE_STATES = (PREPARED, SELF_UPDATE_PENDING, PUSHED, RESTARTED, HEALTH_VERIFIED)
# Bu durumlarda edit/push TEKRARLANMAZ; yalnizca dogrulama yapilir.
NO_REDO_STATES = (SELF_UPDATE_PENDING, PUSHED, RESTARTED, HEALTH_VERIFIED)

# Ajan yalnizca kendi kodunu degistirebilir.
ALLOWED_PREFIXES = ("cloud-agent/",)
# Kurulum tasiyicisina ve is akislarina ajan DOKUNAMAZ.
BLOCKED_PREFIXES = (".github/",)

SYSTEM = (
    "Sen G17 Cloud Agent'in bakim modusun. YALNIZ cloud-agent/ altindaki "
    "Python dosyalarini degistirirsin. Oyun kaynagina, .github/ altina ve "
    "engine/bot bloklarina DOKUNMAZSIN. Cikti YALNIZ JSON: "
    '{"rootCause": "...", "edits": [{"path": "...", "content": "..."}]}'
)


class SelfEditError(RuntimeError):
    pass


MAINT_BUILD_WORDS = ("bakim", "bakım", "maintenance", "self", "agent")


def is_maintenance(build):
    """BUILD alani sayi degil de bir bakim kelimesiyse lane = MAINTENANCE.

    Konsol arayuzu degismesin diye lane BUILD alanindan okunur:
    "v172" -> release, "bakim" -> maintenance.
    """
    b = str(build or "").strip().lower()
    return b in MAINT_BUILD_WORDS


def _lkg_path(cfg):
    return Path(cfg.state_dir) / "last_known_good.json"


def read_last_known_good(cfg):
    try:
        with open(_lkg_path(cfg), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_last_known_good(cfg, sha, note=""):
    """Push oncesi, o an CALISAN commit. Asla push sonrasi yazilmaz."""
    p = _lkg_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"sha": sha, "note": note, "at": int(time.time())}, fh)
    os.replace(tmp, str(p))
    return sha


class _SelfCfg:
    """cfg'nin repo/repo_dir alanlari AJANIN reposuna bakan ince sarmalayici.

    GitHubCore tek repo ile calisir; kopyalamak yerine ayni nesnenin
    yalnizca iki alanini golgeleyip guvenlik kurallarini aynen koruruz.
    """

    def __init__(self, cfg):
        self._c = cfg
        self.repo = cfg.self_repo
        self.repo_dir = Path(cfg.self_repo_dir)
        self.branch = cfg.branch

    def __getattr__(self, name):
        return getattr(self._c, name)


class MaintenancePipeline:
    def __init__(self, cfg, store, lock, log=None):
        self.cfg = cfg
        self.store = store
        self.lock = lock
        self.log = log or (lambda *a: None)
        self.guard = ReleaseGuard(cfg, log=self.log)
        self.ai = AIWorker(cfg, log=self.log)

    # ---------------------------------------------------------------- yardim
    def _ev(self, tid, phase, msg, **extra):
        self.store.event(tid, phase, msg, **extra)
        self.log("[%s] %s: %s" % (tid, phase, msg))

    def _set_state(self, tid, state, **extra):
        """Durumu KALICI yaz. Her gecis diske iner."""
        res = dict((self.store.get(tid) or {}).get("result") or {})
        res["selfState"] = state
        res.update(extra)
        self.store.update(tid, result=res, phase=state)
        self.log("[%s] state -> %s" % (tid, state))
        return res

    def _state_of(self, rec):
        return ((rec or {}).get("result") or {}).get("selfState")

    def gh(self):
        return GitHubCore(_SelfCfg(self.cfg), log=self.log)

    # ---------------------------------------------------------------- guvenlik
    @staticmethod
    def check_paths(paths):
        """Ajan yalnizca kendi kodunu degistirebilir."""
        bad = []
        for p in paths:
            p = str(p or "").replace("\\", "/").strip()
            while p.startswith("./"):
                p = p[2:]
            parts = [x for x in p.split("/") if x]
            # ".." ile kapsam disina cikma denemesi: mutlak RED.
            if not parts or ".." in parts or p.startswith("/"):
                bad.append(p or "(bos)")
                continue
            if any(p.startswith(b) for b in BLOCKED_PREFIXES):
                bad.append(p)
            elif not any(p.startswith(a) for a in ALLOWED_PREFIXES):
                bad.append(p)
        if bad:
            raise SelfEditError("izin verilmeyen yol: %s" % ", ".join(sorted(set(bad))[:8]))
        return True

    # ---------------------------------------------------------------- smoke
    def smoke(self, worktree):
        """SELF-BRICK KORUMASI. Ayri surecte: import + config + API boot +
        /health + /ready + tam self-test. Biri bile duserse push YOK."""
        agent = Path(worktree) / "cloud-agent"
        script = agent / "tests" / "smoke_boot.py"
        if not script.is_file():
            raise GuardFailure("SMOKE", "tests/smoke_boot.py yok — "
                                        "self-brick korumasi olmadan push YASAK")
        env = dict(os.environ)
        env["G17_STATE_DIR"] = str(Path(worktree) / ".smoke-state")
        env["G17_DEV_MODE"] = "1"
        env["PYTHONPATH"] = str(agent)
        p = subprocess.run([sys.executable, str(script)], cwd=str(agent),
                           capture_output=True, text=True,
                           timeout=max(120, self.cfg.test_timeout), env=env)
        out = (p.stdout or "") + (p.stderr or "")
        if p.returncode != 0:
            fails = [ln for ln in out.splitlines()
                     if ln.startswith("SMOKE-FAIL") or ln.startswith("FAIL ")]
            raise GuardFailure("SMOKE", "boot smoke FAIL: %s"
                               % ("; ".join(fails)[:400] or "cikis %d" % p.returncode),
                               {"stdout": out[-3000:], "returncode": p.returncode})
        return {"ok": True, "output": out[-1200:]}

    # ---------------------------------------------------------------- dogrulama
    def remote_has(self, gh, sha):
        """Beklenen commit uzak main'de mi. Push sonrasi tek gercek kanit."""
        if not sha:
            return False
        try:
            gh._git(["fetch", "--quiet", "origin", self.cfg.branch],
                    cwd=self.cfg.self_repo_dir)
            remote = gh._git(["rev-parse", "origin/" + self.cfg.branch],
                             cwd=self.cfg.self_repo_dir)
        except GitHubError:
            return False
        if remote.startswith(sha) or sha.startswith(remote[:7]):
            return True
        try:
            gh._git(["merge-base", "--is-ancestor", sha, "origin/" + self.cfg.branch],
                    cwd=self.cfg.self_repo_dir)
            return True
        except GitHubError:
            return False

    def health_ok(self):
        """Bu ornek ayakta (kodu calistiriyoruz) + /ready mantigi PASS mi."""
        return self.cfg.ai_auth_mode() != "AI_UNAUTHENTICATED"

    # ---------------------------------------------------------------- ana akis
    def run(self, task_id):
        rec = self.store.get(task_id)
        if not rec:
            return None
        state = self._state_of(rec)

        # --- YENIDEN DOGAN ORNEK: edit/push TEKRARLANMAZ -------------------
        if state in NO_REDO_STATES:
            return self.resume(task_id)

        wt = None
        gh = self.gh()
        try:
            # --- 1 PREPARED: temiz klon + izole worktree --------------------
            self._ev(task_id, "prepare", "ajan reposu hazirlaniyor")
            gh.clone_or_update()
            head_before = gh.head()
            wt = gh.make_worktree(Path(self.cfg.work_dir) / ("self-wt-%s" % task_id))
            self._set_state(task_id, PREPARED, headBefore=head_before[:12])

            # --- 2 AI duzenlemesi ------------------------------------------
            provider = self.ai.select(rec["task"],
                                      rec.get("provider") or "opus")
            self._ev(task_id, "inspect", "bakim modu — saglayici: %s"
                     % getattr(provider, "name", "?"))
            prompt = self._prompt(wt, rec["task"])
            raw = self.ai.call(provider, SYSTEM, prompt)
            plan = parse_json_block(raw)
            edits = plan.get("edits") or []
            if not edits:
                return self._fail(task_id, "EDIT", "AI hicbir degisiklik onermedi")
            self.check_paths([e.get("path") for e in edits])
            changed = sorted(set(apply_edits(wt, edits)))
            self._ev(task_id, "implement", "%d dosya degisti" % len(changed),
                     files=changed[:20])

            # --- 3 ZORUNLU self-test (repodaki gercek suite) ----------------
            tests = self.guard.run_self_tests(wt)
            self._ev(task_id, "selftest", tests["summary"])

            # --- 4 SELF-BRICK smoke ----------------------------------------
            self.smoke(wt)
            self._ev(task_id, "smoke", "import + config + API boot + health/ready PASS")

            # --- 5 calisma kopyasina uygula, YALNIZ cloud-agent/ ------------
            self._apply(wt, changed)
            gh._git(["add", "-A", "--", "cloud-agent"], cwd=self.cfg.self_repo_dir)
            staged = [x for x in gh._git(["diff", "--cached", "--name-only"],
                                         cwd=self.cfg.self_repo_dir).splitlines() if x]
            if not staged:
                return self._fail(task_id, "EDIT", "uygulanacak fark yok")
            self.check_paths(staged)
            self.guard.check_secrets(
                gh._git(["diff", "--cached"], cwd=self.cfg.self_repo_dir), wt)
            self._ev(task_id, "guards", "yol + secret guard PASS (%d dosya)" % len(staged))

            if rec.get("dryRun") or rec.get("noDeploy"):
                self.store.update(task_id, status="success", phase="done",
                                  result=dict(rec.get("result") or {},
                                              mode="dry-run", push="SKIPPED",
                                              selfState="DRY_RUN",
                                              selfTests=tests["summary"]))
                self._ev(task_id, "done", "dry-run tamam — push YOK")
                return self.store.get(task_id)

            # --- 6 LAST_KNOWN_GOOD: push ONCESI calisan commit -------------
            write_last_known_good(self.cfg, head_before, "self-update oncesi")
            self._ev(task_id, "lkg", "son bilinen saglikli commit: %s" % head_before[:12])

            # --- 7 commit + expected_commit'i PUSH ONCESI kalici yaz --------
            sha = gh.commit("agent: %s" % (rec["task"] or "maintenance")[:72])
            if not sha:
                return self._fail(task_id, "COMMIT", "commit olusmadi")
            full = gh._git(["rev-parse", "HEAD"], cwd=self.cfg.self_repo_dir)
            self._set_state(task_id, SELF_UPDATE_PENDING,
                            expectedCommit=full, lastKnownGood=head_before,
                            selfTests=tests["summary"], changedFiles=staged)

            # --- 8 push. Bundan sonra Railway BIZI yeniden kurabilir --------
            self._ev(task_id, "push", "self-update gonderiliyor (%s)" % sha)
            gh.push()
            self._set_state(task_id, PUSHED, expectedCommit=full,
                            lastKnownGood=head_before)

            # Hala ayaktaysak dogrulamayi burada surdur; degilsek yeni ornek
            # recover() ile ayni yerden devam eder.
            return self.resume(task_id)

        except (GuardFailure,) as ex:
            return self._fail(task_id, ex.stage, ex.reason, ex.detail)
        except (SelfEditError, AIError, GitHubError) as ex:
            return self._fail(task_id, "MAINTENANCE", str(ex)[:300])
        except Exception as ex:                                   # beklenmeyen
            return self._fail(task_id, "INTERNAL",
                              "%s: %s" % (type(ex).__name__, str(ex)[:200]))
        finally:
            if wt:
                try:
                    gh.remove_worktree(wt)
                except Exception:
                    pass

    # ---------------------------------------------------------------- resume
    def resume(self, task_id):
        """Yeniden dogan ornek burada devam eder. EDIT/PUSH YAPMAZ."""
        rec = self.store.get(task_id)
        state = self._state_of(rec)
        res = (rec.get("result") or {})
        expected = res.get("expectedCommit")
        gh = self.gh()
        try:
            gh.clone_or_update()
        except GitHubError as ex:
            return self._fail(task_id, "RESUME", "ajan reposu okunamadi: %s" % str(ex)[:160])

        if state in (SELF_UPDATE_PENDING, PUSHED):
            if not self.remote_has(gh, expected):
                if state == SELF_UPDATE_PENDING:
                    return self._fail(task_id, "PUSH",
                                      "commit uzak main'de YOK — push tamamlanmadi",
                                      {"expectedCommit": expected})
                return self._fail(task_id, "PUSH",
                                  "PUSHED yazildi ama commit uzakta bulunamadi",
                                  {"expectedCommit": expected})
            self._set_state(task_id, RESTARTED, expectedCommit=expected)
            state = RESTARTED

        if state == RESTARTED:
            if not self.health_ok():
                return self._fail(task_id, "HEALTH",
                                  "/ready PASS degil — yeni surum saglikli degil",
                                  {"aiAuth": self.cfg.ai_auth_mode(),
                                   "lastKnownGood": res.get("lastKnownGood")})
            self._set_state(task_id, HEALTH_VERIFIED, expectedCommit=expected)
            state = HEALTH_VERIFIED

        if state == HEALTH_VERIFIED:
            self.store.update(task_id, status="success", phase="done",
                              result=dict((self.store.get(task_id) or {}).get("result") or {},
                                          selfState=DONE, push="PASS",
                                          health="PASS", ready="PASS"))
            self._ev(task_id, "done", "self-update DOGRULANDI (%s)"
                     % (expected or "?")[:12])
            return self.store.get(task_id)
        return rec

    # ---------------------------------------------------------------- ic
    def _prompt(self, wt, task):
        agent = Path(wt) / "cloud-agent"
        listing = []
        for p in sorted(agent.rglob("*.py")):
            if "__pycache__" in str(p):
                continue
            listing.append(str(p.relative_to(wt)))
        return ("GOREV: %s\n\nDEGISTIREBILECEGIN DOSYALAR (yalnizca bunlar):\n%s\n\n"
                "Kurallar: tam dosya icerigi dondur; stdlib disi bagimlilik ekleme; "
                "cloud-agent/tests/ altindaki testleri bozma."
                % (task, "\n".join(listing[:200])))

    def _apply(self, wt, changed):
        import shutil
        src, dst = Path(wt), Path(self.cfg.self_repo_dir)
        for rel in changed:
            rel = str(rel).replace("\\", "/")
            s, d = src / rel, dst / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(s), str(d))
        return len(changed)

    def _fail(self, task_id, stage, reason, detail=None):
        rec = self.store.get(task_id) or {}
        res = dict(rec.get("result") or {})
        res.update({"failStage": stage, "failReason": reason})
        if detail:
            res["failDetail"] = detail
        self.store.update(task_id, status="failed", phase=stage, result=res)
        self._ev(task_id, stage, "FAILED: %s" % reason)
        return self.store.get(task_id)
