#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G17 Cloud Agent v2 — cihaz worker kuyrugu.

Telefona disaridan baglanti ACILAMAZ; bu yuzden akis TERS YONDUR: Termux'taki
worker periyodik olarak ajani yoklar (lease), isi KENDI cihazinda calistirir
ve sonucu geri yazar (report). Ajan bu dosyada hicbir komutu KENDISI
CALISTIRMAZ — yalnizca is kaydini bellek + kalici state dizininde tutar.

Is durumlari: pending -> leased -> done|failed. Kiralanan bir is LEASE_TIMEOUT
suresi icinde sonuclanmazsa (worker cevap vermezse) otomatik pending'e doner.
"""
import json
import secrets
import threading
from pathlib import Path

from .store import atomic_write, now

STATUSES = ("pending", "leased", "done", "failed")
# Worker cihaz uzerinde calisip donene kadar bu sureyi asarsa is yeniden
# pending'e alinir (worker cokerse/aginı kaybederse is sonsuza dek kilitli
# kalmasin diye).
DEFAULT_LEASE_TIMEOUT = 300


def new_job_id():
    return "w_" + secrets.token_hex(8)


class WorkerQueue:
    """Basit dosya-tabanli is kuyrugu: bellek + kalici state dizini.

    Her is kaydi diske atomik olarak yazilir; servis yeniden baslasa bile
    bekleyen/kiralanmis isler KAYBOLMAZ. Komut CALISTIRMA burada YOKTUR;
    yalnizca is kaydi tutulur, calistirma cihaz tarafindaki worker'a aittir.
    """

    def __init__(self, state_dir, lease_timeout=DEFAULT_LEASE_TIMEOUT):
        self.dir = Path(state_dir) / "worker_jobs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lease_timeout = lease_timeout
        self._lock = threading.RLock()

    def _path(self, job_id):
        return self.dir / ("%s.json" % job_id)

    def _read(self, job_id):
        p = self._path(job_id)
        if not p.is_file():
            return None
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _write(self, rec):
        rec["updatedAt"] = now()
        atomic_write(self._path(rec["id"]), json.dumps(rec, ensure_ascii=False, indent=2))
        return rec

    def _all(self):
        out = []
        for p in self.dir.glob("w_*.json"):
            try:
                with open(p, encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except (OSError, ValueError):
                continue
        return out

    def add(self, commands, cwd_label=None):
        """Yeni is ekler. commands: calistirilacak komut adimlarinin metin
        listesi. Ajan bu komutlari KENDISI calistirmaz; yalnizca kaydeder,
        cihaz worker'i cekip kendi tarafinda calistirir."""
        job_id = new_job_id()
        rec = {
            "id": job_id,
            "createdAt": now(),
            "updatedAt": now(),
            "status": "pending",
            "commands": [str(c) for c in (commands or [])],
            "cwdLabel": cwd_label or "",
            "leasedAt": None,
            "completedAt": None,
            "output": None,
            "exitCode": None,
        }
        with self._lock:
            self._write(rec)
        return rec

    def _requeue_expired(self):
        """Suresi dolan kiralanmis isleri pending'e dondurur. Kilit ALTINDA
        cagrilir."""
        for rec in self._all():
            if rec.get("status") != "leased":
                continue
            leased_at = int(rec.get("leasedAt") or 0)
            if now() - leased_at > self.lease_timeout:
                rec["status"] = "pending"
                rec["leasedAt"] = None
                self._write(rec)

    def lease(self):
        """Bekleyen en eski isi kiralar, leased isaretler ve isi doner.
        Bekleyen is yoksa None doner (worker bos yanit alir, komut
        calistirmaz)."""
        with self._lock:
            self._requeue_expired()
            pending = [r for r in self._all() if r.get("status") == "pending"]
            if not pending:
                return None
            pending.sort(key=lambda r: r.get("createdAt", 0))
            rec = pending[0]
            rec["status"] = "leased"
            rec["leasedAt"] = now()
            return self._write(rec)

    def report(self, job_id, output, exit_code, ok=True):
        """Worker sonucu geri yazar: cikti + cikis kodu + basari durumu.
        Is bulunamazsa None doner."""
        with self._lock:
            rec = self._read(job_id)
            if not rec:
                return None
            rec["status"] = "done" if ok else "failed"
            rec["output"] = output
            rec["exitCode"] = exit_code
            rec["completedAt"] = now()
            return self._write(rec)

    def get(self, job_id):
        """Is durumunu okur."""
        return self._read(job_id)

    def list(self, limit=50, status=None):
        out = sorted(self._all(), key=lambda r: r.get("createdAt", 0), reverse=True)
        if status:
            out = [r for r in out if r.get("status") == status]
        return out[:limit]
