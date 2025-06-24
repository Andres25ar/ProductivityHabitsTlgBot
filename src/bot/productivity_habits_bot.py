# src/bot/productivity_habits_bot.py

import os
import logging
from datetime import datetime, time, timedelta
import pytz
import dateparser
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler

from src.database.database_interation import (
    create_user_if_not_exists, get_user_by_telegram_id,
    load_default_habits, set_task, get_incomplete_tasks, mark_as_completed,
    delete_task_by_id, complete_task_by_id, update_user_timezone, get_user_tasks
)
from src.database.db_context import get_db, init_db_async
from src.utils.scheduler import (
    setup_scheduler, get_scheduler, schedule_instant_reminder,
    schedule_recurring_task, schedule_all_due_tasks_for_persistence
)
from src.utils.logger_config import configure_logging
from src.handlers.set_timezone_handler import setup_set_timezone_handler
from src.handlers.weather_handler import get_weather_conversation_handler # Importar el handler de clima

configure_logging()
logger = logging.getLogger(__name__)

TASK_DESCRIPTION, TASK_DUE_DATE, TASK_FREQUENCY = range(3)
COMPLETE_TASK_SELECT_ID, DELETE_TASK_SELECT_ID = range(3, 5)


async def post_init(application: Application):
    logger.info("post_init: Inicializando la base de datos y configurando el scheduler...")
    
    await init_db_async()
    logger.info("post_init: Base de datos inicializada (tablas creadas si no existían).")

    async with get_db() as db:
        await load_default_habits(db)
    logger.info("post_init: Hábitos por defecto cargados (si no existían).")

    scheduler_instance = setup_scheduler() 
    
    await schedule_all_due_tasks_for_persistence() 
    logger.info("post_init: Tareas pendientes programadas.")
    logger.info("post_init: Bot y scheduler listos para operar.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    user_first_name = user.first_name
    username = user.username
    last_name = user.last_name

    logger.info(f"Comando /start recibido de usuario: {user_id} ({user_first_name})")

    async with get_db() as db:
        new_user = await create_user_if_not_exists(db, user_id, username, user_first_name, last_name)

    await update.message.reply_html(
        rf"¡Hola {user.mention_html()}! Soy tu bot de hábitos. "
        "Para empezar, configura tu zona horaria con /set_timezone."
    )
    logger.info(f"Usuario {user_id} ({user_first_name}) procesado. Mensaje de bienvenida enviado.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Aquí están los comandos disponibles:\n"
                                     "/start - Inicia el bot\n"
                                     "/help - Muestra esta ayuda\n"
                                     "/set_timezone - Configura tu zona horaria\n"
                                     "/new_task - Crea una nueva tarea\n"
                                     "/list_tasks - Lista tus tareas incompletas\n"
                                     "/complete_task - Marca una tarea como completada\n"
                                     "/delete_task - Elimina una tarea\n"
                                     "/clima - Consulta el clima de una ciudad\n" # Añadido a la ayuda
                                     "/cancel - Cancela cualquier operación en curso")


async def new_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Por favor, ingresa la descripción de tu nueva tarea:')
    return TASK_DESCRIPTION

async def received_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['current_task_description'] = update.message.text
    await update.message.reply_text('¿Para cuándo es la tarea? (Ej: "mañana a las 9am", "25/12/2025", "hoy 18:00", "Lunes", "en 3 días" o "sin fecha"). Si no aplica, escribe "ninguna"):')
    return TASK_DUE_DATE

async def received_task_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    due_date_str = update.message.text.lower().strip()
    parsed_due_date = None
    user_id = update.effective_user.id

    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id)
        if not user or not user.timezone:
            await update.message.reply_text(
                "Por favor, configura tu zona horaria con /set_timezone antes de añadir tareas con fecha."
                "Puedes decir 'ninguna' para continuar sin fecha."
            )
            return TASK_DUE_DATE

        user_tz = None
        try:
            user_tz = ZoneInfo(user.timezone)
        except ZoneInfoNotFoundError:
            logger.error(f"Zona horaria '{user.timezone}' no válida para el usuario {user_id}. Usando UTC.")
            user_tz = ZoneInfo('UTC')

    if due_date_str == "ninguna":
        parsed_due_date = None
    else:
        try:
            parsed_date_time = dateparser.parse(
                due_date_str,
                settings={
                    'TIMEZONE': user_tz.key,
                    'TO_TIMEZONE': 'UTC',
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
    frequency_str = update.message.text.lower().strip()
    frequency = None
    
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
        async with get_db() as db:
            task = await set_task(db, user_id, description, due_date, frequency)
        
        await update.message.reply_text(f'Tarea "{task.description}" (ID: `{task.id}`) creada exitosamente.')
        logger.info(f"Tarea '{task.description}' (ID: {task.id}) creada por el usuario {user_id}.")

        if task.due_date:
            if task.frequency in [None, 'una_vez']:
                await schedule_instant_reminder(task.id)
            elif task.frequency in ['diaria', 'semanal', 'mensual', 'anual']:
                await schedule_recurring_task(task.id, task.frequency)
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


async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    async with get_db() as db:
        user = await get_user_by_telegram_id(db, user_id)
        if not user:
            await update.message.reply_text("Por favor, usa /start primero para registrarte.")
            return

        tasks = await get_incomplete_tasks(db, user.id)
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


async def complete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        async with get_db() as db:
            tasks = await get_incomplete_tasks(db, user_id)
        if not tasks:
            await update.message.reply_text("No tienes tareas incompletas para marcar como completadas.")
            return ConversationHandler.END

        context.user_data['tasks_to_complete'] = {str(task.id): task for task in tasks}

        message = "Por favor, ingresa el ID de la tarea que quieres marcar como completada:\n"
        for i, task in enumerate(tasks):
            due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M') if task.due_date else "Sin fecha"
            freq_str = f" ({task.frequency.capitalize()})" if task.frequency else ""
            message += f"ID: {task.id} - {task.description} (Vence: {due_date_str}){freq_str}\n"
        await update.message.reply_text(message)
        return COMPLETE_TASK_SELECT_ID
    except Exception as e:
        logger.error(f"Error en complete_task_command para el usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al iniciar el proceso de completar tarea.')
        return ConversationHandler.END

async def confirm_complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    task_id_str = update.message.text
    user_id = update.effective_user.id

    try:
        task_id = int(task_id_str)
        
        task_obj = context.user_data.get('tasks_to_complete', {}).get(task_id_str)

        if not task_obj:
            await update.message.reply_text("ID de tarea no válido. Por favor, ingresa un ID de la lista.")
            return COMPLETE_TASK_SELECT_ID
        
        if task_obj.frequency and task_obj.frequency != 'una_vez':
            await update.message.reply_text(f"La tarea '{task_obj.description}' (ID: `{task_id}`) es recurrente. No se marca como 'completada' permanentemente. Simplemente la estás registrando como hecha para este ciclo.")
            logger.info(f"Usuario {user_id} intentó 'completar' tarea recurrente {task_id}. No se marcó como 'completed=True'.")
            return ConversationHandler.END


        async with get_db() as db:
            success = await complete_task_by_id(db, task_id)
            
            if success:
                await update.message.reply_text(f"Tarea {task_id} marcada como completada exitosamente. ¡Felicidades!")
                logger.info(f"Tarea {task.id} marcada como completada por el usuario {user_id}.")
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

async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    try:
        async with get_db() as db:
            tasks = await get_user_tasks(db, user_id)
        if not tasks:
            await update.message.reply_text("No tienes tareas para eliminar.")
            return ConversationHandler.END

        context.user_data['tasks_to_delete'] = {str(task.id): task for task in tasks}

        message = "Por favor, ingresa el ID de la tarea que quieres eliminar:\n"
        for i, task in enumerate(tasks):
            status = "Completada" if task.completed else "Incompleta"
            due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M') if task.due_date else "Sin fecha"
            freq_str = f" ({task.frequency.capitalize()})" if task.frequency else ""
            message += f"ID: {task.id} - {task.description} (Estado: {status}, Vence: {due_date_str}){freq_str}\n"
        await update.message.reply_text(message)
        return DELETE_TASK_SELECT_ID
    except Exception as e:
        logger.error(f"Error en delete_task_command para el usuario {user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al iniciar el proceso de eliminación de tarea.')
        return ConversationHandler.END

async def confirm_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    task_id_str = update.message.text
    user_id = update.effective_user.id

    try:
        task_id = int(task_id_str)
        task_obj = context.user_data.get('tasks_to_delete', {}).get(task_id_str)

        if not task_obj:
            await update.message.reply_text("ID de tarea no válido. Por favor, ingresa un ID de la lista.")
            return DELETE_TASK_SELECT_ID

        async with get_db() as db:
            success = await delete_task_by_id(db, task_id)
            if success:
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
                logger.info(f"Tarea {task.id} eliminada por el usuario {user_id}.")
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

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Operación cancelada.')
    return ConversationHandler.END

def main() -> None:
    logger.info("Iniciando la aplicación principal del bot...")
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN no está configurado. ¡El bot no podrá iniciarse!")
        raise ValueError("El token de Telegram no está configurado en las variables de entorno.")

    application = Application.builder().token(token).post_init(post_init).build()
    logger.info("Aplicación de Telegram construida.")

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    setup_set_timezone_handler(application)

    # Añadir el ConversationHandler para el clima
    application.add_handler(get_weather_conversation_handler())

    new_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('new_task', new_task_command)],
        states={
            TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_description)],
            TASK_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_due_date)],
            TASK_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_frequency)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )
    application.add_handler(new_task_conv_handler)

    application.add_handler(CommandHandler("list_tasks", list_tasks_command))

    complete_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('complete_task', complete_task_command)],
        states={
            COMPLETE_TASK_SELECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_complete_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )
    application.add_handler(complete_task_conv_handler)

    delete_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('delete_task', delete_task_command)],
        states={
            DELETE_TASK_SELECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_task)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )
    application.add_handler(delete_task_conv_handler)

    logger.info("Iniciando polling del bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
