"""
Blueprint para la API REST.
Configura Flask-RESTX con Swagger automático.
"""

from flask import Blueprint, current_app
from flask_restx import Api
from werkzeug.exceptions import HTTPException

# Crear blueprint
bp = Blueprint('api', __name__, url_prefix='/api')

# Configurar Flask-RESTX (Swagger)
api = Api(
    bp,
    title='API Adopción de Mascotas',
    version='1.0',
    description='API REST para gestionar adopciones de mascotas',
    doc='/docs',
    authorizations={
        'Bearer': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': 'Escribe: Bearer <tu_token>'
        }
    },
    security='Bearer'  # Swagger UI en /api/docs
)

# Agregar namespaces a la API
from app.routes.api import auth, mascotas, solicitudes  # noqa: E402 (después de crear api, import circular)

api.add_namespace(auth.ns)
api.add_namespace(mascotas.ns)
api.add_namespace(solicitudes.ns)

# Desactivar X-Fields header en Swagger
api.mask_header = None

# Mensajes de error en español para los códigos más habituales
MENSAJES_ERROR = {
    404: 'Recurso no encontrado',
    405: 'Método no permitido',
    429: 'Demasiadas peticiones, inténtalo más tarde',
}


@api.errorhandler(HTTPException)
def error_http(error):
    """Todos los errores de la API usan el mismo formato: {"error": "mensaje"}."""
    mensaje = MENSAJES_ERROR.get(error.code, error.description)
    return {'error': mensaje}, error.code


@api.errorhandler(Exception)
def error_interno(error):
    """Errores no controlados: 500 sin detalles internos."""
    current_app.logger.exception('Error no controlado en la API')
    return {'error': 'Error interno del servidor'}, 500
