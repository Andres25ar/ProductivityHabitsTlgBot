# src/database/db_context.py

import os
import logging
from contextlib import asynccontextmanager # ¡IMPORTAR ESTO!
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.future import select # Aunque no se usa directamente en este archivo, lo mantengo si otros módulos lo necesitan.
from dotenv import load_dotenv

db_logger = logging.getLogger(__name__)
db_logger.setLevel(logging.INFO)

# Cargar variables de entorno al inicio del módulo
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# ***** LÍNEA DE DEPURACIÓN CLAVE Y EXPLÍCITA *****
# Usamos print() para asegurarnos de que se muestre, incluso si el logging falla.
print(f"DEBUG: DATABASE_URL leída en db_context.py: {DATABASE_URL}")
# *************************************************

if not DATABASE_URL:
    db_logger.critical("DATABASE_URL no está configurada. ¡La conexión a la DB fallará!")
    raise ValueError("DATABASE_URL no está configurada. La conexión a la DB fallará.")

engine = create_async_engine(DATABASE_URL, echo=True) 

AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base() # Esta Base es la que deben usar todos tus modelos

@asynccontextmanager # ¡AÑADIR ESTE DECORADOR!
async def get_db():
    """
    Proporciona una sesión de base de datos asíncrona a través de un context manager.
    Debe usarse con 'async with'.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # Asegúrate de que la sesión se cierre correctamente.
            # En SQLAlchemy 2.0, el async with para AsyncSessionLocal
            # ya maneja el cierre, pero explicitarlo no está de más.
            await session.close()


async def init_db_async():
    """
    Inicializa la base de datos de forma asíncrona, creando todas las tablas
    definidas en los modelos si no existen.
    """
    async with engine.begin() as conn:
        # Importación local para evitar circularidad si models.py también importara algo de db_context.
        # Asegúrate de que todos los modelos estén importados en algún lugar
        # antes de llamar a create_all si no es aquí.
        from .models import Base as ModelsBase # Usamos el alias para evitar conflicto con la 'Base' definida arriba
        await conn.run_sync(ModelsBase.metadata.create_all)

