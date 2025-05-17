import os
import json
from datetime import datetime
from dotenv import load_dotenv

from fastapi import Form, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from twilio.rest import Client

from app.cookies_utils import set_cookies, get_cookies, clear_cookies
from app.prompts import SYSTEM_PROMPT
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

    # Si el mensaje es demasiado largo (más de 2000 caracteres), dividirlo
    if len(message) > 2000:
        chunks = [message[i:i+2000] for i in range(0, len(message), 2000)]
        for chunk in chunks:
            twilio_client.messages.create(
                body=chunk,
                from_=TWILIO_WHATSAPP_PHONE_NUMBER,
                to=to_number
            )
    else:
        # Enviar el mensaje completo si es lo suficientemente corto
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_PHONE_NUMBER,
            to=to_number
        )


@app.post('/whatsapp-endpoint')
async def whatsapp_endpoint(request: Request, From: str = Form(...), Body: str = Form(...)):
    logger.info(f'WhatsApp endpoint triggered...')
    logger.info(f'Request: {request}')
    logger.info(f'Body: {Body}')
    logger.info(f'From: {From}')

    query = Body
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

    # Format the system prompt with the conversation summary and current date
    system_prompt = SYSTEM_PROMPT.format(
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
    openai_response = gpt_without_functions(
                        model="gpt-4.1-mini",
                        stream=False,
                        messages=[
                            {'role': 'system', 'content': system_prompt}, 
                            {'role': 'assistant', 'content': "Hi there, how can I help you?"}
                        ] + history)
    chatbot_response = openai_response.choices[0].message.content.strip()

    # Append the assistant's response to the chat history on Redis
    history.append({'role': 'assistant', 'content': chatbot_response},)
    set_cookies(redis_conn, name=f'whatsapp_twilio_demo_{chat_session_id}_history', value=json.dumps(history))

    # Send the assistant's response back to the user via WhatsApp
    respond(From, chatbot_response)


if __name__ == '__main__':
    import uvicorn
    uvicorn.run("app.main:app", host='0.0.0.0', port=3002, reload=True)