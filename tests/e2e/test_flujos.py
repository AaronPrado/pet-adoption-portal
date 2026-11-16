"""
Flujos completos en el navegador: comprueban lo que los tests unitarios no
ven (JavaScript, CSP, CSRF con formularios reales, menú móvil).
"""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import ADMIN, ADOPTANTE, iniciar_sesion

pytestmark = pytest.mark.e2e


def test_catalogo_publico(page, errores_js):
    page.goto('/mascotas/catalogo')

    expect(page.get_by_role('heading', name='Toby')).to_be_visible()
    page.get_by_label('Especie').select_option('Gato')
    page.get_by_role('button', name='Filtrar').click()

    expect(page.get_by_role('heading', name='Misu')).to_be_visible()
    expect(page.get_by_role('heading', name='Toby')).to_have_count(0)


def test_adoptante_envia_solicitud(page, errores_js):
    iniciar_sesion(page, *ADOPTANTE)

    page.goto('/mascotas/catalogo')
    tarjeta = page.locator('.card').filter(has=page.get_by_role('heading', name='Toby'))
    tarjeta.get_by_role('link').first.click()
    expect(page).to_have_url(re.compile(r'/mascotas/\d+$'))
    page.get_by_role('link', name='Solicitar Adopción').click()

    page.locator('#vivienda_tipo').select_option(index=1)
    page.locator('#vivienda_propia').select_option(index=1)
    page.locator('#jardin_si').check()
    page.locator('#mascotas_no').check()
    page.locator('#experiencia_previa').fill('He tenido perros toda la vida')
    page.locator('#horas_solo').select_option(index=1)
    page.locator('#emergencia_veterinaria').select_option(index=1)
    page.locator('#motivo_adopcion').fill('Quiero darle un hogar a un perro tranquilo')
    page.locator('#gastos_si').check()
    page.locator('#tiempo_si').check()
    page.get_by_role('button', name=re.compile('Enviar')).click()

    expect(page).to_have_url(re.compile('/solicitudes/mis-solicitudes'))
    expect(page.get_by_text('Solicitud enviada con éxito para Toby')).to_be_visible()


def test_login_desde_la_ficha_vuelve_al_cuestionario(page, errores_js):
    """El anónimo que pulsa «Inicia sesión para adoptar» acaba en el cuestionario."""
    page.goto('/mascotas/catalogo')
    tarjeta = page.locator('.card').filter(has=page.get_by_role('heading', name='Misu'))
    tarjeta.get_by_role('link').first.click()
    page.get_by_role('link', name='Inicia sesión para adoptar').click()

    # Un primer intento fallido conserva el correo y el destino
    page.get_by_label('Email').fill(ADOPTANTE[0])
    page.get_by_label('Contraseña').fill('clave-equivocada')
    page.get_by_role('button', name='Iniciar Sesión').click()
    expect(page.get_by_text('Email o contraseña incorrectos.')).to_be_visible()
    expect(page.get_by_label('Email')).to_have_value(ADOPTANTE[0])
    expect(page.get_by_label('Contraseña')).to_have_value('')

    page.get_by_label('Contraseña').fill(ADOPTANTE[1])
    page.get_by_role('button', name='Iniciar Sesión').click()

    expect(page).to_have_url(re.compile(r'/solicitudes/nueva/\d+$'))
    expect(page.get_by_text('Misu').first).to_be_visible()


def test_admin_crea_y_borra_mascota(page, errores_js):
    iniciar_sesion(page, *ADMIN)

    page.goto('/mascotas/admin/nueva')
    page.get_by_label('Nombre').fill('Rex')
    page.get_by_label('Especie').fill('Perro')
    page.get_by_label('Descripción').fill('Perro grande y bonachón')
    page.get_by_role('button', name='Crear Mascota').click()
    expect(page.get_by_text('Mascota "Rex" creada exitosamente.')).to_be_visible()

    # Cancelar la confirmación no borra nada
    page.once('dialog', lambda dialog: dialog.dismiss())
    page.get_by_role('button', name='Eliminar Rex').click()
    expect(page.get_by_role('button', name='Eliminar Rex')).to_be_visible()

    # Aceptarla envía el formulario (con su token CSRF)
    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Eliminar Rex').click()
    expect(page.get_by_text('Mascota "Rex" eliminada exitosamente.')).to_be_visible()


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
