# src/database/database_interation.py

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import text
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

# Importar solo los modelos que necesita, no AsyncSessionLocal o engine
from src.database.models import Base, User, DefaultHabit, UserHabit, UserTask 

db_logger = logging.getLogger(__name__)
db_logger.setLevel(logging.INFO)

async def create_user_if_not_exists(db: AsyncSession, telegram_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
    db_logger.info(f"Comprobando si existe el usuario con Telegram ID: {telegram_id}")
    result = await db.execute(select(User).filter(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        db_logger.info(f"Usuario con Telegram ID {telegram_id} no encontrado. Creando nuevo.")
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        db_logger.info(f"Nuevo usuario creado con Telegram ID: {telegram_id}")
    else:
        db_logger.debug(f"Usuario con Telegram ID: {telegram_id} ya existe.")
    return user

async def load_default_habits(db: AsyncSession):
    db_logger.info("Cargando hábitos por defecto...")
    default_habits = [
        {"name": "Ejercicio", "description": "Recuerda hacer tu rutina de ejercicio diaria"},
        {"name": "Meditacion", "description": "Dedica 10 minutos a meditar"},
        {"name": "Leer", "description": "Lee un libro durante 30 minutos"},
        {"name": "Hidratacion", "description": "No olvides beber suficiente agua"},
        {"name": "Dormir", "description": "Cumple tus 7 horas de sueño"},
        {"name": "Medicar", "description": "Recuerda tomar tus medicamentos"},
        {"name": "Aprende", "description": "Todos los días se aprende algo nuevo"},
        {"name": "Descansa", "description": "Toma un descanso de 5 minutos cada hora en tu trabajo"},
        {"name": "Busca a los Niños", "description": "No olvides buscar a los niños al colegio"},
        {"name": "Limpieza", "description": "Dedica 15 minutos a limpiar tu casa"},
        {"name": "Planifica el día", "description": "Dedica 10 minutos a planificar tu día"},
        {"name": "Revisa tus finanzas", "description": "Revisa tus gastos e ingresos diarios"},
        {"name": "Practica un hobby", "description": "Dedica tiempo a tu pasatiempo favorito"},
        {"name": "Socializa", "description": "Habla con un amigo o familiar hoy"},
        {"name": "Escucha música", "description": "Disfruta de tu música favorita durante 30 minutos"},
        {"name": "Escribe un diario", "description": "Escribe tus pensamientos y reflexiones del día"},
    ]
    try:
        for habit in default_habits:
            result = await db.execute(select(DefaultHabit).filter_by(name=habit["name"]))
            existing_habit = result.scalar_one_or_none()
            if not existing_habit:
                new_habit = DefaultHabit(**habit)
                db.add(new_habit)
                db_logger.debug(f"Añadiendo hábito por defecto: '{habit['name']}'")
            else:
                db_logger.debug(f"Hábito por defecto '{habit['name']}' ya existe. Saltando.")
        await db.commit()
        db_logger.info(f"Hábitos por defecto cargados o ya existían. {len(default_habits)} hábitos procesados.")
    except Exception as e:
        await db.rollback()
        db_logger.error(f"Error al cargar hábitos por defecto: {e}", exc_info=True)


async def get_user_by_telegram_id(db: AsyncSession, telegram_id: int) -> User | None:
    db_logger.debug(f"[DB] Buscando usuario con telegram_id: {telegram_id}")
    result = await db.execute(select(User).filter(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        db_logger.debug(f"[DB] Usuario {telegram_id} encontrado: {user.first_name}, timezone actual: {user.timezone}")
    else:
        db_logger.debug(f"[DB] Usuario con telegram_id {telegram_id} no encontrado.")
    return user

async def update_user_timezone(db: AsyncSession, user_id: int, new_timezone: str) -> bool:
    db_logger.info(f"Intentando actualizar la zona horaria para user_id {user_id} a '{new_timezone}'")
    try:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            try:
                ZoneInfo(new_timezone)
            except ZoneInfoNotFoundError:
                db_logger.error(f"Zona horaria '{new_timezone}' no es válida según ZoneInfo para user_id {user_id}.")
                return False

            user.timezone = new_timezone
            await db.commit()
            await db.refresh(user)
            db_logger.info(f"Zona horaria para usuario {user_id} actualizada a: {user.timezone}")
            return True
        else:
            db_logger.warning(f"No se encontró el usuario con user_id {user_id} para actualizar la zona horaria.")
            return False
    except Exception as e:
        await db.rollback()
        db_logger.error(f"Error al actualizar la zona horaria para user_id {user_id}: {e}", exc_info=True)
        raise

async def set_task(db: AsyncSession, user_id: int, description: str, due_date: datetime = None, frequency: str = None) -> UserTask:
    db_logger.info(f"Intentando guardar nueva tarea para user_id: {user_id}, descripción: '{description}', fecha: {due_date}, frecuencia: {frequency}")
    try:
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(f"Usuario con ID {user_id} no encontrado.")

        user_timezone_str = user.timezone if user.timezone else 'UTC'
        try:
            user_tz = ZoneInfo(user_timezone_str)
        except ZoneInfoNotFoundError:
            db_logger.warning(f"Zona horaria '{user_timezone_str}' no válida para el usuario {user_id}. Usando UTC.")
            user_tz = ZoneInfo('UTC')

        if due_date is None:
            current_time_in_user_tz = datetime.now(user_tz)
            due_date_utc = current_time_in_user_tz.astimezone(ZoneInfo('UTC'))
            db_logger.debug(f"due_date no proporcionada, usando fecha y hora actual ({current_time_in_user_tz}) convertida a UTC: {due_date_utc}")
        else:
            if due_date.tzinfo is None:
                due_date_aware_in_user_tz = due_date.replace(tzinfo=user_tz)
                due_date_utc = due_date_aware_in_user_tz.astimezone(ZoneInfo('UTC'))
                db_logger.debug(f"due_date naive proporcionada ({due_date}), asumiendo TZ de usuario ({user_tz}) y convirtiendo a UTC: {due_date_utc}")
            else:
                due_date_utc = due_date.astimezone(ZoneInfo('UTC'))
                db_logger.debug(f"due_date aware proporcionada ({due_date}), convirtiendo a UTC: {due_date_utc}")

        task = UserTask(
            user_id=user_id,
            description=description,
            due_date=due_date_utc,
            completed=False,
            frequency=frequency
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        db_logger.info(f"Tarea {task.id} ('{task.description}') guardada exitosamente para usuario {user_id}. due_date UTC: {task.due_date}")
        return task
    except Exception as e:
        await db.rollback()
        db_logger.error(f"Error al guardar la tarea para user_id {user_id} en la DB: {e}", exc_info=True)
        raise

async def get_task(db: AsyncSession, task_id: int) -> UserTask | None:
    db_logger.debug(f"Buscando tarea con ID: {task_id}")
    try:
        result = await db.execute(select(UserTask).filter(UserTask.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            db_logger.debug(f"Tarea {task_id} encontrada: '{task.description}'.")
        else:
            db_logger.debug(f"Tarea con ID {task_id} no encontrada.")
        return task
    except Exception as e:
        db_logger.error(f"Error al obtener tarea con ID {task_id}: {e}", exc_info=True)
        raise

async def get_user_tasks(db: AsyncSession, user_id: int) -> list[UserTask]:
    db_logger.debug(f"Obteniendo todas las tareas para user_id: {user_id}")
    try:
        result = await db.execute(select(UserTask).filter(UserTask.user_id == user_id).order_by(UserTask.due_date))
        tasks = result.scalars().all()
        db_logger.info(f"Encontradas {len(tasks)} tareas para user_id: {user_id}.")
        return tasks
    except Exception as e:
        db_logger.error(f"Error al obtener todas las tareas para user_id {user_id}: {e}", exc_info=True)
        raise

async def get_incomplete_tasks(db: AsyncSession, user_id: int) -> list[UserTask]:
    db_logger.debug(f"Obteniendo tareas incompletas para user_id: {user_id}")
    try:
        result = await db.execute(
            select(UserTask).filter(
                UserTask.user_id == user_id,
                UserTask.completed == False
            ).order_by(UserTask.due_date)
        )
        tasks = result.scalars().all()
        db_logger.info(f"Encontradas {len(tasks)} tareas incompletas para user_id: {user_id}.")
        return tasks
    except Exception as e:
        db_logger.error(f"Error al obtener tareas incompletas para user_id {user_id}: {e}", exc_info=True)
        raise

async def get_all_incomplete_tasks(db: AsyncSession) -> list[UserTask]:
    """
    Obtiene todas las tareas incompletas de TODOS los usuarios.
    Útil para el scheduler al inicio del bot.
    """
    db_logger.debug("Obteniendo TODAS las tareas incompletas para el scheduler.")
    try:
        result = await db.execute(
            select(UserTask).filter(UserTask.completed == False).order_by(UserTask.due_date)
        )
        tasks = result.scalars().all()
        db_logger.info(f"Encontradas {len(tasks)} tareas incompletas en total para el scheduler.")
        return tasks
    except Exception as e:
        db_logger.error(f"Error al obtener todas las tareas incompletas para el scheduler: {e}", exc_info=True)
        raise

async def get_completed_tasks(db: AsyncSession, user_id: int) -> list[UserTask]:
    db_logger.debug(f"Obteniendo tareas completadas para user_id: {user_id}")
    try:
        result = await db.execute(
            select(UserTask).filter(
                UserTask.user_id == user_id,
                UserTask.completed == True
            ).order_by(UserTask.due_date)
        )
        tasks = result.scalars().all()
        db_logger.info(f"Encontradas {len(tasks)} tareas completadas para user_id: {user_id}.")
        return tasks
    except Exception as e:
        db_logger.error(f"Error al obtener tareas completadas para user_id {user_id}: {e}", exc_info=True)
        raise

async def mark_as_completed(db: AsyncSession, task_id: int) -> bool:
    db_logger.info(f"Marcando tarea ID {task_id} como completada.")
    try:
        result = await db.execute(select(UserTask).filter(UserTask.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            task.completed = True
            await db.commit()
            await db.refresh(task)
            db_logger.info(f"Tarea {task_id} marcada como completada exitosamente.")
            return True
        else:
            db_logger.warning(f"No se encontró la tarea con ID {task_id} para marcar como completada.")
            return False
    except Exception as e:
        await db.rollback()
        db_logger.error(f"Error al marcar tarea {task_id} como completada: {e}", exc_info=True)
        raise

async def delete_task_by_id(db: AsyncSession, task_id: int) -> bool:
    db_logger.info(f"Intentando eliminar tarea con ID: {task_id}")
    try:
        result = await db.execute(select(UserTask).filter(UserTask.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            await db.delete(task)
            await db.commit()
            db_logger.info(f"Tarea {task_id} eliminada exitosamente.")
            return True
        else:
            db_logger.warning(f"No se encontró la tarea con ID {task_id} para eliminar.")
            return False
    except Exception as e:
        await db.rollback()
        db_logger.error(f"Error al eliminar la tarea con ID {task_id}: {e}", exc_info=True)
        raise

async def complete_task_by_id(db: AsyncSession, task_id: int) -> bool:
    db_logger.info(f"Intentando marcar como completada la tarea con ID: {task_id}")
    try:
        result = await db.execute(select(UserTask).filter(UserTask.id == task_id))
        task = result.scalar_one_or_none()
        if task:
            task.completed = True
            await db.commit()
            await db.refresh(task)
            db_logger.info(f"Tarea {task_id} marcada como completada exitosamente.")
            return True
        else:
            db_logger.warning(f"No se encontró la tarea con ID {task_id} para marcar como completada.")
            return False
    except Exception as e:
        await db.rollback()
        db_logger.error(f"Error al marcar como completada la tarea con ID {task_id}: {e}", exc_info=True)
        raise