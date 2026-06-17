"""Test weekly cron schedule computes next_run_at from current time, not last_run_at."""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

pytest.importorskip("croniter")

from cron.jobs import compute_next_run, parse_schedule


def test_weekly_cron_computes_from_now_not_last_run(monkeypatch):
    morocco = ZoneInfo("Africa/Casablanca")
    now = datetime(2026, 6, 17, 10, 0, 0, tzinfo=morocco)  # Wednesday
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)
    schedule = {"kind": "cron", "expr": "0 0 * * 1"}  # weekly Monday midnight
    result = compute_next_run(schedule)  # NO last_run_at
    assert result is not None
    next_dt = datetime.fromisoformat(result)
    assert next_dt.isoweekday() == 1  # Monday
    assert next_dt.date().isoformat() == "2026-06-22"
    assert next_dt.hour == 0
    assert next_dt.minute == 0


def test_weekly_after_off_schedule_fire(monkeypatch):
    morocco = ZoneInfo("Africa/Casablanca")
    now = datetime(2026, 6, 17, 10, 0, 0, tzinfo=morocco)  # Wednesday
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)
    schedule = {"kind": "cron", "expr": "0 0 * * 1"}
    last_run = datetime(2026, 6, 13, 10, 2, 0, tzinfo=morocco)  # Saturday
    result = compute_next_run(schedule, last_run_at=last_run.isoformat())
    assert result is not None
    next_dt = datetime.fromisoformat(result)
    # Should be upcoming Monday (June 22) from NOW, not from last_run (June 15)
    assert next_dt.isoweekday() == 1  # Monday
    assert next_dt.date().isoformat() == "2026-06-22"
    assert next_dt.hour == 0


def test_cron_parser_handles_weekly_monday():
    result = parse_schedule("0 0 * * 1")
    assert result["kind"] == "cron"
    assert result["expr"] == "0 0 * * 1"


def test_every_6h_cron_computes_from_now_not_last_run(monkeypatch):
    morocco = ZoneInfo("Africa/Casablanca")
    last_run = datetime(2026, 4, 6, 14, 10, 0, tzinfo=morocco)
    now = datetime(2026, 4, 10, 22, 0, 0, tzinfo=morocco)
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)
    schedule = {"kind": "cron", "expr": "0 */6 * * *"}
    result = compute_next_run(schedule, last_run_at=last_run.isoformat())
    assert result is not None
    next_dt = datetime.fromisoformat(result)
    assert next_dt.date().isoformat() == "2026-04-11"
    assert next_dt.hour == 0
