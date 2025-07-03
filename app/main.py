import os
import json
import base64
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

def download_twilio_media(media_url):
    """
    Descarga media desde Twilio usando autenticación
    """
    try:
        # Usar las credenciales de Twilio para descargar el media
        response = requests.get(
            media_url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        )
        response.raise_for_status()
        return response.content
    except Exception as e:
        logger.error(f"Error downloading Twilio media: {e}")
        return None


def gpt_with_web_search(messages, user_location=None, context_size="medium"):
    """
    Función simplificada que usa gpt-4.1-mini con web search para TODO
    (texto, imágenes, audio transcrito)
    """
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
        # gpt-4.1-mini puede hacer web search según la documentación
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            web_search_options=web_search_options,
            messages=messages,
        )
        return response
    except Exception as e:
        logger.error(f"Error with gpt-4.1-mini web search: {e}")
        # Fallback sin web search
        return client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=messages,
        )


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
    logger.info(f'NumMedia: {NumMedia}, MediaUrl0: {MediaUrl0}, MediaContentType0: {MediaContentType0}')

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
    
    # Append the user's query to the chat history
    history.append({"role": 'user', "content": query})

    # Summarize the conversation history
    history_summary = summarise_conversation(history)

    # Obtener el prompt dinámico desde Google Docs
    try:
        raw_prompt = get_google_doc_content()
    except Exception as e:
        logger.error(f"Failed to fetch system prompt from Google Docs: {e}")
        raw_prompt = "You are a helpful assistant. (Default prompt used due to error.)"

    # Formatear el prompt con los datos necesarios
    system_prompt = raw_prompt.format(
        ProductName="WhatsApp Assistant",
        history_summary=history_summary,
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

    # Get a response from OpenAI's GPT model
    try:
        logger.info(f"Enviando a OpenAI: {system_prompt[:100]}... + history ({len(history)})")
        
        # Prepare messages for OpenAI - SOLO el prompt del sistema y el historial
        messages = [
            {'role': 'system', 'content': system_prompt}
        ] + history
        
        # If there's an image, modify the last user message to include image content
        if image_url:
            logger.info(f"Image URL ready for processing: {image_url[:50]}...")
            # Find the last user message in the history and update it with image content
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
                    logger.info("Image content added to message successfully")
                    break
        else:
            logger.info("No image to process, using text only")
        
        # SIEMPRE usar gpt-4.1-mini con web search para TODO (texto, imágenes, audio)
        logger.info("Using gpt-4.1-mini with web search for all content types")
        openai_response = gpt_with_web_search(
            messages=messages,
            user_location={"country": "CO", "city": "Bogotá"},
            context_size="medium"
        )
            
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

    # Append the assistant's response to the chat history on Redis
    history.append({'role': 'assistant', 'content': chatbot_response},)
    set_cookies(redis_conn, name=f'whatsapp_twilio_demo_{chat_session_id}_history', value=json.dumps(history))

    # Send the assistant's response back to the user via WhatsApp
    respond(From, chatbot_response)
    return PlainTextResponse("OK", status_code=200)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app.main:app", host='0.0.0.0', port=3002, reload=True)