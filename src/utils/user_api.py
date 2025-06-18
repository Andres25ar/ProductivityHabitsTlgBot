from src.database.database_interation import User, SessionLocal

def create_or_get_user(user_id, username=None, first_name=None, last_name=None):
    session = SessionLocal()
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        user = User(id=user_id, username=username, first_name=first_name, last_name=last_name)
        session.add(user)
        session.commit()
    session.close()
    return user

def update_user_name(user_id, name):
    session = SessionLocal()
    user = session.query(User).filter_by(id=user_id).first()
    if user:
        user.first_name = name
        session.commit()
    session.close()

def delete_user(user_id):
    session = SessionLocal()
    user = session.query(User).filter_by(id=user_id).first()
    if user:
        session.delete(user)
        session.commit()
    session.close()