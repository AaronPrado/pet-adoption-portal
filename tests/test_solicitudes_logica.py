"""
Tests de reglas de negocio de las solicitudes que afectan a la integridad:
una mascota no puede adoptarse dos veces ni recibir solicitudes ilimitadas.
"""

import pytest

from app import db
from app.models import Mascota, Solicitud, Usuario
from app.routes.api.auth import generate_token


def crear_por_api(client, usuario, mascota_id, cuestionario=None):
    return client.post('/api/solicitudes/', json={
        'mascota_id': mascota_id,
        'cuestionario': cuestionario if cuestionario is not None else {'vivienda_tipo': 'Casa'}
    }, headers={'Authorization': f'Bearer {generate_token(usuario.id)}'})


class TestApiSolicitudes:

    def test_crear_por_api_marca_mascota_en_proceso(self, client, usuario_adoptante, mascota_disponible):
        assert crear_por_api(client, usuario_adoptante, mascota_disponible.id).status_code == 201
        assert db.session.get(Mascota, mascota_disponible.id).estado == 'en_proceso'

    def test_segunda_solicitud_por_api_rechazada(self, client, usuario_adoptante, mascota_disponible):
        otro = Usuario(email='otro@test.com', nombre='Otro', password='password123')
        db.session.add(otro)
        db.session.commit()

        crear_por_api(client, usuario_adoptante, mascota_disponible.id)
        response = crear_por_api(client, otro, mascota_disponible.id)

        assert response.status_code == 400
        assert Solicitud.query.count() == 1

    @pytest.mark.parametrize('cuestionario', [
        ['no', 'es', 'objeto'],
        {'anidado': {'a': 1}},
        {'largo': 'x' * 2001},
        {f'campo{i}': 'x' for i in range(31)},
        'texto',
    ])
    def test_cuestionario_invalido(self, client, usuario_adoptante, mascota_disponible, cuestionario):
        response = crear_por_api(client, usuario_adoptante, mascota_disponible.id, cuestionario)
        assert response.status_code == 400

    @pytest.mark.parametrize('mascota_id', ['1', True, None, 1.5])
    def test_mascota_id_debe_ser_entero(self, client, usuario_adoptante, mascota_disponible, mascota_id):
        assert crear_por_api(client, usuario_adoptante, mascota_id).status_code == 400


class TestRevisionAdmin:

    def test_solicitud_revisada_no_se_puede_cambiar(self, client, auth_headers_admin, solicitud_pendiente):
        url = f'/solicitudes/admin/revisar/{solicitud_pendiente.id}'
        client.post(url, data={'accion': 'rechazar', 'comentarios': ''})

        client.post(url, data={'accion': 'aprobar', 'comentarios': ''})

        solicitud = db.session.get(Solicitud, solicitud_pendiente.id)
        assert solicitud.estado == 'rechazada'
        assert solicitud.mascota.estado != 'adoptado'

    def test_no_se_aprueba_mascota_ya_adoptada(self, client, auth_headers_admin, solicitud_pendiente):
        otro = Usuario(email='otro@test.com', nombre='Otro', password='password123')
        db.session.add(otro)
        db.session.commit()
        segunda = Solicitud(usuario_id=otro.id, mascota_id=solicitud_pendiente.mascota_id)
        db.session.add(segunda)
        db.session.commit()

        client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}', data={'accion': 'aprobar'})
        client.post(f'/solicitudes/admin/revisar/{segunda.id}', data={'accion': 'aprobar'})

        assert db.session.get(Solicitud, segunda.id).estado == 'pendiente'
