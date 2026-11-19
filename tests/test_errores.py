"""
Tests del manejo de errores: páginas de error en español con navegación y
salida, CSRF caducado, límite de intentos y errores internos. La API sigue
respondiendo en JSON.
"""

import io
import logging
import re

import pytest
from flask import abort
from flask_wtf.csrf import CSRFError

from app import create_app, db
from app.models import Usuario
from config import TestingConfig


def h1(html):
    """Texto del único h1 de la página."""
    titulos = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    assert len(titulos) == 1, titulos
    return titulos[0].strip()


def enlaces(html):
    """Pares (href, texto) de los enlaces de salida de la página de error."""
    bloque = re.search(r'<div class="cabecera-pagina__acciones">(.*?)</div>', html, re.S).group(1)
    return [(href, texto.strip()) for href, texto in re.findall(r'<a [^>]*href="([^"]*)"[^>]*>(.*?)</a>', bloque, re.S)]


@pytest.fixture
def rutas_de_error(app):
    """Rutas de prueba que provocan los errores que la app no lanza por sí sola."""
    app.config['PROPAGATE_EXCEPTIONS'] = False

    @app.route('/_prueba/<int:codigo>')
    def provocar(codigo):
        abort(codigo)

    @app.route('/_prueba/excepcion')
    def excepcion():
        raise RuntimeError('detalle interno que no debe verse')

    # Ruta bajo /api/ que no es de flask-restx: los manejadores web no la tocan
    @app.route('/api/_prueba/<int:codigo>')
    def provocar_api(codigo):
        abort(codigo)

    @app.route('/api/_prueba/csrf')
    def csrf_api():
        raise CSRFError('The CSRF token is missing.')

    return app


@pytest.fixture
def csrf_client(app):
    """Cliente con la protección CSRF activada (en testing está desactivada)."""
    app.config['WTF_CSRF_ENABLED'] = True
    return app.test_client()


class TestPaginasDeError:

    @pytest.mark.parametrize('url, metodo, codigo, titulo', [
        ('/_prueba/400', 'get', 400, 'No hemos podido procesar la petición'),
        ('/_prueba/403', 'get', 403, 'No tienes acceso a esta página'),
        ('/no-existe', 'get', 404, 'No encontramos esta página'),
        ('/auth/logout', 'get', 405, 'Esta acción no está disponible desde aquí'),
        ('/_prueba/405', 'get', 405, 'Esta acción no está disponible desde aquí'),
        ('/_prueba/429', 'get', 429, 'Has hecho demasiados intentos'),
        ('/_prueba/500', 'get', 500, 'Algo ha fallado'),
    ])
    def test_pagina_en_espanol_con_navegacion_y_salida(self, client, rutas_de_error, url, metodo, codigo, titulo):
        response = getattr(client, metodo)(url)
        html = response.data.decode()

        assert response.status_code == codigo
        assert response.mimetype == 'text/html'
        assert '<html lang="es">' in html
        assert h1(html) == titulo
        assert 'aria-label="Principal"' in html
        assert ('/', 'Ir al inicio') in enlaces(html)

    def test_404_enlaza_al_catalogo(self, client):
        html = client.get('/mascotas/99999').data.decode()

        assert ('/mascotas/catalogo', 'Ver mascotas disponibles') in enlaces(html)

    def test_403_ofrece_iniciar_sesion_al_anonimo(self, client, rutas_de_error):
        html = client.get('/_prueba/403').data.decode()

        assert enlaces(html) == [('/auth/login', 'Iniciar sesión'), ('/', 'Ir al inicio')]

    def test_403_con_sesion_no_ofrece_iniciar_sesion(self, client, rutas_de_error, auth_headers_adoptante):
        html = client.get('/_prueba/403').data.decode()

        assert enlaces(html) == [('/', 'Ir al inicio')]

    def test_405_conserva_la_cabecera_allow(self, client):
        response = client.get('/auth/logout')

        assert 'POST' in response.headers['Allow']

    def test_429_sin_limite_conocido_pide_esperar_un_minuto(self, client, rutas_de_error):
        response = client.get('/_prueba/429')

        assert response.headers['Retry-After'] == '60'
        assert 'Espera un minuto y vuelve a intentarlo.' in response.data.decode()

    def test_429_si_falla_el_limitador_pide_esperar_un_minuto(self, client, rutas_de_error, monkeypatch):
        from flask_limiter import Limiter

        def roto(self):
            raise RuntimeError('almacenamiento caído')

        monkeypatch.setattr(Limiter, 'current_limit', property(roto))
        response = client.get('/_prueba/429')

        assert response.status_code == 429
        assert response.headers['Retry-After'] == '60'

    def test_titulo_de_la_pagina(self, client):
        html = client.get('/no-existe').data.decode()

        assert '<title>No encontramos esta página - Portal de Adopción</title>' in html


class TestErrorInterno:

    def test_excepcion_muestra_mensaje_generico_y_se_registra_una_vez(self, client, rutas_de_error, caplog):
        with caplog.at_level(logging.ERROR):
            response = client.get('/_prueba/excepcion')
        html = response.data.decode()

        assert response.status_code == 500
        assert h1(html) == 'Algo ha fallado'
        assert 'detalle interno' not in html
        assert 'RuntimeError' not in html
        # Flask ya la registra; el manejador no la duplica
        registros = [r for r in caplog.records if r.exc_info and r.exc_info[0] is RuntimeError]
        assert len(registros) == 1

    def test_abort_500_explicito_se_registra(self, client, rutas_de_error, caplog):
        with caplog.at_level(logging.ERROR):
            client.get('/_prueba/500')

        assert [r.getMessage() for r in caplog.records] == ["Error 500 en GET '/_prueba/500'"]
        assert caplog.records[0].exc_info is not None

    def test_ofrece_mis_solicitudes_al_adoptante(self, client, rutas_de_error, auth_headers_adoptante):
        html = client.get('/_prueba/excepcion').data.decode()

        assert enlaces(html)[0] == ('/solicitudes/mis-solicitudes', 'Ver mis solicitudes')

    def test_sin_sesion_no_ofrece_mis_solicitudes(self, client, rutas_de_error):
        html = client.get('/_prueba/excepcion').data.decode()

        assert enlaces(html) == [('/', 'Ir al inicio')]

    def test_rollback_fallido_no_impide_la_pagina(self, client, rutas_de_error, monkeypatch):
        def rollback_roto():
            raise RuntimeError('conexión perdida')

        monkeypatch.setattr(db.session, 'rollback', rollback_roto)
        response = client.get('/_prueba/excepcion')

        assert response.status_code == 500
        assert h1(response.data.decode()) == 'Algo ha fallado'

    def test_si_falla_la_plantilla_responde_texto_minimo(self, client, rutas_de_error, monkeypatch):
        """Si la propia página de error falla (p. ej. sin base de datos), se
        responde una página mínima en español en lugar de la de Werkzeug."""
        import app.errores as paquete

        def plantilla_rota(*args, **kwargs):
            raise RuntimeError('sin base de datos')

        monkeypatch.setattr(paquete, 'render_template', plantilla_rota)
        response = client.get('/_prueba/excepcion')
        html = response.data.decode()

        assert response.status_code == 500
        assert '<html lang="es">' in html
        assert h1(html) == 'Algo ha fallado'
        assert 'href="/"' in html
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
        assert 'sin base de datos' not in html


class TestCSRF:

    def post_sin_token(self, cliente, referer=None):
        cabeceras = {'Referer': referer} if referer else {}
        return cliente.post('/auth/login', data={'email': 'a@test.com', 'password': 'x'}, headers=cabeceras)

    def test_token_ausente_explica_que_la_sesion_ha_caducado(self, csrf_client):
        response = self.post_sin_token(csrf_client, 'http://localhost/auth/login?next=/solicitudes/')
        html = response.data.decode()

        assert response.status_code == 400
        assert '<html lang="es">' in html
        assert h1(html) == 'Tu sesión ha caducado'
        assert 'CSRF' not in html and 'token' not in html
        assert enlaces(html)[0] == ('/auth/login?next=/solicitudes/', 'Volver al formulario')

    def test_token_invalido_tambien(self, csrf_client):
        csrf_client.get('/auth/login')
        response = csrf_client.post('/auth/login', data={'csrf_token': 'manipulado'},
                                    headers={'Referer': 'http://localhost/auth/login'})

        assert response.status_code == 400
        assert h1(response.data.decode()) == 'Tu sesión ha caducado'

    @pytest.mark.parametrize('referer', [
        None,
        'https://evil.example/auth/login',
        'http://localhost.evil.example/auth/login',
        'http://localhost//evil.example/x',
        'javascript:alert(1)',
    ])
    def test_referer_ajeno_o_ausente_enlaza_a_la_portada(self, csrf_client, referer):
        html = self.post_sin_token(csrf_client, referer).data.decode()

        assert enlaces(html) == [('/', 'Ir al inicio')]
        assert 'evil' not in html


class TestLimiteDeIntentos:

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

    def test_login_bloqueado_en_espanol_con_retry_after(self, client_con_limite):
        for _ in range(5):
            client_con_limite.post('/auth/login', data={'email': 'a@test.com', 'password': 'mala'})
        response = client_con_limite.post('/auth/login', data={'email': 'a@test.com', 'password': 'mala'})
        html = response.data.decode()

        assert response.status_code == 429
        assert 0 < int(response.headers['Retry-After']) <= 60
        assert '<html lang="es">' in html
        assert h1(html) == 'Has hecho demasiados intentos'
        assert 'Espera un minuto y vuelve a intentarlo.' in html
        assert 'per' not in h1(html)

    def test_registro_bloqueado_indica_los_minutos(self, client_con_limite):
        datos = {'email': 'b@test.com', 'nombre': 'B', 'password': 'password123', 'password_confirm': 'otra'}
        for _ in range(10):
            client_con_limite.post('/auth/registro', data=datos)
        response = client_con_limite.post('/auth/registro', data=datos)
        html = response.data.decode()

        assert response.status_code == 429
        espera = int(response.headers['Retry-After'])
        assert 60 < espera <= 3600
        minutos = re.search(r'Espera (\d+) minutos y vuelve a intentarlo\.', html)
        assert minutos and int(minutos.group(1)) == -(-espera // 60)

    def test_api_sigue_en_json(self, client_con_limite):
        for _ in range(6):
            response = client_con_limite.post('/api/auth/login', json={'email': 'a@test.com', 'password': 'mala'})

        assert response.status_code == 429
        assert response.get_json() == {'error': 'Demasiadas peticiones, inténtalo más tarde'}


class TestApiSinCambios:

    def test_404_de_recurso_en_json(self, client):
        response = client.get('/api/mascotas/99999')

        assert response.status_code == 404
        assert response.get_json() == {'error': 'Recurso no encontrado'}

    def test_405_en_json(self, client):
        response = client.delete('/api/mascotas/')

        assert response.status_code == 405
        assert response.get_json() == {'error': 'Método no permitido'}

    def test_ruta_inexistente_no_usa_la_pagina_web(self, client):
        response = client.get('/api/no-existe')

        assert response.status_code == 404
        assert 'aria-label="Principal"' not in response.data.decode()

    @pytest.mark.parametrize('ruta, codigo', [
        ('/api/_prueba/400', 400), ('/api/_prueba/403', 403), ('/api/_prueba/404', 404),
        ('/api/_prueba/405', 405), ('/api/_prueba/429', 429),
        ('/api/_prueba/500', 500), ('/api/_prueba/csrf', 400),
    ])
    def test_manejadores_web_no_interceptan_la_api(self, client, rutas_de_error, ruta, codigo):
        response = client.get(ruta)

        assert response.status_code == codigo
        assert 'aria-label="Principal"' not in response.data.decode()

    def test_csrf_no_afecta_a_la_api(self, csrf_client):
        response = csrf_client.post('/api/auth/login', json={'email': 'a@test.com', 'password': 'x'})

        assert response.status_code == 401
        assert 'error' in response.get_json()


def test_archivo_demasiado_grande_redirige_con_aviso(client, auth_headers_admin):
    """Una subida de más de 5 MB vuelve al formulario en lugar de dar un 500."""
    grande = io.BytesIO(b'0' * (5 * 1024 * 1024 + 1))
    response = client.post('/mascotas/admin/nueva', data={
        'nombre': 'Rocky',
        'foto': (grande, 'foto.png'),
    }, content_type='multipart/form-data')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/mascotas/admin/nueva')

    with client.session_transaction() as sesion:
        mensajes = [m for _, m in sesion.get('_flashes', [])]
    assert 'La foto ocupa demasiado. Elige una de 5 MB como máximo.' in mensajes
