#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent — kendi test kosucusu (stdlib, bagimlilik yok).

Kullanim:
    python3 cloud-agent/tests/run_tests.py            # hepsi
    python3 cloud-agent/tests/run_tests.py test_appzip  # tek dosya

Cikti son satiri release_guard tarafindan okunur:
    RESULT: <pass> PASS / <fail> FAIL
FAIL varsa exit 1 ve HER basarisiz kontrol icin tam ad + hata satiri yazilir.
"""
import importlib.util
import io
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent
for p in (str(AGENT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv):
    only = set(a for a in argv[1:] if not a.startswith("-"))
    files = sorted(HERE.glob("test_*.py"))
    if only:
        files = [f for f in files if f.stem in only or f.name in only]
    if not files:
        sys.stderr.write("TEST: test_*.py bulunamadi (%s)\n" % HERE)
        return 2

    passed, failed = 0, []
    for f in files:
        try:
            mod = load(f)
        except Exception:
            failed.append(("%s::<import>" % f.stem, traceback.format_exc(limit=4)))
            continue
        checks = sorted(n for n in dir(mod) if n.startswith("check_"))
        for name in checks:
            full = "%s::%s" % (f.stem, name)
            buf = io.StringIO()
            old = sys.stdout
            try:
                sys.stdout = buf
                getattr(mod, name)()
                passed += 1
            except Exception:
                failed.append((full, traceback.format_exc(limit=4) +
                               ("\n--- stdout ---\n" + buf.getvalue() if buf.getvalue() else "")))
            finally:
                sys.stdout = old

    for full, tb in failed:
        print("FAIL %s" % full)
        for line in tb.strip().splitlines()[-6:]:
            print("     " + line)
    print("RESULT: %d PASS / %d FAIL" % (passed, len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
