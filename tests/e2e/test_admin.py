"""e2e del panel de administración: alta y baja de mascotas, errores del formulario y fotos."""

import io
import re

import pytest
from PIL import Image
from playwright.sync_api import expect

from tests.e2e.conftest import ADMIN, iniciar_sesion

pytestmark = pytest.mark.e2e


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


def test_alta_de_mascota_con_error_conserva_lo_escrito(page, errores_js):
    """Regresión P-02: el servidor rechaza la descripción y el formulario sigue relleno."""
    iniciar_sesion(page, *ADMIN)

    page.goto('/mascotas/admin/nueva')
    page.get_by_label('Nombre').fill('Lur')
    page.get_by_label('Especie').fill('Gato')
    page.get_by_label('Raza').fill('Europeo')
    page.get_by_label('Sexo').select_option('Hembra')
    page.get_by_label('Descripción').fill('Corta')
    page.get_by_label('Vacunado').check()
    page.get_by_role('button', name='Crear Mascota').click()

    descripcion = page.get_by_label('Descripción')
    expect(descripcion).to_have_attribute('aria-invalid', 'true')
    expect(page.locator('#descripcion-error')).to_have_text('La descripción debe tener al menos 10 caracteres.')
    expect(descripcion).to_have_value('Corta')
    expect(page.get_by_label('Nombre')).to_have_value('Lur')
    expect(page.get_by_label('Raza')).to_have_value('Europeo')
    expect(page.get_by_label('Sexo')).to_have_value('Hembra')
    expect(page.get_by_label('Vacunado')).to_be_checked()

    descripcion.fill('Gata tímida pero muy cariñosa')
    page.get_by_role('button', name='Crear Mascota').click()
    expect(page.get_by_text('Mascota "Lur" creada exitosamente.')).to_be_visible()


def test_foto_demasiado_grande_no_se_envia(page, errores_js):
    """El servidor no puede conservar los datos de un 413: el navegador lo evita antes."""
    iniciar_sesion(page, *ADMIN)

    page.goto('/mascotas/admin/nueva')
    page.get_by_label('Nombre').fill('Bolt')
    foto = page.get_by_label('Foto de la mascota')
    # Justo por debajo de 5 MB: con el resto del formulario la petición daría 413
    foto.set_input_files({'name': 'grande.png', 'mimeType': 'image/png',
                          'buffer': b'0' * (5 * 1024 * 1024 - 1024)})

    mensaje = 'La foto ocupa más de 5 MB. Elige otra más pequeña o quita el archivo para usar una URL.'
    assert foto.evaluate('campo => campo.validationMessage') == mensaje
    expect(page.locator('#foto-error')).to_have_text(mensaje)
    expect(foto).to_have_attribute('aria-invalid', 'true')
    expect(foto).to_have_attribute('aria-describedby', 'foto-error foto-ayuda')
    page.get_by_role('button', name='Crear Mascota').click()
    expect(page).to_have_url(re.compile(r'/mascotas/admin/nueva$'))
    expect(page.get_by_label('Nombre')).to_have_value('Bolt')

    # Quitar el archivo (para usar una URL) borra el aviso y sus marcas
    foto.set_input_files([])
    assert foto.evaluate('campo => campo.validationMessage') == ''
    expect(page.locator('#foto-error')).to_have_count(0)
    expect(foto).not_to_have_attribute('aria-invalid', 'true')
    expect(foto).to_have_attribute('aria-describedby', 'foto-ayuda')


def test_elegir_otra_foto_quita_el_error_del_servidor(page, errores_js):
    """Tras un 400 con foto rechazada se avisa de volver a elegirla; al elegirla, el error se va."""
    iniciar_sesion(page, *ADMIN)

    page.goto('/mascotas/admin/nueva')
    page.get_by_label('Nombre').fill('Kira')
    page.get_by_label('Especie').fill('Perro')
    page.get_by_label('Descripción').fill('Perra activa que adora correr')
    foto = page.get_by_label('Foto de la mascota')
    foto.set_input_files({'name': 'kira.png', 'mimeType': 'image/png', 'buffer': b'no es una imagen'})
    page.get_by_role('button', name='Crear Mascota').click()

    expect(page.locator('#foto-error')).to_have_text(
        'No hemos podido usar esa imagen. Sube un archivo JPG, PNG, GIF o WebP.')
    expect(page.locator('#foto-aviso')).to_be_visible()
    expect(foto).to_have_attribute('aria-describedby', 'foto-error foto-aviso foto-ayuda')
    expect(page.get_by_label('Nombre')).to_have_value('Kira')

    foto.set_input_files({'name': 'otra.png', 'mimeType': 'image/png', 'buffer': b'0' * 10})
    expect(page.locator('#foto-error')).to_have_count(0)
    expect(foto).to_have_attribute('aria-describedby', 'foto-aviso foto-ayuda')
    expect(foto).not_to_have_attribute('aria-invalid', 'true')


def test_foto_subida_se_ve_en_la_ficha(page, errores_js):
    """Backend local: la foto se guarda y la app la sirve en /fotos/<clave> sin que la CSP la bloquee."""
    iniciar_sesion(page, *ADMIN)

    page.goto('/mascotas/admin/nueva')
    page.get_by_label('Nombre').fill('Nala')
    page.get_by_label('Especie').fill('Gato')
    page.get_by_label('Descripción').fill('Gata tranquila que busca sofá')
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), 'orange').save(buffer, format='PNG')
    page.get_by_label('Foto de la mascota').set_input_files(
        {'name': 'nala.png', 'mimeType': 'image/png', 'buffer': buffer.getvalue()})
    page.get_by_role('button', name='Crear Mascota').click()
    expect(page.get_by_text('Mascota "Nala" creada exitosamente.')).to_be_visible()

    page.goto('/mascotas/catalogo')
    foto = page.get_by_role('img', name='Nala')
    expect(foto).to_have_count(1)
    expect(foto).to_have_attribute('src', re.compile(r'^/fotos/'))
    expect(foto).to_have_js_property('naturalWidth', 40)

