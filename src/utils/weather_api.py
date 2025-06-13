
import os
import requests
from dotenv import load_dotenv

# Importaciones específicas de python-telegram-bot que necesita este módulo
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

# Carga la API Key de OpenWeather
load_dotenv() #Esto permite que se cargue la constante OPENWEATHER_API_KEY
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY") 

async def start_weather_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para obtener el clima."""
    await update.message.reply_text("Por favor, ingresa el nombre de la ciudad para la cual quieres saber el clima:")
    return 0 # Estado para esperar el nombre de la ciudad

async def get_weather(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Obtiene y muestra el clima para la ciudad ingresada."""
    city = update.message.text.strip()
    api_key = OPENWEATHER_API_KEY
    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric", # Para obtener grados Celsius
        "lang": "es"       # Para obtener la descripción en español
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status() # Lanza un error para códigos de estado HTTP erróneos
        weather_data = response.json()

        if weather_data["cod"] == 200: # Si la respuesta es exitosa
            main_data = weather_data["main"]
            weather_desc = weather_data["weather"][0]["description"]
            city_name = weather_data["name"]
            country_name = weather_data["sys"]["country"]

            temperature = main_data["temp"]
            feels_like = main_data["feels_like"]
            humidity = main_data["humidity"]

            message = (
                f"El clima en {city_name}, {country_name}:\n"
                f"🌡️ Temperatura: {temperature}°C\n"
                f"🥶 Sensación térmica: {feels_like}°C\n"
                f"☁️ Descripción: {weather_desc.capitalize()}\n"
                f"💧 Humedad: {humidity}%"
            )
        else:
            message = f"No se pudo encontrar el clima para '{city}'. Por favor, verifica el nombre de la ciudad."

    except requests.exceptions.RequestException as e:
        message = f"Lo siento, no pude conectar con el servicio del clima. Error: {e}"
    except KeyError:
        message = f"Hubo un problema al procesar los datos del clima para '{city}'. Asegúrate de que el nombre de la ciudad es correcto."
    except Exception as e:
        message = f"Ocurrió un error inesperado: {e}"

    await update.message.reply_text(message)
    return ConversationHandler.END # Termina la conversación

async def cancel_weather_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de consulta del clima."""
    await update.message.reply_text("Consulta del clima cancelada.")
    return ConversationHandler.END