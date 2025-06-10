#api del bot: TELEGRAM_BOT_TOKEN
#api para acceder a datos del clima: OPENWEATHER_API_KEY

# src/bot/productivity_habits_bot.py

import os
import logging
from telegram.ext import ApplicationBuilder, Update # Necesitas Update para allowed_updates
from dotenv import load_dotenv

# --- Importaciones de Handlers ---
from handlers.start_handler import get_handler as get_start_handler
from handlers.weather_handler import get_weather_conversation_handler # Importa la función del handler del clima

# --- Importaciones de la Base de Datos ---
# Ajusta según tu archivo real en src/database/
from database.database_interation import init_db, load_default_habits

# Carga las variables de entorno
load_dotenv()

# Configura la API Key del bot de Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING) # Silencia mensajes de httpx

    logging.info("Inicializando la base de datos...")
    init_db()
    load_default_habits()
    logging.info("Base de datos inicializada y hábitos por defecto cargados.")

    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN no está configurado. Asegúrate de tenerlo en tu archivo .env")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    logging.info("Bot de Telegram iniciado.")

    logging.info("Registrando handlers...")

    # Registrar el handler de /start
    application.add_handler(get_start_handler())

    # Registrar el handler del clima
    application.add_handler(get_weather_conversation_handler())

    # Aquí añadirías otros handlers, por ejemplo, para tareas o hábitos...

    logging.info("Handlers registrados. El bot está listo para escuchar.")

    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logging.info("El bot ha dejado de ejecutarse.")

if __name__ == "__main__":
    main()