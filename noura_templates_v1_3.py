# noura_templates_v1.3.py

TEMPLATES = {
    "greeting": {
        "es": """NOURA: EVIDENCE-BASED WELLBEING™

👋 Hola, soy NOURA, tu asistente de consumo consciente 🌿
Puedo ayudarte a entender el impacto real de productos en tu salud y el planeta.

📸 Envíame una foto de cualquier producto
✍️ Escribe el nombre de un producto
🎯 Pregunta por una categoría (ej: "shampoo sin sulfatos")

📍 ¿En qué país te encuentras?""",
        
        "en": """NOURA: EVIDENCE-BASED WELLBEING™

👋 Hi, I'm NOURA, your conscious consumption assistant 🌿
I help you understand the real impact of products on your health and the planet.

📸 Send me a photo of any product
✍️ Type a product name
🎯 Ask for a category (e.g., "sulfate-free shampoo")

📍 Which country are you in?""",
        
        "fr": """NOURA: EVIDENCE-BASED WELLBEING™

👋 Bonjour, je suis NOURA, ton assistant de consommation consciente 🌿
Je t'aide à comprendre l'impact réel des produits sur ta santé et la planète.

📸 Envoie-moi une photo de n'importe quel produit
✍️ Tape le nom d'un produit
🎯 Demande une catégorie (ex: "shampoing sans sulfates")

📍 Dans quel pays te trouves-tu?"""
    },
    
    "golden_format": {
        "structure": {
            "header": "NOURA: EVIDENCE-BASED WELLBEING™",
            "algorithm_version": "Algorithm v{version} ({date})",
            "product": "{product_name}",
            "overall_score": "{score}/100 {emoji}",
            "subscores": {
                "health": "🌱 Health: {score}/100 {insight}",
                "planet": "🌍 Planet: {score}/100 {insight}",
                "social": "⚖️ Social Justice: {score}/100 {insight}",
                "animal": "🐾 Animal Welfare: {score}/100 {insight}"
            },
            "alternatives_header": "💡 CLEANER ALTERNATIVES (≥85/100):",
            "alternative_item": "• {name} ({price}) ({certifications}) 🛒 {link}",
            "cta": "Reply 'More' for detailed analysis and sources",
            "filters": "🔍 Filter by: Vegan | Fragrance-free | Local | Budget"
        },
        "emojis": {
            "score_85_100": "🟢",
            "score_70_84": "🟡",
            "score_50_69": "🟠",
            "score_0_49": "🔴"
        }
    },
    
    "errors": {
        "image_unreadable": "📷 No puedo leer la etiqueta claramente. Por favor envía otra foto o escribe el nombre del producto.",
        "product_not_found": "🔍 No encontré este producto exacto. Aquí tienes 3 alternativas limpias disponibles en tu área:",
        "api_unavailable": "⚠️ Algunas fuentes no están disponibles. Usando datos en caché (última actualización: {date})",
        "out_of_scope": "Soy NOURA, tu asistente de compra consciente. No puedo responder eso, pero puedo ayudarte a encontrar productos más responsables.",
        "medical_query": "No puedo dar consejos médicos. Consulta con un profesional de la salud. ¿Quieres explorar productos de cuidado personal limpios?",
        "pii_detected": "🔒 Por tu seguridad, no puedo procesar datos personales. ¡Sigamos buscando productos!",
        "blocked_category": "Este tipo de producto está fuera de mi alcance de evaluación. ¿Puedo sugerir alternativas limpias en cuidado personal o alimentación?",
        "no_country": "Por favor, dime en qué país estás para darte mejores recomendaciones 📍",
        "generic_error": "Lo siento, ocurrió un error. Por favor intenta de nuevo."
    },
    
    "follow_ups": {
        "show_more": {
            "ingredients": """📋 ANÁLISIS DETALLADO DE INGREDIENTES:
{detailed_breakdown}

✅ Ingredientes seguros: {safe_count}
⚠️ Ingredientes cuestionables: {questionable_count}
❌ Ingredientes a evitar: {avoid_count}""",
            
            "sources": """📚 FUENTES CONSULTADAS:
{numbered_list}

Nota: Solo uso fuentes científicas verificadas y certificadoras reconocidas.""",
            
            "methodology": """🔬 METODOLOGÍA DE PUNTUACIÓN:
- Salud (35%): Basado en FDA, EFSA, EWG
- Planeta (30%): EPA, huella de carbono, certificaciones
- Justicia Social (20%): B-Corp, Fair Trade, prácticas laborales
- Bienestar Animal (15%): Leaping Bunny, PETA, políticas cruelty-free

Penalizaciones:
- Sin certificaciones: -21 puntos
- Greenwashing detectado: -15 puntos
- Ingredientes controversiales: -10 puntos"""
        },
        
        "progressive_options": [
            "¿Quieres ver más opciones?",
            "¿Diferente rango de precio?",
            "¿Filtrar por certificaciones específicas?",
            "¿Buscas algo más específico?"
        ],
        
        "filters_prompt": "¿Cómo quieres filtrar los resultados?\n• Vegano\n• Sin fragancia\n• Producción local\n• Económico (<$10)\n• Premium certificado"
    },
    
    "score_trace_log": {
        "timestamp": "{iso_timestamp}",
        "product_id": "{product_identifier}",
        "sources_used": [],
        "ingredients_detected": [],
        "certifications_found": [],
        "penalties_applied": [],
        "final_calculation": {
            "health_score": 0,
            "planet_score": 0,
            "social_score": 0,
            "animal_score": 0,
            "overall_score": 0
        },
        "algorithm_version": "{version}"
    },
    
    "category_results": {
        "header": "🎯 TOP 3 {category} LIMPIOS EN {country}:",
        "no_results": "No encontré productos limpios de {category} en {country}. ¿Quieres buscar en categorías relacionadas?",
        "item_format": """
{number}. {product_name}
   Score: {score}/100 {emoji}
   Precio: {price}
   ✓ {main_certification}
   📍 {availability}"""
    },
    
    "conversation_flows": {
        "ask_country": "¿En qué país te encuentras? Esto me ayuda a darte opciones locales y más sostenibles 🌍",
        "confirm_product": "¿Te refieres a {product_name} de {brand}?",
        "multiple_matches": "Encontré varios productos similares:\n{options}\n¿Cuál quieres analizar?",
        "session_expired": "¡Hola de nuevo! Han pasado más de 24 horas. ¿En qué puedo ayudarte hoy?",
        "thank_you": "¡Gracias por elegir consumo consciente! 🌿",
        "help_prompt": "Puedo ayudarte a:\n• Analizar productos (foto o texto)\n• Buscar alternativas limpias\n• Comparar opciones sostenibles\n¿Qué necesitas?"
    },
    
    "quick_replies": {
        "after_analysis": ["Ver más", "Otra opción", "Cambiar filtros"],
        "after_greeting": ["Analizar producto", "Ver categorías", "Ayuda"],
        "after_error": ["Intentar de nuevo", "Ayuda", "Cambiar país"]
    }
}
