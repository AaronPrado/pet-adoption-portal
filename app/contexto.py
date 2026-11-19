"""
Contexto común de las plantillas.

- `usuario_nav`: lo que la navegación y las salidas de las páginas de error
  necesitan del usuario. Nunca lanza: también se usa al pintar la página del
  500, cuando la base de datos puede no responder.
"""

from typing import NamedTuple

from flask import current_app, g
from flask_login import current_user


class UsuarioNav(NamedTuple):
    nombre: str
    admin: bool


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
