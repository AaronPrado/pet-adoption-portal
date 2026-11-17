"""
Tests de los comandos CLI.
"""

import io
import os

import pytest
from botocore.exceptions import ClientError
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import db, fotos
from app.fotos import s3 as fotos_s3
from app.models import Mascota, Usuario

BASE_S3 = 'https://bucket-test.s3.eu-west-1.amazonaws.com/mascotas/'
ANTIGUA = 'a' * 32 + '.png'


def subir_foto():
    buffer = io.BytesIO()
    Image.new('RGB', (30, 20), 'red').save(buffer, format='PNG')
    buffer.seek(0)
    return fotos.guardar_foto(FileStorage(stream=buffer, filename='foto.png'))


def mascota_con_foto(foto_url, nombre='Rocky'):
    mascota = Mascota(nombre=nombre, especie='Perro', descripcion='Perro tranquilo', estado='disponible',
                      foto_url=foto_url)
    db.session.add(mascota)
    db.session.commit()
    return mascota


def claves(url):
    return [u.rsplit('/', 1)[1] for u in fotos.urls_de_la_foto(url)]


class TestExportarFotos:

    def test_copia_originales_y_variantes_de_todas_las_mascotas(self, app, runner, tmp_path):
        app.config['FOTOS_BACKEND'] = 'local'
        nueva = subir_foto()
        directorio = tmp_path / 'fotos'
        (directorio / ANTIGUA).write_bytes(b'png antiguo')
        mascota_con_foto(nueva)
        mascota_con_foto(nueva, 'Comparte la foto')
        mascota_con_foto('/fotos/' + ANTIGUA, 'Antigua')
        mascota_con_foto('https://images.unsplash.com/photo.jpg', 'Externa')
        mascota_con_foto(None, 'Sin foto')
        destino = tmp_path / 'copia' / 'fotos'

        result = runner.invoke(args=['exportar-fotos', str(destino)])

        assert result.exit_code == 0, result.output
        esperadas = sorted([*claves(nueva), ANTIGUA])
        assert sorted(f.name for f in destino.iterdir()) == esperadas
        for nombre in esperadas:
            assert (destino / nombre).read_bytes() == (directorio / nombre).read_bytes()
        assert f'2 fotos (4 archivos) exportadas a {destino}' in result.output

    def test_avisa_de_las_fotos_que_no_encuentra(self, app, runner, tmp_path):
        app.config['FOTOS_BACKEND'] = 'local'
        url = subir_foto()
        perdida = claves(url)[0]
        (tmp_path / 'fotos' / perdida).unlink()
        mascota_con_foto(url)
        mascota_con_foto('/fotos/' + ANTIGUA, 'Antigua')
        destino = tmp_path / 'copia'

        result = runner.invoke(args=['exportar-fotos', str(destino)])

        assert result.exit_code == 1
        assert f'No se ha encontrado {perdida}' in result.output
        assert f'No se ha encontrado {ANTIGUA}' in result.output
        assert '1 fotos (2 archivos) exportadas' in result.output
        assert '2 archivos no encontrados' in result.output
        assert sorted(f.name for f in destino.iterdir()) == sorted(claves(url)[1:])

    def test_exportar_al_propio_directorio_no_estropea_las_fotos(self, app, runner, tmp_path):
        app.config['FOTOS_BACKEND'] = 'local'
        url = subir_foto()
        mascota_con_foto(url)
        directorio = tmp_path / 'fotos'
        antes = {f.name: f.read_bytes() for f in directorio.iterdir()}

        result = runner.invoke(args=['exportar-fotos', str(directorio)])

        assert result.exit_code == 0, result.output
        assert {f.name: f.read_bytes() for f in directorio.iterdir()} == antes

    def test_sin_fotos_propias(self, app, runner, tmp_path):
        app.config['FOTOS_BACKEND'] = 'local'
        mascota_con_foto('https://images.unsplash.com/photo.jpg')

        result = runner.invoke(args=['exportar-fotos', str(tmp_path / 'copia')])

        assert result.exit_code == 0, result.output
        assert '0 fotos (0 archivos) exportadas' in result.output

    def test_sin_backend_da_error(self, app, runner, tmp_path):
        app.config['FOTOS_BACKEND'] = ''

        result = runner.invoke(args=['exportar-fotos', str(tmp_path / 'copia')])

        assert result.exit_code != 0
        assert 'FOTOS_BACKEND' in result.output

    def test_destino_que_no_es_un_directorio(self, app, runner, tmp_path):
        app.config['FOTOS_BACKEND'] = 'local'
        destino = tmp_path / 'archivo'
        destino.write_text('x')

        result = runner.invoke(args=['exportar-fotos', str(destino)])

        assert result.exit_code != 0

    @pytest.mark.skipif(os.geteuid() == 0, reason='root puede escribir sin permisos')
    @pytest.mark.parametrize('subdirectorio', [False, True], ids=['destino', 'dentro_del_destino'])
    def test_destino_sin_permisos_da_un_mensaje(self, app, runner, tmp_path, subdirectorio):
        app.config['FOTOS_BACKEND'] = 'local'
        mascota_con_foto(subir_foto())
        protegido = tmp_path / 'protegido'
        protegido.mkdir()
        protegido.chmod(0o500)
        destino = protegido / 'copia' if subdirectorio else protegido

        try:
            result = runner.invoke(args=['exportar-fotos', str(destino)])
        finally:
            protegido.chmod(0o700)

        assert result.exit_code == 1
        assert f'No se puede escribir en {destino}' in result.output
        assert 'Traceback' not in result.output
        assert isinstance(result.exception, SystemExit)

    def test_fallo_al_renombrar_da_un_mensaje_y_no_deja_temporales(self, app, runner, tmp_path, monkeypatch):
        app.config['FOTOS_BACKEND'] = 'local'
        mascota_con_foto(subir_foto())
        destino = tmp_path / 'copia'

        def fallar(origen, final):
            raise PermissionError(13, 'Permiso denegado')
        monkeypatch.setattr('app.fotos.os.replace', fallar)

        result = runner.invoke(args=['exportar-fotos', str(destino)])

        assert result.exit_code == 1
        assert 'Permiso denegado' in result.output
        assert list(destino.iterdir()) == []

    def test_no_sigue_enlaces_ni_deja_temporales(self, app, runner, tmp_path):
        app.config['FOTOS_BACKEND'] = 'local'
        url = subir_foto()
        mascota_con_foto(url)
        destino = tmp_path / 'copia'
        destino.mkdir()
        externo = tmp_path / 'externo.txt'
        externo.write_text('no tocar')
        (destino / claves(url)[0]).symlink_to(externo)

        result = runner.invoke(args=['exportar-fotos', str(destino)])

        assert result.exit_code == 0, result.output
        assert externo.read_text() == 'no tocar'
        assert not (destino / claves(url)[0]).is_symlink()
        assert sorted(f.name for f in destino.iterdir()) == sorted(claves(url))

    def test_desde_s3(self, app, runner, tmp_path, monkeypatch):
        app.config.update(FOTOS_BACKEND='s3', AWS_S3_BUCKET='bucket-test', AWS_S3_REGION='eu-west-1',
                          AWS_S3_ENDPOINT_URL=None)
        base = 'b' * 32
        objetos = {f'mascotas/{base}-{ancho}.webp': f'webp {ancho}'.encode() for ancho in (400, 800)}

        class ClienteFalso:
            def download_fileobj(self, bucket, key, fileobj):
                assert bucket == 'bucket-test'
                if key not in objetos:
                    raise ClientError({'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')
                fileobj.write(objetos[key])
        monkeypatch.setattr(fotos_s3.boto3, 'client', lambda *args, **kwargs: ClienteFalso())
        mascota_con_foto(f'{BASE_S3}{base}-1200.webp')
        destino = tmp_path / 'copia'

        result = runner.invoke(args=['exportar-fotos', str(destino)])

        assert result.exit_code == 1
        assert f'No se ha encontrado {base}-1200.webp' in result.output
        assert (destino / f'{base}-400.webp').read_bytes() == b'webp 400'
        assert not (destino / f'{base}-1200.webp').exists()

    @pytest.mark.parametrize('url', ['/fotos/../config.py', '/fotos/' + 'a' * 32 + '.svg'])
    def test_no_exporta_claves_no_validas(self, app, runner, tmp_path, url):
        app.config['FOTOS_BACKEND'] = 'local'
        mascota_con_foto(url)

        result = runner.invoke(args=['exportar-fotos', str(tmp_path / 'copia')])

        assert result.exit_code == 0, result.output
        assert list((tmp_path / 'copia').iterdir()) == []


def test_crear_admin(runner):
    result = runner.invoke(args=['crear-admin', '--email', 'Jefa@Refugio.com', '--nombre', 'Jefa',
                                 '--password', 'clave-segura-1'])

    assert result.exit_code == 0, result.output
    admin = Usuario.query.filter_by(email='jefa@refugio.com').one()
    assert admin.is_admin()
    assert admin.check_password('clave-segura-1')


def test_crear_admin_asciende_usuario_existente(runner, usuario_adoptante):
    result = runner.invoke(args=['crear-admin', '--email', 'adoptante@test.com', '--nombre', 'Pepe',
                                 '--password', 'clave-segura-2'])

    assert result.exit_code == 0, result.output
    assert Usuario.query.filter_by(email='adoptante@test.com').one().is_admin()


def test_crear_admin_rechaza_contrasena_corta(runner):
    result = runner.invoke(args=['crear-admin', '--email', 'a@b.com', '--nombre', 'A',
                                 '--password', 'corta'])

    assert result.exit_code != 0
    assert Usuario.query.count() == 0
