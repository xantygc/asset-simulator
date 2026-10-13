# 🚀 Guía de Lanzamiento del Sistema

Esta guía contiene toda la información necesaria para lanzar el sistema completo.

## ✅ Sistema Listo para Producción

El proyecto está completamente configurado y probado. Todos los servicios están listos para iniciar.

---

## 📦 Verificar Instalación (Primera vez)

```bash
# Verificar que Poetry está instalado
poetry --version

# Instalar todas las dependencias
poetry install

# Verificar que las dependencias están correctamente instaladas
poetry run pytest --version
```

---

## 🎯 Lanzamiento Completo (Automático)

### Opción 1: Script Todo-en-Uno ⭐ RECOMENDADO

```bash
./examples/battery_web_demo.sh
```

Este script:
1. Inicia el simulador de batería en puerto 5020
2. Inicia el monitor web en puerto 8000
3. Muestra logs en tiempo real
4. Presiona `Ctrl+C` para detener todo

**Luego abre:** http://localhost:8000

---

## 🔧 Lanzamiento Manual (Control Total)

### Paso 1: Iniciar Simulador de Batería

**Terminal 1:**

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --soc 50 \
    --port 5020
```

**Verificar que inició:**
```bash
# Debes ver:
Batería: 100.0 kW / 215.0 kWh, SoC 50.0 %, eta_rt=0.92
Server listening.
```

### Paso 2: Iniciar Monitor Web

**Terminal 2:**

```bash
poetry run python -m asset_simulator.clients.battery_monitor \
    --battery-host localhost \
    --battery-port 5020 \
    --web-port 8000
```

**Verificar que inició:**
```bash
# Debes ver:
Connected to battery at localhost:5020
Starting web server on 0.0.0.0:8000
Open http://localhost:8000 in your browser
```

### Paso 3: Abrir Navegador

Abre: **http://localhost:8000**

---

## 🎮 Uso de la Interfaz Web

### Elementos de la Interfaz

1. **Métricas en Tiempo Real** (Tarjetas superiores)
   - State of Charge (SoC) con barra de progreso
   - State of Health (SOH) con ciclos equivalentes
   - Potencia actual con estado visual
   - Especificaciones de la batería
   - Energías acumuladas

2. **Panel de Control** (Arriba)
   - **Mode**: Selecciona `Standby` o `Run`
   - **Setpoint (kW)**: 
     - Positivo = Descarga (batería inyecta)
     - Negativo = Carga (batería consume)

3. **Gráficos Interactivos** (Centro)
   - **Power & SoC History**: Potencia y SoC en tiempo real
   - **SOH & Cycles**: Salud y degradación de la batería
   - **🆕 ZOOM**: 
     - Rueda del ratón: Zoom in/out
     - Arrastrar: Desplazar vista
     - Doble click: Reset zoom

4. **Panel de Debug** (Abajo)
   - Logs en tiempo real de señales Modbus
   - Timestamps de cada mensaje
   - Estado, potencia, SoC, SOH, heartbeat
   - Botón "Clear" para limpiar logs

### Secuencia de Prueba Básica

```
1. Cambiar modo a "Run" → Click "Set Mode"
2. Establecer consigna: 50 → Click "Set Power"
3. Observar:
   ✓ SoC disminuye
   ✓ Potencia muestra 50 kW
   ✓ Estado cambia a "DISCHARGING"
   ✓ Gráficos se actualizan
   ✓ Logs muestran nuevos mensajes

4. Cambiar consigna: -30 → Click "Set Power"
5. Observar:
   ✓ SoC aumenta
   ✓ Potencia muestra -30 kW
   ✓ Estado cambia a "CHARGING"
   
6. Hacer zoom en gráfico:
   ✓ Usa rueda del ratón para acercar
   ✓ Arrastra para desplazar
   ✓ Doble click para resetear
```

---

## 🔬 Configuraciones Avanzadas

### Simulador con Degradación

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --degradation \
    --initial-soh 95 \
    --fade-per-cycle 0.01 \
    --time-accel 100 \
    --port 5020
```

Con `--time-accel 100`, la degradación será visible rápidamente.

### Simulador con Curva de Potencia vs SoC

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

La potencia se reduce automáticamente en extremos de SoC.

### Ambas Opciones Combinadas

```bash
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 --capacity-kwh 215 \
    --soc-derate --derate-charge-from 80 \
    --degradation --initial-soh 95 --fade-per-cycle 0.01 \
    --time-accel 50 --port 5020
```

---

## 🛑 Detener Servicios

### Método 1: En Terminales

Presiona `Ctrl+C` en cada terminal.

### Método 2: Desde Otra Terminal

```bash
# Detener ambos servicios
pkill -f battery

# O detener por separado
pkill -f "batteries.basic"  # Simulador
pkill -f "battery_monitor"  # Monitor web
```

### Verificar que se Detuvieron

```bash
# No debe mostrar nada
ps aux | grep -E "(batteries|monitor)" | grep python | grep -v grep

# Puertos deben estar libres
netstat -tuln | grep -E ":(5020|8000)"
```

---

## 🔍 Verificación de Estado

### Verificar Simulador

```bash
# Puerto 5020 debe estar escuchando
netstat -tuln | grep 5020
# Debe mostrar: 0.0.0.0:5020 ... ESCUCHAR

# Ver proceso
ps aux | grep "batteries.basic" | grep -v grep
```

### Verificar Monitor Web

```bash
# Puerto 8000 debe estar escuchando
netstat -tuln | grep 8000
# Debe mostrar: 0.0.0.0:8000 ... ESCUCHAR

# Ver proceso
ps aux | grep "battery_monitor" | grep -v grep
```

### Probar API REST

```bash
curl -s http://localhost:8000/api/status | python3 -m json.tool | head -30
```

Debe devolver JSON con todos los datos de la batería.

---

## 🐛 Solución de Problemas

### 1. Puerto ya en uso

**Error:** "Address already in use"

**Solución para puerto 5020:**
```bash
sudo lsof -ti:5020 | xargs kill -9
```

**Solución para puerto 8000:**
```bash
sudo lsof -ti:8000 | xargs kill -9
```

### 2. Monitor no muestra datos

**Síntomas:** Interfaz muestra `--` en todas las métricas

**Verificaciones:**
```bash
# 1. ¿Simulador corriendo?
netstat -tuln | grep 5020

# 2. ¿Monitor conectado?
# En logs del monitor debería decir: "Connected to battery at localhost:5020"

# 3. Probar API directamente
curl http://localhost:8000/api/status
```

**Solución:**
1. Detener todo: `pkill -f battery`
2. Reiniciar simulador primero
3. Esperar 3 segundos
4. Reiniciar monitor
5. Recargar navegador (F5)

### 3. Panel de logs vacío

**Síntomas:** "Waiting for data..." por más de 10 segundos

**Causa:** WebSocket no conectado

**Solución:**
1. Abrir consola del navegador (F12)
2. Buscar errores de WebSocket
3. Recargar página
4. Si persiste, reiniciar monitor web

### 4. Gráficos no se actualizan

**Síntomas:** Gráficos permanecen planos

**Verificaciones:**
- ¿Modo en "Run"?
- ¿Consigna diferente de 0?
- ¿WebSocket conectado? (indicador verde arriba)

**Solución:**
1. Cambiar modo a "Run"
2. Establecer consigna no-cero (ej: 50 o -30)
3. Esperar 2-3 segundos

### 5. Zoom no funciona

**Síntomas:** Rueda del ratón no hace zoom

**Causa:** Navegador no soportado o JavaScript deshabilitado

**Solución:**
- Usa Chrome, Firefox, o Edge moderno
- Habilita JavaScript
- Recarga la página (Ctrl+Shift+R)

---

## 📊 Métricas y Monitoreo

### Registros Modbus Disponibles

**Input Registers (solo lectura):**
- IR 0: Estado (0=standby, 1=cargando, 2=descargando)
- IR 1: Potencia (int16, 0.1 kW)
- IR 2: SoC (uint16, 0.1 %)
- IR 3: Potencia nominal (uint16, 0.1 kW)
- IR 4: Capacidad nominal (uint16, 0.1 kWh)
- IR 5: Energía almacenada (uint16, 0.1 kWh)
- IR 6-7: Energía cargada (uint32, 0.1 kWh)
- IR 8-9: Energía descargada (uint32, 0.1 kWh)
- IR 10: Heartbeat (uint16)
- IR 11: SOH (uint16, 0.1 %)
- IR 12: Ciclos equivalentes (uint16, 0.1 ciclos)
- IR 13-14: Potencia máx descarga/carga (uint16, 0.1 kW)
- IR 15: Capacidad útil (uint16, 0.1 kWh)

**Holding Registers (lectura/escritura):**
- HR 0: Modo (0=standby, 1=run)
- HR 1: Consigna potencia (int16, 0.1 kW)
- HR 2: Límite potencia (uint16, 0.1 kW)
- HR 3: SoC mínimo (uint16, 0.1 %)
- HR 4: SoC máximo (uint16, 0.1 %)

---

## 🔗 API REST Endpoints

### GET /api/status

Obtiene el estado actual de la batería.

**Ejemplo:**
```bash
curl http://localhost:8000/api/status
```

**Respuesta:**
```json
{
    "timestamp": "2026-10-10T10:00:00.123456",
    "state": 2,
    "power_kw": 50.0,
    "soc_pct": 45.5,
    "soh_pct": 100.0,
    ...
}
```

### WebSocket /ws

Conexión en tiempo real para recibir actualizaciones cada 500ms.

---

## 📚 Documentación Adicional

- **[QUICKSTART.md](QUICKSTART.md)** - Inicio rápido (2 minutos)
- **[README.md](README.md)** - Documentación principal
- **[docs/batteries/basic.md](docs/batteries/basic.md)** - Simulador detallado
- **[docs/clients/battery_monitor.md](docs/clients/battery_monitor.md)** - Monitor web completo
- **[examples/README.md](examples/README.md)** - Más ejemplos de uso

---

## ✅ Checklist Pre-Lanzamiento

Antes de lanzar en un entorno nuevo:

```
□ Poetry instalado y funcionando
□ Dependencias instaladas (poetry install)
□ Tests pasando (poetry run pytest)
□ Puerto 5020 libre
□ Puerto 8000 libre
□ Firewall permite conexiones en 5020 y 8000 (si acceso remoto)
□ Navegador moderno disponible (Chrome, Firefox, Edge)
```

---

## 🎯 Próximos Pasos

1. **Experimentar**: Prueba diferentes consignas y observa el comportamiento
2. **Degradación**: Activa degradación para ver evolución del SOH
3. **Integración**: Conecta tus dispositivos Profitflex al puerto 5020
4. **Personalización**: Modifica el HTML para adaptar la interfaz
5. **Expansión**: Agrega más simuladores (inversores, paneles solares)

---

## 💡 Tips y Trucos

1. **Múltiples Baterías**: Cambia el puerto para cada simulador
   ```bash
   # Batería 1
   poetry run python -m asset_simulator.assets.batteries.basic --port 5020
   
   # Batería 2
   poetry run python -m asset_simulator.assets.batteries.basic --port 5021
   ```

2. **Logs Detallados**: Activa logs del simulador
   ```bash
   poetry run python -m asset_simulator.assets.batteries.basic --log-every 5
   ```

3. **Desarrollo**: Usa hot-reload con uvicorn
   ```bash
   poetry run uvicorn asset_simulator.clients.battery_monitor:app --reload
   ```

4. **Docker**: Próximamente se agregará Dockerfile

---

## 📞 Soporte

Si encuentras problemas:
1. Revisa esta guía
2. Consulta [docs/clients/battery_monitor.md](docs/clients/battery_monitor.md)
3. Verifica logs del simulador y monitor
4. Revisa la consola del navegador (F12)

---

**Versión:** 1.0  
**Última actualización:** 2026-10-10  
**Estado:** ✅ Producción
