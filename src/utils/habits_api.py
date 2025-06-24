# src/utils/habits_api.py

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import logging
from src.database.database_interation import get_all_users, get_user_habits, get_habits

# Configura el logger si no lo has hecho ya
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Definimos el estado para mayor claridad
SELECTING_HABIT_ID = 1

async def start_habits_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para añadir hábitos y lista los disponibles."""
    logger.info(f"Comando /habits recibido de {update.effective_user.full_name} (ID: {update.effective_user.id}).")
    
    # Aquí deberías cargar tus hábitos desde la DB o una lista predefinida
    # Por ahora, usaremos una lista de ejemplo
    available_habits = {
        1: "Ejercicio - Recuerda hacer tu rutina de ejercicio diaria",
        2: "Meditacion - Dedica 10 minutos a meditar",
        3: "Leer - Lee un libro durante 30 minutos",
        4: "Hidratacion - No olvides beber suficiente agua",
        5: "Dormir - Cumple tus 7 horas de sueño",
        6: "Medicar - Recuerda tomar tus medicamentos",
        7: "Aprende - Todos los días se aprende algo nuevo",
        8: "Descansa - Toma un descanso de 5 minutos cada hora en tu trabajo",
        9: "Busca a los Niños - No olvides buscar a los niños al colegio",
        10: "Limpieza - Dedica 15 minutos a limpiar tu casa",
        11: "Planifica el día - Dedica 10 minutos a planificar tu día",
        12: "Revisa tus finanzas - Revisa tus gastos e ingresos"
    }

    habits_list_text = "\n".join([f"**{_id}**: {desc}" for _id, desc in available_habits.items()])

    await update.message.reply_text(
        f"Hábitos disponibles para mejorar:\n{habits_list_text}\n\n"
        "Escribe el **ID del hábito** que deseas añadir a tu lista personal. "
        "O envía /cancel para terminar."
    )
    # Devuelve el estado para la siguiente entrada
    return SELECTING_HABIT_ID

async def add_habit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la entrada del ID del hábito y lo añade al usuario."""
    user_input = update.message.text
    user_id = update.effective_user.id
    logger.info(f"Recibido input '{user_input}' para añadir hábito de usuario {user_id}.")

    try:
        habit_id = int(user_input)
        # Aquí iría tu lógica para añadir el hábito a la base de datos para este usuario.
        # Por ejemplo: db_manager.add_user_habit(user_id, habit_id)
        
        # Simulación de éxito
        await update.message.reply_text(f"¡Hábito con ID **{habit_id}** añadido exitosamente a tu lista!")
        logger.info(f"Hábito {habit_id} añadido para el usuario {user_id}.")
        return ConversationHandler.END # ¡CRÍTICO! Termina la conversación

    except ValueError:
        await update.message.reply_text(
            "Eso no parece un ID de hábito válido. Por favor, ingresa un **número**."
        )
        logger.warning(f"Entrada inválida '{user_input}' para añadir hábito del usuario {user_id}.")
        return SELECTING_HABIT_ID # Permanece en el mismo estado para que reintente

    except Exception as e:
        logger.error(f"Error al añadir hábito para el usuario {user_id} con ID '{user_input}': {e}", exc_info=True)
        await update.message.reply_text(
            "Lo siento, hubo un error al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde."
        )
        return ConversationHandler.END # En caso de error inesperado, termina la conversación

async def cancel_habits_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación para añadir hábitos."""
    logger.info(f"Conversación de hábitos cancelada por {update.effective_user.full_name} (ID: {update.effective_user.id}).")
    await update.message.reply_text("Operación cancelada. ¡Cuando quieras añadir más hábitos, solo escribe /habits de nuevo!")
    return ConversationHandler.END # ¡CRÍTICO! Termina la conversación

async def send_daily_habits(context: ContextTypes.DEFAULT_TYPE):
    """
    Envía recordatorios diarios de hábitos a todos los usuarios.
    Esta función sería programada por JobQueue.
    """
    logger.info("Iniciando el envío de recordatorios diarios de hábitos.")
    
    users = get_all_users() # Obtiene todos los usuarios de la base de datos

    for user in users:
        user_habits_records = get_user_habits(user.id) # Obtiene los hábitos personalizados del usuario
        
        if not user_habits_records:
            logger.info(f"Usuario {user.telegram_id} no tiene hábitos personalizados. Saltando.")
            continue

        habit_messages_list = [] # Cambiado el nombre de la variable para evitar confusiones si la llamas "habit_messages" en otros sitios
        for uh in user_habits_records:
            default_habit_list = get_habits(uh.habit_id) 
            if default_habit_list:
                default_habit = default_habit_list[0]
                habit_messages_list.append(f"- {default_habit.description}")
            else:
                habit_messages_list.append(f"- Hábito con ID {uh.habit_id} (descripción no encontrada)")

        if habit_messages_list:
            # Construye la parte de los hábitos por separado y luego insértala.
            # Esto puede ayudar a aislar el problema si es con la expresión compleja.
            habits_formatted_text = '\n'.join(habit_messages_list)

            message_text = f"""
¡Hola {user.first_name}!
Es hora de recordar tus hábitos de hoy:
{habits_formatted_text}

¡Vamos a por ello! 💪
"""
            message_text = message_text.strip() 

            try:
                await context.bot.send_message(chat_id=user.telegram_id, text=message_text)
                logger.info(f"Recordatorio enviado a {user.username} (ID: {user.telegram_id}).")
            except Exception as e:
                logger.error(f"Error al enviar recordatorio al usuario {user.telegram_id}: {e}")
        else:
            logger.info(f"No hay hábitos para enviar al usuario {user.telegram_id}.")

    logger.info("Envío de recordatorios diarios de hábitos finalizado.")