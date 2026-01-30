#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tigo_auth_legacy.py - Sistema de Autenticación Tigo Money LEGADO
Método antiguo como fallback cuando el nuevo método falla
"""

import requests
import json
import time
import logging
import uuid as uuid_lib
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (
    TIGO_ACCOUNTS,
    TIGO_IDENTITY_HOST,
    TIGO_WALLET_HOST,
    TIGO_IDENTITY_API_KEY,
    TIGO_WALLET_API_KEY,
    TIGO_API_KEY,
    PROXY_CONFIG,
    REQUEST_TIMEOUT,
    OTP_FILE,
    SMS_WAIT_TIMEOUT,
    SMS_CHECK_INTERVAL
)

logger = logging.getLogger(__name__)


class TigoAuthLegacy:
    """
    Sistema de autenticación Tigo Money - Método antiguo
    Usa el flujo de identity-backend y nwallet
    """
    
    NAMESPACE_APP = "com.juvo.tigomoney"
    BUILD_APP = "81010001"
    VERSION_APP = "8.1.1"
    DEVICE_CODE = "Fj7V0f6zKsg"
    
    def __init__(self, username: str = None):
        """
        Inicializa el sistema de autenticación
        
        Args:
            username: Número de teléfono Tigo
        """
        self.username = username or list(TIGO_ACCOUNTS.keys())[0]
        self.account_config = TIGO_ACCOUNTS.get(self.username)
        
        if not self.account_config:
            raise ValueError(f"Cuenta no configurada: {self.username}")
        
        self.password = self.account_config['password']
        
        # Estado
        self.uuid = None
        self.id_token = None
        self.token_expires_at = None
        
        # Sesión HTTP
        self.session = requests.Session()
        self.session.proxies = PROXY_CONFIG
        
        self.base_headers = {
            "User-Agent": "Dart/3.5 (dart:io)",
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json; charset=utf-8",
            "x-namespace-app": self.NAMESPACE_APP,
            "x-build-app": self.BUILD_APP,
            "x-version-app": self.VERSION_APP
        }
    
    def _log_request(self, method, url, headers, payload=None):
        """Log de request"""
        logger.debug(f"{method} {url}")
        logger.debug(f"Headers: {headers}")
        if payload:
            logger.debug(f"Body: {json.dumps(payload, indent=2)}")
    
    def _log_response(self, status_code, body):
        """Log de response"""
        logger.debug(f"Response: {status_code}")
        logger.debug(f"Body: {body[:500] if body else 'Empty'}")
    
    def _step1_validate_account(self) -> bool:
        """Paso 1: Validar cuenta y obtener UUID"""
        try:
            logger.info("🔹 LEGACY Paso 1: Validando cuenta")
            
            url = f"https://{TIGO_IDENTITY_HOST}/auth/validation/{self.username}"
            headers = self.base_headers.copy()
            headers["Host"] = TIGO_IDENTITY_HOST
            headers["x-api-key"] = TIGO_IDENTITY_API_KEY
            
            self._log_request("GET", url, headers)
            r = self.session.get(url, headers=headers, verify=False, timeout=REQUEST_TIMEOUT)
            self._log_response(r.status_code, r.text)
            
            if r.status_code == 200:
                data = r.json()
                self.uuid = data.get("uuid")
                
                if self.uuid:
                    logger.info(f"✅ Cuenta validada - UUID: {self.uuid}")
                    return True
                else:
                    logger.error("❌ No se recibió UUID")
            else:
                logger.error(f"❌ Error validando cuenta: HTTP {r.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Excepción validando cuenta: {e}")
        
        return False
    
    def _step2_request_otp(self) -> bool:
        """Paso 2: Solicitar envío de OTP por SMS"""
        try:
            logger.info("🔹 LEGACY Paso 2: Solicitando OTP")
            
            url = f"https://{TIGO_WALLET_HOST}/utilities/v1-0-0-0/utils/otp"
            headers = self.base_headers.copy()
            headers["Host"] = TIGO_WALLET_HOST
            headers["x-api-key"] = TIGO_WALLET_API_KEY
            
            payload = {
                "phone": f"+{self.username}",
                "userName": "Test2",
                "chanel": "phone",
                "deviceCode": self.DEVICE_CODE,
                "otpType": "registro",
                "otp_length": "6"
            }
            
            self._log_request("POST", url, headers, payload)
            r = self.session.post(url, headers=headers, json=payload, verify=False, timeout=REQUEST_TIMEOUT)
            self._log_response(r.status_code, r.text)
            
            if r.status_code == 200:
                logger.info("✅ Solicitud de OTP enviada")
                return True
            else:
                logger.error(f"❌ Error solicitando OTP: HTTP {r.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Excepción solicitando OTP: {e}")
        
        return False
    
    def _step3_wait_for_otp(self) -> Optional[str]:
        """Paso 3: Esperar OTP desde SMS"""
        logger.info(f"⏳ LEGACY: Esperando OTP por SMS...")
        
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
                        
                        try:
                            otp_time = datetime.fromisoformat(timestamp)
                            age = (datetime.now() - otp_time).total_seconds()
                            
                            if age < 300 and otp.isdigit() and len(otp) == 6:
                                logger.info(f"📱 OTP recibido: {otp}")
                                os.remove(OTP_FILE)
                                return otp
                        except:
                            pass
                
                time.sleep(SMS_CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error leyendo OTP: {e}")
                time.sleep(SMS_CHECK_INTERVAL)
        
        logger.error("❌ Timeout esperando SMS")
        return None
    
    def _step4_validate_otp(self, otp: str) -> bool:
        """Paso 4: Validar el código OTP"""
        try:
            logger.info(f"🔹 LEGACY Paso 4: Validando OTP {otp}")
            
            url = f"https://{TIGO_WALLET_HOST}/utilities/v1-0-0-0/utils/otp?otp={otp}&phone={self.username}&channel=phone"
            headers = self.base_headers.copy()
            headers["Host"] = TIGO_WALLET_HOST
            headers["x-api-key"] = TIGO_WALLET_API_KEY
            
            self._log_request("GET", url, headers)
            r = self.session.get(url, headers=headers, verify=False, timeout=REQUEST_TIMEOUT)
            self._log_response(r.status_code, r.text)
            
            if r.status_code == 200:
                data = r.json()
                if data.get("validCode") is True:
                    logger.info(f"✅ OTP validado")
                    return True
                else:
                    logger.error(f"❌ OTP inválido")
            else:
                logger.error(f"❌ Error validando OTP: HTTP {r.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Excepción validando OTP: {e}")
        
        return False
    
    def _step5_get_token(self) -> bool:
        """Paso 5: Obtener token Bearer"""
        try:
            logger.info("🔹 LEGACY Paso 5: Obteniendo token")
            
            url = f"https://{TIGO_IDENTITY_HOST}/auth/loginWithDevice"
            headers = self.base_headers.copy()
            headers["Host"] = TIGO_IDENTITY_HOST
            headers["x-api-key"] = TIGO_IDENTITY_API_KEY
            
            payload = {
                "username": self.username,
                "password": self.password,
                "uuid": self.uuid,
                "imei": str(uuid_lib.uuid4()),
                "model": "Iphone"
            }
            
            self._log_request("POST", url, headers, payload)
            r = self.session.post(url, headers=headers, json=payload, verify=False, timeout=REQUEST_TIMEOUT)
            self._log_response(r.status_code, r.text)
            
            if r.status_code == 200:
                data = r.json()
                token = data.get("token_aws") or data.get("access_token")
                
                if token:
                    self.id_token = token
                    expires_in = data.get("expires_in", 6000)
                    self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)
                    
                    logger.info(f"✅ Token obtenido (expira en {expires_in}s)")
                    return True
                else:
                    logger.error("❌ No se recibió token")
            else:
                logger.error(f"❌ Error obteniendo token: HTTP {r.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Excepción obteniendo token: {e}")
        
        return False
    
    def login(self) -> bool:
        """Flujo completo de autenticación"""
        logger.info("=" * 60)
        logger.info(f"🚀 INICIANDO AUTENTICACIÓN LEGACY - {self.username}")
        logger.info("=" * 60)
        
        # Paso 1: Validar cuenta
        if not self._step1_validate_account():
            return False
        
        # Paso 2: Solicitar OTP
        if not self._step2_request_otp():
            return False
        
        # Paso 3: Esperar OTP
        otp = self._step3_wait_for_otp()
        if not otp:
            return False
        
        # Paso 4: Validar OTP
        if not self._step4_validate_otp(otp):
            return False
        
        # Paso 5: Obtener token
        if not self._step5_get_token():
            return False
        
        logger.info("=" * 60)
        logger.info("✅ AUTENTICACIÓN LEGACY EXITOSA")
        logger.info("=" * 60)
        return True
    
    def is_token_valid(self) -> bool:
        """Verifica si el token es válido"""
        return (
            self.id_token is not None and
            self.token_expires_at is not None and
            datetime.now() < self.token_expires_at
        )
    
    def get_token(self) -> Optional[str]:
        """Obtiene token válido"""
        if not self.is_token_valid():
            if not self.login():
                return None
        return self.id_token
    
    def get_api_headers(self, account_number: str = None) -> Optional[Dict]:
        """Obtiene headers para la API"""
        token = self.get_token()
        if not token:
            return None
        
        headers = {
            "Host": TIGO_WALLET_HOST,
            "User-Agent": "Dart/3.5 (dart:io)",
            "Content-Type": "application/json; charset=utf-8",
            "x-api-key": TIGO_API_KEY,
            "Authorization": f"Bearer {token}"
        }
        
        if account_number:
            headers["accountnumber"] = account_number
        
        return headers
