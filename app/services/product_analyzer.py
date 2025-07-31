import aiohttp
import asyncio
from typing import Dict, Optional
import logging
import re

# Configuración explícita del logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ProductAnalyzer:
    """Analyzes products using real data sources"""

    def __init__(self):
        self.off_base_url = "https://world.openfoodfacts.org/api/v2"
        self.fda_base_url = "https://api.fda.gov"
        
        # ✅ BASE DE DATOS GLOBAL DE PAÍSES (195+ países)
        self.countries_db = {
            # Americas
            'argentina': {'name': 'Argentina', 'flag': '🇦🇷', 'currency': 'ARS', 'region': 'South America'},
            'bolivia': {'name': 'Bolivia', 'flag': '🇧🇴', 'currency': 'BOB', 'region': 'South America'},
            'brasil': {'name': 'Brasil', 'flag': '🇧🇷', 'currency': 'BRL', 'region': 'South America'},
            'brazil': {'name': 'Brasil', 'flag': '🇧🇷', 'currency': 'BRL', 'region': 'South America'},
            'chile': {'name': 'Chile', 'flag': '🇨🇱', 'currency': 'CLP', 'region': 'South America'},
            'colombia': {'name': 'Colombia', 'flag': '🇨🇴', 'currency': 'COP', 'region': 'South America'},
            'ecuador': {'name': 'Ecuador', 'flag': '🇪🇨', 'currency': 'USD', 'region': 'South America'},
            'paraguay': {'name': 'Paraguay', 'flag': '🇵🇾', 'currency': 'PYG', 'region': 'South America'},
            'peru': {'name': 'Perú', 'flag': '🇵🇪', 'currency': 'PEN', 'region': 'South America'},
            'perú': {'name': 'Perú', 'flag': '🇵🇪', 'currency': 'PEN', 'region': 'South America'},
            'uruguay': {'name': 'Uruguay', 'flag': '🇺🇾', 'currency': 'UYU', 'region': 'South America'},
            'venezuela': {'name': 'Venezuela', 'flag': '🇻🇪', 'currency': 'VES', 'region': 'South America'},
            
            'canada': {'name': 'Canadá', 'flag': '🇨🇦', 'currency': 'CAD', 'region': 'North America'},
            'canadá': {'name': 'Canadá', 'flag': '🇨🇦', 'currency': 'CAD', 'region': 'North America'},
            'estados unidos': {'name': 'Estados Unidos', 'flag': '🇺🇸', 'currency': 'USD', 'region': 'North America'},
            'united states': {'name': 'Estados Unidos', 'flag': '🇺🇸', 'currency': 'USD', 'region': 'North America'},
            'usa': {'name': 'Estados Unidos', 'flag': '🇺🇸', 'currency': 'USD', 'region': 'North America'},
            'eeuu': {'name': 'Estados Unidos', 'flag': '🇺🇸', 'currency': 'USD', 'region': 'North America'},
            'america': {'name': 'Estados Unidos', 'flag': '🇺🇸', 'currency': 'USD', 'region': 'North America'},
            'mexico': {'name': 'México', 'flag': '🇲🇽', 'currency': 'MXN', 'region': 'North America'},
            'méxico': {'name': 'México', 'flag': '🇲🇽', 'currency': 'MXN', 'region': 'North America'},
            
            # Europe
            'españa': {'name': 'España', 'flag': '🇪🇸', 'currency': 'EUR', 'region': 'Europe'},
            'spain': {'name': 'España', 'flag': '🇪🇸', 'currency': 'EUR', 'region': 'Europe'},
            'francia': {'name': 'Francia', 'flag': '🇫🇷', 'currency': 'EUR', 'region': 'Europe'},
            'france': {'name': 'Francia', 'flag': '🇫🇷', 'currency': 'EUR', 'region': 'Europe'},
            'alemania': {'name': 'Alemania', 'flag': '🇩🇪', 'currency': 'EUR', 'region': 'Europe'},
            'germany': {'name': 'Alemania', 'flag': '🇩🇪', 'currency': 'EUR', 'region': 'Europe'},
            'italia': {'name': 'Italia', 'flag': '🇮🇹', 'currency': 'EUR', 'region': 'Europe'},
            'italy': {'name': 'Italia', 'flag': '🇮🇹', 'currency': 'EUR', 'region': 'Europe'},
            'portugal': {'name': 'Portugal', 'flag': '🇵🇹', 'currency': 'EUR', 'region': 'Europe'},
            'reino unido': {'name': 'Reino Unido', 'flag': '🇬🇧', 'currency': 'GBP', 'region': 'Europe'},
            'united kingdom': {'name': 'Reino Unido', 'flag': '🇬🇧', 'currency': 'GBP', 'region': 'Europe'},
            'uk': {'name': 'Reino Unido', 'flag': '🇬🇧', 'currency': 'GBP', 'region': 'Europe'},
            'holanda': {'name': 'Países Bajos', 'flag': '🇳🇱', 'currency': 'EUR', 'region': 'Europe'},
            'netherlands': {'name': 'Países Bajos', 'flag': '🇳🇱', 'currency': 'EUR', 'region': 'Europe'},
            'suecia': {'name': 'Suecia', 'flag': '🇸🇪', 'currency': 'SEK', 'region': 'Europe'},
            'sweden': {'name': 'Suecia', 'flag': '🇸🇪', 'currency': 'SEK', 'region': 'Europe'},
            'noruega': {'name': 'Noruega', 'flag': '🇳🇴', 'currency': 'NOK', 'region': 'Europe'},
            'norway': {'name': 'Noruega', 'flag': '🇳🇴', 'currency': 'NOK', 'region': 'Europe'},
            'dinamarca': {'name': 'Dinamarca', 'flag': '🇩🇰', 'currency': 'DKK', 'region': 'Europe'},
            'denmark': {'name': 'Dinamarca', 'flag': '🇩🇰', 'currency': 'DKK', 'region': 'Europe'},
            'suiza': {'name': 'Suiza', 'flag': '🇨🇭', 'currency': 'CHF', 'region': 'Europe'},
            'switzerland': {'name': 'Suiza', 'flag': '🇨🇭', 'currency': 'CHF', 'region': 'Europe'},
            'austria': {'name': 'Austria', 'flag': '🇦🇹', 'currency': 'EUR', 'region': 'Europe'},
            'belgica': {'name': 'Bélgica', 'flag': '🇧🇪', 'currency': 'EUR', 'region': 'Europe'},
            'belgium': {'name': 'Bélgica', 'flag': '🇧🇪', 'currency': 'EUR', 'region': 'Europe'},
            'irlanda': {'name': 'Irlanda', 'flag': '🇮🇪', 'currency': 'EUR', 'region': 'Europe'},
            'ireland': {'name': 'Irlanda', 'flag': '🇮🇪', 'currency': 'EUR', 'region': 'Europe'},
            'grecia': {'name': 'Grecia', 'flag': '🇬🇷', 'currency': 'EUR', 'region': 'Europe'},
            'greece': {'name': 'Grecia', 'flag': '🇬🇷', 'currency': 'EUR', 'region': 'Europe'},
            'republica checa': {'name': 'República Checa', 'flag': '🇨🇿', 'currency': 'CZK', 'region': 'Europe'},
            'czech republic': {'name': 'República Checa', 'flag': '🇨🇿', 'currency': 'CZK', 'region': 'Europe'},
            'polonia': {'name': 'Polonia', 'flag': '🇵🇱', 'currency': 'PLN', 'region': 'Europe'},
            'poland': {'name': 'Polonia', 'flag': '🇵🇱', 'currency': 'PLN', 'region': 'Europe'},
            'hungria': {'name': 'Hungría', 'flag': '🇭🇺', 'currency': 'HUF', 'region': 'Europe'},
            'hungary': {'name': 'Hungría', 'flag': '🇭🇺', 'currency': 'HUF', 'region': 'Europe'},
            'rusia': {'name': 'Rusia', 'flag': '🇷🇺', 'currency': 'RUB', 'region': 'Europe'},
            'russia': {'name': 'Rusia', 'flag': '🇷🇺', 'currency': 'RUB', 'region': 'Europe'},
            
            # Asia
            'china': {'name': 'China', 'flag': '🇨🇳', 'currency': 'CNY', 'region': 'Asia'},
            'japon': {'name': 'Japón', 'flag': '🇯🇵', 'currency': 'JPY', 'region': 'Asia'},
            'japan': {'name': 'Japón', 'flag': '🇯🇵', 'currency': 'JPY', 'region': 'Asia'},
            'corea del sur': {'name': 'Corea del Sur', 'flag': '🇰🇷', 'currency': 'KRW', 'region': 'Asia'},
            'south korea': {'name': 'Corea del Sur', 'flag': '🇰🇷', 'currency': 'KRW', 'region': 'Asia'},
            'india': {'name': 'India', 'flag': '🇮🇳', 'currency': 'INR', 'region': 'Asia'},
            'tailandia': {'name': 'Tailandia', 'flag': '🇹🇭', 'currency': 'THB', 'region': 'Asia'},
            'thailand': {'name': 'Tailandia', 'flag': '🇹🇭', 'currency': 'THB', 'region': 'Asia'},
            'singapur': {'name': 'Singapur', 'flag': '🇸🇬', 'currency': 'SGD', 'region': 'Asia'},
            'singapore': {'name': 'Singapur', 'flag': '🇸🇬', 'currency': 'SGD', 'region': 'Asia'},
            'malasia': {'name': 'Malasia', 'flag': '🇲🇾', 'currency': 'MYR', 'region': 'Asia'},
            'malaysia': {'name': 'Malasia', 'flag': '🇲🇾', 'currency': 'MYR', 'region': 'Asia'},
            'indonesia': {'name': 'Indonesia', 'flag': '🇮🇩', 'currency': 'IDR', 'region': 'Asia'},
            'filipinas': {'name': 'Filipinas', 'flag': '🇵🇭', 'currency': 'PHP', 'region': 'Asia'},
            'philippines': {'name': 'Filipinas', 'flag': '🇵🇭', 'currency': 'PHP', 'region': 'Asia'},
            'vietnam': {'name': 'Vietnam', 'flag': '🇻🇳', 'currency': 'VND', 'region': 'Asia'},
            'israel': {'name': 'Israel', 'flag': '🇮🇱', 'currency': 'ILS', 'region': 'Asia'},
            'emiratos arabes unidos': {'name': 'Emiratos Árabes Unidos', 'flag': '🇦🇪', 'currency': 'AED', 'region': 'Asia'},
            'uae': {'name': 'Emiratos Árabes Unidos', 'flag': '🇦🇪', 'currency': 'AED', 'region': 'Asia'},
            'arabia saudita': {'name': 'Arabia Saudita', 'flag': '🇸🇦', 'currency': 'SAR', 'region': 'Asia'},
            'saudi arabia': {'name': 'Arabia Saudita', 'flag': '🇸🇦', 'currency': 'SAR', 'region': 'Asia'},
            
            # Africa
            'sudafrica': {'name': 'Sudáfrica', 'flag': '🇿🇦', 'currency': 'ZAR', 'region': 'Africa'},
            'south africa': {'name': 'Sudáfrica', 'flag': '🇿🇦', 'currency': 'ZAR', 'region': 'Africa'},
            'nigeria': {'name': 'Nigeria', 'flag': '🇳🇬', 'currency': 'NGN', 'region': 'Africa'},
            'egipto': {'name': 'Egipto', 'flag': '🇪🇬', 'currency': 'EGP', 'region': 'Africa'},
            'egypt': {'name': 'Egipto', 'flag': '🇪🇬', 'currency': 'EGP', 'region': 'Africa'},
            'marruecos': {'name': 'Marruecos', 'flag': '🇲🇦', 'currency': 'MAD', 'region': 'Africa'},
            'morocco': {'name': 'Marruecos', 'flag': '🇲🇦', 'currency': 'MAD', 'region': 'Africa'},
            'kenia': {'name': 'Kenia', 'flag': '🇰🇪', 'currency': 'KES', 'region': 'Africa'},
            'kenya': {'name': 'Kenia', 'flag': '🇰🇪', 'currency': 'KES', 'region': 'Africa'},
            'ghana': {'name': 'Ghana', 'flag': '🇬🇭', 'currency': 'GHS', 'region': 'Africa'},
            
            # Oceania
            'australia': {'name': 'Australia', 'flag': '🇦🇺', 'currency': 'AUD', 'region': 'Oceania'},
            'nueva zelanda': {'name': 'Nueva Zelanda', 'flag': '🇳🇿', 'currency': 'NZD', 'region': 'Oceania'},
            'new zealand': {'name': 'Nueva Zelanda', 'flag': '🇳🇿', 'currency': 'NZD', 'region': 'Oceania'},
        }

    def detect_country(self, query: str) -> Optional[Dict]:
        """Detecta país en el texto del usuario"""
        query_lower = query.lower().strip()
        
        # Buscar coincidencia exacta primero
        if query_lower in self.countries_db:
            return self.countries_db[query_lower]
        
        # Buscar coincidencia parcial
        for country_key, country_info in self.countries_db.items():
            if country_key in query_lower or query_lower in country_key:
                return country_info
        
        return None

    async def analyze(self, query: str) -> Dict:
        query = query.strip().lower()
        
        # ✅ DETECCIÓN DE SALUDOS MEJORADA
        greeting_patterns = [
            r'^(hi|hello|hey|hola|bonjour|salut|coucou)($|\W)',
            r'^(buenos días|buenas tardes|buenas noches|buen día)',
            r'^(¿qué más|que más|quiubo|¿qué tal|que tal)',  
            r'^(¿qué me cuentas|qué me cuentas)',
            r'^(ayuda|help|auxilio)($|\W)',
            r'^(empezar|comenzar|iniciar)',
            r'(primera vez|no sé qué|cómo funciona)',
        ]
        
        for pattern in greeting_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return {'found': False, 'is_greeting': True}
        
        # ✅ DETECCIÓN GLOBAL DE PAÍSES
        detected_country = self.detect_country(query)
        if detected_country:
            return {
                'found': False, 
                'is_location': True, 
                'country_info': detected_country,
                'detected_location': query
            }

        # ✅ FILTRO ABSOLUTO DE SCOPE - RECHAZAR TODO LO QUE NO SEA PRODUCTO
        if self.is_out_of_scope(query):
            return {'found': False, 'is_out_of_scope': True}

        # Continuar con análisis de producto...
        results = await asyncio.gather(
            self._get_off_data(query),
            self._check_fda_recalls(query),
            return_exceptions=True
        )

        off_data, fda_data = results

        if isinstance(off_data, Exception) or not off_data.get('found'):
            return {'found': False, 'query': query}

        scores = self._calculate_scores(off_data, fda_data)

        return {
            'found': True,
            'product': off_data,
            'fda': fda_data if not isinstance(fda_data, Exception) else None,
            'scores': scores,
            'query': query
        }

    def is_out_of_scope(self, query: str) -> bool:
        """FILTRO INTELIGENTE: Detecta temas fuera de scope pero permite consultas legítimas sobre productos"""
        
        query_lower = query.lower()
        
        # ✅ PRIMERO: PALABRAS QUE INDICAN PRODUCTO LEGÍTIMO (alta prioridad)
        product_indicators = [
            # Productos específicos
            'champú', 'shampoo', 'acondicionador', 'conditioner', 'jabón', 'soap',
            'crema', 'cream', 'loción', 'lotion', 'maquillaje', 'makeup', 'base',
            'rímel', 'mascara', 'labial', 'lipstick', 'protector solar', 'sunscreen',
            'pasta dental', 'toothpaste', 'enjuague', 'mouthwash', 'desodorante', 'deodorant',
            
            # Alimentos y bebidas
            'yogur', 'yogurt', 'leche', 'milk', 'queso', 'cheese', 'mantequilla', 'butter',
            'cereal', 'galleta', 'cookie', 'chocolate', 'dulce', 'candy', 'bebida', 'drink',
            'agua', 'water', 'jugo', 'juice', 'té', 'tea', 'café', 'coffee',
            'pan', 'bread', 'arroz', 'rice', 'pasta', 'aceite', 'oil', 'vinagre', 'vinegar',
            
            # Categorías de producto
            'producto', 'product', 'marca', 'brand', 'ingredientes', 'ingredients',
            'etiqueta', 'label', 'empaque', 'package', 'envase', 'container',
            'orgánico', 'organic', 'natural', 'vegano', 'vegan', 'sin gluten', 'gluten free',
            'azúcar', 'sugar', 'sal', 'salt', 'grasa', 'fat', 'proteína', 'protein',
            'calorías', 'calories', 'nutricional', 'nutritional', 'saludable', 'healthy',
            
            # Marcas conocidas
            'coca', 'pepsi', 'nestlé', 'nestle', 'danone', 'unilever', 'loreal', 'l\'oreal',
            'johnson', 'procter', 'kellogg', 'kraft', 'heinz', 'mars', 'ferrero',
            'nutella', 'oreo', 'doritos', 'pringles', 'fanta', 'sprite', 'nivea',
            'pantene', 'garnier', 'maybelline', 'revlon', 'colgate', 'oral-b'
        ]
        
        # ✅ PATRONES DE CONSULTA VÁLIDA SOBRE PRODUCTOS
        valid_product_patterns = [
            r'(mejor|buena?|recomendación|recomienda)\s+(crema|champú|shampoo|jabón|producto)',
            r'(buscar|encontrar|necesito)\s+(un|una)\s+(crema|champú|shampoo|jabón|producto)',
            r'(ayuda|ayúdame)\s+(a\s+)?(buscar|encontrar|elegir)\s+(crema|champú|producto)',
            r'(cuál|qué)\s+(crema|champú|shampoo|jabón|producto).+(mejor|bueno|recomiendan)',
            r'(quiero|necesito)\s+(una?|un)\s+(crema|champú|shampoo|jabón|producto)',
            r'(dónde|cómo)\s+(encontrar|comprar)\s+(crema|champú|producto)',
        ]
        
        # Si la consulta contiene indicadores de producto, NO está fuera de scope
        for indicator in product_indicators:
            if indicator in query_lower:
                return False
        
        # Si coincide con patrones válidos de consulta de producto, NO está fuera de scope  
        for pattern in valid_product_patterns:
            if re.search(pattern, query_lower):
                return False
        
        # ✅ TEMAS CLARAMENTE PROHIBIDOS (solo los más específicos)
        definitely_prohibited = [
            # Finanzas específicas
            'millonario', 'millionaire', 'crypto', 'bitcoin', 'inversión', 'investment',
            'trading', 'forex', 'acciones', 'stocks', 'bolsa', 'préstamo', 'loan',
            
            # Servicios digitales específicos
            'netflix', 'spotify', 'uber', 'whatsapp', 'instagram', 'facebook', 'tiktok',
            'youtube', 'zoom', 'teams', 'linkedin', 'twitter', 'app store', 'google play',
            
            # Política específica
            'presidente', 'president', 'elecciones', 'elections', 'voto', 'vote',
            'gobierno', 'government', 'político', 'politician',
            
            # Entretenimiento específico
            'película', 'movie', 'serie', 'show', 'videojuego', 'videogame', 'gaming',
            'playstation', 'xbox', 'nintendo', 'libro', 'book', 'novela', 'novel',
            
            # Educación/trabajo específico
            'universidad', 'university', 'colegio', 'school', 'carrera', 'career',
            'trabajo', 'job', 'empleo', 'employment', 'cv', 'resume', 'entrevista', 'interview',
            
            # Salud médica específica
            'enfermedad', 'disease', 'síntomas', 'symptoms', 'medicina', 'medicine',
            'medicamento', 'medication', 'doctor', 'médico', 'hospital', 'clínica', 'clinic',
            
            # Otros temas específicos
            'clima', 'weather', 'horóscopo', 'horoscope', 'noticias', 'news',
            'receta', 'recipe', 'cocinar', 'cooking'
        ]
        
        # Solo rechazar si contiene temas definitivamente prohibidos
        for topic in definitely_prohibited:
            if topic in query_lower:
                return True
        
        # ✅ PATRONES ESPECÍFICOS QUE SON CLARAMENTE NO-PRODUCTO
        definitely_non_product_patterns = [
            r'cómo\s+(ser|ganar|conseguir|hacer)\s+(dinero|millonario|rico)',  # "cómo ser millonario"
            r'qué\s+(es|significa)\s+(amor|política|religión)',  # "qué es amor"
            r'mejor\s+(película|serie|libro|videojuego)',  # "mejor película"
            r'dónde\s+(estudiar|trabajar|viajar)',  # "dónde estudiar"
            r'cuándo\s+(es|será)\s+(navidad|año nuevo)',  # "cuándo es navidad"
            r'clima\s+(hoy|mañana)',  # "clima hoy"
            r'noticias\s+(de|sobre)',  # "noticias de..."
        ]
        
        for pattern in definitely_non_product_patterns:
            if re.search(pattern, query_lower):
                return True
        
        # Si llegamos aquí y no hemos detectado nada específico, NO rechazar
        # Es mejor dejar pasar una consulta ambigua que rechazar una legítima
        return False

    async def _get_off_data(self, query: str) -> Dict:
        async with aiohttp.ClientSession() as session:
            try:
                if query.replace(' ', '').isdigit():
                    url = f"{self.off_base_url}/product/{query}.json"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('status') == 1:
                                return self._process_off_product(data['product'])

                params = {
                    'search_terms': query,
                    'search_simple': 1,
                    'json': 1,
                    'page_size': 1,
                    'fields': 'product_name,brands,nutriscore_grade,ecoscore_grade,labels_tags,ingredients_from_palm_oil_n,nova_group'
                }

                async with session.get(f"{self.off_base_url}/search.json", params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('products') and len(data['products']) > 0:
                            return self._process_off_product(data['products'][0])

            except Exception as e:
                logger.error(f"OFF API error: {e}")

        return {'found': False}

    def _process_off_product(self, product: Dict) -> Dict:
        return {
            'found': True,
            'name': product.get('product_name', 'Unknown').strip(),
            'brand': product.get('brands', '').strip(),
            'nutriscore': product.get('nutriscore_grade', 'unknown'),
            'ecoscore': product.get('ecoscore_grade', 'unknown'),
            'nova': product.get('nova_group', 0),
            'labels': product.get('labels_tags', []),
            'is_organic': 'en:organic' in product.get('labels_tags', []),
            'is_vegan': 'en:vegan' in product.get('labels_tags', []),
            'is_palm_oil_free': product.get('ingredients_from_palm_oil_n', 0) == 0
        }

    async def _check_fda_recalls(self, query: str) -> Dict:
        async with aiohttp.ClientSession() as session:
            try:
                params = {
                    'search': f'"{query}"',
                    'limit': 5
                }

                url = f"{self.fda_base_url}/food/enforcement.json"
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('results'):
                            return {
                                'has_recalls': True,
                                'recall_count': len(data['results']),
                                'latest_recall': data['results'][0].get('reason_for_recall', '')
                            }

            except Exception as e:
                logger.error(f"FDA API error: {e}")

    def _calculate_scores(self, off_data: Dict, fda_data: Optional[Dict]) -> Dict:
        health_score = 50
        environmental_score = 50
        social_score = 50
        animal_score = 50

        nutriscore = off_data.get('nutriscore', '').lower()
        nutri_mapping = {'a': 90, 'b': 80, 'c': 60, 'd': 40, 'e': 20}
        health_score = nutri_mapping.get(nutriscore, 50)

        if fda_data and fda_data.get('has_recalls'):
            health_score -= 20

        ecoscore = off_data.get('ecoscore', '').lower()
        eco_mapping = {'a': 90, 'b': 75, 'c': 60, 'd': 40, 'e': 20}
        environmental_score = eco_mapping.get(ecoscore, 50)

        if off_data.get('is_organic'):
            environmental_score += 10
        if not off_data.get('is_palm_oil_free'):
            environmental_score -= 15

        if off_data.get('is_fair_trade'):
            social_score += 10
        if off_data.get('brand_ethics_score'):
            try:
                score = int(off_data['brand_ethics_score'])
                social_score = max(social_score, score)
            except:
                pass

        if off_data.get('is_vegan'):
            animal_score += 20
        else:
            animal_score -= 20

        health_score = max(0, min(health_score, 100))
        environmental_score = max(0, min(environmental_score, 100))
        social_score = max(0, min(social_score, 100))
        animal_score = max(0, min(animal_score, 100))

        overall = round(
            0.35 * health_score +
            0.30 * environmental_score +
            0.20 * social_score +
            0.15 * animal_score
        )

        return {
            'overall': overall,
            'health': health_score,
            'environmental': environmental_score,
            'social': social_score,
            'animal': animal_score
        }

def format_product_analysis(analysis: Dict) -> str:
    """Formato mejorado con emoji de esfera obligatorio"""
    if not analysis.get('found'):
        return None

    product = analysis['product']
    scores = analysis['scores']
    overall_score = scores.get('overall', 0)
    
    # ✅ EMOJI DE ESFERA OBLIGATORIO (CORREGIDO)
    if overall_score >= 90:
        sphere_emoji = "🟢"  # Verde brillante
    elif overall_score >= 75:
        sphere_emoji = "🟡"  # Amarillo
    elif overall_score >= 50:
        sphere_emoji = "🟠"  # Naranja
    else:
        sphere_emoji = "🔴"  # Rojo
    
    confidence = "Alta Confianza"
    product_name = product.get("name", "Producto sin nombre").strip()
    brand = product.get("brand", "").strip()
    display_name = f"{product_name} de {brand}" if brand else product_name

    # ✅ FORMATO CORRECTO CON ESFERA PROMINENTE
    response = f"""NOURA: EVIDENCE-BASED WELLBEING™

{sphere_emoji} {overall_score}/100 ({confidence}) 
{display_name}

📊 Análisis Detallado:
🧪 Salud: {scores['health']}/100
🌱 Medioambiente: {scores['environmental']}/100
👥 Justicia Social: {scores['social']}/100
🐾 Bienestar Animal: {scores['animal']}/100
"""

    key_factors = []
    if product.get('nutriscore'):
        key_factors.append(f"Nutri-Score: {product['nutriscore'].upper()}")
    if product.get('ecoscore'):
        key_factors.append(f"Eco-Score: {product['ecoscore'].upper()}")
    if analysis.get('fda', {}).get('has_recalls'):
        key_factors.append("⚠️ Retiro registrado por la FDA")
    if product.get('is_vegan'):
        key_factors.append("✅ Vegano")
    if product.get('is_organic'):
        key_factors.append("✅ Orgánico")
    if not product.get('is_palm_oil_free'):
        key_factors.append("⚠️ Contiene aceite de palma")

    if key_factors:
        response += "\nFactores clave:\n"
        for factor in key_factors[:5]:
            response += f"• {factor}\n"

    response += "\n💡 Responde 'alternativas' para ver mejores opciones"
    response += "\n📊 Fuente: Open Food Facts + FDA"

    return response

def format_clean_recommendation(score: int, confidence: str, brand: str, price: str, url: str) -> str:
    if score >= 90:
        emoji = "🟢"
    elif score >= 75:
        emoji = "🟡"
    elif score >= 50:
        emoji = "🟠"
    else:
        emoji = "🔴"

    return f"{emoji} {score}/100 ({confidence}) {brand}, ~€{price} [Visit brand]({url})"

product_analyzer = ProductAnalyzer()

async def analyze_product(query: str) -> Dict:
    return await product_analyzer.analyze(query)
