#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tigo_auth_new.py - Nuevo Sistema de Autenticación Tigo Money
Implementa el flujo simplificado con fingerprint y OTP
"""

import requests
import json
import time
import logging
import random
import string
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (
    TIGO_ACCOUNTS,
    TIGO_AUTH_BASE_URL,
    TIGO_AUTH_HEADERS,
    OTP_DEVICE_CODE,
    PROXY_CONFIG,
    REQUEST_TIMEOUT,
    FINGERPRINTS_FILE,
    TOKENS_FILE,
    OTP_FILE,
    SMS_WAIT_TIMEOUT,
    SMS_CHECK_INTERVAL,
    MAX_OTP_ATTEMPTS
)

logger = logging.getLogger(__name__)

# Configurar logger HTTP
http_logger = logging.getLogger('http_requests')
if not http_logger.handlers:
    os.makedirs('logs', exist_ok=True)
    http_handler = logging.FileHandler('logs/http_requests.log', encoding='utf-8')
    http_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    http_logger.addHandler(http_handler)
    http_logger.setLevel(logging.INFO)


class TigoAuthNew:
    """
    Nuevo sistema de autenticación Tigo Money
    Soporta múltiples cuentas con fingerprints persistentes
    """
    
    def __init__(self, username: str = None):
        """
        Inicializa el sistema de autenticación
        
        Args:
            username: Número de teléfono Tigo (opcional, usa default si no se especifica)
        """
        self.username = username or list(TIGO_ACCOUNTS.keys())[0]
        self.account_config = TIGO_ACCOUNTS.get(self.username)
        
        if not self.account_config:
            raise ValueError(f"Cuenta no configurada: {self.username}")
        
        self.password = self.account_config['password']
        self.model = self.account_config['model']
        
        # Estado de autenticación
        self.fingerprint = None
        self.uuid = None
        self.access_token = None
        self.refresh_token = None
        self.token_aws = None
        self.token_expires_at = None
        self.account_info = None
        
        # Sesión HTTP
        self.session = requests.Session()
        self.session.proxies = PROXY_CONFIG
        
        # Cargar fingerprint guardado
        self._load_fingerprint()
    
    # ============================================================
    # GESTIÓN DE FINGERPRINTS
    # ============================================================
    
    def _generate_fingerprint(self) -> str:
        """Genera un fingerprint aleatorio de 16 caracteres hexadecimales"""
        return ''.join(random.choices('0123456789abcdef', k=16))
    
    def _load_fingerprint(self):
        """Carga el fingerprint guardado para esta cuenta"""
        try:
            if os.path.exists(FINGERPRINTS_FILE):
                with open(FINGERPRINTS_FILE, 'r') as f:
                    fingerprints = json.load(f)
                
                if self.username in fingerprints:
                    self.fingerprint = fingerprints[self.username].get('fingerprint')
                    logger.info(f"📱 Fingerprint cargado para {self.username}: {self.fingerprint}")
        except Exception as e:
            logger.error(f"Error cargando fingerprint: {e}")
    
    def _save_fingerprint(self):
        """Guarda el fingerprint para esta cuenta"""
        try:
            fingerprints = {}
            if os.path.exists(FINGERPRINTS_FILE):
                with open(FINGERPRINTS_FILE, 'r') as f:
                    fingerprints = json.load(f)
            
            fingerprints[self.username] = {
                'fingerprint': self.fingerprint,
                'validated_at': datetime.now().isoformat(),
                'model': self.model
            }
            
            with open(FINGERPRINTS_FILE, 'w') as f:
                json.dump(fingerprints, f, indent=2)
            
            logger.info(f"💾 Fingerprint guardado para {self.username}")
        except Exception as e:
            logger.error(f"Error guardando fingerprint: {e}")
    
    def _clear_fingerprint(self):
        """Limpia el fingerprint (para renovación)"""
        self.fingerprint = None
        try:
            if os.path.exists(FINGERPRINTS_FILE):
                with open(FINGERPRINTS_FILE, 'r') as f:
                    fingerprints = json.load(f)
                
                if self.username in fingerprints:
                    del fingerprints[self.username]
                    
                    with open(FINGERPRINTS_FILE, 'w') as f:
                        json.dump(fingerprints, f, indent=2)
                    
                    logger.info(f"🗑️ Fingerprint eliminado para {self.username}")
        except Exception as e:
            logger.error(f"Error limpiando fingerprint: {e}")
    
    # ============================================================
    # GESTIÓN DE TOKENS
    # ============================================================
    
    def _save_tokens(self):
        """Guarda los tokens en archivo"""
        try:
            tokens = {}
            if os.path.exists(TOKENS_FILE):
                with open(TOKENS_FILE, 'r') as f:
                    tokens = json.load(f)
            
            tokens[self.username] = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'token_aws': self.token_aws,
                'expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None,
                'account_info': self.account_info,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(TOKENS_FILE, 'w') as f:
                json.dump(tokens, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Tokens guardados para {self.username}")
        except Exception as e:
            logger.error(f"Error guardando tokens: {e}")
    
    def _load_tokens(self) -> bool:
        """Carga tokens guardados si aún son válidos"""
        try:
            if os.path.exists(TOKENS_FILE):
                with open(TOKENS_FILE, 'r') as f:
                    tokens = json.load(f)
                
                if self.username in tokens:
                    token_data = tokens[self.username]
                    expires_at = token_data.get('expires_at')
                    
                    if expires_at:
                        expires_dt = datetime.fromisoformat(expires_at)
                        if datetime.now() < expires_dt:
                            self.access_token = token_data.get('access_token')
                            self.refresh_token = token_data.get('refresh_token')
                            self.token_aws = token_data.get('token_aws')
                            self.token_expires_at = expires_dt
                            self.account_info = token_data.get('account_info')
                            logger.info(f"✅ Tokens válidos cargados para {self.username}")
                            return True
            return False
        except Exception as e:
            logger.error(f"Error cargando tokens: {e}")
            return False
    
    # ============================================================
    # MÉTODOS HTTP
    # ============================================================
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Realiza una petición HTTP con logging"""
        url = f"{TIGO_AUTH_BASE_URL}{endpoint}"
        
        headers = TIGO_AUTH_HEADERS.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        
        http_logger.info(f"{'='*60}")
        http_logger.info(f"REQUEST: {method} {url}")
        http_logger.info(f"Headers: {json.dumps(headers, indent=2)}")
        if 'json' in kwargs:
            http_logger.info(f"Body: {json.dumps(kwargs['json'], indent=2)}")
        
        try:
            response = self.session.request(
                method,
                url,
                headers=headers,
                verify=False,
                timeout=REQUEST_TIMEOUT,
                **kwargs
            )
            
            http_logger.info(f"RESPONSE: {response.status_code}")
            http_logger.info(f"Body: {response.text[:1000]}")
            http_logger.info(f"{'='*60}")
            
            return response
        except Exception as e:
            http_logger.error(f"ERROR: {e}")
            raise
    
    # ============================================================
    # FLUJO DE AUTENTICACIÓN - NUEVO MÉTODO
    # ============================================================
    
    def _step1_access_task(self) -> Tuple[bool, bool, str]:
        """
        Paso 1: POST /access/task
        Verifica si el fingerprint es válido
        
        Returns:
            Tuple (éxito, necesita_otp, uuid)
        """
        # Si no hay fingerprint, generar uno nuevo
        if not self.fingerprint:
            self.fingerprint = self._generate_fingerprint()
            logger.info(f"🔑 Nuevo fingerprint generado: {self.fingerprint}")
        
        try:
            payload = {
                "username": self.username,
                "fingerprint": self.fingerprint,
                "model": self.model
            }
            
            logger.info(f"📤 Paso 1: Access Task para {self.username}")
            response = self._make_request('POST', '/access/task', json=payload)
            
            if response.status_code == 200:
                data = response.json()
                self.uuid = data.get('uuid')
                needs_otp = data.get('otp', True)
                
                logger.info(f"✅ Access Task exitoso - UUID: {self.uuid}, OTP requerido: {needs_otp}")
                return True, needs_otp, self.uuid
            else:
                logger.error(f"❌ Access Task falló: {response.status_code} - {response.text}")
                return False, True, None
                
        except Exception as e:
            logger.error(f"❌ Error en Access Task: {e}")
            return False, True, None
    
    def _step2_request_otp(self) -> bool:
        """
        Paso 2: POST /otp - Solicitar código OTP
        """
        if not self.uuid:
            logger.error("UUID no disponible para solicitar OTP")
            return False
        
        try:
            payload = {
                "uuid": self.uuid,
                "code": OTP_DEVICE_CODE
            }
            
            logger.info(f"📤 Paso 2: Solicitando OTP para UUID {self.uuid}")
            response = self._make_request('POST', '/otp', json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('message') == 'OTP Generated':
                    logger.info("✅ OTP solicitado correctamente - Esperando SMS")
                    return True
                else:
                    logger.warning(f"⚠️ Respuesta inesperada: {data}")
                    return True  # Intentar de todas formas
            else:
                logger.error(f"❌ Error solicitando OTP: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error en solicitud OTP: {e}")
            return False
    
    def _step3_wait_for_sms_otp(self) -> Optional[str]:
        """
        Paso 3: Esperar y leer OTP desde SMS
        Máximo 3 minutos de espera
        """
        logger.info(f"⏳ Esperando OTP por SMS (máx {SMS_WAIT_TIMEOUT}s)...")
        
        # Limpiar archivo OTP anterior
        if os.path.exists(OTP_FILE):
            os.remove(OTP_FILE)
        
        start_time = time.time()
        
        while (time.time() - start_time) < SMS_WAIT_TIMEOUT:
            try:
                if os.path.exists(OTP_FILE):
                    with open(OTP_FILE, 'r') as f:
                        lines = f.read().strip().split('\n')
                    
                    if len(lines) >= 2:
                        otp = lines[0].strip()
                        timestamp = lines[1].strip()
                        
                        # Verificar que sea reciente (últimos 5 minutos)
                        try:
                            otp_time = datetime.fromisoformat(timestamp)
                            age = (datetime.now() - otp_time).total_seconds()
                            
                            if age < 300 and otp.isdigit() and len(otp) == 6:
                                logger.info(f"📱 OTP recibido: {otp} (edad: {int(age)}s)")
                                os.remove(OTP_FILE)  # Limpiar después de leer
                                return otp
                        except:
                            pass
                
                elapsed = int(time.time() - start_time)
                if elapsed > 0 and elapsed % 30 == 0:
                    logger.info(f"⏳ Esperando SMS... ({elapsed}s / {SMS_WAIT_TIMEOUT}s)")
                
                time.sleep(SMS_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error leyendo OTP: {e}")
                time.sleep(SMS_CHECK_INTERVAL)
        
        logger.error(f"❌ Timeout esperando SMS ({SMS_WAIT_TIMEOUT}s)")
        return None
    
    def _step4_validate_otp(self, otp: str) -> bool:
        """
        Paso 4: PUT /otp - Validar código OTP
        """
        if not self.uuid or not otp:
            logger.error("UUID u OTP no disponible")
            return False
        
        try:
            payload = {
                "uuid": self.uuid,
                "otp": otp
            }
            
            logger.info(f"📤 Paso 4: Validando OTP {otp}")
            response = self._make_request('PUT', '/otp', json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('message') == 'OTP Validated':
                    logger.info("✅ OTP validado correctamente")
                    # Guardar fingerprint ya que está validado
                    self._save_fingerprint()
                    return True
                else:
                    logger.warning(f"⚠️ Respuesta: {data}")
                    return False
            else:
                logger.error(f"❌ OTP inválido: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error validando OTP: {e}")
            return False
    
    def _step5_validate_uuid(self) -> bool:
        """
        Paso 5: GET /auth/validate/{uuid} - Validar UUID
        """
        if not self.uuid:
            logger.error("UUID no disponible")
            return False
        
        try:
            logger.info(f"📤 Paso 5: Validando UUID {self.uuid}")
            response = self._make_request('GET', f'/auth/validate/{self.uuid}')
            
            if response.status_code == 200:
                data = response.json()
                next_step = data.get('next')
                self.account_info = data.get('account_info')
                
                if next_step == 'LOGIN':
                    logger.info(f"✅ UUID validado - Cuenta: {self.account_info.get('name', {}).get('fullName', 'N/A')}")
                    return True
                else:
                    logger.warning(f"⚠️ Next step inesperado: {next_step}")
                    return False
            elif response.status_code == 406:
                logger.warning("⚠️ UUID/Fingerprint no válido - Requiere renovación")
                self._clear_fingerprint()
                return False
            else:
                logger.error(f"❌ Error validando UUID: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error validando UUID: {e}")
            return False
    
    def _step6_login(self) -> bool:
        """
        Paso 6: POST /auth/login - Login final
        """
        if not self.uuid:
            logger.error("UUID no disponible para login")
            return False
        
        try:
            payload = {
                "uuid": self.uuid,
                "password": self.password
            }
            
            logger.info(f"📤 Paso 6: Login final con UUID {self.uuid}")
            response = self._make_request('POST', '/auth/login', json=payload)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extraer tokens
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                self.token_aws = data.get('token_aws')
                
                # Calcular expiración
                expires_in = data.get('expires_in', 6000)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                
                # Info de cuenta
                self.account_info = data.get('account_info', self.account_info)
                
                # Guardar tokens
                self._save_tokens()
                
                logger.info("=" * 60)
                logger.info("✅ LOGIN EXITOSO")
                logger.info(f"   Usuario: {self.username}")
                logger.info(f"   Nombre: {self.account_info.get('name', {}).get('fullName', 'N/A')}")
                logger.info(f"   Token expira en: {expires_in}s")
                logger.info("=" * 60)
                
                return True
            else:
                logger.error(f"❌ Login falló: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error en login: {e}")
            return False
    
    # ============================================================
    # MÉTODOS PÚBLICOS
    # ============================================================
    
    def login(self) -> bool:
        """
        Ejecuta el flujo completo de autenticación
        
        Returns:
            True si el login fue exitoso
        """
        logger.info("=" * 60)
        logger.info(f"🚀 INICIANDO AUTENTICACIÓN - {self.username}")
        logger.info("=" * 60)
        
        # Verificar si ya tenemos tokens válidos
        if self._load_tokens():
            logger.info("✅ Usando tokens existentes válidos")
            return True
        
        # Paso 1: Access Task
        success, needs_otp, uuid = self._step1_access_task()
        if not success:
            logger.error("❌ Falló Access Task")
            return False
        
        # Si necesita OTP (fingerprint nuevo o no validado)
        if needs_otp:
            logger.info("🔐 Fingerprint requiere validación con OTP")
            
            # Paso 2: Solicitar OTP
            if not self._step2_request_otp():
                logger.error("❌ Falló solicitud de OTP")
                return False
            
            # Paso 3: Esperar SMS
            otp = self._step3_wait_for_sms_otp()
            if not otp:
                logger.error("❌ No se recibió OTP por SMS")
                return False
            
            # Paso 4: Validar OTP
            if not self._step4_validate_otp(otp):
                logger.error("❌ Falló validación de OTP")
                return False
        else:
            logger.info("✅ Fingerprint ya validado - Sin OTP requerido")
            # Guardar fingerprint si no está guardado
            self._save_fingerprint()
        
        # Paso 5: Validar UUID
        if not self._step5_validate_uuid():
            logger.error("❌ Falló validación de UUID")
            # Si falla, puede ser que el fingerprint ya no sea válido
            self._clear_fingerprint()
            return False
        
        # Paso 6: Login
        if not self._step6_login():
            logger.error("❌ Falló login final")
            return False
        
        return True
    
    def is_token_valid(self) -> bool:
        """Verifica si el token actual es válido"""
        if not self.access_token or not self.token_expires_at:
            return False
        
        return datetime.now() < self.token_expires_at
    
    def get_token(self) -> Optional[str]:
        """Obtiene un token válido (reautentica si es necesario)"""
        if self.is_token_valid():
            return self.access_token
        
        logger.info("Token expirado o no disponible, renovando...")
        if self.login():
            return self.access_token
        return None
    
    def get_api_headers(self, account_number: str = None) -> Optional[Dict]:
        """
        Obtiene headers para hacer requests a la API de recargas
        IMPORTANTE: Usa token_aws (JWT), NO access_token
        
        Args:
            account_number: Número de cuenta para el header (opcional)
        
        Returns:
            Dict con headers o None si no hay token válido
        """
        # Verificar que tenemos token_aws válido
        if not self.is_token_valid():
            logger.info("Token expirado o no disponible, renovando...")
            if not self.login():
                return None
        
        # CRÍTICO: Usar token_aws para las operaciones de API
        if not self.token_aws:
            logger.error("token_aws no disponible después de login")
            return None
        
        headers = {
            "Host": "nwallet.py.tigomoney.io",
            "User-Agent": "Dart/3.7 (dart:io)",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
            "x-api-key": "dxtyCQG4pUk0FZvpEi8DFwmOEUs4qX0cL4wYL9SCAL5vTgYv",
            "x-namespace-app": "com.juvo.tigomoney",
            "x-build-app": "82000060",
            "x-version-app": "8.2.0",
            "Authorization": f"Bearer {self.token_aws}"  # USAR token_aws, NO access_token
        }
        
        if account_number:
            headers["accountnumber"] = account_number
        
        return headers
    
    def force_refresh(self) -> bool:
        """
        Fuerza renovación de tokens usando fingerprint existente.
        NO recarga tokens del archivo - realiza renovación real.
        
        Returns:
            True si la renovación fue exitosa
        """
        logger.info("=" * 60)
        logger.info("🔄 FORZANDO RENOVACIÓN DE TOKEN")
        logger.info("=" * 60)
        
        # Limpiar tokens actuales en memoria
        self.access_token = None
        self.refresh_token = None
        self.token_aws = None
        self.token_expires_at = None
        
        # Limpiar tokens del archivo para evitar que _load_tokens() los recargue
        self._clear_saved_tokens()
        
        # Si tenemos fingerprint válido, usar renovación simple
        if self.fingerprint:
            logger.info(f"✅ Fingerprint disponible: {self.fingerprint[:8]}...")
            return self._renew_token_with_fingerprint()
        else:
            # Sin fingerprint, necesita flujo completo con OTP
            logger.warning("⚠️ Sin fingerprint - Requiere autenticación completa con OTP")
            return self.login()
    
    def _clear_saved_tokens(self):
        """Limpia los tokens guardados en archivo para esta cuenta"""
        try:
            if os.path.exists(TOKENS_FILE):
                with open(TOKENS_FILE, 'r') as f:
                    tokens = json.load(f)
                
                if self.username in tokens:
                    del tokens[self.username]
                    with open(TOKENS_FILE, 'w') as f:
                        json.dump(tokens, f, indent=2)
                    logger.info(f"🗑️ Tokens eliminados del archivo para {self.username}")
        except Exception as e:
            logger.error(f"Error limpiando tokens del archivo: {e}")
    
    def _renew_token_with_fingerprint(self) -> bool:
        """
        Renueva token usando fingerprint existente (sin OTP).
        Flujo simplificado: access/task → validate → login
        
        Returns:
            True si la renovación fue exitosa
        """
        logger.info("🔐 Renovación rápida con fingerprint existente")
        
        try:
            # Paso 1: Access Task (verificar fingerprint)
            success, needs_otp, uuid = self._step1_access_task()
            
            if not success:
                logger.error("❌ Access Task falló durante renovación")
                # Fingerprint puede estar inválido
                self._clear_fingerprint()
                return False
            
            if needs_otp:
                # Fingerprint ya no es válido, necesita OTP
                logger.warning("⚠️ Fingerprint ya no es válido - Requiere OTP")
                # Intentar flujo completo
                return self._complete_auth_with_otp()
            
            # Paso 5: Validar UUID
            if not self._step5_validate_uuid():
                logger.error("❌ Validación de UUID falló")
                self._clear_fingerprint()
                return False
            
            # Paso 6: Login
            if not self._step6_login():
                logger.error("❌ Login falló durante renovación")
                return False
            
            logger.info("✅ Renovación de token exitosa")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error en renovación con fingerprint: {e}")
            return False
    
    def _complete_auth_with_otp(self) -> bool:
        """
        Completa autenticación con OTP cuando fingerprint no es válido.
        Se usa como fallback de _renew_token_with_fingerprint.
        
        Returns:
            True si la autenticación fue exitosa
        """
        logger.info("🔐 Completando autenticación con OTP...")
        
        # Paso 2: Solicitar OTP
        if not self._step2_request_otp():
            logger.error("❌ Falló solicitud de OTP")
            return False
        
        # Paso 3: Esperar SMS
        otp = self._step3_wait_for_sms_otp()
        if not otp:
            logger.error("❌ No se recibió OTP por SMS")
            return False
        
        # Paso 4: Validar OTP
        if not self._step4_validate_otp(otp):
            logger.error("❌ Falló validación de OTP")
            return False
        
        # Paso 5: Validar UUID
        if not self._step5_validate_uuid():
            logger.error("❌ Falló validación de UUID")
            return False
        
        # Paso 6: Login
        if not self._step6_login():
            logger.error("❌ Falló login final")
            return False
        
        return True
    
    def force_fingerprint_renewal(self) -> bool:
        """Fuerza renovación de fingerprint (requiere OTP)"""
        logger.info("Forzando renovación de fingerprint...")
        self._clear_fingerprint()
        self.access_token = None
        self.token_expires_at = None
        return self.login()
    
    def get_status(self) -> Dict:
        """Obtiene el estado actual del sistema de autenticación"""
        return {
            'username': self.username,
            'has_fingerprint': self.fingerprint is not None,
            'fingerprint': self.fingerprint[:8] + '...' if self.fingerprint else None,
            'has_token': self.access_token is not None,
            'token_valid': self.is_token_valid(),
            'token_expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None,
            'account_name': self.account_info.get('name', {}).get('fullName') if self.account_info else None
        }


# ============================================================
# GESTOR DE MÚLTIPLES CUENTAS
# ============================================================

class TigoAuthManager:
    """
    Gestor de autenticación para múltiples cuentas Tigo
    Permite rotar entre cuentas y manejar fallbacks
    """
    
    def __init__(self):
        self.authenticators: Dict[str, TigoAuthNew] = {}
        self.current_account = None
        self._initialization_status = {}  # Estado de inicialización por cuenta
        self._retry_scheduled = False
        self._last_init_attempt = None
        
        # Inicializar autenticadores para todas las cuentas configuradas
        for username in TIGO_ACCOUNTS.keys():
            self.authenticators[username] = TigoAuthNew(username)
            self._initialization_status[username] = {
                'initialized': False,
                'last_attempt': None,
                'error': None
            }
        
        # Establecer cuenta por defecto
        if self.authenticators:
            self.current_account = list(self.authenticators.keys())[0]
    
    def initialize_all_accounts(self) -> Tuple[bool, str]:
        """
        Inicializa ambas cuentas al arranque del sistema.
        Si ambas fallan, programa un reintento en 10 minutos.
        
        Returns:
            Tuple (al_menos_una_exitosa, mensaje_estado)
        """
        from config import RETRY_DELAY_MINUTES
        
        logger.info("=" * 60)
        logger.info("🚀 INICIALIZACIÓN DUAL DE CUENTAS")
        logger.info("=" * 60)
        
        self._last_init_attempt = datetime.now()
        accounts_ok = []
        accounts_failed = []
        
        for username, auth in self.authenticators.items():
            logger.info(f"\n📱 Intentando cuenta: {username}")
            try:
                if auth.login():
                    accounts_ok.append(username)
                    self._initialization_status[username] = {
                        'initialized': True,
                        'last_attempt': datetime.now().isoformat(),
                        'error': None
                    }
                    logger.info(f"✅ Cuenta {username} inicializada correctamente")
                else:
                    accounts_failed.append(username)
                    self._initialization_status[username] = {
                        'initialized': False,
                        'last_attempt': datetime.now().isoformat(),
                        'error': 'Login falló'
                    }
                    logger.warning(f"❌ Cuenta {username} falló en login")
            except Exception as e:
                accounts_failed.append(username)
                self._initialization_status[username] = {
                    'initialized': False,
                    'last_attempt': datetime.now().isoformat(),
                    'error': str(e)
                }
                logger.error(f"❌ Error con cuenta {username}: {e}")
        
        # Resumen
        logger.info("\n" + "=" * 60)
        logger.info("📊 RESUMEN DE INICIALIZACIÓN")
        logger.info(f"   Exitosas: {len(accounts_ok)} - {accounts_ok}")
        logger.info(f"   Fallidas: {len(accounts_failed)} - {accounts_failed}")
        logger.info("=" * 60)
        
        if accounts_ok:
            self.current_account = accounts_ok[0]
            self._retry_scheduled = False
            
            if accounts_failed:
                return True, f"PARTIAL: {accounts_ok[0]} OK, {accounts_failed} fallaron"
            else:
                return True, f"READY: Todas las cuentas inicializadas"
        else:
            # Ambas fallaron - programar reintento
            self._retry_scheduled = True
            logger.warning(f"⏳ Ambas cuentas fallaron. Reintento en {RETRY_DELAY_MINUTES} minutos")
            return False, f"WAITING_RETRY: Reintento en {RETRY_DELAY_MINUTES} minutos"
    
    def should_retry(self) -> bool:
        """Verifica si es tiempo de reintentar la inicialización"""
        from config import RETRY_DELAY_MINUTES
        
        if not self._retry_scheduled:
            return False
        
        if not self._last_init_attempt:
            return True
        
        elapsed = (datetime.now() - self._last_init_attempt).total_seconds() / 60
        return elapsed >= RETRY_DELAY_MINUTES
    
    def retry_initialization(self) -> Tuple[bool, str]:
        """
        Reintenta la inicialización si ha pasado el tiempo de espera
        
        Returns:
            Tuple (éxito, mensaje)
        """
        if not self.should_retry():
            remaining = 10 - int((datetime.now() - self._last_init_attempt).total_seconds() / 60)
            return False, f"Espera {remaining} minutos más para reintentar"
        
        logger.info("🔄 Ejecutando reintento programado de inicialización...")
        return self.initialize_all_accounts()
    
    def get_system_status(self) -> str:
        """
        Obtiene el estado actual del sistema
        
        Returns:
            'READY', 'PARTIAL', 'WAITING_RETRY', 'ERROR'
        """
        initialized_count = sum(
            1 for status in self._initialization_status.values()
            if status.get('initialized', False)
        )
        
        total = len(self._initialization_status)
        
        if initialized_count == total:
            return 'READY'
        elif initialized_count > 0:
            return 'PARTIAL'
        elif self._retry_scheduled:
            return 'WAITING_RETRY'
        else:
            return 'ERROR'
    
    def get_auth(self, username: str = None) -> TigoAuthNew:
        """Obtiene el autenticador para una cuenta específica"""
        if username is None:
            username = self.current_account
        
        if username not in self.authenticators:
            raise ValueError(f"Cuenta no configurada: {username}")
        
        return self.authenticators[username]
    
    def login(self, username: str = None) -> bool:
        """Realiza login con una cuenta específica"""
        auth = self.get_auth(username)
        success = auth.login()
        
        if success:
            self._initialization_status[username or self.current_account] = {
                'initialized': True,
                'last_attempt': datetime.now().isoformat(),
                'error': None
            }
        
        return success
    
    def login_any(self) -> Tuple[bool, str]:
        """
        Intenta login con cualquier cuenta disponible
        
        Returns:
            Tuple (éxito, username de la cuenta que funcionó)
        """
        for username, auth in self.authenticators.items():
            logger.info(f"Intentando login con {username}...")
            if auth.login():
                self.current_account = username
                self._initialization_status[username] = {
                    'initialized': True,
                    'last_attempt': datetime.now().isoformat(),
                    'error': None
                }
                return True, username
        
        return False, None
    
    def get_valid_auth(self) -> Optional[TigoAuthNew]:
        """Obtiene un autenticador con token válido"""
        # Primero intentar con la cuenta actual
        if self.current_account:
            auth = self.authenticators[self.current_account]
            if auth.is_token_valid():
                return auth
        
        # Buscar cualquier cuenta con token válido
        for username, auth in self.authenticators.items():
            if auth.is_token_valid():
                self.current_account = username
                return auth
        
        # Intentar login con cualquier cuenta
        success, username = self.login_any()
        if success:
            return self.authenticators[username]
        
        return None
    
    def switch_account(self) -> Tuple[bool, str]:
        """
        Cambia a la otra cuenta disponible
        
        Returns:
            Tuple (éxito, nuevo_username)
        """
        other_accounts = [u for u in self.authenticators.keys() if u != self.current_account]
        
        for username in other_accounts:
            auth = self.authenticators[username]
            if auth.is_token_valid() or auth.login():
                old_account = self.current_account
                self.current_account = username
                logger.info(f"🔄 Cambiado de {old_account} a {username}")
                return True, username
        
        return False, self.current_account
    
    def get_all_status(self) -> Dict:
        """Obtiene el estado de todas las cuentas"""
        return {
            'system_status': self.get_system_status(),
            'current_account': self.current_account,
            'retry_scheduled': self._retry_scheduled,
            'last_init_attempt': self._last_init_attempt.isoformat() if self._last_init_attempt else None,
            'accounts': {
                username: {
                    **auth.get_status(),
                    'init_status': self._initialization_status.get(username, {})
                }
                for username, auth in self.authenticators.items()
            }
        }
