from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters

# Importa las funciones lógicas desde tu archivo de utilidad del clima
from utils.weather_api import (
    start_weather_conversation,
    get_weather,
    cancel_weather_conversation
)

def get_weather_conversation_handler():
    """
    Devuelve el ConversationHandler para manejar la funcionalidad del clima.
    """
    return ConversationHandler(
        entry_points=[CommandHandler("clima", start_weather_conversation)],
        states={
            0: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weather)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_weather_conversation)],
    )