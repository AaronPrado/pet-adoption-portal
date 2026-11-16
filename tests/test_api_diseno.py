"""
Tests del diseño de la API: formato de errores, paginación, filtros por
rango de edad y cabecera Location al crear.
"""

import pytest

from app import db
from app.models import Mascota, Usuario
from app.routes.api.auth import generate_token


def cabecera(usuario):
    return {'Authorization': f'Bearer {generate_token(usuario.id)}'}


class TestFormatoErrores:

    @pytest.mark.parametrize('metodo, url, codigo, mensaje', [
        ('get', '/api/mascotas/999', 404, 'Recurso no encontrado'),
        ('delete', '/api/mascotas/', 405, 'Método no permitido'),
    ])
    def test_errores_http_con_formato_comun(self, client, metodo, url, codigo, mensaje):
        response = getattr(client, metodo)(url)

        assert response.status_code == codigo
        assert response.get_json() == {'error': mensaje}

    def test_cuerpo_que_no_es_json(self, client, usuario_adoptante):
        response = client.post('/api/solicitudes/', data='texto', content_type='text/plain',
                               headers=cabecera(usuario_adoptante))

        assert response.status_code == 415
        assert 'error' in response.get_json()

    def test_error_interno_sin_detalles(self, client, monkeypatch):
        def fallar(*args, **kwargs):
            raise RuntimeError('detalle interno que no debe salir')
        monkeypatch.setattr(Mascota, 'query', property(fallar))

        response = client.get('/api/mascotas/')

        assert response.status_code == 500
        assert response.get_json() == {'error': 'Error interno del servidor'}


class TestPaginacion:

    @pytest.fixture
    def mascotas(self, app):
        db.session.add_all([
            Mascota(nombre=f'M{i:02d}', especie='Perro', descripcion='Descripción', edad_aprox=i % 10)
            for i in range(25)
        ])
        db.session.commit()

    def test_primera_pagina_por_defecto(self, client, mascotas):
        response = client.get('/api/mascotas/')

        assert len(response.get_json()) == 20
        assert response.headers['X-Total-Count'] == '25'
        assert 'rel="next"' in response.headers['Link']
        assert 'rel="prev"' not in response.headers['Link']

    def test_per_page_y_page(self, client, mascotas):
        response = client.get('/api/mascotas/?per_page=10&page=3')

        assert len(response.get_json()) == 5
        assert 'rel="prev"' in response.headers['Link']
        assert 'rel="next"' not in response.headers['Link']

    def test_enlaces_conservan_filtros(self, client, mascotas):
        link = client.get('/api/mascotas/?especie=Perro&per_page=5').headers['Link']
        assert 'especie=Perro' in link and 'per_page=5' in link and 'page=2' in link

    @pytest.mark.parametrize('query, mensaje', [
        ('per_page=101', 'per_page debe estar entre 1 y 100'),
        ('per_page=0', 'per_page debe estar entre 1 y 100'),
        ('page=0', 'page debe estar mayor o igual que 1'),
        ('page=abc', 'page debe ser un número entero'),
        ('edad_aprox=tres', 'edad_aprox debe ser un número entero'),
    ])
    def test_parametros_invalidos(self, client, query, mensaje):
        response = client.get(f'/api/mascotas/?{query}')

        assert response.status_code == 400
        assert response.get_json() == {'error': mensaje}


class TestFiltroEdad:

    @pytest.fixture
    def mascotas(self, app):
        db.session.add_all([
            Mascota(nombre=n, especie='Perro', descripcion='Descripción', edad_aprox=e)
            for n, e in [('Cachorro', 1), ('Adulto', 5), ('Mayor', 12)]
        ])
        db.session.commit()

    @pytest.mark.parametrize('query, esperados', [
        ('edad_min=2', {'Adulto', 'Mayor'}),
        ('edad_max=5', {'Cachorro', 'Adulto'}),
        ('edad_min=2&edad_max=10', {'Adulto'}),
        ('edad_aprox=12', {'Mayor'}),
    ])
    def test_rango(self, client, mascotas, query, esperados):
        nombres = {m['nombre'] for m in client.get(f'/api/mascotas/?{query}').get_json()}
        assert nombres == esperados


class TestSolicitudes:

    def test_crear_devuelve_location(self, client, usuario_adoptante, mascota_disponible, respuestas_validas):
        response = client.post('/api/solicitudes/', headers=cabecera(usuario_adoptante), json={
            'mascota_id': mascota_disponible.id, 'cuestionario': respuestas_validas
        })

        assert response.status_code == 201
        ubicacion = response.headers['Location']
        assert ubicacion.endswith(f"/api/solicitudes/{response.get_json()['id']}")

        detalle = client.get(ubicacion, headers=cabecera(usuario_adoptante))
        assert detalle.status_code == 200
        assert detalle.get_json()['mascota_id'] == mascota_disponible.id

    def test_solicitud_ajena_da_404(self, client, solicitud_pendiente):
        otro = Usuario(email='otro@test.com', nombre='Otro', password='password123')
        db.session.add(otro)
        db.session.commit()

        response = client.get(f'/api/solicitudes/{solicitud_pendiente.id}', headers=cabecera(otro))

        assert response.status_code == 404
        assert response.get_json() == {'error': 'Recurso no encontrado'}

    def test_detalle_requiere_token(self, client, solicitud_pendiente):
        assert client.get(f'/api/solicitudes/{solicitud_pendiente.id}').status_code == 401
