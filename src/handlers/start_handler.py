from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_user.first_name
    await update.message.reply_text(
        f"¡Hola, {user_first_name}! Soy tu asistente de productividad 🚀\n"
        "Usá /ayuda para ver todo lo que puedo hacer."
    )

def get_handler():
    return CommandHandler("start", start)
