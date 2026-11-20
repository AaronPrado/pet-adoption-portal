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
        assert 'id="resumen-errores"' in html
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

        assert 'No hemos podido crear tu cuenta' in html
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
        assert 'id="resumen-errores"' in response.data.decode()

    def test_cuenta_desactivada(self, client, usuario_adoptante):
        usuario_adoptante.activo = False
        db.session.commit()

        response = client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'password123'})

        assert 'Tu cuenta está desactivada' in response.data.decode()
        assert client.get('/solicitudes/mis-solicitudes').status_code == 302

    def test_email_con_mayusculas(self, client, usuario_adoptante):
        response = client.post('/auth/login', data={'email': ' Adoptante@Test.com', 'password': 'password123'})
        assert response.status_code == 302


class TestGoogle:

    @pytest.fixture
    def google(self, app, monkeypatch):
        """Cliente OAuth de Google configurado y sin llamadas de red."""
        app.config.update(GOOGLE_CLIENT_ID='id-de-prueba', GOOGLE_CLIENT_SECRET='secreto-de-prueba')
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

        assert 'No hemos podido obtener tus datos de Google' in response.data.decode()

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
    match = re.search(rf'<p id="{campo}-error"[^>]*>\s*<span[^>]*>Error: </span>(.*?)</p>', html, re.S)
    return match.group(1).strip() if match else None


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
        assert campo_con_error(html, 'email') == 'El correo electrónico es obligatorio.'
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


class TestRegistroIniciaSesion:
    """P-07: el registro inicia sesión y vuelve a `next`."""

    def test_registro_inicia_sesion(self, client):
        response = client.post('/auth/registro', data=datos_registro())

        assert response.status_code == 302
        assert response.headers['Location'] == '/'
        assert client.get('/solicitudes/mis-solicitudes').status_code == 200

    def test_registro_redirige_a_next_local(self, client):
        response = client.post('/auth/registro', data=datos_registro(next='/solicitudes/nueva/1'))
        assert response.headers['Location'] == '/solicitudes/nueva/1'

    def test_registro_acepta_next_en_la_query(self, client):
        response = client.post('/auth/registro?next=/mascotas/1', data=datos_registro())
        assert response.headers['Location'] == '/mascotas/1'

    def test_formulario_conserva_next(self, client):
        html = client.get('/auth/registro?next=/solicitudes/nueva/3').data.decode()
        assert '<input type="hidden" name="next" value="/solicitudes/nueva/3">' in html
        assert 'href="/auth/login?next=/solicitudes/nueva/3"' in html

    def test_error_conserva_next(self, client):
        html = client.post('/auth/registro',
                           data=datos_registro(password_confirm='otra', next='/mascotas/2')).data.decode()
        assert '<input type="hidden" name="next" value="/mascotas/2">' in html

    def test_email_duplicado_lleva_al_login_con_next(self, client, usuario_adoptante):
        response = client.post('/auth/registro',
                               data=datos_registro(email='adoptante@test.com', next='/mascotas/2'))
        assert response.status_code == 302
        assert response.headers['Location'] == '/auth/login?next=/mascotas/2'
        assert client.get('/solicitudes/mis-solicitudes').status_code == 302


class TestLoginConservaDatos:
    """P-02 y P-07 en el login."""

    def test_login_fallido_conserva_email_y_no_la_contrasena(self, client, usuario_adoptante):
        html = client.post('/auth/login',
                           data={'email': 'adoptante@test.com', 'password': 'clave-mala-xyz'}).data.decode()

        assert 'Correo o contraseña incorrectos.' in html
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

    def test_formulario_conserva_next(self, app, client):
        app.config.update(GOOGLE_CLIENT_ID='id-de-prueba', GOOGLE_CLIENT_SECRET='secreto-de-prueba')
        html = client.get('/auth/login?next=/solicitudes/nueva/3').data.decode()

        assert '<input type="hidden" name="next" value="/solicitudes/nueva/3">' in html
        assert 'href="/auth/registro?next=/solicitudes/nueva/3"' in html
        assert 'href="/auth/google?next=/solicitudes/nueva/3"' in html

    def test_next_en_el_formulario_redirige(self, client, usuario_adoptante):
        response = client.post('/auth/login', data={
            'email': 'adoptante@test.com', 'password': 'password123', 'next': '/solicitudes/nueva/3'})
        assert response.headers['Location'] == '/solicitudes/nueva/3'

    def test_login_fallido_conserva_next(self, client, usuario_adoptante):
        html = client.post('/auth/login', data={
            'email': 'adoptante@test.com', 'password': 'mala', 'next': '/mascotas/2'}).data.decode()
        assert '<input type="hidden" name="next" value="/mascotas/2">' in html

    def test_sin_next_no_hay_campo_oculto(self, client):
        assert 'name="next"' not in client.get('/auth/login').data.decode()


def test_detalle_anonimo_enlaza_login_con_next(client, mascota_disponible):
    """«Inicia sesión para adoptar» vuelve al cuestionario de esa mascota."""
    html = client.get(f'/mascotas/{mascota_disponible.id}').data.decode()
    assert f'href="/auth/login?next=/solicitudes/nueva/{mascota_disponible.id}"' in html


class TestGoogleNext:
    """P-07: el login con Google vuelve a `next`, guardado en la sesión."""

    @pytest.fixture
    def google(self, app, monkeypatch):
        app.config.update(GOOGLE_CLIENT_ID='id-de-prueba', GOOGLE_CLIENT_SECRET='secreto-de-prueba')
        client = oauth.create_client('google')
        monkeypatch.setattr(client, 'load_server_metadata', lambda: {
            'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth'
        })
        monkeypatch.setattr(client, 'authorize_access_token', lambda **kwargs: {'userinfo': {
            'sub': 'g-next', 'email': 'next@gmail.com', 'email_verified': True}})
        return client

    def test_guarda_next_en_la_sesion_y_vuelve(self, client, google):
        client.get('/auth/google?next=/solicitudes/nueva/4')
        with client.session_transaction() as sesion:
            assert sesion['next_google'] == '/solicitudes/nueva/4'

        response = client.get('/auth/google/callback')

        assert response.headers['Location'] == '/solicitudes/nueva/4'
        with client.session_transaction() as sesion:
            assert 'next_google' not in sesion

    def test_sin_next_va_al_catalogo(self, client, google):
        client.get('/auth/google')
        assert client.get('/auth/google/callback').headers['Location'] == '/mascotas/catalogo'

    def test_next_externo_no_se_guarda(self, client, google):
        client.get('/auth/google?next=//evil.com')
        with client.session_transaction() as sesion:
            assert 'next_google' not in sesion
        assert client.get('/auth/google/callback').headers['Location'] == '/mascotas/catalogo'

    def test_nuevo_intento_sin_next_borra_el_anterior(self, client, google):
        client.get('/auth/google?next=/mascotas/1')
        client.get('/auth/google')
        assert client.get('/auth/google/callback').headers['Location'] == '/mascotas/catalogo'

    def test_next_manipulado_en_la_sesion_se_ignora(self, client, google):
        with client.session_transaction() as sesion:
            sesion['next_google'] = 'https://evil.com'
        assert client.get('/auth/google/callback').headers['Location'] == '/mascotas/catalogo'

    def test_fallo_vuelve_al_login_con_next(self, client, google, monkeypatch):
        def fallar(**kwargs):
            raise OAuthError(error='access_denied')
        monkeypatch.setattr(google, 'authorize_access_token', fallar)
        client.get('/auth/google?next=/mascotas/1')

        response = client.get('/auth/google/callback')

        assert response.headers['Location'] == '/auth/login?next=/mascotas/1'
        with client.session_transaction() as sesion:
            assert 'next_google' not in sesion


class TestRediseñoAuth:
    """B4.3: login y registro con el sistema de diseño (P-13, P-16, P-33, P-36, P-42, P-43)."""

    @staticmethod
    def etiqueta(html, campo):
        return re.search(rf'<(?:input|textarea)[^>]*\bid="{campo}"[^>]*>', html, re.S).group(0)

    @pytest.mark.parametrize('url', ['/auth/login', '/auth/registro'])
    def test_paginas_sin_bootstrap_y_con_un_h1(self, client, url):
        html = client.get(url).data.decode()

        assert 'bootstrap' not in html
        assert 'form-control' not in html
        assert html.count('<h1') == 1
        assert 'paginas/auth.css' in html
        assert 'name="csrf_token"' in html

    @pytest.mark.parametrize('url, esperado', [
        ('/auth/login', {'email': 'email', 'password': 'current-password'}),
        ('/auth/registro', {'email': 'email', 'nombre': 'given-name', 'apellidos': 'family-name',
                            'telefono': 'tel', 'password': 'new-password', 'password_confirm': 'new-password'}),
    ])
    def test_autocomplete_de_cada_campo(self, client, url, esperado):
        html = client.get(url).data.decode()
        for campo, valor in esperado.items():
            assert f'autocomplete="{valor}"' in self.etiqueta(html, campo), campo

    def test_registro_tiene_leyenda_y_direccion_opcional(self, client):
        html = client.get('/auth/registro').data.decode()

        assert 'son obligatorios' in html
        assert 'Opcional' in re.search(r'<p id="direccion-ayuda"[^>]*>(.*?)</p>', html, re.S).group(1)
        assert 'Necesaria para solicitudes' not in html
        assert 'placeholder="Mínimo' not in html
        assert 'id="password-ayuda"' in html

    def test_errores_en_el_campo_y_resumen_enlazado(self, client):
        response = client.post('/auth/registro', data={'apellidos': 'Gil'})
        html = response.data.decode()

        assert response.status_code == 400
        assert 'data-resumen-errores' in html
        assert 'href="#email"' in html and 'href="#nombre"' in html and 'href="#password"' in html
        assert 'aria-invalid="true"' in self.etiqueta(html, 'email')
        assert 'email-error' in self.etiqueta(html, 'email')
        # el resumen sustituye al flash genérico
        assert 'Revisa los campos marcados' not in html

    def test_login_vacio_tiene_resumen(self, client):
        html = client.post('/auth/login', data={'email': '', 'password': ''}).data.decode()
        assert 'data-resumen-errores' in html
        assert campo_con_error(html, 'email') == 'El correo electrónico es obligatorio.'

    def test_credenciales_incorrectas_error_en_la_contrasena(self, client, usuario_adoptante):
        response = client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'mala'})
        html = response.data.decode()

        assert response.status_code == 400
        assert campo_con_error(html, 'password') == 'Correo o contraseña incorrectos.'
        assert 'data-resumen-errores' in html
        assert valor_de(html, 'email') == 'adoptante@test.com'
        assert valor_de(html, 'password') is None

    def test_credenciales_incorrectas_no_distinguen_usuario(self, client, usuario_adoptante):
        malo = client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'mala'})
        inexistente = client.post('/auth/login', data={'email': 'nadie@test.com', 'password': 'mala'})
        assert campo_con_error(malo.data.decode(), 'password') == \
            campo_con_error(inexistente.data.decode(), 'password')

    def test_google_configurado_con_svg_propio_sin_recursos_externos(self, app, client):
        app.config.update(GOOGLE_CLIENT_ID='id-de-prueba', GOOGLE_CLIENT_SECRET='secreto-de-prueba')
        html = client.get('/auth/login').data.decode()

        assert 'developers.google.com' not in html
        assert 'href="/auth/google"' in html
        boton = html.split('href="/auth/google"')[1].split('</a>')[0]
        assert '<svg' in boton and 'aria-hidden="true"' in boton

    @pytest.mark.parametrize('id_cliente, secreto', [(None, None), ('id', None), (None, 'secreto'), ('', '')])
    def test_google_sin_configurar_no_muestra_el_boton(self, app, client, id_cliente, secreto):
        app.config.update(GOOGLE_CLIENT_ID=id_cliente, GOOGLE_CLIENT_SECRET=secreto)
        html = client.get('/auth/login').data.decode()
        assert '/auth/google' not in html
        assert 'Continuar con Google' not in html

    def test_entrar_en_google_sin_configurar_redirige_al_login(self, app, client):
        app.config.update(GOOGLE_CLIENT_ID=None, GOOGLE_CLIENT_SECRET=None)

        response = client.get('/auth/google?next=/mascotas/1')

        assert response.status_code == 302
        assert response.headers['Location'] == '/auth/login?next=/mascotas/1'
        html = client.get(response.headers['Location']).data.decode()
        assert 'Ahora mismo no se puede iniciar sesión con Google' in html

    def test_callback_de_google_sin_configurar_no_da_500(self, app, client):
        app.config.update(GOOGLE_CLIENT_ID=None, GOOGLE_CLIENT_SECRET=None)
        assert client.get('/auth/google/callback').status_code == 302

    def test_login_tiene_leyenda_de_obligatorios(self, client):
        assert 'son obligatorios' in client.get('/auth/login').data.decode()

    def test_el_registro_no_tiene_boton_de_google(self, client):
        assert '/auth/google' not in client.get('/auth/registro').data.decode()

    @pytest.mark.parametrize('contacto, esperado', [
        ('refugio@example.org', 'escríbenos a refugio@example.org'),
        ('', 'contacta con el refugio'),
    ])
    def test_cuenta_desactivada_usa_el_contacto_de_la_marca(self, app, client, usuario_adoptante, contacto, esperado):
        app.config['MARCA_CONTACTO'] = contacto
        usuario_adoptante.activo = False
        db.session.commit()

        html = client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'password123'}) \
            .data.decode()

        assert 'Tu cuenta está desactivada.' in html
        assert esperado in html
        assert 'administrador' not in html

    def test_cuenta_desactivada_con_google_usa_el_contacto(self, app, client, usuario_adoptante, monkeypatch):
        app.config['MARCA_CONTACTO'] = '981 000 000'
        usuario_adoptante.activo = False
        db.session.commit()
        monkeypatch.setattr(oauth.create_client('google'), 'authorize_access_token', lambda **k: {'userinfo': {
            'sub': 'g-x', 'email': 'adoptante@test.com', 'email_verified': True}})

        html = client.get('/auth/google/callback', follow_redirects=True).data.decode()

        assert 'escríbenos a 981 000 000' in html

    def test_mensajes_de_google_nuevos(self, client, monkeypatch):
        google = oauth.create_client('google')
        monkeypatch.setattr(google, 'authorize_access_token', lambda **k: {'userinfo': {
            'sub': 'g-y', 'email': 'x@gmail.com', 'email_verified': False}})
        html = client.get('/auth/google/callback', follow_redirects=True).data.decode()
        assert 'no tiene el correo verificado' in html

        monkeypatch.setattr(google, 'authorize_access_token', lambda **k: {'userinfo': {
            'sub': 'g-z', 'email': 'z@gmail.com', 'email_verified': True, 'given_name': 'Zoe'}})
        html = client.get('/auth/google/callback', follow_redirects=True).data.decode()
        assert '¡Hola, Zoe!' in html
        assert 'Bienvenido' not in html

    def test_bienvenida_sin_masculino_por_defecto(self, client, usuario_adoptante):
        html = client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'password123'},
                           follow_redirects=True).data.decode()
        assert '¡Hola, ' in html
        assert 'Bienvenido' not in html

    def test_next_se_mantiene_y_se_valida_en_el_registro(self, client):
        html = client.get('/auth/registro?next=/mascotas/1').data.decode()
        assert '<input type="hidden" name="next" value="/mascotas/1">' in html
        assert 'name="next"' not in client.get('/auth/registro?next=//evil.com').data.decode()
