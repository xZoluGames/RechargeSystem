#!/bin/bash
# stop_services.sh - Detiene todos los servicios

echo "🛑 Deteniendo servicios..."

pkill -f "api.py" 2>/dev/null && echo "✓ API detenida"
pkill -f "sms_receiver.py" 2>/dev/null && echo "✓ SMS Receiver detenido"

sleep 1

# Verificar
if pgrep -f "api.py" > /dev/null || pgrep -f "sms_receiver.py" > /dev/null; then
    echo "⚠️ Algunos procesos siguen activos, forzando..."
    pkill -9 -f "api.py" 2>/dev/null
    pkill -9 -f "sms_receiver.py" 2>/dev/null
fi

echo "✅ Servicios detenidos"
