from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters
from src.utils.user_api import create_or_get_user, update_user_name, delete_user

ASK_NAME = 1

async def start(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    last_name = update.effective_user.last_name
    create_or_get_user(user_id, username, first_name, last_name)
    await update.message.reply_text(
        "¡Bienvenido! ¿Cómo te gustaría que te llame el bot? Por favor, escribe tu nombre."
    )
    return ASK_NAME

async def save_name(update, context):
    user_id = update.effective_user.id
    name = update.message.text.strip()
    update_user_name(user_id, name)
    await update.message.reply_text(f"¡Gracias, {name}! Ya puedes usar el resto de las funciones del bot.")
    return ConversationHandler.END

async def off(update, context):
    user_id = update.effective_user.id
    delete_user(user_id)
    await update.message.reply_text("Tu usuario ha sido eliminado del bot. Puedes usar /start para comenzar de nuevo.")

user_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
    },
    fallbacks=[],
)