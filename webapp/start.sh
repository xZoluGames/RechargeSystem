#!/bin/bash
# Iniciar WebApp

cd "$(dirname "$0")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  🌐 INICIANDO WEBAPP - RECARGAS TIGO                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"

mkdir -p data logs

if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}❌ Python3 no encontrado${NC}"
    exit 1
fi

python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}📦 Instalando dependencias...${NC}"
    pip3 install --break-system-packages -q -r requirements.txt
fi

echo -e "${GREEN}✅ Iniciando servidor web en puerto 8000...${NC}"
python3 app.py
