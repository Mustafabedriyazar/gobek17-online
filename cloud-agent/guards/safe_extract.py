#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guvenli ZIP acici + artifact root tespiti.

Engellenen: mutlak yol, ../ path traversal, symlink kacisi, device/fifo girdisi,
.git uzerine yazma, asiri buyuk toplam boyut, asiri girdi sayisi.

Kullanim:
    safe_extract.py <zip> <hedef_dizin> [--max-mb 400] [--max-entries 20000]
Cikti: JSON {"root": "<hedef icindeki gercek proje koku>", "entries": N, "bytes": N}
Hata: exit 40 (artifact hatasi), stderr'de Turkce sebep.
"""
import json
import os
import stat
import sys
import zipfile

MARKERS = ("index.html", "package.json", "server", "bootstrap.cjs", "gobek17-app.zip", "server.cjs")
EXIT_ARTIFACT = 40


def fail(msg):
    sys.stderr.write("ZIP GUVENLIK: " + msg + "\n")
    sys.exit(EXIT_ARTIFACT)


def check_name(name):
    if not name:
        fail("bos girdi adi")
    if "\\" in name:
        fail("ters bolu iceren girdi: %s" % name)
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        fail("mutlak yol girdisi: %s" % name)
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        fail("path traversal girdisi: %s" % name)
    if parts and parts[0] == ".git":
        fail("artifact icinde .git var: %s" % name)
    if any(p == ".git" for p in parts):
        fail("artifact icinde .git var: %s" % name)
    return "/".join(parts)


def detect_root(dest):
    top = sorted(os.listdir(dest))
    if not top:
        fail("zip bos")
    here = [t for t in top if t in MARKERS]
    dirs = [t for t in top if os.path.isdir(os.path.join(dest, t))]
    files = [t for t in top if not os.path.isdir(os.path.join(dest, t))]
    if here:
        return ""
    if len(dirs) == 1 and not files:
        sub = os.path.join(dest, dirs[0])
        if any(m in os.listdir(sub) for m in MARKERS):
            return dirs[0]
        fail("tek klasor bulundu ama proje isaretleri yok: %s" % dirs[0])
    cands = [d for d in dirs if any(m in os.listdir(os.path.join(dest, d)) for m in MARKERS)]
    if len(cands) == 1:
        return cands[0]
    fail("artifact koku belirsiz (adaylar: %s)" % (", ".join(cands) or "yok"))


def main(argv):
    if len(argv) < 3:
        sys.stderr.write("kullanim: safe_extract.py <zip> <hedef> [--max-mb N] [--max-entries N]\n")
        return 2
    src, dest = argv[1], argv[2]
    max_mb, max_entries = 400, 20000
    for i, a in enumerate(argv):
        if a == "--max-mb" and i + 1 < len(argv):
            max_mb = int(argv[i + 1])
        if a == "--max-entries" and i + 1 < len(argv):
            max_entries = int(argv[i + 1])
    if not zipfile.is_zipfile(src):
        fail("gecerli bir zip degil: %s" % src)
    os.makedirs(dest, exist_ok=True)
    dest_real = os.path.realpath(dest)
    total = 0
    count = 0
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        if len(infos) > max_entries:
            fail("cok fazla girdi (%d)" % len(infos))
        for info in infos:
            rel = check_name(info.filename)
            if not rel:
                continue
            mode = (info.external_attr >> 16) & 0xFFFF
            fmt = stat.S_IFMT(mode)
            if fmt and stat.S_ISLNK(mode):
                fail("symlink girdisi: %s" % info.filename)
            if fmt and not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                fail("normal olmayan dosya girdisi: %s" % info.filename)
            total += info.file_size
            if total > max_mb * 1024 * 1024:
                fail("acilmis toplam boyut %d MB sinirini asti" % max_mb)
            target = os.path.realpath(os.path.join(dest_real, rel))
            if target != dest_real and not target.startswith(dest_real + os.sep):
                fail("hedef disina yazma denemesi: %s" % info.filename)
            if info.filename.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(info) as fin, open(target, "wb") as fout:
                while True:
                    chunk = fin.read(1 << 20)
                    if not chunk:
                        break
                    fout.write(chunk)
            count += 1
    root = detect_root(dest)
    print(json.dumps({"root": root, "entries": count, "bytes": total}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
