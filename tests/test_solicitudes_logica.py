"""
Tests de la regla de adopción (ADR-0004): las solicitudes se admiten en
paralelo y el estado de la mascota lo decide solo el flujo.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import delete, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app import adopciones, db
from app.models import Mascota, Solicitud, Usuario, utcnow
from app.routes.api.auth import generate_token


def crear_por_api(client, usuario, mascota_id, cuestionario):
    return client.post('/api/solicitudes/', json={
        'mascota_id': mascota_id,
        'cuestionario': cuestionario
    }, headers={'Authorization': f'Bearer {generate_token(usuario.id)}'})


def nuevo_usuario(email):
    usuario = Usuario(email=email, nombre=email.split('@')[0], password='password123')
    db.session.add(usuario)
    db.session.commit()
    return usuario


def nueva_solicitud(usuario, mascota):
    solicitud = Solicitud(usuario_id=usuario.id, mascota_id=mascota.id, cuestionario={'a': 'b'})
    db.session.add(solicitud)
    db.session.commit()
    return solicitud


@pytest.fixture
def tres_pendientes(usuario_adoptante, mascota_disponible):
    """Tres solicitudes pendientes de usuarios distintos para la misma mascota."""
    usuarios = [usuario_adoptante, nuevo_usuario('dos@test.com'), nuevo_usuario('tres@test.com')]
    return [nueva_solicitud(u, mascota_disponible) for u in usuarios]


class TestApiSolicitudes:

    def test_crear_por_api_deja_la_mascota_disponible(self, client, usuario_adoptante, mascota_disponible,
                                                        respuestas_validas):
        assert crear_por_api(client, usuario_adoptante, mascota_disponible.id, respuestas_validas).status_code == 201
        assert db.session.get(Mascota, mascota_disponible.id).estado == 'disponible'

    def test_segunda_solicitud_en_paralelo_por_api(self, client, usuario_adoptante, mascota_disponible,
                                                   respuestas_validas):
        otro = nuevo_usuario('otro@test.com')

        crear_por_api(client, usuario_adoptante, mascota_disponible.id, respuestas_validas)
        response = crear_por_api(client, otro, mascota_disponible.id, respuestas_validas)

        assert response.status_code == 201
        assert Solicitud.query.filter_by(estado='pendiente').count() == 2

    def test_mascota_adoptada_por_api(self, client, usuario_adoptante, mascota_adoptada, respuestas_validas):
        response = crear_por_api(client, usuario_adoptante, mascota_adoptada.id, respuestas_validas)

        assert response.status_code == 400
        assert response.get_json() == {'error': adopciones.MascotaNoDisponible.mensaje}

    def test_duplicada_por_api_usa_el_mensaje_del_dominio(self, client, usuario_adoptante, mascota_disponible,
                                                         respuestas_validas):
        crear_por_api(client, usuario_adoptante, mascota_disponible.id, respuestas_validas)
        response = crear_por_api(client, usuario_adoptante, mascota_disponible.id, respuestas_validas)

        assert response.status_code == 409
        assert response.get_json() == {'error': adopciones.SolicitudDuplicada.mensaje}

    def test_mascota_borrada_mientras_tanto_por_api_da_404(self, client, usuario_adoptante,
                                                            mascota_disponible, monkeypatch, respuestas_validas):
        def fallar(*args):
            raise adopciones.MascotaNoEncontrada()
        monkeypatch.setattr(adopciones, 'crear_solicitud', fallar)

        response = crear_por_api(client, usuario_adoptante, mascota_disponible.id, respuestas_validas)

        assert response.status_code == 404
        assert response.get_json() == {'error': adopciones.MascotaNoEncontrada.mensaje}

    @pytest.mark.parametrize('cuestionario', [
        ['no', 'es', 'objeto'],
        {'anidado': {'a': 1}},
        {'largo': 'x' * 2001},
        {f'campo{i}': 'x' for i in range(31)},
        'texto',
    ])
    def test_cuestionario_invalido(self, client, usuario_adoptante, mascota_disponible, cuestionario):
        response = crear_por_api(client, usuario_adoptante, mascota_disponible.id, cuestionario)
        assert response.status_code == 400

    @pytest.mark.parametrize('mascota_id', ['1', True, None, 1.5])
    def test_mascota_id_debe_ser_entero(self, client, usuario_adoptante, mascota_disponible, mascota_id,
                                       respuestas_validas):
        assert crear_por_api(client, usuario_adoptante, mascota_id, respuestas_validas).status_code == 400


class TestCrearSolicitud:

    def test_crear_no_cambia_la_mascota(self, app, usuario_adoptante, mascota_disponible):
        solicitud = adopciones.crear_solicitud(usuario_adoptante.id, mascota_disponible.id, {'a': 'b'})

        assert solicitud.estado == 'pendiente'
        assert db.session.get(Mascota, mascota_disponible.id).estado == 'disponible'

    def test_crear_duplicada(self, app, usuario_adoptante, mascota_disponible):
        adopciones.crear_solicitud(usuario_adoptante.id, mascota_disponible.id, {'a': 'b'})

        with pytest.raises(adopciones.SolicitudDuplicada):
            adopciones.crear_solicitud(usuario_adoptante.id, mascota_disponible.id, {'a': 'b'})
        assert Solicitud.query.count() == 1

    def test_crear_sobre_mascota_inexistente(self, app, usuario_adoptante):
        with pytest.raises(adopciones.MascotaNoEncontrada):
            adopciones.crear_solicitud(usuario_adoptante.id, 9999, {'a': 'b'})

    def test_otra_restriccion_no_se_confunde_con_duplicada(self, app, mascota_disponible, monkeypatch):
        """Solo la restricción única es «duplicada»; el resto se registra y se relanza."""
        registrados = []
        monkeypatch.setattr(app.logger, 'exception', registrados.append)

        with pytest.raises(IntegrityError):
            adopciones.crear_solicitud(None, mascota_disponible.id, {'a': 'b'})
        assert registrados == ['Error de integridad al crear la solicitud']
        assert Solicitud.query.count() == 0

    @pytest.mark.parametrize(('orig', 'esperado'), [
        (SimpleNamespace(diag=SimpleNamespace(constraint_name='unique_usuario_mascota')), True),
        (SimpleNamespace(diag=SimpleNamespace(constraint_name='solicitudes_usuario_id_fkey')), False),
        (Exception('UNIQUE constraint failed: solicitudes.usuario_id, solicitudes.mascota_id'), True),
        (Exception('NOT NULL constraint failed: solicitudes.usuario_id'), False),
    ])
    def test_reconoce_la_restriccion_unica(self, orig, esperado):
        """psycopg 3 da el nombre en `diag.constraint_name`; SQLite solo en el texto."""
        error = IntegrityError('INSERT', {}, orig)

        assert adopciones.es_solicitud_duplicada(error) is esperado

    def test_crear_sobre_mascota_adoptada(self, app, usuario_adoptante, mascota_adoptada):
        with pytest.raises(adopciones.MascotaNoDisponible):
            adopciones.crear_solicitud(usuario_adoptante.id, mascota_adoptada.id, {'a': 'b'})
        assert Solicitud.query.count() == 0


class TestRechazar:

    def test_rechazar_solo_cambia_esa_solicitud(self, app, usuario_admin, tres_pendientes):
        primera, segunda, tercera = tres_pendientes

        adopciones.rechazar(primera, usuario_admin.id, 'No encaja')

        assert primera.estado == 'rechazada'
        assert primera.comentarios_admin == 'No encaja'
        assert primera.revisado_por == usuario_admin.id
        assert primera.fecha_revision is not None
        assert [segunda.estado, tercera.estado] == ['pendiente', 'pendiente']
        assert db.session.get(Mascota, primera.mascota_id).estado == 'disponible'

    def test_rechazar_ya_revisada(self, app, usuario_admin, tres_pendientes):
        adopciones.rechazar(tres_pendientes[0], usuario_admin.id, '')

        with pytest.raises(adopciones.SolicitudYaRevisada):
            adopciones.rechazar(tres_pendientes[0], usuario_admin.id, '')


class TestAprobar:

    def test_aprobar_adopta_y_rechaza_las_demas(self, app, usuario_admin, tres_pendientes):
        elegida, segunda, tercera = tres_pendientes
        otra_mascota = Mascota(nombre='Otra', especie='Gato', descripcion='x')
        db.session.add(otra_mascota)
        db.session.commit()
        ajena = nueva_solicitud(segunda.usuario, otra_mascota)

        adopciones.aprobar(elegida, usuario_admin.id, 'Perfecto')
        db.session.expire_all()

        assert db.session.get(Mascota, elegida.mascota_id).estado == 'adoptado'
        assert elegida.estado == 'aprobada'
        assert elegida.comentarios_admin == 'Perfecto'
        for solicitud in (segunda, tercera):
            assert solicitud.estado == 'rechazada'
            assert solicitud.comentarios_admin == adopciones.COMENTARIO_RECHAZO_AUTOMATICO
            assert solicitud.revisado_por == usuario_admin.id
            assert solicitud.fecha_revision is not None
        # Las solicitudes de otras mascotas no se tocan
        assert ajena.estado == 'pendiente'
        assert db.session.get(Mascota, otra_mascota.id).estado == 'disponible'

    def test_no_rechaza_de_nuevo_las_ya_resueltas(self, app, usuario_admin, tres_pendientes):
        elegida, rechazada_antes, _ = tres_pendientes
        adopciones.rechazar(rechazada_antes, usuario_admin.id, 'Motivo propio')

        adopciones.aprobar(elegida, usuario_admin.id, '')

        assert rechazada_antes.comentarios_admin == 'Motivo propio'

    def test_doble_aprobacion_seguida(self, app, usuario_admin, tres_pendientes):
        primera, segunda, _ = tres_pendientes
        adopciones.aprobar(primera, usuario_admin.id, '')

        with pytest.raises(adopciones.SolicitudYaRevisada):
            adopciones.aprobar(segunda, usuario_admin.id, '')
        assert Solicitud.query.filter_by(estado='aprobada').count() == 1

    def test_vuelve_a_leer_la_solicitud_tras_el_bloqueo(self, app, usuario_admin, tres_pendientes):
        """Otra transacción la resolvió mientras se esperaba el bloqueo: la copia en memoria está obsoleta."""
        solicitud = tres_pendientes[0]
        db.session.execute(
            update(Solicitud).where(Solicitud.id == solicitud.id).values(estado='rechazada'),
            execution_options={'synchronize_session': False},
        )
        assert solicitud.estado == 'pendiente'

        with pytest.raises(adopciones.SolicitudYaRevisada):
            adopciones.aprobar(solicitud, usuario_admin.id, '')
        assert db.session.get(Mascota, solicitud.mascota_id).estado == 'disponible'

    def test_aprobar_sobre_mascota_ya_adoptada_no_cambia_nada(self, app, usuario_admin, tres_pendientes):
        """Datos anteriores a la regla: pendiente sobre una mascota ya adoptada."""
        solicitud = tres_pendientes[0]
        db.session.execute(
            update(Mascota).where(Mascota.id == solicitud.mascota_id).values(estado='adoptado'),
            execution_options={'synchronize_session': False},
        )

        with pytest.raises(adopciones.MascotaYaAdoptada):
            adopciones.aprobar(solicitud, usuario_admin.id, '')
        db.session.expire_all()
        assert {s.estado for s in tres_pendientes} == {'pendiente'}

    def test_aprobar_si_la_mascota_ya_no_existe(self, app, usuario_admin, solicitud_pendiente):
        db.session.execute(
            delete(Mascota).where(Mascota.id == solicitud_pendiente.mascota_id),
            execution_options={'synchronize_session': False},
        )

        with pytest.raises(adopciones.MascotaNoEncontrada):
            adopciones.aprobar(solicitud_pendiente, usuario_admin.id, '')

    @pytest.mark.parametrize('operacion', ['aprobar', 'rechazar'])
    def test_solicitud_borrada_mientras_tanto(self, app, usuario_admin, tres_pendientes, operacion):
        """P. ej. se borró en cascada con su usuario: la relectura no la encuentra."""
        solicitud = tres_pendientes[0]
        db.session.execute(
            delete(Solicitud).where(Solicitud.id == solicitud.id),
            execution_options={'synchronize_session': False},
        )

        with pytest.raises(adopciones.SolicitudNoEncontrada):
            getattr(adopciones, operacion)(solicitud, usuario_admin.id, '')
        db.session.expire_all()
        assert db.session.get(Mascota, solicitud.mascota_id).estado == 'disponible'

    def test_los_errores_llevan_el_mensaje(self):
        assert str(adopciones.SolicitudYaRevisada()) == adopciones.SolicitudYaRevisada.mensaje

    def test_la_consulta_bloquea_la_fila_en_postgresql(self):
        consulta = adopciones.consulta_mascota_bloqueada(7)

        sql = str(consulta.compile(dialect=postgresql.dialect()))

        assert sql.rstrip().endswith('FOR UPDATE')
        assert 'mascotas.id = ' in sql


class TestRevisionAdmin:

    def test_solicitud_revisada_no_se_puede_cambiar(self, client, auth_headers_admin, solicitud_pendiente):
        url = f'/solicitudes/admin/revisar/{solicitud_pendiente.id}'
        client.post(url, data={'accion': 'rechazar', 'motivo': 'No encaja'})

        response = client.post(url, data={'accion': 'aprobar', 'comentarios': ''}, follow_redirects=True)

        assert 'Esta solicitud ya ha sido revisada.' in response.data.decode()
        solicitud = db.session.get(Solicitud, solicitud_pendiente.id)
        assert solicitud.estado == 'rechazada'
        assert solicitud.mascota.estado == 'disponible'

    def test_rechazar_por_la_web_deja_la_mascota_en_el_catalogo(self, client, auth_headers_admin,
                                                                solicitud_pendiente):
        client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}',
                    data={'accion': 'rechazar', 'motivo': 'No encaja'})

        assert 'Cerbero' in client.get('/mascotas/catalogo').data.decode()

    def test_aprobar_por_la_web_rechaza_las_demas(self, client, auth_headers_admin, solicitud_pendiente):
        segunda = nueva_solicitud(nuevo_usuario('otro@test.com'), solicitud_pendiente.mascota)

        client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}', data={'accion': 'aprobar'})
        response = client.post(f'/solicitudes/admin/revisar/{segunda.id}', data={'accion': 'aprobar'},
                               follow_redirects=True)

        assert 'Esta solicitud ya ha sido revisada.' in response.data.decode()
        assert db.session.get(Solicitud, segunda.id).estado == 'rechazada'

    def test_aprobar_por_la_web_mascota_ya_adoptada(self, client, auth_headers_admin, solicitud_pendiente):
        solicitud_pendiente.mascota.estado = 'adoptado'
        db.session.commit()

        response = client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}',
                               data={'accion': 'aprobar'}, follow_redirects=True)

        assert adopciones.MascotaYaAdoptada.mensaje in response.data.decode()
        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'pendiente'


    @pytest.mark.parametrize('error', [adopciones.MascotaNoEncontrada, adopciones.SolicitudNoEncontrada])
    @pytest.mark.parametrize('operacion', ['aprobar', 'rechazar'])
    def test_borrada_mientras_se_revisaba_da_404(self, client, auth_headers_admin,
                                                  solicitud_pendiente, monkeypatch, operacion, error):
        def fallar(*args):
            raise error()
        monkeypatch.setattr(adopciones, operacion, fallar)

        response = client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}',
                               data={'accion': operacion, 'motivo': 'No encaja'})

        assert response.status_code == 404


class TestRechazoSinRevisor:
    """La migración 0002 cierra pendientes sin admin: `revisado_por` queda NULL."""

    @pytest.fixture
    def cerrada_por_migracion(self, solicitud_pendiente):
        solicitud_pendiente.estado = 'rechazada'
        solicitud_pendiente.comentarios_admin = adopciones.COMENTARIO_RECHAZO_AUTOMATICO
        solicitud_pendiente.fecha_revision = utcnow()
        db.session.commit()
        assert solicitud_pendiente.revisado_por is None
        return solicitud_pendiente

    def test_la_ve_el_adoptante(self, client, auth_headers_adoptante, cerrada_por_migracion):
        for url in ['/solicitudes/mis-solicitudes', f'/solicitudes/detalle/{cerrada_por_migracion.id}']:
            response = client.get(url)
            assert response.status_code == 200, url
            assert 'Esta mascota ya ha encontrado un hogar' in response.data.decode(), url

    def test_la_ve_el_admin(self, client, auth_headers_admin, cerrada_por_migracion):
        for url in ['/solicitudes/admin', f'/solicitudes/admin/revisar/{cerrada_por_migracion.id}']:
            assert client.get(url).status_code == 200, url

    def test_la_devuelve_la_api(self, client, usuario_adoptante, cerrada_por_migracion):
        response = client.get('/api/solicitudes/mias',
                              headers={'Authorization': f'Bearer {generate_token(usuario_adoptante.id)}'})

        assert response.status_code == 200
        assert response.get_json()[0]['estado'] == 'rechazada'
        assert response.get_json()[0]['comentarios_admin'] == adopciones.COMENTARIO_RECHAZO_AUTOMATICO


class TestSolicitudesWebEnParalelo:

    def test_segundo_usuario_solicita_por_la_web(self, client, solicitud_pendiente, respuestas_validas):
        nuevo_usuario('otro@test.com')
        client.post('/auth/login', data={'email': 'otro@test.com', 'password': 'password123'})

        response = client.post(f'/solicitudes/nueva/{solicitud_pendiente.mascota_id}', data=respuestas_validas,
                               follow_redirects=True)

        assert 'Hemos recibido tu solicitud para adoptar a Cerbero.' in response.data.decode()
        assert Solicitud.query.filter_by(estado='pendiente').count() == 2
        assert db.session.get(Mascota, solicitud_pendiente.mascota_id).estado == 'disponible'


class TestEstadoManual:
    """Cambios de estado a mano del admin (ADR-0004): adopción fuera del portal y su vuelta atrás."""

    def test_adoptar_fuera_del_portal(self, app, usuario_admin, tres_pendientes):
        mascota = db.session.get(Mascota, tres_pendientes[0].mascota_id)

        adopciones.adoptar_fuera_del_portal(mascota, usuario_admin.id)

        assert mascota.estado == 'adoptado'
        for solicitud in tres_pendientes:
            assert solicitud.estado == 'rechazada'
            assert solicitud.comentarios_admin == adopciones.COMENTARIO_RECHAZO_AUTOMATICO
            assert solicitud.revisado_por == usuario_admin.id

    def test_adoptar_fuera_del_portal_ya_adoptada(self, app, usuario_admin, mascota_adoptada):
        with pytest.raises(adopciones.MascotaYaAdoptada):
            adopciones.adoptar_fuera_del_portal(mascota_adoptada, usuario_admin.id)

    @pytest.mark.parametrize('operacion', ['adoptar_fuera_del_portal', 'volver_a_disponible'])
    def test_mascota_borrada(self, app, usuario_admin, operacion):
        argumentos = (usuario_admin.id,) if operacion == 'adoptar_fuera_del_portal' else ()

        with pytest.raises(adopciones.MascotaNoEncontrada):
            getattr(adopciones, operacion)(SimpleNamespace(id=999), *argumentos)

    def test_volver_a_disponible_tras_adopcion_fuera_del_portal(self, app, usuario_admin, mascota_disponible):
        adopciones.adoptar_fuera_del_portal(mascota_disponible, usuario_admin.id)

        adopciones.volver_a_disponible(mascota_disponible)

        assert db.session.get(Mascota, mascota_disponible.id).estado == 'disponible'

    def test_volver_a_disponible_desde_disponible(self, app, mascota_disponible):
        with pytest.raises(adopciones.TransicionNoPermitida):
            adopciones.volver_a_disponible(mascota_disponible)

    def test_no_deshace_una_adopcion_del_portal(self, app, usuario_admin, solicitud_pendiente):
        adopciones.aprobar(solicitud_pendiente, usuario_admin.id, '')

        with pytest.raises(adopciones.TransicionNoPermitida):
            adopciones.volver_a_disponible(solicitud_pendiente.mascota)
        assert solicitud_pendiente.mascota.estado == 'adoptado'

    def test_puede_volver_a_disponible(self, app, usuario_admin, mascota_disponible, mascota_adoptada,
                                       solicitud_pendiente):
        assert adopciones.puede_volver_a_disponible(mascota_adoptada)
        assert not adopciones.puede_volver_a_disponible(mascota_disponible)

        adopciones.aprobar(solicitud_pendiente, usuario_admin.id, '')

        assert not adopciones.puede_volver_a_disponible(mascota_disponible)


class TestPendientesPorMascota:

    def test_cuenta_solo_las_pendientes(self, app, usuario_admin, tres_pendientes, mascota_adoptada):
        mascota_id = tres_pendientes[0].mascota_id
        adopciones.rechazar(tres_pendientes[0], usuario_admin.id, '')

        assert adopciones.pendientes_por_mascota([mascota_id, mascota_adoptada.id]) == {mascota_id: 2}

    def test_sin_mascotas_no_consulta(self, app, monkeypatch):
        monkeypatch.setattr(db.session, 'execute', None)

        assert adopciones.pendientes_por_mascota([]) == {}
