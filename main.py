# main.py
import logging
import os
from dotenv import load_dotenv

# Importa la función 'main' de tu bot
from src.bot.productivity_habits_bot import main as run_bot_application_sync

# Cargar variables de entorno desde .env (útil para desarrollo local)
load_dotenv()

# Configuración básica de logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

if __name__ == "__main__":
    logging.info("Iniciando la aplicación del bot...")
    # Llama a la función 'main' del bot, que es la que gestionará asyncio.run()
    run_bot_application_sync()