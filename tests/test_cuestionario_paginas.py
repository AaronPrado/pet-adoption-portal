"""
Tests del cuestionario de adopción con la base nueva (B4.4): estructura y
accesibilidad de `solicitudes/nueva.html` (P-12, P-16), aviso de solicitud
duplicada (P-44) y confirmación del envío (P-24).
"""

import re
from html.parser import HTMLParser

import pytest
from markupsafe import escape

from app import adopciones, cuestionario
from app.models import Solicitud
from app.routes import solicitudes as rutas


def url_nueva(mascota):
    return f'/solicitudes/nueva/{mascota.id}'


def contenido(response):
    return response.data.decode()


class Estructura(HTMLParser):
    """Recoge ids, labels, fieldsets con su legend y los radios de cada fieldset."""

    def __init__(self):
        super().__init__()
        self.ids = set()
        self.labels_for = []
        self.fieldsets = []  # [attrs, legend, nombres de los radios]
        self.radios_fuera = []
        self.h1 = []
        self._abiertos = []
        self._en_legend = False
        self._en_h1 = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.add(a['id'])
        if tag == 'label' and 'for' in a:
            self.labels_for.append(a['for'])
        if tag == 'fieldset':
            self._abiertos.append([a, '', set()])
        if tag == 'legend':
            self._en_legend = True
        if tag == 'h1':
            self._en_h1 = True
            self.h1.append('')
        if tag == 'input' and a.get('type') == 'radio':
            if self._abiertos:
                self._abiertos[-1][2].add(a['name'])
            else:
                self.radios_fuera.append(a['name'])

    def handle_data(self, data):
        if self._en_legend and self._abiertos:
            self._abiertos[-1][1] += data
        if self._en_h1:
            self.h1[-1] += data

    def handle_endtag(self, tag):
        if tag == 'legend':
            self._en_legend = False
        if tag == 'h1':
            self._en_h1 = False
        if tag == 'fieldset':
            self.fieldsets.append(self._abiertos.pop())


def estructura(html):
    analizador = Estructura()
    analizador.feed(html)
    return analizador


CON_OPCIONES = [campo for campo, p in cuestionario.PREGUNTAS.items() if p.opciones]
DE_TEXTO = [campo for campo, p in cuestionario.PREGUNTAS.items() if not p.opciones]


class TestEstructura:

    @pytest.fixture
    def html(self, client, auth_headers_adoptante, mascota_disponible):
        return contenido(client.get(url_nueva(mascota_disponible)))

    def test_extiende_la_base_nueva_con_su_css(self, html):
        assert 'bootstrap' not in html
        assert 'href="/static/css/sistema.css"' in html
        assert 'href="/static/css/paginas/cuestionario.css"' in html

    def test_un_solo_h1_que_nombra_a_la_mascota(self, html):
        h1 = estructura(html).h1

        assert [texto.strip() for texto in h1] == ['Solicitar la adopción de Cerbero']
        assert '<title>Solicitar la adopción de Cerbero - ' in html

    def test_csrf_y_envio_a_la_misma_ruta(self, html, mascota_disponible):
        assert '<input type="hidden" name="csrf_token" value="' in html
        assert f'<form class="cuestionario__formulario" method="POST" action="{url_nueva(mascota_disponible)}"' in html

    def test_un_fieldset_por_grupo_de_radios_con_su_pregunta(self, html):
        """P-12: cada grupo de radios va en un fieldset cuyo legend es la pregunta."""
        analizador = estructura(html)
        grupos = {a['id']: (legend, nombres) for a, legend, nombres in analizador.fieldsets}

        assert analizador.radios_fuera == []
        assert list(grupos) == CON_OPCIONES
        for campo in CON_OPCIONES:
            legend, nombres = grupos[campo]
            assert nombres == {campo}
            assert legend.replace('*', '').strip() == cuestionario.PREGUNTAS[campo].texto

    def test_ningun_label_huerfano(self, html):
        analizador = estructura(html)

        assert [destino for destino in analizador.labels_for if destino not in analizador.ids] == []

    def test_opciones_salen_del_modulo(self, html):
        """Fuente única: los radios pintan exactamente las opciones de PREGUNTAS, en orden."""
        for campo in CON_OPCIONES:
            pintadas = re.findall(
                rf'<input class="opcion__control" type="radio" id="{campo}_[^"]+" name="{campo}" value="([^"]+)"'
                rf'[^>]*>\s*<label class="opcion__etiqueta" for="[^"]+">([^<]+)</label>', html)
            assert tuple(pintadas) == tuple(
                (valor, str(escape(etiqueta))) for valor, etiqueta in cuestionario.PREGUNTAS[campo].opciones)

    def test_preguntas_de_texto_con_su_label(self, html):
        for campo in DE_TEXTO:
            pregunta = cuestionario.PREGUNTAS[campo]
            assert f'<label class="campo__etiqueta" for="{campo}">{escape(pregunta.texto)}' in html
            assert re.search(rf'<textarea class="campo__control" rows="\d+" id="{campo}" name="{campo}"', html)

    def test_obligatorias_con_required_y_leyenda(self, html):
        assert 'Los campos marcados con' in html
        for campo, pregunta in cuestionario.PREGUNTAS.items():
            if pregunta.opciones:
                control = re.search(rf'<input [^>]*name="{campo}"[^>]*>', html).group(0)
            else:
                control = re.search(rf'<textarea [^>]*name="{campo}"[^>]*>', html).group(0)
            assert (' required' in control) == pregunta.obligatoria, campo

    def test_ayudas_enlazadas(self, html):
        for campo, pregunta in cuestionario.PREGUNTAS.items():
            if pregunta.ayuda:
                assert f'id="{campo}-ayuda"' in html
                assert f'aria-describedby="{campo}-ayuda"' in html

    def test_secciones_nombradas_por_su_titulo(self, html):
        secciones = re.findall(r'<section class="cuestionario__seccion" aria-labelledby="([^"]+)">\s*'
                               r'<h2 id="([^"]+)" class="cuestionario__titulo">([^<]+)</h2>', html)

        assert [titulo for _, _, titulo in secciones] == [titulo for titulo, _ in cuestionario.SECCIONES]
        assert all(apunta == id_ for apunta, id_, _ in secciones)
        assert len({id_ for _, id_, _ in secciones}) == len(secciones)

    def test_sin_placeholders_como_instrucciones(self, html):
        assert 'placeholder=' not in html

    def test_boton_de_envio_y_vuelta_a_la_ficha(self, html, mascota_disponible):
        assert '<button type="submit" class="boton boton--primario">Enviar solicitud</button>' in html
        assert f'href="/mascotas/{mascota_disponible.id}">Volver a Cerbero</a>' in html

    def test_junto_al_boton_avisa_de_que_no_se_puede_cambiar(self, html):
        """WCAG 3.3.4: el aviso se repite justo antes de enviar, no solo en la entradilla."""
        assert re.search(r'<p class="cuestionario__aviso">[^<]*no podrás cambiar[^<]*</p>\s*'
                         r'<button type="submit"[^>]*>Enviar solicitud</button>', html)

    def test_vuelta_a_la_ficha(self, html, mascota_disponible):
        assert f'href="/mascotas/{mascota_disponible.id}">Volver a Cerbero</a>' in html

    def test_primera_visita_sin_errores_ni_selecciones(self, html):
        assert 'aria-invalid' not in html
        assert 'data-resumen-errores' not in html
        assert ' checked' not in html


class TestErrores:
    """Contrato `valores`/`errores` + 400, con resumen de errores (P-16)."""

    def enviar(self, client, mascota, datos):
        return client.post(url_nueva(mascota), data=datos)

    def test_resumen_enlaza_cada_pregunta_en_el_orden_del_formulario(self, client, auth_headers_adoptante,
                                                                    mascota_disponible, respuestas_validas):
        datos = {**respuestas_validas, 'tiene_mascotas': 'si', 'horas_solo': '', 'vivienda_tipo': 'castillo'}
        response = self.enviar(client, mascota_disponible, datos)

        assert response.status_code == 400
        html = contenido(response)
        enlaces = re.findall(r'<li><a href="#([^"]+)">([^<]+)</a></li>', html)
        assert [destino for destino, _ in enlaces] == ['vivienda_tipo', 'mascotas_detalles', 'horas_solo']
        textos = dict(enlaces)
        assert textos['horas_solo'] == str(escape(
            f'{cuestionario.PREGUNTAS["horas_solo"].texto} {cuestionario.MENSAJE_OBLIGATORIO}'))
        assert textos['vivienda_tipo'].endswith(cuestionario.MENSAJE_OPCION)

    def test_resumen_sustituye_al_aviso_general(self, client, auth_headers_adoptante, mascota_disponible):
        html = contenido(self.enviar(client, mascota_disponible, {}))

        assert 'data-resumen-errores' in html
        assert 'Revisa los campos marcados.' not in html
        assert 'autofocus' not in html

    def test_grupo_de_radios_con_error(self, client, auth_headers_adoptante, mascota_disponible,
                                       respuestas_validas):
        datos = {**respuestas_validas}
        del datos['tiene_jardin']
        html = contenido(self.enviar(client, mascota_disponible, datos))

        fieldset = re.search(r'<fieldset id="tiene_jardin"[^>]*>', html).group(0)
        assert 'tabindex="-1"' in fieldset
        assert 'aria-describedby="tiene_jardin-error"' in fieldset
        assert 'id="tiene_jardin-error"' in html
        assert html.count('aria-invalid="true"') == 2  # las dos opciones del grupo

    def test_conserva_lo_contestado(self, client, auth_headers_adoptante, mascota_disponible,
                                    respuestas_validas):
        datos = {**respuestas_validas, 'tiene_mascotas': 'si', 'horas_solo': '8+', 'referencias': 'Ana <García>'}
        html = contenido(self.enviar(client, mascota_disponible, datos))

        assert 'id="horas_solo_8+" name="horas_solo" value="8+" checked' in html
        assert 'id="tiene_mascotas_si" name="tiene_mascotas" value="si" checked' in html
        assert 'value="no" checked' not in html.split('id="tiene_mascotas_no"')[1].split('>')[0]
        assert 'Ana &lt;García&gt;</textarea>' in html
        assert 'He tenido perros toda la vida</textarea>' in html


class TestSolicitudDuplicada:
    """P-44: quien ya la solicitó lo lee y llega a su solicitud."""

    def test_get_lleva_a_su_solicitud(self, client, auth_headers_adoptante, solicitud_pendiente):
        response = client.get(f'/solicitudes/nueva/{solicitud_pendiente.mascota_id}')

        assert response.status_code == 302
        assert response.headers['Location'] == f'/solicitudes/detalle/{solicitud_pendiente.id}'
        html = contenido(client.get(response.headers['Location']))
        assert 'Ya tienes una solicitud para Cerbero.' in html

    def test_post_no_crea_otra(self, client, auth_headers_adoptante, solicitud_pendiente, respuestas_validas):
        response = client.post(f'/solicitudes/nueva/{solicitud_pendiente.mascota_id}', data=respuestas_validas)

        assert response.headers['Location'] == f'/solicitudes/detalle/{solicitud_pendiente.id}'
        assert Solicitud.query.count() == 1

    def test_se_avisa_antes_que_la_falta_de_disponibilidad(self, client, auth_headers_adoptante,
                                                          solicitud_pendiente, usuario_admin):
        """Si su solicitud ya se aprobó, no le decimos que la mascota «ya no está disponible»."""
        adopciones.aprobar(solicitud_pendiente, usuario_admin.id)

        response = client.get(f'/solicitudes/nueva/{solicitud_pendiente.mascota_id}', follow_redirects=True)

        html = contenido(response)
        assert 'Ya tienes una solicitud para Cerbero.' in html
        assert adopciones.MascotaNoDisponible.mensaje not in html

    def test_envio_simultaneo_lleva_a_la_que_gano(self, client, auth_headers_adoptante, mascota_disponible,
                                                  respuestas_validas, usuario_adoptante, monkeypatch):
        """Dos envíos a la vez: el segundo choca con la restricción única y va a la del primero."""
        crear = adopciones.crear_solicitud

        def crear_otra_antes(usuario_id, mascota_id, respuestas):
            crear(usuario_id, mascota_id, respuestas)
            return crear(usuario_id, mascota_id, respuestas)

        monkeypatch.setattr(adopciones, 'crear_solicitud', crear_otra_antes)
        response = client.post(url_nueva(mascota_disponible), data=respuestas_validas)

        ganadora = Solicitud.query.one()
        assert response.headers['Location'] == f'/solicitudes/detalle/{ganadora.id}'
        assert 'Ya tienes una solicitud para Cerbero.' in contenido(client.get(response.headers['Location']))

    def test_choque_sin_solicitud_que_mostrar(self, client, auth_headers_adoptante, mascota_disponible,
                                              respuestas_validas, monkeypatch):
        """Si la otra se borró justo después del choque, se va a la lista."""
        def chocar(*_):
            raise adopciones.SolicitudDuplicada()

        monkeypatch.setattr(adopciones, 'crear_solicitud', chocar)
        response = client.post(url_nueva(mascota_disponible), data=respuestas_validas)

        assert response.headers['Location'] == '/solicitudes/mis-solicitudes'
        assert 'Ya tienes una solicitud para Cerbero.' in contenido(client.get(response.headers['Location']))

    def test_la_api_mantiene_su_mensaje(self):
        assert adopciones.SolicitudDuplicada.mensaje == 'Ya has enviado una solicitud para esta mascota.'


class TestConfirmacion:
    """P-24: tras enviar, el adoptante sabe qué pasa ahora y dónde verlo."""

    def test_explica_que_pasa_ahora(self, client, auth_headers_adoptante, mascota_disponible, respuestas_validas):
        response = client.post(url_nueva(mascota_disponible), data=respuestas_validas)

        assert response.status_code == 302
        assert response.headers['Location'] == '/solicitudes/mis-solicitudes'
        html = contenido(client.get(response.headers['Location']))
        assert str(escape(rutas.MENSAJE_RECIBIDA.format(nombre='Cerbero'))) in html
        assert 'éxito' not in html

    def test_texto_de_la_confirmacion(self):
        texto = rutas.MENSAJE_RECIBIDA.format(nombre='Toby')

        assert texto.startswith('Hemos recibido tu solicitud para adoptar a Toby.')
        assert 'revis' in texto and 'esta página' in texto

    def test_la_mascota_no_disponible_sigue_igual(self, client, auth_headers_adoptante, mascota_adoptada):
        response = client.get(url_nueva(mascota_adoptada))

        assert response.headers['Location'] == f'/mascotas/{mascota_adoptada.id}'
        assert Solicitud.query.count() == 0
