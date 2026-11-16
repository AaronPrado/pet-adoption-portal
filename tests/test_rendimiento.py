"""
Tests de rendimiento de consultas (N+1) y de la paginación de listados.
"""

import pytest
from sqlalchemy import event

from app import db
from app.models import Mascota, Solicitud, Usuario


class ContadorConsultas:
    def __init__(self, engine):
        self.engine = engine
        self.total = 0

    def _contar(self, *args, **kwargs):
        self.total += 1

    def __enter__(self):
        event.listen(self.engine, 'before_cursor_execute', self._contar)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, 'before_cursor_execute', self._contar)


def crear_solicitudes(n, prefijo='u'):
    for i in range(n):
        usuario = Usuario(email=f'{prefijo}{i}@test.com', nombre=f'Usuario {i}', password='password123')
        mascota = Mascota(nombre=f'Mascota {prefijo}{i}', especie='Perro', descripcion='Descripción larga')
        db.session.add_all([usuario, mascota])
        db.session.flush()
        db.session.add(Solicitud(usuario_id=usuario.id, mascota_id=mascota.id))
    db.session.commit()
    # Vaciar el mapa de identidad para que la vista tenga que cargar los objetos
    db.session.expunge_all()


def consultas_en(client, url):
    with ContadorConsultas(db.engine) as contador:
        assert client.get(url).status_code == 200
    return contador.total


class TestNMasUno:

    def test_admin_solicitudes_no_crece_con_las_filas(self, client, auth_headers_admin):
        crear_solicitudes(2)
        con_2 = consultas_en(client, '/solicitudes/admin')

        crear_solicitudes(8, prefijo='x')

        assert consultas_en(client, '/solicitudes/admin') == con_2

    def test_mis_solicitudes_no_crece_con_las_filas(self, client, usuario_adoptante):
        client.post('/auth/login', data={'email': 'adoptante@test.com', 'password': 'password123'})
        usuario_id = usuario_adoptante.id
        for i in range(5):
            mascota = Mascota(nombre=f'M{i}', especie='Perro', descripcion='Descripción larga')
            db.session.add(mascota)
            db.session.flush()
            db.session.add(Solicitud(usuario_id=usuario_id, mascota_id=mascota.id))
            db.session.commit()
            db.session.expunge_all()
            if i == 0:
                con_1 = consultas_en(client, '/solicitudes/mis-solicitudes')

        assert consultas_en(client, '/solicitudes/mis-solicitudes') == con_1

    @pytest.mark.parametrize('ruta', ['/solicitudes/admin/revisar/{}', '/solicitudes/detalle/{}'])
    def test_revision_y_detalle_no_crecen_con_las_pendientes(self, client, auth_headers_admin,
                                                            solicitud_pendiente, ruta):
        """Las otras pendientes de la mascota se cuentan con una consulta agregada."""
        url = ruta.format(solicitud_pendiente.id)
        mascota_id = solicitud_pendiente.mascota_id

        def otras(n, prefijo):
            for i in range(n):
                usuario = Usuario(email=f'{prefijo}{i}@test.com', nombre=f'Usuario {i}', password='password123')
                db.session.add(usuario)
                db.session.flush()
                db.session.add(Solicitud(usuario_id=usuario.id, mascota_id=mascota_id))
            db.session.commit()
            db.session.expunge_all()

        otras(1, 'a')
        con_1 = consultas_en(client, url)
        otras(5, 'b')

        assert consultas_en(client, url) == con_1
        # Usuario de la sesión, solicitud con mascota y solicitante, pendientes y revisor
        assert con_1 <= 4

    def test_revision_de_una_resuelta(self, client, auth_headers_admin, solicitud_pendiente, usuario_admin):
        solicitud_pendiente.registrar_revision('aprobada', usuario_admin.id)
        db.session.commit()
        url = f'/solicitudes/admin/revisar/{solicitud_pendiente.id}'
        db.session.expunge_all()

        # Sin recuento de pendientes; el revisor sí se carga
        assert consultas_en(client, url) <= 3

    def test_catalogo_cuenta_pendientes_con_una_consulta(self, client):
        crear_solicitudes(1)
        con_1 = consultas_en(client, '/mascotas/catalogo')

        crear_solicitudes(11, prefijo='x')

        html = client.get('/mascotas/catalogo').data.decode()
        assert html.count('Tiene solicitudes en curso') == 12
        assert consultas_en(client, '/mascotas/catalogo') == con_1


class TestPaginacion:

    @pytest.fixture
    def mascotas(self, app):
        db.session.add_all([
            Mascota(nombre=f'Mascota {i:02d}', especie='Gato' if i % 2 else 'Perro', descripcion='Descripción larga')
            for i in range(30)
        ])
        db.session.commit()

    def test_catalogo_muestra_12_por_pagina(self, client, mascotas):
        html = client.get('/mascotas/catalogo').data.decode()

        assert html.count('<h5 class="card-title">Mascota ') == 12
        assert 'aria-label="Paginación"' in html

    def test_catalogo_ultima_pagina(self, client, mascotas):
        html = client.get('/mascotas/catalogo?page=3').data.decode()
        assert html.count('<h5 class="card-title">Mascota ') == 6

    def test_enlaces_conservan_los_filtros(self, client, mascotas):
        for i in range(30, 45):
            db.session.add(Mascota(nombre=f'Gato {i}', especie='Gato', descripcion='Descripción larga'))
        db.session.commit()

        html = client.get('/mascotas/catalogo?especie=Gato').data.decode()

        assert 'especie=Gato&amp;page=2' in html

    def test_pagina_fuera_de_rango_no_da_error(self, client, mascotas):
        assert client.get('/mascotas/catalogo?page=99').status_code == 200

    def test_admin_mascotas_total_real(self, client, auth_headers_admin, mascotas):
        html = client.get('/mascotas/admin').data.decode()

        assert 'Total: 30 mascotas' in html
        assert html.count('title="Eliminar"') == 20

    def test_admin_solicitudes_paginado(self, client, auth_headers_admin):
        crear_solicitudes(25)

        html = client.get('/solicitudes/admin?page=2').data.decode()

        assert html.count('/solicitudes/admin/revisar/') == 5

    def test_sin_paginacion_si_cabe_en_una_pagina(self, client, mascota_disponible):
        assert 'aria-label="Paginación"' not in client.get('/mascotas/catalogo').data.decode()
