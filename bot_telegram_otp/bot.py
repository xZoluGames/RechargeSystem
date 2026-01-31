#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot.py - Bot de Telegram para OTP
CORREGIDO v2.3:
- Usa config.py separado para configuración
- Registra el username de Telegram en la API al generar OTP
- Soporta enlace directo de login
"""

import os
import json
import logging
import secrets
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    BOT_TOKEN,
    ADMIN_TELEGRAM_ID,
    WEB_URL,
    OTP_EXPIRATION_MINUTES,
    OTP_FILE,
    API_URL,
    SHARED_BEARER_TOKEN
)

# Crear directorios necesarios
os.makedirs('logs', exist_ok=True)
os.makedirs('data', exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# OTP MANAGER
# ============================================================
class OTPManager:
    def __init__(self, otp_file: str):
        self.otp_file = otp_file
        self._ensure_file()
    
    def _ensure_file(self):
        if not os.path.exists(self.otp_file):
            os.makedirs(os.path.dirname(self.otp_file), exist_ok=True)
            with open(self.otp_file, 'w') as f:
                json.dump({}, f)
    
    def _load(self) -> dict:
        try:
            with open(self.otp_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _save(self, data: dict):
        with open(self.otp_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def generate(self, telegram_id: int) -> str:
        otp_code = str(secrets.randbelow(900000) + 100000)
        
        data = self._load()
        data[str(telegram_id)] = {
            'code': otp_code,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=OTP_EXPIRATION_MINUTES)).isoformat(),
            'used': False
        }
        self._save(data)
        
        logger.info(f"OTP generado para {telegram_id}")
        return otp_code
    
    def verify(self, telegram_id: int, otp_code: str) -> bool:
        data = self._load()
        tid_str = str(telegram_id)
        
        if tid_str not in data:
            return False
        
        otp_data = data[tid_str]
        
        if otp_data.get('used', False):
            return False
        
        try:
            expires = datetime.fromisoformat(otp_data['expires_at'])
            if datetime.now() > expires:
                return False
        except:
            return False
        
        if otp_data['code'] != otp_code:
            return False
        
        data[tid_str]['used'] = True
        data[tid_str]['used_at'] = datetime.now().isoformat()
        self._save(data)
        
        return True


otp_manager = OTPManager(OTP_FILE)


def verify_otp_code(telegram_id: int, otp_code: str) -> bool:
    """Función exportada para verificar OTP desde otros módulos"""
    return otp_manager.verify(telegram_id, otp_code)


# ============================================================
# API HELPER - Registrar username
# ============================================================
def register_username_in_api(telegram_id: int, username: str, first_name: str):
    """Registra el username de Telegram en la API"""
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {SHARED_BEARER_TOKEN}'
        }
        data = {
            'telegram_id': telegram_id,
            'username': username or '',
            'first_name': first_name or ''
        }
        response = requests.post(
            f"{API_URL}/api/telegram/register-username",
            headers=headers,
            json=data,
            timeout=5
        )
        if response.status_code == 200:
            logger.info(f"Username registrado: {telegram_id} -> @{username}")
        else:
            logger.warning(f"No se pudo registrar username: {response.status_code}")
    except Exception as e:
        logger.warning(f"Error registrando username: {e}")


# ============================================================
# COMANDOS DEL BOT
# ============================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    is_admin = user.id == ADMIN_TELEGRAM_ID
    
    # Registrar username en la API
    register_username_in_api(user.id, user.username, user.first_name)
    
    message = f"""👋 ¡Hola {user.first_name}!

🔐 *Sistema de Autenticación OTP*

Tu ID de Telegram: `{user.id}`

📱 *¿Cómo funciona?*
1. Ve a la web: {WEB_URL}
2. Ingresa tu Telegram ID
3. Usa /otp para obtener tu código
4. Ingresa el código en la web

⚡ *Comandos disponibles:*
/otp - Obtener código de acceso
/myid - Ver tu Telegram ID
/help - Ver ayuda"""

    if is_admin:
        message += "\n\n👑 *Eres administrador*"
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def otp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /otp - Genera código OTP"""
    user = update.effective_user
    is_admin = user.id == ADMIN_TELEGRAM_ID
    
    # Registrar username en la API
    register_username_in_api(user.id, user.username, user.first_name)
    
    # Generar OTP
    otp_code = otp_manager.generate(user.id)
    
    # Crear enlace directo
    login_url = f"{WEB_URL}/?tid={user.id}&otp={otp_code}"
    
    message = f"""🔐 *Tu Código de Acceso*

`{otp_code}`

⏱️ Válido por {OTP_EXPIRATION_MINUTES} minutos
🔒 Uso único

⚡ *Acceso rápido:*
Haz clic en el botón de abajo"""

    if is_admin:
        message += "\n\n👑 *Acceso de Administrador*"
    
    # Botón de acceso rápido
    keyboard = [[InlineKeyboardButton("🚀 Iniciar Sesión", url=login_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        message,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    logger.info(f"OTP enviado a {user.id} (admin: {is_admin})")


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /myid - Muestra el Telegram ID"""
    user = update.effective_user
    
    # Registrar username en la API
    register_username_in_api(user.id, user.username, user.first_name)
    
    message = f"""🆔 *Tu Telegram ID*

`{user.id}`

📋 Copia este número para iniciar sesión en la web."""
    
    await update.message.reply_text(message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help"""
    message = """📚 *Ayuda del Bot*

*Comandos disponibles:*

/start - Mensaje de bienvenida
/otp - Obtener código de acceso (válido 10 min)
/myid - Ver tu Telegram ID
/help - Esta ayuda

*¿Problemas?*
- Asegúrate de usar el código antes de que expire
- Cada código es de uso único
- Si expira, genera uno nuevo con /otp"""
    
    await update.message.reply_text(message, parse_mode='Markdown')


# ============================================================
# MAIN
# ============================================================
def main():
    """Iniciar el bot"""
    logger.info("=" * 50)
    logger.info("INICIANDO BOT TELEGRAM OTP v2.3")
    logger.info(f"Admin ID: {ADMIN_TELEGRAM_ID}")
    logger.info(f"Web URL: {WEB_URL}")
    logger.info("=" * 50)
    
    # Crear aplicación
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Registrar comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("otp", otp_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("✅ Bot iniciado correctamente")
    
    # Ejecutar
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
