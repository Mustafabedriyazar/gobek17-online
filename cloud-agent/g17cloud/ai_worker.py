#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — AI Worker.

GUVENLIK SOZLESMESI (kod duzeyinde zorlanir):
  * AI GitHub/Railway credential'i GORMEZ. Saglayici cagrisina giden ortam
    temizlenir; API anahtari yalnizca AI saglayicisinin kendisine gider.
  * AI git CALISTIRAMAZ, push YAPAMAZ. Ciktisi kabuk olarak YORUMLANMAZ.
  * AI'nin tek eylem yuzeyi yapisal "edit" listesidir; her yol worktree
    icinde cozulmek ZORUNDADIR (path traversal / symlink kacisi reddedilir).
  * Sonsuz dongu yok: onarim turu ust sinirla kisitlidir (pipeline yonetir).

PROVIDER ROUTING:
  fable -> buyuk ve kesin kapsamli isler (yeniden yazim, coklu dosya, genis kapsam)
  opus  -> audit, debugging, kucuk/orta hassas isler
Otomatik secim gorev metninden yapilir; istek "provider" parametresiyle ezilebilir.
"""
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

MAX_EDIT_BYTES = 2 * 1024 * 1024

BIG_HINTS = ("yeniden yaz", "rewrite", "refactor", "bastan", "baştan", "tum ", "tüm ",
             "komple", "buyuk", "büyük", "migrate", "port et", "yeni ozellik",
             "yeni özellik", "feature", "implement", "ekle ve", "sistemi")
SURGICAL_HINTS = ("audit", "debug", "root cause", "neden", "hata", "bug", "kucuk",
                  "küçük", "duzelt", "düzelt", "fix", "regression", "inceleme",
                  "guvenlik", "güvenlik", "review", "analiz")


class AIError(RuntimeError):
    pass


class UnsafeEdit(AIError):
    pass


def route_provider(task_text, requested=None, default="opus"):
    """Gorev -> saglayici. Acik istek her zaman kazanir."""
    if requested and requested not in ("auto", "", None):
        return requested
    t = (task_text or "").lower()
    big = sum(1 for h in BIG_HINTS if h in t)
    small = sum(1 for h in SURGICAL_HINTS if h in t)
    if big > small:
        return "fable"
    if small > 0:
        return "opus"
    return default


# ---------------------------------------------------------------- yol guvenligi
def safe_join(root: Path, rel: str) -> Path:
    root = root.resolve()
    if not rel or rel.startswith("/") or "\x00" in rel:
        raise UnsafeEdit("gecersiz yol: %r" % rel[:80])
    p = (root / rel).resolve()
    if p != root and root not in p.parents:
        raise UnsafeEdit("worktree disina yazma girisimi: %r" % rel[:80])
    if ".git" in p.relative_to(root).parts:
        raise UnsafeEdit(".git altina yazma girisimi")
    return p


def apply_edits(worktree: Path, edits):
    """AI'nin ONERDIGI degisiklikleri BIZ uygularz. AI'nin eli klavyede degil."""
    changed = []
    for ed in edits or []:
        if not isinstance(ed, dict):
            continue
        action = (ed.get("action") or "replace").lower()
        rel = ed.get("path") or ""
        target = safe_join(worktree, rel)
        if action == "delete":
            if target.is_file():
                target.unlink()
                changed.append(rel)
            continue
        content = ed.get("new")
        if content is None:
            continue
        if len(content.encode("utf-8")) > MAX_EDIT_BYTES:
            raise UnsafeEdit("cok buyuk duzenleme: %s" % rel)
        if action == "replace" and ed.get("old"):
            if not target.is_file():
                raise AIError("degistirilecek dosya yok: %s" % rel)
            cur = target.read_text(encoding="utf-8", errors="replace")
            if ed["old"] not in cur:
                raise AIError("eslesmeyen duzenleme (old bulunamadi): %s" % rel)
            if cur.count(ed["old"]) > 1:
                raise AIError("belirsiz duzenleme (old birden fazla): %s" % rel)
            target.write_text(cur.replace(ed["old"], content, 1), encoding="utf-8")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        changed.append(rel)
    return sorted(set(changed))


def parse_json_block(text):
    """AI ciktisindan yapisal JSON cikarir. ASLA eval/exec kullanilmaz."""
    if not text:
        raise AIError("AI bos yanit dondu")
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    start = t.find("{")
    end = t.rfind("}")
    if start < 0 or end <= start:
        raise AIError("AI yanitinda JSON bulunamadi")
    try:
        return json.loads(t[start:end + 1])
    except ValueError as ex:
        raise AIError("AI JSON'u cozumlenemedi: %s" % ex) from None


# ---------------------------------------------------------------- saglayicilar
class BaseProvider:
    name = "base"

    def available(self):
        return False

    def run(self, system, prompt, timeout):
        raise NotImplementedError


class AnthropicAPIProvider(BaseProvider):
    """Fable/Opus icin HTTP API adaptoru. Cloud'da varsayilan yol budur."""

    def __init__(self, cfg, model, name):
        self.cfg = cfg
        self.model = model
        self.name = name

    def available(self):
        return bool(self.cfg.ai_key())

    def run(self, system, prompt, timeout=900):
        body = {
            "model": self.model,
            "max_tokens": 8000,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            self.cfg.ai_api_base.rstrip("/") + "/v1/messages",
            data=json.dumps(body).encode(), method="POST",
            headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": self.cfg.ai_key(),
                "user-agent": "g17-cloud-agent",
            })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as ex:
            raise AIError("AI API hatasi: HTTP %s" % ex.code) from None
        except (urllib.error.URLError, OSError) as ex:
            raise AIError("AI API ulasilamadi: %s" % type(ex).__name__) from None
        parts = [b.get("text", "") for b in (data.get("content") or [])
                 if b.get("type") == "text"]
        return "\n".join(parts)


class ClaudeCLIProvider(BaseProvider):
    """Claude Code CLI adaptoru — v1.2.1 politikasi korunur.

    GERCEK ALLOWLIST yalnizca --tools ile uygulanir; --allowedTools tek basina
    arac MEVCUDIYETINI kisitlamadigi icin FALLBACK OLARAK KULLANILMAZ.
    Bayrak yoksa saglayici KULLANILAMAZ sayilir (fail-closed).
    """
    name = "claude-cli"
    TOOLS = "Read,Glob,Grep,Edit,Write"
    DENY = ("Bash,BashOutput,KillShell,Task,Agent,WebFetch,WebSearch,"
            "NotebookEdit,SlashCommand,mcp__*")

    def __init__(self, cfg, command="claude"):
        self.cfg = cfg
        self.command = command

    def _help(self):
        try:
            p = subprocess.run([self.command, "--help"], capture_output=True,
                               text=True, timeout=30)
            return (p.stdout or "") + (p.stderr or "")
        except (OSError, subprocess.SubprocessError):
            return ""

    def available(self):
        if not shutil.which(self.command):
            return False
        h = self._help()
        return bool(re.search(r"(^|[^-])--tools([^A-Za-z-]|$)", h))

    def run(self, system, prompt, timeout=900, cwd=None):
        if not self.available():
            raise AIError("CLAUDE_PROVIDER_UNSAFE: --tools yok, kisitlanamiyor")
        env = scrub_env(os.environ)
        p = subprocess.run(
            [self.command, "--print", "--tools", self.TOOLS,
             "--disallowedTools", self.DENY, "--permission-mode", "acceptEdits",
             "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
             "--append-system-prompt", system],
            input=prompt, cwd=str(cwd or "."), env=env,
            capture_output=True, text=True, timeout=timeout)
        return p.stdout


class MockProvider(BaseProvider):
    """Testler icin. Davranis G17_MOCK_SCRIPT dosyasindan okunur."""
    name = "mock"

    def __init__(self, cfg=None, script=None):
        self.cfg = cfg
        self.script = script or os.environ.get("G17_MOCK_SCRIPT", "")

    def available(self):
        return bool(self.script and Path(self.script).is_file())

    def run(self, system, prompt, timeout=60):
        p = subprocess.run(["/bin/sh", self.script], input=prompt,
                           capture_output=True, text=True, timeout=timeout,
                           env=scrub_env(os.environ))
        if p.returncode != 0:
            raise AIError("mock provider hatasi: %s" % p.stderr[:200])
        return p.stdout


SECRET_ENV = (
    "GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN", "G17_GH_TOKEN",
    "RAILWAY_TOKEN", "RAILWAY_API_TOKEN", "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID", "NPM_TOKEN", "OPENAI_API_KEY", "G17_API_TOKEN",
    "GITHUB_APP_PRIVATE_KEY_FILE", "GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID",
)


def scrub_env(env):
    """AI surecine giden ortamdan TUM GitHub/Railway/altyapi sirlarini siler."""
    clean = {k: v for k, v in dict(env).items() if k not in SECRET_ENV}
    clean["G17_AI_SANDBOX"] = "1"
    return clean


class AIWorker:
    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)

    def provider_for(self, name):
        if name == "mock":
            return MockProvider(self.cfg)
        if name == "claude-cli":
            return ClaudeCLIProvider(self.cfg)
        if name == "fable":
            return AnthropicAPIProvider(self.cfg, self.cfg.model_fable, "fable")
        return AnthropicAPIProvider(self.cfg, self.cfg.model_opus, "opus")

    def select(self, task_text, requested=None):
        if self.cfg.ai_provider == "mock" or requested == "mock":
            return MockProvider(self.cfg)
        name = route_provider(task_text, requested or (
            None if self.cfg.ai_provider == "auto" else self.cfg.ai_provider))
        prov = self.provider_for(name)
        if not prov.available():
            raise AIError("AI saglayici kullanilamiyor: %s" % name)
        return prov

    def call(self, provider, system, prompt, timeout=None):
        return provider.run(system, prompt, timeout or self.cfg.ai_timeout)
