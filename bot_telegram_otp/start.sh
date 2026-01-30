#!/bin/bash
# Iniciar Bot Telegram OTP

cd "$(dirname "$0")"

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  🤖 INICIANDO BOT TELEGRAM OTP                               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"

# Crear directorios
mkdir -p data logs

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}❌ Python3 no encontrado${NC}"
    exit 1
fi

# Verificar dependencias
python3 -c "from telegram import Update" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}📦 Instalando dependencias...${NC}"
    pip3 install --break-system-packages -q -r requirements.txt
fi

echo -e "${GREEN}✅ Iniciando bot...${NC}"
python3 bot.py
