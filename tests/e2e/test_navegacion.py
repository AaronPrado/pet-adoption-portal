"""e2e de la navegación común: menú de usuario, menú móvil, CSRF y páginas de error."""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import ADOPTANTE, iniciar_sesion

pytestmark = pytest.mark.e2e


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
