#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bot.py - Bot de Telegram para generar códigos OTP
"""

import logging
import json
import secrets
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    BOT_TOKEN,
    ADMIN_TELEGRAM_ID,
    WEB_URL,
    OTP_EXPIRATION_MINUTES,
    OTP_FILE
)

# Configurar logging
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
# GESTOR DE OTPs
# ============================================================

class OTPManager:
    """Gestiona los códigos OTP"""
    
    def __init__(self, otp_file: str):
        self.otp_file = otp_file
        self._ensure_file()
    
    def _ensure_file(self):
        """Crea el archivo si no existe"""
        try:
            with open(self.otp_file, 'r') as f:
                json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            with open(self.otp_file, 'w') as f:
                json.dump({}, f)
    
    def _load(self) -> dict:
        """Carga los OTPs"""
        try:
            with open(self.otp_file, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    def _save(self, data: dict):
        """Guarda los OTPs"""
        with open(self.otp_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def generate(self, telegram_id: int) -> str:
        """Genera un nuevo OTP para un usuario"""
        otp_code = str(secrets.randbelow(900000) + 100000)  # 6 dígitos
        
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
        """Verifica un código OTP"""
        data = self._load()
        tid_str = str(telegram_id)
        
        if tid_str not in data:
            logger.warning(f"No hay OTP para {telegram_id}")
            return False
        
        otp_data = data[tid_str]
        
        # Verificar si ya fue usado
        if otp_data.get('used', False):
            logger.warning(f"OTP ya usado para {telegram_id}")
            return False
        
        # Verificar expiración
        try:
            expires = datetime.fromisoformat(otp_data['expires_at'])
            if datetime.now() > expires:
                logger.warning(f"OTP expirado para {telegram_id}")
                return False
        except:
            return False
        
        # Verificar código
        if otp_data['code'] != otp_code:
            logger.warning(f"OTP incorrecto para {telegram_id}")
            return False
        
        # Marcar como usado
        data[tid_str]['used'] = True
        data[tid_str]['used_at'] = datetime.now().isoformat()
        self._save(data)
        
        logger.info(f"OTP verificado correctamente para {telegram_id}")
        return True


# Instancia global
otp_manager = OTPManager(OTP_FILE)


# Función exportada para uso externo
def verify_otp_code(telegram_id: int, otp_code: str) -> bool:
    """Función exportada para verificar OTP desde otros módulos"""
    return otp_manager.verify(telegram_id, otp_code)


# ============================================================
# COMANDOS DEL BOT
# ============================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user = update.effective_user
    is_admin = user.id == ADMIN_TELEGRAM_ID
    
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
    import os
    os.makedirs('logs', exist_ok=True)
    
    # Crear aplicación
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Registrar comandos
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("otp", otp_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("Bot iniciado correctamente")
    
    # Ejecutar
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
