#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
key_manager.py - Gestión de claves de API
Versión simplificada para API REST pura
"""

import json
import random
import string
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
import os

from config import KEYS_FILE, DATA_DIR

logger = logging.getLogger(__name__)


class KeyManager:
    """Gestiona las claves de API"""
    
    def __init__(self, keys_file: str = None):
        self.keys_file = keys_file or KEYS_FILE
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Crea el archivo si no existe"""
        os.makedirs(os.path.dirname(self.keys_file), exist_ok=True)
        
        if not os.path.exists(self.keys_file):
            with open(self.keys_file, 'w') as f:
                json.dump({}, f)
    
    def load_keys(self) -> Dict:
        """Carga todas las claves"""
        try:
            with open(self.keys_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._ensure_file_exists()
            return {}
    
    def save_keys(self, keys: Dict) -> bool:
        """Guarda las claves"""
        try:
            with open(self.keys_file, 'w') as f:
                json.dump(keys, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error guardando claves: {e}")
            return False
    
    def generate_key(self, max_amount: int, valid_days: int = 30,
                    description: str = "") -> Optional[str]:
        """
        Genera una nueva clave
        
        Args:
            max_amount: Monto máximo permitido
            valid_days: Días de validez
            description: Descripción opcional
            
        Returns:
            La clave generada o None
        """
        try:
            key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
            keys = self.load_keys()
            
            while key in keys:
                key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
            
            keys[key] = {
                'created': datetime.now().isoformat(),
                'expires': (datetime.now() + timedelta(days=valid_days)).isoformat(),
                'max_amount': max_amount,
                'used_amount': 0,
                'active': True,
                'use_count': 0,
                'description': description,
                'last_used': None
            }
            
            if self.save_keys(keys):
                logger.info(f"Clave generada: {key[:8]}... - Monto: {max_amount}")
                return key
            return None
            
        except Exception as e:
            logger.error(f"Error generando clave: {e}")
            return None
    
    def validate_key(self, key: str, amount: int = 0) -> Tuple[bool, str]:
        """
        Valida una clave
        
        Args:
            key: Clave a validar
            amount: Monto a verificar (opcional)
            
        Returns:
            Tuple (es_válida, mensaje)
        """
        keys = self.load_keys()
        
        if key not in keys:
            return False, "Clave inválida"
        
        key_data = keys[key]
        
        if not key_data.get('active', True):
            return False, "Clave desactivada"
        
        try:
            expires = datetime.fromisoformat(key_data['expires'])
            if datetime.now() > expires:
                return False, "Clave expirada"
        except:
            return False, "Error en fecha de expiración"
        
        remaining = key_data['max_amount'] - key_data.get('used_amount', 0)
        
        if remaining <= 0:
            return False, "Clave sin saldo"
        
        if amount > 0 and amount > remaining:
            return False, f"Saldo insuficiente. Disponible: Gs. {remaining:,}"
        
        return True, f"OK - Saldo disponible: Gs. {remaining:,}"
    
    def use_amount(self, key: str, amount: int) -> bool:
        """Registra uso de un monto"""
        try:
            keys = self.load_keys()
            
            if key not in keys:
                return False
            
            keys[key]['used_amount'] = keys[key].get('used_amount', 0) + amount
            keys[key]['last_used'] = datetime.now().isoformat()
            keys[key]['use_count'] = keys[key].get('use_count', 0) + 1
            
            return self.save_keys(keys)
            
        except Exception as e:
            logger.error(f"Error actualizando uso: {e}")
            return False
    
    def get_key_info(self, key: str) -> Optional[Dict]:
        """Obtiene información de una clave"""
        keys = self.load_keys()
        
        if key not in keys:
            return None
        
        key_data = keys[key].copy()
        key_data['remaining'] = key_data['max_amount'] - key_data.get('used_amount', 0)
        
        return key_data
    
    def get_remaining_balance(self, key: str) -> int:
        """Obtiene saldo restante"""
        key_info = self.get_key_info(key)
        if key_info:
            return key_info['remaining']
        return 0
    
    def deactivate_key(self, key: str, reason: str = "") -> bool:
        """Desactiva una clave"""
        try:
            keys = self.load_keys()
            if key in keys:
                keys[key]['active'] = False
                keys[key]['deactivated_at'] = datetime.now().isoformat()
                keys[key]['deactivation_reason'] = reason
                return self.save_keys(keys)
            return False
        except Exception as e:
            logger.error(f"Error desactivando clave: {e}")
            return False
    
    def activate_key(self, key: str) -> bool:
        """Activa una clave"""
        try:
            keys = self.load_keys()
            if key in keys:
                keys[key]['active'] = True
                keys[key]['reactivated_at'] = datetime.now().isoformat()
                return self.save_keys(keys)
            return False
        except Exception as e:
            logger.error(f"Error activando clave: {e}")
            return False
    
    def modify_key(self, key: str, **kwargs) -> bool:
        """
        Modifica una clave
        
        Args:
            key: Clave a modificar
            **kwargs: Campos a modificar (max_amount, valid_days, etc.)
        """
        try:
            keys = self.load_keys()
            
            if key not in keys:
                return False
            
            if 'max_amount' in kwargs:
                keys[key]['max_amount'] = kwargs['max_amount']
            
            if 'used_amount' in kwargs:
                keys[key]['used_amount'] = kwargs['used_amount']
            
            if 'valid_days' in kwargs:
                keys[key]['expires'] = (datetime.now() + timedelta(days=kwargs['valid_days'])).isoformat()
            
            if 'description' in kwargs:
                keys[key]['description'] = kwargs['description']
            
            keys[key]['modified_at'] = datetime.now().isoformat()
            
            return self.save_keys(keys)
            
        except Exception as e:
            logger.error(f"Error modificando clave: {e}")
            return False
    
    def get_all_keys(self, include_inactive: bool = False) -> List[Dict]:
        """Obtiene todas las claves"""
        keys = self.load_keys()
        result = []
        
        for key, data in keys.items():
            if not include_inactive and not data.get('active', True):
                continue
            
            info = data.copy()
            info['key'] = key
            info['remaining'] = data['max_amount'] - data.get('used_amount', 0)
            
            # Verificar expiración
            try:
                expires = datetime.fromisoformat(data['expires'])
                info['expired'] = datetime.now() > expires
            except:
                info['expired'] = True
            
            result.append(info)
        
        return result
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas de claves"""
        keys = self.load_keys()
        
        total = len(keys)
        active = 0
        expired = 0
        total_balance = 0
        used_balance = 0
        
        for key, data in keys.items():
            if data.get('active', True):
                try:
                    expires = datetime.fromisoformat(data['expires'])
                    if datetime.now() <= expires:
                        active += 1
                    else:
                        expired += 1
                except:
                    expired += 1
            
            total_balance += data.get('max_amount', 0)
            used_balance += data.get('used_amount', 0)
        
        return {
            'total_keys': total,
            'active_keys': active,
            'expired_keys': expired,
            'total_balance': total_balance,
            'used_balance': used_balance,
            'available_balance': total_balance - used_balance
        }
