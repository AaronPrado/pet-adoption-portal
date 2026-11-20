"""
e2e de la autenticación: registro con `next`, login fallido (error en el
campo y foco en el resumen) y la página 429 en español.
"""

import re
import threading

import pytest
from playwright.sync_api import expect
from werkzeug.serving import make_server

from app import create_app, db, limiter
from app.models import Usuario
from config import TestingConfig, config
from tests.e2e.conftest import ADOPTANTE

pytestmark = pytest.mark.e2e

CLAVE = 'clave-registro-e2e'


def contrasena(page):
    return page.get_by_label(re.compile('^Contraseña'))


def test_registro_con_next_vuelve_al_cuestionario(page, errores_js, mascotas):
    """Quien se registra al ir a adoptar acaba en el cuestionario, ya con sesión."""
    page.goto(f'/auth/registro?next=/solicitudes/nueva/{mascotas["Misu"]}')
    expect(page.get_by_role('heading', level=1, name='Crear cuenta')).to_be_visible()

    page.get_by_label('Correo electrónico').fill('nueva.persona@e2e.test')
    page.get_by_label(re.compile('^Nombre')).fill('Noa')
    page.get_by_label('Apellidos').fill('Vidal')
    contrasena(page).fill(CLAVE)
    page.get_by_label('Confirma la contraseña').fill(CLAVE)
    page.get_by_role('button', name='Crear cuenta').click()

    expect(page).to_have_url(re.compile(rf'/solicitudes/nueva/{mascotas["Misu"]}$'))
    expect(page.get_by_text('Cuenta creada. ¡Hola, Noa!')).to_be_visible()


def test_registro_con_error_marca_el_campo_y_enfoca_el_resumen(page, errores_js):
    page.goto('/auth/registro')
    page.get_by_label('Correo electrónico').fill('otra@e2e.test')
    page.get_by_label(re.compile('^Nombre')).fill('Iker')
    page.get_by_label('Teléfono').fill('612345678')
    contrasena(page).fill(CLAVE)
    page.get_by_label('Confirma la contraseña').fill('distinta-1234')
    page.get_by_role('button', name='Crear cuenta').click()

    resumen = page.get_by_role('group', name='Revisa estos campos antes de continuar')
    expect(resumen).to_be_focused()
    expect(page.get_by_label('Confirma la contraseña')).to_have_attribute('aria-invalid', 'true')
    # Lo escrito se conserva, salvo las contraseñas
    expect(page.get_by_label('Teléfono')).to_have_value('612345678')
    expect(contrasena(page)).to_have_value('')

    # El enlace del resumen lleva al campo
    resumen.get_by_role('link', name='Las contraseñas no coinciden.').click()
    expect(page.get_by_label('Confirma la contraseña')).to_be_focused()


def test_login_fallido_muestra_el_error_en_el_campo_y_enfoca_el_resumen(page, errores_js):
    page.goto('/auth/login?next=/mascotas/catalogo')
    page.get_by_label('Correo electrónico').fill(ADOPTANTE[0])
    contrasena(page).fill('clave-equivocada')
    page.get_by_role('button', name='Iniciar sesión').click()

    resumen = page.get_by_role('group', name='Revisa estos campos antes de continuar')
    expect(resumen).to_be_focused()
    expect(resumen.get_by_role('link', name='Correo o contraseña incorrectos.')).to_be_visible()
    campo = contrasena(page)
    expect(campo).to_have_attribute('aria-invalid', 'true')
    expect(campo).to_have_accessible_description(re.compile('Correo o contraseña incorrectos'))
    expect(campo).to_have_value('')
    expect(page.get_by_label('Correo electrónico')).to_have_value(ADOPTANTE[0])

    # El destino sobrevive al intento fallido
    contrasena(page).fill(ADOPTANTE[1])
    page.get_by_role('button', name='Iniciar sesión').click()
    expect(page).to_have_url(re.compile(r'/mascotas/catalogo$'))


@pytest.fixture
def servidor_con_limite(tmp_path):
    """
    Una app aparte, con el límite de intentos activado, para que el 429 no
    afecte a los demás e2e (su app lo desactiva). Tiene su propia base de datos.
    """
    class LimiteConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{tmp_path / "limite.db"}'
        WTF_CSRF_ENABLED = True
        FOTOS_DIR = str(tmp_path / 'fotos')
        RATELIMIT_ENABLED = True
        RATELIMIT_LOGIN = '3 per minute'

    config['e2e_limite'] = LimiteConfig
    app = create_app('e2e_limite')
    with app.app_context():
        db.create_all()
        db.session.add(Usuario(email=ADOPTANTE[0], nombre='Ana', password=ADOPTANTE[1]))
        db.session.commit()
    servidor = make_server('127.0.0.1', 0, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        yield f'http://127.0.0.1:{servidor.server_port}'
    finally:
        try:
            servidor.shutdown()
        finally:
            # El limitador es global: se deja como lo dejan los tests (desactivado)
            limiter.enabled = False
            del config['e2e_limite']


def test_demasiados_intentos_de_login_muestran_la_429_en_espanol(page, servidor_con_limite):
    for _ in range(3):
        page.goto(f'{servidor_con_limite}/auth/login')
        page.get_by_label('Correo electrónico').fill(ADOPTANTE[0])
        contrasena(page).fill('clave-equivocada')
        page.get_by_role('button', name='Iniciar sesión').click()
        expect(page.get_by_role('group', name='Revisa estos campos antes de continuar')).to_be_visible()

    page.get_by_label('Correo electrónico').fill(ADOPTANTE[0])
    contrasena(page).fill(ADOPTANTE[1])
    with page.expect_response(re.compile('/auth/login$')) as respuesta:
        page.get_by_role('button', name='Iniciar sesión').click()

    assert respuesta.value.status == 429
    assert respuesta.value.headers['retry-after']
    expect(page.get_by_role('heading', level=1, name='Has hecho demasiados intentos')).to_be_visible()
    expect(page.get_by_text(re.compile(r'Espera (un minuto|\d+ minutos) y vuelve a intentarlo'))).to_be_visible()
    expect(page.locator('html')).to_have_attribute('lang', 'es')
