"""
Tests de las ramas de validación y error del CRUD de mascotas (panel admin)
y de los filtros del catálogo que no cubre test_mascotas.py.
"""

import io
import logging
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.datastructures import FileStorage

from app import adopciones, db, fotos
from app.fotos import s3 as fotos_s3
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
    """Sustituye el guardado y el borrado de fotos de las rutas de mascotas."""
    llamadas = {'subidas': [], 'borrados': [], 'url': 'https://bucket/mascotas/nueva.png'}

    def subir(foto):
        llamadas['subidas'].append(foto.filename)
        if llamadas['url'] is None:
            raise fotos.ErrorAlmacenamiento(fotos.MENSAJE_FORMATO)
        return llamadas['url']

    monkeypatch.setattr(fotos, 'guardar_foto', subir)
    monkeypatch.setattr(fotos, 'borrar_foto', lambda url: llamadas['borrados'].append(url))
    return llamadas


def png():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')
    return buffer.getvalue()


def foto_png(nombre='rocky.png'):
    return (io.BytesIO(png()), nombre)


def fotos_guardadas(app):
    """URLs de las fotos que hay en el directorio del backend local."""
    directorio = Path(app.config['FOTOS_DIR'])
    return {'/fotos/' + f.name for f in directorio.iterdir()} if directorio.exists() else set()


@pytest.fixture
def foto_local(app):
    """Guarda una foto en el backend local (tmp_path) y devuelve su foto_url."""
    return fotos.guardar_foto(FileStorage(stream=io.BytesIO(png()), filename='actual.png'))


@pytest.fixture
def con_foto_local(mascota_disponible, foto_local):
    mascota_disponible.foto_url = foto_local
    db.session.commit()
    return mascota_disponible


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
    ({'nombre': 'R'}, 'nombre', 'El nombre debe tener al menos 2 caracteres.'),
    ({'nombre': '   '}, 'nombre', 'El nombre debe tener al menos 2 caracteres.'),
    ({'especie': ''}, 'especie', 'La especie es obligatoria.'),
    # Se valida la especie ya normalizada (Mascota.normalizar_especie): el
    # validador del modelo lanzaría ValueError y acabaría en un 500
    ({'especie': '​​'}, 'especie', 'La especie es obligatoria.'),
    ({'especie': 'P​'}, 'especie', 'La especie es obligatoria.'),
    ({'especie': 'ß' * 50}, 'especie', 'La especie no puede superar 50 caracteres.'),
    ({'descripcion': 'Corta'}, 'descripcion', 'La descripción debe tener al menos 10 caracteres.'),
    ({'edad_aprox': '31'}, 'edad_aprox', 'La edad debe estar entre 0 y 30 años.'),
    ({'edad_aprox': '-1'}, 'edad_aprox', 'La edad debe estar entre 0 y 30 años.'),
    ({'edad_aprox': 'abc'}, 'edad_aprox', 'La edad debe ser un número válido.'),
    ({'foto_url': 'http://inseguro.com/foto.jpg'}, 'foto_url', 'La URL de la foto debe empezar por https://'),
    # Una ruta del backend local solo vale si es la foto que ya tiene la mascota
    ({'foto_url': '/fotos/' + 'a' * 32 + '.png'}, 'foto_url', 'La URL de la foto debe empezar por https://'),
]

# Ficha completa distinta de la de mascota_disponible, para comprobar que tras
# un error se vuelve a mostrar lo enviado y no lo guardado
FICHA_ENVIADA = {
    'nombre': 'Rocky',
    'especie': 'Gato',
    'raza': 'Siamés',
    'edad_aprox': '7',
    'sexo': 'Hembra',
    'tamano': 'Pequeño',
    'descripcion': 'Gata tranquila que busca un hogar',
    'foto_url': 'https://ejemplo.com/rocky.jpg',
    'vacunado': 'on',
    'esterilizado': 'on',
}

CASILLAS = ('vacunado', 'esterilizado')


def casillas_marcadas(html):
    """Nombres de los checkbox marcados en el HTML."""
    return set(re.findall(r'<input[^>]*type="checkbox"[^>]*name="(\w+)"[^>]*\bchecked\b', html))


def campos_invalidos(html):
    """Campos marcados como no válidos → ids de los elementos que los describen."""
    return dict(re.findall(r'name="(\w+)"[^>]*aria-invalid="true" aria-describedby="([\w -]+)"', html))


def assert_conserva(html, enviados):
    """El formulario vuelve a mostrar los valores enviados (sin espacios alrededor)."""
    campos = campos_del_formulario(html)
    for nombre, valor in enviados.items():
        if nombre not in CASILLAS:
            assert campos[nombre] == valor.strip(), nombre
    assert casillas_marcadas(html) == {c for c in CASILLAS if c in enviados}


def assert_error_en_campo(html, campo, mensaje):
    """El error aparece junto a su campo y el campo apunta a él."""
    assert f'<div id="{campo}-error" class="invalid-feedback">{mensaje}</div>' in html
    invalidos = campos_invalidos(html)
    assert list(invalidos) == [campo]
    assert f'{campo}-error' in invalidos[campo].split()


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

    @pytest.mark.parametrize('cambios, campo, mensaje', VALIDACIONES)
    def test_datos_invalidos_no_crean_mascota(self, client, auth_headers_admin, cambios, campo, mensaje):
        """Regresión P-02: cada validación responde 400 con el error junto a su campo y lo escrito."""
        enviados = {**FICHA_ENVIADA, **cambios}
        response = client.post('/mascotas/admin/nueva', data=enviados)

        html = response.data.decode()
        assert response.status_code == 400
        assert_error_en_campo(html, campo, mensaje)
        assert_conserva(html, enviados)
        assert Mascota.query.count() == 0

    def test_conserva_casillas_desmarcadas_y_opcionales_vacios(self, client, auth_headers_admin):
        enviados = datos_mascota(nombre='R', raza='', sexo='', tamano='', foto_url='')
        html = client.post('/mascotas/admin/nueva', data=enviados).data.decode()

        assert_conserva(html, enviados)

    def test_muestra_todos_los_errores_a_la_vez(self, client, auth_headers_admin):
        response = client.post('/mascotas/admin/nueva',
                               data=datos_mascota(nombre='R', especie='', edad_aprox='abc'))

        html = response.data.decode()
        assert response.status_code == 400
        assert set(campos_invalidos(html)) == {'nombre', 'especie', 'edad_aprox'}
        assert 'Revisa los campos marcados.' in html

    def test_con_errores_no_sube_la_foto(self, client, auth_headers_admin, s3_falso):
        datos = datos_mascota(nombre='R', foto=(io.BytesIO(b'png'), 'rocky.png'))
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        assert response.status_code == 400
        assert s3_falso['subidas'] == []

    def test_con_archivo_no_se_valida_la_url(self, client, auth_headers_admin, s3_falso):
        """El archivo tiene prioridad sobre la URL: una URL no válida no impide subirlo."""
        datos = datos_mascota(foto_url='http://inseguro.com/x.jpg', foto=(io.BytesIO(b'png'), 'rocky.png'))
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        assert response.status_code == 302
        assert Mascota.query.one().foto_url == s3_falso['url']

    def test_guarda_la_especie_normalizada(self, client, auth_headers_admin):
        response = client.post('/mascotas/admin/nueva', data=datos_mascota(especie='  gATO​  común '))

        assert response.status_code == 302
        assert Mascota.query.one().especie == 'Gato común'

    def test_get_sin_errores_ni_valores(self, client, auth_headers_admin):
        html = client.get('/mascotas/admin/nueva').data.decode()

        assert 'aria-invalid' not in html
        assert 'is-invalid' not in html
        assert set(campos_del_formulario(html).values()) == {''}
        assert casillas_marcadas(html) == set()
        assert 'foto-aviso' not in html

    def test_error_con_archivo_pide_volver_a_elegirlo(self, client, auth_headers_admin, s3_falso):
        """El navegador no conserva el archivo: se avisa junto al campo de foto."""
        datos = datos_mascota(nombre='R', foto=(io.BytesIO(b'png'), 'rocky.png'))
        html = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data').data.decode()

        assert '<div id="foto-aviso" class="form-text">Vuelve a seleccionar la foto' in html
        assert re.search(r'name="foto"[^>]*aria-describedby="foto-aviso"', html)

    def test_foto_rechazada_describe_error_y_aviso(self, client, auth_headers_admin, s3_falso):
        s3_falso['url'] = None
        datos = datos_mascota(foto=(io.BytesIO(b'x'), 'rocky.png'))
        html = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data').data.decode()

        assert re.search(r'name="foto"[^>]*aria-invalid="true" aria-describedby="foto-error foto-aviso"', html)

    def test_error_sin_archivo_no_avisa_de_la_foto(self, client, auth_headers_admin):
        html = client.post('/mascotas/admin/nueva', data=datos_mascota(nombre='R')).data.decode()

        assert 'foto-aviso' not in html

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

    def test_foto_rechazada_conserva_los_datos(self, client, auth_headers_admin, s3_falso):
        """Regresión P-02: una imagen no válida ya no redirige ni vacía el formulario."""
        s3_falso['url'] = None
        datos = {**FICHA_ENVIADA, 'foto': (io.BytesIO(b'no es imagen'), 'rocky.png')}
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        html = response.data.decode()
        assert response.status_code == 400
        assert_error_en_campo(html, 'foto', 'Formato de imagen no permitido')
        assert_conserva(html, FICHA_ENVIADA)
        assert Mascota.query.count() == 0

    @pytest.mark.parametrize('nombre, contenido', [
        ('rocky.txt', b'\x89PNG\r\n\x1a\n'),
        ('rocky.png', b'<html></html>'),
    ], ids=['extension', 'contenido'])
    def test_foto_no_valida_conserva_los_datos(self, client, auth_headers_admin, nombre, contenido):
        """Con la validación real de app/fotos, que rechaza antes de llamar a S3."""
        datos = {**FICHA_ENVIADA, 'foto': (io.BytesIO(contenido), nombre)}
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        html = response.data.decode()
        assert response.status_code == 400
        assert_error_en_campo(html, 'foto', 'Formato de imagen no permitido')
        assert_conserva(html, FICHA_ENVIADA)

    def test_error_de_base_de_datos_muestra_mensaje_generico(self, client, auth_headers_admin, commit_falla):
        commit_falla()
        response = client.post('/mascotas/admin/nueva', data=FICHA_ENVIADA)

        html = response.data.decode()
        assert 'No se pudo crear la mascota' in html
        assert 'fallo simulado' not in html
        assert_conserva(html, FICHA_ENVIADA)

    def test_error_de_base_de_datos_borra_la_foto_subida(self, app, client, auth_headers_admin, commit_falla):
        """Sin mascota guardada, la foto recién subida no debe quedar huérfana."""
        commit_falla()
        datos = {**FICHA_ENVIADA, 'foto': foto_png()}
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        assert 'No se pudo crear la mascota' in response.data.decode()
        assert fotos_guardadas(app) == set()


class TestSinBackendDeFotos:
    """P-09: sin almacenamiento configurado, un archivo da un error del campo y nunca un 500."""

    @pytest.fixture(params=[{'FOTOS_BACKEND': ''}, {'FOTOS_BACKEND': 's3', 'AWS_S3_BUCKET': None}],
                    ids=['sin_backend', 's3_sin_bucket'])
    def sin_backend(self, app, request):
        app.config.update(request.param)

    def test_post_con_archivo_da_error_de_campo_y_conserva(self, client, auth_headers_admin, sin_backend):
        datos = {**FICHA_ENVIADA, 'foto': foto_png()}
        response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        html = response.data.decode()
        assert response.status_code == 400
        assert_error_en_campo(html, 'foto', fotos.MENSAJE_NO_DISPONIBLE)
        assert 'Quita el archivo y pega el enlace https://' in html
        assert_conserva(html, FICHA_ENVIADA)
        assert Mascota.query.count() == 0

    def test_con_url_se_crea(self, client, auth_headers_admin, sin_backend):
        response = client.post('/mascotas/admin/nueva', data=FICHA_ENVIADA)

        assert response.status_code == 302
        assert Mascota.query.one().foto_url == FICHA_ENVIADA['foto_url']


class TestErrorDeS3:

    @pytest.fixture
    def s3_que_falla(self, app, monkeypatch):
        app.config.update(FOTOS_BACKEND='s3', AWS_S3_BUCKET='bucket-test', AWS_S3_ENDPOINT_URL=None)

        class Cliente:
            def upload_fileobj(self, *args, **kwargs):
                raise ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'denegado'}}, 'PutObject')
        monkeypatch.setattr(fotos_s3.boto3, 'client', lambda *args, **kwargs: Cliente())

    def test_client_error_da_error_de_campo_y_se_registra(self, client, auth_headers_admin, s3_que_falla, caplog):
        datos = {**FICHA_ENVIADA, 'foto': foto_png()}
        with caplog.at_level(logging.ERROR):
            response = client.post('/mascotas/admin/nueva', data=datos, content_type='multipart/form-data')

        html = response.data.decode()
        assert response.status_code == 400
        assert_error_en_campo(html, 'foto', fotos.MENSAJE_FALLO)
        assert 'AccessDenied' not in html
        assert_conserva(html, FICHA_ENVIADA)
        assert 'AccessDenied' in caplog.text
        assert Mascota.query.count() == 0


class TestEditarMascota:

    def url(self, mascota):
        return f'/mascotas/admin/editar/{mascota.id}'

    @pytest.mark.parametrize('cambios, campo, mensaje', VALIDACIONES)
    def test_datos_invalidos_no_modifican(self, client, auth_headers_admin, mascota_disponible,
                                          cambios, campo, mensaje):
        """Regresión P-02: tras un error se muestra lo enviado, no lo guardado, con 400."""
        enviados = {**FICHA_ENVIADA, **cambios}
        response = client.post(self.url(mascota_disponible), data=enviados)

        html = response.data.decode()
        assert response.status_code == 400
        assert_error_en_campo(html, campo, mensaje)
        assert_conserva(html, enviados)
        db.session.refresh(mascota_disponible)
        assert mascota_disponible.nombre == 'Cerbero'

    def test_error_mantiene_las_acciones_de_estado(self, client, auth_headers_admin, mascota_disponible):
        html = client.post(self.url(mascota_disponible), data=datos_mascota(nombre='R')).data.decode()

        assert f'/mascotas/admin/adoptada-fuera/{mascota_disponible.id}' in html

    def test_casillas_desmarcadas_con_error_siguen_desmarcadas(self, client, auth_headers_admin,
                                                             mascota_disponible):
        mascota_disponible.vacunado = True
        mascota_disponible.esterilizado = True
        db.session.commit()

        html = client.post(self.url(mascota_disponible), data=datos_mascota(nombre='R')).data.decode()

        assert casillas_marcadas(html) == set()

    def test_get_marca_las_casillas_guardadas(self, client, auth_headers_admin, mascota_disponible):
        mascota_disponible.vacunado = True
        mascota_disponible.esterilizado = False
        db.session.commit()

        html = client.get(self.url(mascota_disponible)).data.decode()

        assert casillas_marcadas(html) == {'vacunado'}
        assert 'aria-invalid' not in html

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

    def test_nueva_foto_borra_la_anterior(self, app, client, auth_headers_admin, con_foto_local):
        foto_anterior = con_foto_local.foto_url
        datos = datos_mascota(foto=foto_png('nueva.png'))
        response = client.post(self.url(con_foto_local), data=datos, content_type='multipart/form-data')

        assert response.status_code == 302
        db.session.refresh(con_foto_local)
        assert con_foto_local.foto_url != foto_anterior
        assert fotos_guardadas(app) == {con_foto_local.foto_url}

    def test_foto_rechazada_conserva_la_anterior(self, app, client, auth_headers_admin, con_foto_local):
        """Regresión P-02: no redirige; muestra lo editado y no toca la foto guardada."""
        foto_anterior = con_foto_local.foto_url
        enviados = {**FICHA_ENVIADA, 'foto_url': foto_anterior}
        datos = {**enviados, 'foto': (io.BytesIO(b'x'), 'nueva.png')}
        response = client.post(self.url(con_foto_local), data=datos, content_type='multipart/form-data')

        html = response.data.decode()
        assert response.status_code == 400
        assert_error_en_campo(html, 'foto', fotos.MENSAJE_FORMATO)
        assert_conserva(html, enviados)
        db.session.refresh(con_foto_local)
        assert con_foto_local.foto_url == foto_anterior
        assert con_foto_local.nombre == 'Cerbero'
        assert fotos_guardadas(app) == {foto_anterior}

    def test_cambiar_url_borra_la_foto_anterior(self, app, client, auth_headers_admin, con_foto_local):
        client.post(self.url(con_foto_local), data=datos_mascota(foto_url='https://ejemplo.com/otra.jpg'))

        db.session.refresh(con_foto_local)
        assert con_foto_local.foto_url == 'https://ejemplo.com/otra.jpg'
        assert fotos_guardadas(app) == set()

    def test_vaciar_la_url_borra_la_foto(self, app, client, auth_headers_admin, con_foto_local):
        client.post(self.url(con_foto_local), data=datos_mascota(foto_url=''))

        db.session.refresh(con_foto_local)
        assert con_foto_local.foto_url is None
        assert fotos_guardadas(app) == set()

    def test_reenviar_sin_cambios_conserva_la_foto_local(self, app, client, auth_headers_admin, con_foto_local):
        """La ruta /fotos/<clave> no es https://, pero es la foto actual: se acepta tal cual."""
        foto = con_foto_local.foto_url
        datos = campos_del_formulario(client.get(self.url(con_foto_local)).data.decode())
        assert datos['foto_url'] == foto
        response = client.post(self.url(con_foto_local), data=datos)

        assert response.status_code == 302
        db.session.refresh(con_foto_local)
        assert con_foto_local.foto_url == foto
        assert fotos_guardadas(app) == {foto}

    def test_url_http_heredada_se_vuelve_a_validar(self, client, auth_headers_admin, mascota_disponible):
        """Solo se acepta sin validar la foto propia actual, no una URL externa no segura."""
        mascota_disponible.foto_url = 'http://antigua.ejemplo.com/foto.jpg'
        db.session.commit()

        response = client.post(self.url(mascota_disponible),
                               data={**FICHA_ENVIADA, 'foto_url': 'http://antigua.ejemplo.com/foto.jpg'})

        assert response.status_code == 400
        assert_error_en_campo(response.data.decode(), 'foto_url', 'La URL de la foto debe empezar por https://')

    def test_foto_compartida_no_se_borra(self, app, client, auth_headers_admin, con_foto_local):
        """Otra ficha con la misma foto_url la sigue usando."""
        foto = con_foto_local.foto_url
        db.session.add(Mascota(nombre='Gemelo', especie='Perro', descripcion='Comparte la foto', foto_url=foto))
        db.session.commit()

        client.post(self.url(con_foto_local), data=datos_mascota(foto_url='https://ejemplo.com/otra.jpg'))

        assert fotos_guardadas(app) == {foto}

    def test_url_externa_anterior_no_se_toca(self, app, client, auth_headers_admin, mascota_disponible):
        response = client.post(self.url(mascota_disponible), data=datos_mascota(foto=foto_png()),
                               content_type='multipart/form-data')

        assert response.status_code == 302
        db.session.refresh(mascota_disponible)
        assert fotos_guardadas(app) == {mascota_disponible.foto_url}

    def test_error_de_base_de_datos_con_foto_nueva(self, app, client, auth_headers_admin, con_foto_local,
                                                   commit_falla):
        """Si el commit falla, la mascota conserva su foto y la nueva no queda huérfana."""
        foto_anterior = con_foto_local.foto_url
        commit_falla()
        datos = {**FICHA_ENVIADA, 'foto': foto_png('nueva.png')}
        response = client.post(self.url(con_foto_local), data=datos, content_type='multipart/form-data')

        assert 'No se pudo actualizar la mascota' in response.data.decode()
        assert fotos_guardadas(app) == {foto_anterior}
        assert db.session.get(Mascota, con_foto_local.id).foto_url == foto_anterior

    @pytest.mark.parametrize('falla', ['consulta', 'borrado'])
    def test_fallo_al_borrar_la_anterior_no_da_500(self, app, client, auth_headers_admin, con_foto_local,
                                                   monkeypatch, caplog, falla):
        """El cambio ya está guardado: el fallo se registra y la foto queda huérfana."""
        foto_anterior = con_foto_local.foto_url

        def fallar(*args, **kwargs):
            raise RuntimeError('fallo simulado')
        if falla == 'consulta':
            monkeypatch.setattr(db.session, 'scalar', fallar)
        else:
            monkeypatch.setattr(fotos, 'borrar_foto', fallar)

        with caplog.at_level(logging.ERROR):
            response = client.post(self.url(con_foto_local), data=datos_mascota(foto_url='https://ejemplo.com/b.jpg'))

        assert response.status_code == 302
        assert 'No se pudo borrar la foto anterior' in caplog.text
        assert db.session.get(Mascota, con_foto_local.id).foto_url == 'https://ejemplo.com/b.jpg'
        assert fotos_guardadas(app) == {foto_anterior}

    def test_misma_url_no_borra_nada(self, app, client, auth_headers_admin, con_foto_local):
        client.post(self.url(con_foto_local), data=datos_mascota(foto_url=con_foto_local.foto_url))

        assert fotos_guardadas(app) == {con_foto_local.foto_url}

    @pytest.mark.parametrize('estado', ['adoptado', 'en_proceso', 'inventado'])
    def test_editar_no_cambia_el_estado(self, client, auth_headers_admin, mascota_disponible, estado):
        client.post(self.url(mascota_disponible),
                    data=datos_mascota(estado=estado, foto_url=mascota_disponible.foto_url))

        db.session.refresh(mascota_disponible)
        assert mascota_disponible.nombre == 'Rocky'
        assert mascota_disponible.estado == 'disponible'

    def test_editar_una_adoptada_la_deja_adoptada(self, client, auth_headers_admin, mascota_adoptada):
        client.post(self.url(mascota_adoptada), data=datos_mascota(foto_url=mascota_adoptada.foto_url))

        db.session.refresh(mascota_adoptada)
        assert mascota_adoptada.estado == 'adoptado'

    def test_el_formulario_no_tiene_selector_de_estado(self, client, auth_headers_admin, mascota_disponible):
        html = client.get(self.url(mascota_disponible)).data.decode()

        assert 'name="estado"' not in html
        assert 'en_proceso' not in html

    def test_error_de_base_de_datos_muestra_mensaje_generico(self, client, auth_headers_admin,
                                                            mascota_disponible, commit_falla):
        commit_falla()
        enviados = {**FICHA_ENVIADA, 'foto_url': mascota_disponible.foto_url}
        response = client.post(self.url(mascota_disponible), data=enviados)

        html = response.data.decode()
        assert 'No se pudo actualizar la mascota' in html
        assert_conserva(html, enviados)


class TestEliminarMascota:

    def test_bloquea_la_mascota_antes_de_comprobar(self, client, auth_headers_admin, mascota_disponible,
                                                  monkeypatch):
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

    def test_elimina_la_foto(self, app, client, auth_headers_admin, con_foto_local):
        client.post(f'/mascotas/admin/eliminar/{con_foto_local.id}')

        assert db.session.get(Mascota, con_foto_local.id) is None
        assert fotos_guardadas(app) == set()

    def test_foto_compartida_no_se_borra(self, app, client, auth_headers_admin, con_foto_local):
        foto = con_foto_local.foto_url
        db.session.add(Mascota(nombre='Gemelo', especie='Perro', descripcion='Comparte la foto', foto_url=foto))
        db.session.commit()

        client.post(f'/mascotas/admin/eliminar/{con_foto_local.id}')

        assert fotos_guardadas(app) == {foto}

    def test_error_de_base_de_datos_conserva_la_foto(self, app, client, auth_headers_admin,
                                                    con_foto_local, commit_falla):
        """La foto se borra después del commit: si falla, la mascota sigue con su foto."""
        foto = con_foto_local.foto_url
        commit_falla()
        response = client.post(f'/mascotas/admin/eliminar/{con_foto_local.id}', follow_redirects=True)

        assert 'No se pudo eliminar la mascota' in response.data.decode()
        assert fotos_guardadas(app) == {foto}

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


class TestLimiteDeFotoEnElNavegador:
    """app.js usa data-max-bytes para no enviar fotos que acabarían en 413."""

    @pytest.fixture
    def urls(self, mascota_disponible):
        return ['/mascotas/admin/nueva', f'/mascotas/admin/editar/{mascota_disponible.id}']

    def test_formulario_incluye_limite_con_margen(self, app, client, auth_headers_admin, urls):
        esperado = app.config['MAX_CONTENT_LENGTH'] - 64 * 1024
        for url in urls:
            html = client.get(url).data.decode()
            assert re.search(rf'name="foto"[^>]*data-max-bytes="{esperado}"', html), url
            assert ('data-mensaje-tamano="La foto ocupa más de 5 MB. Elige otra más pequeña '
                    'o quita el archivo para usar una URL."') in html

    def test_limite_sigue_a_la_configuracion(self, app, client, auth_headers_admin, urls):
        app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
        html = client.get(urls[0]).data.decode()

        assert f'data-max-bytes="{2 * 1024 * 1024 - 64 * 1024}"' in html
        assert 'La foto ocupa más de 2 MB.' in html
