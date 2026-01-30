# 📱 Sistema de Recargas Tigo - Guía de Instalación

## Índice
1. [Arquitectura del Sistema](#arquitectura-del-sistema)
2. [Requisitos](#requisitos)
3. [Instalación](#instalación)
4. [Configuración](#configuración)
5. [Puertos y Firewall](#puertos-y-firewall)
6. [Iniciar Servicios](#iniciar-servicios)
7. [Systemd (Servicios Automáticos)](#systemd-servicios-automáticos)
8. [Verificación](#verificación)
9. [Solución de Problemas](#solución-de-problemas)

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│                           USUARIO                                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐    ┌────────────────┐    ┌─────────────────┐
│ BotTelegramOTP│    │    WebApp      │    │    API REST     │
│               │    │   (Puerto      │    │   (Puerto 5000) │
│  (Sin puerto, │    │    8000)       │    │                 │
│   usa API     │    │                │    │  YA EXISTENTE   │
│   Telegram)   │    └───────┬────────┘    └────────┬────────┘
└───────┬───────┘            │                      │
        │                    │                      │
        │     Genera OTP     │   Consulta paquetes  │
        │◄───────────────────┤   Hace recargas      │
        │                    │─────────────────────►│
        │                    │                      │
        └────────────────────┴──────────────────────┘
```

### Componentes

| Componente | Puerto | Descripción |
|------------|--------|-------------|
| **API REST** | 5000 | Backend de recargas (YA EXISTE) |
| **SMS Receiver** | 5002 | Receptor de SMS para OTP Tigo (YA EXISTE) |
| **WebApp** | 8000 | Interfaz web para usuarios |
| **BotTelegramOTP** | - | Bot para enviar códigos OTP a usuarios |

---

## Requisitos

### Sistema Operativo
- Ubuntu 20.04+ / Debian 11+
- Python 3.8+

### Verificar Python
```bash
python3 --version
# Debe mostrar 3.8 o superior
```

### Instalar pip si no existe
```bash
sudo apt update
sudo apt install python3-pip -y
```

---

## Instalación

### 1. Subir los archivos al VPS

```bash
# Opción A: Con SCP desde tu PC
scp tigo_system.zip usuario@TU_IP:/home/usuario/

# Opción B: Con wget si tienes el archivo en un servidor
wget URL_DEL_ARCHIVO -O tigo_system.zip
```

### 2. Descomprimir

```bash
cd /home/usuario
unzip tigo_system.zip
cd tigo_system
```

### 3. Estructura esperada

```
tigo_system/
├── BotTelegramOTP/
│   ├── bot.py
│   ├── config.py
│   ├── requirements.txt
│   ├── start.sh
│   └── data/
├── WebApp/
│   ├── app.py
│   ├── config.py
│   ├── requirements.txt
│   ├── start.sh
│   ├── templates/
│   └── data/
└── GUIA_INSTALACION.md
```

### 4. Dar permisos de ejecución

```bash
chmod +x BotTelegramOTP/start.sh
chmod +x WebApp/start.sh
```

### 5. Instalar dependencias

```bash
# Bot Telegram
cd BotTelegramOTP
pip3 install --break-system-packages -r requirements.txt

# WebApp
cd ../WebApp
pip3 install --break-system-packages -r requirements.txt
```

---

## Configuración

### 1. Configurar Bot Telegram OTP

Edita `BotTelegramOTP/config.py`:

```python
# Token de tu bot (obtén uno con @BotFather)
BOT_TOKEN = "TU_TOKEN_DE_BOT"

# Tu ID de Telegram (admin)
ADMIN_TELEGRAM_ID = 123456789  # Usa @userinfobot para obtenerlo

# URL de tu WebApp
WEB_URL = "http://TU_IP_VPS:8000"

# Minutos de validez del OTP
OTP_EXPIRATION_MINUTES = 10
```

### 2. Configurar WebApp

Edita `WebApp/config.py`:

```python
# URL de tu API REST existente
API_URL = "http://localhost:5000"

# Credenciales admin de la API (las mismas de tu API)
ADMIN_API_KEY = "ZoluGames"
ADMIN_API_PASSWORD = "Gamehag2025*"

# Puerto de la WebApp
WEB_PORT = 8000

# Tu ID de Telegram (admin)
ADMIN_TELEGRAM_ID = 123456789

# Clave secreta para JWT (CAMBIAR EN PRODUCCIÓN)
JWT_SECRET = "una_clave_muy_larga_y_segura_cambiar_esto"

# Verificación OTP local (True si bot está en mismo servidor)
OTP_VERIFICATION_LOCAL = True
```

---

## Puertos y Firewall

### Puertos necesarios

| Puerto | Servicio | Acceso |
|--------|----------|--------|
| 5000 | API REST | Interno (localhost) o externo si lo necesitas |
| 5002 | SMS Receiver | Externo (para recibir SMS del móvil) |
| 8000 | WebApp | Externo (para usuarios) |

### UFW (Ubuntu Firewall)

```bash
# Ver estado actual
sudo ufw status

# Habilitar firewall (si no está activo)
sudo ufw enable

# Abrir puertos necesarios
sudo ufw allow 22/tcp      # SSH (¡IMPORTANTE!)
sudo ufw allow 8000/tcp    # WebApp
sudo ufw allow 5002/tcp    # SMS Receiver (si usas)
sudo ufw allow 5000/tcp    # API (solo si la expones externamente)

# Verificar
sudo ufw status
```

### iptables (alternativa)

```bash
# WebApp
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT

# SMS Receiver
sudo iptables -A INPUT -p tcp --dport 5002 -j ACCEPT

# API (opcional)
sudo iptables -A INPUT -p tcp --dport 5000 -j ACCEPT

# Guardar reglas
sudo iptables-save > /etc/iptables/rules.v4
```

---

## Iniciar Servicios

### Método Manual (para pruebas)

Abre 3 terminales (o usa `screen`/`tmux`):

```bash
# Terminal 1: API REST (si aún no está corriendo)
cd /ruta/a/tu/api
python3 api.py

# Terminal 2: Bot Telegram OTP
cd /home/usuario/tigo_system/BotTelegramOTP
./start.sh

# Terminal 3: WebApp
cd /home/usuario/tigo_system/WebApp
./start.sh
```

### Con Screen (recomendado para pruebas)

```bash
# Instalar screen
sudo apt install screen -y

# Crear sesión para Bot
screen -S bot
cd /home/usuario/tigo_system/BotTelegramOTP
./start.sh
# Presiona Ctrl+A, luego D para salir

# Crear sesión para WebApp
screen -S web
cd /home/usuario/tigo_system/WebApp
./start.sh
# Presiona Ctrl+A, luego D para salir

# Ver sesiones activas
screen -ls

# Reconectar a una sesión
screen -r bot
screen -r web
```

---

## Systemd (Servicios Automáticos)

### 1. Servicio para Bot Telegram

Crea `/etc/systemd/system/tigo-bot.service`:

```bash
sudo nano /etc/systemd/system/tigo-bot.service
```

Contenido:
```ini
[Unit]
Description=Tigo Bot Telegram OTP
After=network.target

[Service]
Type=simple
User=TU_USUARIO
WorkingDirectory=/home/TU_USUARIO/tigo_system/BotTelegramOTP
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Servicio para WebApp

Crea `/etc/systemd/system/tigo-web.service`:

```bash
sudo nano /etc/systemd/system/tigo-web.service
```

Contenido:
```ini
[Unit]
Description=Tigo WebApp
After=network.target

[Service]
Type=simple
User=TU_USUARIO
WorkingDirectory=/home/TU_USUARIO/tigo_system/WebApp
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3. Activar servicios

```bash
# Recargar systemd
sudo systemctl daemon-reload

# Habilitar servicios (inicio automático)
sudo systemctl enable tigo-bot
sudo systemctl enable tigo-web

# Iniciar servicios
sudo systemctl start tigo-bot
sudo systemctl start tigo-web

# Ver estado
sudo systemctl status tigo-bot
sudo systemctl status tigo-web
```

### 4. Comandos útiles

```bash
# Reiniciar servicio
sudo systemctl restart tigo-bot
sudo systemctl restart tigo-web

# Ver logs
sudo journalctl -u tigo-bot -f
sudo journalctl -u tigo-web -f

# Detener servicio
sudo systemctl stop tigo-bot
sudo systemctl stop tigo-web
```

---

## Verificación

### 1. Verificar que los servicios están corriendo

```bash
# Ver procesos
ps aux | grep python

# Ver puertos en uso
sudo netstat -tlnp | grep -E "5000|5002|8000"
# o
sudo ss -tlnp | grep -E "5000|5002|8000"
```

### 2. Probar WebApp

```bash
# Desde el servidor
curl http://localhost:8000

# Desde tu navegador
http://TU_IP_VPS:8000
```

### 3. Probar Bot Telegram

1. Busca tu bot en Telegram (el que creaste con @BotFather)
2. Envía `/start`
3. Envía `/myid` para ver tu ID
4. Envía `/otp` para generar un código

### 4. Probar API REST

```bash
curl http://localhost:5000/health
```

---

## Solución de Problemas

### Error: "Connection refused" en WebApp

**Causa**: La API REST no está corriendo o está en otro puerto.

**Solución**:
```bash
# Verificar que la API está corriendo
curl http://localhost:5000/health

# Si no responde, iniciar la API
cd /ruta/a/tu/api
python3 api.py
```

### Error: "Bot not responding"

**Causa**: Token incorrecto o bot no iniciado.

**Solución**:
1. Verifica el token en `BotTelegramOTP/config.py`
2. Revisa los logs: `journalctl -u tigo-bot -f`

### Error: "Port already in use"

**Causa**: Otro proceso está usando el puerto.

**Solución**:
```bash
# Ver qué proceso usa el puerto
sudo lsof -i :8000

# Matarlo si es necesario
sudo kill -9 PID_DEL_PROCESO
```

### OTP no se verifica

**Causa**: El bot y la webapp no comparten el archivo de OTPs.

**Solución**:
1. Asegúrate de que `OTP_VERIFICATION_LOCAL = True` en `WebApp/config.py`
2. Verifica que ambos usan la misma estructura de carpetas

### Error: "Module not found"

**Solución**:
```bash
# Reinstalar dependencias
cd BotTelegramOTP
pip3 install --break-system-packages -r requirements.txt

cd ../WebApp
pip3 install --break-system-packages -r requirements.txt
```

---

## Resumen de URLs

| Servicio | URL |
|----------|-----|
| WebApp (Login) | `http://TU_IP:8000/` |
| WebApp (Usuario) | `http://TU_IP:8000/user` |
| WebApp (Admin) | `http://TU_IP:8000/admin` |
| API Health | `http://TU_IP:5000/health` |

---

## Checklist de Instalación

- [ ] Python 3.8+ instalado
- [ ] Archivos descomprimidos en `/home/usuario/tigo_system/`
- [ ] Permisos de ejecución dados a los `.sh`
- [ ] Dependencias instaladas
- [ ] `BotTelegramOTP/config.py` configurado
- [ ] `WebApp/config.py` configurado
- [ ] Puertos abiertos en firewall (8000, 5002)
- [ ] Servicios systemd creados y habilitados
- [ ] Bot responde en Telegram
- [ ] WebApp accesible desde navegador
- [ ] API REST corriendo

---

**¡Listo!** Tu sistema debería estar funcionando. Si tienes problemas, revisa los logs con `journalctl -u SERVICIO -f`.
