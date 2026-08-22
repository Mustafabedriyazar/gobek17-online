#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — GitHub Core (deterministik).

TEK YETKILI KATMAN: repoya yazan, commit/push eden, GitHub API'sine konusan
yalnizca burasidir. AI Worker bu modulu CAGIRAMAZ ve token'i GORMEZ.

YASAKLAR (kod duzeyinde zorlanir):
  force push, --force-with-lease, reset --hard, clean -fdx,
  branch silme, remote silme, history rewrite, tag silme.
"""
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"

FORBIDDEN = (
    re.compile(r"(^|\s)--force(-with-lease)?(\s|$)"),
    re.compile(r"(^|\s)-f(\s|$)"),
    re.compile(r"reset\s+--hard"),
    re.compile(r"clean\s+-[a-z]*f[a-z]*d"),
    re.compile(r"push\s+.*--delete"),
    re.compile(r"branch\s+-[dD]\b"),
    re.compile(r"remote\s+remove"),
    re.compile(r"filter-branch|filter-repo"),
)


class GitHubError(RuntimeError):
    pass


class ForbiddenGitOperation(GitHubError):
    pass


def _scrub(text, token):
    if token and token in (text or ""):
        return text.replace(token, "***")
    return text or ""


class GitHubCore:
    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self._token_expires = 0

    # ---------------------------------------------------------------- kimlik
    def token(self):
        """Kisa omurlu App token'i gerekirse yeniler. Token DISKE YAZILMAZ."""
        if self.cfg.gh_app_id and self.cfg.gh_app_key_file:
            if not self.cfg.github_token() or time.time() > self._token_expires - 300:
                tok, exp = self._app_token()
                self.cfg.set_github_token(tok)
                self._token_expires = exp
        return self.cfg.github_token()

    def _app_token(self):
        import base64
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except ImportError as ex:
            raise GitHubError("GitHub App icin 'cryptography' gerekli") from ex

        def b64(d):
            return base64.urlsafe_b64encode(d).rstrip(b"=")

        now = int(time.time())
        head = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        body = b64(json.dumps({"iat": now - 60, "exp": now + 540,
                               "iss": str(self.cfg.gh_app_id)}).encode())
        signing = head + b"." + body
        with open(self.cfg.gh_app_key_file, "rb") as fh:
            key = serialization.load_pem_private_key(fh.read(), password=None)
        sig = key.sign(signing, padding.PKCS1v15(), hashes.SHA256())
        jwt = (signing + b"." + b64(sig)).decode()
        # PART L: MINIMUM izinler. admin/delete/secrets ISTENMEZ.
        perms = {"contents": "write", "metadata": "read", "actions": "read",
                 "checks": "read", "pull_requests": "write", "issues": "write"}
        res = self._api("POST",
                        "/app/installations/%s/access_tokens" % self.cfg.gh_app_install,
                        {"permissions": perms}, bearer=jwt)
        return res.get("token", ""), now + 3300

    def auth_status(self):
        """Kimlik + yetenek ozeti. TOKEN DEGERI DONMEZ."""
        out = {"mode": "none", "identity": None, "read": "UNKNOWN",
               "write": "UNKNOWN", "protected": "unknown"}
        tok = ""
        try:
            tok = self.token()
        except GitHubError as ex:
            out["error"] = str(ex)
        if tok:
            out["mode"] = "app" if self.cfg.gh_app_id else "token"
            try:
                who = self._api("GET", "/user")
                out["identity"] = who.get("login")
            except GitHubError:
                out["identity"] = "installation"
            try:
                repo = self._api("GET", "/repos/%s" % self.cfg.repo)
                perm = (repo.get("permissions") or {})
                out["read"] = "PASS" if repo.get("name") else "FAIL"
                out["write"] = "PASS" if perm.get("push") else (
                    "UNAVAILABLE" if perm else "UNKNOWN")
            except GitHubError:
                pass
            try:
                self._api("GET", "/repos/%s/branches/%s/protection"
                          % (self.cfg.repo, self.cfg.branch))
                out["protected"] = "yes"
            except GitHubError:
                out["protected"] = "no"
        elif self._git_can_read():
            out["mode"] = "git-credential"
            out["read"] = "PASS"
        return out

    def _git_can_read(self):
        if not Path(self.cfg.repo_dir).is_dir():
            return False
        try:
            self._git(["ls-remote", "--heads", "origin"], cwd=self.cfg.repo_dir)
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- git
    def _git(self, args, cwd=None, check=True, timeout=300):
        cmdline = " ".join(args)
        for rx in FORBIDDEN:
            if rx.search(cmdline):
                raise ForbiddenGitOperation("yasak git islemi engellendi: %s" % cmdline)
        tok = self.cfg.github_token()
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "/bin/true"
        pre = ["git"]
        if tok:
            # Token YALNIZ bu cagrinin ortaminda; komut satirinda GORUNMEZ
            # (process listesine dusmez), diske yazilmaz.
            env["G17_GH_TOKEN"] = tok
            helper = ('!f(){ echo username=x-access-token; '
                      'echo password=$G17_GH_TOKEN; };f')
            pre += ["-c", "credential.helper=", "-c", "credential.helper=" + helper]
        workdir = str(cwd or self.cfg.repo_dir)
        try:
            proc = subprocess.run(pre + args, cwd=workdir,
                                  env=env, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as ex:
            # Repo henuz klonlanmamis olabilir (ilk acilis) ya da git yok.
            # Uzun calisan serviste bu HAM ISTISNA olarak disari sizmamali.
            raise GitHubError("git calistirilamadi (%s): %s" % (cmdline, type(ex).__name__))
        if check and proc.returncode != 0:
            raise GitHubError("git %s -> %s" % (
                cmdline, _scrub(proc.stderr.strip() or proc.stdout.strip(), tok)[:400]))
        return _scrub(proc.stdout.strip(), tok)

    def clone_or_update(self):
        """Repoyu hazirlar. Telefon yok: her sey container diskinde."""
        rd = Path(self.cfg.repo_dir)
        if (rd / ".git").is_dir():
            self._git(["remote", "set-url", "origin", self.remote_url()], cwd=rd)
            self._git(["fetch", "--quiet", "origin", self.cfg.branch], cwd=rd)
            self._git(["checkout", self.cfg.branch], cwd=rd)
            self._git(["merge", "--ff-only", "origin/" + self.cfg.branch], cwd=rd)
            return rd
        rd.parent.mkdir(parents=True, exist_ok=True)
        if rd.exists():
            shutil.rmtree(rd)
        self._git(["clone", "--branch", self.cfg.branch, self.remote_url(), str(rd)],
                  cwd=rd.parent, timeout=900)
        return rd

    def remote_url(self):
        if self.cfg.repo.startswith(("http://", "https://", "/", "file://")):
            return self.cfg.repo          # testlerde yerel bare repo
        return "https://github.com/%s.git" % self.cfg.repo

    def head(self):
        return self._git(["rev-parse", "HEAD"])

    def short_head(self):
        return self._git(["rev-parse", "--short", "HEAD"])

    def is_clean(self):
        return self._git(["status", "--porcelain"]) == ""

    def make_worktree(self, path, ref=None):
        """AI icin TEK KULLANIMLIK worktree. AI ana calisma kopyasina dokunmaz."""
        p = Path(path)
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
        self._git(["worktree", "prune"], check=False)
        self._git(["worktree", "add", "--detach", str(p),
                   ref or ("origin/" + self.cfg.branch)])
        return p

    def remove_worktree(self, path):
        try:
            self._git(["worktree", "remove", "--force", str(path)], check=False)
        except GitHubError:
            pass
        shutil.rmtree(str(path), ignore_errors=True)
        self._git(["worktree", "prune"], check=False)

    def commit(self, message, author="G17 Cloud Agent <g17-agent@users.noreply.github.com>"):
        self._git(["add", "-A", "--", "."])
        staged = self._git(["diff", "--cached", "--name-only"])
        if not staged:
            return None
        # BUG-3 mirasi: diff --check FAIL ise commit YOK
        self._git(["diff", "--cached", "--check"])
        name, email = author.rsplit(" <", 1)
        self._git(["-c", "user.name=" + name, "-c", "user.email=" + email.rstrip(">"),
                   "commit", "-q", "-m", message])
        return self.short_head()

    def push(self):
        """YALNIZCA fast-forward. Force asla."""
        branch = self.cfg.branch
        cur = self._git(["rev-parse", "--abbrev-ref", "HEAD"])
        if cur != branch:
            raise GitHubError("branch %s — yalnizca %s'e push edilir" % (cur, branch))
        self._git(["push", "origin", branch], timeout=600)
        return self.short_head()

    def staged_files(self):
        return [x for x in self._git(["diff", "--cached", "--name-only"]).splitlines() if x]

    def diff_cached(self):
        return self._git(["diff", "--cached"])

    # ---------------------------------------------------------------- API
    def _api(self, method, path, body=None, bearer=None, raw=False):
        tok = bearer or self.cfg.github_token()
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "g17-cloud-agent",
            "Content-Type": "application/json",
            **({"Authorization": "Bearer " + tok} if tok else {}),
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                payload = r.read().decode()
        except urllib.error.HTTPError as ex:
            raise GitHubError("GitHub API %s %s -> %s" % (method, path, ex.code)) from None
        except (urllib.error.URLError, OSError) as ex:
            raise GitHubError("GitHub API ulasilamadi: %s" % type(ex).__name__) from None
        if raw:
            return payload
        try:
            return json.loads(payload)
        except ValueError:
            return {}

    # ---- Actions -------------------------------------------------------------
    def actions_for_commit(self, sha):
        try:
            res = self._api("GET", "/repos/%s/actions/runs?head_sha=%s&per_page=5"
                            % (self.cfg.repo, sha))
        except GitHubError:
            return None
        runs = res.get("workflow_runs") or []
        if not runs:
            return None
        return [{"name": r.get("name"), "status": r.get("status"),
                 "conclusion": r.get("conclusion"), "id": r.get("id"),
                 "url": r.get("html_url")} for r in runs]

    def wait_actions(self, sha, timeout=900, interval=10, sleep=time.sleep):
        """PASS / FAIL / N/A / TIMEOUT. Basarisiz CI asla PASS gosterilmez."""
        waited = 0
        while waited <= timeout:
            runs = self.actions_for_commit(sha)
            if runs is None:
                return {"result": "N/A", "runs": []}
            done = [r for r in runs if r["status"] == "completed"]
            if len(done) == len(runs):
                bad = [r for r in done if r["conclusion"] not in ("success", "skipped", "neutral")]
                return {"result": "FAIL" if bad else "PASS", "runs": runs}
            sleep(interval)
            waited += interval
        return {"result": "TIMEOUT", "runs": []}

    def failed_run_log(self, run_id, limit=2000):
        try:
            return self._api("GET", "/repos/%s/actions/runs/%s/logs"
                             % (self.cfg.repo, run_id), raw=True)[-limit:]
        except GitHubError:
            return ""

    # ---- PR / Release / Issues -------------------------------------------------
    def list_prs(self, state="open"):
        return self._api("GET", "/repos/%s/pulls?state=%s&per_page=20" % (self.cfg.repo, state))

    def create_pr(self, head, title, body=""):
        return self._api("POST", "/repos/%s/pulls" % self.cfg.repo,
                         {"title": title, "head": head, "base": self.cfg.branch, "body": body})

    def list_releases(self):
        return self._api("GET", "/repos/%s/releases?per_page=20" % self.cfg.repo)

    def create_release(self, tag, name, body):
        return self._api("POST", "/repos/%s/releases" % self.cfg.repo,
                         {"tag_name": tag, "name": name, "body": body, "draft": False})

    def list_issues(self):
        return self._api("GET", "/repos/%s/issues?state=open&per_page=20" % self.cfg.repo)

    def create_issue(self, title, body):
        return self._api("POST", "/repos/%s/issues" % self.cfg.repo,
                         {"title": title, "body": body})
