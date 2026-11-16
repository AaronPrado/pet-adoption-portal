"""
Tests de endurecimiento de la autenticación: cuentas desactivadas,
redirecciones tras el login, login con Google y límite de intentos.
"""

import re

import pytest

from app import create_app, db, oauth
from app.models import Usuario
from app.routes.api.auth import generate_token
from app.routes.auth import es_redireccion_segura
from config import TestingConfig

# Destinos de `next` que no deben provocar una redirección fuera del sitio
NEXT_PELIGROSOS = [
    'https://evil.com', 'http://evil.com/mascotas', '//evil.com', '///evil.com',
    '/\\evil.com', '\\\\evil.com', '/\\/evil.com', '/\t/evil.com', '/\n/evil.com',
    '/\x7f/evil.com',
    ' //evil.com', 'javascript:alert(1)', 'JavaScript:alert(1)', 'javascript://evil.com/%0aalert(1)',
    'data:text/html,evil.com', 'evil.com',
]


def login(client, email='adoptante@test.com', password='password123', next_url=None):
    url = '/auth/login' + (f'?next={next_url}' if next_url else '')
    return client.post(url, data={'email': email, 'password': password})


class TestRedireccionNext:

    @pytest.mark.parametrize('destino', ['/mascotas/', '/solicitudes/mis-solicitudes?x=1'])
    def test_rutas_locales_permitidas(self, destino):
        assert es_redireccion_segura(destino)

    @pytest.mark.parametrize('destino', [
        None, '', 'https://evil.com', '//evil.com', '/\\evil.com',
        '\\\\evil.com', 'javascript:alert(1)', 'mascotas', *NEXT_PELIGROSOS
    ])
    def test_destinos_externos_rechazados(self, destino):
        assert not es_redireccion_segura(destino)

    def test_login_no_redirige_fuera(self, client, usuario_adoptante):
        response = login(client, next_url='//evil.com')
        assert response.status_code == 302
        assert 'evil.com' not in response.headers['Location']

    def test_login_respeta_next_local(self, client, usuario_adoptante):
        response = login(client, next_url='/mascotas/')
        assert response.headers['Location'].endswith('/mascotas/')

    @pytest.mark.parametrize('destino', NEXT_PELIGROSOS)
    def test_login_ignora_next_peligroso_del_formulario(self, client, usuario_adoptante, destino):
        response = client.post('/auth/login', data={
            'email': 'adoptante@test.com', 'password': 'password123', 'next': destino})
        assert response.status_code == 302
        assert response.headers['Location'] == '/'

    @pytest.mark.parametrize('destino', NEXT_PELIGROSOS)
    def test_registro_ignora_next_peligroso(self, client, destino):
        response = client.post('/auth/registro', data={
            'email': 'nuevo@test.com', 'nombre': 'Nuevo', 'password': 'password123',
            'password_confirm': 'password123', 'next': destino})
        assert response.status_code == 302
        assert response.headers['Location'] == '/'

    @pytest.mark.parametrize('url', ['/auth/login', '/auth/registro'])
    @pytest.mark.parametrize('destino', NEXT_PELIGROSOS)
    def test_formularios_no_conservan_next_peligroso(self, client, url, destino):
        html = client.get(url, query_string={'next': destino}).data.decode()
        assert 'name="next"' not in html
        assert 'evil.com' not in html

    @pytest.mark.parametrize('destino', NEXT_PELIGROSOS)
    def test_google_no_guarda_next_peligroso(self, client, destino, monkeypatch):
        google = oauth.create_client('google')
        monkeypatch.setattr(google, 'load_server_metadata', lambda: {
            'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth'})
        client.get('/auth/google', query_string={'next': destino})
        with client.session_transaction() as sesion:
            assert 'next_google' not in sesion

    def test_next_del_formulario_con_csrf_activo(self, app, usuario_adoptante):
        """Con CSRF activo, el `next` viaja en el formulario junto al token."""
        app.config['WTF_CSRF_ENABLED'] = True
        client = app.test_client()
        html = client.get('/auth/login?next=/solicitudes/nueva/7').data.decode()
        token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
        next_oculto = re.search(r'name="next" value="([^"]+)"', html).group(1)

        response = client.post('/auth/login', data={
            'email': 'adoptante@test.com', 'password': 'password123',
            'csrf_token': token, 'next': next_oculto})

        assert response.headers['Location'] == '/solicitudes/nueva/7'


def token_de(client, url='/auth/login'):
    """Token CSRF del formulario de `url`."""
    html = client.get(url).data.decode()
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


class TestRenovacionTokenCsrf:
    """El token dura la sesión, así que se renueva al iniciarla y al cerrarla."""

    @pytest.fixture
    def csrf_client(self, app, usuario_adoptante):
        app.config['WTF_CSRF_ENABLED'] = True
        return app.test_client()

    def test_token_anterior_al_login_deja_de_valer(self, csrf_client):
        antiguo = token_de(csrf_client)
        csrf_client.post('/auth/login', data={
            'email': 'adoptante@test.com', 'password': 'password123', 'csrf_token': antiguo})

        assert csrf_client.post('/auth/logout', data={'csrf_token': antiguo}).status_code == 400
        nuevo = token_de(csrf_client, '/mascotas/catalogo')
        assert nuevo != antiguo
        assert csrf_client.post('/auth/logout', data={'csrf_token': nuevo}).status_code == 302

    def test_token_anterior_al_registro_deja_de_valer(self, csrf_client):
        antiguo = token_de(csrf_client, '/auth/registro')
        respuesta = csrf_client.post('/auth/registro', data={
            'email': 'nuevo@test.com', 'nombre': 'N', 'password': 'password123',
            'password_confirm': 'password123', 'csrf_token': antiguo})

        assert respuesta.status_code == 302
        assert csrf_client.post('/auth/logout', data={'csrf_token': antiguo}).status_code == 400

    def test_token_de_la_sesion_cerrada_deja_de_valer(self, csrf_client):
        csrf_client.post('/auth/login', data={
            'email': 'adoptante@test.com', 'password': 'password123', 'csrf_token': token_de(csrf_client)})
        de_la_sesion = token_de(csrf_client, '/mascotas/catalogo')
        assert csrf_client.post('/auth/logout', data={'csrf_token': de_la_sesion}).status_code == 302

        respuesta = csrf_client.post('/auth/login', data={
            'email': 'adoptante@test.com', 'password': 'password123', 'csrf_token': de_la_sesion})
        assert respuesta.status_code == 400


class TestCuentaDesactivada:

    def test_desactivar_cierra_sesion_abierta(self, client, usuario_adoptante):
        login(client)
        assert client.get('/solicitudes/mis-solicitudes').status_code == 200

        usuario_adoptante.activo = False
        db.session.commit()

        response = client.get('/solicitudes/mis-solicitudes')
        assert response.status_code == 302
        assert '/auth/login' in response.headers['Location']

    def test_jwt_de_cuenta_desactivada_rechazado(self, client, usuario_adoptante):
        token = generate_token(usuario_adoptante.id)
        usuario_adoptante.activo = False
        db.session.commit()

        response = client.get('/api/solicitudes/mias',
                              headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 401


class TestGoogleOAuth:

    @pytest.fixture
    def google_devuelve(self, app, monkeypatch):
        """Sustituye el intercambio de código con Google por datos fijos."""
        def configurar(userinfo):
            client = oauth.create_client('google')
            monkeypatch.setattr(client, 'authorize_access_token',
                                lambda **kwargs: {'userinfo': userinfo})
        return configurar

    def test_email_no_verificado_rechazado(self, client, usuario_admin, google_devuelve):
        google_devuelve({'sub': 'g-1', 'email': 'admin@test.com', 'email_verified': False})

        client.get('/auth/google/callback')

        assert db.session.get(Usuario, usuario_admin.id).oauth_id is None
        assert client.get('/mascotas/admin').status_code == 302

    def test_cuenta_desactivada_no_entra_con_google(self, client, usuario_adoptante, google_devuelve):
        usuario_adoptante.activo = False
        db.session.commit()
        google_devuelve({'sub': 'g-2', 'email': 'adoptante@test.com', 'email_verified': True})

        client.get('/auth/google/callback')

        assert client.get('/solicitudes/mis-solicitudes').status_code == 302

    def test_login_con_google_renueva_el_token_csrf(self, app, usuario_adoptante, google_devuelve):
        app.config['WTF_CSRF_ENABLED'] = True
        client = app.test_client()
        antiguo = token_de(client)
        google_devuelve({'sub': 'g-4', 'email': 'adoptante@test.com', 'email_verified': True})

        client.get('/auth/google/callback')

        assert client.post('/auth/logout', data={'csrf_token': antiguo}).status_code == 400
        assert client.post('/auth/logout', data={'csrf_token': token_de(client, '/')}).status_code == 302

    def test_email_verificado_enlaza_cuenta(self, client, usuario_adoptante, google_devuelve):
        google_devuelve({'sub': 'g-3', 'email': 'Adoptante@Test.com', 'email_verified': True})

        client.get('/auth/google/callback')

        assert db.session.get(Usuario, usuario_adoptante.id).oauth_id == 'g-3'
        assert client.get('/solicitudes/mis-solicitudes').status_code == 200


class TestLimiteIntentos:

    @pytest.fixture
    def client_con_limite(self, monkeypatch):
        monkeypatch.setattr(TestingConfig, 'RATELIMIT_ENABLED', True)
        app = create_app('testing')
        with app.app_context():
            db.create_all()
            db.session.add(Usuario(email='a@test.com', nombre='A', password='password123'))
            db.session.commit()
            yield app.test_client()
            db.session.remove()
            db.drop_all()

    def test_login_web_bloquea_tras_5_intentos(self, client_con_limite):
        codigos = [login(client_con_limite, 'a@test.com', 'mala').status_code for _ in range(6)]
        assert codigos[:5] == [200] * 5
        assert codigos[5] == 429

    def test_login_api_bloquea_tras_5_intentos(self, client_con_limite):
        codigos = [
            client_con_limite.post('/api/auth/login',
                                   json={'email': 'a@test.com', 'password': 'mala'}).status_code
            for _ in range(6)
        ]
        assert codigos[:5] == [401] * 5
        assert codigos[5] == 429

        bloqueada = client_con_limite.post('/api/auth/login', json={'email': 'a@test.com', 'password': 'mala'})
        assert bloqueada.get_json() == {'error': 'Demasiadas peticiones, inténtalo más tarde'}

    def test_registro_bloquea_tras_10_intentos(self, client_con_limite):
        """El registro inicia sesión: se limita para no crear cuentas en masa."""
        # Los intentos fallidos también cuentan (si no, el registro correcto
        # dejaría la sesión iniciada y los siguientes no llegarían al formulario)
        codigos = [
            client_con_limite.post('/auth/registro', data={
                'email': f'masivo{i}@test.com', 'nombre': 'M', 'password': 'password123',
                'password_confirm': 'otra'}).status_code
            for i in range(10)
        ]
        bloqueado = client_con_limite.post('/auth/registro', data={
            'email': 'masivo@test.com', 'nombre': 'M', 'password': 'password123',
            'password_confirm': 'password123'})

        assert codigos == [400] * 10
        assert bloqueado.status_code == 429
        assert Usuario.query.filter_by(email='masivo@test.com').count() == 0

    def test_registro_get_no_cuenta_para_el_limite(self, client_con_limite):
        for _ in range(11):
            client_con_limite.get('/auth/registro')
        respuesta = client_con_limite.post('/auth/registro', data={
            'email': 'uno@test.com', 'nombre': 'U', 'password': 'password123',
            'password_confirm': 'password123'})
        assert respuesta.status_code == 302
