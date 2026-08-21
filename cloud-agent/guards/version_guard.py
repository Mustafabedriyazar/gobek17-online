#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GÖBEK17 surum tespiti ve version guard.

Yalnizca KANONIK dosyalar taranir (dokuman adlarindaki v169 gibi degerler
yanlis pozitif uretmesin diye):

    package.json              -> "version": "1.71.0"
    server/package.json       -> "version": "1.71.0"
    sw.js                     -> var C="gobek17-171-..."
    server/server.cjs         -> build:'gobek17-171-...'
    index.html                -> var BUILD="gobek17-171-..."
    gobek17-app.zip           -> icindeki ayni dosyalar (acmadan)

Kullanim:
    version_guard.py detect <dizin>              -> JSON
    version_guard.py verify <dizin> <171>        -> exit 0 / 50
    version_guard.py stamp  <dizin>              -> health stamp (bulunursa)
"""
import io
import json
import os
import re
import sys
import zipfile

EXIT_VERSION = 50
STAMP_RE = re.compile(rb"gobek17-(\d{3})-([a-z0-9\-]+)")
PKG_RE = re.compile(rb'"version"\s*:\s*"(\d+)\.(\d+)\.(\d+)"')
CANON = ("package.json", "server/package.json", "sw.js", "server/server.cjs",
         "index.html", "multiplayer-client.js", "multiplayer-bridge.js")


def read_bytes(root, rel, limit=None):
    p = os.path.join(root, rel.replace("/", os.sep))
    try:
        with open(p, "rb") as f:
            return f.read() if limit is None else f.read(limit)
    except OSError:
        return None


def scan_blob(blob, source, out):
    if blob is None:
        return
    for m in STAMP_RE.finditer(blob):
        num = int(m.group(1))
        stamp = m.group(0).decode("ascii", "replace")
        out["stamps"].setdefault(stamp, []).append(source)
        out["versions"].setdefault(num, []).append(source + ":stamp")
    if source.endswith("package.json"):
        m = PKG_RE.search(blob)
        if m:
            major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
            out["packageVersions"][source] = "%d.%d.%d" % (major, minor, patch)
            num = (100 + minor) if minor < 100 else minor
            if major == 1:
                out["versions"].setdefault(num, []).append(source + ":pkg")


def detect(root):
    out = {"root": root, "versions": {}, "stamps": {}, "packageVersions": {}, "appZip": False}
    for rel in CANON:
        scan_blob(read_bytes(root, rel), rel, out)
    app = os.path.join(root, "gobek17-app.zip")
    if os.path.isfile(app):
        out["appZip"] = True
        try:
            with zipfile.ZipFile(app) as z:
                names = set(z.namelist())
                for rel in CANON:
                    if rel in names:
                        with z.open(rel) as f:
                            scan_blob(f.read(), "app.zip:" + rel, out)
        except zipfile.BadZipFile:
            out["appZipError"] = "bozuk gobek17-app.zip"
    nums = sorted(out["versions"].keys())
    out["version"] = nums[0] if len(nums) == 1 else None
    out["mixed"] = nums if len(nums) > 1 else []
    out["strong"] = bool(out["stamps"]) or bool(out["packageVersions"])
    best = None
    for stamp, sources in out["stamps"].items():
        rank = 0
        for s in sources:
            if s.endswith("server/server.cjs"):
                rank = 3
            elif s.endswith("sw.js") and rank < 2:
                rank = 2
            elif rank < 1:
                rank = 1
        if best is None or rank > best[0]:
            best = (rank, stamp)
    out["healthStamp"] = best[1] if best else None
    return out


# ---------------------------------------------------------------------------
# BUG-1 duzeltmesi: build numarasi -> semver. TEK guvenilir kaynak burasi.
#   v169 -> 1.69.0   v170 -> 1.70.0   v171 -> 1.71.0   v172 -> 1.72.0
#   v200 -> 2.0.0    v271 -> 2.71.0
# Artifact kendi package.json surumunu tasiyorsa O otoritedir (tahmin yok).
# ---------------------------------------------------------------------------
def build_to_semver(build):
    n = int(build)
    if n < 0:
        raise ValueError("negatif build")
    return "%d.%d.0" % (n // 100, n % 100)


def semver_for(build, root=None):
    """Once artifact package.json, yoksa kanonik kural."""
    want = build_to_semver(build)
    if root:
        for rel in ("package.json", "server/package.json"):
            p = os.path.join(root, rel)
            if os.path.isfile(p):
                try:
                    txt = open(p, encoding="utf-8", errors="replace").read(65536)
                except OSError:
                    continue
                m = re.search(r'"version"\s*:\s*"(\d+\.\d+\.\d+)"', txt)
                if m:
                    v = m.group(1)
                    # yalnizca hedef build ile TUTARLI ise kabul et
                    if v == want or int(v.split(".")[1]) == n_minor(build):
                        return v
    return want


def n_minor(build):
    return int(build) % 100


def cmd_semver(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="version_guard semver")
    ap.add_argument("--build", required=True, type=int)
    ap.add_argument("--root", default=None)
    a = ap.parse_args(argv)
    print(semver_for(a.build, a.root))
    return 0


def main(argv):
    if len(argv) > 1 and argv[1] == "semver":
        return cmd_semver(argv[2:])

    if len(argv) < 3:
        sys.stderr.write("kullanim: version_guard.py detect|verify|stamp <dizin> [surum]\n")
        return 2
    cmd, root = argv[1], argv[2]
    info = detect(root)
    if cmd == "detect":
        print(json.dumps(info, ensure_ascii=False))
        return 0
    if cmd == "stamp":
        print(info["healthStamp"] or "")
        return 0
    if cmd == "verify":
        if len(argv) < 4:
            sys.stderr.write("verify icin beklenen surum gerekli\n")
            return 2
        want = int(argv[3])
        if not info["strong"]:
            sys.stderr.write("SURUM: pakette kanonik surum gostergesi yok (package.json / build damgasi)\n")
            return EXIT_VERSION
        if info["mixed"]:
            sys.stderr.write("SURUM: pakette KARISIK surum damgalari var: %s\n"
                             % ", ".join("v%d" % n for n in info["mixed"]))
            return EXIT_VERSION
        if info["version"] != want:
            sys.stderr.write("SURUM: paket v%s, istenen v%d\n"
                             % (info["version"] if info["version"] else "?", want))
            return EXIT_VERSION
        print(json.dumps(info, ensure_ascii=False))
        return 0
    sys.stderr.write("bilinmeyen komut: %s\n" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
