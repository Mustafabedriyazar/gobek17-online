# -*- coding: utf-8 -*-
"""Cihaz worker kuyrugu (g17cloud.worker_queue.WorkerQueue) davranis kaniti.

Termux'taki cihaz worker'i bu kuyruk uzerinden is kiralar (POST /worker/lease)
ve sonucu geri yazar (POST /worker/jobs/:id/result). Bu dosya HTTP katmanini
(api.py /worker/* uclari) DEGIL, kuyrugun kendisini dogrudan sinar.

Is durumlari: pending -> leased -> done|failed. Kiralanan bir is
lease_timeout suresi icinde sonuclanmazsa otomatik pending'e doner.
"""
import shutil

from _util import tmpdir


def _queue(lease_timeout=None):
    from g17cloud.worker_queue import DEFAULT_LEASE_TIMEOUT, WorkerQueue
    d = tmpdir()
    to = DEFAULT_LEASE_TIMEOUT if lease_timeout is None else lease_timeout
    return WorkerQueue(d, lease_timeout=to), d


# ==================================================================== is ekleme
def check_added_job_is_pending():
    q, d = _queue()
    try:
        job = q.add(["echo hi"], cwd_label="repo")
        assert job["status"] == "pending", job
        assert job["commands"] == ["echo hi"], job
        assert job["cwdLabel"] == "repo", job
        rec = q.get(job["id"])
        assert rec["status"] == "pending", rec
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_added_job_appears_in_pending_list():
    q, d = _queue()
    try:
        job = q.add(["echo hi"])
        pending = q.list(status="pending")
        assert [r["id"] for r in pending] == [job["id"]], pending
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ==================================================================== kiralama (lease)
def check_lease_returns_none_when_queue_empty():
    q, d = _queue()
    try:
        assert q.lease() is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_lease_marks_job_leased_and_sets_leased_at():
    q, d = _queue()
    try:
        job = q.add(["echo hi"])
        leased = q.lease()
        assert leased["id"] == job["id"], leased
        assert leased["status"] == "leased", leased
        assert leased["leasedAt"], leased
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_leased_job_not_leased_twice():
    q, d = _queue()
    try:
        q.add(["echo hi"])
        first = q.lease()
        assert first is not None, "ilk kiralama basarisiz olmamali"
        second = q.lease()
        assert second is None, second
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_lease_takes_oldest_pending_job_first():
    q, d = _queue()
    try:
        first = q.add(["echo 1"])
        second = q.add(["echo 2"])
        leased = q.lease()
        assert leased["id"] == first["id"], (leased, first, second)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ==================================================================== sonuc bildirimi (report)
def check_report_marks_done_and_stores_output_and_exit_code():
    q, d = _queue()
    try:
        job = q.add(["echo hi"])
        q.lease()
        done = q.report(job["id"], "hi\n", 0, ok=True)
        assert done["status"] == "done", done
        assert done["output"] == "hi\n", done
        assert done["exitCode"] == 0, done
        assert done["completedAt"], done
        rec = q.get(job["id"])
        assert rec["status"] == "done", rec
        assert rec["output"] == "hi\n", rec
        assert rec["exitCode"] == 0, rec
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_report_ok_false_marks_failed():
    q, d = _queue()
    try:
        job = q.add(["false"])
        q.lease()
        failed = q.report(job["id"], "hata\n", 1, ok=False)
        assert failed["status"] == "failed", failed
        assert failed["exitCode"] == 1, failed
        assert failed["output"] == "hata\n", failed
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_report_unknown_job_returns_none():
    q, d = _queue()
    try:
        assert q.report("w_bilinmeyen", "x", 0, ok=True) is None
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ==================================================================== kira zaman asimi
def check_leased_job_requeued_after_lease_timeout():
    # lease_timeout=-1: now() - leasedAt (her zaman >= 0) her zaman -1'den
    # buyuktur; sonraki lease() cagrisi suresi dolmus isi otomatik pending'e
    # alir ve hemen yeniden kiralar (worker cevap vermeden coktugu senaryonun
    # kaniti).
    q, d = _queue(lease_timeout=-1)
    try:
        job = q.add(["echo hi"])
        first = q.lease()
        assert first["status"] == "leased", first
        second = q.lease()
        assert second is not None, "suresi dolan is yeniden kiralanmadi"
        assert second["id"] == job["id"], second
        assert second["status"] == "leased", second
    finally:
        shutil.rmtree(d, ignore_errors=True)


def check_lease_timeout_does_not_requeue_fresh_lease():
    q, d = _queue(lease_timeout=300)
    try:
        q.add(["echo hi"])
        q.lease()
        assert q.lease() is None, "yeni kiralanan is suresi dolmadan yeniden kiralandi"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ==================================================================== bos kuyruk
def check_lease_empty_queue_returns_none_repeatedly():
    q, d = _queue()
    try:
        assert q.lease() is None
        assert q.lease() is None
        q.add(["echo hi"])
        assert q.lease() is not None
        assert q.lease() is None
    finally:
        shutil.rmtree(d, ignore_errors=True)
