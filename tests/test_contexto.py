"""
Tests de `app/contexto.py`:
- `usuario_nav()`: el usuario que ven la navegación y las salidas de las
  páginas de error. Nunca lanza, para que un 500 con la base de datos caída
  no se quede sin página.
- `contexto_marca`: la marca de la protectora y el año del pie.
"""

import logging
from datetime import UTC, datetime

import pytest
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
        assert contexto.usuario_nav() == contexto.UsuarioNav(nombre='Admin Test', admin=True, pendientes=0)


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


# utcnow() devuelve UTC sin zona
EN_2031 = datetime(2031, 5, 1, tzinfo=UTC).replace(tzinfo=None)


class TestContextoDeMarca:

    def test_valores_por_defecto(self, app, monkeypatch):
        monkeypatch.setattr(contexto, 'utcnow', lambda: EN_2031)
        with app.test_request_context('/'):
            assert contexto.contexto_marca() == {
                'marca_nombre': 'Portal de Adopción', 'marca_logo': '', 'marca_contacto': '',
                'marca_credito': 'Desarrollado por Aarón Prado', 'anio_actual': 2031}

    def test_logo_dentro_de_static(self, app):
        app.config.update(MARCA_NOMBRE='Protectora Ejemplo', MARCA_LOGO='img/logo.svg',
                          MARCA_CONTACTO='hola@protectora.example', MARCA_CREDITO='')
        with app.test_request_context('/'):
            marca = contexto.contexto_marca()
        assert {clave: marca[clave] for clave in ('marca_nombre', 'marca_logo', 'marca_contacto', 'marca_credito')} == {
            'marca_nombre': 'Protectora Ejemplo', 'marca_logo': '/static/img/logo.svg',
            'marca_contacto': 'hola@protectora.example', 'marca_credito': ''}

    @pytest.mark.parametrize('logo', ['https://cdn.example/logo.svg', '/logo.svg', 'javascript:alert(1)'])
    def test_url_o_ruta_absoluta_se_deja_para_url_segura(self, app, logo):
        app.config['MARCA_LOGO'] = logo
        with app.test_request_context('/'):
            assert contexto.contexto_marca()['marca_logo'] == logo

    def test_registrado_en_la_factory(self, app):
        assert contexto.contexto_marca in app.template_context_processors[None]
