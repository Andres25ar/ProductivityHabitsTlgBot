#api del bot: TELEGRAM_BOT_TOKEN
#api para acceder a datos del clima: OPENWEATHER_API_KEY
"""
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from dotenv import load_dotenv
import requests
"""