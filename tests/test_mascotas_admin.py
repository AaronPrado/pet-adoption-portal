"""
Tests de las ramas de validación y error del CRUD de mascotas (panel admin)
y de los filtros del catálogo que no cubre test_mascotas.py.
"""

import io

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models import Mascota
from app.routes import mascotas as rutas_mascotas


def datos_mascota(**cambios):
    datos = {
        'nombre': 'Rocky',
        'especie': 'Perro',
        'descripcion': 'Perro tranquilo y cariñoso',
        'edad_aprox': '5',
    }
    datos.update(cambios)
    return datos


@pytest.fixture
def s3_falso(monkeypatch):
    """Sustituye la subida y el borrado en S3 de las rutas de mascotas."""
    llamadas = {'subidas': [], 'borrados': [], 'url': 'https://bucket/mascotas/nueva.png'}

    def subir(foto):
        llamadas['subidas'].append(foto.filename)
        return llamadas['url']

    monkeypatch.setattr(rutas_mascotas, 'upload_to_s3', subir)
    monkeypatch.setattr(rutas_mascotas, 'delete_from_s3', lambda url: llamadas['borrados'].append(url))
    return llamadas


@pytest.fixture
def commit_falla(monkeypatch):
    """Hace que el siguiente commit de la sesión falle."""
    def activar():
        def fallar():
            raise SQLAlchemyError('fallo simulado')
        monkeypatch.setattr(db.session, 'commit', fallar)
    return activar


VALIDACIONES = [
    ({'nombre': 'R'}, 'El nombre debe tener al menos 2 caracteres.'),
    ({'especie': ''}, 'La especie es obligatoria.'),
    ({'descripcion': 'Corta'}, 'La descripción debe tener al menos 10 caracteres.'),
    ({'edad_aprox': '31'}, 'La edad debe estar entre 0 y 30 años.'),
    ({'edad_aprox': '-1'}, 'La edad debe estar entre 0 y 30 años.'),
    ({'edad_aprox': 'abc'}, 'La edad debe ser un número válido.'),
    ({'foto_url': 'http://inseguro.com/foto.jpg'}, 'La URL de la foto debe empezar por https://'),
]


class TestCatalogo:

    def test_filtro_edad_no_numerico_se_ignora(self, client, mascota_disponible):
        response = client.get('/mascotas/catalogo?edad=abc')

        assert response.status_code == 200
        assert mascota_disponible.nombre in response.data.decode()


class TestAdminLista:

    @pytest.fixture
    def tres_mascotas(self, app):
        for nombre in ['Bruno', 'Atila', 'Coco']:
            db.session.add(Mascota(nombre=nombre, especie='Perro', descripcion='Descripción larga'))
        db.session.commit()

    def posiciones(self, html):
        return sorted(['Atila', 'Bruno', 'Coco'], key=html.index)

    def test_ordenar_por_nombre_ascendente(self, client, auth_headers_admin, tres_mascotas):
        html = client.get('/mascotas/admin?orden=nombre&dir=asc').data.decode()
        assert self.posiciones(html) == ['Atila', 'Bruno', 'Coco']

    def test_ordenar_por_nombre_descendente(self, client, auth_headers_admin, tres_mascotas):
        html = client.get('/mascotas/admin?orden=nombre&dir=desc').data.decode()
        assert self.posiciones(html) == ['Coco', 'Bruno', 'Atila']

    def test_campo_de_orden_desconocido_usa_id(self, client, auth_headers_admin, tres_mascotas):
        html = client.get('/mascotas/admin?orden=password_hash').data.decode()
        assert self.posiciones(html) == ['Bruno', 'Atila', 'Coco']


class TestCrearMascota:

    @pytest.mark.parametrize('cambios, mensaje', VALIDACIONES)
    def test_datos_invalidos_no_crean_mascota(self, client, auth_headers_admin, cambios, mensaje):
        response = client.post('/mascotas/admin/nueva', data=datos_mascota(**cambios))

        assert response.status_code == 200
        assert mensaje in response.data.decode()
        assert Mascota.query.count() == 0

    def test_get_muestra_formulario(self, client, auth_headers_admin):
        response = client.get('/mascotas/admin/nueva')
        assert response.status_code == 200
        assert 'name="nombre"' in response.data.decode()

    def test_foto_subida_a_s3(self, client, auth_headers_admin, s3_falso):
        datos = datos_mascota(foto=(io.BytesIO(b'png'), 'rocky.png'))
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        assert response.status_code == 302
        assert s3_falso['subidas'] == ['rocky.png']
        assert Mascota.query.one().foto_url == s3_falso['url']

    def test_foto_rechazada_vuelve_al_formulario(self, client, auth_headers_admin, s3_falso):
        s3_falso['url'] = None
        datos = datos_mascota(foto=(io.BytesIO(b'no es imagen'), 'rocky.png'))
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/mascotas/admin/nueva')
        assert Mascota.query.count() == 0

    def test_error_de_base_de_datos_muestra_mensaje_generico(self, client, auth_headers_admin, commit_falla):
        commit_falla()
        response = client.post('/mascotas/admin/nueva', data=datos_mascota())

        html = response.data.decode()
        assert 'No se pudo crear la mascota' in html
        assert 'fallo simulado' not in html


class TestEditarMascota:

    def url(self, mascota):
        return f'/mascotas/admin/editar/{mascota.id}'

    @pytest.mark.parametrize('cambios, mensaje', VALIDACIONES)
    def test_datos_invalidos_no_modifican(self, client, auth_headers_admin, mascota_disponible, cambios, mensaje):
        response = client.post(self.url(mascota_disponible), data=datos_mascota(**cambios))

        assert mensaje in response.data.decode()
        db.session.refresh(mascota_disponible)
        assert mascota_disponible.nombre == 'Cerbero'

    def test_get_muestra_datos_actuales(self, client, auth_headers_admin, mascota_disponible):
        response = client.get(self.url(mascota_disponible))
        assert 'value="Cerbero"' in response.data.decode()

    def test_nueva_foto_borra_la_anterior(self, client, auth_headers_admin, mascota_disponible, s3_falso):
        foto_anterior = mascota_disponible.foto_url
        datos = datos_mascota(foto=(io.BytesIO(b'png'), 'nueva.png'))
        client.post(self.url(mascota_disponible), data=datos, content_type='multipart/form-data')

        db.session.refresh(mascota_disponible)
        assert mascota_disponible.foto_url == s3_falso['url']
        assert s3_falso['borrados'] == [foto_anterior]

    def test_foto_rechazada_conserva_la_anterior(self, client, auth_headers_admin, mascota_disponible, s3_falso):
        foto_anterior = mascota_disponible.foto_url
        s3_falso['url'] = None
        datos = datos_mascota(foto=(io.BytesIO(b'x'), 'nueva.png'))
        response = client.post(self.url(mascota_disponible), data=datos, content_type='multipart/form-data')

        assert response.status_code == 302
        db.session.refresh(mascota_disponible)
        assert mascota_disponible.foto_url == foto_anterior
        assert s3_falso['borrados'] == []

    def test_cambiar_url_borra_la_foto_anterior(self, client, auth_headers_admin, mascota_disponible, s3_falso):
        foto_anterior = mascota_disponible.foto_url
        client.post(self.url(mascota_disponible),
                    data=datos_mascota(foto_url='https://ejemplo.com/otra.jpg'))

        assert s3_falso['borrados'] == [foto_anterior]

    def test_misma_url_no_borra_nada(self, client, auth_headers_admin, mascota_disponible, s3_falso):
        client.post(self.url(mascota_disponible),
                    data=datos_mascota(foto_url=mascota_disponible.foto_url))

        assert s3_falso['borrados'] == []

    @pytest.mark.parametrize('estado, esperado', [
        ('adoptado', 'adoptado'),
        ('en_proceso', 'en_proceso'),
        ('inventado', 'disponible'),
    ])
    def test_estado_solo_admite_valores_validos(self, client, auth_headers_admin, mascota_disponible,
                                                 s3_falso, estado, esperado):
        client.post(self.url(mascota_disponible),
                    data=datos_mascota(estado=estado, foto_url=mascota_disponible.foto_url))

        db.session.refresh(mascota_disponible)
        assert mascota_disponible.estado == esperado

    def test_error_de_base_de_datos_muestra_mensaje_generico(self, client, auth_headers_admin,
                                                            mascota_disponible, s3_falso, commit_falla):
        commit_falla()
        response = client.post(self.url(mascota_disponible),
                               data=datos_mascota(foto_url=mascota_disponible.foto_url))

        assert 'No se pudo actualizar la mascota' in response.data.decode()


class TestEliminarMascota:

    def test_no_elimina_si_tiene_solicitudes(self, client, auth_headers_admin, solicitud_pendiente):
        mascota_id = solicitud_pendiente.mascota_id
        response = client.post(f'/mascotas/admin/eliminar/{mascota_id}', follow_redirects=True)

        assert 'tiene solicitudes de adopción asociadas' in response.data.decode()
        assert db.session.get(Mascota, mascota_id) is not None

    def test_elimina_foto_de_s3(self, client, auth_headers_admin, mascota_disponible, s3_falso):
        foto = mascota_disponible.foto_url
        client.post(f'/mascotas/admin/eliminar/{mascota_disponible.id}')

        assert s3_falso['borrados'] == [foto]

    def test_error_de_base_de_datos_muestra_mensaje_generico(self, client, auth_headers_admin,
                                                            mascota_disponible, s3_falso, commit_falla):
        commit_falla()
        response = client.post(f'/mascotas/admin/eliminar/{mascota_disponible.id}', follow_redirects=True)

        assert 'No se pudo eliminar la mascota' in response.data.decode()

    def test_mascota_inexistente_devuelve_404(self, client, auth_headers_admin):
        assert client.post('/mascotas/admin/eliminar/999').status_code == 404
