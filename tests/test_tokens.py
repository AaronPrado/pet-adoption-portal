"""
Tokens del sistema de diseño (ADR-0002): contraste WCAG de la paleta
y fuentes autoalojadas.

Lee las custom properties de `sistema.css` y `marca.css` (resolviendo los
`var()`), así que una protectora que cambie su color de acento en
`marca.css` sabe al pasar los tests si sigue cumpliendo el contraste.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / 'app' / 'static' / 'css'
FUENTES = RAIZ / 'app' / 'static' / 'fonts'
ARCHIVOS_CSS = ('sistema.css', 'marca.css')

# El lookbehind evita confundir un modificador BEM (`.boton--primario:hover`)
# con una custom property
PROPIEDAD = re.compile(r'(?<![\w-])(--[\w-]+)\s*:\s*([^;}]+)')
VAR = re.compile(r'^var\(\s*(--[\w-]+)\s*(?:,\s*(.+))?\)$')
HEX = re.compile(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def _leer(nombre):
    """Contenido de un CSS sin comentarios."""
    texto = (CSS / nombre).read_text(encoding='utf-8')
    return re.sub(r'/\*.*?\*/', '', texto, flags=re.S)


def _extraer(textos):
    """Custom properties de varios CSS (pares origen, texto), sin `!important`.

    Falla si una se define dos veces, por ejemplo otra vez dentro de un
    `@media`: el test solo vería la última y no comprobaría la otra.
    """
    props = {}
    for origen, css in textos:
        for clave, valor in PROPIEDAD.findall(css):
            assert clave not in props, f'{clave} se redefine en {origen}'
            props[clave] = re.sub(r'\s*!important\s*$', '', valor.strip())
    return props


def _propiedades():
    """Custom properties de sistema.css y marca.css."""
    return _extraer((nombre, _leer(nombre)) for nombre in ARCHIVOS_CSS)


def _reglas(css):
    """Pares (lista de selectores, cuerpo) de las reglas sin bloques anidados."""
    return [([sel.strip() for sel in selectores.split(',')], cuerpo)
            for selectores, cuerpo in re.findall(r'([^{};]+)\{([^{}]*)\}', css)]


def _resolver(props, nombre, visitados=()):
    """Valor final de una custom property, siguiendo los var()."""
    assert nombre not in visitados, f'Referencia circular en {nombre}'
    if nombre not in props:
        raise KeyError(nombre)
    valor = props[nombre]
    m = VAR.match(valor)
    if not m:
        return valor
    try:
        return _resolver(props, m.group(1), (*visitados, nombre))
    except KeyError:
        if m.group(2) is None:
            raise
        return m.group(2).strip()


def _luminancia(color):
    """Luminancia relativa de un color #rgb o #rrggbb (WCAG 2.2)."""
    m = HEX.match(color)
    assert m, f'Color no reconocido: {color!r} (usa #rgb o #rrggbb)'
    h = m.group(1)
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    canales = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        canales.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = canales
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    """Relación de contraste WCAG entre dos colores."""
    claro, oscuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


@pytest.fixture(scope='module')
def props():
    return _propiedades()


# --- Utilidades del propio test -------------------------------------------

def test_contraste_conocido():
    """La fórmula da los valores de referencia de WCAG."""
    assert contraste('#000', '#fff') == pytest.approx(21)
    assert contraste('#fff', '#fff') == pytest.approx(1)
    # A11Y-03: el borde de Bootstrap #dee2e6 sobre blanco da 1,30:1
    assert contraste('#dee2e6', '#ffffff') == pytest.approx(1.30, abs=0.01)


def test_resolver_sigue_var_y_valores_por_defecto():
    p = {'--a': 'var(--b)', '--b': '#123456', '--c': 'var(--nada, #fff)', '--d': 'var(--nada)'}
    assert _resolver(p, '--a') == '#123456'
    assert _resolver(p, '--c') == '#fff'
    with pytest.raises(KeyError):
        _resolver(p, '--d')


def test_extraer_quita_important():
    assert _extraer([('x.css', ':root { --a: #fff !important; }')]) == {'--a': '#fff'}


def test_extraer_ignora_modificadores_bem():
    css = ':root { --a: #fff; } .boton--a:hover { color: var(--a); }'
    assert _extraer([('x.css', css)]) == {'--a': '#fff'}


def test_extraer_detecta_redefiniciones():
    """Una custom property redefinida (aquí en un @media) hace fallar el test."""
    css = ':root { --a: #fff; } @media (min-width: 40em) { :root { --a: #000; } }'
    with pytest.raises(AssertionError, match='--a se redefine en x.css'):
        _extraer([('x.css', css)])


def test_reglas_separa_listas_de_selectores():
    assert _reglas('a, .b:hover { color: red; }') == [(['a', '.b:hover'], ' color: red; ')]


# --- Contraste (P-13, P-14, A11Y-03, A11Y-20) --------------------------------

TEXTO = ['--color-texto', '--color-texto-suave', '--color-placeholder']
FONDOS = ['--color-fondo', '--color-superficie']


@pytest.mark.parametrize('fondo', FONDOS)
@pytest.mark.parametrize('texto', TEXTO)
def test_texto_sobre_fondos(props, texto, fondo):
    """Texto normal: ≥ 4,5:1 (WCAG 1.4.3)."""
    ratio = contraste(_resolver(props, texto), _resolver(props, fondo))
    assert ratio >= 4.5, f'{texto} sobre {fondo}: {ratio:.2f}:1'


@pytest.mark.parametrize('fondo', [*FONDOS, '--color-acento-suave'])
@pytest.mark.parametrize('token', ['--color-borde-control', '--color-foco'])
def test_borde_y_foco_sobre_fondos(props, token, fondo):
    """Bordes de controles y anillo de foco: ≥ 3:1 (WCAG 1.4.11, P-13)."""
    ratio = contraste(_resolver(props, token), _resolver(props, fondo))
    assert ratio >= 3, f'{token} sobre {fondo}: {ratio:.2f}:1'


@pytest.mark.parametrize('fondo', FONDOS)
@pytest.mark.parametrize('token', ['--color-acento', '--color-acento-fuerte'])
def test_acento_como_texto(props, token, fondo):
    """El acento sirve como color de enlace o de texto: ≥ 4,5:1."""
    ratio = contraste(_resolver(props, token), _resolver(props, fondo))
    assert ratio >= 4.5, f'{token} sobre {fondo}: {ratio:.2f}:1'


@pytest.mark.parametrize('fondo', ['--color-acento', '--color-acento-fuerte'])
def test_texto_sobre_boton_de_acento(props, fondo):
    """Texto de un botón de acento, en reposo y en hover: ≥ 4,5:1 (A11Y-20)."""
    ratio = contraste(_resolver(props, '--color-sobre-acento'), _resolver(props, fondo))
    assert ratio >= 4.5, f'--color-sobre-acento sobre {fondo}: {ratio:.2f}:1'


@pytest.mark.parametrize('texto', ['--color-texto', '--color-texto-suave', '--color-acento', '--color-acento-fuerte'])
def test_texto_sobre_acento_suave(props, texto):
    """El fondo suave del acento (seleccionado, destacado) admite texto."""
    ratio = contraste(_resolver(props, texto), _resolver(props, '--color-acento-suave'))
    assert ratio >= 4.5, f'{texto} sobre --color-acento-suave: {ratio:.2f}:1'


ESTADOS = ['exito', 'aviso', 'error', 'info']


@pytest.mark.parametrize('estado', ESTADOS)
def test_colores_de_estado(props, estado):
    """Cada estado se lee como texto sobre el fondo, la superficie y su tono suave."""
    color = _resolver(props, f'--color-{estado}')
    for fondo in (*FONDOS, f'--color-{estado}-suave'):
        ratio = contraste(color, _resolver(props, fondo))
        assert ratio >= 4.5, f'--color-{estado} sobre {fondo}: {ratio:.2f}:1'
    for texto in ('--color-texto', '--color-texto-suave'):
        ratio = contraste(_resolver(props, texto), _resolver(props, f'--color-{estado}-suave'))
        assert ratio >= 4.5, f'{texto} sobre --color-{estado}-suave: {ratio:.2f}:1'


def test_tokens_no_dependen_de_bootstrap(props):
    """Los tokens no heredan del tema de Bootstrap (P-14, DIS-01)."""
    assert not any('--bs-' in v for v in props.values())


# --- Estructura del CSS ------------------------------------------------------

def test_orden_de_capas():
    """sistema.css declara las capas antes que cualquier regla."""
    css = _leer('sistema.css').lstrip()
    assert css.startswith('@layer reset, tokens, base, componentes, utilidades;')


def test_marca_solo_define_tokens():
    """marca.css solo trae tokens de marca y @font-face, en la capa tokens."""
    css = _leer('marca.css')
    sin_fuentes = re.sub(r'@font-face\s*\{[^}]*\}', '', css)
    assert re.fullmatch(r'\s*@layer tokens\s*\{\s*:root\s*\{[^{}]*\}\s*\}\s*', sin_fuentes)
    assert all(nombre.startswith('--marca-') for nombre, _ in PROPIEDAD.findall(sin_fuentes))


def test_enlaces_subrayados():
    """Los enlaces no se distinguen solo por el color (A11Y-06, WCAG 1.4.1)."""
    cuerpos = [cuerpo for selectores, cuerpo in _reglas(_leer('sistema.css')) if 'a' in selectores]
    assert cuerpos, 'No hay ninguna regla para el selector a'
    assert any(re.search(r'text-decoration(-line)?\s*:\s*underline', c) for c in cuerpos)


def _capa(css, nombre):
    """Contenido de una `@layer nombre { ... }`, con sus llaves anidadas."""
    inicio = css.index(f'@layer {nombre} {{') + len(f'@layer {nombre} {{')
    profundidad = 1
    for i in range(inicio, len(css)):
        profundidad += {'{': 1, '}': -1}.get(css[i], 0)
        if profundidad == 0:
            return css[inicio:i]
    raise ValueError(f'Capa {nombre} sin cerrar')


def _cuerpos(css, selector):
    """Cuerpos de las reglas cuya lista de selectores incluye `selector`."""
    return [cuerpo for selectores, cuerpo in _reglas(css) if selector in selectores]


def test_componentes_solo_usan_tokens_de_color():
    """La capa componentes no escribe colores a mano: todo sale de los tokens (ADR-0002)."""
    componentes = _capa(_leer('sistema.css'), 'componentes')
    assert componentes.strip(), 'La capa componentes está vacía'
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|\b(rgb|hsl|oklch)a?\(', componentes)
    assert not PROPIEDAD.search(componentes), 'Los tokens se definen en la capa tokens'


def test_foco_visible_en_controles_y_botones():
    """Anillo de foco con el token en enlaces, botones y campos (P-17)."""
    base = _capa(_leer('sistema.css'), 'base')
    for selector in ('a:focus-visible', 'button:focus-visible', 'input:focus-visible',
                     'select:focus-visible', 'textarea:focus-visible'):
        cuerpos = _cuerpos(base, selector)
        assert any('outline: var(--foco-anillo)' in c for c in cuerpos), selector
        assert any('outline-offset: var(--foco-separacion)' in c for c in cuerpos), selector


@pytest.mark.parametrize('selector', ['.campo__control', '.boton', '.opcion', '.opcion__etiqueta'])
def test_objetivos_tactiles_minimos(selector):
    """Controles y botones de al menos --objetivo-min (WCAG 2.5.8)."""
    cuerpos = _cuerpos(_capa(_leer('sistema.css'), 'componentes'), selector)
    assert any('min-height: var(--objetivo-min)' in c for c in cuerpos), selector


@pytest.mark.parametrize('selector', [
    '.boton--primario:hover', '.boton--secundario:hover', '.boton--peligro:hover', '.boton:active',
    '.boton:disabled', '.boton[aria-disabled="true"]', 'form[aria-busy="true"]',
    '.campo__control:disabled', '.campo__control[aria-invalid="true"]',
])
def test_estados_de_interaccion(selector):
    """Hover, pulsado, deshabilitado, enviando e inválido tienen estilo propio (P-20)."""
    assert _cuerpos(_capa(_leer('sistema.css'), 'componentes'), selector), selector


@pytest.mark.parametrize('clase', ['.visualmente-oculto', '.visually-hidden'])
def test_utilidad_visualmente_oculto(clase):
    """La región «Enviando…» de app.js usa .visually-hidden: tiene que existir sin Bootstrap."""
    cuerpos = _cuerpos(_capa(_leer('sistema.css'), 'utilidades'), clase)
    assert any('clip-path: inset(50%)' in c for c in cuerpos), clase


def test_capa_sin_cerrar():
    with pytest.raises(ValueError):
        _capa('@layer x { a { b: c; }', 'x')


# --- Fuentes autoalojadas ----------------------------------------------------

def _font_faces():
    bloques = []
    for nombre in ARCHIVOS_CSS:
        bloques += re.findall(r'@font-face\s*\{([^}]*)\}', _leer(nombre))
    return bloques


def test_font_face_esperados():
    """Exactamente Atkinson Hyperlegible 400 y 700, y Fraunces variable."""
    familias = []
    for bloque in _font_faces():
        familia = re.search(r'font-family\s*:\s*["\']?([^;"\']+)', bloque).group(1).strip()
        peso = re.search(r'font-weight\s*:\s*([^;]+)', bloque).group(1).strip()
        familias.append((familia, peso))
    assert sorted(familias) == [('Atkinson Hyperlegible', '400'), ('Atkinson Hyperlegible', '700'),
                                ('Fraunces', '100 900')]
    # Ni fuentes sin usar ni de más: cada WOFF2 pesa en la primera visita
    assert len(list(FUENTES.glob('*.woff2'))) == 3


def test_font_face_con_swap_y_archivos_presentes():
    """Cada @font-face usa swap y apunta a un WOFF2 de app/static/fonts."""
    bloques = _font_faces()
    assert bloques
    for bloque in bloques:
        assert re.search(r'font-display\s*:\s*swap', bloque)
        urls = re.findall(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)', bloque)
        assert urls
        for url in urls:
            assert url.startswith('../fonts/') and url.endswith('.woff2'), url
            ruta = FUENTES / url.removeprefix('../fonts/')
            assert ruta.is_file(), f'Falta {ruta}'
            assert ruta.read_bytes()[:4] == b'wOF2', f'{ruta} no es WOFF2'


def test_fuentes_con_licencia_y_readme():
    """Las fuentes van con su licencia OFL y un README con el origen."""
    for licencia in ('LICENSE-atkinson-hyperlegible.txt', 'LICENSE-fraunces.txt'):
        assert 'SIL Open Font License' in (FUENTES / licencia).read_text(encoding='utf-8')
    readme = (FUENTES / 'README.md').read_text(encoding='utf-8')
    assert '5.3.0' in readme and 'OFL' in readme

