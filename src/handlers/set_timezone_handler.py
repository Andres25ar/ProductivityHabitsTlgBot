import logging
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
)
import math

# Importar las funciones de base de datos
from src.database.database_interation import get_user_by_telegram_id, update_user_timezone
from src.database.db_context import get_db

logger = logging.getLogger(__name__)

# --- Estados para la conversación ---
SELECT_CONTINENT, SELECT_COUNTRY, SELECT_TIMEZONE = range(3)
COUNTRIES_PER_PAGE = 8 # Puedes ajustar cuántos países mostrar por página

# --- Funciones auxiliares ---

def get_timezones_data():
    """Crea una estructura de datos anidada de zonas horarias."""
    timezones_data = {}
    for country_code in pytz.country_timezones:
        country_name = pytz.country_names[country_code]
        for tz in pytz.country_timezones[country_code]:
            try:
                continent, city = tz.split('/', 1)
                if continent not in timezones_data: timezones_data[continent] = {}
                if country_name not in timezones_data[continent]: timezones_data[continent][country_name] = []
                timezones_data[continent][country_name].append(tz)
            except ValueError: continue
    return timezones_data

TIMEZONES_DATA = get_timezones_data()

# --- Funciones de la Conversación ---

async def start_set_timezone_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación y muestra la lista de continentes."""
    logger.info(f"Comando /set_timezone recibido de usuario: {update.effective_user.id}")
    continents = sorted(TIMEZONES_DATA.keys())
    keyboard = [[InlineKeyboardButton(c, callback_data=f"continent_{c}")] for c in continents]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Paso 1/3: Por favor, selecciona tu continente:", reply_markup=reply_markup)
    return SELECT_CONTINENT

async def handle_continent_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Muestra la primera página de países para el continente seleccionado."""
    query = update.callback_query
    await query.answer()
    continent = query.data.split('_', 1)[1]
    context.user_data['selected_continent'] = continent

    country_list = sorted(TIMEZONES_DATA[continent].keys())
    context.user_data['country_list'] = country_list

    # Construir y enviar la primera página
    await send_paginated_countries(query, context, page=0)
    return SELECT_COUNTRY

async def send_paginated_countries(query, context: ContextTypes.DEFAULT_TYPE, page: int):
    """Función reutilizable para enviar una página de países."""
    continent = context.user_data['selected_continent']
    country_list = context.user_data['country_list']

    start_index = page * COUNTRIES_PER_PAGE
    end_index = start_index + COUNTRIES_PER_PAGE

    keyboard = []
    for country in country_list[start_index:end_index]:
        keyboard.append([InlineKeyboardButton(country, callback_data=f"country_{country}")])

    # --- Lógica de botones de paginación ---
    total_pages = math.ceil(len(country_list) / COUNTRIES_PER_PAGE)
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("◀️ Anterior", callback_data=f"page_country_{page - 1}"))

    pagination_buttons.append(InlineKeyboardButton(f"Pág {page + 1}/{total_pages}", callback_data="noop")) # Botón que no hace nada

    if end_index < len(country_list):
        pagination_buttons.append(InlineKeyboardButton("Siguiente ▶️", callback_data=f"page_country_{page + 1}"))

    if pagination_buttons: keyboard.append(pagination_buttons)

    keyboard.append([InlineKeyboardButton("⬅️ Volver a Continentes", callback_data="back_to_continents")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        text=f"Paso 2/3: Has seleccionado '{continent}'. Ahora, selecciona tu país:",
        reply_markup=reply_markup
    )

async def handle_country_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja los clics en los botones de paginación de países."""
    query = update.callback_query
    await query.answer()

    page = int(query.data.split('_')[-1])
    await send_paginated_countries(query, context, page=page)

    return SELECT_COUNTRY


async def handle_country_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección del país y muestra las zonas horarias disponibles."""
    query = update.callback_query
    await query.answer()
    country = query.data.split('_', 1)[1]
    continent = context.user_data['selected_continent']
    timezones = sorted(TIMEZONES_DATA[continent][country])

    keyboard = []
    for tz in timezones:
        city_region = tz.split('/', 1)[1].replace('_', ' ')
        keyboard.append([InlineKeyboardButton(city_region, callback_data=f"tz_{tz}")])

    keyboard.append([InlineKeyboardButton("⬅️ Volver a Países", callback_data=f"back_to_countries_{continent}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=f"Paso 3/3: Has seleccionado '{country}'. Ahora, selecciona tu zona horaria:",
        reply_markup=reply_markup
    )
    return SELECT_TIMEZONE

async def handle_timezone_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Maneja la selección final y guarda la zona horaria."""
    query = update.callback_query
    await query.answer()
    timezone_str = query.data.split('_', 1)[1]
    user_telegram_id = query.from_user.id
    try:
        async with get_db() as db:
            user = await get_user_by_telegram_id(db, user_telegram_id)
            if not user:
                await query.edit_message_text("Error: No estás registrado. Usa /start primero.")
                return ConversationHandler.END
            success = await update_user_timezone(db, user.id, timezone_str)
            if success:
                await query.edit_message_text(f"✅ ¡Listo! Tu zona horaria ha sido establecida a `{timezone_str}`.")
            else:
                await query.edit_message_text("⚠️ Hubo un problema al guardar tu zona horaria.")
    except Exception as e:
        logger.error(f"Error al guardar la zona horaria para {user_telegram_id}: {e}", exc_info=True)
        await query.edit_message_text("Ocurrió un error al guardar tu zona horaria.")
    context.user_data.clear()
    return ConversationHandler.END

async def handle_back_to_continents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Regresa a la selección de continentes."""
    query = update.callback_query
    await query.answer()
    continents = sorted(TIMEZONES_DATA.keys())
    keyboard = [[InlineKeyboardButton(c, callback_data=f"continent_{c}")] for c in continents]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Paso 1/3: Por favor, selecciona tu continente:", reply_markup=reply_markup)
    return SELECT_CONTINENT

async def handle_back_to_countries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Regresa a la selección de países (a la primera página)."""
    query = update.callback_query
    await query.answer()
    # Volvemos a mostrar la primera página de países del continente guardado
    await send_paginated_countries(query, context, page=0)
    return SELECT_COUNTRY

async def cancel_set_timezone_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación."""
    await update.message.reply_text("Configuración de zona horaria cancelada.")
    context.user_data.clear()
    return ConversationHandler.END

def get_set_timezone_conversation_handler():
    """Crea y devuelve el ConversationHandler con paginación."""
    return ConversationHandler(
        entry_points=[CommandHandler("set_timezone", start_set_timezone_conversation)],
        states={
            SELECT_CONTINENT: [
                CallbackQueryHandler(handle_continent_selection, pattern="^continent_"),
            ],
            SELECT_COUNTRY: [
                CallbackQueryHandler(handle_country_pagination, pattern="^page_country_"),
                CallbackQueryHandler(handle_country_selection, pattern="^country_"),
                CallbackQueryHandler(handle_back_to_continents, pattern="^back_to_continents$"),
            ],
            SELECT_TIMEZONE: [
                CallbackQueryHandler(handle_timezone_selection, pattern="^tz_"),
                CallbackQueryHandler(handle_back_to_countries, pattern="^back_to_countries_"),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancel_set_timezone_conversation)],
    )
