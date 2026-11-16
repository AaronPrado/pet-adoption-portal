"""
Comprobaciones automáticas de accesibilidad (WCAG 2.2 AA) sobre el HTML
renderizado: textos alternativos, nombres accesibles, etiquetas de
formulario y estructura básica. No sustituyen a una revisión manual con
lector de pantalla y teclado.
"""

from html.parser import HTMLParser

import pytest

from app import db
from app.models import Solicitud


class Analizador(HTMLParser):
    """Recoge los problemas de accesibilidad detectables en el HTML."""

    VACIOS = {'img', 'input', 'br', 'hr', 'meta', 'link', 'path', 'source'}

    def __init__(self):
        super().__init__()
        self.problemas = []
        self.lang = None
        self.ids_con_label = set()
        self.campos = []
        self.pila = []  # elementos interactivos abiertos: [tag, attrs, texto]

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html':
            self.lang = a.get('lang')
        if tag == 'img' and 'alt' not in a:
            self.problemas.append(f'img sin alt: {a.get("src")}')
        if tag == 'svg' and a.get('aria-hidden') != 'true' and 'aria-label' not in a:
            self.problemas.append('svg sin aria-hidden ni aria-label')
        if tag == 'label' and 'for' in a:
            self.ids_con_label.add(a['for'])
        if tag in ('input', 'select', 'textarea') and a.get('type') not in ('hidden', 'submit', 'button'):
            self.campos.append(a)
        for elemento in self.pila:
            if tag == 'img' and a.get('alt'):
                elemento[2] += a['alt']
        if tag in ('a', 'button') and tag not in self.VACIOS:
            self.pila.append([tag, a, ''])

    def handle_data(self, data):
        for elemento in self.pila:
            elemento[2] += data

    def handle_endtag(self, tag):
        if tag in ('a', 'button') and self.pila and self.pila[-1][0] == tag:
            _, a, texto = self.pila.pop()
            if not (texto.strip() or a.get('aria-label') or a.get('aria-labelledby')):
                self.problemas.append(f'<{tag}> sin nombre accesible: {a}')

    def resultado(self):
        if self.lang != 'es':
            self.problemas.append('html sin lang="es"')
        for campo in self.campos:
            if campo.get('id') not in self.ids_con_label and not campo.get('aria-label'):
                self.problemas.append(f'campo sin etiqueta: {campo.get("name")}')
        return self.problemas


def problemas(client, url, codigo=200):
    response = client.get(url)
    assert response.status_code == codigo, url
    analizador = Analizador()
    analizador.feed(response.data.decode())
    return analizador.resultado()


PUBLICAS = ['/', '/mascotas/catalogo', '/auth/login', '/auth/registro']


@pytest.mark.parametrize('url', PUBLICAS)
def test_paginas_publicas(client, mascota_disponible, url):
    assert problemas(client, url) == []


def test_detalle_mascota(client, mascota_disponible):
    assert problemas(client, f'/mascotas/{mascota_disponible.id}') == []


def test_paginas_de_adoptante(client, auth_headers_adoptante, solicitud_pendiente, mascota_adoptada):
    for url in ['/solicitudes/mis-solicitudes', f'/solicitudes/detalle/{solicitud_pendiente.id}']:
        assert problemas(client, url) == [], url


def test_formulario_de_solicitud(client, auth_headers_adoptante, mascota_disponible):
    assert problemas(client, f'/solicitudes/nueva/{mascota_disponible.id}') == []


def test_paneles_admin(client, auth_headers_admin, solicitud_pendiente):
    urls = ['/mascotas/admin', '/mascotas/admin/nueva',
            f'/mascotas/admin/editar/{solicitud_pendiente.mascota_id}',
            '/solicitudes/admin', f'/solicitudes/admin/revisar/{solicitud_pendiente.id}']
    for url in urls:
        assert problemas(client, url) == [], url


def test_botones_de_icono_nombran_el_elemento(client, auth_headers_admin, solicitud_pendiente):
    html = client.get('/mascotas/admin').data.decode()
    nombre = db.session.get(Solicitud, solicitud_pendiente.id).mascota.nombre

    assert f'aria-label="Eliminar {nombre}"' in html
    assert f'aria-label="Editar {nombre}"' in html


def test_enlace_para_saltar_al_contenido(client):
    html = client.get('/').data.decode()
    assert 'href="#contenido"' in html and 'id="contenido"' in html


@pytest.mark.parametrize('url, codigo', [('/no-existe', 404), ('/mascotas/99999', 404), ('/auth/logout', 405)])
def test_paginas_de_error(client, url, codigo):
    assert problemas(client, url, codigo) == []


def test_pagina_de_error_con_sesion_iniciada(client, auth_headers_adoptante):
    assert problemas(client, '/no-existe', 404) == []


def test_pagina_de_sesion_caducada(app, client):
    app.config['WTF_CSRF_ENABLED'] = True
    response = client.post('/auth/login', data={}, headers={'Referer': 'http://localhost/auth/login'})
    assert response.status_code == 400
    analizador = Analizador()
    analizador.feed(response.data.decode())
    assert analizador.resultado() == []
