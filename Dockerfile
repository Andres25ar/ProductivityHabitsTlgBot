# Usa una imagen base de Python ligera
FROM python:3.11-slim-buster

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de requerimientos e instala las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia los scripts de inicialización y dales permisos de ejecución
COPY init.sh .
COPY wait-for-it.sh .
RUN chmod +x init.sh wait-for-it.sh

# Copia el archivo .env primero (si es necesario para la fase de construcción, aunque es menos común)
# Si tu .env solo contiene variables para el runtime, puedes omitir esta línea y depender de docker-compose.yml
COPY .env .

# Copia el resto del código de la aplicación
COPY . .

# ***** LÍNEA AÑADIDA: Establece PYTHONPATH para que Python encuentre los módulos en 'src' *****
ENV PYTHONPATH=/app
# ************************************************************************************************

# Define el comando que se ejecutará cuando el contenedor se inicie
# Ahora se ejecuta init.sh, que a su vez iniciará el bot.
CMD ["./init.sh"]