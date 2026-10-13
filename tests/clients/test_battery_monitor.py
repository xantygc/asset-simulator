"""Tests for battery monitor client."""

from asset_simulator.clients.battery_monitor import BatteryData, ConnectionManager


class TestBatteryData:
    """Test battery data structure."""

    def test_initialization(self) -> None:
        """Test BatteryData initialization."""
        data = BatteryData(
            timestamp="2026-10-09T10:00:00",
            state=0,
            power_kw=0.0,
            soc_pct=50.0,
            rated_power_kw=100.0,
            rated_capacity_kwh=215.0,
            stored_energy_kwh=107.5,
            energy_charged_kwh=0.0,
            energy_discharged_kwh=0.0,
            heartbeat=0,
            soh_pct=100.0,
            efc=0.0,
            max_discharge_kw=100.0,
            max_charge_kw=100.0,
            usable_capacity_kwh=215.0,
            mode=0,
            setpoint_kw=0.0,
            limit_kw=100.0,
            soc_min_pct=5.0,
            soc_max_pct=95.0,
        )

        assert data.soc_pct == 50.0
        assert data.soh_pct == 100.0
        assert data.power_kw == 0.0

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        data = BatteryData(
            timestamp="2026-10-09T10:00:00",
            state=1,
            power_kw=-50.0,
            soc_pct=60.0,
            rated_power_kw=100.0,
            rated_capacity_kwh=215.0,
            stored_energy_kwh=129.0,
            energy_charged_kwh=10.5,
            energy_discharged_kwh=5.2,
            heartbeat=100,
            soh_pct=98.5,
            efc=0.5,
            max_discharge_kw=98.5,
            max_charge_kw=98.5,
            usable_capacity_kwh=211.8,
            mode=1,
            setpoint_kw=-50.0,
            limit_kw=100.0,
            soc_min_pct=10.0,
            soc_max_pct=90.0,
        )

        d = data.to_dict()
        assert isinstance(d, dict)
        assert d["soc_pct"] == 60.0
        assert d["power_kw"] == -50.0
        assert d["state"] == 1


class TestConnectionManager:
    """Test WebSocket connection manager."""

    def test_initialization(self) -> None:
        """Test ConnectionManager initialization."""
        manager = ConnectionManager()
        assert len(manager.active_connections) == 0
