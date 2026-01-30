#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config.py - Configuración del Bot Telegram OTP
"""

import os

# Token del bot (obtener de @BotFather)
BOT_TOKEN = "8458859222:AAFGCvcvYnnxxvOiSenjfnTBkhKj1cW43YM"

# ID del administrador (tu Telegram ID)
ADMIN_TELEGRAM_ID = 6317586539

# URL de la webapp
WEB_URL = "http://155.117.45.228:8000"

# Tiempo de expiración del OTP en minutos
OTP_EXPIRATION_MINUTES = 10

# === RUTA COMPARTIDA PARA OTPs ===
# Usar ruta absoluta para que WebApp pueda leer los OTPs
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DATA_DIR = os.path.join(BASE_DIR, "shared_data")
OTP_FILE = os.path.join(SHARED_DATA_DIR, "otp_codes.json")

# Crear directorio compartido si no existe
os.makedirs(SHARED_DATA_DIR, exist_ok=True)

# Directorio local de datos (para otros archivos)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
