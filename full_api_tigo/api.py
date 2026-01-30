#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api.py - API REST Principal para Sistema de Recargas Tigo
Puerto 5000

API pura sin web ni Telegram.
Soporta:
- Nuevo método de autenticación (fingerprint)
- Método antiguo como fallback (legacy)
- Múltiples cuentas Tigo
- Gestión de claves de API
- Recargas de paquetes
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

# Importar módulos del sistema
from config import (
    API_PORT,
    ADMIN_API_KEY,
    ADMIN_PASSWORD,
    HISTORY_FILE,
    TIGO_ACCOUNTS,
    DATA_DIR,
    LOG_DIR,
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

# Componentes del sistema
auth_manager = TigoAuthManager()  # Gestor de autenticación (nuevo método)
tigo_api: Optional[TigoAPI] = None  # API de recargas
key_manager = KeyManager()
package_manager = PackageManager()

# Estado del sistema
system_initialized = False
current_auth_method = "new"  # "new" o "legacy"


# ============================================================
# DECORADORES
# ============================================================
def require_api_key(f):
    """Decorador que requiere clave de API válida"""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key requerida'
            }), 401
        
        is_valid, message = key_manager.validate_key(api_key)
        
        if not is_valid:
            return jsonify({
                'success': False,
                'error': message
            }), 401
        
        request.api_key = api_key
        request.key_info = key_manager.get_key_info(api_key)
        
        return f(*args, **kwargs)
    
    return decorated


def require_admin(f):
    """Decorador que requiere autenticación de admin"""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_key = request.headers.get('X-Admin-Key')
        admin_pass = request.headers.get('X-Admin-Password')
        
        if admin_key != ADMIN_API_KEY or admin_pass != ADMIN_PASSWORD:
            return jsonify({
                'success': False,
                'error': 'No autorizado'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================
def init_auth_system(use_new_method: bool = True, username: str = None) -> bool:
    """
    Inicializa el sistema de autenticación
    
    Args:
        use_new_method: Usar nuevo método (True) o legacy (False)
        username: Cuenta específica a usar
    """
    global tigo_api, system_initialized, current_auth_method
    
    try:
        logger.info("=" * 60)
        logger.info("INICIALIZANDO SISTEMA DE AUTENTICACIÓN")
        logger.info(f"Método: {'Nuevo' if use_new_method else 'Legacy'}")
        logger.info(f"Cuenta: {username or 'Por defecto'}")
        logger.info("=" * 60)
        
        if use_new_method:
            # Usar inicialización dual (intenta ambas cuentas)
            success, status_msg = auth_manager.initialize_all_accounts()
            
            if success:
                # Obtener auth de la cuenta que funcionó
                auth = auth_manager.get_valid_auth()
                if auth:
                    tigo_api = TigoAPI(auth)
                    current_auth_method = "new"
                    system_initialized = True
                    logger.info(f"✅ Sistema inicializado: {status_msg}")
                    return True
        
        # Fallback a método legacy
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
        logger.error(traceback.format_exc())
        return False


def check_retry_initialization():
    """Verifica si es necesario reintentar la inicialización"""
    global tigo_api, system_initialized
    
    if auth_manager.should_retry():
        logger.info("⏰ Tiempo de reintento alcanzado, iniciando...")
        success, msg = auth_manager.retry_initialization()
        
        if success:
            auth = auth_manager.get_valid_auth()
            if auth:
                tigo_api = TigoAPI(auth)
                system_initialized = True
                logger.info(f"✅ Reintento exitoso: {msg}")
                return True
    
    return False


def ensure_auth() -> bool:
    """Verifica y renueva autenticación si es necesario"""
    global tigo_api
    
    # Verificar si es tiempo de reintentar inicialización fallida
    if not system_initialized:
        if auth_manager.should_retry():
            check_retry_initialization()
        
        if not system_initialized:
            return init_auth_system()
    
    if not tigo_api:
        return init_auth_system()
    
    # Verificar si el token actual es válido
    if hasattr(tigo_api.auth, 'is_token_valid') and not tigo_api.auth.is_token_valid():
        logger.info("Token expirado, renovando...")
        
        # Intentar con cuenta actual primero
        if tigo_api.auth.login():
            return True
        
        # Intentar cambiar de cuenta
        success, new_account = auth_manager.switch_account()
        if success:
            tigo_api = TigoAPI(auth_manager.get_auth(new_account))
            return True
        
        # Reinicializar completo
        return init_auth_system()
    
    return True


def save_to_history(api_key: str, destination: str, package: Dict,
                   success: bool, result_data: Dict, error: str = ""):
    """Guarda transacción en el historial"""
    try:
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        
        transaction = {
            "timestamp": datetime.now().isoformat(),
            "api_key": api_key[:8] + "...",
            "destination": destination,
            "package_id": package.get('id', ''),
            "package_name": package.get('name', ''),
            "amount": package.get('amount', 0),
            "status": "SUCCESS" if success else "FAILED",
            "order_id": result_data.get('orderId', '') if result_data else '',
            "transaction_id": result_data.get('transactionId', '') if result_data else '',
            "error": error
        }
        
        history.insert(0, transaction)
        history = history[:10000]  # Limitar
        
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"Error guardando historial: {e}")


# ============================================================
# ENDPOINTS PÚBLICOS
# ============================================================
@app.route('/', methods=['GET'])
def index():
    """Información de la API"""
    return jsonify({
        'service': 'Tigo Recharge API',
        'version': '2.0',
        'status': 'running',
        'auth_method': current_auth_method if system_initialized else 'not_initialized',
        'endpoints': {
            'GET /health': 'Estado del sistema',
            'GET /api/packages': 'Obtener paquetes',
            'POST /api/recharge': 'Realizar recarga',
            'GET /api/balance': 'Consultar saldo',
            'GET /api/history': 'Historial de recargas',
            'GET /api/verify_order/<id>': 'Verificar orden'
        }
    }), 200


@app.route('/health', methods=['GET'])
def health_check():
    """Health check del sistema con estado detallado"""
    auth_status = "not_initialized"
    account_info = None
    
    # Verificar reintento pendiente
    check_retry_initialization()
    
    if system_initialized and tigo_api:
        if hasattr(tigo_api.auth, 'is_token_valid'):
            auth_status = "valid" if tigo_api.auth.is_token_valid() else "expired"
        else:
            auth_status = "active"
        
        if hasattr(tigo_api.auth, 'account_info'):
            account_info = tigo_api.auth.account_info
    
    # Estado del sistema de múltiples cuentas
    system_status = auth_manager.get_all_status()
    
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'system': {
            'initialized': system_initialized,
            'auth_method': current_auth_method,
            'auth_status': auth_status,
            'system_state': system_status.get('system_status', 'UNKNOWN'),
            'current_account': tigo_api.auth.username if tigo_api else None,
            'account_name': account_info.get('name', {}).get('fullName') if account_info else None,
            'retry_scheduled': system_status.get('retry_scheduled', False),
            'accounts': system_status.get('accounts', {})
        }
    }), 200


# ============================================================
# ENDPOINTS DE RECARGAS
# ============================================================
@app.route('/api/packages', methods=['GET', 'POST'])
@require_api_key
def get_packages():
    """
    Obtiene paquetes disponibles para un número
    
    GET/POST /api/packages
    Params: destination (número de 10 dígitos)
    """
    try:
        if request.method == 'POST':
            data = request.get_json() or {}
        else:
            data = request.args.to_dict()
        
        destination = data.get('destination', '').strip()
        
        if not destination:
            return jsonify({
                'success': False,
                'error': 'Número de destino requerido'
            }), 400
        
        if not destination.isdigit() or len(destination) != 10:
            return jsonify({
                'success': False,
                'error': 'Número debe tener 10 dígitos'
            }), 400
        
        # Verificar autenticación
        if not ensure_auth():
            return jsonify({
                'success': False,
                'error': 'Error de autenticación con Tigo'
            }), 500
        
        # Obtener paquetes
        success, packages, message = tigo_api.get_packages(destination)
        
        if not success:
            return jsonify({
                'success': False,
                'error': message
            }), 500
        
        # Organizar por categorías
        organized = package_manager.organize_packages(packages)
        
        # Cachear
        package_manager.cache_packages(destination, packages)
        
        return jsonify({
            'success': True,
            'destination': destination,
            'packages': packages,
            'by_category': organized,
            'total': len(packages),
            'categories': list(organized.keys())
        }), 200
        
    except Exception as e:
        logger.error(f"Error en /api/packages: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/recharge', methods=['POST'])
@require_api_key
def create_recharge():
    """
    Realiza una recarga
    
    POST /api/recharge
    Body: {
        "destination": "0981234567",
        "package_id": "PACK_ID"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Datos requeridos'
            }), 400
        
        destination = data.get('destination', '').strip()
        package_id = data.get('package_id', '').strip()
        
        if not destination or not package_id:
            return jsonify({
                'success': False,
                'error': 'destination y package_id requeridos'
            }), 400
        
        if not destination.isdigit() or len(destination) != 10:
            return jsonify({
                'success': False,
                'error': 'Número debe tener 10 dígitos'
            }), 400
        
        # Verificar autenticación
        if not ensure_auth():
            return jsonify({
                'success': False,
                'error': 'Error de autenticación'
            }), 500
        
        # Obtener paquetes
        success, packages, msg = tigo_api.get_packages(destination)
        
        if not success:
            return jsonify({
                'success': False,
                'error': f'Error obteniendo paquetes: {msg}'
            }), 500
        
        # Buscar paquete
        selected_package = package_manager.find_by_id(packages, package_id)
        
        if not selected_package:
            return jsonify({
                'success': False,
                'error': f'Paquete no encontrado: {package_id}'
            }), 404
        
        # Verificar saldo
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
        
        # Verificar cooldown
        can_order, cooldown_msg = tigo_api.can_create_order(destination)
        if not can_order:
            return jsonify({
                'success': False,
                'error': cooldown_msg
            }), 429
        
        # Procesar recarga
        logger.info(f"📱 Recarga: {destination} - {selected_package['name']} - Gs. {package_amount:,}")
        
        success, order_data, result_msg = tigo_api.process_recharge(destination, selected_package)
        
        # Actualizar saldo si exitoso
        if success:
            key_manager.use_amount(api_key, package_amount)
            remaining -= package_amount
        
        # Guardar historial
        save_to_history(api_key, destination, selected_package, success, order_data, 
                       result_msg if not success else "")
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Recarga completada',
                'data': {
                    'destination': destination,
                    'package': {
                        'id': selected_package.get('id'),
                        'name': selected_package.get('name'),
                        'amount': package_amount
                    },
                    'order_id': order_data.get('orderId'),
                    'transaction_id': order_data.get('transactionId'),
                    'remaining_balance': remaining
                }
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': result_msg,
                'order_data': order_data
            }), 500
        
    except Exception as e:
        logger.error(f"Error en /api/recharge: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/balance', methods=['GET'])
@require_api_key
def get_balance():
    """Obtiene saldo de la API key"""
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
                'use_count': key_info.get('use_count', 0)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error en /api/balance: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/history', methods=['GET'])
@require_api_key
def get_history():
    """Obtiene historial de recargas"""
    try:
        api_key = request.api_key
        limit = int(request.args.get('limit', 20))
        
        if not os.path.exists(HISTORY_FILE):
            return jsonify({
                'success': True,
                'history': [],
                'total': 0
            }), 200
        
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            all_history = json.load(f)
        
        # Filtrar por API key (comparando primeros 8 chars)
        key_prefix = api_key[:8]
        user_history = [
            t for t in all_history
            if t.get('api_key', '').startswith(key_prefix)
        ][:limit]
        
        return jsonify({
            'success': True,
            'history': user_history,
            'total': len(user_history)
        }), 200
        
    except Exception as e:
        logger.error(f"Error en /api/history: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/verify_order/<order_id>', methods=['GET'])
@require_api_key
def verify_order(order_id):
    """Verifica estado de una orden"""
    try:
        if not ensure_auth():
            return jsonify({
                'success': False,
                'error': 'Error de autenticación'
            }), 500
        
        success, order_data, message = tigo_api.check_order_status(order_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': message
            }), 500
        
        return jsonify({
            'success': True,
            'order_id': order_id,
            'status': order_data.get('status', 'Unknown'),
            'payment_status': order_data.get('currentPaymentStatus'),
            'fulfillment_status': order_data.get('currentFulfillmentStatus'),
            'data': order_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error en /api/verify_order: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================
# ENDPOINTS DE ADMINISTRACIÓN
# ============================================================
@app.route('/api/admin/status', methods=['GET'])
@require_admin
def admin_status():
    """Estado completo del sistema"""
    try:
        # Estado de autenticación
        auth_status = {}
        if system_initialized and tigo_api:
            if hasattr(tigo_api.auth, 'get_status'):
                auth_status = tigo_api.auth.get_status()
            else:
                auth_status = {
                    'username': tigo_api.auth.username,
                    'token_valid': tigo_api.auth.is_token_valid() if hasattr(tigo_api.auth, 'is_token_valid') else 'unknown'
                }
        
        # Estado de todas las cuentas
        all_accounts = {}
        for username in TIGO_ACCOUNTS.keys():
            all_accounts[username] = {
                'configured': True,
                'is_current': tigo_api.auth.username == username if tigo_api else False
            }
        
        return jsonify({
            'success': True,
            'system': {
                'initialized': system_initialized,
                'auth_method': current_auth_method,
                'current_auth': auth_status,
                'accounts': all_accounts
            },
            'keys': key_manager.get_stats(),
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error en admin_status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/auth/init', methods=['POST'])
@require_admin
def admin_init_auth():
    """
    Inicializa/reinicia autenticación
    
    POST /api/admin/auth/init
    Body: {
        "method": "new" | "legacy",
        "username": "0985308247" (opcional)
    }
    """
    try:
        data = request.get_json() or {}
        method = data.get('method', 'new')
        username = data.get('username')
        
        use_new = method != 'legacy'
        
        success = init_auth_system(use_new_method=use_new, username=username)
        
        return jsonify({
            'success': success,
            'message': 'Autenticación inicializada' if success else 'Error en autenticación',
            'method': current_auth_method,
            'account': tigo_api.auth.username if tigo_api else None
        }), 200 if success else 500
        
    except Exception as e:
        logger.error(f"Error en admin_init_auth: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/auth/refresh', methods=['POST'])
@require_admin
def admin_refresh_auth():
    """Fuerza renovación de tokens"""
    try:
        if not tigo_api:
            return jsonify({
                'success': False,
                'error': 'Sistema no inicializado'
            }), 400
        
        if hasattr(tigo_api.auth, 'force_refresh'):
            success = tigo_api.auth.force_refresh()
        else:
            success = tigo_api.auth.login()
        
        return jsonify({
            'success': success,
            'message': 'Tokens renovados' if success else 'Error renovando'
        }), 200 if success else 500
        
    except Exception as e:
        logger.error(f"Error en admin_refresh_auth: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/auth/fingerprint', methods=['POST'])
@require_admin
def admin_renew_fingerprint():
    """Fuerza renovación de fingerprint (requiere OTP)"""
    try:
        if not tigo_api:
            return jsonify({
                'success': False,
                'error': 'Sistema no inicializado'
            }), 400
        
        if hasattr(tigo_api.auth, 'force_fingerprint_renewal'):
            success = tigo_api.auth.force_fingerprint_renewal()
            return jsonify({
                'success': success,
                'message': 'Fingerprint renovado' if success else 'Error renovando'
            }), 200 if success else 500
        else:
            return jsonify({
                'success': False,
                'error': 'Método no disponible para auth legacy'
            }), 400
        
    except Exception as e:
        logger.error(f"Error en admin_renew_fingerprint: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/auth/switch', methods=['POST'])
@require_admin
def admin_switch_account():
    """Cambia a la otra cuenta Tigo disponible"""
    global tigo_api
    
    try:
        success, new_account = auth_manager.switch_account()
        
        if success:
            tigo_api = TigoAPI(auth_manager.get_auth(new_account))
            return jsonify({
                'success': True,
                'message': f'Cambiado a cuenta {new_account}',
                'current_account': new_account,
                'status': auth_manager.get_all_status()
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': 'No se pudo cambiar de cuenta',
                'current_account': new_account
            }), 400
        
    except Exception as e:
        logger.error(f"Error en admin_switch_account: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/auth/retry', methods=['POST'])
@require_admin
def admin_retry_init():
    """Fuerza reintento de inicialización inmediatamente"""
    global tigo_api, system_initialized
    
    try:
        logger.info("🔄 Reintento manual solicitado por admin")
        
        success, msg = auth_manager.initialize_all_accounts()
        
        if success:
            auth = auth_manager.get_valid_auth()
            if auth:
                tigo_api = TigoAPI(auth)
                system_initialized = True
        
        return jsonify({
            'success': success,
            'message': msg,
            'system_status': auth_manager.get_all_status()
        }), 200 if success else 400
        
    except Exception as e:
        logger.error(f"Error en admin_retry_init: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/keys', methods=['GET', 'POST'])
@require_admin
def admin_keys():
    """Listar o crear claves"""
    try:
        if request.method == 'GET':
            # Listar claves
            include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'
            keys = key_manager.get_all_keys(include_inactive)
            
            return jsonify({
                'success': True,
                'keys': keys,
                'stats': key_manager.get_stats()
            }), 200
        
        else:  # POST
            # Crear clave
            data = request.get_json()
            
            max_amount = int(data.get('max_amount', 0))
            valid_days = int(data.get('valid_days', 30))
            description = data.get('description', '')
            
            if max_amount <= 0:
                return jsonify({
                    'success': False,
                    'error': 'max_amount debe ser positivo'
                }), 400
            
            key = key_manager.generate_key(max_amount, valid_days, description)
            
            if key:
                return jsonify({
                    'success': True,
                    'key': key,
                    'info': key_manager.get_key_info(key)
                }), 201
            else:
                return jsonify({
                    'success': False,
                    'error': 'Error generando clave'
                }), 500
                
    except Exception as e:
        logger.error(f"Error en admin_keys: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/keys/<key>', methods=['GET', 'PUT', 'DELETE'])
@require_admin
def admin_key_detail(key):
    """Gestionar clave específica"""
    try:
        key_info = key_manager.get_key_info(key)
        
        if not key_info:
            return jsonify({
                'success': False,
                'error': 'Clave no encontrada'
            }), 404
        
        if request.method == 'GET':
            return jsonify({
                'success': True,
                'key': key,
                'info': key_info
            }), 200
        
        elif request.method == 'PUT':
            data = request.get_json() or {}
            
            success = key_manager.modify_key(key, **data)
            
            return jsonify({
                'success': success,
                'message': 'Clave modificada' if success else 'Error modificando',
                'info': key_manager.get_key_info(key)
            }), 200 if success else 500
        
        else:  # DELETE
            success = key_manager.deactivate_key(key, "Desactivada por admin")
            
            return jsonify({
                'success': success,
                'message': 'Clave desactivada' if success else 'Error desactivando'
            }), 200 if success else 500
        
    except Exception as e:
        logger.error(f"Error en admin_key_detail: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/admin/history', methods=['GET'])
@require_admin
def admin_history():
    """Historial completo de recargas"""
    try:
        limit = int(request.args.get('limit', 100))
        status_filter = request.args.get('status')
        
        if not os.path.exists(HISTORY_FILE):
            return jsonify({
                'success': True,
                'history': [],
                'total': 0
            }), 200
        
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        if status_filter:
            history = [h for h in history if h.get('status') == status_filter.upper()]
        
        history = history[:limit]
        
        # Estadísticas
        all_history = json.load(open(HISTORY_FILE, 'r', encoding='utf-8'))
        total = len(all_history)
        successful = sum(1 for h in all_history if h.get('status') == 'SUCCESS')
        total_amount = sum(h.get('amount', 0) for h in all_history if h.get('status') == 'SUCCESS')
        
        return jsonify({
            'success': True,
            'history': history,
            'stats': {
                'total': total,
                'successful': successful,
                'failed': total - successful,
                'total_amount': total_amount
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error en admin_history: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================
# MANEJO DE ERRORES
# ============================================================
@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'success': False,
        'error': 'Endpoint no encontrado'
    }), 404


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Error 500: {e}")
    return jsonify({
        'success': False,
        'error': 'Error interno del servidor'
    }), 500


# ============================================================
# INICIALIZACIÓN
# ============================================================
def initialize():
    """Inicializa el sistema al arrancar"""
    logger.info("=" * 60)
    logger.info("INICIANDO API REST DE RECARGAS TIGO v2.1")
    logger.info(f"Puerto: {API_PORT}")
    logger.info(f"Cuentas configuradas: {list(TIGO_ACCOUNTS.keys())}")
    logger.info("=" * 60)
    
    print_config_info()
    
    # Intentar inicializar autenticación dual
    logger.info("Ejecutando inicialización dual de cuentas...")
    if init_auth_system():
        status = auth_manager.get_system_status()
        logger.info(f"✅ Sistema listo - Estado: {status}")
    else:
        logger.warning("⚠️ Inicialización inicial falló")
        logger.warning("⚠️ Sistema reintentará automáticamente en 10 minutos")
        logger.warning("⚠️ O use POST /api/admin/auth/init para forzar manualmente")


if __name__ == '__main__':
    initialize()
    app.run(host='0.0.0.0', port=API_PORT, debug=False, threaded=True)
