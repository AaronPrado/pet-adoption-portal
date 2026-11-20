"""
Macro `paginacion_sistema` (`macros/paginacion.html`), la paginación de la base
nueva: accesibilidad de la página actual y de los extremos, y conservación de
los filtros. La macro `paginacion` (Bootstrap) la cubren los tests del panel.
"""

import re
from pathlib import Path

from flask import render_template_string

from app import db
from app.models import Mascota

LLAMADA = ('{% from "macros/paginacion.html" import paginacion_sistema %}'
           "{{ paginacion_sistema(pagina, 'mascotas.catalogo') }}")
CSS = Path(__file__).parent.parent / 'app/static/css/sistema.css'


def renderizar(app, pagina, query=''):
    with app.test_request_context('/mascotas/catalogo' + query):
        return render_template_string(LLAMADA, pagina=pagina)


def paginar(pagina, por_pagina=2):
    return db.paginate(db.select(Mascota).order_by(Mascota.id), page=pagina, per_page=por_pagina, error_out=False)


def crear(n):
    db.session.add_all([Mascota(nombre=f'Mascota {i:02d}', especie='Gato', descripcion='Descripción larga')
                        for i in range(n)])
    db.session.commit()


def test_una_sola_pagina_no_pinta_nada(app):
    crear(2)
    assert renderizar(app, paginar(1)).strip() == ''


def test_pagina_actual_con_texto_oculto_en_el_elemento_con_aria_current(app):
    crear(10)
    html = renderizar(app, paginar(2))

    actual = re.search(r'<span class="[^"]*" aria-current="page">(.*?)</span></span>', html, flags=re.S)
    assert actual
    assert 'aria-label' not in actual.group(0)
    assert re.sub(r'<[^>]+>', '', actual.group(0)) == 'Página 2, actual'
    assert html.count('aria-current') == 1 and not re.search(r'<li[^>]*aria-current', html)


def test_enlaces_con_nombre_y_extremos_sin_atributos_inertes(app):
    crear(10)
    html = renderizar(app, paginar(1))

    assert 'aria-label="Página 2"' in html and 'rel="next"' in html and 'rel="prev"' not in html
    assert '<span class="paginacion__enlace paginacion__enlace--inactivo">Anterior</span>' in html
    assert 'aria-disabled' not in html


def test_puntos_suspensivos_ocultos_a_lectores(app):
    crear(40)
    html = renderizar(app, paginar(10, por_pagina=2))

    assert '<span class="paginacion__puntos" aria-hidden="true">…</span>' in html


def test_conserva_filtros(app):
    crear(10)
    html = renderizar(app, paginar(1), '?especie=Gato&_external=1')

    assert 'href="/mascotas/catalogo?especie=Gato&amp;page=2"' in html
    assert '_external' not in html


def test_estilos_en_sistema_css_con_senal_que_no_es_solo_color():
    css = re.sub(r'/\*.*?\*/', '', CSS.read_text(encoding='utf-8'), flags=re.S)
    regla = re.search(r'\.paginacion__enlace--actual[^{]*\{([^}]*)\}', css).group(1)

    assert 'border: 2px' in regla and 'box-shadow' in regla
