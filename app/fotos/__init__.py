"""
Almacenamiento de las fotos de mascotas (ADR-0003).

Interfaz común sobre dos backends, elegidos con FOTOS_BACKEND:
- `local`: archivos en FOTOS_DIR (o instance/fotos), servidos por GET /fotos/<clave>;
- `s3`: AWS S3 o un servicio compatible (AWS_S3_ENDPOINT_URL).

Sin backend, `subida_disponible()` es falso y el formulario solo admite URLs.
`foto_url` guarda la ruta `/fotos/<clave>` (local), la URL completa (S3) o
una URL externa `https://`, que nunca se borra.

Cada foto subida se reprocesa (app/fotos/procesado.py) y se guarda como tres
variantes WebP con el mismo nombre aleatorio: `<hex>-400.webp`,
`<hex>-800.webp` y `<hex>-1200.webp`. `foto_url` apunta a la de 1200 y
`srcset_foto` deduce las otras de ella. Las fotos anteriores a las variantes
(`<hex>.png`, `.jpg`...) siguen siendo válidas y son un único archivo.
"""

import io
import re
import uuid

from flask import current_app

from app.fotos import local, procesado, s3

BACKENDS = {'local': local, 's3': s3}

# Nombre de cada archivo guardado: 32 hex aleatorios y, o bien el sufijo de
# una variante, o bien la extensión de una foto anterior a las variantes
PATRON_CLAVE = re.compile(
    r'(?P<base>[0-9a-f]{32})'
    r'(?:\.(?:png|jpg|gif|webp)|-(?P<ancho>' + '|'.join(map(str, procesado.ANCHOS)) + r')\.webp)'
)

CONTENT_TYPE_VARIANTES = 'image/webp'

# Mensajes para el campo de foto: la causa y qué puede hacer el admin (P-32)
MENSAJE_FORMATO = 'No hemos podido usar esa imagen. Sube un archivo JPG, PNG, GIF o WebP.'
MENSAJE_DIMENSIONES = f'La imagen es demasiado grande: como máximo {procesado.MAX_LADO} px por lado.'
MENSAJE_NO_DISPONIBLE = ('La subida de archivos no está disponible en este servidor. '
                         'Quita el archivo y pega el enlace https:// de la imagen.')
MENSAJE_FALLO = ('No hemos podido guardar la foto por un problema del servidor. '
                 'Inténtalo de nuevo más tarde o pega el enlace https:// de la imagen.')


class ErrorAlmacenamiento(Exception):
    """La foto no se ha guardado; `mensaje` se muestra junto al campo."""

    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.mensaje = mensaje


def es_clave_valida(clave):
    """Solo las claves que genera guardar_foto: impide rutas como `../x`."""
    return bool(clave) and PATRON_CLAVE.fullmatch(clave) is not None


def es_url_imagen_valida(url):
    """Una URL de foto introducida a mano debe ser https."""
    return url.lower().startswith('https://')


def _backend():
    return BACKENDS.get(current_app.config.get('FOTOS_BACKEND') or '')


def subida_disponible():
    """Hay un backend configurado con lo que necesita para guardar fotos."""
    backend = _backend()
    return backend is not None and backend.disponible()


def _extension_permitida(nombre):
    return '.' in nombre and nombre.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def _clave_variante(base, ancho):
    return f'{base}-{ancho}.webp'


def _claves_de_la_foto(clave):
    """Todas las claves de la foto: sus variantes o, si es anterior a ellas, solo la suya."""
    coincidencia = PATRON_CLAVE.fullmatch(clave)
    if coincidencia['ancho'] is None:
        return [clave]
    return [_clave_variante(coincidencia['base'], ancho) for ancho in procesado.ANCHOS]


def _borrar_claves(backend, claves):
    """Borra cada clave aunque falle alguna; devuelve si se han borrado todas."""
    borradas = True
    for clave in claves:
        try:
            backend.borrar(clave)
        except backend.ERRORES:
            current_app.logger.exception('No se pudo borrar la foto %s', clave)
            borradas = False
    return borradas


def guardar_foto(archivo):
    """
    Reprocesa la foto subida y guarda sus variantes con un nombre aleatorio.

    El tipo se deduce del contenido, no del nombre ni del Content-Type que
    envía el navegador: así no se puede subir HTML con extensión .png. Lo
    que se guarda es siempre WebP recodificado, sin metadatos.

    Returns:
        str: el valor para `foto_url` (la variante de 1200 px).

    Raises:
        ErrorAlmacenamiento: sin backend, formato no válido o fallo al guardar
        (este último se registra en el log y no deja variantes sueltas).
    """
    if not subida_disponible():
        raise ErrorAlmacenamiento(MENSAJE_NO_DISPONIBLE)
    if not _extension_permitida(archivo.filename or ''):
        raise ErrorAlmacenamiento(MENSAJE_FORMATO)
    try:
        variantes = procesado.procesar(archivo.stream, current_app.config.get('FOTOS_MAX_PIXELES'))
    except procesado.ImagenNoValida as error:
        current_app.logger.info('Foto rechazada: %s', error)
        mensaje = MENSAJE_DIMENSIONES if isinstance(error, procesado.ImagenDemasiadoGrande) else MENSAJE_FORMATO
        raise ErrorAlmacenamiento(mensaje) from None

    backend = _backend()
    base = uuid.uuid4().hex
    guardadas = []
    completa = False
    try:
        for ancho, contenido in variantes.items():
            clave = _clave_variante(base, ancho)
            url = backend.guardar(io.BytesIO(contenido), clave, CONTENT_TYPE_VARIANTES)
            guardadas.append(clave)
        completa = True
    except backend.ERRORES:
        current_app.logger.exception('No se pudo guardar la foto (backend %s)', current_app.config.get('FOTOS_BACKEND'))
        raise ErrorAlmacenamiento(MENSAJE_FALLO) from None
    finally:
        # Ante cualquier excepción, que no queden variantes sueltas
        if not completa:
            _borrar_claves(backend, guardadas)
    # ANCHOS va de menor a mayor: la última es la principal
    return url


def _clave_propia(backend, url):
    """
    Clave de una foto guardada por el backend, o None.

    foto_url puede ser una URL externa introducida a mano: solo se aceptan
    las claves que genera guardar_foto, sin `/` ni `..`, para no tocar otros
    archivos u objetos.
    """
    nombre = backend.nombre_en_url(url) if backend else None
    return nombre if es_clave_valida(nombre) else None


def es_foto_propia(url):
    """La foto la guardó el backend actual (y no es una URL externa)."""
    return _clave_propia(_backend(), url) is not None


def urls_de_la_foto(url):
    """
    URLs de todos los archivos de la foto, de menor a mayor.

    Para una foto propia con variantes, las de las tres variantes (sea cual
    sea la que se pase); para cualquier otra, solo la propia `url`.
    """
    clave = _clave_propia(_backend(), url)
    if clave is None:
        return [url]
    prefijo = url[:-len(clave)]
    return [prefijo + c for c in _claves_de_la_foto(clave)]


def srcset_foto(url):
    """
    Filtro Jinja: el `srcset` de las variantes de una foto propia.

    Devuelve '' para las URLs externas, las fotos anteriores a las variantes
    o sin foto, así que la plantilla puede omitir el atributo. Las variantes
    de una imagen más estrecha que su ancho no se amplían, pero se anuncian
    con el ancho nominal.
    """
    clave = _clave_propia(_backend(), url)
    if clave is None or PATRON_CLAVE.fullmatch(clave)['ancho'] is None:
        return ''
    return ', '.join(f'{u} {ancho}w' for u, ancho in zip(urls_de_la_foto(url), procesado.ANCHOS, strict=True))


def borrar_foto(url):
    """
    Borra una foto propia con todas sus variantes; las URLs externas o
    ajenas se ignoran.

    Un fallo se registra en el log y no se propaga: se llama después de un
    commit correcto y no debe convertirlo en un error para el usuario.

    Returns:
        bool: True si la foto era propia y ya no existe ninguno de sus archivos.
    """
    backend = _backend()
    clave = _clave_propia(backend, url)
    if clave is None:
        return False
    return _borrar_claves(backend, _claves_de_la_foto(clave))
