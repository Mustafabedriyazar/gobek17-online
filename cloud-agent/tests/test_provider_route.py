# -*- coding: utf-8 -*-
"""Saglayici secimi: 'otomatik' istegi AI_PROVIDER'i GERCEKTEN okumali.

21 Agustos regresyonu: konsol "auto" gonderdiginde cfg.ai_provider hic
okunmuyordu; claude-cli (Claude ABONELIGI) hicbir sekilde secilemiyor,
her gorev API'ye dusuyordu.
"""
import shutil
import tempfile
import types
from pathlib import Path

from g17cloud.ai_worker import AIError, AIWorker, MockProvider, agent_install_dir, route_provider


class _P:
    def __init__(self, name, ok=True):
        self.name, self._ok = name, ok

    def available(self):
        return self._ok


def _worker(ai_provider="auto"):
    cfg = types.SimpleNamespace(ai_provider=ai_provider, ai_timeout=60)
    w = AIWorker(cfg)
    seen = {}

    def provider_for(name):
        seen["name"] = name
        return _P(name)

    w.provider_for = provider_for
    w._seen = seen
    return w


def check_auto_request_honours_configured_provider():
    w = _worker("claude-cli")
    w.select("kucuk bir duzeltme", requested="auto")
    assert w._seen["name"] == "claude-cli", w._seen


def check_empty_request_honours_configured_provider():
    for req in (None, "", "  "):
        w = _worker("claude-cli")
        w.select("kucuk bir duzeltme", requested=req)
        assert w._seen["name"] == "claude-cli", (req, w._seen)


def check_explicit_request_still_wins():
    w = _worker("claude-cli")
    w.select("kucuk bir duzeltme", requested="opus")
    assert w._seen["name"] == "opus", w._seen


def check_auto_config_falls_back_to_heuristic():
    w = _worker("auto")
    w.select("kucuk cerrahi duzeltme", requested="auto")
    assert w._seen["name"] in ("opus", "fable"), w._seen


def check_mock_short_circuits():
    w = _worker("claude-cli")
    assert isinstance(w.select("x", requested="mock"), MockProvider)


def check_route_provider_unchanged_for_explicit():
    assert route_provider("x", "claude-cli") == "claude-cli"
    assert route_provider("x", "fable") == "fable"


# --------------------------------------------------------- calisma alani izolasyonu
class _RecordingProvider:
    """AIWorker.call'un saglayiciya GERCEKTEN hangi cwd'yi verdigini kaydeder."""

    def __init__(self):
        self.calls = []

    def run(self, system, prompt, timeout, cwd=None):
        self.calls.append(cwd)
        return "{}"


def _call_worker():
    return AIWorker(types.SimpleNamespace(ai_provider="mock", ai_timeout=30))


def check_call_requires_isolated_worktree_cwd():
    w, prov = _call_worker(), _RecordingProvider()
    try:
        w.call(prov, "sys", "prompt")
        raise AssertionError("cwd verilmeden cagri kabul edildi")
    except AIError:
        pass
    assert prov.calls == [], "cwd yokken saglayici hic cagrilmamali: %s" % prov.calls


def check_call_rejects_agent_install_dir_as_cwd():
    w, prov = _call_worker(), _RecordingProvider()
    try:
        w.call(prov, "sys", "prompt", cwd=agent_install_dir())
        raise AssertionError("ajan kurulum dizini cwd olarak kabul edildi")
    except AIError:
        pass
    assert prov.calls == [], "kurulum dizini verildiginde saglayici cagrilmamali"


def check_call_passes_isolated_worktree_cwd_to_provider():
    tmp = tempfile.mkdtemp(prefix="g17wt-")
    try:
        w, prov = _call_worker(), _RecordingProvider()
        w.call(prov, "sys", "prompt", cwd=tmp)
        assert prov.calls == [str(Path(tmp).resolve())], prov.calls
        assert prov.calls[0] != str(agent_install_dir()), "worktree kurulum dizinine denk geldi"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
