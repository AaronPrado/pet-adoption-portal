"""
Tests de coherencia de los datos de prueba (`scripts_bd/02_seed.sql`).

El seed se carga en la SQLite en memoria de los tests (con el esquema de
`app/models.py`, que coincide con las migraciones) adaptando las dos únicas
sentencias propias de PostgreSQL. Así se comprueba sin PostgreSQL que los
datos cumplen las reglas de la app: cuestionarios válidos, estados derivados
del flujo (ADR-0004) y especies normalizadas. El job `migraciones` del CI lo
carga además en PostgreSQL real.
"""

import re
from pathlib import Path

import pytest

from app import cuestionario, db
from app.models import Mascota, Solicitud, Usuario

RUTA_SEED = Path(__file__).resolve().parent.parent / 'scripts_bd' / '02_seed.sql'


def sql_para_sqlite(sql):
    """Adapta el seed a SQLite: sin TRUNCATE (la BD ya está vacía) y NOW() estándar."""
    sql = re.sub(r'^TRUNCATE TABLE[^;]*;', '', sql, flags=re.MULTILINE)
    sql = sql.replace('NOW()', 'CURRENT_TIMESTAMP')
    # Si el seed cambia de formato, que el fallo diga qué no se ha adaptado
    assert 'TRUNCATE' not in sql, 'El seed tiene un TRUNCATE que no se ha podido quitar'
    assert 'NOW()' not in sql, 'El seed tiene un NOW() que no se ha podido adaptar'
    return sql


@pytest.fixture
def seed(app):
    """Carga el seed en la BD de testing."""
    conexion = db.engine.raw_connection()
    try:
        conexion.executescript(sql_para_sqlite(RUTA_SEED.read_text(encoding='utf-8')))
    finally:
        conexion.close()
    db.session.expire_all()


def como_formulario(respuestas):
    """Convierte un cuestionario guardado en el envío que lo produciría (True → 'si')."""
    def valor(v):
        if isinstance(v, bool):
            return 'si' if v else 'no'
        return v
    return {campo: valor(v) for campo, v in respuestas.items()}


def test_el_seed_crea_datos(seed):
    """El seed se carga y crea usuarios, mascotas y solicitudes."""
    assert db.session.query(Usuario).count() > 0
    assert db.session.query(Mascota).count() > 0
    assert db.session.query(Solicitud).count() > 0


def test_cuestionarios_tienen_las_claves_de_la_app(seed):
    """Cada cuestionario guarda exactamente las preguntas de `app/cuestionario.py`."""
    for solicitud in db.session.query(Solicitud):
        assert set(solicitud.cuestionario_json) == set(cuestionario.PREGUNTAS), solicitud.id


def test_cuestionarios_pasan_validar(seed):
    """Cada cuestionario es el resultado de validar un envío correcto."""
    for solicitud in db.session.query(Solicitud):
        guardado = solicitud.cuestionario_json
        limpio, errores = cuestionario.validar(como_formulario(guardado))
        assert errores == {}, (solicitud.id, errores)
        assert limpio == guardado, solicitud.id


def test_ninguna_mascota_en_proceso(seed):
    """El flujo ya no usa `en_proceso` (ADR-0004)."""
    assert db.session.query(Mascota).filter_by(estado='en_proceso').count() == 0


def test_mascota_con_solicitud_aprobada_esta_adoptada(seed):
    """Aprobar una solicitud adopta la mascota, y solo puede haber una aprobada."""
    for mascota in db.session.query(Mascota):
        aprobadas = mascota.solicitudes.filter_by(estado='aprobada').count()
        assert aprobadas <= 1, mascota.nombre
        if aprobadas:
            assert mascota.estado == 'adoptado', mascota.nombre


def test_mascota_adoptada_sin_solicitudes_pendientes(seed):
    """Al adoptar se rechazan las demás pendientes (ADR-0004)."""
    for mascota in db.session.query(Mascota).filter_by(estado='adoptado'):
        assert not mascota.tiene_solicitudes_pendientes(), mascota.nombre


def test_revision_coherente_con_el_estado(seed):
    """Las resueltas tienen fecha y revisor admin; las pendientes, no."""
    for solicitud in db.session.query(Solicitud):
        if solicitud.estado == 'pendiente':
            assert solicitud.fecha_revision is None, solicitud.id
            assert solicitud.revisado_por is None, solicitud.id
            assert solicitud.comentarios_admin is None, solicitud.id
        else:
            assert solicitud.fecha_revision >= solicitud.fecha_solicitud, solicitud.id
            revisor = db.session.get(Usuario, solicitud.revisado_por)
            assert revisor is not None and revisor.rol == 'admin', solicitud.id


def test_solicitud_posterior_al_ingreso_de_la_mascota(seed):
    """Nadie solicita una mascota antes de que llegue al refugio."""
    for solicitud in db.session.query(Solicitud):
        assert solicitud.fecha_solicitud >= solicitud.mascota.fecha_ingreso, solicitud.id


def test_especies_normalizadas(seed):
    """Las especies ya están en su forma canónica, como las guarda la app."""
    for mascota in db.session.query(Mascota):
        assert mascota.especie == Mascota.normalizar_especie(mascota.especie), mascota.nombre


def test_fotos_externas_https(seed):
    """Las fotos son URLs `https://` (el seed no añade archivos al repo)."""
    for mascota in db.session.query(Mascota):
        assert mascota.foto_url.startswith('https://'), mascota.nombre
