#api del bot: TELEGRAM_BOT_TOKEN
#api para acceder a datos del clima: OPENWEATHER_API_KEY


import os
import logging
from datetime import time
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Handlers personalizados
from src.handlers.weather_handler import get_weather_conversation_handler
from src.handlers.habits_handler import get_habits_conversation_handler
from src.handlers.task_handler import task_conv_handler
from src.handlers.user_handler import user_conv_handler, off
from src.utils.habits_api import send_daily_habits


# Utilidades y base de datos
from src.utils.habits_api import get_daily_habits_for_user
from src.database.database_interation import init_db, DefaultHabit
from src.database.database_interation import SessionLocal, User

# Carga las variables de entorno
load_dotenv()

# Configura la API Key del bot de Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def main():
    # Configura el logging para mostrar información útil en la consola
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Inicializa la base de datos y carga los hábitos por defecto si no existen
    logging.info("Inicializando la base de datos...")
    init_db()
    DefaultHabit.load_default_habits()
    logging.info("Base de datos inicializada y hábitos por defecto cargados.")

    # Verifica que el token del bot esté configurado
    if not TELEGRAM_BOT_TOKEN:
        logging.error("TELEGRAM_BOT_TOKEN no está configurado. Asegúrate de tenerlo en tu archivo .env")
        return

    # Crea la aplicación del bot de Telegram
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    logging.info("Bot de Telegram iniciado.")

    logging.info("Registrando handlers...")

    # Registra el handler para el comando /start y la conversación de usuario
    application.add_handler(user_conv_handler)
    
    # Registra el handler para el comando /off
    application.add_handler(CommandHandler("off", off))

    # Registra el handler para la conversación del clima
    application.add_handler(get_weather_conversation_handler())

    # Registra el handler para la conversación de hábitos
    application.add_handler(get_habits_conversation_handler())

    # Registra el handler para la conversación de tareas
    application.add_handler(task_conv_handler)
    
    logging.info("Handlers registrados. El bot está listo para escuchar.")

    # Programa mensajes diarios para todos los usuarios registrados en la base de datos
    session = SessionLocal()
    users = session.query(User).all()
    session.close()
    for user in users:
        schedule_daily_messages(application, user.id)

    # Inicia el bot y comienza a escuchar mensajes
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logging.info("El bot ha dejado de ejecutarse.")

if __name__ == "__main__":
    main()
    

def schedule_daily_messages(application, user_id):
    """
    Programa tres mensajes diarios para enviar los hábitos al usuario:
    - A las 6:00 (mañana)
    - A las 12:00 (mediodía)
    - A las 22:00 (noche)
    """
    # 6:00
    application.job_queue.run_daily(
        send_daily_habits,
        time=time(6, 0),
        data={"user_id": user_id},
        name=f"morning_{user_id}"
    )
    # 12:00
    application.job_queue.run_daily(
        send_daily_habits,
        time=time(12, 0),
        data={"user_id": user_id},
        name=f"noon_{user_id}"
    )
    # 23:03
    application.job_queue.run_daily(
        send_daily_habits,
        time=time(22, 0),
        data={"user_id": user_id},
        name=f"night_{user_id}"
    )