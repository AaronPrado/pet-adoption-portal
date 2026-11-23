"""e2e de las solicitudes del adoptante: la lista con sus estados, el detalle y el estado vacío."""

import pytest
from playwright.sync_api import expect

from app import db
from app.models import Mascota, Solicitud, Usuario
from tests.e2e.conftest import iniciar_sesion

pytestmark = pytest.mark.e2e

CON_SOLICITUDES = ('solicitudes@e2e.test', 'clave-solicitudes-e2e')
SIN_SOLICITUDES = ('vacio@e2e.test', 'clave-vacio-e2e')


@pytest.fixture(scope='module')
def solicitudes(app_e2e):
    """
    Un adoptante con una solicitud pendiente, otra aprobada y otra rechazada
    (con mensaje del refugio), y otro sin ninguna. Las mascotas son conejos,
    para no alterar los filtros del catálogo de los otros módulos.
    """
    with app_e2e.app_context():
        usuario = Usuario(email=CON_SOLICITUDES[0], nombre='Lucía', password=CON_SOLICITUDES[1])
        sin = Usuario(email=SIN_SOLICITUDES[0], nombre='Mario', password=SIN_SOLICITUDES[1])
        admin = db.session.execute(db.select(Usuario).filter_by(rol='admin')).scalars().first()
        mascotas = [Mascota(nombre=nombre, especie='Conejo', descripcion='Conejo tranquilo y cariñoso')
                    for nombre in ('Pelusa', 'Canela', 'Trébol')]
        db.session.add_all([usuario, sin, *mascotas])
        db.session.flush()
        pendiente, aprobada, rechazada = (Solicitud(usuario_id=usuario.id, mascota_id=m.id) for m in mascotas)
        aprobada.registrar_revision('aprobada', admin.id, 'Pasa el sábado por la protectora')
        rechazada.registrar_revision('rechazada', admin.id, 'Vivienda demasiado pequeña')
        db.session.add_all([pendiente, aprobada, rechazada])
        db.session.commit()
        return {mascota.nombre: solicitud.id
                for mascota, solicitud in zip(mascotas, (pendiente, aprobada, rechazada), strict=True)}


def test_lista_con_estados_y_enlaces_unicos(page, errores_js, solicitudes):
    iniciar_sesion(page, *CON_SOLICITUDES)

    page.goto('/solicitudes/mis-solicitudes')

    expect(page.get_by_role('heading', level=1, name='Mis solicitudes')).to_be_visible()
    for mascota, estado in (('Pelusa', 'Pendiente'), ('Canela', 'Aprobada'), ('Trébol', 'Rechazada')):
        tarjeta = page.get_by_role('article').filter(has=page.get_by_role('heading', name=mascota))
        expect(tarjeta.get_by_text(estado, exact=True)).to_be_visible()
        expect(tarjeta.get_by_role('link', name=f'Ver la solicitud de {mascota}')).to_be_visible()
    rechazada = page.get_by_role('article').filter(has=page.get_by_role('heading', name='Trébol'))
    expect(rechazada.get_by_text('Mensaje del refugio')).to_be_visible()
    expect(rechazada.get_by_text('Vivienda demasiado pequeña')).to_be_visible()


def test_detalle_con_que_pasa_ahora(page, errores_js, solicitudes):
    iniciar_sesion(page, *CON_SOLICITUDES)
    page.goto('/solicitudes/mis-solicitudes')

    page.get_by_role('link', name='Ver la solicitud de Pelusa').click()

    expect(page.get_by_role('heading', level=1, name='Solicitud de Pelusa')).to_be_visible()
    expect(page.get_by_role('heading', name='Qué pasa ahora')).to_be_visible()
    expect(page.get_by_text('Estamos revisando tu solicitud')).to_be_visible()
    expect(page.get_by_role('heading', name='Respuestas del cuestionario')).to_be_visible()
    page.get_by_role('link', name='Volver a mis solicitudes').click()
    expect(page.get_by_role('heading', level=1, name='Mis solicitudes')).to_be_visible()


def test_detalle_rechazada_ofrece_otras_mascotas(page, errores_js, solicitudes):
    iniciar_sesion(page, *CON_SOLICITUDES)

    page.goto(f'/solicitudes/detalle/{solicitudes["Trébol"]}')

    expect(page.get_by_text('Esta vez no ha podido ser')).to_be_visible()
    expect(page.get_by_role('heading', name='Mensaje del refugio')).to_be_visible()
    page.get_by_role('link', name='Ver mascotas disponibles').click()
    expect(page.get_by_role('heading', level=1, name='Mascotas en adopción')).to_be_visible()


def test_detalle_aprobada(page, errores_js, solicitudes):
    iniciar_sesion(page, *CON_SOLICITUDES)

    page.goto(f'/solicitudes/detalle/{solicitudes["Canela"]}')

    expect(page.get_by_text('¡Enhorabuena!')).to_be_visible()
    expect(page.get_by_text('Pasa el sábado por la protectora')).to_be_visible()


def test_estado_vacio_enlaza_al_catalogo(page, errores_js, solicitudes):
    iniciar_sesion(page, *SIN_SOLICITUDES)

    page.goto('/solicitudes/mis-solicitudes')

    expect(page.get_by_role('heading', name='Aún no tienes solicitudes')).to_be_visible()
    page.get_by_role('link', name='Ver mascotas disponibles').click()
    expect(page.get_by_role('heading', level=1, name='Mascotas en adopción')).to_be_visible()


def test_sin_scroll_horizontal_en_movil(page, errores_js, solicitudes):
    iniciar_sesion(page, *CON_SOLICITUDES)
    page.set_viewport_size({'width': 320, 'height': 700})

    for url in ('/solicitudes/mis-solicitudes', f'/solicitudes/detalle/{solicitudes["Trébol"]}'):
        page.goto(url)
        assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), url
