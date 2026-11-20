"""e2e de la solicitud de adopción: de la ficha de la mascota al cuestionario enviado."""

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import ADOPTANTE, iniciar_sesion

pytestmark = pytest.mark.e2e


def test_adoptante_envia_solicitud(page, errores_js, mascotas):
    iniciar_sesion(page, *ADOPTANTE)

    page.goto(f'/mascotas/{mascotas["Toby"]}')
    page.get_by_role('link', name='Solicitar Adopción').click()

    page.get_by_label('Tipo de vivienda').select_option(index=1)
    page.get_by_label('¿Es vivienda propia o alquilada?').select_option(index=1)
    # «Sí» y «No» se repiten en varias preguntas: las opciones van por su id
    page.locator('#jardin_si').check()
    page.locator('#mascotas_no').check()
    page.get_by_label('¿Tienes experiencia previa con mascotas?').fill('He tenido perros toda la vida')
    page.get_by_label('¿Cuántas horas al día estaría solo/a?').select_option(index=1)
    page.get_by_label('¿Cómo actuarías ante una emergencia veterinaria?').select_option(index=1)
    page.get_by_label('¿Por qué quieres adoptar a Toby?').fill('Quiero darle un hogar a un perro tranquilo')
    page.locator('#gastos_si').check()
    page.locator('#tiempo_si').check()
    page.get_by_role('button', name=re.compile('Enviar')).click()

    expect(page).to_have_url(re.compile('/solicitudes/mis-solicitudes'))
    expect(page.get_by_text('Solicitud enviada con éxito para Toby')).to_be_visible()


def test_login_desde_la_ficha_vuelve_al_cuestionario(page, errores_js, mascotas):
    """El anónimo que pulsa «Inicia sesión para adoptar» acaba en el cuestionario."""
    page.goto(f'/mascotas/{mascotas["Misu"]}')
    page.get_by_role('link', name='Inicia sesión para adoptar').click()

    # Un primer intento fallido conserva el correo y el destino
    page.get_by_label('Correo electrónico').fill(ADOPTANTE[0])
    page.get_by_label('Contraseña').fill('clave-equivocada')
    page.get_by_role('button', name='Iniciar Sesión').click()
    expect(page.get_by_role('link', name='Correo o contraseña incorrectos.')).to_be_visible()
    expect(page.get_by_label('Correo electrónico')).to_have_value(ADOPTANTE[0])
    expect(page.get_by_label('Contraseña')).to_have_value('')

    page.get_by_label('Contraseña').fill(ADOPTANTE[1])
    page.get_by_role('button', name='Iniciar Sesión').click()

    expect(page).to_have_url(re.compile(r'/solicitudes/nueva/\d+$'))
    expect(page.get_by_text('Misu').first).to_be_visible()
