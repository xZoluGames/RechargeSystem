#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py - WebApp para Sistema de Recargas Tigo
"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import jwt
import json
import logging
import requests
from datetime import datetime, timedelta
from functools import wraps

from config import (
    API_URL,
    ADMIN_API_KEY,
    ADMIN_API_PASSWORD,
    WEB_HOST,
    WEB_PORT,
    ADMIN_TELEGRAM_ID,
    JWT_SECRET,
    JWT_ALGORITHM,
    SESSION_HOURS,
    SESSION_REMEMBER_HOURS,
    OTP_FILE,
    LOCAL_DATA_DIR,
    SESSIONS_FILE
)

# Configurar logging
import os
os.makedirs('logs', exist_ok=True)
os.makedirs(LOCAL_DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/web.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)
app.secret_key = JWT_SECRET


# ============================================================
# VERIFICACIÓN OTP (Lee archivo compartido)
# ============================================================

def verify_otp_code(telegram_id: int, otp_code: str) -> bool:
    """
    Verifica un código OTP leyendo el archivo compartido
    """
    try:
        # Leer archivo de OTPs compartido
        if not os.path.exists(OTP_FILE):
            logger.error(f"Archivo OTP no existe: {OTP_FILE}")
            return False
        
        with open(OTP_FILE, 'r') as f:
            data = json.load(f)
        
        tid_str = str(telegram_id)
        
        if tid_str not in data:
            logger.warning(f"No hay OTP para telegram_id {telegram_id}")
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
        except Exception as e:
            logger.error(f"Error parseando fecha: {e}")
            return False
        
        # Verificar código
        if otp_data.get('code') != otp_code:
            logger.warning(f"OTP incorrecto para {telegram_id}: esperado {otp_data.get('code')}, recibido {otp_code}")
            return False
        
        # Marcar como usado
        data[tid_str]['used'] = True
        data[tid_str]['used_at'] = datetime.now().isoformat()
        
        with open(OTP_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"OTP verificado correctamente para {telegram_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error verificando OTP: {e}")
        return False


# ============================================================
# GESTIÓN DE SESIONES
# ============================================================

def _load_sessions() -> dict:
    try:
        with open(SESSIONS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def _save_sessions(data: dict):
    with open(SESSIONS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def create_token(telegram_id: int, is_admin: bool, remember: bool = False) -> str:
    """Crea un JWT token"""
    hours = SESSION_REMEMBER_HOURS if remember else SESSION_HOURS
    expires = datetime.utcnow() + timedelta(hours=hours)
    
    payload = {
        'telegram_id': telegram_id,
        'is_admin': is_admin,
        'exp': expires,
        'iat': datetime.utcnow()
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Guardar sesión
    sessions = _load_sessions()
    tid_str = str(telegram_id)
    if tid_str not in sessions:
        sessions[tid_str] = []
    
    sessions[tid_str].append({
        'token': token,
        'created_at': datetime.now().isoformat(),
        'expires_at': expires.isoformat()
    })
    _save_sessions(sessions)
    
    return token

def verify_token(token: str) -> dict:
    """Verifica un JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ============================================================
# DECORADORES
# ============================================================

def require_auth(f):
    """Requiere autenticación"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'No autorizado'}), 401
        
        token = auth_header.split(' ')[1]
        payload = verify_token(token)
        
        if not payload:
            return jsonify({'success': False, 'error': 'Token inválido'}), 401
        
        request.telegram_id = payload['telegram_id']
        request.is_admin = payload.get('is_admin', False)
        
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    """Requiere ser admin"""
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if not request.is_admin:
            return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
        return f(*args, **kwargs)
    return decorated


# ============================================================
# HELPER: API REQUEST
# ============================================================

def api_request(method: str, endpoint: str, data: dict = None, is_admin: bool = False, api_key: str = None):
    """Hace request a la API REST"""
    url = f"{API_URL}{endpoint}"
    headers = {'Content-Type': 'application/json'}
    
    if is_admin:
        headers['X-Admin-Key'] = ADMIN_API_KEY
        headers['X-Admin-Password'] = ADMIN_API_PASSWORD
    elif api_key:
        headers['X-API-Key'] = api_key
    
    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, params=data, timeout=30)
        elif method == 'POST':
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == 'PUT':
            resp = requests.put(url, headers=headers, json=data, timeout=30)
        elif method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return None, "Método no soportado"
        
        return resp.json(), None
    except requests.exceptions.ConnectionError:
        return None, "API no disponible"
    except Exception as e:
        return None, str(e)


# ============================================================
# RUTAS: PÁGINAS
# ============================================================

@app.route('/')
def login_page():
    return render_template('login.html')

@app.route('/user')
def user_page():
    return render_template('user.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')


# ============================================================
# RUTAS: AUTENTICACIÓN
# ============================================================

@app.route('/api/auth/verify-otp', methods=['POST'])
def auth_verify_otp():
    """Verifica OTP y devuelve token"""
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        otp_code = data.get('otp_code')
        remember = data.get('remember', False)
        
        if not telegram_id or not otp_code:
            return jsonify({'success': False, 'error': 'Datos incompletos'}), 400
        
        telegram_id = int(telegram_id)
        otp_code = str(otp_code).strip()
        
        # Verificar OTP
        if not verify_otp_code(telegram_id, otp_code):
            return jsonify({'success': False, 'error': 'Código incorrecto o expirado'}), 401
        
        # Determinar si es admin
        is_admin = telegram_id == ADMIN_TELEGRAM_ID
        
        # Crear token
        token = create_token(telegram_id, is_admin, remember)
        
        logger.info(f"Login exitoso: {telegram_id} (admin: {is_admin})")
        
        return jsonify({
            'success': True,
            'token': token,
            'is_admin': is_admin,
            'telegram_id': telegram_id,
            'redirect': '/admin' if is_admin else '/user'
        })
        
    except Exception as e:
        logger.error(f"Error en verify-otp: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def auth_logout():
    """Cierra sesión"""
    # Podríamos invalidar el token aquí si quisiéramos
    return jsonify({'success': True})


# ============================================================
# RUTAS: USUARIO
# ============================================================

@app.route('/api/user/info', methods=['GET'])
@require_auth
def user_info():
    """Info del usuario"""
    return jsonify({
        'success': True,
        'user': {
            'telegram_id': request.telegram_id,
            'is_admin': request.is_admin
        }
    })

@app.route('/api/packages', methods=['GET', 'POST'])
@require_auth
def get_packages():
    """Obtiene paquetes"""
    api_key = request.headers.get('X-API-Key')
    
    if request.method == 'POST':
        data = request.get_json()
    else:
        data = request.args.to_dict()
    
    result, error = api_request('POST', '/api/packages', data, api_key=api_key)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)

@app.route('/api/recharge', methods=['POST'])
@require_auth
def do_recharge():
    """Realiza recarga"""
    api_key = request.headers.get('X-API-Key')
    data = request.get_json()
    
    result, error = api_request('POST', '/api/recharge', data, api_key=api_key)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)

@app.route('/api/balance', methods=['GET'])
@require_auth
def get_balance():
    """Obtiene saldo"""
    api_key = request.headers.get('X-API-Key')
    
    result, error = api_request('GET', '/api/balance', is_admin=False, api_key=api_key)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)

@app.route('/api/history', methods=['GET'])
@require_auth
def get_history():
    """Obtiene historial"""
    api_key = request.headers.get('X-API-Key')
    
    result, error = api_request('GET', '/api/history', is_admin=False, api_key=api_key)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


# ============================================================
# RUTAS: ADMIN
# ============================================================

@app.route('/api/admin/health', methods=['GET'])
@require_admin
def admin_health():
    """Estado del sistema"""
    result, error = api_request('GET', '/health', is_admin=True)
    
    if error:
        return jsonify({
            'success': True,
            'api_status': 'offline',
            'error': error
        })
    
    return jsonify({
        'success': True,
        'api_status': 'online',
        'data': result
    })

@app.route('/api/admin/keys', methods=['GET', 'POST'])
@require_admin
def admin_keys():
    """Gestionar claves"""
    if request.method == 'GET':
        result, error = api_request('GET', '/api/admin/keys', is_admin=True)
    else:
        data = request.get_json()
        result, error = api_request('POST', '/api/admin/generate_key', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)

@app.route('/api/admin/keys/<key>', methods=['PUT', 'DELETE'])
@require_admin
def admin_key_action(key):
    """Modificar/eliminar clave"""
    if request.method == 'DELETE':
        result, error = api_request('DELETE', f'/api/admin/keys/{key}', is_admin=True)
    else:
        data = request.get_json()
        result, error = api_request('PUT', f'/api/admin/keys/{key}', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)

@app.route('/api/admin/history', methods=['GET'])
@require_admin
def admin_history():
    """Historial completo"""
    result, error = api_request('GET', '/api/admin/history', is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)

@app.route('/api/admin/auth/<action>', methods=['POST'])
@require_admin
def admin_auth_action(action):
    """Acciones de auth"""
    endpoint_map = {
        'init': '/api/admin/force_reauth',
        'refresh': '/api/admin/force_reauth',
    }
    
    endpoint = endpoint_map.get(action)
    if not endpoint:
        return jsonify({'success': False, 'error': 'Acción no válida'}), 400
    
    result, error = api_request('POST', endpoint, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    logger.info(f"Iniciando WebApp en {WEB_HOST}:{WEB_PORT}")
    logger.info(f"Archivo OTP: {OTP_FILE}")
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
