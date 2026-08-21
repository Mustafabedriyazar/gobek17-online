#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Commit oncesi secret tarayici.

Girdi: `git diff --cached` ciktisi (stdin) veya dosya listesi.
Bulunan degerin TAMAMI asla yazilmaz; maskeli rapor uretilir.

Kullanim:
    git diff --cached | secret_scan.py --stdin
    secret_scan.py --files a.js b.json
Exit: 0 temiz, 70 secret bulundu.
"""
import argparse
import re
import sys

EXIT_SECRET = 70

# STRONG: gercek anahtar/token bicimleri — her yerde ABORT sebebi (test dosyalari dahil)
# WEAK  : "password=..." gibi atama kaliplari — test/fixture dosyalarinda mesru olabilir
STRONG = [
    ("private key blogu", re.compile(r"BEGIN\s+(RSA|EC|OPENSSH|PGP|DSA)?\s*PRIVATE KEY")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("GitHub PAT (fine-grained)", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("Railway token", re.compile(r"\brailway[_-]?(api[_-]?)?(token|key)\s*[:=]\s*['\"]?[A-Za-z0-9\-_]{16,}")),
    ("AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("AWS secret", re.compile(r"\baws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{30,}")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{30,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("redis url (kimlikli)", re.compile(r"\bredis(s)?://[^:\s]+:[^@\s]{4,}@")),
    ("postgres url (kimlikli)", re.compile(r"\bpostgres(ql)?://[^:\s]+:[^@\s]{4,}@")),
]
WEAK = [
    ("password= atamasi", re.compile(r"\bpass(word|wd)?\s*[:=]\s*['\"][^'\"\s]{6,}['\"]", re.I)),
    ("secret= atamasi", re.compile(r"\bsecret\s*[:=]\s*['\"][^'\"\s]{8,}['\"]", re.I)),
    ("api_key= atamasi", re.compile(r"\bapi[_-]?key\s*[:=]\s*['\"][^'\"\s]{8,}['\"]", re.I)),
]
RULES = STRONG + WEAK
# .env.example / .env.sample / .env.template repoda mesru olarak bulunur
ENV_OK = re.compile(r"\.env\.(example|sample|template|dist)$")
# test / fixture dosyalarinda sahte parola normaldir; ZAYIF kurallar orada uygulanmaz
TESTISH = re.compile(r"(^|/)(tests?|fixtures?|spec|__tests__)/|(^|/)(test|spec)[-_.]|[-_.](test|spec)\.[cm]?jsx?$")
FILE_RULES = [
    ("izinsiz .env dosyasi", re.compile(r"(^|/)\.env(\.|$)")),
    ("ozel anahtar dosyasi", re.compile(r"\.(pem|key|p12|keystore|jks)$")),
]
# Ornek/sahte degerler (repo icinde mesru olarak bulunanlar)
ALLOW = re.compile(r"(example|sample|placeholder|dummy|changeme|your[_-]?token|xxxx+|<[^>]+>)", re.I)


def mask(text):
    t = text.strip()
    if len(t) <= 10:
        return t[:2] + "***"
    return t[:4] + "***" + t[-2:] + " (%d karakter)" % len(t)


def scan_lines(lines):
    hits = []
    path = "?"
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if line.startswith("+++ b/"):
            path = line[6:]
            for name, rx in FILE_RULES:
                if rx.search(path) and not ENV_OK.search(path):
                    hits.append((name, path, i, mask(path)))
            continue
        if line.startswith("---") or line.startswith("diff ") or line.startswith("index "):
            continue
        if line.startswith("-"):
            continue
        body = line[1:] if line.startswith("+") else line
        if ALLOW.search(body):
            continue
        rules = STRONG if TESTISH.search(path) else RULES
        for name, rx in rules:
            m = rx.search(body)
            if m:
                hits.append((name, path, i, mask(m.group(0))))
    return hits


def scan_tree(root, max_mb=12):
    """Yayinlanacak kaynak agacini tarar. Bootstrap modunda commit'e giren dosya
    binary bir zip oldugu icin diff taramasi KOR kalir; asil koruma burasidir."""
    import os
    skip_dirs = {".git", "node_modules", ".cache", "dist", "build", ".gobek17-app"}
    text_ext = {".js", ".cjs", ".mjs", ".json", ".html", ".htm", ".css", ".md", ".txt",
                ".yml", ".yaml", ".sh", ".env", ".toml", ".webmanifest", ".ts", ".jsx"}
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            relslash = rel.replace(os.sep, "/")
            for rname, rx in FILE_RULES:
                if rx.search(relslash) and not ENV_OK.search(relslash):
                    hits.append((rname, rel, 0, mask(rel)))
            ext = os.path.splitext(name)[1].lower()
            if ext not in text_ext:
                continue
            try:
                if os.path.getsize(path) > max_mb * 1024 * 1024:
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    for i, line in enumerate(fh, 1):
                        if len(line) > 4000 or ALLOW.search(line):
                            continue
                        for rname, rx in (STRONG if TESTISH.search(relslash) else RULES):
                            m = rx.search(line)
                            if m:
                                hits.append((rname, rel, i, mask(m.group(0))))
            except OSError:
                continue
    return hits


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--tree", default="")
    p.add_argument("--files", nargs="*", default=[])
    args = p.parse_args(argv[1:])
    hits = []
    if args.stdin:
        hits += scan_lines(sys.stdin.read().splitlines())
    if args.tree:
        hits += scan_tree(args.tree)
    for f in args.files:
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                hits += [(n, f, i, m) for (n, _p, i, m) in scan_lines(fh.read().splitlines())]
        except OSError:
            continue
    if not hits:
        print("SECRET GUARD: temiz")
        return 0
    print("SECRET GUARD: %d supheli deger bulundu (degerler maskeli)" % len(hits))
    for name, path, line, m in hits[:40]:
        print("  - %s | %s satir %d | %s" % (name, path, line, m))
    return EXIT_SECRET


if __name__ == "__main__":
    sys.exit(main(sys.argv))
