"""
Tests de la configuración por entornos.
"""

import pytest

from app import create_app
from config import ProductionConfig


@pytest.fixture
def config_produccion(monkeypatch):
    """Configura ProductionConfig con valores válidos (BD SQLite en memoria)."""
    monkeypatch.setattr(ProductionConfig, 'SECRET_KEY', 'clave-prod')
    monkeypatch.setattr(ProductionConfig, 'JWT_SECRET_KEY', 'clave-jwt-prod')
    monkeypatch.setattr(ProductionConfig, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///:memory:')
    return ProductionConfig


@pytest.mark.parametrize('variable', ['SECRET_KEY', 'JWT_SECRET_KEY', 'SQLALCHEMY_DATABASE_URI'])
def test_produccion_exige_variables(config_produccion, monkeypatch, variable):
    """Producción no arranca si falta un secreto o la BD."""
    monkeypatch.setattr(config_produccion, variable, None)

    with pytest.raises(RuntimeError, match=variable):
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
