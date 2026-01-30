#!/bin/bash
# start_all.sh - Inicia todos los servicios del sistema Tigo

cd "$(dirname "$0")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  🚀 SISTEMA DE RECARGAS TIGO - INICIO COMPLETO              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo

# Función para verificar si un puerto está en uso
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Verificar API REST (puerto 5000)
echo -e "${YELLOW}1. Verificando API REST (puerto 5000)...${NC}"
if check_port 5000; then
    echo -e "${GREEN}   ✓ API REST ya está corriendo${NC}"
else
    echo -e "${RED}   ✗ API REST no está corriendo${NC}"
    echo -e "${YELLOW}   ⚠ Asegúrate de iniciar tu API REST primero${NC}"
fi
echo

# Crear directorios de datos
echo -e "${YELLOW}2. Creando directorios necesarios...${NC}"
mkdir -p BotTelegramOTP/data BotTelegramOTP/logs
mkdir -p WebApp/data WebApp/logs
echo -e "${GREEN}   ✓ Directorios creados${NC}"
echo

# Inicializar archivos de datos si no existen
echo -e "${YELLOW}3. Inicializando archivos de datos...${NC}"
[ ! -f BotTelegramOTP/data/otp_codes.json ] && echo '{}' > BotTelegramOTP/data/otp_codes.json
[ ! -f WebApp/data/sessions.json ] && echo '{}' > WebApp/data/sessions.json
echo -e "${GREEN}   ✓ Archivos inicializados${NC}"
echo

# Verificar dependencias
echo -e "${YELLOW}4. Verificando dependencias...${NC}"
python3 -c "from telegram import Update" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}   Instalando dependencias del bot...${NC}"
    pip3 install --break-system-packages -q -r BotTelegramOTP/requirements.txt
fi

python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}   Instalando dependencias de la webapp...${NC}"
    pip3 install --break-system-packages -q -r WebApp/requirements.txt
fi
echo -e "${GREEN}   ✓ Dependencias verificadas${NC}"
echo

# Iniciar Bot Telegram en background
echo -e "${YELLOW}5. Iniciando Bot Telegram OTP...${NC}"
cd BotTelegramOTP
nohup python3 bot.py > logs/bot.log 2>&1 &
BOT_PID=$!
cd ..
sleep 2
if ps -p $BOT_PID > /dev/null 2>&1; then
    echo -e "${GREEN}   ✓ Bot iniciado (PID: $BOT_PID)${NC}"
else
    echo -e "${RED}   ✗ Error iniciando bot. Ver logs/bot.log${NC}"
fi
echo

# Iniciar WebApp en foreground
echo -e "${YELLOW}6. Iniciando WebApp...${NC}"
echo -e "${GREEN}   Puerto: 8000${NC}"
echo
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Sistema listo. Presiona Ctrl+C para detener.${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo

# Trap para limpiar al salir
cleanup() {
    echo
    echo -e "${YELLOW}Deteniendo servicios...${NC}"
    kill $BOT_PID 2>/dev/null
    pkill -f "python3 bot.py" 2>/dev/null
    pkill -f "python3 app.py" 2>/dev/null
    echo -e "${GREEN}Servicios detenidos${NC}"
    exit 0
}
trap cleanup INT TERM

cd WebApp
python3 app.py
