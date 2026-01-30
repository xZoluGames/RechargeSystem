#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py - Configuración de la WebApp
"""

import os

# === API REST ===
API_URL = "http://localhost:5000"
ADMIN_API_KEY = "ZoluGames"
ADMIN_API_PASSWORD = "Gamehag2025*"

# === SERVIDOR WEB ===
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000

# === ADMIN ===
ADMIN_TELEGRAM_ID = 6317586539

# === JWT ===
JWT_SECRET = "tu_clave_secreta_cambiar_en_produccion_abc123xyz"
JWT_ALGORITHM = "HS256"
SESSION_HOURS = 72           # 3 días
SESSION_REMEMBER_HOURS = 504  # 21 días

# === RUTA COMPARTIDA PARA OTPs ===
# Debe coincidir con la del bot
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DATA_DIR = os.path.join(BASE_DIR, "shared_data")
OTP_FILE = os.path.join(SHARED_DATA_DIR, "otp_codes.json")

# Crear directorio compartido si no existe
os.makedirs(SHARED_DATA_DIR, exist_ok=True)

# === DIRECTORIOS LOCALES ===
LOCAL_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SESSIONS_FILE = os.path.join(LOCAL_DATA_DIR, "sessions.json")

os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
