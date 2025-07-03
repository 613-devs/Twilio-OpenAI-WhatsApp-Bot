# Twilio-OpenAI-WhatsApp-Bot/app/openai_utils.py

import os 
from dotenv import load_dotenv
from litellm import completion
from app.prompts import SUMMARY_PROMPT
import logging

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

# IF YOU WANT TO ADD MORE MODELS
# GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
# AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
# REGION_NAME = os.getenv("REGION_NAME")

# os.environ['GROQ_API_KEY'] = GROQ_API_KEY
# os.environ["AWS_ACCESS_KEY_ID"] = AWS_ACCESS_KEY_ID
# os.environ["AWS_SECRET_ACCESS_KEY"] = AWS_SECRET_ACCESS_KEY
# os.environ["AWS_REGION_NAME"] = REGION_NAME

# Constants
TEMPERATURE = 0.1
MAX_TOKENS = 350
STOP_SEQUENCES = ["==="]
TOP_P = 1
TOP_K = 1
BEST_OF = 1
FREQUENCY_PENALTY = 0
PRESENCE_PENALTY = 0


SUPPORTED_MODELS = {
    # Groq Llama models
    "groq/llama3-8b-8192", 
    "groq/llama-3.1-8b-instant", 
    "groq/llama-3.1-70b-versatile", 
    # OpenAI models
    "gpt-3.5-turbo-0125",
    "gpt-4o", 
    "gpt-4o-mini",
    "gpt-4-0125-preview",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    # Amazon Anthropic models
    "bedrock/anthropic.claude-3-sonnet-20240229-v1:0",
    "bedrock/anthropic.claude-3-opus-20240229-v1:0",
    "bedrock/anthropic.claude-v2:1",
    }


def gpt_without_functions(model, stream=False, messages=[]):
    """ GPT model without function call. """
    if model not in SUPPORTED_MODELS:
        return False
    response = completion(
        model=model, 
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        top_p=TOP_P,
        frequency_penalty=FREQUENCY_PENALTY,
        presence_penalty=PRESENCE_PENALTY,
        stream=stream
    )
    return response 



def summarise_conversation(history):
    """Summarise conversation history in one sentence"""
    import re

    def clean_twilio_urls(text):
        """Limpia URLs de Twilio del texto"""
        if not text:
            return text
        
        text = str(text)
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

    conversation = ""
    for item in history[-70:]:
        # Usar el formato correcto de role/content
        if item.get('role') == 'user':
            content = clean_twilio_urls(item.get('content', ''))
            conversation += f"User: {content}\n"
        elif item.get('role') == 'assistant':
            content = clean_twilio_urls(item.get('content', ''))
            conversation += f"Bot: {content}\n"
        
        # Mantener compatibilidad con formato antiguo si existe
        if 'user_input' in item:
            content = clean_twilio_urls(item['user_input'])
            conversation += f"User: {content}\n"
        if 'bot_response' in item:
            content = clean_twilio_urls(item['bot_response'])
            conversation += f"Bot: {content}\n"

    # Si no hay conversación, retornar un summary genérico
    if not conversation.strip():
        return "Nueva conversación iniciada"

    openai_response = gpt_without_functions(
                        model="gpt-4.1-mini",
                        stream=False,
                        messages=[
                            {'role': 'system', 'content': SUMMARY_PROMPT}, 
                            {'role': 'user', 'content': conversation}
                    ])
    chatbot_response = openai_response.choices[0].message.content.strip()

    return chatbot_response


def gpt_with_web_search(messages, stream=False):
    """ GPT model with web search capability. """
    model = "gpt-4.1-mini"  # Specify the model you want to use
    if model not in SUPPORTED_MODELS:
        logging.error(f"Model {model} not supported.")
        return "[Error: Modelo no soportado]"
    try:
        response = completion(
            model=model, 
            messages=messages,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            top_p=TOP_P,
            frequency_penalty=FREQUENCY_PENALTY,
            presence_penalty=PRESENCE_PENALTY,
            stream=stream
        )
        # Manejo robusto de la respuesta
        if hasattr(response, 'choices') and response.choices:
            content = getattr(response.choices[0].message, 'content', None)
            if content:
                return content.strip()
            else:
                logging.error("La respuesta de OpenAI no contiene contenido.")
                return "[Error: No se recibió contenido de la IA]"
        else:
            logging.error(f"Respuesta inesperada de OpenAI: {response}")
            return "[Error: Respuesta inesperada de la IA]"
    except Exception as e:
        logging.exception(f"Error al llamar a OpenAI: {e}")
        return "[Error: No se pudo obtener respuesta de la IA]"


def handle_conversation_with_search(history, system_prompt):
    """Handle conversation with web search capability."""
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'assistant', 'content': "Hi there, how can I help you?"}
    ] + history

    # Si quieres usar búsqueda web:
    chatbot_response = gpt_with_web_search(messages)

    return chatbot_response
