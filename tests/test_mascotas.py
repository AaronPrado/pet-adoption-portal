"""
Tests para el módulo de mascotas.

Tests incluidos:
- CRUD de mascotas (crear, leer, actualizar, eliminar)
- Catálogo público con filtros
- Panel de administración
- Validaciones y permisos
"""

import pytest

from app import db
from app.models import Mascota


class TestCatalogo:
    """Tests para el catálogo público de mascotas."""

    def test_catalogo_muestra_mascotas_disponibles(self, client, mascota_disponible):
        """Test: El catálogo muestra mascotas disponibles."""
        response = client.get('/mascotas/catalogo')

        assert response.status_code == 200
        assert 'Cerbero' in response.data.decode()
        assert 'Chihuahua' in response.data.decode()

    def test_catalogo_no_muestra_mascotas_adoptadas(self, client, mascota_disponible):
        """Test: El catálogo no muestra mascotas adoptadas."""
        # Marcar como adoptada
        mascota_disponible.estado = 'adoptado'
        db.session.commit()

        response = client.get('/mascotas/catalogo')

        assert response.status_code == 200
        assert 'Cerbero' not in response.data.decode()

    def test_catalogo_filtro_especie(self, client, mascota_disponible):
        """Test: Filtro por especie funciona correctamente."""
        # Crear gato
        gato = Mascota(
            nombre='Michi',
            especie='Gato',
            descripcion='Gata cariñosa y tranquila',
            estado='disponible'
        )
        db.session.add(gato)
        db.session.commit()

        # Filtrar por Perro
        response = client.get('/mascotas/catalogo?especie=Perro')
        assert 'Cerbero' in response.data.decode()
        assert 'Michi' not in response.data.decode()

        # Filtrar por Gato
        response = client.get('/mascotas/catalogo?especie=Gato')
        assert 'Michi' in response.data.decode()
        assert 'Cerbero' not in response.data.decode()

    def test_catalogo_filtro_especie_una_opcion_por_especie(self, client, mascota_disponible):
        """P-31: «perro» y « PERRO » se guardan como «Perro» y salen una sola vez en el filtro."""
        for nombre, especie in (('Bobi', 'perro'), ('Rex', ' PERRO ')):
            db.session.add(Mascota(nombre=nombre, especie=especie,
                                   descripcion='Perro sociable y tranquilo', estado='disponible'))
        db.session.commit()

        html = client.get('/mascotas/catalogo').data.decode()
        assert html.count('<option value="Perro"') == 1
        assert 'value="perro"' not in html and 'value="PERRO"' not in html

        html = client.get('/mascotas/catalogo?especie=Perro').data.decode()
        assert all(nombre in html for nombre in ('Cerbero', 'Bobi', 'Rex'))

    def test_catalogo_filtro_tamano(self, client, mascota_disponible):
        """Test: Filtro por tamaño funciona correctamente."""
        response = client.get('/mascotas/catalogo?tamano=Pequeño')

        assert response.status_code == 200
        assert 'Cerbero' in response.data.decode()

    def test_catalogo_filtro_sexo(self, client, mascota_disponible):
        """Test: Filtro por sexo funciona correctamente."""
        response = client.get('/mascotas/catalogo?sexo=Macho')

        assert response.status_code == 200
        assert 'Cerbero' in response.data.decode()

    def test_catalogo_filtro_edad_maxima(self, client, mascota_disponible):
        """Test: Filtro por edad máxima funciona correctamente."""
        # El formulario del catálogo envía el parámetro "edad"
        response = client.get('/mascotas/catalogo?edad=5')

        assert response.status_code == 200
        # Cerbero tiene 3 años
        assert 'Cerbero' in response.data.decode()

        response = client.get('/mascotas/catalogo?edad=2')
        assert 'Cerbero' not in response.data.decode()


class TestDetalle:
    """Tests para la página de detalle de mascota."""

    def test_detalle_muestra_mascota(self, client, mascota_disponible):
        """Test: La página de detalle muestra información completa."""
        response = client.get(f'/mascotas/{mascota_disponible.id}')

        assert response.status_code == 200
        assert 'Cerbero' in response.data.decode()
        assert 'Chihuahua' in response.data.decode()
        assert 'amigable' in response.data.decode()

    def test_detalle_mascota_inexistente(self, client):
        """Test: Mascota inexistente retorna 404."""
        response = client.get('/mascotas/99999')

        assert response.status_code == 404

    def test_detalle_boton_adoptar_disponible(self, client, auth_headers_adoptante, mascota_disponible):
        """Test: Botón de adopción visible si mascota disponible."""
        response = client.get(f'/mascotas/{mascota_disponible.id}')

        assert response.status_code == 200
        assert 'Solicitar' in response.data.decode() or 'Adoptar' in response.data.decode()

    def test_detalle_no_boton_si_adoptada(self, client, auth_headers_adoptante, mascota_disponible):
        """Test: No mostrar botón si mascota adoptada."""
        mascota_disponible.estado = 'adoptado'
        db.session.commit()

        response = client.get(f'/mascotas/{mascota_disponible.id}')

        assert response.status_code == 200
        assert 'Adoptad' in response.data.decode()


class TestAdminPanel:
    """Tests para el panel de administración de mascotas."""

    def test_admin_panel_requiere_autenticacion(self, client):
        """Test: Panel admin requiere login."""
        response = client.get('/mascotas/admin', follow_redirects=True)

        assert response.status_code == 200
        assert 'Iniciar Sesión' in response.data.decode() or 'Login' in response.data.decode()

    def test_admin_panel_solo_admin(self, client, auth_headers_adoptante):
        """Test: Solo admin puede acceder al panel."""
        response = client.get('/mascotas/admin', follow_redirects=True)

        assert response.status_code == 200
        # Debe denegar acceso o redirigir
        content = response.data.decode().lower()
        assert 'admin' in content or 'permiso' in content or 'no tienes' in content

    def test_admin_panel_muestra_todas_mascotas(self, client, auth_headers_admin,
                                                mascota_disponible, mascota_adoptada):
        """Test: Panel admin muestra todas las mascotas."""
        response = client.get('/mascotas/admin')

        assert response.status_code == 200
        assert 'Cerbero' in response.data.decode()
        assert 'Luna' in response.data.decode()

    def test_admin_panel_filtro_estado(self, client, auth_headers_admin, mascota_disponible, mascota_adoptada):
        """Test: Filtro por estado en panel admin."""
        response = client.get('/mascotas/admin?estado=disponible')

        assert response.status_code == 200
        assert 'Cerbero' in response.data.decode()
        assert 'Luna' not in response.data.decode()


class TestCRUD:
    """Tests para operaciones CRUD de mascotas."""

    def test_crear_mascota_requiere_admin(self, client, auth_headers_adoptante):
        """Test: Solo admin puede crear mascotas."""
        response = client.get('/mascotas/admin/nueva', follow_redirects=True)

        assert response.status_code == 200
        content = response.data.decode().lower()
        assert 'admin' in content or 'permiso' in content or 'no tienes' in content

    def test_crear_mascota_exitoso(self, client, auth_headers_admin):
        """Test: Admin puede crear mascota."""
        response = client.post('/mascotas/admin/nueva', data={
            'nombre': 'Rocky',
            'especie': 'Perro',
            'raza': 'Pastor Alemán',
            'edad_aprox': 5,
            'sexo': 'Macho',
            'tamano': 'Grande',
            'descripcion': 'Perro guardián muy leal y protector',
            'foto_url': 'https://example.com/rocky.jpg',
            'vacunado': 'on',
            'esterilizado': 'on'
        }, follow_redirects=True)

        assert response.status_code == 200
        assert 'creada exitosamente' in response.data.decode() or 'Rocky' in response.data.decode()

        # Verificar en BD
        mascota = Mascota.query.filter_by(nombre='Rocky').first()
        assert mascota is not None
        assert mascota.especie == 'Perro'
        assert mascota.estado == 'disponible'

    def test_crear_mascota_normaliza_la_especie(self, client, auth_headers_admin):
        """P-31: el alta por el panel guarda la especie normalizada."""
        client.post('/mascotas/admin/nueva', data={
            'nombre': 'Rocky',
            'especie': '  pERRO ',
            'descripcion': 'Perro guardián muy leal y protector',
        })

        assert Mascota.query.filter_by(nombre='Rocky').one().especie == 'Perro'

    def test_editar_mascota(self, client, auth_headers_admin, mascota_disponible):
        """Test: Admin puede editar mascota."""
        response = client.post(f'/mascotas/admin/editar/{mascota_disponible.id}', data={
            'nombre': 'Cerbero Editado',
            'especie': 'Perro',
            'raza': 'Golden Retriever',
            'edad_aprox': 4,
            'sexo': 'Macho',
            'tamano': 'Grande',
            'descripcion': 'Descripción actualizada con más detalle',
            'foto_url': mascota_disponible.foto_url,
            'estado': 'disponible',
            'vacunado': 'on',
            'esterilizado': 'on'
        }, follow_redirects=True)

        assert response.status_code == 200

        # Verificar cambios
        db.session.refresh(mascota_disponible)
        assert mascota_disponible.nombre == 'Cerbero Editado'
        assert mascota_disponible.raza == 'Golden Retriever'

    def test_editar_mascota_normaliza_la_especie(self, client, auth_headers_admin, mascota_disponible):
        """P-31: la edición por el panel guarda la especie normalizada."""
        client.post(f'/mascotas/admin/editar/{mascota_disponible.id}', data={
            'nombre': mascota_disponible.nombre,
            'especie': 'gATO',
            'descripcion': mascota_disponible.descripcion,
            'foto_url': mascota_disponible.foto_url,
        })

        db.session.refresh(mascota_disponible)
        assert mascota_disponible.especie == 'Gato'

    def test_eliminar_mascota(self, client, auth_headers_admin, mascota_disponible):
        """Test: Admin puede eliminar mascota."""
        mascota_id = mascota_disponible.id

        response = client.post(f'/mascotas/admin/eliminar/{mascota_id}', follow_redirects=True)

        assert response.status_code == 200

        # Verificar que fue eliminada
        mascota = db.session.get(Mascota, mascota_id)
        assert mascota is None


class TestModelo:
    """Tests para el modelo Mascota."""

    def test_crear_mascota(self, app):
        """Test: Crear mascota correctamente."""
        mascota = Mascota(
            nombre='Test',
            especie='Perro',
            descripcion='Descripción test'
        )
        db.session.add(mascota)
        db.session.commit()

        # Verificar valores por defecto
        assert mascota.estado == 'disponible'
        assert mascota.vacunado is False
        assert mascota.esterilizado is False

    @pytest.mark.parametrize(('entrada', 'esperada'), [
        ('perro', 'Perro'),
        (' PERRO ', 'Perro'),
        ('gATO', 'Gato'),
        ('ñandú', 'Ñandú'),
        # Dos palabras: mayúscula solo al inicio y un único espacio entre ellas
        ('  cobaya   DE indias ', 'Cobaya de indias'),
        ('Conejo\tenano', 'Conejo enano'),
        # Casos adversos: deben dar la misma opción en el filtro
        ('n\u0303andu\u0301', 'Ñandú'),               # NFD: letra + tilde combinante
        ('cobaya\xa0de\xa0indias', 'Cobaya de indias'),  # NBSP
        ('pe\u200brro', 'Perro'),                       # U+200B, espacio de anchura cero
        ('\tperro\n', 'Perro'),
        ('gato\r\n\tmontés', 'Gato montés'),
        ('ßpecies', 'Sspecies'),                         # «ß» en mayúscula es «Ss»
        ('x' * 50, 'X' + 'x' * 49),                      # justo la longitud de la columna
    ])
    def test_especie_se_normaliza(self, app, entrada, esperada):
        """P-31: la especie se guarda sin espacios sobrantes y con mayúscula inicial."""
        mascota = Mascota(nombre='Test', especie=entrada, descripcion='Descripción test')
        assert mascota.especie == esperada

        mascota.especie = entrada
        assert mascota.especie == esperada

    @pytest.mark.parametrize('entrada', ['', '   ', '\t\n', '\u200b', '\xa0'])
    def test_especie_vacia_no_se_admite(self, app, entrada):
        """P-31: una especie vacía, solo con espacios o con invisibles se rechaza."""
        with pytest.raises(ValueError, match='obligatoria'):
            Mascota(nombre='Test', especie=entrada, descripcion='Descripción test')

    @pytest.mark.parametrize('entrada', [None, 7, b'perro'])
    def test_especie_que_no_es_texto_no_se_admite(self, app, entrada):
        with pytest.raises(ValueError, match='texto'):
            Mascota(nombre='Test', especie=entrada, descripcion='Descripción test')

    @pytest.mark.parametrize('entrada', ['x' * 51, 'ß' * 50])
    def test_especie_demasiado_larga_no_se_admite(self, app, entrada):
        """Se rechaza en el modelo, no con un error de BD; «ß» * 50 pasa a 51 caracteres."""
        with pytest.raises(ValueError, match='50 caracteres'):
            Mascota(nombre='Test', especie=entrada, descripcion='Descripción test')

    def test_esta_disponible(self, app, mascota_disponible):
        """Test: Método esta_disponible() funciona."""
        assert mascota_disponible.esta_disponible() is True

        mascota_disponible.estado = 'adoptado'
        assert mascota_disponible.esta_disponible() is False

    def test_marcar_adoptado(self, app, mascota_disponible):
        """Test: Marcar mascota como adoptada."""
        mascota_disponible.marcar_adoptado()
        db.session.commit()

        db.session.refresh(mascota_disponible)
        assert mascota_disponible.estado == 'adoptado'

    def test_tiene_solicitudes_pendientes(self, app, mascota_disponible, solicitud_pendiente):
        """Test: Verificar si tiene solicitudes pendientes."""
        assert mascota_disponible.tiene_solicitudes_pendientes() is True

    def test_repr_mascota(self, app, mascota_disponible):
        """Test: Representación en string de mascota."""
        repr_str = repr(mascota_disponible)

        assert 'Mascota' in repr_str
        assert 'Cerbero' in repr_str
        assert 'Perro' in repr_str
        assert 'disponible' in repr_str


class TestAvisoSolicitudesEnCurso:
    """ADR-0004: con pendientes, la mascota sigue en el catálogo con un aviso."""

    AVISO = 'Tiene solicitudes en curso'

    def test_catalogo_muestra_el_aviso(self, client, solicitud_pendiente):
        html = client.get('/mascotas/catalogo').data.decode()

        assert 'Cerbero' in html
        assert html.count(self.AVISO) == 1

    def test_catalogo_sin_pendientes_sin_aviso(self, client, mascota_disponible):
        assert self.AVISO not in client.get('/mascotas/catalogo').data.decode()

    def test_catalogo_solo_avisa_en_la_mascota_con_pendientes(self, client, solicitud_pendiente):
        db.session.add(Mascota(nombre='Michi', especie='Gato', descripcion='Gata cariñosa y tranquila'))
        db.session.commit()

        html = client.get('/mascotas/catalogo').data.decode()

        assert html.count(self.AVISO) == 1

    def test_detalle_muestra_el_aviso(self, client, solicitud_pendiente):
        html = client.get(f'/mascotas/{solicitud_pendiente.mascota_id}').data.decode()

        assert self.AVISO in html
        assert 'Disponible para adopción' in html

    def test_detalle_sin_pendientes_sin_aviso(self, client, mascota_disponible):
        assert self.AVISO not in client.get(f'/mascotas/{mascota_disponible.id}').data.decode()

    def test_detalle_rechazada_sin_aviso(self, client, solicitud_pendiente):
        solicitud_pendiente.estado = 'rechazada'
        db.session.commit()

        assert self.AVISO not in client.get(f'/mascotas/{solicitud_pendiente.mascota_id}').data.decode()

    def test_detalle_sin_en_proceso(self, client, mascota_disponible):
        mascota_disponible.estado = 'en_proceso'
        db.session.commit()

        html = client.get(f'/mascotas/{mascota_disponible.id}').data.decode()

        assert 'En proceso de adopción' not in html
        assert 'Adoptada' not in html
