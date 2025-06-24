# src/utils/user_api.py

import logging
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.database.db_context import get_db # Importar get_db para obtener sesiones asíncronas
from src.database.database_interation import set_user, get_user_by_telegram_id # Importar funciones de interación de DB

# Configuración del logger para este módulo
user_api_logger = logging.getLogger(__name__)
user_api_logger.setLevel(logging.INFO)

async def create_or_get_user(telegram_id: int, username: str, first_name: str, last_name: str = None) -> bool:
    """
    Crea un nuevo usuario si no existe, o lo recupera si ya está en la base de datos.
    Retorna True si el usuario existe o fue creado exitosamente, False en caso contrario.
    """
    user_api_logger.info(f"Intentando crear o recuperar usuario con Telegram ID: {telegram_id}")
    async with get_db() as db:
        try:
            # Reutilizamos la función set_user de database_interation
            user = await set_user(db, telegram_id, username, first_name, last_name)
            if user:
                user_api_logger.info(f"Usuario {telegram_id} recuperado/creado exitosamente.")
                return True
            else:
                user_api_logger.error(f"Fallo desconocido al crear o recuperar usuario {telegram_id}.")
                return False
        except Exception as e:
            user_api_logger.error(f"Error al crear o recuperar usuario {telegram_id}: {e}", exc_info=True)
            return False

async def update_user_name(telegram_id: int, new_username: str, new_first_name: str, new_last_name: str = None) -> bool:
    """
    Actualiza el nombre de usuario y los nombres.
    """
    user_api_logger.info(f"Intentando actualizar nombre de usuario para Telegram ID: {telegram_id}")
    async with get_db() as db:
        try:
            user = await get_user_by_telegram_id(db, telegram_id)
            if user:
                user.username = new_username
                user.first_name = new_first_name
                user.last_name = new_last_name
                await db.commit()
                await db.refresh(user)
                user_api_logger.info(f"Nombre de usuario para {telegram_id} actualizado exitosamente.")
                return True
            else:
                user_api_logger.warning(f"Usuario {telegram_id} no encontrado para actualizar nombre.")
                return False
        except Exception as e:
            await db.rollback()
            user_api_logger.error(f"Error al actualizar nombre de usuario para {telegram_id}: {e}", exc_info=True)
            return False

async def delete_user(telegram_id: int) -> bool:
    """
    Elimina un usuario de la base de datos.
    """
    user_api_logger.info(f"Intentando eliminar usuario con Telegram ID: {telegram_id}")
    async with get_db() as db:
        try:
            user = await get_user_by_telegram_id(db, telegram_id)
            if user:
                await db.delete(user)
                await db.commit()
                user_api_logger.info(f"Usuario {telegram_id} eliminado exitosamente.")
                return True
            else:
                user_api_logger.warning(f"Usuario {telegram_id} no encontrado para eliminar.")
                return False
        except Exception as e:
            await db.rollback()
            user_api_logger.error(f"Error al eliminar usuario {telegram_id}: {e}", exc_info=True)
            return False
