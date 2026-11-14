"""
Tests de la subida y borrado de fotos en S3 (cliente boto3 simulado).
"""

import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import s3

BASE = 'https://bucket-test.s3.eu-west-1.amazonaws.com/mascotas/'


class ClienteS3Falso:
    def __init__(self):
        self.subidas = []
        self.borrados = []

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        self.subidas.append((bucket, key, ExtraArgs))

    def delete_object(self, Bucket, Key):
        self.borrados.append((Bucket, Key))


@pytest.fixture
def cliente_s3(app, monkeypatch):
    app.config['AWS_S3_BUCKET'] = 'bucket-test'
    app.config['AWS_S3_REGION'] = 'eu-west-1'
    falso = ClienteS3Falso()
    monkeypatch.setattr(s3.boto3, 'client', lambda *args, **kwargs: falso)
    return falso


def archivo(contenido, nombre, content_type):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre, content_type=content_type)


def png_valido():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2), 'red').save(buffer, format='PNG')
    return buffer.getvalue()


class TestUpload:

    def test_sube_imagen_con_content_type_del_contenido(self, cliente_s3):
        # El navegador declara text/html, pero el contenido es un PNG
        url = s3.upload_to_s3(archivo(png_valido(), 'foto.png', 'text/html'))

        assert url.startswith(BASE) and url.endswith('.png')
        _, key, extra = cliente_s3.subidas[0]
        assert key.startswith('mascotas/')
        assert extra == {'ContentType': 'image/png'}

    def test_rechaza_html_con_extension_de_imagen(self, cliente_s3):
        url = s3.upload_to_s3(archivo(b'<script>alert(1)</script>', 'foto.png', 'image/png'))

        assert url is None
        assert cliente_s3.subidas == []

    def test_rechaza_extension_no_permitida(self, cliente_s3):
        assert s3.upload_to_s3(archivo(png_valido(), 'foto.svg', 'image/svg+xml')) is None


class TestDelete:

    def test_borra_foto_propia(self, cliente_s3):
        s3.delete_from_s3(BASE + 'abc.png')
        assert cliente_s3.borrados == [('bucket-test', 'mascotas/abc.png')]

    @pytest.mark.parametrize('url', [
        None,
        'https://images.unsplash.com/photo.jpg',
        'https://otro.s3.eu-west-1.amazonaws.com/mascotas/abc.png',
        'https://x.amazonaws.com/backups/db.sql',
        BASE + '../backups/db.sql',
        BASE,
    ])
    def test_no_borra_claves_ajenas(self, cliente_s3, url):
        s3.delete_from_s3(url)
        assert cliente_s3.borrados == []


def test_url_manual_debe_ser_https(client, auth_headers_admin):
    response = client.post('/mascotas/admin/nueva', data={
        'nombre': 'Rocky',
        'especie': 'Perro',
        'descripcion': 'Perro tranquilo y cariñoso',
        'foto_url': 'javascript:alert(1)'
    })
    assert 'debe empezar por https://' in response.data.decode()
