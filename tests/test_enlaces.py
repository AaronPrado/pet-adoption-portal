"""
Helpers de URL de las plantillas (`app/enlaces.py`): enlaces de orden de la
macro `tabla` y validación de los `href` que llegan a las macros.
"""

import pytest
from flask import render_template_string

from app.enlaces import url_orden, url_segura


def orden(app, query, clave='nombre', direccion='asc'):
    with app.test_request_context('/mascotas/admin?' + query):
        return url_orden('mascotas.admin_lista', clave, direccion)


# --- url_orden ------------------------------------------------------------------

def test_url_orden_conserva_filtros_y_vuelve_a_la_primera_pagina(app):
    url = orden(app, 'estado=disponible&page=3&orden=id&dir=desc')
    assert url == '/mascotas/admin?estado=disponible&orden=nombre&dir=asc'


def test_url_orden_conserva_valores_repetidos(app):
    assert orden(app, 'especie=Perro&especie=Gato') == '/mascotas/admin?especie=Perro&especie=Gato&orden=nombre&dir=asc'


@pytest.mark.parametrize('query', ['_external=1', '_scheme=http', '_anchor=x', '_method=POST', '_otro=1'])
def test_url_orden_descarta_claves_con_guion_bajo(app, query):
    """Los argumentos de url_for no se pueden inyectar desde la URL."""
    assert orden(app, query + '&estado=disponible') == '/mascotas/admin?estado=disponible&orden=nombre&dir=asc'


def test_url_orden_descarta_endpoint(app):
    """`endpoint` chocaba con el primer argumento de url_for (TypeError → 500)."""
    assert orden(app, 'endpoint=1', 'id', 'desc') == '/mascotas/admin?orden=id&dir=desc'


def test_url_orden_direccion_invalida_es_ascendente(app):
    assert orden(app, '', direccion='<x>').endswith('dir=asc')


def test_peticion_real_con_endpoint_en_la_query(app, client):
    """Una página con la tabla y `?endpoint=1` responde 200, no 500."""
    def pagina():
        return render_template_string(
            '{% import "macros/componentes.html" as c %}'
            "{{ c.tabla('t', 'T', [{'clave': 'id', 'titulo': 'ID', 'ordenable': true}], "
            "endpoint='mascotas.admin_lista') }}")
    app.add_url_rule('/prueba-tabla', 'prueba_tabla', pagina)

    respuesta = client.get('/prueba-tabla?endpoint=1&_external=1&estado=a&estado=b')

    assert respuesta.status_code == 200
    html = respuesta.get_data(as_text=True)
    assert 'href="/mascotas/admin?estado=a&amp;estado=b&amp;orden=id&amp;dir=asc"' in html


# --- url_segura -----------------------------------------------------------------

@pytest.mark.parametrize('url', [
    '/mascotas/catalogo', '/', '/a?b=c#d', 'https://ejemplo.com/x', 'http://ejemplo.com',
    'HTTPS://EJEMPLO.COM', 'mailto:hola@ejemplo.com', '  /con-espacios  ',
])
def test_url_segura_admite(url):
    assert url_segura(url) == url.strip()


@pytest.mark.parametrize('url', [
    'javascript:alert(1)', 'JavaScript:alert(1)', '  javascript:alert(1)', 'java\tscript:alert(1)',
    'java\nscript:alert(1)', 'data:text/html,x', 'vbscript:x', '//evil.com', '/\\evil.com',
    ' //evil.com', 'relativa/sin/barra', '#', '', None, 'ftp://ejemplo.com',
])
def test_url_segura_rechaza(url):
    assert url_segura(url) == ''


def test_url_segura_registrado_como_filtro(app):
    plantilla = app.jinja_env.from_string('[{{ u|url_segura }}]')
    assert plantilla.render(u='javascript:x') == '[]'
    assert plantilla.render(u='/a') == '[/a]'
