#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent — SELF-BRICK KORUMASI (boot smoke).

Bir self-update adayi push edilmeden ONCE bu betik AYRI SURECTE kosar.
Amaci tek: "bu kod gercekten ayaga kalkiyor mu".

Sirayla:
  1) paketin tum modulleri import ediliyor mu
  2) Config yukleniyor mu, dizinler acilabiliyor mu
  3) HTTP sunucusu bos bir portta ayaga kalkiyor mu
  4) /health 200 donuyor mu
  5) /ready cevap veriyor mu (200 ya da 503 — govde okunabilir olmali)
  6) repodaki tam self-test suite PASS mi

Herhangi biri duserse SMOKE-FAIL satiri basar ve exit 1 verir.
Cikti sir icermez.
"""
import json
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent
for p in (str(AGENT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

FAILS = []


def step(name, fn):
    try:
        val = fn()
        print("SMOKE-OK  %s" % name)
        return val
    except Exception:
        FAILS.append(name)
        print("SMOKE-FAIL %s" % name)
        for ln in traceback.format_exc(limit=3).strip().splitlines()[-4:]:
            print("     " + ln)
        return None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _imports():
    import importlib
    for m in ("g17cloud.config", "g17cloud.store", "g17cloud.github_core",
              "g17cloud.release_guard", "g17cloud.production", "g17cloud.ai_worker",
              "g17cloud.pipeline", "g17cloud.api"):
        importlib.import_module(m)
    return True


def _config():
    from g17cloud.config import Config
    c = Config()
    c.ensure_dirs()
    d = c.public_dict()
    assert "version" in d and "githubTokenPresent" in d
    return c


def main():
    os.environ.setdefault("G17_DEV_MODE", "1")
    step("imports", _imports)
    cfg = step("config", _config)
    if FAILS:
        print("RESULT-SMOKE: FAIL")
        return 1

    port = free_port()
    cfg.port = port
    cfg.host = "127.0.0.1"

    from g17cloud.api import Service, make_handler
    from http.server import ThreadingHTTPServer

    httpd = [None]

    def boot():
        svc = Service(cfg)
        httpd[0] = ThreadingHTTPServer((cfg.host, cfg.port), make_handler(svc))
        t = threading.Thread(target=httpd[0].serve_forever, daemon=True)
        t.start()
        return svc

    step("api-boot", boot)
    if FAILS:
        print("RESULT-SMOKE: FAIL")
        return 1

    base = "http://127.0.0.1:%d" % port

    def get(path, expect=None):
        deadline = time.time() + 10
        last = None
        while time.time() < deadline:
            try:
                req = urllib.request.Request(base + path)
                with urllib.request.urlopen(req, timeout=3) as r:
                    body = json.loads(r.read().decode("utf-8"))
                    if expect and r.status != expect:
                        raise AssertionError("%s -> %d (beklenen %d)"
                                             % (path, r.status, expect))
                    return body
            except urllib.error.HTTPError as ex:
                body = json.loads(ex.read().decode("utf-8"))
                if expect and ex.code != expect:
                    raise AssertionError("%s -> %d (beklenen %d)" % (path, ex.code, expect))
                return body
            except Exception as ex:                       # henuz ayakta degil
                last = ex
                time.sleep(0.2)
        raise AssertionError("%s cevap vermedi: %s" % (path, last))

    def health():
        b = get("/health", expect=200)
        assert b.get("ok") is True, b
        assert b.get("version"), b
        return b

    def ready():
        # 200 (hazir) ya da 503 (kimlik yok) kabul; govde OKUNABILIR olmali.
        b = get("/ready")
        assert "ok" in b and "provider" in b, b
        return b

    step("health", health)
    step("ready", ready)

    try:
        if httpd[0]:
            httpd[0].shutdown()
            httpd[0].server_close()
    except Exception:
        pass

    def selftests():
        import subprocess
        r = subprocess.run([sys.executable, str(HERE / "run_tests.py")],
                           cwd=str(AGENT), capture_output=True, text=True, timeout=600)
        out = (r.stdout or "") + (r.stderr or "")
        for ln in out.splitlines():
            if ln.startswith("FAIL ") or ln.startswith("RESULT:"):
                print("     " + ln)
        assert r.returncode == 0, "self-test suite FAIL"
        return True

    step("selftests", selftests)

    if FAILS:
        print("RESULT-SMOKE: FAIL (%s)" % ", ".join(FAILS))
        return 1
    print("RESULT-SMOKE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
