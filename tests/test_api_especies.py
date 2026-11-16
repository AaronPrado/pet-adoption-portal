"""
Tests del filtro ?especie= de la API de mascotas (P-31).

Las especies se guardan normalizadas («Perro»), así que el parámetro se
normaliza igual para que «perro» o « PERRO » sigan encontrándolas.
"""

import pytest

from app import db
from app.models import Mascota


def nombres(response):
    return {mascota['nombre'] for mascota in response.get_json()}


@pytest.fixture
def gato(app):
    mascota = Mascota(nombre='Michi', especie='Gato', descripcion='Gata cariñosa y tranquila',
                      estado='disponible')
    db.session.add(mascota)
    db.session.commit()
    return mascota


@pytest.mark.parametrize('especie', ['Perro', 'perro', ' PERRO ', 'pe%E2%80%8Brro'])
def test_filtro_especie_normaliza_el_parametro(client, mascota_disponible, gato, especie):
    response = client.get(f'/api/mascotas/?especie={especie}')

    assert response.status_code == 200
    assert nombres(response) == {'Cerbero'}


@pytest.mark.parametrize('consulta', ['', '?especie=', '?especie=%20%20'])
def test_filtro_especie_vacio_no_filtra(client, mascota_disponible, gato, consulta):
    response = client.get(f'/api/mascotas/{consulta}')

    assert response.status_code == 200
    assert nombres(response) == {'Cerbero', 'Michi'}
