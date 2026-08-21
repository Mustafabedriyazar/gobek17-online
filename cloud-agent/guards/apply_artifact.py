#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Artifact'i repoya GUVENLI uygular. Kor unzip yok, rm -rf yok.

Her yazilan dosyanin oncesi backup dizinine alinir ve manifest'e islenir;
herhangi bir guard/test FAIL olursa `restore` ile calisma agaci bit-bit
eski haline dondurulur.

Modlar:
  bootstrap : repo kokunde bootstrap.cjs + gobek17-app.zip + package.json varsa.
              Yalnizca bu 3 dosya guncellenir (kanonik Railway modeli).
  direct    : repo kokunde dogrudan proje dosyalari varsa.
  auto      : yukaridakini repo icerigine bakarak secer. IKI YONTEM KARISTIRILMAZ.

Kullanim:
  apply_artifact.py apply --src DIR --dest REPO --backup DIR --manifest F
                          [--mode auto|direct|bootstrap] [--version 1.71.0]
  apply_artifact.py restore --manifest F
  apply_artifact.py appzip --src DIR --out FILE
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

EXIT_ARTIFACT = 40
PROTECTED_DIRS = {".git", "node_modules", ".cache", ".g17-state", ".gobek17-app", "logs", "tmp"}
PROTECTED_FILES = {"g17.conf", ".env"}
PROTECTED_PATTERNS = (
    re.compile(r"^\.env(\..*)?$"),
    re.compile(r".*\.(log|pem|key|p12|keystore)$"),
    re.compile(r"^(credentials|secrets?)([._-].*)?$"),
)
ZIP_SKIP_ROOT = {"bootstrap.cjs", "gobek17-app.zip"}
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
VERSION_RE = re.compile(r'("version"\s*:\s*")\d+\.\d+\.\d+(")')


def fail(msg, code=EXIT_ARTIFACT):
    sys.stderr.write("APPLY: " + msg + "\n")
    sys.exit(code)


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_protected(rel):
    parts = rel.split("/")
    if parts[0] in PROTECTED_DIRS or any(p in PROTECTED_DIRS for p in parts):
        return True
    base = parts[-1]
    if base in PROTECTED_FILES:
        return True
    return any(p.match(base) for p in PROTECTED_PATTERNS)


def walk_rel(root, skip_root=()):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in sorted(dirnames) if d not in PROTECTED_DIRS]
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        for name in sorted(filenames):
            rel = name if not rel_dir else rel_dir + "/" + name
            if not rel_dir and name in skip_root:
                continue
            if is_protected(rel):
                continue
            yield rel


def make_app_zip(src, out):
    """Deterministik app zip: ayni artifact -> ayni bayt -> duplicate commit yok."""
    if (not os.path.isfile(os.path.join(src, "server.cjs"))
            and not os.path.isfile(os.path.join(src, "server", "server.cjs"))
            and os.path.isdir(os.path.join(src, "app"))):
        src = os.path.join(src, "app")  # APP DUZENI
    files = sorted(walk_rel(src, skip_root=ZIP_SKIP_ROOT))
    _e = next((c for c in ("server.cjs","server/server.cjs") if c in files), None)
    if _e is None:
        fail("app zip kokunde server.cjs yok — bootstrap bu dosyayi calistiriyor")
    tmp = out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            info = zipfile.ZipInfo(rel, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16  # S_IFREG | 0644 — tip bitleri sart
            info.create_system = 3
            with open(os.path.join(src, rel.replace("/", os.sep)), "rb") as f:
                z.writestr(info, f.read())
    os.replace(tmp, out)
    return {"files": len(files), "bytes": os.path.getsize(out), "sha256": sha_file(out)}


def detect_mode(dest):
    root = set(os.listdir(dest)) if os.path.isdir(dest) else set()
    boot = "bootstrap.cjs" in root and "gobek17-app.zip" in root
    direct = "index.html" in root or "server" in root
    if boot and direct:
        fail("repo kokunde HEM bootstrap HEM dogrudan duzen var — iki yontem karistirilmis, elle duzeltilmeli")
    if boot:
        return "bootstrap"
    if direct:
        return "direct"
    fail("repo duzeni taninmadi (bootstrap.cjs+gobek17-app.zip veya index.html/server bekleniyor)")


class Applier(object):
    def __init__(self, dest, backup, manifest_path, mode):
        self.dest = dest
        self.backup = backup
        self.manifest_path = manifest_path
        self.entries = []
        self.mode = mode
        os.makedirs(backup, exist_ok=True)

    def write(self, rel, data):
        target = os.path.join(self.dest, rel.replace("/", os.sep))
        before = None
        action = "add"
        if os.path.exists(target):
            before = sha_file(target)
            after = hashlib.sha256(data).hexdigest()
            if before == after:
                self.entries.append({"path": rel, "action": "same", "backup": None,
                                     "sha_before": before, "sha_after": after})
                return False
            action = "modify"
            bpath = os.path.join(self.backup, rel.replace("/", "__"))
            shutil.copy2(target, bpath)
        else:
            bpath = None
        os.makedirs(os.path.dirname(target) or self.dest, exist_ok=True)
        tmp = target + ".g17tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
        self.entries.append({"path": rel, "action": action,
                             "backup": os.path.basename(bpath) if bpath else None,
                             "sha_before": before, "sha_after": sha_file(target)})
        return True

    def write_file(self, rel, src_path):
        with open(src_path, "rb") as f:
            return self.write(rel, f.read())

    def save(self, extra):
        data = {"dest": self.dest, "backup": self.backup, "mode": self.mode,
                "entries": self.entries}
        data.update(extra or {})
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        return data


def do_apply(args):
    src, dest = os.path.abspath(args.src), os.path.abspath(args.dest)
    if not os.path.isdir(src):
        fail("kaynak dizin yok: %s" % src)
    if not os.path.isdir(dest):
        fail("repo dizini yok: %s" % dest)
    mode = args.mode if args.mode != "auto" else detect_mode(dest)
    ap = Applier(dest, os.path.abspath(args.backup), os.path.abspath(args.manifest), mode)
    extra = {"mode": mode}

    if mode == "bootstrap":
        ready = os.path.join(src, "gobek17-app.zip")
        if os.path.isfile(ready):
            extra["appZip"] = {"source": "artifact", "sha256": sha_file(ready),
                               "bytes": os.path.getsize(ready)}
            with open(ready, "rb") as f:
                ap.write("gobek17-app.zip", f.read())
        else:
            built = os.path.join(args.backup, "built-app.zip")
            info = make_app_zip(src, built)
            info["source"] = "built"
            extra["appZip"] = info
            with open(built, "rb") as f:
                ap.write("gobek17-app.zip", f.read())
        boot = os.path.join(src, "bootstrap.cjs")
        if os.path.isfile(boot):
            ap.write_file("bootstrap.cjs", boot)
        pkg = os.path.join(dest, "package.json")
        if args.version and os.path.isfile(pkg):
            with open(pkg, "rb") as f:
                raw = f.read().decode("utf-8")
            new, n = VERSION_RE.subn(r'\g<1>%s\g<2>' % args.version, raw, count=1)
            if n == 0:
                fail("repo package.json icinde version alani bulunamadi")
            ap.write("package.json", new.encode("utf-8"))
        appsrc = os.path.join(src, "app")  # APP AGACI SENKRONU
        if os.path.isdir(appsrc):
            n=0
            for rel in walk_rel(appsrc):
                if ap.write_file("app/"+rel, os.path.join(appsrc, rel.replace("/", os.sep))): n+=1
            extra["appTree"]={"synced":n}
    else:
        touched = 0
        for rel in walk_rel(src):
            if ap.write_file(rel, os.path.join(src, rel.replace("/", os.sep))):
                touched += 1
        stale = []
        for rel in walk_rel(dest):
            if not os.path.exists(os.path.join(src, rel.replace("/", os.sep))):
                stale.append(rel)
        extra["stale"] = stale[:200]
        extra["staleCount"] = len(stale)
        extra["touched"] = touched

    data = ap.save(extra)
    changed = [e for e in data["entries"] if e["action"] != "same"]
    print(json.dumps({"mode": mode, "changed": len(changed), "total": len(data["entries"]),
                      "appZip": extra.get("appZip"), "staleCount": extra.get("staleCount", 0),
                      "paths": [e["path"] for e in changed][:20]}, ensure_ascii=False))
    return 0


def do_restore(args):
    with open(args.manifest, encoding="utf-8") as f:
        data = json.load(f)
    dest, backup = data["dest"], data["backup"]
    undone = 0
    for e in reversed(data["entries"]):
        target = os.path.join(dest, e["path"].replace("/", os.sep))
        if e["action"] == "add":
            if os.path.exists(target):
                os.remove(target)
                undone += 1
        elif e["action"] == "modify" and e["backup"]:
            src = os.path.join(backup, e["backup"])
            if os.path.exists(src):
                shutil.copy2(src, target)
                undone += 1
    print(json.dumps({"restored": undone}, ensure_ascii=False))
    return 0


def do_appzip(args):
    print(json.dumps(make_app_zip(os.path.abspath(args.src), os.path.abspath(args.out)),
                     ensure_ascii=False))
    return 0


def main(argv):
    p = argparse.ArgumentParser(add_help=True)
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("apply")
    a.add_argument("--src", required=True)
    a.add_argument("--dest", required=True)
    a.add_argument("--backup", required=True)
    a.add_argument("--manifest", required=True)
    a.add_argument("--mode", default="auto", choices=["auto", "direct", "bootstrap"])
    a.add_argument("--version", default="")
    r = sub.add_parser("restore")
    r.add_argument("--manifest", required=True)
    z = sub.add_parser("appzip")
    z.add_argument("--src", required=True)
    z.add_argument("--out", required=True)
    args = p.parse_args(argv[1:])
    if args.cmd == "apply":
        return do_apply(args)
    if args.cmd == "restore":
        return do_restore(args)
    if args.cmd == "appzip":
        return do_appzip(args)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
