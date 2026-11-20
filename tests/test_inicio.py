"""
Portada (B4.1): usa la base sin Bootstrap y las macros, una imagen principal
local y rápida (P-38), contadores que no enseñan ceros, el recorrido de
adopción con un solo vocabulario (P-42) y la marca desde la configuración.
"""

import re
from pathlib import Path

from app import db
from app.models import Mascota

RAIZ_STATIC = Path(__file__).resolve().parent.parent / 'app' / 'static'


def portada(client):
    response = client.get('/')
    assert response.status_code == 200
    return response.data.decode()


def etiqueta(html, patron):
    coincidencia = re.search(patron, html)
    assert coincidencia, patron
    return coincidencia.group(0)


def test_usa_la_base_sin_bootstrap(client):
    html = portada(client)

    assert 'css/sistema.css' in html and 'bootstrap' not in html.lower()
    assert not re.search(r'class="[^"]*\b(btn|card|row|col-[a-z]+-\d+|container|text-center)\b', html)
    assert 'css/paginas/inicio.css' in html


def test_un_solo_h1_y_titulo_coherente(client, app):
    html = portada(client)

    assert html.count('<h1') == 1
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S).group(1).strip()
    titulo = re.search(r'<title>(.*?)</title>', html, re.S).group(1)
    assert h1 in titulo
    assert app.config['MARCA_NOMBRE'] in titulo


def test_la_marca_sale_de_la_configuracion(app, client):
    app.config['MARCA_NOMBRE'] = 'Huellas del Sur'

    html = portada(client)

    assert 'Huellas del Sur' in re.search(r'<title>(.*?)</title>', html).group(1)
    assert 'Portal de Adopción' not in re.search(r'<main.*?</main>', html, re.S).group(0)


def test_imagen_principal_local_y_prioritaria(client):
    html = portada(client)
    hero = etiqueta(html, r'<img[^>]*inicio-hero__imagen[^>]*>')

    assert 'srcset="/static/img/hero-640.webp 640w, /static/img/hero-1280.webp 1280w"' in hero
    assert 'src="/static/img/hero-1280.webp"' in hero
    assert 'sizes="' in hero
    assert 'width="1280"' in hero and 'height="753"' in hero
    assert 'fetchpriority="high"' in hero
    assert 'loading' not in hero
    # Decorativa: el mensaje lo da el h1
    assert 'alt=""' in hero
    assert 'unsplash' not in html.lower()
    for ancho in (640, 1280):
        assert (RAIZ_STATIC / 'img' / f'hero-{ancho}.webp').is_file()


def test_el_texto_va_en_un_panel_y_no_sobre_la_foto(client):
    html = portada(client)
    hero = re.search(r'<section class="inicio-hero".*?</section>', html, re.S).group(0)

    assert hero.index('inicio-hero__imagen') < hero.index('inicio-hero__panel')
    assert '<h1' in hero[hero.index('inicio-hero__panel'):]


def test_la_css_de_la_portada_solo_usa_tokens():
    css = (RAIZ_STATIC / 'css' / 'paginas' / 'inicio.css').read_text(encoding='utf-8')

    assert not re.search(r'#[0-9a-fA-F]{3,8}\b|\b(rgb|hsl|oklch)a?\(', css)
    assert 'unsplash' not in css.lower()
    assert '@layer componentes' in css


def test_sin_datos_no_hay_contadores_a_cero(client):
    html = portada(client)

    assert 'inicio-cifras' not in html
    assert not re.search(r'>\s*0\s*<', html)


def test_contadores_con_datos_y_plural(client, mascota_disponible, mascota_adoptada):
    html = portada(client)
    cifras = re.search(r'<ul class="inicio-cifras" role="list".*?</ul>', html, re.S).group(0)

    assert re.search(r'<strong>1</strong>\s*mascota espera un hogar', cifras)
    assert re.search(r'<strong>1</strong>\s*adopción lograda', cifras)
    # Sin adoptantes registrados: esa cifra se oculta
    assert 'registrad' not in cifras


def test_contadores_en_plural(client, mascota_disponible, mascota_adoptada, usuario_adoptante):
    otra = Mascota(nombre='Kira', especie='Perro', descripcion='Perra juguetona', estado='disponible')
    db.session.add(otra)
    db.session.commit()

    cifras = re.search(r'<ul class="inicio-cifras" role="list".*?</ul>', portada(client), re.S).group(0)

    assert re.search(r'<strong>2</strong>\s*mascotas esperan un hogar', cifras)
    assert re.search(r'<strong>1</strong>\s*persona registrada', cifras)


def test_mascotas_destacadas_con_la_tarjeta_comun(client, mascota_disponible):
    html = portada(client)

    assert '<ul class="rejilla-tarjetas">' in html
    assert 'Ver a Cerbero' in html
    assert re.search(r'<h3 id="mascota-\d+-nombre"', html)


def test_sin_mascotas_no_hay_seccion_de_destacadas(client):
    assert 'rejilla-tarjetas' not in portada(client)


def test_recorrido_de_adopcion(client):
    html = portada(client)
    pasos = re.search(r'<ol class="inicio-pasos" role="list".*?</ol>', html, re.S).group(0)

    for titulo in ('Crea tu cuenta', 'Elige una mascota', 'Envía tu solicitud', 'Espera nuestra respuesta'):
        assert titulo in pasos
    assert pasos.count('<li') == 4
    # El número visible no se lee dos veces: la lista ordenada ya los numera
    assert len(re.findall(r'class="inicio-pasos__numero" aria-hidden="true"', pasos)) == 4
    assert 'Comenzar Ahora' not in html and 'Proceso de Adopción' not in html


def test_llamadas_a_la_accion_segun_la_sesion(client, auth_headers_adoptante):
    con_sesion = portada(client)

    assert 'href="/mascotas/catalogo"' in con_sesion
    assert 'Crear mi cuenta' not in con_sesion


def test_invitado_ve_crear_cuenta(client):
    html = portada(client)

    assert 'href="/auth/registro"' in html and 'Crear mi cuenta' in html
    assert 'Ver mascotas disponibles' in html


def test_sin_emojis_ni_estilos_en_linea(client, mascota_disponible):
    html = portada(client)

    assert not re.search(r'[\U0001F300-\U0001FAFF☀-➿]', html)
    assert ' style=' not in html and '<style' not in html and 'onclick' not in html


def test_listas_sin_estilo_conservan_su_rol(client, mascota_disponible, mascota_adoptada):
    """Safari deja de anunciar como lista las `ul`/`ol` con list-style: none."""
    html = portada(client)

    assert '<ul class="inicio-cifras" role="list">' in html
    assert '<ol class="inicio-pasos" role="list">' in html
