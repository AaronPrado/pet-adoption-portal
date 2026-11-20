"""
Infraestructura de los tests end-to-end con Playwright.

Arranca la app real en un hilo (con CSRF activado, a diferencia de los tests
unitarios) sobre una base de datos SQLite temporal y abre las páginas en
Chromium. Se ejecutan con:

    python -m pytest -m e2e

Los tests van en un módulo por área (`test_navegacion.py`, `test_catalogo.py`,
`test_solicitud.py` y `test_admin.py`) y localizan los elementos por rol, por
etiqueta o por texto accesible, no por clases de Bootstrap ni por la
estructura del HTML, para que sobrevivan al rediseño.
"""

import threading

import pytest
from flask import Blueprint, render_template_string, request
from werkzeug.serving import make_server

from app import create_app, db
from app.models import Mascota, Usuario
from config import TestingConfig, config

ADMIN = ('admin@e2e.test', 'clave-admin-e2e')
ADOPTANTE = ('adoptante@e2e.test', 'clave-adoptante-e2e')

# Página que solo existe en los e2e (solo se registra en app_e2e): prueba
# app.js en un formulario con varios botones submit con name/value y un
# resumen de errores, en HTML plano y sin depender de ninguna plantilla.
PAGINA_DE_PRUEBA = '''<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Formulario de prueba</title></head>
<body>
<main>
  {% if errores %}
  <div tabindex="-1" role="group" aria-labelledby="resumen-titulo" data-resumen-errores>
    <h2 id="resumen-titulo">Revisa estos campos antes de continuar</h2>
    <ul><li><a href="#nombre">Escribe un nombre.</a></li></ul>
  </div>
  {% endif %}
  <form method="POST" action="{{ url_for('pruebas.formulario') }}">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <label for="nombre">Nombre</label>
    <input id="nombre" name="nombre" required>
    <button type="submit" name="accion" value="aprobar">Aprobar</button>
    <button type="submit" name="accion" value="rechazar">Rechazar</button>
  </form>
</main>
<script src="{{ url_for('static', filename='js/app.js') }}"></script>
</body>
</html>'''

pruebas = Blueprint('pruebas', __name__, url_prefix='/_pruebas')


@pruebas.route('/formulario', methods=['GET', 'POST'])
def formulario():
    """GET pinta el formulario (`?errores=1` con el resumen); POST responde en texto plano lo recibido."""
    if request.method == 'POST':
        cuerpo = f'nombre={request.form.get("nombre")} accion={request.form.get("accion")}'
        return cuerpo, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    return render_template_string(PAGINA_DE_PRUEBA, errores=bool(request.args.get('errores')))


class Retencion:
    """
    Retiene en el servidor los POST a una ruta hasta `soltar()`, como un
    servidor lento: mientras, la página sigue con el formulario «enviando».
    """

    def __init__(self, ruta):
        self.ruta = ruta
        self.recibidos = []  # request.form de cada POST que llegó
        self._llegadas = threading.Semaphore(0)
        self._suelta = threading.Event()

    def retener(self):
        if request.method == 'POST' and request.path == self.ruta:
            self.recibidos.append(request.form.to_dict())
            self._llegadas.release()
            self._suelta.wait(timeout=30)

    def esperar(self, cuantos=1):
        """Espera (sin sondear) a que lleguen `cuantos` POST más, como mucho 5 s cada uno."""
        for _ in range(cuantos):
            assert self._llegadas.acquire(timeout=5), f'No ha llegado ningún POST a {self.ruta}'

    def soltar(self):
        self._suelta.set()


_RETENCIONES = []


@pytest.fixture(scope='session')
def app_e2e(tmp_path_factory):
    """La app con CSRF activado y la semilla de los e2e en una SQLite temporal."""
    class E2EConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path_factory.mktemp('e2e') / 'e2e.db'}"
        WTF_CSRF_ENABLED = True
        FOTOS_DIR = str(tmp_path_factory.mktemp('fotos'))

    config['e2e'] = E2EConfig
    app = create_app('e2e')
    app.register_blueprint(pruebas)

    @app.before_request
    def aplicar_retenciones():
        for retencion in list(_RETENCIONES):
            retencion.retener()

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

    yield app
    del config['e2e']


@pytest.fixture(scope='session')
def servidor(app_e2e):
    servidor = make_server('127.0.0.1', 0, app_e2e, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    yield f'http://127.0.0.1:{servidor.server_port}'
    servidor.shutdown()


@pytest.fixture(scope='session')
def mascotas(app_e2e):
    """Id de cada mascota por su nombre, para entrar directamente en su ficha."""
    with app_e2e.app_context():
        return {nombre: id_ for nombre, id_ in db.session.execute(db.select(Mascota.nombre, Mascota.id))}


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


@pytest.fixture
def retener(servidor):
    """Devuelve una función que crea una Retencion para una ruta; al acabar las suelta todas."""
    creadas = []

    def crear(ruta):
        retencion = Retencion(ruta)
        creadas.append(retencion)
        _RETENCIONES.append(retencion)
        return retencion

    yield crear
    for retencion in creadas:
        retencion.soltar()
        _RETENCIONES.remove(retencion)


def pulsar_seguido(formulario, *botones):
    """
    Pulsa los botones uno tras otro, como un usuario impaciente.

    Con un envío en marcha, Playwright espera a que termine la navegación
    antes de cualquier otra acción o consulta. Por eso los clics y sus
    comprobaciones van en una sola tarea de la página, antes de que la
    navegación empiece. Recibe ElementHandle (obtenidos por rol) y devuelve si
    el formulario quedó con aria-busy tras cada clic y `window.envios`.
    """
    return formulario.evaluate("""(formulario, botones) => {
        const enviando = botones.map((boton) => {
            boton.click();
            return formulario.getAttribute('aria-busy') === 'true';
        });
        return {enviando, envios: window.envios, deshabilitados: botones.some((boton) => boton.disabled)};
    }""", list(botones))


def registrar_envios(page):
    """Apunta en `window.envios` si cada evento submit acabó cancelado (True) o no."""
    page.evaluate("""() => {
        window.envios = [];
        window.addEventListener('submit', (evento) => window.envios.push(evento.defaultPrevented));
    }""")


def iniciar_sesion(page, email, password):
    page.goto('/auth/login')
    page.get_by_label('Correo electrónico').fill(email)
    page.get_by_label('Contraseña').fill(password)
    page.get_by_role('button', name='Iniciar Sesión').click()
    page.wait_for_url('**/')
