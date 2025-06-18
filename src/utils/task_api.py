from src.database.database_interation import Task, SessionLocal, User
from telegram.ext import ConversationHandler
from datetime import datetime, timedelta
import asyncio
from telegram import Bot

# Estados para la conversación
ASK_DESCRIPTION, ASK_TIME = range(2)

async def start_tasks_conversation(update, context):
    session = SessionLocal()
    tasks = Task.get_user_tasks(update.effective_user.id)
    if tasks:
        msg = "Tus tareas:\n"
        for task in tasks:
            status = "✅" if task.completed else "❌"
            msg += f"{task.id}: {task.description} (Para: {task.due_date}) {status}\n"
    else:
        msg = "No tienes tareas registradas.\n"
    msg += "\nEscribe la descripción de la nueva tarea o /cancel para salir."
    await update.message.reply_text(msg)
    session.close()
    return ASK_DESCRIPTION  # Siguiente estado: descripción

async def add_task_description(update, context):
    context.user_data['description'] = update.message.text.strip()
    await update.message.reply_text("¿A qué hora deseas realizar la tarea? (Formato HH:MM, 24hs)")
    return ASK_TIME

from src.database.database_interation import User

async def add_task_time(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    last_name = update.effective_user.last_name

    # Verifica/crea el usuario
    session = SessionLocal()
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        user = User(id=user_id, username=username, first_name=first_name, last_name=last_name)
        session.add(user)
        session.commit()
    session.close()

    description = context.user_data.get('description')
    time_text = update.message.text.strip()
    try:
        task_time = datetime.strptime(time_text, "%H:%M").time()
    except ValueError:
        await update.message.reply_text("Formato de hora inválido. Por favor, usa HH:MM (ejemplo: 14:30).")
        return ASK_TIME

    session = SessionLocal()
    Task.set_task(user_id, description, due_time=task_time)
    await update.message.reply_text("¡Tarea agregada! Escribe otra descripción para agregar más o /cancel para terminar.")
    session.close()
    return ASK_DESCRIPTION


async def list_tasks(update, context):
    session = SessionLocal()
    tasks = Task.get_user_tasks(update.effective_user.id)
    if tasks:
        msg = "Tus tareas:\n"
        for task in tasks:
            status = "✅" if task.completed else "❌"
            msg += f"{task.id}: {task.description} (Para: {task.due_date}) {status}\n"
    else:
        msg = "No tienes tareas registradas."
    await update.message.reply_text(msg)
    session.close()

async def cancel_tasks_conversation(update, context):
    await update.message.reply_text("Selección de tareas finalizada.")
    return ConversationHandler.END

def get_daily_tasks_for_user(user_id):
    session = SessionLocal()
    tasks = Task.get_user_tasks(user_id)
    session.close()
    return tasks

async def notify_user_task(bot: Bot, user_id: int, task):
    await bot.send_message(
        chat_id=user_id,
        text=f"¡Tienes una tarea próxima!\n{task.description}\nProgramada para: {task.due_date.strftime('%H:%M')}"
    )

async def schedule_task_notifications(bot: Bot, user_id: int, task):
    now = datetime.now()
    if isinstance(task.due_date, datetime):
        task_time = task.due_date
    else:
        # Si due_date es solo hora, combinar con hoy
        task_time = datetime.combine(now.date(), task.due_date)
    notifications = [
        ("1 hora antes", task_time - timedelta(hours=1)),
        ("15 minutos antes", task_time - timedelta(minutes=15)),
        ("En la hora", task_time)
    ]
    for label, notify_time in notifications:
        delay = (notify_time - now).total_seconds()
        if delay > 0:
            asyncio.create_task(
                delayed_notification(bot, user_id, task, delay, label)
            )

async def delayed_notification(bot, user_id, task, delay, label):
        await asyncio.sleep(delay)
        await bot.send_message(
            chat_id=user_id,
            text=f"Recordatorio ({label}):\n{task.description}\nProgramada para: {task.due_date.strftime('%H:%M')}"
        )

async def schedule_all_user_tasks(bot: Bot):
    session = SessionLocal()
    users = session.query(Task.user_id).distinct()
    for user in users:
        tasks = Task.get_user_tasks(user.user_id)
        for task in tasks:
            if not task.completed:
                await schedule_task_notifications(bot, user.user_id, task)
    session.close()