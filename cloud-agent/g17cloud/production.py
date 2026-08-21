#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — Production Controller.

Railway'de MANUEL Deploy butonuna basilmaz: GitHub main'e push edildiginde
Railway kendi otomatik deploy'unu yapar. Bizim isimiz BEKLEMEK ve DOGRULAMAK.

KURAL: beklenen build damgasi /health/live'da GORULMEDEN asla SUCCESS denmez.
Eski damga gorunuyorsa bu FAIL degil, "hala bekleniyor" demektir.
Gecici 5xx / baglanti hatalari da timeout penceresi boyunca tolere edilir.
"""
import json
import re
import time
import urllib.error
import urllib.request

STAMP_RX = re.compile(r"gobek17-\d{2,4}-[a-z0-9-]+", re.I)


def fetch_build(url, timeout=12, opener=None):
    """Health uctan build damgasini okur. (damga, ham_durum) doner."""
    try:
        if opener:
            body = opener(url)
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "g17-cloud-agent"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as ex:
        return None, "http-%s" % ex.code
    except (urllib.error.URLError, OSError) as ex:
        return None, type(ex).__name__
    try:
        data = json.loads(body)
        if isinstance(data, dict) and data.get("build"):
            return str(data["build"]), "ok"
    except ValueError:
        pass
    m = STAMP_RX.search(body or "")
    return (m.group(0) if m else None), "ok"


class ProductionController:
    def __init__(self, cfg, log=None):
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)

    def current_build(self, opener=None):
        return fetch_build(self.cfg.health_url, opener=opener)[0]

    def wait_for(self, expected_stamp, timeout=None, interval=None,
                 sleep=time.sleep, opener=None, on_poll=None):
        """Beklenen damga gelene kadar bekler.

        Doner: {"result": PASS|TIMEOUT, "seen": <son gorulen>, "waited": sn}
        """
        timeout = self.cfg.health_timeout if timeout is None else timeout
        interval = self.cfg.health_interval if interval is None else interval
        waited, seen, last_state = 0, None, "?"
        while waited <= timeout:
            seen, last_state = fetch_build(self.cfg.health_url, opener=opener)
            if on_poll:
                on_poll(seen, last_state, waited)
            if seen and expected_stamp and seen == expected_stamp:
                return {"result": "PASS", "seen": seen, "waited": waited}
            sleep(interval)
            waited += interval
        return {"result": "TIMEOUT", "seen": seen, "state": last_state, "waited": waited}

    def smoke(self, opener=None):
        """Yikici OLMAYAN production kontrolu. Kullanici verisine DOKUNMAZ."""
        checks = []
        stamp, state = fetch_build(self.cfg.health_url, opener=opener)
        checks.append({"check": "health/live", "ok": bool(stamp), "detail": stamp or state})
        return {"ok": all(c["ok"] for c in checks), "checks": checks}
