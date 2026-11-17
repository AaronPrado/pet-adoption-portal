"""
Tests de la configuración por entornos.
"""

import pytest

from app import create_app
from config import ProductionConfig, config


@pytest.fixture
def config_produccion(monkeypatch):
    """Configura ProductionConfig con valores válidos (BD SQLite en memoria)."""
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 's' * 32)
    monkeypatch.setattr(ProductionConfig, 'JWT_SECRET_KEY', 'j' * 32)
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    return ProductionConfig


@pytest.mark.parametrize('variable', ['SECRET_KEY', 'JWT_SECRET_KEY', 'SQLALCHEMY_DATABASE_URI'])
def test_produccion_exige_variables(config_produccion, monkeypatch, variable):
    """Producción no arranca si falta un secreto o la BD."""
    monkeypatch.setattr(config_produccion, variable, None)

    with pytest.raises(RuntimeError, match=variable):
        create_app('production')


@pytest.mark.parametrize('variable', ['SECRET_KEY', 'JWT_SECRET_KEY'])
def test_produccion_exige_claves_largas(config_produccion, monkeypatch, variable):
    """Una clave de menos de 32 bytes se rechaza al arrancar."""
    monkeypatch.setattr(config_produccion, variable, 'x' * 31)

    with pytest.raises(RuntimeError, match=f'{variable} debe tener al menos 32 bytes'):
        create_app('production')


def test_produccion_arranca_con_variables(config_produccion):
    """Con todas las variables definidas la app se crea."""
    app = create_app('production')
    assert app.config['DEBUG'] is False


def test_produccion_oculta_swagger(config_produccion):
    """La documentación Swagger no se publica en producción."""
    client = create_app('production').test_client()

    assert client.get('/api/docs').status_code == 404
    assert client.get('/api/swagger.json').status_code == 404


def test_desarrollo_publica_swagger(client):
    """En testing/desarrollo Swagger sigue disponible."""
    assert client.get('/api/docs').status_code == 200


def test_driver_postgresql_instalado():
    """Las URLs postgresql:// de DATABASE_URL deben poder crear un engine.

    SQLAlchemy 2.1 cambió el driver por defecto de psycopg2 a psycopg (v3);
    create_engine importa el driver aunque no llegue a conectar.
    """
    from sqlalchemy import create_engine

    engine = create_engine('postgresql://usuario:clave@localhost:5432/bd')
    assert engine.dialect.driver == 'psycopg'


def test_postgresql_con_timeouts(config_produccion, monkeypatch):
    """Con PostgreSQL se configuran timeouts para no colgar peticiones."""
    monkeypatch.setattr(config_produccion, 'SQLALCHEMY_DATABASE_URI', 'postgresql://u:c@localhost/bd')

    opciones = create_app('production').config['SQLALCHEMY_ENGINE_OPTIONS']

    assert opciones['pool_pre_ping'] is True
    assert opciones['connect_args'] == {'connect_timeout': 5, 'tcp_user_timeout': 5000}


def test_sqlite_sin_opciones_de_postgresql(app):
    assert 'connect_args' not in app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})


@pytest.mark.parametrize('nombre', ['development', 'production', 'testing'])
def test_token_csrf_dura_lo_que_la_sesion(config_produccion, nombre):
    """Sin límite de tiempo, quien tarda en rellenar el cuestionario no pierde el envío."""
    assert create_app(nombre).config['WTF_CSRF_TIME_LIMIT'] is None


@pytest.mark.parametrize('nombre', ['production', 'testing'])
def test_backend_de_fotos_desconocido_no_arranca(config_produccion, monkeypatch, nombre):
    """Un FOTOS_BACKEND mal escrito falla al arrancar, no al subir la primera foto."""
    monkeypatch.setattr(config[nombre], 'FOTOS_BACKEND', 'gcs')

    with pytest.raises(RuntimeError, match="FOTOS_BACKEND no válido: 'gcs'"):
        create_app(nombre)


def test_produccion_local_exige_fotos_dir(config_produccion, monkeypatch):
    """En un PaaS con disco efímero, instance/fotos se perdería en cada despliegue."""
    monkeypatch.setattr(config_produccion, 'FOTOS_BACKEND', 'local')
    monkeypatch.setattr(config_produccion, 'FOTOS_DIR', None)

    with pytest.raises(RuntimeError, match="FOTOS_BACKEND='local' exige FOTOS_DIR"):
        create_app('production')


def test_produccion_local_con_fotos_dir(config_produccion, monkeypatch, tmp_path):
    monkeypatch.setattr(config_produccion, 'FOTOS_BACKEND', 'local')
    monkeypatch.setattr(config_produccion, 'FOTOS_DIR', str(tmp_path))

    assert create_app('production').config['FOTOS_DIR'] == str(tmp_path)


@pytest.mark.parametrize('backend', ['', 's3'])
def test_produccion_sin_backend_o_con_s3_no_exige_fotos_dir(config_produccion, monkeypatch, backend):
    monkeypatch.setattr(config_produccion, 'FOTOS_BACKEND', backend)
    monkeypatch.setattr(config_produccion, 'FOTOS_DIR', None)
    monkeypatch.setattr(config_produccion, 'AWS_S3_BUCKET', 'bucket')

    assert create_app('production').config['FOTOS_BACKEND'] == backend


def test_produccion_s3_exige_bucket(config_produccion, monkeypatch):
    """Sin bucket, el backend s3 no puede guardar nada: mejor fallar al arrancar."""
    monkeypatch.setattr(config_produccion, 'FOTOS_BACKEND', 's3')
    monkeypatch.setattr(config_produccion, 'AWS_S3_BUCKET', None)

    with pytest.raises(RuntimeError, match="FOTOS_BACKEND='s3' exige AWS_S3_BUCKET"):
        create_app('production')
