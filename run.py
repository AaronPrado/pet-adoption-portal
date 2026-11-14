"""
Este archivo es el punto de entrada para ejecutar la aplicación.
Utiliza el Application Factory pattern para crear la instancia de Flask.

Uso:
    python run.py

    O con variables de entorno:
    FLASK_ENV=development python run.py
    FLASK_ENV=production python run.py

Si FLASK_ENV no está definida se usa 'production', que exige los secretos
en variables de entorno. En local, define FLASK_ENV=development en .env.
"""

import os
from app import create_app

# Obtener el entorno desde variable de entorno (production por defecto, para
# que un despliegue sin configurar no arranque en modo debug)
config_name = os.environ.get("FLASK_ENV") or "production"

# Crear la aplicación usando el Application Factory
app = create_app(config_name)

if __name__ == "__main__":
    """
    Ejecutar la aplicación Flask.

    En desarrollo:
    - Debug activado (recarga automática)
    - Host 127.0.0.1 por defecto (el depurador de Werkzeug no debe quedar
      expuesto a la red); se puede cambiar con la variable HOST
    - Puerto 5000

    En producción:
    - Usar gunicorn o waitress (no flask run directamente)
    - Ejemplo: gunicorn -w 4 -b 0.0.0.0:8000 run:app
    """
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 5000)),       # Puerto por defecto de Flask
        debug=app.config["DEBUG"]  # Debug según configuración
    )

