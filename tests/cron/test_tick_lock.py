"""Tests for F-CRON-002: tick file lock held until async jobs complete."""

import threading
import time
from unittest.mock import patch

import pytest

try:
    import fcntl
except ImportError:
    fcntl = None

pytestmark = pytest.mark.skipif(fcntl is None, reason="fcntl not available")


class TestTickLockHeldDuringAsyncJobs:
    @pytest.fixture(autouse=True)
    def _isolate_tick_lock(self, tmp_path):
        lock_dir = tmp_path / "cron"
        lock_dir.mkdir()
        lock_file = lock_dir / ".tick.lock"
        with patch("cron.scheduler._get_lock_paths", return_value=(lock_dir, lock_file)):
            self._lock_file = lock_file
            yield

    def _make_job(self, job_id: str) -> dict:
        return {"id": job_id, "name": job_id, "deliver": "local"}

    def test_lock_held_while_slow_job_runs(self):
        tick_started = threading.Event()
        release_run_job = threading.Event()
        lock_blocked = threading.Event()

        def mock_run_job(job):
            tick_started.set()
            release_run_job.wait(timeout=5)
            return (True, "output", "response", None)

        jobs = [self._make_job("slow-job")]

        def try_acquire_lock():
            tick_started.wait(timeout=5)
            try:
                with open(self._lock_file, "w", encoding="utf-8") as fd:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Should not reach here while tick holds lock
            except BlockingIOError:
                lock_blocked.set()

        with patch("cron.scheduler.get_due_jobs", return_value=jobs), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.run_job", side_effect=mock_run_job), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result", return_value=None), \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick

            side = threading.Thread(target=try_acquire_lock)
            side.start()
            tick_thread = threading.Thread(target=lambda: tick(verbose=False))
            tick_thread.start()
            side.join(timeout=5)
            assert lock_blocked.is_set(), "expected tick lock to block concurrent acquire"
            release_run_job.set()
            tick_thread.join(timeout=5)

        with open(self._lock_file, "w", encoding="utf-8") as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)

    def test_lock_released_after_fast_job(self):
        jobs = [self._make_job("fast-job")]
        lock_ok = threading.Event()

        def mock_run_job(job):
            return (True, "output", "response", None)

        def try_acquire_lock():
            try:
                with open(self._lock_file, "w", encoding="utf-8") as fd:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(fd, fcntl.LOCK_UN)
                lock_ok.set()
            except BlockingIOError:
                pass

        with patch("cron.scheduler.get_due_jobs", return_value=jobs), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.run_job", side_effect=mock_run_job), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result", return_value=None), \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick

            tick(verbose=False)
            side = threading.Thread(target=try_acquire_lock)
            side.start()
            side.join(timeout=5)

        assert lock_ok.is_set()

    def test_lock_released_after_future_wait_timeout(self, monkeypatch):
        monkeypatch.setattr("cron.scheduler._tick_wait_timeout", 0.1)

        def mock_run_job(job):
            time.sleep(2)
            return (True, "output", "response", None)

        jobs = [self._make_job("hung-job")]
        lock_ok = threading.Event()

        with patch("cron.scheduler.get_due_jobs", return_value=jobs), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.run_job", side_effect=mock_run_job), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result", return_value=None), \
             patch("cron.scheduler.mark_job_run") as mock_mark:
            from cron.scheduler import tick

            result = tick(verbose=False)

            def try_acquire_lock():
                try:
                    with open(self._lock_file, "w", encoding="utf-8") as fd:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    lock_ok.set()
                except BlockingIOError:
                    pass

            side = threading.Thread(target=try_acquire_lock)
            side.start()
            side.join(timeout=5)

        assert result == 0
        assert lock_ok.is_set()
        assert not mock_mark.called
