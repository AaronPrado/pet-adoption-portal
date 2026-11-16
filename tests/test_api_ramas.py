"""
Tests de las ramas de error de la API (JWT, login, filtros) y de la
revisión de solicitudes que no cubren test_api.py ni test_solicitudes.py.
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy.exc import IntegrityError

from app import adopciones, db
from app.models import Mascota, Solicitud, Usuario


def token_con(app, **payload):
    return jwt.encode(payload, app.config['JWT_SECRET_KEY'], algorithm='HS256')


def mis_solicitudes(client, token):
    return client.get('/api/solicitudes/mias', headers={'Authorization': f'Bearer {token}'})


class TestJWT:

    def test_token_expirado(self, app, client, usuario_adoptante):
        token = token_con(app, user_id=usuario_adoptante.id,
                          exp=datetime.now(UTC) - timedelta(minutes=1))

        response = mis_solicitudes(client, token)

        assert response.status_code == 401
        assert response.get_json()['error'] == 'Token expirado'

    def test_token_firmado_con_otra_clave(self, client, usuario_adoptante):
        otra_clave = 'otra-clave-distinta-de-al-menos-32-bytes'
        token = jwt.encode({'user_id': usuario_adoptante.id}, otra_clave, algorithm='HS256')
        assert mis_solicitudes(client, token).get_json()['error'] == 'Token inválido'

    def test_token_sin_user_id(self, app, client):
        assert mis_solicitudes(client, token_con(app, foo='bar')).get_json()['error'] == 'Token inválido'

    def test_usuario_inexistente(self, app, client):
        response = mis_solicitudes(client, token_con(app, user_id=999))
        assert response.get_json()['error'] == 'Usuario no encontrado'

    @pytest.mark.parametrize('cabecera', ['Token abc', 'Bearer', ''])
    def test_cabecera_mal_formada(self, client, cabecera):
        response = client.get('/api/solicitudes/mias', headers={'Authorization': cabecera})
        assert response.status_code == 401


class TestLoginApi:

    def login(self, client, email, password):
        return client.post('/api/auth/login', json={'email': email, 'password': password})

    def test_usuario_de_google_sin_contrasena(self, client):
        db.session.add(Usuario(email='google@test.com', nombre='G', oauth_id='g-1', oauth_provider='google'))
        db.session.commit()

        assert self.login(client, 'google@test.com', 'cualquiera').status_code == 401

    def test_cuenta_desactivada(self, client, usuario_adoptante):
        usuario_adoptante.activo = False
        db.session.commit()

        response = self.login(client, 'adoptante@test.com', 'password123')

        assert response.status_code == 401
        assert response.get_json()['error'] == 'Cuenta desactivada'

    def test_email_se_normaliza(self, client, usuario_adoptante):
        assert self.login(client, ' ADOPTANTE@test.com ', 'password123').status_code == 200


class TestFiltrosApiMascotas:

    @pytest.fixture
    def mascotas(self, app):
        db.session.add_all([
            Mascota(nombre='Toby', especie='Perro', descripcion='Descripción', raza='Beagle',
                    edad_aprox=2, tamano='Mediano'),
            Mascota(nombre='Max', especie='Perro', descripcion='Descripción', raza='Mastín',
                    edad_aprox=7, tamano='Grande'),
        ])
        db.session.commit()

    @pytest.mark.parametrize('query, esperados', [
        ('raza=Beagle', ['Toby']),
        ('edad_aprox=7', ['Max']),
        ('tamano=Grande', ['Max']),
        ('especie=Perro&tamano=Mediano', ['Toby']),
    ])
    def test_filtros(self, client, mascotas, query, esperados):
        nombres = [m['nombre'] for m in client.get(f'/api/mascotas/?{query}').get_json()]
        assert nombres == esperados


class TestCrearSolicitudApi:

    def crear(self, app, client, usuario, cuestionario):
        token = token_con(app, user_id=usuario.id,
                          exp=datetime.now(UTC) + timedelta(hours=1))
        return client.post('/api/solicitudes/', json={'mascota_id': 1, 'cuestionario': cuestionario},
                           headers={'Authorization': f'Bearer {token}'})

    def test_clave_demasiado_larga(self, app, client, usuario_adoptante, mascota_disponible):
        assert self.crear(app, client, usuario_adoptante, {'x' * 101: 'valor'}).status_code == 400

    def test_duplicado_simultaneo_devuelve_409(self, app, client, usuario_adoptante,
                                               mascota_disponible, monkeypatch):
        """Si otra petición inserta la misma solicitud a la vez, salta la restricción única."""
        def fallar():
            raise IntegrityError('INSERT', {}, Exception('unique_usuario_mascota'))
        monkeypatch.setattr(db.session, 'commit', fallar)

        response = self.crear(app, client, usuario_adoptante, {'vivienda_tipo': 'Casa'})

        assert response.status_code == 409


class TestSolicitudesWeb:

    def test_solicitud_previa_rechazada_no_permite_otra(self, client, auth_headers_adoptante,
                                                        solicitud_pendiente):
        solicitud_pendiente.estado = 'rechazada'
        solicitud_pendiente.mascota.estado = 'disponible'
        db.session.commit()

        response = client.get(f'/solicitudes/nueva/{solicitud_pendiente.mascota_id}', follow_redirects=True)

        assert 'Ya has enviado una solicitud para esta mascota.' in response.data.decode()

    def test_envio_simultaneo_duplicado(self, client, auth_headers_adoptante, mascota_disponible, monkeypatch):
        """Si otra petición inserta la misma solicitud a la vez, salta la restricción única."""
        def fallar(*args):
            raise adopciones.SolicitudDuplicada()
        monkeypatch.setattr(adopciones, 'crear_solicitud', fallar)

        response = client.post(f'/solicitudes/nueva/{mascota_disponible.id}', data={}, follow_redirects=True)

        assert 'Ya has enviado una solicitud para esta mascota.' in response.data.decode()
        assert Solicitud.query.count() == 0

    def test_adoptada_mientras_se_rellenaba(self, client, auth_headers_adoptante, mascota_disponible, monkeypatch):
        """Otra petición la adopta entre la carga del formulario y el envío."""
        def fallar(*args):
            raise adopciones.MascotaNoDisponible()
        monkeypatch.setattr(adopciones, 'crear_solicitud', fallar)

        response = client.post(f'/solicitudes/nueva/{mascota_disponible.id}', data={}, follow_redirects=True)

        assert 'Esta mascota ya no está disponible para adopción.' in response.data.decode()
        assert response.request.path == f'/mascotas/{mascota_disponible.id}'

    def test_mascota_borrada_mientras_se_rellenaba(self, client, auth_headers_adoptante, mascota_disponible,
                                                    monkeypatch):
        def fallar(*args):
            raise adopciones.MascotaNoEncontrada()
        monkeypatch.setattr(adopciones, 'crear_solicitud', fallar)

        response = client.post(f'/solicitudes/nueva/{mascota_disponible.id}', data={})

        assert response.status_code == 404

    def test_accion_desconocida_no_cambia_la_solicitud(self, client, auth_headers_admin, solicitud_pendiente):
        client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}', data={'accion': 'borrar'})

        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'pendiente'
