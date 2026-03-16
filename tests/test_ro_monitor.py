"""
Tests for RO monitor logic — runs on host Python, no CircuitPython needed.

Extracts the pure functions from nodes/ro_monitor/code.py and tests
TDS conversion, rejection rate, alerts, and membrane life estimation.
"""

import pytest


# ── Extracted logic (mirrors nodes/ro_monitor/code.py) ────

def voltage_to_tds(voltage, temp_c=25.0):
    temp_coeff = 1.0 + 0.02 * (temp_c - 25.0)
    compensated_v = voltage / temp_coeff
    tds = (133.42 * compensated_v ** 3
           - 255.86 * compensated_v ** 2
           + 857.39 * compensated_v) * 0.5
    return max(0.0, tds)


def rejection_rate(tds_pre, tds_post):
    if tds_pre <= 0:
        return 0.0
    return (1.0 - tds_post / tds_pre) * 100.0


def evaluate_alerts(tds_post, flow_lpm, rejection_pct, thresholds):
    alerts = {
        "tds_alert": tds_post > thresholds.get("tds_alert_ppm", 50),
        "tds_warn": tds_post > thresholds.get("tds_warn_ppm", 20),
        "flow_low": False,
        "rejection_low": rejection_pct < 80.0 if rejection_pct > 0 else False,
    }
    return alerts


def membrane_life_remaining(liters_lifetime, rejection_pct, thresholds):
    max_liters = thresholds.get("membrane_life_liters", 2000)
    if max_liters <= 0:
        return 100.0
    volume_pct = max(0.0, 100.0 - (liters_lifetime / max_liters) * 100.0)
    if rejection_pct > 0 and rejection_pct < 85:
        penalty = (85 - rejection_pct) * 2
        volume_pct = max(0.0, volume_pct - penalty)
    return round(volume_pct, 1)


# ── Default thresholds ────────────────────────────────────

DEFAULT_THRESHOLDS = {
    "tds_alert_ppm": 50,
    "tds_warn_ppm": 20,
    "flow_min_lpm": 0.1,
    "membrane_life_liters": 2000,
}


# ── Tests: TDS conversion ────────────────────────────────

class TestVoltagToTds:
    def test_zero_voltage(self):
        assert voltage_to_tds(0.0) == 0.0

    def test_known_voltage(self):
        """Mid-range voltage should give reasonable TDS."""
        tds = voltage_to_tds(1.0, 25.0)
        assert 100 < tds < 500

    def test_high_voltage(self):
        """Higher voltage = higher TDS."""
        low = voltage_to_tds(0.5)
        high = voltage_to_tds(1.5)
        assert high > low

    def test_negative_clamps_to_zero(self):
        """Very low voltages should not produce negative TDS."""
        tds = voltage_to_tds(0.001)
        assert tds >= 0.0

    def test_temperature_compensation_hot(self):
        """Hotter water should give lower TDS reading (conductivity rises)."""
        tds_25 = voltage_to_tds(1.0, 25.0)
        tds_35 = voltage_to_tds(1.0, 35.0)
        # At higher temp, the same voltage represents lower actual TDS
        assert tds_35 < tds_25

    def test_temperature_compensation_cold(self):
        """Colder water should give higher TDS reading."""
        tds_25 = voltage_to_tds(1.0, 25.0)
        tds_15 = voltage_to_tds(1.0, 15.0)
        assert tds_15 > tds_25

    def test_at_reference_temp(self):
        """At 25C (reference), temp coefficient should be 1.0."""
        tds = voltage_to_tds(1.0, 25.0)
        # Manually compute: (133.42*1 - 255.86*1 + 857.39*1) * 0.5
        expected = (133.42 - 255.86 + 857.39) * 0.5
        assert abs(tds - expected) < 0.01


# ── Tests: rejection rate ─────────────────────────────────

class TestRejectionRate:
    def test_perfect_rejection(self):
        assert rejection_rate(200, 0) == 100.0

    def test_no_rejection(self):
        assert rejection_rate(200, 200) == 0.0

    def test_typical_rejection(self):
        """95% rejection: 200 pre, 10 post."""
        rate = rejection_rate(200, 10)
        assert abs(rate - 95.0) < 0.01

    def test_zero_pre_avoids_division_by_zero(self):
        assert rejection_rate(0, 10) == 0.0

    def test_negative_pre_avoids_division_by_zero(self):
        assert rejection_rate(-5, 10) == 0.0

    def test_partial_rejection(self):
        """50% rejection."""
        rate = rejection_rate(100, 50)
        assert abs(rate - 50.0) < 0.01


# ── Tests: alert evaluation ───────────────────────────────

class TestAlerts:
    def test_clean_water_no_alerts(self):
        alerts = evaluate_alerts(10, 1.0, 95.0, DEFAULT_THRESHOLDS)
        assert alerts["tds_alert"] is False
        assert alerts["tds_warn"] is False
        assert alerts["rejection_low"] is False

    def test_tds_warning(self):
        alerts = evaluate_alerts(30, 1.0, 90.0, DEFAULT_THRESHOLDS)
        assert alerts["tds_warn"] is True
        assert alerts["tds_alert"] is False

    def test_tds_alert(self):
        alerts = evaluate_alerts(60, 1.0, 70.0, DEFAULT_THRESHOLDS)
        assert alerts["tds_alert"] is True
        assert alerts["tds_warn"] is True

    def test_low_rejection(self):
        alerts = evaluate_alerts(15, 1.0, 75.0, DEFAULT_THRESHOLDS)
        assert alerts["rejection_low"] is True

    def test_zero_rejection_no_alert(self):
        """Zero rejection rate (no data) should not flag."""
        alerts = evaluate_alerts(0, 0.0, 0.0, DEFAULT_THRESHOLDS)
        assert alerts["rejection_low"] is False

    def test_custom_thresholds(self):
        custom = {"tds_alert_ppm": 100, "tds_warn_ppm": 50}
        alerts = evaluate_alerts(60, 1.0, 90.0, custom)
        assert alerts["tds_alert"] is False
        assert alerts["tds_warn"] is True


# ── Tests: membrane life estimation ───────────────────────

class TestMembraneLife:
    def test_new_membrane(self):
        pct = membrane_life_remaining(0, 98.0, DEFAULT_THRESHOLDS)
        assert pct == 100.0

    def test_half_life(self):
        pct = membrane_life_remaining(1000, 95.0, DEFAULT_THRESHOLDS)
        assert abs(pct - 50.0) < 0.1

    def test_end_of_life(self):
        pct = membrane_life_remaining(2000, 95.0, DEFAULT_THRESHOLDS)
        assert pct == 0.0

    def test_over_life(self):
        """Past rated life, should clamp at 0."""
        pct = membrane_life_remaining(3000, 95.0, DEFAULT_THRESHOLDS)
        assert pct == 0.0

    def test_degraded_rejection_penalty(self):
        """Low rejection rate should penalize life estimate."""
        good = membrane_life_remaining(500, 95.0, DEFAULT_THRESHOLDS)
        bad = membrane_life_remaining(500, 70.0, DEFAULT_THRESHOLDS)
        assert bad < good

    def test_zero_rejection_no_penalty(self):
        """Zero rejection (no data) should not penalize."""
        pct = membrane_life_remaining(500, 0.0, DEFAULT_THRESHOLDS)
        assert pct == 75.0  # pure volume-based: (1 - 500/2000) * 100

    def test_custom_life_liters(self):
        custom = {"membrane_life_liters": 4000}
        pct = membrane_life_remaining(1000, 95.0, custom)
        assert abs(pct - 75.0) < 0.1

    def test_zero_max_liters(self):
        """Zero max liters should return 100% (avoid division by zero)."""
        pct = membrane_life_remaining(1000, 95.0, {"membrane_life_liters": 0})
        assert pct == 100.0
