from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import logging
from src.database.database_interation import get_user_by_telegram_id, get_habits, add_user_habit, get_all_users, get_user_habits
from src.database.db_context import get_db

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SELECTING_HABIT_ID = 1

async def start_habits_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para añadir hábitos y lista los disponibles desde la BD."""
    logger.info(f"Comando /habits recibido de {update.effective_user.full_name} (ID: {update.effective_user.id}).")

    habits_list_text = "No hay hábitos disponibles en este momento."
    async with get_db() as db:
        available_habits = await get_habits(db)
        if available_habits:
            habits_list_text = "\n".join([f"**{habit.id}**: {habit.description}" for habit in available_habits])

    await update.message.reply_text(
        f"Hábitos disponibles para mejorar:\n{habits_list_text}\n\n"
        "Escribe el **ID del hábito** que deseas añadir a tu lista personal. "
        "O envía /cancelar para terminar."
    )
    return SELECTING_HABIT_ID

async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la entrada del ID del hábito y lo añade al usuario."""
    user_input = update.message.text
    telegram_user_id = update.effective_user.id
    logger.info(f"Recibido input '{user_input}' para añadir hábito de usuario {telegram_user_id}.")

    try:
        habit_id = int(user_input)
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, telegram_user_id)
            if not user:
                await update.message.reply_text("Error: No estás registrado. Por favor, usa /start primero.")
                return ConversationHandler.END

            new_habit = await add_user_habit(db, user.id, habit_id)
            if new_habit:
                await update.message.reply_text(f"¡Hábito con ID **{habit_id}** añadido exitosamente a tu lista!")
                logger.info(f"Hábito {habit_id} añadido para el usuario {telegram_user_id}.")
            else:
                await update.message.reply_text(f"No se pudo añadir el hábito. Es posible que ya lo tengas o que el ID no sea válido.")
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("Eso no parece un ID de hábito válido. Por favor, ingresa un **número**.")
        return SELECTING_HABIT_ID
    except Exception as e:
        logger.error(f"Error al añadir hábito para el usuario {telegram_user_id} con ID '{user_input}': {e}", exc_info=True)
        await update.message.reply_text("Lo siento, hubo un error al procesar tu solicitud.")
        return ConversationHandler.END

async def cancel_habits_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación para añadir hábitos."""
    logger.info(f"Conversación de hábitos cancelada por {update.effective_user.full_name}.")
    await update.message.reply_text("Operación cancelada.")
    return ConversationHandler.END


async def send_daily_habits(context: ContextTypes.DEFAULT_TYPE):
    """
    Envía un recordatorio diario con la lista de hábitos a cada usuario.
    """
    logger.info("Iniciando el envío de recordatorios de hábitos.")
    async with get_db() as db:
        # Obtener todos los usuarios registrados
        users = await get_all_users(db)

        for user in users:
            # Para cada usuario, obtener sus hábitos personales
            user_habits_records = await get_user_habits(db, user.id)

            if not user_habits_records:
                logger.info(f"Usuario {user.telegram_id} no tiene hábitos registrados. Saltando.")
                continue

            habits_descriptions = []
            for user_habit in user_habits_records:
                # Obtener la descripción de cada hábito
                default_habits = await get_habits(db, user_habit.habit_id)
                if default_habits:
                    habits_descriptions.append(f"  - {default_habits[0].description}")

            if habits_descriptions:
                message_text = "🔔 Recordatorio Diario de Hábitos\n\nRecuerda practicar hoy:\n" + "\n".join(habits_descriptions)
                try:
                    await context.bot.send_message(
                        chat_id=user.telegram_id,
                        text=message_text,
                        parse_mode='Markdown'
                    )
                    logger.info(f"Recordatorio de hábitos enviado a {user.telegram_id}.")
                except Exception as e:
                    logger.error(f"Error al enviar recordatorio de hábitos al usuario {user.telegram_id}: {e}")

    logger.info("Envío de recordatorios de hábitos finalizado.")





