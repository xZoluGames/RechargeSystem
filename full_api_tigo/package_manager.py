#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
package_manager.py - Gestor de Paquetes
MODIFICADO:
- Categorías mejoradas: Internet y Llamadas, Ilimitados, Voz, Otros
- Ordenamiento de mayor a menor valor
- Mejor detección de categorías
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from config import PACKAGE_CATEGORIES

logger = logging.getLogger(__name__)


class PackageManager:
    """Gestor de paquetes con categorización mejorada"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5 minutos
    
    def categorize_package(self, package: Dict) -> str:
        """
        Determina la categoría de un paquete
        
        Returns:
            Clave de categoría (INTERNET_Y_LLAMADAS, ILIMITADOS, VOZ, OTROS)
        """
        name = package.get('name', '').upper()
        description = package.get('description', '').upper()
        text = f"{name} {description}"
        
        # Verificar Ilimitados primero (tienen prioridad)
        ilimitado_keywords = PACKAGE_CATEGORIES['ILIMITADOS']['keywords']
        for kw in ilimitado_keywords:
            if kw.upper() in text:
                return 'ILIMITADOS'
        
        # Verificar Internet y Llamadas (combos)
        internet_keywords = PACKAGE_CATEGORIES['INTERNET_Y_LLAMADAS']['keywords']
        has_internet = any(kw.upper() in text for kw in ['INTERNET', 'DATOS', 'MB', 'GB'])
        has_calls = any(kw.upper() in text for kw in ['MINUTOS', 'LLAMADAS', 'COMBO'])
        
        if has_internet or (has_internet and has_calls):
            return 'INTERNET_Y_LLAMADAS'
        
        # Verificar solo Voz
        if has_calls and not has_internet:
            return 'VOZ'
        
        # Otros
        return 'OTROS'
    
    def organize_packages(self, packages: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Organiza paquetes por categorías, ordenados de mayor a menor precio
        
        Args:
            packages: Lista de paquetes
            
        Returns:
            Dict con categorías como clave y lista de paquetes ordenados
        """
        organized = {}
        
        # Inicializar categorías en orden
        for cat_key in sorted(PACKAGE_CATEGORIES.keys(), 
                             key=lambda x: PACKAGE_CATEGORIES[x]['order']):
            organized[cat_key] = {
                'name': PACKAGE_CATEGORIES[cat_key]['name'],
                'icon': PACKAGE_CATEGORIES[cat_key]['icon'],
                'color': PACKAGE_CATEGORIES[cat_key]['color'],
                'packages': []
            }
        
        # Categorizar cada paquete
        for pkg in packages:
            category = self.categorize_package(pkg)
            organized[category]['packages'].append(pkg)
        
        # Ordenar cada categoría de mayor a menor precio
        for cat_key in organized:
            organized[cat_key]['packages'].sort(
                key=lambda x: x.get('amount', 0),
                reverse=True  # Mayor a menor
            )
            organized[cat_key]['count'] = len(organized[cat_key]['packages'])
        
        # Remover categorías vacías
        organized = {k: v for k, v in organized.items() if v['packages']}
        
        return organized
    
    def organize_packages_flat(self, packages: List[Dict]) -> List[Dict]:
        """
        Organiza paquetes con categoría incluida, ordenados
        
        Returns:
            Lista de paquetes con campo 'category' agregado
        """
        result = []
        
        for pkg in packages:
            category = self.categorize_package(pkg)
            cat_info = PACKAGE_CATEGORIES.get(category, PACKAGE_CATEGORIES['OTROS'])
            
            pkg_with_cat = {
                **pkg,
                'category': category,
                'category_name': cat_info['name'],
                'category_icon': cat_info['icon'],
                'category_color': cat_info['color']
            }
            result.append(pkg_with_cat)
        
        # Ordenar: primero por orden de categoría, luego por precio descendente
        def sort_key(p):
            cat_order = PACKAGE_CATEGORIES.get(p['category'], {}).get('order', 99)
            return (cat_order, -p.get('amount', 0))
        
        result.sort(key=sort_key)
        
        return result
    
    def find_by_id(self, packages: List[Dict], package_id: str) -> Optional[Dict]:
        """Busca un paquete por ID"""
        for pkg in packages:
            if pkg.get('id') == package_id:
                return pkg
        return None
    
    def find_by_amount(self, packages: List[Dict], amount: int, 
                       tolerance: int = 0) -> List[Dict]:
        """Busca paquetes por monto (con tolerancia opcional)"""
        result = []
        for pkg in packages:
            pkg_amount = pkg.get('amount', 0)
            if abs(pkg_amount - amount) <= tolerance:
                result.append(pkg)
        return result
    
    def cache_packages(self, destination: str, packages: List[Dict]):
        """Cachea paquetes para un destino"""
        self.cache[destination] = {
            'packages': packages,
            'timestamp': datetime.now()
        }
    
    def get_cached(self, destination: str) -> Optional[List[Dict]]:
        """Obtiene paquetes cacheados si aún son válidos"""
        if destination not in self.cache:
            return None
        
        cached = self.cache[destination]
        age = (datetime.now() - cached['timestamp']).total_seconds()
        
        if age > self.cache_ttl:
            del self.cache[destination]
            return None
        
        return cached['packages']
    
    def clear_cache(self, destination: str = None):
        """Limpia el cache"""
        if destination:
            self.cache.pop(destination, None)
        else:
            self.cache.clear()
    
    def get_summary(self, packages: List[Dict]) -> Dict:
        """Obtiene resumen de paquetes disponibles"""
        organized = self.organize_packages(packages)
        
        summary = {
            'total': len(packages),
            'categories': {},
            'price_range': {
                'min': min(p.get('amount', 0) for p in packages) if packages else 0,
                'max': max(p.get('amount', 0) for p in packages) if packages else 0
            }
        }
        
        for cat_key, cat_data in organized.items():
            summary['categories'][cat_key] = {
                'name': cat_data['name'],
                'count': cat_data['count'],
                'icon': cat_data['icon']
            }
        
        return summary
    
    def filter_by_price_range(self, packages: List[Dict], 
                              min_price: int = 0, 
                              max_price: int = float('inf')) -> List[Dict]:
        """Filtra paquetes por rango de precio"""
        return [
            p for p in packages
            if min_price <= p.get('amount', 0) <= max_price
        ]
    
    def filter_by_category(self, packages: List[Dict], 
                          categories: List[str]) -> List[Dict]:
        """Filtra paquetes por categorías"""
        result = []
        for pkg in packages:
            cat = self.categorize_package(pkg)
            if cat in categories:
                result.append(pkg)
        return result
    
    def search_packages(self, packages: List[Dict], query: str) -> List[Dict]:
        """Busca paquetes por texto"""
        query = query.upper()
        result = []
        
        for pkg in packages:
            name = pkg.get('name', '').upper()
            desc = pkg.get('description', '').upper()
            
            if query in name or query in desc:
                result.append(pkg)
        
        return result
