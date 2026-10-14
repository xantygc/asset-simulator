#!/usr/bin/env python3
"""
Asset Simulator - Huawei SUN2000/LUNA2000 Simulator
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
Simulador de inversor híbrido Huawei SUN2000 + batería LUNA2000 por Modbus TCP.

Reutiliza el modelo de batería del módulo basic.py:
rendimiento, rampa, curva de potencia vs SoC y degradación (opcionales).

Uso básico:
    python3 -m asset_simulator.assets.batteries.huawei --power-kw 5 --capacity-kwh 10 \
        --inverter-kw 10 --pv-kw 6 --load-kw 1.5 --port 5020

Fuente del mapa: "SUN2000MA Modbus Interface Definitions", Issue 08 (2024-07-04).
Las direcciones y escalas deben contrastarse con el PDF oficial antes de usarse en producción.

Convenciones de Huawei (distintas del basic.py)
-----------------------------------------------
* Potencia de batería (37001, 37765, 47084): POSITIVA = carga, NEGATIVA = descarga.
* Potencia del medidor (37113): POSITIVA = inyección a red, NEGATIVA = consumo de red.
* Enteros de 32 bits: 2 registros, palabra alta primero (HI_FIRST).
* Se lee todo con FC03 (holding); se escribe con FC06/FC16. Direcciones base 0.
* Unit id por defecto 0: el simulador responde a cualquier unit id.

Registros implementados
----------------------
Ver documentación completa en docs/batteries/huawei.md

Extensión NO Huawei (para manipular el escenario en caliente)
  60000 U32 potencia FV disponible, W (RW; con --pv-profile pasa a solo lectura)
  60002 U32 potencia de la carga, W (RW)
  60004 U32 reloj simulado, segundos Unix UTC (RO)

Producción FV a partir de perfiles
----------------------------------
Usar el módulo pv_profile.py para generar perfiles CSV de producción solar.

    python3 -m asset_simulator.assets.batteries.huawei --pv-profile perfil.csv \
        --start "2026-06-21 07:00" --time-accel 600 --inverter-kw 5 --load-kw 0.8

La FV se interpola linealmente cada paso y los datos se reutilizan para cualquier año.
Los contadores "del día" se reinician a medianoche local.

Simplificaciones y suposiciones
-------------------------------
* Inversor ideal (sin pérdidas) y sin tensión/corriente por string
* Modo 2 (y 0, 3, 5): autoconsumo. TOU no implementado
* Modo 4 (inyección total): la batería no actúa
* La batería solo se carga con excedente FV fuera de carga forzada
* Valores fuera de rango se acotan automáticamente
* Registros no implementados devuelven 0
"""
import argparse
import asyncio
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pymodbus.constants import ExcCodes
from pymodbus.server import StartAsyncTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

# Importar clases del simulador básico
from asset_simulator.assets.batteries.basic import Battery, DerateCurve, Degradation

# Importar perfil PV
from asset_simulator.utils.pv_profile import PVProfile, PVError

HI_FIRST = True  # 32 bits: palabra alta en el primer registro
N_REGS = 60010
WRITE_FCS = (6, 16, 22, 23)

log = logging.getLogger("huawei_sim")


# ---------------------------------------------------------------- codificación
def clamp(v, lo, hi):
    """Acotar valor entre límites."""
    return max(lo, min(hi, v))


def enc(kind, v):
    """Codificar valor a registros Modbus."""
    if kind == "u16":
        return [int(v) & 0xFFFF]
    if kind == "i16":
        return [int(v) & 0xFFFF]
    w = [(int(v) >> 16) & 0xFFFF, int(v) & 0xFFFF]
    return w if HI_FIRST else w[::-1]


def dec(kind, words):
    """Decodificar registros Modbus a valor."""
    if kind == "u16":
        return words[0] & 0xFFFF
    if kind == "i16":
        v = words[0] & 0xFFFF
        return v - 0x10000 if v >= 0x8000 else v
    w = words if HI_FIRST else words[::-1]
    v = ((w[0] & 0xFFFF) << 16) | (w[1] & 0xFFFF)
    if kind == "i32" and v >= 0x80000000:
        v -= 0x100000000
    return v


def enc_str(s, n_regs):
    """Codificar string a registros Modbus."""
    b = s.encode("ascii")[: 2 * n_regs].ljust(2 * n_regs, b"\x00")
    return [(b[i] << 8) | b[i + 1] for i in range(0, len(b), 2)]


@dataclass
class Reg:
    """Definición de registro de lectura/escritura."""
    addr: int
    kind: str  # u16 | i16 | u32 | i32
    lo: int
    hi: int
    default: int

    @property
    def size(self):
        """Tamaño en registros (1 o 2)."""
        return 1 if self.kind in ("u16", "i16") else 2


def rw_registers(rated_w, plant_w):
    """Definir registros de lectura/escritura."""
    R = Reg
    return [
        R(47000, "u16", 0, 2, 2),
        R(47075, "u32", 0, rated_w, rated_w),
        R(47077, "u32", 0, rated_w, rated_w),
        R(47081, "u16", 900, 1000, 1000),
        R(47082, "u16", 120, 200, 150),
        R(47083, "u16", 0, 1440, 0),
        R(47084, "i32", -rated_w, rated_w, 0),
        R(47086, "u16", 0, 5, 2),
        R(47087, "u16", 0, 1, 0),
        R(47088, "u16", 200, 1000, 500),
        R(47089, "u16", 0, 2, 0),
        R(47100, "u16", 0, 2, 0),
        R(47101, "u16", 0, 1000, 1000),
        R(47102, "u16", 0, 1000, 0),
        R(47106, "u16", 0, 2, 2),
        R(47107, "u16", 0, 65534, 1),
        R(47108, "u16", 0, 65534, 0),
        R(47242, "u32", 0, 30000, 0),
        R(47244, "u32", 0, 30000, 2000),
        R(47246, "u16", 0, 65535, 0),
        R(47247, "u32", 0, rated_w, 0),
        R(47249, "u32", 0, rated_w, 0),
        R(47299, "u16", 0, 1, 1),
        R(47415, "u16", 0, 7, 0),
        R(47416, "i32", -1_000_000, plant_w, 0),
        R(47418, "i16", 0, 1000, 0),
        R(47604, "u16", 0, 1, 0),
        R(47605, "u16", 0, 1, 0),
        R(60000, "u32", 0, 1_000_000, 0),
        R(60002, "u32", 0, 1_000_000, 0),
    ]


# ----------------------------------------------------------------- simulación
class HuaweiSim:
    """Simulación del sistema Huawei SUN2000 + LUNA2000."""

    def __init__(
        self,
        bat: Battery,
        inverter_kw,
        bus_voltage,
        pv_kw,
        load_kw,
        profile=None,
        pv_scale=1.0,
        start_utc=None,
        tz=None,
    ):
        self.bat = bat
        self.profile = profile  # PVProfile o None (FV constante/manual)
        self.pv_scale = pv_scale
        self.tz = tz or ZoneInfo("Europe/Madrid")
        self.start_utc = start_utc or datetime.now(timezone.utc)
        self.inv_kw = inverter_kw
        self.bus_v = bus_voltage
        rated_w = int(round(bat.rated_kw * 1000))
        self.rw = rw_registers(rated_w, int(round(inverter_kw * 1000)))
        self.store = {r.addr: r.default for r in self.rw}
        self.store[60000] = int(round(pv_kw * 1000))
        self.store[60002] = int(round(load_kw * 1000))
        self.owner = {}  # dirección de palabra -> Reg
        for r in self.rw:
            for j in range(r.size):
                self.owner[r.addr + j] = r
        # estado de salida
        self.pv_used_kw = 0.0
        self.ac_kw = 0.0
        self.meter_kw = 0.0  # + inyecta
        self.e_export_kwh = 0.0
        self.e_import_kwh = 0.0
        self.sim_t = 0.0  # segundos simulados desde el arranque
        self.day = self.local_date()  # los contadores "del día" cambian a medianoche local
        self.base_ch = 0.0
        self.base_dis = 0.0
        # forzado
        self.forced_prev = 0
        self.forced_t = 0.0
        self.forced_floor = 0.0

    def get(self, addr):
        """Obtener valor de registro."""
        return self.store[addr]

    # ---- reloj simulado
    def now_utc(self):
        """Timestamp UTC actual del simulador."""
        return self.start_utc + timedelta(seconds=self.sim_t)

    def local_date(self):
        """Fecha local actual del simulador."""
        return self.now_utc().astimezone(self.tz).date()

    # ---- límites efectivos
    @property
    def soc_min(self):
        """SoC mínimo efectivo (máximo entre corte de descarga y respaldo)."""
        return max(self.get(47082), self.get(47102)) / 10.0

    @property
    def soc_max(self):
        """SoC máximo efectivo."""
        return max(self.soc_min, self.get(47081) / 10.0)

    # ---- un paso de simulación
    def step(self, dt):
        """Ejecutar un paso de simulación."""
        b = self.bat
        if self.profile is not None:  # la FV sigue el perfil según el reloj simulado
            w = self.profile.power_w(self.now_utc()) * self.pv_scale
            self.store[60000] = int(clamp(round(w), 0, 1_000_000))
        pv = self.get(60000) / 1000.0
        load = self.get(60002) / 1000.0
        max_chg = self.get(47075) / 1000.0
        max_dis = self.get(47077) / 1000.0
        soc_min, soc_max = self.soc_min, self.soc_max

        # --- carga/descarga forzada
        cmd = self.get(47100)
        if cmd != self.forced_prev:
            self.forced_t = 0.0
            if cmd == 2:
                tgt = self.get(47101) / 10.0
                self.forced_floor = tgt if tgt < b.soc else soc_min
            self.forced_prev = cmd
        want = None
        if cmd in (1, 2):
            self.forced_t += dt
            p = abs(self.get(47084)) / 1000.0
            if p == 0:
                p = self.get(47247 if cmd == 1 else 47249) / 1000.0
            if p == 0:
                p = max_chg if cmd == 1 else max_dis
            dur = self.get(47083)
            if dur > 0:  # con duración: termina por tiempo
                done = self.forced_t >= dur * 60.0
            elif cmd == 1:  # sin duración: hasta el SOC objetivo
                done = b.soc >= self.get(47101) / 10.0
            else:
                done = b.soc <= self.forced_floor
            if done:
                self.store[47100] = 0
                self.forced_prev = 0
                cmd = 0
            else:
                want = -p if cmd == 1 else p  # interno: + descarga
        if want is None:
            mode = self.get(47086)
            if mode in (0, 2, 3, 5):  # autoconsumo (TOU aproximado)
                want = load - pv
            else:  # 1 fijo (sin periodos) / 4 inyección total
                want = 0.0
        want = clamp(want, -max_chg, max_dis)
        b.step(dt, 1, want, b.rated_kw, soc_min, soc_max)
        bat_kw = b.power_kw  # + descarga

        # --- inversor, vertido y red
        ctl = self.get(47415)
        exp_max = None
        if ctl == 5:
            exp_max = 0.0
        elif ctl == 6:
            exp_max = max(0.0, self.get(47416) / 1000.0)
        elif ctl == 7:
            exp_max = self.get(47418) / 1000.0 * self.inv_kw

        pv_used = pv
        ac = pv_used + bat_kw
        if ac > self.inv_kw:  # el inversor no da más: se recorta FV
            pv_used = max(0.0, pv_used - (ac - self.inv_kw))
            ac = min(pv_used + bat_kw, self.inv_kw)
        exp = ac - load
        if exp_max is not None and exp > exp_max:  # límite de inyección: se recorta FV
            pv_used = max(0.0, pv_used - (exp - exp_max))
            ac = pv_used + bat_kw
        self.pv_used_kw = pv_used
        self.ac_kw = ac
        self.meter_kw = ac - load
        if self.meter_kw > 0:
            self.e_export_kwh += self.meter_kw * dt / 3600.0
        else:
            self.e_import_kwh += -self.meter_kw * dt / 3600.0

        # --- contadores diarios (día local simulado)
        self.sim_t += dt
        day = self.local_date()
        if day != self.day:
            self.day = day
            self.base_ch, self.base_dis = b.e_charged_kwh, b.e_discharged_kwh

    # ---- registros de solo lectura
    def read_only_words(self):
        """Generar valores de registros de solo lectura."""
        b = self.bat
        p_w = -b.power_kw * 1000.0  # Huawei: + carga
        status = 2 if abs(b.power_kw) >= 0.05 else 1
        mode_w = self.get(47086)
        mode_r = {0: 0, 1: 3, 2: 4, 3: 2, 4: 5, 5: 6}.get(mode_w, 0)
        if self.get(47100) in (1, 2):
            mode_r = 1
        cap = b.capacity_kwh
        if b.power_kw < 0:
            left = max(0.0, (self.soc_max - b.soc) / 100.0 * cap)
        elif b.power_kw > 0:
            left = max(0.0, (b.soc - self.soc_min) / 100.0 * cap)
        else:
            left = 0.0
        minutes = int(clamp(left / abs(b.power_kw) * 60.0, 0, 1440)) if b.power_kw else 0
        lim = min(b.rated_kw, self.inv_kw)
        soc10 = int(round(b.soc * 10))
        i_bus = p_w / self.bus_v * 10.0
        today_ch = (b.e_charged_kwh - self.base_ch) * 100
        today_dis = (b.e_discharged_kwh - self.base_dis) * 100
        tot_ch, tot_dis = b.e_charged_kwh * 100, b.e_discharged_kwh * 100
        out = [
            (37000, enc("u16", status)),
            (37001, enc("i32", round(p_w))),
            (37003, enc("u16", round(self.bus_v * 10))),
            (37004, enc("u16", soc10)),
            (37006, enc("u16", mode_r)),
            (37007, enc("u32", round(b.rated_kw * 1000))),
            (37009, enc("u32", round(b.rated_kw * 1000))),
            (37014, enc("u16", 0)),
            (37015, enc("u32", round(today_ch))),
            (37017, enc("u32", round(today_dis))),
            (37021, enc("i16", round(i_bus))),
            (37022, enc("i16", 250)),
            (37025, enc("u16", minutes)),
            (37026, enc_str("SIM-DCDC-1.0", 10)),
            (37036, enc_str("SIM-BMS-1.0", 10)),
            (37046, enc("u32", round(b.max_charge_kw(lim) * 1000))),
            (37048, enc("u32", round(b.max_discharge_kw(lim) * 1000))),
            (37052, enc_str("SIM0000000001", 10)),
            (37066, enc("u32", round(tot_ch))),
            (37068, enc("u32", round(tot_dis))),
            (37758, enc("u32", round(b.nominal_kwh * 1000))),
            (37760, enc("u16", soc10)),
            (37762, enc("u16", status)),
            (37763, enc("u16", round(self.bus_v * 10))),
            (37764, enc("i16", round(i_bus))),
            (37765, enc("i32", round(p_w))),
            (37780, enc("u32", round(tot_ch))),
            (37782, enc("u32", round(tot_dis))),
            (37784, enc("u32", round(today_ch))),
            (37786, enc("u32", round(today_dis))),
            (37100, enc("u16", 1)),
            (37101, enc("i32", 2300)),
            (37113, enc("i32", round(self.meter_kw * 1000))),
            (37118, enc("i16", 5000)),
            (37119, enc("i32", round(self.e_export_kwh * 100))),
            (37121, enc("i32", round(self.e_import_kwh * 100))),
            (37125, enc("u16", 0)),
            (32064, enc("i32", round(self.pv_used_kw * 1000))),
            (32080, enc("i32", round(self.ac_kw * 1000))),
            (60004, enc("u32", int(self.now_utc().timestamp()))),
        ]
        return out

    def refresh(self, regs):
        """Actualizar todos los registros."""
        for addr, words in self.read_only_words():
            regs[addr : addr + len(words)] = words
        for r in self.rw:
            regs[r.addr : r.addr + r.size] = enc(r.kind, self.store[r.addr])

    # ---- escrituras
    def apply_write(self, address, words):
        """Aplicar escritura de registros."""
        n = len(words)
        touched = []
        for i in range(n):
            r = self.owner.get(address + i)
            if r is None:
                return ExcCodes.ILLEGAL_ADDRESS
            if r not in touched:
                touched.append(r)
        if self.profile is not None and any(r.addr == 60000 for r in touched):
            return ExcCodes.ILLEGAL_ADDRESS  # 60000 es del perfil FV (solo lectura)
        for r in touched:
            cur = enc(r.kind, self.store[r.addr])
            for j in range(r.size):
                a = r.addr + j
                if address <= a < address + n:
                    cur[j] = int(words[a - address]) & 0xFFFF
            val = clamp(dec(r.kind, cur), r.lo, r.hi)
            self.store[r.addr] = val
            new = enc(r.kind, val)
            for j in range(r.size):
                a = r.addr + j
                if address <= a < address + n:
                    words[a - address] = new[j]
        return None


def make_action(sim: HuaweiSim):
    """Crear callback de acción para pymodbus SimDevice."""

    async def action(fc, start, address, count, regs, set_values):
        """Manejar cada request Modbus: validar escrituras y refrescar registros."""
        if set_values is not None:
            if fc not in WRITE_FCS:
                return ExcCodes.ILLEGAL_ADDRESS
            if err := sim.apply_write(address, set_values):
                return err
        sim.refresh(regs)
        return None

    return action


async def sim_loop(sim: HuaweiSim, dt, accel, log_every):
    """Loop principal de simulación."""
    tick = 0
    while True:
        sim.step(dt * accel)
        tick += 1
        if log_every and tick % log_every == 0:
            b = sim.bat
            log.info(
                "SOC=%.1f%% bat=%+.2fkW(Huawei +carga) PV=%.2fkW AC=%.2fkW red=%+.2fkW(+inyecta) modo=%d forzado=%d",
                b.soc,
                -b.power_kw,
                sim.pv_used_kw,
                sim.ac_kw,
                sim.meter_kw,
                sim.get(47086),
                sim.get(47100),
            )
        await asyncio.sleep(dt)


def parse_args():
    """Parsear argumentos de línea de comandos."""
    p = argparse.ArgumentParser(description="Simulador Huawei SUN2000 + LUNA2000 por Modbus TCP")
    p.add_argument("--power-kw", type=float, default=5.0, help="Potencia nominal de la batería (kW)")
    p.add_argument("--capacity-kwh", type=float, default=10.0, help="Capacidad nominal (kWh)")
    p.add_argument("--inverter-kw", type=float, default=10.0, help="Potencia nominal del inversor (kW)")
    p.add_argument("--pv-kw", type=float, default=0.0, help="Potencia FV disponible inicial (kW)")
    p.add_argument("--load-kw", type=float, default=0.0, help="Consumo inicial (kW)")
    p.add_argument("--soc", type=float, default=50.0, help="SoC inicial (%%)")
    p.add_argument("--efficiency", type=float, default=0.92, help="Rendimiento round-trip (0-1)")
    p.add_argument("--ramp-kw-s", type=float, default=0.0, help="Rampa máxima kW/s (0 = instantánea)")
    p.add_argument("--bus-voltage", type=float, default=600.0, help="Tensión de bus simulada (V)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5021)
    p.add_argument("--unit-id", type=int, default=0, help="0 = responde a cualquier unit id")
    p.add_argument("--dt", type=float, default=0.5, help="Paso de simulación (s, tiempo real)")
    p.add_argument("--time-accel", type=float, default=1.0, help="Aceleración del tiempo simulado")
    p.add_argument("--log-every", type=int, default=10, help="Log cada N pasos (0 = no)")

    c = p.add_argument_group("producción FV desde un perfil (opcional)")
    c.add_argument(
        "--pv-profile",
        default=None,
        metavar="CSV",
        help="CSV de perfil PV. La FV sigue el reloj simulado y 60000 pasa a solo lectura",
    )
    c.add_argument(
        "--pv-scale",
        type=float,
        default=1.0,
        help="Factor sobre el perfil, p. ej. 0.5 si el CSV era para el doble de kWp",
    )
    c.add_argument(
        "--start",
        default=None,
        metavar="'AAAA-MM-DD HH:MM'",
        help="Instante inicial del reloj simulado, en hora local (def. ahora)",
    )
    c.add_argument("--tz", default="Europe/Madrid", help="Zona horaria de --start (def. Europe/Madrid)")

    g = p.add_argument_group("curva de potencia vs SoC (opcional)")
    g.add_argument("--soc-derate", action="store_true")
    g.add_argument("--derate-charge-from", type=float, default=None)
    g.add_argument("--derate-discharge-below", type=float, default=None)
    g.add_argument("--derate-min-factor", type=float, default=None)
    d = p.add_argument_group("degradación (opcional)")
    d.add_argument("--degradation", action="store_true")
    d.add_argument("--initial-soh", type=float, default=None)
    d.add_argument("--fade-per-cycle", type=float, default=None)
    d.add_argument("--min-soh", type=float, default=None)
    a = p.parse_args()

    if not a.soc_derate and any(
        v is not None for v in (a.derate_charge_from, a.derate_discharge_below, a.derate_min_factor)
    ):
        p.error("las opciones --derate-* requieren --soc-derate")
    if not a.degradation and any(v is not None for v in (a.initial_soh, a.fade_per_cycle, a.min_soh)):
        p.error("--initial-soh/--fade-per-cycle/--min-soh requieren --degradation")
    if min(a.power_kw, a.capacity_kwh, a.inverter_kw, a.bus_voltage, a.dt, a.time_accel) <= 0:
        p.error("potencias, capacidad, tensión, --dt y --time-accel deben ser > 0")
    if a.pv_kw < 0 or a.load_kw < 0:
        p.error("--pv-kw y --load-kw deben ser >= 0")
    if a.pv_scale <= 0:
        p.error("--pv-scale debe ser > 0")
    if a.pv_profile is None and a.pv_scale != 1.0:
        p.error("--pv-scale requiere --pv-profile")
    if a.pv_profile is not None and a.pv_kw:
        p.error("--pv-kw y --pv-profile son excluyentes (la FV la marca el perfil)")
    try:
        a.tzinfo = ZoneInfo(a.tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        p.error(f"zona horaria desconocida: {a.tz!r} (en Windows: pip install tzdata)")
    a.start_utc = None
    if a.start is not None:
        try:
            local = datetime.strptime(a.start, "%Y-%m-%d %H:%M").replace(tzinfo=a.tzinfo)
        except ValueError:
            p.error("--start debe tener el formato 'AAAA-MM-DD HH:MM'")
        a.start_utc = local.astimezone(timezone.utc)
    if not 0 < a.efficiency <= 1 or not 0 <= a.soc <= 100:
        p.error("--efficiency en (0,1] y --soc en [0,100]")
    a.charge_from = 80.0 if a.derate_charge_from is None else a.derate_charge_from
    a.discharge_below = 20.0 if a.derate_discharge_below is None else a.derate_discharge_below
    a.min_factor = 0.1 if a.derate_min_factor is None else a.derate_min_factor
    if not (0 <= a.charge_from <= 100 and 0 <= a.discharge_below <= 100 and 0 <= a.min_factor <= 1):
        p.error("umbrales de derate en [0,100] y factor mínimo en [0,1]")
    a.soh0 = 100.0 if a.initial_soh is None else a.initial_soh
    a.fade = 0.005 if a.fade_per_cycle is None else a.fade_per_cycle
    a.soh_min = 60.0 if a.min_soh is None else a.min_soh
    if not (0 < a.soh0 <= 100 and 0 <= a.soh_min <= a.soh0 and a.fade >= 0):
        p.error("SOH: 0 < initial-soh <= 100, 0 <= min-soh <= initial-soh, fade >= 0")
    return a


async def main():
    """Punto de entrada principal."""
    a = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    curve = DerateCurve(a.soc_derate, a.charge_from, a.discharge_below, a.min_factor)
    deg = Degradation(a.degradation, a.soh0 / 100.0, a.fade / 100.0, a.soh_min / 100.0)
    bat = Battery(a.power_kw, a.capacity_kwh, a.soc, a.efficiency, a.ramp_kw_s, curve, deg)
    profile = None
    if a.pv_profile:
        try:
            profile = PVProfile.from_csv(a.pv_profile)
        except (PVError, OSError, ValueError, KeyError) as e:
            sys.exit(f"error: no se pudo cargar el perfil FV {a.pv_profile}: {e}")
    sim = HuaweiSim(bat, a.inverter_kw, a.bus_voltage, a.pv_kw, a.load_kw, profile, a.pv_scale, a.start_utc, a.tzinfo)
    if profile is not None:
        log.info(
            "Perfil FV: %s (fuente %s, %s kWp, escala x%g) | reloj simulado desde %s (%s)",
            a.pv_profile,
            profile.meta.get("source", "?"),
            profile.meta.get("kwp", "?"),
            a.pv_scale,
            sim.now_utc().astimezone(a.tzinfo).strftime("%Y-%m-%d %H:%M"),
            a.tz,
        )

    log.info(
        "Huawei SUN2000 %.1f kW + LUNA %.1f kW / %.1f kWh | FV=%.2f kW carga=%.2f kW | Modbus TCP %s:%d (unit %d)",
        a.inverter_kw,
        a.power_kw,
        a.capacity_kwh,
        a.pv_kw,
        a.load_kw,
        a.host,
        a.port,
        a.unit_id,
    )

    sd = SimData(0, count=N_REGS, values=0, datatype=DataType.REGISTERS)
    device = SimDevice(id=a.unit_id, simdata=[sd], action=make_action(sim))
    task = asyncio.create_task(sim_loop(sim, a.dt, a.time_accel, a.log_every))
    try:
        await StartAsyncTcpServer(context=device, address=(a.host, a.port))
    finally:
        task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
