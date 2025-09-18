import os
import json
import base64
import re
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
from dotenv import load_dotenv
import warnings

from fastapi import Form, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from twilio.rest import Client
import requests
from openai import OpenAI

# Import existing utilities from same directory
from cookies_utils import set_cookies, get_cookies, clear_cookies
from prompts import get_google_doc_content
from openai_utils import gpt_without_functions, summarise_conversation
from redis_utils import redis_conn
from logger_utils import logger

# Import from services subdirectory
from services.product_analyzer import analyze_product, format_product_analysis, format_detailed_analysis
from services.redis_utils import get_latest_analysis, store_latest_analysis

# Import new modular components from same directory
from noura_core_v1_3 import NOURA_CORE
from noura_templates_v1_3 import TEMPLATES
from noura_state_machine_v1_3 import STATE_MACHINE

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

load_dotenv()

# Environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

# Validate critical environment variables
if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, OPENAI_API_KEY]):
    raise ValueError("Missing critical environment variables")

logger.info("All credentials loaded successfully")

app = FastAPI(
    title="NOURA-WhatsApp-Bot",
    description="NOURA Evidence-Based Wellbeing Assistant",
    version=NOURA_CORE["version"],
    contact={
        "name": "NOURA Team",
        "url": "https://noura.ai",
        "email": "hello@noura.ai",
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


class NOURASession:
    """Manages NOURA conversation state and context"""
    
    def __init__(self, phone_no: str):
        self.phone_no = phone_no
        self.session_key = f'noura_session_{phone_no}'
        self.state_key = f'noura_state_{phone_no}'
        self.trace_key = f'noura_trace_{phone_no}'
        self.load_state()
    
    def load_state(self):
        """Load current state from Redis"""
        state_data = redis_conn.get(self.state_key)
        if state_data:
            state_info = json.loads(state_data)
            self.current_state = state_info.get('state', 'INIT')
            self.last_activity = datetime.fromisoformat(state_info.get('last_activity', datetime.now().isoformat()))
            
            # Check for 24h timeout
            if datetime.now() - self.last_activity > timedelta(hours=24):
                self.current_state = 'INIT'
        else:
            self.current_state = 'INIT'
            self.last_activity = datetime.now()
    
    def save_state(self, new_state: str):
        """Save state to Redis with timestamp"""
        state_info = {
            'state': new_state,
            'last_activity': datetime.now().isoformat(),
            'algorithm_version': NOURA_CORE['version']
        }
        redis_conn.setex(
            self.state_key,
            86400 * 7,  # 7 days expiry
            json.dumps(state_info)
        )
        self.current_state = new_state
    
    def get_country(self) -> Optional[str]:
        """Get stored country for user"""
        country_data = redis_conn.get(f'user_location_{self.phone_no}')
        if country_data:
            return json.loads(country_data).get('country')
        return None
    
    def save_country(self, country: str, city: Optional[str] = None):
        """Save user location"""
        location = {'country': country}
        if city:
            location['city'] = city
        redis_conn.setex(
            f'user_location_{self.phone_no}',
            86400 * 7,  # 7 days as per NOURA_CORE
            json.dumps(location)
        )
    
    def log_trace(self, action: str, data: Dict):
        """Log scoring trace for audit"""
        trace = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'data': data,
            'algorithm_version': NOURA_CORE['version']
        }
        # Store in Redis list for audit trail
        redis_conn.lpush(self.trace_key, json.dumps(trace))
        redis_conn.expire(self.trace_key, 86400 * 30)  # 30 days retention


class NOURAProcessor:
    """Core NOURA logic processor"""
    
    def __init__(self, session: NOURASession):
        self.session = session
        self.core = NOURA_CORE
        self.templates = TEMPLATES
        self.state_machine = STATE_MACHINE
        
    def detect_language(self, text: str) -> str:
        """Detect user language"""
        text_lower = text.lower()
        if any(word in text_lower for word in ['hola', 'gracias', 'buenos', 'qué']):
            return 'es'
        elif any(word in text_lower for word in ['bonjour', 'merci', 'salut']):
            return 'fr'
        else:
            return 'en'
    
    def detect_intent(self, text: str) -> Tuple[str, Dict]:
        """Detect user intent and extract entities"""
        text_lower = text.lower().strip()
        
        # Check for greetings
        greeting_triggers = ['hola', 'hi', 'hello', 'bonjour', 'buenos', 'hey']
        if any(text_lower.startswith(trigger) for trigger in greeting_triggers):
            return 'greeting', {'language': self.detect_language(text)}
        
        # Check for country
        countries = {
            'colombia': 'CO', 'méxico': 'MX', 'mexico': 'MX',
            'españa': 'ES', 'spain': 'ES', 'argentina': 'AR',
            'chile': 'CL', 'perú': 'PE', 'peru': 'PE'
        }
        for country_name, code in countries.items():
            if country_name in text_lower:
                return 'country', {'country': code, 'name': country_name}
        
        # Check for "more" or "why" commands
        if text_lower in ['more', 'más', 'plus', 'why', 'por qué', 'pourquoi']:
            return 'expand', {}
        
        # Check for filter commands
        if 'vegan' in text_lower or 'sin fragancia' in text_lower or 'local' in text_lower:
            return 'filter', {'criteria': text_lower}
        
        # Check for PII patterns
        pii_patterns = [r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', r'\b\d{3}-\d{2}-\d{4}\b']
        for pattern in pii_patterns:
            if re.search(pattern, text):
                return 'pii_detected', {}
        
        # Check for medical queries
        medical_keywords = ['medicina', 'doctor', 'enfermedad', 'síntoma', 'tratamiento', 
                          'medicine', 'disease', 'symptom', 'treatment']
        if any(keyword in text_lower for keyword in medical_keywords):
            return 'medical', {}
        
        # Check for out-of-scope
        out_of_scope = ['hora', 'tiempo', 'clima', 'weather', 'time', 'joke', 'chiste']
        if any(keyword in text_lower for keyword in out_of_scope):
            return 'out_of_scope', {}
        
        # Check for product categories
        categories = ['shampoo', 'jabón', 'soap', 'crema', 'cream', 'desodorante', 'deodorant']
        for category in categories:
            if category in text_lower:
                return 'category', {'category': category}
        
        # Default: assume it's a product name
        return 'product', {'name': text}
    
    def process_state_transition(self, intent: str, entities: Dict) -> Tuple[str, str]:
        """Process state machine transition and return new state + response"""
        current_state = self.session.current_state
        state_config = self.state_machine['states'].get(current_state, {})
        
        # INIT State
        if current_state == 'INIT':
            lang = entities.get('language', 'en')
            greeting = self.templates['greeting'].get(lang, self.templates['greeting']['en'])
            self.session.save_state('AWAITING_COUNTRY')
            return 'AWAITING_COUNTRY', greeting
        
        # AWAITING_COUNTRY State
        elif current_state == 'AWAITING_COUNTRY':
            if intent == 'country':
                self.session.save_country(entities['country'])
                self.session.save_state('READY')
                return 'READY', "Perfecto! ¿Qué producto quieres que analice? 📸"
            elif intent in ['product', 'category']:
                # Use default country but still process
                self.session.save_country('US')  # Default
                self.session.save_state('READY')
                return 'READY', None  # Continue to analysis
            else:
                return 'AWAITING_COUNTRY', self.templates['errors']['no_country']
        
        # READY State
        elif current_state == 'READY':
            if intent == 'pii_detected':
                return 'READY', self.templates['errors']['pii_detected']
            elif intent == 'medical':
                return 'READY', self.templates['errors']['medical_query']
            elif intent == 'out_of_scope':
                return 'READY', self.templates['errors']['out_of_scope']
            elif intent in ['product', 'category']:
                self.session.save_state('ANALYZING')
                return 'ANALYZING', None  # Proceed to analysis
            else:
                return 'READY', "¿Qué producto te gustaría que analice?"
        
        # RESULTS_SHOWN State
        elif current_state == 'RESULTS_SHOWN':
            if intent == 'expand':
                # Return detailed analysis
                last_analysis = get_latest_analysis(self.session.phone_no)
                if last_analysis:
                    return 'RESULTS_SHOWN', self.format_detailed_response(last_analysis)
                return 'READY', "¿Qué producto quieres analizar?"
            elif intent == 'filter':
                return 'ANALYZING', None  # Re-analyze with filters
            elif intent in ['product', 'category']:
                self.session.save_state('ANALYZING')
                return 'ANALYZING', None
            else:
                return 'READY', "¿Quieres ver otro producto?"
        
        # Default fallback
        return 'READY', "¿En qué puedo ayudarte?"
    
    def format_golden_response(self, product_data: Dict) -> str:
        """Format response according to Golden Format template"""
        template = self.templates['golden_format']['structure']
        
        # Build response
        response = f"{template['header']}\n"
        response += f"{template['algorithm_version'].format(version=self.core['version'], date='Sept 2024')}\n\n"
        response += f"Product: {product_data['name']}\n"
        response += f"Score: {product_data['overall_score']}/100 {self.get_score_emoji(product_data['overall_score'])}\n\n"
        
        # Add sub-scores
        response += "Sub-scores:\n"
        for key, label_template in template['subscores'].items():
            score = product_data.get(f'{key}_score', 0)
            insight = product_data.get(f'{key}_insight', '')[:50]  # Max 50 chars
            response += label_template.format(score=score, insight=insight) + "\n"
        
        response += f"\n{template['alternatives_header']}\n"
        
        # Add alternatives
        for alt in product_data.get('alternatives', [])[:3]:
            response += template['alternative_item'].format(
                name=alt['name'],
                price=alt.get('price', 'Check store'),
                certifications=alt.get('certifications', ''),
                link=alt.get('link', '#')
            ) + "\n"
        
        response += f"\n{template['cta']}\n"
        response += f"{template['filters']}"
        
        return response
    
    def get_score_emoji(self, score: int) -> str:
        """Get emoji based on score"""
        emojis = self.templates['golden_format']['emojis']
        if score >= 85:
            return emojis['score_85_100']
        elif score >= 70:
            return emojis['score_70_84']
        elif score >= 50:
            return emojis['score_50_69']
        else:
            return emojis['score_0_49']
    
    def format_detailed_response(self, analysis_data: Dict) -> str:
        """Format detailed analysis response"""
        detailed = self.templates['follow_ups']['show_more']
        
        response = f"{detailed['ingredients'].format(detailed_breakdown=analysis_data.get('ingredients', 'N/A'), safe_count=0, questionable_count=0, avoid_count=0)}\n\n"
        response += f"{detailed['sources'].format(numbered_list=analysis_data.get('sources', 'N/A'))}\n\n"
        response += f"{detailed['methodology']}"
        
        return response


def clean_system_tags(text: str) -> str:
    """Remove any system tags from text"""
    if not text:
        return text
    
    # Remove system tags
    patterns = [
        r'<[^>]+>',  # Any XML-like tags
        r'\[MEDIA_CONTENT\]',
        r'MM[A-Za-z0-9]{32}',
        r'ME[A-Za-z0-9]{32}'
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text.strip()


@app.post('/whatsapp-endpoint')
async def whatsapp_endpoint(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: str = Form("0"),
    MediaUrl0: str = Form(None),
    MediaContentType0: str = Form(None)
):
    """Main WhatsApp webhook endpoint with modular architecture"""
    try:
        logger.info(f'Request from: {From}, Body: {Body[:50]}...')
        
        phone_no = From.replace('whatsapp:+', '')
        query = clean_system_tags(Body)
        
        # Initialize session and processor
        session = NOURASession(phone_no)
        processor = NOURAProcessor(session)
        
        # Log interaction for audit
        session.log_trace('incoming_message', {
            'raw_body': Body[:100],
            'has_media': bool(NumMedia and int(NumMedia) > 0),
            'current_state': session.current_state
        })
        
        # Process media if present
        if NumMedia and int(NumMedia) > 0 and MediaUrl0:
            if MediaContentType0 and MediaContentType0.startswith("image"):
                # Process image through existing pipeline
                query = "analyze_product_image"
                # Image processing logic remains same
        
        # Detect intent and entities
        intent, entities = processor.detect_intent(query)
        
        # Process state transition
        new_state, response = processor.process_state_transition(intent, entities)
        
        # If response is None, we need to do analysis
        if response is None and new_state == 'ANALYZING':
            # Run product analysis
            try:
                analysis_result = await analyze_product(query)
                
                if analysis_result.get('found'):
                    # Format with Golden Format
                    product_data = {
                        'name': analysis_result.get('product_name', query),
                        'overall_score': analysis_result.get('score', 0),
                        'health_score': analysis_result.get('health_score', 0),
                        'health_insight': analysis_result.get('health_insight', ''),
                        'planet_score': analysis_result.get('planet_score', 0),
                        'planet_insight': analysis_result.get('planet_insight', ''),
                        'social_score': analysis_result.get('social_score', 0),
                        'social_insight': analysis_result.get('social_insight', ''),
                        'animal_score': analysis_result.get('animal_score', 0),
                        'animal_insight': analysis_result.get('animal_insight', ''),
                        'alternatives': analysis_result.get('alternatives', [])
                    }
                    
                    response = processor.format_golden_response(product_data)
                    
                    # Store analysis for "more" command
                    store_latest_analysis(phone_no, analysis_result)
                    
                    # Log trace
                    session.log_trace('product_scored', {
                        'product': product_data['name'],
                        'score': product_data['overall_score'],
                        'sources_used': analysis_result.get('sources', [])
                    })
                    
                    session.save_state('RESULTS_SHOWN')
                else:
                    response = TEMPLATES['errors']['product_not_found']
                    session.save_state('READY')
                    
            except Exception as e:
                logger.error(f"Analysis error: {e}")
                response = TEMPLATES['errors']['api_unavailable'].format(
                    date=datetime.now().strftime('%Y-%m-%d')
                )
                session.save_state('READY')
        
        # Send response via Twilio
        if response:
            send_whatsapp_message(From, response)
        
        return PlainTextResponse("OK", status_code=200)
        
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        
        # Send fallback message
        try:
            send_whatsapp_message(
                From, 
                TEMPLATES['errors']['generic_error']
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message: {send_error}")
        
        return PlainTextResponse("Error", status_code=500)


def send_whatsapp_message(to_number: str, message: str):
    """Send WhatsApp message via Twilio"""
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    
    # Clean any remaining system tags
    message = clean_system_tags(message)
    
    # Split if too long
    max_length = 3000
    if len(message) > max_length:
        chunks = [message[i:i+max_length] for i in range(0, len(message), max_length)]
        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                chunk = f"Part {i+1}/{len(chunks)}: {chunk}"
            client.messages.create(
                body=chunk,
                from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
                to=to_number
            )
    else:
        client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
            to=to_number
        )


if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main_v2:app", host='0.0.0.0', port=3002, reload=True)
