#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
package_manager.py - Gestor de Paquetes
MODIFICADO v2.2:
- Categorías: Internet y Llamadas, Ilimitados, Voz, Otros
- Ordenamiento de mayor a menor valor
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

from config import PACKAGE_CATEGORIES

logger = logging.getLogger(__name__)


class PackageManager:
    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300
    
    def categorize_package(self, package: Dict) -> str:
        name = package.get('name', '').upper()
        description = package.get('description', '').upper()
        text = f"{name} {description}"
        
        # Ilimitados primero
        for kw in PACKAGE_CATEGORIES['ILIMITADOS']['keywords']:
            if kw.upper() in text:
                return 'ILIMITADOS'
        
        # Internet y Llamadas
        has_internet = any(kw.upper() in text for kw in ['INTERNET', 'DATOS', 'MB', 'GB'])
        has_calls = any(kw.upper() in text for kw in ['MINUTOS', 'LLAMADAS', 'COMBO'])
        
        if has_internet or (has_internet and has_calls):
            return 'INTERNET_Y_LLAMADAS'
        
        if has_calls and not has_internet:
            return 'VOZ'
        
        return 'OTROS'
    
    def organize_packages(self, packages: List[Dict]) -> Dict[str, List[Dict]]:
        organized = {}
        
        for cat_key in sorted(PACKAGE_CATEGORIES.keys(), 
                             key=lambda x: PACKAGE_CATEGORIES[x]['order']):
            organized[cat_key] = {
                'name': PACKAGE_CATEGORIES[cat_key]['name'],
                'icon': PACKAGE_CATEGORIES[cat_key]['icon'],
                'color': PACKAGE_CATEGORIES[cat_key]['color'],
                'packages': []
            }
        
        for pkg in packages:
            category = self.categorize_package(pkg)
            organized[category]['packages'].append(pkg)
        
        for cat_key in organized:
            organized[cat_key]['packages'].sort(key=lambda x: x.get('amount', 0), reverse=True)
            organized[cat_key]['count'] = len(organized[cat_key]['packages'])
        
        organized = {k: v for k, v in organized.items() if v['packages']}
        return organized
    
    def organize_packages_flat(self, packages: List[Dict]) -> List[Dict]:
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
        
        def sort_key(p):
            cat_order = PACKAGE_CATEGORIES.get(p['category'], {}).get('order', 99)
            return (cat_order, -p.get('amount', 0))
        
        result.sort(key=sort_key)
        return result
    
    def find_by_id(self, packages: List[Dict], package_id: str) -> Optional[Dict]:
        for pkg in packages:
            if pkg.get('id') == package_id:
                return pkg
        return None
    
    def find_by_amount(self, packages: List[Dict], amount: int, tolerance: int = 0) -> List[Dict]:
        return [p for p in packages if abs(p.get('amount', 0) - amount) <= tolerance]
    
    def cache_packages(self, destination: str, packages: List[Dict]):
        self.cache[destination] = {'packages': packages, 'timestamp': datetime.now()}
    
    def get_cached(self, destination: str) -> Optional[List[Dict]]:
        if destination not in self.cache:
            return None
        cached = self.cache[destination]
        age = (datetime.now() - cached['timestamp']).total_seconds()
        if age > self.cache_ttl:
            del self.cache[destination]
            return None
        return cached['packages']
    
    def clear_cache(self, destination: str = None):
        if destination:
            self.cache.pop(destination, None)
        else:
            self.cache.clear()
    
    def get_summary(self, packages: List[Dict]) -> Dict:
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
