# Ejemplos de Uso

Esta carpeta contiene scripts y ejemplos que demuestran cómo usar los simuladores de assets.

## 🔋 Battery Simulator

### Demo Web Completo (Recomendado)

**[battery_web_demo.sh](battery_web_demo.sh)** - Lanza simulador + monitor web automáticamente:

```bash
./examples/battery_web_demo.sh
```

Luego abre http://localhost:8000 en tu navegador para ver:
- 📊 Gráficos en tiempo real de potencia, SoC, SOH
- 🎮 Panel de control para cambiar modo y potencia
- 📈 Histórico de últimos 30 segundos
- 🔄 Actualización automática cada 500ms

**Controles disponibles en la web:**
- **Modo**: Standby (0) o Run (1)
- **Setpoint**: Positivo = descarga, Negativo = carga
  - Ejemplo: `50` descarga 50 kW, `-30` carga 30 kW

### Uso Programático

**[battery_basic_demo.py](battery_basic_demo.py)** - Demuestra el uso del simulador sin servidor Modbus:

```bash
poetry run python examples/battery_basic_demo.py
```

Este ejemplo muestra:
- Creación de instancias de batería
- Simulación de carga/descarga
- Curvas de potencia vs SoC
- Degradación por ciclos (50 ciclos simulados)

**Output de ejemplo:**
```
============================================================
Demo: Simulador de Batería Básico
============================================================

1. Creando batería sin degradación...
   - Potencia nominal: 100.0 kW
   - Capacidad: 200.0 kWh
   - SoC inicial: 50.0%

2. Simulando descarga a 50 kW durante 1 hora...
   - Potencia actual: 50.00 kW
   - SoC final: 23.95%
   - Energía descargada: 49.97 kWh
...
```

## 🌐 Cliente Modbus Manual

### Servidor Modbus TCP

Para iniciar un simulador con servidor Modbus TCP:

```bash
# Batería básica
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --port 5020

# Con todas las opciones
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --soc 60 \
    --efficiency 0.92 \
    --ramp-kw-s 10 \
    --host 0.0.0.0 \
    --port 5020 \
    --soc-derate \
    --derate-charge-from 80 \
    --derate-discharge-below 20 \
    --degradation \
    --initial-soh 97 \
    --fade-per-cycle 0.005
```

### Cliente Python con pymodbus

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("localhost", port=5020)
client.connect()

# Activar modo run
client.write_register(0, 1, slave=1)

# Consigna de 50 kW descarga
client.write_register(1, 500, slave=1)  # 50.0 * 10

# Leer SoC
result = client.read_input_registers(2, 1, slave=1)
soc = result.registers[0] / 10.0
print(f"SoC: {soc}%")

# Leer potencia actual
result = client.read_input_registers(1, 1, slave=1)
power_raw = result.registers[0]
power = (power_raw - 65536 if power_raw >= 32768 else power_raw) / 10.0
print(f"Potencia: {power} kW")

client.close()
```

### Cliente con REPL Interactivo

Instalar herramienta de pruebas (opcional):

```bash
poetry add --group dev pymodbus-repl
```

Usar el REPL:

```bash
poetry run pymodbus.console tcp --host localhost --port 5020
```

Comandos en el REPL:
```
# Leer todos los input registers
> client.read_input_registers address=0 count=16 unit=1

# Activar modo run
> client.write_register address=0 value=1 unit=1

# Consigna de 50 kW descarga (50.0 * 10 = 500)
> client.write_register address=1 value=500 unit=1

# Leer SoC (IR 2, dividir por 10)
> client.read_input_registers address=2 count=1 unit=1

# Consigna de -30 kW carga (número negativo en complemento a 2)
# -30 * 10 = -300, en uint16 = 65536 - 300 = 65236
> client.write_register address=1 value=65236 unit=1
```

## 📊 Escenarios de Prueba

### Escenario 1: Ciclo Completo Carga/Descarga

```bash
# Terminal 1: Simulador con logs
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 --capacity-kwh 200 --soc 20 --port 5020 --log-every 10

# Terminal 2: Cliente Python
python << 'EOF'
from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient("localhost", port=5020)
client.connect()

# Activar y cargar
client.write_register(0, 1, slave=1)
client.write_register(1, 65036, slave=1)  # -50 kW = carga
print("Cargando a 50 kW...")
time.sleep(10)

# Cambiar a descarga
client.write_register(1, 500, slave=1)  # +50 kW = descarga
print("Descargando a 50 kW...")
time.sleep(10)

# Standby
client.write_register(0, 0, slave=1)
print("Standby")

client.close()
EOF
```

### Escenario 2: Monitoreo de Degradación

```bash
# Simulador con degradación acelerada
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 --capacity-kwh 200 \
    --degradation --initial-soh 90 --fade-per-cycle 0.1 \
    --time-accel 1000 --port 5020

# Monitor web
poetry run python -m asset_simulator.clients.battery_monitor \
    --battery-port 5020 --web-port 8000

# Abrir http://localhost:8000
# Ejecutar ciclos de carga/descarga y observar degradación en el gráfico
```

### Escenario 3: Curva de Potencia vs SoC

```bash
# Terminal 1: Simulador con curva
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 --capacity-kwh 200 --soc 10 \
    --soc-derate --derate-discharge-below 20 --port 5020

# Terminal 2: Monitor
poetry run python -m asset_simulator.clients.battery_monitor --web-port 8000

# Observar en el navegador:
# - A SoC < 20%, la potencia máx. de descarga se reduce
# - La métrica "Max discharge" muestra el límite dinámico
```

## 🔗 Integración con Profitflex

Ejemplo de integración con dispositivos Profitflex:

```python
import asyncio
from pymodbus.client import AsyncModbusTcpClient

async def profitflex_integration():
    """Ejemplo de integración con gestión de energía."""
    
    # Conectar a simulador
    battery = AsyncModbusTcpClient("battery-simulator", port=5020)
    await battery.connect()
    
    # Conectar a sistema de gestión (ejemplo)
    # ems = EnergyManagementSystem(...)
    
    while True:
        # Leer estado de la batería
        ir = await battery.read_input_registers(0, 16, slave=1)
        soc = ir.registers[2] / 10.0
        power = (ir.registers[1] - 65536 if ir.registers[1] >= 32768 else ir.registers[1]) / 10.0
        
        # Lógica de control (ejemplo simplificado)
        if soc < 20:
            # SoC bajo, cargar
            setpoint = -50  # 50 kW de carga
        elif soc > 80:
            # SoC alto, descargar
            setpoint = 50   # 50 kW de descarga
        else:
            # Rango normal, mantener
            setpoint = power
        
        # Enviar consigna
        value = int(setpoint * 10) & 0xFFFF
        await battery.write_register(0, 1, slave=1)  # modo run
        await battery.write_register(1, value, slave=1)
        
        print(f"SoC: {soc:.1f}%, Power: {power:.1f} kW, Setpoint: {setpoint:.1f} kW")
        await asyncio.sleep(1)

# Ejecutar
asyncio.run(profitflex_integration())
```

## 📝 Notas

- **Convención de signos**: 
  - Potencia **positiva** (+) = Descarga (batería inyecta)
  - Potencia **negativa** (-) = Carga (batería consume)
  
- **Escalado Modbus**: Todos los valores de potencia y energía se multiplican por 10
  - 50.5 kW → 505 en registro
  - -30.2 kW → 65234 en registro (complemento a 2)

- **Permisos**: El script `battery_web_demo.sh` necesita permisos de ejecución
  ```bash
  chmod +x examples/battery_web_demo.sh
  ```

## 🚀 Próximos Pasos

- Ver documentación completa: [docs/batteries/basic.md](../docs/batteries/basic.md)
- Ver documentación del monitor: [docs/clients/battery_monitor.md](../docs/clients/battery_monitor.md)
- Explorar configuraciones avanzadas
- Integrar con tu sistema SCADA
