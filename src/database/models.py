# src/database/models.py

import sqlalchemy as sa
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

# Importar la Base desde db_context.py para asegurar que todos los modelos usan la Base correcta
# Esta importación es crucial y debe ser la primera para evitar problemas de definición.
from src.database.db_context import Base 

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    
    # La zona horaria del usuario para mostrar y programar
    timezone = Column(String, default="UTC", nullable=False) 
    created_at = Column(DateTime(timezone=True), server_default=func.now()) 

    user_tasks = relationship("UserTask", back_populates="user")
    user_habits = relationship("UserHabit", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username='{self.username}', timezone='{self.timezone}')>"

class DefaultHabit(Base):
    """
    Define los hábitos predeterminados que el bot puede sugerir a los usuarios.
    """
    __tablename__ = "default_habits"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    user_habits = relationship("UserHabit", back_populates="default_habit") 

    def __repr__(self):
        return f"<DefaultHabit(id={self.id}, name='{self.name}')>"

class UserHabit(Base):
    """
    Relaciona a los usuarios con los hábitos que han elegido o creado.
    """
    __tablename__ = "user_habits"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    habit_id = Column(Integer, ForeignKey("default_habits.id"))

    user = relationship("User", back_populates="user_habits")
    default_habit = relationship("DefaultHabit", back_populates="user_habits")

    def __repr__(self):
        return f"<UserHabit(id={self.id}, user_id={self.user_id}, habit_id={self.habit_id})>"

class UserTask(Base):
    """
    Representa una tarea individual creada por un usuario.
    """
    __tablename__ = "user_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    description = Column(String, index=True)
    # Importante: Usa DateTime(timezone=True) si tu DB soporta y almacenas la TZ
    # Esto es ideal para fechas guardadas en UTC y luego convertidas.
    due_date = sa.Column(sa.DateTime(timezone=True), nullable=True) 
    completed = Column(Boolean, default=False)
    frequency = Column(String, nullable=True) # Ej: 'daily', 'weekly', 'monthly', 'yearly', 'once' o None

    user = relationship("User", back_populates="user_tasks")

    def __repr__(self):
        return f"<UserTask(id={self.id}, user_id={self.user_id}, description='{self.description}', due_date='{self.due_date}', frequency='{self.frequency}')>"

