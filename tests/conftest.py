"""
Configuración de pytest y fixtures para testing.

Este archivo contiene las fixtures reutilizables para todos los tests.
Las fixtures proporcionan datos de prueba y configuración del entorno de testing.
"""

import pytest
from flask import g

from app import create_app, db
from app.models import Mascota, Solicitud, Usuario


@pytest.fixture(scope='function')
def app(tmp_path):
    """
    Fixture que crea una instancia de la aplicación Flask en modo testing.

    Cada test obtiene una aplicación nueva con una BD en memoria SQLite y
    un directorio de fotos temporal (backend local).
    Después de cada test, la BD se destruye automáticamente.

    Yields:
        Flask: Instancia de la aplicación en modo testing
    """
    # Crear app en modo testing
    app = create_app('testing')
    app.config.update(FOTOS_BACKEND='local', FOTOS_DIR=str(tmp_path / 'fotos'))

    # El contexto de aplicación del fixture sigue activo durante las
    # peticiones del cliente, así que todas comparten `g`. Flask-Login guarda
    # ahí el usuario cargado y, sin limpiarlo, load_user no se volvía a
    # ejecutar en las peticiones siguientes (en producción cada petición
    # tiene su propio `g`).
    @app.teardown_request
    def limpiar_usuario_cargado(exc):
        g.pop('_login_user', None)

    # Establecer contexto de aplicación
    with app.app_context():
        # Crear todas las tablas
        db.create_all()

        yield app

        # Limpiar después del test
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """
    Fixture que proporciona un cliente de testing de Flask.

    Permite hacer peticiones HTTP a la aplicación sin levantar un servidor.

    Args:
        app: Fixture de aplicación Flask

    Returns:
        FlaskClient: Cliente para hacer peticiones de prueba
    """
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """
    Fixture que proporciona un runner de comandos CLI.

    Útil para probar comandos personalizados de Flask.

    Args:
        app: Fixture de aplicación Flask

    Returns:
        FlaskCliRunner: Runner para comandos CLI
    """
    return app.test_cli_runner()


@pytest.fixture(scope='function')
def usuario_adoptante(app):
    """
    Fixture que crea un usuario adoptante de prueba.

    Args:
        app: Fixture de aplicación Flask

    Returns:
        Usuario: Usuario con rol 'adoptante'
    """
    usuario = Usuario(
        email='adoptante@test.com',
        nombre='Pepe',
        password='password123',
        rol='adoptante'
    )
    usuario.apellidos = 'Pérez Pérez'
    usuario.telefono = '612345678'
    usuario.direccion = 'Calle Test 123, Lugo'

    db.session.add(usuario)
    db.session.commit()

    return usuario


@pytest.fixture(scope='function')
def usuario_admin(app):
    """
    Fixture que crea un usuario administrador de prueba.

    Args:
        app: Fixture de aplicación Flask

    Returns:
        Usuario: Usuario con rol 'admin'
    """
    admin = Usuario(
        email='admin@test.com',
        nombre='Admin Test',
        password='admin123',
        rol='admin'
    )

    db.session.add(admin)
    db.session.commit()

    return admin


@pytest.fixture(scope='function')
def mascota_disponible(app):
    """
    Fixture que crea una mascota disponible para adopción.

    Args:
        app: Fixture de aplicación Flask

    Returns:
        Mascota: Mascota con estado 'disponible'
    """
    mascota = Mascota(
        nombre='Cerbero',
        especie='Perro',
        descripcion='Perro muy amigable y juguetón',
        raza='Chihuahua',
        edad_aprox=3,
        sexo='Macho',
        tamano='Pequeño',
        estado='disponible',
        foto_url='https://images.unsplash.com/photo-1587300003388-59208cc962cb',
        vacunado=True,
        esterilizado=True
    )

    db.session.add(mascota)
    db.session.commit()

    return mascota


@pytest.fixture(scope='function')
def mascota_adoptada(app):
    """
    Fixture que crea una mascota ya adoptada (fuera del catálogo).

    Args:
        app: Fixture de aplicación Flask

    Returns:
        Mascota: Mascota con estado 'adoptado'
    """
    mascota = Mascota(
        nombre='Luna',
        especie='Gato',
        descripcion='Gata tranquila y cariñosa',
        raza='Siamés',
        edad_aprox=2,
        sexo='Hembra',
        tamano='Pequeño',
        estado='adoptado',
        foto_url='https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba',
        vacunado=True,
        esterilizado=True
    )

    db.session.add(mascota)
    db.session.commit()

    return mascota


@pytest.fixture
def respuestas_validas():
    """
    Respuestas válidas del cuestionario (app/cuestionario.py), tal como las
    envían el formulario web y la API. Cada test recibe una copia nueva.
    """
    return {
        'vivienda_tipo': 'casa',
        'vivienda_propia': 'propia',
        'tiene_jardin': 'si',
        'tiene_mascotas': 'no',
        'experiencia_previa': 'He tenido perros toda la vida',
        'horas_solo': '0-4',
        'emergencia_veterinaria': 'veterinario',
        'motivo_adopcion': 'Quiero darle un hogar a un perro tranquilo',
        'compromiso_gastos': 'si',
        'compromiso_tiempo': 'si',
    }


@pytest.fixture(scope='function')
def solicitud_pendiente(app, usuario_adoptante, mascota_disponible):
    """
    Fixture que crea una solicitud de adopción pendiente.

    Args:
        app: Fixture de aplicación Flask
        usuario_adoptante: Fixture de usuario adoptante
        mascota_disponible: Fixture de mascota disponible

    Returns:
        Solicitud: Solicitud con estado 'pendiente'
    """
    cuestionario = {
        'tipo_vivienda': 'Casa',
        'vivienda_propia': 'Sí',
        'tiene_jardin': 'Sí',
        'otras_mascotas': 'No',
        'experiencia_previa': 'Sí, he tenido perros antes',
        'horas_solo': '4-6 horas',
        'gastos_veterinarios': 'Sí',
        'tiempo_dedicado': '2-3 horas diarias',
        'motivo_adopcion': 'Quiero un compañero para mi familia',
        'que_harias_emergencia': 'Llevaría al veterinario inmediatamente',
        'compromisos': 'Sí, estoy comprometido',
        'referencias': 'Ana García (amiga) - 654321987'
    }

    solicitud = Solicitud(
        usuario_id=usuario_adoptante.id,
        mascota_id=mascota_disponible.id,
        cuestionario=cuestionario
    )

    db.session.add(solicitud)
    db.session.commit()

    return solicitud


@pytest.fixture(scope='function')
def auth_headers_adoptante(client, usuario_adoptante):
    """
    Fixture que proporciona headers de autenticación para un adoptante.

    Inicia sesión y retorna las cookies de sesión necesarias.

    Args:
        client: Fixture de cliente Flask
        usuario_adoptante: Fixture de usuario adoptante

    Returns:
        dict: Headers con cookies de sesión
    """
    client.post('/auth/login', data={
        'email': 'adoptante@test.com',
        'password': 'password123'
    }, follow_redirects=True)

    return {}


@pytest.fixture(scope='function')
def auth_headers_admin(client, usuario_admin):
    """
    Fixture que proporciona headers de autenticación para un admin.

    Inicia sesión y retorna las cookies de sesión necesarias.

    Args:
        client: Fixture de cliente Flask
        usuario_admin: Fixture de usuario admin

    Returns:
        dict: Headers con cookies de sesión
    """
    client.post('/auth/login', data={
        'email': 'admin@test.com',
        'password': 'admin123'
    }, follow_redirects=True)

    return {}
