#api del bot: TELEGRAM_BOT_TOKEN
#api para acceder a datos del clima: OPENWEATHER_API_KEY

import os
import logging
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from dotenv import load_dotenv
from datetime import datetime
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

    def __init__(self, id, username, first_name, last_name=None):
        session = SessionLocal()
        self.id = id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        session.add(self)
        session.commit()
        session.close()

    def get_user(user_id):
        session = SessionLocal()
        user = session.query(User).filter(User.id == user_id).first()
        session.close()
        return user

class DefaultHabit(Base):
    __tablename__ = "default_habits"
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String, nullable=False, unique=True)
    description = sa.Column(sa.String, nullable=True)
    user_habits = relationship("UserHabit", back_populates="habit")

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

    #obtener los habitos por defecto
    @staticmethod   #no estoy seguro si es staticmethod o classmethod
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

    def __init__(self, user_id, habit_id, time):
        session = SessionLocal()
        self.user_id = user_id
        self.habit_id = habit_id
        self.time = time
        session.commit()
        session.close()

    #carga los habitos de cada usuario y la hora pedida por pantalla
    def set_habit_for_user(user_id, habit_id, time):
        session = SessionLocal()
        user_habit = UserHabit(user_id=user_id, habit_id=habit_id, time=time)
        session.add(user_habit)
        session.commit()
        session.close()

    def get_user_habits(user_id):
        session = SessionLocal()
        user_habits = session.query(UserHabit).filter(UserHabit.user_id == user_id).all()
        session.close()
        return user_habits
    
    def change_time(user_id, habit_id, new_time):
        session = SessionLocal()
        user_habit = session.query(UserHabit).filter(
            UserHabit.user_id == user_id,
            UserHabit.habit_id == habit_id
        ).first()
        if user_habit:
            user_habit.time = new_time
            session.commit()
        session.close()



class Task(Base):
    __tablename__ = "tasks"
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.BigInteger, sa.ForeignKey("users.id"))
    description = sa.Column(sa.String, nullable=False)
    due_date = sa.Column(sa.DateTime, nullable=True)
    time = sa.Column(sa.Time, nullable=True)
    completed = sa.Column(sa.Boolean, default=False)
    user = relationship("User", back_populates="tasks")

    #consultar si debe ser estatico o no
    def __init__(self, user_id, description, due_date=None, time=None):
        session = SessionLocal()
        self.user_id = user_id
        self.description = description
        self.due_date = due_date if due_date else datetime.now().date()
        self.time = time if time else datetime.now().time()
        session.commit()
        session.close()


    #cargar una tarea para un usuario
    #@staticmethod
    def set_task(user_id, description, due_date=None):
        session = SessionLocal()
        task = Task(user_id=user_id, description=description, due_date=due_date)
        session.add(task)
        session.commit()
        session.close()

    def get_task(task_id):
        session = SessionLocal()
        task = session.query(Task).filter(Task.id == task_id).first()
        session.close()
        return task

    def get_task_to_time(user_id, time):
        session = SessionLocal()
        tasks = session.query(Task).filter(
            Task.user_id == user_id,
            Task.time == time
        ).all()
        session.close()
        return tasks

    def get_user_tasks(user_id):
        session = SessionLocal()
        tasks = session.query(Task).filter(Task.user_id == user_id).all()
        session.close()
        return tasks

    def get_incomplete_tasks(user_id):
        session = SessionLocal()
        tasks = session.query(Task).filter(
            Task.user_id == user_id,
            Task.completed == False
        ).all()
        session.close()
        return tasks

    def get_completed_tasks(user_id):
        session = SessionLocal()
        tasks = session.query(Task).filter(
            Task.user_id == user_id,
            Task.completed == True
        ).all()
        session.close()
        return tasks

    def mark_as_completed(task_id):
        session = SessionLocal()
        task = session.query(Task).filter(Task.id == task_id).first()
        if task:
            task.completed = True
            session.commit()
        session.close()

engine = sa.create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)

'''otras tareas sobre la base de datos'''



