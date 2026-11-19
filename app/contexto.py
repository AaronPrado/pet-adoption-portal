"""
Contexto común de las plantillas (base sin Bootstrap, `base.html`, B3.6).

- `contexto_marca`: context processor con la marca de la protectora
  (`MARCA_NOMBRE`, `MARCA_LOGO`, `MARCA_CONTACTO` y `MARCA_CREDITO` de
  config.py) y el año del pie.
- `usuario_nav`: global de Jinja con lo que la navegación y las salidas de
  las páginas de error necesitan del usuario. Nunca lanza: la base también
  pinta la página del 500, cuando la base de datos puede no responder.
"""

from typing import NamedTuple

from flask import current_app, g, url_for
from flask_login import current_user

from app.models import utcnow


class UsuarioNav(NamedTuple):
    nombre: str
    admin: bool


def url_logo(logo):
    """
    URL de MARCA_LOGO: una ruta relativa se sirve desde static/; una ruta
    absoluta o una URL se deja tal cual, y la plantilla la pasa por
    `url_segura`, que descarta lo que no sea propio, http(s) o mailto.
    """
    if not logo or logo.startswith('/') or ':' in logo:
        return logo
    return url_for('static', filename=logo)


def contexto_marca():
    """Marca de la protectora y año actual (UTC) para todas las plantillas."""
    config = current_app.config
    return {
        'marca_nombre': config['MARCA_NOMBRE'],
        'marca_logo': url_logo(config['MARCA_LOGO']),
        'marca_contacto': config['MARCA_CONTACTO'],
        'marca_credito': config['MARCA_CREDITO'],
        'anio_actual': utcnow().year,
    }


def usuario_nav():
    """
    Nombre y rol del usuario con sesión, o None si es anónimo. Si cargarlo
    falla (base de datos caída, transacción deshecha tras un error), se trata
    como anónimo para que la página se pinte igualmente. La traza se
    registra una sola vez por petición, aunque se llame en cada render.
    """
    try:
        if not current_user.is_authenticated:
            return None
        return UsuarioNav(nombre=current_user.nombre, admin=current_user.is_admin())
    except Exception:
        if not g.get('fallo_usuario_nav'):
            g.fallo_usuario_nav = True
            current_app.logger.exception('No se ha podido cargar el usuario para la navegación')
        return None


def registrar_contexto(app):
    """Registra la marca y el usuario de la navegación en las plantillas de `app`."""
    app.context_processor(contexto_marca)
    app.add_template_global(usuario_nav)
