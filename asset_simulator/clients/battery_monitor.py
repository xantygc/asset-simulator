#!/usr/bin/env python3
"""
Monitor de batería con interfaz web en tiempo real.

Conecta a un simulador de batería vía Modbus TCP y expone los datos
mediante WebSockets para visualización en tiempo real.

Uso:
    python -m asset_simulator.clients.battery_monitor --battery-host localhost --battery-port 5020
"""

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

log = logging.getLogger("battery_monitor")


@dataclass
class BatteryData:
    """Battery telemetry data."""

    timestamp: str
    state: int  # 0=standby, 1=charging, 2=discharging
    power_kw: float
    soc_pct: float
    rated_power_kw: float
    rated_capacity_kwh: float
    stored_energy_kwh: float
    energy_charged_kwh: float
    energy_discharged_kwh: float
    heartbeat: int
    soh_pct: float
    efc: float
    max_discharge_kw: float
    max_charge_kw: float
    usable_capacity_kwh: float

    # Control registers
    mode: int
    setpoint_kw: float
    limit_kw: float
    soc_min_pct: float
    soc_max_pct: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class BatteryMonitor:
    """Monitor Modbus battery and broadcast via WebSocket."""

    def __init__(self, host: str, port: int, unit_id: int = 1) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.client = AsyncModbusTcpClient(host=host, port=port)
        self.connected = False
        self.latest_data: BatteryData | None = None

    async def connect(self) -> bool:
        """Connect to Modbus server."""
        try:
            await self.client.connect()
            self.connected = self.client.connected
            if self.connected:
                log.info(f"Connected to battery at {self.host}:{self.port}")
            else:
                log.error(f"Failed to connect to {self.host}:{self.port}")
            return self.connected
        except Exception as e:
            log.error(f"Connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from Modbus server."""
        if self.client:
            self.client.close()
            self.connected = False
            log.info("Disconnected from battery")

    def _from_i16(self, v: int) -> int:
        """Convert uint16 to signed int16."""
        return v - 0x10000 if v >= 0x8000 else v

    async def read_data(self) -> BatteryData | None:
        """Read all battery data from Modbus registers."""
        if not self.connected:
            return None

        try:
            # Read input registers (status)
            ir_result = await self.client.read_input_registers(
                address=0, count=16, device_id=self.unit_id
            )
            if ir_result.isError():
                log.error(f"Error reading input registers: {ir_result}")
                return None

            # Read holding registers (control)
            hr_result = await self.client.read_holding_registers(
                address=0, count=5, device_id=self.unit_id
            )
            if hr_result.isError():
                log.error(f"Error reading holding registers: {hr_result}")
                return None

            ir = ir_result.registers
            hr = hr_result.registers

            # Parse input registers
            state = ir[0]
            power_kw = self._from_i16(ir[1]) / 10.0
            soc = ir[2] / 10.0
            rated_power = ir[3] / 10.0
            rated_capacity = ir[4] / 10.0
            stored_energy = ir[5] / 10.0
            energy_charged = ((ir[6] << 16) | ir[7]) / 10.0
            energy_discharged = ((ir[8] << 16) | ir[9]) / 10.0
            heartbeat = ir[10]
            soh = ir[11] / 10.0
            efc = ir[12] / 10.0
            max_discharge = ir[13] / 10.0
            max_charge = ir[14] / 10.0
            usable_capacity = ir[15] / 10.0

            # Parse holding registers
            mode = hr[0]
            setpoint = self._from_i16(hr[1]) / 10.0
            limit = hr[2] / 10.0
            soc_min = hr[3] / 10.0
            soc_max = hr[4] / 10.0

            data = BatteryData(
                timestamp=datetime.now().isoformat(),
                state=state,
                power_kw=power_kw,
                soc_pct=soc,
                rated_power_kw=rated_power,
                rated_capacity_kwh=rated_capacity,
                stored_energy_kwh=stored_energy,
                energy_charged_kwh=energy_charged,
                energy_discharged_kwh=energy_discharged,
                heartbeat=heartbeat,
                soh_pct=soh,
                efc=efc,
                max_discharge_kw=max_discharge,
                max_charge_kw=max_charge,
                usable_capacity_kwh=usable_capacity,
                mode=mode,
                setpoint_kw=setpoint,
                limit_kw=limit,
                soc_min_pct=soc_min,
                soc_max_pct=soc_max,
            )

            self.latest_data = data
            return data

        except ModbusException as e:
            log.error(f"Modbus error: {e}")
            return None
        except Exception as e:
            log.error(f"Unexpected error reading data: {e}")
            return None

    async def write_control(
        self, mode: int | None = None, setpoint_kw: float | None = None
    ) -> bool:
        """Write control registers."""
        if not self.connected:
            return False

        try:
            if mode is not None:
                result = await self.client.write_register(
                    address=0, value=mode, device_id=self.unit_id
                )
                if result.isError():
                    log.error(f"Error writing mode: {result}")
                    return False

            if setpoint_kw is not None:
                value = int(setpoint_kw * 10) & 0xFFFF
                result = await self.client.write_register(
                    address=1, value=value, device_id=self.unit_id
                )
                if result.isError():
                    log.error(f"Error writing setpoint: {result}")
                    return False

            return True
        except Exception as e:
            log.error(f"Error writing control: {e}")
            return False


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket connection."""
        self.active_connections.remove(websocket)
        log.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str) -> None:
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                log.error(f"Error sending to websocket: {e}")
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


# Global instances
monitor: BatteryMonitor | None = None
manager = ConnectionManager()
app = FastAPI(title="Battery Monitor")


@app.on_event("startup")
async def startup_event() -> None:
    """Start monitoring task."""
    asyncio.create_task(monitoring_loop())


async def monitoring_loop() -> None:
    """Main monitoring loop - read data and broadcast."""
    global monitor
    if monitor is None:
        return

    while True:
        try:
            data = await monitor.read_data()
            if data:
                message = json.dumps(data.to_dict())
                await manager.broadcast(message)
        except Exception as e:
            log.error(f"Error in monitoring loop: {e}")

        await asyncio.sleep(0.5)  # 2 Hz update rate


@app.get("/", response_class=HTMLResponse)
async def get_index() -> HTMLResponse:
    """Serve main HTML page."""
    html_file = Path(__file__).parent / "static" / "battery_monitor.html"
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text())
    return HTMLResponse(content="<h1>Error: battery_monitor.html not found</h1>")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time data."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and receive control commands
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                if cmd.get("type") == "control" and monitor:
                    await monitor.write_control(
                        mode=cmd.get("mode"), setpoint_kw=cmd.get("setpoint_kw")
                    )
            except json.JSONDecodeError:
                log.error(f"Invalid JSON received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    """Get latest battery status."""
    if monitor and monitor.latest_data:
        return monitor.latest_data.to_dict()
    return {"error": "No data available"}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    p = argparse.ArgumentParser(description="Battery monitor with web interface")
    p.add_argument("--battery-host", default="localhost", help="Battery Modbus host")
    p.add_argument("--battery-port", type=int, default=5020, help="Battery Modbus port")
    p.add_argument("--battery-unit", type=int, default=1, help="Modbus unit ID")
    p.add_argument("--web-host", default="0.0.0.0", help="Web server host")
    p.add_argument("--web-port", type=int, default=8000, help="Web server port")
    return p.parse_args()


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    global monitor
    monitor = BatteryMonitor(args.battery_host, args.battery_port, args.battery_unit)

    # Connect to battery
    if not await monitor.connect():
        log.error("Failed to connect to battery. Exiting.")
        return

    log.info(f"Starting web server on {args.web_host}:{args.web_port}")
    log.info(f"Open http://localhost:{args.web_port} in your browser")

    # Import here to avoid circular import
    import uvicorn

    config = uvicorn.Config(app, host=args.web_host, port=args.web_port, log_level="info")
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        await monitor.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down...")
