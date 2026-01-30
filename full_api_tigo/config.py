#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py - Configuración central de la API Tigo
MODIFICADO: 
- Bearer token compartido obligatorio
- Configuración de roles (admin, revendedor, usuario)
- Categorías de paquetes mejoradas
- Notas administrativas predefinidas
"""

import os
from datetime import datetime

# ============================================================
#  BEARER TOKEN COMPARTIDO (NUEVO)
# ============================================================
# Este token es OBLIGATORIO en todas las solicitudes a la API
# Debe coincidir con el configurado en webapp/config.py
# IMPORTANTE: Cambiar en producción
SHARED_BEARER_TOKEN = "TigoRecargas2026SecureToken_XyZ789"

# ============================================================
#  CONFIGURACIÓN DE CUENTAS TIGO
# ============================================================
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

DEFAULT_TIGO_USER = "0985308247"

# ============================================================
#  ENDPOINTS TIGO - NUEVO SISTEMA AUTH
# ============================================================
TIGO_AUTH_HOST = "auth.api.py-tigomoney.io"
TIGO_AUTH_BASE_URL = f"https://{TIGO_AUTH_HOST}"

TIGO_AUTH_HEADERS = {
    "User-Agent": "Dart/3.7 (dart:io)",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "x-api-key": "dxtyCQG4pUk0FZvpEi8DFwmOEUs4qX0cL4wYL9SCAL5vTgYv",
    "x-namespace-app": "com.juvo.tigomoney",
    "x-build-app": "82000060",
    "x-version-app": "8.2.0"
}

OTP_DEVICE_CODE = "Fj7V0f6zKsg"

# ============================================================
#  ENDPOINTS TIGO - SISTEMA ANTIGUO (FALLBACK)
# ============================================================
TIGO_IDENTITY_HOST = "py-prod-identity-backend.py.tigomoney.io"
TIGO_WALLET_HOST = "nwallet.py.tigomoney.io"
TIGO_BASE_URL_LOGIN = f"https://{TIGO_IDENTITY_HOST}"
TIGO_BASE_URL_API = f"https://{TIGO_WALLET_HOST}"

TIGO_API_KEY = "rqt5y3XnRI6FM17kKuENR53J2DUTTOM35djPZl6I"
TIGO_API_KEY_LOGIN = "JjKPsTXMRJ2T3HFyhtaDX9iQkb7M7ZKc2kwP54TL"
TIGO_API_KEY_AUTH = "rmvRcn4NUN7GtPwTsFFrX1zHfwhQJgYg1hnOHhjU"
TIGO_IDENTITY_API_KEY = "H6Uk74mroet8szORwv5uDvrGPfAbhQjo"
TIGO_WALLET_API_KEY = "rmvRcn4NUN7GtPwTsFFrX1zHfwhQJgYg1hnOHhjU"

# ============================================================
#  CONFIGURACIÓN DE RED
# ============================================================
PROXY_CONFIG = {
    'http': 'http://3793b16f509a810299c7__cr.py:54b0f07f9f44fe73@gw.dataimpulse.com:823',
    'https': 'http://3793b16f509a810299c7__cr.py:54b0f07f9f44fe73@gw.dataimpulse.com:823'
}
REQUEST_TIMEOUT = 120
MAX_RETRY_ATTEMPTS = 3

# ============================================================
#  CONFIGURACIÓN SMS/OTP
# ============================================================
SMS_WAIT_TIMEOUT = 180
SMS_CHECK_INTERVAL = 2
MAX_OTP_ATTEMPTS = 3

# ============================================================
#  RUTAS Y DIRECTORIOS
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")

KEYS_FILE = os.path.join(DATA_DIR, "keys_database.json")
HISTORY_FILE = os.path.join(DATA_DIR, "historial_recargas.json")
FINGERPRINTS_FILE = os.path.join(DATA_DIR, "fingerprints.json")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
FAILED_ORDERS_FILE = os.path.join(DATA_DIR, "failed_orders.json")

# NUEVOS archivos para roles y revendedores
RESELLERS_FILE = os.path.join(DATA_DIR, "resellers.json")
KEY_MODIFICATIONS_FILE = os.path.join(DATA_DIR, "key_modifications.json")

OTP_FILE = os.path.join(BASE_DIR, "ultimo_otp.txt")

# ============================================================
#  CONFIGURACIÓN DE LOGS
# ============================================================
LOG_FILE = os.path.join(LOG_DIR, "api.log")
ERROR_FILE = os.path.join(LOG_DIR, "errors.log")
HTTP_LOG_FILE = os.path.join(LOG_DIR, "http_requests.log")
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ============================================================
#  CONFIGURACIÓN DE ÓRDENES Y RECARGAS
# ============================================================
MAX_ORDER_ATTEMPTS = 10
ORDER_CHECK_INTERVAL = 4
ORDER_COOLDOWN_SECONDS = 65
MAX_ORDER_TRACKING_TIME = 45

# ============================================================
#  PUERTOS DE SERVICIOS
# ============================================================
API_PORT = 5000
SMS_RECEIVER_PORT = 5002

# ============================================================
#  LÍMITES
# ============================================================
MIN_PACK_PRICE = 1000
MAX_PACK_PRICE = 500000

# ============================================================
#  ADMIN
# ============================================================
ADMIN_API_KEY = "ZoluGames"
ADMIN_PASSWORD = "Gamehag2025*"
ADMIN_TELEGRAM_ID = 6317586539  # Telegram ID del admin principal

# ============================================================
#  RETRY Y REINTENTOS
# ============================================================
RETRY_DELAY_MINUTES = 10

# ============================================================
#  CATEGORÍAS DE PAQUETES MEJORADAS (NUEVO)
# ============================================================
PACKAGE_CATEGORIES = {
    "INTERNET_Y_LLAMADAS": {
        "name": "Internet y Llamadas",
        "keywords": ["Internet", "Datos", "MB", "GB", "Minutos", "Combo"],
        "icon": "📱",
        "color": "#4CAF50",
        "order": 1
    },
    "ILIMITADOS": {
        "name": "Ilimitados",
        "keywords": ["Ilimitado", "Unlimited", "Sin límite", "Todo el día"],
        "icon": "♾️",
        "color": "#2196F3",
        "order": 2
    },
    "VOZ": {
        "name": "Voz",
        "keywords": ["Minutos", "Llamadas", "Voz", "Nacional", "Internacional"],
        "icon": "📞",
        "color": "#9C27B0",
        "order": 3
    },
    "OTROS": {
        "name": "Otros",
        "keywords": [],
        "icon": "📦",
        "color": "#607D8B",
        "order": 4
    }
}

# ============================================================
#  NOTAS ADMINISTRATIVAS PREDEFINIDAS (NUEVO)
# ============================================================
ADMIN_NOTES_PRESETS = {
    "AJUSTE_ADMIN": {
        "text": "Ajuste administrativo",
        "color": "#FF9800",  # Naranja
        "icon": "⚙️"
    },
    "CARGA_SALDO": {
        "text": "Carga de Saldo",
        "color": "#4CAF50",  # Verde
        "icon": "💰"
    },
    "CORRECCION_SALDO": {
        "text": "Corrección de Saldo",
        "color": "#2196F3",  # Azul
        "icon": "🔧"
    },
    "EXTENSION_VALIDEZ": {
        "text": "Extensión de Validez",
        "color": "#9C27B0",  # Púrpura
        "icon": "📅"
    },
    "DESVINCULACION": {
        "text": "Desvinculación de cuenta",
        "color": "#F44336",  # Rojo
        "icon": "🔓"
    },
    "VINCULACION": {
        "text": "Vinculación de cuenta",
        "color": "#00BCD4",  # Cyan
        "icon": "🔗"
    },
    "BONUS": {
        "text": "Bonificación",
        "color": "#8BC34A",  # Verde claro
        "icon": "🎁"
    },
    "PENALIZACION": {
        "text": "Penalización",
        "color": "#E91E63",  # Rosa
        "icon": "⚠️"
    }
}

# ============================================================
#  ROLES DEL SISTEMA (NUEVO)
# ============================================================
USER_ROLES = {
    "ADMIN": {
        "name": "Administrador",
        "permissions": ["all"],
        "description": "Acceso total al sistema"
    },
    "RESELLER": {
        "name": "Revendedor",
        "permissions": ["view_assigned_users", "recharge", "view_own_balance"],
        "description": "Puede ver usuarios asignados y realizar recargas"
    },
    "USER": {
        "name": "Usuario",
        "permissions": ["recharge", "view_own_balance", "view_own_history"],
        "description": "Usuario normal con acceso a recargas"
    }
}

# ============================================================
#  FUNCIONES HELPER
# ============================================================
def ensure_directories():
    """Crea los directorios necesarios si no existen"""
    for directory in [LOG_DIR, DATA_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✓ Directorio creado: {directory}")

def get_timestamp():
    """Retorna timestamp actual en formato ISO"""
    return datetime.now().isoformat()

def get_account_config(username: str = None) -> dict:
    """Obtiene la configuración de una cuenta Tigo"""
    if username is None:
        username = DEFAULT_TIGO_USER
    return TIGO_ACCOUNTS.get(username, TIGO_ACCOUNTS[DEFAULT_TIGO_USER])

def print_config_info():
    """Imprime información de configuración al inicio"""
    print("=" * 60)
    print("CONFIGURACIÓN DEL SISTEMA - API TIGO v2.2")
    print("=" * 60)
    print(f"Cuentas disponibles: {list(TIGO_ACCOUNTS.keys())}")
    print(f"Base DIR: {BASE_DIR}")
    print(f"Archivo OTP: {OTP_FILE}")
    print(f"Puerto API: {API_PORT}")
    print(f"Puerto SMS: {SMS_RECEIVER_PORT}")
    print(f"Bearer Token: {'Configurado' if SHARED_BEARER_TOKEN else 'NO CONFIGURADO'}")
    print(f"Roles habilitados: {list(USER_ROLES.keys())}")
    print("=" * 60)

# Crear directorios al importar
ensure_directories()
