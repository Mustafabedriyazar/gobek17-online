# -*- coding: utf-8 -*-
"""Saglayici secimi: 'otomatik' istegi AI_PROVIDER'i GERCEKTEN okumali.

21 Agustos regresyonu: konsol "auto" gonderdiginde cfg.ai_provider hic
okunmuyordu; claude-cli (Claude ABONELIGI) hicbir sekilde secilemiyor,
her gorev API'ye dusuyordu.
"""
import types

from g17cloud.ai_worker import AIWorker, MockProvider, route_provider


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
