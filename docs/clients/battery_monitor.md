# Battery Web Monitor

Monitor web en tiempo real para simuladores de batería con interfaz Modbus TCP.

## Características

- **Visualización en tiempo real**: Actualización cada 500ms vía WebSockets
- **Gráficos interactivos**: Chart.js para histórico de potencia, SoC, SOH
- **Panel de control**: Cambiar modo y consigna de potencia desde la web
- **Métricas completas**: SoC, SOH, potencia, energías, ciclos
- **Reconexión automática**: Se reconecta automáticamente si pierde conexión
- **Responsive**: Adaptado para desktop y móvil

## Instalación

Las dependencias ya están instaladas si seguiste la instalación del proyecto:

```bash
poetry install
```

Dependencias específicas:
- `fastapi` - Framework web
- `uvicorn` - Servidor ASGI
- `websockets` - Comunicación en tiempo real
- `pymodbus` - Cliente Modbus TCP

## Uso

### Opción 1: Script automático (recomendado)

Lanza simultáneamente el simulador de batería y el monitor web:

```bash
./examples/battery_web_demo.sh
```

Luego abre http://localhost:8000 en tu navegador.

### Opción 2: Manual

**Terminal 1** - Iniciar simulador de batería:

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --port 5020
```

**Terminal 2** - Iniciar monitor web:

```bash
poetry run python -m asset_simulator.clients.battery_monitor \
    --battery-host localhost \
    --battery-port 5020 \
    --web-port 8000
```

**Navegador** - Abrir:

```
http://localhost:8000
```

## Parámetros de Línea de Comandos

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `--battery-host` | `localhost` | Host del simulador de batería |
| `--battery-port` | `5020` | Puerto Modbus TCP del simulador |
| `--battery-unit` | `1` | ID de unidad Modbus |
| `--web-host` | `0.0.0.0` | Host del servidor web |
| `--web-port` | `8000` | Puerto del servidor web |

## Interfaz Web

### Métricas Mostradas

La interfaz muestra en tiempo real:

1. **State of Charge (SoC)**
   - Porcentaje actual
   - Barra de progreso visual
   - Energía almacenada (kWh)

2. **State of Health (SOH)**
   - Porcentaje de salud
   - Barra de progreso visual
   - Ciclos equivalentes acumulados

3. **Potencia**
   - Potencia actual (kW)
   - Estado (standby/cargando/descargando)
   - Límites de carga/descarga

4. **Especificaciones**
   - Potencia nominal
   - Capacidad nominal y útil
   - Energía cargada/descargada total

### Gráficos

**Gráfico 1: Power & SoC History**
- Eje Y izquierdo: Potencia (kW)
- Eje Y derecho: SoC (%)
- Histórico de últimos 60 puntos (~30 segundos)

**Gráfico 2: SOH & Cycles**
- Eje Y izquierdo: SOH (%)
- Eje Y derecho: Ciclos equivalentes
- Seguimiento de degradación

### Panel de Control

Desde la interfaz puedes:

1. **Cambiar modo**:
   - `Standby (0)`: Batería en reposo
   - `Run (1)`: Seguir consigna de potencia

2. **Establecer consigna de potencia**:
   - Valores positivos: Descarga (batería inyecta)
   - Valores negativos: Carga (batería consume)
   - Ejemplo: `50` = descargar 50 kW, `-30` = cargar 30 kW

## Arquitectura

```
┌─────────────┐          ┌──────────────┐          ┌─────────────┐
│   Browser   │          │   FastAPI    │          │   Battery   │
│             │◄────────►│  + WebSocket │◄────────►│  Simulator  │
│ (HTML/JS)   │   HTTP   │              │  Modbus  │  (Modbus)   │
└─────────────┘   WS     └──────────────┘   TCP    └─────────────┘
                         Monitor Loop (2 Hz)
```

### Flujo de Datos

1. **Monitor → Battery**: Cliente Modbus lee registros cada 500ms
2. **Monitor → Browser**: WebSocket broadcast de datos a todos los clientes
3. **Browser → Monitor → Battery**: Comandos de control vía WebSocket → Modbus write

### Registros Modbus Leídos

**Input Registers (0-15)**: Estado de la batería
- IR 0: Estado
- IR 1: Potencia activa
- IR 2: SoC
- IR 3-4: Potencia/capacidad nominal
- IR 5: Energía almacenada
- IR 6-9: Energías acumuladas
- IR 10: Heartbeat
- IR 11-15: SOH, ciclos, límites, capacidad útil

**Holding Registers (0-4)**: Control
- HR 0: Modo
- HR 1: Consigna de potencia
- HR 2: Límite de potencia
- HR 3-4: SoC mínimo/máximo

## API REST

Además de WebSockets, el monitor expone una API REST:

### GET `/api/status`

Obtiene el último estado de la batería en formato JSON.

```bash
curl http://localhost:8000/api/status
```

Respuesta:
```json
{
  "timestamp": "2026-10-09T16:45:00.123456",
  "state": 2,
  "power_kw": 50.0,
  "soc_pct": 48.5,
  "soh_pct": 100.0,
  "rated_power_kw": 100.0,
  "rated_capacity_kwh": 215.0,
  ...
}
```

## Desarrollo

### Estructura de Archivos

```
asset_simulator/clients/
├── __init__.py
├── battery_monitor.py          # Servidor FastAPI + cliente Modbus
└── static/
    └── battery_monitor.html    # Interfaz web
```

### Modificar la Interfaz

Edita `asset_simulator/clients/static/battery_monitor.html` para:
- Cambiar estilos CSS
- Agregar nuevas métricas
- Modificar gráficos
- Personalizar colores/diseño

### Extender Funcionalidad

Para agregar nuevas funcionalidades:

1. **Nueva métrica**: Agregar al `BatteryData` dataclass
2. **Nuevo endpoint**: Agregar ruta FastAPI en `battery_monitor.py`
3. **Nueva gráfica**: Agregar canvas y Chart.js config en HTML

## Troubleshooting

### El monitor no se conecta al simulador

```bash
# Verificar que el simulador esté corriendo
netstat -tulpn | grep 5020

# Verificar logs del simulador
# Debe mostrar "Server listening"
```

### WebSocket no conecta

- Verifica que el puerto 8000 esté libre
- Revisa la consola del navegador (F12) para errores
- Asegúrate de usar `http://localhost:8000` (no `file://`)

### Los gráficos no se actualizan

- Verifica que el modo esté en `Run (1)` si quieres ver cambios
- Establece una consigna de potencia diferente de 0
- Revisa la consola del navegador para errores de WebSocket

### Error de permisos en el puerto

```bash
# Cambiar a puerto >1024 si tienes problemas
poetry run python -m asset_simulator.clients.battery_monitor --web-port 8080
```

## Ejemplos de Uso

### Simular carga completa

1. Abre http://localhost:8000
2. Establece modo: `Run`
3. Establece consigna: `-50` (cargar a 50 kW)
4. Observa cómo el SoC aumenta en tiempo real

### Simular descarga con degradación

```bash
# Terminal 1: Simulador con degradación
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 --capacity-kwh 215 \
    --degradation --initial-soh 95 --fade-per-cycle 0.01 \
    --time-accel 100 --port 5020

# Terminal 2: Monitor
poetry run python -m asset_simulator.clients.battery_monitor

# Navegador: Establece consigna alternando +50/-50 kW
# Observa la degradación del SOH en el gráfico
```

### Integración con sistema externo

```python
import asyncio
import aiohttp

async def monitor_battery():
    async with aiohttp.ClientSession() as session:
        while True:
            async with session.get('http://localhost:8000/api/status') as resp:
                data = await resp.json()
                print(f"SoC: {data['soc_pct']}%, Power: {data['power_kw']} kW")
            await asyncio.sleep(1)

asyncio.run(monitor_battery())
```

## Despliegue

### Producción

Para despliegue en producción:

```bash
# Con más workers y log estructurado
poetry run uvicorn asset_simulator.clients.battery_monitor:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2 \
    --log-level info
```

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install poetry && poetry install --no-dev

EXPOSE 8000

CMD ["poetry", "run", "python", "-m", "asset_simulator.clients.battery_monitor", \
     "--battery-host", "battery-simulator", "--web-port", "8000"]
```

## Roadmap

- [ ] Autenticación de usuarios
- [ ] Histórico en base de datos
- [ ] Exportar datos a CSV
- [ ] Alertas configurables
- [ ] Dashboard multi-batería
- [ ] Integración con InfluxDB/Grafana

## Referencias

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [Chart.js](https://www.chartjs.org/)
