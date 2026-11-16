"""
Tests de las migraciones de Alembic (Flask-Migrate).

Se aplican sobre una base de datos SQLite en un archivo temporal; el job
"migraciones" del CI las prueba además contra PostgreSQL.
"""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect, text

from app import adopciones, create_app, db
from app.models import Mascota, utcnow
from config import TestingConfig


@pytest.fixture
def app_bd_archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f"sqlite:///{tmp_path / 'mig.db'}")
    app = create_app('testing')
    with app.app_context():
        yield app
        db.engine.dispose()


def test_upgrade_crea_el_esquema_de_los_modelos(app_bd_archivo):
    upgrade()

    with db.engine.connect() as conexion:
        diferencias = compare_metadata(MigrationContext.configure(conexion), db.metadata)

    assert diferencias == []


def test_downgrade_deja_la_base_vacia(app_bd_archivo):
    upgrade()
    downgrade(revision='base')

    assert set(inspect(db.engine).get_table_names()) <= {'alembic_version'}


def test_create_app_no_crea_tablas(app_bd_archivo):
    """El esquema solo lo crean las migraciones, no el arranque de la app."""
    assert inspect(db.engine).get_table_names() == []


def estados_de_mascotas():
    with db.engine.connect() as conexion:
        return dict(conexion.execute(text('SELECT nombre, estado FROM mascotas')).all())


def solicitudes():
    """{id: (estado, comentario, fecha_revision, revisado_por)} de todas las solicitudes."""
    with db.engine.connect() as conexion:
        filas = conexion.execute(text(
            'SELECT id, estado, comentarios_admin, fecha_revision, revisado_por FROM solicitudes'))
        return {fila[0]: tuple(fila[1:]) for fila in filas}


@pytest.fixture
def datos_en_proceso(app_bd_archivo):
    """Base en 0001 con mascotas en cada caso que trata la migración 0002."""
    upgrade(revision='0001')
    fecha = '2026-01-01 00:00:00'
    with db.engine.begin() as conexion:
        conexion.execute(text(
            "INSERT INTO usuarios (id, email, password_hash, nombre, rol, fecha_registro, activo) VALUES "
            "(1, 'a@test.com', 'x', 'A', 'adoptante', :f, 1), (2, 'b@test.com', 'x', 'B', 'adoptante', :f, 1)"),
            {'f': fecha})
        conexion.execute(text(
            "INSERT INTO mascotas (id, nombre, especie, estado, fecha_ingreso, vacunado, esterilizado) VALUES "
            "(1, 'Aprobada', 'Perro', 'en_proceso', :f, 0, 0), (2, 'Pendiente', 'Perro', 'en_proceso', :f, 0, 0), "
            "(3, 'Rechazada', 'Gato', 'en_proceso', :f, 0, 0), (4, 'Libre', 'Gato', 'disponible', :f, 0, 0), "
            "(5, 'Adoptada', 'Gato', 'adoptado', :f, 0, 0), (6, 'Esperando', 'Gato', 'disponible', :f, 0, 0)"),
            {'f': fecha})
        conexion.execute(text(
            "INSERT INTO solicitudes (id, usuario_id, mascota_id, estado, fecha_solicitud) VALUES "
            "(1, 1, 1, 'aprobada', :f), (2, 2, 1, 'pendiente', :f), (3, 1, 2, 'pendiente', :f), "
            "(4, 1, 3, 'rechazada', :f), (5, 2, 6, 'pendiente', :f), (6, 1, 5, 'pendiente', :f)"),
            {'f': fecha})


def test_0002_upgrade_deriva_los_estados(datos_en_proceso):
    upgrade(revision='0002')

    assert estados_de_mascotas() == {
        'Aprobada': 'adoptado', 'Pendiente': 'disponible', 'Rechazada': 'disponible',
        'Libre': 'disponible', 'Adoptada': 'adoptado', 'Esperando': 'disponible',
    }


def test_0002_upgrade_cierra_las_pendientes_de_las_adoptadas(datos_en_proceso):
    """Invariante: una mascota adoptada no tiene solicitudes pendientes."""
    antes = utcnow()
    upgrade(revision='0002')

    filas = solicitudes()
    # 2 (de una en_proceso con otra aprobada) y 6 (de una ya adoptada)
    for cerrada in (2, 6):
        estado, comentario, fecha, revisor = filas[cerrada]
        assert (estado, comentario, revisor) == ('rechazada', adopciones.COMENTARIO_RECHAZO_AUTOMATICO, None)
        assert antes <= datetime.fromisoformat(str(fecha)) <= utcnow()
    assert filas[3][0] == filas[5][0] == 'pendiente'
    assert filas[1][0] == 'aprobada' and filas[4][0] == 'rechazada'


def test_0002_upgrade_es_idempotente(datos_en_proceso):
    """Volver a ejecutar el cuerpo del upgrade no cambia estados ni fechas."""
    upgrade(revision='0002')
    mascotas, filas = estados_de_mascotas(), solicitudes()

    ruta = Path(__file__).parent.parent / 'migrations' / 'versions' / '0002_estados_derivados.py'
    spec = importlib.util.spec_from_file_location('migracion_0002', ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)
    with db.engine.begin() as conexion, Operations.context(MigrationContext.configure(conexion)):
        migracion.upgrade()

    assert estados_de_mascotas() == mascotas
    assert solicitudes() == filas


def test_0002_downgrade_vuelve_a_en_proceso_las_que_tienen_pendientes(datos_en_proceso):
    upgrade(revision='0002')
    downgrade(revision='0001')

    # Las adopciones no se revierten: «Aprobada» sigue adoptada
    assert estados_de_mascotas() == {
        'Aprobada': 'adoptado', 'Pendiente': 'en_proceso', 'Rechazada': 'disponible',
        'Libre': 'disponible', 'Adoptada': 'adoptado', 'Esperando': 'en_proceso',
    }
    # Ni se reabren las solicitudes que cerró el upgrade
    assert solicitudes()[2][0] == solicitudes()[6][0] == 'rechazada'


def cargar_migracion(nombre):
    """Importa un archivo de migrations/versions como módulo."""
    ruta = Path(__file__).parent.parent / 'migrations' / 'versions' / nombre
    spec = importlib.util.spec_from_file_location(ruta.stem, ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)
    return migracion


def especies_de_mascotas():
    with db.engine.connect() as conexion:
        return dict(conexion.execute(text('SELECT nombre, especie FROM mascotas')).all())


ESPECIES_SIN_NORMALIZAR = {
    'Bien': 'Perro', 'Minusculas': 'perro', 'Espacios': ' PERRO ', 'Gato': 'gATO',
    'Acento': 'ñandú', 'DosPalabras': '  cobaya   DE indias ', 'Vacia': '   ',
    'Nfd': 'n\u0303andu\u0301', 'Nbsp': 'cobaya\xa0de\xa0indias', 'AnchuraCero': 'pe\u200brro',
    'Larga': 'ß' * 50,
}

# Casos adversos para comparar la copia de la migración con el modelo
ESPECIES_ADVERSAS = [
    *ESPECIES_SIN_NORMALIZAR.values(),
    'n\u0303', 'gato\xa0montés', 'ßpecies', '\u200b', 'pe\u200b\u200drro', '\tperro\n',
    'gato\r\n\tmontés', '\u00a0\u2003perro\u3000', 'x' * 51,
]


@pytest.fixture
def datos_especies(app_bd_archivo):
    """Base en 0002 con especies escritas de varias formas, como antes de 0003."""
    upgrade(revision='0002')
    with db.engine.begin() as conexion:
        for numero, (nombre, especie) in enumerate(ESPECIES_SIN_NORMALIZAR.items(), start=1):
            conexion.execute(text(
                "INSERT INTO mascotas (id, nombre, especie, estado, fecha_ingreso, vacunado, esterilizado) "
                "VALUES (:id, :nombre, :especie, 'disponible', '2026-01-01 00:00:00', FALSE, FALSE)"),
                {'id': numero, 'nombre': nombre, 'especie': especie})


def test_0003_upgrade_normaliza_las_especies(datos_especies):
    upgrade(revision='0003')

    # La vacía y la que pasaría de 50 caracteres se dejan como están
    assert especies_de_mascotas() == {
        'Bien': 'Perro', 'Minusculas': 'Perro', 'Espacios': 'Perro', 'Gato': 'Gato',
        'Acento': 'Ñandú', 'DosPalabras': 'Cobaya de indias', 'Vacia': '   ',
        'Nfd': 'Ñandú', 'Nbsp': 'Cobaya de indias', 'AnchuraCero': 'Perro', 'Larga': 'ß' * 50,
    }


def test_0003_avisa_de_las_especies_que_no_puede_normalizar(datos_especies, caplog):
    """Se ejecuta el cuerpo directamente: env.py reconfigura el logging y caplog no lo vería."""
    migracion = cargar_migracion('0003_normalizar_especies.py')
    with caplog.at_level('WARNING', logger='alembic.runtime.migration'), db.engine.begin() as conexion, \
            Operations.context(MigrationContext.configure(conexion)):
        migracion.upgrade()

    avisos = [registro.getMessage() for registro in caplog.records if registro.levelname == 'WARNING']
    assert len(avisos) == 2
    assert any(repr('   ') in aviso and '[7]' in aviso for aviso in avisos)
    assert any(repr('ß' * 50) in aviso and '[11]' in aviso for aviso in avisos)


def test_0003_usa_el_mismo_criterio_que_el_modelo():
    """La migración copia la normalización del modelo; deben coincidir."""
    migracion = cargar_migracion('0003_normalizar_especies.py')
    assert migracion.LONGITUD_ESPECIE == Mascota.LONGITUD_ESPECIE
    for especie in ESPECIES_ADVERSAS:
        assert migracion.normalizar_especie(especie) == Mascota.normalizar_especie(especie), repr(especie)


def test_0003_upgrade_es_idempotente(datos_especies):
    upgrade(revision='0003')
    especies = especies_de_mascotas()

    migracion = cargar_migracion('0003_normalizar_especies.py')
    with db.engine.begin() as conexion, Operations.context(MigrationContext.configure(conexion)):
        migracion.upgrade()

    assert especies_de_mascotas() == especies


def test_0003_downgrade_no_cambia_los_datos(datos_especies):
    """El downgrade no hace nada: la forma original de cada especie no se guardó."""
    upgrade(revision='0003')
    especies = especies_de_mascotas()
    downgrade(revision='0002')

    assert especies_de_mascotas() == especies
