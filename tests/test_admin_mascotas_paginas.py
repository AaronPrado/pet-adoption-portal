"""
Lista de mascotas del panel de admin sin Bootstrap (B5.1: P-23, P-43, P-46):
tabla accesible, estados con badge_estado, paginación de la base nueva y
«Eliminar» solo para las mascotas sin solicitudes (también en el servidor).
"""

import re
from pathlib import Path

import pytest

from app import db
from app.models import Mascota, Solicitud, Usuario

LISTA = '/mascotas/admin'
PLANTILLA = Path(__file__).resolve().parent.parent / 'app/templates/mascotas/admin/lista.html'
CSS = Path(__file__).resolve().parent.parent / 'app/static/css/paginas/admin-mascotas.css'
CLASES_BOOTSTRAP = re.compile(r'class="[^"]*\b(btn(-\w+)?|card(-\w+)?|col-\w+|row|badge|bg-\w+|alert|container|'
                              r'table(-\w+)?|text-muted|page-link|page-item|mb-\d|mt-\d|d-none|d-flex)\b')
COLUMNAS = ['ID', 'Nombre', 'Especie', 'Raza', 'Edad', 'Tamaño', 'Estado', 'Acciones']


def html_de(client, url=LISTA):
    respuesta = client.get(url)
    assert respuesta.status_code == 200, url
    return respuesta.data.decode()


def solicitar(mascota, estado='pendiente', email='otra@test.com'):
    usuario = Usuario(email=email, nombre=email.split('@')[0], password='password123')
    db.session.add(usuario)
    db.session.flush()
    solicitud = Solicitud(usuario_id=usuario.id, mascota_id=mascota.id)
    solicitud.estado = estado
    db.session.add(solicitud)
    db.session.commit()


def fila(html, nombre):
    """HTML de la fila de la tabla cuya cabecera de fila es `nombre`."""
    for tr in re.findall(r'<tr>.*?</tr>', html, re.S):
        if re.search(rf'<th scope="row">\s*{re.escape(nombre)}\s*</th>', tr):
            return tr
    raise AssertionError(f'sin fila para {nombre}')


def cabecera(html, titulo):
    """Etiqueta <th ...> de la columna `titulo`."""
    for th in re.findall(r'<th scope="col"[^>]*>.*?</th>', html, re.S):
        if re.search(rf'>\s*{re.escape(titulo)}\b', th):
            return th[:th.index('>') + 1]
    raise AssertionError(titulo)


class TestPagina:

    def test_base_nueva_sin_bootstrap_y_un_solo_h1(self, client, auth_headers_admin, mascota_disponible):
        html = html_de(client)

        assert PLANTILLA.read_text(encoding='utf-8').startswith('{% extends "base.html" %}')
        assert 'bootstrap' not in html.lower()
        assert not CLASES_BOOTSTRAP.search(html)
        assert html.count('<h1') == 1
        assert '<h1>Gestión de mascotas</h1>' in html
        assert '<title>Gestión de mascotas - ' in html
        assert 'css/paginas/admin-mascotas.css' in html

    def test_enlace_para_crear_una_mascota(self, client, auth_headers_admin, mascota_disponible):
        html = html_de(client)

        assert re.search(r'<a class="boton boton--primario" href="/mascotas/admin/nueva">Nueva mascota</a>', html)

    def test_css_solo_con_tokens_y_en_capa(self):
        texto = CSS.read_text(encoding='utf-8')
        codigo = re.sub(r'/\*.*?\*/', '', texto, flags=re.S).strip()

        assert codigo.startswith('@layer componentes {')
        # Colores, tamaños y espaciado solo con tokens de sistema.css
        assert not re.search(r'#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(', codigo)
        # (solo los grosores de borde de 1 y 2 px, como en sistema.css)
        assert not re.search(r'\b(?!(1|2)px\b)\d+(\.\d+)?(px|rem|em)\b', codigo)


class TestTabla:

    def test_region_desplazable_con_caption_y_todas_las_columnas(self, client, auth_headers_admin,
                                                               mascota_disponible):
        html = html_de(client)

        assert '<div class="tabla" role="region" aria-labelledby="mascotas-titulo" tabindex="0">' in html
        assert '<caption id="mascotas-titulo">Todas las mascotas</caption>' in html
        titulos = [re.sub(r'<[^>]+>|[▲▼⇅]|, ordenar \w+', '', th).strip()
                   for th in re.findall(r'<th scope="col"[^>]*>(.*?)</th>', html, re.S)]
        # Ninguna columna se oculta (P-23): Estado y Acciones se alcanzan desplazando la región
        assert titulos == COLUMNAS

    def test_nombre_como_cabecera_de_fila(self, client, auth_headers_admin, mascota_disponible):
        html = html_de(client)

        assert '<th scope="row">Cerbero</th>' in fila(html, 'Cerbero')

    def test_orden_por_defecto_marca_aria_sort_en_id(self, client, auth_headers_admin, mascota_disponible):
        html = html_de(client)

        assert 'aria-sort="ascending"' in cabecera(html, 'ID')
        assert html.count('aria-sort=') == 1

    def test_orden_descendente_por_nombre(self, client, auth_headers_admin, mascota_disponible):
        html = html_de(client, LISTA + '?orden=nombre&dir=desc')

        assert 'aria-sort="descending"' in cabecera(html, 'Nombre')
        # El enlace conserva los filtros y dice qué hará el clic
        assert 'href="/mascotas/admin?orden=nombre&amp;dir=asc"' in html
        assert ', ordenar ascendente' in html

    @pytest.mark.parametrize('query', ['orden=password_hash', 'orden=nombre&dir=raro'])
    def test_orden_desconocido_se_normaliza(self, client, auth_headers_admin, mascota_disponible, query):
        html = html_de(client, f'{LISTA}?{query}')

        columna = 'Nombre' if 'nombre' in query else 'ID'
        assert 'aria-sort="ascending"' in cabecera(html, columna)
        assert 'password_hash' not in html

    def test_ordenar_conserva_el_filtro_de_estado(self, client, auth_headers_admin, mascota_disponible):
        html = html_de(client, LISTA + '?estado=disponible')

        assert 'href="/mascotas/admin?estado=disponible&amp;orden=nombre&amp;dir=asc"' in html

    def test_estados_con_badge_estado(self, client, auth_headers_admin, mascota_disponible, mascota_adoptada):
        html = html_de(client)

        assert 'chapa--exito' in fila(html, 'Cerbero') and '</span>Disponible</span>' in fila(html, 'Cerbero')
        assert 'chapa--info' in fila(html, 'Luna') and '</span>Adoptada</span>' in fila(html, 'Luna')
        assert 'Adoptado' not in html

    def test_estado_heredado_con_su_etiqueta(self, client, auth_headers_admin, mascota_disponible):
        mascota_disponible.estado = 'en_proceso'
        db.session.commit()

        assert '</span>En proceso</span>' in fila(html_de(client), 'Cerbero')

    @pytest.mark.parametrize('edad, texto', [(3, '3 años'), (1, '1 año'), (0, 'Menos de 1 año')])
    def test_edad_con_unidad(self, client, auth_headers_admin, mascota_disponible, edad, texto):
        mascota_disponible.edad_aprox = edad
        db.session.commit()

        assert f'<td>{texto}</td>' in fila(html_de(client), 'Cerbero')

    def test_datos_que_faltan(self, client, auth_headers_admin):
        db.session.add(Mascota(nombre='Nadie', especie='Gato', descripcion='Descripción larga'))
        db.session.commit()

        tr = fila(html_de(client), 'Nadie')
        # Raza, edad y tamaño sin dato: una raya que el lector de pantalla lee como «Sin datos»
        assert tr.count('<span aria-hidden="true">—</span><span class="visualmente-oculto">Sin datos</span>') == 3


class TestAcciones:

    def test_ver_y_editar_nombran_la_mascota(self, client, auth_headers_admin, mascota_disponible):
        tr = fila(html_de(client), 'Cerbero')

        assert f'href="/mascotas/{mascota_disponible.id}"' in tr
        # 2.4.6: dice adónde lleva, como «Ver la solicitud de X» en B4.5
        assert 'Ver<span class="visualmente-oculto"> la ficha de Cerbero</span>' in tr
        assert f'href="/mascotas/admin/editar/{mascota_disponible.id}"' in tr
        assert 'Editar<span class="visualmente-oculto"> a Cerbero</span>' in tr

    def test_sin_solicitudes_se_puede_eliminar(self, client, auth_headers_admin, mascota_disponible):
        tr = fila(html_de(client), 'Cerbero')

        formulario = re.search(r'<form [^>]*>.*?</form>', tr, re.S).group(0)
        assert f'action="/mascotas/admin/eliminar/{mascota_disponible.id}"' in formulario
        assert 'method="post"' in formulario.lower()
        assert 'name="csrf_token"' in formulario
        assert 'aria-label="Eliminar a Cerbero"' in formulario
        assert 'class="boton boton--peligro"' in formulario
        assert 'Tiene ' not in tr

    def test_confirmacion_con_el_nombre_y_la_consecuencia(self, client, auth_headers_admin, mascota_disponible):
        tr = fila(html_de(client), 'Cerbero')

        assert 'data-confirmar="¿Eliminar a Cerbero? Su ficha se borrará y no se puede deshacer."' in tr

    def test_con_solicitudes_no_ofrece_eliminar(self, client, auth_headers_admin, solicitud_pendiente):
        html = html_de(client)
        tr = fila(html, 'Cerbero')

        assert '/mascotas/admin/eliminar/' not in tr
        assert 'Eliminar' not in tr
        assert 'Tiene 1 solicitud<span class="visualmente-oculto">, no se puede eliminar</span>' in tr

    def test_disponible_con_solicitudes_ofrece_marcarla_como_adoptada(self, client, auth_headers_admin,
                                                                      solicitud_pendiente):
        tr = fila(html_de(client), 'Cerbero')

        mascota_id = solicitud_pendiente.mascota_id
        assert re.search(rf'<a [^>]*href="/mascotas/admin/editar/{mascota_id}"[^>]*>'
                         r'Marcar como adoptada<span class="visualmente-oculto"> a Cerbero</span></a>', tr)

    def test_adoptada_con_solicitudes_solo_lo_explica(self, client, auth_headers_admin, mascota_adoptada):
        solicitar(mascota_adoptada, estado='aprobada')

        tr = fila(html_de(client), 'Luna')

        assert 'Tiene 1 solicitud' in tr
        assert 'Marcar como adoptada' not in tr
        assert '/mascotas/admin/eliminar/' not in tr

    def test_cuenta_todas_las_solicitudes_en_plural(self, client, auth_headers_admin, mascota_disponible):
        solicitar(mascota_disponible, 'pendiente', 'a@test.com')
        solicitar(mascota_disponible, 'rechazada', 'b@test.com')
        solicitar(mascota_disponible, 'rechazada', 'c@test.com')

        assert 'Tiene 3 solicitudes<span' in fila(html_de(client), 'Cerbero')

    def test_solo_cuenta_las_suyas(self, client, auth_headers_admin, solicitud_pendiente, mascota_adoptada):
        html = html_de(client)

        assert 'Tiene ' not in fila(html, 'Luna')
        assert f'action="/mascotas/admin/eliminar/{mascota_adoptada.id}"' in fila(html, 'Luna')


class TestFiltroYPaginacion:

    def enlace(self, html, texto):
        coincidencia = re.search(rf'<a ([^>]*)>{texto}</a>', html)
        assert coincidencia, texto
        return coincidencia.group(1)

    def test_filtro_marca_el_estado_actual(self, client, auth_headers_admin, mascota_disponible, mascota_adoptada):
        html = html_de(client, LISTA + '?estado=adoptado')

        assert '<nav class="filtro-estado" aria-label="Filtrar por estado">' in html
        assert 'aria-current="page"' in self.enlace(html, 'Adoptadas')
        assert 'aria-current' not in self.enlace(html, 'Todas')
        assert '<caption id="mascotas-titulo">Mascotas adoptadas</caption>' in html
        assert 'Luna' in html and 'Cerbero' not in html

    @pytest.mark.parametrize('estado', ['en_proceso', 'inventado'])
    def test_filtro_desconocido_muestra_todas(self, client, auth_headers_admin, mascota_disponible,
                                              mascota_adoptada, estado):
        html = html_de(client, f'{LISTA}?estado={estado}')

        assert 'aria-current="page"' in self.enlace(html, 'Todas')
        assert 'Cerbero' in html and 'Luna' in html
        assert '<caption id="mascotas-titulo">Todas las mascotas</caption>' in html
        # Los enlaces de orden conservan la query string tal cual (url_orden); el filtro sigue ignorado
        assert f'aria-current="page">{estado}' not in html

    @pytest.fixture
    def veinticinco(self, app):
        db.session.add_all([Mascota(nombre=f'M{i:02d}', especie='Perro', descripcion='Descripción larga')
                            for i in range(25)])
        db.session.commit()

    def test_paginacion_de_la_base_nueva(self, client, auth_headers_admin, veinticinco):
        html = html_de(client)

        assert '<nav class="paginacion" aria-label="Paginación">' in html
        assert 'page-link' not in html
        assert 'Total: 25 mascotas' in html

    def test_paginacion_conserva_filtro_y_orden(self, client, auth_headers_admin, veinticinco):
        html = html_de(client, LISTA + '?estado=disponible&orden=nombre&dir=desc')

        assert 'href="/mascotas/admin?estado=disponible&amp;orden=nombre&amp;dir=desc&amp;page=2"' in html

    @pytest.mark.parametrize('direccion', ['asc', 'desc'])
    def test_empates_se_desempatan_por_id_sin_repetir_ni_saltar(self, client, auth_headers_admin, direccion):
        """Con valores repetidos, las dos páginas juntas son todas las mascotas, una vez y por id creciente."""
        db.session.add_all([Mascota(nombre=f'E{i:02d}', especie='Perro', descripcion='Descripción larga',
                                    estado='adoptado' if i % 2 else 'disponible') for i in range(25)])
        db.session.commit()
        ids = {m.nombre: m.id for m in db.session.scalars(db.select(Mascota))}

        vistos = []
        for pagina in (1, 2):
            html = html_de(client, f'{LISTA}?orden=especie&dir={direccion}&page={pagina}')
            vistos += re.findall(r'<th scope="row">(E\d\d)</th>', html)

        assert sorted(vistos) == sorted(ids)
        assert [ids[n] for n in vistos] == sorted(ids.values())

    def test_total_en_singular(self, client, auth_headers_admin, mascota_disponible):
        assert 'Total: 1 mascota<' in html_de(client)


class TestEstadoVacio:

    def test_sin_mascotas(self, client, auth_headers_admin):
        html = html_de(client)

        assert 'Todavía no hay mascotas' in html
        assert '<table' not in html
        assert 'href="/mascotas/admin/nueva">Añadir la primera</a>' in html

    def test_sin_mascotas_con_ese_estado(self, client, auth_headers_admin, mascota_disponible):
        html = html_de(client, LISTA + '?estado=adoptado')

        assert 'No hay mascotas adoptadas' in html
        assert 'href="/mascotas/admin">Ver todas</a>' in html


class TestEliminarEnElServidor:
    """Aunque se fuerce el POST, una mascota con solicitudes no se borra (P-46)."""

    @pytest.mark.parametrize('estado', ['pendiente', 'aprobada', 'rechazada'])
    def test_rechaza_con_cualquier_solicitud(self, client, auth_headers_admin, mascota_disponible, estado):
        solicitar(mascota_disponible, estado)
        mascota_id = mascota_disponible.id

        respuesta = client.post(f'/mascotas/admin/eliminar/{mascota_id}', follow_redirects=True)

        html = respuesta.data.decode()
        assert ('No puedes eliminar a Cerbero porque tiene solicitudes. Si ya no está en el refugio, '
                'márcala como adoptada desde «Editar».') in html
        assert db.session.get(Mascota, mascota_id) is not None

    def test_aviso_al_eliminar(self, client, auth_headers_admin, mascota_disponible):
        respuesta = client.post(f'/mascotas/admin/eliminar/{mascota_disponible.id}', follow_redirects=True)

        assert 'Se ha eliminado a Cerbero.' in respuesta.data.decode()

    def test_sin_token_csrf_no_borra(self, app, client, auth_headers_admin, mascota_disponible):
        app.config['WTF_CSRF_ENABLED'] = True
        mascota_id = mascota_disponible.id

        assert client.post(f'/mascotas/admin/eliminar/{mascota_id}').status_code == 400
        assert db.session.get(Mascota, mascota_id) is not None

    def test_adoptante_no_puede_eliminar(self, client, auth_headers_adoptante, mascota_disponible):
        mascota_id = mascota_disponible.id

        # admin_required redirige al catálogo sin tocar nada
        respuesta = client.post(f'/mascotas/admin/eliminar/{mascota_id}')
        assert respuesta.status_code == 302
        assert respuesta.headers['Location'].endswith('/mascotas/catalogo')
        assert db.session.get(Mascota, mascota_id) is not None

    def test_por_get_no_se_borra(self, client, auth_headers_admin, mascota_disponible):
        assert client.get(f'/mascotas/admin/eliminar/{mascota_disponible.id}').status_code == 405
