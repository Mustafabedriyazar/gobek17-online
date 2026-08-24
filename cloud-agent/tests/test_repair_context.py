# -*- coding: utf-8 -*-
"""FAZ B DILIM 3A: onarim promptuna GUNCEL dosya icerigi.

Onceki davranis: onarim turu promptu yalniz degisen dosyalarin AD listesini
tasiyordu ("Su ana kadarki degisiklikler: server/x.js"). AI, "old" alanini
hafizasindan uretiyor ve eslesmeyen duzenleme hatasini tekrarliyordu. Simdi
promptun {changed} yerine gecen deger, o goreve ait degisen dosyalarin
worktree'deki GUNCEL tam icerigini de tasir (pipeline.repair_file_context).
"""
import shutil
from pathlib import Path
from _util import pipeline_stub, tmpdir


def check_repair_file_context_carries_full_current_content_of_changed_file():
    from g17cloud.pipeline import Pipeline
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        (wt / "server").mkdir()
        (wt / "server" / "x.js").write_text(
            "function f() {\n  return 1;\n}\n", encoding="utf-8")
        ctx = Pipeline.repair_file_context(pipeline_stub(), wt, ["server/x.js"])
        assert "server/x.js" in ctx, ctx
        assert "function f() {\n  return 1;\n}" in ctx, "guncel icerik tam tasinmadi"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_repair_prompt_call_site_embeds_current_file_content():
    """implement/repair akisiyla AYNI cagri sekli: REPAIR_PROMPT.format(changed=...)
    artik repair_file_context ciktisini alir; sablon degismez."""
    from g17cloud.pipeline import Pipeline, REPAIR_PROMPT
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        (wt / "server").mkdir()
        (wt / "server" / "y.js").write_text("const Y = 42;\n", encoding="utf-8")
        changed_value = Pipeline.repair_file_context(pipeline_stub(), wt, ["server/y.js"])
        rp = REPAIR_PROMPT.format(attempt=1, max=3, failure="hata ciktisi",
                                  changed=changed_value, build=171)
        assert "const Y = 42;" in rp, "onarim promptu guncel icerigi tasimiyor"
        assert "server/y.js" in rp, rp
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_repair_file_context_truncates_large_file_with_head_and_tail_notice():
    from g17cloud.pipeline import Pipeline
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        lines = ["line-%d\n" % i for i in range(500)]
        (wt / "big.js").write_text("".join(lines), encoding="utf-8")
        ctx = Pipeline.repair_file_context(pipeline_stub(), wt, ["big.js"], budget=200,
                                           head_lines=5, tail_lines=5)
        assert "KIRPILDI" in ctx, "kirpma acikca belirtilmedi"
        assert "line-0" in ctx, "dosyanin ilk satiri eksik"
        assert "line-499" in ctx, "dosyanin son satiri eksik"
        assert "line-250" not in ctx, "ortadaki bolge kirpilmali"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_repair_file_context_reports_missing_file_without_crashing():
    from g17cloud.pipeline import Pipeline
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        ctx = Pipeline.repair_file_context(pipeline_stub(), wt, ["server/silindi.js"])
        assert "server/silindi.js" in ctx, ctx
        assert "dosya yok" in ctx, ctx
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_repair_file_context_uses_already_known_changed_list_no_new_tracking():
    """Dosya listesi pipeline'in zaten bildigi 'changed' kaydindan alinir —
    bos liste verilirse hicbir dosya taranmaz, yalnizca isim ozeti dondurulur."""
    from g17cloud.pipeline import Pipeline
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        ctx = Pipeline.repair_file_context(pipeline_stub(), wt, [])
        assert ctx == "(yok)", ctx
    finally:
        shutil.rmtree(d, ignore_errors=True)


# =================================================== mevcut sozlesme KORUNUR
def check_repair_prompt_still_contains_same_edit_contract_as_implement():
    from g17cloud.pipeline import REPAIR_PROMPT
    rp = REPAIR_PROMPT.format(attempt=1, max=3, failure="hata ciktisi",
                              changed="server/x.js", build=171)
    for token in ('"path"', '"action"', '"new"', '"old"', 'replace', 'create'):
        assert token in rp, "onarim promptunda edit sozlesmesi eksik: %s" % token
    assert "BOS BIRAKILAMAZ" in rp, "onarim promptunda bos path yasagi acikca yok"


def check_repair_prompt_still_accepts_path_file_filename_fields():
    from g17cloud.ai_worker import edit_path
    assert edit_path({"path": "a"}) == "a"
    assert edit_path({"file": "b"}) == "b"
    assert edit_path({"filename": "c"}) == "c"
    assert edit_path({}) == ""


def check_apply_repair_edits_empty_path_still_ignored():
    from g17cloud.pipeline import apply_repair_edits
    d = tmpdir()
    try:
        wt = Path(d) / "wt"; wt.mkdir()
        rep = {"edits": [{"path": "", "action": "create", "new": "yok sayilmali"},
                         {"path": "server/z.txt", "action": "create", "new": "z"}]}
        changed, total, this_round = apply_repair_edits(wt, rep, 1, 3, 0)
        assert changed == ["server/z.txt"], changed
        assert this_round == 1, this_round
    finally:
        shutil.rmtree(d, ignore_errors=True)
