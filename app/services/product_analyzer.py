"""
Quick integration to add real product data to your existing WhatsApp bot
This bypasses GPT hallucination for product queries
"""

import aiohttp
import asyncio
from typing import Dict, Optional
import logging
import re

logger = logging.getLogger(__name__)

class ProductAnalyzer:
    """Analyzes products using real data sources"""
    
    def __init__(self):
        self.off_base_url = "https://world.openfoodfacts.org/api/v2"
        self.fda_base_url = "https://api.fda.gov"
        
    async def analyze(self, query: str) -> Dict:
        """
        Main analysis function that coordinates all data sources
        """
        # Clean query
        query = query.strip().lower()
        
        # Check if it's a product query (not a greeting or general question)
        greetings_patterns = [
    r'^(hi|hello|hey|hola|bonjour|salut|buenos días|buenas tardes|ayuda|help|¿qué más|que más|quiubo|¿qué me cuentas|qué me cuentas)',
]
for pattern in greetings_patterns:
    if re.search(pattern, query, re.IGNORECASE):
        return {'found': False, 'is_greeting': True}
        
        # Gather data from sources
        results = await asyncio.gather(
            self._get_off_data(query),
            self._check_fda_recalls(query),
            return_exceptions=True
        )
        
        off_data, fda_data = results
        
        # If no data found, return not found
        if isinstance(off_data, Exception) or not off_data.get('found'):
            return {'found': False, 'query': query}
        
        # Calculate scores
        scores = self._calculate_scores(off_data, fda_data)
        
        return {
            'found': True,
            'product': off_data,
            'fda': fda_data if not isinstance(fda_data, Exception) else None,
            'scores': scores,
            'query': query
        }
    
    async def _get_off_data(self, query: str) -> Dict:
        """Get data from Open Food Facts"""
        async with aiohttp.ClientSession() as session:
            try:
                # Try barcode first if query is numeric
                if query.replace(' ', '').isdigit():
                    url = f"{self.off_base_url}/product/{query}.json"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('status') == 1:
                                return self._process_off_product(data['product'])
                
                # Otherwise search by name
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
        """Process Open Food Facts product data"""
        return {
            'found': True,
            'name': product.get('product_name', 'Unknown'),
            'brand': product.get('brands', ''),
            'nutriscore': product.get('nutriscore_grade', 'unknown'),
            'ecoscore': product.get('ecoscore_grade', 'unknown'),
            'nova': product.get('nova_group', 0),
            'labels': product.get('labels_tags', []),
            'is_organic': 'en:organic' in product.get('labels_tags', []),
            'is_vegan': 'en:vegan' in product.get('labels_tags', []),
            'is_palm_oil_free': product.get('ingredients_from_palm_oil_n', 0) == 0
        }
    
    async def _check_fda_recalls(self, query: str) -> Dict:
        """Check FDA for recalls"""
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
        """
        Calcula las puntuaciones de bienestar holístico, penalizando productos no limpios
        y bonificando aquellos con atributos deseables.
        """
        # Inicializar puntuaciones base
        health_score = 50
        environmental_score = 50
        social_score = 50
        animal_score = 50

        # 🔬 Salud (basado en Nutriscore y FDA)
        nutriscore = off_data.get('nutriscore', '').lower()
        nutri_mapping = {
            'a': 90, 'b': 80, 'c': 60, 'd': 40, 'e': 20
        }
        health_score = nutri_mapping.get(nutriscore, 50)

        if fda_data and fda_data.get('has_recalls'):
            health_score -= 20  # Penalización por retiro FDA

        # 🌱 Medioambiente (EcoScore, orgánico, palma)
        ecoscore = off_data.get('ecoscore', '').lower()
        eco_mapping = {
            'a': 90, 'b': 75, 'c': 60, 'd': 40, 'e': 20
        }
        environmental_score = eco_mapping.get(ecoscore, 50)

        if off_data.get('is_organic'):
            environmental_score += 10

        if not off_data.get('is_palm_oil_free'):
            environmental_score -= 15

        # 👥 Justicia social
        if off_data.get('is_fair_trade'):
            social_score += 10
        if off_data.get('brand_ethics_score'):
            try:
                score = int(off_data['brand_ethics_score'])
                social_score = max(social_score, score)
            except:
                pass

        # 🐾 Bienestar animal
        if off_data.get('is_vegan'):
            animal_score += 20
        else:
            animal_score -= 20

        # Normalizar
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

    def _generate_score_reasons(self, off_data: Dict, fda_data: Optional[Dict]) -> Dict:
        reasons = {
            'health': "Puntuación base de salud.",
            'environmental': "Puntuación base ambiental.",
            'social': "Puntuación social sin datos específicos.",
            'animal': "Puntuación animal sin datos específicos."
        }

        # Health reason
        if 'nutriscore' in off_data:
            reasons['health'] = f"Nutriscore reportado como {off_data['nutriscore'].upper()}."
        if fda_data and fda_data.get('has_recalls'):
            reasons['health'] += " Penalización por retiro del mercado (FDA recall)."

        # Environmental reason
        if off_data.get('carbon_footprint'):
            reasons['environmental'] = "Tiene datos de huella de carbono reportados."
        elif off_data.get('eco_score'):
            reasons['environmental'] = f"Eco-score reportado como {off_data['eco_score'].upper()}."

        # Social reason
        if off_data.get('is_fair_trade'):
            reasons['social'] = "Certificado de comercio justo."
        elif off_data.get('brand_ethics_score'):
            reasons['social'] = f"Marca con puntuación ética de {off_data['brand_ethics_score']}."

        # Animal reason
        if off_data.get('is_vegan'):
            reasons['animal'] = "Producto etiquetado como vegano."

        return reasons

# Singleton instance
product_analyzer = ProductAnalyzer()

    def _generate_score_reasons(self, off_data: Dict, fda_data: Optional[Dict]) -> Dict:
        reasons = {
            'health': "Puntuación base de salud.",
            'environmental': "Puntuación base ambiental.",
            'social': "Puntuación social sin datos específicos.",
            'animal': "Puntuación animal sin datos específicos."
        }

        # Health reason
        if 'nutriscore' in off_data:
            reasons['health'] = f"Nutriscore reportado como {off_data['nutriscore'].upper()}."
        if fda_data and fda_data.get('has_recalls'):
            reasons['health'] += " Penalización por retiro del mercado (FDA recall)."

        # Environmental reason
        if off_data.get('carbon_footprint'):
            reasons['environmental'] = "Tiene datos de huella de carbono reportados."
        elif off_data.get('eco_score'):
            reasons['environmental'] = f"Eco-score reportado como {off_data['eco_score'].upper()}."

        # Social reason
        if off_data.get('is_fair_trade'):
            reasons['social'] = "Certificado de comercio justo."
        elif off_data.get('brand_ethics_score'):
            reasons['social'] = f"Marca con puntuación ética de {off_data['brand_ethics_score']}."

        # Animal reason
        if off_data.get('is_vegan'):
            reasons['animal'] = "Producto etiquetado como vegano."

        return reasons

# Singleton instance
product_analyzer = ProductAnalyzer()
# Singleton instance
product_analyzer = ProductAnalyzer()

async def analyze_product(query: str) -> Dict:
    """Public function to analyze products"""
    return await product_analyzer.analyze(query)


   def format_product_analysis(analysis: Dict) -> str:
    """Format analysis results for WhatsApp"""
    
    if not analysis.get('found'):
        return None
    
    product = analysis['product']
    scores = analysis['scores']
    
    # Determine emoji based on overall score
    if scores['overall'] >= 80:
        emoji = "🟢"
        rating = "Excellent choice!"
    elif scores['overall'] >= 60:
        emoji = "🟡"
        rating = "Good option"
    elif scores['overall'] >= 40:
        emoji = "🟠"
        rating = "Consider alternatives"
    else:
        emoji = "🔴"
        rating = "Poor choice"
    
    # Build response
    response = f"""NOURA: EVIDENCE-BASED WELLBEING™

{product['name']}
Brand: {product['brand']}

{emoji} Overall Score: {scores['overall']}/100
{rating}

📊 Detailed Analysis:
🧪 Health: {scores['health']}/100
🌱 Environment: {scores['environmental']}/100
👥 Social Justice: {scores['social']}/100
🐾 Animal Welfare: {scores['animal']}/100

"""
    
    # Add key factors
    key_factors = []
    
    if product.get('nutriscore'):
        key_factors.append(f"Nutri-Score: {product['nutriscore'].upper()}")
    
    if product.get('ecoscore'):
        key_factors.append(f"Eco-Score: {product['ecoscore'].upper()}")
    
    if analysis.get('fda', {}).get('has_recalls'):
        key_factors.append("⚠️ FDA Recalls Found!")
    
    if product.get('is_vegan'):
        key_factors.append("✅ Vegan")
    
    if product.get('is_organic'):
        key_factors.append("✅ Organic")
    
    if not product.get('is_palm_oil_free'):
        key_factors.append("⚠️ Contains Palm Oil")
    
    if key_factors:
        response += "Key Factors:\n"
        for factor in key_factors[:5]:  # Limit to 5 factors
            response += f"• {factor}\n"
    
    response += "\n💡 Reply 'alternatives' for better options"
    response += "\n📊 Data: Open Food Facts + FDA"
    
    return response
    def format_clean_recommendation(score: int, confidence: str, brand: str, price: str, url: str) -> str:
    """
    Retorna una recomendación limpia, visual y con enlace embebido.
    """
    # Color visual
    if score >= 90:
        emoji = "🟢"
    elif score >= 75:
        emoji = "🟡"
    elif score >= 50:
        emoji = "🟠"
    else:
        emoji = "🔴"

    return f"{emoji} {score}/100 ({confidence}) {brand}, ~€{price} [Visit brand]({url})"
