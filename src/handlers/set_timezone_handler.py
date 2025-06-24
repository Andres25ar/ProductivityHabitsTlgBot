import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError # Import ZoneInfoNotFoundError for specific error handling
import pytz
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

# Importar las funciones de base de datos y el context manager necesario
# ¡CORRECCIÓN AQUÍ! Cambiado 'set_user_timezone' a 'update_user_timezone'
from src.database.database_interation import get_user_by_telegram_id, update_user_timezone 
from src.database.db_context import get_db # Usar esta importación para get_db

logger = logging.getLogger(__name__)

async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Establece la zona horaria del usuario.
    Uso: /set_timezone <ZonaHorariaIANA>
    Ej: /set_timezone America/Argentina/Salta
    """
    user_telegram_id = update.effective_user.id
    logger.info(f"Comando /set_timezone recibido de usuario: {user_telegram_id} con args: {context.args}")

    if not context.args:
        logger.warning(f"Usuario {user_telegram_id} no proporcionó argumento para /set_timezone.")
        await update.message.reply_text(
            "Por favor, proporciona tu zona horaria en formato IANA/Olson (ej: `America/Argentina/Salta`). "
            "Puedes encontrar una lista completa aquí: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        )
        return

    # Unir todos los argumentos para permitir zonas horarias con espacios (aunque es raro en IANA)
    timezone_str = " ".join(context.args)
    logger.debug(f"Usuario {user_telegram_id} intenta setear zona horaria a: {timezone_str}")

    try:
        # Intenta crear un objeto ZoneInfo para validar si la cadena es un TZ IANA/Olson válido
        ZoneInfo(timezone_str)
        logger.debug(f"Zona horaria '{timezone_str}' es válida para usuario {user_telegram_id}.")
    except ZoneInfoNotFoundError:
        logger.warning(f"Usuario {user_telegram_id} intentó establecer zona horaria inválida: {timezone_str}")
        await update.message.reply_text(
            "❌ Esa no es una zona horaria válida. Por favor, usa el formato IANA/Olson "
            f"(ej: `America/Argentina/Salta`).\n"
            "Consulta la lista aquí: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones"
        )
        return
    except Exception as e:
        logger.error(f"Error inesperado al validar zona horaria '{timezone_str}' para usuario {user_telegram_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al validar tu zona horaria. Por favor, inténtalo de nuevo.")
        return

    try:
        # Usar el context manager get_db del src.database.db_context
        async with get_db() as db: 
            user = await get_user_by_telegram_id(db, user_telegram_id) 
            logger.debug(f"Resultado get_user_by_telegram_id para {user_telegram_id}: {user}")

            if not user:
                logger.warning(f"Usuario {user_telegram_id} intentó establecer zona horaria sin estar registrado.")
                await update.message.reply_text("No estás registrado. Por favor, usa /start primero para registrarte.")
                return

            # ¡CORRECCIÓN AQUÍ! Llamando a la función renombrada
            await update_user_timezone(db, user.id, timezone_str) 
            logger.info(f"Zona horaria del usuario {user_telegram_id} actualizada en DB a {timezone_str}.")
            await update.message.reply_text(
                f"✅ ¡Listo! Tu zona horaria ha sido establecida a `{timezone_str}`.\n"
                "A partir de ahora, los recordatorios y tareas se ajustarán a esta zona horaria."
            )
    except Exception as e:
        logger.error(f"Error al actualizar zona horaria para usuario {user_telegram_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error al intentar guardar tu zona horaria en la base de datos. Por favor, inténtalo de nuevo.")

def setup_set_timezone_handler(application):
    """Registra el CommandHandler para /set_timezone en la aplicación."""
    application.add_handler(CommandHandler("set_timezone", set_timezone_command))

