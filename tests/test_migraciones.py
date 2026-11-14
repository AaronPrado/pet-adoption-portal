"""
Tests de las migraciones de Alembic (Flask-Migrate).

Se aplican sobre una base de datos SQLite en un archivo temporal; el job
"migraciones" del CI las prueba además contra PostgreSQL.
"""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect

from app import create_app, db
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
