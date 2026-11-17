"""
Blueprint que sirve las fotos del backend local (ADR-0003).

Con el backend `s3` las fotos se sirven desde el bucket y esta ruta solo
encuentra las que se guardaron antes en local.
"""

from flask import Blueprint, abort, send_from_directory

from app import fotos
from app.fotos import local

bp = Blueprint('fotos', __name__, url_prefix='/fotos')

# Los nombres son aleatorios y nunca se reutilizan: se pueden cachear un año
CACHE_SEGUNDOS = 365 * 24 * 3600


@bp.route('/<clave>')
def servir(clave):
    """Foto guardada en FOTOS_DIR. Solo claves generadas por la app (sin rutas)."""
    if not fotos.es_clave_valida(clave):
        abort(404)
    return send_from_directory(local.directorio(), clave, max_age=CACHE_SEGUNDOS)
