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

    def ensure_dirs(self):
        for d in (self.state_dir, self.work_dir, self.state_dir / "tasks",
                  self.state_dir / "artifacts"):
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
            "aiKeyPresent": bool(self._ai_key),
            "models": {"fable": self.model_fable, "opus": self.model_opus},
            "maxRepairAttempts": self.max_repair,
            "strictSequentialBuilds": self.strict_sequential,
            "stateDir": str(self.state_dir),
        }
