# src/utils/task_api.py

from src.database.database_interation import set_task, get_user_tasks # Asegúrate de importar set_task y get_user_tasks
from telegram.ext import ConversationHandler
from datetime import datetime, timedelta, time # Importar time para manejarlo mejor
import asyncio
from telegram import Bot
from src.utils.scheduler import schedule_instant_reminder, schedule_recurring_task # Importar función para tareas recurrentes
import os
import re

# --- Estados de la Conversación ---
ASK_DESCRIPTION, ASK_DATE, ASK_TIME, ASK_FREQUENCY, CONFIRM_TASK = range(5)

async def start_tasks_conversation(update, context):
    """Inicia la conversación para añadir una nueva tarea."""
    user_id = update.effective_user.id
    
    # Mostrar tareas existentes si las hay, como un contexto útil
    tasks = get_user_tasks(user_id) 
    if tasks:
        msg = "Tus tareas actuales:\n"
        for task in tasks:
            status = "✅" if task.completed else "❌"
            # Formatear la fecha/hora para mostrarla de forma clara
            due_str = task.due_date.strftime('%d/%m %H:%M') if task.due_date else "Sin fecha/hora"
            msg += f"  - {task.description} (Para: {due_str}) {status}\n"
    else:
        msg = "No tienes tareas registradas actualmente.\n"
    
    msg += "\n¡Vamos a agregar una nueva tarea! Por favor, escribe la **descripción** de la tarea (ej. 'Llamar a María para el proyecto').\n\nO envía /cancelar en cualquier momento para abortar."
    
    await update.message.reply_text(msg)
    return ASK_DESCRIPTION

async def ask_date(update, context):
    """Guarda la descripción y pide la fecha."""
    context.user_data['description'] = update.message.text.strip()
    if not context.user_data['description']:
        await update.message.reply_text("La descripción no puede estar vacía. Por favor, escribe la descripción de la tarea.")
        return ASK_DESCRIPTION # Volver a pedir la descripción

    await update.message.reply_text(
        "Perfecto. Ahora, ¿para qué **fecha** es esta tarea? (Formato: DD-MM-YYYY)\n"
        "Si es para hoy, puedes escribir 'hoy'. Si es para mañana, escribe 'mañana'.\n"
        "O envía /cancelar para abortar."
    )
    return ASK_DATE

async def ask_time(update, context):
    """Procesa la fecha, la guarda y pide la hora."""
    date_text = update.message.text.strip().lower()
    today = datetime.now().date()
    
    due_date = None
    try:
        if date_text == 'hoy':
            due_date = today
        elif date_text == 'mañana':
            due_date = today + timedelta(days=1)
        else:
            # Intentar parsear como DD-MM-YYYY
            due_date = datetime.strptime(date_text, "%d-%m-%Y").date()
            # Si la fecha es en el pasado (y no es hoy), avisar
            if due_date < today:
                await update.message.reply_text(
                    "La fecha que ingresaste ya pasó. Por favor, ingresa una fecha en el futuro (DD-MM-YYYY), 'hoy' o 'mañana').\n"
                    "O envía /cancelar para abortar."
                )
                return ASK_DATE # Permanece en el estado de pedir fecha

    except ValueError:
        await update.message.reply_text(
            "Ese no es un formato de fecha válido. Por favor, usa DD-MM-YYYY (ej. 25-12-2025), 'hoy' o 'mañana'.\n"
            "O envía /cancelar para abortar."
        )
        return ASK_DATE # Permanece en el estado de pedir fecha

    context.user_data['due_date'] = due_date
    await update.message.reply_text(
        f"Entendido, la tarea es para el {due_date.strftime('%d/%m/%Y')}. Ahora, ¿a qué **hora** debe sonar la alarma? (Formato: HH:MM, ej. 14:30)\n"
        "O envía /cancelar para abortar."
    )
    return ASK_TIME

async def ask_frequency(update, context):
    """Procesa la hora, la guarda y pide la frecuencia."""
    time_text = update.message.text.strip()
    
    try:
        # Intentar parsear como HH:MM
        task_time_obj = datetime.strptime(time_text, "%H:%M").time()
    except ValueError:
        await update.message.reply_text(
            "Ese no es un formato de hora válido. Por favor, usa HH:MM (ej. 09:00, 14:30).\n"
            "O envía /cancelar para abortar."
        )
        return ASK_TIME # Permanece en el estado de pedir hora

    context.user_data['task_time'] = task_time_obj

    # Combinar fecha y hora para la validación final y almacenamiento
    due_date = context.user_data['due_date']
    due_datetime = datetime.combine(due_date, task_time_obj)
    now = datetime.now()

    # Si la fecha es hoy y la hora ya pasó, ajustar para mañana
    if due_datetime <= now:
        # Si la fecha es hoy y la hora ya pasó, pregunta si es para el día siguiente
        if due_date == now.date():
            await update.message.reply_text(
                f"La hora {time_text} ya pasó hoy. ¿Quieres programarla para mañana a la misma hora? (Sí/No)\n"
                "Si dices 'No', te pediré la hora nuevamente."
            )
            context.user_data['ask_tomorrow_confirmation'] = True
            return ASK_TIME # Reutilizamos este estado para la confirmación
        else: # Si la fecha es futura pero la hora combinada es pasada por algún motivo (ej. cambio de zona horaria o error)
              # Esto no debería ocurrir con la lógica de ask_date
            await update.message.reply_text(
                "La fecha y hora especificadas ya pasaron. Por favor, ingresa una hora futura.\n"
                "O envía /cancelar para abortar."
            )
            return ASK_TIME
            
    context.user_data['due_datetime'] = due_datetime # Guarda el datetime completo
    
    await update.message.reply_text(
        "¿Con qué **frecuencia** deseas esta tarea? (ej. 'una vez', 'diaria', 'semanal', 'mensual', 'anual')\n"
        "O envía /cancelar para abortar."
    )
    return ASK_FREQUENCY

async def process_tomorrow_confirmation(update, context):
    """Maneja la confirmación de si la tarea es para mañana."""
    response = update.message.text.strip().lower()
    if response == 's' or response == 'si':
        due_date = context.user_data['due_date']
        task_time_obj = context.user_data['task_time']
        
        # Ajustar para mañana
        due_date_tomorrow = due_date + timedelta(days=1)
        due_datetime_tomorrow = datetime.combine(due_date_tomorrow, task_time_obj)
        context.user_data['due_datetime'] = due_datetime_tomorrow
        
        await update.message.reply_text(f"Tarea programada para el {due_datetime_tomorrow.strftime('%d/%m/%Y')} a las {due_datetime_tomorrow.strftime('%H:%M')}.")
        
        # Continuar a pedir la frecuencia
        del context.user_data['ask_tomorrow_confirmation'] # Limpiar la bandera
        await update.message.reply_text(
            "¿Con qué **frecuencia** deseas esta tarea? (ej. 'una vez', 'diaria', 'semanal', 'mensual', 'anual')\n"
            "O envía /cancelar para abortar."
        )
        return ASK_FREQUENCY
    elif response == 'n' or response == 'no':
        del context.user_data['ask_tomorrow_confirmation'] # Limpiar la bandera
        await update.message.reply_text(
            "Por favor, ingresa una **hora** en el futuro para hoy, o ajusta la fecha previamente.\n"
            "O envía /cancelar para abortar."
        )
        return ASK_TIME # Volver a pedir la hora
    else:
        await update.message.reply_text("Respuesta no válida. Por favor, responde 'Sí' o 'No'.")
        return ASK_TIME # Permanece en el estado de confirmación

async def confirm_task(update, context):
    """Procesa la frecuencia, la guarda y pide confirmación final."""
    frequency_text = update.message.text.strip().lower()
    valid_frequencies = ['una vez', 'diaria', 'semanal', 'mensual', 'anual']

    if frequency_text not in valid_frequencies:
        await update.message.reply_text(
            "Frecuencia no válida. Por favor, elige entre 'una vez', 'diaria', 'semanal', 'mensual', 'anual'.\n"
            "O envía /cancelar para abortar."
        )
        return ASK_FREQUENCY # Permanece en el estado de pedir frecuencia
    
    context.user_data['frequency'] = frequency_text

    description = context.user_data['description']
    due_datetime = context.user_data['due_datetime']
    
    summary = (
        f"Confirma los detalles de la tarea:\n"
        f"  Descripción: **{description}**\n"
        f"  Fecha y Hora: **{due_datetime.strftime('%d/%m/%Y %H:%M')}**\n"
        f"  Frecuencia: **{frequency_text.capitalize()}**\n\n"
        "¿Es correcto? (Sí/No)\nO envía /cancelar para abortar."
    )
    await update.message.reply_text(summary)
    return CONFIRM_TASK

async def finalize_task(update, context):
    """Confirma y guarda la tarea."""
    confirmation = update.message.text.strip().lower()
    if confirmation == 's' or confirmation == 'si':
        user_id = update.effective_user.id
        description = context.user_data['description']
        due_datetime = context.user_data['due_datetime']
        frequency = context.user_data['frequency']

        # Guarda la tarea en la base de datos
        task = set_task(user_id, description, due_date=due_datetime)
        
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if telegram_bot_token:
            if frequency == 'una vez':
                # Programa un recordatorio instantáneo para esta tarea única
                await schedule_instant_reminder(telegram_bot_token, task.id)
                await update.message.reply_text(f"¡Tarea '{description}' programada para el {due_datetime.strftime('%d/%m/%Y %H:%M')}!")
            else:
                # Programa una tarea recurrente
                await schedule_recurring_task(telegram_bot_token, task.id, frequency)
                await update.message.reply_text(f"¡Tarea '{description}' programada con frecuencia {frequency} a partir del {due_datetime.strftime('%d/%m/%Y %H:%M')}!")
        else:
            await update.message.reply_text("Error: TELEGRAM_BOT_TOKEN no configurado. La tarea se guardó, pero no se pudo programar el recordatorio.")
        
        # Limpiar user_data
        context.user_data.clear()
        return ConversationHandler.END
    elif confirmation == 'n' or confirmation == 'no':
        await update.message.reply_text("Registro de tarea cancelado. Puedes empezar de nuevo con /task.")
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("Respuesta no válida. Por favor, responde 'Sí' o 'No'.")
        return CONFIRM_TASK # Permanece en el estado de confirmación

async def cancel_tasks_conversation(update, context):
    """Cancela la conversación y limpia los datos del usuario."""
    await update.message.reply_text("Proceso de registro de tarea abortado. Puedes empezar de nuevo con /task.")
    if 'description' in context.user_data: # Limpiar solo si hay datos pendientes
        context.user_data.clear()
    return ConversationHandler.END

# --- Funciones existentes de la API de tareas (mantener o ajustar si es necesario) ---

async def list_tasks(update, context):
    user_id = update.effective_user.id
    tasks = get_user_tasks(user_id) 
    if tasks:
        msg = "Tus tareas:\n"
        for task in tasks:
            status = "✅" if task.completed else "❌"
            due_str = task.due_date.strftime('%d/%m %H:%M') if task.due_date else "Sin fecha/hora"
            msg += f"  - {task.description} (Para: {due_str}) {status}\n"
    else:
        msg = "No tienes tareas registradas."
    await update.message.reply_text(msg)

# No necesitamos las funciones add_task_description, add_task_time anteriores
# ya que ahora tenemos un flujo de conversación completo.