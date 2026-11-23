"""
Tests para el módulo de solicitudes de adopción.

Tests incluidos:
- Creación de solicitudes
- Cuestionario de adopción
- Revisión y aprobación/rechazo (admin)
- Validaciones y restricciones
"""

import re

import pytest
from markupsafe import escape

from app import cuestionario, db
from app.models import Mascota, Solicitud, Usuario


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
        assert 'data-resumen-errores' in html
        assert 'Esta pregunta es obligatoria.' in html
        assert 'éxito' not in html
        # Es el formulario, no la página genérica del 400 (app/errores.py)
        assert 'id="vivienda_tipo"' in html
        assert 'No hemos podido procesar la petición' not in html

    def test_errores_junto_a_su_campo(self, client, auth_headers_adoptante, mascota_disponible):
        html = self.enviar(client, mascota_disponible, {}).data.decode()

        assert 'aria-describedby="experiencia_previa-error experiencia_previa-ayuda"' in html
        assert 'id="vivienda_tipo-error"' in html
        # En los radios, el error describe el grupo (su fieldset)
        assert html.count('aria-describedby="tiene_jardin-error"') == 1
        assert 'id="tiene_jardin_si"' in html and 'id="compromiso_gastos_si"' in html
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

        assert 'id="vivienda_tipo_casa" name="vivienda_tipo" value="casa" checked' in html
        assert 'id="horas_solo_8+" name="horas_solo" value="8+" checked' in html
        assert 'He tenido perros toda la vida</textarea>' in html
        assert 'Ana &lt;García&gt;</textarea>' in html
        assert 'id="tiene_mascotas_si" name="tiene_mascotas" value="si" checked' in html
        assert 'id="tiene_mascotas_no" name="tiene_mascotas" value="no" checked' not in html
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
            'motivo': 'No cumple requisitos de espacio'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert 'rechazada' in response.data.decode().lower()

        # Verificar en BD
        db.session.refresh(solicitud_pendiente)
        assert solicitud_pendiente.estado == 'rechazada'
        assert solicitud_pendiente.revisado_por == usuario_admin.id
        assert solicitud_pendiente.comentarios_admin is not None


def contenido(response):
    """HTML del `<main>`, sin la navegación (que tiene el formulario de cerrar sesión)."""
    html = response.data.decode()
    return html.split('<main', 1)[1].split('</main>', 1)[0]


def formulario(html, accion):
    """HTML del `<form>` que envía `accion`."""
    for trozo in html.split('<form')[1:]:
        trozo = trozo.split('</form>', 1)[0]
        if f'name="accion" value="{accion}"' in trozo:
            return '<form' + trozo
    raise AssertionError(f'No hay formulario para {accion}')


def otras_pendientes(mascota, numero):
    for i in range(numero):
        usuario = Usuario(email=f'otra{i}@test.com', nombre=f'Otra{i}', password='password123')
        db.session.add(usuario)
        db.session.flush()
        db.session.add(Solicitud(usuario_id=usuario.id, mascota_id=mascota.id, cuestionario={}))
    db.session.commit()


class TestRevisionConConfirmacion:
    """P-06: aprobar pide confirmación, rechazar exige motivo y una resuelta no tiene formulario."""

    def url(self, solicitud):
        return f'/solicitudes/admin/revisar/{solicitud.id}'

    @pytest.mark.parametrize('numero, texto', [
        (0, 'No hay otras solicitudes pendientes'),
        (1, 'Se rechazará automáticamente 1 solicitud pendiente'),
        (2, 'Se rechazarán automáticamente 2 solicitudes pendientes'),
    ])
    def test_aprobar_confirma_cuantas_pendientes_se_rechazan(self, client, auth_headers_admin,
                                                            solicitud_pendiente, numero, texto):
        otras_pendientes(solicitud_pendiente.mascota, numero)

        html = contenido(client.get(self.url(solicitud_pendiente)))

        aprobar = formulario(html, 'aprobar')
        confirmar = re.search(r'data-confirmar="([^"]*)"', aprobar).group(1)
        assert texto in confirmar
        assert 'Cerbero' in confirmar and 'Pepe' in confirmar
        assert 'No se puede deshacer' in confirmar
        # También visible sin JavaScript
        assert texto in html.replace(confirmar, '')
        assert 'name="csrf_token"' in aprobar

    def test_rechazar_tiene_su_formulario_con_motivo(self, client, auth_headers_admin, solicitud_pendiente):
        html = contenido(client.get(self.url(solicitud_pendiente)))

        rechazar = formulario(html, 'rechazar')
        assert 'name="motivo"' in rechazar and 'required' in rechazar
        assert '<label for="motivo"' in rechazar
        assert 'name="csrf_token"' in rechazar
        assert 'aria-invalid' not in rechazar
        assert 'name="motivo"' not in formulario(html, 'aprobar')

    @pytest.mark.parametrize('motivo', ['', '   '])
    def test_rechazar_sin_motivo(self, client, auth_headers_admin, solicitud_pendiente, motivo):
        response = client.post(self.url(solicitud_pendiente), data={'accion': 'rechazar', 'motivo': motivo})

        assert response.status_code == 400
        html = contenido(response)
        assert 'id="motivo-error"' in html
        assert 'aria-invalid="true"' in html
        assert re.search(r'aria-describedby="motivo-error[^"]*"', html)
        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'pendiente'

    def test_formularios_con_su_titulo_y_aviso_visible(self, client, auth_headers_admin, solicitud_pendiente):
        html = contenido(client.get(self.url(solicitud_pendiente)))

        assert 'aria-labelledby="aprobar-titulo"' in formulario(html, 'aprobar')
        assert 'aria-labelledby="rechazar-titulo"' in formulario(html, 'rechazar')
        assert '<h5 id="aprobar-titulo">' in html and '<h5 id="rechazar-titulo">' in html
        confirmar = re.search(r'data-confirmar="([^"]*)"', html).group(1)
        # El aviso está también en el párrafo visible, entre el título y el formulario
        assert 'No se puede deshacer' in html.replace(confirmar, '').split('aprobar-titulo', 2)[1]
        assert 'autofocus' not in html

    @pytest.mark.parametrize('campo', ['comentarios', 'motivo'])
    def test_textareas_con_maxlength(self, client, auth_headers_admin, solicitud_pendiente, campo):
        html = contenido(client.get(self.url(solicitud_pendiente)))

        assert re.search(rf'<textarea[^>]*id="{campo}"[^>]*maxlength="{cuestionario.LONGITUD_MAXIMA}"', html)

    def test_rechazar_sin_motivo_da_el_foco_al_motivo(self, client, auth_headers_admin, solicitud_pendiente):
        html = contenido(client.post(self.url(solicitud_pendiente), data={'accion': 'rechazar'}))

        assert re.search(r'<textarea[^>]*id="motivo"[^>]*autofocus', html)
        assert html.count('autofocus') == 1

    @pytest.mark.parametrize('accion, campo', [('aprobar', 'comentarios'), ('rechazar', 'motivo')])
    def test_texto_demasiado_largo(self, client, auth_headers_admin, solicitud_pendiente, accion, campo):
        largo = 'x' * (cuestionario.LONGITUD_MAXIMA + 50)

        response = client.post(self.url(solicitud_pendiente), data={'accion': accion, campo: largo})

        assert response.status_code == 400
        html = contenido(response)
        assert f'id="{campo}-error"' in html
        assert '2000 caracteres' in html
        # Se repinta recortado a un carácter de más
        assert '>' + 'x' * (cuestionario.LONGITUD_MAXIMA + 1) + '</textarea>' in html
        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'pendiente'

    @pytest.mark.parametrize('accion, campo', [('aprobar', 'comentarios'), ('rechazar', 'motivo')])
    def test_texto_en_el_limite(self, client, auth_headers_admin, solicitud_pendiente, accion, campo):
        texto = 'x' * cuestionario.LONGITUD_MAXIMA

        response = client.post(self.url(solicitud_pendiente), data={'accion': accion, campo: f'  {texto}  '})

        assert response.status_code == 302
        assert db.session.get(Solicitud, solicitud_pendiente.id).comentarios_admin == texto

    def test_rechazar_sin_motivo_conserva_lo_escrito(self, client, auth_headers_admin, solicitud_pendiente):
        response = client.post(self.url(solicitud_pendiente), data={
            'accion': 'rechazar', 'motivo': '', 'comentarios': 'Hola <Pepe>'})

        assert 'Hola &lt;Pepe&gt;</textarea>' in response.data.decode()

    def test_rechazar_guarda_el_motivo(self, client, auth_headers_admin, solicitud_pendiente):
        response = client.post(self.url(solicitud_pendiente), data={
            'accion': 'rechazar', 'motivo': '  Vivienda pequeña  '})

        assert response.status_code == 302
        solicitud = db.session.get(Solicitud, solicitud_pendiente.id)
        assert solicitud.estado == 'rechazada'
        assert solicitud.comentarios_admin == 'Vivienda pequeña'

    def test_aprobar_sin_mensaje_lo_deja_vacio(self, client, auth_headers_admin, solicitud_pendiente):
        client.post(self.url(solicitud_pendiente), data={'accion': 'aprobar', 'comentarios': '  '})

        solicitud = db.session.get(Solicitud, solicitud_pendiente.id)
        assert solicitud.estado == 'aprobada'
        assert solicitud.comentarios_admin is None

    @pytest.mark.parametrize('accion', ['borrar', '', None])
    def test_accion_no_valida(self, client, auth_headers_admin, solicitud_pendiente, accion):
        datos = {'motivo': 'x'} if accion is None else {'accion': accion, 'motivo': 'x'}

        response = client.post(self.url(solicitud_pendiente), data=datos)

        assert response.status_code == 400
        assert 'Acción no válida.' in response.data.decode()
        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'pendiente'

    @pytest.mark.parametrize('estado, insignia', [('aprobada', 'Aprobada'), ('rechazada', 'Rechazada')])
    def test_resuelta_sin_formulario(self, client, auth_headers_admin, solicitud_pendiente, usuario_admin,
                                     estado, insignia):
        solicitud_pendiente.registrar_revision(estado, usuario_admin.id, 'Mensaje <del> refugio')
        db.session.commit()

        response = client.get(self.url(solicitud_pendiente))

        assert response.status_code == 200
        html = contenido(response)
        assert '<form' not in html
        assert insignia in html
        assert 'Mensaje del refugio' in html
        assert 'Mensaje &lt;del&gt; refugio' in html
        assert usuario_admin.nombre in html

    @pytest.mark.parametrize('ruta', ['/solicitudes/mis-solicitudes', '/solicitudes/detalle/{}'])
    def test_el_adoptante_ve_el_mensaje_del_refugio(self, client, auth_headers_adoptante, solicitud_pendiente,
                                                     usuario_admin, ruta):
        solicitud_pendiente.registrar_revision('rechazada', usuario_admin.id, 'Vivienda pequeña')
        db.session.commit()

        html = contenido(client.get(ruta.format(solicitud_pendiente.id)))

        assert 'Mensaje del refugio' in html and 'Vivienda pequeña' in html
        assert 'Comentarios del' not in html

    def test_resuelta_sin_mensaje(self, client, auth_headers_admin, solicitud_pendiente):
        solicitud_pendiente.registrar_revision('rechazada', None, None)
        db.session.commit()

        html = contenido(client.get(self.url(solicitud_pendiente)))

        assert '<form' not in html
        assert 'Sin mensaje para el solicitante' in html

    def test_rechazar_una_resuelta_sin_motivo_avisa_que_ya_esta_revisada(self, client, auth_headers_admin,
                                                                        solicitud_pendiente, usuario_admin):
        solicitud_pendiente.registrar_revision('aprobada', usuario_admin.id)
        db.session.commit()

        response = client.post(self.url(solicitud_pendiente), data={'accion': 'rechazar'},
                               follow_redirects=True)

        assert 'Esta solicitud ya ha sido revisada.' in response.data.decode()
        assert db.session.get(Solicitud, solicitud_pendiente.id).estado == 'aprobada'


class TestRespuestasLegibles:
    """P-10: revisar y detalle muestran la etiqueta de cada respuesta."""

    @pytest.fixture
    def solicitud_nueva(self, usuario_adoptante, mascota_disponible, respuestas_validas):
        respuestas, _ = cuestionario.validar({**respuestas_validas, 'horas_solo': '8+',
                                              'emergencia_veterinaria': 'espera', 'compromiso_tiempo': 'no'})
        solicitud = Solicitud(usuario_id=usuario_adoptante.id, mascota_id=mascota_disponible.id,
                              cuestionario=respuestas)
        db.session.add(solicitud)
        db.session.commit()
        return solicitud

    @pytest.mark.parametrize('ruta', ['/solicitudes/admin/revisar/{}', '/solicitudes/detalle/{}'])
    def test_etiquetas(self, client, auth_headers_admin, solicitud_nueva, ruta):
        html = contenido(client.get(ruta.format(solicitud_nueva.id)))

        assert 'Más de 8 horas' in html
        assert 'Esperaría a ver cómo evoluciona' in html
        assert 'No puedo garantizarlo' in html
        assert '>8+<' not in html and '>espera<' not in html
        # Las opcionales sin contestar
        assert html.count('Sin respuesta') == 2
        for pregunta in cuestionario.PREGUNTAS.values():
            assert str(escape(pregunta.texto)) in html, pregunta.texto

    def test_detalle_del_adoptante(self, client, auth_headers_adoptante, solicitud_nueva):
        html = contenido(client.get(f'/solicitudes/detalle/{solicitud_nueva.id}'))

        assert 'Más de 8 horas' in html

    @pytest.mark.parametrize('ruta', ['/solicitudes/admin/revisar/{}', '/solicitudes/detalle/{}'])
    @pytest.mark.parametrize('respuestas', [
        {'experiencia': 'Si, Beagle antes', 'vivienda': 'Casa con jardin'},
        {'tiene_jardin': 'Sí', 'horas_solo': ['8+'], 'compromiso_gastos': 'x'},
        {},
    ])
    def test_cuestionarios_antiguos_no_dan_error(self, client, auth_headers_admin, solicitud_pendiente,
                                                 ruta, respuestas):
        solicitud_pendiente.cuestionario_json = respuestas
        db.session.commit()

        response = client.get(ruta.format(solicitud_pendiente.id))

        assert response.status_code == 200
        assert 'Sin respuesta' in response.data.decode()


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
