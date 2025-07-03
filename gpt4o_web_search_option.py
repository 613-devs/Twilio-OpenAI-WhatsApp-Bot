# Opción para usar gpt-4o con búsqueda web real
def gpt_with_real_web_search(messages, user_location=None, context_size="medium"):
    """
    Función que usa gpt-4o con búsqueda web REAL
    """
    import openai
    
    client = openai.OpenAI()
    
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
        # gpt-4o SÍ soporta web search
        response = client.chat.completions.create(
            model="gpt-4o",  # Cambiar a gpt-4o
            web_search_options=web_search_options,
            messages=messages,
            temperature=0.1,
            max_tokens=800,
        )
        return response
    except Exception as e:
        logger.error(f"Error with gpt-4o web search: {e}")
        # Fallback sin web search
        return client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.1,
            max_tokens=800,
        )
