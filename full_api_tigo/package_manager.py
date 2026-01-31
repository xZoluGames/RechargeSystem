#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
package_manager.py - Gestor de Paquetes
CORREGIDO v2.3:
- Categorización mejorada que coincide con las categorías del JSON original:
  - "Internet" / "DATOS" -> INTERNET_Y_LLAMADAS
  - "Ilimitados" -> ILIMITADOS
  - "Llamadas y SMS" / "VOZ" -> VOZ
  - "OTROS" -> OTROS
- Ordenamiento correcto de mayor a menor valor por categoría
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
        """
        Categoriza un paquete basándose en su categoría original y características.
        
        El JSON de Tigo puede venir con diferentes formatos de categoría:
        - by_category: DATOS, VOZ, OTROS
        - flat: Internet, Llamadas y SMS, Ilimitados
        
        Esta función normaliza ambos formatos.
        """
        # Primero verificar si el paquete ya tiene una categoría asignada
        original_category = package.get('category', '').upper()
        name = package.get('name', '').upper()
        description = package.get('description', '').upper()
        text = f"{name} {description}"
        
        # Mapeo de categorías originales de Tigo a nuestras categorías
        category_mapping = {
            'DATOS': 'INTERNET_Y_LLAMADAS',
            'INTERNET': 'INTERNET_Y_LLAMADAS',
            'VOZ': 'VOZ',
            'LLAMADAS Y SMS': 'VOZ',
            'LLAMADAS': 'VOZ',
            'ILIMITADOS': 'ILIMITADOS',
            'ILIMITADO': 'ILIMITADOS',
            'OTROS': 'OTROS'
        }
        
        # Si tiene una categoría original, mapearla
        if original_category in category_mapping:
            mapped = category_mapping[original_category]
            
            # Pero verificar si realmente es ilimitado por su contenido
            ilimitado_keywords = ['ILIMITAD', 'UNLIMITED', 'SIN LIMITE', 'SIN LÍMITE', 
                                   'INTERNET+MIN', 'NOCHE ILIMITADA', 'NOCHES ILIMITADAS']
            for kw in ilimitado_keywords:
                if kw in text:
                    return 'ILIMITADOS'
            
            return mapped
        
        # Si no tiene categoría o es desconocida, determinar por contenido
        
        # 1. Verificar si es Ilimitado
        ilimitado_keywords = ['ILIMITAD', 'UNLIMITED', 'SIN LIMITE', 'SIN LÍMITE', 
                               'INTERNET+MIN', 'NOCHE ILIMITADA', 'NOCHES ILIMITADAS',
                               'TODO EL DÍA', 'TODO EL DIA']
        for kw in ilimitado_keywords:
            if kw in text:
                return 'ILIMITADOS'
        
        # 2. Verificar si es Internet/Datos
        internet_keywords = ['GB', 'MB', 'INTERNET', 'DATOS', 'WHATSAPP', 'NAVEGA']
        has_internet = any(kw in text for kw in internet_keywords)
        
        # 3. Verificar si es Voz
        voz_keywords = ['MINUTOS', 'MIN ', 'LLAMADAS', 'TODO DESTINO', 'TDEST', 'TIGO']
        has_voz = any(kw in text for kw in voz_keywords)
        
        # 4. Decidir categoría
        if has_internet and has_voz:
            # Es un combo, va a Internet y Llamadas
            return 'INTERNET_Y_LLAMADAS'
        elif has_internet:
            return 'INTERNET_Y_LLAMADAS'
        elif has_voz:
            return 'VOZ'
        
        return 'OTROS'
    
    def organize_packages(self, packages: List[Dict]) -> Dict[str, Dict]:
        """
        Organiza los paquetes por categorías.
        Retorna un diccionario con estructura:
        {
            'CATEGORY_KEY': {
                'name': 'Nombre Categoría',
                'icon': '📱',
                'color': '#4CAF50',
                'packages': [...],
                'count': N
            }
        }
        """
        organized = {}
        
        # Inicializar todas las categorías en orden
        for cat_key in sorted(PACKAGE_CATEGORIES.keys(), 
                             key=lambda x: PACKAGE_CATEGORIES[x]['order']):
            organized[cat_key] = {
                'name': PACKAGE_CATEGORIES[cat_key]['name'],
                'icon': PACKAGE_CATEGORIES[cat_key]['icon'],
                'color': PACKAGE_CATEGORIES[cat_key]['color'],
                'packages': []
            }
        
        # Asignar cada paquete a su categoría
        for pkg in packages:
            category = self.categorize_package(pkg)
            if category in organized:
                organized[category]['packages'].append(pkg)
            else:
                organized['OTROS']['packages'].append(pkg)
        
        # Ordenar paquetes dentro de cada categoría (mayor a menor precio)
        for cat_key in organized:
            organized[cat_key]['packages'].sort(
                key=lambda x: x.get('amount', 0), 
                reverse=True
            )
            organized[cat_key]['count'] = len(organized[cat_key]['packages'])
        
        # Eliminar categorías vacías
        organized = {k: v for k, v in organized.items() if v['packages']}
        
        return organized
    
    def organize_packages_flat(self, packages: List[Dict]) -> List[Dict]:
        """
        Retorna una lista plana de paquetes con información de categoría añadida.
        Ordenados por categoría y luego por precio (mayor a menor).
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
        
        # Ordenar por orden de categoría y luego por precio descendente
        def sort_key(p):
            cat_order = PACKAGE_CATEGORIES.get(p['category'], {}).get('order', 99)
            return (cat_order, -p.get('amount', 0))
        
        result.sort(key=sort_key)
        return result
    
    def find_by_id(self, packages: List[Dict], package_id: str) -> Optional[Dict]:
        """Busca un paquete por su ID"""
        for pkg in packages:
            if str(pkg.get('id')) == str(package_id):
                return pkg
        return None
    
    def find_by_amount(self, packages: List[Dict], amount: int, tolerance: int = 0) -> List[Dict]:
        """Busca paquetes por monto con tolerancia opcional"""
        return [p for p in packages if abs(p.get('amount', 0) - amount) <= tolerance]
    
    def cache_packages(self, destination: str, packages: List[Dict]):
        """Guarda paquetes en cache"""
        self.cache[destination] = {
            'packages': packages, 
            'timestamp': datetime.now()
        }
    
    def get_cached(self, destination: str) -> Optional[List[Dict]]:
        """Obtiene paquetes del cache si no han expirado"""
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
        """Genera un resumen de los paquetes disponibles"""
        if not packages:
            return {
                'total': 0,
                'categories': {},
                'price_range': {'min': 0, 'max': 0}
            }
        
        organized = self.organize_packages(packages)
        
        summary = {
            'total': len(packages),
            'categories': {},
            'price_range': {
                'min': min(p.get('amount', 0) for p in packages),
                'max': max(p.get('amount', 0) for p in packages)
            }
        }
        
        for cat_key, cat_data in organized.items():
            summary['categories'][cat_key] = {
                'name': cat_data['name'],
                'count': cat_data['count'],
                'icon': cat_data['icon']
            }
        
        return summary
    
    def filter_by_category(self, packages: List[Dict], category: str) -> List[Dict]:
        """Filtra paquetes por categoría"""
        result = []
        category_upper = category.upper()
        
        for pkg in packages:
            pkg_category = self.categorize_package(pkg)
            if pkg_category == category_upper:
                result.append(pkg)
        
        return result
    
    def filter_by_price_range(self, packages: List[Dict], 
                              min_price: int = 0, 
                              max_price: int = float('inf')) -> List[Dict]:
        """Filtra paquetes por rango de precio"""
        return [
            p for p in packages 
            if min_price <= p.get('amount', 0) <= max_price
        ]
    
    def search_packages(self, packages: List[Dict], query: str) -> List[Dict]:
        """Busca paquetes por texto en nombre o descripción"""
        query_upper = query.upper()
        
        return [
            p for p in packages
            if query_upper in p.get('name', '').upper() or 
               query_upper in p.get('description', '').upper()
        ]
