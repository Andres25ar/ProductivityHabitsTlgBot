import logging
from datetime import datetime, timedelta
from dateutil import parser as dateparser_lib # Renombrar para evitar conflicto con variables
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

# Importar funciones de base de datos
from src.database.db_context import get_db
from src.database.database_interation import set_task, get_user_by_telegram_id, get_incomplete_tasks, mark_as_completed, delete_task_by_id, get_user_tasks
from src.utils.scheduler import schedule_instant_reminder, schedule_recurring_task

# Configuración del logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Estados para la conversación de nueva tarea
TASK_DESCRIPTION, TASK_DUE_DATE, TASK_FREQUENCY = range(3)

# Diccionario para almacenar el estado de la conversación por usuario
# {chat_id: {"description": "...", "due_date_str": "..."}}
user_task_data = {}

# Diccionario para almacenar el ID de la tarea a completar/eliminar
# {chat_id: task_id}
pending_task_action = {}


async def new_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para crear una nueva tarea."""
    logger.debug("new_task_command iniciado.")
    user_id = update.effective_user.id
    user_task_data[user_id] = {} # Inicializa los datos de la tarea para este usuario
    await update.message.reply_text("Por favor, ingresa la descripción de tu nueva tarea:")
    return TASK_DESCRIPTION


async def received_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda la descripción de la tarea y pide la fecha de vencimiento."""
    logger.debug("received_task_description iniciado.")
    user_id = update.effective_user.id
    user_task_data[user_id]["description"] = update.message.text
    await update.message.reply_text(
        "¿Para cuándo es la tarea? (Ej: \"mañana a las 9am\", \"25/12/2025\", \"hoy 18:00\", \"Lunes\", \"en 3 días\" o \"sin fecha\"). Si no aplica, escribe \"ninguna\"):"
    )
    return TASK_DUE_DATE


async def _parse_due_date_input(user_input: str, user_timezone_str: str) -> datetime | None:
    """
    Intenta parsear la entrada del usuario a un objeto datetime consciente de la zona horaria del usuario.
    Si el input es 'ninguna' o 'sin fecha', retorna None.
    Asegura que las fechas de día de la semana apunten siempre a la próxima ocurrencia.
    """
    user_input_lower = user_input.lower().strip()
    if user_input_lower in ["ninguna", "sin fecha"]:
        logger.debug(f"Input de fecha '{user_input}' interpretado como sin fecha.")
        return None

    try:
        user_tz = ZoneInfo(user_timezone_str)
    except ZoneInfoNotFoundError:
        logger.warning(f"Zona horaria '{user_timezone_str}' no válida. Usando UTC para parseo de fecha.")
        user_tz = ZoneInfo('UTC')

    now_in_user_tz = datetime.now(user_tz)

    try:
        # Intentar parsear con dateutil.parser
        # Añadir un 'settings' para preferir el futuro para fechas relativas
        parsed_dt_naive = dateparser_lib.parse(
            user_input,
            fuzzy=True,
            dayfirst=False, # Ajustar según preferencia regional
            yearfirst=False, # Ajustar según preferencia regional
            settings={'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': now_in_user_tz} # <--- Clave para preferir futuro y contexto
        )
        # Hacerlo consciente de la zona horaria del usuario
        parsed_dt_aware_user_tz = parsed_dt_naive.replace(tzinfo=user_tz)
        logger.debug(f"Fecha parseada inicialmente (UTC antes de ajuste): {parsed_dt_aware_user_tz.astimezone(ZoneInfo('UTC'))}")

        # Lógica adicional para días de la semana (ej. "Martes") para asegurar la próxima ocurrencia
        # Esto es crucial si el parser por defecto no siempre toma la "próxima" ocurrencia cuando la hora ya pasó hoy.
        if parsed_dt_aware_user_tz.date() < now_in_user_tz.date():
            # Si el parser dio una fecha en el pasado (ej. "Martes" del mes anterior)
            # y la entrada no incluía un mes/año explícito que indicara el pasado,
            # entonces asumir que el usuario quería el próximo.
            # Esta parte se maneja mejor con PREFER_DATES_FROM='future', pero es un buen fallback.
            delta_days = (now_in_user_tz.date() - parsed_dt_aware_user_tz.date()).days
            if delta_days > 0 and parsed_dt_aware_user_tz.year == now_in_user_tz.year: # Para evitar saltos a años anteriores
                parsed_dt_aware_user_tz += timedelta(days=(7 - (parsed_dt_aware_user_tz.weekday() - now_in_user_tz.weekday()) % 7) % 7)
                logger.debug(f"Ajustada fecha pasada a próxima ocurrencia: {parsed_dt_aware_user_tz.astimezone(ZoneInfo('UTC'))}")
        
        # Ajuste para el caso "Martes 14:45" hoy Martes 14:46
        # Si la fecha parseada es hoy, pero la hora ya pasó, avanzar una semana
        if parsed_dt_aware_user_tz.date() == now_in_user_tz.date() and parsed_dt_aware_user_tz < now_in_user_tz:
             parsed_dt_aware_user_tz += timedelta(weeks=1)
             logger.debug(f"Ajustada fecha de hoy pasada a la próxima semana: {parsed_dt_aware_user_tz.astimezone(ZoneInfo('UTC'))}")


        logger.debug(f"Fecha de vencimiento parseada y ajustada (en TZ de usuario): {parsed_dt_aware_user_tz.strftime('%Y-%m-%d %H:%M %Z')}")
        return parsed_dt_aware_user_tz
    except ValueError as e:
        logger.error(f"Error al parsear fecha '{user_input}': {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error inesperado al parsear fecha '{user_input}': {e}", exc_info=True)
        return None


async def received_task_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda la fecha de vencimiento y pide la frecuencia."""
    logger.debug("received_task_due_date iniciado.")
    user_id = update.effective_user.id
    user_input = update.message.text

    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id)
        if not user:
            await update.message.reply_text("Lo siento, no pude encontrar tus datos de usuario. Por favor, intenta /start de nuevo.")
            return ConversationHandler.END

    user_timezone = user.timezone if user.timezone else 'UTC'
    
    # Aquí se llama a la función de parseo
    parsed_date = await _parse_due_date_input(user_input, user_timezone)

    if parsed_date is None and user_input.lower().strip() not in ["ninguna", "sin fecha"]:
        await update.message.reply_text(
            "No pude entender la fecha. Por favor, intenta de nuevo con un formato como \"mañana 9am\", \"25/12/2025\", \"hoy 18:00\", \"Lunes\", \"en 3 días\" o \"sin fecha\"."
        )
        return TASK_DUE_DATE # Permanece en el mismo estado para que el usuario reingrese la fecha

    user_task_data[user_id]["due_date"] = parsed_date
    user_task_data[user_id]["due_date_str"] = user_input # Guardar la cadena original para depuración si es necesario

    # Ofrecer opciones de frecuencia
    frequency_options = [["diaria"], ["semanal"], ["mensual"], ["anual"], ["ninguna"]]
    reply_markup = ReplyKeyboardMarkup(frequency_options, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "¿Con qué frecuencia debe repetirse esta tarea? (Ej: \"diaria\", \"semanal\", \"mensual\", \"anual\" o \"ninguna\"):",
        reply_markup=reply_markup
    )
    return TASK_FREQUENCY


async def received_task_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Guarda la frecuencia y crea la tarea."""
    logger.debug("received_task_frequency iniciado.")
    user_id = update.effective_user.id
    frequency = update.message.text.lower()

    if frequency not in ["diaria", "semanal", "mensual", "anual", "ninguna"]:
        await update.message.reply_text(
            "Frecuencia no válida. Por favor, elige entre \"diaria\", \"semanal\", \"mensual\", \"anual\" o \"ninguna\"."
        )
        return TASK_FREQUENCY

    user_task_data[user_id]["frequency"] = frequency if frequency != "ninguna" else None # Si es "ninguna", se guarda como None

    description = user_task_data[user_id]["description"]
    due_date = user_task_data[user_id]["due_date"]
    
    # Eliminar los datos de la tarea una vez que se han obtenido para evitar persistencia accidental
    del user_task_data[user_id] 

    logger.debug("Entrando al contexto de la base de datos para obtener usuario.")
    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id)
        if not user:
            logger.error(f"Usuario no encontrado en la DB para Telegram ID: {user_id}. No se pudo crear la tarea.")
            await update.message.reply_text("Lo siento, hubo un error al procesar tu usuario. Por favor, intenta /start de nuevo.")
            return ConversationHandler.END

        try:
            logger.debug(f"Intentando guardar tarea: desc='{description}', due_date='{due_date}', freq='{frequency}' para internal_user_id={user.id} (Telegram ID: {user.telegram_id})")
            task = await set_task(db, user.id, description, due_date, frequency)
            
            if task:
                await update.message.reply_text(f"Tarea \"{task.description}\" (ID: `{task.id}`) creada exitosamente.", reply_markup=ReplyKeyboardRemove())
                logger.info(f"Tarea '{task.description}' (ID: {task.id}) creada por el usuario {user_id}.")
                logger.debug(f"Tarea guardada exitosamente. Task ID: {task.id}, Description: {task.description}")

                if task.due_date: # Solo programar si hay una fecha de vencimiento
                    if task.frequency is None or task.frequency == 'una vez': # Considerar 'ninguna' como 'una vez'
                        logger.debug(f"Programando recordatorio instantáneo para tarea {task.id}")
                        await schedule_instant_reminder(task.id)
                    else:
                        logger.debug(f"Programando tarea recurrente para tarea {task.id} con frecuencia {task.frequency}")
                        await schedule_recurring_task(task.id, task.frequency)
                else:
                    logger.info(f"Tarea {task.id} creada sin fecha de vencimiento, no se programa recordatorio.")

            else:
                logger.error(f"Error desconocido al crear la tarea para el usuario {user_id}. set_task retornó None.")
                await update.message.reply_text("Lo siento, ocurrió un error al crear la tarea. Por favor, inténtalo de nuevo.", reply_markup=ReplyKeyboardRemove())

        except Exception as e:
            logger.error(f"Error al crear y programar la tarea para el usuario {user_id}: {e}", exc_info=True)
            await update.message.reply_text("Lo siento, ocurrió un error al crear la tarea. Por favor, inténtalo de nuevo.", reply_markup=ReplyKeyboardRemove())
    
    logger.debug("received_task_frequency finalizado exitosamente.")
    return ConversationHandler.END


async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista las tareas incompletas del usuario."""
    logger.debug("list_tasks_command iniciado.")
    user_id = update.effective_user.id
    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id)
        if not user:
            await update.message.reply_text("Lo siento, no pude encontrar tus datos de usuario. Por favor, intenta /start de nuevo.")
            return

        tasks = await get_incomplete_tasks(db, user.id)
        if not tasks:
            await update.message.reply_text("No tienes tareas incompletas. ¡Bien hecho!")
        else:
            response = "Tus tareas incompletas:\n"
            for task in tasks:
                due_date_str = "Sin fecha"
                if task.due_date and user.timezone:
                    try:
                        user_tz = ZoneInfo(user.timezone)
                        local_due_date = task.due_date.astimezone(user_tz)
                        due_date_str = local_due_date.strftime('%Y-%m-%d %H:%M %Z')
                    except ZoneInfoNotFoundError:
                        logger.error(f"Zona horaria '{user.timezone}' no válida para el usuario {user_id} al mostrar tareas.")
                        due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC') # Fallback a UTC si la TZ es inválida
                elif task.due_date: # Si hay fecha pero no hay TZ de usuario, mostrar en UTC
                    due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')

                frequency_str = f" (Frecuencia: {task.frequency})" if task.frequency else ""
                response += f"ID: `{task.id}` - {task.description} (Vence: {due_date_str}){frequency_str}\n"
            await update.message.reply_text(response)
    logger.info(f"Comando /list_tasks ejecutado por el usuario {user_id}.")


async def complete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para marcar una tarea como completada."""
    logger.debug("complete_task_command iniciado.")
    user_id = update.effective_user.id
    
    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id)
        if not user:
            await update.message.reply_text("Lo siento, no pude encontrar tus datos de usuario. Por favor, intenta /start de nuevo.")
            return ConversationHandler.END
        
        tasks = await get_incomplete_tasks(db, user.id) # Listar solo incompletas
        if not tasks:
            await update.message.reply_text("No tienes tareas incompletas para marcar como completadas. ¡Bien hecho!")
            return ConversationHandler.END
        
        task_list_str = "Tus tareas incompletas:\n"
        keyboard = []
        for task in tasks:
            due_date_str = "Sin fecha"
            if task.due_date and user.timezone:
                try:
                    user_tz = ZoneInfo(user.timezone)
                    local_due_date = task.due_date.astimezone(user_tz)
                    due_date_str = local_due_date.strftime('%Y-%m-%d %H:%M %Z')
                except ZoneInfoNotFoundError:
                    due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            elif task.due_date:
                due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            
            task_list_str += f"ID: `{task.id}` - {task.description} (Vence: {due_date_str})\n"
            keyboard.append([str(task.id)]) # Crear un botón por cada ID de tarea

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            f"{task_list_str}\nPor favor, ingresa el ID de la tarea que deseas marcar como completada:",
            reply_markup=reply_markup
        )
    return 1 # Estado para recibir el ID de la tarea


async def confirm_complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma y marca una tarea como completada."""
    logger.debug("confirm_complete_task iniciado.")
    user_id = update.effective_user.id
    try:
        task_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("ID de tarea inválido. Por favor, ingresa un número.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    async with get_db() as db:
        # Primero, verifica que la tarea exista y pertenezca al usuario
        task_to_complete = await get_task_by_id(db, task_id)
        if not task_to_complete or task_to_complete.user_id != user_id:
            await update.message.reply_text("No se encontró una tarea con ese ID o no te pertenece.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        if task_to_complete.frequency and task_to_complete.frequency != 'una vez':
            # Si es una tarea recurrente, no la marcamos como completada, solo informamos.
            await update.message.reply_text(
                f"La tarea \"{task_to_complete.description}\" (ID: `{task_id}`) es una tarea recurrente y no puede ser marcada como completada de forma permanente. Puedes eliminarla con /delete_task si ya no la necesitas.",
                reply_markup=ReplyKeyboardRemove()
            )
            logger.info(f"Usuario {user_id} intentó 'completar' tarea recurrente {task_id}.")
            return ConversationHandler.END
        else:
            success = await mark_as_completed(db, task_id)
            if success:
                await update.message.reply_text(f"Tarea \"{task_to_complete.description}\" (ID: `{task_id}`) marcada como completada.", reply_markup=ReplyKeyboardRemove())
                # Eliminar el job del scheduler si era una tarea de una vez
                job_id_prefix_once = f"instant_reminder_{task_id}"
                for job in list(context.job_queue.jobs()): # Asumiendo que el job_queue está disponible en context
                    if job.id and job.id.startswith(job_id_prefix_once):
                        job.remove()
                        logger.info(f"Job APScheduler {job.id} eliminado después de marcar tarea {task_id} como completada.")
                
            else:
                await update.message.reply_text("Lo siento, no pude marcar la tarea como completada. Inténtalo de nuevo.", reply_markup=ReplyKeyboardRemove())
    
    return ConversationHandler.END


async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para eliminar una tarea."""
    logger.debug("delete_task_command iniciado.")
    user_id = update.effective_user.id

    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id)
        if not user:
            await update.message.reply_text("Lo siento, no pude encontrar tus datos de usuario. Por favor, intenta /start de nuevo.")
            return ConversationHandler.END
        
        tasks = await get_user_tasks(db, user.id) # Listar todas las tareas (completas e incompletas)
        if not tasks:
            await update.message.reply_text("No tienes tareas para eliminar.")
            return ConversationHandler.END
        
        task_list_str = "Tus tareas:\n"
        keyboard = []
        for task in tasks:
            status = "✅" if task.completed else "⏳"
            due_date_str = "Sin fecha"
            if task.due_date and user.timezone:
                try:
                    user_tz = ZoneInfo(user.timezone)
                    local_due_date = task.due_date.astimezone(user_tz)
                    due_date_str = local_due_date.strftime('%Y-%m-%d %H:%M %Z')
                except ZoneInfoNotFoundError:
                    due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            elif task.due_date:
                due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')

            frequency_str = f" (Frecuencia: {task.frequency})" if task.frequency else ""
            task_list_str += f"ID: `{task.id}` - {status} {task.description} (Vence: {due_date_str}){frequency_str}\n"
            keyboard.append([str(task.id)]) # Crear un botón por cada ID de tarea

        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

        await update.message.reply_text(
            f"{task_list_str}\nPor favor, ingresa el ID de la tarea que deseas eliminar:",
            reply_markup=reply_markup
        )
    pending_task_action[user_id] = "delete" # Indicar que la próxima entrada es para eliminar
    return 1 # Estado para recibir el ID de la tarea


async def confirm_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma y elimina una tarea."""
    logger.debug("confirm_delete_task iniciado.")
    user_id = update.effective_user.id
    try:
        task_id = int(update.message.text)
    except ValueError:
        await update.message.reply_text("ID de tarea inválido. Por favor, ingresa un número.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    async with get_db() as db:
        # Primero, verifica que la tarea exista y pertenezca al usuario
        task_to_delete = await get_task_by_id(db, task_id)
        if not task_to_delete or task_to_delete.user_id != user_id:
            await update.message.reply_text("No se encontró una tarea con ese ID o no te pertenece.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        success = await delete_task_by_id(db, task_id)
        if success:
            await update.message.reply_text(f"Tarea \"{task_to_delete.description}\" (ID: `{task_id}`) eliminada.", reply_markup=ReplyKeyboardRemove())
            logger.info(f"Tarea {task_id} eliminada por el usuario {user_id}.")
            
            # Eliminar jobs asociados del scheduler
            job_id_prefix_instant = f"instant_reminder_{task_id}"
            job_id_prefix_recurring = f"recurring_task_{task_id}"

            # Iterar sobre una copia de la lista de jobs para evitar RuntimeError por modificación durante iteración
            for job in list(context.job_queue.jobs()): # Asumiendo que el job_queue está disponible en context
                if job.id and (job.id.startswith(job_id_prefix_instant) or job.id.startswith(job_id_prefix_recurring)):
                    try:
                        job.remove()
                        logger.info(f"Job APScheduler {job.id} eliminado del scheduler tras eliminar tarea {task_id}.")
                    except Exception as e:
                        logger.error(f"Error al eliminar job {job.id} del scheduler APScheduler: {e}", exc_info=True)
            
        else:
            await update.message.reply_text("Lo siento, no pude eliminar la tarea. Inténtalo de nuevo.", reply_markup=ReplyKeyboardRemove())
    
    # Limpiar el estado de acción pendiente
    if user_id in pending_task_action:
        del pending_task_action[user_id]
    
    return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela cualquier operación en curso."""
    user_id = update.effective_user.id
    if user_id in user_task_data:
        del user_task_data[user_id]
    if user_id in pending_task_action:
        del pending_task_action[user_id]
    await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

