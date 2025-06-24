# src/handlers/set_timezone_handler.py

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError 
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler

# Importar las funciones de base de datos y el context manager necesario
from src.database.database_interation import get_user_by_telegram_id, update_user_timezone 
from src.database.db_context import get_db 

logger = logging.getLogger(__name__)

# Estados para la conversación de set_timezone
SET_TIMEZONE_INPUT = 0

async def start_set_timezone_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Inicia la conversación para establecer la zona horaria.
    Pide al usuario que ingrese su zona horaria.
    """
    user_telegram_id = update.effective_user.id
    logger.info(f"Comando /set_timezone recibido de usuario: {user_telegram_id}. Iniciando conversación.")

    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_telegram_id} en /set_timezone. No se puede responder.")
        return ConversationHandler.END

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Por favor, ingresa tu zona horaria en formato IANA/Olson (ej: `America/Argentina/Salta`). "
             "Puedes encontrar una lista completa aquí: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones\n"
             "Escribe /cancelar en cualquier momento para abortar."
    )
    return SET_TIMEZONE_INPUT # Pasa al estado donde esperamos la entrada de la zona horaria

async def receive_timezone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Recibe la entrada de la zona horaria del usuario, la valida y la guarda.
    """
    user_telegram_id = update.effective_user.id
    timezone_str = update.message.text.strip()
    logger.debug(f"Usuario {user_telegram_id} ingresó zona horaria: {timezone_str}")

    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_telegram_id} al recibir la zona horaria. No se puede responder.")
        return ConversationHandler.END

    try:
        # Intenta crear un objeto ZoneInfo para validar si la cadena es un TZ IANA/Olson válido
        ZoneInfo(timezone_str)
        logger.debug(f"Zona horaria '{timezone_str}' es válida para usuario {user_telegram_id}.")
    except ZoneInfoNotFoundError:
        logger.warning(f"Usuario {user_telegram_id} intentó establecer zona horaria inválida: {timezone_str}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Esa no es una zona horaria válida. Por favor, usa el formato IANA/Olson "
                 f"(ej: `America/Argentina/Salta`).\n"
                 "Consulta la lista aquí: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones\n"
                 "Por favor, intenta de nuevo o /cancelar."
        )
        return SET_TIMEZONE_INPUT # Permanece en el mismo estado para que el usuario intente de nuevo
    except Exception as e:
        logger.error(f"Error inesperado al validar zona horaria '{timezone_str}' para usuario {user_telegram_id}: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ocurrió un error inesperado al validar tu zona horaria. Por favor, inténtalo de nuevo o /cancelar."
        )
        return SET_TIMEZONE_INPUT # Permanece en el mismo estado

    try:
        async with get_db() as db: 
            user = await get_user_by_telegram_id(db, user_telegram_id) 
            logger.debug(f"Resultado get_user_by_telegram_id para {user_telegram_id}: {user}")

            if not user:
                logger.warning(f"Usuario {user_telegram_id} intentó establecer zona horaria sin estar registrado.")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="No estás registrado. Por favor, usa /start primero para registrarte."
                )
                return ConversationHandler.END # Termina la conversación

            success = await update_user_timezone(db, user.id, timezone_str) 
            
            if success:
                logger.info(f"Zona horaria del usuario {user_telegram_id} actualizada en DB a {timezone_str}.")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"✅ ¡Listo! Tu zona horaria ha sido establecida a `{timezone_str}`.\n"
                         "A partir de ahora, los recordatorios y tareas se ajustarán a esta zona horaria."
                )
            else:
                logger.warning(f"Fallo al actualizar la zona horaria en la DB para usuario {user_telegram_id} a {timezone_str}.")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="⚠️ Hubo un problema al guardar tu zona horaria. Parece que tu usuario no fue encontrado o la zona horaria no se pudo aplicar correctamente."
                )
        return ConversationHandler.END # Termina la conversación si fue exitoso o falló al guardar
    except Exception as e:
        logger.error(f"Error al actualizar zona horaria para usuario {user_telegram_id}: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ocurrió un error al intentar guardar tu zona horaria en la base de datos. Por favor, inténtalo de nuevo o /cancelar."
        )
        return ConversationHandler.END # Termina la conversación en caso de error grave

async def cancel_set_timezone_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de configuración de zona horaria."""
    user_telegram_id = update.effective_user.id
    logger.info(f"Conversación /set_timezone cancelada por el usuario {user_telegram_id}.")
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Configuración de zona horaria cancelada."
        )
    return ConversationHandler.END

def get_set_timezone_conversation_handler():
    """
    Devuelve el ConversationHandler para manejar la configuración de la zona horaria.
    """
    return ConversationHandler(
        entry_points=[CommandHandler("set_timezone", start_set_timezone_conversation)],
        states={
            SET_TIMEZONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_timezone_input)],
        },
        fallbacks=[CommandHandler("cancelar", cancel_set_timezone_conversation)],
    )
