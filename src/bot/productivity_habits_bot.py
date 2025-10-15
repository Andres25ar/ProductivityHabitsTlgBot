import os
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler

# Importar funciones de interacción con la base de datos
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
from src.handlers.set_timezone_handler import get_set_timezone_conversation_handler 
from src.handlers.weather_handler import get_weather_conversation_handler
from src.handlers.habits_handler import get_habits_conversation_handler
from src.utils.habits_api import send_daily_habits

# Configuración del logger para este módulo
configure_logging()
logger = logging.getLogger(__name__)

# Definición de estados para los ConversationHandlers (conversaciones con el bot)
TASK_DESCRIPTION, TASK_DATE, TASK_TIME, TASK_FREQUENCY = range(4)
COMPLETE_TASK_SELECT_ID, DELETE_TASK_SELECT_ID = range(4, 6)


async def global_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela cualquier conversación en curso y limpia los datos del usuario."""
    logger.info(f"Comando /cancelar recibido de usuario: {update.effective_user.id}. Limpiando user_data.")
    context.user_data.clear()
    
    if update.effective_chat:
        await update.message.reply_text('Operación cancelada.')
    else:
        logger.error(f"No se recibió un objeto de chat válido para el usuario {update.effective_user.id} al cancelar. No se puede responder.")
    return ConversationHandler.END


async def post_init(application: Application):
    """
    Función que se ejecuta después de que la aplicación de Telegram se inicializa.
    Aquí se inicializa la base de datos y se configura el scheduler.
    """
    logger.info("post_init: Inicializando la base de datos y configurando el scheduler...")
    
    await init_db_async()
    logger.info("post_init: Base de datos inicializada (tablas creadas si no existían).")

    async with get_db() as db:
        await load_default_habits(db)
    logger.info("post_init: Hábitos por defecto cargados (si no existían).")

    scheduler_instance = setup_scheduler() 
    await schedule_all_due_tasks_for_persistence() 
    logger.info("post_init: Tareas pendientes y recurrentes programadas en el scheduler.")
    #para configurar el horario de notificacion de los habitos
    notification_times = [
        #esto no esta en el horario del usuario, sino en UTC
        #hora_utc = hora_arg + 3(horas)
        time(hour=6, minute=0),
        time(hour=19, minute=0)
    ]
    for notification_time in notification_times:
        application.job_queue.run_daily(send_daily_habits, time=notification_time)
        logger.info(f"programada las notificaciones diarias de habitos a las {notification_time.strftime('%H:%M')}.")
    logger.info("post_init: Bot y scheduler listos para operar.")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /start. Registra al usuario si es nuevo y le da la bienvenida.
    """
    user = update.effective_user
    user_telegram_id = user.id
    user_first_name = user.first_name
    username = user.username
    last_name = user.last_name

    logger.info(f"Comando /start recibido del usuario: {user_telegram_id} ({user_first_name})")

    async with get_db() as db:
        new_user = await create_user_if_not_exists(db, user_telegram_id, username, user_first_name, last_name)

    await update.message.reply_html(
        rf"¡Hola {user.mention_html()}! Soy tu bot de hábitos y productividad. "
        "Para empezar, configura tu zona horaria con /set_timezone."
    )
    logger.info(f"Usuario {user_telegram_id} ({user_first_name}) procesado. Mensaje de bienvenida enviado.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /help. Muestra una lista de comandos disponibles.
    """
    await update.message.reply_text("Estos son los comandos que puedes usar:\n"
                                     "/start - Inicia el bot y te registra\n"
                                     "/help - Muestra esta ayuda\n"
                                     "/set_timezone - Configura tu zona horaria\n"
                                     "/task - Crea una nueva tarea\n" 
                                     "/list_tasks - Lista tus tareas pendientes\n"
                                     "/complete_task - Marca una tarea como completada\n"
                                     "/delete_task - Elimina una tarea\n"
                                     "/cancelar - Cancela cualquier operación en curso") 


async def new_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Inicia la conversación para crear una nueva tarea.
    Pide la descripción de la tarea.
    """
    if context.args:
        context.user_data['current_task_description'] = " ".join(context.args)
        await update.message.reply_text('¿Para cuándo es la tarea? (Ej: "DD/MM/AAAA" o "ninguna"):')
        return TASK_DATE
    else:
        await update.message.reply_text('Por favor, ingresa la descripción de tu nueva tarea:')
        return TASK_DESCRIPTION

async def received_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Guarda la descripción de la tarea proporcionada por el usuario y pide la fecha de vencimiento.
    Añadida validación para `update.message` y `update.message.text`.
    """
    if not update.message or not update.message.text:
        await update.message.reply_text("Por favor, ingresa una descripción válida para la tarea.")
        return TASK_DESCRIPTION # Quédate en este estado
        
    context.user_data['current_task_description'] = update.message.text
    await update.message.reply_text('¿Para cuándo es la tarea? (Ej: "DD/MM/AAAA" o "ninguna"):')
    return TASK_DATE

async def received_task_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Parsea la fecha de vencimiento ingresada por el usuario y la guarda.
    Luego pide la hora.
    """
    if not update.message or not update.message.text:
        await update.message.reply_text('Por favor, ingresa una fecha válida (Ej: "DD/MM/AAAA" o "ninguna").')
        return TASK_DATE # Quédate en este estado

    date_str = update.message.text.lower().strip()
    telegram_user_id = update.effective_user.id

    if date_str == "ninguna":
        context.user_data['current_task_due_date'] = None
        await update.message.reply_text('¿Con qué frecuencia debe repetirse esta tarea? (Ej: "diaria", "semanal", "mensual", "anual", "una vez" o "ninguna"):')
        return TASK_FREQUENCY
    else:
        try:
            parsed_date_naive = datetime.strptime(date_str, '%d/%m/%Y').date()
            context.user_data['current_task_date'] = parsed_date_naive
            await update.message.reply_text('¿A qué hora debe ser el recordatorio? (Ej: "HH:MM" o "ninguna"):')
            return TASK_TIME
        except ValueError:
            await update.message.reply_text(
                'Formato de fecha inválido. Por favor, usa "DD/MM/AAAA" (ej: "25/12/2025") o escribe "ninguna".'
            )
            return TASK_DATE
        except Exception as e:
            logger.error(f"Error al parsear fecha '{date_str}' para el usuario {telegram_user_id}: {e}", exc_info=True)
            await update.message.reply_text(
                'Ocurrió un error al procesar la fecha. Por favor, intenta con el formato "DD/MM/AAAA" o escribe "ninguna".'
            )
            return TASK_DATE



async def received_task_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Parsea la hora, la combina con la fecha y presenta un menú de botones para la frecuencia.
    """
    if not update.message or not update.message.text:
        await update.message.reply_text('Por favor, ingresa una hora válida (Ej: "HH:MM" o "ninguna").')
        return TASK_TIME

    time_str = update.message.text.lower().strip()
    telegram_user_id = update.effective_user.id
    parsed_due_date = None

    async with get_db() as db:
        user = await get_user_by_telegram_id(db, telegram_user_id)
        if not user or not user.timezone:
            await update.message.reply_text(
                "Por favor, establece tu zona horaria con /set_timezone antes de añadir tareas con fecha."
            )
            return TASK_TIME

    user_tz = ZoneInfo(user.timezone)
    current_task_date = context.user_data.get('current_task_date')

    if time_str == "ninguna":
        if current_task_date:
            parsed_date_time_naive = datetime.combine(current_task_date, time(0, 0))
            # --- LÍNEA CORREGIDA ---
            parsed_due_date_aware = parsed_date_time_naive.replace(tzinfo=user_tz)
            parsed_due_date = parsed_due_date_aware.astimezone(ZoneInfo('UTC'))
    else:
        try:
            parsed_time_naive = datetime.strptime(time_str, '%H:%M').time()
            if current_task_date:
                parsed_date_time_naive = datetime.combine(current_task_date, parsed_time_naive)
                # --- LÍNEA CORREGIDA ---
                parsed_due_date_aware = parsed_date_time_naive.replace(tzinfo=user_tz)
                parsed_due_date = parsed_due_date_aware.astimezone(ZoneInfo('UTC'))

            if parsed_due_date and parsed_due_date < datetime.now(ZoneInfo('UTC')):
                await update.message.reply_text('La fecha y hora proporcionada ya han pasado. Por favor, ingresa una hora futura.')
                return TASK_TIME
        except ValueError:
            await update.message.reply_text('Formato de hora inválido. Usa "HH:MM" (ej: "18:00").')
            return TASK_TIME

    context.user_data['current_task_due_date'] = parsed_due_date

    # ---  MENU DE BOTONES ---
    keyboard = [
        [InlineKeyboardButton("Una sola vez", callback_data="freq_una vez")],
        [InlineKeyboardButton("Diaria", callback_data="freq_diaria")],
        [InlineKeyboardButton("Semanal", callback_data="freq_semanal")],
        [InlineKeyboardButton("Mensual", callback_data="freq_mensual")],
        [InlineKeyboardButton("Anual", callback_data="freq_anual")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('¿Con qué frecuencia debe repetirse?', reply_markup=reply_markup)

    return TASK_FREQUENCY


async def received_task_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Recibe la frecuencia desde el botón, crea la tarea en la DB y la programa.
    """
    query = update.callback_query
    await query.answer()

    # Extrae la frecuencia del callback_data (ej. "freq_diaria" -> "diaria")
    frequency_str = query.data.split('_', 1)[1]

    await query.edit_message_text(f"Frecuencia seleccionada: {frequency_str.capitalize()}. Creando tarea...")

    frequency = None if frequency_str in ["una vez", "ninguna"] else frequency_str

    telegram_user_id = query.from_user.id
    description = context.user_data['current_task_description']
    due_date = context.user_data.get('current_task_due_date')

    try:
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, telegram_user_id)
            if not user:
                await query.message.reply_text("Error: No se encontró tu usuario. Usa /start.")
                return ConversationHandler.END

            task = await set_task(db, user.id, description, due_date, frequency)

        await query.message.reply_text(f'Tarea "{task.description}" (ID: `{task.id}`) creada exitosamente.')
        logger.info(f"Tarea '{task.description}' (ID: {task.id}) creada por {telegram_user_id}.")

        if task.due_date:
            if not task.frequency or task.frequency == 'una vez':
                await schedule_instant_reminder(task.id)
            elif task.frequency in ['diaria', 'semanal', 'mensual', 'anual']:
                await schedule_recurring_task(task.id, task.frequency)

    except Exception as e:
        logger.error(f"Error al crear tarea para {telegram_user_id}: {e}", exc_info=True)
        await query.message.reply_text('Lo siento, ocurrió un error al crear la tarea.')

    finally:
        context.user_data.clear()

    return ConversationHandler.END


async def list_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Maneja el comando /list_tasks. Lista las tareas incompletas del usuario.
    Optimización: Obtener user una sola vez.
    """
    telegram_user_id = update.effective_user.id
    async with get_db() as db:
        user = await get_user_by_telegram_id(db, telegram_user_id)
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
                logger.warning(f"Zona horaria inválida '{user_tz_str}' para el usuario {telegram_user_id}. Usando UTC para mostrar tareas.")
                user_tz = ZoneInfo('UTC') 

            for task in tasks:
                display_due_date = "Sin fecha"
                if task.due_date:
                    if task.due_date.tzinfo is None:
                        task.due_date = task.due_date.replace(tzinfo=ZoneInfo('UTC'))
                    
                    due_date_in_user_tz = task.due_date.astimezone(user_tz)
                    display_due_date = due_date_in_user_tz.strftime('%Y-%m-%d %H:%M %Z')
                
                freq_str = f" (Frecuencia: {task.frequency.capitalize()})" if task.frequency else ""
                response += f"- ID: `{task.id}` | `{task.description}` (Vence: {display_due_date}){freq_str}\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("No tienes tareas pendientes. ¡Buen trabajo!")
    logger.info(f"Comando /list_tasks ejecutado por el usuario {telegram_user_id}.")


async def complete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Inicia el proceso para marcar una tarea como completada.
    Lista las tareas pendientes y pide al usuario el ID de la tarea a completar.
    Optimización: Obtener user y user_tz una sola vez.
    """
    telegram_user_id = update.effective_user.id
    try:
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, telegram_user_id)
            if not user:
                await update.message.reply_text("Por favor, usa /start primero para registrarte.")
                return ConversationHandler.END

            tasks = await get_incomplete_tasks(db, user.id)
        if not tasks:
            await update.message.reply_text("No tienes tareas incompletas para marcar como completadas.")
            return ConversationHandler.END

        context.user_data['tasks_to_complete'] = {str(task.id): task for task in tasks}

        message = "Por favor, ingresa el ID de la tarea que quieres marcar como completada:\n"
        
        user_tz_str = user.timezone if user.timezone else 'UTC'
        try:
            user_tz = ZoneInfo(user_tz_str)
        except ZoneInfoNotFoundError:
            logger.error(f"Zona horaria '{user_tz_str}' no válida para el usuario {telegram_user_id}. Mostrando fecha en UTC.")
            user_tz = ZoneInfo('UTC')

        for task_item in tasks:
            due_date_str = "Sin fecha"
            if task_item.due_date:
                if task_item.due_date.tzinfo is None:
                    task_item.due_date = task_item.due_date.replace(tzinfo=ZoneInfo('UTC'))
                due_date_str = task_item.due_date.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')
            
            freq_str = f" (Frecuencia: {task_item.frequency.capitalize()})" if task_item.frequency else ""
            message += f"ID: {task_item.id} - {task_item.description} (Vence: {due_date_str}){freq_str}\n"
        await update.message.reply_text(message)
        return COMPLETE_TASK_SELECT_ID 
    except Exception as e:
        logger.error(f"Error en complete_task_command para usuario {telegram_user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al iniciar el proceso para completar una tarea.')
        return ConversationHandler.END

async def confirm_complete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Confirma y marca una tarea como completada.
    """
    task_id_str = update.message.text
    telegram_user_id = update.effective_user.id

    try:
        task_id = int(task_id_str)
        
        task_obj = context.user_data.get('tasks_to_complete', {}).get(task_id_str)

        if not task_obj:
            await update.message.reply_text("ID de tarea inválido. Por favor, ingresa un ID de la lista.")
            return COMPLETE_TASK_SELECT_ID 

        if task_obj.frequency and task_obj.frequency != 'una vez' and task_obj.frequency is not None:
            await update.message.reply_text(f"La tarea '{task_obj.description}' (ID: `{task_id}`) es una tarea recurrente. No se puede marcar como 'completada' permanentemente en este contexto. Puedes eliminarla si ya no la necesitas.")
            logger.info(f"Usuario {telegram_user_id} intentó 'completar' tarea recurrente {task_id}.")
            return ConversationHandler.END 

        async with get_db() as db:
            success = await complete_task_by_id(db, task_id) 
            
            if success:
                await update.message.reply_text(f"Tarea {task_id} marcada como completada exitosamente. ¡Felicitaciones!")
                logger.info(f"Tarea {task_obj.id} marcada como completada por el usuario {telegram_user_id}.")
                scheduler = get_scheduler() 
                job_id_instant = str(task_id) 
                if scheduler.get_job(job_id_instant):
                    scheduler.remove_job(job_id_instant)
                    logger.info(f"Job instantáneo {job_id_instant} removido del scheduler después de completar la tarea {task_id}.")
            else:
                await update.message.reply_text(f"No se pudo encontrar la tarea con ID {task_id} o ya estaba completada.")
                logger.warning(f"Intento de marcar como completada la tarea {task_id} falló para el usuario {telegram_user_id}.")
        return ConversationHandler.END 
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un número válido para el ID de la tarea.")
        return COMPLETE_TASK_SELECT_ID 
    except Exception as e:
        logger.error(f"Error en confirm_complete_task para usuario {telegram_user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al marcar la tarea como completada. Por favor, inténtalo de nuevo.')
        return ConversationHandler.END

async def delete_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Inicia el proceso para eliminar una tarea.
    Lista todas las tareas del usuario (completadas e incompletas) y pide el ID de la tarea a eliminar.
    Optimización: Obtener user y user_tz una sola vez.
    """
    telegram_user_id = update.effective_user.id
    try:
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, telegram_user_id)
            if not user:
                await update.message.reply_text("Por favor, usa /start primero para registrarte.")
                return ConversationHandler.END

            tasks = await get_user_tasks(db, user.id) 
        if not tasks:
            await update.message.reply_text("No tienes tareas para eliminar.")
            return ConversationHandler.END

        context.user_data['tasks_to_delete'] = {str(task.id): task for task in tasks}

        message = "Por favor, ingresa el ID de la tarea que quieres eliminar:\n"
        
        user_tz_str = user.timezone if user.timezone else 'UTC'
        try:
            user_tz = ZoneInfo(user_tz_str)
        except ZoneInfoNotFoundError:
            logger.error(f"Zona horaria '{user_tz_str}' no válida para el usuario {telegram_user_id}. Mostrando fecha en UTC.")
            user_tz = ZoneInfo('UTC')

        for task_item in tasks:
            status = "✅ Completada" if task_item.completed else "⏳ Pendiente"
            due_date_str = "Sin fecha"
            if task_item.due_date:
                if task_item.due_date.tzinfo is None:
                    task_item.due_date = task_item.due_date.replace(tzinfo=ZoneInfo('UTC'))
                due_date_str = task_item.due_date.astimezone(user_tz).strftime('%Y-%m-%d %H:%M')

            freq_str = f" (Frecuencia: {task_item.frequency.capitalize()})" if task_item.frequency else ""
            message += f"ID: {task_item.id} - {task_item.description} (Estado: {status}, Vence: {due_date_str}){freq_str}\n"
        await update.message.reply_text(message)
        return DELETE_TASK_SELECT_ID 
    except Exception as e:
        logger.error(f"Error en delete_task_command para usuario {telegram_user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al iniciar el proceso para eliminar una tarea.')
        return ConversationHandler.END

async def confirm_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Confirma y elimina una tarea de la base de datos y del scheduler.
    """
    task_id_str = update.message.text
    telegram_user_id = update.effective_user.id

    try:
        task_id = int(task_id_str)
        task_obj = context.user_data.get('tasks_to_delete', {}).get(task_id_str)

        if not task_obj:
            await update.message.reply_text("ID de tarea inválido. Por favor, ingresa un número de la lista.")
            return DELETE_TASK_SELECT_ID 

        async with get_db() as db:
            success = await delete_task_by_id(db, task_id) 
            if success:
                scheduler = get_scheduler()
                
                job_id_instant = str(task_id) 
                if scheduler.get_job(job_id_instant):
                    scheduler.remove_job(job_id_instant)
                    logger.info(f"Job instantáneo {job_id_instant} removido del scheduler después de eliminar la tarea {task_id}.")
                
                jobs_to_remove = [job.id for job in list(scheduler.get_jobs()) if job.id and job.id.startswith(f"recurring_task_{task_id}")]
                for job_id_rec in jobs_to_remove:
                    scheduler.remove_job(job_id_rec)
                    logger.info(f"Job recurrente {job_id_rec} removido del scheduler después de eliminar la tarea {task_id}.")

                await update.message.reply_text(f"Tarea {task_id} eliminada exitosamente.")
                logger.info(f"Tarea {task_obj.id} eliminada por el usuario {telegram_user_id}.")
            else:
                await update.message.reply_text(f"No se pudo encontrar la tarea con ID {task_id}.")
                logger.warning(f"Intento de eliminar tarea {task_id} falló para el usuario {telegram_user_id}.")
        return ConversationHandler.END 
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un número válido para el ID de la tarea.")
        return DELETE_TASK_SELECT_ID 
    except Exception as e:
        logger.error(f"Error en confirm_delete_task para usuario {telegram_user_id}: {e}", exc_info=True)
        await update.message.reply_text('Lo siento, ocurrió un error al eliminar la tarea. Por favor, inténtalo de nuevo.')
        return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Maneja el comando /cancel. Cancela cualquier conversación o operación en curso.
    """
    context.user_data.clear()
        
    await update.message.reply_text('Operación cancelada.', reply_markup=ForceReply()) 
    return ConversationHandler.END 

def main() -> None:
    #Función principal para iniciar el bot de Telegram. Configura la aplicación
    logger.info("Iniciando la aplicación principal del bot...")
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN no está configurado. ¡El bot no puede iniciarse!")
        raise ValueError("El token de Telegram no está configurado en las variables de entorno.")

    application = Application.builder().token(token).post_init(post_init).build()
    logger.info("Aplicación de Telegram construida.")

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancelar", global_cancel_command))

    application.add_handler(get_set_timezone_conversation_handler())

    new_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('task', new_task_command)],
        states={
            TASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_description)],
            TASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_date)],
            TASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_task_time)],
            TASK_FREQUENCY: [CallbackQueryHandler(received_task_frequency, pattern="^freq_")],
        },
        fallbacks=[CommandHandler('cancelar', global_cancel_command)],
    )

    application.add_handler(new_task_conv_handler) 

    application.add_handler(CommandHandler("list_tasks", list_tasks_command))

    complete_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('complete_task', complete_task_command)],
        states={
            COMPLETE_TASK_SELECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_complete_task)],
        },
        fallbacks=[CommandHandler('cancelar', global_cancel_command)], 
    )
    application.add_handler(complete_task_conv_handler)

    delete_task_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('delete_task', delete_task_command)],
        states={
            DELETE_TASK_SELECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete_task)],
        },
        fallbacks=[CommandHandler('cancelar', global_cancel_command)], 
    )
    application.add_handler(delete_task_conv_handler)

    application.add_handler(get_habits_conversation_handler())

    application.add_handler(get_weather_conversation_handler())

    logger.info("Iniciando polling del bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
