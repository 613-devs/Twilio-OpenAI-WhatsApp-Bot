import os
import json
import base64
import re
import tempfile
from datetime import datetime
from dotenv import load_dotenv
import warnings

from fastapi import Form, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from twilio.rest import Client
import requests
from openai import OpenAI

from app.cookies_utils import set_cookies, get_cookies, clear_cookies
from app.prompts import get_google_doc_content
from app.openai_utils import gpt_without_functions, summarise_conversation
from app.redis_utils import redis_conn
from app.logger_utils import logger
from app.services.product_analyzer import analyze_product, format_product_analysis, format_detailed_analysis
from app.services.redis_utils import get_latest_analysis, store_latest_analysis

# Suppress Pydantic warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Load environment variables from a .env file
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

# Validate critical environment variables
if not TWILIO_ACCOUNT_SID:
    raise ValueError("TWILIO_ACCOUNT_SID environment variable is required")
if not TWILIO_AUTH_TOKEN:
    raise ValueError("TWILIO_AUTH_TOKEN environment variable is required")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is required")

# Safe logging - no partial secrets
logger.info("Twilio Account SID loaded successfully")
logger.info("OpenAI API Key loaded successfully")

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


class ConversationHistory:
    """Manages conversation history with Redis storage and cleaning."""
    
    def __init__(self, redis_conn, session_id: str, max_messages: int = 50):
        self.redis_conn = redis_conn
        self.session_id = session_id
        self.max_messages = max_messages
    
    def load(self) -> list:
        """Load and clean history from Redis."""
        history = get_cookies(self.redis_conn, f'whatsapp_twilio_demo_{self.session_id}_history')
        if history:
            history = json.loads(history)
            # Clean once during load
            return [self._clean_message(msg) for msg in history[-self.max_messages:]]
        return []
    
    def save(self, history: list):
        """Save cleaned history to Redis."""
        cleaned = [self._clean_message(msg) for msg in history]
        set_cookies(
            self.redis_conn, 
            name=f'whatsapp_twilio_demo_{self.session_id}_history',
            value=json.dumps(cleaned)
        )
    
    def _clean_message(self, msg: dict) -> dict:
        """Clean Twilio URLs from a message."""
        cleaned = msg.copy()
        if 'content' in cleaned:
            cleaned['content'] = clean_twilio_urls(cleaned['content'])
        return cleaned


class UserContext:
    """Manages user context including location and preferences."""
    
    @staticmethod
    def get_user_location(phone_no: str) -> dict:
        """Get user location from Redis or return default."""
        location_data = get_cookies(redis_conn, f'user_location_{phone_no}')
        if location_data:
            return json.loads(location_data)
        # Default location - should be updated after user provides it
        return {"country": "Unknown", "city": "Unknown"}
    
    @staticmethod
    def save_user_location(phone_no: str, country: str, city: str = None):
        """Save user location to Redis."""
        location = {"country": country}
        if city:
            location["city"] = city
        set_cookies(
            redis_conn,
            name=f'user_location_{phone_no}',
            value=json.dumps(location)
        )
    
    @staticmethod
    def detect_location_from_message(message: str) -> dict:
        """Try to detect location from user message."""
        message_lower = message.lower()
        
        # Common country patterns
        locations = {
            "colombia": {"country": "CO", "city": "Bogotá"},
            "méxico": {"country": "MX", "city": "Ciudad de México"},
            "mexico": {"country": "MX", "city": "Ciudad de México"},
            "españa": {"country": "ES", "city": "Madrid"},
            "spain": {"country": "ES", "city": "Madrid"},
            "argentina": {"country": "AR", "city": "Buenos Aires"},
            "chile": {"country": "CL", "city": "Santiago"},
            "perú": {"country": "PE", "city": "Lima"},
            "peru": {"country": "PE", "city": "Lima"},
            "brasil": {"country": "BR", "city": "São Paulo"},
            "brazil": {"country": "BR", "city": "São Paulo"},
            "france": {"country": "FR", "city": "Paris"},
            "francia": {"country": "FR", "city": "Paris"},
            "usa": {"country": "US", "city": "New York"},
            "estados unidos": {"country": "US", "city": "New York"},
            "united states": {"country": "US", "city": "New York"},
        }
        
        for country_name, location_data in locations.items():
            if country_name in message_lower:
                return location_data
        
        return None


def clean_twilio_urls(text):
    """Clean URLs from Twilio to avoid OpenAI trying to download them."""
    if not text:
        return text
    
    # Convert to string if not already
    text = str(text)
    
    # Patterns for Twilio URLs
    patterns = [
        r'https://api\.twilio\.com/[^\s\'"]*',
        r'https://[^\s]*\.twilio\.com/[^\s\'"]*',
        r'https://[^\s]*\.twiliocdn\.com/[^\s\'"]*',
        r'/2010-04-01/Accounts/[A-Z0-9]+/Messages/[A-Z0-9]+/Media/[A-Z0-9]+[^\s\'"]*',
        r'MM[A-Za-z0-9]{32}',
        r'ME[A-Za-z0-9]{32}',
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '[MEDIA_CONTENT]', text, flags=re.IGNORECASE)
    
    return text


def download_twilio_media(media_url):
    """Download media from Twilio using authentication."""
    try:
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logger.error("Missing Twilio credentials")
            return None
            
        logger.info("Attempting to download media from Twilio")
        
        response = requests.get(
            media_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            timeout=30
        )
        
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 401:
            logger.error("Authentication failed - check credentials")
            return None
        elif response.status_code == 404:
            logger.error("Media not found - URL may have expired")
            return None
        elif response.status_code == 403:
            logger.error("Access forbidden - check permissions")
            return None
            
        response.raise_for_status()
        logger.info(f"Successfully downloaded {len(response.content)} bytes")
        return response.content
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error downloading Twilio media: {e}")
        return None
    except Exception as e:
        logger.error(f"Error downloading Twilio media: {e}")
        return None


def get_greeting_message(user_text: str) -> str:
    """Get appropriate greeting message based on language detection."""
    user_text_lower = user_text.strip().lower()
    
    greetings = {
        'es': {
            'triggers': ["hola", "buenos", "buenas", "qué", "que", "oye"],
            'message': """NOURA: EVIDENCE-BASED WELLBEING™

👋 Hola, soy NOURA, tu asistente de consumo consciente 🌿
Puedo ayudarte a analizar productos y compararlos según su impacto en tu bienestar integral y el del planeta.

Puedes enviarme:
📸 Una foto o escanear un producto para conocer su score
📝 Texto o voz con el nombre de un producto

📍 ¿En qué país te encuentras?
Esto me permite mostrarte opciones locales y más sostenibles."""
        },
        'fr': {
            'triggers': ["bonjour", "salut", "coucou"],
            'message': """NOURA: EVIDENCE-BASED WELLBEING™

👋 Bonjour, je suis NOURA, ton assistant de consommation consciente 🌿
Je peux t'aider à analyser des produits et les comparer selon leur impact sur ton bien-être global et celui de la planète.

Tu peux m'envoyer :
📸 Une photo ou scanner un produit pour connaître son score
📝 Un texte ou message vocal avec le nom d'un produit

📍 Dans quel pays te trouves-tu ?
Cela me permet de te montrer des options locales et plus durables."""
        },
        'en': {
            'triggers': ["hi", "hello", "hey"],
            'message': """NOURA: EVIDENCE-BASED WELLBEING™

👋 Hi, I'm NOURA, your conscious consumption assistant 🌿
I can help you analyze products and compare them based on their impact on your overall wellbeing and the planet's.

You can send me:
📸 A photo or scan of a product to get its score
📝 Text or voice with the name of a product

📍 Which country are you in?
This allows me to show you local and more sustainable options."""
        }
    }
    
    # Check triggers for each language
    for lang, config in greetings.items():
        if any(user_text_lower.startswith(trigger) for trigger in config['triggers']):
            return config['message']
    
    # Default to English if no triggers match
    return greetings['en']['message']


async def process_audio_message(media_url: str) -> str:
    """Process audio message and return transcribed text."""
    audio_data = download_twilio_media(media_url)
    if not audio_data:
        return "Lo siento, no pude descargar tu mensaje de audio."
    
    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp_file:
        tmp_file.write(audio_data)
        tmp_path = tmp_file.name
    
    try:
        # Initialize OpenAI client properly
        client = OpenAI(api_key=OPENAI_API_KEY)
        with open(tmp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
        return transcript.text
    except Exception as e:
        logger.error(f"Error transcribing audio: {e}")
        return "Lo siento, no pude transcribir tu mensaje de audio."
    finally:
        try:
            os.unlink(tmp_path)
        except OSError as e:
            logger.error(f"Error deleting temp file: {e}")


async def process_image_message(media_url: str, media_content_type: str) -> str:
    """Process image message and return base64 encoded data URL."""
    image_data = download_twilio_media(media_url)
    if not image_data:
        return None
    
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    return f"data:{media_content_type};base64,{image_base64}"


def gpt_with_web_search(messages, user_location=None, context_size="medium"):
    """Use GPT with web search capabilities."""
    # Initialize OpenAI client properly
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # Extract system prompt
    system_prompt = None
    user_messages = []
    
    for msg in messages:
        if msg['role'] == 'system':
            system_prompt = msg['content']
        else:
            user_messages.append(msg)
    
    # Enhanced system prompt
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

    # Configure web search options
    web_search_options = {
        "search_context_size": context_size,
    }
    
    if user_location and user_location.get("country") != "Unknown":
        web_search_options["user_location"] = {
            "type": "approximate",
            "approximate": user_location
        }
    
    try:
        enhanced_messages = [
            {'role': 'system', 'content': enhanced_system_prompt}
        ] + user_messages
        
        # Check if there's an image in messages
        has_image = any(
            isinstance(m.get('content'), list) and 
            any(i.get('type') == 'image_url' for i in m.get('content'))
            for m in enhanced_messages
        )
        
        if has_image:
            # Use gpt-4.1 for images without web search
            response = client.chat.completions.create(
                model="gpt-4.1",
                messages=enhanced_messages
            )
        else:
            # Use gpt-4o-search-preview with web search
            response = client.chat.completions.create(
                model="gpt-4o-search-preview",
                web_search_options=web_search_options,
                messages=enhanced_messages
            )
        return response
    except Exception as e:
        logger.error(f"Error with GPT model: {e}")
        
        # Fallback to gpt-4.1 without web search
        try:
            logger.info("Fallback to gpt-4.1 without web search")
            
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
                model="gpt-4.1",
                messages=fallback_messages,
                temperature=0.1,
                max_tokens=800,
            )
            return response
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            raise


def respond(to_number: str, message: str) -> None:
    """Send a message via Twilio WhatsApp."""
    TWILIO_WHATSAPP_PHONE_NUMBER = "whatsapp:" + TWILIO_WHATSAPP_NUMBER
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    # Split message if too long
    max_length = 3000
    
    if len(message) > max_length:
        chunks = [message[i:i+max_length] for i in range(0, len(message), max_length)]
        
        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                chunk = f"Part {i+1}/{len(chunks)}: {chunk}"
                
            twilio_client.messages.create(
                body=chunk,
                from_=TWILIO_WHATSAPP_PHONE_NUMBER,
                to=to_number
            )
    else:
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_PHONE_NUMBER,
            to=to_number
        )


def prepare_messages_for_openai(history: list, system_prompt: str, max_messages: int = 10) -> list:
    """Prepare and clean messages for OpenAI API."""
    # Limit history size
    limited_history = history[-max_messages:] if len(history) > max_messages else history
    
    # Clean history from base64 images and long content
    cleaned_history = []
    for msg in limited_history:
        cleaned_msg = msg.copy()
        
        if isinstance(msg.get('content'), list):
            # Extract only text from multimodal content
            text_content = []
            for item in msg['content']:
                if item.get('type') == 'text':
                    text_content.append(item)
            
            if text_content:
                cleaned_msg['content'] = text_content[0]['text'] if len(text_content) == 1 else text_content
            else:
                cleaned_msg['content'] = "[Imagen procesada anteriormente]"
        elif isinstance(msg.get('content'), str):
            # Truncate very long messages
            content = msg['content']
            if len(content) > 1000:
                cleaned_msg['content'] = content[:500] + "... [mensaje truncado]"
        
        cleaned_history.append(cleaned_msg)
    
    # Combine system prompt with history
    return [{'role': 'system', 'content': system_prompt}] + cleaned_history


@app.post('/whatsapp-endpoint')
async def whatsapp_endpoint(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: str = Form("0"),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None)
):
    """Main WhatsApp webhook endpoint."""
    try:
        logger.info(f'WhatsApp endpoint triggered from: {From}')
        logger.info(f'Body: {Body}')
        logger.info(f'NumMedia: {NumMedia}, MediaContentType0: {MediaContentType0}')
        
        query = Body
        image_url = None
        phone_no = From.replace('whatsapp:+', '')
        
        # Process media if exists
        if NumMedia and int(NumMedia) > 0 and MediaUrl0:
            if MediaContentType0 and MediaContentType0.startswith("audio"):
                # Process audio
                query = await process_audio_message(MediaUrl0)
                logger.info(f"Audio transcribed: {query}")
                
            elif MediaContentType0 and MediaContentType0.startswith("image"):
                # Process image
                image_url = await process_image_message(MediaUrl0, MediaContentType0)
                if image_url:
                    logger.info("Image processed successfully")
                    if not query or query.strip() == "":
                        query = "Please analyze this product image using NOURA evidence-based wellbeing analysis."
                else:
                    logger.error("Failed to process image")
                    if not query or query.strip() == "":
                        query = "Lo siento, no pude procesar la imagen. Por favor, describe el producto para analizarlo."
        
        # Default message if no content
        if not query or query.strip() == "":
            query = "Recibí tu mensaje, pero no pude procesar el contenido. Por favor envía texto, una imagen o un audio."
        
        # Clean query from Twilio URLs
        query = clean_twilio_urls(query)
        
        # Check if user is providing location info
        detected_location = UserContext.detect_location_from_message(query)
        if detected_location:
            UserContext.save_user_location(phone_no, detected_location["country"], detected_location.get("city"))
            logger.info(f"User location detected and saved: {detected_location}")
        
        # Product Analysis Check
        try:
            analysis_result = await analyze_product(query)
            
            # Check if it's a greeting
            if analysis_result.get('is_greeting'):
                greeting_msg = get_greeting_message(query)
                respond(From, greeting_msg)
                return PlainTextResponse("OK", status_code=200)
            
            # Check if user is asking "why" for previous analysis
            if query.strip().lower() in ['por qué', 'porque', 'explica', 'why']:
                last_result = get_latest_analysis(phone_no)
                if last_result and last_result.get('found'):
                    detailed_response = format_detailed_analysis(last_result)
                    respond(From, detailed_response)
                    return PlainTextResponse("OK", status_code=200)
            
            # If product was analyzed successfully
            if analysis_result.get('found'):
                product_response = format_product_analysis(analysis_result)
                store_latest_analysis(phone_no, analysis_result)
                respond(From, product_response)
                return PlainTextResponse("OK", status_code=200)
                
        except Exception as e:
            logger.error(f"Error during product analysis: {e}")
        
        # Continue with GPT processing if not handled by product analyzer
        
        # Initialize conversation history manager
        history_manager = ConversationHistory(redis_conn, phone_no)
        history = history_manager.load()
        
        # Add user message to history
        history.append({"role": 'user', "content": query})
        
        # Get system prompt from Google Docs
        try:
            raw_prompt = get_google_doc_content()
        except Exception as e:
            logger.error(f"Failed to fetch system prompt from Google Docs: {e}")
            raw_prompt = "You are a helpful assistant. (Default prompt used due to error.)"
        
        # Format system prompt
        history_summary = summarise_conversation(history)
        system_prompt = raw_prompt.format(
            ProductName="WhatsApp Assistant",
            history_summary=clean_twilio_urls(history_summary),
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
        
        system_prompt = clean_twilio_urls(system_prompt)
        
        # Prepare messages for OpenAI
        messages = prepare_messages_for_openai(history, system_prompt, max_messages=10)
        
        # Add image if present
        if image_url:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]['role'] == 'user':
                    messages[i]['content'] = [
                        {
                            "type": "text",
                            "text": query
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "high"
                            }
                        }
                    ]
                    break
        
        # Get user location for web search
        user_location = UserContext.get_user_location(phone_no)
        
        # Get response from OpenAI
        try:
            logger.info(f"Sending to OpenAI with {len(messages)} messages")
            
            openai_response = gpt_with_web_search(
                messages=messages,
                user_location=user_location,
                context_size="medium"
            )
            
            if openai_response and hasattr(openai_response, 'choices') and openai_response.choices:
                chatbot_response = openai_response.choices[0].message.content.strip()
                logger.info(f"OpenAI response received: {len(chatbot_response)} chars")
            else:
                logger.error("Invalid OpenAI response")
                chatbot_response = "Lo siento, no pude procesar tu solicitud. Por favor, intenta de nuevo."
                
        except Exception as e:
            logger.error(f"Error calling OpenAI: {e}")
            
            # Try with reduced history if token limit exceeded
            if 'context' in str(e).lower():
                try:
                    logger.info("Retrying with reduced history")
                    messages = prepare_messages_for_openai(history, system_prompt, max_messages=5)
                    
                    if image_url:
                        for i in range(len(messages) - 1, -1, -1):
                            if messages[i]['role'] == 'user':
                                messages[i]['content'] = [
                                    {"type": "text", "text": query},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": image_url,
                                            "detail": "low"
                                        }
                                    }
                                ]
                                break
                    
                    openai_response = gpt_with_web_search(
                        messages=messages,
                        user_location=user_location,
                        context_size="low"
                    )
                    
                    if openai_response and hasattr(openai_response, 'choices') and openai_response.choices:
                        chatbot_response = openai_response.choices[0].message.content.strip()
                    else:
                        chatbot_response = "Lo siento, hubo un problema con el procesamiento. Por favor, intenta de nuevo."
                        
                except Exception as e2:
                    logger.error(f"Retry failed: {e2}")
                    chatbot_response = "Lo siento, no pude procesar tu solicitud debido a limitaciones técnicas."
            else:
                chatbot_response = "Lo siento, ocurrió un error al procesar tu mensaje. Por favor, intenta de nuevo."
        
        # Add assistant response to history
        history.append({'role': 'assistant', 'content': chatbot_response})
        
        # Save updated history
        history_manager.save(history)
        
        # Send response to user
        respond(From, chatbot_response)
        
        return PlainTextResponse("OK", status_code=200)
        
    except Exception as e:
        logger.error(f"Critical error in whatsapp_endpoint: {e}", exc_info=True)
        
        # Try to send error message to user
        try:
            respond(From, "Lo siento, ocurrió un error inesperado. Por favor, intenta de nuevo más tarde.")
        except Exception as send_error:
            logger.error(f"Error sending error message to user: {send_error}")
        
        return PlainTextResponse("Error", status_code=500)


def validate_twilio_credentials():
    """Validate Twilio credentials by attempting to create a client."""
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        account = client.api.accounts(TWILIO_ACCOUNT_SID).fetch()
        logger.info(f"Twilio credentials validated successfully. Account: {account.friendly_name}")
        return True
    except Exception as e:
        logger.error(f"Twilio credentials validation failed: {e}")
        return False


if __name__ == '__main__':
    # Validate credentials at startup
    if not validate_twilio_credentials():
        logger.error("Invalid Twilio credentials. Please check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN")
        exit(1)
    
    import uvicorn
    uvicorn.run("app.main:app", host='0.0.0.0', port=3002, reload=True)
