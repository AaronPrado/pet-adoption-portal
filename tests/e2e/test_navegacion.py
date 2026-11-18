"""
e2e de la navegación común: menú de usuario, menú móvil, CSRF, páginas de
error y el comportamiento de app.js en todos los formularios (foco en el
resumen de errores y protección contra el doble envío).
"""

import re

import pytest
from playwright.sync_api import expect

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
    registrar_envios(page)
    filtrar = page.get_by_role('button', name='Filtrar').element_handle()

    resultado = pulsar_seguido(page.locator('form').element_handle(), filtrar, filtrar)

    assert resultado['enviando'] == [False, False]
    assert resultado['envios'] == [False, False]
    page.wait_for_url(re.compile(r'/mascotas/catalogo\?'))


def test_cerrar_sesion_desde_el_menu(page, errores_js):
    iniciar_sesion(page, *ADOPTANTE)

    page.get_by_role('button', name='Ana').click()
    page.get_by_role('button', name='Cerrar Sesión').click()

    expect(page.get_by_text('Has cerrado sesión correctamente.')).to_be_visible()
    expect(page.get_by_role('link', name='Iniciar Sesión')).to_be_visible()


def test_menu_movil(page, errores_js):
    page.set_viewport_size({'width': 375, 'height': 800})
    page.goto('/')

    enlace = page.get_by_role('link', name='Mascotas', exact=True)
    expect(enlace).to_be_hidden()
    page.get_by_role('button', name='Mostrar u ocultar la navegación').click()
    expect(enlace).to_be_visible()


def test_formulario_sin_token_csrf_rechazado(page):
    """Un POST desde otra página sin token CSRF no inicia sesión."""
    page.goto('/auth/login')
    page.evaluate("""() => {
        const form = document.querySelector('form[action$="/auth/login"]');
        form.querySelector('input[name=csrf_token]').remove();
    }""")
    page.get_by_label('Email').fill(ADOPTANTE[0])
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
