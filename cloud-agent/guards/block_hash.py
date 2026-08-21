#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GÖBEK17 kanonik blok hash aracı.

Engine ve strategic-bot bloklarının SHA-256'sını hesaplar. Blok sınırları
TAHMİN EDİLMEZ; index.html icindeki kanonik isaretler kullanilir:

    ENGINE : /*OKEY17-BAS*/    ... /*OKEY17-SON*/
    BOT    : /*OKEY17BOT-BAS   ... /*OKEY17BOT-SON*/

Ayrica sunucu tarafi kopyalari (server/engine-factory.cjs, server/bot-factory.cjs)
dosya butunu olarak hashlenir.

Kullanim:
    block_hash.py <dizin>          -> JSON
Isaret bulunamazsa ilgili alan null doner (ABORT karari cagirana aittir).
"""
import hashlib
import json
import os
import re
import sys

ENGINE_START = b"/*OKEY17-BAS*/"
ENGINE_END = b"/*OKEY17-SON*/"
BOT_START = b"/*OKEY17BOT-BAS"
BOT_END = b"/*OKEY17BOT-SON*/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def slice_block(blob, start_marker, end_marker):
    i = blob.find(start_marker)
    if i < 0:
        return None, "start_marker_missing"
    j = blob.find(end_marker, i)
    if j < 0:
        return None, "end_marker_missing"
    if blob.find(start_marker, i + 1) >= 0:
        return None, "start_marker_duplicated"
    return blob[i:j + len(end_marker)], None


def read(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def collect(root):
    out = {"root": root, "blocks": {}, "files": {}, "errors": []}
    index = os.path.join(root, "index.html")
    blob = read(index)
    if blob is None:
        out["errors"].append("index.html yok")
    else:
        for name, (s, e) in (("engine", (ENGINE_START, ENGINE_END)),
                             ("bot", (BOT_START, BOT_END))):
            block, err = slice_block(blob, s, e)
            if block is None:
                out["blocks"][name] = None
                out["errors"].append("index.html %s blogu: %s" % (name, err))
            else:
                out["blocks"][name] = {"sha256": sha(block), "bytes": len(block)}
    for name, rel in (("engine_factory", os.path.join("server", "engine-factory.cjs")),
                      ("bot_factory", os.path.join("server", "bot-factory.cjs"))):
        data = read(os.path.join(root, rel))
        out["files"][name] = None if data is None else {"sha256": sha(data), "bytes": len(data)}
    return out


def compare(a, b):
    """a=eski, b=yeni -> degisen kanonik blok adlari."""
    changed = []
    for key in ("engine", "bot"):
        x = (a.get("blocks", {}) or {}).get(key)
        y = (b.get("blocks", {}) or {}).get(key)
        if x and y and x["sha256"] != y["sha256"]:
            changed.append(key)
    for key in ("engine_factory", "bot_factory"):
        x = (a.get("files", {}) or {}).get(key)
        y = (b.get("files", {}) or {}).get(key)
        if x and y and x["sha256"] != y["sha256"]:
            changed.append(key)
    return changed


def main(argv):
    if len(argv) == 2:
        print(json.dumps(collect(argv[1]), ensure_ascii=False))
        return 0
    if len(argv) == 4 and argv[1] == "compare":
        a = json.load(open(argv[2], encoding="utf-8"))
        b = json.load(open(argv[3], encoding="utf-8"))
        print(json.dumps({"changed": compare(a, b)}, ensure_ascii=False))
        return 0
    sys.stderr.write("kullanim: block_hash.py <dizin> | block_hash.py compare <eski.json> <yeni.json>\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
