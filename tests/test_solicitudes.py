"""
Tests para el módulo de solicitudes de adopción.

Tests incluidos:
- Creación de solicitudes
- Cuestionario de adopción
- Revisión y aprobación/rechazo (admin)
- Validaciones y restricciones
"""

import re

from app import cuestionario, db
from app.models import Mascota, Solicitud


class TestCrearSolicitud:
    """Tests para crear solicitudes de adopción."""

    def test_crear_solicitud_requiere_login(self, client, mascota_disponible):
        """Test: Crear solicitud requiere autenticación."""
        response = client.get(f'/solicitudes/nueva/{mascota_disponible.id}', follow_redirects=True)

        assert response.status_code == 200
        assert 'Iniciar Sesión' in response.data.decode() or 'Login' in response.data.decode()

    def test_crear_solicitud_get_muestra_formulario(self, client, auth_headers_adoptante, mascota_disponible):
        """Test: GET muestra formulario de cuestionario."""
        response = client.get(f'/solicitudes/nueva/{mascota_disponible.id}')

        assert response.status_code == 200
        content = response.data.decode()
        assert 'Cuestionario' in content or 'Solicitud' in content or 'vivienda' in content.lower()

    def test_crear_solicitud_exitosa(self, client, auth_headers_adoptante, mascota_disponible,
                                     respuestas_validas):
        """Test: Crear solicitud con cuestionario completo."""
        response = client.post(f'/solicitudes/nueva/{mascota_disponible.id}', data=respuestas_validas,
                               follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode().lower()
        assert 'solicitud' in content and ('enviada' in content or 'éxito' in content or 'exito' in content)

        # Verificar en BD
        solicitud = Solicitud.query.filter_by(mascota_id=mascota_disponible.id).first()
        assert solicitud is not None
        assert solicitud.estado == 'pendiente'
        assert solicitud.cuestionario_json is not None

        # La mascota sigue disponible: admite más solicitudes en paralelo
        db.session.refresh(mascota_disponible)
        assert mascota_disponible.estado == 'disponible'

    def test_crear_solicitud_mascota_no_disponible(self, client, auth_headers_adoptante, mascota_adoptada):
        """Test: No se puede solicitar mascota que no está disponible."""
        response = client.get(f'/solicitudes/nueva/{mascota_adoptada.id}', follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode().lower()
        assert 'no está disponible' in content

    def test_crear_solicitud_duplicada(self, client, auth_headers_adoptante, solicitud_pendiente):
        """Test: No se puede solicitar la misma mascota dos veces."""
        response = client.get(f'/solicitudes/nueva/{solicitud_pendiente.mascota_id}', follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode().lower()
        assert 'ya' in content or 'solicitud' in content


class TestValidarCuestionarioWeb:
    """P-04: el servidor valida el cuestionario antes de crear la solicitud."""

    def enviar(self, client, mascota, datos):
        return client.post(f'/solicitudes/nueva/{mascota.id}', data=datos)

    def test_envio_vacio_no_crea_la_solicitud(self, client, auth_headers_adoptante, mascota_disponible):
        response = self.enviar(client, mascota_disponible, {})

        assert response.status_code == 400
        assert Solicitud.query.count() == 0
        html = response.data.decode()
        assert 'Revisa los campos marcados.' in html
        assert 'Esta pregunta es obligatoria.' in html
        assert 'éxito' not in html
        # Es el formulario, no la página genérica del 400 (app/errores.py)
        assert 'id="vivienda_tipo"' in html
        assert 'No hemos podido procesar la petición' not in html

    def test_errores_junto_a_su_campo(self, client, auth_headers_adoptante, mascota_disponible):
        html = self.enviar(client, mascota_disponible, {}).data.decode()

        assert 'aria-describedby="vivienda_tipo-error"' in html
        assert 'id="vivienda_tipo-error"' in html
        # En los radios, cada opción apunta al error del grupo
        assert html.count('aria-describedby="tiene_jardin-error"') == 2
        assert 'id="jardin_si"' in html and 'id="gastos_si"' in html
        # Las opcionales no se marcan
        assert 'id="referencias-error"' not in html

    def test_opcion_fuera_de_la_lista(self, client, auth_headers_adoptante, mascota_disponible,
                                      respuestas_validas):
        response = self.enviar(client, mascota_disponible, {**respuestas_validas, 'horas_solo': '24'})

        assert response.status_code == 400
        assert Solicitud.query.count() == 0
        assert 'id="horas_solo-error"' in response.data.decode()

    def test_conserva_lo_escrito(self, client, auth_headers_adoptante, mascota_disponible,
                                 respuestas_validas):
        datos = {**respuestas_validas, 'tiene_mascotas': 'si', 'referencias': 'Ana <García>',
                 'horas_solo': '8+'}
        html = self.enviar(client, mascota_disponible, datos).data.decode()

        assert '<option value="casa" selected>' in html
        assert '<option value="8+" selected>' in html
        assert 'He tenido perros toda la vida</textarea>' in html
        assert 'Ana &lt;García&gt;</textarea>' in html
        assert 'id="mascotas_si" value="si" checked' in html
        assert 'id="mascotas_no" value="no" checked' not in html
        # El único error es la dependencia
        assert 'id="mascotas_detalles-error"' in html
        assert html.count('aria-invalid="true"') == 1

    def test_tiene_mascotas_exige_detalles(self, client, auth_headers_adoptante, mascota_disponible,
                                           respuestas_validas):
        response = self.enviar(client, mascota_disponible, {**respuestas_validas, 'tiene_mascotas': 'si'})

        assert response.status_code == 400
        assert 'Si tienes otras mascotas, cuéntanos cuáles.' in response.data.decode()

    def test_no_contestado_se_guarda_como_null(self, client, auth_headers_adoptante, mascota_disponible,
                                               respuestas_validas):
        response = self.enviar(client, mascota_disponible, {**respuestas_validas, 'compromiso_tiempo': 'no'})

        assert response.status_code == 302
        guardado = Solicitud.query.one().cuestionario_json
        assert guardado['referencias'] is None
        assert guardado['mascotas_detalles'] is None
        assert guardado['compromiso_tiempo'] is False
        assert guardado['tiene_jardin'] is True

    def test_ignora_campos_que_no_son_preguntas(self, client, auth_headers_adoptante, mascota_disponible,
                                                respuestas_validas):
        self.enviar(client, mascota_disponible, {**respuestas_validas, 'es_admin': 'si'})

        assert 'es_admin' not in Solicitud.query.one().cuestionario_json

    def test_texto_con_nul(self, client, auth_headers_adoptante, mascota_disponible, respuestas_validas):
        response = self.enviar(client, mascota_disponible, {**respuestas_validas, 'motivo_adopcion': 'a\x00b'})

        assert response.status_code == 400
        assert Solicitud.query.count() == 0
        assert 'id="motivo_adopcion-error"' in response.data.decode()

    def test_texto_largo_se_repinta_recortado(self, client, auth_headers_adoptante, mascota_disponible,
                                              respuestas_validas):
        enorme = 'x' * 100_000
        html = self.enviar(client, mascota_disponible, {**respuestas_validas, 'referencias': enorme}).data.decode()

        assert 'id="referencias-error"' in html
        assert 'x' * (cuestionario.LONGITUD_MAXIMA + 1) + '</textarea>' in html
        assert 'x' * (cuestionario.LONGITUD_MAXIMA + 2) not in html

    def test_referencias_enlaza_pista_y_error(self, client, auth_headers_adoptante, mascota_disponible,
                                              respuestas_validas):
        largo = 'x' * (cuestionario.LONGITUD_MAXIMA + 1)
        html = self.enviar(client, mascota_disponible, {**respuestas_validas, 'referencias': largo}).data.decode()

        assert 'aria-describedby="referencias-error referencias-ayuda"' in html
        assert 'id="referencias-ayuda"' in html

    def test_referencias_enlaza_la_pista_sin_error(self, client, auth_headers_adoptante, mascota_disponible):
        html = client.get(f'/solicitudes/nueva/{mascota_disponible.id}').data.decode()

        assert 'aria-describedby="referencias-ayuda"' in html

    def test_opciones_de_los_select_salen_del_modulo(self, client, auth_headers_adoptante, mascota_disponible):
        """Fuente única: los <select> pintan exactamente las opciones de PREGUNTAS."""
        html = client.get(f'/solicitudes/nueva/{mascota_disponible.id}').data.decode()

        selects = re.findall(r'<select[^>]*\bname="([^"]+)"[^>]*>(.*?)</select>', html, re.S)
        assert {nombre for nombre, _ in selects} == {
            campo for campo, p in cuestionario.PREGUNTAS.items() if p.opciones and not p.si_no}
        for nombre, cuerpo in selects:
            pintadas = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', cuerpo)
            assert pintadas[0] == ('', 'Selecciona...')
            assert tuple(pintadas[1:]) == cuestionario.PREGUNTAS[nombre].opciones, nombre

    def test_get_sin_errores(self, client, auth_headers_adoptante, mascota_disponible):
        html = client.get(f'/solicitudes/nueva/{mascota_disponible.id}').data.decode()

        assert 'aria-invalid' not in html
        assert ' selected>' not in html and ' checked' not in html


class TestMisSolicitudes:
    """Tests para ver las solicitudes del usuario."""

    def test_mis_solicitudes_requiere_login(self, client):
        """Test: Ver mis solicitudes requiere login."""
        response = client.get('/solicitudes/mis-solicitudes', follow_redirects=True)

        assert response.status_code == 200
        assert 'Iniciar Sesión' in response.data.decode() or 'Login' in response.data.decode()

    def test_mis_solicitudes_muestra_solicitudes(self, client, auth_headers_adoptante, solicitud_pendiente):
        """Test: Muestra las solicitudes del usuario."""
        response = client.get('/solicitudes/mis-solicitudes')

        assert response.status_code == 200
        content = response.data.decode()
        assert 'Cerbero' in content  # Nombre de la mascota
        assert 'Pendiente' in content or 'pendiente' in content

    def test_mis_solicitudes_solo_propias(self, client, auth_headers_adoptante, solicitud_pendiente):
        """Test: Solo muestra solicitudes propias del usuario."""
        # Crear otro usuario y otra solicitud
        from app.models import Usuario
        otro_usuario = Usuario(
            email='otro@test.com',
            nombre='Otro Usuario',
            password='pass123'
        )
        db.session.add(otro_usuario)
        db.session.commit()

        response = client.get('/solicitudes/mis-solicitudes')

        # Solo debe mostrar la solicitud del usuario logueado
        assert response.status_code == 200


class TestDetalleSolicitud:
    """Tests para ver detalle de una solicitud."""

    def test_detalle_requiere_login(self, client, solicitud_pendiente):
        """Test: Ver detalle requiere login."""
        response = client.get(f'/solicitudes/detalle/{solicitud_pendiente.id}', follow_redirects=True)

        assert response.status_code == 200
        assert 'Iniciar Sesión' in response.data.decode() or 'Login' in response.data.decode()

    def test_detalle_muestra_cuestionario(self, client, auth_headers_adoptante, solicitud_pendiente):
        """Test: Detalle muestra el cuestionario completo."""
        response = client.get(f'/solicitudes/detalle/{solicitud_pendiente.id}')

        assert response.status_code == 200
        content = response.data.decode()
        # Verificar que muestra información de la solicitud
        assert 'Cerbero' in content or 'solicitud' in content.lower()

    def test_detalle_solo_propietario_o_admin(self, client, auth_headers_adoptante, solicitud_pendiente):
        """Test: Solo el propietario o admin pueden ver la solicitud."""
        # Crear otro usuario adoptante
        from app.models import Usuario
        otro_usuario = Usuario(
            email='otro2@test.com',
            nombre='Otro Usuario',
            password='pass123'
        )
        db.session.add(otro_usuario)
        db.session.commit()

        # Logout y login como otro usuario
        client.post('/auth/logout')
        client.post('/auth/login', data={
            'email': 'otro2@test.com',
            'password': 'pass123'
        })

        response = client.get(f'/solicitudes/detalle/{solicitud_pendiente.id}', follow_redirects=True)

        assert response.status_code == 200
        # Debe denegar acceso o redirigir
        content = response.data.decode().lower()
        assert 'permiso' in content or 'acceso' in content or 'no tienes' in content or 'solicitudes' in content


class TestAdminPanel:
    """Tests para panel de administración de solicitudes."""

    def test_admin_panel_requiere_login(self, client):
        """Test: Panel admin requiere login."""
        response = client.get('/solicitudes/admin', follow_redirects=True)

        assert response.status_code == 200
        assert 'Iniciar Sesión' in response.data.decode() or 'Login' in response.data.decode()

    def test_admin_panel_solo_admin(self, client, auth_headers_adoptante):
        """Test: Solo admin puede acceder."""
        response = client.get('/solicitudes/admin', follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode().lower()
        assert 'admin' in content or 'permiso' in content or 'no tienes' in content

    def test_admin_panel_muestra_solicitudes(self, client, auth_headers_admin, solicitud_pendiente):
        """Test: Panel muestra todas las solicitudes."""
        response = client.get('/solicitudes/admin')

        assert response.status_code == 200
        content = response.data.decode()
        assert 'Cerbero' in content or 'Pepe' in content or 'adoptante@test.com' in content

    def test_admin_panel_filtro_estado(self, client, auth_headers_admin, solicitud_pendiente):
        """Test: Filtro por estado funciona."""
        response = client.get('/solicitudes/admin?estado=pendiente')

        assert response.status_code == 200
        content = response.data.decode()
        assert 'Cerbero' in content or 'pendiente' in content.lower()


class TestRevisarSolicitud:
    """Tests para revisar y aprobar/rechazar solicitudes."""

    def test_revisar_solo_admin(self, client, auth_headers_adoptante, solicitud_pendiente):
        """Test: Solo admin puede revisar."""
        response = client.get(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}', follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode().lower()
        assert 'admin' in content or 'permiso' in content or 'no tienes' in content

    def test_revisar_muestra_cuestionario(self, client, auth_headers_admin, solicitud_pendiente):
        """Test: Página de revisión muestra el cuestionario."""
        response = client.get(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}')

        assert response.status_code == 200
        content = response.data.decode()
        assert 'Casa' in content or 'vivienda' in content.lower()
        assert 'Aprobar' in content or 'aprobar' in content
        assert 'Rechazar' in content or 'rechazar' in content

    def test_aprobar_solicitud(self, client, auth_headers_admin, solicitud_pendiente, usuario_admin):
        """Test: Admin puede aprobar solicitud."""
        response = client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}', data={
            'accion': 'aprobar',
            'comentarios': 'Aprobada por cumplir requisitos'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert 'aprobada' in response.data.decode().lower()

        # Verificar en BD
        db.session.refresh(solicitud_pendiente)
        assert solicitud_pendiente.estado == 'aprobada'
        assert solicitud_pendiente.revisado_por == usuario_admin.id
        assert solicitud_pendiente.comentarios_admin is not None

        # Verificar que mascota pasó a adoptado
        mascota = db.session.get(Mascota, solicitud_pendiente.mascota_id)
        assert mascota.estado == 'adoptado'

    def test_rechazar_solicitud(self, client, auth_headers_admin, solicitud_pendiente, usuario_admin):
        """Test: Admin puede rechazar solicitud."""
        response = client.post(f'/solicitudes/admin/revisar/{solicitud_pendiente.id}', data={
            'accion': 'rechazar',
            'comentarios': 'No cumple requisitos de espacio'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert 'rechazada' in response.data.decode().lower()

        # Verificar en BD
        db.session.refresh(solicitud_pendiente)
        assert solicitud_pendiente.estado == 'rechazada'
        assert solicitud_pendiente.revisado_por == usuario_admin.id
        assert solicitud_pendiente.comentarios_admin is not None


class TestModelo:
    """Tests para el modelo Solicitud."""

    def test_crear_solicitud(self, app, usuario_adoptante, mascota_disponible):
        """Test: Crear solicitud correctamente."""
        solicitud = Solicitud(
            usuario_id=usuario_adoptante.id,
            mascota_id=mascota_disponible.id,
            cuestionario={'pregunta': 'respuesta'}
        )
        db.session.add(solicitud)
        db.session.commit()

        # Verificar valores por defecto
        assert solicitud.estado == 'pendiente'
        assert solicitud.cuestionario_json == {'pregunta': 'respuesta'}

    def test_registrar_revision(self, app, solicitud_pendiente, usuario_admin):
        """Test: registrar_revision() solo anota la revisión, sin tocar la mascota ni hacer commit."""
        solicitud_pendiente.registrar_revision('aprobada', usuario_admin.id, 'Aprobada')

        assert solicitud_pendiente.estado == 'aprobada'
        assert solicitud_pendiente.revisado_por == usuario_admin.id
        assert solicitud_pendiente.comentarios_admin == 'Aprobada'
        assert solicitud_pendiente.fecha_revision is not None
        assert solicitud_pendiente.mascota.estado == 'disponible'
        db.session.rollback()
        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'pendiente'

    def test_esta_pendiente(self, app, solicitud_pendiente):
        """Test: Método esta_pendiente() funciona."""
        assert solicitud_pendiente.esta_pendiente() is True

        solicitud_pendiente.estado = 'aprobada'
        assert solicitud_pendiente.esta_pendiente() is False

    def test_repr_solicitud(self, app, solicitud_pendiente):
        """Test: Representación en string de solicitud."""
        repr_str = repr(solicitud_pendiente)

        assert 'Solicitud' in repr_str
        assert str(solicitud_pendiente.id) in repr_str
        assert 'pendiente' in repr_str
