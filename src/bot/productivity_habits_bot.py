#api del bot: TELEGRAM_BOT_TOKEN
#api para acceder a datos del clima: OPENWEATHER_API_KEY

import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.ext import MessageHandler, filters
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from dotenv import load_dotenv
from datetime import datetime
from telegram.ext import ConversationHandler
# ...existing code...

load_dotenv()

POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

#coneccion a la base de datos postgreSQL
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}"

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = sa.Column(sa.BigInteger, primary_key=True)
    username = sa.Column(sa.String, nullable=True)
    first_name = sa.Column(sa.String, nullable=False)
    last_name = sa.Column(sa.String, nullable=True)
    habits = relationship("UserHabit", back_populates="user")
    tasks = relationship("Task", back_populates="user")

class DefaultHabit(Base):
    __tablename__ = "default_habits"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String, nullable=False, unique=True)
    description = sa.Column(sa.String, nullable=True)
    user_habits = relationship("UserHabit", back_populates="habit")

#entidad que rompe relacion muchos a muchos entre usuario y habitos
class UserHabit(Base):
    __tablename__ = "user_habits"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"))
    habit_id = sa.Column(sa.Integer, sa.ForeignKey("default_habits.id"))
    time = sa.Column(sa.Time, nullable=False)
    #custom_name = sa.Column(sa.String, nullable=True)
    #config = sa.Column(sa.JSON, nullable=True)
    user = relationship("User", back_populates="habits")
    habit = relationship("DefaultHabit", back_populates="user_habits")

class Task(Base):
    __tablename__ = "tasks"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"))
    description = sa.Column(sa.String, nullable=False)
    due_date = sa.Column(sa.DateTime, nullable=True)
    completed = sa.Column(sa.Boolean, default=False)
    user = relationship("User", back_populates="tasks")


engine = sa.create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)

'''tareas sobre la base de datos'''

#lista de habitos por defecto
def load_default_habits():
    session = SessionLocal()
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
    for habit in default_habits:
        existing_habit = session.query(DefaultHabit).filter_by(name=habit["name"]).first()
        if not existing_habit:
            new_habit = DefaultHabit(**habit)
            session.add(new_habit)
    session.commit()
    session.close()

def get_habits(default_habit_id=None):  #Mejorar con try catch
    session = SessionLocal()    # Obtiene una sesión de la base de datos
    # Si se proporciona un ID de hábito por defecto, filtra por ese ID
    if default_habit_id:
        habits = session.query(DefaultHabit).filter(DefaultHabit.id == default_habit_id).all()
    # Si no se proporciona un ID, devuelve todos los hábitos por defecto
    else:
        habits = session.query(DefaultHabit).all()
    session.close()
    return habits
    



def set_new_task ():
    async def start_new_task_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Por favor, ingresa la descripción de la tarea:")

        context.user_data["new_task"] = {}
        return "WAITING_DESCRIPTION"

    async def receive_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["new_task"]["description"] = update.message.text
        await update.message.reply_text("¿Cuál es la fecha límite de la tarea? (Formato: AAAA-MM-DD HH:MM) o escribe 'ninguna' si no tiene fecha límite:")
        return "WAITING_DUE_DATE"

    async def receive_task_due_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
        due_date_text = update.message.text.strip()
        if due_date_text.lower() == "ninguna":
            due_date = None
        else:
            try:
                due_date = datetime.strptime(due_date_text, "%Y-%m-%d %H:%M")
            except ValueError:
                await update.message.reply_text("Formato de fecha inválido. Intenta de nuevo (AAAA-MM-DD HH:MM) o escribe 'ninguna':")
                return "WAITING_DUE_DATE"

        context.user_data["new_task"]["due_date"] = due_date

        # Guardar en la base de datos
        session = SessionLocal()
        user_id = update.effective_user.id
        description = context.user_data["new_task"]["description"]
        task = Task(user_id=user_id, description=description, due_date=due_date)
        session.add(task)
        session.commit()
        session.close()

        await update.message.reply_text("¡Tarea agregada exitosamente!")
        context.user_data.pop("new_task", None)
        return -1  # End of conversation


    def set_new_task(application):
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("nuevatarea", start_new_task_interaction)],
            states={
                "WAITING_DESCRIPTION": [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_description)],
                "WAITING_DUE_DATE": [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_due_date)],
            },
            fallbacks=[],
        )
        application.add_handler(conv_handler)