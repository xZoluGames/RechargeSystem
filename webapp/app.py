#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py - WebApp para Sistema de Recargas Tigo
MODIFICADO:
- Bearer token obligatorio en todas las solicitudes a la API
- Soporte para roles (admin, revendedor, usuario)
- Endpoints para modificación de claves
- Soporte para categorías de paquetes
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
    SHARED_BEARER_TOKEN,
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

app = Flask(__name__)
CORS(app)
app.secret_key = JWT_SECRET


# ============================================================
# VERIFICACIÓN OTP
# ============================================================
def verify_otp_code(telegram_id: int, otp_code: str) -> bool:
    """Verifica un código OTP"""
    try:
        if not os.path.exists(OTP_FILE):
            logger.error(f"Archivo OTP no existe: {OTP_FILE}")
            return False
        
        with open(OTP_FILE, 'r') as f:
            data = json.load(f)
        
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
        
        if otp_data.get('code') != otp_code:
            return False
        
        data[tid_str]['used'] = True
        with open(OTP_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        return True
        
    except Exception as e:
        logger.error(f"Error verificando OTP: {e}")
        return False


# ============================================================
# JWT TOKENS
# ============================================================
def create_token(telegram_id: int, is_admin: bool = False, 
                is_reseller: bool = False, remember: bool = False) -> str:
    """Crea un token JWT"""
    hours = SESSION_REMEMBER_HOURS if remember else SESSION_HOURS
    payload = {
        'telegram_id': telegram_id,
        'is_admin': is_admin,
        'is_reseller': is_reseller,
        'exp': datetime.utcnow() + timedelta(hours=hours),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verifica y decodifica un token JWT"""
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
        request.is_reseller = payload.get('is_reseller', False)
        
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


def require_reseller_or_admin(f):
    """Requiere ser revendedor o admin"""
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if not request.is_admin and not request.is_reseller:
            return jsonify({'success': False, 'error': 'Acceso denegado'}), 403
        return f(*args, **kwargs)
    return decorated


# ============================================================
# HELPER: API REQUEST
# ============================================================
def api_request(method: str, endpoint: str, data: dict = None, 
               is_admin: bool = False, api_key: str = None,
               telegram_id: int = None):
    """
    Hace request a la API REST con Bearer token obligatorio
    """
    url = f"{API_URL}{endpoint}"
    
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {SHARED_BEARER_TOKEN}'
    }
    
    if is_admin:
        headers['X-Admin-Key'] = ADMIN_API_KEY
        headers['X-Admin-Password'] = ADMIN_API_PASSWORD
    
    if api_key:
        headers['X-API-Key'] = api_key
    
    if telegram_id:
        headers['X-Telegram-ID'] = str(telegram_id)
    
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

@app.route('/reseller')
def reseller_page():
    return render_template('reseller.html')


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
        
        if not verify_otp_code(telegram_id, otp_code):
            return jsonify({'success': False, 'error': 'Código incorrecto o expirado'}), 401
        
        is_admin = telegram_id == ADMIN_TELEGRAM_ID
        
        # Verificar si es revendedor consultando la API
        is_reseller = False
        if not is_admin:
            result, _ = api_request('GET', f'/api/admin/resellers/{telegram_id}', is_admin=True)
            if result and result.get('success'):
                is_reseller = True
        
        token = create_token(telegram_id, is_admin, is_reseller, remember)
        
        # Determinar redirección
        if is_admin:
            redirect = '/admin'
        elif is_reseller:
            redirect = '/reseller'
        else:
            redirect = '/user'
        
        return jsonify({
            'success': True,
            'token': token,
            'is_admin': is_admin,
            'is_reseller': is_reseller,
            'telegram_id': telegram_id,
            'redirect': redirect
        })
        
    except Exception as e:
        logger.error(f"Error en verify-otp: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def auth_logout():
    """Cierra sesión"""
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
            'is_admin': request.is_admin,
            'is_reseller': request.is_reseller
        }
    })


@app.route('/api/packages', methods=['GET', 'POST'])
@require_auth
def get_packages():
    """Obtiene paquetes organizados por categorías"""
    if request.method == 'POST':
        data = request.get_json()
        api_key = data.get('api_key') if data else None
    else:
        data = request.args.to_dict()
        api_key = request.args.get('api_key')
    
    if not api_key:
        api_key = request.headers.get('X-API-Key')
    
    result, error = api_request('POST', '/api/packages', data, 
                               api_key=api_key, telegram_id=request.telegram_id)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/recharge', methods=['POST'])
@require_auth
def do_recharge():
    """Realiza recarga"""
    data = request.get_json()
    api_key = data.get('api_key') if data else None
    
    if not api_key:
        api_key = request.headers.get('X-API-Key')
    
    result, error = api_request('POST', '/api/recharge', data, 
                               api_key=api_key, telegram_id=request.telegram_id)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/balance', methods=['GET'])
@require_auth
def get_balance():
    """Obtiene saldo"""
    api_key = request.args.get('api_key') or request.headers.get('X-API-Key')
    
    result, error = api_request('GET', '/api/balance', 
                               api_key=api_key, telegram_id=request.telegram_id)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/history', methods=['GET'])
@require_auth
def get_history():
    """Obtiene historial con modificaciones"""
    api_key = request.args.get('api_key') or request.headers.get('X-API-Key')
    
    result, error = api_request('GET', '/api/history', 
                               api_key=api_key, telegram_id=request.telegram_id)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/package-categories', methods=['GET'])
@require_auth
def get_package_categories():
    """Obtiene categorías de paquetes"""
    result, error = api_request('GET', '/api/package-categories')
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


# ============================================================
# RUTAS: REVENDEDOR
# ============================================================
@app.route('/api/reseller/users', methods=['GET'])
@require_reseller_or_admin
def reseller_users():
    """Obtiene usuarios asignados al revendedor"""
    result, error = api_request('GET', '/api/reseller/users', 
                               telegram_id=request.telegram_id,
                               is_admin=request.is_admin)
    
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


@app.route('/api/admin/status', methods=['GET'])
@require_admin
def admin_status():
    """Estado completo"""
    result, error = api_request('GET', '/api/admin/status', is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/recharge', methods=['POST'])
@require_admin
def admin_recharge():
    """Recarga de admin sin límite"""
    data = request.get_json()
    
    result, error = api_request('POST', '/api/admin/recharge', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/keys', methods=['GET', 'POST'])
@require_admin
def admin_keys():
    """Gestionar claves"""
    if request.method == 'GET':
        result, error = api_request('GET', '/api/admin/keys', is_admin=True)
    else:
        data = request.get_json()
        result, error = api_request('POST', '/api/admin/keys', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/keys/<key>', methods=['GET', 'PUT', 'DELETE'])
@require_admin
def admin_key_action(key):
    """Modificar/eliminar clave"""
    if request.method == 'GET':
        result, error = api_request('GET', f'/api/admin/keys/{key}', is_admin=True)
    elif request.method == 'DELETE':
        result, error = api_request('DELETE', f'/api/admin/keys/{key}', is_admin=True)
    else:
        data = request.get_json()
        result, error = api_request('PUT', f'/api/admin/keys/{key}', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/keys/<key>/add-balance', methods=['POST'])
@require_admin
def admin_add_balance(key):
    """Agregar saldo a clave"""
    data = request.get_json()
    result, error = api_request('POST', f'/api/admin/keys/{key}/add-balance', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/keys/<key>/unlink', methods=['POST'])
@require_admin
def admin_unlink_telegram(key):
    """Desvincular Telegram de clave"""
    data = request.get_json() or {}
    result, error = api_request('POST', f'/api/admin/keys/{key}/unlink', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/keys/<key>/link', methods=['POST'])
@require_admin
def admin_link_telegram(key):
    """Vincular Telegram a clave"""
    data = request.get_json()
    result, error = api_request('POST', f'/api/admin/keys/{key}/link', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/resellers', methods=['GET', 'POST'])
@require_admin
def admin_resellers():
    """Gestionar revendedores"""
    if request.method == 'GET':
        result, error = api_request('GET', '/api/admin/resellers', is_admin=True)
    else:
        data = request.get_json()
        result, error = api_request('POST', '/api/admin/resellers', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/resellers/<int:telegram_id>', methods=['GET', 'PUT', 'DELETE'])
@require_admin
def admin_reseller_action(telegram_id):
    """Gestionar revendedor específico"""
    if request.method == 'GET':
        result, error = api_request('GET', f'/api/admin/resellers/{telegram_id}', is_admin=True)
    elif request.method == 'DELETE':
        result, error = api_request('DELETE', f'/api/admin/resellers/{telegram_id}', is_admin=True)
    else:
        data = request.get_json()
        result, error = api_request('PUT', f'/api/admin/resellers/{telegram_id}', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/resellers/<int:telegram_id>/assign', methods=['POST'])
@require_admin
def admin_assign_user(telegram_id):
    """Asignar usuario a revendedor"""
    data = request.get_json()
    result, error = api_request('POST', f'/api/admin/resellers/{telegram_id}/assign', data, is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/resellers/<int:telegram_id>/remove', methods=['POST'])
@require_admin
def admin_remove_user(telegram_id):
    """Remover usuario de revendedor"""
    data = request.get_json()
    result, error = api_request('POST', f'/api/admin/resellers/{telegram_id}/remove', data, is_admin=True)
    
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


@app.route('/api/admin/note-presets', methods=['GET'])
@require_admin
def admin_note_presets():
    """Obtener presets de notas"""
    result, error = api_request('GET', '/api/note-presets', is_admin=True)
    
    if error:
        return jsonify({'success': False, 'error': error}), 500
    
    return jsonify(result)


@app.route('/api/admin/auth/<action>', methods=['POST'])
@require_admin
def admin_auth_action(action):
    """Acciones de auth"""
    endpoint_map = {
        'init': '/api/admin/auth/init',
        'refresh': '/api/admin/auth/refresh',
        'switch': '/api/admin/auth/switch',
        'retry': '/api/admin/auth/retry',
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
    logger.info(f"API URL: {API_URL}")
    logger.info(f"Bearer Token: {'Configurado' if SHARED_BEARER_TOKEN else 'No'}")
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
