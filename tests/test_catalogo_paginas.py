"""
Catálogo y ficha de mascota sin Bootstrap (B4.2: P-19, P-24, P-30, P-35, P-37,
P-39, P-41, P-42, P-43) y la paginación de la base nueva.
"""

import re
from pathlib import Path

import pytest

from app import db
from app.models import Mascota, Solicitud, Usuario

CATALOGO = '/mascotas/catalogo'
CLASES_BOOTSTRAP = re.compile(r'class="[^"]*\b(btn|card|col-\w+|row|badge|alert|container|form-control|form-select|'
                              r'form-label|page-link|page-item|mb-\d|mt-\d)\b')


def html_de(client, url):
    respuesta = client.get(url)
    assert respuesta.status_code == 200, url
    return respuesta.data.decode()


def crear_mascotas(n, especie='Gato', prefijo='Gato', **extra):
    for i in range(n):
        db.session.add(Mascota(nombre=f'{prefijo} {i:02d}', especie=especie,
                               descripcion='Descripción larga', **extra))
    db.session.commit()


def solicitar(mascota):
    usuario = Usuario(email='otra@test.com', nombre='Otra', password='password123')
    db.session.add(usuario)
    db.session.flush()
    db.session.add(Solicitud(usuario_id=usuario.id, mascota_id=mascota.id))
    db.session.commit()


class TestCatalogo:

    def test_sin_bootstrap_y_un_solo_h1(self, client, mascota_disponible):
        html = html_de(client, CATALOGO)

        assert 'bootstrap' not in html.lower()
        assert not CLASES_BOOTSTRAP.search(html)
        assert html.count('<h1') == 1
        assert '<title>Mascotas en adopción - ' in html
        assert 'css/paginas/catalogo.css' in html

    def test_tarjetas_en_lista_con_enlace_de_nombre_unico(self, client, mascota_disponible):
        crear_mascotas(2)
        html = html_de(client, CATALOGO)

        assert '<ul class="rejilla-tarjetas">' in html
        assert html.count('<article class="tarjeta-mascota"') == 3
        assert 'Ver a Cerbero</a>' in html and 'Ver a Gato 00</a>' in html
        assert 'Ver Detalles' not in html

    def test_primera_fila_sin_lazy(self, client):
        crear_mascotas(5, foto_url='https://example.com/foto.jpg')
        html = html_de(client, CATALOGO)

        fotos = re.findall(r'<img class="tarjeta-mascota__foto"[^>]*>', html)
        assert len(fotos) == 5
        assert [('loading="lazy"' in foto) for foto in fotos] == [False, False, False, True, True]
        assert all('width="800"' in foto and 'height="600"' in foto for foto in fotos)

    def test_filtros_en_fieldset_con_nombre_dentro_de_details(self, client, mascota_disponible):
        html = html_de(client, CATALOGO)

        assert re.search(r'<details[^>]*>\s*<summary[^>]*>Filtrar mascotas</summary>\s*<form', html)
        assert re.search(r'<fieldset[^>]*>\s*<legend[^>]*>[^<]+</legend>', html)
        assert 'Edad máxima (años)' in html
        assert 'Ej:' not in html

    def test_resumen_cuenta_los_filtros_activos(self, client, mascota_disponible):
        html = html_de(client, CATALOGO + '?especie=Perro&tamano=Pequeño&edad=5')

        assert 'Filtrar mascotas (3 activos)' in html
        assert '1 mascota disponible' in html
        assert 'Perro, Pequeño, hasta 5 años' in html

    def test_resumen_en_plural_y_sin_filtros(self, client, mascota_disponible):
        crear_mascotas(2)
        html = html_de(client, CATALOGO)

        assert '3 mascotas disponibles' in html
        assert 'Filtrar mascotas</summary>' in html

    def test_especie_se_normaliza_como_en_la_api(self, client, mascota_disponible):
        crear_mascotas(1)
        for valor in ('perro', '%20PERRO%20', 'pErRo'):
            html = html_de(client, f'{CATALOGO}?especie={valor}')
            assert 'Ver a Cerbero' in html, valor
            assert 'Ver a Gato 00' not in html, valor
            assert '<option value="Perro" selected>' in html, valor

    def test_especie_vacia_tras_normalizar_no_filtra(self, client, mascota_disponible):
        assert 'Ver a Cerbero' in html_de(client, CATALOGO + '?especie=%E2%80%8B')

    @pytest.mark.parametrize('edad', ['abc', '-1', '31', '99999999999999999999999', '2.5'])
    def test_edad_invalida_avisa_y_no_filtra(self, client, mascota_disponible, edad):
        html = html_de(client, f'{CATALOGO}?edad={edad}')

        assert 'La edad máxima debe ser un número entero entre 0 y 30' in html
        assert 'role="alert"' in html
        assert 'Ver a Cerbero' in html
        assert 'Filtrar mascotas</summary>' in html

    def test_edad_valida_no_avisa(self, client, mascota_disponible):
        html = html_de(client, CATALOGO + '?edad=5')

        assert 'La edad máxima debe ser' not in html

    def test_vacio_con_filtros_nombra_el_filtro_y_ofrece_quitarlos(self, client, mascota_disponible):
        html = html_de(client, CATALOGO + '?especie=Gato&sexo=Hembra')

        assert 'Ninguna mascota coincide con estos filtros' in html
        assert 'Gato, Hembra' in html
        assert re.search(r'<a class="boton boton--secundario" href="/mascotas/catalogo">Quitar filtros</a>', html)

    def test_vacio_sin_filtros_no_culpa_a_los_filtros(self, client):
        html = html_de(client, CATALOGO)

        assert 'Ahora mismo no hay mascotas en adopción' in html
        assert 'Quitar filtros' not in html
        assert 'coincide' not in html

    def test_pagina_fuera_de_rango(self, client):
        crear_mascotas(15)
        html = html_de(client, CATALOGO + '?page=99')

        assert 'Esta página no existe' in html
        assert 'Ahora mismo no hay mascotas' not in html
        assert 'Ninguna mascota coincide' not in html
        assert 'href="/mascotas/catalogo"' in html

    def test_pendientes_dicen_que_aun_se_puede_solicitar(self, client, mascota_disponible):
        crear_mascotas(1)
        solicitar(mascota_disponible)
        html = html_de(client, CATALOGO)

        assert html.count('Aún puedes solicitarla') == 1
        assert 'tarjeta-mascota__nota' in html


def test_aviso_de_pendientes_definido_una_sola_vez():
    """El texto vive en AVISO_PENDIENTES (app/models.py), no en cada plantilla."""
    raiz = Path(__file__).parent.parent / 'app/templates'
    assert not [p.name for p in raiz.rglob('*.html') if 'Aún puedes solicitarla' in p.read_text(encoding='utf-8')]


class TestPaginacion:

    @pytest.fixture
    def treinta(self, app):
        crear_mascotas(30)

    def test_pagina_actual_con_aria_current_en_el_elemento_con_texto(self, client, treinta):
        html = html_de(client, CATALOGO + '?page=2')

        assert html.count('aria-current="page"') == 2  # la paginación y la navegación («Mascotas»)
        assert re.search(r'<span[^>]*aria-current="page"[^>]*>.*?Página .*?2.*?, actual', html, flags=re.S)
        assert not re.search(r'<li[^>]*aria-current', html)

    def test_enlaces_con_nombre_y_deshabilitados_marcados(self, client, treinta):
        html = html_de(client, CATALOGO)

        assert 'aria-label="Página 2"' in html
        assert re.search(r'<span class="paginacion__enlace paginacion__enlace--inactivo">Anterior</span>', html)
        assert 'aria-disabled' not in html
        assert 'rel="next"' in html and 'rel="prev"' not in html
        assert 'page-item' not in html and 'pagination' not in html

    def test_conserva_filtros_y_descarta_argumentos_de_url_for(self, client, treinta):
        html = html_de(client, CATALOGO + '?especie=Gato&_external=1&endpoint=x')

        assert 'especie=Gato&amp;page=2' in html
        assert '_external' not in html and 'endpoint=' not in html

    def test_macro_bootstrap_de_las_paginas_admin_sigue_igual(self, client, auth_headers_admin, treinta):
        html = html_de(client, '/mascotas/admin')

        assert 'class="pagination' in html and 'page-link' in html




@pytest.mark.parametrize('css', ['catalogo.css'])
def test_css_de_pagina_solo_con_tokens_y_en_capa(css):
    texto = (Path(__file__).parent.parent / 'app/static/css/paginas' / css).read_text(encoding='utf-8')

    codigo = re.sub(r'/\*.*?\*/', '', texto, flags=re.S).lstrip()
    assert codigo.startswith('@layer componentes {')
    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|!important', texto)
