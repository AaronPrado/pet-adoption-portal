"""
Macros de formulario (`app/templates/macros/formulario.html`, ADR-0002).

Renderiza cada macro con contextos de prueba y comprueba los atributos de
accesibilidad que generan: etiqueta, `aria-invalid`, `aria-describedby`,
`autocomplete`, obligatorios, ayuda visible, roles de los avisos y escape del
contenido. Así las macros y el contrato `valores`/`errores` no se separan.
"""

from html.parser import HTMLParser

import pytest
from flask import flash, render_template_string

from tests.test_accesibilidad import Analizador

IMPORTAR = '{% import "macros/formulario.html" as f %}'
VACIOS = {'input', 'br', 'hr', 'img', 'meta', 'link', 'source'}


class Elementos(HTMLParser):
    """Lista plana de elementos con sus atributos y su texto (incluido el de sus hijos)."""

    def __init__(self):
        super().__init__()
        self.todos = []
        self.abiertos = []

    def handle_starttag(self, tag, attrs):
        elemento = {'tag': tag, 'attrs': dict(attrs), 'texto': ''}
        self.todos.append(elemento)
        if tag not in VACIOS:
            self.abiertos.append(elemento)

    def handle_endtag(self, tag):
        for i in range(len(self.abiertos) - 1, -1, -1):
            if self.abiertos[i]['tag'] == tag:
                del self.abiertos[i:]
                break

    def handle_data(self, data):
        for elemento in self.abiertos:
            elemento['texto'] += data


def renderizar(llamada, **contexto):
    return render_template_string(IMPORTAR + llamada, **contexto)


def elementos(html):
    parser = Elementos()
    parser.feed(html)
    return parser.todos


def uno(html, tag, **filtros):
    encontrados = [e for e in elementos(html) if e['tag'] == tag
                   and all(e['attrs'].get(k) == v for k, v in filtros.items())]
    assert len(encontrados) == 1, (tag, filtros, html)
    return encontrados[0]


def sin_problemas_de_accesibilidad(html):
    analizador = Analizador()
    analizador.feed('<html lang="es">' + html + '</html>')
    return analizador.resultado() == []


@pytest.fixture
def ctx(app):
    with app.test_request_context():
        yield


# --- campo -----------------------------------------------------------------

def test_campo_basico_con_etiqueta_ayuda_y_autocomplete(ctx):
    html = renderizar("{{ f.campo('email', 'Email', tipo='email', autocomplete='email', "
                      "ayuda='Te escribiremos aquí.') }}")

    etiqueta = uno(html, 'label')
    campo = uno(html, 'input')
    ayuda = uno(html, 'p', id='email-ayuda')
    assert etiqueta['attrs']['for'] == campo['attrs']['id'] == 'email'
    assert etiqueta['texto'].strip() == 'Email'
    assert campo['attrs']['type'] == 'email'
    assert campo['attrs']['name'] == 'email'
    assert campo['attrs']['autocomplete'] == 'email'
    assert campo['attrs']['aria-describedby'] == 'email-ayuda'
    assert 'aria-invalid' not in campo['attrs']
    assert 'required' not in campo['attrs']
    assert ayuda['texto'] == 'Te escribiremos aquí.'
    assert sin_problemas_de_accesibilidad(html)


def test_campo_sin_ayuda_ni_error_no_lleva_describedby(ctx):
    campo = uno(renderizar("{{ f.campo('nombre', 'Nombre') }}"), 'input')
    assert campo['attrs']['type'] == 'text'
    assert 'aria-describedby' not in campo['attrs']
    assert 'autocomplete' not in campo['attrs']


def test_campo_con_error_marca_invalido_y_enlaza_error_y_ayuda(ctx):
    html = renderizar("{{ f.campo('email', 'Email', valores=valores, errores=errores, ayuda='Ayuda') }}",
                      valores={'email': 'ana@'}, errores={'email': 'El email no es válido.'})

    campo = uno(html, 'input')
    error = uno(html, 'p', id='email-error')
    assert campo['attrs']['aria-invalid'] == 'true'
    assert campo['attrs']['aria-describedby'] == 'email-error email-ayuda'
    assert campo['attrs']['value'] == 'ana@'
    assert error['texto'].strip().endswith('El email no es válido.')
    assert 'autofocus' not in campo['attrs']  # el foco va al resumen de errores


def test_campo_obligatorio_lleva_required_y_asterisco(ctx):
    html = renderizar("{{ f.campo('nombre', 'Nombre', obligatorio=true) }}")

    campo = uno(html, 'input')
    asterisco = uno(html, 'span', **{'class': 'campo__obligatorio'})
    assert 'required' in campo['attrs']
    assert asterisco['texto'] == '*'
    assert asterisco['attrs']['aria-hidden'] == 'true'  # required ya lo anuncia


def test_campo_con_id_propio_y_atributos_extra(ctx):
    html = renderizar("{{ f.campo('edad', 'Edad', tipo='number', id='edad_aprox', valores={'edad': 0}, "
                      "atributos={'min': 0, 'max': 30, 'inputmode': 'numeric'}) }}")

    campo = uno(html, 'input')
    assert uno(html, 'label')['attrs']['for'] == campo['attrs']['id'] == 'edad_aprox'
    assert campo['attrs']['name'] == 'edad'
    assert campo['attrs']['value'] == '0'  # el 0 no se pierde
    assert (campo['attrs']['min'], campo['attrs']['max']) == ('0', '30')
    assert campo['attrs']['inputmode'] == 'numeric'


@pytest.mark.parametrize('tipo', ['text', 'email', 'number', 'tel'])
def test_tipos_de_input(ctx, tipo):
    campo = uno(renderizar("{{ f.campo('x', 'X', tipo=tipo, valores={'x': '1'}) }}", tipo=tipo), 'input')
    assert campo['attrs']['type'] == tipo
    assert campo['attrs']['value'] == '1'


def test_password_nunca_se_vuelve_a_rellenar(ctx):
    html = renderizar("{{ f.campo('password', 'Contraseña', tipo='password', valores=valores, "
                      "errores={'password': 'Incorrecta'}, autocomplete='current-password') }}",
                      valores={'password': 'secreto-123'})

    campo = uno(html, 'input')
    assert campo['attrs']['type'] == 'password'
    assert 'value' not in campo['attrs']
    assert 'secreto-123' not in html
    assert campo['attrs']['autocomplete'] == 'current-password'


@pytest.mark.parametrize('tipo', ['PASSWORD', 'Password', ' password'])
def test_password_en_mayusculas_tampoco_se_rellena(ctx, tipo):
    campo = uno(renderizar("{{ f.campo('clave', 'Clave', tipo=tipo, valores={'clave': 'secreto'}) }}",
                           tipo=tipo), 'input')
    assert campo['attrs']['type'] == 'password'
    assert 'value' not in campo['attrs']


def test_password_ignora_value_en_atributos(ctx):
    html = renderizar("{{ f.campo('clave', 'Clave', tipo='password', atributos={'value': 'secreto', "
                      "'VALUE': 'otro', 'minlength': 8}) }}")
    campo = uno(html, 'input')
    assert 'secreto' not in html and 'otro' not in html
    assert campo['attrs']['minlength'] == '8'


@pytest.mark.parametrize('tipo', ['hidden', 'file', 'image', 'checkbox', 'nada'])
def test_tipo_fuera_de_la_lista_blanca_es_text(ctx, tipo):
    campo = uno(renderizar("{{ f.campo('x', 'X', tipo=tipo) }}", tipo=tipo), 'input')
    assert campo['attrs']['type'] == 'text'


def test_atributos_descartan_manejadores_on(ctx):
    html = renderizar("{{ f.campo('x', 'X', atributos=a) }}{{ f.boton('Ok', atributos=a) }}",
                      a={'onclick': 'alert(1)', 'OnFocus': 'alert(2)', 'data-x': '1', 'maxlength': 5})
    assert 'alert' not in html
    assert uno(html, 'input')['attrs']['data-x'] == uno(html, 'button')['attrs']['data-x'] == '1'
    assert uno(html, 'input')['attrs']['maxlength'] == '5'


def test_textarea_conserva_el_valor(ctx):
    html = renderizar("{{ f.campo('descripcion', 'Descripción', tipo='textarea', filas=5, valores=valores, "
                      "obligatorio=true) }}", valores={'descripcion': 'Perro tranquilo'})

    area = uno(html, 'textarea')
    assert area['attrs']['id'] == area['attrs']['name'] == 'descripcion'
    assert area['attrs']['rows'] == '5'
    assert 'required' in area['attrs']
    assert area['texto'] == 'Perro tranquilo'
    assert sin_problemas_de_accesibilidad(html)


def test_select_marca_la_opcion_enviada(ctx):
    html = renderizar("{{ f.campo('sexo', 'Sexo', tipo='select', opciones=opciones, valores={'sexo': 'Hembra'}, "
                      "errores={'sexo': 'Elige uno'}) }}",
                      opciones=[('Macho', 'Macho'), ('Hembra', 'Hembra')])

    select = uno(html, 'select')
    opciones = [e for e in elementos(html) if e['tag'] == 'option']
    assert select['attrs']['aria-invalid'] == 'true'
    assert [o['attrs']['value'] for o in opciones] == ['', 'Macho', 'Hembra']
    assert opciones[0]['texto'] == 'Elige una opción'
    assert [('selected' in o['attrs']) for o in opciones] == [False, False, True]
    assert sin_problemas_de_accesibilidad(html)


def test_select_sin_opcion_vacia_y_valores_numericos(ctx):
    html = renderizar("{{ f.campo('n', 'N', tipo='select', opciones=[(1, 'Uno'), (2, 'Dos')], "
                      "opcion_vacia=none, valores={'n': '2'}) }}")

    opciones = [e for e in elementos(html) if e['tag'] == 'option']
    assert [o['attrs']['value'] for o in opciones] == ['1', '2']
    assert 'selected' in opciones[1]['attrs']


def test_campo_escapa_todo_el_contenido(ctx):
    malicioso = '"><script>alert(1)</script>'
    html = renderizar("{{ f.campo('x', m, ayuda=m, valores={'x': m}, errores={'x': m}, "
                      "atributos={'placeholder': m}) }}"
                      "{{ f.campo('y', m, tipo='textarea', valores={'y': m}) }}"
                      "{{ f.campo('z', m, tipo='select', opciones=[(m, m)], valores={'z': m}) }}",
                      m=malicioso)

    assert '<script>' not in html
    assert '&lt;script&gt;' in html


def test_campo_sin_valores_ni_errores(ctx):
    """Las macros aceptan `valores` y `errores` vacíos o None (primera visita)."""
    html = renderizar("{{ f.campo('x', 'X', valores=none, errores=none) }}")
    assert 'value' not in uno(html, 'input')['attrs']


# --- leyenda_obligatorios --------------------------------------------------

def test_leyenda_obligatorios(ctx):
    html = renderizar('{{ f.leyenda_obligatorios() }}')
    leyenda = uno(html, 'p', **{'class': 'leyenda-obligatorios'})
    assert '*' in leyenda['texto'] and 'obligatorio' in leyenda['texto']


# --- grupo_opciones --------------------------------------------------------

def test_grupo_de_radios_con_fieldset_legend_y_error(ctx):
    html = renderizar("{{ f.grupo_opciones('jardin', '¿Tienes jardín?', opciones, valores={'jardin': 'no'}, "
                      "errores={'jardin': 'Esta pregunta es obligatoria.'}, obligatorio=true, ayuda='Ayuda') }}",
                      opciones=[('si', 'Sí'), ('no', 'No')])

    grupo = uno(html, 'fieldset')
    leyenda = uno(html, 'legend')
    radios = [e for e in elementos(html) if e['tag'] == 'input']
    assert grupo['attrs']['aria-describedby'] == 'jardin-error jardin-ayuda'
    assert '¿Tienes jardín?' in leyenda['texto']
    assert uno(html, 'p', id='jardin-error')['texto'].strip().endswith('Esta pregunta es obligatoria.')
    assert [r['attrs']['id'] for r in radios] == ['jardin_si', 'jardin_no']
    assert all(r['attrs']['type'] == 'radio' and r['attrs']['name'] == 'jardin' for r in radios)
    assert all('required' in r['attrs'] and r['attrs']['aria-invalid'] == 'true' for r in radios)
    assert [('checked' in r['attrs']) for r in radios] == [False, True]
    assert sin_problemas_de_accesibilidad(html)


def test_grupo_de_checkboxes_con_varias_marcadas(ctx):
    html = renderizar("{{ f.grupo_opciones('extras', 'Extras', opciones, tipo='checkbox', "
                      "valores={'extras': ['vacunado', 'chip']}, obligatorio=true) }}",
                      opciones=[('vacunado', 'Vacunado'), ('esterilizado', 'Esterilizado'), ('chip', 'Chip')])

    cajas = [e for e in elementos(html) if e['tag'] == 'input']
    grupo = uno(html, 'fieldset')
    assert all(c['attrs']['type'] == 'checkbox' for c in cajas)
    assert [('checked' in c['attrs']) for c in cajas] == [True, False, True]
    # HTML no sabe exigir «al menos una» casilla: el servidor lo valida
    assert not any('required' in c['attrs'] for c in cajas)
    assert 'aria-describedby' not in grupo['attrs']
    assert 'aria-invalid' not in cajas[0]['attrs']
    assert uno(html, 'span', **{'class': 'campo__obligatorio'})


def test_grupo_de_una_casilla_obligatoria(ctx):
    html = renderizar("{{ f.grupo_opciones('acepto', 'Condiciones', [('si', 'Acepto')], tipo='checkbox', "
                      "obligatorio=true, valores={'acepto': 'si'}) }}")
    casilla = uno(html, 'input')
    assert 'required' in casilla['attrs'] and 'checked' in casilla['attrs']


def test_grupo_con_id_enfocable_destino_del_resumen(ctx):
    grupo = uno(renderizar("{{ f.grupo_opciones('jardin', 'J', [('si', 'Sí')]) }}"), 'fieldset')
    assert (grupo['attrs']['id'], grupo['attrs']['tabindex']) == ('jardin', '-1')


def test_ids_de_opciones_sin_espacios(ctx):
    html = renderizar("{{ f.grupo_opciones('horas', 'Horas', [('menos de 4', 'Menos de 4'), "
                      "(' 8\\t+ ', 'Más de 8'), (3, 'Tres')]) }}")
    radios = [e for e in elementos(html) if e['tag'] == 'input']
    assert [r['attrs']['id'] for r in radios] == ['horas_menos-de-4', 'horas_8-+', 'horas_3']
    assert [r['attrs']['value'] for r in radios] == ['menos de 4', ' 8\t+ ', '3']  # el value no cambia
    assert sin_problemas_de_accesibilidad(html)


def test_grupo_escapa_el_contenido(ctx):
    m = '<b>x</b>'
    html = renderizar("{{ f.grupo_opciones('g', m, [(m, m)], ayuda=m, errores={'g': m}) }}", m=m)
    assert '<b>' not in html


# --- boton -----------------------------------------------------------------

@pytest.mark.parametrize('variante', ['primario', 'secundario', 'peligro'])
def test_boton_variantes(ctx, variante):
    boton = uno(renderizar("{{ f.boton('Guardar', variante=variante) }}", variante=variante), 'button')
    assert boton['attrs']['type'] == 'submit'
    assert boton['attrs']['class'] == f'boton boton--{variante}'
    assert boton['texto'].strip() == 'Guardar'


def test_boton_tipo_nombre_valor_y_atributos(ctx):
    boton = uno(renderizar("{{ f.boton('Rechazar', variante='peligro', tipo='button', nombre='accion', "
                           "valor='rechazar', atributos={'aria-controls': 'x'}) }}"), 'button')
    assert boton['attrs']['type'] == 'button'
    assert (boton['attrs']['name'], boton['attrs']['value']) == ('accion', 'rechazar')
    assert boton['attrs']['aria-controls'] == 'x'


def test_boton_variante_desconocida_usa_primario(ctx):
    boton = uno(renderizar("{{ f.boton('Ok', variante='rara', tipo='otro') }}"), 'button')
    assert boton['attrs']['class'] == 'boton boton--primario'
    assert boton['attrs']['type'] == 'submit'


def test_boton_escapa_el_texto(ctx):
    assert '<i>' not in renderizar("{{ f.boton('<i>x</i>') }}")


# --- resumen_errores -------------------------------------------------------

def test_resumen_de_errores_enlaza_cada_campo(ctx):
    html = renderizar("{{ f.resumen_errores(errores) }}",
                      errores={'email': 'El email no es válido.', 'jardin': 'Obligatoria.'})

    resumen = uno(html, 'div', id='resumen-errores')
    enlaces = [e for e in elementos(html) if e['tag'] == 'a']
    assert resumen['attrs']['tabindex'] == '-1'
    # Con role="group" el nombre (su título) se anuncia al recibir el foco
    assert resumen['attrs']['role'] == 'group'
    assert resumen['attrs']['aria-labelledby'] == 'resumen-errores-titulo'
    assert 'data-resumen-errores' in resumen['attrs']
    assert uno(html, 'h2', id='resumen-errores-titulo')['texto'].strip()
    assert [(a['attrs']['href'], a['texto']) for a in enlaces] == [
        ('#email', 'El email no es válido.'), ('#jardin', 'Obligatoria.')]


def test_cada_enlace_del_resumen_apunta_a_un_id_existente(ctx):
    """Campos, grupos y campos con un id distinto de su nombre (con `destinos`)."""
    errores = {'email': 'Mal', 'jardin': 'Obligatoria', 'edad': 'Demasiado'}
    html = renderizar("{{ f.resumen_errores(errores, destinos={'edad': 'edad_aprox'}) }}"
                      "{{ f.campo('email', 'Email', errores=errores) }}"
                      "{{ f.grupo_opciones('jardin', '¿Jardín?', [('si', 'Sí')], errores=errores) }}"
                      "{{ f.campo('edad', 'Edad', id='edad_aprox', errores=errores) }}",
                      errores=errores)

    ids = {e['attrs']['id'] for e in elementos(html) if 'id' in e['attrs']}
    destinos = [e['attrs']['href'][1:] for e in elementos(html) if e['tag'] == 'a']
    assert destinos == ['email', 'jardin', 'edad_aprox']
    assert set(destinos) <= ids


def test_resumen_con_destinos_none(ctx):
    html = renderizar("{{ f.resumen_errores({'x': 'Mal'}, destinos=none) }}")
    assert uno(html, 'a')['attrs']['href'] == '#x'


def test_resumen_de_errores_vacio_no_pinta_nada(ctx):
    assert renderizar('{{ f.resumen_errores({}) }}').strip() == ''
    assert renderizar('{{ f.resumen_errores(none) }}').strip() == ''


def test_resumen_de_errores_escapa(ctx):
    html = renderizar("{{ f.resumen_errores({'x': '<img src=x>'}, titulo='<b>t</b>') }}")
    assert '<img' not in html and '<b>' not in html


# --- avisos ----------------------------------------------------------------

@pytest.mark.parametrize('categoria, rol, clase', [
    ('success', 'status', 'aviso--exito'),
    ('info', 'status', 'aviso--info'),
    ('warning', 'alert', 'aviso--aviso'),
    ('danger', 'alert', 'aviso--error'),
    ('message', 'status', 'aviso--info'),
])
def test_avisos_usan_el_rol_de_su_categoria(app, categoria, rol, clase):
    with app.test_request_context():
        flash('Mensaje de prueba', categoria)
        html = renderizar('{{ f.avisos() }}')

    aviso = uno(html, 'div', role=rol)
    assert aviso['attrs']['class'] == f'aviso {clase}'
    assert aviso['texto'].strip() == 'Mensaje de prueba'


def test_avisos_con_varios_mensajes_y_escape(ctx):
    html = renderizar('{{ f.avisos(mensajes) }}',
                      mensajes=[('success', 'Hecho'), ('danger', '<script>x</script>')])
    roles = [e['attrs'].get('role') for e in elementos(html) if e['tag'] == 'div' and 'role' in e['attrs']]
    assert roles == ['status', 'alert']
    assert '<script>' not in html


def test_avisos_sin_mensajes_no_pinta_nada(ctx):
    assert renderizar('{{ f.avisos() }}').strip() == ''
