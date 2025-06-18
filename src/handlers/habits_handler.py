from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters

from src.utils.habits_api import (
    start_habits_conversation,
    list_habits,
    add_habit,
    cancel_habits_conversation
)

def get_habits_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("habits", start_habits_conversation)],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_habit)],
        },
        fallbacks=[CommandHandler("cancel", cancel_habits_conversation)],
    )
