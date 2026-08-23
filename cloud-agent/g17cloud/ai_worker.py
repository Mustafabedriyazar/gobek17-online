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
  * CALISMA ALANI IZOLASYONU: saglayici HER cagrida yalniz o goreve ait
    izole worktree'yi cwd olarak alir; ajanin KENDI kurulum dizini hicbir
    kosulda cwd ya da ek erisim kapsami olarak VERILMEZ (bkz. AIWorker.call,
    agent_install_dir, clean_install_leftovers, cleanup_task_workspace).

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


def edit_path(ed):
    """Bir edit girdisinden yol alanini cozer.

    "path" ONCELIKLIDIR; yoksa/bossa "file" sonra "filename" denenir —
    boylece AI alternatif alan adiyla gelirse girdi kaybolmaz. Ilk turde
    (implement) ve onarim turunde (repair) AYNI cozumleme kullanilir.
    """
    if not isinstance(ed, dict):
        return ""
    for key in ("path", "file", "filename"):
        v = ed.get(key)
        if v:
            return v
    return ""


def apply_edits(worktree: Path, edits):
    """AI'nin ONERDIGI degisiklikleri BIZ uygularz. AI'nin eli klavyede degil."""
    changed = []
    for ed in edits or []:
        if not isinstance(ed, dict):
            continue
        action = (ed.get("action") or "replace").lower()
        rel = edit_path(ed)
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


def split_repair_edits(edits):
    """ONARIM TURU icin edit girdilerini ayirir.

    Yol alani (path, yoksa file/filename — bkz. edit_path) bos/eksik olan
    (ya da dict OLMAYAN) girdiler YOK SAYILIR — raise EDILMEZ; digerleri
    degismeden dondurulur. Yalnizca onarim turu (pipeline repair loop) icin
    kullanilir; ilk uygulama (implement) apply_edits'i dogrudan cagirir ve
    orada bos path halen UnsafeEdit ile REDDEDILIR.

    Donus: (gecerli_edits, yok_sayilan_sayisi)
    """
    valid, ignored = [], 0
    for ed in edits or []:
        if not isinstance(ed, dict) or not str(edit_path(ed) or "").strip():
            ignored += 1
            continue
        valid.append(ed)
    return valid, ignored


def agent_install_dir():
    """Ajanin KENDI kurulum dizini (bu paket agacinin koku: g17cloud/, guards/,
    tests/ burada yasar). AI saglayicisina cwd ya da erisim kapsami olarak
    ASLA verilmez — bkz. AIWorker.call."""
    return Path(__file__).resolve().parent.parent


# Bu isimler/onekler DISINDA HICBIR SEYE dokunulmaz. Bilerek DENYLIST degil
# ALLOWLIST: kurulum dizininde Procfile, requirements.txt, README.md gibi
# GERCEK dagitim dosyalari olabilir — yalniz KENDI gecici artik desenlerimiz
# (worktree adlandirmasi + bilinen tarama ciktilari) silinir.
_INSTALL_LEFTOVER_PREFIXES = ("wt-", "self-wt-")
_INSTALL_LEFTOVER_NAMES = {"gobek17-app.zip", "manifest.json", "backup", ".smoke-state"}


def clean_install_leftovers(root=None, log=None):
    """GOREV BASINDA HAZIRLIK: kurulum dizininde onceki turlardan (crash,
    eski surum) kalmis olabilecek BILINEN gecici artiklari siler.

    Yalnizca ust-duzey (rglob DEGIL) ve YALNIZCA _INSTALL_LEFTOVER_PREFIXES /
    _INSTALL_LEFTOVER_NAMES ile eslesen girdilere dokunur. Ajanin gercek
    kaynak agaci (g17cloud/, guards/, tests/) ve dagitim dosyalari
    (Procfile, requirements.txt, README.md, vb.) bu desenlerle ASLA
    eslesmez ve dokunulmadan kalir.
    """
    log = log or (lambda *a, **k: None)
    base = Path(root) if root is not None else agent_install_dir()
    removed = []
    if not base.is_dir():
        return removed
    for entry in sorted(base.iterdir()):
        name = entry.name
        if not (name.startswith(_INSTALL_LEFTOVER_PREFIXES) or name in _INSTALL_LEFTOVER_NAMES):
            continue
        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink()
            removed.append(name)
        except OSError:
            continue
    if removed:
        log("kurulum dizini temizlendi (artik): %s" % ", ".join(removed))
    return removed


def cleanup_task_workspace(cfg, task_id, log=None):
    """GOREV SONUNDA TEMIZLIK: o goreve ait gecici dosya/dizin ve worktree
    kaydini kaldirir. Basarili da basarisiz da bitse cagirilir.

    Yalnizca work_dir altindaki, o gorev id'sine ait BILINEN gecici yollara
    dokunur; kalici state_dir (tasks/artifacts/release.lock), git deposu ya
    da log/gorev kayitlarina KESINLIKLE DOKUNMAZ.
    """
    log = log or (lambda *a, **k: None)
    wd = Path(cfg.work_dir)
    removed = []
    for name in ("wt-%s" % task_id, "self-wt-%s" % task_id):
        p = wd / name
        if p.exists() or p.is_symlink():
            shutil.rmtree(p, ignore_errors=True)
            removed.append(str(p))
    if removed:
        log("gorev calisma alani temizlendi: %s" % ", ".join(removed))
    return removed


_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\s*\n?(.*?)```", re.S)


def _balanced_spans(text):
    """Metindeki DENGELI ust duzey {...} bloklarini bulur.

    String icindeki suslu parantezleri ve kacis dizilerini dogru atlar;
    boylece "ilk { ile son }" hatasi ortadan kalkar.
    """
    spans = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth:
                depth -= 1
                if depth == 0 and start >= 0:
                    spans.append((start, i + 1))
    return spans


def _candidates(text):
    """Denenecek metin parcalarini ONCELIK sirasiyla uretir."""
    out = []
    fences = _FENCE.findall(text or "")
    # Kod blogu varsa SONDAN basa dene: model once aciklama, sonra JSON yazar.
    for f in reversed(fences):
        out.append(f.strip())
    out.append((text or "").strip())
    return out


def parse_json_block(text, want=("edits",)):
    """AI ciktisindan yapisal JSON cikarir. ASLA eval/exec kullanilmaz.

    Strateji:
      1) kod bloklarini SONDAN basa dene (aciklama once gelir, JSON sonra)
      2) her adayda DENGELI {...} bloklarini tara, en buyugunden basla
      3) beklenen anahtari (edits) iceren ILK gecerli JSON'u dondur
      4) hicbiri olmazsa ham ciktinin ilk 800 karakterini hataya EKLE
    """
    if not text or not str(text).strip():
        raise AIError("AI bos yanit dondu")
    text = str(text)
    fallback = None

    for cand in _candidates(text):
        if not cand:
            continue
        spans = _balanced_spans(cand)
        # En buyuk blok once: ic ice objelerde dis kabugu yakalar.
        for a, b in sorted(spans, key=lambda s: s[1] - s[0], reverse=True):
            chunk = cand[a:b]
            try:
                obj = json.loads(chunk)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            if any(k in obj for k in want):
                return obj
            if fallback is None:
                fallback = obj
    if fallback is not None:
        return fallback

    raise AIError("AI JSON'u cozumlenemedi. HAM CIKTI (ilk 800): %s"
                  % text.strip()[:800])


# ---------------------------------------------------------------- saglayicilar
class BaseProvider:
    name = "base"

    def available(self):
        return False

    def run(self, system, prompt, timeout, cwd=None):
        raise NotImplementedError


class AnthropicAPIProvider(BaseProvider):
    """Fable/Opus icin HTTP API adaptoru. Cloud'da varsayilan yol budur."""

    def __init__(self, cfg, model, name):
        self.cfg = cfg
        self.model = model
        self.name = name

    def available(self):
        return bool(self.cfg.ai_key())

    def run(self, system, prompt, timeout=900, cwd=None):
        # HTTP API cagrisi: dosya sistemine hic dokunmaz, cwd bu saglayici
        # icin anlamsizdir ama arayuz tutarliligi icin kabul edilir.
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
            # Govde OLMADAN hata ayiklanamiyor; sir icermez, API'nin
            # kendi hata aciklamasidir.
            try:
                _b = ex.read().decode("utf-8", "replace")[:500]
            except Exception:
                _b = ""
            raise AIError("AI API hatasi: HTTP %s %s" % (ex.code, _b)) from None
        except (urllib.error.URLError, OSError) as ex:
            raise AIError("AI API ulasilamadi: %s" % type(ex).__name__) from None
        parts = [b.get("text", "") for b in (data.get("content") or [])
                 if b.get("type") == "text"]
        return "\n".join(parts)


def g17_resolve_tool_flags(help_text):
    """CLI help ciktisindan guvenli allow/deny bayraklarini sec (Faz 0).

    Yalnizca GERCEK option satirlari sayilir: satir basi, en cok 12
    bosluk girinti ve istege bagli kisa bayrak (-x,) sonrasi dogrudan
    --bayrak ile baslamalidir. Aciklama icinde gecen deprecated --tools
    gibi sozler capability sayilmaz.
    Oncelik: --allowedTools > --allowed-tools > --tools.
    Allow VEYA deny cozulemiyorsa fail-closed (CLI_CAPABILITY_MISMATCH).
    """
    h = help_text or ""
    declared = set(re.findall(
        r"(?m)^[ \t]{0,12}(?:-[A-Za-z][ \t]*,[ \t]*)?(--[A-Za-z][A-Za-z0-9-]*)",
        h))
    allow = next((f for f in ("--allowedTools", "--allowed-tools", "--tools")
                  if f in declared), None)
    deny = next((f for f in ("--disallowedTools", "--disallowed-tools")
                 if f in declared), None)
    if not allow or not deny:
        raise AIError(
            "CLI_CAPABILITY_MISMATCH: guvenli allow/deny arac bayraklari "
            "help option satirlarinda bulunamadi")
    return allow, deny


def g17_probe_ok(help_text):
    try:
        g17_resolve_tool_flags(help_text)
        return True
    except AIError:
        return False


class ClaudeCLIProvider(BaseProvider):
    """Claude Code CLI adaptoru — v1.2.1 politikasi korunur.

    Bayrak secimi CLI help ciktisindaki GERCEK option satirlarindan yapilir
    (g17_resolve_tool_flags); aciklama metnindeki bayrak sozleri sayilmaz.
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
        # Kimlik yoksa CLI calissa da model cagrisi yapamaz.
        # Abonelik: setup-token (env) VEYA bir kez yapilmis /login (kalici disk).
        if not (self.cfg.subscription_available() or self.cfg.ai_key()):
            return False
        h = self._help()
        return g17_probe_ok(h)

    def run(self, system, prompt, timeout=900, cwd=None):
        if not self.available():
            raise AIError("CLAUDE_PROVIDER_UNSAFE: saglayici hazir degil (CLI, kimlik veya guvenli bayrak yok)")
        if not cwd:
            # Calisma alani izolasyonu: cwd VERILMEDEN calistirilmaz. Bos
            # birakilirsa alt surec varsayilan olarak ajanin KENDI kurulum
            # dizinini gorurdu — bu asla olmamali (fail-closed).
            raise AIError("CLAUDE_PROVIDER_UNSAFE: izole worktree cwd verilmeden calistirilamaz")
        env = scrub_env(os.environ)
        # ABONELIK KIMLIGI: scrub_env altyapi sirlarini siler; model kimligini
        # burada BILEREK geri koyariz — CLI'nin tek ihtiyaci budur.
        # Deger loglanmaz, yankilanmaz, diske yazilmaz.
        # Karari config TEK yerde verir; /ready ne diyorsa cocuk sureç onu kullanir.
        # Anthropic dokumani: ANTHROPIC_API_KEY abonelige gore ONCELIKLIDIR — bu
        # yuzden abonelik modunda API anahtarini cocuga HIC gecirmeyiz, yoksa
        # sessizce API'ye dusup faturalandirirdi.
        mode = self.cfg.ai_auth_mode()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        if mode == "ANTHROPIC_API_READY" and self.cfg.ai_key():
            env["ANTHROPIC_API_KEY"] = self.cfg.ai_key()
        elif mode == "CLAUDE_SUBSCRIPTION_READY":
            tok = self.cfg.claude_oauth()
            if tok:
                env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
            # token yoksa kalici /login kimligi kullanilir (asagidaki HOME)
        # Kalici oturum: CLAUDE_CONFIG_DIR BELGELENMEMIS oldugu icin tek basina
        # guvenilmez. Belgelenmis konum ~/.claude; bu yuzden cocuga kalici bir
        # HOME veririz ve ayrica CLAUDE_CONFIG_DIR'i de set ederiz.
        home = getattr(self.cfg, "claude_home", "")
        if home:
            try:
                os.makedirs(os.path.join(home, ".claude"), mode=0o700, exist_ok=True)
                os.chmod(home, 0o700)
            except OSError:
                pass
            env["HOME"] = home
        cfgdir = getattr(self.cfg, "claude_config_dir", "")
        if cfgdir:
            try:
                os.makedirs(cfgdir, mode=0o700, exist_ok=True)
            except OSError:
                pass
            env["CLAUDE_CONFIG_DIR"] = cfgdir
        # NOT: "--bare" KULLANILMAZ. Resmi dokumana gore bare modu
        # CLAUDE_CODE_OAUTH_TOKEN'i OKUMAZ; abonelik yolu sessizce bozulurdu.
        hh = self._help()
        allow_flag, deny_flag = g17_resolve_tool_flags(hh)
        p = subprocess.run(
            [self.command, "--print", allow_flag, self.TOOLS,
             deny_flag, self.DENY, "--permission-mode", "acceptEdits",
             "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
             "--append-system-prompt", system],
            input=prompt, cwd=str(cwd), env=env,
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

    def run(self, system, prompt, timeout=60, cwd=None):
        p = subprocess.run(["/bin/sh", self.script], input=prompt,
                           cwd=str(cwd) if cwd else None,
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
    # Model kimlikleri de varsayilan olarak SILINIR. Yalnizca ClaudeCLIProvider
    # kendi cagrisinda gerekli olani bilerek geri koyar.
    "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
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
        # "auto" ve bos istek AYNI seydir: karari yapilandirmaya birak.
        # Onceki halde requested="auto" dolu sayildigi icin cfg.ai_provider
        # HIC okunmuyordu ve claude-cli (abonelik) secilemiyordu.
        req = (requested or "").strip().lower()
        if req in ("", "auto"):
            cfgp = (self.cfg.ai_provider or "auto").strip().lower()
            req = None if cfgp == "auto" else cfgp
        name = route_provider(task_text, req)
        prov = self.provider_for(name)
        if not prov.available():
            raise AIError("AI saglayici kullanilamiyor: %s" % name)
        return prov

    def call(self, provider, system, prompt, timeout=None, cwd=None):
        """Saglayiciya giden calisma dizini HER ZAMAN gorevin izole worktree'sidir.

        Ajanin kurulum dizini (agent_install_dir) hicbir kosulda buradan
        gecirilemez — cagiran cwd vermezse ya da cwd kurulum dizinine denk
        gelir/kesisirse istek fail-closed REDDEDILIR.
        """
        if not cwd:
            raise AIError("ic hata: AI saglayicisina izole worktree cwd verilmedi")
        root = Path(cwd).resolve()
        inst = agent_install_dir()
        if root == inst or inst in root.parents or root in inst.parents:
            raise AIError("guvenlik: AI calisma alani ajan kurulum dizinine denk geliyor")
        return provider.run(system, prompt, timeout or self.cfg.ai_timeout, cwd=str(root))
