"""
Tests del almacenamiento de fotos (app/fotos): procesado con Pillow y
variantes WebP, backend local con tmp_path, backend S3 con un cliente boto3
falso y la ruta GET /fotos/<clave>.
"""

import io
import logging
import re

import pytest
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import ClientError
from PIL import ExifTags, Image, ImageCms
from werkzeug.datastructures import FileStorage

from app import fotos
from app.fotos import procesado
from app.fotos import s3 as fotos_s3

BASE_S3 = 'https://bucket-test.s3.eu-west-1.amazonaws.com/mascotas/'
CLAVE = 'a' * 32 + '.png'
BASE = 'b' * 32
VARIANTES = [f'{BASE}-400.webp', f'{BASE}-800.webp', f'{BASE}-1200.webp']
PATRON_PRINCIPAL = r'[0-9a-f]{32}-1200\.webp'


def archivo(contenido, nombre='foto.png', content_type='image/png'):
    return FileStorage(stream=io.BytesIO(contenido), filename=nombre, content_type=content_type)


def codificar(imagen, formato='PNG', **opciones):
    buffer = io.BytesIO()
    imagen.save(buffer, format=formato, **opciones)
    return buffer.getvalue()


def png_valido(tamano=(2, 2)):
    return codificar(Image.new('RGB', tamano, 'red'))


def abrir(contenido):
    imagen = Image.open(io.BytesIO(contenido))
    imagen.load()
    return imagen


def parecido(color, esperado, margen=40):
    """Compresión con pérdida: el color se compara con margen."""
    return all(abs(a - b) <= margen for a, b in zip(color[:3], esperado, strict=True))


def jpeg_con_gps(tamano=(40, 20), orientacion=None):
    """JPEG rojo a la izquierda y azul a la derecha, con cámara, fecha, GPS y orientación."""
    imagen = Image.new('RGB', tamano, 'red')
    imagen.paste('blue', (tamano[0] // 2, 0, tamano[0], tamano[1]))
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = 'CamaraDeLaAcogida'
    exif[ExifTags.Base.DateTime] = '2026:11:17 10:00:00'
    exif[ExifTags.IFD.GPSInfo] = {
        ExifTags.GPS.GPSLatitudeRef: 'N',
        ExifTags.GPS.GPSLatitude: (40.0, 25.0, 1.5),
        ExifTags.GPS.GPSLongitudeRef: 'W',
        ExifTags.GPS.GPSLongitude: (3.0, 42.0, 7.5),
    }
    if orientacion:
        exif[ExifTags.Base.Orientation] = orientacion
    return codificar(imagen, 'JPEG', exif=exif, quality=95)


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
        self.error = None

    def upload_fileobj(self, fileobj, bucket, key, ExtraArgs=None):
        if self.error:
            raise self.error
        self.subidas.append((bucket, key, ExtraArgs, fileobj.read()))

    def delete_object(self, Bucket, Key):
        if self.error:
            raise self.error
        self.borrados.append((Bucket, Key))


def error_s3():
    return ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'denegado'}}, 'PutObject')


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

    def test_rechaza_html_con_extension_de_imagen(self, directorio):
        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(b'<script>alert(1)</script>'))
        assert error.value.mensaje == fotos.MENSAJE_FORMATO
        assert not directorio.exists()

    def test_rechaza_extension_no_permitida(self, directorio):
        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido(), 'foto.svg', 'image/svg+xml'))
        assert error.value.mensaje == fotos.MENSAJE_FORMATO

    def test_bomba_de_descompresion_es_error_de_formato(self, directorio, monkeypatch):
        """Más del doble de Image.MAX_IMAGE_PIXELS: Pillow lanza DecompressionBombError."""
        monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', 1)

        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido()))
        assert error.value.mensaje == fotos.MENSAJE_FORMATO
        assert not directorio.exists()

    def test_el_mensaje_de_formato_dice_causa_y_solucion(self):
        assert fotos.MENSAJE_FORMATO == 'No hemos podido usar esa imagen. Sube un archivo JPG, PNG, GIF o WebP.'

    def test_url_manual_debe_ser_https(self):
        assert fotos.es_url_imagen_valida('https://ejemplo.com/a.jpg')
        assert fotos.es_url_imagen_valida('HTTPS://ejemplo.com/a.jpg')
        assert not fotos.es_url_imagen_valida('http://ejemplo.com/a.jpg')
        assert not fotos.es_url_imagen_valida('javascript:alert(1)')


class TestSinBackend:

    @pytest.mark.parametrize('config', [
        {'FOTOS_BACKEND': ''},
        {'FOTOS_BACKEND': None},
        {'FOTOS_BACKEND': 's3', 'AWS_S3_BUCKET': None},
    ], ids=['vacio', 'none', 's3_sin_bucket'])
    def test_subida_no_disponible(self, app, config):
        app.config.update(config)
        assert fotos.subida_disponible() is False

    def test_guardar_da_error_con_solucion_y_no_500(self, app):
        app.config['FOTOS_BACKEND'] = ''
        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido()))
        assert 'no está disponible' in error.value.mensaje
        assert 'https://' in error.value.mensaje

    def test_borrar_no_hace_nada(self, app):
        app.config['FOTOS_BACKEND'] = ''
        assert fotos.borrar_foto('/fotos/' + CLAVE) is False
        assert fotos.es_foto_propia('/fotos/' + CLAVE) is False


class TestBackendLocal:

    def test_disponible(self, directorio):
        assert fotos.subida_disponible() is True

    def test_guarda_las_variantes_y_devuelve_la_de_1200(self, directorio):
        url = fotos.guardar_foto(archivo(png_valido(), 'foto.png', 'text/html'))

        clave = url.removeprefix('/fotos/')
        assert re.fullmatch(PATRON_PRINCIPAL, clave)
        base = clave.removesuffix('-1200.webp')
        assert sorted(f.name for f in directorio.iterdir()) == sorted(
            f'{base}-{ancho}.webp' for ancho in (400, 800, 1200))
        assert abrir((directorio / clave).read_bytes()).format == 'WEBP'
        assert fotos.es_foto_propia(url)

    def test_fallo_a_medias_no_deja_variantes(self, directorio, monkeypatch):
        from app.fotos import local
        guardar = local.guardar

        def fallar_en_la_tercera(stream, clave, content_type):
            if clave.endswith('-1200.webp'):
                raise OSError('disco lleno')
            return guardar(stream, clave, content_type)
        monkeypatch.setattr(local, 'guardar', fallar_en_la_tercera)

        with pytest.raises(fotos.ErrorAlmacenamiento):
            fotos.guardar_foto(archivo(png_valido()))
        assert list(directorio.iterdir()) == []

    def test_error_inesperado_borra_las_variantes_y_se_propaga(self, directorio, monkeypatch):
        from app.fotos import local
        guardar = local.guardar

        def fallar_en_la_tercera(stream, clave, content_type):
            if clave.endswith('-1200.webp'):
                raise RuntimeError('fallo inesperado')
            return guardar(stream, clave, content_type)
        monkeypatch.setattr(local, 'guardar', fallar_en_la_tercera)

        with pytest.raises(RuntimeError):
            fotos.guardar_foto(archivo(png_valido()))
        assert list(directorio.iterdir()) == []

    def test_sin_fotos_dir_usa_instance(self, app, monkeypatch, tmp_path):
        monkeypatch.setattr(app, 'instance_path', str(tmp_path / 'instance'))
        app.config.update(FOTOS_BACKEND='local', FOTOS_DIR=None)

        url = fotos.guardar_foto(archivo(png_valido()))

        assert (tmp_path / 'instance' / 'fotos' / url.removeprefix('/fotos/')).exists()

    def test_error_de_disco_da_error_de_campo_y_se_registra(self, directorio, caplog):
        directorio.parent.mkdir(exist_ok=True)
        directorio.write_text('no es un directorio')

        with caplog.at_level(logging.ERROR), pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido()))

        assert error.value.mensaje == fotos.MENSAJE_FALLO
        assert 'No se pudo guardar la foto' in caplog.text

    def test_escritura_fallida_no_deja_archivo_a_medias(self, directorio, monkeypatch):
        def fallar(origen, destino):
            destino.write(b'parcial')
            raise OSError('disco lleno')
        monkeypatch.setattr('app.fotos.local.shutil.copyfileobj', fallar)

        with pytest.raises(fotos.ErrorAlmacenamiento):
            fotos.guardar_foto(archivo(png_valido()))
        assert list(directorio.iterdir()) == []

    def test_borra_foto_propia(self, directorio):
        url = fotos.guardar_foto(archivo(png_valido()))

        assert fotos.borrar_foto(url) is True
        assert list(directorio.iterdir()) == []

    def test_borrar_foto_que_ya_no_existe_no_falla(self, directorio):
        assert fotos.borrar_foto('/fotos/' + CLAVE) is True

    @pytest.mark.parametrize('variante', VARIANTES)
    def test_borrar_desde_cualquier_variante_borra_todas(self, directorio, variante):
        directorio.mkdir(parents=True)
        for nombre in [*VARIANTES, 'c' * 32 + '-400.webp']:
            (directorio / nombre).write_bytes(b'x')

        assert fotos.borrar_foto('/fotos/' + variante) is True
        assert [f.name for f in directorio.iterdir()] == ['c' * 32 + '-400.webp']

    def test_borra_las_variantes_de_una_foto_subida(self, directorio):
        url = fotos.guardar_foto(archivo(png_valido()))

        assert fotos.borrar_foto(url) is True
        assert list(directorio.iterdir()) == []

    def test_foto_antigua_sin_variantes_se_borra(self, directorio):
        directorio.mkdir(parents=True)
        (directorio / CLAVE).write_bytes(b'x')

        assert fotos.borrar_foto('/fotos/' + CLAVE) is True
        assert list(directorio.iterdir()) == []

    def test_urls_de_la_foto(self, directorio):
        assert fotos.urls_de_la_foto('/fotos/' + VARIANTES[0]) == ['/fotos/' + v for v in VARIANTES]
        assert fotos.urls_de_la_foto('/fotos/' + CLAVE) == ['/fotos/' + CLAVE]
        assert fotos.urls_de_la_foto('https://ejemplo.com/a.jpg') == ['https://ejemplo.com/a.jpg']

    def test_error_al_borrar_se_registra_sin_propagarse(self, directorio, monkeypatch, caplog):
        url = fotos.guardar_foto(archivo(png_valido()))

        def fallar(ruta):
            raise PermissionError('sin permiso')
        monkeypatch.setattr('app.fotos.local.os.remove', fallar)

        with caplog.at_level(logging.ERROR):
            assert fotos.borrar_foto(url) is False
        assert 'No se pudo borrar la foto' in caplog.text

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
        '/fotos/' + BASE + '-600.webp',
        '/fotos/' + BASE + '-400.png',
        '/fotos/' + BASE + '-400.webp/../x',
        '/fotos/' + BASE + '-0400.webp',
        '/fotos/' + BASE + '-400.webp\n',
    ])
    def test_no_borra_claves_ajenas(self, directorio, url):
        directorio.mkdir(parents=True)
        (directorio.parent / 'config.py').write_text('secreto')

        assert fotos.es_foto_propia(url) is False
        assert fotos.borrar_foto(url) is False
        assert (directorio.parent / 'config.py').exists()


class TestRutaFotos:

    def test_sirve_la_foto_guardada(self, client, directorio):
        url = fotos.guardar_foto(archivo(png_valido()))

        response = client.get(url)

        assert response.status_code == 200
        assert response.data == (directorio / url.removeprefix('/fotos/')).read_bytes()
        assert response.mimetype == 'image/webp'
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
        '/fotos/' + 'a' * 32 + '-1200.WEBP',
        '/fotos/' + 'a' * 32 + '-1600.webp',
        '/fotos/' + 'a' * 32 + '-400.webp%2F..%2Fsecreto.png',
        '/fotos/' + 'a' * 32 + '-400.webp%00',
    ])
    def test_clave_no_valida_404(self, client, directorio, ruta):
        directorio.mkdir(parents=True)
        (directorio / 'secreto.png').write_bytes(b'x')
        (directorio.parent / 'secreto.png').write_bytes(b'x')
        (directorio / ('a' * 32 + '.html')).write_bytes(b'<script></script>')

        assert client.get(ruta).status_code == 404

    @pytest.mark.parametrize('variante', VARIANTES)
    def test_sirve_las_variantes(self, client, directorio, variante):
        directorio.mkdir(parents=True)
        (directorio / variante).write_bytes(b'RIFF')

        response = client.get('/fotos/' + variante)

        assert response.status_code == 200
        assert response.mimetype == 'image/webp'


class TestBackendS3:

    def test_disponible_con_bucket(self, cliente_s3):
        assert fotos.subida_disponible() is True

    def test_sube_las_variantes_webp(self, cliente_s3):
        # El navegador declara text/html, pero el contenido es un PNG
        url = fotos.guardar_foto(archivo(png_valido(), 'foto.png', 'text/html'))

        clave = url.removeprefix(BASE_S3)
        assert re.fullmatch(PATRON_PRINCIPAL, clave)
        base = clave.removesuffix('-1200.webp')
        assert [key for _, key, _, _ in cliente_s3.subidas] == [
            f'mascotas/{base}-{ancho}.webp' for ancho in (400, 800, 1200)]
        for bucket, _, extra, subido in cliente_s3.subidas:
            assert bucket == 'bucket-test'
            assert extra == {'ContentType': 'image/webp'}
            assert abrir(subido).format == 'WEBP'
        assert cliente_s3.argumentos['endpoint_url'] is None

    def test_fallo_a_medias_borra_las_variantes_subidas(self, cliente_s3, monkeypatch):
        subir = cliente_s3.upload_fileobj

        def fallar_en_la_segunda(fileobj, bucket, key, ExtraArgs=None):
            if cliente_s3.subidas:
                raise error_s3()
            subir(fileobj, bucket, key, ExtraArgs)
        monkeypatch.setattr(cliente_s3, 'upload_fileobj', fallar_en_la_segunda)

        with pytest.raises(fotos.ErrorAlmacenamiento):
            fotos.guardar_foto(archivo(png_valido()))

        assert len(cliente_s3.subidas) == 1
        assert [key for _, key in cliente_s3.borrados] == [key for _, key, _, _ in cliente_s3.subidas]

    def test_endpoint_url_opcional(self, app, cliente_s3):
        app.config['AWS_S3_ENDPOINT_URL'] = 'https://s3.ejemplo.test/'

        url = fotos.guardar_foto(archivo(png_valido()))

        assert cliente_s3.argumentos['endpoint_url'] == 'https://s3.ejemplo.test/'
        assert url.startswith('https://s3.ejemplo.test/bucket-test/mascotas/')
        assert fotos.es_foto_propia(url)
        assert not fotos.es_foto_propia(BASE_S3 + CLAVE)

    def test_client_error_da_error_de_campo_y_se_registra(self, cliente_s3, caplog):
        cliente_s3.error = error_s3()

        with caplog.at_level(logging.ERROR), pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido()))

        assert error.value.mensaje == fotos.MENSAJE_FALLO
        assert 'AccessDenied' in caplog.text

    def test_s3_upload_failed_error_da_error_de_campo(self, cliente_s3):
        """upload_fileobj envuelve el ClientError en S3UploadFailedError (de boto3, no de botocore)."""
        cliente_s3.error = S3UploadFailedError('Failed to upload: AccessDenied')

        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido()))

        assert error.value.mensaje == fotos.MENSAJE_FALLO

    def test_borra_foto_propia(self, cliente_s3):
        assert fotos.borrar_foto(BASE_S3 + CLAVE) is True
        assert cliente_s3.borrados == [('bucket-test', 'mascotas/' + CLAVE)]

    def test_borra_todas_las_variantes(self, cliente_s3):
        assert fotos.borrar_foto(BASE_S3 + VARIANTES[-1]) is True
        assert cliente_s3.borrados == [('bucket-test', 'mascotas/' + v) for v in VARIANTES]

    def test_error_al_borrar_se_registra_sin_propagarse(self, cliente_s3, caplog):
        cliente_s3.error = error_s3()

        with caplog.at_level(logging.ERROR):
            assert fotos.borrar_foto(BASE_S3 + CLAVE) is False
        assert 'No se pudo borrar la foto' in caplog.text

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


class TestProcesado:
    """Toda foto subida se vuelve a codificar con Pillow (ADR-0003)."""

    def test_jpeg_con_gps_se_guarda_sin_exif(self, directorio):
        original = jpeg_con_gps()
        assert abrir(original).getexif().get_ifd(ExifTags.IFD.GPSInfo)
        assert b'CamaraDeLaAcogida' in original

        fotos.guardar_foto(archivo(original, 'foto.jpg', 'image/jpeg'))

        guardadas = list(directorio.iterdir())
        assert len(guardadas) == 3
        for variante in guardadas:
            contenido = variante.read_bytes()
            imagen = abrir(contenido)
            assert not imagen.getexif()
            assert not {'exif', 'xmp', 'icc_profile'} & set(imagen.info)
            assert b'Exif' not in contenido and b'CamaraDeLaAcogida' not in contenido

    def test_se_quitan_xmp_e_icc(self, caplog):
        imagen = Image.new('RGB', (8, 8), 'red')
        contenido = codificar(imagen, 'WEBP', xmp=b'<x:xmpmeta>casa</x:xmpmeta>', icc_profile=b'perfil-falso')
        assert b'xmpmeta' in contenido and b'perfil-falso' in contenido

        with caplog.at_level(logging.WARNING):
            variantes = procesado.procesar(io.BytesIO(contenido))

        for variante in variantes.values():
            assert b'xmpmeta' not in variante and b'perfil-falso' not in variante
        # Un perfil que no se puede leer no impide guardar la foto, pero se registra
        assert 'No se pudo convertir el perfil de color a sRGB' in caplog.text

    @pytest.mark.parametrize('modo', ['RGB', 'RGBA'])
    def test_el_perfil_icc_se_convierte_a_srgb(self, monkeypatch, caplog, modo):
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        contenido = codificar(Image.new(modo, (8, 8), 'red'), 'PNG', icc_profile=icc)
        llamadas = []
        convertir = ImageCms.profileToProfile

        def espiar(imagen, *args, **kwargs):
            llamadas.append((imagen.mode, kwargs['outputMode']))
            return convertir(imagen, *args, **kwargs)
        monkeypatch.setattr(ImageCms, 'profileToProfile', espiar)

        with caplog.at_level(logging.WARNING):
            resultado = abrir(procesado.procesar(io.BytesIO(contenido))[400])

        assert llamadas == [(modo, modo)]
        assert 'icc_profile' not in resultado.info
        assert parecido(resultado.getpixel((4, 4)), (255, 0, 0))
        assert caplog.text == ''

    def test_perfil_icc_de_un_jpeg_cmyk_sale_en_rgb(self, monkeypatch):
        icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        contenido = codificar(Image.new('CMYK', (8, 8)), 'JPEG', icc_profile=icc)
        llamadas = []

        def convertir(imagen, origen, destino, outputMode, **kwargs):
            llamadas.append((imagen.mode, outputMode, kwargs.get('inPlace', False)))
            return imagen.convert(outputMode)
        monkeypatch.setattr(ImageCms, 'profileToProfile', convertir)

        assert abrir(procesado.procesar(io.BytesIO(contenido))[400]).mode == 'RGB'
        assert llamadas == [('CMYK', 'RGB', False)]

    def test_sin_perfil_icc_no_se_convierte(self, monkeypatch):
        def fallar(*args, **kwargs):
            raise AssertionError('no debería convertir')
        monkeypatch.setattr(ImageCms, 'profileToProfile', fallar)

        procesado.procesar(io.BytesIO(png_valido()))

    def test_perfil_icc_de_otro_espacio_se_registra_y_sigue(self, caplog):
        lab = ImageCms.ImageCmsProfile(ImageCms.createProfile('LAB')).tobytes()
        contenido = codificar(Image.new('RGB', (8, 8), 'red'), 'PNG', icc_profile=lab)

        with caplog.at_level(logging.WARNING):
            resultado = abrir(procesado.procesar(io.BytesIO(contenido))[400])

        assert resultado.mode == 'RGB'
        assert 'No se pudo convertir el perfil de color a sRGB' in caplog.text

    def test_perfil_icc_de_un_gris_se_ignora(self, monkeypatch):
        srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        contenido = codificar(Image.new('L', (8, 8), 128), 'PNG', icc_profile=srgb)
        monkeypatch.setattr(ImageCms, 'profileToProfile', lambda *a, **k: pytest.fail('no debería convertir'))

        assert abrir(procesado.procesar(io.BytesIO(contenido))[400]).mode == 'RGB'

    def test_png_rgb_con_trns_se_pone_sobre_blanco(self):
        imagen = Image.new('RGB', (20, 10), (0, 0, 0))
        imagen.paste((255, 0, 0), (0, 0, 10, 10))
        contenido = codificar(imagen, transparency=(0, 0, 0))
        assert abrir(contenido).mode == 'RGB'

        resultado = abrir(procesado.procesar(io.BytesIO(contenido))[400])

        assert parecido(resultado.getpixel((3, 5)), (255, 0, 0))
        assert parecido(resultado.getpixel((16, 5)), (255, 255, 255))

    def test_png_gris_de_16_bits_se_escala_a_8(self):
        contenido = codificar(Image.new('I;16', (8, 8), 32768))
        assert abrir(contenido).mode.startswith('I')

        resultado = abrir(procesado.procesar(io.BytesIO(contenido))[400])

        assert parecido(resultado.getpixel((4, 4)), (128, 128, 128), margen=8)

    @pytest.mark.parametrize('tamano', [(16384, 1), (1, 16384)])
    def test_lado_mayor_que_el_maximo_de_webp_da_mensaje_claro(self, directorio, tamano):
        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(codificar(Image.new('L', tamano))))

        assert error.value.mensaje == 'La imagen es demasiado grande: como máximo 16383 px por lado.'
        assert not directorio.exists()

    def test_lado_en_el_maximo_de_webp_se_acepta(self):
        variantes = procesado.procesar(io.BytesIO(codificar(Image.new('L', (16383, 1)))))

        assert abrir(variantes[1200]).size == (1200, 1)

    def test_limite_de_pixeles_de_la_configuracion(self, app, directorio):
        assert app.config['FOTOS_MAX_PIXELES'] == 40_000_000
        app.config['FOTOS_MAX_PIXELES'] = 3
        limite_pillow = Image.MAX_IMAGE_PIXELS

        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido()))

        assert error.value.mensaje == fotos.MENSAJE_FORMATO
        assert limite_pillow == Image.MAX_IMAGE_PIXELS
        assert not directorio.exists()

    def test_las_variantes_se_generan_en_cadena_sin_copiar_el_original(self, monkeypatch):
        def fallar(self):
            raise AssertionError('copia completa del original')
        monkeypatch.setattr(Image.Image, 'copy', fallar)

        variantes = procesado.procesar(io.BytesIO(jpeg_con_gps((2000, 1000), orientacion=6)))

        assert [abrir(v).size for v in variantes.values()] == [(400, 800), (800, 1600), (1000, 2000)]

    def test_se_aplica_la_orientacion_exif(self):
        # Orientación 6: la cámara estaba girada; hay que rotar 90° a la derecha
        variantes = procesado.procesar(io.BytesIO(jpeg_con_gps((40, 20), orientacion=6)))

        imagen = abrir(variantes[1200])
        assert imagen.size == (20, 40)
        # La mitad izquierda (roja) pasa a estar arriba
        assert parecido(imagen.getpixel((10, 5)), (255, 0, 0))
        assert parecido(imagen.getpixel((10, 35)), (0, 0, 255))

    def test_png_con_transparencia_se_pone_sobre_blanco(self):
        imagen = Image.new('RGBA', (20, 10), (0, 0, 0, 0))
        imagen.paste((255, 0, 0, 255), (0, 0, 10, 10))

        resultado = abrir(procesado.procesar(io.BytesIO(codificar(imagen)))[400])

        assert resultado.mode == 'RGB'
        assert parecido(resultado.getpixel((3, 5)), (255, 0, 0))
        assert parecido(resultado.getpixel((16, 5)), (255, 255, 255))

    def test_gif_con_paleta_y_transparencia_se_convierte(self):
        imagen = Image.new('P', (10, 10), 0)
        imagen.putpalette([0, 0, 0, 0, 255, 0] + [0] * 762)
        imagen.paste(1, (0, 0, 5, 10))

        resultado = abrir(procesado.procesar(io.BytesIO(codificar(imagen, 'GIF', transparency=0)))[400])

        assert resultado.mode == 'RGB'
        assert parecido(resultado.getpixel((2, 5)), (0, 255, 0))
        assert parecido(resultado.getpixel((8, 5)), (255, 255, 255))

    @pytest.mark.parametrize('modo, formato', [('L', 'PNG'), ('CMYK', 'JPEG'), ('P', 'PNG')])
    def test_otros_modos_pasan_a_rgb(self, modo, formato):
        contenido = codificar(Image.new(modo, (8, 8)), formato)

        assert abrir(procesado.procesar(io.BytesIO(contenido))[800]).mode == 'RGB'

    @pytest.mark.parametrize('formato', ['PNG', 'JPEG'])
    def test_genera_las_tres_variantes_webp(self, formato):
        # JPEG grande: se decodifica ya reducido (draft) sin bajar de 1200 px
        contenido = codificar(Image.new('RGB', (5000, 2500), 'red'), formato)
        variantes = procesado.procesar(io.BytesIO(contenido))

        assert list(variantes) == [400, 800, 1200]
        assert [abrir(v).size for v in variantes.values()] == [(400, 200), (800, 400), (1200, 600)]
        assert {abrir(v).format for v in variantes.values()} == {'WEBP'}

    def test_no_amplia_las_imagenes_pequenas(self):
        variantes = procesado.procesar(io.BytesIO(png_valido((600, 300))))

        assert [abrir(v).size for v in variantes.values()] == [(400, 200), (600, 300), (600, 300)]

    def test_imagen_muy_apaisada_conserva_al_menos_un_pixel_de_alto(self):
        variantes = procesado.procesar(io.BytesIO(png_valido((3000, 1))))

        assert abrir(variantes[400]).size == (400, 1)

    @pytest.mark.filterwarnings('ignore::PIL.Image.DecompressionBombWarning')
    @pytest.mark.parametrize('max_pixeles', [3, 1], ids=['aviso_de_pillow', 'error_de_pillow'])
    def test_mas_pixeles_que_el_limite_es_error_de_formato(self, directorio, monkeypatch, max_pixeles):
        """2x2 = 4 píxeles: por encima de MAX_IMAGE_PIXELS, aunque Pillow solo avisaría."""
        monkeypatch.setattr(Image, 'MAX_IMAGE_PIXELS', max_pixeles)

        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(png_valido()))
        assert error.value.mensaje == fotos.MENSAJE_FORMATO
        assert not directorio.exists()

    @pytest.mark.parametrize('contenido', [
        codificar(Image.new('RGB', (4, 4)), 'BMP'),
        codificar(Image.new('RGB', (4, 4)), 'TIFF'),
        png_valido((50, 50))[:60],
        b'',
    ], ids=['bmp', 'tiff', 'truncada', 'vacia'])
    def test_tipo_real_no_permitido_o_danado(self, directorio, contenido):
        with pytest.raises(fotos.ErrorAlmacenamiento) as error:
            fotos.guardar_foto(archivo(contenido, 'foto.png'))
        assert error.value.mensaje == fotos.MENSAJE_FORMATO
        assert not directorio.exists()

    @pytest.mark.parametrize('formato', ['JPEG', 'GIF', 'WEBP'])
    def test_el_tipo_sale_del_contenido_y_no_del_nombre(self, directorio, formato):
        url = fotos.guardar_foto(archivo(codificar(Image.new('RGB', (4, 4)), formato), 'foto.png'))

        assert fotos.es_foto_propia(url)

    def test_solo_la_primera_imagen_de_un_gif_animado(self):
        cuadros = [Image.new('RGB', (6, 6), color) for color in ('red', 'blue')]
        contenido = codificar(cuadros[0], 'GIF', save_all=True, append_images=cuadros[1:])

        resultado = abrir(procesado.procesar(io.BytesIO(contenido))[400])

        assert getattr(resultado, 'n_frames', 1) == 1
        assert parecido(resultado.getpixel((3, 3)), (255, 0, 0))
