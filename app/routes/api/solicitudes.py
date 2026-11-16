"""
Endpoints de solicitudes para la API.
"""

from flask import g, request, url_for
from flask_restx import Namespace, Resource, fields

from app import adopciones, cuestionario
from app.models import Solicitud
from app.routes.api.auth import jwt_required

ns = Namespace("solicitudes", description="Solicitudes")

# Máximo de claves desconocidas que se nombran en el mensaje de error
MAX_CLAVES_EN_ERROR = 5

# Motivo breve de cada error del cuestionario, para el mensaje de la API
MOTIVOS = {
    cuestionario.MENSAJE_OBLIGATORIO: 'falta',
    cuestionario.MENSAJE_DETALLES: 'falta',
    cuestionario.MENSAJE_OPCION: 'opción no válida',
    cuestionario.MENSAJE_TEXTO: 'texto no válido',
    cuestionario.MENSAJE_LARGO: 'demasiado largo',
}


def validar_cuestionario(datos):
    """
    Valida el cuestionario recibido con las mismas reglas que la web.

    Returns:
        tuple: (respuestas limpias, None) si es válido, o (None, mensaje).
    """
    desconocidas = cuestionario.claves_desconocidas(datos)
    if desconocidas:
        nombres = ', '.join(clave[:100] for clave in desconocidas[:MAX_CLAVES_EN_ERROR])
        return None, f'Cuestionario no válido: campos desconocidos: {nombres}'
    respuestas, errores = cuestionario.validar(datos)
    if errores:
        detalle = ', '.join(f'{campo} ({MOTIVOS[errores[campo]]})' for campo in sorted(errores))
        return None, f'Cuestionario no válido: {detalle}'
    return respuestas, None

# Modelos para Swagger
solicitud_model = ns.model('Solicitudes', {
    'id': fields.Integer(required=True, description='ID único de la solicitud'),
    'usuario_id': fields.Integer(required=True, description='ID único del usuario'),
    'mascota_id': fields.Integer(required=True, description='ID único de la mascota.'),
    'fecha_solicitud': fields.String(required=True, description='Fecha ISO de la solicitud'),
    'estado': fields.String(required=True, description='pendiente/aprobada/rechazada'),
    'fecha_revision': fields.String(required=True, description='Fecha ISO de la revisión'),
    'comentarios_admin': fields.String(required=True, description='Comentarios del administrador'),
    'cuestionario': fields.Raw(required=True, description='Cuestionario')
})

create_solicitud_model = ns.model('CrearSolicitud', {
    'mascota_id': fields.Integer(required=True, description='ID de la mascota'),
    'cuestionario': fields.Raw(required=True,
                               description='Respuestas del cuestionario (claves y valores de app/cuestionario.py)')
})

@ns.route("/mias")
class MisSolicitudes(Resource):
    @jwt_required
    @ns.marshal_list_with(solicitud_model)
    def get(self):
        """Devuelve las solicitudes del usuario actual"""
        query = Solicitud.query.filter_by(usuario_id=g.current_user.id)

        solicitudes = query.order_by(Solicitud.fecha_solicitud).all()
        return [s.to_dict() for s in solicitudes]


@ns.route("/")
class CrearSolicitud (Resource):
    @jwt_required
    @ns.expect(create_solicitud_model)
    @ns.response(201, 'Solicitud creada exitosamente', solicitud_model)
    @ns.response(409, 'Solicitud duplicada')
    def post(self):
        data = request.get_json()

        mascota_id = data.get('mascota_id') if isinstance(data, dict) else None
        if not isinstance(mascota_id, int) or isinstance(mascota_id, bool) \
                or not isinstance(data.get('cuestionario'), dict):
            return {'error': 'Datos inválidos'}, 400

        # Mismas reglas que el formulario web (P-04), antes de crear nada
        respuestas, error = validar_cuestionario(data['cuestionario'])
        if error:
            return {'error': error}, 400

        # Misma regla que la web: la mascota sigue disponible (ADR-0004)
        try:
            solicitud = adopciones.crear_solicitud(g.current_user.id, mascota_id, respuestas)
        except adopciones.MascotaNoEncontrada as error:
            return {'error': error.mensaje}, 404
        except adopciones.MascotaNoDisponible as error:
            return {'error': error.mensaje}, 400
        except adopciones.SolicitudDuplicada as error:
            return {'error': error.mensaje}, 409
        ubicacion = url_for('api.solicitudes_solicitud_detail', id=solicitud.id)
        return solicitud.to_dict(), 201, {'Location': ubicacion}


@ns.route("/<int:id>")
class SolicitudDetail(Resource):
    @jwt_required
    @ns.marshal_with(solicitud_model)
    @ns.response(404, 'Solicitud no encontrada')
    def get(self, id):
        """Devuelve una solicitud del usuario actual."""
        # 404 también para solicitudes de otros usuarios: no revela si existen
        solicitud = Solicitud.query.filter_by(id=id, usuario_id=g.current_user.id).first_or_404()
        return solicitud.to_dict()


