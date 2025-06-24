from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters
from src.utils.habits_api import (
    start_habits_conversation,
    add_habit, # Asegúrate de importar add_habit
    cancel_habits_conversation
)

# Definimos el mismo estado aquí para que coincida
SELECTING_HABIT_ID = 1

def get_habits_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("habits", start_habits_conversation)],
        states={
            # Usamos SELECTING_HABIT_ID en lugar del número literal 1
            # Y el filtro `filters.Regex(r'^\d+$')` es más específico para números
            SELECTING_HABIT_ID: [MessageHandler(filters.Regex(r'^\d+$'), add_habit)],
            # También podrías usar `MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit)`
            # pero `filters.Regex(r'^\d+$')` es mejor si solo esperas dígitos.
        },
        fallbacks=[CommandHandler("cancel", cancel_habits_conversation)],
        # Esto es útil para depuración:
        allow_reentry=True # Permite reentrar a la conversación si el usuario manda el entry_point de nuevo
    )