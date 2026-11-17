"""
Tests de protecciones web: CSRF, cookies, cabeceras de seguridad y XSS.
"""

import re

import pytest

from app import db
from app.models import Mascota


@pytest.fixture
def csrf_client(app):
    """Cliente con la protección CSRF activada (en testing está desactivada)."""
    app.config['WTF_CSRF_ENABLED'] = True
    return app.test_client()


def extraer_csrf(html):
    """Obtiene el token CSRF de un formulario renderizado."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, 'El formulario no incluye csrf_token'
    return match.group(1)


class TestCSRF:

    def test_post_sin_token_rechazado(self, csrf_client, usuario_adoptante):
        response = csrf_client.post('/auth/login', data={
            'email': 'adoptante@test.com',
            'password': 'password123'
        })
        assert response.status_code == 400

    def test_post_con_token_aceptado(self, csrf_client, usuario_adoptante):
        token = extraer_csrf(csrf_client.get('/auth/login').data.decode())
        response = csrf_client.post('/auth/login', data={
            'email': 'adoptante@test.com',
            'password': 'password123',
            'csrf_token': token
        })
        assert response.status_code == 302

    def test_api_no_requiere_csrf(self, csrf_client, usuario_adoptante):
        response = csrf_client.post('/api/auth/login', json={
            'email': 'adoptante@test.com',
            'password': 'password123'
        })
        assert response.status_code == 200

    def test_formularios_incluyen_token(self, client, auth_headers_admin, mascota_disponible):
        for url in ['/auth/login', '/auth/registro', '/mascotas/admin/nueva',
                    f'/mascotas/admin/editar/{mascota_disponible.id}', '/mascotas/admin']:
            # El admin autenticado es redirigido desde login/registro; basta con el resto
            response = client.get(url)
            if response.status_code == 200:
                assert 'name="csrf_token"' in response.data.decode(), url

    def test_logout_por_get_no_permitido(self, client, auth_headers_adoptante):
        assert client.get('/auth/logout').status_code == 405


class TestCabeceras:

    def test_cabeceras_seguridad(self, client):
        response = client.get('/')
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert response.headers['X-Frame-Options'] == 'DENY'
        assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']

    def test_csp_sin_unsafe_inline_ni_cdn(self, client):
        """ADR-0001: Bootstrap se sirve desde /static, así que la CSP no
        necesita la CDN ni 'unsafe-inline'. Se fijan todas las directivas
        para que ninguna se relaje sin que falle este test."""
        csp = client.get('/').headers['Content-Security-Policy']
        assert 'unsafe-inline' not in csp
        assert 'jsdelivr' not in csp
        directivas = dict(d.strip().split(' ', 1) for d in csp.split(';'))
        assert directivas == {
            'default-src': "'self'",
            'script-src': "'self'",
            'style-src': "'self'",
            'img-src': "'self' https: data:",
            'font-src': "'self'",
            'object-src': "'none'",
            'base-uri': "'none'",
            'form-action': "'self'",
            'frame-ancestors': "'none'",
        }

    def test_cookie_sesion_samesite(self, client, usuario_adoptante):
        response = client.post('/auth/login', data={
            'email': 'adoptante@test.com',
            'password': 'password123'
        })
        cookie = response.headers.get('Set-Cookie', '')
        assert 'HttpOnly' in cookie
        assert 'SameSite=Lax' in cookie


class TestXSS:

    def test_nombre_mascota_no_se_ejecuta_en_panel_admin(self, client, auth_headers_admin):
        nombre = "x');alert(1);//"
        db.session.add(Mascota(nombre=nombre, especie='Perro', descripcion='Descripción de prueba'))
        db.session.commit()

        html = client.get('/mascotas/admin').data.decode()

        # El nombre ya no se interpola en JavaScript inline, solo en un atributo escapado
        assert 'onclick' not in html
        assert 'data-confirmar="¿Estás seguro de eliminar a x&#39;);alert(1);//?"' in html
