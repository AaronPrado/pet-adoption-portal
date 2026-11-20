"""
e2e de la navegación común: menú de usuario, menú móvil, CSRF, páginas de
error y el comportamiento de app.js en todos los formularios (foco en el
resumen de errores y protección contra el doble envío).
"""

import re

import pytest
from playwright.sync_api import expect

from app import db
from app.models import Usuario
from tests.e2e.conftest import ADOPTANTE, iniciar_sesion, pulsar_seguido, registrar_envios

pytestmark = pytest.mark.e2e

PRUEBA = '/_pruebas/formulario'


def test_foco_en_el_resumen_de_errores(page, errores_js):
    page.goto(f'{PRUEBA}?errores=1')

    resumen = page.get_by_role('group', name='Revisa estos campos antes de continuar')
    expect(resumen).to_be_focused()

    # Su enlace lleva al campo con el error
    page.get_by_role('link', name='Escribe un nombre.').click()
    expect(page.get_by_label('Nombre')).to_be_focused()


def test_sin_resumen_de_errores_no_mueve_el_foco(page, errores_js):
    page.goto(PRUEBA)
    assert page.evaluate('document.activeElement === document.body')


def test_doble_envio_se_ignora_y_llega_el_valor_del_boton(page, errores_js, retener):
    """El botón que envía no se deshabilita: su name/value llega al servidor."""
    retencion = retener(PRUEBA)
    page.goto(PRUEBA)
    registrar_envios(page)
    page.get_by_label('Nombre').fill('Toby')
    formulario = page.locator('form').element_handle()
    aprobar = page.get_by_role('button', name='Aprobar').element_handle()
    rechazar = page.get_by_role('button', name='Rechazar').element_handle()

    resultado = pulsar_seguido(formulario, rechazar, rechazar, aprobar)

    assert resultado == {'enviando': [True, True, True], 'envios': [False, True, True], 'deshabilitados': False}
    retencion.esperar()
    retencion.soltar()
    expect(page.get_by_text('nombre=Toby accion=rechazar')).to_be_visible()
    assert [envio['accion'] for envio in retencion.recibidos] == ['rechazar']


def test_validacion_html5_fallida_no_bloquea_el_formulario(page, errores_js, retener):
    retencion = retener(PRUEBA)
    page.goto(PRUEBA)
    registrar_envios(page)

    page.get_by_role('button', name='Aprobar').click()  # «Nombre» es obligatorio

    assert page.evaluate('window.envios') == []
    expect(page.locator('form')).not_to_have_attribute('aria-busy', 'true')
    page.get_by_label('Nombre').fill('Misu')
    resultado = pulsar_seguido(page.locator('form').element_handle(),
                               page.get_by_role('button', name='Aprobar').element_handle())
    assert resultado['enviando'] == [True]
    retencion.esperar()


def test_pageshow_reactiva_el_formulario(page, errores_js):
    """
    Al volver con «Atrás» desde la bfcache, la página reaparece tal cual se
    dejó. Chromium automatizado no usa la bfcache, así que se simula el evento
    en la misma tarea que el envío.
    """
    page.goto(PRUEBA)
    registrar_envios(page)
    page.get_by_label('Nombre').fill('Lur')

    resultado = page.get_by_role('button', name='Aprobar').evaluate("""(boton) => {
        const estados = [];
        boton.click();
        estados.push(boton.form.getAttribute('aria-busy'));
        window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}));
        estados.push(boton.form.getAttribute('aria-busy'));
        boton.click();
        return {estados, envios: window.envios};
    }""")

    assert resultado == {'estados': ['true', None], 'envios': [False, False]}
    expect(page.get_by_text('nombre=Lur accion=aprobar')).to_be_visible()


def test_envio_sin_respuesta_se_anuncia_y_se_libera(page, errores_js):
    """
    «Enviando…» se anuncia en una región role="status" (aria-busy no se lee),
    también al intentar un segundo envío. Si la respuesta no llega (aquí, un
    envío cancelado), el formulario se libera a los 10 s para reintentar.
    """
    page.clock.install()
    page.route(f'**{PRUEBA}',
               lambda ruta: ruta.abort('aborted') if ruta.request.method == 'POST' else ruta.continue_())
    page.goto(PRUEBA)
    estado = page.get_by_role('status')
    formulario = page.locator('form')
    page.get_by_label('Nombre').fill('Kira')

    page.get_by_role('button', name='Aprobar').click()
    expect(formulario).to_have_attribute('aria-busy', 'true')
    page.clock.run_for(100)
    expect(estado).to_have_text('Enviando…')

    registrar_envios(page)
    page.get_by_role('button', name='Aprobar').click()
    assert page.evaluate('window.envios') == [True]
    expect(estado).to_have_text('')  # se vacía y se repite el anuncio
    page.clock.run_for(100)
    expect(estado).to_have_text('Enviando…')

    page.clock.run_for(10_000)
    expect(formulario).not_to_have_attribute('aria-busy', 'true')
    expect(estado).to_have_text('')
    page.get_by_role('button', name='Aprobar').click()
    assert page.evaluate('window.envios') == [True, False]


def test_los_formularios_get_no_se_bloquean(page, errores_js):
    """Un filtro (GET) puede repetirse: no cambia nada en el servidor."""
    page.goto('/mascotas/catalogo')
    page.get_by_text('Filtrar mascotas').click()
    registrar_envios(page)
    filtrar = page.get_by_role('button', name='Filtrar').element_handle()

    resultado = pulsar_seguido(page.locator('form').element_handle(), filtrar, filtrar)

    assert resultado['enviando'] == [False, False]
    assert resultado['envios'] == [False, False]
    page.wait_for_url(re.compile(r'/mascotas/catalogo\?'))


def test_cerrar_sesion_desde_el_menu(page, errores_js):
    iniciar_sesion(page, *ADOPTANTE)  # termina en la portada
    expect(page.get_by_role('heading', level=1, name='Encuentra a tu compañero')).to_be_visible()
    expect(page.get_by_role('link', name='Crear mi cuenta')).to_have_count(0)

    page.get_by_role('button', name='Ana').click()
    page.get_by_role('button', name='Cerrar Sesión').click()

    expect(page.get_by_text('Has cerrado sesión correctamente.')).to_be_visible()
    expect(page.get_by_role('link', name='Iniciar Sesión')).to_be_visible()


def test_menu_movil_en_la_portada(page, errores_js):
    page.set_viewport_size({'width': 375, 'height': 800})
    page.goto('/')

    enlace = page.get_by_role('link', name='Mascotas', exact=True)
    expect(enlace).to_be_hidden()
    page.get_by_role('button', name='Menú').click()
    expect(enlace).to_be_visible()


def test_formulario_sin_token_csrf_rechazado(page):
    """Un POST desde otra página sin token CSRF no inicia sesión."""
    page.goto('/auth/login')
    page.evaluate("""() => {
        const form = document.querySelector('form[action$="/auth/login"]');
        form.querySelector('input[name=csrf_token]').remove();
    }""")
    page.get_by_label('Correo electrónico').fill(ADOPTANTE[0])
    page.get_by_label('Contraseña').fill(ADOPTANTE[1])
    page.get_by_role('button', name='Iniciar Sesión').click()

    expect(page.get_by_role('heading', name='Tu sesión ha caducado')).to_be_visible()
    volver = page.get_by_role('link', name='Volver al formulario')
    expect(volver).to_have_attribute('href', '/auth/login')
    volver.click()
    expect(page).to_have_url(re.compile(r'/auth/login$'))


def test_pagina_404_con_salida(page, errores_js):
    page.goto('/mascotas/99999')

    expect(page.get_by_role('heading', name='No encontramos esta página')).to_be_visible()
    page.get_by_role('link', name='Ver mascotas disponibles').click()
    expect(page).to_have_url(re.compile(r'/mascotas/catalogo$'))


# --- Base sin Bootstrap (base.html): de momento solo la usan las páginas de error ---

def test_base_nueva_menu_movil_con_teclado(page, errores_js):
    """A 375 px el menú se abre con Enter o Espacio y se cierra con Escape,
    que devuelve el foco al botón. El primer Tab llega al salto al contenido."""
    page.set_viewport_size({'width': 375, 'height': 800})
    page.goto('/no-existe')
    menu = page.get_by_role('button', name='Menú')
    mascotas = page.get_by_role('link', name='Mascotas', exact=True)

    page.keyboard.press('Tab')
    salto = page.get_by_role('link', name='Saltar al contenido')
    expect(salto).to_be_focused()
    expect(salto).to_be_visible()
    page.keyboard.press('Enter')
    expect(page.get_by_role('main')).to_be_focused()

    page.goto('/no-existe')
    expect(menu).to_have_attribute('aria-expanded', 'false')
    expect(mascotas).to_be_hidden()
    menu.focus()
    page.keyboard.press('Enter')
    expect(menu).to_have_attribute('aria-expanded', 'true')
    expect(mascotas).to_be_visible()
    page.keyboard.press('Escape')
    expect(mascotas).to_be_hidden()
    expect(menu).to_be_focused()

    page.keyboard.press('Space')
    expect(mascotas).to_be_visible()
    page.keyboard.press('Tab')
    expect(page.get_by_role('link', name='Inicio', exact=True)).to_be_focused()
    page.keyboard.press('Escape')
    expect(menu).to_be_focused()
    expect(menu).to_have_attribute('aria-expanded', 'false')

    # Sin scroll horizontal ni a 320 px, con el menú abierto
    page.set_viewport_size({'width': 320, 'height': 800})
    menu.click()
    expect(mascotas).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth') <= 320


def test_base_nueva_sin_javascript(browser, base_url):
    """Sin JS la navegación se ve abierta, sin botón de menú, y funciona."""
    contexto = browser.new_context(java_script_enabled=False, base_url=base_url,
                                   viewport={'width': 375, 'height': 800})
    page = contexto.new_page()
    try:
        page.goto('/no-existe')

        expect(page.get_by_role('button', name='Menú')).to_be_hidden()
        for nombre in ('Inicio', 'Iniciar Sesión', 'Registrarse'):
            expect(page.get_by_role('link', name=nombre, exact=True)).to_be_visible()
        page.get_by_role('link', name='Mascotas', exact=True).click()
        expect(page).to_have_url(re.compile(r'/mascotas/catalogo$'))
    finally:
        contexto.close()


def test_base_nueva_desplegable_de_usuario(page, errores_js):
    iniciar_sesion(page, *ADOPTANTE)
    page.goto('/no-existe')
    usuario = page.get_by_role('button', name='Ana')
    mis_solicitudes = page.get_by_role('link', name='Mis Solicitudes')

    expect(usuario).to_have_attribute('aria-expanded', 'false')
    expect(mis_solicitudes).to_be_hidden()

    # Clic fuera cierra
    usuario.click()
    expect(mis_solicitudes).to_be_visible()
    page.get_by_role('heading', name='No encontramos esta página').click()
    expect(mis_solicitudes).to_be_hidden()

    # Escape cierra y devuelve el foco
    usuario.focus()
    page.keyboard.press('Enter')
    page.keyboard.press('Tab')
    expect(mis_solicitudes).to_be_focused()
    page.keyboard.press('Escape')
    expect(mis_solicitudes).to_be_hidden()
    expect(usuario).to_be_focused()

    # Si el foco sale del menú, se cierra
    page.keyboard.press('Enter')
    page.keyboard.press('Tab')
    page.keyboard.press('Tab')
    expect(page.get_by_role('button', name='Cerrar Sesión')).to_be_focused()
    page.keyboard.press('Tab')
    expect(mis_solicitudes).to_be_hidden()
    expect(usuario).to_have_attribute('aria-expanded', 'false')

    # Cerrar sesión por POST con su token CSRF
    usuario.click()
    page.get_by_role('button', name='Cerrar Sesión').click()
    expect(page.get_by_text('Has cerrado sesión correctamente.')).to_be_visible()


NOMBRE_LARGO = 'Maximilianaconunnombrelarguisimoquenocabeenningunapantalla'


@pytest.fixture
def usuario_de_nombre_largo(app_e2e):
    """Un adoptante con un nombre sin espacios más ancho que la pantalla y una
    marca igual de larga, para comprobar el reflow (WCAG 1.4.10)."""
    email, clave = 'largo@e2e.test', 'clave-largo-e2e'
    with app_e2e.app_context():
        if not db.session.execute(db.select(Usuario).filter_by(email=email)).scalar():
            db.session.add(Usuario(email=email, nombre=NOMBRE_LARGO, password=clave))
            db.session.commit()
    nombre_marca = app_e2e.config['MARCA_NOMBRE']
    app_e2e.config['MARCA_NOMBRE'] = 'Asociación protectora de animales abandonados de la comarca'
    yield email, clave
    app_e2e.config['MARCA_NOMBRE'] = nombre_marca


@pytest.mark.parametrize('ancho', [320, 800])
def test_base_nueva_sin_scroll_horizontal_con_textos_largos(page, errores_js, usuario_de_nombre_largo, ancho):
    iniciar_sesion(page, *usuario_de_nombre_largo)
    page.set_viewport_size({'width': ancho, 'height': 800})
    page.goto('/no-existe')

    if ancho < 768:
        page.get_by_role('button', name='Menú').click()
    page.get_by_role('button', name=NOMBRE_LARGO).click()
    expect(page.get_by_role('link', name='Mis Solicitudes')).to_be_visible()

    assert page.evaluate('document.documentElement.scrollWidth') <= ancho


def test_base_nueva_aria_controls_roto_no_da_errores(page, errores_js):
    """Un desplegable cuyo aria-controls no existe se ignora sin errores de
    JavaScript y el resto sigue funcionando."""
    def con_id_roto(ruta):
        respuesta = ruta.fetch()
        html = respuesta.text().replace('aria-controls="menu-usuario"', 'aria-controls="no-existe"', 1)
        ruta.fulfill(response=respuesta, body=html)

    iniciar_sesion(page, *ADOPTANTE)
    page.route('**/no-existe', con_id_roto)
    page.goto('/no-existe')

    page.get_by_role('button', name='Ana').click()
    page.keyboard.press('Escape')
    page.get_by_role('heading', name='No encontramos esta página').click()
    page.set_viewport_size({'width': 375, 'height': 800})
    menu = page.get_by_role('button', name='Menú')
    menu.click()
    expect(menu).to_have_attribute('aria-expanded', 'true')


# --- Portada (B4.1) ---

def test_portada_imagen_principal_del_propio_origen(page, errores_js, base_url):
    """El hero carga desde /static (nada de terceros), en la variante que toca."""
    peticiones = []
    page.on('request', lambda peticion: peticiones.append(peticion.url))
    page.set_viewport_size({'width': 375, 'height': 800})
    page.goto('/')

    imagen = page.locator('img.inicio-hero__imagen')
    expect(imagen).to_be_visible()
    page.wait_for_function('document.querySelector("img.inicio-hero__imagen").complete')
    assert page.evaluate('document.querySelector("img.inicio-hero__imagen").naturalWidth') > 0
    actual = page.evaluate('document.querySelector("img.inicio-hero__imagen").currentSrc')
    assert actual == f'{base_url}/static/img/hero-640.webp'
    hero = [url for url in peticiones if 'hero' in url or 'photo-1450778869180' in url]
    assert hero == [f'{base_url}/static/img/hero-640.webp']


def test_portada_un_h1_y_recorrido_de_adopcion(page, errores_js):
    page.goto('/')

    expect(page.get_by_role('heading', level=1)).to_have_count(1)
    pasos = page.get_by_role('list').filter(has=page.get_by_role('heading', name='Crea tu cuenta'))
    expect(pasos.get_by_role('listitem')).to_have_count(4)


@pytest.mark.parametrize('ancho', [320, 375, 1280])
def test_portada_sin_scroll_horizontal(page, errores_js, ancho):
    page.set_viewport_size({'width': ancho, 'height': 800})
    page.goto('/')

    assert page.evaluate('document.documentElement.scrollWidth') <= ancho
