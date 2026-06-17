"""Test that compute_next_run uses current time for cron jobs.

Cron schedules always anchor to _hermes_now(), not last_run_at.
Interval schedules still use last_run_at when provided.
Stale-run fast-forward in get_due_jobs() handles catch-up separately.
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

pytest.importorskip("croniter")

from cron.jobs import compute_next_run


class TestCronComputeNextRunUsesNow:
    """compute_next_run MUST use _hermes_now() as the croniter base for cron jobs."""

    def test_cron_uses_now_for_every_6h_schedule(self, monkeypatch):
        """For a schedule like 'every 6 hours', next run is computed from now.
        If now is Apr 10 22:00, next should be Apr 11 00:00 (not Apr 6 18:00
        from last_run_at)."""
        morocco = ZoneInfo("Africa/Casablanca")

        last_run = datetime(2026, 4, 6, 14, 10, 0, tzinfo=morocco)
        now = datetime(2026, 4, 10, 22, 0, 0, tzinfo=morocco)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "0 */6 * * *"}

        result = compute_next_run(schedule, last_run_at=last_run.isoformat())
        assert result is not None
        next_dt = datetime.fromisoformat(result)

        assert next_dt.date().isoformat() == "2026-04-11", (
            f"Expected next run on Apr 11 (from now), got {next_dt}"
        )
        assert next_dt.hour == 0

    def test_cron_without_last_run_at_uses_now(self, monkeypatch):
        """When last_run_at is NOT provided, compute_next_run falls back to
        _hermes_now() as the croniter base (existing behavior)."""
        morocco = ZoneInfo("Africa/Casablanca")

        now = datetime(2026, 4, 10, 22, 0, 0, tzinfo=morocco)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        schedule = {"kind": "cron", "expr": "0 */6 * * *"}

        result = compute_next_run(schedule)
        assert result is not None
        next_dt = datetime.fromisoformat(result)

        assert next_dt.date().isoformat() == "2026-04-11", (
            f"Expected next run on Apr 11 (from now), got {next_dt}"
        )
        assert next_dt.hour == 0

    def test_cron_weekly_consistent_with_interval(self, monkeypatch):
        """Cron jobs anchor to now; interval jobs still anchor to last_run_at."""
        morocco = ZoneInfo("Africa/Casablanca")

        last_run = datetime(2026, 4, 6, 14, 10, 0, tzinfo=morocco)
        now = datetime(2026, 4, 10, 22, 0, 0, tzinfo=morocco)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        cron_schedule = {"kind": "cron", "expr": "0 */6 * * *"}
        interval_schedule = {"kind": "interval", "minutes": 14 * 24 * 60}

        cron_result = compute_next_run(cron_schedule, last_run_at=last_run.isoformat())
        interval_result = compute_next_run(interval_schedule, last_run_at=last_run.isoformat())

        cron_dt = datetime.fromisoformat(cron_result)
        interval_dt = datetime.fromisoformat(interval_result)

        assert cron_dt.date().isoformat() == "2026-04-11"
        assert cron_dt.hour == 0
        assert interval_dt.date().isoformat() == "2026-04-20"
        assert interval_dt > last_run
