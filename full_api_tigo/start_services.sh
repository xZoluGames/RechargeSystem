#!/bin/bash
# start_services.sh - Inicia todos los servicios del sistema

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  🚀 INICIANDO API DE RECARGAS TIGO                              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}\n"

# Directorio del script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Detener servicios anteriores
echo -e "${YELLOW}🛑 Deteniendo servicios previos...${NC}"
pkill -f "api.py" 2>/dev/null
pkill -f "sms_receiver.py" 2>/dev/null
sleep 2

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 no está instalado${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python3 disponible${NC}"

# Verificar dependencias
echo -e "\n${YELLOW}📦 Verificando dependencias...${NC}"
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Instalando dependencias...${NC}"
    pip3 install --break-system-packages -q -r requirements.txt
fi
echo -e "${GREEN}✓ Dependencias instaladas${NC}"

# Crear directorios
echo -e "\n${YELLOW}📁 Verificando directorios...${NC}"
mkdir -p data logs
echo -e "${GREEN}✓ Directorios verificados${NC}"

# Crear archivos de datos vacíos si no existen
for file in keys_database.json fingerprints.json tokens.json historial_recargas.json; do
    if [ ! -f "data/$file" ]; then
        echo "{}" > "data/$file"
        echo -e "${GREEN}✓ Creado: data/$file${NC}"
    fi
done

# 1. Iniciar Receptor SMS (Puerto 5002)
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  1. INICIANDO RECEPTOR SMS (Puerto 5002)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

nohup python3 sms_receiver.py > logs/sms_receiver.log 2>&1 &
SMS_PID=$!
sleep 2

if ps -p $SMS_PID > /dev/null; then
    echo -e "${GREEN}✅ Receptor SMS iniciado (PID: $SMS_PID)${NC}"
    echo -e "   Puerto: 5002"
    echo -e "   Log: logs/sms_receiver.log"
else
    echo -e "${RED}❌ Error iniciando Receptor SMS${NC}"
fi

# 2. Iniciar API Principal (Puerto 5000)
echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  2. INICIANDO API PRINCIPAL (Puerto 5000)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "${GREEN}Iniciando API...${NC}"
echo -e "${YELLOW}Presiona Ctrl+C para detener${NC}\n"
sleep 1

# Trap para limpiar al salir
trap 'echo -e "\n${YELLOW}🛑 Deteniendo servicios...${NC}"; pkill -P $$; exit' INT TERM

# Ejecutar API en primer plano
python3 api.py
