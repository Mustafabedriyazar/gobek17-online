# -*- coding: utf-8 -*-
"""parse_json_block — 21 Agustos gecesi yasanan 4 belirtinin regresyon testi."""
from g17cloud.ai_worker import AIError, parse_json_block

GOOD = {"path": "cloud-agent/g17cloud/x.py", "new": "kod"}


def _ok(raw):
    obj = parse_json_block(raw)
    assert isinstance(obj, dict) and obj.get("edits"), obj
    assert obj["edits"][0]["path"] == GOOD["path"], obj
    return obj


def check_plain_json():
    _ok('{"rootCause":"x","edits":[%s]}' % _j(GOOD))


def check_prose_before_json_with_braces():
    """Model once aciklama yazip icinde {} kullanirsa da bulunmali."""
    _ok('Analiz: sozluk {yanlis} kullanilmis.\n'
        '{"rootCause":"x","edits":[%s]}' % _j(GOOD))


def check_prose_after_json_with_braces():
    _ok('{"rootCause":"x","edits":[%s]}\nNot: bos sozluk {} olur.' % _j(GOOD))


def check_python_fence_then_json_fence():
    """ILK blok python ise ona takilmamali; SON blok tercih edilmeli."""
    _ok('Once:\n```python\nd = {"a": 1}\n```\nSonuc:\n```json\n'
        '{"rootCause":"x","edits":[%s]}\n```' % _j(GOOD))


def check_braces_inside_string_content():
    """Dosya icerigindeki suslu parantez ve kacis dizileri kesmeyi bozmamali."""
    ed = {"path": GOOD["path"], "new": 'def f():\n    return {"k": "}"}\n'}
    obj = parse_json_block('{"rootCause":"x","edits":[%s]}' % _j(ed))
    assert '"k"' in obj["edits"][0]["new"], obj


def check_raw_output_in_error_message():
    """Cozumlenemeyen ciktida ham metin GORUNMELI — kor ucus yasak."""
    try:
        parse_json_block("Uzgunum, bu istegi yerine getiremiyorum.")
    except AIError as ex:
        assert "HAM CIKTI" in str(ex), str(ex)
        assert "Uzgunum" in str(ex), str(ex)
        return
    raise AssertionError("gecersiz cikti kabul edildi")


def check_empty_output_rejected():
    for bad in ("", "   ", None):
        try:
            parse_json_block(bad)
        except AIError:
            continue
        raise AssertionError("bos cikti kabul edildi: %r" % bad)


def _j(d):
    import json
    return json.dumps(d)
