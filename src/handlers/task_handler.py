# src/handlers/task_handler.py

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError # Para validar y usar zonas horarias
import dateparser # Importar dateparser

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters, CommandHandler, ConversationHandler

from src.database.db_context import get_db # Importa get_db desde db_context
from src.database.database_interation import (
    get_user_by_telegram_id, set_task, get_incomplete_tasks, complete_task_by_id, delete_task_by_id, get_user_tasks
) # Asegúrate de que estas funciones existan en database_interation.py
from src.utils.scheduler import (
    get_scheduler, schedule_instant_reminder, schedule_recurring_task
) # Asegúrate de importar estas funciones

logger = logging.getLogger(__name__)

# Estados para el manejo de conversación de tareas
# Asegúrate de que estos rangos no colisionen si tienes otros ConversationHandlers
TASK_DESCRIPTION, TASK_DUE_DATE, TASK_FREQUENCY = range(3)
COMPLETE_TASK_SELECT_ID, DELETE_TASK_SELECT_ID = range(3, 5)


# --- Handlers de Tareas ---

# NEW_TASK CONVERSATION
async def new_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para crear una nueva tarea."""
    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {update.effective_user.id} en /new_task. No se puede responder.")
        return ConversationHandler.END
    await update.message.reply_text('Por favor, ingresa la descripción de tu nueva tarea:')
    return TASK_DESCRIPTION

async def received_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la descripción de la tarea y pide la fecha de vencimiento."""
    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {update.effective_user.id} al recibir descripción. No se puede responder.")
        return ConversationHandler.END
    context.user_data['current_task_description'] = update.message.text
    await update.message.reply_text('¿Para cuándo es la tarea? (Ej: "mañana a las 9am", "25/12/2025", "hoy 18:00", "Lunes", "en 3 días" o "sin fecha"). Si no aplica, escribe "ninguna"):')
    return TASK_DUE_DATE

async def received_task_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la fecha de vencimiento de la tarea y pide la frecuencia."""
    due_date_str = update.message.text.lower().strip()
    parsed_due_date = None
    user_id = update.effective_user.id

    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_id} al recibir fecha de vencimiento. No se puede responder.")
        return ConversationHandler.END

    # Usar async with para el context manager de la base de datos
    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id) # Llamada asíncrona
        if not user or not user.timezone:
            await update.message.reply_text(
                "Por favor, configura tu zona horaria con /set_timezone antes de añadir tareas con fecha. "
                "Puedes decir 'ninguna' para continuar sin fecha."
            )
            return TASK_DUE_DATE # Permite reintentar o decir 'ninguna'

        user_tz = None
        try:
            user_tz = ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            logger.error(f"Zona horaria '{user.timezone}' no válida para el usuario {user_id}. Usando UTC.")
            user_tz = ZoneInfo('UTC') # Fallback a UTC si la TZ del usuario es inválida

    if due_date_str == "ninguna":
        parsed_due_date = None
    else:
        try:
            parsed_date_time = dateparser.parse(
                due_date_str,
                settings={
                    'TIMEZONE': user_tz.key,
                    'TO_TIMEZONE': 'UTC', # Almacenar siempre en UTC en la DB
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'PREFER_DATES_FROM': 'future'
                }
            )
            if parsed_date_time:
                parsed_due_date = parsed_date_time
            else:
                await update.message.reply_text(
                    'No pude entender la fecha y hora. Por favor, intenta con un formato como "25/12/2025 18:00", "mañana a las 9am", "Lunes 14:00" o escribe "ninguna".'
                )
                return TASK_DUE_DATE
        except Exception as e:
            logger.error(f"Error al parsear fecha '{due_date_str}' para usuario {user_id}: {e}", exc_info=True)
            await update.message.reply_text(
                'Ocurrió un error al procesar la fecha. Por favor, intenta con un formato más simple o escribe "ninguna".'
            )
            return TASK_DUE_DATE

    context.user_data['current_task_due_date'] = parsed_due_date
    await update.message.reply_text('¿Con qué frecuencia debe repetirse esta tarea? (Ej: "diaria", "semanal", "mensual", "anual" o "ninguna"):')
    return TASK_FREQUENCY

async def received_task_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la frecuencia de la tarea, la guarda y programa recordatorios."""
    frequency_str = update.message.text.lower().strip()
    frequency = None
    
    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {update.effective_user.id} al recibir frecuencia. No se puede responder.")
        return ConversationHandler.END

    valid_frequencies = ["ninguna", "diaria", "semanal", "mensual", "anual"]
    if frequency_str not in valid_frequencies:
        await update.message.reply_text(f'Frecuencia no reconocida. Por favor, usa una de las siguientes: {", ".join(valid_frequencies)}.')
        return TASK_FREQUENCY

    if frequency_str != "ninguna":
        frequency = frequency_str

    user_id = update.effective_user.id
    description = context.user_data['current_task_description']
    due_date = context.user_data['current_task_due_date']

    try:
        async with get_db() as db: # Usar async with
            task = await set_task(db, user_id, description, due_date, frequency) # Llamada asíncrona
        
        await update.message.reply_text(f'Tarea "{task.description}" (ID: `{task.id}`) creada exitosamente.')
        logger.info(f"Tarea '{task.description}' (ID: {task.id}) creada por el usuario {user_id}.")

        if task.due_date:
            # Los argumentos de schedule_instant_reminder y schedule_recurring_task cambiaron
            # Ahora solo necesitan el task_id y la frecuencia (para recurring)
            if task.frequency in [None, 'una_vez']: # 'una_vez' es el string en la DB, no 'una vez'
                await schedule_instant_reminder(task.id) # Llamada asíncrona
            elif task.frequency in ['diaria', 'semanal', 'mensual', 'anual']:
                await schedule_recurring_task(task.id, task.frequency) # Llamada asíncrona
            else:
                logger.warning(f"Tarea {task.id} con frecuencia '{task.frequency}' no pudo ser programada por el scheduler.")
        else:
            await update.message.reply_text("Esta tarea no tiene recordatorio programado ya que no se especificó una fecha de vencimiento.")
            logger.info(f"Tarea {task.id} creada sin fecha de vencimiento, no se programó recordatorio.")

        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error al crear y programar la tarea para el usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al crear la tarea. Por favor, inténtalo de nuevo.')
        return ConversationHandler.END


# LIST_TASKS
async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista las tareas pendientes del usuario."""
    user_id = update.effective_user.id

    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_id} en /list_tasks. No se puede responder.")
        return ConversationHandler.END

    async with get_db() as db: # Usar async with
        user = await get_user_by_telegram_id(db, user_id) # Llamada asíncrona
        if not user:
            await update.message.reply_text("Por favor, usa /start primero para registrarte.")
            return

        tasks = await get_incomplete_tasks(db, user.id) # Llamada asíncrona, asumiendo incompletas
        if tasks:
            response = "Tus tareas pendientes:\n"
            user_tz_str = user.timezone if user.timezone else 'UTC'
            try:
                user_tz = ZoneInfo(user_tz_str)
            except ZoneInfoNotFoundError:
                logger.warning(f"Zona horaria '{user_tz_str}' no válida para el usuario {user_id}. Usando UTC para mostrar tareas.")
                user_tz = ZoneInfo('UTC')

            for task in tasks:
                display_due_date = "Sin fecha"
                if task.due_date:
                    due_date_in_user_tz = task.due_date.astimezone(user_tz)
                    display_due_date = due_date_in_user_tz.strftime('%Y-%m-%d %H:%M %Z')
                
                freq_str = f" ({task.frequency.capitalize()})" if task.frequency else ""
                response += f"- ID: `{task.id}` | `{task.description}` (Vence: {display_due_date}){freq_str}\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("No tienes tareas pendientes. ¡Bien hecho!")
    logger.info(f"Comando /list_tasks ejecutado por el usuario {user_id}.")


# COMPLETE_TASK CONVERSATION
async def complete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para marcar una tarea como completada."""
    user_id = update.effective_user.id
    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_id} en /complete_task. No se puede responder.")
        return ConversationHandler.END
    try:
        async with get_db() as db: # Usar async with
            tasks = await get_incomplete_tasks(db, user_id) # Llamada asíncrona
        if not tasks:
            await update.message.reply_text("No tienes tareas incompletas para marcar como completadas.")
            return ConversationHandler.END

        context.user_data['tasks_to_complete'] = {str(task.id): task for task in tasks}

        message = "Por favor, ingresa el ID de la tarea que quieres marcar como completada:\n"
        for task in tasks:
            due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M') if task.due_date else "Sin fecha"
            freq_str = f" ({task.frequency.capitalize()})" if task.frequency else ""
            message += f"ID: `{task.id}` - `{task.description}` (Vence: {due_date_str}){freq_str}\n"
        await update.message.reply_text(message)
        return COMPLETE_TASK_SELECT_ID
    except Exception as e:
        logger.error(f"Error en complete_task_command para el usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al iniciar el proceso de completar tarea.')
        return ConversationHandler.END

async def confirm_complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma y marca una tarea como completada."""
    task_id_str = update.message.text
    user_id = update.effective_user.id

    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_id} al confirmar completar. No se puede responder.")
        return ConversationHandler.END

    try:
        task_id = int(task_id_str)
        task_obj = context.user_data.get('tasks_to_complete', {}).get(task_id_str)

        if not task_obj:
            await update.message.reply_text("ID de tarea no válido. Por favor, ingresa un ID de la lista.")
            return COMPLETE_TASK_SELECT_ID
        
        # Para tareas recurrentes, solo informamos, no las marcamos como completadas permanentemente.
        if task_obj.frequency and task_obj.frequency != 'una_vez': # 'una_vez' es el string en la DB
            await update.message.reply_text(f"La tarea '{task_obj.description}' (ID: `{task_id}`) es recurrente. No se marca como 'completada' permanentemente. Simplemente la estás registrando como hecha para este ciclo.")
            logger.info(f"Usuario {user_id} intentó 'completar' tarea recurrente {task_id}. No se marcó como 'completed=True'.")
            return ConversationHandler.END # No finalizamos, permitimos que el usuario complete otra tarea si lo desea

        async with get_db() as db: # Usar async with
            success = await complete_task_by_id(db, task_id) # Llamada asíncrona y pasa solo task_id
            
            if success:
                # Si la tarea se marcó como completada y era de una vez, eliminamos el job asociado
                scheduler = get_scheduler()
                job_id = f"instant_reminder_{task_id}"
                if scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
                    logger.info(f"Job {job_id} eliminado del scheduler tras completar la tarea {task_id}.")

                await update.message.reply_text(f"Tarea {task_id} marcada como completada exitosamente. ¡Felicidades!")
                logger.info(f"Tarea {task_id} marcada como completada por el usuario {user_id}.")
            else:
                await update.message.reply_text(f"No se pudo encontrar la tarea con ID {task_id} o ya estaba completada.")
                logger.warning(f"Intento de marcar como completada tarea {task_id} fallido por usuario {user_id}.")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un número válido para el ID de la tarea.")
        return COMPLETE_TASK_SELECT_ID
    except Exception as e:
        logger.error(f"Error en confirm_complete_task para el usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al marcar la tarea como completada. Por favor, inténtalo de nuevo.')
        return ConversationHandler.END

# DELETE_TASK CONVERSATION
async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para eliminar una tarea."""
    user_id = update.effective_user.id
    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_id} en /delete_task. No se puede responder.")
        return ConversationHandler.END
    try:
        async with get_db() as db: # Usar async with
            tasks = await get_user_tasks(db, user_id) # Obtener todas las tareas para dar más opciones al eliminar (Llamada asíncrona)
        if not tasks:
            await update.message.reply_text("No tienes tareas para eliminar.")
            return ConversationHandler.END

        context.user_data['tasks_to_delete'] = {str(task.id): task for task in tasks}

        message = "Por favor, ingresa el ID de la tarea que quieres eliminar:\n"
        for task in tasks:
            status = "Completada" if task.completed else "Incompleta"
            due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M') if task.due_date else "Sin fecha"
            freq_str = f" ({task.frequency.capitalize()})" if task.frequency else ""
            message += f"ID: `{task.id}` - `{task.description}` (Estado: {status}, Vence: {due_date_str}){freq_str}\n"
        await update.message.reply_text(message)
        return DELETE_TASK_SELECT_ID
    except Exception as e:
        logger.error(f"Error en delete_task_command para el usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al iniciar el proceso de eliminación de tarea.')
        return ConversationHandler.END

async def confirm_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma y elimina una tarea."""
    task_id_str = update.message.text
    user_id = update.effective_user.id

    if not update.effective_chat:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {user_id} al confirmar eliminar. No se puede responder.")
        return ConversationHandler.END

    try:
        task_id = int(task_id_str)
        task_obj = context.user_data.get('tasks_to_delete', {}).get(task_id_str)

        if not task_obj:
            await update.message.reply_text("ID de tarea no válido. Por favor, ingresa un ID de la lista.")
            return DELETE_TASK_SELECT_ID

        async with get_db() as db: # Usar async with
            success = await delete_task_by_id(db, task_id) # Llamada asíncrona
            if success:
                # Si la tarea se eliminó de la DB, también elimina los jobs asociados del scheduler
                scheduler = get_scheduler()
                
                job_id_instant = f"instant_reminder_{task_id}"
                if scheduler.get_job(job_id_instant):
                    scheduler.remove_job(job_id_instant)
                    logger.info(f"Job instantáneo {job_id_instant} eliminado del scheduler tras eliminar la tarea {task_id}.")
                
                jobs_to_remove = [job.id for job in list(scheduler.get_jobs()) if job.id and job.id.startswith(f"recurring_task_{task_id}")]
                for job_id_rec in jobs_to_remove:
                    scheduler.remove_job(job_id_rec)
                    logger.info(f"Job recurrente {job_id_rec} eliminado del scheduler tras eliminar la tarea {task_id}.")

                await update.message.reply_text(f"Tarea {task_id} eliminada exitosamente.")
                logger.info(f"Tarea {task_id} eliminada por el usuario {user_id}.")
            else:
                await update.message.reply_text(f"No se pudo encontrar la tarea con ID {task_id}.")
                logger.warning(f"Intento de eliminar tarea {task_id} fallido por usuario {user_id}.")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un número válido para el ID de la tarea.")
        return DELETE_TASK_SELECT_ID
    except Exception as e:
        logger.error(f"Error en confirm_delete_task para el usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al eliminar la tarea. Por favor, inténtalo de nuevo.')
        return ConversationHandler.END

async def cancel_command_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela cualquier conversación de tareas en curso."""
    if update.effective_chat:
        await update.message.reply_text('Operación de tarea cancelada.')
    else:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {update.effective_user.id} al cancelar. No se puede responder.")
    return ConversationHandler.END

def setup_task_handlers(application):
    """Registra todos los ConversationHandlers y CommandHandlers de tareas en la aplicación."""
    logger.info("Configurando handlers de tareas...")

    # Conversación para nuevas tareas
    new_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('new_task', new_task_command)],
        states={
            TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_description)],
            TASK_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_due_date)],
            TASK_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_frequency)],
        },
        fallbacks=[CommandHandler('cancelar', cancel_command_tasks)], # Usar /cancelar
    )
    application.add_handler(new_task_conv_handler)

    # Comando para listar tareas
    application.add_handler(CommandHandler("list_tasks", list_tasks_command))

    # Conversación para completar tareas
    complete_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('complete_task', complete_task_command)],
        states={
            COMPLETE_TASK_SELECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_complete_task)],
        },
        fallbacks=[CommandHandler('cancelar', cancel_command_tasks)], # Usar /cancelar
    )
    application.add_handler(complete_task_conv_handler)

    # Conversación para eliminar tareas
    delete_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('delete_task', delete_task_command)],
        states={
            DELETE_TASK_SELECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_task)],
        },
        fallbacks=[CommandHandler('cancelar', cancel_command_tasks)], # Usar /cancelar
    )
    application.add_handler(delete_task_conv_handler)
    logger.info("Handlers de tareas configurados.")
