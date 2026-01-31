#!/bin/bash
# start_services.sh - Inicia los servicios de la API Tigo
# v2.3

cd "$(dirname "$0")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  🚀 API RECARGAS TIGO - INICIO DE SERVICIOS                  ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo

# Crear directorios necesarios
echo -e "${YELLOW}1. Creando directorios...${NC}"
mkdir -p data logs
echo -e "${GREEN}   ✓ Directorios creados${NC}"
echo

# Detener procesos anteriores
echo -e "${YELLOW}2. Deteniendo procesos anteriores...${NC}"
pkill -f "python3 api.py" 2>/dev/null
pkill -f "python3 sms_receiver.py" 2>/dev/null
sleep 1
echo -e "${GREEN}   ✓ Procesos detenidos${NC}"
echo

# Iniciar SMS Receiver
echo -e "${YELLOW}3. Iniciando SMS Receiver (puerto 5002)...${NC}"
nohup python3 sms_receiver.py > logs/sms_receiver.log 2>&1 &
SMS_PID=$!
sleep 2
if ps -p $SMS_PID > /dev/null 2>&1; then
    echo -e "${GREEN}   ✓ SMS Receiver iniciado (PID: $SMS_PID)${NC}"
else
    echo -e "${RED}   ✗ Error iniciando SMS Receiver${NC}"
fi
echo

# Iniciar API
echo -e "${YELLOW}4. Iniciando API REST (puerto 5000)...${NC}"
nohup python3 api.py > logs/api_startup.log 2>&1 &
API_PID=$!
sleep 3
if ps -p $API_PID > /dev/null 2>&1; then
    echo -e "${GREEN}   ✓ API iniciada (PID: $API_PID)${NC}"
else
    echo -e "${RED}   ✗ Error iniciando API. Ver logs/api_startup.log${NC}"
    tail -20 logs/api_startup.log
fi
echo

# Verificar
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Estado de servicios:${NC}"
echo

if pgrep -f "api.py" > /dev/null; then
    echo -e "${GREEN}✓ API REST: Corriendo en puerto 5000${NC}"
else
    echo -e "${RED}✗ API REST: No está corriendo${NC}"
fi

if pgrep -f "sms_receiver.py" > /dev/null; then
    echo -e "${GREEN}✓ SMS Receiver: Corriendo en puerto 5002${NC}"
else
    echo -e "${RED}✗ SMS Receiver: No está corriendo${NC}"
fi

echo
echo -e "${BLUE}Para ver logs:${NC}"
echo "  tail -f logs/api.log"
echo "  tail -f logs/sms_receiver.log"
echo
echo -e "${GREEN}✅ Inicio completado${NC}"
