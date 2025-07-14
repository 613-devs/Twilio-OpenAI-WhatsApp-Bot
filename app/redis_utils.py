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
