"""
Tests del almacenamiento de fotos (app/fotos): backend S3 con un cliente
boto3 falso.
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
    app.config.update(AWS_S3_BUCKET='bucket-test', AWS_S3_REGION='eu-west-1', AWS_S3_ENDPOINT_URL=None)
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
