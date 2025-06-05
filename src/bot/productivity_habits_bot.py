#api del bot: TELEGRAM_BOT_TOKEN
#api para acceder a datos del clima: OPENWEATHER_API_KEY

import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from dotenv import load_dotenv
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
    time = sa.Column(sa.Time, nullable=False)
    user_habits = relationship("UserHabit", back_populates="habit")

#entidad que rompe relacion muchos a muchos entre usuario y habitos
class UserHabit(Base):
    __tablename__ = "user_habits"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"))
    habit_id = sa.Column(sa.Integer, sa.ForeignKey("default_habits.id"))
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