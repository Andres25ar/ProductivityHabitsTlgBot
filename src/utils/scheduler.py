# src/utils/scheduler.py

import asyncio
import datetime
import os
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from telegram import Bot

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session, joinedload
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger

from src.database.db_context import AsyncSessionLocal, get_db
from src.database.database_interation import get_task_by_id, get_user_by_telegram_id, mark_as_completed
from src.database.models import UserTask, User
import sqlalchemy as sa
from sqlalchemy import select

load_dotenv()

# --- Configuración del Logger ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    file_handler = logging.FileHandler('scheduler.log')
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


# --- Variables de Entorno ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

SQLALCHEMY_JOBSTORE_DATABASE_URL = os.getenv("DATABASE_URL").replace("+asyncpg", "")

if not TELEGRAM_BOT_TOKEN:
    logger.warning("Advertencia: TELEGRAM_BOT_TOKEN no está configurado en scheduler.py. Esto podría causar fallos al enviar mensajes.")
if not SQLALCHEMY_JOBSTORE_DATABASE_URL:
    logger.critical("Error: SQLALCHEMY_JOBSTORE_DATABASE_URL no está configurada en scheduler.py. El scheduler persistente no funcionará.")
    raise ValueError("SQLALCHEMY_JOBSTORE_DATABASE_URL must be set for the persistent scheduler.")


# --- Instancia de APScheduler (se configura y se inicia externamente) ---
persistent_scheduler = AsyncIOScheduler()

def setup_scheduler():
    global scheduler
    scheduler = persistent_scheduler

    try:
        salta_timezone = ZoneInfo('America/Argentina/Salta')

        scheduler.configure(
            jobstores={
                "default": {
                    'type': 'sqlalchemy',
                    'url': SQLALCHEMY_JOBSTORE_DATABASE_URL
                }
            },
            executors={
                'default': AsyncIOExecutor()
            },
            job_defaults={
                'coalesce': False,
                'max_instances': 1
            },
            timezone=salta_timezone
        )
        logger.info("APScheduler persistente configurado exitosamente.")

        if not scheduler.running:
            scheduler.start()
            logger.info("APScheduler persistente iniciado.")
        
        return scheduler

    except Exception as e:
        logger.critical(f"Error al configurar o iniciar APScheduler persistente: {e}", exc_info=True)
        raise


def get_scheduler():
    if not persistent_scheduler.running:
        logger.warning("Intentando obtener el scheduler pero no está en ejecución. Asegúrate de llamar setup_scheduler() primero.")
    return persistent_scheduler


# --- Funciones de recordatorio para APScheduler ---

async def send_reminder(bot_token: str, chat_id: int, message: str, task_id: int = None):
    """Envía un recordatorio de una tarea al usuario."""
    bot = Bot(token=bot_token)
    try:
        await bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Recordatorio enviado a {chat_id}: {message}")

        if task_id:
            async with get_db() as db:
                task = await get_task_by_id(db, task_id)

                if task and (task.frequency is None or task.frequency == 'una vez'):
                    await mark_as_completed(db, task_id)
                    logger.info(f"Tarea única {task_id} marcada como completada después de enviar recordatorio.")
                    job_id_prefix_once = f"instant_reminder_{task_id}"
                    
                    for job in list(persistent_scheduler.get_jobs()): 
                        if job.id and job.id.startswith(job_id_prefix_once):
                            try:
                                persistent_scheduler.remove_job(job.id)
                                logger.info(f"Job APScheduler persistente para tarea única {job.id} eliminado después de completarse.")
                            except Exception as e:
                                logger.error(f"Error al eliminar job {job.id} del scheduler persistente: {e}", exc_info=True)
                elif task and task.frequency != 'una vez':
                    logger.debug(f"Tarea recurrente {task_id} no marcada como completada automáticamente.")
                else:
                    logger.warning(f"Tarea {task_id} no encontrada o ya procesada al intentar marcar como completada.")
    except Exception as e:
        logger.error(f"Error al enviar el recordatorio al chat {chat_id}: {e}", exc_info=True)
    # ELIMINADA LA LÍNEA: finally: await bot.session.close()


async def schedule_all_due_tasks_for_persistence():
    """
    Carga todas las tareas pendientes de la base de datos y las programa
    en el scheduler persistente (APScheduler).
    Se ejecuta al inicio del bot para restaurar los jobs.
    """
    logger.info("Cargando y programando tareas pendientes en el scheduler persistente...")
    if not persistent_scheduler.running:
        logger.warning("Scheduler no está en ejecución. No se pueden programar tareas pendientes.")
        return

    logger.info("Limpiando todos los jobs existentes del scheduler para asegurar un estado limpio...")
    for job in persistent_scheduler.get_jobs():
        try:
            persistent_scheduler.remove_job(job.id)
            logger.info(f"Job {job.id} eliminado durante la limpieza inicial.")
        except Exception as e:
            logger.error(f"Error al intentar eliminar el job {job.id} durante la limpieza inicial: {e}", exc_info=True)

    async with get_db() as db:
        now_aware_scheduler_tz = datetime.datetime.now(persistent_scheduler.timezone)

        result = await db.execute(
            select(UserTask)
            .options(joinedload(UserTask.user))
            .filter(
                UserTask.completed == False,
                UserTask.due_date != None,
                UserTask.due_date > now_aware_scheduler_tz.astimezone(ZoneInfo('UTC')),
                (UserTask.frequency == 'una vez') | (UserTask.frequency == None)
            )
        )
        tasks_to_schedule = result.scalars().all()

        logger.info(f"Se encontraron {len(tasks_to_schedule)} tareas únicas pendientes para programar.")
        for task in tasks_to_schedule:
            if task.user and task.user.telegram_id:
                await schedule_instant_reminder(task.id)
            else:
                logger.warning(f"No se pudo programar recordatorio para tarea única {task.id}: Usuario o Telegram ID no encontrado.")

        result = await db.execute(
            select(UserTask)
            .options(joinedload(UserTask.user))
            .filter(
                UserTask.completed == False,
                UserTask.due_date != None,
                UserTask.frequency.in_(['diaria', 'semanal', 'mensual', 'anual'])
            )
        )
        recurring_tasks = result.scalars().all()

        logger.info(f"Se encontraron {len(recurring_tasks)} tareas recurrentes pendientes para programar.")
        for task in recurring_tasks:
            if task.user and task.user.telegram_id:
                await schedule_recurring_task(task.id, task.frequency)
            else:
                logger.warning(f"No se pudo programar recordatorio para tarea recurrente {task.id}: Usuario o Telegram ID no encontrado.")


async def schedule_instant_reminder(task_id: int):
    logger.debug(f"Intentando programar recordatorio instantáneo para la tarea {task_id} en scheduler persistente...")

    async with get_db() as db:
        task = await get_task_by_id(db, task_id)

        if task and task.due_date and task.user and task.user.telegram_id:
            task_due_datetime_utc_aware = task.due_date

            run_date_in_scheduler_tz = task_due_datetime_utc_aware.astimezone(persistent_scheduler.timezone)

            now_in_scheduler_tz = datetime.datetime.now(persistent_scheduler.timezone)

            if run_date_in_scheduler_tz <= now_in_scheduler_tz:
                logger.debug(f"La fecha de recordatorio para la tarea {task.id} ya pasó ({run_date_in_scheduler_tz}), omitiendo programación.")
                return

            chat_id = task.user.telegram_id
            label = "Recordatorio"
            notify_time = run_date_in_scheduler_tz

            display_due_date = task_due_datetime_utc_aware
            time_str = "N/A"
            if task.user.timezone:
                try:
                    user_tz = ZoneInfo(task.user.timezone)
                    display_due_date = display_due_date.astimezone(user_tz)
                    time_str = display_due_date.strftime('%Y-%m-%d %H:%M %Z')
                except ZoneInfoNotFoundError:
                    logger.error(f"Zona horaria '{task.user.timezone}' no válida para el usuario {task.user.telegram_id}. Usando UTC.")
                    time_str = display_due_date.strftime('%Y-%m-%d %H:%M UTC')
                except Exception as e:
                    logger.error(f"Error al formatear TZ de usuario {task.user.timezone} para tarea {task.id}: {e}", exc_info=True)
                    time_str = display_due_date.strftime('%Y-%m-%d %H:%M UTC')
            else:
                time_str = display_due_date.strftime('%Y-%m-%d %H:%M UTC')

            message = f"⏰ {label}: ¡Es hora de '{task.description}'!\nProgramada para: {time_str}."
            job_id = f"instant_reminder_{task.id}"

            if persistent_scheduler.get_job(job_id):
                persistent_scheduler.remove_job(job_id)
                logger.info(f"Eliminado job persistente existente: {job_id}")

            try:
                persistent_scheduler.add_job(
                    send_reminder,
                    DateTrigger(run_date=notify_time),
                    args=[TELEGRAM_BOT_TOKEN, chat_id, message, task.id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600
                )
                job = persistent_scheduler.get_job(job_id)
                if job and job.next_run_time:
                    next_run_time_str = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')
                else:
                    next_run_time_str = "N/A"
                logger.info(f"Recordatorio único programado en scheduler persistente: '{label}' para la tarea {task.id} (usuario {chat_id}) a las {notify_time.strftime('%Y-%m-%d %H:%M:%S %Z')}. Próximo disparo: {next_run_time_str}")
            except Exception as e:
                logger.error(f"Error al añadir job instantáneo {job_id} al scheduler: {e}", exc_info=True)
        else:
            logger.warning(f"No se encontró la tarea {task_id}, no tiene fecha de vencimiento, o el usuario/telegram_id no está asociado/disponible para programar recordatorio instantáneo.")
    logger.debug(f"DEBUG: async with block exited successfully for instant reminder task {task_id}.")

async def schedule_recurring_task(task_id: int, frequency: str):
    logger.debug(f"Intentando programar recordatorio recurrente para la tarea {task_id} con frecuencia '{frequency}' en scheduler persistente...")

    async with get_db() as db:
        task = await get_task_by_id(db, task_id)

        if task and task.due_date and task.user and task.user.telegram_id:
            chat_id = task.user.telegram_id
            
            task_due_datetime_utc_aware = task.due_date

            display_due_date = task_due_datetime_utc_aware
            time_str = "N/A"
            if task.user.timezone:
                try:
                    user_tz = ZoneInfo(task.user.timezone)
                    display_due_date = display_due_date.astimezone(user_tz)
                    time_str = display_due_date.strftime('%Y-%m-%d %H:%M %Z')
                except ZoneInfoNotFoundError:
                    logger.error(f"Zona horaria '{task.user.timezone}' no válida para el usuario {task.user.telegram_id}. Usando UTC.")
                    time_str = display_due_date.strftime('%Y-%m-%d %H:%M UTC')
                except Exception as e:
                    logger.error(f"Error al formatear TZ de usuario {task.user.timezone} para tarea {task.id}: {e}", exc_info=True)
                    time_str = display_due_date.strftime('%Y-%m-%d %H:%M UTC')
            else:
                time_str = display_due_date.strftime('%Y-%m-%d %H:%M UTC')

            message = f"🔔 Recordatorio recurrente: ¡Es hora de '{task.description}'!\nProgramada para: {time_str}."

            start_date_in_scheduler_tz = task_due_datetime_utc_aware.astimezone(persistent_scheduler.timezone)

            job_id_prefix = f"recurring_task_{task.id}"

            trigger_type = CronTrigger
            trigger_kwargs = {
                'hour': start_date_in_scheduler_tz.hour,
                'minute': start_date_in_scheduler_tz.minute,
                'second': start_date_in_scheduler_tz.second,
                'timezone': persistent_scheduler.timezone
            }
            logger.debug(f"DEBUG: CronTrigger kwargs antes de añadir job: {trigger_kwargs}")

            if frequency == 'diaria':
                pass
            elif frequency == 'semanal':
                trigger_kwargs['day_of_week'] = start_date_in_scheduler_tz.weekday()
            elif frequency == 'mensual':
                trigger_kwargs['day'] = start_date_in_scheduler_tz.day
            elif frequency == 'anual':
                trigger_kwargs['month'] = start_date_in_scheduler_tz.month
                trigger_kwargs['day'] = start_date_in_scheduler_tz.day
            else:
                logger.error(f"Frecuencia '{frequency}' no soportada para programación recurrente para la tarea {task.id}.")
                return

            now_in_scheduler_tz = datetime.datetime.now(persistent_scheduler.timezone)
            
            if start_date_in_scheduler_tz > now_in_scheduler_tz:
                trigger_kwargs['start_date'] = start_date_in_scheduler_tz
                logger.debug(f"Configurando start_date para el trigger recurrente: {start_date_in_scheduler_tz}")
            else:
                logger.debug(f"La fecha de inicio para la tarea recurrente {task.id} ({start_date_in_scheduler_tz}) ya pasó o es ahora. El trigger comenzará en la próxima ocurrencia basada en el patrón cron.")

            logger.debug(f"DEBUG: CronTrigger final kwargs antes de añadir job: {trigger_kwargs}")

            for existing_job in list(persistent_scheduler.get_jobs()):
                if existing_job.id and existing_job.id.startswith(job_id_prefix):
                    persistent_scheduler.remove_job(existing_job.id)
                    logger.info(f"Eliminado job recurrente existente del scheduler persistente: {existing_job.id}")

            job_id = f"{job_id_prefix}_{frequency}"

            try:
                persistent_scheduler.add_job(
                    send_reminder,
                    trigger=trigger_type(**trigger_kwargs),
                    args=[TELEGRAM_BOT_TOKEN, chat_id, message, None],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600
                )
                job = persistent_scheduler.get_job(job_id)
                if job and job.next_run_time:
                    next_run_time_str = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')
                else:
                    next_run_time_str = "N/A"
                logger.info(f"Recordatorio recurrente programado en scheduler persistente: '{task.description}' (ID: {task.id}) para el usuario {chat_id} con frecuencia '{frequency}'. Próximo disparo: {next_run_time_str}")
            except Exception as e:
                logger.error(f"Error al añadir job recurrente {job_id} al scheduler: {e}", exc_info=True)
        else:
            logger.warning(f"No se pudo programar el recordatorio recurrente para la tarea {task.id}: no encontrado, sin fecha, o el usuario/telegram_id no disponible.")
    logger.debug(f"DEBUG: async with block exited successfully for recurring task {task_id}.")
