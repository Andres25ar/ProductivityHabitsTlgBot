from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from src.utils.task_api import (
    start_tasks_conversation,
    add_task_description,
    add_task_time,
    list_tasks,
    cancel_tasks_conversation,
    ASK_DESCRIPTION,
    ASK_TIME
)

# Handler de conversación para tareas
task_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("task", start_tasks_conversation)],
    states={
        ASK_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_description)],
        ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_time)],
    },
    fallbacks=[CommandHandler("cancel", cancel_tasks_conversation)],
)

# Handler para listar tareas (opcional, puedes agregarlo al bot principal si lo deseas)
listar_tareas_handler = CommandHandler("listartareas", list_tasks)