"""
Tests estáticos de las plantillas: nada que obligue a relajar la CSP
(estilos en línea) ni recursos servidos por terceros (ADR-0001).
"""

import base64
import hashlib
import re
from pathlib import Path

import pytest

RAIZ_APP = Path(__file__).resolve().parent.parent / 'app'

BASE_HTML = RAIZ_APP / 'templates' / 'base.html'
BASE_BOOTSTRAP = RAIZ_APP / 'templates' / 'base_bootstrap.html'
# Bases que se comprueban: sin terceros ni crossorigin
BASES = [BASE_HTML, BASE_BOOTSTRAP]
FICHEROS_BOOTSTRAP = ['bootstrap.min.css', 'bootstrap.bundle.min.js']


def _texto_base():
    """La base con Bootstrap vendorizado, la única que lo carga (ADR-0001)."""
    return BASE_BOOTSTRAP.read_text(encoding='utf-8')


def _etiquetas_recurso(texto):
    return re.findall(r'<(?:link|script)\b[^>]*>', texto)


def _ruta_vendor(texto, fichero):
    """Ruta dentro de static/ (vendor/bootstrap/<versión>/<fichero>) que
    base_bootstrap.html pasa a url_for, o None si no lo carga desde ahí."""
    patron = rf"filename='(vendor/bootstrap/[^/']+/{re.escape(fichero)})'"
    coincidencia = re.search(patron, texto)
    return coincidencia.group(1) if coincidencia else None


@pytest.mark.parametrize('base', BASES, ids=lambda ruta: ruta.name)
def test_base_no_referencia_cdn(base):
    """Las bases cargan CSS y JS solo desde /static (sin URL absolutas)."""
    texto = base.read_text(encoding='utf-8')
    externos = [
        e for e in _etiquetas_recurso(texto)
        if re.search(r'(?:href|src)\s*=\s*["\'](?:https?:)?//', e)
    ]
    assert not externos, f'{base.name} carga recursos de terceros: {externos}'
    assert 'jsdelivr' not in texto


@pytest.mark.parametrize('base', BASES, ids=lambda ruta: ruta.name)
def test_base_sin_crossorigin(base):
    """En el mismo origen crossorigin sobra para SRI."""
    assert 'crossorigin' not in base.read_text(encoding='utf-8')


@pytest.mark.parametrize('fichero', FICHEROS_BOOTSTRAP)
def test_bootstrap_vendorizado_coincide_con_su_sri(fichero):
    """El hash SRI de base_bootstrap.html coincide con el fichero al que apunta."""
    etiqueta = next((e for e in _etiquetas_recurso(_texto_base()) if fichero in e), None)
    assert etiqueta, f'base_bootstrap.html no carga {fichero}'
    ruta = _ruta_vendor(etiqueta, fichero)
    assert ruta, f'{fichero} no se sirve desde static/vendor/bootstrap/<versión>/'
    contenido = (RAIZ_APP / 'static' / ruta).read_bytes()
    sri = 'sha384-' + base64.b64encode(hashlib.sha384(contenido).digest()).decode()
    assert f'integrity="{sri}"' in etiqueta


def test_bootstrap_vendorizado_con_licencia():
    ruta = _ruta_vendor(_texto_base(), 'bootstrap.min.css')
    assert ruta, 'base_bootstrap.html no carga bootstrap.min.css desde static/vendor/'
    licencia = (RAIZ_APP / 'static' / ruta).parent / 'LICENSE'
    assert 'MIT' in licencia.read_text(encoding='utf-8')


# Comentarios HTML y de Jinja: su contenido no llega al navegador.
COMENTARIOS = re.compile(r'<!--.*?-->|\{#.*?#\}', re.DOTALL)
# Atributo style (también en la columna 0) o elemento <style>.
ESTILO_EN_LINEA = re.compile(r'(?:^|\s)style\s*=|<style[\s>]', re.IGNORECASE | re.MULTILINE)
PLANTILLAS = sorted((RAIZ_APP / 'templates').rglob('*.html'))


def _rel(ruta):
    return ruta.relative_to(RAIZ_APP).as_posix()


def _estilos_en_linea(texto):
    """Fragmentos con estilos en línea, sin contar los comentarios."""
    return [m.group(0).strip() for m in ESTILO_EN_LINEA.finditer(COMENTARIOS.sub('', texto))]


def test_hay_plantillas():
    assert PLANTILLAS, 'No se han encontrado plantillas'


@pytest.mark.parametrize('texto, esperado', [
    ('<img src="x" style="width: 1px">', True),
    ('style="color: red"', True),
    ('<div\nstyle="x">', True),
    ('<style>\n.a {}\n</style>', True),
    ('<!-- <p style="x"> -->', False),
    ('{# <style> #}', False),
    ('<div data-style="x" class="estilo">', False),
])
def test_deteccion_de_estilos_en_linea(texto, esperado):
    assert bool(_estilos_en_linea(texto)) is esperado


@pytest.mark.parametrize('plantilla', PLANTILLAS, ids=_rel)
def test_plantilla_sin_estilos_en_linea(plantilla):
    """La CSP no permite 'unsafe-inline' en style-src: los estilos van en
    app/static/css/styles.css."""
    encontrados = _estilos_en_linea(plantilla.read_text(encoding='utf-8'))
    assert not encontrados, f'{_rel(plantilla)} tiene estilos en línea: {encontrados}'
