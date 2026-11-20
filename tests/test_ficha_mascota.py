"""
Ficha de mascota sin Bootstrap (B4.2: P-24, P-39, P-42, P-43).
"""

import re
from pathlib import Path

import pytest

from app import db
from tests.test_catalogo_paginas import CLASES_BOOTSTRAP, html_de, solicitar


class TestDetalle:

    def url(self, mascota):
        return f'/mascotas/{mascota.id}'

    def test_sin_bootstrap_un_h1_y_titulo(self, client, mascota_disponible):
        html = html_de(client, self.url(mascota_disponible))

        assert not CLASES_BOOTSTRAP.search(html)
        assert 'bootstrap' not in html.lower()
        assert re.findall(r'<h1[^>]*>([^<]+)</h1>', html) == ['Cerbero']
        assert '<title>Cerbero - ' in html
        assert 'css/paginas/detalle-mascota.css' in html
        assert 'Volver al catálogo</a>' in html

    def test_foto_con_dimensiones_alt_y_sin_servicios_externos(self, client, mascota_disponible):
        html = html_de(client, self.url(mascota_disponible))

        foto = re.search(r'<img class="ficha__foto"[^>]*>', html).group(0)
        assert 'width="800"' in foto and 'height="600"' in foto
        assert 'alt="Foto de Cerbero, perro"' in foto
        assert 'fetchpriority="high"' in foto and 'lazy' not in foto

    def test_sin_foto_no_pide_nada_a_placehold(self, client, mascota_disponible):
        mascota_disponible.foto_url = None
        db.session.commit()
        html = html_de(client, self.url(mascota_disponible))

        assert 'placehold' not in html
        assert 'Cerbero todavía no tiene foto' in html

    def test_datos_en_lista_de_definiciones(self, client, mascota_disponible):
        html = html_de(client, self.url(mascota_disponible))

        assert '<table' not in html and '✓' not in html
        for dato in ('Especie', 'Raza', 'Edad aproximada', 'Sexo', 'Tamaño', 'Vacunas', 'Esterilización'):
            assert f'<dt>{dato}</dt>' in html, dato
        assert '<dd>3 años</dd>' in html
        assert '<dd>Al día</dd>' in html

    def test_datos_opcionales_y_edad_cero(self, client, mascota_disponible):
        mascota_disponible.raza = mascota_disponible.sexo = mascota_disponible.tamano = None
        mascota_disponible.edad_aprox = 0
        mascota_disponible.vacunado = mascota_disponible.esterilizado = False
        db.session.commit()
        html = html_de(client, self.url(mascota_disponible))

        assert '<dd>Menos de 1 año</dd>' in html
        assert '<dt>Raza</dt>' not in html and '<dt>Sexo</dt>' not in html
        assert '<dd>Pendientes</dd>' in html

    def test_edad_un_ano(self, client, mascota_disponible):
        mascota_disponible.edad_aprox = 1
        db.session.commit()

        assert '<dd>1 año</dd>' in html_de(client, self.url(mascota_disponible))

    def test_invitado_inicia_sesion_para_solicitar(self, client, mascota_disponible):
        html = html_de(client, self.url(mascota_disponible))

        assert 'Inicia sesión para solicitar la adopción' in html
        assert f'/auth/login?next=/solicitudes/nueva/{mascota_disponible.id}' in html.replace('%2F', '/')

    def test_adoptante_solicita_adopcion(self, client, auth_headers_adoptante, mascota_disponible):
        html = html_de(client, self.url(mascota_disponible))

        assert f'href="/solicitudes/nueva/{mascota_disponible.id}">Solicitar adopción</a>' in html
        assert 'cuestionario' in html

    def test_con_pendientes_aun_se_puede_solicitar(self, client, mascota_disponible):
        solicitar(mascota_disponible)
        html = html_de(client, self.url(mascota_disponible))

        assert 'Aún puedes solicitarla' in html
        assert html.count('Aún puedes solicitarla') == 1
        assert 'Inicia sesión para solicitar la adopción' in html

    def test_adoptada_ya_tiene_hogar(self, client, auth_headers_adoptante, mascota_adoptada):
        html = html_de(client, self.url(mascota_adoptada))

        assert 'Ya tiene hogar' in html
        assert 'Adoptada' in html
        assert 'Ver mascotas disponibles</a>' in html
        assert 'Solicitar adopción' not in html and 'Inicia sesión' not in html

    def test_en_proceso_explica_por_que_no_se_puede_solicitar(self, client, mascota_disponible):
        mascota_disponible.estado = 'en_proceso'
        db.session.commit()
        html = html_de(client, self.url(mascota_disponible))

        assert 'solicitud en revisión' in html
        assert 'Ver mascotas disponibles</a>' in html
        assert 'Solicitar adopción' not in html

    def test_nombre_con_html_se_escapa(self, client, mascota_disponible):
        mascota_disponible.nombre = '<script>x</script>'
        db.session.commit()

        assert '<script>x' not in html_de(client, self.url(mascota_disponible))


@pytest.mark.parametrize('css', ['detalle-mascota.css'])
def test_css_de_pagina_solo_con_tokens_y_en_capa(css):
    texto = (Path(__file__).parent.parent / 'app/static/css/paginas' / css).read_text(encoding='utf-8')

    codigo = re.sub(r'/\*.*?\*/', '', texto, flags=re.S).lstrip()
    assert codigo.startswith('@layer componentes {')
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|!important', texto)
