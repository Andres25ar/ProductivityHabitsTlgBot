# src/utils/scheduler.py

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError # Para validar y usar zonas horarias
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import asyncio

# Importar las funciones de interacción de la base de datos con los nombres correctos
from src.database.database_interation import get_task, get_user_by_telegram_id, complete_task_by_id, get_all_incomplete_tasks
from src.database.db_context import get_db

logger = logging.getLogger(__name__)

_scheduler = None # Variable global para mantener la instancia del scheduler

def setup_scheduler() -> AsyncIOScheduler:
    """
    Configura e inicia el APScheduler.
    Retorna la instancia del scheduler.
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
        _scheduler.start()
        logger.info("APScheduler iniciado.")
    return _scheduler

def get_scheduler() -> AsyncIOScheduler:
    """
    Retorna la instancia global del APScheduler.
    Asegúrate de llamar a setup_scheduler() primero.
    """
    if _scheduler is None:
        raise RuntimeError("El scheduler no ha sido configurado. Llama a setup_scheduler() primero.")
    return _scheduler


async def send_task_reminder(task_id: int):
    """
    Función que el scheduler ejecuta para enviar recordatorios de tareas.
    """
    from src.bot.productivity_habits_bot import application # Importación local para evitar circularidad
    
    logger.info(f"Intentando enviar recordatorio para la tarea ID: {task_id}")
    try:
        async with get_db() as db:
            task = await get_task(db, task_id)
            if not task:
                logger.warning(f"Recordatorio para tarea ID {task_id} cancelado: tarea no encontrada en la DB.")
                # Eliminar el job si la tarea no existe
                scheduler = get_scheduler()
                if scheduler.get_job(f"instant_reminder_{task_id}"):
                    scheduler.remove_job(f"instant_reminder_{task_id}")
                    logger.info(f"Job instantáneo {task_id} eliminado del scheduler.")
                # También eliminar trabajos recurrentes si los hay
                jobs_to_remove = [job.id for job in list(scheduler.get_jobs()) if job.id and job.id.startswith(f"recurring_task_{task_id}")]
                for job_id_rec in jobs_to_remove:
                    scheduler.remove_job(job_id_rec)
                    logger.info(f"Job recurrente {job_id_rec} eliminado del scheduler.")
                return

            if task.completed and not task.frequency: # Si es tarea de una vez y ya completada
                logger.info(f"Recordatorio para tarea ID {task_id} no enviado: tarea ya completada y no recurrente.")
                scheduler = get_scheduler()
                if scheduler.get_job(f"instant_reminder_{task_id}"):
                    scheduler.remove_job(f"instant_reminder_{task_id}")
                    logger.info(f"Job instantáneo {task_id} eliminado del scheduler.")
                return

            user = await get_user_by_telegram_id(db, task.user.telegram_id)
            if not user or not user.telegram_id:
                logger.warning(f"Recordatorio para tarea ID {task_id} no enviado: usuario {task.user.telegram_id} no encontrado.")
                return
            
            # Obtener la instancia del bot para enviar el mensaje
            if application and application.bot:
                # Determinar la zona horaria del usuario para el recordatorio
                user_tz_str = user.timezone if user.timezone else 'UTC'
                try:
                    user_tz = ZoneInfo(user_tz_str)
                except ZoneInfoNotFoundError:
                    logger.warning(f"Zona horaria '{user_tz_str}' no válida para usuario {user.telegram_id}. Usando UTC para recordatorio.")
                    user_tz = ZoneInfo('UTC')

                # Formatear la fecha de vencimiento en la zona horaria del usuario si existe
                display_due_date = ""
                if task.due_date:
                    due_date_in_user_tz = task.due_date.astimezone(user_tz)
                    display_due_date = f" (Vence: {due_date_in_user_tz.strftime('%H:%M del %d-%m-%Y %Z')})"

                await application.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"⏰ ¡Recordatorio de tarea! Tienes pendiente: `{task.description}`{display_due_date}"
                )
                logger.info(f"Recordatorio enviado para la tarea ID {task_id} a {user.telegram_id}.")
                
                # Para tareas recurrentes, marcarlas como no completadas para el próximo ciclo
                if task.frequency and task.frequency != 'una_vez':
                    # Esto simula un "reset" para el siguiente ciclo.
                    # No es un "complete", es para que vuelva a ser considerada pendiente.
                    # No usamos complete_task_by_id aquí, ya que queremos que permanezca incompleta para el próximo ciclo.
                    logger.info(f"Tarea recurrente {task_id} recordada, no se marca como completada.")

            else:
                logger.error("La instancia de 'application' o 'application.bot' no está disponible para enviar el mensaje.")
    except Exception as e:
        logger.error(f"Error al enviar recordatorio para la tarea ID {task_id}: {e}", exc_info=True)


async def schedule_instant_reminder(task_id: int):
    """
    Programa un recordatorio único para una tarea.
    """
    scheduler = get_scheduler()
    async with get_db() as db:
        task = await get_task(db, task_id)
        if task and task.due_date and not task.completed:
            job_id = f"instant_reminder_{task.id}"
            scheduler.add_job(
                send_task_reminder,
                DateTrigger(run_date=task.due_date),
                args=[task.id],
                id=job_id,
                replace_existing=True # Reemplazar si ya existe un job con este ID
            )
            logger.info(f"Recordatorio instantáneo para la tarea {task.id} programado para {task.due_date}.")
        else:
            logger.warning(f"No se pudo programar recordatorio instantáneo para la tarea {task_id}: no encontrada, sin fecha de vencimiento o ya completada.")


async def schedule_recurring_task(task_id: int, frequency: str):
    """
    Programa un recordatorio recurrente para una tarea.
    """
    scheduler = get_scheduler()
    async with get_db() as db:
        task = await get_task(db, task_id)
        if task and task.due_date:
            job_id = f"recurring_task_{task.id}"
            # Asegurar que el due_date esté en la zona horaria del usuario para la programación recurrente
            user = await get_user_by_telegram_id(db, task.user.telegram_id)
            user_tz = ZoneInfo(user.timezone if user.timezone else 'UTC')
            
            # Convertir la due_date de UTC a la zona horaria del usuario para la programación con cron
            local_due_date = task.due_date.astimezone(user_tz)

            if frequency == 'diaria':
                # Ejecutar diariamente a la misma hora (en la zona horaria del usuario)
                trigger = CronTrigger(hour=local_due_date.hour, minute=local_due_date.minute, timezone=user_tz)
            elif frequency == 'semanal':
                # Ejecutar semanalmente el mismo día de la semana y a la misma hora
                trigger = CronTrigger(day_of_week=local_due_date.weekday(), hour=local_due_date.hour, minute=local_due_date.minute, timezone=user_tz)
            elif frequency == 'mensual':
                # Ejecutar mensualmente el mismo día del mes y a la misma hora
                trigger = CronTrigger(day=local_due_date.day, hour=local_due_date.hour, minute=local_due_date.minute, timezone=user_tz)
            elif frequency == 'anual':
                # Ejecutar anualmente el mismo mes, día del mes y a la misma hora
                trigger = CronTrigger(month=local_due_date.month, day=local_due_date.day, hour=local_due_date.hour, minute=local_due_date.minute, timezone=user_tz)
            else:
                logger.warning(f"Frecuencia '{frequency}' no reconocida para la tarea recurrente {task.id}. No se programó.")
                return

            scheduler.add_job(
                send_task_reminder,
                trigger,
                args=[task.id],
                id=job_id,
                replace_existing=True
            )
            logger.info(f"Recordatorio recurrente para la tarea {task.id} (frecuencia: {frequency}) programado.")
        else:
            logger.warning(f"No se pudo programar recordatorio recurrente para la tarea {task_id}: no encontrada o sin fecha de vencimiento.")

async def schedule_all_due_tasks_for_persistence():
    """
    Carga todas las tareas pendientes de la base de datos y las programa en el scheduler.
    Esto se ejecuta al inicio del bot para persistir los recordatorios entre reinicios.
    """
    scheduler = get_scheduler()
    logger.info("Programando todas las tareas pendientes al inicio...")
    try:
        async with get_db() as db:
            # Obtener todas las tareas incompletas de la base de datos
            all_incomplete_tasks = await get_all_incomplete_tasks(db) 
            
            for task in all_incomplete_tasks:
                if task.due_date: # Solo programar si tiene fecha de vencimiento
                    if task.frequency in [None, 'una_vez']:
                        # Asegurarse de que el job no se programe para el pasado
                        if task.due_date > datetime.now(task.due_date.tzinfo):
                            await schedule_instant_reminder(task.id)
                        else:
                            logger.info(f"Tarea instantánea {task.id} vencida y no completada. No se programa recordatorio.")
                    elif task.frequency in ['diaria', 'semanal', 'mensual', 'anual']:
                        await schedule_recurring_task(task.id, task.frequency)
                    else:
                        logger.warning(f"Tarea {task.id} con frecuencia '{task.frequency}' no reconocida. No se programó.")
                else:
                    logger.info(f"Tarea {task.id} sin fecha de vencimiento, no se programó recordatorio.")
            logger.info(f"Total de {len(all_incomplete_tasks)} tareas incompletas procesadas para programación al inicio.")
    except Exception as e:
        logger.error(f"Error al programar tareas persistentes al inicio: {e}", exc_info=True)

