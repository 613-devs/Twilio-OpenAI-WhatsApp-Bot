import os
import redis
from dotenv import load_dotenv

load_dotenv()

REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

redis_conn = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    password=REDIS_PASSWORD,
    db=0)
import json

def store_latest_analysis(phone_no, analysis_result):
    """Store the latest product analysis for a user"""
    redis_key = f"noura_last_analysis_{phone_no}"
    redis_conn.set(redis_key, json.dumps(analysis_result), ex=3600)  # Expires in 1 hour

def get_latest_analysis(phone_no):
    """Retrieve the latest product analysis for a user"""
    redis_key = f"noura_last_analysis_{phone_no}"
    data = redis_conn.get(redis_key)
    if data:
        return json.loads(data)
    return None
from datetime import datetime

def save_conversation_context(phone_no, user_input, bot_response):
    """Guarda el contexto de la última interacción significativa"""
    context_key = f"noura_context_{phone_no}"
    payload = {
        "last_user_input": user_input,
        "last_bot_output": bot_response,
        "timestamp": datetime.utcnow().isoformat()
    }
    redis_conn.set(context_key, json.dumps(payload), ex=1800)  # Expira en 30 min

def get_conversation_context(phone_no):
    """Recupera el contexto anterior si existe"""
    context_key = f"noura_context_{phone_no}"
    data = redis_conn.get(context_key)
    if data:
        return json.loads(data)
    return {}
