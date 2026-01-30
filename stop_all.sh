#!/bin/bash
# stop_all.sh - Detiene todos los servicios

echo "🛑 Deteniendo servicios..."

pkill -f "python3 bot.py" 2>/dev/null
pkill -f "python3 app.py" 2>/dev/null

echo "✓ Servicios detenidos"
