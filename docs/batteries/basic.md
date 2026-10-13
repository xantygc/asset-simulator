# Battery Simulator - Basic

Simulador de batería con interfaz Modbus TCP que permite simular el comportamiento de sistemas de almacenamiento de energía.

## Características

- **Simulación física**: Modelo de carga/descarga con eficiencia configurable
- **Control Modbus TCP**: Interfaz estándar para integración con sistemas SCADA
- **Curva de potencia vs SoC**: Opcional, reduce potencia en extremos de carga
- **Degradación**: Modelo opcional de pérdida de capacidad por ciclos
- **Límites operacionales**: SoC mínimo/máximo, rampa de potencia

## Instalación

```bash
cd asset-simulator
poetry install
```

## Uso Básico

### Simulador simple (100 kW / 215 kWh)

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --port 5020
```

### Con curva de potencia dependiente del SoC

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --soc-derate \
    --derate-charge-from 80 \
    --derate-discharge-below 20 \
    --derate-min-factor 0.1 \
    --port 5020
```

### Con degradación por ciclos

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --degradation \
    --initial-soh 97 \
    --fade-per-cycle 0.005 \
    --min-soh 60 \
    --time-accel 100 \
    --port 5020
```

## Parámetros de Línea de Comandos

### Básicos

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--power-kw` | float | **requerido** | Potencia nominal (kW) |
| `--capacity-kwh` | float | `2 × power-kw` | Capacidad nominal (kWh) |
| `--soc` | float | `50.0` | SoC inicial (%) |
| `--efficiency` | float | `0.92` | Rendimiento round-trip (0-1) |
| `--ramp-kw-s` | float | `0.0` | Rampa máxima kW/s (0 = instantánea) |

### Red

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--host` | str | `0.0.0.0` | Dirección de escucha |
| `--port` | int | `5020` | Puerto TCP |
| `--unit-id` | int | `1` | ID de unidad Modbus |

### Simulación

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--dt` | float | `0.5` | Paso de simulación (s) |
| `--time-accel` | float | `1.0` | Aceleración del tiempo |
| `--log-every` | int | `10` | Log cada N pasos (0 = desactivado) |

### Curva de potencia vs SoC (opcional)

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--soc-derate` | flag | - | Activa reducción de potencia por SoC |
| `--derate-charge-from` | float | `80.0` | SoC desde donde se reduce la carga (%) |
| `--derate-discharge-below` | float | `20.0` | SoC bajo el cual se reduce la descarga (%) |
| `--derate-min-factor` | float | `0.1` | Factor de potencia mínimo (0-1) |

### Degradación (opcional)

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--degradation` | flag | - | Activa degradación por ciclos |
| `--initial-soh` | float | `100.0` | SOH inicial (%) |
| `--fade-per-cycle` | float | `0.005` | Pérdida de SOH por ciclo (%) |
| `--min-soh` | float | `60.0` | Suelo del SOH (%) |

## Mapa de Registros Modbus

### Holding Registers (FC03 lectura, FC06/FC16 escritura)

| Dirección | Nombre | Tipo | Escala | Descripción |
|-----------|--------|------|--------|-------------|
| **0** | Modo | uint16 | - | 0 = standby, 1 = run |
| **1** | Consigna potencia | int16 | 0.1 kW | Positivo = descarga, negativo = carga |
| **2** | Límite potencia | uint16 | 0.1 kW | Límite máximo (0 a potencia nominal) |
| **3** | SoC mínimo | uint16 | 0.1 % | Límite inferior de SoC |
| **4** | SoC máximo | uint16 | 0.1 % | Límite superior de SoC |
| **100-115** | - | uint16 | - | Espejo de IR 0-15 (solo lectura) |

### Input Registers (FC04, solo lectura)

| Dirección | Nombre | Tipo | Escala | Descripción |
|-----------|--------|------|--------|-------------|
| **0** | Estado | uint16 | - | 0 = standby, 1 = cargando, 2 = descargando |
| **1** | Potencia activa | int16 | 0.1 kW | Potencia actual |
| **2** | SoC | uint16 | 0.1 % | State of Charge |
| **3** | Potencia nominal | uint16 | 0.1 kW | Capacidad de potencia |
| **4** | Capacidad nominal | uint16 | 0.1 kWh | Capacidad de energía |
| **5** | Energía almacenada | uint16 | 0.1 kWh | Energía actual en la batería |
| **6-7** | Energía cargada | uint32 | 0.1 kWh | Total acumulado (hi, lo) |
| **8-9** | Energía descargada | uint32 | 0.1 kWh | Total acumulado (hi, lo) |
| **10** | Heartbeat | uint16 | - | Contador incremental |
| **11** | SOH | uint16 | 0.1 % | State of Health |
| **12** | Ciclos equivalentes | uint16 | 0.1 ciclos | EFC acumulados |
| **13** | Potencia máx. descarga | uint16 | 0.1 kW | Disponible según SoC/SOH/límite |
| **14** | Potencia máx. carga | uint16 | 0.1 kW | Disponible según SoC/SOH/límite |
| **15** | Capacidad útil | uint16 | 0.1 kWh | Nominal × SOH |

## Convención de Signos

- **Potencia POSITIVA** (+): Descarga (la batería inyecta energía)
- **Potencia NEGATIVA** (-): Carga (la batería consume energía)

## Ejemplos de Uso con Cliente Modbus

### Python (pymodbus)

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("localhost", port=5020)
client.connect()

# Activar modo run
client.write_register(0, 1, slave=1)

# Configurar consigna de 50 kW descarga (50.0 kW × 10 = 500)
client.write_register(1, 500, slave=1)

# Leer SoC actual (registro 2 en input registers)
result = client.read_input_registers(2, 1, slave=1)
soc = result.registers[0] / 10.0  # dividir por 10 para obtener %
print(f"SoC: {soc}%")

client.close()
```

### Lectura de energía acumulada (uint32)

```python
# Leer energía descargada (IR 8-9)
result = client.read_input_registers(8, 2, slave=1)
e_discharged_raw = (result.registers[0] << 16) | result.registers[1]
e_discharged_kwh = e_discharged_raw / 10.0
print(f"Energía descargada: {e_discharged_kwh} kWh")
```

## Modelo Físico

### Eficiencia

El simulador usa eficiencia unidireccional (`η = √efficiency`):

- **Carga**: `E_celda = E_AC × η`
- **Descarga**: `E_AC = E_celda × η`

Para `efficiency=0.92`, `η ≈ 0.959` (95.9% en cada dirección).

### Degradación

El modelo calcula ciclos equivalentes (EFC):

```
EFC = E_throughput_celda / (2 × Capacidad_nominal)
SOH = max(SOH_min, SOH_inicial - fade_per_efc × EFC)
```

La capacidad útil se reduce a `Capacidad_nominal × SOH`.

### Curva de Potencia vs SoC

Cuando está activa (`--soc-derate`):

- **Carga**: potencia al 100% hasta `derate-charge-from`, luego baja linealmente hasta `min-factor` al 100% SoC
- **Descarga**: potencia al 100% desde `derate-discharge-below`, baja linealmente hasta `min-factor` al 0% SoC

## Tests

```bash
poetry run pytest tests/assets/batteries/test_basic.py -v
```

## Integración con Profitflex

Este simulador está diseñado para conectarse con dispositivos Profitflex mediante el protocolo Modbus TCP estándar. Los dispositivos Profitflex pueden:

1. Leer el estado y métricas de la batería (SoC, potencia, energía)
2. Escribir consignas de potencia y límites operacionales
3. Monitorear degradación y capacidad disponible
4. Gestionar la batería según estrategias de control definidas

## Troubleshooting

### El simulador no arranca

- Verifica que el puerto no esté en uso: `netstat -tulpn | grep 5020`
- Asegúrate de tener permisos para abrir el puerto

### El cliente no puede conectar

- Verifica firewall: `sudo ufw allow 5020/tcp`
- Prueba conexión local primero: `--host 127.0.0.1`

### La batería no responde a consignas

- Verifica que el modo esté en `1` (run)
- Comprueba los límites de SoC (min/max)
- Revisa el límite de potencia (registro 2)

## Referencias

- [Protocolo Modbus](https://modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf)
- [pymodbus Documentation](https://pymodbus.readthedocs.io/)
