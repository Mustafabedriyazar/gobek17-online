#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — gorev akisi.

TASK -> clone/worktree -> AI inspect -> reproduce -> root cause -> fix
     -> repair loop -> tests -> guards -> vXXX artifact -> commit/push
     -> Actions -> Railway auto deploy -> production health -> final report

KILIT KURALI: AI fazlari kilitsiz (paralel arastirma serbest). Guard'dan
production'a kadar olan zincir TEK release kilidi altinda calisir.
"""
import json
import time
from pathlib import Path

from . import ai_worker as aiw
from .ai_worker import AIError, AIWorker, apply_edits, parse_json_block, route_provider
from .github_core import GitHubCore, GitHubError
from .production import ProductionController
from .release_guard import GuardFailure, ReleaseGuard, preflight
from .store import DEFAULT_TASK_MODE


def reproduce_required(mode):
    """REPRODUCE kapisinin TEK yetki kaynagi. Gorev metni ETKILEMEZ.

    mode='fix' -> REPRODUCE zorunlu (eski davranis). mode='feature'/'chore'
    -> REPRODUCE atlanir, akis dogrudan root-cause/implement ile devam eder.
    """
    return (mode or DEFAULT_TASK_MODE) == "fix"


SYSTEM_CONTEXT = """GÖBEK17 / OKEY17 kanonik projesi.

Calisma ilkesi: REPRODUCE -> ROOT CAUSE -> MINIMAL TARGETED FIX -> REGRESSION -> RELEASE.

Kurallar:
- Eski bir checkpoint'e/branch'e ASLA donme. Her gercek release sirali bir sonraki build'dir.
- Kanonik gameplay engine (/*OKEY17-BAS*/../*OKEY17-SON*/) ve strategic bot (EBOT)
  bloklarini gorev gerektirmedikce DEGISTIRME.
- Su davranislari koru: offline mod, ozel oda, auth, multiplayer, reconnect,
  Railway uyumu, Android dosya/icerik onizleme, mevcut production davranisi.
- Minimal diff uret. Gereksiz bagimlilik ekleme. Secret yazma.
- Sen git calistiramazsin, push edemezsin, credential goremezsin. Yalnizca
  asagida istenen JSON'u dondurursun; degisiklikleri sistem uygular.
"""

INSPECT_PROMPT = """# GOREV (faz: inspect)
Build: v{build}
Parent: {parent}
Gorev: {task}

Repo ozeti:
{context}

Once KOD DEGISTIRME. Once anla. Yalnizca su JSON'u dondur:
{{"reproduced": true|false,
  "rootCause": "kisa teknik aciklama",
  "files": ["degisecek dosyalar"],
  "minimalFix": "en kucuk mudahale plani",
  "tests": ["kosulacak/eklenmesi gereken testler"],
  "title": "kisa release basligi"}}
Reproduce edemiyorsan reproduced:false dondur ve TAHMINLE genis refactor ONERME.
"""

IMPLEMENT_PROMPT = """# GOREV (faz: implement)
Build: v{build}
Gorev: {task}
Kok neden: {rootCause}
Plan: {minimalFix}

Ilgili dosya icerikleri:
{files}

Minimal duzeltmeyi uygula. Yalnizca su JSON'u dondur:
{{"edits": [
   {{"path": "server/x.cjs", "action": "replace", "old": "tam eslesen mevcut metin",
     "new": "yeni metin"}},
   {{"path": "server/test-v{build}-x.cjs", "action": "create", "new": "dosya icerigi"}}
 ],
 "summary": "tek cumle"}}
"old" alani dosyada TAM OLARAK BIR KEZ gecmelidir.
"""

REPAIR_PROMPT = """# GOREV (faz: repair, deneme {attempt}/{max})
Testler FAIL etti. Hata ciktisi:
{failure}

Su ana kadarki degisiklikler: {changed}

Hatayi gider. Ilk uygulama turuyla AYNI edit sozlesmesini kullanarak yalnizca
su JSON'u dondur:
{{"edits": [
   {{"path": "server/x.cjs", "action": "replace", "old": "tam eslesen mevcut metin",
     "new": "yeni metin"}},
   {{"path": "server/test-v{build}-x.cjs", "action": "create", "new": "dosya icerigi"}}
 ],
 "summary": "tek cumle"}}
Her edit girdisi "path" (worktree'ye gore TAM dosya yolu — BOS BIRAKILAMAZ),
"action" ("replace"|"create"|"delete") ve icerik alanlarini ("new", gerekirse
"old") tasir. "old" alani dosyada TAM OLARAK BIR KEZ gecmelidir. Kapsami
GENISLETME.
"""


def apply_repair_edits(wt, rep, attempt, max_attempts, ignored_total):
    """ONARIM TURU EDIT DOGRULAMASI.

    Onarim turundan gelen "edits" listesinde yol alani (path, yoksa file/
    filename — bkz. aiw.edit_path) bos/eksik olan girdiler YOK SAYILIR (raise
    EDILMEZ); gecerli girdiler normal sekilde uygulanir. Listede hicbir
    gecerli girdi kalmazsa GuardFailure(REPAIR_INVALID_EDITS) firlatir;
    mesaj o turda kac girdinin yok sayildigini belirtir.

    Ilk uygulama (implement) turunu ETKILEMEZ — orada apply_edits dogrudan
    cagrilir ve bos path halen UnsafeEdit ile REDDEDILIR (bkz. run()).

    Donus: (bu_turda_degisen_dosyalar, guncel_toplam_yok_sayilan, bu_turda_yok_sayilan)
    """
    valid, ignored = aiw.split_repair_edits(rep.get("edits"))
    ignored_total += ignored
    if not valid:
        raise GuardFailure(
            "REPAIR_INVALID_EDITS",
            "onarim turu %d/%d: uygulanacak gecerli edit yok (%d girdi yok sayildi — "
            "path alani bos/eksik)" % (attempt, max_attempts, ignored),
            {"attempt": attempt, "ignoredRepairEdits": ignored_total})
    return apply_edits(wt, valid), ignored_total, ignored


def repair_failure_signature(entry):
    """Onarim turu icin hata imzasi: hata tipi + hataya konu dosya yolunun birlesimi.

    Ayni imza (ayni hata tipi + ayni dosya) bir sonraki denemede de gorulurse
    onarim dongusu REPEATED_FAILURE ile durur (bkz. Pipeline.run, bolum 5).
    """
    import re
    output = entry.get("output") or ""
    first_line = next((ln.strip() for ln in output.splitlines() if ln.strip()), "")
    m = re.search(r"([A-Za-z_][A-Za-z0-9_.]*Error)\b", output)
    err_type = m.group(1) if m else (first_line[:60] or "UNKNOWN")
    return "%s::%s" % (err_type, entry.get("test") or "?")


class Pipeline:
    def __init__(self, cfg, store, lock, log=None):
        self.cfg = cfg
        self.store = store
        self.lock = lock
        self.log = log or (lambda *a, **k: None)
        self.gh = GitHubCore(cfg)
        self.guard = ReleaseGuard(cfg)
        self.ai = AIWorker(cfg)
        self.prod = ProductionController(cfg)

    # ------------------------------------------------------------------ yardim
    def _ev(self, tid, phase, msg, **extra):
        self.log("[%s] %s: %s" % (tid, phase, msg))
        return self.store.event(tid, phase, msg, **extra)

    def _fail(self, rec, stage, reason, detail=None):
        rec = self.store.get(rec["id"]) or rec
        rec["status"] = "failed"
        rec["phase"] = stage
        rec["result"] = dict(rec.get("result") or {},
                             stage=stage, reason=reason, detail=detail or {},
                             commit=rec.get("result", {}).get("commit"),
                             push="NOT PUSHED" if not rec.get("result", {}).get("pushed") else "PUSHED",
                             production="UNCHANGED")
        self.store.save(rec)
        self._ev(rec["id"], stage, "FAILED: %s" % reason)
        return rec

    def _preflight(self, task_id, rec):
        """GOREVIN ILK ADIMI. FAIL ise GuardFailure firlatir (bkz. release_guard.preflight);
        cagiran run() bunu yakalayip gorevi PREFLIGHT asamasinda durdurur."""
        wt_target = Path(self.cfg.work_dir) / ("wt-%s" % task_id)
        repo_exists = (Path(self.cfg.repo_dir) / ".git").is_dir()
        pf = preflight(
            lane="release", repo=self.cfg.repo, other_repo=self.cfg.self_repo,
            branch=self.cfg.branch, work_dir=self.cfg.work_dir, worktree_path=wt_target,
            repo_exists=repo_exists,
            current_branch=lambda: self.gh._git(["rev-parse", "--abbrev-ref", "HEAD"]),
            is_clean=self.gh.is_clean)
        rec = self.store.update(task_id, result=dict(rec.get("result") or {}, preflight=pf))
        self._ev(task_id, "preflight", "PASS (%s)" % ", ".join(pf["checks"]))
        return rec

    def repo_context(self, repo_dir, build):
        """AI'ya SECICI baglam. Tum repo prompt'a basilmaz."""
        rd = Path(repo_dir)
        lines = []
        for rel in ("package.json", "server/package.json"):
            p = rd / rel
            if p.is_file():
                lines.append("%s: %s" % (rel, p.read_text(encoding="utf-8",
                                                          errors="replace")[:600]))
        srv = rd / "server"
        if srv.is_dir():
            names = sorted(x.name for x in srv.iterdir() if x.is_file())
            lines.append("server/: " + ", ".join(names[:60]))
        tests = self.guard.discover_tests(rd, build)
        lines.append("kosulacak testler: " + (", ".join(tests) or "yok"))
        return "\n".join(lines)[:6000]

    def file_context(self, source, files, budget=60000):
        out, used = [], 0
        for rel in (files or [])[:12]:
            try:
                p = aiw.safe_join(Path(source), rel)
            except aiw.UnsafeEdit:
                continue
            if not p.is_file():
                out.append("### %s\n(dosya yok — yeni olusturulacak)" % rel)
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            if used + len(txt) > budget:
                txt = txt[: max(0, budget - used)]
            used += len(txt)
            out.append("### %s\n%s" % (rel, txt))
        return "\n\n".join(out)

    def repair_file_context(self, wt, changed, budget=8000, head_lines=40, tail_lines=40):
        """ONARIM TURU baglami: degisen dosyalarin GUNCEL icerigini AI'ya tasir.

        AI "old" alanini bu icerikten uretmelidir — hafizadan uretilen
        eslesmeyen metin, "eslesmeyen duzenleme" hatasinin onarim turunda
        tekrar etmesine yol aciyordu. Dosya listesi pipeline'in zaten
        bildigi degisiklik kaydindan (changed) gelir; ayri bir izleme
        mekanizmasi kurulmaz. Dosya budget'i asarsa yalnizca ilk/son
        satirlar eklenir ve kirpildigi acikca belirtilir.
        """
        names = ", ".join(changed or []) or "(yok)"
        blocks = []
        for rel in changed or []:
            try:
                p = aiw.safe_join(Path(wt), rel)
            except aiw.UnsafeEdit:
                continue
            if not p.is_file():
                blocks.append("### %s\n(dosya yok — bu turda silinmis olabilir)" % rel)
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            if len(txt) <= budget:
                blocks.append("### %s\n%s" % (rel, txt))
                continue
            lines = txt.splitlines()
            head = "\n".join(lines[:head_lines])
            tail = "\n".join(lines[-tail_lines:])
            blocks.append(
                "### %s (KIRPILDI — %d satirin ilk %d ve son %d satiri gosteriliyor)\n%s\n...\n%s"
                % (rel, len(lines), head_lines, tail_lines, head, tail))
        if not blocks:
            return names
        return names + "\n\nGUNCEL dosya icerikleri (old alanini BUNDAN uret):\n" + "\n\n".join(blocks)

    # ------------------------------------------------------------------ akis
    def run(self, task_id):
        rec = self.store.get(task_id)
        if not rec:
            return None
        build = int(str(rec["build"]).lstrip("vV"))
        wt = None
        try:
            rec = self.store.update(task_id, status="running", phase="prepare")

            # --- PREFLIGHT: gorevin ILK ADIMI ------------------------------------
            # Serit kurali (dogru repo), worktree konumu, branch ve calisma agaci
            # temizligi AI/git/guard zincirinden ONCE dogrulanir. Basarisiz olursa
            # gorev burada durur; sonraki adimlara GECILMEZ (bkz. release_guard.preflight).
            rec = self._preflight(task_id, rec)

            # --- 0 kurulum dizini hijyeni ---------------------------------------
            # Onceki turdan (crash, eski surum vb.) kurulum dizininde artik
            # kalmis olabilir; goreve baslamadan temizlenir.
            aiw.clean_install_leftovers(log=self.log)

            # --- 1 repo -------------------------------------------------------
            self._ev(task_id, "prepare", "repo hazirlaniyor")
            self.gh.clone_or_update()
            parent = self.gh.short_head()
            auth = self.gh.auth_status()
            rec = self.store.update(task_id, result=dict(rec.get("result") or {},
                                                         parent=parent, githubAuth=auth))
            if auth.get("write") == "UNAVAILABLE" and not rec["dryRun"] and not rec["noDeploy"]:
                return self._fail(rec, "AUTH", "GITHUB_WRITE: UNAVAILABLE")

            # --- 2 worktree (AI hapishanesi) ------------------------------------
            wt = self.gh.make_worktree(Path(self.cfg.work_dir) / ("wt-%s" % task_id))
            self._ev(task_id, "worktree", "tek kullanimlik worktree hazir")
            before_hashes = self.guard.block_hashes(wt)

            # --- 3 AI inspect ---------------------------------------------------
            provider_name = route_provider(rec["task"], rec.get("provider"))
            provider = self.ai.select(rec["task"], rec.get("provider"))
            self._ev(task_id, "inspect", "AI analiz ediyor",
                     provider=getattr(provider, "name", provider_name))
            plan_raw = self.ai.call(provider, SYSTEM_CONTEXT, INSPECT_PROMPT.format(
                build=build, parent=parent, task=rec["task"],
                context=self.repo_context(wt, build)), cwd=wt)
            plan = parse_json_block(plan_raw)
            if reproduce_required(rec.get("mode")) and not plan.get("reproduced"):
                return self._fail(rec, "REPRODUCE", "AI sorunu reproduce edemedi",
                                  {"rootCause": str(plan.get("rootCause"))[:300]})
            self._ev(task_id, "root-cause", str(plan.get("rootCause"))[:200])
            rec = self.store.update(task_id, result=dict(rec.get("result") or {},
                                                         plan={k: plan.get(k) for k in
                                                               ("rootCause", "files",
                                                                "minimalFix", "title")},
                                                         provider=getattr(provider, "name",
                                                                          provider_name)))

            # --- 4 implement ------------------------------------------------------
            self._ev(task_id, "implement", "minimal duzeltme uygulaniyor")
            impl_raw = self.ai.call(provider, SYSTEM_CONTEXT, IMPLEMENT_PROMPT.format(
                build=build, task=rec["task"], rootCause=plan.get("rootCause", ""),
                minimalFix=plan.get("minimalFix", ""),
                files=self.file_context(wt, plan.get("files"))), cwd=wt)
            impl = parse_json_block(impl_raw)
            edits = impl.get("edits") or []
            if not edits and (rec.get("mode") or DEFAULT_TASK_MODE) == "chore":
                rec = self.store.update(task_id, status="success", phase="done",
                                        result=dict(rec.get("result") or {},
                                                    outcome="NO_CHANGE_REQUIRED",
                                                    push="SKIPPED",
                                                    production="UNCHANGED"))
                self._ev(task_id, "done",
                         "NO_CHANGE_REQUIRED: chore modunda degisiklik gerekmedi — commit/push YOK")
                return rec
            changed = apply_edits(wt, edits)
            if not changed:
                return self._fail(rec, "IMPLEMENT", "AI hicbir degisiklik uretmedi")
            self._ev(task_id, "implement", "%d dosya degisti" % len(changed),
                     files=changed[:20])

            # --- 5 testler + onarim dongusu (SINIRLI) ------------------------------
            attempt = 0
            ignored_repair_edits = 0
            seen_failure_signatures = set()
            tests = self.guard.run_tests(wt, build)
            while not tests["ok"]:
                attempt += 1
                if attempt > self.cfg.max_repair:
                    return self._fail(rec, "TEST_REPAIR",
                                      "%d onarim turunda testler gecmedi" % self.cfg.max_repair,
                                      {"attempts": attempt - 1,
                                       "failed": [f["test"] for f in tests["failed"]]})
                current_signatures = {repair_failure_signature(f) for f in tests["failed"]}
                repeated = current_signatures & seen_failure_signatures
                if repeated:
                    err_type, _, err_path = next(iter(repeated)).partition("::")
                    return self._fail(rec, "REPEATED_FAILURE",
                                      "onarim dongusu durdu: '%s' hatasi '%s' dosyasinda tekrarladi"
                                      % (err_type, err_path),
                                      {"attempts": attempt - 1,
                                       "signature": next(iter(repeated))})
                seen_failure_signatures |= current_signatures
                self._ev(task_id, "repair", "test FAIL — AI onarim turu %d/%d"
                         % (attempt, self.cfg.max_repair))
                failure = "\n".join("%s:\n%s" % (f["test"], f["output"])
                                    for f in tests["failed"])[:6000]
                rep_raw = self.ai.call(provider, SYSTEM_CONTEXT, REPAIR_PROMPT.format(
                    attempt=attempt, max=self.cfg.max_repair, failure=failure,
                    changed=self.repair_file_context(wt, changed), build=build), cwd=wt)
                rep = parse_json_block(rep_raw)
                new_changed, ignored_repair_edits, ignored_now = apply_repair_edits(
                    wt, rep, attempt, self.cfg.max_repair, ignored_repair_edits)
                if ignored_now:
                    self._ev(task_id, "repair", "%d gecersiz edit (bos/eksik path) yok sayildi"
                             % ignored_now)
                changed = sorted(set(changed) | set(new_changed))
                rec = self.store.update(task_id, result=dict(
                    rec.get("result") or {}, ignoredRepairEdits=ignored_repair_edits))
                tests = self.guard.run_tests(wt, build)
            self._ev(task_id, "tests", tests["summary"])
            rec = self.store.update(task_id, attempts=attempt,
                                    result=dict(rec.get("result") or {},
                                                tests=tests["summary"],
                                                changedFiles=changed,
                                                ignoredRepairEdits=ignored_repair_edits))

            # --- 6 GUARD ZINCIRI (release kilidi altinda) ---------------------------
            if not self.lock.acquire(task_id, build):
                holder = self.lock.holder() or {}
                return self._fail(rec, "LOCK",
                                  "baska bir release surüyor (build v%s)"
                                  % holder.get("build", "?"),
                                  {"holder": holder.get("taskId")})
            try:
                self.lock.heartbeat(task_id)
                self._ev(task_id, "guards", "deterministik guard zinciri")

                after_hashes = self.guard.block_hashes(wt)
                canon = self.guard.check_canonical(before_hashes, after_hashes)
                self._ev(task_id, "guards", "engine/bot: %s" % canon["status"])

                cur = self.guard.repo_build(self.cfg.repo_dir)
                seq = self.guard.check_sequential(cur, build)
                self._ev(task_id, "guards", "surum: v%s -> v%s"
                         % (seq.get("current"), build))

                stamp = self._stamp(build, plan.get("title"))
                self._stamp_release(wt, build, stamp)
                self.repackage_app(wt, build); tests2 = self.guard.run_tests(wt, build)
                if not tests2["ok"]:
                    return self._fail(rec, "RELEASE", "surum damgasi sonrasi testler FAIL")
                self.guard.verify_artifact(wt, build)

                art_dir = Path(self.cfg.state_dir) / "artifacts"
                art_dir.mkdir(parents=True, exist_ok=True)
                art = self.guard.build_artifact(wt, art_dir / ("%s.zip" % stamp))
                self._ev(task_id, "artifact", "SHA256 %s" % art["sha256"][:16])
                rec = self.store.update(task_id, result=dict(rec.get("result") or {},
                                                             artifact=Path(art["path"]).name,
                                                             sha256=art["sha256"],
                                                             healthStamp=stamp,
                                                             engineGuard=canon["status"]))

                if rec["dryRun"] or rec["noDeploy"] or not self.cfg.auto_deploy:
                    mode = "dry-run" if rec["dryRun"] else "no-deploy"
                    rec = self.store.update(task_id, status="success", phase="done",
                                            result=dict(rec.get("result") or {},
                                                        mode=mode, push="SKIPPED",
                                                        production="UNCHANGED"))
                    self._ev(task_id, "done", "%s tamam — commit/push YOK" % mode)
                    return rec

                # --- 7 repoya uygula + secret/diff guard -------------------------
                self.guard.apply_to_repo(wt, self.cfg.repo_dir, build,
                                         backup_dir=Path(self.cfg.work_dir) / "backup",
                                         manifest=Path(self.cfg.work_dir) / "manifest.json")
                self.gh._git(["add", "-A", "--", "."])
                files = self.gh.staged_files()
                self.guard.check_diff(files, self.cfg.repo_dir)
                self.guard.check_secrets(self.gh.diff_cached(), wt)
                self._ev(task_id, "guards", "diff + secret guard PASS (%d dosya)"
                         % len(files))

                # --- 8 commit + push ------------------------------------------------
                title = (plan.get("title") or "production build")
                sha = self.gh.commit("v%d: %s" % (build, title))
                if not sha:
                    return self._fail(rec, "COMMIT", "commit olusmadi")
                self._ev(task_id, "commit", sha)
                rec = self.store.update(task_id, result=dict(rec.get("result") or {},
                                                             commit=sha))
                self.lock.heartbeat(task_id)
                self.gh.push()
                self._ev(task_id, "push", "GitHub main guncellendi")
                rec = self.store.update(task_id, result=dict(rec.get("result") or {},
                                                             pushed=True, push="PASS"))

                # --- 9 Actions ---------------------------------------------------------
                acts = self.gh.wait_actions(self.gh.head(), timeout=600)
                self._ev(task_id, "actions", "GitHub Actions: %s" % acts["result"])
                rec = self.store.update(task_id, result=dict(rec.get("result") or {},
                                                             actions=acts["result"]))

                # --- 10 Railway auto deploy + production dogrulama --------------------
                self._ev(task_id, "production", "Railway otomatik deploy bekleniyor")
                res = self.prod.wait_for(stamp)
                if res["result"] != "PASS":
                    return self._fail(rec, "PRODUCTION",
                                      "beklenen damga gorulmedi (%s)" % stamp,
                                      {"seen": res.get("seen"), "waited": res.get("waited"),
                                       "note": "commit KORUNDU, rollback YAPILMADI"})
                self._ev(task_id, "production", "v%d YAYINDA (%s)" % (build, stamp))
                rec = self.store.update(task_id, status="success", phase="done",
                                        result=dict(rec.get("result") or {},
                                                    production="PASS", health=stamp))
                return rec
            finally:
                self.lock.release(task_id)
        except GuardFailure as ex:
            return self._fail(rec, ex.stage, ex.reason, ex.detail)
        except (AIError, GitHubError) as ex:
            return self._fail(rec, rec.get("phase", "?").upper(), str(ex)[:300])
        except Exception as ex:                                    # beklenmeyen
            return self._fail(rec, "INTERNAL", "%s: %s" % (type(ex).__name__, str(ex)[:200]))
        finally:
            if wt:
                try:
                    self.gh.remove_worktree(wt)
                except Exception:
                    pass
            # Basarili da basarisiz da bitse: o goreve ait gecici alan kalkar.
            aiw.cleanup_task_workspace(self.cfg, task_id, log=self.log)

    # ------------------------------------------------------------------ damga
    def _stamp(self, build, title):
        slug = "".join(c if c.isalnum() else "-" for c in (title or "production build").lower())
        slug = "-".join(x for x in slug.split("-") if x)[:40] or "production-build"
        return "gobek17-%d-%s" % (build, slug)

    def _stamp_release(self, source, build, stamp):
        """Kanonik surum damgalarini HEDEFLI olarak yazar (kor global replace YOK)."""
        from .release_guard import _py
        rc, out, err = _py(self.cfg.guards_dir, "version_guard.py",
                           ["semver", "--build", str(build)])
        semver = (out or "").strip()
        src = Path(source) / "app" if (Path(source) / "app").is_dir() else Path(source)
        edits = 0
        import re as _re
        for rel, pattern, repl in (
            ("package.json", r'("version"\s*:\s*")\d+\.\d+\.\d+(")', r"\g<1>%s\g<2>" % semver),
            ("server/package.json", r'("version"\s*:\s*")\d+\.\d+\.\d+(")', r"\g<1>%s\g<2>" % semver),
            ("index.html", r'(var\s+BUILD\s*=\s*")gobek17-\d+-[a-z0-9-]+(")', r"\g<1>%s\g<2>" % stamp),
            ("sw.js", r'(var\s+C\s*=\s*")gobek17-\d+-[a-z0-9-]+(")', r"\g<1>%s\g<2>" % stamp),
            ("multiplayer-client.js", r"(build\s*:\s*')gobek17-\d+-[a-z0-9-]+(')", r"\g<1>%s\g<2>" % stamp),
            ("multiplayer-bridge.js", r"(build\s*:\s*')gobek17-\d+-[a-z0-9-]+(')", r"\g<1>%s\g<2>" % stamp),
            ("server/server.cjs", r"(build\s*:\s*')gobek17-\d+-[a-z0-9-]+(')", r"\g<1>%s\g<2>" % stamp),
        ):
            p = src / rel
            if not p.is_file():
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            new = _re.sub(pattern, repl, txt)
            if new != txt:
                p.write_text(new, encoding="utf-8")
                edits += 1
        # --- KANONIK DAMGA ESITLEME ------------------------------------------
        # version_guard yalnizca asagidaki 7 dosyayi tarar, ama damgayi dosyanin
        # HER YERINDE arar. Yukaridaki hedefli yamalar sadece atama bicimini
        # degistirdigi icin ayni dosyadaki diger gecisler eski surumde kalip
        # "KARISIK surum damgalari" hatasi uretiyordu. Global replace kapsami
        # guard'in kapsamiyla ayni tutuluyor: dokuman ve testlere DOKUNULMAZ.
        _CANON = ("package.json", "server/package.json", "sw.js",
                  "server/server.cjs", "index.html",
                  "multiplayer-client.js", "multiplayer-bridge.js")
        _leftover = _re.compile(r"gobek17-\d{3}-[a-z0-9-]+")
        _root = Path(source)
        _targets = [src / rel for rel in _CANON]
        if src != _root:
            _targets.append(_root / "package.json")   # 3-file bootstrap koku
        for p in _targets:
            if not p.is_file():
                continue
            txt = p.read_text(encoding="utf-8", errors="replace")
            new = _leftover.sub(stamp, txt)
            if new != txt:
                p.write_text(new, encoding="utf-8")
                edits += 1
        return edits

    def repackage_app(self, wt, build):
        import json, zipfile, os
        from pathlib import Path
        root = Path(wt); appdir = root / "app"
        if not appdir.is_dir():
            return None
        minor = build if build < 100 else build - 100
        ver = "1.%d.0" % minor
        for tgt in (appdir / "package.json", appdir / "server" / "package.json", root / "package.json"):
            if tgt.is_file():
                d = json.loads(tgt.read_text(encoding="utf-8"))
                d["version"] = ver
                tgt.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        import re as _re  # ZIP EXCLUDE
        _skip = _re.compile(r"^(QA_GUARD_REPORT_|QA_V\d|RULE_DELTA_|MULTIPLAYER_PROTOCOL_|README_|ESLI-2V2-CONTRACT|test-)|(\.md$)|(^\.gitignore$)")
        zp = root / "gobek17-app.zip"
        with zipfile.ZipFile(zp, "w", 8) as z:
            for dp, _, fs in os.walk(appdir):
                for f in sorted(fs):
                    fp = Path(dp) / f
                    rel = str(fp.relative_to(appdir)).replace("\\", "/")
                    if _skip.search(rel) or _skip.search(rel.split("/")[-1]): continue
                    z.write(fp, rel)
        return ver
