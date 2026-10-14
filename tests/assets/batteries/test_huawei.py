"""Tests para el simulador Huawei SUN2000/LUNA2000."""
import pytest
from asset_simulator.assets.batteries.huawei import HuaweiSim, clamp, enc, dec
from asset_simulator.assets.batteries.basic import Battery, Derate Curve, Degradation


def test_clamp():
    """Test función clamp."""
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(15, 0, 10) == 10


def test_encoding():
    """Test codificación/decodificación de registros."""
    # U16
    assert enc("u16", 100) == [100]
    assert dec("u16", [100]) == 100

    # I16
    assert enc("i16", -100) == [65436]
    assert dec("i16", [65436]) == -100

    # U32
    assert enc("u32", 100000) == [1, 34464]
    assert dec("u32", [1, 34464]) == 100000

    # I32
    assert enc("i32", -100000) == [65535, 31072]
    assert dec("i32", [65535, 31072]) == -100000


def test_huawei_sim_init():
    """Test inicialización del simulador Huawei."""
    bat = Battery(5.0, 10.0, 50.0, 0.92, 0.0)
    sim = HuaweiSim(bat, 10.0, 600.0, 5.0, 2.0)

    assert sim.inv_kw == 10.0
    assert sim.bus_v == 600.0
    assert sim.bat == bat
    assert sim.get(60000) == 5000  # PV en W
    assert sim.get(60002) == 2000  # Load en W


def test_huawei_sim_step():
    """Test paso de simulación."""
    bat = Battery(5.0, 10.0, 50.0, 0.92, 0.0)
    sim = HuaweiSim(bat, 10.0, 600.0, 5.0, 2.0)

    # Modo autoconsumo (modo 2 por defecto)
    sim.step(1.0)

    # Verificar que el simulador avanza
    assert sim.sim_t == 1.0


def test_soc_limits():
    """Test límites de SoC."""
    bat = Battery(5.0, 10.0, 50.0, 0.92, 0.0)
    sim = HuaweiSim(bat, 10.0, 600.0, 0.0, 0.0)

    # Configurar límites
    sim.store[47082] = 200  # 20% min
    sim.store[47081] = 900  # 90% max
    sim.store[47102] = 100  # 10% backup

    assert sim.soc_min == 20.0
    assert sim.soc_max == 90.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
