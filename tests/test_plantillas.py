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
FICHEROS_BOOTSTRAP = ['bootstrap.min.css', 'bootstrap.bundle.min.js']


def _texto_base():
    return BASE_HTML.read_text(encoding='utf-8')


def _etiquetas_recurso(texto):
    return re.findall(r'<(?:link|script)\b[^>]*>', texto)


def _ruta_vendor(texto, fichero):
    """Ruta dentro de static/ (vendor/bootstrap/<versión>/<fichero>) que
    base.html pasa a url_for, o None si no lo carga desde ahí."""
    patron = rf"filename='(vendor/bootstrap/[^/']+/{re.escape(fichero)})'"
    coincidencia = re.search(patron, texto)
    return coincidencia.group(1) if coincidencia else None


def test_base_no_referencia_cdn():
    """base.html carga CSS y JS solo desde /static (sin URL absolutas)."""
    texto = _texto_base()
    externos = [
        e for e in _etiquetas_recurso(texto)
        if re.search(r'(?:href|src)\s*=\s*["\'](?:https?:)?//', e)
    ]
    assert not externos, f'base.html carga recursos de terceros: {externos}'
    assert 'jsdelivr' not in texto


def test_base_sin_crossorigin():
    """En el mismo origen crossorigin sobra para SRI."""
    assert 'crossorigin' not in _texto_base()


@pytest.mark.parametrize('fichero', FICHEROS_BOOTSTRAP)
def test_bootstrap_vendorizado_coincide_con_su_sri(fichero):
    """El hash SRI de base.html coincide con el fichero al que apunta."""
    etiqueta = next((e for e in _etiquetas_recurso(_texto_base()) if fichero in e), None)
    assert etiqueta, f'base.html no carga {fichero}'
    ruta = _ruta_vendor(etiqueta, fichero)
    assert ruta, f'{fichero} no se sirve desde static/vendor/bootstrap/<versión>/'
    contenido = (RAIZ_APP / 'static' / ruta).read_bytes()
    sri = 'sha384-' + base64.b64encode(hashlib.sha384(contenido).digest()).decode()
    assert f'integrity="{sri}"' in etiqueta


def test_bootstrap_vendorizado_con_licencia():
    ruta = _ruta_vendor(_texto_base(), 'bootstrap.min.css')
    assert ruta, 'base.html no carga bootstrap.min.css desde static/vendor/'
    licencia = (RAIZ_APP / 'static' / ruta).parent / 'LICENSE'
    assert 'MIT' in licencia.read_text(encoding='utf-8')
