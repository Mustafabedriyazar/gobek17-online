#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — yapilandirma.

TELEFON YOK: burada Termux, Android storage veya yerel Downloads klasoru kavrami
YOKTUR. Her sey ortam degiskenleriyle gelir; servis uzun calisan bir container'dir.
"""
import os
from pathlib import Path

VERSION = "2.0.0"
NAME = "G17 Cloud Agent"


def _b(key, default=False):
    v = os.environ.get(key)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _i(key, default):
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


class Config:
    def __init__(self, env=None):
        e = env or os.environ

        # --- durum (kalici disk) -------------------------------------------
        self.state_dir = Path(e.get("G17_STATE_DIR", "/data/g17")).resolve()
        self.work_dir = Path(e.get("G17_WORK_DIR", str(self.state_dir / "work"))).resolve()
        self.repo_dir = self.work_dir / "repo"

        # --- GitHub ---------------------------------------------------------
        self.repo = e.get("G17_REPO", "")                    # owner/repo
        self.branch = e.get("G17_BRANCH", "main")
        self.gh_auth_mode = e.get("GITHUB_AUTH_MODE", "auto")  # auto|app|token|git
        self.gh_app_id = e.get("GITHUB_APP_ID", "")
        self.gh_app_install = e.get("GITHUB_APP_INSTALLATION_ID", "")
        self.gh_app_key_file = e.get("GITHUB_APP_PRIVATE_KEY_FILE", "")
        # Token YALNIZ bellekte tutulur; diske yazilmaz, loglanmaz.
        self._gh_token = e.get("GITHUB_TOKEN") or e.get("GH_TOKEN") or ""

        # --- production ------------------------------------------------------
        self.prod_base = e.get(
            "G17_PROD_BASE", "https://gobekliokey-production.up.railway.app"
        ).rstrip("/")
        self.health_url = e.get("G17_HEALTH_URL") or (self.prod_base + "/health/live")
        self.health_timeout = _i("RAILWAY_WAIT_SECONDS", 600)
        self.health_interval = _i("HEALTH_POLL_SECONDS", 8)

        # --- AI ---------------------------------------------------------------
        self.ai_provider = e.get("AI_PROVIDER", "auto")   # auto|fable|opus|claude-cli|mock
        self.ai_api_base = e.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self._ai_key = e.get("ANTHROPIC_API_KEY", "")
        # v2.1 — ABONELIK KIMLIGI (API key ZORUNLU DEGIL).
        # Resmi akis: kullanici tarayicisi olan bir makinede bir kez
        #   claude setup-token
        # calistirir; komut bir YILLIK token basar (hicbir yere kaydetmez) ve
        # bu token CLAUDE_CODE_OAUTH_TOKEN olarak verilir. Token Pro/Max/Team
        # aboneligiyle dogrular. Kendi OAuth istemcimizi YAZMIYORUZ.
        self._claude_oauth = e.get("CLAUDE_CODE_OAUTH_TOKEN", "")
        # Claude CLI yapilandirma dizini kalici diskte tutulur ki restart/deploy
        # sonrasi onboarding sihirbazi ve yerel ayarlar kaybolmasin.
        self.claude_config_dir = e.get("CLAUDE_CONFIG_DIR", str(self.state_dir / "claude"))
        # CLAUDE_CONFIG_DIR Anthropic tarafindan BELGELENMEMISTIR (github issue 33430
        # "not planned" ile kapandi). Belgelenmis konum ~/.claude oldugu icin cocuk
        # surece ayrica kalici bir HOME veririz; boylece oturum volume'da yasar.
        self.claude_home = e.get("G17_CLAUDE_HOME", str(self.state_dir / "claude-home"))
        # auto | subscription | api  — hangi kimligin oncelikli oldugunu belirler.
        self.ai_auth_pref = (e.get("AI_AUTH_PREFERENCE", "auto") or "auto").lower()
        self.model_fable = e.get("G17_MODEL_FABLE", "claude-fable-5")
        self.model_opus = e.get("G17_MODEL_OPUS", "claude-opus-5")
        self.ai_timeout = _i("AI_TIMEOUT_SECONDS", 900)
        self.max_repair = _i("MAX_AGENT_REPAIR_ATTEMPTS", 3)

        # --- politika -----------------------------------------------------------
        self.strict_sequential = _b("STRICT_SEQUENTIAL_BUILDS", True)
        self.engine_guard = e.get("ENGINE_GUARD", "strict")
        self.test_timeout = _i("TEST_TIMEOUT_SECONDS", 300)
        self.auto_deploy = _b("AGENT_AUTO_DEPLOY", True)
        self.max_new_file_mb = _i("MAX_NEW_FILE_MB", 50)

        # --- API ----------------------------------------------------------------
        self.port = _i("PORT", 8080)
        self.host = e.get("G17_BIND", "0.0.0.0")
        self.api_token = e.get("G17_API_TOKEN", "")
        self.dev_mode = _b("G17_DEV_MODE", False)

        self.guards_dir = Path(__file__).resolve().parent.parent / "guards"

    # Token erisimi TEK NOKTADAN. AI tarafina asla verilmez (bkz. ai_worker).
    def github_token(self):
        return self._gh_token

    def set_github_token(self, tok):
        self._gh_token = tok or ""

    def ai_key(self):
        return self._ai_key


    def claude_oauth(self):
        """Abonelik token'i. DEGERI HICBIR YERDE LOGLANMAZ."""
        return self._claude_oauth

    def claude_credentials_on_disk(self):
        """Bir kez yapilan 'claude /login' sonrasi olusan kimlik dosyasi var mi.
        SADECE VARLIK bakilir; icerik OKUNMAZ, loglanmaz, doner degere girmez."""
        import os as _os
        for base in (self.claude_home, self.claude_config_dir):
            if not base:
                continue
            for rel in (".claude/.credentials.json", ".credentials.json",
                        ".claude/.claude.json", ".claude.json"):
                try:
                    pth = _os.path.join(base, rel)
                    if _os.path.isfile(pth) and _os.path.getsize(pth) > 2:
                        return True
                except OSError:
                    pass
        return False

    def subscription_available(self):
        return bool(self._claude_oauth) or self.claude_credentials_on_disk()

    def ai_auth_mode(self):
        """/ready icin saglayici durumu.
        CLAUDE_SUBSCRIPTION_READY-> abonelik (setup-token veya kalici /login)
        ANTHROPIC_API_READY      -> API anahtari (ISTEGE BAGLI yol)
        AI_UNAUTHENTICATED       -> ikisi de yok; agent gorev ALMAZ.

        Anthropic dokumani: ANTHROPIC_API_KEY varsa abonelige gore ONCELIKLIDIR.
        Bu yuzden ikisi de varken hangisinin kullanildigini burada TEK yerden
        belirleriz ve ai_worker ayni karari uygular (rapor ile gercek ayrilmaz).
        """
        sub, key = self.subscription_available(), bool(self._ai_key)
        pref = self.ai_auth_pref
        if pref == "subscription" and sub:
            return "CLAUDE_SUBSCRIPTION_READY"
        if pref == "api" and key:
            return "ANTHROPIC_API_READY"
        if key:
            return "ANTHROPIC_API_READY"
        if sub:
            return "CLAUDE_SUBSCRIPTION_READY"
        return "AI_UNAUTHENTICATED"

    def ensure_dirs(self):
        for d in (self.state_dir, self.work_dir, self.state_dir / "tasks",
                  self.state_dir / "artifacts",
                  Path(self.claude_home), Path(self.claude_config_dir)):
            d.mkdir(parents=True, exist_ok=True)

    def public_dict(self):
        """Durum uclarinda gosterilen guvenli ozet — SIR ICERMEZ."""
        return {
            "name": NAME,
            "version": VERSION,
            "repo": self.repo,
            "branch": self.branch,
            "githubAuthMode": self.gh_auth_mode,
            "githubTokenPresent": bool(self._gh_token or self.gh_app_id),
            "prodBase": self.prod_base,
            "healthUrl": self.health_url,
            "aiProvider": self.ai_provider,
            "aiAuth": self.ai_auth_mode(),
            "aiKeyPresent": bool(self._ai_key),
            "subscriptionPresent": self.subscription_available(),
            "claudeHome": self.claude_home,
            "models": {"fable": self.model_fable, "opus": self.model_opus},
            "maxRepairAttempts": self.max_repair,
            "strictSequentialBuilds": self.strict_sequential,
            "stateDir": str(self.state_dir),
        }
