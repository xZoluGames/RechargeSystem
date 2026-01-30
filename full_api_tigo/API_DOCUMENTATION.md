# 📱 API de Recargas Tigo - Documentación Completa

## Índice
1. [Descripción General](#descripción-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Autenticación Tigo](#autenticación-tigo)
4. [Configuración](#configuración)
5. [Endpoints de la API](#endpoints-de-la-api)
6. [Ejemplos con cURL](#ejemplos-con-curl)
7. [Estructura de Datos](#estructura-de-datos)
8. [Estados del Sistema](#estados-del-sistema)
9. [Troubleshooting](#troubleshooting)
10. [Credenciales de Desarrollo](#credenciales-de-desarrollo)

---

## Descripción General

Esta API REST permite realizar recargas de paquetes Tigo Money de forma programática. El sistema soporta:

- **Autenticación dual**: Nuevo método con fingerprint + método legacy como fallback
- **Múltiples cuentas Tigo**: Rotación automática entre cuentas
- **Gestión de claves API**: Control de acceso y límites de saldo
- **Historial de transacciones**: Registro completo de recargas
- **Reintentos automáticos**: Si la autenticación falla, reintenta cada 10 minutos

### Puertos de Servicio
| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| API REST | 5000 | API principal de recargas |
| SMS Receiver | 5002 | Receptor de SMS/OTP |

---

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENTE                                  │
│  (Aplicación, Bot, Sistema Externo)                             │
└─────────────────────┬───────────────────────────────────────────┘
                      │ HTTP REST (Puerto 5000)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      api.py                                      │
│  • Endpoints REST                                                │
│  • Validación de API Keys                                        │
│  • Control de Admin                                              │
└─────────┬───────────────────┬───────────────────────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────┐  ┌────────────────────────────────────────────┐
│  key_manager.py │  │        tigo_auth_new.py                    │
│                 │  │  • TigoAuthNew (por cuenta)                │
│  • Generación   │  │  • TigoAuthManager (gestor multi-cuenta)   │
│  • Validación   │  │  • Fingerprint + OTP                       │
│  • Límites      │  │  • Tokens (token_aws, access_token)        │
└─────────────────┘  └────────────────────┬───────────────────────┘
                                          │
                                          ▼
                     ┌────────────────────────────────────────────┐
                     │        tigo_api.py                         │
                     │  • Consulta de paquetes                    │
                     │  • Creación de órdenes                     │
                     │  • Seguimiento de recargas                 │
                     └────────────────────┬───────────────────────┘
                                          │
                                          ▼
                     ┌────────────────────────────────────────────┐
                     │        API Tigo Money                      │
                     │  auth.api.py-tigomoney.io                  │
                     │  nwallet.py.tigomoney.io                   │
                     └────────────────────────────────────────────┘
```

### Archivos del Sistema

| Archivo | Descripción |
|---------|-------------|
| `api.py` | API REST principal (Flask) |
| `tigo_auth_new.py` | Nuevo sistema de autenticación con fingerprint |
| `tigo_auth_legacy.py` | Sistema de autenticación antiguo (fallback) |
| `tigo_api.py` | Operaciones con API de Tigo (paquetes, recargas) |
| `key_manager.py` | Gestión de claves de API |
| `package_manager.py` | Categorización de paquetes |
| `sms_receiver.py` | Receptor de SMS para OTP |
| `config.py` | Configuración central |

---

## Autenticación Tigo

### Método Nuevo (Fingerprint)

El nuevo método de autenticación usa un fingerprint persistente que, una vez validado con OTP, permite login sin código SMS.

#### Flujo de Autenticación

```
1. POST /access/task
   ├── Si otp: false → Fingerprint válido, ir a paso 5
   └── Si otp: true  → Fingerprint nuevo, ir a paso 2

2. POST /otp (solicitar código)
   └── Tigo envía SMS con código

3. Esperar SMS (máx 3 minutos)
   └── sms_receiver.py captura el OTP

4. PUT /otp (validar código)
   └── Si exitoso, fingerprint queda validado

5. GET /auth/validate/{uuid}
   └── Valida el UUID de sesión

6. POST /auth/login
   └── Obtiene tokens: token_aws, access_token, refresh_token
```

#### Tokens Obtenidos

```json
{
  "token_aws": "eyJhbGci...",      // ← USAR ESTE para API de recargas
  "access_token": "eeea0a82...",   // Token de acceso (NO para recargas)
  "refresh_token": "ba0663d0...",  // Token de renovación
  "expires_in": 6000,              // Segundos hasta expiración
  "account_info": {...}            // Info de la cuenta
}
```

**⚠️ IMPORTANTE**: Para las operaciones de recargas y consulta de paquetes, se debe usar `token_aws` (el JWT largo), NO `access_token`.

### Método Legacy (Fallback)

Si el método nuevo falla, el sistema intenta automáticamente con el método legacy que usa un flujo de autenticación diferente basado en tokens tradicionales.

### Inicialización Dual

Al arrancar el sistema:

1. Intenta autenticar cuenta 1 (0985308247)
2. Intenta autenticar cuenta 2 (0985139979)
3. Si ambas fallan → Programa reintento en 10 minutos
4. Repite hasta que al menos una cuenta funcione

---

## Configuración

### Archivo: `config.py`

```python
# Cuentas Tigo disponibles
TIGO_ACCOUNTS = {
    "0985308247": {
        "password": "0612",
        "model": "iPhone 2026 Pro Max"
    },
    "0985139979": {
        "password": "0612",
        "model": "Samsung Galaxy S26"
    }
}

# Credenciales Admin (CAMBIAR EN PRODUCCIÓN)
ADMIN_API_KEY = "ZoluGames"
ADMIN_PASSWORD = "Gamehag2025*"

# Tiempo de reintento tras fallo de auth
RETRY_DELAY_MINUTES = 10
```

### Archivos de Datos

| Archivo | Ruta | Contenido |
|---------|------|-----------|
| `fingerprints.json` | `data/` | Fingerprints validados por cuenta |
| `tokens.json` | `data/` | Tokens activos por cuenta |
| `keys_database.json` | `data/` | Base de datos de API keys |
| `historial_recargas.json` | `data/` | Historial de transacciones |

---

## Endpoints de la API

### Públicos

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/` | Información de la API |
| GET | `/health` | Estado del sistema |

### Requieren API Key

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET/POST | `/api/packages` | Obtener paquetes disponibles |
| POST | `/api/recharge` | Realizar una recarga |
| GET | `/api/balance` | Consultar saldo de la clave |
| GET | `/api/history` | Historial de recargas |
| GET | `/api/verify_order/{id}` | Verificar estado de orden |

### Requieren Admin

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/admin/auth/init` | Inicializar autenticación |
| POST | `/api/admin/auth/refresh` | Refrescar tokens |
| POST | `/api/admin/auth/fingerprint` | Renovar fingerprint |
| POST | `/api/admin/auth/switch` | Cambiar de cuenta Tigo |
| POST | `/api/admin/auth/retry` | Forzar reintento de init |
| GET/POST | `/api/admin/keys` | Listar/Crear claves |
| PUT | `/api/admin/keys/{key}` | Modificar clave |
| DELETE | `/api/admin/keys/{key}` | Desactivar clave |
| GET | `/api/admin/history` | Historial completo |

---

## Ejemplos con cURL

### Credenciales de Desarrollo

```bash
# Variables de entorno (para facilitar ejemplos)
export API_URL="http://localhost:5000"
export ADMIN_KEY="ZoluGames"
export ADMIN_PASS="Gamehag2025*"
```

### 1. Verificar Estado del Sistema

```bash
curl -X GET "$API_URL/health"
```

**Respuesta:**
```json
{
  "success": true,
  "status": "healthy",
  "timestamp": "2026-01-30T10:00:00",
  "system": {
    "initialized": true,
    "auth_method": "new",
    "auth_status": "valid",
    "system_state": "READY",
    "current_account": "0985308247",
    "account_name": "JOSE LUIS CABALLERO GAVILAN",
    "retry_scheduled": false,
    "accounts": {...}
  }
}
```

### 2. Crear una Clave de API

```bash
curl -X POST "$API_URL/api/admin/keys" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "X-Admin-Password: $ADMIN_PASS" \
  -d '{
    "max_amount": 1000000,
    "valid_days": 365,
    "description": "Clave de prueba"
  }'
```

**Respuesta:**
```json
{
  "success": true,
  "key": "TG-XXXX-XXXX-XXXX",
  "info": {
    "max_amount": 1000000,
    "remaining": 1000000,
    "expires_at": "2027-01-30T10:00:00"
  }
}
```

### 3. Consultar Paquetes

```bash
# Guardar la clave generada
export API_KEY="TG-XXXX-XXXX-XXXX"

curl -X GET "$API_URL/api/packages?destination=0981123456" \
  -H "X-API-Key: $API_KEY"
```

**Respuesta:**
```json
{
  "success": true,
  "destination": "0981123456",
  "packages": [
    {
      "id": "PACK_001",
      "name": "Pack 10GB",
      "description": "10GB + 100 minutos",
      "amount": 50000,
      "category": "COMBOS"
    },
    ...
  ],
  "total": 25
}
```

### 4. Realizar una Recarga

```bash
curl -X POST "$API_URL/api/recharge" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "destination": "0981123456",
    "package_id": "PACK_001"
  }'
```

**Respuesta Exitosa:**
```json
{
  "success": true,
  "message": "Recarga exitosa",
  "transaction": {
    "order_id": "ORD123456789",
    "destination": "0981123456",
    "package": "Pack 10GB",
    "amount": 50000,
    "status": "SUCCESS",
    "timestamp": "2026-01-30T10:05:00"
  }
}
```

### 5. Verificar Saldo de la Clave

```bash
curl -X GET "$API_URL/api/balance" \
  -H "X-API-Key: $API_KEY"
```

**Respuesta:**
```json
{
  "success": true,
  "balance": {
    "max_amount": 1000000,
    "used": 50000,
    "remaining": 950000,
    "expires_at": "2027-01-30T10:00:00"
  }
}
```

### 6. Cambiar de Cuenta Tigo

```bash
curl -X POST "$API_URL/api/admin/auth/switch" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "X-Admin-Password: $ADMIN_PASS"
```

### 7. Forzar Reintento de Autenticación

```bash
curl -X POST "$API_URL/api/admin/auth/retry" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "X-Admin-Password: $ADMIN_PASS"
```

### 8. Ver Historial de Recargas

```bash
curl -X GET "$API_URL/api/history?limit=10" \
  -H "X-API-Key: $API_KEY"
```

---

## Estructura de Datos

### fingerprints.json

```json
{
  "0985308247": {
    "fingerprint": "0965eeb792a71525",
    "validated_at": "2026-01-30T09:00:00",
    "model": "iPhone 2026 Pro Max"
  },
  "0985139979": {
    "fingerprint": "a1b2c3d4e5f67890",
    "validated_at": "2026-01-30T09:05:00",
    "model": "Samsung Galaxy S26"
  }
}
```

### tokens.json

```json
{
  "0985308247": {
    "access_token": "eeea0a82b79eddabaa1cd6f29a4295b3",
    "refresh_token": "ba0663d0f96d19a0e5ade9d581f07a2b",
    "token_aws": "eyJhbGciOiJIUzM4NCJ9...",
    "expires_at": "2026-01-30T11:00:00",
    "account_info": {...},
    "saved_at": "2026-01-30T09:30:00"
  }
}
```

### keys_database.json

```json
{
  "TG-XXXX-XXXX-XXXX": {
    "max_amount": 1000000,
    "used_amount": 50000,
    "created_at": "2026-01-30T09:00:00",
    "expires_at": "2027-01-30T09:00:00",
    "active": true,
    "description": "Clave de prueba"
  }
}
```

---

## Estados del Sistema

### system_state

| Estado | Descripción |
|--------|-------------|
| `READY` | Todas las cuentas inicializadas correctamente |
| `PARTIAL` | Al menos una cuenta OK, otra(s) fallaron |
| `WAITING_RETRY` | Todas fallaron, esperando 10 min para reintentar |
| `ERROR` | Fallo crítico irrecuperable |

### auth_status

| Estado | Descripción |
|--------|-------------|
| `valid` | Token vigente y funcionando |
| `expired` | Token expirado, requiere renovación |
| `not_initialized` | Sistema no ha iniciado auth |

---

## Troubleshooting

### Error: "Token expirado"

**Causa**: El `token_aws` tiene duración limitada (≈100 min).

**Solución**: El sistema renueva automáticamente. Si persiste:
```bash
curl -X POST "$API_URL/api/admin/auth/refresh" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "X-Admin-Password: $ADMIN_PASS"
```

### Error: "Fingerprint no válido"

**Causa**: Tigo invalidó el fingerprint guardado.

**Solución**: Renovar fingerprint (requiere recibir OTP):
```bash
curl -X POST "$API_URL/api/admin/auth/fingerprint" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "X-Admin-Password: $ADMIN_PASS"
```

### Error: "Ambas cuentas fallaron"

**Causa**: Ninguna cuenta pudo autenticar.

**Verificar**:
1. SMS Receiver funcionando en puerto 5002
2. Conexión a internet/proxy
3. Credenciales de cuentas correctas

**Solución**: El sistema reintenta cada 10 min. Para forzar:
```bash
curl -X POST "$API_URL/api/admin/auth/retry" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "X-Admin-Password: $ADMIN_PASS"
```

### Error: "Error 403 en recargas"

**Causa**: Token incorrecto o expirado.

**Verificar**: Asegurarse que el sistema usa `token_aws` (JWT largo), no `access_token`.

### No recibe SMS/OTP

**Verificar**:
1. SMS Forwarder configurado correctamente en el móvil
2. URL apunta a `http://IP:5002/otp`
3. El móvil tiene señal y crédito
4. Revisar logs: `tail -f logs/api.log`

---

## Credenciales de Desarrollo

> ⚠️ **IMPORTANTE**: Estas credenciales son SOLO para desarrollo. Cambiarlas en producción.

### Admin

| Parámetro | Valor |
|-----------|-------|
| X-Admin-Key | `ZoluGames` |
| X-Admin-Password | `Gamehag2025*` |

### Cuentas Tigo

| Número | Password |
|--------|----------|
| 0985308247 | 0612 |
| 0985139979 | 0612 |

### Headers para API de Tigo

```
Authorization: Bearer {token_aws}
x-api-key: dxtyCQG4pUk0FZvpEi8DFwmOEUs4qX0cL4wYL9SCAL5vTgYv
x-namespace-app: com.juvo.tigomoney
x-build-app: 82000060
x-version-app: 8.2.0
```

---

## Logs

Los logs se guardan en el directorio `logs/`:

| Archivo | Contenido |
|---------|-----------|
| `api.log` | Log general de la API |
| `http_requests.log` | Requests HTTP a Tigo (debug) |
| `errors.log` | Solo errores |

### Ver logs en tiempo real

```bash
# Log general
tail -f logs/api.log

# HTTP requests (debug detallado)
tail -f logs/http_requests.log
```

---

## Licencia

Sistema propietario. Uso interno únicamente.

**Versión**: 2.1  
**Última actualización**: Enero 2026
