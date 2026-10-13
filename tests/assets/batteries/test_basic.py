"""Tests for basic battery simulator."""

import pytest

from asset_simulator.assets.batteries.basic import (
    Battery,
    Degradation,
    DerateCurve,
    Sim,
    from_i16,
    to_i16,
    to_u16,
)


class TestConversionFunctions:
    """Test conversion functions for Modbus registers."""

    def test_to_u16_normal(self) -> None:
        assert to_u16(100.6) == 101
        assert to_u16(0) == 0
        assert to_u16(65535) == 65535

    def test_to_u16_clamping(self) -> None:
        assert to_u16(-10) == 0
        assert to_u16(70000) == 65535

    def test_to_i16_normal(self) -> None:
        assert to_i16(100.6) == 101
        assert to_i16(-100.4) == 0xFF9C

    def test_to_i16_clamping(self) -> None:
        assert to_i16(40000) == 32767
        assert to_i16(-40000) == 0x8000

    def test_from_i16(self) -> None:
        assert from_i16(100) == 100
        assert from_i16(0xFF9B) == -101
        assert from_i16(0x8000) == -32768
        assert from_i16(0x7FFF) == 32767


class TestDerateCurve:
    """Test power derating based on SoC."""

    def test_disabled_curve(self) -> None:
        curve = DerateCurve(enabled=False)
        assert curve.charge_factor(90.0) == 1.0
        assert curve.discharge_factor(10.0) == 1.0

    def test_charge_factor_below_threshold(self) -> None:
        curve = DerateCurve(enabled=True, charge_from=80.0, min_factor=0.1)
        assert curve.charge_factor(50.0) == 1.0
        assert curve.charge_factor(80.0) == 1.0

    def test_charge_factor_above_threshold(self) -> None:
        curve = DerateCurve(enabled=True, charge_from=80.0, min_factor=0.1)
        assert abs(curve.charge_factor(100.0) - 0.1) < 1e-10
        factor_90 = curve.charge_factor(90.0)
        assert 0.1 < factor_90 < 1.0

    def test_discharge_factor_above_threshold(self) -> None:
        curve = DerateCurve(enabled=True, discharge_below=20.0, min_factor=0.1)
        assert curve.discharge_factor(50.0) == 1.0
        assert curve.discharge_factor(20.0) == 1.0

    def test_discharge_factor_below_threshold(self) -> None:
        curve = DerateCurve(enabled=True, discharge_below=20.0, min_factor=0.1)
        assert curve.discharge_factor(0.0) == 0.1
        factor_10 = curve.discharge_factor(10.0)
        assert 0.1 < factor_10 < 1.0


class TestDegradation:
    """Test battery degradation model."""

    def test_default_values(self) -> None:
        deg = Degradation()
        assert not deg.enabled
        assert deg.initial_soh == 1.0
        assert deg.min_soh == 0.6

    def test_custom_values(self) -> None:
        deg = Degradation(enabled=True, initial_soh=0.95, fade_per_efc=0.001, min_soh=0.7)
        assert deg.enabled
        assert deg.initial_soh == 0.95
        assert deg.fade_per_efc == 0.001
        assert deg.min_soh == 0.7


class TestBattery:
    """Test battery simulation core."""

    def test_initialization(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=10.0)
        assert bat.rated_kw == 100.0
        assert bat.nominal_kwh == 200.0
        assert bat.soc == 50.0
        assert bat.power_kw == 0.0
        assert bat.soh == 1.0

    def test_capacity_kwh_no_degradation(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        assert bat.capacity_kwh == 200.0

    def test_capacity_kwh_with_degradation(self) -> None:
        deg = Degradation(enabled=True, initial_soh=0.9, fade_per_efc=0.001, min_soh=0.6)
        bat = Battery(
            power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0, deg=deg
        )
        assert bat.capacity_kwh == 180.0

    def test_state_standby(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        assert bat.state == 0

    def test_state_charging(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        bat.power_kw = -10.0
        assert bat.state == 1

    def test_state_discharging(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        bat.power_kw = 10.0
        assert bat.state == 2

    def test_step_standby_mode(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        initial_soc = bat.soc
        bat.step(dt=1.0, mode=0, setpoint_kw=10.0, limit_kw=100.0, soc_min=10.0, soc_max=90.0)
        assert bat.power_kw == 0.0
        assert bat.soc == initial_soc

    def test_step_discharge(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        initial_soc = bat.soc
        bat.step(dt=1.0, mode=1, setpoint_kw=10.0, limit_kw=100.0, soc_min=10.0, soc_max=90.0)
        assert bat.power_kw == 10.0
        assert bat.soc < initial_soc
        assert bat.e_discharged_kwh > 0

    def test_step_charge(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        initial_soc = bat.soc
        bat.step(dt=1.0, mode=1, setpoint_kw=-10.0, limit_kw=100.0, soc_min=10.0, soc_max=90.0)
        assert bat.power_kw == -10.0
        assert bat.soc > initial_soc
        assert bat.e_charged_kwh > 0

    def test_step_soc_min_limit(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=15.0, efficiency=0.92, ramp_kw_s=0.0)
        bat.step(dt=1.0, mode=1, setpoint_kw=10.0, limit_kw=100.0, soc_min=15.0, soc_max=90.0)
        assert bat.power_kw == 0.0

    def test_step_soc_max_limit(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=85.0, efficiency=0.92, ramp_kw_s=0.0)
        bat.step(dt=1.0, mode=1, setpoint_kw=-10.0, limit_kw=100.0, soc_min=10.0, soc_max=85.0)
        assert bat.power_kw == 0.0

    def test_step_with_ramp_rate(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=5.0)
        bat.step(dt=1.0, mode=1, setpoint_kw=10.0, limit_kw=100.0, soc_min=10.0, soc_max=90.0)
        assert 0 < bat.power_kw <= 5.0

    def test_efc_calculation(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        bat.cell_throughput_kwh = 200.0
        assert bat.efc == 0.5

    def test_max_discharge_kw(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        assert bat.max_discharge_kw(100.0) == 100.0

    def test_max_charge_kw(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        assert bat.max_charge_kw(100.0) == 100.0


class TestSim:
    """Test simulation state management."""

    def test_initialization(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        assert sim.mode == 0
        assert sim.setpoint_raw == 0
        assert sim.heartbeat == 0

    def test_setpoint_kw_positive(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        sim.setpoint_raw = 1000
        assert sim.setpoint_kw == 100.0

    def test_setpoint_kw_negative(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        sim.setpoint_raw = 0xFF9C
        assert sim.setpoint_kw == -10.0

    def test_limit_kw(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        sim.limit_raw = 800
        assert sim.limit_kw == 80.0

    def test_soc_min(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        sim.soc_min_raw = 100
        assert sim.soc_min == 10.0

    def test_soc_max(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        sim.soc_max_raw = 900
        assert sim.soc_max == 90.0

    def test_control_words(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        sim.mode = 1
        sim.setpoint_raw = 500
        words = sim.control_words()
        assert len(words) == 5
        assert words[0] == 1
        assert words[1] == 500

    def test_status_words(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        words = sim.status_words()
        assert len(words) == 16
        assert words[0] == 0
        assert words[2] == 500
        assert words[3] == 1000

    def test_apply_write_mode(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        result = sim.apply_write(0, 1)
        assert result == 1
        assert sim.mode == 1

    def test_apply_write_setpoint(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        result = sim.apply_write(1, 0xFF9C)
        assert result == 0xFF9C
        assert sim.setpoint_raw == 0xFF9C

    def test_apply_write_limit(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        result = sim.apply_write(2, 800)
        assert result == 800
        assert sim.limit_raw == 800

    def test_apply_write_limit_clamping(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        result = sim.apply_write(2, 2000)
        assert result == 1000

    def test_apply_write_soc_min(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        result = sim.apply_write(3, 100)
        assert result == 100
        assert sim.soc_min_raw == 100

    def test_apply_write_soc_max(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        result = sim.apply_write(4, 900)
        assert result == 900
        assert sim.soc_max_raw == 900

    def test_apply_write_invalid_address(self) -> None:
        bat = Battery(power_kw=100.0, capacity_kwh=200.0, soc=50.0, efficiency=0.92, ramp_kw_s=0.0)
        sim = Sim(bat)
        with pytest.raises(KeyError):
            sim.apply_write(99, 100)
