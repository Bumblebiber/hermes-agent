"""Tests for F-CRON-003: skip-if-running guard in tick()."""

import time
from unittest.mock import patch

import pytest

import cron.scheduler as scheduler_mod


class TestSkipIfRunning:
    @pytest.fixture(autouse=True)
    def _clear_running_job_ids(self):
        with scheduler_mod._running_job_ids_lock:
            scheduler_mod._running_job_ids.clear()
        yield
        with scheduler_mod._running_job_ids_lock:
            scheduler_mod._running_job_ids.clear()

    @pytest.fixture(autouse=True)
    def _isolate_tick_lock(self, tmp_path):
        lock_dir = tmp_path / "cron"
        lock_dir.mkdir()
        lock_file = lock_dir / ".tick.lock"
        with patch("cron.scheduler._get_lock_paths", return_value=(lock_dir, lock_file)):
            yield

    def _make_job(self, job_id: str) -> dict:
        return {"id": job_id, "name": job_id, "deliver": "local"}

    def test_skip_job_already_running(self):
        job = self._make_job("job-x")
        with scheduler_mod._running_job_ids_lock:
            scheduler_mod._running_job_ids.add("job-x")

        with patch("cron.scheduler.get_due_jobs", return_value=[job]), \
             patch("cron.scheduler.advance_next_run") as mock_advance, \
             patch("cron.scheduler.run_job") as mock_run, \
             patch("cron.scheduler.save_job_output") as mock_save, \
             patch("cron.scheduler._deliver_result") as mock_deliver, \
             patch("cron.scheduler.mark_job_run") as mock_mark:
            from cron.scheduler import tick

            result = tick(verbose=False)

        assert result == 0
        mock_run.assert_not_called()
        mock_save.assert_not_called()
        mock_deliver.assert_not_called()
        mock_advance.assert_called_once_with("job-x")
        mock_mark.assert_called_once_with(
            "job-x",
            False,
            "still running — skipped",
            delivery_error=None,
        )

    def test_dispatch_job_not_running(self):
        job = self._make_job("job-y")

        with patch("cron.scheduler.get_due_jobs", return_value=[job]), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.run_job", return_value=(True, "out", "resp", None)), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result", return_value=None), \
             patch("cron.scheduler.mark_job_run") as mock_mark:
            from cron.scheduler import tick

            result = tick(verbose=False)

        assert result == 1
        mock_mark.assert_called_once()

    def test_running_job_ids_tracked_during_process_job(self):
        job = self._make_job("job-z")
        seen_during_run = {}

        def mock_run_job(j):
            with scheduler_mod._running_job_ids_lock:
                seen_during_run["present"] = j["id"] in scheduler_mod._running_job_ids
            time.sleep(0.05)
            return (True, "out", "resp", None)

        with patch("cron.scheduler.get_due_jobs", return_value=[job]), \
             patch("cron.scheduler.advance_next_run"), \
             patch("cron.scheduler.run_job", side_effect=mock_run_job), \
             patch("cron.scheduler.save_job_output", return_value="/tmp/out.md"), \
             patch("cron.scheduler._deliver_result", return_value=None), \
             patch("cron.scheduler.mark_job_run"):
            from cron.scheduler import tick

            tick(verbose=False)

        assert seen_during_run.get("present") is True
        with scheduler_mod._running_job_ids_lock:
            assert "job-z" not in scheduler_mod._running_job_ids
