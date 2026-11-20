"""
Tests de la base nueva sin Bootstrap (`base.html`, B3.6): marca,
navegación, avisos y pie. El contexto de la marca está en test_contexto.py.

Las páginas de error son las primeras que la extienden; el resto sigue en
`base_bootstrap.html` hasta su migración (fases 4 y 5).
"""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flask import flash, render_template
from flask_login import login_user

from app import contexto, db

RAIZ_APP = Path(__file__).resolve().parent.parent / 'app'
PLANTILLAS = RAIZ_APP / 'templates'
# utcnow() devuelve UTC sin zona
EN_2031 = datetime(2031, 5, 1, tzinfo=UTC).replace(tzinfo=None)
SISTEMA_CSS = (RAIZ_APP / 'static' / 'css' / 'sistema.css').read_text(encoding='utf-8')


def pagina(app, ruta='/no-existe', **contexto_extra):
    """Renderiza la página de error (que extiende base.html) como si se pidiera `ruta`."""
    with app.test_request_context(ruta):
        return render_template('errores/error.html', titulo='Título', mensaje='Mensaje',
                               salidas=[('Ir al inicio', '/')], **contexto_extra)


def etiqueta(html, patron):
    """Primera etiqueta de apertura que contiene `patron`."""
    coincidencia = re.search(rf'<[^>]*{patron}[^>]*>', html)
    assert coincidencia, patron
    return coincidencia.group(0)


def enlace_nav(html, texto):
    """Etiqueta <a ...> del enlace de la navegación con ese texto."""
    coincidencia = re.search(rf'(<a [^>]*>)\s*{re.escape(texto)}\s*</a>', html)
    assert coincidencia, texto
    return coincidencia.group(1)


class TestPlantillas:

    def test_cada_pagina_extiende_una_de_las_dos_bases(self):
        """Mientras dure la migración, una página usa base.html o base_bootstrap.html; la migrada no lleva Bootstrap."""
        bases = {}
        for ruta in PLANTILLAS.rglob('*.html'):
            coincidencia = re.match(r'{% extends "([^"]+)" %}', ruta.read_text(encoding='utf-8'))
            if coincidencia:
                bases[ruta.relative_to(PLANTILLAS).as_posix()] = coincidencia.group(1)

        assert set(bases.values()) <= {'base.html', 'base_bootstrap.html'}
        assert bases['errores/error.html'] == 'base.html'
        clases_bootstrap = re.compile(r'class="[^"]*\b(btn(-\w+)?|card(-\w+)?|col(-\w+)+|row|badge|alert|container|'
                                      r'form-(control|select|label)|page-(link|item)|mb-\d|mt-\d|d-flex)\b')
        for plantilla, base in bases.items():
            if base == 'base.html':
                texto = (PLANTILLAS / plantilla).read_text(encoding='utf-8')
                assert not clases_bootstrap.search(texto), f'{plantilla} usa clases de Bootstrap'

    def test_la_base_nueva_no_carga_bootstrap(self):
        texto = re.sub(r'{#.*?#}', '', (PLANTILLAS / 'base.html').read_text(encoding='utf-8'), flags=re.S)
        assert 'bootstrap' not in texto.lower()
        assert 'data-bs-' not in texto


class TestCabecera:

    def test_hojas_del_sistema_en_orden_y_sin_bootstrap(self, app):
        html = pagina(app)
        hojas = re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)

        # sistema.css declara el orden de las capas; marca.css redefine sus tokens
        assert hojas == ['/static/css/sistema.css', '/static/css/marca.css']
        assert 'bootstrap' not in html
        assert '<script src="/static/js/app.js"></script>' in html

    def test_con_js_antes_del_primer_pintado(self, app):
        """con-js.js va en <head>, sin defer ni async: marca <html> antes de
        pintar y el menú no aparece abierto un instante."""
        html = pagina(app)
        cabeza = html[:html.index('</head>')]

        assert '<script src="/static/js/con-js.js"></script>' in cabeza
        texto = (RAIZ_APP / 'static' / 'js' / 'con-js.js').read_text(encoding='utf-8')
        assert "document.documentElement.classList.add('con-js')" in texto

    def test_salto_al_contenido(self, app):
        html = pagina(app)

        salto = etiqueta(html, 'href="#contenido"')
        assert 'visualmente-oculto-enfocable' in salto
        assert '<main id="contenido"' in html and 'tabindex="-1"' in re.search(r'<main[^>]*>', html).group(0)
        # Es lo primero que se enfoca
        assert html.index('href="#contenido"') < html.index('<header')

    def test_logo_svg_propio_con_el_nombre_de_la_marca(self, app):
        html = pagina(app)
        marca = re.search(r'<a class="marca"[^>]*>(.*?)</a>', html, re.S).group(1)

        assert '🐾' not in html
        assert '<svg' in marca and 'aria-hidden="true"' in marca and 'currentColor' in marca
        assert 'Portal de Adopción' in marca

    def test_logo_configurado(self, app):
        app.config.update(MARCA_NOMBRE='Protectora Ejemplo', MARCA_LOGO='img/logo.svg')
        html = pagina(app)
        marca = re.search(r'<a class="marca"[^>]*>(.*?)</a>', html, re.S).group(1)

        assert '<img class="marca__logo" src="/static/img/logo.svg" alt=""' in marca
        assert '<svg' not in marca
        assert 'Protectora Ejemplo' in marca

    def test_logo_con_url_no_admitida_usa_el_isotipo(self, app):
        app.config['MARCA_LOGO'] = 'javascript:alert(1)'
        html = pagina(app)

        assert 'javascript:' not in html
        assert '<svg class="marca__logo"' in html

    def test_titulo_con_la_marca(self, app):
        app.config['MARCA_NOMBRE'] = 'Protectora <Ejemplo>'
        html = pagina(app)

        assert '<title>Título - Protectora &lt;Ejemplo&gt;</title>' in html


class TestNavegacion:

    def test_disclosure_del_menu_movil(self, app):
        html = pagina(app)
        boton = etiqueta(html, 'aria-controls="navegacion"')

        assert boton.startswith('<button type="button"')
        assert 'data-desplegable' in boton
        # Cerrado de entrada: sin JS no se pliega nada (las reglas dependen de
        # .con-js) y el botón no se ve
        assert 'aria-expanded="false"' in boton
        assert '<nav id="navegacion" class="navegacion" aria-label="Principal">' in html

    def test_anonimo(self, app):
        html = pagina(app)

        for texto, href in [('Inicio', '/'), ('Mascotas', '/mascotas/catalogo'),
                            ('Iniciar Sesión', '/auth/login'), ('Registrarse', '/auth/registro')]:
            assert f'href="{href}"' in enlace_nav(html, texto)
        assert 'Cerrar Sesión' not in html

    @pytest.mark.parametrize('ruta, texto', [
        ('/', 'Inicio'), ('/mascotas/catalogo', 'Mascotas'), ('/auth/login', 'Iniciar Sesión'),
        ('/auth/registro', 'Registrarse'),
    ])
    def test_enlace_activo(self, app, ruta, texto):
        html = pagina(app, ruta)

        assert 'aria-current="page"' in enlace_nav(html, texto)
        assert html.count('aria-current="page"') == 1

    def test_sin_endpoint_no_hay_enlace_activo(self, app):
        assert 'aria-current' not in pagina(app, '/no-existe')

    def test_adoptante(self, client, auth_headers_adoptante):
        html = client.get('/no-existe').data.decode()

        boton = etiqueta(html, 'aria-controls="menu-usuario"')
        assert boton.startswith('<button type="button"') and 'aria-expanded="false"' in boton
        assert 'id="menu-usuario"' in html
        assert 'href="/solicitudes/mis-solicitudes"' in enlace_nav(html, 'Mis Solicitudes')
        assert 'Panel Admin' not in html
        assert 'Iniciar Sesión' not in html

    def test_admin(self, client, auth_headers_admin):
        html = client.get('/no-existe').data.decode()

        assert 'href="/mascotas/admin"' in enlace_nav(html, 'Panel Admin Mascotas')
        assert 'href="/solicitudes/admin"' in enlace_nav(html, 'Panel Admin Solicitudes')
        assert 'Mis Solicitudes' not in html

    def test_admin_enlace_activo(self, app, usuario_admin):
        with app.test_request_context('/mascotas/admin'):
            login_user(usuario_admin)
            html = render_template('errores/error.html', titulo='T', mensaje='M', salidas=[])

        assert 'aria-current="page"' in enlace_nav(html, 'Panel Admin Mascotas')

    def test_cerrar_sesion_por_post_con_csrf(self, app, client, auth_headers_adoptante):
        app.config['WTF_CSRF_ENABLED'] = True
        html = client.get('/no-existe').data.decode()

        formulario = re.search(r'<form method="POST" action="/auth/logout">(.*?)</form>', html, re.S).group(1)
        assert re.search(r'<input type="hidden" name="csrf_token" value="[^"]+">', formulario)
        assert '<button type="submit" class="menu-usuario__opcion">Cerrar Sesión</button>' in formulario

    def test_nombre_del_usuario_escapado(self, client, auth_headers_adoptante, usuario_adoptante):
        usuario_adoptante.nombre = '<b>Ana</b>'
        db.session.commit()

        html = client.get('/no-existe').data.decode()

        assert '&lt;b&gt;Ana&lt;/b&gt;' in html and '<b>Ana</b>' not in html


class TestUsuarioDeLaNavegacion:
    """La base no puede fallar en un 500 aunque falle la base de datos."""

    def test_un_500_sin_base_de_datos_pinta_la_base_completa(self, app, client, usuario_adoptante, monkeypatch):
        """Si cargar el usuario falla, la página de error sale con la navegación
        de anónimo en lugar de la página mínima."""
        app.config['PROPAGATE_EXCEPTIONS'] = False

        @app.route('/_prueba/sin-bd')
        def sin_bd():
            raise RuntimeError('fallo')

        client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'password123'})

        class UsuarioRoto:
            @property
            def is_authenticated(self):
                raise RuntimeError('sin base de datos')

        monkeypatch.setattr(contexto, 'current_user', UsuarioRoto())
        response = client.get('/_prueba/sin-bd')
        html = response.data.decode()

        assert response.status_code == 500
        assert 'aria-label="Principal"' in html
        assert 'Iniciar Sesión' in html
        assert 'Ver mis solicitudes' not in html


class TestAvisosYPie:

    def test_avisos_flash_dentro_de_main(self, app):
        with app.test_request_context('/no-existe'):
            flash('Guardado', 'success')
            html = render_template('errores/error.html', titulo='T', mensaje='M', salidas=[])

        main = html[html.index('<main'):html.index('</main>')]
        assert '<div class="aviso aviso--exito" role="status">' in main

    def test_pie_sin_contacto(self, app, monkeypatch):
        monkeypatch.setattr(contexto, 'utcnow', lambda: EN_2031)
        html = pagina(app)
        pie = re.search(r'<footer class="pie-sitio">(.*?)</footer>', html, re.S).group(1)

        assert '<p>&copy; 2031 Portal de Adopción</p>' in pie
        assert 'Contacto' not in pie
        assert '<p class="pie-sitio__credito">Desarrollado por Aarón Prado</p>' in pie

    def test_pie_sin_credito(self, app):
        app.config['MARCA_CREDITO'] = ''
        html = pagina(app)
        pie = re.search(r'<footer class="pie-sitio">(.*?)</footer>', html, re.S).group(1)

        assert 'pie-sitio__credito' not in pie
        assert 'Desarrollado' not in pie

    def test_credito_escapado(self, app):
        app.config['MARCA_CREDITO'] = 'Hecho por <i>Lur</i>'
        html = pagina(app)

        assert 'Hecho por &lt;i&gt;Lur&lt;/i&gt;' in html

    def test_pie_con_email(self, app):
        app.config['MARCA_CONTACTO'] = 'hola@protectora.example'
        html = pagina(app)

        assert '<a href="mailto:hola@protectora.example">hola@protectora.example</a>' in html

    def test_pie_con_telefono(self, app):
        app.config['MARCA_CONTACTO'] = '600 000 000'
        html = pagina(app)
        pie = re.search(r'<footer class="pie-sitio">(.*?)</footer>', html, re.S).group(1)

        assert 'Contacto: 600 000 000' in pie
        assert 'mailto' not in pie


class TestCSS:

    def test_estilos_de_la_base_en_la_capa_de_componentes(self):
        componentes = SISTEMA_CSS[SISTEMA_CSS.index('@layer componentes'):SISTEMA_CSS.index('@layer utilidades')]
        for clase in ('.pagina', '.salto-contenido', '.cabecera-sitio', '.marca', '.navegacion',
                      '.menu-usuario', '.pie-sitio', '.contenedor'):
            assert f'{clase} ' in componentes or f'{clase},' in componentes, clase

    def test_solo_se_pliega_con_js(self):
        """Sin JS la navegación tiene que verse: toda regla que oculta un
        panel de navegación depende de la clase .con-js de <html>."""
        sin_comentarios = re.sub(r'/\*.*?\*/', '', SISTEMA_CSS, flags=re.S)
        reglas = re.findall(r'([^{}]+)\{[^{}]*display:\s*none', sin_comentarios)
        plegados = [r.strip() for r in reglas if 'aria-expanded="false"' in r]
        assert plegados
        assert all(selector.startswith('.con-js') for regla in plegados for selector in regla.split(','))

    def test_pie_al_fondo(self):
        assert re.search(r'\.pagina \{[^}]*display: flex;[^}]*flex-direction: column;', SISTEMA_CSS)
        assert re.search(r'\.contenido \{[^}]*flex: 1 0 auto;', SISTEMA_CSS)
