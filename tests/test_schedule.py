"""
Tests for schedule logic — runs on host Python, no CircuitPython needed.

Extracts the pure functions from code.py and tests edge cases:
overnight periods, quiet hours spanning midnight, boundaries, etc.
"""

import time
import pytest


# ── Extracted logic (mirrors code.py) ──────────────────────

def in_quiet_hours(now, schedule):
    qs = schedule.get("quiet_start", -1)
    qe = schedule.get("quiet_end", -1)
    if qs < 0 or qe < 0:
        return False
    hour = now.tm_hour
    if qs > qe:
        return hour >= qs or hour < qe
    else:
        return qs <= hour < qe


def should_be_on(now, schedule):
    if not schedule.get("enabled", True):
        return False
    if in_quiet_hours(now, schedule):
        return False
    current_minutes = now.tm_hour * 60 + now.tm_min
    for p in schedule.get("periods", []):
        on_minutes = p["on_hour"] * 60 + p["on_minute"]
        off_minutes = p["off_hour"] * 60 + p["off_minute"]
        if on_minutes <= off_minutes:
            if on_minutes <= current_minutes < off_minutes:
                return True
        else:
            if current_minutes >= on_minutes or current_minutes < off_minutes:
                return True
    return False


def migrate_schedule(old):
    return {
        "periods": [{
            "on_hour": old["on_hour"],
            "on_minute": old["on_minute"],
            "off_hour": old["off_hour"],
            "off_minute": old["off_minute"],
        }],
        "enabled": old.get("enabled", True),
    }


# ── Helpers ────────────────────────────────────────────────

def t(hour, minute=0):
    """Make a struct_time for testing."""
    return time.struct_time((2026, 3, 10, hour, minute, 0, 0, 69, -1))


DEFAULT = {
    "periods": [{"on_hour": 6, "on_minute": 0, "off_hour": 22, "off_minute": 0}],
    "enabled": True,
    "quiet_start": 23,
    "quiet_end": 5,
}


# ── Tests: should_be_on ───────────────────────────────────

class TestShouldBeOn:
    def test_midday_on(self):
        assert should_be_on(t(12, 0), DEFAULT) is True

    def test_early_morning_off(self):
        assert should_be_on(t(3, 0), DEFAULT) is False

    def test_late_night_off(self):
        assert should_be_on(t(23, 30), DEFAULT) is False

    def test_exactly_on_boundary(self):
        assert should_be_on(t(6, 0), DEFAULT) is True

    def test_exactly_off_boundary(self):
        assert should_be_on(t(22, 0), DEFAULT) is False

    def test_one_minute_before_on(self):
        assert should_be_on(t(5, 59), DEFAULT) is False

    def test_one_minute_before_off(self):
        assert should_be_on(t(21, 59), DEFAULT) is True

    def test_disabled(self):
        s = {**DEFAULT, "enabled": False}
        assert should_be_on(t(12, 0), s) is False

    def test_empty_periods(self):
        s = {"periods": [], "enabled": True}
        assert should_be_on(t(12, 0), s) is False


class TestOvernightPeriod:
    """Period that spans midnight, e.g., 22:00 - 06:00."""
    OVERNIGHT = {
        "periods": [{"on_hour": 22, "on_minute": 0, "off_hour": 6, "off_minute": 0}],
        "enabled": True,
    }

    def test_before_midnight(self):
        assert should_be_on(t(23, 0), self.OVERNIGHT) is True

    def test_after_midnight(self):
        assert should_be_on(t(2, 0), self.OVERNIGHT) is True

    def test_midday_off(self):
        assert should_be_on(t(12, 0), self.OVERNIGHT) is False

    def test_exactly_on(self):
        assert should_be_on(t(22, 0), self.OVERNIGHT) is True

    def test_exactly_off(self):
        assert should_be_on(t(6, 0), self.OVERNIGHT) is False


class TestMultiplePeriods:
    """Two periods with a gap: morning + evening."""
    SPLIT = {
        "periods": [
            {"on_hour": 6, "on_minute": 0, "off_hour": 12, "off_minute": 0},
            {"on_hour": 14, "on_minute": 0, "off_hour": 20, "off_minute": 0},
        ],
        "enabled": True,
    }

    def test_morning_on(self):
        assert should_be_on(t(9, 0), self.SPLIT) is True

    def test_gap_off(self):
        assert should_be_on(t(13, 0), self.SPLIT) is False

    def test_evening_on(self):
        assert should_be_on(t(17, 0), self.SPLIT) is True

    def test_night_off(self):
        assert should_be_on(t(21, 0), self.SPLIT) is False


# ── Tests: quiet hours ────────────────────────────────────

class TestQuietHours:
    def test_quiet_blocks_active_period(self):
        """Quiet hours override even an active period."""
        s = {
            "periods": [{"on_hour": 0, "on_minute": 0, "off_hour": 23, "off_minute": 59}],
            "enabled": True,
            "quiet_start": 23,
            "quiet_end": 5,
        }
        assert should_be_on(t(2, 0), s) is False
        assert should_be_on(t(12, 0), s) is True

    def test_no_quiet_hours(self):
        s = {"periods": DEFAULT["periods"], "enabled": True}
        # no quiet_start/quiet_end keys — should not block
        assert should_be_on(t(3, 0), s) is False  # still off (not in period)
        assert should_be_on(t(12, 0), s) is True

    def test_quiet_same_day(self):
        """Quiet hours that don't span midnight: e.g., 13:00-15:00."""
        s = {
            "periods": [{"on_hour": 6, "on_minute": 0, "off_hour": 22, "off_minute": 0}],
            "enabled": True,
            "quiet_start": 13,
            "quiet_end": 15,
        }
        assert should_be_on(t(14, 0), s) is False
        assert should_be_on(t(12, 0), s) is True
        assert should_be_on(t(15, 0), s) is True


# ── Tests: migration ──────────────────────────────────────

class TestMigration:
    def test_old_format_migrates(self):
        old = {"on_hour": 6, "on_minute": 0, "off_hour": 22, "off_minute": 0, "enabled": True}
        new = migrate_schedule(old)
        assert "periods" in new
        assert len(new["periods"]) == 1
        assert new["periods"][0]["on_hour"] == 6
        assert new["enabled"] is True

    def test_disabled_preserved(self):
        old = {"on_hour": 6, "on_minute": 0, "off_hour": 22, "off_minute": 0, "enabled": False}
        new = migrate_schedule(old)
        assert new["enabled"] is False


# ── Tests: adaptive clock logic ───────────────────────────

class TestAdaptiveInterval:
    """Test the interval doubling/halving logic in isolation."""
    MIN = 900
    MAX = 86400

    def adapt(self, interval, drift, epsilon):
        """Simulate one adaptation step."""
        if drift < epsilon:
            return min(interval * 2, self.MAX)
        else:
            return max(interval // 2, self.MIN)

    def test_stable_doubles(self):
        interval = 3600
        interval = self.adapt(interval, drift=1.0, epsilon=30)
        assert interval == 7200

    def test_drifting_halves(self):
        interval = 3600
        interval = self.adapt(interval, drift=45.0, epsilon=30)
        assert interval == 1800

    def test_clamps_at_max(self):
        interval = 43200  # 12h
        interval = self.adapt(interval, drift=1.0, epsilon=30)
        assert interval == self.MAX

    def test_clamps_at_min(self):
        interval = 900
        interval = self.adapt(interval, drift=45.0, epsilon=30)
        assert interval == self.MIN

    def test_convergence_from_1h(self):
        """Starting at 1h with stable clock, should reach max in a few steps."""
        interval = 3600
        steps = 0
        while interval < self.MAX:
            interval = self.adapt(interval, drift=0.5, epsilon=30)
            steps += 1
        assert steps <= 5  # 1h -> 2h -> 4h -> 8h -> 16h -> 24h

    def test_recovery_from_max(self):
        """At max interval, sudden drift should drop quickly."""
        interval = self.MAX
        steps = 0
        while interval > 3600:
            interval = self.adapt(interval, drift=60.0, epsilon=30)
            steps += 1
        assert steps <= 5  # 24h -> 12h -> 6h -> 3h -> 1.5h

    def test_tight_epsilon(self):
        """With epsilon=2, even small drift triggers correction."""
        interval = 7200
        interval = self.adapt(interval, drift=3.0, epsilon=2)
        assert interval == 3600

    def test_loose_epsilon(self):
        """With epsilon=120, large drift is still tolerable."""
        interval = 3600
        interval = self.adapt(interval, drift=60.0, epsilon=120)
        assert interval == 7200  # backs off — drift within tolerance
