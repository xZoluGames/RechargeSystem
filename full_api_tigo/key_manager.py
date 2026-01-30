#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
key_manager.py - Gestor de Claves de API
MODIFICADO v2.2:
- Vinculación de clave a Telegram ID (1 clave por usuario)
- Historial de modificaciones visibles para el usuario
- Soporte para notas administrativas con colores
- Gestión de roles (revendedor)
"""

import json
import os
import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

from config import (
    KEYS_FILE,
    KEY_MODIFICATIONS_FILE,
    RESELLERS_FILE,
    ADMIN_NOTES_PRESETS,
    DATA_DIR
)

logger = logging.getLogger(__name__)
os.makedirs(DATA_DIR, exist_ok=True)


class KeyManager:
    def __init__(self):
        self.keys_file = KEYS_FILE
        self.modifications_file = KEY_MODIFICATIONS_FILE
        self.resellers_file = RESELLERS_FILE
        self._ensure_files()
    
    def _ensure_files(self):
        for filepath in [self.keys_file, self.modifications_file, self.resellers_file]:
            if not os.path.exists(filepath):
                with open(filepath, 'w') as f:
                    json.dump({}, f)
    
    def _load_keys(self) -> Dict:
        try:
            with open(self.keys_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_keys(self, keys: Dict):
        with open(self.keys_file, 'w', encoding='utf-8') as f:
            json.dump(keys, f, ensure_ascii=False, indent=2)
    
    def _load_modifications(self) -> Dict:
        try:
            with open(self.modifications_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_modifications(self, mods: Dict):
        with open(self.modifications_file, 'w', encoding='utf-8') as f:
            json.dump(mods, f, ensure_ascii=False, indent=2)
    
    def _load_resellers(self) -> Dict:
        try:
            with open(self.resellers_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_resellers(self, resellers: Dict):
        with open(self.resellers_file, 'w', encoding='utf-8') as f:
            json.dump(resellers, f, ensure_ascii=False, indent=2)
    
    def _generate_key_string(self) -> str:
        chars = string.ascii_uppercase + string.digits
        segments = [''.join(secrets.choice(chars) for _ in range(4)) for _ in range(4)]
        return "TG-" + "-".join(segments)
    
    def _add_modification(self, key: str, mod_type: str, details: Dict, 
                         admin_note: str = None, note_preset: str = None):
        mods = self._load_modifications()
        if key not in mods:
            mods[key] = []
        
        preset_info = None
        if note_preset and note_preset in ADMIN_NOTES_PRESETS:
            preset_info = ADMIN_NOTES_PRESETS[note_preset]
        
        modification = {
            "timestamp": datetime.now().isoformat(),
            "type": mod_type,
            "details": details,
            "note_preset": note_preset,
            "preset_info": preset_info,
            "admin_note": admin_note,
            "visible_to_user": True
        }
        
        mods[key].insert(0, modification)
        mods[key] = mods[key][:100]
        self._save_modifications(mods)
    
    def generate_key(self, max_amount: int, valid_days: int = 30, 
                    description: str = "", telegram_id: int = None) -> Optional[str]:
        try:
            keys = self._load_keys()
            
            if telegram_id:
                existing_key = self.get_key_by_telegram_id(telegram_id)
                if existing_key:
                    logger.warning(f"Telegram ID {telegram_id} ya tiene clave activa")
                    return None
            
            key = self._generate_key_string()
            while key in keys:
                key = self._generate_key_string()
            
            now = datetime.now()
            expires = now + timedelta(days=valid_days)
            
            keys[key] = {
                "max_amount": max_amount,
                "used_amount": 0,
                "created": now.isoformat(),
                "expires": expires.isoformat(),
                "description": description,
                "active": True,
                "use_count": 0,
                "telegram_id": telegram_id,
                "telegram_username": None,
                "role": "USER",
                "last_used": None
            }
            
            self._save_keys(keys)
            self._add_modification(key, "CREATION", {
                "max_amount": max_amount,
                "valid_days": valid_days,
                "telegram_id": telegram_id
            }, note_preset="VINCULACION" if telegram_id else None)
            
            logger.info(f"Clave generada: {key[:8]}...")
            return key
        except Exception as e:
            logger.error(f"Error generando clave: {e}")
            return None
    
    def validate_key(self, key: str, telegram_id: int = None) -> Tuple[bool, str]:
        keys = self._load_keys()
        
        if key not in keys:
            return False, "Clave no encontrada"
        
        key_info = keys[key]
        
        if not key_info.get('active', True):
            return False, "Clave desactivada"
        
        expires = datetime.fromisoformat(key_info['expires'])
        if datetime.now() > expires:
            return False, "Clave expirada"
        
        linked_telegram = key_info.get('telegram_id')
        if linked_telegram and telegram_id:
            if linked_telegram != telegram_id:
                return False, "Esta clave está vinculada a otro usuario"
        
        remaining = key_info['max_amount'] - key_info.get('used_amount', 0)
        if remaining <= 0:
            return False, "Saldo agotado"
        
        return True, "OK"
    
    def get_key_info(self, key: str) -> Optional[Dict]:
        keys = self._load_keys()
        return keys.get(key)
    
    def get_key_by_telegram_id(self, telegram_id: int) -> Optional[str]:
        keys = self._load_keys()
        for key, info in keys.items():
            if info.get('telegram_id') == telegram_id:
                if info.get('active', True):
                    expires = datetime.fromisoformat(info['expires'])
                    if datetime.now() < expires:
                        return key
        return None
    
    def get_remaining_balance(self, key: str) -> int:
        info = self.get_key_info(key)
        if not info:
            return 0
        return info['max_amount'] - info.get('used_amount', 0)
    
    def use_amount(self, key: str, amount: int) -> bool:
        try:
            keys = self._load_keys()
            if key not in keys:
                return False
            keys[key]['used_amount'] = keys[key].get('used_amount', 0) + amount
            keys[key]['use_count'] = keys[key].get('use_count', 0) + 1
            keys[key]['last_used'] = datetime.now().isoformat()
            self._save_keys(keys)
            return True
        except Exception as e:
            logger.error(f"Error usando saldo: {e}")
            return False
    
    def modify_key(self, key: str, admin_note: str = None, note_preset: str = None, **kwargs) -> bool:
        try:
            keys = self._load_keys()
            if key not in keys:
                return False
            
            changes = {}
            
            if 'max_amount' in kwargs:
                changes['max_amount'] = {'old': keys[key]['max_amount'], 'new': kwargs['max_amount']}
                keys[key]['max_amount'] = kwargs['max_amount']
            
            if 'used_amount' in kwargs:
                changes['used_amount'] = {'old': keys[key].get('used_amount', 0), 'new': kwargs['used_amount']}
                keys[key]['used_amount'] = kwargs['used_amount']
            
            if 'valid_days' in kwargs:
                old_expires = keys[key]['expires']
                new_expires = (datetime.now() + timedelta(days=kwargs['valid_days'])).isoformat()
                changes['expires'] = {'old': old_expires, 'new': new_expires, 'days_added': kwargs['valid_days']}
                keys[key]['expires'] = new_expires
            
            if 'expires' in kwargs:
                changes['expires'] = {'old': keys[key]['expires'], 'new': kwargs['expires']}
                keys[key]['expires'] = kwargs['expires']
            
            if 'telegram_id' in kwargs:
                new_tid = kwargs['telegram_id']
                if new_tid:
                    existing = self.get_key_by_telegram_id(new_tid)
                    if existing and existing != key:
                        return False
                changes['telegram_id'] = {'old': keys[key].get('telegram_id'), 'new': new_tid}
                keys[key]['telegram_id'] = new_tid
            
            if 'telegram_username' in kwargs:
                changes['telegram_username'] = {'old': keys[key].get('telegram_username'), 'new': kwargs['telegram_username']}
                keys[key]['telegram_username'] = kwargs['telegram_username']
            
            if 'active' in kwargs:
                changes['active'] = {'old': keys[key].get('active', True), 'new': kwargs['active']}
                keys[key]['active'] = kwargs['active']
            
            if 'description' in kwargs:
                changes['description'] = {'old': keys[key].get('description', ''), 'new': kwargs['description']}
                keys[key]['description'] = kwargs['description']
            
            if 'role' in kwargs:
                changes['role'] = {'old': keys[key].get('role', 'USER'), 'new': kwargs['role']}
                keys[key]['role'] = kwargs['role']
            
            self._save_keys(keys)
            
            if changes:
                self._add_modification(key, "MODIFICATION", changes, admin_note, note_preset)
            
            return True
        except Exception as e:
            logger.error(f"Error modificando clave: {e}")
            return False
    
    def deactivate_key(self, key: str, reason: str = None) -> bool:
        return self.modify_key(key, active=False, admin_note=reason, note_preset="AJUSTE_ADMIN")
    
    def unlink_telegram(self, key: str, admin_note: str = None) -> bool:
        return self.modify_key(key, telegram_id=None, telegram_username=None, 
                              admin_note=admin_note, note_preset="DESVINCULACION")
    
    def link_telegram(self, key: str, telegram_id: int, telegram_username: str = None, admin_note: str = None) -> bool:
        return self.modify_key(key, telegram_id=telegram_id, telegram_username=telegram_username,
                              admin_note=admin_note, note_preset="VINCULACION")
    
    def add_balance(self, key: str, amount: int, admin_note: str = None) -> bool:
        info = self.get_key_info(key)
        if not info:
            return False
        return self.modify_key(key, max_amount=info['max_amount'] + amount, 
                              admin_note=admin_note, note_preset="CARGA_SALDO")
    
    def get_modifications(self, key: str, limit: int = 20) -> List[Dict]:
        mods = self._load_modifications()
        return mods.get(key, [])[:limit]
    
    def get_user_visible_modifications(self, key: str, limit: int = 10) -> List[Dict]:
        mods = self.get_modifications(key, limit * 2)
        visible = [m for m in mods if m.get('visible_to_user', True)]
        return visible[:limit]
    
    def get_all_keys(self, include_inactive: bool = False) -> List[Dict]:
        keys = self._load_keys()
        result = []
        for key, info in keys.items():
            if not include_inactive and not info.get('active', True):
                continue
            result.append({
                'key': key,
                'key_masked': key[:8] + "...",
                **info,
                'remaining': info['max_amount'] - info.get('used_amount', 0)
            })
        return result
    
    def get_keys_by_telegram_ids(self, telegram_ids: List[int]) -> List[Dict]:
        keys = self._load_keys()
        result = []
        for key, info in keys.items():
            if info.get('telegram_id') in telegram_ids and info.get('active', True):
                result.append({
                    'key_masked': key[:8] + "...",
                    'telegram_id': info.get('telegram_id'),
                    'telegram_username': info.get('telegram_username'),
                    'remaining': info['max_amount'] - info.get('used_amount', 0),
                    'used_amount': info.get('used_amount', 0),
                    'expires': info['expires'],
                    'last_used': info.get('last_used')
                })
        return result
    
    def get_stats(self) -> Dict:
        keys = self._load_keys()
        total = len(keys)
        active = sum(1 for k in keys.values() if k.get('active', True))
        expired = sum(1 for k in keys.values() if datetime.fromisoformat(k['expires']) < datetime.now())
        total_balance = sum(k['max_amount'] for k in keys.values() if k.get('active', True))
        total_used = sum(k.get('used_amount', 0) for k in keys.values())
        
        by_role = {}
        for k in keys.values():
            role = k.get('role', 'USER')
            by_role[role] = by_role.get(role, 0) + 1
        
        return {
            'total': total,
            'active': active,
            'inactive': total - active,
            'expired': expired,
            'total_balance': total_balance,
            'total_used': total_used,
            'by_role': by_role
        }
    
    # GESTIÓN DE REVENDEDORES
    def create_reseller(self, telegram_id: int, name: str, assigned_users: List[int] = None) -> bool:
        try:
            resellers = self._load_resellers()
            resellers[str(telegram_id)] = {
                "name": name,
                "telegram_id": telegram_id,
                "created": datetime.now().isoformat(),
                "active": True,
                "assigned_users": assigned_users or [],
                "stats": {"total_views": 0, "last_active": None}
            }
            self._save_resellers(resellers)
            
            key = self.get_key_by_telegram_id(telegram_id)
            if key:
                self.modify_key(key, role="RESELLER")
            
            return True
        except Exception as e:
            logger.error(f"Error creando revendedor: {e}")
            return False
    
    def get_reseller(self, telegram_id: int) -> Optional[Dict]:
        resellers = self._load_resellers()
        return resellers.get(str(telegram_id))
    
    def is_reseller(self, telegram_id: int) -> bool:
        reseller = self.get_reseller(telegram_id)
        return reseller is not None and reseller.get('active', True)
    
    def get_reseller_users(self, reseller_telegram_id: int) -> List[Dict]:
        reseller = self.get_reseller(reseller_telegram_id)
        if not reseller:
            return []
        
        assigned = reseller.get('assigned_users', [])
        if not assigned:
            return []
        
        resellers = self._load_resellers()
        resellers[str(reseller_telegram_id)]['stats']['total_views'] += 1
        resellers[str(reseller_telegram_id)]['stats']['last_active'] = datetime.now().isoformat()
        self._save_resellers(resellers)
        
        return self.get_keys_by_telegram_ids(assigned)
    
    def assign_user_to_reseller(self, reseller_telegram_id: int, user_telegram_id: int) -> bool:
        try:
            resellers = self._load_resellers()
            key = str(reseller_telegram_id)
            if key not in resellers:
                return False
            if user_telegram_id not in resellers[key]['assigned_users']:
                resellers[key]['assigned_users'].append(user_telegram_id)
                self._save_resellers(resellers)
            return True
        except:
            return False
    
    def remove_user_from_reseller(self, reseller_telegram_id: int, user_telegram_id: int) -> bool:
        try:
            resellers = self._load_resellers()
            key = str(reseller_telegram_id)
            if key not in resellers:
                return False
            if user_telegram_id in resellers[key]['assigned_users']:
                resellers[key]['assigned_users'].remove(user_telegram_id)
                self._save_resellers(resellers)
            return True
        except:
            return False
    
    def get_all_resellers(self) -> List[Dict]:
        resellers = self._load_resellers()
        return [{"telegram_id": int(k), **v} for k, v in resellers.items()]
    
    def update_reseller(self, telegram_id: int, **kwargs) -> bool:
        try:
            resellers = self._load_resellers()
            key = str(telegram_id)
            if key not in resellers:
                return False
            for field, value in kwargs.items():
                if field in resellers[key]:
                    resellers[key][field] = value
            self._save_resellers(resellers)
            return True
        except:
            return False
    
    def delete_reseller(self, telegram_id: int) -> bool:
        return self.update_reseller(telegram_id, active=False)
