"""
Tests para la API REST.

Tests incluidos:
- Autenticación JWT (login)
- Endpoints de mascotas (listar, detalle, filtros)
- Endpoints de solicitudes (crear, listar)
"""

import json

from app.models import Solicitud


class TestAuthAPI:
    """Tests para /api/auth"""

    def test_login_exitoso(self, client, usuario_adoptante):
        """POST /api/auth/login con credenciales válidas."""
        response = client.post('/api/auth/login',
            data=json.dumps({
                'email': 'adoptante@test.com',
                'password': 'password123'
            }),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert 'token' in data
        assert 'user' in data
        assert data['user']['email'] == 'adoptante@test.com'

    def test_login_credenciales_invalidas(self, client, usuario_adoptante):
        """POST /api/auth/login con password incorrecto."""
        response = client.post('/api/auth/login',
            data=json.dumps({
                'email': 'adoptante@test.com',
                'password': 'wrongpassword'
            }),
            content_type='application/json'
        )

        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data

    def test_login_sin_datos(self, client):
        """POST /api/auth/login sin body."""
        response = client.post('/api/auth/login',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 400


class TestMascotasAPI:
    """Tests para /api/mascotas"""

    def test_listar_mascotas(self, client, mascota_disponible):
        """GET /api/mascotas/ devuelve lista de mascotas."""
        response = client.get('/api/mascotas/')

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]['nombre'] == 'Cerbero'

    def test_listar_mascotas_filtro_especie(self, client, mascota_disponible):
        """GET /api/mascotas/?especie=Perro filtra correctamente."""
        response = client.get('/api/mascotas/?especie=Perro')

        assert response.status_code == 200
        data = response.get_json()
        assert all(m['especie'] == 'Perro' for m in data)

    def test_detalle_mascota(self, client, mascota_disponible):
        """GET /api/mascotas/<id> devuelve detalle."""
        response = client.get(f'/api/mascotas/{mascota_disponible.id}')

        assert response.status_code == 200
        data = response.get_json()
        assert data['nombre'] == 'Cerbero'
        assert data['id'] == mascota_disponible.id

    def test_detalle_mascota_no_existe(self, client):
        """GET /api/mascotas/999 devuelve 404."""
        response = client.get('/api/mascotas/999')

        assert response.status_code == 404


class TestSolicitudesAPI:
    """Tests para /api/solicitudes"""

    def get_token(self, client, email='adoptante@test.com', password='password123'):
        """Helper para obtener token JWT."""
        response = client.post('/api/auth/login',
            data=json.dumps({'email': email, 'password': password}),
            content_type='application/json'
        )
        return response.get_json()['token']

    def test_mis_solicitudes_sin_token(self, client):
        """GET /api/solicitudes/mias sin JWT devuelve 401."""
        response = client.get('/api/solicitudes/mias')

        assert response.status_code == 401

    def test_mis_solicitudes_con_token(self, client, usuario_adoptante):
        """GET /api/solicitudes/mias con JWT devuelve lista."""
        token = self.get_token(client)

        response = client.get('/api/solicitudes/mias',
            headers={'Authorization': f'Bearer {token}'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)

    def crear(self, client, mascota_id, cuestionario):
        """Helper: POST /api/solicitudes/ con el token del adoptante."""
        return client.post('/api/solicitudes/', json={'mascota_id': mascota_id, 'cuestionario': cuestionario},
                           headers={'Authorization': f'Bearer {self.get_token(client)}'})

    def test_crear_solicitud_exitosa(self, client, usuario_adoptante, mascota_disponible, respuestas_validas):
        """POST /api/solicitudes/ crea solicitud."""
        response = self.crear(client, mascota_disponible.id, respuestas_validas)

        assert response.status_code == 201
        data = response.get_json()
        assert data['mascota_id'] == mascota_disponible.id
        assert data['estado'] == 'pendiente'
        # Se guarda el cuestionario limpio: sí/no como booleano y lo no contestado como null
        assert data['cuestionario']['tiene_jardin'] is True
        assert data['cuestionario']['tiene_mascotas'] is False
        assert data['cuestionario']['referencias'] is None

    def test_cuestionario_arbitrario_ya_no_es_valido(self, client, usuario_adoptante, mascota_disponible):
        """P-04: el contrato anterior aceptaba cualquier objeto plano."""
        response = self.crear(client, mascota_disponible.id, {
            'vivienda_tipo': 'Casa', 'tiene_jardin': True, 'experiencia_previa': True})

        assert response.status_code == 400
        assert set(response.get_json()) == {'error'}
        assert Solicitud.query.count() == 0

    def test_claves_desconocidas(self, client, usuario_adoptante, mascota_disponible, respuestas_validas):
        response = self.crear(client, mascota_disponible.id, {**respuestas_validas, 'es_admin': 'si'})

        assert response.status_code == 400
        assert response.get_json() == {'error': 'Cuestionario no válido: campos desconocidos: es_admin'}
        assert Solicitud.query.count() == 0

    def test_opciones_fuera_de_la_lista(self, client, usuario_adoptante, mascota_disponible,
                                        respuestas_validas):
        response = self.crear(client, mascota_disponible.id,
                              {**respuestas_validas, 'horas_solo': '24', 'vivienda_tipo': None})

        assert response.status_code == 400
        assert response.get_json() == {
            'error': 'Cuestionario no válido: horas_solo (opción no válida), vivienda_tipo (falta)'}

    def test_si_no_como_booleano_json_da_400(self, client, usuario_adoptante, mascota_disponible,
                                             respuestas_validas):
        """Los sí/no se envían como las cadenas "si"/"no", igual que el formulario."""
        response = self.crear(client, mascota_disponible.id, {**respuestas_validas, 'tiene_jardin': True})

        assert response.status_code == 400
        assert response.get_json() == {'error': 'Cuestionario no válido: tiene_jardin (opción no válida)'}

    def test_texto_con_nul_da_400(self, client, usuario_adoptante, mascota_disponible, respuestas_validas):
        """PostgreSQL rechaza \\u0000 en JSONB: sin esta regla la respuesta sería un 500."""
        response = self.crear(client, mascota_disponible.id, {**respuestas_validas, 'referencias': 'a\u0000b'})

        assert response.status_code == 400
        assert response.get_json() == {'error': 'Cuestionario no válido: referencias (texto no válido)'}
        assert Solicitud.query.count() == 0

    def test_texto_que_no_es_cadena_o_largo(self, client, usuario_adoptante, mascota_disponible,
                                            respuestas_validas):
        response = self.crear(client, mascota_disponible.id,
                              {**respuestas_validas, 'motivo_adopcion': 5, 'referencias': 'x' * 2001})

        assert response.get_json() == {
            'error': 'Cuestionario no válido: motivo_adopcion (texto no válido), referencias (demasiado largo)'}

    def test_tiene_mascotas_exige_detalles(self, client, usuario_adoptante, mascota_disponible,
                                           respuestas_validas):
        response = self.crear(client, mascota_disponible.id, {**respuestas_validas, 'tiene_mascotas': 'si'})

        assert response.status_code == 400
        assert response.get_json() == {'error': 'Cuestionario no válido: mascotas_detalles (falta)'}

    def test_cuestionario_vacio_o_ausente(self, client, usuario_adoptante, mascota_disponible):
        for cuerpo in [{'mascota_id': mascota_disponible.id, 'cuestionario': {}},
                       {'mascota_id': mascota_disponible.id}]:
            response = client.post('/api/solicitudes/', json=cuerpo,
                                   headers={'Authorization': f'Bearer {self.get_token(client)}'})
            assert response.status_code == 400
        assert Solicitud.query.count() == 0

    def test_crear_solicitud_sin_token(self, client, mascota_disponible):
        """POST /api/solicitudes/ sin JWT devuelve 401."""
        response = client.post('/api/solicitudes/',
            data=json.dumps({
                'mascota_id': mascota_disponible.id,
                'cuestionario': {}
            }),
            content_type='application/json'
        )

        assert response.status_code == 401

    def test_crear_solicitud_mascota_no_existe(self, client, usuario_adoptante, respuestas_validas):
        """POST /api/solicitudes/ con mascota inexistente devuelve 404."""
        assert self.crear(client, 999, respuestas_validas).status_code == 404

    def test_crear_solicitud_mascota_no_disponible(self, client, usuario_adoptante, mascota_adoptada,
                                                   respuestas_validas):
        """POST /api/solicitudes/ con mascota adoptada devuelve 400."""
        assert self.crear(client, mascota_adoptada.id, respuestas_validas).status_code == 400
