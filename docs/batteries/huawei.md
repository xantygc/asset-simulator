# Simulador Huawei SUN2000 + LUNA2000

Simulador de inversor híbrido Huawei SUN2000 con batería LUNA2000, implementando la interfaz Modbus TCP completa según las especificaciones oficiales de Huawei.

## Características

- **Sistema completo**: Inversor híbrido + batería + medidor de red + FV
- **Protocolo Modbus TCP**: Compatible con especificación Huawei SUN2000MA
- **Modelo físico avanzado**: Reutiliza el modelo de batería con degradación y curvas
- **Perfiles solares**: Soporte para perfiles de producción FV realistas
- **Modos de operación**: Autoconsumo, TOU, inyección total, forzado
- **Control de inyección**: Límites configurables (kW, %, inyección cero)
- **Reloj simulado**: Aceleración de tiempo para pruebas rápidas

## Instalación

```bash
cd asset-simulator
poetry install
```

## Uso Básico

### Sistema simple (5 kW batería + 10 kW inversor)

```bash
poetry run python -m asset_simulator.assets.batteries.huawei \
    --power-kw 5 \
    --capacity-kwh 10 \
    --inverter-kw 10 \
    --pv-kw 6 \
    --load-kw 1.5 \
    --port 5021
```

### Con perfil solar real

```bash
# Generar perfil solar (requiere herramienta pvlib)
# python3 pv_profile_generator.py --lat 39.47 --lon -6.37 --kwp 6 --out perfil.csv

poetry run python -m asset_simulator.assets.batteries.huawei \
    --pv-profile perfil.csv \
    --start "2026-06-21 07:00" \
    --time-accel 600 \
    --inverter-kw 5 \
    --capacity-kwh 10 \
    --load-kw 0.8 \
    --port 5021
```

## Parámetros de Línea de Comandos

### Básicos

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--power-kw` | float | `5.0` | Potencia nominal de la batería (kW) |
| `--capacity-kwh` | float | `10.0` | Capacidad nominal (kWh) |
| `--inverter-kw` | float | `10.0` | Potencia nominal del inversor (kW) |
| `--pv-kw` | float | `0.0` | Potencia FV disponible inicial (kW) |
| `--load-kw` | float | `0.0` | Consumo inicial (kW) |
| `--soc` | float | `50.0` | SoC inicial (%) |
| `--efficiency` | float | `0.92` | Rendimiento round-trip (0-1) |
| `--ramp-kw-s` | float | `0.0` | Rampa máxima kW/s |
| `--bus-voltage` | float | `600.0` | Tensión de bus simulada (V) |

### Red y comunicación

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--host` | str | `0.0.0.0` | Dirección de escucha |
| `--port` | int | `5021` | Puerto TCP |
| `--unit-id` | int | `0` | ID Modbus (0 = responde a todos) |

### Simulación

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--dt` | float | `0.5` | Paso de simulación (s) |
| `--time-accel` | float | `1.0` | Aceleración del tiempo |
| `--log-every` | int | `10` | Log cada N pasos |

### Perfil solar (opcional)

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `--pv-profile` | str | - | Archivo CSV con perfil FV |
| `--pv-scale` | float | `1.0` | Factor de escala del perfil |
| `--start` | str | ahora | Hora inicial ('YYYY-MM-DD HH:MM') |
| `--tz` | str | `Europe/Madrid` | Zona horaria |

## Convenciones Huawei

⚠️ **Importante**: Las convenciones de signo de Huawei son **diferentes** al simulador básico:

### Potencia de batería
- **POSITIVA** (+): Batería cargando
- **NEGATIVA** (-): Batería descargando

### Potencia del medidor
- **POSITIVA** (+): Inyección a red (exportando)
- **NEGATIVA** (-): Consumo de red (importando)

### Formato de datos
- Enteros de 32 bits: 2 registros, palabra alta primero (big-endian)
- Unit ID 0: El simulador responde a cualquier unit ID
- Function codes: FC03 (lectura), FC06/FC16 (escritura)

## Interfaz Modbus TCP

### Información General

- **Protocolo**: Modbus TCP
- **Puerto por defecto**: 5021
- **Unit ID**: 0 (responde a todos)
- **Byte Order**: Big-endian (HI_FIRST)
- **Direcciones base**: 0
- **Fuente**: SUN2000MA Modbus Interface Definitions, Issue 08 (2024-07-04)

### Mapa de Registros - Batería (ESU 1)

#### Registros de estado (Solo lectura)

| Dirección | Tipo | Escala | Unidad | Descripción |
|-----------|------|--------|--------|-------------|
| **37000** | U16 | 1 | - | Estado: 0=offline, 1=espera, 2=funcionando, 3=fallo, 4=reposo |
| **37001-37002** | I32 | 1 | W | Potencia carga/descarga (**+carga**, **-descarga**) |
| **37003** | U16 | 0.1 | V | Tensión de bus DC |
| **37004** | U16 | 0.1 | % | State of Charge (SoC) |
| **37006** | U16 | 1 | - | Modo de trabajo (lectura): 0=adaptativo, 1=forzado, 2=TOU(LG), 3=fijo, 4=máx.autoconsumo, 5=inyección total, 6=TOU(LUNA) |
| **37007-37008** | U32 | 1 | W | Potencia nominal de carga |
| **37009-37010** | U32 | 1 | W | Potencia nominal de descarga |
| **37014** | U16 | 1 | - | ID de fallo (0 = sin fallo) |
| **37015-37016** | U32 | 0.01 | kWh | Energía cargada en el día |
| **37017-37018** | U32 | 0.01 | kWh | Energía descargada en el día |
| **37021** | I16 | 0.1 | A | Corriente de bus DC |
| **37022** | I16 | 0.1 | °C | Temperatura de batería |
| **37025** | U16 | 1 | min | Tiempo restante de carga/descarga |
| **37026-37035** | STRING | - | - | Versión DC/DC (10 registros, ASCII) |
| **37036-37045** | STRING | - | - | Versión BMS (10 registros, ASCII) |
| **37046-37047** | U32 | 1 | W | Potencia máxima de carga disponible |
| **37048-37049** | U32 | 1 | W | Potencia máxima de descarga disponible |
| **37052-37061** | STRING | - | - | Número de serie (10 registros, ASCII) |
| **37066-37067** | U32 | 0.01 | kWh | Energía cargada total acumulada |
| **37068-37069** | U32 | 0.01 | kWh | Energía descargada total acumulada |

### Mapa de Registros - Sistema de almacenamiento

| Dirección | Tipo | Escala | Unidad | Descripción |
|-----------|------|--------|--------|-------------|
| **37758-37759** | U32 | 1 | Wh | Capacidad nominal |
| **37760** | U16 | 0.1 | % | State of Charge |
| **37762** | U16 | 1 | - | Estado del sistema |
| **37763** | U16 | 0.1 | V | Tensión |
| **37764** | I16 | 0.1 | A | Corriente |
| **37765-37766** | I32 | 1 | W | Potencia (**+carga**, **-descarga**) |
| **37780-37781** | U32 | 0.01 | kWh | Carga total acumulada |
| **37782-37783** | U32 | 0.01 | kWh | Descarga total acumulada |
| **37784-37785** | U32 | 0.01 | kWh | Carga del día |
| **37786-37787** | U32 | 0.01 | kWh | Descarga del día |

### Mapa de Registros - Medidor de red

| Dirección | Tipo | Escala | Unidad | Descripción |
|-----------|------|--------|--------|-------------|
| **37100** | U16 | 1 | - | Estado del medidor (1=activo) |
| **37101-37102** | I32 | 0.1 | V | Tensión fase A |
| **37113-37114** | I32 | 1 | W | Potencia activa (**+inyecta**, **-consume**) |
| **37118** | I16 | 0.01 | Hz | Frecuencia de red |
| **37119-37120** | I32 | 0.01 | kWh | Energía inyectada total |
| **37121-37122** | I32 | 0.01 | kWh | Energía consumida total |
| **37125** | U16 | 1 | - | Tipo de medidor (0=monofásico) |

### Mapa de Registros - Inversor

| Dirección | Tipo | Escala | Unidad | Descripción |
|-----------|------|--------|--------|-------------|
| **32064-32065** | I32 | 1 | W | Potencia de entrada FV |
| **32080-32081** | I32 | 1 | W | Potencia activa de salida AC |

### Registros de Control (Lectura/Escritura)

#### Configuración de batería

| Dirección | Tipo | Escala | R/W | Rango | Descripción |
|-----------|------|--------|-----|-------|-------------|
| **47000** | U16 | 1 | R/W | 0-2 | Modelo ESU1 (0/1/2) |
| **47075-47076** | U32 | 1 | R/W | 0-P_nom | Potencia máxima de carga (W) |
| **47077-47078** | U32 | 1 | R/W | 0-P_nom | Potencia máxima de descarga (W) |
| **47081** | U16 | 0.1 | R/W | 900-1000 | Corte de carga (%) |
| **47082** | U16 | 0.1 | R/W | 120-200 | Corte de descarga (%) |
| **47083** | U16 | 1 | R/W | 0-1440 | Duración carga/descarga forzada (min, 0=hasta SOC objetivo) |
| **47084-47085** | I32 | 1 | R/W | ±P_nom | Potencia forzada (W, **+carga** / **-descarga**, 0=usar 47247/47249) |
| **47086** | U16 | 1 | R/W | 0-5 | Modo de trabajo: 0=adaptativo, 1=fijo, 2=máx.autoconsumo, 3=TOU(LG), 4=inyección total, 5=TOU(LUNA) |
| **47087** | U16 | 1 | R/W | 0-1 | Carga desde red (0=no, 1=sí) |
| **47088** | U16 | 0.1 | R/W | 200-1000 | SOC corte carga desde red (%) |
| **47089** | U16 | 1 | R/W | 0-2 | Modelo ESU2 |
| **47100** | U16 | 1 | R/W | 0-2 | Comando carga/descarga forzada: 0=parar, 1=cargar, 2=descargar |
| **47101** | U16 | 0.1 | R/W | 0-1000 | SOC objetivo (%) |
| **47102** | U16 | 0.1 | R/W | 0-1000 | SOC de respaldo (%) - reserva para emergencias |
| **47247-47248** | U32 | 1 | R/W | 0-P_nom | Potencia forzada de carga (W) |
| **47249-47250** | U32 | 1 | R/W | 0-P_nom | Potencia forzada de descarga (W) |

#### Control de potencia activa

| Dirección | Tipo | Escala | R/W | Rango | Descripción |
|-----------|------|--------|-----|-------|-------------|
| **47415** | U16 | 1 | R/W | 0-7 | Control de inyección: 0/1=sin límite, 5=inyección cero, 6=límite kW, 7=límite % |
| **47416-47417** | I32 | 0.001 | R/W | - | Potencia máx. de inyección (kW → escribir en W) |
| **47418** | I16 | 0.1 | R/W | 0-1000 | Máx. inyección como % de P_inversor |

### Registros Extendidos (NO Huawei)

Registros adicionales para control del escenario:

| Dirección | Tipo | Escala | R/W | Descripción |
|-----------|------|--------|-----|-------------|
| **60000-60001** | U32 | 1 | R/W* | Potencia FV disponible (W) - *RO si hay --pv-profile |
| **60002-60003** | U32 | 1 | R/W | Potencia de la carga (W) |
| **60004-60005** | U32 | 1 | RO | Reloj simulado (Unix timestamp UTC) |

## Modos de Operación

### Modo 0: Adaptativo (por defecto)
- La batería gestiona automáticamente según disponibilidad FV y carga
- Prioridad al autoconsumo

### Modo 1: Fijo
- La batería no actúa salvo en carga/descarga forzada
- Útil para estrategias de control externas

### Modo 2: Máximo Autoconsumo
- Optimiza para minimizar consumo de red
- Carga con excedente FV, descarga cuando hay déficit

### Modo 3: TOU (LG) / Modo 5: TOU (LUNA)
- Simplificado como autoconsumo en el simulador
- Periodos tarifarios no implementados

### Modo 4: Inyección Total
- Toda la FV se inyecta a red
- La batería no participa

## Carga/Descarga Forzada

### Comando de forzado (47100)

```
0 = Parar forzado
1 = Forzar carga
2 = Forzar descarga
```

### Parámetros

- **47083**: Duración en minutos (0 = hasta alcanzar SOC objetivo)
- **47084**: Potencia a usar (W, con signo Huawei)
- **47101**: SOC objetivo
- **47247/47249**: Potencias alternativas de carga/descarga

### Ejemplo: Forzar carga a 3 kW hasta 90% SOC

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("localhost", port=5021)
client.connect()

# Configurar SOC objetivo: 90% = 900
client.write_register(47101, 900, slave=1)

# Configurar potencia de carga: 3000 W
client.write_registers(47247, [0, 3000], slave=1)  # U32 HI, LO

# Activar carga forzada
client.write_register(47100, 1, slave=1)

client.close()
```

## Control de Inyección

### Inyección sin límite (47415 = 0 o 1)
Toda la potencia disponible puede inyectarse.

### Inyección cero (47415 = 5)
No se permite inyectar a red. El excedente FV se recorta.

```python
client.write_register(47415, 5, slave=1)
```

### Límite en kW (47415 = 6)
Máximo especificado en 47416 (en W).

```python
# Limitar a 3 kW (3000 W)
client.write_register(47415, 6, slave=1)
client.write_registers(47416, [0, 3000], slave=1)
```

### Límite en % (47415 = 7)
Máximo como % de la potencia del inversor (47418).

```python
# Limitar al 50% del inversor
client.write_register(47415, 7, slave=1)
client.write_register(47418, 500, slave=1)  # 50.0%
```

## Ejemplos de Código

### Lectura de estado completo

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("localhost", port=5021)
client.connect()

# Leer estado de batería (37000-37004)
result = client.read_holding_registers(37000, 5, slave=1)
status = result.registers[0]
power_w = (result.registers[1] << 16) | result.registers[2]
if power_w >= 0x80000000:
    power_w -= 0x100000000
bus_v = result.registers[3] / 10.0
soc_pct = result.registers[4] / 10.0

print(f"Estado: {status} | Potencia: {power_w} W | SoC: {soc_pct}%")

# Leer potencia del medidor (37113)
result = client.read_holding_registers(37113, 2, slave=1)
meter_w = (result.registers[0] << 16) | result.registers[1]
if meter_w >= 0x80000000:
    meter_w -= 0x100000000

print(f"Medidor: {meter_w} W ({'inyectando' if meter_w > 0 else 'consumiendo'})")

client.close()
```

### Configurar modo autoconsumo con límites

```python
client = ModbusTcpClient("localhost", port=5021)
client.connect()

# Configurar modo 2 (máximo autoconsumo)
client.write_register(47086, 2, slave=1)

# Límites de SoC
client.write_register(47082, 150, slave=1)  # Min 15%
client.write_register(47081, 950, slave=1)  # Max 95%

# SOC de respaldo (reserva para emergencias)
client.write_register(47102, 200, slave=1)  # 20%

# Potencias máximas (5000 W = 5 kW)
client.write_registers(47075, [0, 5000], slave=1)  # Carga
client.write_registers(47077, [0, 5000], slave=1)  # Descarga

client.close()
```

### Cambiar FV y carga en caliente

```python
# Modificar producción FV (registro extendido 60000)
client.write_registers(60000, [0, 4500], slave=1)  # 4.5 kW

# Modificar consumo (registro extendido 60002)
client.write_registers(60002, [0, 2000], slave=1)  # 2.0 kW
```

## Integración

Este simulador es compatible con:
- **Sistemas SCADA**: Que soporten Modbus TCP
- **Plataformas de gestión**: Home Assistant, OpenHAB, Node-RED
- **Software de monitoreo**: Fusion Solar (Modbus compatible)
- **Herramientas de testing**: Para validar integraciones Huawei

## Troubleshooting

### El simulador no arranca
- Puerto en uso: `netstat -tulpn | grep 5021`
- Permisos: Ejecutar como usuario normal

### Lecturas Modbus dan 0
- Verificar que el tiempo de simulación avanza
- Verificar dirección de registro (base 0)
- Comprobar function code (FC03 para holding)

### El perfil FV no se carga
- Verificar formato CSV (ver asset_simulator/utils/pv_profile.py)
- Comprobar zona horaria con `--tz`
- Validar timestamps en el CSV

### Potencia negativa inesperada
- Recordar convención Huawei: **+carga, -descarga** (batería)
- En medidor: **+inyecta, -consume**

## Referencias

- [Huawei SUN2000MA Modbus Interface Definitions (2024)](https://support.huawei.com/enterprise/en/doc/EDOC1100195479)
- [Protocolo Modbus TCP](https://modbus.org/docs/Modbus_Messaging_Implementation_Guide_V1_0b.pdf)
- [pymodbus Documentation](https://pymodbus.readthedocs.io/)
