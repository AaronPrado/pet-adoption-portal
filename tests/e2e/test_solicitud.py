"""
e2e de la solicitud de adopción: de la ficha de la mascota al cuestionario
enviado, solo con teclado (B4.4), con sus errores y con el aviso de solicitud
duplicada (P-44).
"""

import re

import pytest
from playwright.sync_api import expect

from app import db
from app.models import Mascota, Solicitud, Usuario
from tests.e2e.conftest import ADOPTANTE, iniciar_sesion

pytestmark = pytest.mark.e2e

HORAS = '¿Cuántas horas al día pasaría la mascota sin compañía?'
RESUMEN = 'Revisa estas respuestas antes de enviar la solicitud'


def _mascota(app_e2e, nombre, con_solicitud=False):
    """
    Una mascota nueva para un solo test (así no depende del orden de los
    demás). Devuelve su id y, si se pide, el de una solicitud de la adoptante.
    """
    with app_e2e.app_context():
        mascota = Mascota(nombre=nombre, especie='Perro', descripcion='Perro alegre y muy sociable')
        db.session.add(mascota)
        db.session.flush()
        solicitud = None
        if con_solicitud:
            adoptante = db.session.execute(db.select(Usuario).filter_by(email=ADOPTANTE[0])).scalar_one()
            solicitud = Solicitud(adoptante.id, mascota.id)
            db.session.add(solicitud)
        db.session.commit()
        return mascota.id, solicitud and solicitud.id


def tabular_hasta(page, destino, maximo=40):
    """Pulsa Tab hasta que `destino` tiene el foco, como haría alguien con teclado."""
    for _ in range(maximo):
        page.keyboard.press('Tab')
        if destino.evaluate('elemento => elemento === document.activeElement'):
            return
    raise AssertionError(f'{destino} no recibe el foco con Tab')


def grupo(page, pregunta):
    """El fieldset de una pregunta, por su legend."""
    return page.get_by_role('group', name=pregunta)


def pulsar(page, tecla, enfocado):
    """Pulsa `tecla` y comprueba adónde fue el foco."""
    page.keyboard.press(tecla)
    expect(enfocado).to_be_focused()


def test_cuestionario_completo_solo_con_teclado(page, errores_js, app_e2e):
    """Tab entre preguntas, flechas dentro de un grupo de radios, Espacio para marcar y Enter para enviar."""
    mascota_id, _ = _mascota(app_e2e, 'Kira')
    iniciar_sesion(page, *ADOPTANTE)
    page.goto(f'/mascotas/{mascota_id}')

    solicitar = page.get_by_role('link', name='Solicitar adopción')
    tabular_hasta(page, solicitar)
    page.keyboard.press('Enter')
    expect(page.get_by_role('heading', level=1, name='Solicitar la adopción de Kira')).to_be_visible()

    # Vivienda: con las flechas se cambia (y marca) la opción dentro del grupo
    vivienda = grupo(page, '¿En qué tipo de vivienda vives?')
    tabular_hasta(page, vivienda.get_by_role('radio', name='Casa'))
    pulsar(page, 'ArrowDown', vivienda.get_by_role('radio', name='Apartamento'))
    expect(vivienda.get_by_role('radio', name='Apartamento')).to_be_checked()

    propia = grupo(page, '¿Tu vivienda es propia o alquilada?').get_by_role('radio', name='Propia')
    pulsar(page, 'Tab', propia)
    page.keyboard.press('Space')
    expect(propia).to_be_checked()

    jardin = grupo(page, '¿Tienes jardín o patio?').get_by_role('radio', name='Sí')
    pulsar(page, 'Tab', jardin)
    page.keyboard.press('Space')

    otras = grupo(page, '¿Tienes otras mascotas?')
    pulsar(page, 'Tab', otras.get_by_role('radio', name='Sí'))
    pulsar(page, 'ArrowDown', otras.get_by_role('radio', name='No'))
    expect(otras.get_by_role('radio', name='No')).to_be_checked()

    # La pregunta opcional se salta con Tab
    pulsar(page, 'Tab', page.get_by_label('¿Qué otras mascotas tienes?'))
    pulsar(page, 'Tab', page.get_by_label('¿Tienes experiencia previa con mascotas?'))
    page.keyboard.type('He tenido perros toda la vida')

    horas = grupo(page, HORAS)
    pulsar(page, 'Tab', horas.get_by_role('radio', name='Menos de 4 horas'))
    pulsar(page, 'ArrowDown', horas.get_by_role('radio', name='De 4 a 8 horas'))

    pulsar(page, 'Tab', grupo(page, '¿Qué harías ante una emergencia veterinaria?').get_by_role('radio').first)
    page.keyboard.press('Space')

    pulsar(page, 'Tab', page.get_by_label('¿Por qué quieres adoptar?'))
    page.keyboard.type('Quiero darle un hogar a un perro alegre')

    for pregunta in ('cubrir los gastos veterinarios', 'dedicarle tiempo cada día'):
        compromiso = grupo(page, re.compile(pregunta)).get_by_role('radio', name='Sí, me comprometo')
        pulsar(page, 'Tab', compromiso)
        page.keyboard.press('Space')
        expect(compromiso).to_be_checked()

    pulsar(page, 'Tab', page.get_by_label('¿Tienes referencias personales o veterinarias?'))
    pulsar(page, 'Tab', page.get_by_role('button', name='Enviar solicitud'))
    page.keyboard.press('Enter')

    # P-24: la confirmación dice qué pasa ahora y dónde seguirla
    expect(page).to_have_url(re.compile('/solicitudes/mis-solicitudes'))
    expect(page.get_by_text('Hemos recibido tu solicitud para adoptar a Kira.')).to_be_visible()
    expect(page.get_by_text('El refugio revisará tus respuestas')).to_be_visible()


def test_error_lleva_al_resumen_y_del_resumen_a_la_pregunta(page, errores_js, app_e2e):
    """El foco va al resumen; su enlace lleva al fieldset de la pregunta, que anuncia su error."""
    mascota_id, _ = _mascota(app_e2e, 'Bruno')
    iniciar_sesion(page, *ADOPTANTE)
    page.goto(f'/solicitudes/nueva/{mascota_id}')

    grupo(page, '¿En qué tipo de vivienda vives?').get_by_role('radio', name='Casa').check()
    grupo(page, '¿Tu vivienda es propia o alquilada?').get_by_role('radio', name='Alquilada').check()
    grupo(page, '¿Tienes jardín o patio?').get_by_role('radio', name='No').check()
    grupo(page, '¿Tienes otras mascotas?').get_by_role('radio', name='No').check()
    page.get_by_label('¿Tienes experiencia previa con mascotas?').fill('Dos gatos durante diez años')
    grupo(page, '¿Qué harías ante una emergencia veterinaria?').get_by_role('radio').first.check()
    page.get_by_label('¿Por qué quieres adoptar?').fill('Tenemos tiempo y un piso grande')
    for pregunta in ('cubrir los gastos veterinarios', 'dedicarle tiempo cada día'):
        grupo(page, re.compile(pregunta)).get_by_role('radio', name='Sí, me comprometo').check()
    # Sin contestar las horas. `required` lo frenaría en el navegador; aquí se
    # prueba la validación del servidor, que es la que vale (y la de la API)
    enviar = page.get_by_role('button', name='Enviar solicitud')
    enviar.evaluate('boton => { boton.form.noValidate = true; }')
    enviar.click()

    resumen = page.get_by_role('group', name=RESUMEN)
    expect(resumen).to_be_focused()
    enlace = resumen.get_by_role('link', name=f'{HORAS} Esta pregunta es obligatoria.')
    expect(resumen.get_by_role('link')).to_have_count(1)

    pulsar(page, 'Tab', enlace)
    page.keyboard.press('Enter')
    horas = grupo(page, HORAS)
    expect(horas).to_be_focused()
    expect(horas).to_have_accessible_description('Error: Esta pregunta es obligatoria.')
    expect(horas.get_by_role('radio').first).to_have_attribute('aria-invalid', 'true')

    # Lo contestado sigue ahí
    expect(page.get_by_label('¿Tienes experiencia previa con mascotas?')).to_have_value('Dos gatos durante diez años')
    expect(grupo(page, '¿Tu vivienda es propia o alquilada?').get_by_role('radio', name='Alquilada')).to_be_checked()

    # Desde el grupo, Tab entra en sus opciones
    pulsar(page, 'Tab', horas.get_by_role('radio', name='Menos de 4 horas'))
    page.keyboard.press('Space')
    page.get_by_role('button', name='Enviar solicitud').click()
    expect(page.get_by_text('Hemos recibido tu solicitud para adoptar a Bruno.')).to_be_visible()


def test_quien_ya_la_solicito_va_a_su_solicitud(page, errores_js, app_e2e):
    """P-44: «Ya tienes una solicitud para Simba», en la propia solicitud, no «ya no está disponible»."""
    mascota_id, solicitud_id = _mascota(app_e2e, 'Simba', con_solicitud=True)
    iniciar_sesion(page, *ADOPTANTE)

    page.goto(f'/mascotas/{mascota_id}')
    page.get_by_role('link', name='Solicitar adopción').click()

    expect(page).to_have_url(re.compile(rf'/solicitudes/detalle/{solicitud_id}$'))
    expect(page.get_by_text('Ya tienes una solicitud para Simba.')).to_be_visible()
    expect(page.get_by_text('ya no está disponible')).to_have_count(0)


def test_login_desde_la_ficha_vuelve_al_cuestionario(page, errores_js, mascotas):
    """El anónimo que pulsa «Inicia sesión para solicitar la adopción» acaba en el cuestionario."""
    page.goto(f'/mascotas/{mascotas["Misu"]}')
    page.get_by_role('link', name='Inicia sesión para solicitar la adopción').click()

    # Un primer intento fallido conserva el correo y el destino
    page.get_by_label('Correo electrónico').fill(ADOPTANTE[0])
    page.get_by_label('Contraseña').fill('clave-equivocada')
    page.get_by_role('button', name='Iniciar Sesión').click()
    expect(page.get_by_role('link', name='Correo o contraseña incorrectos.')).to_be_visible()
    expect(page.get_by_label('Correo electrónico')).to_have_value(ADOPTANTE[0])
    expect(page.get_by_label('Contraseña')).to_have_value('')

    page.get_by_label('Contraseña').fill(ADOPTANTE[1])
    page.get_by_role('button', name='Iniciar Sesión').click()

    expect(page).to_have_url(re.compile(r'/solicitudes/nueva/\d+$'))
    expect(page.get_by_role('heading', level=1, name='Solicitar la adopción de Misu')).to_be_visible()
