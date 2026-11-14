"""
Configuración de gunicorn para producción.

Todos los valores se pueden ajustar con variables de entorno.
"""

import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Por defecto 2 workers por CPU + 1. Con más de un worker, el límite de
# intentos de login necesita RATELIMIT_STORAGE_URI=redis://... para que
# todos compartan el mismo contador.
workers = int(os.environ.get('WEB_CONCURRENCY') or multiprocessing.cpu_count() * 2 + 1)
threads = int(os.environ.get('GUNICORN_THREADS') or 1)
timeout = int(os.environ.get('GUNICORN_TIMEOUT') or 30)

# Logs a la salida estándar (los recoge Docker o la plataforma)
accesslog = '-'
errorlog = '-'

# Las cabeceras X-Forwarded-* las procesa ProxyFix en la app (TRUSTED_PROXIES)
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')
