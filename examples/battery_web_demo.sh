#!/bin/bash
# Script para lanzar el simulador de batería y el monitor web simultáneamente

echo "============================================"
echo "Battery Simulator + Web Monitor"
echo "============================================"
echo ""
echo "Starting battery simulator on port 5020..."
echo "Starting web monitor on http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop both services"
echo ""

# Función para manejar Ctrl+C
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $PID_BATTERY $PID_MONITOR 2>/dev/null
    exit 0
}

trap cleanup INT

# Iniciar el simulador de batería en segundo plano
poetry run python -m asset_simulator.assets.batteries.basic \
    --power-kw 100 \
    --capacity-kwh 215 \
    --soc 50 \
    --port 5020 \
    --log-every 0 &
PID_BATTERY=$!

# Esperar a que el simulador se inicie
sleep 2

# Iniciar el monitor web en segundo plano
poetry run python -m asset_simulator.clients.battery_monitor \
    --battery-host localhost \
    --battery-port 5020 \
    --web-port 8000 &
PID_MONITOR=$!

# Esperar a que el monitor se inicie
sleep 2

echo ""
echo "✅ Services running:"
echo "   - Battery simulator: localhost:5020 (Modbus TCP)"
echo "   - Web monitor: http://localhost:8000"
echo ""
echo "Open http://localhost:8000 in your browser"
echo ""

# Esperar a que ambos procesos terminen
wait $PID_BATTERY $PID_MONITOR
