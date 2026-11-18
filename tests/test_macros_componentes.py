"""
Macros de componentes (`app/templates/macros/componentes.html`, ADR-0002).

Renderiza cada macro con contextos de prueba y comprueba sus atributos de
accesibilidad, el escape del contenido y los casos límite: sin foto, nombre
con caracteres especiales, tabla vacía y estado desconocido.
"""

import pytest
from flask import render_template_string

from app.models import ETIQUETAS_ESTADO, Mascota, Solicitud, etiqueta_estado
from tests.test_macros_formulario import elementos, uno

IMPORTAR = '{% import "macros/componentes.html" as c %}'


def renderizar(llamada, **contexto):
    return render_template_string(IMPORTAR + llamada, **contexto)


def con_clase(html, tag, clase):
    return [e for e in elementos(html) if e['tag'] == tag and clase in e['attrs'].get('class', '').split()]


@pytest.fixture
def ctx(app):
    with app.test_request_context('/mascotas/admin?estado=disponible&page=3'):
        yield


# --- Etiquetas de estado (una sola fuente en app/models.py) ------------------

def test_etiquetas_cubren_los_estados_de_la_base_de_datos():
    """Cada valor que admite el CHECK de la tabla tiene su etiqueta, y nada más."""
    for modelo, tipo in ((Mascota, 'mascota'), (Solicitud, 'solicitud')):
        check = next(c for c in modelo.__table__.constraints if str(c.name).endswith('_estado_check'))
        valores = {v.strip(" '") for v in str(check.sqltext).split('(')[1].rstrip(')').split(',')}
        assert set(ETIQUETAS_ESTADO[tipo]) == valores


def test_etiqueta_estado():
    assert etiqueta_estado('en_proceso') == 'En proceso'
    assert etiqueta_estado('aprobada', 'solicitud') == 'Aprobada'
    assert etiqueta_estado('perdido') == 'perdido'
    assert etiqueta_estado(None) == 'Sin estado'
    assert etiqueta_estado('pendiente', 'otro') == 'pendiente'


# --- badge_estado ---------------------------------------------------------------

@pytest.mark.parametrize('estado, tipo, texto, tono', [
    ('disponible', 'mascota', 'Disponible', 'exito'),
    ('en_proceso', 'mascota', 'En proceso', 'aviso'),
    ('adoptado', 'mascota', 'Adoptado', 'info'),
    ('pendiente', 'solicitud', 'Pendiente', 'aviso'),
    ('aprobada', 'solicitud', 'Aprobada', 'exito'),
    ('rechazada', 'solicitud', 'Rechazada', 'error'),
])
def test_badge_estado_con_texto_y_tono(ctx, estado, tipo, texto, tono):
    html = renderizar('{{ c.badge_estado(estado, tipo) }}', estado=estado, tipo=tipo)

    chapa = uno(html, 'span', **{'class': f'chapa chapa--{tono}'})
    assert chapa['texto'].strip() == texto  # el estado se lee, no solo se ve
    punto = uno(html, 'span', **{'class': 'chapa__punto'})
    assert punto['attrs']['aria-hidden'] == 'true'


def test_badge_estado_desconocido_se_escapa_y_va_en_neutro(ctx):
    html = renderizar('{{ c.badge_estado(estado) }}', estado='<b>raro</b>')

    assert '<b>' not in html
    assert '&lt;b&gt;raro&lt;/b&gt;' in html
    assert con_clase(html, 'span', 'chapa--neutro')


def test_badge_estado_sin_estado(ctx):
    assert 'Sin estado' in renderizar('{{ c.badge_estado(none) }}')
