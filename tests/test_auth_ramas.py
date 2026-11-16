"""
Tests de las ramas de validación y error del registro, login local y
login con Google que no cubre test_auth.py.
"""

import re
from urllib.parse import parse_qs, urlparse

import pytest
from authlib.integrations.base_client.errors import OAuthError
from sqlalchemy.exc import SQLAlchemyError

from app import db, oauth
from app.models import Usuario


def datos_registro(**cambios):
    datos = {
        'email': 'nuevo@test.com',
        'nombre': 'Nuevo',
        'password': 'password123',
        'password_confirm': 'password123',
    }
    datos.update(cambios)
    return datos


class TestRegistro:

    @pytest.mark.parametrize('campo', ['email', 'nombre', 'password'])
    def test_campos_obligatorios(self, client, campo):
        response = client.post('/auth/registro', data=datos_registro(**{campo: ''}))

        html = response.data.decode()
        assert response.status_code == 400
        assert 'Revisa los campos marcados.' in html
        assert campo_con_error(html, campo) is not None
        assert Usuario.query.count() == 0

    def test_contrasena_corta(self, client):
        response = client.post('/auth/registro',
                               data=datos_registro(password='corta12', password_confirm='corta12'))

        assert 'al menos 8 caracteres' in response.data.decode()
        assert Usuario.query.count() == 0

    def test_email_se_normaliza(self, client):
        client.post('/auth/registro', data=datos_registro(email='  Nuevo@Test.COM '))
        assert Usuario.query.one().email == 'nuevo@test.com'

    def test_error_de_base_de_datos_muestra_mensaje_generico(self, client, monkeypatch):
        def fallar():
            raise SQLAlchemyError('fallo simulado')
        monkeypatch.setattr(db.session, 'commit', fallar)

        html = client.post('/auth/registro', data=datos_registro()).data.decode()

        assert 'No se pudo crear el usuario' in html
        assert 'fallo simulado' not in html

    @pytest.mark.parametrize('url', ['/auth/registro', '/auth/login'])
    def test_usuario_autenticado_es_redirigido(self, client, auth_headers_adoptante, url):
        response = client.get(url)
        assert response.status_code == 302
        assert response.headers['Location'] == '/'


class TestLoginLocal:

    @pytest.mark.parametrize('datos', [
        {'email': '', 'password': 'password123'},
        {'email': 'adoptante@test.com', 'password': ''},
    ])
    def test_campos_obligatorios(self, client, datos):
        response = client.post('/auth/login', data=datos)
        assert response.status_code == 400
        assert 'Revisa los campos marcados.' in response.data.decode()

    def test_cuenta_desactivada(self, client, usuario_adoptante):
        usuario_adoptante.activo = False
        db.session.commit()

        response = client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'password123'})

        assert 'Tu cuenta ha sido desactivada' in response.data.decode()
        assert client.get('/solicitudes/mis-solicitudes').status_code == 302

    def test_email_con_mayusculas(self, client, usuario_adoptante):
        response = client.post('/auth/login', data={'email': ' Adoptante@Test.com', 'password': 'password123'})
        assert response.status_code == 302


class TestGoogle:

    @pytest.fixture
    def google(self, app, monkeypatch):
        """Cliente OAuth de Google sin llamadas de red."""
        client = oauth.create_client('google')
        monkeypatch.setattr(client, 'load_server_metadata', lambda: {
            'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth'
        })
        return client

    def test_login_redirige_a_google(self, client, google):
        response = client.get('/auth/google')

        assert response.status_code == 302
        destino = urlparse(response.headers['Location'])
        assert destino.netloc == 'accounts.google.com'
        parametros = parse_qs(destino.query)
        assert parametros['redirect_uri'] == ['http://localhost/auth/google/callback']
        assert 'state' in parametros

    def test_callback_con_error_oauth(self, client, google, monkeypatch):
        def fallar(**kwargs):
            raise OAuthError(error='access_denied')
        monkeypatch.setattr(google, 'authorize_access_token', fallar)

        response = client.get('/auth/google/callback', follow_redirects=True)

        assert 'No se pudo completar el inicio de sesión con Google.' in response.data.decode()

    def test_callback_sin_userinfo(self, client, google, monkeypatch):
        monkeypatch.setattr(google, 'authorize_access_token', lambda **kwargs: {})

        response = client.get('/auth/google/callback', follow_redirects=True)

        assert 'Error al obtener información de Google' in response.data.decode()

    def test_callback_crea_usuario_nuevo(self, client, google, monkeypatch):
        monkeypatch.setattr(google, 'authorize_access_token', lambda **kwargs: {'userinfo': {
            'sub': 'g-nuevo', 'email': 'Nueva@Gmail.com', 'email_verified': True,
            'given_name': 'Nueva', 'family_name': 'Usuaria'
        }})

        response = client.get('/auth/google/callback')

        usuario = Usuario.query.filter_by(oauth_id='g-nuevo').one()
        assert usuario.email == 'nueva@gmail.com'
        assert usuario.rol == 'adoptante'
        assert usuario.password_hash is None
        assert response.headers['Location'].endswith('/mascotas/catalogo')

    def test_callback_usuario_ya_enlazado(self, client, google, monkeypatch, usuario_adoptante):
        usuario_adoptante.oauth_id = 'g-existente'
        db.session.commit()
        monkeypatch.setattr(google, 'authorize_access_token', lambda **kwargs: {'userinfo': {
            'sub': 'g-existente', 'email': 'otro-email@gmail.com', 'email_verified': True
        }})

        client.get('/auth/google/callback')

        assert Usuario.query.count() == 1
        assert client.get('/solicitudes/mis-solicitudes').status_code == 200


def campo_con_error(html, campo):
    """Devuelve el mensaje de error que la plantilla muestra junto a `campo`."""
    match = re.search(rf'<div id="{campo}-error"[^>]*>\s*(.*?)\s*</div>', html, re.S)
    return match.group(1) if match else None


def valor_de(html, campo):
    """Devuelve el atributo value del input `campo`, o None si no lo tiene."""
    etiqueta = re.search(rf'<input[^>]*\bid="{campo}"[^>]*>', html, re.S).group(0)
    match = re.search(r'\bvalue="([^"]*)"', etiqueta)
    return match.group(1) if match else None


class TestRegistroConservaDatos:
    """P-02: un error de validación no vacía el formulario de registro."""

    DATOS = {
        'email': 'nuevo@test.com', 'nombre': 'Nuevo', 'apellidos': 'Pérez Gil',
        'telefono': '612345678', 'direccion': 'Calle Mayor 1, Lugo',
        'password': 'secreto-unico-1', 'password_confirm': 'otro-secreto-2',
    }

    def test_contrasenas_distintas_conservan_datos_y_responden_400(self, client):
        response = client.post('/auth/registro', data=self.DATOS)
        html = response.data.decode()

        assert response.status_code == 400
        assert valor_de(html, 'email') == 'nuevo@test.com'
        assert valor_de(html, 'nombre') == 'Nuevo'
        assert valor_de(html, 'apellidos') == 'Pérez Gil'
        assert valor_de(html, 'telefono') == '612345678'
        assert re.search(r'<textarea[^>]*id="direccion"[^>]*>Calle Mayor 1, Lugo</textarea>', html, re.S)
        assert campo_con_error(html, 'password_confirm') == 'Las contraseñas no coinciden.'
        assert 'aria-describedby="password_confirm-error"' in html

    def test_nunca_se_rellena_la_contrasena(self, client):
        html = client.post('/auth/registro', data=self.DATOS).data.decode()

        assert valor_de(html, 'password') is None
        assert valor_de(html, 'password_confirm') is None
        assert 'secreto-unico-1' not in html
        assert 'otro-secreto-2' not in html

    def test_campos_obligatorios_muestran_error_en_cada_campo(self, client):
        response = client.post('/auth/registro', data={'apellidos': 'Gil'})
        html = response.data.decode()

        assert response.status_code == 400
        assert campo_con_error(html, 'email') == 'El email es obligatorio.'
        assert campo_con_error(html, 'nombre') == 'El nombre es obligatorio.'
        assert campo_con_error(html, 'password') == 'La contraseña es obligatoria.'
        assert valor_de(html, 'apellidos') == 'Gil'

    def test_contrasena_corta_error_junto_al_campo(self, client):
        html = client.post('/auth/registro',
                           data=datos_registro(password='corta12', password_confirm='corta12')).data.decode()
        assert campo_con_error(html, 'password') == 'La contraseña debe tener al menos 8 caracteres.'

    def test_get_sin_errores(self, client):
        html = client.get('/auth/registro').data.decode()
        assert 'is-invalid' not in html
        assert 'aria-invalid' not in html

    def test_valores_se_escapan(self, client):
        html = client.post('/auth/registro',
                           data=datos_registro(nombre='"><script>x</script>', password_confirm='otra')).data.decode()
        assert '<script>x</script>' not in html


class TestLoginConservaDatos:
    """P-02 y P-07 en el login."""

    def test_login_fallido_conserva_email_y_no_la_contrasena(self, client, usuario_adoptante):
        html = client.post('/auth/login',
                           data={'email': 'adoptante@test.com', 'password': 'clave-mala-xyz'}).data.decode()

        assert 'Email o contraseña incorrectos.' in html
        assert valor_de(html, 'email') == 'adoptante@test.com'
        assert valor_de(html, 'password') is None
        assert 'clave-mala-xyz' not in html

    def test_campos_vacios_responden_400_con_error_en_el_campo(self, client):
        response = client.post('/auth/login', data={'email': 'a@test.com', 'password': ''})
        html = response.data.decode()

        assert response.status_code == 400
        assert campo_con_error(html, 'password') == 'La contraseña es obligatoria.'
        assert campo_con_error(html, 'email') is None
        assert valor_de(html, 'email') == 'a@test.com'
