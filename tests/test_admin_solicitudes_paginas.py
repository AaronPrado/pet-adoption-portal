"""
Solicitudes del admin sin Bootstrap (B5.3: P-23, P-28, P-42, P-45):
contador de pendientes en la navegación, `solicitudes/admin/lista.html`,
`solicitudes/admin/revisar.html` y el admin ante «Solicitar adopción».
"""

import logging
import os
import re

import pytest
from flask_login import login_user
from sqlalchemy import event, text
from sqlalchemy.exc import SQLAlchemyError

from app import contexto, db
from app.models import Mascota, Solicitud, Usuario
from tests.test_catalogo_paginas import CLASES_BOOTSTRAP, html_de
from tests.test_fechas import utc
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


class TestLista:

    def test_sin_bootstrap_un_h1_y_titulo(self, client, auth_headers_admin, solicitud_pendiente):
        html = html_de(client, LISTA)

        assert not CLASES_BOOTSTRAP.search(html)
        assert 'bootstrap' not in html.lower()
        assert h1_de(html) == ['Gestión de solicitudes']
        assert '<title>Gestión de solicitudes - ' in html
        assert 'css/paginas/admin-solicitudes.css' in html

    def test_tabla_con_estado_fecha_local_y_accion_con_nombre(self, client, auth_headers_admin, solicitud_pendiente):
        solicitud_pendiente.fecha_solicitud = utc(2026, 11, 15, 23, 30)
        db.session.commit()

        html = principal(html_de(client, LISTA))

        assert 'class="tabla" role="region"' in html
        assert '<caption id="solicitudes-titulo"' in html
        assert re.search(r'<th scope="row">\s*Cerbero', html)
        assert 'chapa--aviso' in html and 'Pendiente' in html
        # 23:30 UTC es ya el día 16 en Madrid
        assert '16 de noviembre de 2026' in html
        assert re.search(rf'href="{revisar(solicitud_pendiente)}">Revisar'
                         r'<span class="visualmente-oculto"> la solicitud de Pepe para Cerbero</span></a>', html)
        assert 'adoptante@test.com' in html

    def test_resuelta_se_ve_no_se_revisa(self, client, auth_headers_admin, solicitud_pendiente, usuario_admin):
        solicitud_pendiente.registrar_revision('aprobada', usuario_admin.id)
        db.session.commit()

        html = principal(html_de(client, LISTA))

        assert 'chapa--exito' in html and 'Aprobada' in html
        assert re.search(rf'href="{revisar(solicitud_pendiente)}">Ver<span', html)
        assert '>Revisar<' not in html

    def test_todas_pendientes_primero_de_la_mas_antigua(self, client, auth_headers_admin):
        mascota = mascota_nueva('Toby')
        solicitud_de('Reciente', mascota, utc(2026, 3, 1))
        solicitud_de('Antigua', mascota, utc(2026, 1, 1))
        solicitud_de('Aprobada', mascota_nueva('Luna'), utc(2026, 2, 1), 'aprobada')
        solicitud_de('Rechazada', mascota_nueva('Kira'), utc(2026, 4, 1), 'rechazada')

        html = principal(html_de(client, LISTA))
        orden = re.findall(r'la solicitud de (\w+) para', html)

        # Pendientes de la más antigua a la más reciente; las resueltas, después y de la más reciente
        assert orden == ['Antigua', 'Reciente', 'Rechazada', 'Aprobada']
        assert 'aria-sort' not in html

    @pytest.mark.parametrize('estado, orden, sentido', [
        ('pendiente', ['Antigua', 'Reciente'], 'ascending'),
        ('rechazada', ['Reciente', 'Antigua'], 'descending'),
    ])
    def test_filtro_ordenado_por_fecha(self, client, auth_headers_admin, estado, orden, sentido):
        mascota = mascota_nueva('Toby')
        solicitud_de('Reciente', mascota, utc(2026, 3, 1), estado)
        solicitud_de('Antigua', mascota, utc(2026, 1, 1), estado)
        solicitud_de('Otra', mascota_nueva('Luna'), utc(2026, 2, 1),
                     'aprobada')

        html = principal(html_de(client, f'{LISTA}?estado={estado}'))

        assert re.findall(r'la solicitud de (\w+) para', html) == orden
        assert f'aria-sort="{sentido}"' in html

    def test_filtros_marcan_el_activo(self, client, auth_headers_admin, solicitud_pendiente):
        html = principal(html_de(client, f'{LISTA}?estado=pendiente'))

        filtros = re.search(r'<nav class="filtros-estado" aria-label="Filtrar por estado">(.*?)</nav>',
                            html, re.S).group(1)
        assert re.search(r'href="/solicitudes/admin\?estado=pendiente" aria-current="page">Pendientes</a>', filtros)
        assert re.search(r'href="/solicitudes/admin">Todas</a>', filtros)
        assert filtros.count('aria-current') == 1

    def test_estado_desconocido_muestra_todas(self, client, auth_headers_admin, solicitud_pendiente):
        html = principal(html_de(client, f'{LISTA}?estado=<b>x</b>'))

        assert 'la solicitud de Pepe para Cerbero' in html
        assert re.search(r'href="/solicitudes/admin" aria-current="page">Todas</a>', html)
        assert '<b>x</b>' not in html

    def test_vacia_con_filtro_ofrece_ver_todas(self, client, auth_headers_admin, solicitud_pendiente):
        html = principal(html_de(client, f'{LISTA}?estado=aprobada'))

        assert 'No hay solicitudes aprobadas' in html
        assert 'href="/solicitudes/admin">Ver todas las solicitudes</a>' in html
        assert '<table' not in html

    def test_vacia_sin_filtro(self, client, auth_headers_admin):
        html = principal(html_de(client, LISTA))

        assert 'Todavía no hay solicitudes' in html
        assert 'Ver todas las solicitudes' not in html

    @pytest.mark.parametrize('estado', ['', 'pendiente', 'rechazada'])
    def test_desempate_por_id_estable_entre_paginas(self, app, client, auth_headers_admin, estado):
        """Con la misma fecha manda el id: pendientes por orden de llegada, resueltas al revés."""
        app.config['ADMIN_POR_PAGINA'] = 2
        mascota = mascota_nueva('Toby')
        fecha = utc(2026, 5, 5, 10, 0)
        estado_creado = estado or 'pendiente'
        for nombre in ('Ana', 'Bea', 'Carla', 'Dora', 'Eva'):
            solicitud_de(nombre, mascota, fecha, estado_creado)

        nombres = []
        for page in (1, 2, 3):
            html = principal(html_de(client, f'{LISTA}?estado={estado}&page={page}'))
            nombres += re.findall(r'la solicitud de (\w+) para', html)

        esperado = ['Ana', 'Bea', 'Carla', 'Dora', 'Eva']
        assert nombres == (esperado if estado_creado == 'pendiente' else esperado[::-1])

    def test_desempate_en_todas_con_pendientes_y_resueltas(self, client, auth_headers_admin):
        mascota = mascota_nueva('Toby')
        fecha = utc(2026, 5, 5, 10, 0)
        for nombre, estado in (('Ana', 'aprobada'), ('Bea', 'pendiente'), ('Carla', 'rechazada'),
                               ('Dora', 'pendiente')):
            solicitud_de(nombre, mascota, fecha, estado)

        html = principal(html_de(client, LISTA))

        assert re.findall(r'la solicitud de (\w+) para', html) == ['Bea', 'Dora', 'Carla', 'Ana']

    def test_paginacion_del_sistema_conserva_el_filtro(self, app, client, auth_headers_admin):
        app.config['ADMIN_POR_PAGINA'] = 2
        mascota = mascota_nueva('Toby')
        for i in range(3):
            solicitud_de(f'Ana{i}', mascota, utc(2026, 1, i + 1))

        html = principal(html_de(client, f'{LISTA}?estado=pendiente&page=2'))

        assert '<nav class="paginacion" aria-label="Paginación">' in html
        assert 'href="/solicitudes/admin?estado=pendiente" rel="prev"' in html
        assert 'page-link' not in html
        assert re.findall(r'la solicitud de (\w+) para', html) == ['Ana2']


class TestRevisar:

    def test_sin_bootstrap_un_h1_y_titulo(self, client, auth_headers_admin, solicitud_pendiente):
        html = html_de(client, revisar(solicitud_pendiente))

        assert not CLASES_BOOTSTRAP.search(html)
        assert 'bootstrap' not in html.lower()
        assert h1_de(html) == ['Revisar la solicitud de Pepe para Cerbero']
        assert '<title>Revisar la solicitud de Pepe para Cerbero - ' in html
        assert 'css/paginas/admin-solicitudes.css' in html
        assert 'href="/solicitudes/admin">Volver a gestión de solicitudes</a>' in html

    def test_respuestas_con_el_parcial_de_la_base_nueva(self, client, auth_headers_admin, solicitud_pendiente):
        html = principal(html_de(client, revisar(solicitud_pendiente)))

        assert 'class="respuestas__seccion"' in html
        plantillas = os.path.join(os.path.dirname(__file__), '..', 'app', 'templates', 'solicitudes')
        assert not os.path.exists(os.path.join(plantillas, '_respuestas.html'))

    def test_datos_del_solicitante_y_fecha_local(self, client, auth_headers_admin, solicitud_pendiente):
        solicitud_pendiente.fecha_solicitud = utc(2026, 7, 1, 10, 5)
        db.session.commit()

        html = principal(html_de(client, revisar(solicitud_pendiente)))

        assert 'Pepe Pérez Pérez' in html
        assert 'adoptante@test.com' in html and '612345678' in html
        assert '1 de julio de 2026, 12:05' in html

    def test_otras_candidatas_de_la_misma_mascota(self, client, auth_headers_admin, solicitud_pendiente):
        mascota = solicitud_pendiente.mascota
        otra = solicitud_de('Luis', mascota, utc(2026, 1, 1))
        solicitud_de('Marta', mascota, utc(2026, 2, 1), 'rechazada')
        solicitud_de('Ajena', mascota_nueva('Luna'))

        html = principal(html_de(client, revisar(solicitud_pendiente)))
        seccion = re.search(r'<section class="candidatas"(.*?)</section>', html, re.S).group(1)

        assert 'Otras solicitudes para Cerbero' in seccion
        # La fecha va en el nombre del enlace: dos solicitantes con el mismo nombre no se confunden
        enlaces = re.findall(r'Ver la solicitud de </span>(\w+)'
                             r'<span class="visualmente-oculto">, enviada el ([^<]+)</span></a>', seccion)
        assert enlaces == [('Luis', '1 de enero de 2026'), ('Marta', '1 de febrero de 2026')]
        # La fecha visible no se lee dos veces
        assert '<span class="solicitud__fecha" aria-hidden="true">Enviada el 1 de enero de 2026</span>' in seccion
        assert f'href="{revisar(otra)}"' in seccion
        assert 'Pendiente' in seccion and 'Rechazada' in seccion
        assert 'Ajena' not in html and 'Pepe<' not in seccion

    def test_sin_otras_candidatas(self, client, auth_headers_admin, solicitud_pendiente):
        html = principal(html_de(client, revisar(solicitud_pendiente)))

        assert 'No hay otras solicitudes para Cerbero.' in html

    def test_aprobar_explica_que_rechaza_las_demas(self, client, auth_headers_admin, solicitud_pendiente):
        solicitud_de('Luis', solicitud_pendiente.mascota)

        html = principal(html_de(client, revisar(solicitud_pendiente)))
        decision = re.search(r'<section class="decision"(.*?)</section>', html, re.S).group(1)
        efecto = re.search(r'<p class="decision__efecto[^"]*">(.*?)</p>', decision, re.S).group(1)

        assert 'Cerbero pasará a «Adoptada»' in efecto
        assert 'Se rechazará automáticamente 1 solicitud pendiente' in efecto
        assert 'No se puede deshacer' in efecto
        # El aviso va antes de los dos formularios
        assert decision.index('decision__efecto') < decision.index('<form')

    def test_formularios_con_macros_y_csrf(self, app, client, auth_headers_admin, solicitud_pendiente):
        app.config['WTF_CSRF_ENABLED'] = True
        html = principal(html_de(client, revisar(solicitud_pendiente)))

        formularios = re.findall(r'<form method="POST"[^>]*>(.*?)</form>', html, re.S)
        assert len(formularios) == 2
        for formulario in formularios:
            assert re.search(r'<input type="hidden" name="csrf_token" value="[^"]+">', formulario)
        assert '<label class="campo__etiqueta" for="comentarios">Mensaje para Pepe (opcional)</label>' in html
        assert 'class="campo__etiqueta" for="motivo">Motivo del rechazo' in html
        assert 'class="boton boton--peligro">Rechazar solicitud</button>' in html
        assert 'class="boton boton--primario">Aprobar solicitud</button>' in html

    def test_rechazar_pide_confirmacion_con_nombres(self, client, auth_headers_admin, solicitud_pendiente):
        html = principal(html_de(client, revisar(solicitud_pendiente)))

        rechazar = re.search(r'<form method="POST"[^>]*aria-labelledby="rechazar-titulo"[^>]*>', html).group(0)
        confirmar = re.search(r'data-confirmar="([^"]*)"', rechazar).group(1)
        assert 'Pepe' in confirmar and 'Cerbero' in confirmar
        assert confirmar.startswith('¿Rechazar la solicitud de Pepe para Cerbero?')
        assert 'No se puede deshacer' in confirmar

    def test_aside_con_nombre_descriptivo(self, client, auth_headers_admin, solicitud_pendiente):
        html = principal(html_de(client, revisar(solicitud_pendiente)))

        assert '<aside class="solicitud-detalle__mascota" aria-label="Mascota: Cerbero">' in html

    def test_rechazar_sin_motivo_error_en_el_campo_y_resumen(self, client, auth_headers_admin, solicitud_pendiente):
        response = client.post(revisar(solicitud_pendiente), data={'accion': 'rechazar', 'motivo': ' '})

        assert response.status_code == 400
        html = principal(response.data.decode())
        assert 'id="motivo-error"' in html
        assert re.search(r'<textarea[^>]*id="motivo"[^>]*aria-invalid="true"[^>]*aria-describedby="motivo-error', html)
        assert 'data-resumen-errores' in html and 'href="#motivo"' in html
        assert 'autofocus' not in html
        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'pendiente'

    def test_resuelta_muestra_el_resultado(self, client, auth_headers_admin, solicitud_pendiente, usuario_admin):
        solicitud_pendiente.registrar_revision('rechazada', usuario_admin.id, 'No encaja')
        solicitud_pendiente.fecha_revision = utc(2026, 7, 1, 10, 5)
        db.session.commit()

        html = html_de(client, revisar(solicitud_pendiente))

        assert h1_de(html) == ['Solicitud de Pepe para Cerbero']
        main = principal(html)
        assert '<form' not in main
        assert 'Rechazada el 1 de julio de 2026, 12:05 por Admin Test.' in main
        assert 'chapa--error' in main


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
