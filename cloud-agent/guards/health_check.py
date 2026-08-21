#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Production health kontrolu / Railway deploy bekleme.

Rollout sirasinda connection refused / 502 / 503 / 504 NORMALDIR; timeout
penceresi boyunca tekrar denenir. Yalnizca BEKLENEN build damgasi gelince PASS.

Kullanim:
    health_check.py once  <url>
    health_check.py wait  <url> <beklenen-damga> [--timeout 600] [--interval 8]
Exit: 0 PASS, 90 production dogrulanamadi.
Test icin: G17_HEALTH_FAKE=<dosya> ortam degiskeni verilirse HTTP yerine o dosya okunur.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

EXIT_PROD = 90
STAMP_RE = re.compile(r"gobek17-\d{3}-[a-z0-9\-]+")


def probe(url, timeout=12):
    fake = os.environ.get("G17_HEALTH_FAKE")
    if fake:
        try:
            with open(fake, "r", encoding="utf-8") as f:
                body = f.read().strip()
        except OSError:
            return {"ok": False, "status": 0, "error": "fake yok"}
        if body in ("", "DOWN"):
            return {"ok": False, "status": 0, "error": "baglanti yok"}
        if body.startswith("HTTP:"):
            return {"ok": False, "status": int(body.split(":")[1]), "error": "gecici hata"}
        return {"ok": True, "status": 200, "body": body, "stamp": find_stamp(body)}
    req = urllib.request.Request(url, headers={"User-Agent": "g17-deploy-bot"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(65536).decode("utf-8", "replace")
            return {"ok": True, "status": r.status, "body": body, "stamp": find_stamp(body)}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": "HTTP %d" % e.code}
    except Exception as e:  # noqa: BLE001 - baglanti hatalari rollout'ta normaldir
        return {"ok": False, "status": 0, "error": str(e)[:120]}


def find_stamp(body):
    try:
        data = json.loads(body)
        if isinstance(data, dict) and isinstance(data.get("build"), str):
            return data["build"]
    except ValueError:
        pass
    m = STAMP_RE.search(body or "")
    return m.group(0) if m else None


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["once", "wait"])
    p.add_argument("url")
    p.add_argument("stamp", nargs="?", default="")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--interval", type=int, default=8)
    a = p.parse_args(argv[1:])

    if a.cmd == "once":
        r = probe(a.url)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r.get("ok") else EXIT_PROD

    deadline = time.time() + a.timeout
    last = None
    shown = set()
    while time.time() < deadline:
        r = probe(a.url)
        last = r
        if r.get("ok"):
            got = r.get("stamp") or "?"
            if not a.stamp:
                print("   ✓ Health yanit veriyor (damga: %s)" % got)
                return 0
            if got == a.stamp:
                print("   ✓ Beklenen damga geldi: %s" % got)
                return 0
            if got not in shown:
                shown.add(got)
                print("   … Railway bekleniyor — su an aktif: %s" % got)
        else:
            key = "e:%s" % r.get("status")
            if key not in shown:
                shown.add(key)
                print("   … rollout devam ediyor (%s)" % (r.get("error") or r.get("status")))
        time.sleep(max(3, a.interval))
    print("   ✗ Sure doldu. Son durum: %s" % json.dumps(last, ensure_ascii=False))
    return EXIT_PROD


if __name__ == "__main__":
    sys.exit(main(sys.argv))
