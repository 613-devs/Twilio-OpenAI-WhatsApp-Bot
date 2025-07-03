# Opción para usar gpt-4o-search-preview con búsqueda web real y soporte para imágenes
def gpt_with_real_web_search(messages, user_location=None, context_size="medium"):
    """
    Función que usa gpt-4o-search-preview con búsqueda web REAL
    Este modelo SÍ soporta imágenes + web search sin rate limits
    """
    import openai
    import logging
    
    client = openai.OpenAI()
    
    # Extraer el prompt del sistema para preservarlo
    system_prompt = None
    user_messages = []
    
    for msg in messages:
        if msg['role'] == 'system':
            system_prompt = msg['content']
        else:
            user_messages.append(msg)
    
    # Crear prompt reforzado que evite URLs falsas
    enhanced_system_prompt = f"""{system_prompt}

INSTRUCCIONES CRÍTICAS PARA BÚSQUEDA WEB:
- Siempre sigue las instrucciones del sistema anterior al pie de la letra
- Usa la información web SOLO para complementar, no para contradecir el prompt
- Mantén el formato, tono y estilo especificado en el prompt del sistema
- La búsqueda web debe ENRIQUECER tu respuesta, no cambiar tu comportamiento base

PROHIBIDO TERMINANTEMENTE:
- NUNCA inventes URLs ficticias como "example.com" o sitios que no existen
- NUNCA uses enlaces placeholder como [Comprar aquí](https://www.example.com)
- Si no encuentras URLs reales verificables, simplemente omite los enlaces
- Es mejor NO dar enlace que dar un enlace falso
- Solo incluye URLs que hayas encontrado mediante búsqueda web real
- Si no puedes verificar una tienda online específica, no la menciones"""

    # Configurar opciones de web search
    web_search_options = {
        "search_context_size": context_size,
    }
    
    if user_location:
        web_search_options["user_location"] = {
            "type": "approximate",
            "approximate": user_location
        }
    
    try:
        # gpt-4o-search-preview SÍ soporta web search + imágenes
        enhanced_messages = [
            {'role': 'system', 'content': enhanced_system_prompt}
        ] + user_messages
        
        response = client.chat.completions.create(
            model="gpt-4o-search-preview",  # Modelo más robusto que soporta imágenes
            web_search_options=web_search_options,
            messages=enhanced_messages,
            temperature=0.1,
            max_tokens=800,
        )
        return response
    except Exception as e:
        logging.error(f"Error with gpt-4o-search-preview web search: {e}")
        
        # Fallback a gpt-4o sin web search pero con prompt anti-URLs falsas
        try:
            fallback_system_prompt = f"""{system_prompt}

IMPORTANTE - MODO SIN BÚSQUEDA WEB:
- NO tienes acceso a información web actualizada
- NUNCA inventes URLs, tiendas online o enlaces que no puedas verificar  
- Si no puedes verificar precios o disponibilidad, no los menciones
- Es mejor ser honesto sobre limitaciones que dar información falsa
- Usa solo tu conocimiento base sin inventar datos actuales"""
            
            fallback_messages = [
                {'role': 'system', 'content': fallback_system_prompt}
            ] + user_messages
            
            return client.chat.completions.create(
                model="gpt-4o",
                messages=fallback_messages,
                temperature=0.1,
                max_tokens=800,
            )
        except Exception as e2:
            logging.error(f"Fallback también falló: {e2}")
            raise
