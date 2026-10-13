# Asset Simulator

Simuladores de activos energéticos (baterías, inversores, paneles solares, etc.) con interfaces Modbus TCP para integración con sistemas de gestión de energía.

## Características

- **Simuladores realistas**: Modelos físicos de comportamiento de activos energéticos
- **Protocolo Modbus TCP**: Interfaz estándar para integración SCADA
- **Configuración flexible**: Parámetros ajustables por línea de comandos
- **Modelos avanzados**: Degradación, curvas de potencia, eficiencia
- **Tests completos**: Suite de tests unitarios y de integración

## Instalación

```bash
# Clonar el repositorio
cd asset-simulator

# Instalar dependencias con Poetry
poetry install
```

## Simuladores Disponibles

### Baterías

#### [Battery Simulator - Basic](docs/batteries/basic.md)

Simulador de batería con modelo físico de carga/descarga, eficiencia, degradación opcional y curvas de potencia vs SoC.

```bash
# Uso básico
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --port 5020

# Con degradación y curvas de potencia
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --soc-derate \
    --degradation \
    --initial-soh 97 \
    --port 5020
```

**Características:**
- Modelo de carga/descarga con eficiencia configurable
- Curva de potencia dependiente del SoC (opcional)
- Degradación por ciclos equivalentes (opcional)
- Límites operacionales (SoC min/max, rampa)
- Interfaz Modbus TCP completa

**Documentación completa:** [docs/batteries/basic.md](docs/batteries/basic.md)

## Herramientas de Monitoreo

### [Battery Web Monitor](docs/clients/battery_monitor.md)

Monitor web en tiempo real con interfaz gráfica para visualizar y controlar baterías.

```bash
# Opción 1: Script automático (lanza simulador + monitor)
./examples/battery_web_demo.sh

# Opción 2: Manual
# Terminal 1
poetry run python -m asset_simulator.assets.batteries.basic --power-kw 100 --port 5020

# Terminal 2
poetry run python -m asset_simulator.clients.battery_monitor --battery-port 5020 --web-port 8000

# Abrir http://localhost:8000 en el navegador
```

**Características:**
- 📊 Gráficos en tiempo real (potencia, SoC, SOH, ciclos)
- 🎮 Panel de control web (modo, consigna de potencia)
- 🔄 Actualización cada 500ms vía WebSockets
- 📱 Interfaz responsive (desktop y móvil)
- 🔌 Reconexión automática
- 📡 API REST para integración

**Documentación completa:** [docs/clients/battery_monitor.md](docs/clients/battery_monitor.md)

### Inversores

_Próximamente_

### Paneles Solares

_Próximamente_

## Estructura del Proyecto

```
asset-simulator/
├── asset_simulator/          # Código fuente
│   ├── __init__.py
│   └── assets/               # Simuladores de activos
│       ├── __init__.py
│       └── batteries/        # Simuladores de baterías
│           ├── __init__.py
│           └── basic.py      # Simulador básico
├── tests/                    # Tests
│   ├── __init__.py
│   └── assets/
│       └── batteries/
│           ├── __init__.py
│           └── test_basic.py
├── docs/                     # Documentación
│   └── batteries/
│       └── basic.md          # Documentación del simulador básico
├── pyproject.toml            # Configuración de Poetry
└── README.md                 # Este archivo
```

## Desarrollo

### Ejecutar Tests

```bash
# Todos los tests
poetry run pytest

# Tests específicos con verbosidad
poetry run pytest tests/assets/batteries/test_basic.py -v

# Con cobertura
poetry run pytest --cov=asset_simulator --cov-report=html
```

### Formateo y Linting

```bash
# Formatear código
poetry run black .

# Verificar linting
poetry run ruff check .

# Corregir automáticamente
poetry run ruff check --fix .

# Type checking
poetry run mypy asset_simulator
```

### Agregar Nuevas Dependencias

```bash
# Dependencias de producción
poetry add <paquete>

# Dependencias de desarrollo
poetry add --group dev <paquete>
```

## Integración

Los simuladores están diseñados para integrarse con sistemas de gestión de energía mediante el protocolo Modbus TCP estándar. Esto permite:

1. **Desarrollo y testing**: Probar integraciones sin hardware físico
2. **Validación de estrategias**: Simular comportamiento de activos bajo diferentes condiciones
3. **Entrenamiento**: Familiarizarse con las interfaces Modbus antes de despliegue
4. **CI/CD**: Incluir simuladores en pipelines de integración continua

## Ejemplos

### Demo Interactivo

Ejecuta el script de demostración para ver el simulador en acción:

```bash
poetry run python examples/battery_basic_demo.py
```

Este ejemplo muestra:
- Creación de instancias de batería
- Simulación de carga/descarga
- Curvas de potencia vs SoC
- Degradación por ciclos

### Uso Programático

Los simuladores también pueden utilizarse como bibliotecas Python:

```python
from asset_simulator.assets.batteries.basic import Battery, Sim

# Crear instancia de batería
battery = Battery(
    power_kw=100.0,
    capacity_kwh=200.0,
    soc=50.0,
    efficiency=0.92,
    ramp_kw_s=10.0
)

# Simular paso de tiempo
battery.step(
    dt=1.0,
    mode=1,
    setpoint_kw=50.0,
    limit_kw=100.0,
    soc_min=10.0,
    soc_max=90.0
)

print(f"Potencia: {battery.power_kw} kW")
print(f"SoC: {battery.soc}%")
```

Más ejemplos en [examples/](examples/)

## Requisitos

- Python 3.12+
- Poetry 2.0+
- pymodbus 3.12+

## Contribuir

1. Fork el repositorio
2. Crea una rama para tu feature (`git checkout -b feature/nuevo-simulador`)
3. Commit tus cambios (`git commit -am 'Agregar simulador de inversor'`)
4. Push a la rama (`git push origin feature/nuevo-simulador`)
5. Crea un Pull Request

## Roadmap

- [x] Simulador básico de batería
- [ ] Simulador de inversor
- [ ] Simulador de paneles solares
- [ ] Simulador de cargadores EV
- [ ] Interfaz web de monitoreo
- [ ] Soporte para protocolo SunSpec
- [ ] Simulación de fallos y eventos

## Licencia

MIT

## Contacto

Para preguntas o soporte, contacta al equipo de desarrollo.
