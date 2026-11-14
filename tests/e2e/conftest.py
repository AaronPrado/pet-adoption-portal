"""
Infraestructura de los tests end-to-end con Playwright.

Arranca la app real en un hilo (con CSRF activado, a diferencia de los tests
unitarios) sobre una base de datos SQLite temporal y abre las páginas en
Chromium. Se ejecutan con:

    python -m pytest -m e2e
"""

import threading

import pytest
from werkzeug.serving import make_server

from app import create_app, db
from app.models import Mascota, Usuario
from config import TestingConfig, config

ADMIN = ('admin@e2e.test', 'clave-admin-e2e')
ADOPTANTE = ('adoptante@e2e.test', 'clave-adoptante-e2e')


@pytest.fixture(scope='session')
def servidor(tmp_path_factory):
    class E2EConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path_factory.mktemp('e2e') / 'e2e.db'}"
        WTF_CSRF_ENABLED = True

    config['e2e'] = E2EConfig
    app = create_app('e2e')

    with app.app_context():
        db.create_all()
        db.session.add_all([
            Usuario(email=ADMIN[0], nombre='Admin', password=ADMIN[1], rol='admin'),
            Usuario(email=ADOPTANTE[0], nombre='Ana', password=ADOPTANTE[1]),
            Mascota(nombre='Toby', especie='Perro', descripcion='Perro tranquilo y cariñoso', edad_aprox=3,
                    foto_url='https://images.unsplash.com/photo-1587300003388-59208cc962cb'),
            Mascota(nombre='Misu', especie='Gato', descripcion='Gata curiosa y juguetona', edad_aprox=2),
        ])
        db.session.commit()

    servidor = make_server('127.0.0.1', 0, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f'http://127.0.0.1:{servidor.server_port}'
    servidor.shutdown()
    del config['e2e']


@pytest.fixture(scope='session')
def base_url(servidor):
    """pytest-playwright resuelve las URLs relativas de page.goto() con esta base."""
    return servidor


@pytest.fixture
def errores_js(page):
    """
    Falla el test si la página tiene errores de JavaScript o la CSP bloquea algo.

    Los fallos de carga de recursos externos (fotos de ejemplo) no cuentan.
    """
    errores = []
    page.on('pageerror', lambda error: errores.append(str(error)))
    page.on('console', lambda m: m.type == 'error' and 'Content Security Policy' in m.text
            and errores.append(m.text))
    yield errores
    assert errores == []


def iniciar_sesion(page, email, password):
    page.goto('/auth/login')
    page.get_by_label('Email').fill(email)
    page.get_by_label('Contraseña').fill(password)
    page.get_by_role('button', name='Iniciar Sesión').click()
    page.wait_for_url('**/')
