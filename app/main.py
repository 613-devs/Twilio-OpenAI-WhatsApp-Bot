import os
import json
import base64
import re
from datetime import datetime
from dotenv import load_dotenv
import warnings

from fastapi import Form, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from twilio.rest import Client
import requests
import openai

from app.cookies_utils import set_cookies, get_cookies, clear_cookies
from app.prompts import get_google_doc_content
from app.openai_utils import gpt_without_functions, summarise_conversation
from app.redis_utils import redis_conn
from app.logger_utils import logger

# Suprimir warnings de Pydantic
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Load environment variables from a .env file
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

# Validar que las variables de entorno críticas estén configuradas
if not TWILIO_ACCOUNT_SID:
    raise ValueError("TWILIO_ACCOUNT_SID environment variable is required")
if not TWILIO_AUTH_TOKEN:
    raise ValueError("TWILIO_AUTH_TOKEN environment variable is required")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

logger.info(f"Twilio Account SID configured: {TWILIO_ACCOUNT_SID[:10]}...")
logger.info(f"OpenAI API Key configured: {OPENAI_API_KEY[:10]}...")

app = FastAPI(
    title="Twilio-OpenAI-WhatsApp-Bot",
    description="Twilio OpenAI WhatsApp Bot",
    version="0.0.1",
    contact={
        "name": "Lena Shakurova",
        "url": "http://shakurova.io/",
        "email": "lena@shakurova.io",
    }
)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"]
)

def clean_twilio_urls(text):
    """
    Limpia URLs de Twilio del texto para evitar que OpenAI intente descargarlas
    """
    if not text:
        return text
    
    # Convertir a string si no lo es
    text = str(text)
    
    # Patrones más agresivos para URLs de Twilio
    patterns = [
        r'https://api\.twilio\.com/[^\s\'"]*',  # URLs completas de API de Twilio
        r'https://[^\s]*\.twilio\.com/[^\s\'"]*',  # Cualquier subdominio de Twilio
        r'https://[^\s]*\.twiliocdn\.com/[^\s\'"]*',  # URLs de media de Twilio CDN
        r'/2010-04-01/Accounts/[A-Z0-9]+/Messages/[A-Z0-9]+/Media/[A-Z0-9]+[^\s\'"]*',  # Rutas de media
        r'MM[A-Za-z0-9]{32}',  # Message SIDs que empiezan con MM
        r'ME[A-Za-z0-9]{32}',  # Media SIDs que empiezan con ME
    ]
    
    # Aplicar cada patrón
    for pattern in patterns:
        text = re.sub(pattern, '[MEDIA_CONTENT]', text, flags=re.IGNORECASE)
    
    return text

def download_twilio_media(media_url):
    """
    Descarga media desde Twilio usando autenticación
    """
    try:
        # Validar que tenemos las credenciales
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logger.error("Missing Twilio credentials: TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN")
            return None
            
        logger.info(f"Attempting to download media from: {media_url}")
        logger.info(f"Using Twilio Account SID: {TWILIO_ACCOUNT_SID[:10]}...")
        logger.info(f"Auth token length: {len(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else 'None'}")
        
        # Método 1: Usar requests con autenticación HTTP básica
        response = requests.get(
            media_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=30
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        if response.status_code == 401:
            logger.error("Authentication failed - check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
            logger.error(f"Used credentials - SID: {TWILIO_ACCOUNT_SID}, Token: {TWILIO_AUTH_TOKEN[:10] if TWILIO_AUTH_TOKEN else 'None'}...")
            return None
        elif response.status_code == 404:
            logger.error("Media not found - the URL may have expired")
            return None
        elif response.status_code == 403:
            logger.error("Access forbidden - check permissions")
            return None
            
        response.raise_for_status()
        logger.info(f"Successfully downloaded {len(response.content)} bytes")
        return response.content
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading Twilio media: {e}")
        
        # Método 2: Intentar usando el cliente de Twilio directamente
        try:
            logger.info("Trying alternative method with Twilio client...")
            twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            
            # Extraer el MediaSid de la URL
            # URL formato: https://api.twilio.com/.../Messages/{MessageSid}/Media/{MediaSid}
            url_parts = media_url.split('/')
            media_sid = url_parts[-1]
            message_sid = url_parts[-3]
            
            # Usar el cliente de Twilio para obtener la URL del media
            media = twilio_client.messages(message_sid).media(media_sid).fetch()
            media_uri = f"https://api.twilio.com{media.uri}"
            
            # Descargar usando la URI oficial
            response = requests.get(
                media_uri,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Successfully downloaded via Twilio client: {len(response.content)} bytes")
            return response.content
            
        except Exception as twilio_error:
            logger.error(f"Twilio client method also failed: {twilio_error}")
            return None
            
    except Exception as e:
        logger.error(f"Error downloading Twilio media: {e}")
        return None


def gpt_with_web_search(messages, user_location=None, context_size="medium"):
    """
    Función que usa gpt-4o-search-preview CON búsqueda web real
    Este modelo SÍ soporta imágenes + web search sin rate limits
    """
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
        # Usar gpt-4o para imágenes (sin web_search_options, solo si hay imagen)
        enhanced_messages = [
            {'role': 'system', 'content': enhanced_system_prompt}
        ] + user_messages
        # Detectar si hay imagen en los mensajes
        has_image = any(
            isinstance(m.get('content'), list) and any(i.get('type') == 'image_url' for i in m.get('content'))
            for m in enhanced_messages
        )
        if has_image:
            # No enviar web_search_options, solo messages
            response = client.chat.completions.create(
                model="gpt-4.1",  # gpt-4o soporta imágenes
                messages=enhanced_messages
            )
        else:
            # Si no hay imagen, sí enviar web_search_options
            response = client.chat.completions.create(
                model="gpt-4o-search-preview",
                web_search_options=web_search_options,
                messages=enhanced_messages
            )
        return response
    except Exception as e:
        logger.error(f"Error with gpt-4o-search-preview: {e}")
        
        # Fallback a gpt-4o sin web search pero con prompt anti-URLs falsas
        try:
            logger.info("Fallback to gpt-4o without web search")
            
            fallback_system_prompt = f"""{system_prompt}

IMPORTANTE - MODO SIN BÚSQUEDA WEB:
- NO tienes acceso a información web actualizada
- NUNCA inventes URLs, tiendas online o enlaces que no puedas verificar  
- Si no puedes verificar precios o disponibilidad, no los menciones
- Es mejor ser honesto sobre limitaciones que dar información falsa
- Usa solo tu conocimiento base sin inventar datos actuales
- Si no puedes encontrar tiendas específicas verificables, simplemente omite los enlaces"""
            
            fallback_messages = [
                {'role': 'system', 'content': fallback_system_prompt}
            ] + user_messages
            
            response = client.chat.completions.create(
                model="gpt-4.1",  # Usar gpt-4o para mejor calidad en fallback
                messages=fallback_messages,
                temperature=0.1,
                max_tokens=800,
            )
            return response
        except Exception as e2:
            logger.error(f"Fallback también falló: {e2}")
            # Re-raise para que el caller pueda manejar errores específicos
            raise


def respond(to_number, message) -> None:
    """ Send a message via Twilio WhatsApp """
    TWILIO_WHATSAPP_PHONE_NUMBER = "whatsapp:" + TWILIO_WHATSAPP_NUMBER
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    # Dividir el mensaje si es demasiado largo (WhatsApp tiene un límite de aproximadamente 1600 caracteres)
    max_length = 3000  # Por seguridad usamos un poco menos que el límite real
    
    if len(message) > max_length:
        # Dividir el mensaje en chunks
        chunks = [message[i:i+max_length] for i in range(0, len(message), max_length)]
        
        # Enviar cada chunk como un mensaje separado
        for i, chunk in enumerate(chunks):
            # Añadir indicador de part si hay múltiples mensajes
            if len(chunks) > 1:
                chunk = f"Part {i+1}/{len(chunks)}: {chunk}"
                
            twilio_client.messages.create(
                body=chunk,
                from_=TWILIO_WHATSAPP_PHONE_NUMBER,
                to=to_number
            )
    else:
        # Enviar como un solo mensaje si es lo suficientemente corto
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_PHONE_NUMBER,
            to=to_number
        )


@app.post('/whatsapp-endpoint')
async def whatsapp_endpoint(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: str = Form("0"),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None)
):
    logger.info(f'WhatsApp endpoint triggered...')
    logger.info(f'Request: {request}')
    logger.info(f'Body: {Body}')
    logger.info(f'From: {From}')
    logger.info(f'NumMedia: {NumMedia}, MediaContentType0: {MediaContentType0}')
    # No loggear MediaUrl0 para evitar que URLs sensibles aparezcan en logs que podrían ir a OpenAI
    if MediaUrl0:
        logger.info(f'MediaUrl0 received: [URL_REDACTED_FOR_SECURITY]')

    query = Body
    image_url = None
    
    # Procesar media si existe
    if NumMedia and int(NumMedia) > 0 and MediaUrl0:
        if MediaContentType0 and MediaContentType0.startswith("audio"):
            try:
                logger.info(f"Processing audio from: {MediaUrl0}")
                # Descargar el archivo de audio usando autenticación de Twilio
                audio_data = download_twilio_media(MediaUrl0)
                
                if audio_data:
                    # Guardar temporalmente el archivo
                    audio_filename = "temp_audio.ogg"
                    with open(audio_filename, "wb") as f:
                        f.write(audio_data)
                    
                    # Transcribir usando OpenAI Whisper
                    client = openai.OpenAI()
                    with open(audio_filename, "rb") as audio_file:
                        transcript = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language="es"  # Español como idioma principal
                        )
                    
                    # Usar la transcripción como query
                    query = transcript.text
                    logger.info(f"Audio transcribed: {query}")
                    
                    # Limpiar archivo temporal
                    try:
                        os.remove(audio_filename)
                    except:
                        pass
                else:
                    logger.error("Failed to download audio from Twilio")
                    query = "Lo siento, no pude descargar tu mensaje de audio."
                    
            except Exception as e:
                logger.error(f"Error processing audio: {e}")
                query = "Lo siento, no pude procesar tu mensaje de audio. Por favor, envía un mensaje de texto."
                
        elif MediaContentType0 and MediaContentType0.startswith("image"):
            try:
                logger.info(f"Processing image from: {MediaUrl0}")
                # Descargar imagen usando autenticación de Twilio
                image_data = download_twilio_media(MediaUrl0)
                
                if image_data:
                    # Convertir a base64 para uso con OpenAI
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    image_url = f"data:{MediaContentType0};base64,{image_base64}"
                    logger.info("Image converted to base64 successfully")
                else:
                    logger.error("Failed to download image from Twilio")
                    image_url = None
                    
                if not query or query.strip() == "":
                    query = "Please analyze this product image using NOURA evidence-based wellbeing analysis."
                else:
                    # Limpiar cualquier URL de Twilio del query para evitar que OpenAI intente descargarlas
                    query = clean_twilio_urls(query)
                    
            except Exception as e:
                logger.error(f"Error processing image: {e}")
                image_url = None
                if not query or query.strip() == "":
                    query = "Lo siento, no pude procesar la imagen. Por favor, describe el producto para analizarlo."
    # Si no hay texto ni media, responde con un mensaje amigable
    if not query or query.strip() == "":
        query = "Recibí tu mensaje, pero no pude procesar el contenido. Por favor envía texto, una imagen o un audio."

    phone_no = From.replace('whatsapp:+', '')
    chat_session_id = phone_no

    # Retrieve chat history from Redis
    history = get_cookies(redis_conn, f'whatsapp_twilio_demo_{chat_session_id}_history') or []
    if history:
        history = json.loads(history)
        # Limpiar URLs de Twilio del historial recuperado
        cleaned_retrieved_history = []
        for msg in history:
            cleaned_msg = msg.copy()
            if 'content' in cleaned_msg:
                cleaned_msg['content'] = clean_twilio_urls(cleaned_msg['content'])
            cleaned_retrieved_history.append(cleaned_msg)
        history = cleaned_retrieved_history
        logger.info(f"Retrieved and cleaned history with {len(history)} messages")
        
        # Limitar historial para evitar exceder el límite de tokens
        # Mantener solo los últimos 50 mensajes para evitar problemas de contexto
        if len(history) > 50:
            history = history[-50:]
            logger.info(f"Historial limitado a los últimos {len(history)} mensajes")
    
    # Limpiar URLs de Twilio del query antes de agregarlo al historial
    clean_query = clean_twilio_urls(query)
    
    # Append the user's query to the chat history
    history.append({"role": 'user', "content": clean_query})

    # Limpiar todo el historial antes de crear el summary
    fully_cleaned_history = []
    for msg in history:
        cleaned_msg = msg.copy()
        if 'content' in cleaned_msg:
            cleaned_msg['content'] = clean_twilio_urls(cleaned_msg['content'])
        fully_cleaned_history.append(cleaned_msg)
    
    # Summarize the conversation history usando el historial limpio
    history_summary = summarise_conversation(fully_cleaned_history)

    # Obtener el prompt dinámico desde Google Docs
    try:
        raw_prompt = get_google_doc_content()
    except Exception as e:
        logger.error(f"Failed to fetch system prompt from Google Docs: {e}")
        raw_prompt = "You are a helpful assistant. (Default prompt used due to error.)"

    # Formatear el prompt con los datos necesarios - limpiar URLs de Twilio del history_summary
    cleaned_history_summary = clean_twilio_urls(history_summary)
    
    system_prompt = raw_prompt.format(
        ProductName="WhatsApp Assistant",
        history_summary=cleaned_history_summary,
        today=datetime.now().date(),
        OverallIndicator="helpful and friendly",
        score="85",
        confidence="High",
        indicator="🟢",
        **{
            "key factor": "user support excellence",
            "Topic 1": "User Experience",
            "Topic 2": "Response Time",
            "Insight 1": "Quick and helpful responses",
            "Insight 2": "Available 24/7 for assistance",
            "Insight 3": "Personalized conversation experience",
            "assessment": "Excellent"
        }
    )
    
    # Limpiar URLs de Twilio del prompt del sistema también
    system_prompt = clean_twilio_urls(system_prompt)

    # Get a response from OpenAI's GPT model
    try:
        logger.info(f"Enviando a OpenAI: {system_prompt[:100]}... + history ({len(history)})")
        
        # Limpiar el historial de URLs de Twilio antes de enviarlo a OpenAI
        cleaned_history = []
        for msg in history:
            cleaned_msg = msg.copy()
            if 'content' in cleaned_msg:
                cleaned_msg['content'] = clean_twilio_urls(cleaned_msg['content'])
            cleaned_history.append(cleaned_msg)
        
        # Aplicar limpieza agresiva para evitar context window overflow
        # 1. Limitar a máximo 10 mensajes (no 20) para dar más espacio a la imagen actual
        if len(cleaned_history) > 10:
            cleaned_history = cleaned_history[-10:]
            logger.info(f"Historial limitado para OpenAI a {len(cleaned_history)} mensajes")
        
        # 2. Remover cualquier dato de imagen base64 del historial (solo mantener textos)
        for msg in cleaned_history:
            if isinstance(msg.get('content'), list):
                # Si el contenido es una lista (imagen + texto), solo mantener el texto
                text_only_content = []
                for item in msg['content']:
                    if item.get('type') == 'text':
                        text_only_content.append(item)
                # Si había imagen, reemplazar con texto descriptivo
                if len(msg['content']) > len(text_only_content):
                    text_only_content.append({
                        "type": "text", 
                        "text": "[Imagen procesada anteriormente]"
                    })
                msg['content'] = text_only_content[0]['text'] if len(text_only_content) == 1 else text_only_content
            elif isinstance(msg.get('content'), str):
                # Truncar mensajes muy largos (posiblemente base64)
                content = msg['content']
                if len(content) > 1000:
                    msg['content'] = content[:500] + "... [mensaje truncado]"
        
        logger.info(f"Historial final después de limpieza agresiva: {len(cleaned_history)} mensajes")
        
        # Prepare messages for OpenAI - SOLO el prompt del sistema y el historial limpio
        messages = [
            {'role': 'system', 'content': system_prompt}
        ] + cleaned_history
        
        # Log para debugging - verificar que no hay URLs de Twilio
        logger.info("Checking messages for Twilio URLs before sending to OpenAI...")
        for i, msg in enumerate(messages):
            content = str(msg.get('content', ''))
            if 'twilio.com' in content.lower() or 'MM' in content or 'ME' in content:
                logger.warning(f"Message {i} may contain Twilio content: {content[:100]}...")
        
        # If there's an image, modify the last user message to include image content
        if image_url:
            logger.info(f"Image URL ready for processing: {image_url[:50]}...")
            # Find the last user message in the history and update it with image content
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]['role'] == 'user':
                    # Usar el query ya limpio de URLs de Twilio
                    final_clean_query = clean_twilio_urls(query)
                    messages[i]['content'] = [
                        {
                            "type": "text",
                            "text": final_clean_query
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "high"
                            }
                        }
                    ]
                    logger.info(f"Image content added to message successfully. Text: {final_clean_query[:50]}...")
                    break
        else:
            logger.info("No image to process, using text only")
            
        # Log final para verificar el contenido que se envía a OpenAI
        logger.info("Final message check before sending to OpenAI:")
        for i, msg in enumerate(messages):
            content = msg.get('content', '')
            if isinstance(content, list):
                # Si es una lista (imagen + texto), verificar solo el texto
                for item in content:
                    if item.get('type') == 'text':
                        text_content = item.get('text', '')
                        if 'twilio.com' in text_content.lower():
                            logger.error(f"STILL CONTAINS TWILIO URL in message {i}: {text_content}")
            elif isinstance(content, str):
                if 'twilio.com' in content.lower():
                    logger.error(f"STILL CONTAINS TWILIO URL in message {i}: {content[:100]}")
                    
        logger.info("About to send to OpenAI - all URLs should be cleaned")
        
        # Usar gpt-4o-mini-search-preview CON búsqueda web controlada que respeta el prompt
        logger.info("Using gpt-4o-search-preview with REAL web search (supports images + web)")
        
        # Log token estimation before sending
        total_chars = sum(len(str(msg.get('content', ''))) for msg in messages)
        estimated_tokens = total_chars // 4  # Rough estimation: 4 chars per token
        logger.info(f"Estimated tokens before sending to OpenAI: {estimated_tokens}")
        
        try:
            openai_response = gpt_with_web_search(
                messages=messages,
                user_location={"country": "CO", "city": "Bogotá"},
                context_size="medium"
            )
        except Exception as e:
            error_str = str(e).lower()
            if 'context' in error_str and ('limit' in error_str or 'window' in error_str or 'token' in error_str):
                logger.error(f"Context window exceeded even after aggressive cleaning: {e}")
                # Further reduce history if context window is still exceeded
                if len(cleaned_history) > 5:
                    cleaned_history = cleaned_history[-5:]
                    messages = [
                        {'role': 'system', 'content': system_prompt}
                    ] + cleaned_history
                    
                    # Re-add image to last user message if exists
                    if image_url:
                        for i in range(len(messages) - 1, -1, -1):
                            if messages[i]['role'] == 'user':
                                final_clean_query = clean_twilio_urls(query)
                                messages[i]['content'] = [
                                    {
                                        "type": "text",
                                        "text": final_clean_query
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": image_url,
                                            "detail": "low"  # Use low detail to reduce tokens
                                        }
                                    }
                                ]
                                break
                    
                    logger.info(f"Retry with only {len(cleaned_history)} messages and low detail image")
                    try:
                        openai_response = gpt_with_web_search(
                            messages=messages,
                            user_location={"country": "CO", "city": "Bogotá"},
                            context_size="low"  # Usar contexto más pequeño en el retry
                        )
                    except Exception as e2:
                        logger.error(f"Still failing after aggressive reduction: {e2}")
                        openai_response = None
                else:
                    logger.error("History already minimal, cannot reduce further")
                    openai_response = None
            else:
                logger.error(f"OpenAI error (not context window): {e}")
                openai_response = None
            
        logger.info(f"Respuesta OpenAI: {openai_response}")
        if not openai_response or not hasattr(openai_response, 'choices') or not openai_response.choices:
            logger.error(f"OpenAI response is invalid: {openai_response}")
            chatbot_response = "[Error: No se pudo obtener respuesta de la IA]"
        else:
            chatbot_response = openai_response.choices[0].message.content.strip()
            logger.info(f"Respuesta IA limpia: {chatbot_response}")
    except Exception as e:
        logger.exception(f"Error al llamar a OpenAI: {e}")
        chatbot_response = f"[Error: Excepción en la IA: {e} - Marca oculta: 9e1b2]"

    # Append the assistant's response to the chat history on Redis - limpiar antes de guardar
    clean_chatbot_response = clean_twilio_urls(chatbot_response)
    history.append({'role': 'assistant', 'content': clean_chatbot_response})
    
    # Limpiar todo el historial antes de guardarlo
    cleaned_history_for_storage = []
    for msg in history:
        cleaned_msg = msg.copy()
        if 'content' in cleaned_msg:
            cleaned_msg['content'] = clean_twilio_urls(cleaned_msg['content'])
        cleaned_history_for_storage.append(cleaned_msg)
    
    set_cookies(redis_conn, name=f'whatsapp_twilio_demo_{chat_session_id}_history', value=json.dumps(cleaned_history_for_storage))

    # Send the assistant's response back to the user via WhatsApp
    respond(From, chatbot_response)
    # return PlainTextResponse("OK", status_code=200)


def validate_twilio_credentials():
    """
    Valida las credenciales de Twilio intentando crear un cliente
    """
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        # Intentar obtener información de la cuenta para validar las credenciales
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        logger.info(f"Twilio credentials validated successfully. Account: {account.friendly_name}")
        return True
    except Exception as e:
        logger.error(f"Twilio credentials validation failed: {e}")
        return False


if __name__ == '__main__':
    # Validar credenciales al inicio
    if not validate_twilio_credentials():
        logger.error("Invalid Twilio credentials. Please check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
        exit(1)
    
    import uvicorn
    uvicorn.run("app.main:app", host='0.0.0.0', port=3002, reload=True)