# API de Recargas Tigo Paraguay

Sistema simplificado de API REST para recargas de paquetes Tigo.

## 📋 Características

- **API REST pura** - Sin web ni Telegram
- **Doble método de autenticación**:
  - Nuevo método con fingerprint (más rápido)
  - Método legacy como fallback
- **Múltiples cuentas Tigo** soportadas con rotación automática
- **Inicialización dual**: Intenta autenticar ambas cuentas al inicio
- **Reintento automático**: Si ambas cuentas fallan, reintenta cada 10 minutos
- **Gestión de claves de API** con saldos
- **Receptor de SMS** para OTP

## 🗂️ Estructura del Proyecto

```
tigo_api/
├── api.py                 # API REST principal (Puerto 5000)
├── sms_receiver.py        # Receptor de SMS (Puerto 5002)
├── config.py              # Configuración central
├── tigo_auth_new.py       # Nuevo sistema de autenticación
├── tigo_auth_legacy.py    # Sistema de autenticación legacy
├── tigo_api.py            # API de recargas
├── key_manager.py         # Gestión de claves
├── package_manager.py     # Gestión de paquetes
├── requirements.txt       # Dependencias
├── start_services.sh      # Iniciar servicios
├── stop_services.sh       # Detener servicios
├── check_services.sh      # Verificar estado
├── API_DOCUMENTATION.md   # Documentación completa
├── data/                  # Datos persistentes
│   ├── keys_database.json
│   ├── fingerprints.json
│   ├── tokens.json
│   └── historial_recargas.json
└── logs/                  # Logs del sistema
    ├── api.log
    ├── http_requests.log
    └── sms_receiver.log
```

## 🚀 Instalación

### 1. Clonar/Copiar archivos
```bash
cd /home/administrator
unzip tigo_api_simplified.zip
mv tigo_api_project recargas_tigo_api
cd recargas_tigo_api
```

### 2. Instalar dependencias
```bash
pip3 install -r requirements.txt --break-system-packages
```

### 3. Configurar permisos
```bash
chmod +x start_services.sh stop_services.sh check_services.sh
```

### 4. Crear directorios
```bash
mkdir -p data logs
```

## ⚙️ Configuración

Editar `config.py` para ajustar:

### Cuentas Tigo
```python
TIGO_ACCOUNTS = {
    "0985308247": {
        "password": "0612",
        "fingerprint": None,
        "model": "iPhone 2026 Pro Max"
    },
    "0985139979": {
        "password": "0612",
        "fingerprint": None,
        "model": "Samsung Galaxy S26"
    }
}
```

### Credenciales Admin (⚠️ CAMBIAR EN PRODUCCIÓN)
```python
# Valores de desarrollo:
ADMIN_API_KEY = "ZoluGames"
ADMIN_PASSWORD = "Gamehag2025*"

# Tiempo de reintento tras fallo
RETRY_DELAY_MINUTES = 10
```

### Proxy (si es necesario)
```python
PROXY_CONFIG = {
    'http': 'http://user:pass@proxy:port',
    'https': 'http://user:pass@proxy:port'
}
```

## 🎯 Uso

### Iniciar servicios
```bash
./start_services.sh
```

### Detener servicios
```bash
./stop_services.sh
```

### Verificar estado
```bash
./check_services.sh
```

## 📡 API Endpoints

### Públicos (requieren API Key)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Estado del sistema |
| GET/POST | `/api/packages` | Obtener paquetes |
| POST | `/api/recharge` | Realizar recarga |
| GET | `/api/balance` | Consultar saldo |
| GET | `/api/history` | Historial de recargas |
| GET | `/api/verify_order/<id>` | Verificar orden |

### Admin (requieren Admin Key + Password)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/admin/status` | Estado completo |
| POST | `/api/admin/auth/init` | Inicializar auth |
| POST | `/api/admin/auth/refresh` | Renovar tokens |
| POST | `/api/admin/auth/fingerprint` | Renovar fingerprint |
| POST | `/api/admin/auth/switch` | Cambiar cuenta Tigo |
| POST | `/api/admin/auth/retry` | Forzar reintento |
| GET/POST | `/api/admin/keys` | Gestionar claves |
| GET/PUT/DELETE | `/api/admin/keys/<key>` | Clave específica |
| GET | `/api/admin/history` | Historial completo |

## 📝 Ejemplos de Uso

### Obtener paquetes
```bash
curl -X GET "http://localhost:5000/api/packages?destination=0981234567" \
  -H "X-API-Key: TU_API_KEY"
```

### Realizar recarga
```bash
curl -X POST "http://localhost:5000/api/recharge" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: TU_API_KEY" \
  -d '{"destination": "0981234567", "package_id": "1234"}'
```

### Consultar saldo
```bash
curl -X GET "http://localhost:5000/api/balance" \
  -H "X-API-Key: TU_API_KEY"
```

### Crear clave (Admin)
```bash
curl -X POST "http://localhost:5000/api/admin/keys" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: ZoluGames" \
  -H "X-Admin-Password: Gamehag2025*" \
  -d '{"max_amount": 1000000, "valid_days": 30}'
```

### Cambiar de cuenta Tigo (Admin)
```bash
curl -X POST "http://localhost:5000/api/admin/auth/switch" \
  -H "X-Admin-Key: ZoluGames" \
  -H "X-Admin-Password: Gamehag2025*"
```

### Forzar reintento de autenticación (Admin)
```bash
curl -X POST "http://localhost:5000/api/admin/auth/retry" \
  -H "X-Admin-Key: ZoluGames" \
  -H "X-Admin-Password: Gamehag2025*"
```

## 🔐 Flujo de Autenticación Tigo

### Tokens Importantes

⚠️ **CRÍTICO**: Para operaciones de recargas se usa `token_aws` (JWT largo), NO `access_token`.

```json
{
  "token_aws": "eyJhbGci...",      // ← USAR ESTE para API de recargas
  "access_token": "eeea0a82...",   // Token de acceso (NO usar para recargas)
  "refresh_token": "ba0663d0..."   // Token de renovación
}
```

### Nuevo Método (con fingerprint)

1. **POST /access/task** - Verificar fingerprint
   - Si `otp: false` → Fingerprint válido, continuar
   - Si `otp: true` → Necesita validación con OTP

2. **POST /otp** - Solicitar OTP (si necesario)
3. **Esperar SMS** - Receptor en puerto 5002
4. **PUT /otp** - Validar OTP
5. **GET /auth/validate/{uuid}** - Validar UUID
6. **POST /auth/login** - Login final → Obtiene `token_aws`

### Inicialización Dual

Al arrancar:
1. Intenta autenticar cuenta 1 (0985308247)
2. Intenta autenticar cuenta 2 (0985139979)
3. Si ambas fallan → Programa reintento en 10 minutos
4. Estado del sistema visible en `/health`

## 📱 Configurar SMS Forwarder

1. Instalar "SMS Forwarder" en el móvil con la SIM Tigo
2. Configurar webhook:
   - URL: `http://TU_IP:5002/otp`
   - Método: POST
   - Formato: JSON
   - Campos: `from`, `content`, `sim`

## 🔧 Troubleshooting

### API no responde
```bash
# Verificar proceso
ps aux | grep api.py

# Ver logs
tail -f logs/api.log
```

### Error de autenticación
```bash
# Ver estado del sistema
curl http://localhost:5000/health

# Forzar reintento manual
curl -X POST "http://localhost:5000/api/admin/auth/retry" \
  -H "X-Admin-Key: ZoluGames" \
  -H "X-Admin-Password: Gamehag2025*"
```

### No llegan SMS
```bash
# Verificar receptor SMS
curl http://localhost:5002/health

# Ver último OTP recibido
curl http://localhost:5002/last_otp
```

### Fingerprint inválido
```bash
# Forzar renovación (requiere OTP)
curl -X POST "http://localhost:5000/api/admin/auth/fingerprint" \
  -H "X-Admin-Key: ZoluGames" \
  -H "X-Admin-Password: Gamehag2025*"
```

### Cambiar de cuenta
```bash
curl -X POST "http://localhost:5000/api/admin/auth/switch" \
  -H "X-Admin-Key: ZoluGames" \
  -H "X-Admin-Password: Gamehag2025*"
```

## 📊 Puertos

| Puerto | Servicio |
|--------|----------|
| 5000 | API REST Principal |
| 5002 | Receptor SMS |

## 📚 Documentación Completa

Ver **API_DOCUMENTATION.md** para documentación detallada incluyendo:
- Arquitectura del sistema
- Todos los endpoints con ejemplos
- Estructura de datos
- Guía de troubleshooting
- Credenciales de desarrollo

## 📜 Licencia

Uso interno - No distribuir
