# -*- coding: utf-8 -*-
"""Gorev modu (feature|fix|chore): REPRODUCE kapisinin TEK yetki kaynagi.

mode alani yoksa varsayilan 'feature'dir. Gecersiz deger reddedilir. Gorev
metni (task text) mode kararini ETKILEMEZ — pipeline.reproduce_required
yalnizca gorev kaydindaki 'mode' alanina bakar.
"""
import tempfile
from pathlib import Path

from g17cloud.pipeline import reproduce_required
from g17cloud.store import DEFAULT_TASK_MODE, TASK_MODES, TaskStore, resolve_task_mode


def _store():
    return TaskStore(Path(tempfile.mkdtemp(prefix="g17t-mode-")))


def check_default_mode_is_feature_when_field_absent():
    rec = _store().create("v1", "herhangi bir gorev")
    assert rec["mode"] == "feature" == DEFAULT_TASK_MODE, rec["mode"]


def check_default_mode_applies_for_none_and_empty():
    for raw in (None, ""):
        assert resolve_task_mode(raw) == "feature", raw


def check_invalid_mode_is_rejected():
    for bad in ("bug", "refactor", "hotfix", "Feature!"):
        try:
            resolve_task_mode(bad)
        except ValueError:
            continue
        raise AssertionError("gecersiz mode kabul edildi: %r" % bad)


def check_all_valid_modes_accepted_case_insensitive():
    for m in TASK_MODES:
        assert resolve_task_mode(m) == m
        assert resolve_task_mode(m.upper()) == m


def check_feature_mode_skips_reproduce_gate():
    assert reproduce_required("feature") is False


def check_chore_mode_skips_reproduce_gate():
    assert reproduce_required("chore") is False


def check_fix_mode_requires_reproduce_gate():
    assert reproduce_required("fix") is True


def check_task_text_does_not_override_mode():
    store = _store()
    # Metin "fix" ipuclariyla dolu ama mode='feature' -> REPRODUCE yine atlanir.
    rec_a = store.create("v1", "kucuk bir hata duzelt, bug fix gerekiyor, root cause bul",
                         mode="feature")
    # Metin "feature" ipuclariyla dolu ama mode='fix' -> REPRODUCE yine zorunlu.
    rec_b = store.create("v1", "buyuk yeni ozellik ekle, tum sistemi yeniden yaz",
                         mode="fix")
    assert rec_a["mode"] == "feature", rec_a["mode"]
    assert rec_b["mode"] == "fix", rec_b["mode"]
    assert reproduce_required(rec_a["mode"]) is False
    assert reproduce_required(rec_b["mode"]) is True
