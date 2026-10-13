# 🚀 Guía Rápida de Inicio

Esta guía te permite poner en marcha el sistema en menos de 2 minutos.

## ⚡ Inicio Rápido (Automático)

**La forma más fácil - Un solo comando:**

```bash
./examples/battery_web_demo.sh
```

Luego abre tu navegador en: **http://localhost:8000**

---

## 📋 Inicio Manual (Paso a Paso)

### 1. Instalar Dependencias (solo primera vez)

```bash
poetry install
```

### 2. Iniciar el Simulador de Batería

**Terminal 1:**

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --port 5020
```

Verás:
```
Batería: 100.0 kW / 215.0 kWh, SoC 50.0 %, eta_rt=0.92 -> Modbus TCP 0.0.0.0:5020 (unit 1)
Server listening.
```

### 3. Iniciar el Monitor Web

**Terminal 2:**

```bash
poetry run python -m asset_simulator.clients.battery_monitor \
    --battery-host localhost \
    --battery-port 5020 \
    --web-port 8000
```

Verás:
```
Connected to battery at localhost:5020
Starting web server on 0.0.0.0:8000
Open http://localhost:8000 in your browser
```

### 4. Abrir el Navegador

Abre: **http://localhost:8000**

---

## 🎮 Uso Básico

### En la Interfaz Web:

1. **Cambiar Modo**:
   - Selecciona `Run` en el dropdown
   - Haz clic en `Set Mode`

2. **Establecer Potencia**:
   - Valores positivos = Descarga (batería inyecta)
     - Ejemplo: `50` = descargar 50 kW
   - Valores negativos = Carga (batería consume)
     - Ejemplo: `-30` = cargar 30 kW
   - Haz clic en `Set Power`

3. **Observar**:
   - Métricas se actualizan en tiempo real
   - Gráficos muestran histórico
   - Panel de logs muestra señales Modbus

---

## 🛑 Detener Servicios

### Opción 1: En cada terminal
Presiona `Ctrl+C`

### Opción 2: Desde otra terminal
```bash
pkill -f battery
```

---

## 🔧 Configuración Avanzada

### Simulador con Degradación

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --degradation \
    --initial-soh 95 \
    --fade-per-cycle 0.01 \
    --time-accel 10 \
    --port 5020
```

### Simulador con Curva de Potencia vs SoC

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --soc-derate \
    --derate-charge-from 80 \
    --derate-discharge-below 20 \
    --port 5020
```

### Monitor en Puerto Diferente

```bash
poetry run python -m asset_simulator.clients.battery_monitor \
    --battery-port 5020 \
    --web-port 8080
```

Abre: http://localhost:8080

---

## 📊 Verificar Estado

### Verificar Simulador Corriendo

```bash
netstat -tuln | grep 5020
```

Debe mostrar: `0.0.0.0:5020 ... ESCUCHAR`

### Verificar Monitor Corriendo

```bash
netstat -tuln | grep 8000
```

Debe mostrar: `0.0.0.0:8000 ... ESCUCHAR`

### Probar API REST

```bash
curl http://localhost:8000/api/status
```

Debe devolver JSON con datos de la batería.

---

## 🐛 Solución de Problemas

### Error: "Address already in use"

**Puerto 5020 ocupado:**
```bash
sudo lsof -ti:5020 | xargs kill -9
```

**Puerto 8000 ocupado:**
```bash
sudo lsof -ti:8000 | xargs kill -9
```

### Monitor no muestra datos

1. Verifica que el simulador esté corriendo
2. Recarga la página del navegador (F5)
3. Revisa logs del monitor:
   ```bash
   # Si lo iniciaste manualmente, verás errores en la terminal
   ```

### Panel de logs vacío

- Los logs aparecen solo cuando llegan datos
- Espera 1-2 segundos después de recargar
- Si dice "Waiting for data..." por más de 10 segundos, revisa que el simulador esté corriendo

---

## 📚 Más Información

- **Documentación Completa**: [README.md](README.md)
- **Simulador de Batería**: [docs/batteries/basic.md](docs/batteries/basic.md)
- **Monitor Web**: [docs/clients/battery_monitor.md](docs/clients/battery_monitor.md)
- **Ejemplos**: [examples/README.md](examples/README.md)

---

## 🎯 Próximos Pasos

1. Experimenta con diferentes consignas de potencia
2. Observa cómo el SoC cambia en tiempo real
3. Prueba con degradación activada
4. Integra con tu sistema Profitflex

---

## 💡 Comandos Útiles

```bash
# Ver todos los tests
poetry run pytest -v

# Formatear código
poetry run black .

# Ver ayuda del simulador
poetry run python -m asset_simulator.assets.batteries.basic --help

# Ver ayuda del monitor
poetry run python -m asset_simulator.clients.battery_monitor --help

# Ejecutar demo programático (sin servidor)
poetry run python examples/battery_basic_demo.py
```

---

¿Necesitas ayuda? Revisa la [documentación completa](README.md) o los [ejemplos](examples/README.md).
