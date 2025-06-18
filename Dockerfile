# Usa una imagen base oficial de Python
FROM python:3.11.9

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de requerimientos y módulos a tu contenedor
COPY requirements.txt .

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código de tu bot al contenedor
# Copia el directorio src/bot completo al directorio /app
COPY src/ ./src

# Comando para ejecutar tu aplicación cuando el contenedor inicie
# CMD es el comando principal del contenedor
#CMD ["python", "-m", "productivity_habits_bot.py"]
CMD ["python", "-m", "src.bot.productivity_habits_bot"]