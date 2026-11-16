"""
Páginas de error de la web.

Todas renderizan errores/error.html, que extiende base.html (lang="es" y
navegación), con su código de estado, un h1 en español y al menos una
salida. Las rutas de /api/ conservan su respuesta: devolver la propia
excepción deja que Werkzeug o flask-restx la formateen ({"error": ...}).
"""

import math
import time
from urllib.parse import urlsplit

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf.csrf import CSRFError
from markupsafe import escape

from app import db, limiter
from app.routes.auth import es_redireccion_segura

# Página de reserva si la plantilla de error también falla (p. ej. si la base
# de datos no responde, base.html no puede cargar el usuario)
PAGINA_ERROR_MINIMA = (
    '<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>{titulo} - Portal de Adopción</title></head>'
    '<body><main><h1>{titulo}</h1><p>{mensaje}</p>'
    '<p><a href="/">Ir al inicio</a></p></main></body></html>'
)

MENSAJE_500 = (
    'No hemos podido completar la acción por un problema nuestro. Vuelve a intentarlo '
    'dentro de unos minutos. Si estabas enviando una solicitud, comprueba en Mis solicitudes '
    'si se ha guardado.'
)


def es_anonimo(usuario):
    return not usuario.is_authenticated


def es_adoptante(usuario):
    return usuario.is_authenticated and not usuario.is_admin()


# Salidas: (texto, endpoint) o (texto, endpoint, condición sobre el usuario)
INICIO = ('Ir al inicio', 'index')
CATALOGO = ('Ver mascotas disponibles', 'mascotas.catalogo')
INICIAR_SESION = ('Iniciar sesión', 'auth.login', es_anonimo)
MIS_SOLICITUDES = ('Ver mis solicitudes', 'solicitudes.mis_solicitudes', es_adoptante)

# Errores sin lógica propia: código -> (título, mensaje, salidas)
ERRORES_SIMPLES = {
    400: ('No hemos podido procesar la petición',
          'Los datos enviados no son válidos. Vuelve a la página anterior e inténtalo de nuevo.',
          (INICIO,)),
    403: ('No tienes acceso a esta página',
          'Esta página no está disponible con tu cuenta. Si crees que es un error, '
          'inicia sesión con otra cuenta.',
          (INICIAR_SESION, INICIO)),
    404: ('No encontramos esta página',
          'Puede que la mascota ya no esté en el catálogo o que el enlace sea incorrecto.',
          (CATALOGO, INICIO)),
}


def es_peticion_api():
    """La API tiene su propio formato de errores ({"error": ...}) y no se toca."""
    return request.path.startswith('/api/')


def resolver_salidas(salidas):
    """Convierte las salidas en pares (texto, url), quitando las que no aplican al usuario."""
    return [(texto, url_for(endpoint)) for texto, endpoint, *condicion in salidas
            if not condicion or condicion[0](current_user)]


def pagina_error(codigo, titulo, mensaje, salidas=(INICIO,), primera=None, cabeceras=None):
    """
    Renderiza errores/error.html con el código de estado indicado.

    `primera` es un par (texto, url) ya resuelto que va delante de las
    demás salidas (p. ej. «Volver al formulario»).
    """
    try:
        enlaces = ([primera] if primera else []) + resolver_salidas(salidas)
        html = render_template('errores/error.html', titulo=titulo, mensaje=mensaje, salidas=enlaces)
    except Exception:
        current_app.logger.exception('No se ha podido renderizar la página de error %s', codigo)
        html = PAGINA_ERROR_MINIMA.format(titulo=escape(titulo), mensaje=escape(mensaje))
    return html, codigo, cabeceras or {}


def url_de_vuelta():
    """
    Ruta local de la página anterior (Referer) si es de este mismo sitio, o
    None. Solo se devuelve ruta y query, nunca un host.
    """
    if not request.referrer:
        return None
    partes = urlsplit(request.referrer)
    if partes.scheme not in ('http', 'https') or partes.netloc != request.host:
        return None
    destino = partes.path + (f'?{partes.query}' if partes.query else '')
    return destino if es_redireccion_segura(destino) else None


def texto_espera(segundos):
    """«un minuto» o «N minutos», redondeando hacia arriba."""
    minutos = max(1, math.ceil(segundos / 60))
    return 'un minuto' if minutos == 1 else f'{minutos} minutos'


def segundos_de_espera():
    """
    Segundos hasta que se reinicia el límite superado. Flask-Limiter solo
    añade Retry-After con RATELIMIT_HEADERS_ENABLED, que pondría también las
    cabeceras X-RateLimit-* en todas las respuestas (API incluida).
    """
    try:
        limite = limiter.current_limit
        if limite:
            return max(1, math.ceil(limite.window.reset_time - time.time()))
    except Exception:
        current_app.logger.exception('No se ha podido calcular Retry-After')
    return 60


def manejador_simple(codigo, titulo, mensaje, salidas):
    def manejador(e):
        if es_peticion_api():
            return e
        return pagina_error(codigo, titulo, mensaje, salidas)
    manejador.__name__ = f'error_{codigo}'
    return manejador


def registrar_manejadores_errores(app):
    """Registra las páginas de error de la web en `app`."""
    for codigo, (titulo, mensaje, salidas) in ERRORES_SIMPLES.items():
        app.register_error_handler(codigo, manejador_simple(codigo, titulo, mensaje, salidas))

    @app.errorhandler(CSRFError)
    def sesion_caducada(e):
        if es_peticion_api():
            return e
        current_app.logger.info('Formulario rechazado por CSRF: %s', e.description)
        vuelta = url_de_vuelta()
        return pagina_error(
            400, 'Tu sesión ha caducado',
            'Por seguridad, no hemos podido enviar el formulario. Vuelve a abrirlo y envíalo de nuevo.',
            primera=('Volver al formulario', vuelta) if vuelta else None)

    @app.errorhandler(405)
    def metodo_no_permitido(e):
        if es_peticion_api():
            return e
        cabeceras = {'Allow': ', '.join(e.valid_methods)} if e.valid_methods else None
        return pagina_error(
            405, 'Esta acción no está disponible desde aquí',
            'Puede que hayas llegado por un enlace antiguo. Vuelve al inicio para seguir navegando.',
            cabeceras=cabeceras)

    @app.errorhandler(413)
    def archivo_demasiado_grande(e):
        # Se vuelve al formulario con el aviso. 302 normal: el navegador no
        # sigue un Location con estado 413. No se excluye /api/ para no
        # cambiar su respuesta: las rutas de flask-restx formatean su
        # propio 413 en JSON y este manejador ya atendía el resto
        flash('La foto ocupa demasiado. Elige una de 5 MB como máximo.', 'danger')
        return redirect(request.url)

    @app.errorhandler(429)
    def demasiados_intentos(e):
        if es_peticion_api():
            return e
        espera = segundos_de_espera()
        return pagina_error(
            429, 'Has hecho demasiados intentos',
            f'Por seguridad, hemos pausado los intentos desde tu conexión. '
            f'Espera {texto_espera(espera)} y vuelve a intentarlo.',
            cabeceras={'Retry-After': str(espera)})

    @app.errorhandler(500)
    def error_interno(e):
        if es_peticion_api():
            return e
        # Flask ya registra las excepciones no controladas; aquí solo queda
        # por registrar un abort(500) explícito
        if e.original_exception is None:
            current_app.logger.exception('Error 500 en %s %r', request.method, request.path, exc_info=e)
        # La transacción puede haber quedado a medias
        try:
            db.session.rollback()
        except Exception:
            current_app.logger.exception('No se ha podido deshacer la transacción tras el error')
        return pagina_error(500, 'Algo ha fallado', MENSAJE_500, (MIS_SOLICITUDES, INICIO))
