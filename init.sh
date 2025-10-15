#!/bin/bash
# init.sh

# Esperar a que la base de datos esté lista
echo "Esperando a que la base de datos esté lista..."
./wait-for-it.sh db:5432 --timeout=30 -- echo "Base de datos disponible."

# Sección de depuración (puedes mantenerla para verificar rutas si es necesario)
echo "--- DEBUGGING PYTHON PATH AND FILES ---"
echo "Contenido de la variable de entorno PYTHONPATH: $PYTHONPATH"
echo "Listando el contenido completo de /app/src/ (esperamos ver utils/logger_config.py):"
ls -la /app/src/
echo ""
echo "Listando el contenido de /app/src/bot:"
ls -la /app/src/bot/
echo ""
echo "Listando el contenido de /app/src/database:"
ls -la /app/src/database/
echo ""
echo "Listando el contenido de /app/src/handlers:"
ls -la /app/src/handlers/
echo ""
echo "Listando el contenido de /app/src/utils:"
ls -la /app/src/utils/
echo "Rutas de búsqueda de módulos de Python (sys.path):"
python -c "import sys; print(sys.path)"
echo "Listando el contenido de /app/src/utils/ (debería contener logger_config.py):"
python -c "import os; print(os.listdir('/app/src/utils/'))"
echo "--- FIN DE SECCIÓN DE DEPURACIÓN ---"

# Iniciar el bot de Telegram
# La inicialización de la base de datos y la carga de hábitos
# ahora se manejan exclusivamente en la función post_init de productivity_habits_bot.py
echo "Iniciando el bot de Telegram..."
# Cambiado a 'python -m src.bot.productivity_habits_bot' para ejecutar como módulo
exec python -m src.bot.productivity_habits_bot
