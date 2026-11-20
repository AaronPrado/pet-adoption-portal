"""
URLs de las macros de plantilla (`macros/componentes.html`).

- `url_orden`: enlace de una cabecera ordenable de `tabla`, construido en
  Python para que la query string no pueda manipular `url_for`.
- `url_pagina`: enlace de la paginación de la base nueva, construido igual.
- `url_segura`: filtro que solo deja pasar los `href` admitidos; las macros
  no pintan el enlace si devuelve ''.
"""

import re

from flask import request, url_for

# Parámetros que fija url_orden. Sin `page`, la lista vuelve a la página 1
PARAMETROS_DE_ORDEN = ('orden', 'dir', 'page')

# Argumentos con nombre de url_for que no empiezan por `_`
ARGUMENTOS_URL_FOR = ('endpoint',)

ESQUEMAS_SEGUROS = ('http:', 'https:', 'mailto:')

# El navegador ignora los espacios y controles de los extremos y quita
# tabuladores y saltos de línea en cualquier posición (`java\tscript:`)
_IGNORADOS = re.compile(r'[\x00-\x20\x7f]')


def url_orden(endpoint, clave, direccion):
    """
    URL de `endpoint` ordenada por `clave` en `direccion` ('asc' o 'desc').

    Conserva los filtros de la petición, también los repetidos, y descarta
    los que empiezan por `_` (`_external`, `_scheme`, `_anchor`...) y los que
    chocan con los argumentos de url_for.
    """
    args = {clave_arg: valores for clave_arg, valores in request.args.lists()
            if not clave_arg.startswith('_')
            and clave_arg not in ARGUMENTOS_URL_FOR
            and clave_arg not in PARAMETROS_DE_ORDEN}
    return url_for(endpoint, **args, orden=clave, dir='desc' if direccion == 'desc' else 'asc')


def url_pagina(endpoint, numero):
    """
    URL de `endpoint` en la página `numero`, con los filtros de la petición.

    Igual que url_orden: conserva los filtros (también los repetidos) y
    descarta los que empiezan por `_` o chocan con url_for. La página 1 no
    lleva `page`.
    """
    args = {clave: valores for clave, valores in request.args.lists()
            if not clave.startswith('_') and clave not in ARGUMENTOS_URL_FOR and clave != 'page'}
    if numero > 1:
        args['page'] = numero
    return url_for(endpoint, **args)


def url_segura(url):
    """
    Filtro Jinja: `url` sin espacios en los extremos si es una ruta propia
    (`/...`, pero no `//` ni `/\\`) o usa http, https o mailto; si no, ''.

    La comparación no distingue mayúsculas ni tiene en cuenta los espacios,
    tabuladores o saltos de línea, que el navegador también ignora.
    """
    if not url:
        return ''
    normalizada = _IGNORADOS.sub('', str(url)).lower()
    if normalizada.startswith('/'):
        valida = not normalizada.startswith(('//', '/\\'))
    else:
        valida = normalizada.startswith(ESQUEMAS_SEGUROS)
    return str(url).strip() if valida else ''
