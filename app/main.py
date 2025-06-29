import os
import json
from datetime import datetime
from dotenv import load_dotenv

from fastapi import Form, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from twilio.rest import Client
import requests
import openai

from app.cookies_utils import set_cookies, get_cookies, clear_cookies
from app.prompts import get_google_doc_content
from app.openai_utils import gpt_without_functions, summarise_conversation
from app.redis_utils import redis_conn
from app.logger_utils import logger

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
    # Procesar media si existe
    if NumMedia and int(NumMedia) > 0 and MediaUrl0:
        if MediaContentType0 and MediaContentType0.startswith("audio"):
            audio_response = requests.get(MediaUrl0)
            with open("audio.ogg", "wb") as f:
                f.write(audio_response.content)
            # Aquí deberías llamar a tu función de transcripción real
            query = "[AUDIO RECIBIDO: aquí iría la transcripción]"
        elif MediaContentType0 and MediaContentType0.startswith("image"):
            query = f"[IMAGEN RECIBIDA: {MediaUrl0}]"
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
        openai_response = gpt_without_functions(
            model="gpt-4.1-mini",
            stream=False,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'assistant', 'content': "Hi there, how can I help you?"}
            ] + history)
        if not openai_response or not hasattr(openai_response, 'choices') or not openai_response.choices:
            logger.error(f"OpenAI response is invalid: {openai_response}")
            chatbot_response = "[Error: No se pudo obtener respuesta de la IA]"
        else:
            chatbot_response = openai_response.choices[0].message.content.strip()
    except Exception as e:
        logger.exception(f"Error al llamar a OpenAI: {e}")
        chatbot_response = f"[Error: Excepción en la IA: {e} - Marca oculta: 9e1b2]"

    # Append the assistant's response to the chat history on Redis
    history.append({'role': 'assistant', 'content': chatbot_response},)
    set_cookies(redis_conn, name=f'whatsapp_twilio_demo_{chat_session_id}_history', value=json.dumps(history))

    # Send the assistant's response back to the user via WhatsApp
    respond(From, chatbot_response)


def gpt_with_web_search(messages, user_location=None, context_size="medium"):
    tools = [{
        "type": "web_search_preview",
        "search_context_size": context_size,
    }]
    if user_location:
        tools[0]["user_location"] = user_location

    response = openai.responses.create(
        model="gpt-4.1-mini",  # o el modelo que soporte web_search_preview
        tools=tools,
        input=messages,
    )
    return response.output_text


if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app.main:app", host='0.0.0.0', port=3002, reload=True)