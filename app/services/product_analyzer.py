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

    async def analyze(self, query: str) -> Dict:
        query = query.strip().lower()

        greetings_patterns = [
            re.compile(r'^(hi|hello|hey|hola|bonjour|salut|buenos días|buenas tardes|ayuda|help|¿qué más|que más|quiubo|¿qué me cuentas|qué me cuentas)', re.IGNORECASE)
        ]
        for pattern in greetings_patterns:
            if pattern.search(query):
                return {'found': False, 'is_greeting': True}

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
    if not analysis.get('found'):
        return None

    product = analysis['product']
    scores = analysis['scores']

    overall_score = scores.get('overall')
    if overall_score is None:
        emoji = "⚪"
    elif overall_score >= 90:
        emoji = "🟢"
    elif overall_score >= 75:
        emoji = "🟡"
    else:
        emoji = "🔴"

    confidence = "Alta Confianza"
    product_name = product.get("name", "Producto sin nombre").strip()
    brand = product.get("brand", "").strip()
    display_name = f"{product_name} de {brand}" if brand else product_name

    response = f"""NOURA: EVIDENCE-BASED WELLBEING™\n\n{emoji} {overall_score}/100 ({confidence}) {display_name}\n\n📊 Análisis Detallado:\n🧪 Salud: {scores['health']}/100\n🌱 Medioambiente: {scores['environmental']}/100\n👥 Justicia Social: {scores['social']}/100\n🐾 Bienestar Animal: {scores['animal']}/100\n"""

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
    response += "\n📊 Fuente de datos: Open Food Facts + FDA"

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
