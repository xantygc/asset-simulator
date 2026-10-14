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

## Interfaz Modbus TCP

### Información General

El simulador implementa un servidor Modbus TCP estándar con las siguientes características:

- **Protocolo**: Modbus TCP (puerto por defecto: 5020)
- **Unit ID**: Configurable (por defecto: 1)
- **Byte Order**: Big-endian (network byte order)
- **Direcciones base**: 0 (indexación desde 0)
- **Function Codes soportados**:
  - `FC03` (0x03): Read Holding Registers
  - `FC04` (0x04): Read Input Registers
  - `FC06` (0x06): Write Single Register
  - `FC16` (0x10): Write Multiple Registers

### Mapa de Registros Modbus

#### Holding Registers (Lectura/Escritura)

Registros de control para configurar el comportamiento del simulador.

| Dir. | Nombre | Tipo | Escala | R/W | Rango | Descripción |
|------|--------|------|--------|-----|-------|-------------|
| **0** | Modo | uint16 | 1 | R/W | 0-1 | **0** = standby (sin control)<br>**1** = run (sigue consigna) |
| **1** | Consigna de potencia | int16 | 0.1 kW | R/W | ±P_nom | Setpoint de potencia:<br>**Positivo** = descarga<br>**Negativo** = carga<br>Rango: -32768 a +32767 (raw) |
| **2** | Límite de potencia | uint16 | 0.1 kW | R/W | 0-P_nom | Límite máximo de potencia (carga y descarga)<br>Acotado a potencia nominal |
| **3** | SoC mínimo | uint16 | 0.1 % | R/W | 0-1000 | Límite inferior de operación<br>1000 = 100.0% |
| **4** | SoC máximo | uint16 | 0.1 % | R/W | 0-1000 | Límite superior de operación<br>1000 = 100.0% |
| **100-115** | Espejo de estado | uint16 | - | R | - | Copia de solo lectura de IR 0-15 |

**Notas:**
- Los valores escritos se acotan automáticamente a rangos válidos
- La lectura posterior devuelve el valor realmente aplicado
- El registro 1 (consigna) usa representación int16 en complemento a dos

#### Input Registers (Solo Lectura)

Registros de estado y mediciones del simulador.

| Dir. | Nombre | Tipo | Escala | Unidad | Rango | Descripción |
|------|--------|------|--------|--------|-------|-------------|
| **0** | Estado | uint16 | 1 | - | 0-2 | **0** = standby<br>**1** = cargando (P < 0)<br>**2** = descargando (P > 0) |
| **1** | Potencia activa | int16 | 0.1 kW | kW | ±P_nom | Potencia actual medida<br>**+** = descarga, **-** = carga |
| **2** | SoC | uint16 | 0.1 % | % | 0-1000 | State of Charge actual |
| **3** | Potencia nominal | uint16 | 0.1 kW | kW | - | Potencia máxima de diseño |
| **4** | Capacidad nominal | uint16 | 0.1 kWh | kWh | - | Capacidad de diseño (sin degradación) |
| **5** | Energía almacenada | uint16 | 0.1 kWh | kWh | 0-C_útil | Energía actual: `SoC × C_útil / 100` |
| **6** | Energía cargada (HI) | uint16 | - | - | - | Palabra alta del contador uint32 |
| **7** | Energía cargada (LO) | uint16 | 0.1 kWh | kWh | - | Palabra baja del contador uint32 |
| **8** | Energía descargada (HI) | uint16 | - | - | - | Palabra alta del contador uint32 |
| **9** | Energía descargada (LO) | uint16 | 0.1 kWh | kWh | - | Palabra baja del contador uint32 |
| **10** | Heartbeat | uint16 | 1 | - | 0-65535 | Contador incremental por cada ciclo<br>Útil para detectar comunicación activa |
| **11** | SOH | uint16 | 0.1 % | % | 0-1000 | State of Health<br>1000 = 100% (sin degradación) |
| **12** | Ciclos equivalentes | uint16 | 0.1 | ciclos | 0-6553.5 | EFC acumulados (Equivalent Full Cycles) |
| **13** | Potencia máx. descarga | uint16 | 0.1 kW | kW | 0-P_nom | Disponible ahora según SoC, SOH y límite |
| **14** | Potencia máx. carga | uint16 | 0.1 kW | kW | 0-P_nom | Disponible ahora según SoC, SOH y límite |
| **15** | Capacidad útil actual | uint16 | 0.1 kWh | kWh | 0-C_nom | `Capacidad_nominal × SOH` |

**Notas:**
- Registros 6-9: valores uint32 ocupan 2 registros (high word, low word)
- Para reconstruir uint32: `valor = (HI << 16) | LO`
- Todos los valores escalados usan factor 0.1 (dividir valor raw entre 10)

## Convención de Signos

- **Potencia POSITIVA** (+): Descarga (la batería inyecta energía)
- **Potencia NEGATIVA** (-): Carga (la batería consume energía)

## Ejemplos de Uso con Cliente Modbus

### Configuración Inicial (Python + pymodbus)

```python
from pymodbus.client import ModbusTcpClient
import struct

# Conectar al simulador
client = ModbusTcpClient("localhost", port=5020)
if not client.connect():
    print("Error al conectar")
    exit(1)

UNIT_ID = 1  # Unit ID del simulador
```

### Lectura de Registros de Estado

#### Leer estado básico (SoC, potencia, estado)

```python
# Leer múltiples input registers (IR 0-5)
result = client.read_input_registers(0, 6, slave=UNIT_ID)
if not result.isError():
    estado = result.registers[0]  # 0=standby, 1=charging, 2=discharging
    potencia_raw = result.registers[1]
    soc_raw = result.registers[2]
    p_nominal_raw = result.registers[3]
    cap_nominal_raw = result.registers[4]
    energia_almacenada_raw = result.registers[5]
    
    # Convertir valores escalados
    # int16 para potencia (puede ser negativa)
    potencia_kw = struct.unpack('h', struct.pack('H', potencia_raw))[0] / 10.0
    soc_pct = soc_raw / 10.0
    p_nominal_kw = p_nominal_raw / 10.0
    cap_nominal_kwh = cap_nominal_raw / 10.0
    energia_kwh = energia_almacenada_raw / 10.0
    
    print(f"Estado: {['Standby', 'Cargando', 'Descargando'][estado]}")
    print(f"Potencia: {potencia_kw:+.1f} kW")
    print(f"SoC: {soc_pct:.1f}%")
    print(f"Energía: {energia_kwh:.1f} kWh de {cap_nominal_kwh:.1f} kWh")
```

#### Leer contadores de energía acumulada (uint32)

```python
# Leer energía cargada (IR 6-7)
result = client.read_input_registers(6, 2, slave=UNIT_ID)
if not result.isError():
    e_charged_hi = result.registers[0]
    e_charged_lo = result.registers[1]
    e_charged_raw = (e_charged_hi << 16) | e_charged_lo
    e_charged_kwh = e_charged_raw / 10.0
    print(f"Energía cargada total: {e_charged_kwh:.1f} kWh")

# Leer energía descargada (IR 8-9)
result = client.read_input_registers(8, 2, slave=UNIT_ID)
if not result.isError():
    e_discharged_hi = result.registers[0]
    e_discharged_lo = result.registers[1]
    e_discharged_raw = (e_discharged_hi << 16) | e_discharged_lo
    e_discharged_kwh = e_discharged_raw / 10.0
    print(f"Energía descargada total: {e_discharged_kwh:.1f} kWh")
```

#### Leer información de degradación y capacidad

```python
# Leer SOH, EFC y capacidad útil (IR 11, 12, 15)
result = client.read_input_registers(11, 1, slave=UNIT_ID)
soh_pct = result.registers[0] / 10.0

result = client.read_input_registers(12, 1, slave=UNIT_ID)
efc = result.registers[0] / 10.0

result = client.read_input_registers(15, 1, slave=UNIT_ID)
cap_util_kwh = result.registers[0] / 10.0

print(f"State of Health: {soh_pct:.1f}%")
print(f"Ciclos equivalentes: {efc:.1f}")
print(f"Capacidad útil: {cap_util_kwh:.1f} kWh")
```

#### Leer potencias disponibles

```python
# Leer potencia máxima de carga y descarga disponibles (IR 13-14)
result = client.read_input_registers(13, 2, slave=UNIT_ID)
if not result.isError():
    p_max_discharge_kw = result.registers[0] / 10.0
    p_max_charge_kw = result.registers[1] / 10.0
    
    print(f"Disponible para descarga: {p_max_discharge_kw:.1f} kW")
    print(f"Disponible para carga: {p_max_charge_kw:.1f} kW")
```

### Escritura de Registros de Control

#### Activar y configurar operación

```python
# 1. Configurar límites de SoC (HR 3-4)
# SoC mínimo: 10% -> 10.0 * 10 = 100
# SoC máximo: 90% -> 90.0 * 10 = 900
client.write_register(3, 100, slave=UNIT_ID)  # SoC min
client.write_register(4, 900, slave=UNIT_ID)  # SoC max

# 2. Configurar límite de potencia (HR 2)
# Límite: 80 kW -> 80.0 * 10 = 800
client.write_register(2, 800, slave=UNIT_ID)

# 3. Configurar consigna de potencia (HR 1)
# Descarga 50 kW -> +50.0 * 10 = +500
# Para valores negativos (carga), usar complemento a dos:
potencia_deseada_kw = 50.0  # positivo = descarga
potencia_raw = int(potencia_deseada_kw * 10)
if potencia_raw < 0:
    potencia_raw = potencia_raw & 0xFFFF  # complemento a dos
client.write_register(1, potencia_raw, slave=UNIT_ID)

# 4. Activar modo RUN (HR 0)
client.write_register(0, 1, slave=UNIT_ID)

print("Batería configurada y activada")
```

#### Comandar carga (potencia negativa)

```python
# Cargar a 30 kW -> -30.0 kW
potencia_carga_kw = -30.0
potencia_raw = int(potencia_carga_kw * 10)
# Convertir a representación uint16 (complemento a dos)
if potencia_raw < 0:
    potencia_raw = (potencia_raw + 65536) & 0xFFFF

client.write_register(1, potencia_raw, slave=UNIT_ID)
print(f"Comando de carga: {potencia_carga_kw} kW (raw: {potencia_raw})")
```

#### Detener operación

```python
# Poner en standby (HR 0 = 0)
client.write_register(0, 0, slave=UNIT_ID)
print("Batería en standby")
```

### Escritura múltiple de registros

```python
# Configurar varios parámetros de una vez (FC16)
# HR 0-4: modo, consigna, límite, soc_min, soc_max
valores = [
    1,      # HR 0: modo = run
    500,    # HR 1: consigna = +50.0 kW (descarga)
    1000,   # HR 2: límite = 100.0 kW
    100,    # HR 3: SoC min = 10.0%
    900,    # HR 4: SoC max = 90.0%
]

client.write_registers(0, valores, slave=UNIT_ID)
print("Configuración aplicada en bloque")
```

### Función auxiliar para conversión int16

```python
def int16_to_raw(valor: float, escala: float = 10.0) -> int:
    """Convierte valor con signo a representación uint16."""
    raw = int(valor * escala)
    raw = max(-32768, min(32767, raw))  # clamp a rango int16
    return raw if raw >= 0 else (raw + 65536)

def raw_to_int16(raw: int, escala: float = 10.0) -> float:
    """Convierte representación uint16 a valor con signo."""
    valor = raw if raw < 32768 else (raw - 65536)
    return valor / escala

# Uso
consigna_kw = -25.5  # carga
raw = int16_to_raw(consigna_kw)
client.write_register(1, raw, slave=UNIT_ID)

# Lectura
result = client.read_holding_registers(1, 1, slave=UNIT_ID)
consigna_leida = raw_to_int16(result.registers[0])
print(f"Consigna leída: {consigna_leida:.1f} kW")
```

### Monitoreo continuo

```python
import time

def monitorear_bateria(duracion_seg=60, intervalo_seg=2):
    """Monitorea el estado de la batería durante un tiempo."""
    inicio = time.time()
    
    while (time.time() - inicio) < duracion_seg:
        # Leer estado completo (IR 0-5, 10, 11)
        result = client.read_input_registers(0, 6, slave=UNIT_ID)
        if result.isError():
            print("Error de lectura")
            time.sleep(intervalo_seg)
            continue
            
        estado = result.registers[0]
        potencia_raw = result.registers[1]
        soc_raw = result.registers[2]
        
        potencia_kw = raw_to_int16(potencia_raw)
        soc_pct = soc_raw / 10.0
        
        # Leer heartbeat
        hb = client.read_input_registers(10, 1, slave=UNIT_ID).registers[0]
        
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] Estado: {estado} | P: {potencia_kw:+6.1f} kW | "
              f"SoC: {soc_pct:5.1f}% | HB: {hb}")
        
        time.sleep(intervalo_seg)

# Ejecutar monitoreo
monitorear_bateria(duracion_seg=30, intervalo_seg=1)

# Cerrar conexión
client.close()
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

## Integración con Sistemas de Control

Este simulador implementa el protocolo Modbus TCP estándar, lo que permite integrarlo con cualquier sistema SCADA, PLC o plataforma de gestión de energía. Los sistemas pueden:

1. **Monitorear**: Leer estado y métricas de la batería (SoC, potencia, energía)
2. **Controlar**: Escribir consignas de potencia y límites operacionales
3. **Analizar**: Monitorear degradación, ciclos y capacidad disponible
4. **Optimizar**: Gestionar la batería según estrategias de control definidas

### Compatibilidad

El simulador es compatible con cualquier cliente Modbus TCP estándar:
- **SCADA**: Ignition, WinCC, FactoryTalk, Citect
- **PLC**: Siemens S7, Allen-Bradley, Schneider Modicon
- **Software**: Python (pymodbus), Node-RED, LabVIEW
- **Librerías**: libmodbus, pymodbus, node-modbus, j2mod

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
