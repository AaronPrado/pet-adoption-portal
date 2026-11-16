"""
Tests de las ramas de validación y error del CRUD de mascotas (panel admin)
y de los filtros del catálogo que no cubre test_mascotas.py.
"""

import io
from html.parser import HTMLParser

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import adopciones, db
from app.models import Mascota, Solicitud, Usuario
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


class _CamposFormulario(HTMLParser):
    """Recoge lo que enviaría el navegador: inputs con valor, textareas y opciones seleccionadas."""

    def __init__(self):
        super().__init__()
        self.datos = {}
        self._textarea = None
        self._select = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        nombre = attrs.get('name')
        if tag == 'input' and nombre and attrs.get('type') not in ('file', 'checkbox', 'hidden'):
            self.datos[nombre] = attrs.get('value') or ''
        elif tag == 'textarea' and nombre:
            self._textarea = nombre
            self.datos[nombre] = ''
        elif tag == 'select' and nombre:
            self._select = nombre
            self.datos.setdefault(nombre, '')
        elif tag == 'option' and self._select and 'selected' in attrs:
            self.datos[self._select] = attrs.get('value') or ''

    def handle_endtag(self, tag):
        if tag == 'textarea':
            self._textarea = None
        elif tag == 'select':
            self._select = None

    def handle_data(self, data):
        if self._textarea:
            self.datos[self._textarea] += data


def campos_del_formulario(html):
    parser = _CamposFormulario()
    parser.feed(html)
    return parser.datos


@pytest.fixture
def mascota_sin_opcionales(app):
    """Mascota con raza, edad, sexo, tamaño y foto a NULL (p. ej., creada con S3 sin configurar)."""
    mascota = Mascota(nombre='Sinraza', especie='Gato', descripcion='Gato sin datos opcionales')
    db.session.add(mascota)
    db.session.commit()
    return mascota


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

    def test_get_con_opcionales_nulos_no_muestra_none(self, client, auth_headers_admin, mascota_sin_opcionales):
        """Regresión P-08: los campos a NULL no deben mostrarse como «None»."""
        html = client.get(self.url(mascota_sin_opcionales)).data.decode()

        assert 'None' not in html
        campos = campos_del_formulario(html)
        assert campos['raza'] == ''
        assert campos['foto_url'] == ''
        assert campos['edad_aprox'] == ''

    @pytest.mark.parametrize('vaciar_foto', [False, True], ids=['tal_cual', 'vaciando_foto'])
    def test_guardar_sin_cambios_con_opcionales_nulos(self, client, auth_headers_admin, mascota_sin_opcionales,
                                                      vaciar_foto):
        """Regresión P-08: reenviar el formulario guarda (302) y deja los opcionales a NULL, no «None»."""
        datos = campos_del_formulario(client.get(self.url(mascota_sin_opcionales)).data.decode())
        if vaciar_foto:
            datos['foto_url'] = ''
        response = client.post(self.url(mascota_sin_opcionales), data=datos)

        assert response.status_code == 302
        db.session.refresh(mascota_sin_opcionales)
        assert mascota_sin_opcionales.raza is None
        assert mascota_sin_opcionales.foto_url is None
        assert mascota_sin_opcionales.edad_aprox is None

    def test_get_muestra_edad_cero(self, client, auth_headers_admin, mascota_sin_opcionales):
        mascota_sin_opcionales.edad_aprox = 0
        db.session.commit()

        campos = campos_del_formulario(client.get(self.url(mascota_sin_opcionales)).data.decode())
        assert campos['edad_aprox'] == '0'

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

    @pytest.mark.parametrize('estado', ['adoptado', 'en_proceso', 'inventado'])
    def test_editar_no_cambia_el_estado(self, client, auth_headers_admin, mascota_disponible, s3_falso, estado):
        client.post(self.url(mascota_disponible),
                    data=datos_mascota(estado=estado, foto_url=mascota_disponible.foto_url))

        db.session.refresh(mascota_disponible)
        assert mascota_disponible.nombre == 'Rocky'
        assert mascota_disponible.estado == 'disponible'

    def test_editar_una_adoptada_la_deja_adoptada(self, client, auth_headers_admin, mascota_adoptada, s3_falso):
        client.post(self.url(mascota_adoptada), data=datos_mascota(foto_url=mascota_adoptada.foto_url))

        db.session.refresh(mascota_adoptada)
        assert mascota_adoptada.estado == 'adoptado'

    def test_el_formulario_no_tiene_selector_de_estado(self, client, auth_headers_admin, mascota_disponible):
        html = client.get(self.url(mascota_disponible)).data.decode()

        assert 'name="estado"' not in html
        assert 'en_proceso' not in html

    def test_error_de_base_de_datos_muestra_mensaje_generico(self, client, auth_headers_admin,
                                                            mascota_disponible, s3_falso, commit_falla):
        commit_falla()
        response = client.post(self.url(mascota_disponible),
                               data=datos_mascota(foto_url=mascota_disponible.foto_url))

        assert 'No se pudo actualizar la mascota' in response.data.decode()


class TestEliminarMascota:

    def test_bloquea_la_mascota_antes_de_comprobar(self, client, auth_headers_admin, mascota_disponible,
                                                  s3_falso, monkeypatch):
        bloqueadas = []
        original = rutas_mascotas.consulta_mascota_bloqueada

        def espiar(mascota_id):
            bloqueadas.append(mascota_id)
            return original(mascota_id)
        monkeypatch.setattr(rutas_mascotas, 'consulta_mascota_bloqueada', espiar)

        client.post(f'/mascotas/admin/eliminar/{mascota_disponible.id}')

        assert bloqueadas == [mascota_disponible.id]
        assert db.session.get(Mascota, mascota_disponible.id) is None

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


def nueva_pendiente(mascota, email):
    usuario = Usuario(email=email, nombre=email.split('@')[0], password='password123')
    db.session.add(usuario)
    db.session.flush()
    solicitud = Solicitud(usuario_id=usuario.id, mascota_id=mascota.id, cuestionario={'a': 'b'})
    db.session.add(solicitud)
    db.session.commit()
    return solicitud


class TestEstadoManual:
    """Acciones del admin: «Marcar como adoptada fuera del portal» y «Volver a disponible»."""

    def adoptar(self, client, mascota, **kwargs):
        return client.post(f'/mascotas/admin/adoptada-fuera/{mascota.id}', **kwargs)

    def volver(self, client, mascota, **kwargs):
        return client.post(f'/mascotas/admin/volver-a-disponible/{mascota.id}', **kwargs)

    def test_adoptar_fuera_rechaza_las_pendientes(self, client, auth_headers_admin, usuario_admin,
                                                  mascota_disponible):
        pendientes = [nueva_pendiente(mascota_disponible, f'p{i}@test.com') for i in range(2)]

        response = self.adoptar(client, mascota_disponible, follow_redirects=True)

        assert 'marcada como adoptada fuera del portal' in response.data.decode()
        db.session.expire_all()
        assert db.session.get(Mascota, mascota_disponible.id).estado == 'adoptado'
        for pendiente in pendientes:
            solicitud = db.session.get(Solicitud, pendiente.id)
            assert solicitud.estado == 'rechazada'
            assert solicitud.comentarios_admin == adopciones.COMENTARIO_RECHAZO_AUTOMATICO
            assert solicitud.revisado_por == usuario_admin.id

    def test_adoptar_fuera_redirige_al_formulario(self, client, auth_headers_admin, mascota_disponible):
        response = self.adoptar(client, mascota_disponible)

        assert response.status_code == 302
        assert response.headers['Location'].endswith(f'/mascotas/admin/editar/{mascota_disponible.id}')

    def test_adoptar_fuera_ya_adoptada(self, client, auth_headers_admin, mascota_adoptada):
        response = self.adoptar(client, mascota_adoptada, follow_redirects=True)

        assert adopciones.MascotaYaAdoptada.mensaje in response.data.decode()

    def test_volver_a_disponible_tras_adopcion_fuera(self, client, auth_headers_admin, mascota_disponible):
        self.adoptar(client, mascota_disponible)

        response = self.volver(client, mascota_disponible, follow_redirects=True)

        assert 'vuelve a estar disponible' in response.data.decode()
        db.session.expire_all()
        assert db.session.get(Mascota, mascota_disponible.id).estado == 'disponible'
        assert 'Cerbero' in client.get('/mascotas/catalogo').data.decode()

    def test_volver_a_disponible_tras_aprobar_no_se_permite(self, client, auth_headers_admin, usuario_admin,
                                                            solicitud_pendiente):
        mascota = solicitud_pendiente.mascota
        adopciones.aprobar(solicitud_pendiente, usuario_admin.id, '')

        response = self.volver(client, mascota, follow_redirects=True)

        assert adopciones.TransicionNoPermitida.mensaje in response.data.decode()
        db.session.expire_all()
        assert db.session.get(Mascota, mascota.id).estado == 'adoptado'

    @pytest.mark.parametrize('accion', ['adoptada-fuera', 'volver-a-disponible'])
    def test_mascota_inexistente_devuelve_404(self, client, auth_headers_admin, accion):
        assert client.post(f'/mascotas/admin/{accion}/999').status_code == 404

    @pytest.mark.parametrize('accion', ['adoptada-fuera', 'volver-a-disponible'])
    def test_borrada_mientras_tanto_devuelve_404(self, client, auth_headers_admin, mascota_disponible,
                                                 monkeypatch, accion):
        def fallar(*args):
            raise adopciones.MascotaNoEncontrada()
        monkeypatch.setattr(adopciones, 'adoptar_fuera_del_portal', fallar)
        monkeypatch.setattr(adopciones, 'volver_a_disponible', fallar)

        assert client.post(f'/mascotas/admin/{accion}/{mascota_disponible.id}').status_code == 404

    @pytest.mark.parametrize('accion', ['adoptada-fuera', 'volver-a-disponible'])
    def test_solo_admin(self, client, auth_headers_adoptante, mascota_disponible, accion):
        response = client.post(f'/mascotas/admin/{accion}/{mascota_disponible.id}')

        assert response.status_code == 302
        assert response.headers['Location'].endswith('/mascotas/catalogo')
        assert 'No tienes permisos' in client.get('/mascotas/catalogo').data.decode()
        db.session.expire_all()
        assert db.session.get(Mascota, mascota_disponible.id).estado == 'disponible'

    @pytest.mark.parametrize('accion', ['adoptada-fuera', 'volver-a-disponible'])
    def test_solo_post(self, client, auth_headers_admin, mascota_disponible, accion):
        assert client.get(f'/mascotas/admin/{accion}/{mascota_disponible.id}').status_code == 405

    def test_formulario_de_disponible_ofrece_adoptar_fuera(self, client, auth_headers_admin, mascota_disponible):
        nueva_pendiente(mascota_disponible, 'p@test.com')

        html = client.get(f'/mascotas/admin/editar/{mascota_disponible.id}').data.decode()

        assert f'action="/mascotas/admin/adoptada-fuera/{mascota_disponible.id}"' in html
        assert 'Marcar como adoptada fuera del portal' in html
        assert 'se rechazarán 1 solicitud' in html
        accion = html.split('/mascotas/admin/adoptada-fuera/', 1)[1].split('</form>', 1)[0]
        assert 'name="csrf_token"' in accion
        assert 'Volver a disponible' not in html

    def test_formulario_de_adoptada_fuera_ofrece_volver(self, client, auth_headers_admin, mascota_adoptada):
        html = client.get(f'/mascotas/admin/editar/{mascota_adoptada.id}').data.decode()

        assert f'action="/mascotas/admin/volver-a-disponible/{mascota_adoptada.id}"' in html
        assert 'Marcar como adoptada fuera del portal' not in html

    def test_formulario_de_adoptada_por_el_portal_sin_acciones(self, client, auth_headers_admin, usuario_admin,
                                                               solicitud_pendiente):
        mascota_id = solicitud_pendiente.mascota_id
        adopciones.aprobar(solicitud_pendiente, usuario_admin.id, '')

        html = client.get(f'/mascotas/admin/editar/{mascota_id}').data.decode()

        assert 'adoptada-fuera' not in html
        assert 'volver-a-disponible' not in html
        assert 'solicitud aprobada' in html

    def test_nueva_mascota_sin_acciones_de_estado(self, client, auth_headers_admin):
        html = client.get('/mascotas/admin/nueva').data.decode()

        assert 'adoptada-fuera' not in html


class TestListaSinEnProceso:

    def test_sin_filtro_ni_badge_en_proceso(self, client, auth_headers_admin, mascota_disponible):
        html = client.get('/mascotas/admin').data.decode()

        assert 'en_proceso' not in html
        assert 'En Proceso' not in html

    @pytest.mark.parametrize('estado', ['en_proceso', 'inventado'])
    def test_filtro_desconocido_se_ignora(self, client, auth_headers_admin, mascota_disponible,
                                          mascota_adoptada, estado):
        html = client.get(f'/mascotas/admin?estado={estado}').data.decode()

        assert 'Cerbero' in html
        assert 'Luna' in html
        todas = html.split('>\n                        Todas', 1)[0].rsplit('<a ', 1)[1]
        assert 'btn-primary' in todas
        assert f'estado={estado}' not in html

    def test_estado_heredado_no_se_muestra_como_adoptado(self, client, auth_headers_admin, mascota_disponible):
        mascota_disponible.estado = 'en_proceso'
        db.session.commit()

        html = client.get('/mascotas/admin').data.decode()

        assert 'Cerbero' in html
        assert 'badge bg-secondary">Adoptado' not in html
