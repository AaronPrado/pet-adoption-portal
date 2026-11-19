"""
Tests de `app/contexto.py`:
- `usuario_nav()`: el usuario que ven la navegación y las salidas de las
  páginas de error. Nunca lanza, para que un 500 con la base de datos caída
  no se quede sin página.
"""

import logging

from flask_login import login_user

from app import contexto, errores


class UsuarioRoto:
    """current_user cuando la base de datos no responde."""

    @property
    def is_authenticated(self):
        raise RuntimeError('sin base de datos')


def test_anonimo(app):
    with app.test_request_context('/'):
        assert contexto.usuario_nav() is None


def test_con_sesion(app, usuario_admin):
    with app.test_request_context('/'):
        login_user(usuario_admin)
        assert contexto.usuario_nav() == contexto.UsuarioNav(nombre='Admin Test', admin=True)


def test_adoptante(app, usuario_adoptante):
    with app.test_request_context('/'):
        login_user(usuario_adoptante)
        assert contexto.usuario_nav() == contexto.UsuarioNav(nombre='Pepe', admin=False)


def test_si_falla_la_carga_del_usuario_se_trata_como_anonimo(app, monkeypatch, caplog):
    monkeypatch.setattr(contexto, 'current_user', UsuarioRoto())
    with app.test_request_context('/'), caplog.at_level(logging.ERROR):
        assert contexto.usuario_nav() is None
    assert 'No se ha podido cargar el usuario' in caplog.text


def test_el_fallo_se_registra_una_vez_por_peticion(app, monkeypatch, caplog):
    """Cada render la vuelve a pedir: sin la marca en g, la traza se
    repetiría en el log varias veces por petición."""
    monkeypatch.setattr(contexto, 'current_user', UsuarioRoto())
    # Cada petición real tiene su propio contexto de aplicación (y su g)
    with caplog.at_level(logging.ERROR):
        with app.app_context(), app.test_request_context('/'):
            for _ in range(3):
                assert contexto.usuario_nav() is None
        with app.app_context(), app.test_request_context('/'):
            contexto.usuario_nav()

    assert len([r for r in caplog.records if 'No se ha podido cargar el usuario' in r.getMessage()]) == 2


def test_salidas_de_error_sin_usuario_cargable(app, monkeypatch):
    """Si no se puede cargar el usuario, las salidas son las de un anónimo
    en lugar de hacer fallar la página de error."""
    monkeypatch.setattr(contexto, 'current_user', UsuarioRoto())
    with app.test_request_context('/'):
        salidas = errores.resolver_salidas((errores.INICIAR_SESION, errores.MIS_SOLICITUDES, errores.INICIO))

    assert salidas == [('Iniciar sesión', '/auth/login'), ('Ir al inicio', '/')]


def test_salidas_de_error_del_adoptante(app, usuario_adoptante):
    with app.test_request_context('/'):
        login_user(usuario_adoptante)
        salidas = errores.resolver_salidas((errores.INICIAR_SESION, errores.MIS_SOLICITUDES))

    assert salidas == [('Ver mis solicitudes', '/solicitudes/mis-solicitudes')]
