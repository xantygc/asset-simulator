#!/usr/bin/env python3
"""
Asset Simulator - Battery Simulator
Copyright (C) 2026 Santiago González

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
"""
Simulador de batería con servidor Modbus TCP (pymodbus >= 3.12, API SimDevice).

Uso básico:
    python3 -m asset_simulator.assets.batteries.basic --power-kw 100 --capacity-kwh 215 --port 5020

Con curva de potencia dependiente del SoC y degradación (ambas OPCIONALES):
    python3 -m asset_simulator.assets.batteries.basic --power-kw 100 --capacity-kwh 215 \
        --soc-derate --derate-charge-from 80 --derate-discharge-below 20 --derate-min-factor 0.1 \
        --degradation --initial-soh 97 --fade-per-cycle 0.005 --min-soh 60

Convención de signos: potencia POSITIVA = descarga (inyecta), NEGATIVA = carga.

Modelo opcional
---------------
* --soc-derate: la potencia máxima se reduce según el SoC.
    - Carga: 100 % de la potencia hasta --derate-charge-from (SoC), y baja linealmente
      hasta --derate-min-factor al llegar al 100 %.
    - Descarga: 100 % de la potencia a partir de --derate-discharge-below (SoC), y baja
      linealmente hasta --derate-min-factor al llegar al 0 %.
* --degradation: el SOH baja con los ciclos equivalentes completos (EFC):
      EFC = energía cargada+descargada en celda / (2 x capacidad nominal)
      SOH = max(min_soh, SOH_inicial - fade_por_ciclo x EFC)
    La capacidad útil es capacidad_nominal x SOH, y la potencia disponible se escala
    con el SOH (aumento de resistencia interna). El SoC se mantiene relativo a la
    capacidad útil actual.
* --time-accel N: multiplica el tiempo simulado (útil para ver la degradación).

Mapa de registros (direcciones base 0, 16 bits, big-endian)
-----------------------------------------------------------
HOLDING REGISTERS (FC03 lectura, FC06/FC16 escritura)
  HR 0   Modo               0 = standby, 1 = run (sigue consigna)
  HR 1   Consigna potencia  int16,  0.1 kW  (+descarga / -carga)
  HR 2   Límite potencia    uint16, 0.1 kW  (0..potencia nominal)
  HR 3   SoC mínimo         uint16, 0.1 %
  HR 4   SoC máximo         uint16, 0.1 %
  HR 100..115  espejo de solo lectura de los input registers IR 0..15

INPUT REGISTERS (FC04, solo lectura)
  IR 0   Estado             0 = standby, 1 = cargando, 2 = descargando
  IR 1   Potencia activa    int16,  0.1 kW
  IR 2   SoC                uint16, 0.1 %
  IR 3   Potencia nominal   uint16, 0.1 kW
  IR 4   Capacidad nominal  uint16, 0.1 kWh
  IR 5   Energía almacenada uint16, 0.1 kWh
  IR 6-7 Energía cargada acumulada     uint32 (hi, lo), 0.1 kWh
  IR 8-9 Energía descargada acumulada  uint32 (hi, lo), 0.1 kWh
  IR 10  Heartbeat (contador, +1 por paso de simulación)
  IR 11  SOH                uint16, 0.1 %   (1000 si no hay degradación)
  IR 12  Ciclos equivalentes (EFC) uint16, 0.1 ciclos
  IR 13  Potencia máx. de descarga disponible uint16, 0.1 kW (SoC, SOH y límite)
  IR 14  Potencia máx. de carga disponible    uint16, 0.1 kW (SoC, SOH y límite)
  IR 15  Capacidad útil actual (nominal x SOH) uint16, 0.1 kWh

Los valores escritos se acotan (límite <= nominal, SoC en 0..100 %, etc.) y la
lectura posterior devuelve el valor realmente aplicado.
"""
import argparse
import asyncio
import logging
import math
from dataclasses import dataclass

from pymodbus.constants import ExcCodes
from pymodbus.server import StartAsyncTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

HR_MIRROR = 100
N_STATUS = 16
WRITE_FCS = (5, 6, 15, 16, 22, 23)
HR_FCS = (3, 6, 16, 22, 23)

log = logging.getLogger("battery_sim")


def to_u16(v: float) -> int:
    """Convert float to uint16, clamped to [0, 65535]."""
    return max(0, min(0xFFFF, int(round(v))))


def to_i16(v: float) -> int:
    """Convert float to int16 (as uint16 representation), clamped to [-32768, 32767]."""
    return max(-32768, min(32767, int(round(v)))) & 0xFFFF


def from_i16(v: int) -> int:
    """Convert uint16 representation to signed int16."""
    return v - 0x10000 if v >= 0x8000 else v


@dataclass
class DerateCurve:
    """Power derating curve based on SoC."""

    enabled: bool = False
    charge_from: float = 80.0
    discharge_below: float = 20.0
    min_factor: float = 0.1

    def charge_factor(self, soc: float) -> float:
        """Return charge power factor at given SoC (1.0 = full power)."""
        if not self.enabled or soc <= self.charge_from:
            return 1.0
        if self.charge_from >= 100.0:
            return 1.0
        x = min(1.0, (soc - self.charge_from) / (100.0 - self.charge_from))
        return 1.0 - (1.0 - self.min_factor) * x

    def discharge_factor(self, soc: float) -> float:
        """Return discharge power factor at given SoC (1.0 = full power)."""
        if not self.enabled or soc >= self.discharge_below:
            return 1.0
        if self.discharge_below <= 0.0:
            return 1.0
        x = max(0.0, soc) / self.discharge_below
        return self.min_factor + (1.0 - self.min_factor) * x


@dataclass
class Degradation:
    """Battery degradation model based on equivalent full cycles (EFC)."""

    enabled: bool = False
    initial_soh: float = 1.0
    fade_per_efc: float = 0.00005
    min_soh: float = 0.6


class Battery:
    """Battery model with charge/discharge dynamics, efficiency, and optional degradation."""

    def __init__(
        self,
        power_kw: float,
        capacity_kwh: float,
        soc: float,
        efficiency: float,
        ramp_kw_s: float,
        curve: DerateCurve | None = None,
        deg: Degradation | None = None,
    ) -> None:
        self.rated_kw = power_kw
        self.nominal_kwh = capacity_kwh
        self.soc = soc
        self.eta = math.sqrt(efficiency)
        self.ramp_kw_s = ramp_kw_s
        self.curve = curve or DerateCurve()
        self.deg = deg or Degradation()
        self.power_kw = 0.0
        self.e_charged_kwh = 0.0
        self.e_discharged_kwh = 0.0
        self.cell_throughput_kwh = 0.0
        self.soh = self.deg.initial_soh if self.deg.enabled else 1.0

    @property
    def capacity_kwh(self) -> float:
        """Current usable capacity (nominal * SOH)."""
        return self.nominal_kwh * self.soh

    @property
    def efc(self) -> float:
        """Equivalent full cycles."""
        return self.cell_throughput_kwh / (2.0 * self.nominal_kwh)

    @property
    def power_scale(self) -> float:
        """Power scaling factor due to degradation."""
        return self.soh if self.deg.enabled else 1.0

    def max_discharge_kw(self, limit_kw: float) -> float:
        """Maximum discharge power available considering SoC, SOH, and limit."""
        return limit_kw * self.power_scale * self.curve.discharge_factor(self.soc)

    def max_charge_kw(self, limit_kw: float) -> float:
        """Maximum charge power available considering SoC, SOH, and limit."""
        return limit_kw * self.power_scale * self.curve.charge_factor(self.soc)

    def _update_soh(self) -> None:
        """Update state of health based on EFC."""
        if self.deg.enabled:
            self.soh = max(
                self.deg.min_soh, self.deg.initial_soh - self.deg.fade_per_efc * self.efc
            )

    def step(
        self,
        dt: float,
        mode: int,
        setpoint_kw: float,
        limit_kw: float,
        soc_min: float,
        soc_max: float,
    ) -> None:
        """Advance battery simulation by dt seconds."""
        target = 0.0
        if mode == 1:
            target = max(-limit_kw, min(limit_kw, setpoint_kw))
            if target > 0:
                target = min(target, self.max_discharge_kw(limit_kw))
            elif target < 0:
                target = max(target, -self.max_charge_kw(limit_kw))
        if target > 0 and self.soc <= soc_min:
            target = 0.0
        if target < 0 and self.soc >= soc_max:
            target = 0.0

        if self.ramp_kw_s > 0:
            m = self.ramp_kw_s * dt
            self.power_kw += max(-m, min(m, target - self.power_kw))
        else:
            self.power_kw = target

        cap = self.capacity_kwh
        if self.power_kw > 0:
            e_ac = self.power_kw * dt / 3600.0
            e_cell = e_ac / self.eta
            e_cell_max = max(0.0, (self.soc - soc_min) / 100.0 * cap)
            if e_cell > e_cell_max:
                e_ac, e_cell = e_cell_max * self.eta, e_cell_max
            self.soc -= e_cell / cap * 100.0
            self.e_discharged_kwh += e_ac
            self.cell_throughput_kwh += e_cell
        elif self.power_kw < 0:
            e_ac = -self.power_kw * dt / 3600.0
            e_cell = e_ac * self.eta
            e_cell_max = max(0.0, (soc_max - self.soc) / 100.0 * cap)
            if e_cell > e_cell_max:
                e_ac, e_cell = e_cell_max / self.eta, e_cell_max
            self.soc += e_cell / cap * 100.0
            self.e_charged_kwh += e_ac
            self.cell_throughput_kwh += e_cell
        self._update_soh()

    @property
    def state(self) -> int:
        """Battery state: 0=standby, 1=charging, 2=discharging."""
        if abs(self.power_kw) < 0.05:
            return 0
        return 2 if self.power_kw > 0 else 1


class Sim:
    """Simulation state: battery + control registers + heartbeat."""

    def __init__(self, bat: Battery) -> None:
        self.bat = bat
        self.mode = 0
        self.setpoint_raw = 0
        self.limit_raw = to_u16(bat.rated_kw * 10)
        self.soc_min_raw = 50
        self.soc_max_raw = 950
        self.heartbeat = 0

    @property
    def setpoint_kw(self) -> float:
        """Power setpoint in kW (signed)."""
        return from_i16(self.setpoint_raw) / 10.0

    @property
    def limit_kw(self) -> float:
        """Power limit in kW."""
        return min(self.bat.rated_kw, self.limit_raw / 10.0)

    @property
    def soc_min(self) -> float:
        """Minimum SoC in %."""
        return min(100.0, self.soc_min_raw / 10.0)

    @property
    def soc_max(self) -> float:
        """Maximum SoC in %."""
        return max(self.soc_min, min(100.0, self.soc_max_raw / 10.0))

    def control_words(self) -> list[int]:
        """Return holding registers 0-4 values."""
        return [
            self.mode,
            self.setpoint_raw,
            self.limit_raw,
            self.soc_min_raw,
            self.soc_max_raw,
        ]

    def status_words(self) -> list[int]:
        """Return input registers 0-15 values."""
        b = self.bat
        ec = int(b.e_charged_kwh * 10) & 0xFFFFFFFF
        ed = int(b.e_discharged_kwh * 10) & 0xFFFFFFFF
        return [
            b.state,
            to_i16(b.power_kw * 10),
            to_u16(b.soc * 10),
            to_u16(b.rated_kw * 10),
            to_u16(b.nominal_kwh * 10),
            to_u16(b.soc / 100.0 * b.capacity_kwh * 10),
            (ec >> 16) & 0xFFFF,
            ec & 0xFFFF,
            (ed >> 16) & 0xFFFF,
            ed & 0xFFFF,
            self.heartbeat,
            to_u16(b.soh * 1000),
            to_u16(b.efc * 10),
            to_u16(b.max_discharge_kw(self.limit_kw) * 10),
            to_u16(b.max_charge_kw(self.limit_kw) * 10),
            to_u16(b.capacity_kwh * 10),
        ]

    def apply_write(self, addr: int, value: int) -> int:
        """Apply write to holding register addr; return actually stored value."""
        if addr == 0:
            self.mode = 1 if value == 1 else 0
            return self.mode
        if addr == 1:
            self.setpoint_raw = value & 0xFFFF
            return self.setpoint_raw
        if addr == 2:
            self.limit_raw = min(value, to_u16(self.bat.rated_kw * 10))
            return self.limit_raw
        if addr == 3:
            self.soc_min_raw = min(value, 1000)
            return self.soc_min_raw
        if addr == 4:
            self.soc_max_raw = min(value, 1000)
            return self.soc_max_raw
        raise KeyError(addr)


def make_action(sim: Sim):  # type: ignore
    """Create action callback for pymodbus SimDevice."""

    async def action(fc, start, address, count, regs, set_values):  # type: ignore
        """Handle each Modbus request: validate writes and refresh registers."""
        is_ir = fc == 4
        if fc not in HR_FCS and not is_ir:
            return None

        if set_values is not None and fc in WRITE_FCS:
            for i, _ in enumerate(set_values):
                if not 0 <= address + i <= 4:
                    return ExcCodes.ILLEGAL_ADDRESS
            for i, v in enumerate(set_values):
                set_values[i] = sim.apply_write(address + i, int(v))

        if is_ir:
            regs[0:N_STATUS] = sim.status_words()
        else:
            regs[0:5] = sim.control_words()
            regs[HR_MIRROR : HR_MIRROR + N_STATUS] = sim.status_words()
        return None

    return action


async def sim_loop(sim: Sim, dt: float, accel: float, log_every: int) -> None:
    """Main simulation loop."""
    tick = 0
    while True:
        sim.bat.step(dt * accel, sim.mode, sim.setpoint_kw, sim.limit_kw, sim.soc_min, sim.soc_max)
        sim.heartbeat = (sim.heartbeat + 1) & 0xFFFF
        tick += 1
        if log_every and tick % log_every == 0:
            b = sim.bat
            log.info(
                "modo=%d consigna=%+.1f kW | P=%+.1f kW | SoC=%.2f %% | SOH=%.2f %% | EFC=%.2f",
                sim.mode,
                sim.setpoint_kw,
                b.power_kw,
                b.soc,
                b.soh * 100,
                b.efc,
            )
        await asyncio.sleep(dt)


def build_device(unit_id: int, sim: Sim) -> SimDevice:
    """Build pymodbus SimDevice with coils, discrete inputs, holding and input registers."""
    co = [SimData(0, count=1, values=False, datatype=DataType.BITS)]
    di = [SimData(0, count=1, values=False, datatype=DataType.BITS)]
    hr = [SimData(0, count=200, values=0, datatype=DataType.REGISTERS)]
    ir = [SimData(0, count=100, values=0, datatype=DataType.REGISTERS)]
    return SimDevice(id=unit_id, simdata=(co, di, hr, ir), action=make_action(sim))


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    p = argparse.ArgumentParser(description="Simulador de batería con Modbus TCP")
    p.add_argument("--power-kw", type=float, required=True, help="Potencia nominal (kW)")
    p.add_argument(
        "--capacity-kwh",
        type=float,
        default=None,
        help="Capacidad nominal (kWh). Por defecto 2x la potencia (2 h)",
    )
    p.add_argument("--soc", type=float, default=50.0, help="SoC inicial (%%)")
    p.add_argument("--efficiency", type=float, default=0.92, help="Rendimiento round-trip (0-1)")
    p.add_argument(
        "--ramp-kw-s", type=float, default=0.0, help="Rampa máxima kW/s (0 = instantánea)"
    )
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5020)
    p.add_argument("--unit-id", type=int, default=1)
    p.add_argument("--dt", type=float, default=0.5, help="Paso de simulación (s, tiempo real)")
    p.add_argument(
        "--time-accel",
        type=float,
        default=1.0,
        help="Factor de aceleración del tiempo simulado (por defecto 1)",
    )
    p.add_argument("--log-every", type=int, default=10, help="Log de estado cada N pasos (0 = no)")

    g = p.add_argument_group("curva de potencia vs SoC (opcional)")
    g.add_argument(
        "--soc-derate",
        action="store_true",
        help="Activa la reducción de potencia según el SoC",
    )
    g.add_argument(
        "--derate-charge-from",
        type=float,
        default=None,
        help="SoC (%%) desde el que se reduce la carga (def. 80)",
    )
    g.add_argument(
        "--derate-discharge-below",
        type=float,
        default=None,
        help="SoC (%%) por debajo del que se reduce la descarga (def. 20)",
    )
    g.add_argument(
        "--derate-min-factor",
        type=float,
        default=None,
        help="Factor de potencia mínimo en los extremos, 0..1 (def. 0.1)",
    )

    d = p.add_argument_group("degradación (opcional)")
    d.add_argument("--degradation", action="store_true", help="Activa la degradación por ciclos")
    d.add_argument("--initial-soh", type=float, default=None, help="SOH inicial (%%) (def. 100)")
    d.add_argument(
        "--fade-per-cycle",
        type=float,
        default=None,
        help="Pérdida de SOH en %% por ciclo equivalente completo (def. 0.005)",
    )
    d.add_argument("--min-soh", type=float, default=None, help="Suelo del SOH (%%) (def. 60)")
    a = p.parse_args()

    if not a.soc_derate and any(
        v is not None for v in (a.derate_charge_from, a.derate_discharge_below, a.derate_min_factor)
    ):
        p.error("las opciones --derate-* requieren --soc-derate")
    if not a.degradation and any(
        v is not None for v in (a.initial_soh, a.fade_per_cycle, a.min_soh)
    ):
        p.error("--initial-soh/--fade-per-cycle/--min-soh requieren --degradation")

    if a.power_kw <= 0:
        p.error("--power-kw debe ser > 0")
    if not 0 < a.efficiency <= 1:
        p.error("--efficiency debe estar en (0, 1]")
    a.capacity = a.capacity_kwh if a.capacity_kwh else 2 * a.power_kw
    if a.capacity <= 0 or not 0 <= a.soc <= 100:
        p.error("capacidad > 0 y SoC en [0, 100]")
    if a.power_kw * 10 > 0xFFFF or a.capacity * 10 > 0xFFFF:
        p.error("potencia/capacidad exceden el rango del registro (6553.5)")
    if a.time_accel <= 0 or a.dt <= 0:
        p.error("--dt y --time-accel deben ser > 0")

    a.charge_from = 80.0 if a.derate_charge_from is None else a.derate_charge_from
    a.discharge_below = 20.0 if a.derate_discharge_below is None else a.derate_discharge_below
    a.min_factor = 0.1 if a.derate_min_factor is None else a.derate_min_factor
    if not (0 <= a.charge_from <= 100 and 0 <= a.discharge_below <= 100):
        p.error("los umbrales de derate deben estar en [0, 100]")
    if not 0 <= a.min_factor <= 1:
        p.error("--derate-min-factor debe estar en [0, 1]")

    a.soh0 = 100.0 if a.initial_soh is None else a.initial_soh
    a.fade = 0.005 if a.fade_per_cycle is None else a.fade_per_cycle
    a.soh_min = 60.0 if a.min_soh is None else a.min_soh
    if not (0 < a.soh0 <= 100 and 0 <= a.soh_min <= a.soh0):
        p.error("SOH: 0 < initial-soh <= 100 y 0 <= min-soh <= initial-soh")
    if a.fade < 0:
        p.error("--fade-per-cycle debe ser >= 0")
    return a


async def main() -> None:
    """Main entry point."""
    a = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    curve = DerateCurve(a.soc_derate, a.charge_from, a.discharge_below, a.min_factor)
    deg = Degradation(a.degradation, a.soh0 / 100.0, a.fade / 100.0, a.soh_min / 100.0)
    sim = Sim(Battery(a.power_kw, a.capacity, a.soc, a.efficiency, a.ramp_kw_s, curve, deg))

    log.info(
        "Batería: %.1f kW / %.1f kWh, SoC %.1f %%, eta_rt=%.2f -> Modbus TCP %s:%d (unit %d)",
        a.power_kw,
        a.capacity,
        a.soc,
        a.efficiency,
        a.host,
        a.port,
        a.unit_id,
    )
    if curve.enabled:
        log.info(
            "Curva SoC: carga %.0f%%, descarga %.0f%%, factor mín. %.2f",
            curve.charge_from,
            curve.discharge_below,
            curve.min_factor,
        )
    if deg.enabled:
        log.info(
            "Degradación: SOH inicial %.1f %%, %.4f %%/ciclo, suelo %.0f %%, aceleración x%g",
            a.soh0,
            a.fade,
            a.soh_min,
            a.time_accel,
        )

    task = asyncio.create_task(sim_loop(sim, a.dt, a.time_accel, a.log_every))
    try:
        await StartAsyncTcpServer(context=build_device(a.unit_id, sim), address=(a.host, a.port))
    finally:
        task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
