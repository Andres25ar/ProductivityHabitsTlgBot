# src/handlers/user_handler.py

import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from src.database.db_context import get_db # Importa get_db desde db_context
import pytz # Necesario para la validación de zona horaria
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError # Necesario para validar zonas horarias

# Importar las funciones de base de datos correctas
from src.database.database_interation import add_user, get_user, update_user_timezone # Usamos add_user, get_user y update_user_timezone

logger = logging.getLogger(__name__)

# Estados para ConversationHandler (si se usaran en el futuro para flujo multi-paso)
SET_TIMEZONE_INPUT = 1 # Define el estado para la conversación de zona horaria

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía un mensaje de bienvenida y registra/obtiene el usuario."""
    user_telegram_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    last_name = update.effective_user.last_name

    logger.info(f"Comando /start recibido de usuario: {user_telegram_id} ({username})")

    try:
        with get_db() as db: # Usa el context manager
            # add_user se encarga de añadir o recuperar si ya existe
            user = add_user(db, telegram_id=user_telegram_id, username=username,
                            first_name=first_name, last_name=last_name)
            logger.info(f"Usuario {user.telegram_id} ({user.username}) registrado/obtenido.")

            await update.message.reply_text(
                f"¡Hola, {first_name}! 👋 Soy tu bot de hábitos y productividad. "
                "Estoy aquí para ayudarte a organizar tus tareas y mantener tus hábitos.\n\n"
                "Para empezar, puedes establecer tu zona horaria con `/set_timezone <ZonaHorariaIANA>` "
                "(ej: `/set_timezone America/Argentina/Salta`).\n"
                "También puedes ver tu perfil con /profile."
            )
    except Exception as e:
        logger.error(f"Error al procesar /start para usuario {user_telegram_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error al iniciar. Por favor, inténtalo de nuevo más tarde.")

async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Solicita al usuario que ingrese su zona horaria.
    Este es el inicio de una posible conversación.
    """
    user_telegram_id = update.effective_user.id
    logger.info(f"Comando /set_timezone recibido de usuario: {user_telegram_id}")

    # Si se proporciona un argumento directamente con el comando, intentamos procesarlo
    if context.args:
        timezone_str = " ".join(context.args)
        return await _process_timezone_input(update, context, timezone_str)
    else:
        await update.message.reply_text(
            "Por favor, ingresa tu zona horaria en formato IANA/Olson (ej: `America/Argentina/Salta`).\n"
            "Puedes encontrar una lista aquí: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones\n"
            "O escribe /cancel para anular la operación."
        )
        return SET_TIMEZONE_INPUT # Retorna el estado para la siguiente entrada del usuario

async def handle_timezone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Maneja la entrada de la zona horaria del usuario cuando es parte de una conversación.
    """
    timezone_str = update.message.text.strip()
    return await _process_timezone_input(update, context, timezone_str)

async def _process_timezone_input(update: Update, context: ContextTypes.DEFAULT_TYPE, timezone_str: str) -> int:
    """
    Función auxiliar para procesar y validar la entrada de la zona horaria.
    """
    user_telegram_id = update.effective_user.id
    logger.info(f"Procesando entrada de zona horaria de {user_telegram_id}: {timezone_str}")

    try:
        ZoneInfo(timezone_str) # Intenta crear el objeto ZoneInfo para validar
    except ZoneInfoNotFoundError:
        await update.message.reply_text(
            "❌ Esa no es una zona horaria válida. Por favor, usa el formato IANA/Olson "
            f"(ej: `America/Argentina/Salta`).\n"
            "Consulta la lista aquí: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones\n"
            "O escribe /cancel para anular la operación."
        )
        return SET_TIMEZONE_INPUT # Permanece en el mismo estado para reintentar
    except Exception as e:
        logger.error(f"Error inesperado al validar zona horaria '{timezone_str}' para usuario {user_telegram_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al validar tu zona horaria. Por favor, inténtalo de nuevo.")
        return SET_TIMEZONE_INPUT


    try:
        with get_db() as db: # Usa el context manager
            user = get_user(db, user_telegram_id) # Usa get_user
            if user:
                updated_user = update_user_timezone(db, user.telegram_id, timezone_str) # Pasa telegram_id, no user.id
                if updated_user:
                    logger.info(f"Zona horaria del usuario {user_telegram_id} actualizada a {timezone_str}.")
                    await update.message.reply_text(
                        f"✅ ¡Listo! Tu zona horaria ha sido establecida a `{timezone_str}`.\n"
                        "A partir de ahora, los recordatorios y tareas se ajustarán a esta zona horaria."
                    )
                else:
                    await update.message.reply_text("No pude actualizar tu zona horaria. ¿Estás registrado? Usa /start.")
            else:
                await update.message.reply_text("No estás registrado. Por favor, usa /start primero para registrarte.")
    except Exception as e:
        logger.error(f"Error al actualizar zona horaria para usuario {user_telegram_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error al intentar guardar tu zona horaria en la base de datos. Por favor, inténtalo de nuevo.")

    return ConversationHandler.END # Finaliza la conversación

async def show_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la información del perfil del usuario."""
    user_telegram_id = update.effective_user.id
    logger.info(f"Comando /profile recibido de usuario: {user_telegram_id}")

    try:
        with get_db() as db: # Usa el context manager
            user = get_user(db, user_telegram_id) # Usa get_user
            if user:
                profile_text = (
                    f"✨ **Tu Perfil** ✨\n"
                    f"ID de Telegram: `{user.telegram_id}`\n"
                    f"Nombre: `{user.first_name} {user.last_name or ''}`\n"
                    f"Username: `{user.username or 'N/A'}`\n"
                    f"Zona Horaria: `{user.timezone}`\n"
                    f"Registrado desde: `{user.created_at.strftime('%Y-%m-%d %H:%M:%S %Z')}`"
                )
                await update.message.reply_text(profile_text, parse_mode='Markdown')
            else:
                await update.message.reply_text("No estás registrado. Por favor, usa /start primero para registrarte.")
    except Exception as e:
        logger.error(f"Error al mostrar perfil para usuario {user_telegram_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error al intentar mostrar tu perfil. Por favor, inténtalo de nuevo más tarde.")
