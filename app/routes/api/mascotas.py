"""
Endpoints públicos de mascotas para la API.
"""

from flask import request, url_for
from flask_restx import Namespace, Resource, fields
from werkzeug.exceptions import BadRequest

from app import db
from app.models import Mascota

ns = Namespace("mascotas", description="Mascotas")

# Modelos para Swagger
mascota_model = ns.model('Mascotas', {
    'id': fields.Integer(required=True, description='ID único'),
    'nombre': fields.String(required=True, description='Nombre de la mascota'),
    'especie': fields.String(required=True, description='Perro, Gato, etc.'),
    'raza': fields.String(required=True, description='Raza'),
    'edad_aprox': fields.Integer(required=True, description='Edad aproximada en años'),
    'sexo': fields.String(required=True, description='Macho/Hembra'),
    'tamano': fields.String(required=True, description='Pequeño/Mediano/Grande'),
    'descripcion': fields.String(required=True, description='Descripción'),
    'estado': fields.String(required=True, description='disponible/en_proceso/adoptado'),
    'foto_url': fields.String(required=True, description='URL de la imagen'),
    'fecha_ingreso': fields.String(required=True, description='Fecha ISO'),
    'vacunado': fields.Boolean(required=True, description='Estado vacunación'),
    'esterilizado': fields.Boolean(required=True, description='Estado esterilización')
})

POR_PAGINA_DEFECTO = 20
POR_PAGINA_MAXIMO = 100


def parametro_entero(nombre, defecto=None, minimo=None, maximo=None):
    """Lee un parámetro entero de la URL; 400 si no es un entero válido."""
    valor = request.args.get(nombre)
    if valor in (None, ''):
        return defecto
    try:
        numero = int(valor)
    except ValueError:
        raise BadRequest(f'{nombre} debe ser un número entero') from None
    if (minimo is not None and numero < minimo) or (maximo is not None and numero > maximo):
        rango = f'entre {minimo} y {maximo}' if maximo is not None else f'mayor o igual que {minimo}'
        raise BadRequest(f'{nombre} debe estar {rango}')
    return numero


def cabeceras_paginacion(pagina, endpoint):
    """Total en X-Total-Count y enlaces a otras páginas en Link (RFC 8288)."""
    argumentos = request.args.to_dict()
    enlaces = []
    destinos = {'first': 1, 'last': max(pagina.pages, 1)}
    if pagina.has_prev:
        destinos['prev'] = pagina.prev_num
    if pagina.has_next:
        destinos['next'] = pagina.next_num
    for rel, numero in destinos.items():
        argumentos['page'] = numero
        enlaces.append(f'<{url_for(endpoint, _external=True, **argumentos)}>; rel="{rel}"')
    return {'X-Total-Count': str(pagina.total), 'Link': ', '.join(enlaces)}


@ns.route("/")
class MascotaList(Resource):
    @ns.marshal_list_with(mascota_model)
    @ns.doc(params={
        'especie': 'Filtrar por especie (Perro, Gato...)',
        'raza': 'Filtrar por raza (Golden Retriever, Siamés...)',
        'edad_aprox': 'Filtrar por edad exacta en años',
        'edad_min': 'Edad mínima en años',
        'edad_max': 'Edad máxima en años',
        'tamano': 'Filtrar por tamaño (Pequeño, Mediano, Grande)',
        'page': 'Página (desde 1)',
        'per_page': f'Resultados por página (máximo {POR_PAGINA_MAXIMO}, por defecto {POR_PAGINA_DEFECTO})',
    })
    @ns.response(400, 'Parámetro inválido')
    def get(self):
        """
        Lista las mascotas disponibles para adopción, paginadas.

        El total va en la cabecera X-Total-Count y los enlaces a otras páginas
        en la cabecera Link.
        """
        query = Mascota.query.filter_by(estado='disponible')

        # Filtros opcionales desde query params
        especie = request.args.get("especie")
        if especie:
            query = query.filter_by(especie=especie)

        raza = request.args.get("raza")
        if raza:
            query = query.filter_by(raza=raza)

        edad_aprox = parametro_entero('edad_aprox', minimo=0)
        if edad_aprox is not None:
            query = query.filter_by(edad_aprox=edad_aprox)

        edad_min = parametro_entero('edad_min', minimo=0)
        if edad_min is not None:
            query = query.filter(Mascota.edad_aprox >= edad_min)

        edad_max = parametro_entero('edad_max', minimo=0)
        if edad_max is not None:
            query = query.filter(Mascota.edad_aprox <= edad_max)

        tamano = request.args.get('tamano')
        if tamano:
            query = query.filter_by(tamano=tamano)

        pagina = query.order_by(Mascota.fecha_ingreso.desc(), Mascota.id.desc()).paginate(
            page=parametro_entero('page', defecto=1, minimo=1),
            per_page=parametro_entero('per_page', defecto=POR_PAGINA_DEFECTO, minimo=1, maximo=POR_PAGINA_MAXIMO),
            error_out=False,
        )
        return [m.to_dict() for m in pagina.items], 200, cabeceras_paginacion(pagina, 'api.mascotas_mascota_list')


@ns.route("/<int:id>")
class MascotaDetail(Resource):
    @ns.marshal_with(mascota_model)
    @ns.response(404, 'Mascota no encontrada')
    def get(self, id):
        """Obtiene el detalle de una mascota por ID."""
        mascota = db.get_or_404(Mascota, id)
        return mascota.to_dict()
