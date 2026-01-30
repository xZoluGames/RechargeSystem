#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
package_manager.py - Gestión y categorización de paquetes Tigo
"""

import logging
from typing import List, Dict
from datetime import datetime

from config import PACKAGE_CATEGORIES

logger = logging.getLogger(__name__)


class PackageManager:
    """Gestiona y categoriza los paquetes de Tigo"""
    
    def __init__(self):
        self.categories = PACKAGE_CATEGORIES
        self.cache = {}  # Cache temporal por número
    
    def categorize_package(self, package: Dict) -> str:
        """Categoriza un paquete según su nombre"""
        name = package.get('name', '').upper()
        description = package.get('description', '').upper()
        combined = f"{name} {description}"
        
        for category, keywords in self.categories.items():
            for keyword in keywords:
                if keyword.upper() in combined:
                    return category
        
        return "OTROS"
    
    def organize_packages(self, packages: List[Dict]) -> Dict[str, List[Dict]]:
        """Organiza paquetes por categorías"""
        organized = {cat: [] for cat in self.categories.keys()}
        
        for package in packages:
            category = self.categorize_package(package)
            package_copy = package.copy()
            package_copy['category'] = category
            organized[category].append(package_copy)
        
        # Eliminar categorías vacías y ordenar por precio
        organized = {k: v for k, v in organized.items() if v}
        
        for category in organized:
            organized[category].sort(key=lambda x: x.get('amount', 0))
        
        return organized
    
    def filter_by_price(self, packages: List[Dict], min_price: int = 0,
                       max_price: int = float('inf')) -> List[Dict]:
        """Filtra paquetes por rango de precio"""
        return [
            p for p in packages
            if min_price <= p.get('amount', 0) <= max_price
        ]
    
    def search_packages(self, packages: List[Dict], query: str) -> List[Dict]:
        """Busca paquetes por nombre o descripción"""
        query = query.lower()
        results = []
        
        for package in packages:
            name = package.get('name', '').lower()
            desc = package.get('description', '').lower()
            
            if query in name or query in desc:
                results.append(package)
        
        return results
    
    def find_by_id(self, packages: List[Dict], package_id: str) -> Dict:
        """Busca un paquete por ID"""
        for package in packages:
            if str(package.get('id')) == str(package_id):
                return package
        return None
    
    def cache_packages(self, number: str, packages: List[Dict]):
        """Cachea paquetes para un número"""
        self.cache[number] = {
            'timestamp': datetime.now(),
            'packages': packages
        }
        
        # Limpiar cache viejo (> 30 min)
        self._cleanup_cache()
    
    def get_cached(self, number: str) -> List[Dict]:
        """Obtiene paquetes cacheados"""
        if number in self.cache:
            data = self.cache[number]
            age = (datetime.now() - data['timestamp']).total_seconds()
            
            if age < 1800:  # 30 minutos
                return data['packages']
        
        return None
    
    def _cleanup_cache(self):
        """Limpia cache viejo"""
        current = datetime.now()
        to_remove = []
        
        for number, data in self.cache.items():
            age = (current - data['timestamp']).total_seconds()
            if age > 3600:  # 1 hora
                to_remove.append(number)
        
        for number in to_remove:
            del self.cache[number]
