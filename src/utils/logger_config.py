import logging

def configure_logging():
    """
    Configura el sistema de logging para la aplicación.
    """
    logging.basicConfig(
        level=logging.INFO, # Puedes cambiar a logging.DEBUG para más detalles
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler() # Envía logs a la consola
            # logging.FileHandler("app.log") # Opcional: envía logs a un archivo
        ]
    )
    # Opcional: Configurar logging para librerías específicas si es necesario
    # logging.getLogger('httpx').setLevel(logging.WARNING)
    # logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
