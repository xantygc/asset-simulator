#!/usr/bin/env python3
"""
Demostración del simulador de batería básico.

Este script muestra cómo usar el simulador de batería programáticamente
sin necesidad de iniciar un servidor Modbus.
"""

from asset_simulator.assets.batteries.basic import Battery, Degradation, DerateCurve


def main() -> None:
    print("=" * 60)
    print("Demo: Simulador de Batería Básico")
    print("=" * 60)

    # Crear batería de 100 kW / 200 kWh
    print("\n1. Creando batería sin degradación...")
    battery = Battery(
        power_kw=100.0,
        capacity_kwh=200.0,
        soc=50.0,  # 50% inicial
        efficiency=0.92,
        ramp_kw_s=10.0,  # 10 kW/s de rampa
    )

    print(f"   - Potencia nominal: {battery.rated_kw} kW")
    print(f"   - Capacidad: {battery.capacity_kwh} kWh")
    print(f"   - SoC inicial: {battery.soc}%")
    print(f"   - SOH: {battery.soh * 100}%")

    # Simular descarga
    print("\n2. Simulando descarga a 50 kW durante 1 hora...")
    for _ in range(3600):  # 1 hora en pasos de 1 segundo
        battery.step(
            dt=1.0,
            mode=1,  # run
            setpoint_kw=50.0,  # 50 kW de descarga
            limit_kw=100.0,
            soc_min=10.0,
            soc_max=90.0,
        )

    print(f"   - Potencia actual: {battery.power_kw:.2f} kW")
    print(f"   - SoC final: {battery.soc:.2f}%")
    print(f"   - Energía descargada: {battery.e_discharged_kwh:.2f} kWh")
    print(f"   - Estado: {['standby', 'cargando', 'descargando'][battery.state]}")

    # Batería con curva de potencia
    print("\n3. Creando batería con curva de potencia vs SoC...")
    curve = DerateCurve(enabled=True, charge_from=80.0, discharge_below=20.0, min_factor=0.1)
    battery2 = Battery(
        power_kw=100.0,
        capacity_kwh=200.0,
        soc=15.0,  # SoC bajo
        efficiency=0.92,
        ramp_kw_s=0.0,  # Sin rampa
        curve=curve,
    )

    print(f"   - SoC inicial: {battery2.soc}%")
    print(f"   - Potencia máx. descarga disponible: {battery2.max_discharge_kw(100.0):.2f} kW")
    print(f"   - Factor de descarga: {curve.discharge_factor(battery2.soc):.2f}")

    # Batería con degradación
    print("\n4. Creando batería con degradación...")
    deg = Degradation(enabled=True, initial_soh=0.95, fade_per_efc=0.001, min_soh=0.6)
    battery3 = Battery(
        power_kw=100.0,
        capacity_kwh=200.0,
        soc=50.0,
        efficiency=0.92,
        ramp_kw_s=0.0,
        deg=deg,
    )

    print(f"   - SOH inicial: {battery3.soh * 100:.2f}%")
    print(f"   - Capacidad útil: {battery3.capacity_kwh:.2f} kWh")

    # Simular muchos ciclos
    print("\n5. Simulando 50 ciclos completos (carga/descarga)...")
    for _ in range(50):
        # Descarga completa
        while battery3.soc > 10.0:
            battery3.step(
                dt=1.0, mode=1, setpoint_kw=100.0, limit_kw=100.0, soc_min=10.0, soc_max=90.0
            )

        # Carga completa
        while battery3.soc < 90.0:
            battery3.step(
                dt=1.0, mode=1, setpoint_kw=-100.0, limit_kw=100.0, soc_min=10.0, soc_max=90.0
            )

    print(f"   - SOH final: {battery3.soh * 100:.2f}%")
    print(f"   - Capacidad útil final: {battery3.capacity_kwh:.2f} kWh")
    print(f"   - Ciclos equivalentes: {battery3.efc:.2f}")
    print(f"   - Energía total cargada: {battery3.e_charged_kwh:.2f} kWh")
    print(f"   - Energía total descargada: {battery3.e_discharged_kwh:.2f} kWh")
    print(f"   - Throughput celda: {battery3.cell_throughput_kwh:.2f} kWh")

    print("\n" + "=" * 60)
    print("Demo completada exitosamente")
    print("=" * 60)


if __name__ == "__main__":
    main()
