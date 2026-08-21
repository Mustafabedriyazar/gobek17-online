#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — kalici durum, kuyruk ve release kilidi.

Servis yeniden baslarsa yarim kalan gorev KAYBOLMAZ: her faz gecisi diske
atomik olarak yazilir; acilista terminal olmayan gorevler kurtarilir.

Release kilidi: AYNI ANDA TEK production release. Iki AI arastirma gorevi
paralel calisabilir, ama iki ayri build ayni anda main'e CIKAMAZ.
"""
import json
import os
import secrets
import threading
import time
from pathlib import Path

TERMINAL = ("success", "failed", "cancelled")
# Push'a kadar giden, kilit gerektiren fazlar
RELEASE_PHASES = ("guards", "artifact", "commit", "push", "actions", "production")


def now():
    return int(time.time())


def new_id():
    return "t_" + secrets.token_hex(8)


def atomic_write(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp-%d" % os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class TaskStore:
    def __init__(self, state_dir: Path):
        self.dir = Path(state_dir) / "tasks"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, tid):
        return self.dir / ("%s.json" % tid)

    def create(self, build, task, provider=None, dry_run=False, no_deploy=False):
        tid = new_id()
        rec = {
            "id": tid,
            "build": build,
            "task": task,
            "provider": provider or "auto",
            "dryRun": bool(dry_run),
            "noDeploy": bool(no_deploy),
            "status": "queued",
            "phase": "queued",
            "createdAt": now(),
            "updatedAt": now(),
            "attempts": 0,
            "events": [],
            "result": {},
        }
        with self._lock:
            atomic_write(self._path(tid), json.dumps(rec, ensure_ascii=False, indent=2))
        return rec

    def get(self, tid):
        p = self._path(tid)
        if not p.is_file():
            return None
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def save(self, rec):
        rec["updatedAt"] = now()
        with self._lock:
            atomic_write(self._path(rec["id"]),
                         json.dumps(rec, ensure_ascii=False, indent=2))
        return rec

    def update(self, tid, **fields):
        with self._lock:
            rec = self.get(tid)
            if not rec:
                return None
            rec.update(fields)
            return self.save(rec)

    def event(self, tid, phase, message, **extra):
        """Faz gecisi. SIR YAZILMAZ — mesajlar kisa teknik ozettir."""
        with self._lock:
            rec = self.get(tid)
            if not rec:
                return None
            rec["phase"] = phase
            ev = {"at": now(), "phase": phase, "message": message}
            ev.update(extra)
            rec["events"].append(ev)
            rec["events"] = rec["events"][-200:]
            return self.save(rec)

    def list(self, limit=50, status=None):
        out = []
        for p in sorted(self.dir.glob("t_*.json"), key=lambda x: x.stat().st_mtime,
                        reverse=True):
            try:
                with open(p, encoding="utf-8") as fh:
                    rec = json.load(fh)
            except (OSError, ValueError):
                continue
            if status and rec.get("status") != status:
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        return out

    def recoverable(self):
        """Restart sonrasi devam ettirilecek gorevler."""
        return [r for r in self.list(limit=500)
                if r.get("status") not in TERMINAL]


class ReleaseLock:
    """Tek production release kilidi (atomik mkdir + kalp atisi).

    Arastirma/AI fazlari kilitsiz calisir; yalnizca guard->push->health
    zinciri kilit ister. Boylece paralel AI isleri mumkun, paralel release degil.
    """

    def __init__(self, state_dir: Path, stale_after=1800):
        self.path = Path(state_dir) / "release.lock"
        self.stale_after = stale_after

    def _info(self):
        try:
            with open(self.path / "owner.json", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def holder(self):
        if not self.path.is_dir():
            return None
        return self._info()

    def acquire(self, task_id, build):
        try:
            self.path.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            info = self._info()
            age = now() - int(info.get("heartbeat", 0) or 0)
            if age > self.stale_after:
                # Sahibi olmeyen kilit: yalnizca eskimisse temizlenir.
                self.release(force=True)
                return self.acquire(task_id, build)
            return False
        except OSError:
            return False
        atomic_write(self.path / "owner.json", json.dumps(
            {"taskId": task_id, "build": build, "pid": os.getpid(),
             "acquiredAt": now(), "heartbeat": now()}))
        return True

    def heartbeat(self, task_id):
        info = self._info()
        if info.get("taskId") != task_id:
            return False
        info["heartbeat"] = now()
        atomic_write(self.path / "owner.json", json.dumps(info))
        return True

    def release(self, task_id=None, force=False):
        if not self.path.is_dir():
            return True
        if not force:
            info = self._info()
            if task_id and info.get("taskId") != task_id:
                return False
        try:
            f = self.path / "owner.json"
            if f.exists():
                f.unlink()
            self.path.rmdir()
        except OSError:
            return False
        return True
