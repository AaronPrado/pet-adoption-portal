"""
Solicitudes del adoptante sin Bootstrap (B4.5: P-24, P-26, P-35, P-41, P-42):
`mis_solicitudes.html`, `detalle.html` y la variante de respuestas de la base nueva.
"""

import re

import pytest

from app import adopciones, cuestionario, db
from app.models import Mascota, Solicitud, Usuario
from tests.test_catalogo_paginas import CLASES_BOOTSTRAP, html_de
from tests.test_fechas import utc

LISTA = '/solicitudes/mis-solicitudes'


def detalle(solicitud):
    return f'/solicitudes/detalle/{solicitud.id}'


def resolver(solicitud, estado, admin, mensaje=None):
    solicitud.registrar_revision(estado, admin.id, mensaje)
    db.session.commit()


def h1_de(html):
    return re.findall(r'<h1[^>]*>([^<]+)</h1>', html)


class TestLista:

    def test_sin_bootstrap_un_h1_y_titulo(self, client, auth_headers_adoptante, solicitud_pendiente):
        html = html_de(client, LISTA)

        assert not CLASES_BOOTSTRAP.search(html)
        assert 'bootstrap' not in html.lower()
        assert h1_de(html) == ['Mis solicitudes']
        assert '<title>Mis solicitudes - ' in html
        assert 'css/paginas/solicitudes.css' in html

    def test_cada_solicitud_es_un_article_con_su_estado_y_enlace_unico(
            self, client, auth_headers_adoptante, solicitud_pendiente):
        html = html_de(client, LISTA)

        assert '<article' in html
        assert re.search(r'<h2[^>]*>Cerbero</h2>', html)
        assert 'chapa--aviso' in html and 'Pendiente' in html
        assert f'href="{detalle(solicitud_pendiente)}"' in html
        assert 'Ver la solicitud de Cerbero</a>' in html
        assert 'Ver Detalles' not in html

    def test_enlaces_con_nombre_distinto_por_solicitud(self, client, auth_headers_adoptante,
                                                       solicitud_pendiente, mascota_adoptada, usuario_adoptante):
        db.session.add(Solicitud(usuario_id=usuario_adoptante.id, mascota_id=mascota_adoptada.id))
        db.session.commit()

        html = html_de(client, LISTA)
        nombres = re.findall(r'>(Ver la solicitud de [^<]+)</a>', html)

        assert sorted(nombres) == ['Ver la solicitud de Cerbero', 'Ver la solicitud de Luna']

    def test_las_mas_recientes_primero(self, client, auth_headers_adoptante, solicitud_pendiente,
                                       mascota_adoptada, usuario_adoptante):
        solicitud_pendiente.fecha_solicitud = utc(2026, 1, 1, 10, 0)
        db.session.add(Solicitud(usuario_id=usuario_adoptante.id, mascota_id=mascota_adoptada.id))
        db.session.commit()

        html = html_de(client, LISTA)

        assert html.index('Luna') < html.index('Cerbero')

    @pytest.mark.parametrize('estado, tono, etiqueta', [
        ('aprobada', 'exito', 'Aprobada'),
        ('rechazada', 'error', 'Rechazada'),
    ])
    def test_estados_resueltos(self, client, auth_headers_adoptante, solicitud_pendiente, usuario_admin,
                               estado, tono, etiqueta):
        resolver(solicitud_pendiente, estado, usuario_admin)

        html = html_de(client, LISTA)

        assert f'chapa--{tono}' in html and etiqueta in html

    def test_fechas_en_hora_de_madrid(self, client, auth_headers_adoptante, solicitud_pendiente, usuario_admin):
        solicitud_pendiente.fecha_solicitud = utc(2026, 11, 15, 23, 30)  # UTC
        resolver(solicitud_pendiente, 'aprobada', usuario_admin)
        solicitud_pendiente.fecha_revision = utc(2026, 7, 15, 12, 0)  # UTC
        db.session.commit()

        html = html_de(client, LISTA)

        assert 'Enviada el 16 de noviembre de 2026' in html
        assert 'Revisada el 15 de julio de 2026' in html
        assert '15/11/2026' not in html

    def test_mensaje_del_refugio(self, client, auth_headers_adoptante, solicitud_pendiente, usuario_admin):
        resolver(solicitud_pendiente, 'aprobada', usuario_admin, 'Pasa el sábado <b>a recogerlo</b>')

        html = html_de(client, LISTA)

        assert 'Mensaje del refugio' in html
        assert 'Pasa el sábado &lt;b&gt;a recogerlo&lt;/b&gt;' in html
        assert 'Comentarios del' not in html

    def test_sin_mensaje_no_hay_apartado(self, client, auth_headers_adoptante, solicitud_pendiente):
        assert 'Mensaje del refugio' not in html_de(client, LISTA)

    def test_sin_foto_no_pide_nada_a_placehold(self, client, auth_headers_adoptante, solicitud_pendiente):
        solicitud_pendiente.mascota.foto_url = None
        db.session.commit()

        html = html_de(client, LISTA)

        assert 'placehold' not in html
        assert 'Cerbero todavía no tiene foto' in html

    def test_con_foto_con_dimensiones_y_alt(self, client, auth_headers_adoptante, solicitud_pendiente):
        html = html_de(client, LISTA)

        foto = re.search(r'<img class="solicitud__foto"[^>]*>', html).group(0)
        assert 'width="800"' in foto and 'height="600"' in foto
        assert 'alt="Foto de Cerbero, perro"' in foto and 'loading="lazy"' in foto

    def test_estado_vacio_enlaza_al_catalogo(self, client, auth_headers_adoptante):
        html = html_de(client, LISTA)

        assert 'Aún no tienes solicitudes' in html
        assert re.search(r'<a class="boton[^"]*" href="/mascotas/catalogo">Ver mascotas disponibles</a>', html)
        assert h1_de(html) == ['Mis solicitudes']

    def test_nombre_con_caracteres_especiales_escapado(self, client, auth_headers_adoptante, usuario_adoptante):
        mascota = Mascota(nombre='<i>Ñoño</i>', especie='Perro', descripcion='Descripción larga')
        db.session.add(mascota)
        db.session.flush()
        db.session.add(Solicitud(usuario_id=usuario_adoptante.id, mascota_id=mascota.id))
        db.session.commit()

        html = html_de(client, LISTA)

        assert 'Ver la solicitud de &lt;i&gt;Ñoño&lt;/i&gt;</a>' in html
        assert '<i>Ñoño</i>' not in html


class TestDetalle:

    def test_sin_bootstrap_un_h1_y_titulo(self, client, auth_headers_adoptante, solicitud_pendiente):
        html = html_de(client, detalle(solicitud_pendiente))

        assert not CLASES_BOOTSTRAP.search(html)
        assert 'bootstrap' not in html.lower()
        assert h1_de(html) == ['Solicitud de Cerbero']
        assert '<title>Solicitud de Cerbero - ' in html
        assert 'css/paginas/solicitudes.css' in html
        assert 'Volver a mis solicitudes</a>' in html

    def test_enlace_a_la_ficha_con_nombre_propio(self, client, auth_headers_adoptante, solicitud_pendiente):
        html = html_de(client, detalle(solicitud_pendiente))

        assert f'href="/mascotas/{solicitud_pendiente.mascota_id}"' in html
        assert 'Ver la ficha de Cerbero</a>' in html
        assert 'Ver Perfil Completo' not in html

    def test_que_pasa_ahora_pendiente(self, client, auth_headers_adoptante, solicitud_pendiente):
        html = html_de(client, detalle(solicitud_pendiente))

        assert re.search(r'<h2[^>]*>Qué pasa ahora</h2>', html)
        assert 'Estamos revisando tu solicitud' in html
        assert 'chapa--aviso' in html

    def test_que_pasa_ahora_aprobada(self, client, auth_headers_adoptante, solicitud_pendiente, usuario_admin):
        resolver(solicitud_pendiente, 'aprobada', usuario_admin)

        html = html_de(client, detalle(solicitud_pendiente))

        assert re.search(r'<h2[^>]*>Qué pasa ahora</h2>', html)
        assert 'Enhorabuena' in html and 'entrega de Cerbero' in html
        assert 'Estamos revisando' not in html

    def test_que_pasa_ahora_rechazada_con_alternativa(self, client, auth_headers_adoptante, solicitud_pendiente,
                                                      usuario_admin):
        resolver(solicitud_pendiente, 'rechazada', usuario_admin)

        html = html_de(client, detalle(solicitud_pendiente))

        assert 'Esta vez no ha podido ser' in html
        assert 'href="/mascotas/catalogo">Ver mascotas disponibles</a>' in html

    def test_la_pista_de_contacto_solo_con_marca_contacto(self, app, client, auth_headers_adoptante,
                                                          solicitud_pendiente):
        assert 'Si tienes dudas' not in html_de(client, detalle(solicitud_pendiente))

        app.config['MARCA_CONTACTO'] = 'hola@refugio.test'

        assert 'Si tienes dudas, escribe a hola@refugio.test' in html_de(client, detalle(solicitud_pendiente))

    def test_mensaje_del_refugio_siempre_con_ese_nombre(self, client, auth_headers_adoptante,
                                                        solicitud_pendiente, usuario_admin):
        resolver(solicitud_pendiente, 'rechazada', usuario_admin, 'Vivienda pequeña')

        html = html_de(client, detalle(solicitud_pendiente))

        assert re.search(r'<h2[^>]*>Mensaje del refugio</h2>', html)
        assert 'Vivienda pequeña' in html
        assert 'Comentarios del' not in html and 'Administrador' not in html

    def test_fechas_con_hora_de_madrid(self, client, auth_headers_adoptante, solicitud_pendiente, usuario_admin):
        solicitud_pendiente.fecha_solicitud = utc(2026, 11, 15, 13, 53)
        resolver(solicitud_pendiente, 'aprobada', usuario_admin)
        solicitud_pendiente.fecha_revision = utc(2026, 7, 15, 13, 53)
        db.session.commit()

        html = html_de(client, detalle(solicitud_pendiente))

        assert 'Enviada el 15 de noviembre de 2026, 14:53' in html
        assert 'Revisada el 15 de julio de 2026, 15:53' in html

    def test_solicitante_y_respuestas_legibles_con_encabezados_en_orden(
            self, client, auth_headers_adoptante, usuario_adoptante, mascota_disponible, respuestas_validas):
        respuestas, _ = cuestionario.validar({**respuestas_validas, 'horas_solo': '8+'})
        solicitud = Solicitud(usuario_id=usuario_adoptante.id, mascota_id=mascota_disponible.id,
                              cuestionario=respuestas)
        db.session.add(solicitud)
        db.session.commit()

        html = html_de(client, detalle(solicitud))

        assert 'Pepe Pérez Pérez' in html
        assert 'adoptante@test.com' in html and '612345678' in html
        assert 'Más de 8 horas' in html and '>8+<' not in html
        niveles = [int(n) for n in re.findall(r'<h([1-6])', html)]
        assert niveles[0] == 1
        assert all(b - a <= 1 for a, b in zip(niveles, niveles[1:], strict=False)), niveles
        assert '<h4' not in html and 'class="row' not in html

    def test_sin_foto_no_pide_nada_a_placehold(self, client, auth_headers_adoptante, solicitud_pendiente):
        solicitud_pendiente.mascota.foto_url = None
        db.session.commit()

        html = html_de(client, detalle(solicitud_pendiente))

        assert 'placehold' not in html
        assert 'Cerbero todavía no tiene foto' in html

    def test_el_admin_ve_revisar_y_no_el_que_pasa_ahora(self, client, auth_headers_admin, solicitud_pendiente):
        html = html_de(client, detalle(solicitud_pendiente))

        assert 'Qué pasa ahora' not in html
        assert f'href="/solicitudes/admin/revisar/{solicitud_pendiente.id}">Revisar solicitud</a>' in html
        assert 'Volver a las solicitudes</a>' in html and 'href="/solicitudes/admin"' in html

    def test_el_admin_no_ve_el_boton_en_una_resuelta(self, client, auth_headers_admin, solicitud_pendiente,
                                                     usuario_admin):
        resolver(solicitud_pendiente, 'aprobada', usuario_admin)

        assert 'Revisar solicitud' not in html_de(client, detalle(solicitud_pendiente))

    def test_sin_landmarks_de_mas(self, client, auth_headers_adoptante, solicitud_pendiente):
        html = html_de(client, detalle(solicitud_pendiente))

        assert 'aria-label="Mascota solicitada"' not in html
        assert 'aria-label="Estado de la solicitud"' not in html

    def test_otro_usuario_no_ve_una_solicitud_ajena(self, client, solicitud_pendiente):
        otro = Usuario(email='otro@test.com', nombre='Otro', password='password123')
        db.session.add(otro)
        db.session.commit()
        client.post('/auth/login', data={'email': 'otro@test.com', 'password': 'password123'})

        respuesta = client.get(detalle(solicitud_pendiente))

        assert respuesta.status_code == 302
        html = client.get(respuesta.headers['Location']).data.decode()
        assert 'No tienes permiso para ver esta solicitud.' in html
        for dato in ('Pepe', 'Pérez', 'adoptante@test.com', '612345678', 'Cerbero',
                     'Respuestas del cuestionario', 'Casa con jardin', 'Sí, he tenido perros antes'):
            assert dato not in html, dato

    def test_el_adoptante_no_ve_revisar(self, client, auth_headers_adoptante, solicitud_pendiente):
        assert 'Revisar solicitud' not in html_de(client, detalle(solicitud_pendiente))

    def test_cerrada_por_la_migracion_sin_revisor(self, client, auth_headers_adoptante, solicitud_pendiente):
        solicitud_pendiente.registrar_revision('rechazada', None, adopciones.COMENTARIO_RECHAZO_AUTOMATICO)
        db.session.commit()

        html = html_de(client, detalle(solicitud_pendiente))

        assert 'Esta mascota ya ha encontrado un hogar' in html
        assert 'Esta vez no ha podido ser' in html

    def test_sin_raza_ni_telefono(self, client, auth_headers_adoptante, solicitud_pendiente, usuario_adoptante):
        solicitud_pendiente.mascota.raza = None
        usuario_adoptante.telefono = None
        usuario_adoptante.apellidos = None
        db.session.commit()

        html = html_de(client, detalle(solicitud_pendiente))

        assert 'Solicitud de Cerbero' in html and '612345678' not in html

    def test_cuestionario_antiguo_sin_respuestas(self, client, auth_headers_adoptante, solicitud_pendiente):
        solicitud_pendiente.cuestionario_json = {}
        db.session.commit()

        assert 'Sin respuesta' in html_de(client, detalle(solicitud_pendiente))

