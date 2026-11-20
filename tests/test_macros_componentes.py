"""
Macros de componentes (`app/templates/macros/componentes.html`, ADR-0002).

Renderiza cada macro con contextos de prueba y comprueba sus atributos de
accesibilidad, el escape del contenido y los casos límite: sin foto, nombre
con caracteres especiales, tabla vacía y estado desconocido.
"""

import re
from types import SimpleNamespace

import pytest
from flask import render_template_string

from app.models import ETIQUETAS_ESTADO, Mascota, Solicitud, etiqueta_estado
from tests.test_macros_formulario import elementos, sin_problemas_de_accesibilidad, uno
from tests.test_tokens import _capa, _cuerpos, _leer, _reglas

IMPORTAR = '{% import "macros/componentes.html" as c %}'
FOTO = '/fotos/' + 'b' * 32 + '-1200.webp'


def renderizar(llamada, **contexto):
    return render_template_string(IMPORTAR + llamada, **contexto)


def texto_sin_indicador(elemento):
    """Título visible de una cabecera de tabla, sin el indicador ni la acción oculta."""
    return elemento['texto'].split(',')[0].strip().rstrip('▲▼⇅').strip()


def enlaces_de_orden(html):
    return {texto_sin_indicador(e): e['attrs']['href'] for e in elementos(html) if e['tag'] == 'a'}


def con_clase(html, tag, clase):
    return [e for e in elementos(html) if e['tag'] == tag and clase in e['attrs'].get('class', '').split()]


def mascota(**datos):
    base = {'id': 7, 'nombre': 'Cerbero', 'especie': 'Perro', 'raza': 'Mestizo', 'edad_aprox': 3,
            'tamano': 'Mediano', 'estado': 'disponible', 'foto_url': FOTO}
    return SimpleNamespace(**(base | datos))


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
    ('adoptado', 'mascota', 'Adoptada', 'info'),
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


# --- tarjeta_mascota ------------------------------------------------------------

def test_tarjeta_mascota_completa(ctx):
    html = renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota())

    articulo = uno(html, 'article')
    titulo = uno(html, 'h2')
    assert articulo['attrs']['aria-labelledby'] == titulo['attrs']['id'] == 'mascota-7-nombre'
    assert titulo['texto'].strip() == 'Cerbero'

    img = uno(html, 'img')
    assert img['attrs']['src'] == FOTO
    assert img['attrs']['alt'] == 'Foto de Cerbero, perro'
    assert (img['attrs']['width'], img['attrs']['height']) == ('800', '600')
    assert img['attrs']['loading'] == 'lazy'
    assert img['attrs']['decoding'] == 'async'
    assert img['attrs']['srcset'].endswith('-1200.webp 1200w')
    assert img['attrs']['sizes']

    enlace = uno(html, 'a')
    assert enlace['attrs']['href'] == '/mascotas/7'
    assert enlace['texto'].strip() == 'Ver a Cerbero'  # nombre único entre tarjetas
    assert 'boton' in enlace['attrs']['class'].split()

    datos = [e['texto'].strip() for e in elementos(html) if e['tag'] == 'li']
    assert datos == ['Perro', 'Mestizo', '3 años', 'Mediano']
    assert con_clase(html, 'span', 'chapa--exito')
    assert sin_problemas_de_accesibilidad(html)


def test_tarjeta_mascota_primera_fila_sin_carga_diferida(ctx):
    img = uno(renderizar('{{ c.tarjeta_mascota(m, diferida=false) }}', m=mascota()), 'img')
    assert 'loading' not in img['attrs']
    assert img['attrs']['fetchpriority'] == 'high'


def test_tarjeta_mascota_con_nivel_de_titulo(ctx):
    html = renderizar('{{ c.tarjeta_mascota(m, nivel=3) }}', m=mascota())
    assert uno(html, 'h3')
    assert not [e for e in elementos(html) if e['tag'] == 'h2']


@pytest.mark.parametrize('nivel', [1, 9, 'x'])
def test_tarjeta_mascota_nivel_fuera_de_rango_usa_h2(ctx, nivel):
    assert uno(renderizar('{{ c.tarjeta_mascota(m, nivel=nivel) }}', m=mascota(), nivel=nivel), 'h2')


def test_tarjeta_mascota_externa_sin_srcset(ctx):
    img = uno(renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota(foto_url='https://ejemplo.com/a.jpg')), 'img')
    assert 'srcset' not in img['attrs']
    assert 'sizes' not in img['attrs']


@pytest.mark.parametrize('foto', [None, ''])
def test_tarjeta_mascota_sin_foto_usa_placeholder_propio(ctx, foto):
    html = renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota(foto_url=foto))

    assert not [e for e in elementos(html) if e['tag'] == 'img']  # nada de imágenes de terceros
    vacia = con_clase(html, 'div', 'tarjeta-mascota__foto--vacia')[0]
    assert vacia['attrs']['role'] == 'img'
    assert vacia['attrs']['aria-label'] == 'Cerbero todavía no tiene foto'
    assert uno(html, 'svg')['attrs']['aria-hidden'] == 'true'
    assert sin_problemas_de_accesibilidad(html)


def test_tarjeta_mascota_escapa_el_nombre(ctx):
    html = renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota(nombre='Rex & "Lulú" <script>'))

    assert '<script>' not in html
    assert uno(html, 'a')['texto'].strip() == 'Ver a Rex & "Lulú" <script>'
    assert uno(html, 'img')['attrs']['alt'] == 'Foto de Rex & "Lulú" <script>, perro'


@pytest.mark.parametrize('edad, texto', [(0, 'Menos de 1 año'), (1, '1 año'), (12, '12 años')])
def test_tarjeta_mascota_edad(ctx, edad, texto):
    html = renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota(edad_aprox=edad))
    assert texto in [e['texto'].strip() for e in elementos(html) if e['tag'] == 'li']


def test_tarjeta_mascota_sin_datos_opcionales(ctx):
    html = renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota(raza=None, edad_aprox=None, tamano=''))
    assert [e['texto'].strip() for e in elementos(html) if e['tag'] == 'li'] == ['Perro']


def test_tarjeta_mascota_adoptada(ctx):
    html = renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota(estado='adoptado'))
    assert con_clase(html, 'span', 'chapa--info')[0]['texto'].strip() == 'Adoptada'


def test_tarjeta_mascota_nota(ctx):
    html = renderizar('{{ c.tarjeta_mascota(m, nota=n) }}', m=mascota(), n='Aún <puedes>')

    nota = uno(html, 'p')
    assert nota['attrs']['class'] == 'tarjeta-mascota__nota'
    assert nota['texto'] == 'Aún <puedes>' and '<puedes>' not in html


def test_tarjeta_mascota_sin_nota(ctx):
    assert 'tarjeta-mascota__nota' not in renderizar('{{ c.tarjeta_mascota(m) }}', m=mascota())


def test_tarjetas_con_ids_distintos(ctx):
    html = renderizar('{% for m in ms %}{{ c.tarjeta_mascota(m) }}{% endfor %}',
                      ms=[mascota(id=1), mascota(id=2, nombre='Luna')])
    ids = [e['attrs']['id'] for e in elementos(html) if e['tag'] == 'h2']
    assert ids == ['mascota-1-nombre', 'mascota-2-nombre']


# --- enlace_boton (P-15) --------------------------------------------------------

@pytest.mark.parametrize('variante, clase', [
    ('primario', 'boton--primario'), ('secundario', 'boton--secundario'),
    ('peligro', 'boton--peligro'), ('inventada', 'boton--primario'),
])
def test_enlace_boton_reutiliza_las_clases_de_boton(ctx, variante, clase):
    html = renderizar("{{ c.enlace_boton('Nueva mascota', '/mascotas/admin/nueva', variante) }}",
                      variante=variante)
    enlace = uno(html, 'a')
    assert enlace['attrs']['class'] == f'boton {clase}'
    assert enlace['attrs']['href'] == '/mascotas/admin/nueva'
    assert enlace['texto'] == 'Nueva mascota'


def test_enlace_boton_escapa_texto_y_url(ctx):
    html = renderizar("{{ c.enlace_boton(t, u) }}", t='<i>x</i>', u='/a?b="c"')
    assert '<i>' not in html
    assert uno(html, 'a')['attrs']['href'] == '/a?b="c"'


# --- cabecera_pagina ------------------------------------------------------------

def test_cabecera_pagina_minima(ctx):
    html = renderizar("{{ c.cabecera_pagina('Catálogo') }}")

    assert uno(html, 'header')['attrs']['class'] == 'cabecera-pagina'
    assert uno(html, 'h1')['texto'] == 'Catálogo'
    assert not [e for e in elementos(html) if e['tag'] in ('p', 'a')]
    assert not con_clase(html, 'div', 'cabecera-pagina__acciones')


def test_cabecera_pagina_con_entradilla_volver_y_acciones(ctx):
    html = renderizar("{% call c.cabecera_pagina('Mascotas', 'Gestiona el refugio.', volver_url='/') %}"
                      "{{ c.enlace_boton('Nueva mascota', '/nueva') }}{% endcall %}")

    assert uno(html, 'p', **{'class': 'cabecera-pagina__entradilla'})['texto'] == 'Gestiona el refugio.'
    volver = uno(html, 'a', **{'class': 'cabecera-pagina__volver'})
    assert volver['attrs']['href'] == '/'
    assert volver['texto'].strip() == 'Volver'
    acciones = uno(html, 'div', **{'class': 'cabecera-pagina__acciones'})
    assert 'Nueva mascota' in acciones['texto']
    # El enlace de volver va antes del h1 (miga) y las acciones después
    orden = [e['attrs'].get('class', e['tag']) for e in elementos(html) if e['tag'] in ('h1', 'div', 'a')]
    assert orden == ['cabecera-pagina__volver', 'cabecera-pagina__texto', 'h1', 'cabecera-pagina__acciones',
                     'boton boton--primario']
    assert sin_problemas_de_accesibilidad(html)


def test_cabecera_pagina_escapa(ctx):
    html = renderizar("{{ c.cabecera_pagina(t, t) }}", t='<b>x</b>')
    assert '<b>' not in html


# --- tabla ----------------------------------------------------------------------

COLUMNAS = [
    {'clave': 'id', 'titulo': 'ID', 'ordenable': True, 'numerica': True},
    {'clave': 'nombre', 'titulo': 'Nombre', 'ordenable': True},
    {'titulo': 'Estado'},
    {'titulo': 'Acciones', 'oculto': True},
]
FILA = ("{% call c.tabla('mascotas', 'Mascotas del refugio', columnas, orden=orden, "
        "endpoint='mascotas.admin_lista') %}"
        "<tr><th scope=\"row\">Cerbero</th><td>1</td></tr>{% endcall %}")


def test_tabla_region_caption_y_scope(ctx):
    html = renderizar(FILA, columnas=COLUMNAS, orden=None)

    region = uno(html, 'div', role='region')
    caption = uno(html, 'caption')
    assert region['attrs']['aria-labelledby'] == caption['attrs']['id'] == 'mascotas-titulo'
    assert region['attrs']['tabindex'] == '0'  # desplazable con teclado en el móvil (P-23)
    assert 'tabla' in region['attrs']['class'].split()
    assert caption['texto'] == 'Mascotas del refugio'

    cabeceras = [e for e in elementos(html) if e['tag'] == 'th' and e['attrs'].get('scope') == 'col']
    assert [texto_sin_indicador(e) for e in cabeceras] == ['ID', 'Nombre', 'Estado', 'Acciones']
    assert not any('aria-sort' in e['attrs'] for e in cabeceras)
    assert 'tabla__columna--numerica' in cabeceras[0]['attrs']['class']
    assert 'Acciones' in [e['texto'] for e in con_clase(html, 'span', 'visualmente-oculto')]
    assert uno(html, 'th', scope='row')['texto'] == 'Cerbero'
    assert sin_problemas_de_accesibilidad(html)


def test_tabla_columna_ordenada_con_aria_sort_y_enlaces(ctx):
    html = renderizar(FILA, columnas=COLUMNAS, orden=('nombre', 'asc'))

    ordenadas = [e for e in elementos(html) if e['tag'] == 'th' and 'aria-sort' in e['attrs']]
    assert len(ordenadas) == 1
    assert ordenadas[0]['attrs']['aria-sort'] == 'ascending'
    assert 'Nombre' in ordenadas[0]['texto']

    enlaces = enlaces_de_orden(html)
    # Conserva los filtros, vuelve a la página 1 e invierte la columna activa
    assert enlaces['Nombre'] == '/mascotas/admin?estado=disponible&orden=nombre&dir=desc'
    assert enlaces['ID'] == '/mascotas/admin?estado=disponible&orden=id&dir=asc'
    assert 'Estado' not in enlaces
    indicadores = [e for e in elementos(html) if e['tag'] == 'span' and 'tabla__orden' in e['attrs'].get('class', '')]
    assert indicadores and all(e['attrs']['aria-hidden'] == 'true' for e in indicadores)


def test_tabla_orden_descendente(ctx):
    html = renderizar(FILA, columnas=COLUMNAS, orden=('id', 'desc'))
    th = uno(html, 'th', **{'aria-sort': 'descending'})
    assert 'ID' in th['texto']
    enlaces = enlaces_de_orden(html)
    assert enlaces['ID'].endswith('orden=id&dir=asc')


def test_tabla_sin_endpoint_no_enlaza_pero_marca_el_orden(ctx):
    html = renderizar("{% call c.tabla('t', 'T', columnas, orden=('id', 'asc')) %}<tr><td>1</td></tr>{% endcall %}",
                      columnas=COLUMNAS)
    assert not [e for e in elementos(html) if e['tag'] == 'a']
    assert uno(html, 'th', **{'aria-sort': 'ascending'})


@pytest.mark.parametrize('llamada', [
    "{{ c.tabla('t', 'T', columnas) }}",
    "{% call c.tabla('t', 'T', columnas) %}   {% endcall %}",
])
def test_tabla_vacia_muestra_mensaje(ctx, llamada):
    html = renderizar(llamada, columnas=COLUMNAS)
    celda = uno(html, 'td')
    assert celda['attrs']['colspan'] == '4'
    assert celda['texto'].strip() == 'No hay resultados.'


def test_tabla_vacia_con_mensaje_propio_y_caption_oculto(ctx):
    html = renderizar("{{ c.tabla('t', 'T', columnas, vacia='Sin mascotas', caption_oculto=true) }}",
                      columnas=COLUMNAS)
    assert uno(html, 'td')['texto'].strip() == 'Sin mascotas'
    assert uno(html, 'caption')['attrs']['class'] == 'visualmente-oculto'


def test_tabla_escapa(ctx):
    html = renderizar("{{ c.tabla('t', t, [{'titulo': t}], vacia=t) }}", t='<b>x</b>')
    assert '<b>' not in html


# --- estado_vacio ---------------------------------------------------------------

def test_estado_vacio_con_accion(ctx):
    html = renderizar("{{ c.estado_vacio('No hay mascotas', 'Prueba con otros filtros.', "
                      "'/mascotas/catalogo', 'Ver todas') }}")

    assert uno(html, 'div', **{'class': 'estado-vacio'})
    assert uno(html, 'h2')['texto'] == 'No hay mascotas'
    assert uno(html, 'p')['texto'] == 'Prueba con otros filtros.'
    enlace = uno(html, 'a')
    assert enlace['attrs']['href'] == '/mascotas/catalogo'
    assert enlace['attrs']['class'] == 'boton boton--secundario'
    assert sin_problemas_de_accesibilidad(html)


def test_estado_vacio_minimo_y_nivel(ctx):
    html = renderizar("{{ c.estado_vacio('Nada', nivel=3) }}")
    assert uno(html, 'h3')['texto'] == 'Nada'
    assert not [e for e in elementos(html) if e['tag'] in ('p', 'a')]


def test_estado_vacio_escapa(ctx):
    html = renderizar("{{ c.estado_vacio(t, t, '/x', t) }}", t='<b>x</b>')
    assert '<b>' not in html


# --- CSS de los componentes -----------------------------------------------------

@pytest.fixture(scope='module')
def componentes():
    return _capa(_leer('sistema.css'), 'componentes')


def test_rejilla_llena_el_contenedor(componentes):
    """Columnas flexibles con un mínimo de token: sin huecos ni sangrías (DIS-11, QA-13)."""
    cuerpo, = _cuerpos(componentes, '.rejilla-tarjetas')
    assert 'minmax(min(var(--ancho-tarjeta-min), 100%), 1fr)' in cuerpo


def test_foto_de_tarjeta_por_proporcion_sin_altura_fija(componentes):
    """La foto toma su alto de la proporción, no de un alto fijo (DIS-07)."""
    cuerpo, = _cuerpos(componentes, '.tarjeta-mascota__foto')
    assert 'aspect-ratio: 4 / 3' in cuerpo
    assert 'object-fit: cover' in cuerpo
    tarjeta = [c for selectores, c in _reglas(componentes) if any('tarjeta' in s or 'img' in s for s in selectores)]
    assert not any(re.search(r'(?<![-\w])height\s*:', c) for c in tarjeta), 'La tarjeta no fija altos'


@pytest.mark.parametrize('tono', ['exito', 'aviso', 'error', 'info', 'neutro'])
def test_cada_tono_de_chapa_tiene_estilo(componentes, tono):
    assert _cuerpos(componentes, f'.chapa--{tono}')


def test_tabla_desplazable(componentes):
    cuerpo, = _cuerpos(componentes, '.tabla')
    assert 'overflow-x: auto' in cuerpo


# --- Nombre accesible de los enlaces de orden -----------------------------------

def nombre_accesible(html, elemento_a):
    """Texto del enlace sin lo que va en aria-hidden."""
    ocultos = [e['texto'] for e in elementos(html) if e['attrs'].get('aria-hidden') == 'true'
               and e['texto'] and e['texto'] in elemento_a['texto']]
    texto = elemento_a['texto']
    for oculto in ocultos:
        texto = texto.replace(oculto, '', 1)
    return ' '.join(texto.split())


def test_enlaces_de_orden_anuncian_la_accion(ctx):
    """Cada cabecera ordenable dice qué hará el clic, también las inactivas."""
    html = renderizar(FILA, columnas=COLUMNAS, orden=('nombre', 'asc'))
    nombres = sorted(nombre_accesible(html, e) for e in elementos(html) if e['tag'] == 'a')
    assert nombres == ['ID, ordenar ascendente', 'Nombre, ordenar descendente']


# --- URLs inseguras en las macros -----------------------------------------------

PELIGROSAS = ['javascript:alert(1)', ' JaVaScRiPt:alert(1)', '//evil.com', 'data:text/html,x']


@pytest.mark.parametrize('url', PELIGROSAS)
def test_enlace_boton_no_pinta_urls_inseguras(ctx, url):
    assert renderizar("{{ c.enlace_boton('Ir', url) }}", url=url).strip() == ''


@pytest.mark.parametrize('url', PELIGROSAS)
def test_cabecera_pagina_no_pinta_volver_inseguro(ctx, url):
    html = renderizar("{{ c.cabecera_pagina('T', volver_url=url) }}", url=url)
    assert not [e for e in elementos(html) if e['tag'] == 'a']
    assert uno(html, 'h1')


@pytest.mark.parametrize('url', PELIGROSAS)
def test_estado_vacio_no_pinta_accion_insegura(ctx, url):
    html = renderizar("{{ c.estado_vacio('Nada', 'Texto', url, 'Ir') }}", url=url)
    assert not [e for e in elementos(html) if e['tag'] == 'a']
    assert uno(html, 'p')['texto'] == 'Texto'


def test_enlace_boton_admite_mailto_y_https(ctx):
    html = renderizar("{{ c.enlace_boton('Escríbenos', 'mailto:a@b.es') }}")
    assert uno(html, 'a')['attrs']['href'] == 'mailto:a@b.es'
    assert uno(renderizar("{{ c.enlace_boton('Web', 'https://a.es') }}"), 'a')['attrs']['href'] == 'https://a.es'


# --- CSS: contraste del icono, texto seleccionable y foco de la tarjeta ---------

def test_icono_de_orden_sin_opacidad(componentes):
    """Con opacidad el icono bajaba a ~2,2:1; hereda el color de la cabecera (≥ 3:1)."""
    reglas = [c for selectores, c in _reglas(componentes) if any('tabla__orden' in s for s in selectores)]
    assert reglas
    assert not any('opacity' in c for c in reglas)


def test_texto_de_la_tarjeta_por_encima_del_enlace_extendido(componentes):
    """El nombre y los datos quedan sobre el ::after del enlace: se pueden seleccionar."""
    for selector in ('.tarjeta-mascota__nombre', '.tarjeta-mascota__datos'):
        cuerpos = _cuerpos(componentes, selector)
        assert any('position: relative' in c and 'z-index: 1' in c for c in cuerpos), selector


def test_foco_de_tarjeta_completa(componentes):
    cuerpos = _cuerpos(componentes, '.tarjeta-mascota:has(:focus-visible)')
    assert any('outline: var(--foco-anillo)' in c for c in cuerpos)
