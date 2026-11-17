"""e2e del catálogo público."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_catalogo_publico(page, errores_js):
    page.goto('/mascotas/catalogo')

    expect(page.get_by_role('heading', name='Toby')).to_be_visible()
    page.get_by_label('Especie').select_option('Gato')
    page.get_by_role('button', name='Filtrar').click()

    expect(page.get_by_role('heading', name='Misu')).to_be_visible()
    expect(page.get_by_role('heading', name='Toby')).to_have_count(0)
