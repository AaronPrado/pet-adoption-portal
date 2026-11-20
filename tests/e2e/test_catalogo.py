"""e2e del catálogo público."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_catalogo_publico(page, errores_js):
    page.goto('/mascotas/catalogo')

    expect(page.get_by_role('heading', name='Toby')).to_be_visible()
    page.get_by_text('Filtrar mascotas').click()
    page.get_by_label('Especie').select_option('Gato')
    page.get_by_role('button', name='Filtrar').click()

    expect(page.get_by_role('heading', name='Misu')).to_be_visible()
    expect(page.get_by_role('heading', name='Toby')).to_have_count(0)


def test_de_la_tarjeta_a_la_ficha(page, errores_js):
    """El enlace «Ver a Toby» es único y lleva a la ficha; «Volver al catálogo» regresa."""
    page.goto('/mascotas/catalogo')

    tarjeta = page.get_by_role('article').filter(has=page.get_by_role('heading', name='Toby'))
    tarjeta.get_by_role('link', name='Ver a Toby').click()

    expect(page.get_by_role('heading', level=1, name='Toby')).to_be_visible()
    page.get_by_role('link', name='Volver al catálogo').click()
    expect(page.get_by_role('heading', level=1, name='Mascotas en adopción')).to_be_visible()


def test_filtros_plegados_y_estado_vacio(page, errores_js):
    page.goto('/mascotas/catalogo')

    expect(page.get_by_label('Especie')).to_be_hidden()
    page.get_by_text('Filtrar mascotas').click()
    page.get_by_label('Especie').select_option('Gato')
    page.get_by_label('Sexo').select_option('Macho')
    page.get_by_role('button', name='Filtrar').click()

    expect(page.get_by_role('heading', name='Ninguna mascota coincide con estos filtros')).to_be_visible()
    page.get_by_role('link', name='Quitar filtros').click()
    expect(page.get_by_role('link', name='Ver a Misu')).to_be_visible()
