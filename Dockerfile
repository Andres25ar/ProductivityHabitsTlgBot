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

# ***** LÍNEA ELIMINADA: NO COPIAR .env en la imagen de Docker *****
# COPY .env . 
# ******************************************************************

# Copia el resto del código de la aplicación
COPY . .

# Establece PYTHONPATH para que Python encuentre los módulos en 'src'
ENV PYTHONPATH=/app

# Define el comando que se ejecutará cuando el contenedor se inicie
CMD ["./init.sh"]
