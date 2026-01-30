#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tigo_api.py - API de Tigo para Recargas
Maneja las operaciones de consulta de paquetes y recargas
"""

import requests
import json
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (
    TIGO_BASE_URL_API,
    PROXY_CONFIG,
    REQUEST_TIMEOUT,
    MAX_RETRY_ATTEMPTS,
    MAX_ORDER_ATTEMPTS,
    ORDER_CHECK_INTERVAL,
    ORDER_COOLDOWN_SECONDS
)

logger = logging.getLogger(__name__)


class TigoAPI:
    """Maneja las operaciones con la API de Tigo para recargas"""
    
    def __init__(self, auth_manager):
        """
        Inicializa la API
        
        Args:
            auth_manager: Instancia de TigoAuthNew o TigoAuthLegacy
        """
        self.auth = auth_manager
        self.last_order = None
        self.proxies = PROXY_CONFIG
        self.timeout = REQUEST_TIMEOUT
        
        # Sesión HTTP
        self.session = requests.Session()
        self.session.proxies = self.proxies
        
        # Control de órdenes recientes
        self.recent_orders = {}
        self.order_cooldown_seconds = ORDER_COOLDOWN_SECONDS
    
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Realiza petición HTTP con reintentos"""
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                kwargs['verify'] = False
                kwargs['timeout'] = self.timeout
                
                logger.debug(f"Request [{attempt+1}/{MAX_RETRY_ATTEMPTS}]: {method} {url}")
                
                if method == 'GET':
                    response = self.session.get(url, **kwargs)
                else:
                    response = self.session.post(url, **kwargs)
                
                logger.debug(f"Response: {response.status_code}")
                return response
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout en intento {attempt+1}")
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(2)
            except Exception as e:
                logger.error(f"Error en intento {attempt+1}: {e}")
                if attempt == MAX_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(2)
    
    def get_packages(self, destination_number: str) -> Tuple[bool, List[Dict], str]:
        """
        Obtiene los paquetes disponibles para un número
        
        Args:
            destination_number: Número de destino (10 dígitos)
            
        Returns:
            Tuple (éxito, lista_paquetes, mensaje)
        """
        try:
            headers = self.auth.get_api_headers(destination_number)
            if not headers:
                logger.warning("Headers inválidos, reautenticando...")
                if self.auth.login():
                    headers = self.auth.get_api_headers(destination_number)
                    if not headers:
                        return False, [], "Error de autenticación"
                else:
                    return False, [], "Error de autenticación"
            
            logger.info(f"📦 Consultando paquetes para: {destination_number}")
            
            response = self._make_request(
                'GET',
                f"{TIGO_BASE_URL_API}/middleware/api/v1.0.0/paquetes",
                headers=headers
            )
            
            if response.status_code == 403:
                logger.warning("Error 403, renovando token...")
                if hasattr(self.auth, 'force_refresh'):
                    self.auth.force_refresh()
                else:
                    self.auth.login()
                headers = self.auth.get_api_headers(destination_number)
                response = self._make_request(
                    'GET',
                    f"{TIGO_BASE_URL_API}/middleware/api/v1.0.0/paquetes",
                    headers=headers
                )
            
            if response.status_code == 200:
                packages = response.json()
                logger.info(f"✅ {len(packages)} paquetes encontrados")
                return True, packages, "OK"
            else:
                logger.error(f"Error HTTP {response.status_code}: {response.text[:200]}")
                return False, [], f"Error HTTP {response.status_code}"
                
        except Exception as e:
            logger.error(f"Error en get_packages: {e}")
            return False, [], str(e)
    
    def can_create_order(self, destination: str) -> Tuple[bool, str]:
        """Verifica si se puede crear una orden (cooldown)"""
        if destination in self.recent_orders:
            last_order = self.recent_orders[destination]
            elapsed = (datetime.now() - last_order['timestamp']).total_seconds()
            
            if elapsed < self.order_cooldown_seconds:
                remaining = int(self.order_cooldown_seconds - elapsed)
                return False, f"Espera {remaining}s antes de recargar al mismo número"
        
        return True, "OK"
    
    def generate_order_id(self) -> str:
        """Genera ID único para la orden"""
        timestamp_part = str(int(time.time() * 1000))[-6:]
        random_part = str(random.randint(100000000, 999999999))
        return timestamp_part + random_part
    
    def create_purchase_order(self, destination: str, package: Dict) -> Tuple[bool, Dict, str]:
        """
        Crea una orden de compra
        
        Args:
            destination: Número de destino
            package: Diccionario con info del paquete
            
        Returns:
            Tuple (éxito, datos_orden, mensaje)
        """
        # Verificar cooldown
        can_create, msg = self.can_create_order(destination)
        if not can_create:
            return False, {}, msg
        
        try:
            headers = self.auth.get_api_headers()
            if not headers:
                return False, {}, "Error de autenticación"
            
            headers["date"] = datetime.now().strftime("%d/%m/%Y")
            
            purchase_order_id = self.generate_order_id()
            
            payload = {
                "accountNumber": destination,
                "accountType": "subscribers",
                "applicationName": "tigomoney2-0-all-mobile-packets-tm-prd-py",
                "customerIpAddress": "181.00.000.00",
                "customerName": "Cliente API",
                "deviceId": "0",
                "email": "api@tigo.com.py",
                "paymentAmount": "1.0",
                "paymentChannel": "84",
                "paymentCurrencyCode": "PYG",
                "phoneNumber": destination,
                "productReference": package['id'],
                "purchaseDetails": [
                    {
                        "name": package['id'],
                        "quantity": "1",
                        "amount": str(package['amount'])
                    }
                ],
                "purchaseOrderId": purchase_order_id,
                "updatePaymentSeparately": False,
                "billToAddress": {
                    "firstName": "API",
                    "lastName": "Tigo",
                    "country": "PY",
                    "city": "Asunción",
                    "street": "Calle API 123",
                    "postalCode": "1000",
                    "state": "Central",
                    "email": "api@tigo.com.py"
                },
                "documentType": "nit",
                "documentNumber": "0",
                "deviceFingerprintId": "0",
                "createPaymentToken": False,
                "creditCardDetails": {
                    "accountNumber": self.auth.username,
                    "cvv": "0000"
                }
            }
            
            logger.info(f"💳 Creando orden: {destination} - {package['name']} - ID: {purchase_order_id}")
            
            response = self._make_request(
                'POST',
                f"{TIGO_BASE_URL_API}/apigee/v1-0-0-0/paymentgateway/pg/customers/115b3a1d0ed4224d461c5bbf40093508/transactions/orders",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("httpStatusCode") == 200 and "body" in result:
                    order_data = result["body"]
                    self.last_order = order_data
                    
                    # Registrar orden
                    self.recent_orders[destination] = {
                        'timestamp': datetime.now(),
                        'order_id': order_data.get('orderId'),
                        'purchase_order_id': purchase_order_id
                    }
                    
                    logger.info(f"✅ Orden creada: {order_data.get('orderId')}")
                    return True, order_data, "Orden creada"
                else:
                    return False, {}, result.get('message', 'Error desconocido')
            
            elif response.status_code == 409:
                logger.warning(f"Error 409: Orden duplicada para {destination}")
                return False, {}, "Espera 60 segundos antes de recargar al mismo número"
            
            else:
                logger.error(f"Error HTTP {response.status_code}")
                return False, {}, f"Error HTTP {response.status_code}"
                
        except Exception as e:
            logger.error(f"Error creando orden: {e}")
            return False, {}, str(e)
    
    def check_order_status(self, order_id: str) -> Tuple[bool, Dict, str]:
        """Verifica el estado de una orden"""
        try:
            headers = self.auth.get_api_headers()
            if not headers:
                return False, {}, "Error de autenticación"
            
            headers["date"] = datetime.now().strftime("%d/%m/%Y")
            
            response = self._make_request(
                'GET',
                f"{TIGO_BASE_URL_API}/apigee/v1-0-0-0/paymentgateway/pg/customers/115b3a1d0ed4224d461c5bbf40093508/transactions/orders/{order_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get("httpStatusCode") == 200 and "body" in result:
                    return True, result["body"], "OK"
                else:
                    return False, {}, "Error en respuesta"
            else:
                return False, {}, f"Error HTTP {response.status_code}"
                
        except Exception as e:
            logger.error(f"Error verificando orden: {e}")
            return False, {}, str(e)
    
    def wait_for_completion(self, order_id: str, callback=None) -> Tuple[bool, Dict, str]:
        """
        Espera hasta que la orden se complete o falle
        
        Args:
            order_id: ID de la orden
            callback: Función callback para actualizaciones
            
        Returns:
            Tuple (éxito, datos_finales, mensaje)
        """
        logger.info(f"⏳ Esperando completación de orden {order_id}")
        
        start_time = time.time()
        timeout_seconds = 45
        last_status = None
        order_data = {}
        
        for attempt in range(MAX_ORDER_ATTEMPTS):
            if time.time() - start_time > timeout_seconds:
                logger.warning(f"Timeout para orden {order_id}")
                return False, order_data, f"Timeout ({timeout_seconds}s)"
            
            success, order_data, msg = self.check_order_status(order_id)
            
            if not success:
                time.sleep(2)
                continue
            
            status = order_data.get("status", "")
            payment_status = order_data.get("currentPaymentStatus", "")
            fulfillment_status = order_data.get("currentFulfillmentStatus", "")
            
            if status != last_status:
                logger.info(f"Estado: {status} | Pago: {payment_status} | Fulfillment: {fulfillment_status}")
                last_status = status
            
            if callback:
                callback(attempt + 1, MAX_ORDER_ATTEMPTS, status)
            
            # Estados de FALLO
            if "Refund Completed" in status:
                return False, order_data, "Recarga cancelada y reembolsada"
            
            if payment_status == "Refunded":
                return False, order_data, "Pago reembolsado"
            
            if "Fulfillment Failed" in fulfillment_status:
                if "Refund" in status:
                    return False, order_data, "Recarga falló, siendo reembolsada"
                return False, order_data, "Recarga falló"
            
            if payment_status in ["Declined", "Failed", "Rejected"]:
                error_msg = order_data.get('pgErrorCode', 'Transacción rechazada')
                return False, order_data, f"Pago rechazado: {error_msg}"
            
            # Estados de ÉXITO
            if "Fulfillment Succeeded" in status or ("Completed" in status and "Refund" not in status):
                logger.info(f"✅ Recarga completada - Orden {order_id}")
                return True, order_data, "Recarga exitosa"
            
            if attempt < MAX_ORDER_ATTEMPTS - 1:
                time.sleep(ORDER_CHECK_INTERVAL)
        
        return False, order_data, "Timeout - Verifica el estado más tarde"
    
    def process_recharge(self, destination: str, package: Dict, callback=None) -> Tuple[bool, Dict, str]:
        """
        Procesa una recarga completa
        
        Args:
            destination: Número de destino
            package: Paquete a recargar
            callback: Función callback para actualizaciones
            
        Returns:
            Tuple (éxito, datos, mensaje)
        """
        logger.info(f"🚀 Iniciando recarga: {destination} - {package.get('name', 'N/A')}")
        
        # Crear orden
        success, order_data, msg = self.create_purchase_order(destination, package)
        
        if not success:
            return False, {}, msg
        
        order_id = order_data.get('orderId')
        if not order_id:
            return False, {}, "No se recibió ID de orden"
        
        # Esperar completación
        success, final_data, final_msg = self.wait_for_completion(order_id, callback)
        
        # Limpiar cooldown si falló
        if not success and destination in self.recent_orders:
            del self.recent_orders[destination]
        
        return success, final_data, final_msg
    
    def cleanup_old_orders(self):
        """Limpia órdenes antiguas del registro"""
        current_time = datetime.now()
        to_remove = []
        
        for destination, order_info in self.recent_orders.items():
            elapsed = (current_time - order_info['timestamp']).total_seconds()
            if elapsed > 300:
                to_remove.append(destination)
        
        for destination in to_remove:
            del self.recent_orders[destination]
