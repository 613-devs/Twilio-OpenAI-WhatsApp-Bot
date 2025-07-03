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

### Error 401 al descargar media de Twilio

Si ves errores 401 cuando el bot intenta descargar imágenes o audio de WhatsApp, sigue estos pasos:

1. **Verifica tus credenciales de Twilio**:
   Ejecuta el script de diagnóstico para verificar tu configuración:
   ```bash
   python test_credentials.py
   ```

2. **Revisa tu archivo .env**:
   Asegúrate de que tienes todas las variables requeridas:
   ```plaintext
   TWILIO_ACCOUNT_SID=<tu Account SID de Twilio>
   TWILIO_AUTH_TOKEN=<tu Auth Token de Twilio>
   OPENAI_API_KEY=<tu API key de OpenAI>
   TWILIO_WHATSAPP_NUMBER=<tu número de WhatsApp de Twilio>
   ```

3. **Obtén las credenciales correctas de Twilio**:
   - Ve a tu [Twilio Console](https://console.twilio.com/)
   - En el dashboard principal, encontrarás:
     - **Account SID**: Empieza con "AC..."
     - **Auth Token**: Haz clic en "Show" para revelarlo
   - Copia estos valores exactamente como aparecen

4. **Problema común**: URLs de media caducadas
   - Los URLs de media de Twilio expiran después de un tiempo
   - Si continúas viendo errores 401, el problema puede ser que la URL haya caducado
   - El bot intentará múltiples métodos de descarga automáticamente

5. **Logs de diagnóstico**:
   Revisa los logs del contenedor para más detalles:
   ```bash
   docker-compose logs -f app
   ```

### Otros problemas comunes

- **OpenAI API errors**: Verifica que tu API key sea válida y tenga créditos
- **Redis connection**: Asegúrate de que Redis esté ejecutándose
- **Twilio webhook**: Verifica que la URL del webhook esté configurada correctamente en Twilio