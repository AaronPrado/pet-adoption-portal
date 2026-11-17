"""
Tests del almacenamiento de fotos (app/fotos): backend local con tmp_path,
backend S3 con un cliente boto3 falso y la ruta GET /fotos/<clave>.
"""

import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import fotos
from app.fotos import s3 as fotos_s3

BASE_S3 = 'https://bucket-test.s3.eu-west-1.amazonaws.com/mascotas/'
CLAVE = 'a' * 32 + '.png'


def archivo(contenido, nombre='foto.png', content_type='image/png'):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre, content_type=content_type)


def png_valido():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture
def directorio(app, tmp_path):
    """Backend local en un directorio temporal propio del test."""
    ruta = tmp_path / 'fotos-test'
    app.config.update(FOTOS_BACKEND='local', FOTOS_DIR=str(ruta))
    return ruta


class ClienteS3Falso:
    def __init__(self):
        self.subidas = []
        self.borrados = []

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        self.subidas.append((bucket, key, ExtraArgs, fileobj.read()))

    def delete_object(self, Bucket, Key):
        self.borrados.append((Bucket, Key))


@pytest.fixture
def cliente_s3(app, monkeypatch):
    app.config.update(FOTOS_BACKEND='s3', AWS_S3_BUCKET='bucket-test', AWS_S3_REGION='eu-west-1',
                      AWS_S3_ENDPOINT_URL=None)
    falso = ClienteS3Falso()
    argumentos = {}

    def crear_cliente(*args, **kwargs):
        argumentos.update(kwargs)
        return falso
    monkeypatch.setattr(fotos_s3.boto3, 'client', crear_cliente)
    falso.argumentos = argumentos
    return falso


class TestValidacionComun:
    """Las comprobaciones de formato no dependen del backend."""

    def test_rechaza_html_con_extension_de_imagen(self, cliente_s3):
        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(b'<script>alert(1)</script>'))
        assert error.value.mensaje == fotos.MENSAJE_FORMATO
        assert cliente_s3.subidas == []

    def test_rechaza_extension_no_permitida(self, cliente_s3):
        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido(), 'foto.svg', 'image/svg+xml'))
        assert error.value.mensaje == fotos.MENSAJE_FORMATO

    def test_url_manual_debe_ser_https(self):
        assert fotos.es_url_imagen_valida('https://ejemplo.com/a.jpg')
        assert fotos.es_url_imagen_valida('HTTPS://ejemplo.com/a.jpg')
        assert not fotos.es_url_imagen_valida('http://ejemplo.com/a.jpg')
        assert not fotos.es_url_imagen_valida('javascript:alert(1)')


class TestBackendLocal:

    def test_guarda_en_el_directorio_y_devuelve_la_ruta(self, directorio):
        contenido = png_valido()
        url = fotos.guardar_foto(archivo(contenido, 'foto.png', 'text/html'))

        assert url.startswith('/fotos/') and url.endswith('.png')
        clave = url.removeprefix('/fotos/')
        assert len(clave) == 32 + len('.png')
        assert (directorio / clave).read_bytes() == contenido
        assert fotos.es_foto_propia(url)

    def test_sin_fotos_dir_usa_instance(self, app, monkeypatch, tmp_path):
        monkeypatch.setattr(app, 'instance_path', str(tmp_path / 'instance'))
        app.config.update(FOTOS_BACKEND='local', FOTOS_DIR=None)

        url = fotos.guardar_foto(archivo(png_valido()))

        assert (tmp_path / 'instance' / 'fotos' / url.removeprefix('/fotos/')).exists()

    def test_borra_foto_propia(self, directorio):
        url = fotos.guardar_foto(archivo(png_valido()))

        assert fotos.borrar_foto(url) is True
        assert list(directorio.iterdir()) == []

    def test_borrar_foto_que_ya_no_existe_no_falla(self, directorio):
        assert fotos.borrar_foto('/fotos/' + CLAVE) is True

    @pytest.mark.parametrize('url', [
        None,
        '',
        'https://images.unsplash.com/photo.jpg',
        '/fotos/../config.py',
        '/fotos/..%2Fconfig.py',
        '/fotos/' + 'a' * 32 + '.svg',
        '/fotos/' + 'A' * 32 + '.png',
        '/fotos/' + 'a' * 31 + '.png',
        '/fotos/sub/' + CLAVE,
        '/otra/' + CLAVE,
        BASE_S3 + CLAVE,
    ])
    def test_no_borra_claves_ajenas(self, directorio, url):
        directorio.mkdir(parents=True)
        (directorio.parent / 'config.py').write_text('secreto')

        assert fotos.es_foto_propia(url) is False
        assert fotos.borrar_foto(url) is False
        assert (directorio.parent / 'config.py').exists()


class TestRutaFotos:

    def test_sirve_la_foto_guardada(self, client, directorio):
        contenido = png_valido()
        url = fotos.guardar_foto(archivo(contenido))

        response = client.get(url)

        assert response.status_code == 200
        assert response.data == contenido
        assert response.mimetype == 'image/png'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert 'max-age' in response.headers['Cache-Control']

    def test_foto_inexistente_404(self, client, directorio):
        assert client.get('/fotos/' + CLAVE).status_code == 404

    @pytest.mark.parametrize('ruta', [
        '/fotos/..%2Fsecreto.png',
        '/fotos/%2E%2E/secreto.png',
        '/fotos/secreto.png',
        '/fotos/' + 'a' * 32 + '.html',
        '/fotos/' + 'a' * 32 + '.PNG',
    ])
    def test_clave_no_valida_404(self, client, directorio, ruta):
        directorio.mkdir(parents=True)
        (directorio / 'secreto.png').write_bytes(b'x')
        (directorio.parent / 'secreto.png').write_bytes(b'x')
        (directorio / ('a' * 32 + '.html')).write_bytes(b'<script></script>')

        assert client.get(ruta).status_code == 404


class TestBackendS3:

    def test_sube_con_content_type_del_contenido(self, cliente_s3):
        # El navegador declara text/html, pero el contenido es un PNG
        contenido = png_valido()
        url = fotos.guardar_foto(archivo(contenido, 'foto.png', 'text/html'))

        assert url.startswith(BASE_S3) and url.endswith('.png')
        bucket, key, extra, subido = cliente_s3.subidas[0]
        assert bucket == 'bucket-test'
        assert key == 'mascotas/' + url.removeprefix(BASE_S3)
        assert extra == {'ContentType': 'image/png'}
        assert subido == contenido
        assert cliente_s3.argumentos['endpoint_url'] is None

    def test_endpoint_url_opcional(self, app, cliente_s3):
        app.config['AWS_S3_ENDPOINT_URL'] = 'https://s3.ejemplo.test/'

        url = fotos.guardar_foto(archivo(png_valido()))

        assert cliente_s3.argumentos['endpoint_url'] == 'https://s3.ejemplo.test/'
        assert url.startswith('https://s3.ejemplo.test/bucket-test/mascotas/')
        assert fotos.es_foto_propia(url)
        assert not fotos.es_foto_propia(BASE_S3 + CLAVE)

    def test_borra_foto_propia(self, cliente_s3):
        assert fotos.borrar_foto(BASE_S3 + CLAVE) is True
        assert cliente_s3.borrados == [('bucket-test', 'mascotas/' + CLAVE)]

    @pytest.mark.parametrize('url', [
        None,
        'https://images.unsplash.com/photo.jpg',
        'https://otro.s3.eu-west-1.amazonaws.com/mascotas/' + CLAVE,
        'https://x.amazonaws.com/backups/db.sql',
        BASE_S3 + '../backups/db.sql',
        BASE_S3 + 'sub/' + CLAVE,
        BASE_S3,
        '/fotos/' + CLAVE,
    ])
    def test_no_borra_claves_ajenas(self, cliente_s3, url):
        assert fotos.borrar_foto(url) is False
        assert cliente_s3.borrados == []
