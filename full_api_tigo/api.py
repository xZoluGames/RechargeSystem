#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api.py - API REST Principal para Sistema de Recargas Tigo
Puerto 5000

CORREGIDO v2.3:
- NUEVO endpoint /api/admin/packages que NO requiere API key
- Endpoint para obtener username de Telegram por ID
- Bearer token obligatorio en todas las rutas protegidas
- Admin puede recargar sin límite (con historial)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from functools import wraps
import logging
import os
import json
import traceback
from datetime import datetime
from typing import Dict, Optional
import requests

from config import (
    API_PORT,
    ADMIN_API_KEY,
    ADMIN_PASSWORD,
    ADMIN_TELEGRAM_ID,
    SHARED_BEARER_TOKEN,
    HISTORY_FILE,
    TIGO_ACCOUNTS,
    DATA_DIR,
    LOG_DIR,
    ADMIN_NOTES_PRESETS,
    PACKAGE_CATEGORIES,
    print_config_info
)
from tigo_auth_new import TigoAuthNew, TigoAuthManager
from tigo_auth_legacy import TigoAuthLegacy
from tigo_api import TigoAPI
from key_manager import KeyManager
from package_manager import PackageManager

# ============================================================
# CONFIGURACIÓN DE LOGGING
# ============================================================
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'api.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# INICIALIZACIÓN
# ============================================================
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.urandom(24)

auth_manager = TigoAuthManager()
tigo_api: Optional[TigoAPI] = None
key_manager = KeyManager()
package_manager = PackageManager()

system_initialized = False
current_auth_method = "new"

# ============================================================
# CONFIGURACIÓN BOT TELEGRAM (para obtener usernames)
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_USERNAMES_FILE = os.path.join(DATA_DIR, 'telegram_usernames.json')

def load_telegram_usernames() -> Dict:
    """Carga el cache de usernames de Telegram"""
    try:
        if os.path.exists(TELEGRAM_USERNAMES_FILE):
            with open(TELEGRAM_USERNAMES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_telegram_usernames(data: Dict):
    """Guarda el cache de usernames"""
    try:
        with open(TELEGRAM_USERNAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando usernames: {e}")

def get_telegram_username(telegram_id: int) -> Optional[str]:
    """Obtiene el username de Telegram desde el cache"""
    usernames = load_telegram_usernames()
    return usernames.get(str(telegram_id), {}).get('username')

def update_telegram_username(telegram_id: int, username: str, first_name: str = None):
    """Actualiza el username de Telegram en el cache"""
    usernames = load_telegram_usernames()
    usernames[str(telegram_id)] = {
        'username': username,
        'first_name': first_name,
        'updated_at': datetime.now().isoformat()
    }
    save_telegram_usernames(usernames)


# ============================================================
# DECORADORES
# ============================================================
def require_bearer(f):
    """Decorador que requiere Bearer token válido - OBLIGATORIO"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'success': False, 'error': 'Bearer token requerido'}), 401
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Formato inválido. Use: Bearer <token>'}), 401
        
        token = auth_header.split(' ')[1]
        
        if token != SHARED_BEARER_TOKEN:
            return jsonify({'success': False, 'error': 'Bearer token inválido'}), 401
        
        return f(*args, **kwargs)
    return decorated


def require_api_key(f):
    """Decorador que requiere clave de API válida"""
    @wraps(f)
    @require_bearer
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        telegram_id = request.headers.get('X-Telegram-ID')
        
        if telegram_id:
            try:
                telegram_id = int(telegram_id)
            except:
                telegram_id = None
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API key requerida'}), 401
        
        is_valid, message = key_manager.validate_key(api_key, telegram_id)
        
        if not is_valid:
            return jsonify({'success': False, 'error': message}), 401
        
        request.api_key = api_key
        request.key_info = key_manager.get_key_info(api_key)
        request.telegram_id = telegram_id
        
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Decorador que requiere autenticación de admin"""
    @wraps(f)
    @require_bearer
    def decorated(*args, **kwargs):
        admin_key = request.headers.get('X-Admin-Key')
        admin_pass = request.headers.get('X-Admin-Password')
        
        if admin_key != ADMIN_API_KEY or admin_pass != ADMIN_PASSWORD:
            return jsonify({'success': False, 'error': 'No autorizado'}), 403
        
        request.is_admin = True
        return f(*args, **kwargs)
    return decorated


def require_reseller_or_admin(f):
    """Decorador para rutas de revendedor (o admin)"""
    @wraps(f)
    @require_bearer
    def decorated(*args, **kwargs):
        admin_key = request.headers.get('X-Admin-Key')
        admin_pass = request.headers.get('X-Admin-Password')
        
        if admin_key == ADMIN_API_KEY and admin_pass == ADMIN_PASSWORD:
            request.is_admin = True
            request.is_reseller = False
            return f(*args, **kwargs)
        
        telegram_id = request.headers.get('X-Telegram-ID')
        if telegram_id:
            try:
                telegram_id = int(telegram_id)
                if key_manager.is_reseller(telegram_id):
                    request.is_admin = False
                    request.is_reseller = True
                    request.reseller_telegram_id = telegram_id
                    return f(*args, **kwargs)
            except:
                pass
        
        return jsonify({'success': False, 'error': 'No autorizado'}), 403
    return decorated


# ============================================================
# FUNCIONES DE AUTENTICACIÓN
# ============================================================
def init_auth_system(use_new_method: bool = True, username: str = None) -> bool:
    global tigo_api, system_initialized, current_auth_method
    
    try:
        logger.info("=" * 60)
        logger.info("INICIALIZANDO SISTEMA DE AUTENTICACIÓN")
        logger.info("=" * 60)
        
        if use_new_method:
            success, status_msg = auth_manager.initialize_all_accounts()
            if success:
                auth = auth_manager.get_valid_auth()
                if auth:
                    tigo_api = TigoAPI(auth)
                    current_auth_method = "new"
                    system_initialized = True
                    logger.info(f"✅ Sistema inicializado: {status_msg}")
                    return True
        
        logger.warning("Intentando método legacy...")
        legacy_auth = TigoAuthLegacy(username or list(TIGO_ACCOUNTS.keys())[0])
        
        if legacy_auth.login():
            tigo_api = TigoAPI(legacy_auth)
            current_auth_method = "legacy"
            system_initialized = True
            logger.info("✅ Autenticación exitosa (método legacy)")
            return True
        
        logger.error("❌ Todos los métodos de autenticación fallaron")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error inicializando autenticación: {e}")
        return False


def check_retry_initialization():
    global tigo_api, system_initialized
    
    if auth_manager.should_retry():
        logger.info("⏰ Reintentando inicialización...")
        success, msg = auth_manager.retry_initialization()
        if success:
            auth = auth_manager.get_valid_auth()
            if auth:
                tigo_api = TigoAPI(auth)
                system_initialized = True
                logger.info(f"✅ Reinicio exitoso: {msg}")


def try_legacy_auth() -> bool:
    global tigo_api, system_initialized, current_auth_method
    
    for username, config in TIGO_ACCOUNTS.items():
        try:
            legacy_auth = TigoAuthLegacy(username, config['password'])
            if legacy_auth.login():
                tigo_api = TigoAPI(legacy_auth)
                system_initialized = True
                current_auth_method = "legacy"
                logger.info(f"✅ Auth legacy exitoso: {username}")
                return True
        except Exception as e:
            logger.error(f"Error auth legacy {username}: {e}")
    return False


def ensure_auth() -> bool:
    global tigo_api
    
    if not system_initialized:
        if auth_manager.should_retry():
            check_retry_initialization()
        if not system_initialized:
            return init_auth_system()
    
    if not tigo_api:
        return init_auth_system()
    
    if hasattr(tigo_api.auth, 'is_token_valid') and not tigo_api.auth.is_token_valid():
        logger.info("Token expirado, renovando...")
        if tigo_api.auth.login():
            return True
        success, new_account = auth_manager.switch_account()
        if success:
            tigo_api = TigoAPI(auth_manager.get_auth(new_account))
            return True
        return init_auth_system()
    
    return True


def save_to_history(api_key: str, destination: str, package: Dict,
                   success: bool, result_data: Dict, error: str = "",
                   is_admin_recharge: bool = False):
    try:
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        transaction = {
            "timestamp": datetime.now().isoformat(),
            "api_key": api_key[:8] + "..." if api_key else "ADMIN",
            "destination": destination,
            "package_id": package.get('id', ''),
            "package_name": package.get('name', ''),
            "amount": package.get('amount', 0),
            "status": "SUCCESS" if success else "FAILED",
            "order_id": result_data.get('orderId', '') if result_data else '',
            "transaction_id": result_data.get('transactionId', '') if result_data else '',
            "error": error,
            "is_admin_recharge": is_admin_recharge
        }
        
        history.insert(0, transaction)
        history = history[:10000]
        
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando historial: {e}")


# ============================================================
# ENDPOINTS PÚBLICOS (Sin Bearer)
# ============================================================
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'Tigo Recharge API',
        'version': '2.3',
        'status': 'running',
        'bearer_required': True,
        'features': ['Admin sin límite', 'Vinculación Telegram', 'Roles', 'Categorías']
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    check_retry_initialization()
    auth_status = "not_initialized"
    
    if system_initialized and tigo_api:
        if hasattr(tigo_api.auth, 'is_token_valid'):
            auth_status = "valid" if tigo_api.auth.is_token_valid() else "expired"
        else:
            auth_status = "active"
    
    system_status = auth_manager.get_all_status()
    
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'system': {
            'initialized': system_initialized,
            'auth_method': current_auth_method,
            'auth_status': auth_status,
            'current_account': tigo_api.auth.username if tigo_api else None,
            'accounts': system_status.get('accounts', {})
        }
    }), 200


@app.route('/api/note-presets', methods=['GET'])
@require_bearer
def get_note_presets():
    return jsonify({'success': True, 'presets': ADMIN_NOTES_PRESETS}), 200


@app.route('/api/package-categories', methods=['GET'])
@require_bearer
def get_package_categories():
    return jsonify({'success': True, 'categories': PACKAGE_CATEGORIES}), 200


# ============================================================
# ENDPOINT PARA REGISTRAR USERNAME DE TELEGRAM (llamado por el bot)
# ============================================================
@app.route('/api/telegram/register-username', methods=['POST'])
@require_bearer
def register_telegram_username():
    """Registra el username de un usuario de Telegram (llamado por el bot)"""
    try:
        data = request.get_json()
        telegram_id = data.get('telegram_id')
        username = data.get('username')
        first_name = data.get('first_name')
        
        if not telegram_id:
            return jsonify({'success': False, 'error': 'telegram_id requerido'}), 400
        
        update_telegram_username(telegram_id, username, first_name)
        
        # También actualizar en la clave si existe
        key = key_manager.get_key_by_telegram_id(telegram_id)
        if key:
            key_manager.modify_key(key, telegram_username=username)
        
        return jsonify({
            'success': True,
            'message': 'Username registrado',
            'data': {
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/telegram/usernames', methods=['GET'])
@require_admin
def get_all_telegram_usernames():
    """Obtiene todos los usernames registrados"""
    usernames = load_telegram_usernames()
    return jsonify({
        'success': True,
        'usernames': usernames
    }), 200


# ============================================================
# ENDPOINTS DE RECARGAS
# ============================================================
@app.route('/api/packages', methods=['GET', 'POST'])
@require_api_key
def get_packages():
    try:
        data = request.get_json() or {} if request.method == 'POST' else request.args.to_dict()
        destination = data.get('destination', '').strip()
        
        if not destination:
            return jsonify({'success': False, 'error': 'Número de destino requerido'}), 400
        
        if not destination.isdigit() or len(destination) != 10:
            return jsonify({'success': False, 'error': 'Número debe tener 10 dígitos'}), 400
        
        if not ensure_auth():
            return jsonify({'success': False, 'error': 'Error de autenticación con Tigo'}), 500
        
        success, packages, message = tigo_api.get_packages(destination)
        
        if not success:
            return jsonify({'success': False, 'error': message}), 500
        
        organized = package_manager.organize_packages(packages)
        flat_organized = package_manager.organize_packages_flat(packages)
        package_manager.cache_packages(destination, packages)
        
        return jsonify({
            'success': True,
            'destination': destination,
            'packages': flat_organized,
            'by_category': organized,
            'total': len(packages),
            'summary': package_manager.get_summary(packages)
        }), 200
        
    except Exception as e:
        logger.error(f"Error en /api/packages: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/recharge', methods=['POST'])
@require_api_key
def create_recharge():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Datos requeridos'}), 400
        
        destination = data.get('destination', '').strip()
        package_id = data.get('package_id', '').strip()
        
        if not destination or not package_id:
            return jsonify({'success': False, 'error': 'destination y package_id requeridos'}), 400
        
        if not destination.isdigit() or len(destination) != 10:
            return jsonify({'success': False, 'error': 'Número debe tener 10 dígitos'}), 400
        
        if not ensure_auth():
            return jsonify({'success': False, 'error': 'Error de autenticación'}), 500
        
        success, packages, msg = tigo_api.get_packages(destination)
        if not success:
            return jsonify({'success': False, 'error': f'Error obteniendo paquetes: {msg}'}), 500
        
        selected_package = package_manager.find_by_id(packages, package_id)
        if not selected_package:
            return jsonify({'success': False, 'error': f'Paquete no encontrado: {package_id}'}), 404
        
        api_key = request.api_key
        remaining = key_manager.get_remaining_balance(api_key)
        package_amount = selected_package.get('amount', 0)
        
        if package_amount > remaining:
            return jsonify({
                'success': False,
                'error': f'Saldo insuficiente. Disponible: Gs. {remaining:,}',
                'available': remaining,
                'required': package_amount
            }), 402
        
        can_order, cooldown_msg = tigo_api.can_create_order(destination)
        if not can_order:
            return jsonify({'success': False, 'error': cooldown_msg}), 429
        
        logger.info(f"📱 Recarga: {destination} - {selected_package['name']} - Gs. {package_amount:,}")
        
        success, order_data, result_msg = tigo_api.process_recharge(destination, selected_package)
        
        if success:
            key_manager.use_amount(api_key, package_amount)
            remaining -= package_amount
        
        save_to_history(api_key, destination, selected_package, success, order_data,
                       result_msg if not success else "")
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Recarga completada',
                'data': {
                    'destination': destination,
                    'package': {'id': selected_package.get('id'), 'name': selected_package.get('name'), 'amount': package_amount},
                    'order_id': order_data.get('orderId'),
                    'transaction_id': order_data.get('transactionId'),
                    'remaining_balance': remaining
                }
            }), 200
        else:
            return jsonify({
                'success': False, 
                'error': result_msg, 
                'order_data': order_data,
                'destination': destination,
                'package': {'id': selected_package.get('id'), 'name': selected_package.get('name'), 'amount': package_amount}
            }), 500
        
    except Exception as e:
        logger.error(f"Error en /api/recharge: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/balance', methods=['GET'])
@require_api_key
def get_balance():
    try:
        key_info = request.key_info
        remaining = key_manager.get_remaining_balance(request.api_key)
        
        return jsonify({
            'success': True,
            'balance': {
                'total': key_info['max_amount'],
                'used': key_info.get('used_amount', 0),
                'remaining': remaining,
                'formatted': f"Gs. {remaining:,}"
            },
            'key_info': {
                'created': key_info['created'],
                'expires': key_info['expires'],
                'active': key_info.get('active', True),
                'use_count': key_info.get('use_count', 0),
                'telegram_id': key_info.get('telegram_id'),
                'role': key_info.get('role', 'USER')
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
@require_api_key
def get_history():
    try:
        api_key = request.api_key
        limit = int(request.args.get('limit', 20))
        
        recharge_history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                all_history = json.load(f)
            key_prefix = api_key[:8]
            recharge_history = [t for t in all_history if t.get('api_key', '').startswith(key_prefix)][:limit]
        
        modifications = key_manager.get_user_visible_modifications(api_key, 10)
        
        return jsonify({
            'success': True,
            'recharges': recharge_history,
            'modifications': modifications,
            'total_recharges': len(recharge_history)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/verify_order/<order_id>', methods=['GET'])
@require_api_key
def verify_order(order_id):
    try:
        if not ensure_auth():
            return jsonify({'success': False, 'error': 'Error de autenticación'}), 500
        
        success, order_data, message = tigo_api.check_order_status(order_id)
        
        if not success:
            return jsonify({'success': False, 'error': message}), 500
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'status': order_data.get('status', 'Unknown'),
            'data': order_data
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ENDPOINTS DE REVENDEDOR
# ============================================================
@app.route('/api/reseller/users', methods=['GET'])
@require_reseller_or_admin
def reseller_get_users():
    try:
        if request.is_admin:
            users = key_manager.get_all_keys()
            return jsonify({'success': True, 'users': users, 'is_admin_view': True}), 200
        
        users = key_manager.get_reseller_users(request.reseller_telegram_id)
        return jsonify({'success': True, 'users': users, 'total': len(users)}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ENDPOINTS DE ADMINISTRACIÓN
# ============================================================
@app.route('/api/admin/status', methods=['GET'])
@require_admin
def admin_status():
    try:
        auth_status = {}
        if system_initialized and tigo_api:
            if hasattr(tigo_api.auth, 'get_status'):
                auth_status = tigo_api.auth.get_status()
            else:
                auth_status = {'username': tigo_api.auth.username}
        
        return jsonify({
            'success': True,
            'system': {
                'initialized': system_initialized,
                'auth_method': current_auth_method,
                'current_auth': auth_status
            },
            'keys': key_manager.get_stats(),
            'resellers': len(key_manager.get_all_resellers()),
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ENDPOINT CORREGIDO: PAQUETES PARA ADMIN (SIN API KEY)
# ============================================================
@app.route('/api/admin/packages', methods=['GET', 'POST'])
@require_admin
def admin_get_packages():
    """
    CORREGIDO: Obtiene paquetes para el admin SIN requerir API key.
    Usa las credenciales de admin para autenticación.
    """
    try:
        data = request.get_json() or {} if request.method == 'POST' else request.args.to_dict()
        destination = data.get('destination', '').strip()
        
        if not destination:
            return jsonify({'success': False, 'error': 'Número de destino requerido'}), 400
        
        if not destination.isdigit() or len(destination) != 10:
            return jsonify({'success': False, 'error': 'Número debe tener 10 dígitos'}), 400
        
        if not ensure_auth():
            return jsonify({'success': False, 'error': 'Error de autenticación con Tigo'}), 500
        
        success, packages, message = tigo_api.get_packages(destination)
        
        if not success:
            return jsonify({'success': False, 'error': message}), 500
        
        organized = package_manager.organize_packages(packages)
        flat_organized = package_manager.organize_packages_flat(packages)
        package_manager.cache_packages(destination, packages)
        
        return jsonify({
            'success': True,
            'destination': destination,
            'packages': flat_organized,
            'by_category': organized,
            'total': len(packages),
            'summary': package_manager.get_summary(packages)
        }), 200
        
    except Exception as e:
        logger.error(f"Error en /api/admin/packages: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/recharge', methods=['POST'])
@require_admin
def admin_recharge():
    """Recarga de admin SIN LÍMITE de saldo"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Datos requeridos'}), 400
        
        destination = data.get('destination', '').strip()
        package_id = data.get('package_id', '').strip()
        
        if not destination or not package_id:
            return jsonify({'success': False, 'error': 'destination y package_id requeridos'}), 400
        
        if not destination.isdigit() or len(destination) != 10:
            return jsonify({'success': False, 'error': 'Número debe tener 10 dígitos'}), 400
        
        if not ensure_auth():
            return jsonify({'success': False, 'error': 'Error de autenticación'}), 500
        
        success, packages, msg = tigo_api.get_packages(destination)
        if not success:
            return jsonify({'success': False, 'error': f'Error obteniendo paquetes: {msg}'}), 500
        
        selected_package = package_manager.find_by_id(packages, package_id)
        if not selected_package:
            return jsonify({'success': False, 'error': f'Paquete no encontrado: {package_id}'}), 404
        
        can_order, cooldown_msg = tigo_api.can_create_order(destination)
        if not can_order:
            return jsonify({'success': False, 'error': cooldown_msg}), 429
        
        package_amount = selected_package.get('amount', 0)
        logger.info(f"📱 ADMIN Recarga: {destination} - {selected_package['name']} - Gs. {package_amount:,}")
        
        success, order_data, result_msg = tigo_api.process_recharge(destination, selected_package)
        
        save_to_history("ADMIN", destination, selected_package, success, order_data,
                       result_msg if not success else "", is_admin_recharge=True)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Recarga de admin completada',
                'data': {
                    'destination': destination,
                    'package': {'id': selected_package.get('id'), 'name': selected_package.get('name'), 'amount': package_amount},
                    'order_id': order_data.get('orderId'),
                    'transaction_id': order_data.get('transactionId'),
                    'admin_recharge': True
                }
            }), 200
        else:
            return jsonify({
                'success': False, 
                'error': result_msg, 
                'order_data': order_data,
                'destination': destination,
                'package': {'id': selected_package.get('id'), 'name': selected_package.get('name'), 'amount': package_amount}
            }), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/keys', methods=['GET', 'POST'])
@require_admin
def admin_keys():
    try:
        if request.method == 'GET':
            include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
            keys = key_manager.get_all_keys(include_inactive)
            
            # Agregar usernames de Telegram
            usernames = load_telegram_usernames()
            for key in keys:
                tid = key.get('telegram_id')
                if tid and str(tid) in usernames:
                    key['telegram_username'] = usernames[str(tid)].get('username')
                    key['telegram_first_name'] = usernames[str(tid)].get('first_name')
            
            return jsonify({'success': True, 'keys': keys, 'stats': key_manager.get_stats()}), 200
        else:
            data = request.get_json()
            max_amount = int(data.get('max_amount', 0))
            valid_days = int(data.get('valid_days', 30))
            description = data.get('description', '')
            telegram_id = data.get('telegram_id')
            
            if telegram_id:
                telegram_id = int(telegram_id)
            
            key = key_manager.generate_key(max_amount, valid_days, description, telegram_id)
            
            if not key:
                return jsonify({'success': False, 'error': 'Error generando clave o Telegram ID ya tiene clave'}), 400
            
            return jsonify({
                'success': True,
                'key': key,
                'info': key_manager.get_key_info(key)
            }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/keys/<key>', methods=['GET', 'PUT', 'DELETE'])
@require_admin
def admin_key_actions(key):
    try:
        key_info = key_manager.get_key_info(key)
        if not key_info:
            return jsonify({'success': False, 'error': 'Clave no encontrada'}), 404
        
        if request.method == 'GET':
            # Agregar username de Telegram si existe
            tid = key_info.get('telegram_id')
            if tid:
                usernames = load_telegram_usernames()
                if str(tid) in usernames:
                    key_info['telegram_username'] = usernames[str(tid)].get('username')
                    key_info['telegram_first_name'] = usernames[str(tid)].get('first_name')
            
            return jsonify({
                'success': True,
                'key': key,
                'info': key_info,
                'modifications': key_manager.get_modifications(key, 20),
                'remaining': key_info['max_amount'] - key_info.get('used_amount', 0)
            }), 200
        
        elif request.method == 'PUT':
            data = request.get_json() or {}
            admin_note = data.pop('admin_note', None)
            note_preset = data.pop('note_preset', None)
            success = key_manager.modify_key(key, admin_note=admin_note, note_preset=note_preset, **data)
            return jsonify({
                'success': success,
                'message': 'Clave modificada' if success else 'Error modificando',
                'info': key_manager.get_key_info(key)
            }), 200 if success else 500
        
        else:
            admin_note = request.args.get('reason', 'Desactivada por admin')
            success = key_manager.deactivate_key(key, admin_note)
            return jsonify({'success': success, 'message': 'Clave desactivada' if success else 'Error'}), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/keys/<key>/add-balance', methods=['POST'])
@require_admin
def admin_add_balance(key):
    try:
        data = request.get_json()
        amount = int(data.get('amount', 0))
        admin_note = data.get('admin_note')
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Monto debe ser positivo'}), 400
        
        success = key_manager.add_balance(key, amount, admin_note)
        return jsonify({
            'success': success,
            'message': f'Saldo agregado: Gs. {amount:,}' if success else 'Error',
            'info': key_manager.get_key_info(key)
        }), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/keys/<key>/unlink', methods=['POST'])
@require_admin
def admin_unlink_telegram(key):
    try:
        data = request.get_json() or {}
        admin_note = data.get('admin_note', 'Desvinculación solicitada')
        success = key_manager.unlink_telegram(key, admin_note)
        return jsonify({
            'success': success,
            'message': 'Telegram desvinculado' if success else 'Error',
            'info': key_manager.get_key_info(key)
        }), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/keys/<key>/link', methods=['POST'])
@require_admin
def admin_link_telegram(key):
    try:
        data = request.get_json()
        telegram_id = int(data.get('telegram_id'))
        telegram_username = data.get('telegram_username')
        admin_note = data.get('admin_note')
        
        success = key_manager.link_telegram(key, telegram_id, telegram_username, admin_note)
        
        if not success:
            existing = key_manager.get_key_by_telegram_id(telegram_id)
            if existing and existing != key:
                return jsonify({'success': False, 'error': 'Telegram ID ya tiene otra clave activa'}), 400
        
        return jsonify({
            'success': success,
            'message': 'Telegram vinculado' if success else 'Error',
            'info': key_manager.get_key_info(key)
        }), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ENDPOINTS DE REVENDEDORES
# ============================================================
@app.route('/api/admin/resellers', methods=['GET', 'POST'])
@require_admin
def admin_resellers():
    try:
        if request.method == 'GET':
            resellers = key_manager.get_all_resellers()
            
            # Agregar usernames de Telegram
            usernames = load_telegram_usernames()
            for r in resellers:
                tid = r.get('telegram_id')
                if tid and str(tid) in usernames:
                    r['telegram_username'] = usernames[str(tid)].get('username')
                    r['telegram_first_name'] = usernames[str(tid)].get('first_name')
            
            return jsonify({'success': True, 'resellers': resellers, 'total': len(resellers)}), 200
        else:
            data = request.get_json()
            name = data.get('name')
            telegram_id = int(data.get('telegram_id'))
            assigned_users = data.get('assigned_users', [])
            
            success = key_manager.create_reseller(telegram_id, name, assigned_users)
            return jsonify({
                'success': success,
                'message': 'Revendedor creado' if success else 'Error',
                'reseller': key_manager.get_reseller(telegram_id) if success else None
            }), 201 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/resellers/<int:telegram_id>', methods=['GET', 'PUT', 'DELETE'])
@require_admin
def admin_reseller_actions(telegram_id):
    try:
        reseller = key_manager.get_reseller(telegram_id)
        if not reseller:
            return jsonify({'success': False, 'error': 'Revendedor no encontrado'}), 404
        
        if request.method == 'GET':
            # Agregar username de Telegram
            usernames = load_telegram_usernames()
            if str(telegram_id) in usernames:
                reseller['telegram_username'] = usernames[str(telegram_id)].get('username')
                reseller['telegram_first_name'] = usernames[str(telegram_id)].get('first_name')
            
            return jsonify({'success': True, 'reseller': reseller}), 200
        
        elif request.method == 'PUT':
            data = request.get_json()
            success = key_manager.update_reseller(telegram_id, **data)
            return jsonify({
                'success': success,
                'message': 'Revendedor actualizado' if success else 'Error',
                'reseller': key_manager.get_reseller(telegram_id)
            }), 200 if success else 500
        
        else:
            success = key_manager.deactivate_reseller(telegram_id)
            return jsonify({
                'success': success,
                'message': 'Revendedor desactivado' if success else 'Error'
            }), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/resellers/<int:telegram_id>/assign', methods=['POST'])
@require_admin
def admin_assign_user(telegram_id):
    try:
        data = request.get_json()
        user_telegram_id = int(data.get('user_telegram_id'))
        success = key_manager.assign_user_to_reseller(telegram_id, user_telegram_id)
        return jsonify({
            'success': success,
            'message': 'Usuario asignado' if success else 'Error'
        }), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/resellers/<int:telegram_id>/remove', methods=['POST'])
@require_admin
def admin_remove_user(telegram_id):
    try:
        data = request.get_json()
        user_telegram_id = int(data.get('user_telegram_id'))
        success = key_manager.remove_user_from_reseller(telegram_id, user_telegram_id)
        return jsonify({
            'success': success,
            'message': 'Usuario removido' if success else 'Error'
        }), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/history', methods=['GET'])
@require_admin
def admin_history():
    try:
        limit = int(request.args.get('limit', 100))
        admin_only = request.args.get('admin_only', 'false').lower() == 'true'
        
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        if admin_only:
            history = [h for h in history if h.get('is_admin_recharge', False)]
        
        return jsonify({
            'success': True,
            'history': history[:limit],
            'total': len(history)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ENDPOINTS DE AUTENTICACIÓN ADMIN
# ============================================================
@app.route('/api/admin/auth/init', methods=['POST'])
@require_admin
def admin_auth_init():
    success = init_auth_system()
    return jsonify({
        'success': success,
        'message': 'Sistema inicializado' if success else 'Error de inicialización'
    }), 200 if success else 500


@app.route('/api/admin/auth/refresh', methods=['POST'])
@require_admin
def admin_auth_refresh():
    try:
        if tigo_api and hasattr(tigo_api.auth, 'login'):
            success = tigo_api.auth.login()
            return jsonify({
                'success': success,
                'message': 'Token renovado' if success else 'Error renovando'
            }), 200 if success else 500
        return jsonify({'success': False, 'error': 'Sistema no inicializado'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/auth/switch', methods=['POST'])
@require_admin
def admin_auth_switch():
    global tigo_api
    try:
        success, new_account = auth_manager.switch_account()
        if success:
            tigo_api = TigoAPI(auth_manager.get_auth(new_account))
            return jsonify({
                'success': True,
                'message': f'Cambiado a cuenta: {new_account}',
                'account': new_account
            }), 200
        return jsonify({'success': False, 'error': 'No hay cuentas alternativas disponibles'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/auth/retry', methods=['POST'])
@require_admin
def admin_auth_retry():
    success = init_auth_system()
    return jsonify({
        'success': success,
        'message': 'Reinicio exitoso' if success else 'Error en reintento'
    }), 200 if success else 500


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print_config_info()
    logger.info(f"Iniciando API en puerto {API_PORT}...")
    
    init_auth_system()
    
    app.run(host='0.0.0.0', port=API_PORT, debug=False, threaded=True)
