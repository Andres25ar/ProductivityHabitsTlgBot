# Usa una imagen base oficial de Python
FROM python:3.10-slim-buster

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de requerimientos y módulos a tu contenedor
COPY src/requirements.txt .

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo el código de tu bot al contenedor
# Copia el directorio src/bot completo al directorio /app
COPY src/bot/ .

# Comando para ejecutar tu aplicación cuando el contenedor inicie
# CMD es el comando principal del contenedor
CMD ["python", "productivity_habits_bot.py"]