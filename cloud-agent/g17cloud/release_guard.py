#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — Deterministik Release Guard.

AI'nin isi bittikten SONRA calisan, AI'dan BAGIMSIZ karar cekirdegi.
Sirasi: diff -> secret -> engine/bot SHA -> testler -> ardisik surum -> artifact.
Herhangi biri FAIL ise production'a HICBIR SEY gitmez.

v1.2.1'de gercek testlerle kanitlanmis guard modulleri (block_hash, secret_scan,
version_guard, apply_artifact) OLDUGU GIBI yeniden kullanilir — Termux'a bagli
olmadiklari icin cloud'da da gecerlidir.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

JUNK_RX = re.compile(r"(^|/)(node_modules/|\.cache/|\.gobek17-app/|.*\.log$|"
                     r"\.g17-state/|__pycache__/|\.DS_Store$)", re.I)


class GuardFailure(RuntimeError):
    def __init__(self, stage, reason, detail=None):
        super().__init__("%s: %s" % (stage, reason))
        self.stage = stage
        self.reason = reason
        self.detail = detail or {}


# ---------------------------------------------------------------- 0 preflight
# Serit basina beklenen worktree dizin oneki. release -> oyun reposu worktree'si,
# maintenance -> ajanin kendi reposu worktree'si (bkz. pipeline.py / maintenance.py).
LANE_PREFIXES = {"release": "wt-", "maintenance": "self-wt-"}
PREFLIGHT_CHECKS = ("repo", "worktree", "branch", "clean")


def preflight(lane, repo, other_repo, branch, work_dir, worktree_path,
             repo_exists=False, current_branch=None, is_clean=None):
    """GOREVIN ILK ADIMI. AI/git/guard zincirinden ONCE calisir.

    Dogrular: (1) serit kuralina gore hedef repo dogru mu — release seridi
    oyun reposunu, maintenance seridi ajan reposunu hedeflemeli ve ikisi
    ayni OLMAMALI; (2) worktree yolu beklenen calisma dizini altinda ve
    seridin onekiyle mi adlandirilmis; (3) hedef branch tanimli mi (ve
    yerel repo zaten varsa o branch'te mi); (4) yerel calisma agaci temiz
    mi (commit edilmemis degisiklik yoksa). Herhangi biri basarisiz olursa
    GuardFailure(stage='PREFLIGHT', ...) firlatir; cagiran taraf sonraki
    adimlara GECMEZ — hata rec['result']['detail'] icinde hangi kontrolun
    neden basarisiz oldugunu tasir.

    repo_exists=False ise (ilk klonlama, yerel state yok) branch/clean
    kontrolleri ATLANIR; current_branch/is_clean YALNIZ repo_exists=True
    ise cagrilir (lazy — gereksiz git cagrisi yapilmaz).
    """
    repo = (repo or "").strip()
    if not repo:
        raise GuardFailure("PREFLIGHT", "%s serit icin hedef repo tanimli degil" % lane,
                           {"check": "repo", "lane": lane})
    other_repo = (other_repo or "").strip()
    if other_repo and repo == other_repo:
        raise GuardFailure(
            "PREFLIGHT",
            "%s serit yanlis repoyu hedefliyor (serit reposu digeriyle ayni)" % lane,
            {"check": "repo", "lane": lane, "repo": repo})

    wd = Path(work_dir).resolve()
    wt = Path(worktree_path)
    try:
        wt.resolve().relative_to(wd)
    except ValueError:
        raise GuardFailure("PREFLIGHT", "worktree yolu beklenen calisma dizini disinda",
                           {"check": "worktree", "lane": lane, "path": str(worktree_path)})
    prefix = LANE_PREFIXES.get(lane)
    if prefix and not wt.name.startswith(prefix):
        raise GuardFailure(
            "PREFLIGHT",
            "worktree adi %s seridi icin beklenen onekle baslamiyor (%s)" % (lane, prefix),
            {"check": "worktree", "lane": lane, "path": str(worktree_path)})

    branch = (branch or "").strip()
    if not branch:
        raise GuardFailure("PREFLIGHT", "hedef branch tanimli degil",
                           {"check": "branch", "lane": lane})

    if repo_exists:
        cur = ((current_branch() if current_branch else "") or "").strip()
        if cur and cur != branch:
            raise GuardFailure(
                "PREFLIGHT",
                "yerel repo beklenmeyen branch'te: %s (beklenen %s)" % (cur, branch),
                {"check": "branch", "lane": lane, "current": cur, "expected": branch})
        if not (is_clean() if is_clean else True):
            raise GuardFailure(
                "PREFLIGHT",
                "calisma agaci temiz degil — commit edilmemis degisiklik var",
                {"check": "clean", "lane": lane})

    return {"ok": True, "lane": lane, "repo": repo, "branch": branch,
           "worktree": str(worktree_path), "checks": list(PREFLIGHT_CHECKS)}


def _py(guards_dir, script, args, stdin=None, timeout=300):
    proc = subprocess.run([sys.executable, str(Path(guards_dir) / script)] + args,
                          input=stdin, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


class ReleaseGuard:
    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.g = cfg.guards_dir
        self.log = log or (lambda *a, **k: None)

    # ---------------------------------------------------------------- 1 diff
    def check_diff(self, files, repo_dir):
        if not files:
            raise GuardFailure("DIFF", "uygulanacak degisiklik yok")
        junk = [f for f in files if JUNK_RX.search(f)]
        if junk:
            raise GuardFailure("DIFF", "istenmeyen dosyalar", {"junk": junk[:20]})
        big = []
        limit = self.cfg.max_new_file_mb * 1024 * 1024
        for f in files:
            p = Path(repo_dir) / f
            if p.is_file() and p.stat().st_size > limit:
                big.append({"file": f, "mb": round(p.stat().st_size / 1048576, 2)})
        if big:
            raise GuardFailure("DIFF", "asiri buyuk dosya", {"tooBig": big})
        return {"files": len(files)}

    # ---------------------------------------------------------------- 2 secret
    def check_secrets(self, diff_text, source_dir):
        """secret_scan.py: exit!=0 -> sizinti. Cikti ZATEN MASKELIDIR;
        ham secret degeri hicbir zaman tasinmaz/loglanmaz."""
        rc, out, err = _py(self.g, "secret_scan.py",
                           ["--stdin", "--tree", str(source_dir)], stdin=diff_text)
        if rc != 0:
            masked = [ln.strip() for ln in (out or "").splitlines() if ln.strip().startswith("-")]
            raise GuardFailure("SECRET", "secret tespit edildi",
                               {"findings": masked[:10]})
        return {"ok": True}

    # ---------------------------------------------------------------- 3 engine/bot
    def block_hashes(self, source):
        """block_hash.py IC ICE JSON dondurur:
             {"blocks":{"engine":{"sha256":..}}, "files":{"engine_factory":{"sha256":..}}}
        Bunu DUZ haritaya cevirmezsek check_canonical her zaman None ile karsilastirir
        ve engine guard SESSIZCE HIC TETIKLENMEZ. (Testler bu regresyonu yakaladi.)"""
        rc, out, _ = _py(self.g, "block_hash.py", [str(source)])
        try:
            raw = json.loads(out or "{}")
        except ValueError:
            return {}
        flat = {}
        for group in ("blocks", "files"):
            for key, val in (raw.get(group) or {}).items():
                flat[key] = (val or {}).get("sha256") if isinstance(val, dict) else None
        flat["_errors"] = raw.get("errors") or []
        return flat

    def check_canonical(self, before, after, allow_change=False):
        changed = []
        for key in ("engine", "bot", "engine_factory", "bot_factory"):
            b, a = before.get(key), after.get(key)
            if b and a and b != a:
                changed.append(key)
            elif b and not a:
                # Isaretci/dosya kayboldu: hash karsilastirilamiyor. Bu da bir
                # kanonik blok mudahalesidir, "bilinmiyor" diye GECILMEZ.
                changed.append(key + ":KAYIP")
        if changed and not allow_change and self.cfg.engine_guard == "strict":
            raise GuardFailure("ENGINE_GUARD", "kanonik engine/bot blogu degisti",
                               {"changed": changed})
        return {"changed": changed, "status": "DEGISTI" if changed else "PASS"}

    # ---------------------------------------------------------------- 4 testler
    # --- KENDI TEST SUITE'I -------------------------------------------------
    def self_suite(self, source):
        """Ajanin kendi python test suite'i (varsa) yolunu doner."""
        from pathlib import Path as _P
        for rel in ("cloud-agent/tests/run_tests.py", "tests/run_tests.py"):
            p = _P(source) / rel
            if p.is_file():
                return p
        return None

    def run_self_tests(self, source):
        """Ajanin KENDI kodu icin test kosar. FAIL'de tam kontrol adi + stderr."""
        import subprocess as _sp, sys as _sys, re as _re
        suite = self.self_suite(source)
        if suite is None:
            raise GuardFailure("TEST", "cloud-agent/tests/run_tests.py yok — "
                                       "kendi kodu test edilmeden push YASAK")
        p = _sp.run([_sys.executable, str(suite)], cwd=str(suite.parent.parent),
                    capture_output=True, text=True, timeout=self.cfg.test_timeout)
        out = (p.stdout or "") + (p.stderr or "")
        m = _re.search(r"RESULT:\s*(\d+)\s*PASS\s*/\s*(\d+)\s*FAIL", out)
        npass, nfail = (int(m.group(1)), int(m.group(2))) if m else (0, -1)
        fails = [ln for ln in out.splitlines() if ln.startswith("FAIL ")]
        summary = ("%d PASS / %d FAIL" % (npass, nfail)) if m else "SONUC OKUNAMADI"
        ok = (p.returncode == 0 and m and nfail == 0)
        if not ok:
            raise GuardFailure("SELFTEST", "kendi testleri FAIL: %s | %s"
                               % (summary, "; ".join(fails)[:400]),
                               {"stdout": out[-3000:], "returncode": p.returncode})
        return {"summary": summary, "ok": True, "results": fails}

    def discover_tests(self, source, build):
        sdir = Path(source) / "app" / "server" if (Path(source) / "app" / "server").is_dir() else Path(source) / "server"
        if not sdir.is_dir():
            return []
        found = []
        pkg = sdir / "package.json"
        if pkg.is_file():
            try:
                script = (json.loads(pkg.read_text(encoding="utf-8"))
                          .get("scripts", {}).get("test", ""))
            except ValueError:
                script = ""
            for part in script.split("&&"):
                m = re.search(r"node\s+([A-Za-z0-9._/-]+\.c?js)", part.strip())
                if m and (sdir / m.group(1)).is_file():
                    found.append(m.group(1))
        for extra in sorted(sdir.glob("test-v%s-*.cjs" % build)) + \
                     sorted(sdir.glob("core-regression.cjs")):
            if extra.name not in found:
                found.append(extra.name)
        excl = re.compile(r"(redis|stress-)")
        return [f for f in found if not excl.search(f)]

    def run_tests(self, source, build, node="node"):
        sdir = Path(source) / "app" / "server" if (Path(source) / "app" / "server").is_dir() else Path(source) / "server"
        tests = self.discover_tests(source, build)
        if not tests:
            raise GuardFailure("TEST", "calistirilabilir test bulunamadi")
        results, failed = [], []
        for t in tests:
            try:
                p = subprocess.run([node, t], cwd=str(sdir), capture_output=True,
                                   text=True, timeout=self.cfg.test_timeout)
                ok = p.returncode == 0
                tail = (p.stdout + p.stderr)[-1500:]
            except subprocess.TimeoutExpired:
                ok, tail = False, "TIMEOUT"
            results.append({"test": t, "ok": ok})
            if not ok:
                failed.append({"test": t, "output": tail})
        summary = "%d PASS / %d FAIL" % (len(results) - len(failed), len(failed))
        return {"summary": summary, "results": results, "failed": failed,
                "ok": not failed}

    # ---------------------------------------------------------------- 5 surum
    def repo_build(self, repo_dir):
        rc, out, _ = _py(self.g, "version_guard.py", ["detect", str(repo_dir)])
        try:
            d = json.loads(out or "{}")
        except ValueError:
            return None
        pv = (d.get("packageVersions") or {}).get("package.json")
        if pv:
            try:
                return int(str(pv).split(".")[1])
            except (IndexError, ValueError):
                pass
        stamps = d.get("stamps") or {}
        nums = [int(k) for k in stamps if str(k).isdigit()]
        return max(nums) if nums else None

    def check_sequential(self, current, target, allow_skip=False):
        if current is None:
            return {"current": None, "target": target, "note": "repo surumu okunamadi"}
        if current is not None and target >= 100 and current < 100: current += 100
        if target <= current:
            raise GuardFailure("VERSION", "geri/ayni surum — rollback YASAK",
                               {"current": current, "target": target})
        if target != current + 1 and self.cfg.strict_sequential and not allow_skip:
            raise GuardFailure("VERSION", "sira disi build",
                               {"current": current, "next": current + 1, "target": target})
        return {"current": current, "target": target}

    def verify_artifact(self, source, build):
        rc, out, err = _py(self.g, "version_guard.py", ["verify", str(source), str(build)])
        if rc != 0:
            raise GuardFailure("ARTIFACT", "paket v%s: %s" % (build, (err or out or "?").strip()[:200]),
                               {"detail": (out or err)[:300]})
        return True

    def build_artifact(self, source, out_zip):
        rc, out, err = _py(self.g, "apply_artifact.py",
                           ["appzip", "--src", str(source), "--out", str(out_zip)])
        if rc != 0:
            raise GuardFailure("ARTIFACT", "release zip uretilemedi",
                               {"detail": (out or err)[:300]})
        return {"path": str(out_zip), "sha256": sha256_file(out_zip)}

    def apply_to_repo(self, source, repo_dir, build, backup_dir=None, manifest=None):
        # BUG-1 mirasi: semver TEK guvenilir helper'dan gelir (v171 -> 1.71.0).
        rc0, semver, _ = _py(self.g, "version_guard.py", ["semver", "--build", str(build)])
        semver = (semver or "").strip()
        if rc0 != 0 or not re.match(r"^\d+\.\d+\.\d+$", semver):
            raise GuardFailure("APPLY", "surum eslemesi hesaplanamadi")
        backup_dir = backup_dir or (Path(repo_dir).parent / "backup")
        manifest = manifest or (Path(repo_dir).parent / "apply-manifest.json")
        rc, out, err = _py(self.g, "apply_artifact.py",
                           ["apply", "--src", str(source), "--dest", str(repo_dir),
                            "--backup", str(backup_dir), "--manifest", str(manifest),
                            "--mode", "auto", "--version", semver])
        if rc != 0:
            raise GuardFailure("APPLY", "artifact repoya uygulanamadi",
                               {"detail": (out or err)[:300]})
        try:
            return json.loads(out or "{}")
        except ValueError:
            return {}
