#!/usr/bin/env python3
"""
Asset Simulator - Huawei Battery Monitor
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
Monitor web para simulador Huawei SUN2000 + LUNA2000.

Proporciona interfaz web en tiempo real con:
- Dashboard con gráficos de estado
- Control de modos de operación
- Configuración de límites y parámetros
- Carga/descarga forzada
- Control de inyección

Uso:
    python3 -m asset_simulator.clients.huawei_monitor \
        --huawei-host localhost --huawei-port 5021 \
        --web-port 8001
"""
import argparse
import asyncio
import json
import logging
import subprocess
import signal
from datetime import datetime
from pathlib import Path

from aiohttp import web
from pymodbus.client import AsyncModbusTcpClient

log = logging.getLogger("huawei_monitor")


class HuaweiMonitor:
    """Monitor del simulador Huawei con interfaz web."""

    def __init__(self, modbus_host, modbus_port, modbus_unit):
        self.modbus_host = modbus_host
        self.modbus_port = modbus_port
        self.modbus_unit = modbus_unit
        self.client = None
        self.ws_clients = set()
        self.simulator_process = None
        self.current_profile_path = None

    async def connect(self):
        """Conectar al simulador Modbus."""
        self.client = AsyncModbusTcpClient(self.modbus_host, port=self.modbus_port)
        await self.client.connect()
        log.info(f"Conectado a Huawei en {self.modbus_host}:{self.modbus_port}")

    async def disconnect(self):
        """Desconectar del simulador."""
        if self.client:
            self.client.close()

    def _decode_i32(self, hi, lo):
        """Decodificar int32 desde dos registros."""
        v = (hi << 16) | lo
        return v - 0x100000000 if v >= 0x80000000 else v

    def _decode_u32(self, hi, lo):
        """Decodificar uint32 desde dos registros."""
        return (hi << 16) | lo

    def _encode_u32(self, value):
        """Codificar uint32 a dos registros [HI, LO]."""
        return [(value >> 16) & 0xFFFF, value & 0xFFFF]

    def _encode_i32(self, value):
        """Codificar int32 a dos registros [HI, LO]."""
        if value < 0:
            value = value + 0x100000000
        return [(value >> 16) & 0xFFFF, value & 0xFFFF]

    async def read_status(self):
        """Leer estado completo del sistema."""
        try:
            # Batería ESU1 (37000-37025)
            result = await self.client.read_holding_registers(37000, count=26, device_id=self.modbus_unit)
            if result.isError():
                return None

            regs = result.registers
            status = {
                "battery": {
                    "status": regs[0],
                    "status_text": ["Offline", "Espera", "Funcionando", "Fallo", "Reposo"][min(regs[0], 4)],
                    "power_w": self._decode_i32(regs[1], regs[2]),
                    "bus_voltage_v": regs[3] / 10.0,
                    "soc_pct": regs[4] / 10.0,
                    "mode": regs[6],
                    "mode_text": ["Adaptativo", "Forzado", "TOU(LG)", "Fijo", "Máx.Autoconsumo", "Inyección Total", "TOU(LUNA)"][
                        min(regs[6], 6)
                    ],
                    "rated_charge_w": self._decode_u32(regs[7], regs[8]),
                    "rated_discharge_w": self._decode_u32(regs[9], regs[10]),
                    "fault_id": regs[14],
                    "today_charged_kwh": self._decode_u32(regs[15], regs[16]) / 100.0,
                    "today_discharged_kwh": self._decode_u32(regs[17], regs[18]) / 100.0,
                    "bus_current_a": regs[21] / 10.0,
                    "temperature_c": regs[22] / 10.0,
                    "time_remaining_min": regs[25],
                },
                "timestamp": datetime.now().isoformat(),
            }

            # Potencias máximas disponibles (37046-37049)
            result = await self.client.read_holding_registers(37046, count=4, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["battery"]["max_charge_w"] = self._decode_u32(regs[0], regs[1])
                status["battery"]["max_discharge_w"] = self._decode_u32(regs[2], regs[3])

            # Contadores totales (37066-37069)
            result = await self.client.read_holding_registers(37066, count=4, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["battery"]["total_charged_kwh"] = self._decode_u32(regs[0], regs[1]) / 100.0
                status["battery"]["total_discharged_kwh"] = self._decode_u32(regs[2], regs[3]) / 100.0

            # Sistema de almacenamiento (37758-37766)
            result = await self.client.read_holding_registers(37758, count=9, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["storage"] = {
                    "capacity_wh": self._decode_u32(regs[0], regs[1]),
                    "soc_pct": regs[2] / 10.0,
                    "status": regs[4],
                    "voltage_v": regs[5] / 10.0,
                    "current_a": regs[6] / 10.0,
                    "power_w": self._decode_i32(regs[7], regs[8]),
                }

            # Medidor (37100, 37101, 37113, 37118-37122)
            result = await self.client.read_holding_registers(37100, count=3, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["meter"] = {
                    "status": regs[0],
                    "voltage_v": self._decode_i32(regs[1], regs[2]) / 10.0,
                }

            result = await self.client.read_holding_registers(37113, count=10, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["meter"]["power_w"] = self._decode_i32(regs[0], regs[1])
                status["meter"]["frequency_hz"] = regs[5] / 100.0
                status["meter"]["exported_kwh"] = self._decode_i32(regs[6], regs[7]) / 100.0
                status["meter"]["imported_kwh"] = self._decode_i32(regs[8], regs[9]) / 100.0

            # Inversor (32064, 32080)
            result = await self.client.read_holding_registers(32064, count=2, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["inverter"] = {"pv_power_w": self._decode_i32(regs[0], regs[1])}

            result = await self.client.read_holding_registers(32080, count=2, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["inverter"]["ac_power_w"] = self._decode_i32(regs[0], regs[1])

            # Registros de control (47081-47102)
            result = await self.client.read_holding_registers(47081, count=22, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["control"] = {
                    "charge_cutoff_pct": regs[0] / 10.0,
                    "discharge_cutoff_pct": regs[1] / 10.0,
                    "forced_duration_min": regs[2],
                    "forced_power_w": self._decode_i32(regs[3], regs[4]),
                    "work_mode": regs[5],
                    "grid_charge": regs[6],
                    "grid_charge_soc_pct": regs[7] / 10.0,
                    "forced_command": regs[19],
                    "target_soc_pct": regs[20] / 10.0,
                    "backup_soc_pct": regs[21] / 10.0,
                }

            # Control de inyección (47415-47418)
            result = await self.client.read_holding_registers(47415, count=4, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["control"]["injection_control"] = regs[0]
                status["control"]["injection_limit_w"] = self._decode_i32(regs[1], regs[2])
                status["control"]["injection_limit_pct"] = regs[3] / 10.0

            # Registros extendidos (60000-60004)
            result = await self.client.read_holding_registers(60000, count=6, device_id=self.modbus_unit)
            if not result.isError():
                regs = result.registers
                status["extended"] = {
                    "pv_available_w": self._decode_u32(regs[0], regs[1]),
                    "load_w": self._decode_u32(regs[2], regs[3]),
                    "sim_time": self._decode_u32(regs[4], regs[5]),
                }

            return status

        except Exception as e:
            log.error(f"Error leyendo estado: {e}")
            return None

    async def write_register(self, address, value):
        """Escribir un registro."""
        try:
            await self.client.write_register(address, value, device_id=self.modbus_unit)
            return True
        except Exception as e:
            log.error(f"Error escribiendo registro {address}: {e}")
            return False

    async def write_registers(self, address, values):
        """Escribir múltiples registros."""
        try:
            await self.client.write_registers(address, values, device_id=self.modbus_unit)
            return True
        except Exception as e:
            log.error(f"Error escribiendo registros {address}: {e}")
            return False

    async def poll_loop(self):
        """Loop de polling de estado."""
        while True:
            status = await self.read_status()
            if status:
                # Enviar a todos los clientes WebSocket
                msg = json.dumps(status)
                for ws in list(self.ws_clients):
                    try:
                        await ws.send_str(msg)
                    except Exception:
                        self.ws_clients.discard(ws)
            await asyncio.sleep(1.0)

    # --- Handlers HTTP ---
    async def handle_index(self, request):
        """Servir página principal."""
        html_file = Path(__file__).parent / "static" / "huawei_monitor_v3.html"
        return web.FileResponse(html_file)

    async def handle_ws(self, request):
        """Handler WebSocket para datos en tiempo real."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.ws_clients.add(ws)

        try:
            async for msg in ws:
                pass  # No esperamos mensajes del cliente en este caso
        finally:
            self.ws_clients.discard(ws)

        return ws

    async def handle_solar_generate(self, request):
        """Handler para generar perfil solar."""
        try:
            from asset_simulator.utils.solar_generator import SolarGenerator
            import tempfile

            data = await request.json()
            latitude = float(data.get("latitude", 39.47))
            longitude = float(data.get("longitude", -6.37))
            date = data.get("date", "2026-06-21")
            kwp = float(data.get("kwp", 6.0))
            tilt = data.get("tilt")
            if tilt is not None:
                tilt = float(tilt)
            azimuth = float(data.get("azimuth", 180))
            interval = int(data.get("interval", 15))

            # Generar perfil
            generator = SolarGenerator(latitude, longitude, kwp, tilt, azimuth)
            profile = generator.generate_profile(date, interval)

            # Guardar en archivo temporal
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
            generator.save_profile(profile, temp_file.name)
            temp_file.close()

            # Obtener estadísticas
            stats = generator.get_stats(profile)

            # Guardar ruta del perfil para usarla al arrancar el simulador
            self.current_profile_path = temp_file.name

            # Convertir perfil a formato JSON para el frontend
            profile_data = []
            for _, row in profile.iterrows():
                profile_data.append({
                    "timestamp": row["timestamp"].isoformat(),
                    "power_w": float(row["power_w"]),
                })

            return web.json_response({
                "status": "ok",
                "profile_path": temp_file.name,
                "stats": stats,
                "profile_data": profile_data,
            })
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)

    async def handle_load_generate(self, request):
        """Handler para generar perfil de consumo."""
        try:
            from asset_simulator.utils.load_generator import LoadGenerator
            import tempfile

            data = await request.json()
            profile_type = data.get("profile_type", "industrial")
            date = data.get("date", "2026-06-21")
            peak_kw = float(data.get("peak_kw", 100.0))
            interval = int(data.get("interval", 15))
            seed = data.get("seed")
            if seed is not None:
                seed = int(seed)

            # Generar perfil
            generator = LoadGenerator(profile_type, peak_kw, random_seed=seed)
            profile = generator.generate_profile(date, interval)

            # Guardar en archivo temporal
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
            generator.save_profile(profile, temp_file.name)
            temp_file.close()

            # Obtener estadísticas
            stats = generator.get_stats(profile)

            # Guardar ruta del perfil para usarla al arrancar el simulador
            self.current_load_profile_path = temp_file.name

            # Convertir perfil a formato JSON para el frontend
            profile_data = []
            for _, row in profile.iterrows():
                profile_data.append({
                    "timestamp": row["timestamp"].isoformat(),
                    "power_w": float(row["power_w"]),
                })

            return web.json_response({
                "status": "ok",
                "profile_path": temp_file.name,
                "stats": stats,
                "profile_data": profile_data,
            })
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)

    async def handle_control(self, request):
        """Handler para comandos de control."""
        data = await request.json()
        action = data.get("action")

        if action == "set_mode":
            mode = int(data.get("mode", 2))
            await self.write_register(47086, mode)

        elif action == "set_limits":
            soc_min = int(float(data.get("soc_min", 15)) * 10)
            soc_max = int(float(data.get("soc_max", 95)) * 10)
            await self.write_register(47082, soc_min)
            await self.write_register(47081, soc_max)

        elif action == "set_backup":
            soc_backup = int(float(data.get("soc_backup", 20)) * 10)
            await self.write_register(47102, soc_backup)

        elif action == "force_charge":
            target_soc = int(float(data.get("target_soc", 90)) * 10)
            power_w = int(data.get("power_w", 5000))
            await self.write_register(47101, target_soc)
            await self.write_registers(47247, self._encode_u32(power_w))
            await self.write_register(47100, 1)

        elif action == "force_discharge":
            target_soc = int(float(data.get("target_soc", 20)) * 10)
            power_w = int(data.get("power_w", 5000))
            await self.write_register(47101, target_soc)
            await self.write_registers(47249, self._encode_u32(power_w))
            await self.write_register(47100, 2)

        elif action == "stop_forced":
            await self.write_register(47100, 0)

        elif action == "set_injection":
            control = int(data.get("control", 0))
            await self.write_register(47415, control)
            if control == 6:  # Límite en kW
                limit_w = int(data.get("limit_w", 5000))
                await self.write_registers(47416, self._encode_i32(limit_w))
            elif control == 7:  # Límite en %
                limit_pct = int(float(data.get("limit_pct", 100)) * 10)
                await self.write_register(47418, limit_pct)

        elif action == "set_pv":
            pv_w = int(data.get("pv_w", 0))
            await self.write_registers(60000, self._encode_u32(pv_w))

        elif action == "set_load":
            load_w = int(data.get("load_w", 0))
            await self.write_registers(60002, self._encode_u32(load_w))

        return web.json_response({"status": "ok"})

    async def handle_simulator_start(self, request):
        """Handler para arrancar el simulador Huawei."""
        try:
            if self.simulator_process and self.simulator_process.poll() is None:
                return web.json_response({
                    "status": "error",
                    "message": "Simulador ya está corriendo"
                }, status=400)

            data = await request.json()

            power_kw = float(data.get("power_kw", 5.0))
            capacity_kwh = float(data.get("capacity_kwh", 10.0))
            inverter_kw = float(data.get("inverter_kw", 10.0))
            soc = float(data.get("soc", 50.0))
            pv_kw = float(data.get("pv_kw", 0.0))
            load_kw = float(data.get("load_kw", 2.0))
            efficiency = float(data.get("efficiency", 0.92))
            port = int(data.get("port", self.modbus_port))

            cmd = [
                "poetry", "run", "python", "-m",
                "asset_simulator.assets.batteries.huawei",
                "--power-kw", str(power_kw),
                "--capacity-kwh", str(capacity_kwh),
                "--inverter-kw", str(inverter_kw),
                "--soc", str(soc),
                "--pv-kw", str(pv_kw),
                "--load-kw", str(load_kw),
                "--efficiency", str(efficiency),
                "--port", str(port),
                "--log-every", "10"
            ]

            if self.current_profile_path:
                cmd.extend(["--pv-profile", self.current_profile_path])

            if hasattr(self, 'current_load_profile_path') and self.current_load_profile_path:
                cmd.extend(["--load-profile", self.current_load_profile_path])

            self.simulator_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=Path(__file__).parent.parent.parent
            )

            await asyncio.sleep(2)

            if self.simulator_process.poll() is not None:
                return web.json_response({
                    "status": "error",
                    "message": "El simulador falló al arrancar"
                }, status=500)

            return web.json_response({
                "status": "ok",
                "message": "Simulador arrancado correctamente",
                "pid": self.simulator_process.pid
            })

        except Exception as e:
            log.error(f"Error arrancando simulador: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    async def handle_simulator_stop(self, request):
        """Handler para detener el simulador Huawei."""
        try:
            if not self.simulator_process or self.simulator_process.poll() is not None:
                return web.json_response({
                    "status": "error",
                    "message": "Simulador no está corriendo"
                }, status=400)

            self.simulator_process.send_signal(signal.SIGTERM)

            try:
                self.simulator_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.simulator_process.kill()
                self.simulator_process.wait()

            self.simulator_process = None

            return web.json_response({
                "status": "ok",
                "message": "Simulador detenido correctamente"
            })

        except Exception as e:
            log.error(f"Error deteniendo simulador: {e}")
            return web.json_response({
                "status": "error",
                "message": str(e)
            }, status=500)

    async def handle_simulator_status(self, request):
        """Handler para obtener estado del simulador."""
        is_running = bool(self.simulator_process and self.simulator_process.poll() is None)

        return web.json_response({
            "status": "ok",
            "running": is_running,
            "pid": self.simulator_process.pid if is_running else None,
            "profile_active": self.current_profile_path is not None
        })


async def start_server(monitor, host, port):
    """Iniciar servidor web."""
    app = web.Application()
    app.router.add_get("/", monitor.handle_index)
    app.router.add_get("/ws", monitor.handle_ws)
    app.router.add_post("/control", monitor.handle_control)
    app.router.add_post("/api/solar/generate", monitor.handle_solar_generate)
    app.router.add_post("/api/load/generate", monitor.handle_load_generate)
    app.router.add_post("/api/simulator/start", monitor.handle_simulator_start)
    app.router.add_post("/api/simulator/stop", monitor.handle_simulator_stop)
    app.router.add_get("/api/simulator/status", monitor.handle_simulator_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    log.info(f"Monitor web iniciado en http://{host}:{port}")
    return runner


async def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(description="Monitor web para simulador Huawei")
    parser.add_argument("--huawei-host", default="localhost", help="Host del simulador Huawei")
    parser.add_argument("--huawei-port", type=int, default=5021, help="Puerto Modbus del simulador")
    parser.add_argument("--huawei-unit", type=int, default=1, help="Unit ID Modbus")
    parser.add_argument("--web-host", default="0.0.0.0", help="Host del servidor web")
    parser.add_argument("--web-port", type=int, default=8001, help="Puerto del servidor web")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    monitor = HuaweiMonitor(args.huawei_host, args.huawei_port, args.huawei_unit)

    await monitor.connect()

    runner = await start_server(monitor, args.web_host, args.web_port)

    # Iniciar loop de polling
    poll_task = asyncio.create_task(monitor.poll_loop())

    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        log.info("Deteniendo monitor...")
    finally:
        poll_task.cancel()
        await runner.cleanup()
        await monitor.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
