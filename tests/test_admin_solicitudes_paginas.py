"""
Solicitudes del admin sin Bootstrap (B5.3: P-23, P-28, P-42, P-45):
contador de pendientes en la navegación, `solicitudes/admin/lista.html`,
`solicitudes/admin/revisar.html` y el admin ante «Solicitar adopción».
"""

import logging
import re

import pytest
from flask_login import login_user
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError

from app import contexto, db
from app.models import Mascota, Solicitud, Usuario
from tests.test_catalogo_paginas import html_de
from tests.test_rendimiento import ContadorConsultas

LISTA = '/solicitudes/admin'


def revisar(solicitud):
    return f'/solicitudes/admin/revisar/{solicitud.id}'


def principal(html):
    """HTML del `<main>`, sin la navegación."""
    return html.split('<main', 1)[1].split('</main>', 1)[0]


def h1_de(html):
    return re.findall(r'<h1[^>]*>([^<]+)</h1>', html)


def enlace_solicitudes(html):
    """Texto del enlace del menú a la gestión de solicitudes."""
    return re.search(r'<a class="menu-usuario__opcion" href="/solicitudes/admin"[^>]*>([^<]*)</a>', html).group(1)


def solicitud_de(nombre, mascota, fecha=None, estado='pendiente', email=None):
    """Una solicitud de un usuario nuevo `nombre` para `mascota`."""
    usuario = Usuario(email=email or f'{nombre.lower()}@test.com', nombre=nombre, password='password123')
    db.session.add(usuario)
    db.session.flush()
    solicitud = Solicitud(usuario_id=usuario.id, mascota_id=mascota.id)
    if fecha:
        solicitud.fecha_solicitud = fecha
    solicitud.estado = estado
    db.session.add(solicitud)
    db.session.commit()
    return solicitud


def mascota_nueva(nombre):
    mascota = Mascota(nombre=nombre, especie='Perro', descripcion='Perro sociable y tranquilo')
    db.session.add(mascota)
    db.session.commit()
    return mascota


class TestContadorDePendientes:
    """P-28 y P-42: el enlace del panel dice cuántas solicitudes esperan."""

    def test_enlaces_del_admin_sin_title_case(self, client, auth_headers_admin):
        html = client.get('/no-existe').data.decode()

        assert '>Gestionar mascotas</a>' in html
        assert enlace_solicitudes(html) == 'Gestionar solicitudes'
        assert 'Panel Admin' not in html

    @pytest.mark.parametrize('numero, texto', [
        (1, 'Gestionar solicitudes (1 pendiente)'),
        (3, 'Gestionar solicitudes (3 pendientes)'),
    ])
    def test_cuenta_las_pendientes(self, client, auth_headers_admin, mascota_disponible, numero, texto):
        for i in range(numero):
            solicitud_de(f'Ana{i}', mascota_disponible)
        solicitud_de('Resuelta', mascota_disponible, estado='rechazada')

        assert enlace_solicitudes(client.get('/no-existe').data.decode()) == texto

    def test_admin_una_sola_consulta_por_peticion(self, app, usuario_admin):
        with app.test_request_context('/'):
            login_user(usuario_admin)
            with ContadorConsultas(db.engine) as contador:
                for _ in range(3):
                    assert contexto.usuario_nav().pendientes == 0
        assert contador.total == 1

    def test_adoptante_no_consulta(self, app, usuario_adoptante, solicitud_pendiente):
        with app.test_request_context('/'):
            login_user(usuario_adoptante)
            with ContadorConsultas(db.engine) as contador:
                usuario = contexto.usuario_nav()
        assert usuario.pendientes is None
        assert contador.total == 0

    def test_anonimo_no_consulta(self, app):
        with app.test_request_context('/'), ContadorConsultas(db.engine) as contador:
            assert contexto.usuario_nav() is None
        assert contador.total == 0

    def test_si_falla_el_recuento_no_lanza(self, app, usuario_admin, monkeypatch, caplog):
        def roto():
            raise RuntimeError('sin base de datos')
        monkeypatch.setattr(contexto, 'contar_pendientes', roto)

        with app.test_request_context('/'), caplog.at_level(logging.ERROR):
            login_user(usuario_admin)
            usuario = contexto.usuario_nav()
            assert contexto.usuario_nav() == usuario

        assert usuario == contexto.UsuarioNav(nombre='Admin Test', admin=True, pendientes=None)
        assert caplog.text.count('No se ha podido contar las solicitudes pendientes') == 1

    def test_un_error_de_la_base_de_datos_no_deja_la_transaccion_rota(self, app, client, auth_headers_admin,
                                                                      solicitud_pendiente, monkeypatch):
        """
        En PostgreSQL, un error SQL aborta la transacción y cualquier consulta
        posterior de la misma petición fallaría. Tras el fallo del recuento se
        deshace la transacción y la página se pinta entera.
        """
        def consulta_rota():
            return db.session.scalar(text('SELECT count(*) FROM tabla_que_no_existe'))
        monkeypatch.setattr(contexto, 'contar_pendientes', consulta_rota)
        sucesos = []

        def anotar_sentencia(conn, cursor, sentencia, *args):
            sucesos.append(sentencia)

        def anotar_rollback(conn):
            sucesos.append('ROLLBACK')

        event.listen(db.engine, 'before_cursor_execute', anotar_sentencia)
        event.listen(db.engine, 'rollback', anotar_rollback)
        try:
            # La ficha consulta las pendientes de la mascota después del menú
            response = client.get(f'/mascotas/{solicitud_pendiente.mascota_id}')
        finally:
            event.remove(db.engine, 'before_cursor_execute', anotar_sentencia)
            event.remove(db.engine, 'rollback', anotar_rollback)

        assert response.status_code == 200
        html = response.data.decode()
        assert enlace_solicitudes(html) == 'Gestionar solicitudes'
        assert 'Cerbero' in principal(html)
        posteriores = sucesos[[i for i, s in enumerate(sucesos) if 'tabla_que_no_existe' in s][0] + 1:]
        # Primero se deshace la transacción abortada y después siguen las consultas
        assert posteriores[0] == 'ROLLBACK'
        assert any(s.lstrip().upper().startswith('SELECT') for s in posteriores[1:])

    def test_consulta_posterior_en_la_misma_peticion(self, app, usuario_admin, monkeypatch, caplog):
        def consulta_rota():
            return db.session.scalar(text('SELECT count(*) FROM tabla_que_no_existe'))
        monkeypatch.setattr(contexto, 'contar_pendientes', consulta_rota)

        with app.test_request_context('/'), caplog.at_level(logging.ERROR):
            login_user(usuario_admin)
            assert contexto.usuario_nav().pendientes is None
            assert db.session.scalar(text('SELECT 1')) == 1
        assert 'No se ha podido contar las solicitudes pendientes' in caplog.text

    def test_si_tampoco_se_puede_deshacer_no_lanza(self, app, usuario_admin, monkeypatch, caplog):
        def roto(*args):
            raise SQLAlchemyError('sin conexión')
        monkeypatch.setattr(contexto, 'contar_pendientes', roto)
        monkeypatch.setattr(db.session, 'rollback', roto)

        with app.test_request_context('/'), caplog.at_level(logging.ERROR):
            login_user(usuario_admin)
            assert contexto.usuario_nav().pendientes is None
        assert 'No se ha podido deshacer la transacción tras el recuento' in caplog.text

    def test_el_menu_se_pinta_sin_recuento(self, client, auth_headers_admin, monkeypatch):
        def roto():
            raise RuntimeError('sin base de datos')
        monkeypatch.setattr(contexto, 'contar_pendientes', roto)

        assert enlace_solicitudes(client.get('/no-existe').data.decode()) == 'Gestionar solicitudes'


class TestAdminNoSolicita:
    """P-45: el refugio gestiona solicitudes, no las envía."""

    def test_la_ficha_no_ofrece_solicitar(self, client, auth_headers_admin, mascota_disponible):
        html = principal(html_de(client, f'/mascotas/{mascota_disponible.id}'))

        assert 'Solicitar adopción' not in html
        assert f'/solicitudes/nueva/{mascota_disponible.id}' not in html

    def test_el_adoptante_si(self, client, auth_headers_adoptante, mascota_disponible):
        html = principal(html_de(client, f'/mascotas/{mascota_disponible.id}'))

        assert 'Solicitar adopción' in html

    @pytest.mark.parametrize('metodo', ['get', 'post'])
    def test_la_ruta_da_un_403_propio(self, client, auth_headers_admin, mascota_disponible,
                                      respuestas_validas, metodo):
        url = f'/solicitudes/nueva/{mascota_disponible.id}'
        response = getattr(client, metodo)(url, data=respuestas_validas)

        assert response.status_code == 403
        html = response.data.decode()
        assert h1_de(html) == ['Las cuentas del refugio no pueden solicitar adopciones']
        assert 'Cerbero' in principal(html)
        assert f'href="/mascotas/{mascota_disponible.id}">Volver a la ficha de Cerbero</a>' in html
        assert 'href="/solicitudes/admin">Gestionar solicitudes</a>' in principal(html)
        assert Solicitud.query.count() == 0

    def test_mascota_inexistente_sigue_siendo_404(self, client, auth_headers_admin):
        assert client.get('/solicitudes/nueva/99999').status_code == 404
