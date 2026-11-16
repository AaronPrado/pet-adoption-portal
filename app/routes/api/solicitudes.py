"""
Endpoints de solicitudes para la API.
"""

from flask import g, request, url_for
from flask_restx import Namespace, Resource, fields

from app import adopciones
from app.models import Solicitud
from app.routes.api.auth import jwt_required

ns = Namespace("solicitudes", description="Solicitudes")

# Límites del cuestionario recibido por la API
CUESTIONARIO_MAX_CAMPOS = 30
CUESTIONARIO_MAX_LONGITUD = 2000


def cuestionario_valido(cuestionario):
    """El cuestionario debe ser un objeto plano con valores simples y acotados."""
    if not isinstance(cuestionario, dict) or not 0 < len(cuestionario) <= CUESTIONARIO_MAX_CAMPOS:
        return False
    for clave, valor in cuestionario.items():
        if len(clave) > 100:
            return False
        if valor is not None and not isinstance(valor, (str, bool, int, float)):
            return False
        if isinstance(valor, str) and len(valor) > CUESTIONARIO_MAX_LONGITUD:
            return False
    return True

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
    'cuestionario': fields.Raw(description='Respuestas del cuestionario')
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
                or not cuestionario_valido(data.get('cuestionario')):
            return {'error': 'Datos inválidos'}, 400

        # Misma regla que la web: la mascota sigue disponible (ADR-0004)
        try:
            solicitud = adopciones.crear_solicitud(g.current_user.id, mascota_id, data['cuestionario'])
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


