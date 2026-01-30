#!/bin/bash
# check_services.sh - Verifica estado de los servicios

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  📊 ESTADO DE SERVICIOS                                         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}\n"

# Función para verificar puerto
check_port() {
    local port=$1
    local name=$2
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        local pid=$(lsof -Pi :$port -sTCP:LISTEN -t)
        echo -e "${GREEN}✅ $name (Puerto $port) - PID: $pid${NC}"
        return 0
    else
        echo -e "${RED}❌ $name (Puerto $port) - NO ACTIVO${NC}"
        return 1
    fi
}

# Verificar servicios
echo -e "${YELLOW}1. Verificando puertos...${NC}\n"
check_port 5000 "API Principal"
check_port 5002 "Receptor SMS"

# Verificar procesos
echo -e "\n${YELLOW}2. Verificando procesos...${NC}\n"

if pgrep -f "api.py" > /dev/null; then
    pid=$(pgrep -f "api.py" | head -1)
    echo -e "${GREEN}✅ api.py corriendo (PID: $pid)${NC}"
else
    echo -e "${RED}❌ api.py NO está corriendo${NC}"
fi

if pgrep -f "sms_receiver.py" > /dev/null; then
    pid=$(pgrep -f "sms_receiver.py" | head -1)
    echo -e "${GREEN}✅ sms_receiver.py corriendo (PID: $pid)${NC}"
else
    echo -e "${RED}❌ sms_receiver.py NO está corriendo${NC}"
fi

# Test de endpoints
echo -e "\n${YELLOW}3. Probando endpoints...${NC}\n"

# API Health
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health 2>/dev/null)
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✅ API /health responde (HTTP $response)${NC}"
else
    echo -e "${RED}❌ API /health no responde (HTTP $response)${NC}"
fi

# SMS Receiver Health
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5002/health 2>/dev/null)
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✅ SMS /health responde (HTTP $response)${NC}"
else
    echo -e "${RED}❌ SMS /health no responde (HTTP $response)${NC}"
fi

# Archivos de datos
echo -e "\n${YELLOW}4. Verificando archivos...${NC}\n"
for file in data/keys_database.json data/fingerprints.json data/tokens.json; do
    if [ -f "$file" ]; then
        size=$(du -h "$file" | cut -f1)
        echo -e "${GREEN}✅ $file ($size)${NC}"
    else
        echo -e "${RED}❌ $file NO EXISTE${NC}"
    fi
done

# Logs recientes
echo -e "\n${YELLOW}5. Últimos logs de API...${NC}\n"
if [ -f "logs/api.log" ]; then
    tail -5 logs/api.log | sed 's/^/   /'
else
    echo "   No hay logs"
fi

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "Para iniciar: ${GREEN}./start_services.sh${NC}"
echo -e "Para detener: ${RED}./stop_services.sh${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
