# Twilio-OpenAI-WhatsApp-Bot

This repo contains code to build a chatbot in Python that runs in WhatsApp and answers user messages using OpenAI API. Developed with FastAPI and we use Twilio for Business WhatsApp integration. The source code is available on GitHub under an open-source license.

## Tech stack:
- Python
- Docker
- FastAPI
- Twilio
- OpenAI API
- Redis

## Getting Started

To get started, follow these steps:

1. Clone the repository to your local machine:
   ```bash
   git clone git@github.com:Shakurova/Twilio-OpenAI-WhatsApp-Bot.git
   cd Twilio-OpenAI-WhatsApp-Bot/
   ```

2. Setting up Twilio

   - **Twilio Sandbox for WhatsApp**: Start by setting up the Twilio Sandbox for WhatsApp to test your application. This allows you to send and receive messages using a temporary WhatsApp number provided by Twilio. Follow the steps in the Twilio Console under the "Messaging" section to configure the sandbox. You can find detailed instructions in the [Twilio Blog Guide](https://www.twilio.com/en-us/blog/ai-chatbot-whatsapp-python-twilio-openai).

   - **Moving to Production**: Once you have tested your application in the sandbox environment and are ready to go live, you can set up a Twilio phone number for production use. This involves purchasing a Twilio number and configuring it to handle WhatsApp messages. Refer to [Twilio Guide](https://www.twilio.com/docs/whatsapp) for more information on transitioning to a production environment.

3. Make sure you have docker and redis installed on your machine.

   For macOS:
   Install Redis using Homebrew:
   ```bash
   brew install redis
   ```
   Start Redis:
   ```bash
   brew services start redis
   ```

   Install Docker via Homebrew:
   ```bash
   brew install --cask docker
   Open Docker Desktop and make sure it’s running.
   ```
   Verify installation:
   ```bash
   docker --version
   ```

4. Create a `.env` file in the project directory and set your OpenAI API key and Twilio account details as environment variables:
   ```plaintext
    TWILIO_WHATSAPP_NUMBER=<your Twilio phone number>
    TWILIO_ACCOUNT_SID=<your Twilio account SID>
    TWILIO_AUTH_TOKEN=<your Twilio auth token>
    OPENAI_API_KEY=<your OpenAI API key>
    REDIS_HOST=<your redis host>
    REDIS_PORT=<your redis port>
    REDIS_PASSWORD=<your redis password>
   ```

5. Build and start the chatbot containers by running:
   ```bash
   docker-compose up --build -d
   ```

## Troubleshooting

## Solución de Problemas - Error 401 al descargar media de Twilio

### Problema Principal
OpenAI intentaba descargar directamente las URLs de media de Twilio, que requieren autenticación HTTP básica. Esto causaba errores como:
```
Error while downloading https://api.twilio.com/2010-04-01/Accounts/.../Messages/.../Media/...
```

### Solución Implementada

#### 1. **Descarga Autenticada de Media**
- El bot descarga correctamente media (imágenes/audio) usando autenticación HTTP básica
- Usuario: `TWILIO_ACCOUNT_SID`
- Contraseña: `TWILIO_AUTH_TOKEN`
- Convierte imágenes a base64 para OpenAI

#### 2. **Limpieza de URLs de Twilio**
Se implementó limpieza agresiva de URLs y identificadores de Twilio en múltiples puntos:

```python
# Patrones limpiados:
- https://api.twilio.com/...
- https://subdomain.twilio.com/...
- https://media.twiliocdn.com/...
- MM[32 caracteres] (Message SIDs)
- ME[32 caracteres] (Media SIDs)
- /2010-04-01/Accounts/.../Messages/.../Media/...
```

#### 3. **Puntos de Limpieza**
- **Query del usuario**: Antes de agregar al historial
- **Historial recuperado**: Al cargar de Redis
- **Historial para OpenAI**: Antes de enviar
- **System prompt**: Después de formatear
- **Summary de conversación**: En la función `summarise_conversation`
- **Guardado en Redis**: Antes de almacenar

#### 4. **Logging Mejorado**
- No se loggean URLs originales de media
- Verificación previa al envío a OpenAI
- Detecta automáticamente URLs de Twilio restantes

### Archivos Modificados

1. **`app/main.py`**:
   - Función `clean_twilio_urls()` robusta
   - Limpieza en múltiples puntos del flujo
   - Verificación antes de enviar a OpenAI
   - Logging de seguridad mejorado

2. **`app/openai_utils.py`**:
   - Función `summarise_conversation()` actualizada
   - Soporte para formato correcto de mensajes (`role`/`content`)
   - Limpieza de URLs en el summary

3. **Scripts de testing**:
   - `test_url_cleaning.py`: Prueba patrones de limpieza
   - `debug_messages.py`: Simula estructura de mensajes

### Verificación

Para verificar que todo funciona correctamente:

```bash
# 1. Probar limpieza de URLs (sin dependencias)
python test_simple_image.py

# 2. Probar acceso completo (con dependencias)
python test_image_access.py

# 3. Dentro del contenedor Docker (prueba completa)
docker-compose exec app python test_bot_complete.py

# 4. Monitorear logs en tiempo real
docker-compose logs -f app
```

### Prueba Real con WhatsApp

1. **Envía una imagen por WhatsApp** al número del bot
2. **Revisa los logs** con `docker-compose logs -f app`
3. **Busca estas líneas exitosas**:
   ```
   ✅ Successfully downloaded X bytes
   ✅ Image converted to base64 successfully
   ✅ No se encontraron URLs de Twilio en los mensajes finales
   ```
4. **Confirma que NO aparezcan errores como**:
   ```
   ❌ Error while downloading https://api.twilio.com/...
   ```

### Estado Actual
✅ **Funcionando**: El bot puede procesar imágenes sin errores de OpenAI
✅ **Autenticación**: Media se descarga correctamente de Twilio
✅ **Seguridad**: URLs sensibles no se envían a OpenAI
✅ **Historial**: Conversaciones limpias sin URLs problemáticas

### Otros problemas comunes

- **OpenAI API errors**: Verifica que tu API key sea válida y tenga créditos
- **Redis connection**: Asegúrate de que Redis esté ejecutándose
- **Twilio webhook**: Verifica que la URL del webhook esté configurada correctamente en Twilio