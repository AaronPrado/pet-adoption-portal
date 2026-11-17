"""
Backend `local`: guarda las fotos en FOTOS_DIR (por defecto, instance/fotos).

La app las sirve en GET /fotos/<clave> (app/routes/fotos.py). En un PaaS con
disco efímero se pierden en cada despliegue: ver docs/DESPLIEGUE.md.
"""

import contextlib
import os
import shutil

from flask import current_app

PREFIJO_URL = '/fotos/'

ERRORES = (OSError,)


def directorio():
    """Directorio absoluto de las fotos."""
    return os.path.abspath(current_app.config.get('FOTOS_DIR') or os.path.join(current_app.instance_path, 'fotos'))


def disponible():
    return True


def guardar(stream, clave, content_type):
    os.makedirs(directorio(), exist_ok=True)
    ruta = os.path.join(directorio(), clave)
    # 'x': nunca sobrescribe un archivo existente
    with open(ruta, 'xb') as destino:
        try:
            shutil.copyfileobj(stream, destino)
        except OSError:
            # No dejar a medias el archivo que acabamos de crear
            destino.close()
            os.remove(ruta)
            raise
    return PREFIJO_URL + clave


def nombre_en_url(url):
    """Lo que sigue a `/fotos/` en la URL, o None si no es de este backend."""
    if not url or not url.startswith(PREFIJO_URL):
        return None
    return url[len(PREFIJO_URL):]


def copiar(nombre, destino):
    """Escribe el contenido de la foto en el archivo abierto `destino`."""
    with open(os.path.join(directorio(), nombre), 'rb') as origen:
        shutil.copyfileobj(origen, destino)


def borrar(nombre):
    # Ya borrada: el resultado es el mismo
    with contextlib.suppress(FileNotFoundError):
        os.remove(os.path.join(directorio(), nombre))
