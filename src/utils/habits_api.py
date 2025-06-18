from datetime import datetime
from src.database.database_interation import DefaultHabit, UserHabit, User, SessionLocal
from src.database.database_interation import UserHabit, DefaultHabit, SessionLocal
from telegram.ext import ConversationHandler


async def start_habits_conversation(update, context):
    session = SessionLocal()
    habits = DefaultHabit.get_habits()
    msg = "Habitos:\n"
    for habit in habits:
        msg += f"{habit.id}: {habit.name} - {habit.description}\n"
    msg += "\nEscribe el id del habito que deseas mejorar."
    await update.message.reply_text(msg)
    session.close()
    return 1  # Next state


async def add_habit(update, context):
    user_id = update.effective_user.id
    
    
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    last_name = update.effective_user.last_name

    session = SessionLocal()
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        user = User(id=user_id, username=username, first_name=first_name, last_name=last_name)
        session.add(user)
        session.commit()
        
    
    habit_id_text = update.message.text.strip()
    try:
        habit_id = int(habit_id_text)
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un ID numérico válido.")
        return 1

    session = SessionLocal()
    habit = session.query(DefaultHabit).filter_by(id=habit_id).first()
    if not habit:
        await update.message.reply_text("Lo siento, ese hábito no está en mi base de datos. Intenta con otro ID válido o /cancel.")
        session.close()
        return 1
    # Check if already added
    exists = session.query(UserHabit).filter_by(user_id=user_id, habit_id=habit_id).first()
    if exists:
        await update.message.reply_text("Ya tienes este hábito. Elige otro o /cancel.")
        session.close()
        return 1
    # Add habit to user (pasa la hora actual como ejemplo)
    user_habit = UserHabit(user_id=user_id, habit_id=habit_id)  #no se pide time=datetime.now().time()
    session.add(user_habit)
    session.commit()
    await update.message.reply_text(f"¡Hábito '{habit.name}' agregado! Envía otro ID para agregar más o /cancel para terminar.")
    #await update.message.reply_text("¡Hábito agregado! Envía otro ID para agregar más o /cancel para terminar.")
    session.close()
    return 1

async def list_habits(update, context):
    # Opcional: puedes mostrar los hábitos actuales del usuario aquí si lo deseas
    await start_habits_conversation(update, context)

async def cancel_habits_conversation(update, context):
    
    await update.message.reply_text("Seleccion de habitos a acabado.")
    return ConversationHandler.END

def get_daily_habits_for_user(user_id):
    session = SessionLocal()
    user_habits = session.query(UserHabit).filter_by(user_id=user_id).all()
    habits = []
    for uh in user_habits:
        habit = session.query(DefaultHabit).filter_by(id=uh.habit_id).first()
        if habit:
            habits.append(habit)
    session.close()
    return habits

# ...al final de habits_api.py...

async def send_daily_habits(context):
    user_id = context.job.data["user_id"]
    habits = get_daily_habits_for_user(user_id)
    if habits:
        habits_list = "\n".join([f"- {h.name}" for h in habits])
        await context.bot.send_message(
            chat_id=user_id,
            text=f"¡Recuerda practicar tus hábitos hoy!\n{habits_list}"
        )