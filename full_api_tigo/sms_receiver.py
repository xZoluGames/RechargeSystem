#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sms_receiver.py - Receptor de SMS para OTP de Tigo Money
Puerto 5002
Recibe SMS desde SMS Forwarder y extrae códigos OTP
"""

from flask import Flask, request, jsonify
from datetime import datetime
import logging
import re
import os

app = Flask(__name__)

# ============================================================
# CONFIGURACIÓN
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OTP_FILE = os.path.join(BASE_DIR, "ultimo_otp.txt")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Puerto
API_PORT = 5002

# Configurar logging
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'sms_receiver.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def extract_otp(text: str) -> str:
    """
    Extrae código OTP de 6 dígitos del mensaje
    
    Patrones soportados:
    - "186976 es el codigo de verificacion..."
    - "Tu codigo es 186976"
    - "Codigo: 186976"
    - Cualquier número de 6 dígitos
    """
    if not text:
        return None
    
    text_clean = ' '.join(text.split())
    
    # PATRÓN 1: "XXXXXX es el codigo"
    pattern1 = r'(\d{6})\s+es\s+el\s+c[oó]digo'
    match = re.search(pattern1, text_clean, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # PATRÓN 2: "codigo: XXXXXX"
    pattern2 = r'c[oó]digo[:\s]+(\d{6})'
    match = re.search(pattern2, text_clean, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # PATRÓN 3: "tu codigo es XXXXXX"
    pattern3 = r'tu\s+c[oó]digo\s+es\s+(\d{6})'
    match = re.search(pattern3, text_clean, re.IGNORECASE)
    if match:
        return match.group(1)
    
    # PATRÓN 4: Cualquier 6 dígitos
    pattern4 = r'(?<!\d)(\d{6})(?!\d)'
    matches = re.findall(pattern4, text_clean)
    if matches:
        return matches[0]
    
    return None


def detect_sim_card(data: dict) -> str:
    """Detecta de qué SIM proviene el SMS"""
    sim_field = data.get('sim', '').upper()
    if 'SIM2' in sim_field or sim_field == '2':
        return 'SIM2'
    elif 'SIM1' in sim_field or sim_field == '1':
        return 'SIM1'
    
    sim_slot = str(data.get('simSlot', '')).strip()
    if sim_slot == '1':
        return 'SIM2'
    elif sim_slot == '0':
        return 'SIM1'
    
    return 'SIM1'


@app.route('/otp', methods=['POST', 'GET'])
def receive_otp():
    """
    Endpoint para recibir SMS con OTP
    
    Acepta:
    - POST con JSON: {"from": "numero", "content": "mensaje", "sim": "SIM1"}
    - POST con form-data
    - GET con query params
    """
    try:
        timestamp = datetime.now().isoformat()
        
        # Obtener datos
        if request.method == 'POST':
            if request.is_json:
                data = request.json or {}
            else:
                data = request.form.to_dict()
        else:
            data = request.args.to_dict()
        
        # Extraer información
        from_number = data.get('from', data.get('sender', 'unknown'))
        message = data.get('content', data.get('message', data.get('text', '')))
        sim_card = detect_sim_card(data)
        
        logger.info("=" * 60)
        logger.info(f"📱 SMS recibido de: {from_number}")
        logger.info(f"📟 SIM: {sim_card}")
        logger.info(f"📄 Contenido: {message[:100]}...")
        logger.info("=" * 60)
        
        # Extraer OTP
        otp = extract_otp(message)
        
        if otp:
            logger.info(f"✅ OTP EXTRAÍDO: {otp}")
            
            # Guardar OTP
            with open(OTP_FILE, 'w', encoding='utf-8') as f:
                f.write(f"{otp}\n")
                f.write(f"{timestamp}\n")
                f.write(f"{sim_card}\n")
            
            logger.info(f"💾 OTP guardado en: {OTP_FILE}")
            
            return jsonify({
                'status': 'success',
                'otp_extracted': True,
                'otp': otp,
                'sim_card': sim_card,
                'timestamp': timestamp
            }), 200
        else:
            logger.warning(f"⚠️ No se pudo extraer OTP")
            
            return jsonify({
                'status': 'success',
                'otp_extracted': False,
                'message': 'SMS recibido pero sin OTP válido',
                'timestamp': timestamp
            }), 200
        
    except Exception as e:
        logger.error(f"🚨 ERROR: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/test', methods=['GET'])
def test():
    """Endpoint de prueba"""
    return jsonify({
        'status': 'ok',
        'message': 'Servidor SMS activo',
        'port': API_PORT,
        'timestamp': datetime.now().isoformat(),
        'endpoints': {
            '/otp': 'POST/GET - Recibir SMS con OTP',
            '/test': 'GET - Estado del servidor',
            '/last_otp': 'GET - Último OTP recibido',
            '/health': 'GET - Health check',
            '/clear_otp': 'POST - Limpiar OTP'
        }
    }), 200


@app.route('/last_otp', methods=['GET'])
def get_last_otp():
    """Consultar último OTP recibido"""
    try:
        if os.path.exists(OTP_FILE):
            with open(OTP_FILE, 'r', encoding='utf-8') as f:
                lines = f.read().strip().split('\n')
            
            if len(lines) >= 2:
                otp = lines[0]
                timestamp = lines[1]
                sim_card = lines[2] if len(lines) >= 3 else 'SIM1'
                
                try:
                    otp_time = datetime.fromisoformat(timestamp)
                    age_seconds = (datetime.now() - otp_time).total_seconds()
                    
                    return jsonify({
                        'status': 'ok',
                        'otp': otp,
                        'received_at': timestamp,
                        'sim_card': sim_card,
                        'age_seconds': int(age_seconds),
                        'is_recent': age_seconds < 300
                    }), 200
                except:
                    return jsonify({
                        'status': 'ok',
                        'otp': otp,
                        'received_at': timestamp,
                        'sim_card': sim_card
                    }), 200
        
        return jsonify({
            'status': 'ok',
            'message': 'No hay OTP disponible'
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'SMS OTP Receiver',
        'port': API_PORT,
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/clear_otp', methods=['POST'])
def clear_otp():
    """Limpiar OTP actual"""
    try:
        if os.path.exists(OTP_FILE):
            os.remove(OTP_FILE)
            logger.info("🗑️ OTP limpiado")
            return jsonify({
                'status': 'success',
                'message': 'OTP limpiado'
            }), 200
        else:
            return jsonify({
                'status': 'success',
                'message': 'No había OTP'
            }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info(f"🚀 Iniciando receptor SMS en puerto {API_PORT}")
    logger.info(f"📂 Directorio base: {BASE_DIR}")
    logger.info(f"📝 Archivo OTP: {OTP_FILE}")
    logger.info("=" * 60)
    
    app.run(host='0.0.0.0', port=API_PORT, debug=False)
