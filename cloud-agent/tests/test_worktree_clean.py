# -*- coding: utf-8 -*-
"""Worktree/ana checkout temizligi: selftest/smoke benzeri bir adim ana
chekout icinde Python onbellek artigi (__pycache__/.pyc) biraksa bile,
M.purge_pycache bunu temizler ve bir sonraki gorevin PREFLIGHT temizlik
kontrolunu (git status --porcelain) dusurmez. Kapsam KESIN sinirli oldugunu
(yalnizca __pycache__/.pyc, izlenen dosyalar ve baska kullanicilarin
dosyalari DOKUNULMAZ) da kanitlar."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from g17cloud import maintenance as M

AGENT = Path(__file__).resolve().parent.parent   # cloud-agent/


def _git(args, cwd, check=True):
    p = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError("git %s -> %s" % (" ".join(args), p.stderr))
    return p.stdout.strip()


def _make_checkout(root):
    """self_repo_dir'e benzeyen GERCEK bir git checkout'u: cloud-agent/g17cloud
    ve cloud-agent/tests altinda calistirilabilir, minimal, gercek bir paket."""
    agent = root / "cloud-agent"
    (agent / "g17cloud").mkdir(parents=True)
    (agent / "tests").mkdir(parents=True)
    (agent / "g17cloud" / "__init__.py").write_text("", encoding="utf-8")
    (agent / "g17cloud" / "dummy.py").write_text("VALUE = 1\n", encoding="utf-8")
    (agent / "tests" / "test_dummy.py").write_text(
        "from g17cloud import dummy\n\n\ndef check_dummy():\n    assert dummy.VALUE == 1\n",
        encoding="utf-8")
    # gercek test kosucusuyla BIREBIR ayni davranis icin dosyayi oldugu gibi kopyala.
    shutil.copy2(str(AGENT / "tests" / "run_tests.py"), str(agent / "tests" / "run_tests.py"))

    _git(["init", "-q"], root)
    _git(["symbolic-ref", "HEAD", "refs/heads/main"], root)
    _git(["add", "-A"], root)
    _git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed"], root)
    return agent


def _run_selftest_like_step(agent):
    """release_guard.run_self_tests'in AYNISI: run_tests.py'yi ayri surecte,
    cloud-agent kokunde calistirir. Bu, g17cloud/ ve tests/ altinda gercek
    __pycache__ artigi birakir (import mekanizmasi geregi)."""
    import os
    suite = agent / "tests" / "run_tests.py"
    env = dict(os.environ)
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    env.pop("PYTHONPYCACHEPREFIX", None)
    p = subprocess.run([sys.executable, str(suite)], cwd=str(agent),
                       capture_output=True, text=True, timeout=60, env=env)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "1 PASS / 0 FAIL" in (p.stdout or ""), p.stdout


# --------------------------------------------------------------- purge_pycache
def check_purge_pycache_removes_only_cache_artifacts():
    tmp = Path(tempfile.mkdtemp(prefix="g17purge-"))
    try:
        (tmp / "g17cloud" / "__pycache__").mkdir(parents=True)
        (tmp / "g17cloud" / "__pycache__" / "x.cpython-311.pyc").write_bytes(b"\x00")
        (tmp / "g17cloud" / "stray.pyc").write_bytes(b"\x00")
        (tmp / "tests" / "__pycache__").mkdir(parents=True)
        (tmp / "tests" / "__pycache__" / "y.cpython-311.pyc").write_bytes(b"\x00")
        # kaynak dosyalar VE alakasiz izlenmeyen bir kullanici dosyasi
        (tmp / "g17cloud" / "real.py").write_text("x = 1\n", encoding="utf-8")
        (tmp / "scratch-from-someone-else.txt").write_text("dokunma", encoding="utf-8")

        removed = M.purge_pycache(tmp)

        assert not (tmp / "g17cloud" / "__pycache__").exists()
        assert not (tmp / "tests" / "__pycache__").exists()
        assert not (tmp / "g17cloud" / "stray.pyc").exists()
        assert len(removed) == 3, removed
        assert (tmp / "g17cloud" / "real.py").read_text(encoding="utf-8") == "x = 1\n"
        assert (tmp / "scratch-from-someone-else.txt").read_text(encoding="utf-8") == "dokunma"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_purge_pycache_missing_root_is_noop():
    assert M.purge_pycache("/tmp/g17-does-not-exist-xyz") == []


# --------------------------------------------------------- ana checkout kanit
def check_selftest_like_step_dirties_checkout_before_purge():
    """On kosul: onlem alinmazsa selftest benzeri adim GERCEKTEN kirletir."""
    tmp = Path(tempfile.mkdtemp(prefix="g17wtc1-"))
    try:
        agent = _make_checkout(tmp)
        assert _git(["status", "--porcelain"], tmp) == ""
        _run_selftest_like_step(agent)
        assert _git(["status", "--porcelain"], tmp) != "", \
            "selftest __pycache__ birakmadi — test on kosulu gecersiz"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_purge_pycache_keeps_main_checkout_clean_after_selftest_like_step():
    tmp = Path(tempfile.mkdtemp(prefix="g17wtc2-"))
    try:
        agent = _make_checkout(tmp)
        _run_selftest_like_step(agent)
        assert _git(["status", "--porcelain"], tmp) != ""

        M.purge_pycache(tmp)

        assert _git(["status", "--porcelain"], tmp) == "", \
            "purge_pycache sonrasi ana checkout hala kirli"
        # izlenen dosyalar birebir ayni — HEAD'e karsi fark yok
        assert _git(["diff", "HEAD", "--name-only"], tmp) == ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_purge_pycache_never_removes_unrelated_untracked_file():
    """Baska bir surecin/kullanicinin biraktigi izlenmeyen dosya SILINMEZ —
    yalnizca __pycache__/.pyc kapsam disina hicbir sey alinmaz."""
    tmp = Path(tempfile.mkdtemp(prefix="g17wtc3-"))
    try:
        agent = _make_checkout(tmp)
        _run_selftest_like_step(agent)
        other = tmp / "cloud-agent" / "g17cloud" / "unrelated-user-file.txt"
        other.write_text("baska bir surecin dosyasi", encoding="utf-8")

        M.purge_pycache(tmp)

        assert other.is_file(), "alakasiz izlenmeyen dosya silindi"
        assert other.read_text(encoding="utf-8") == "baska bir surecin dosyasi"
        status = _git(["status", "--porcelain"], tmp)
        assert "unrelated-user-file.txt" in status, \
            "alakasiz dosya hala izlenmeyen olarak gorunmeli (purge onu commit/silme YAPMADI)"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
