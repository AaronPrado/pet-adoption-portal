"""
Almacenamiento de las fotos de mascotas (ADR-0003).

Interfaz común sobre dos backends, elegidos con FOTOS_BACKEND:
- `local`: archivos en FOTOS_DIR (o instance/fotos), servidos por GET /fotos/<clave>;
- `s3`: AWS S3 o un servicio compatible (AWS_S3_ENDPOINT_URL).

Sin backend, `subida_disponible()` es falso y guardar_foto da un error de campo.
`foto_url` guarda la ruta `/fotos/<clave>` (local), la URL completa (S3) o
una URL externa `https://`, que nunca se borra.
"""

import re
import uuid

from flask import current_app
from PIL import Image, UnidentifiedImageError

from app.fotos import local, s3

BACKENDS = {'local': local, 's3': s3}

# Nombre de cada foto guardada: 32 hex aleatorios y la extensión del formato
PATRON_CLAVE = re.compile(r'[0-9a-f]{32}\.(?:png|jpg|gif|webp)')

# Formatos que detecta Pillow -> (extensión, Content-Type)
FORMATOS_IMAGEN = {
    'PNG': ('png', 'image/png'),
    'JPEG': ('jpg', 'image/jpeg'),
    'GIF': ('gif', 'image/gif'),
    'WEBP': ('webp', 'image/webp'),
}

# Mensajes para el campo de foto
MENSAJE_FORMATO = 'Formato de imagen no permitido'
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


def detectar_formato_imagen(archivo):
    """
    Comprueba el contenido real del archivo con Pillow.

    Returns:
        tuple | None: (extensión, Content-Type) o None si no es una imagen
        permitida. El puntero del archivo queda al principio.
    """
    try:
        with Image.open(archivo.stream) as imagen:
            formato = imagen.format
            imagen.verify()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        # DecompressionBombError: más píxeles que Image.MAX_IMAGE_PIXELS
        return None
    finally:
        archivo.stream.seek(0)
    return FORMATOS_IMAGEN.get(formato)


def guardar_foto(archivo):
    """
    Guarda la foto subida con un nombre aleatorio.

    El tipo se deduce del contenido, no del nombre ni del Content-Type que
    envía el navegador: así no se puede subir HTML con extensión .png.

    Returns:
        str: el valor para `foto_url`.

    Raises:
        ErrorAlmacenamiento: sin backend, formato no válido o fallo al guardar
        (este último se registra en el log).
    """
    if not subida_disponible():
        raise ErrorAlmacenamiento(MENSAJE_NO_DISPONIBLE)
    formato = detectar_formato_imagen(archivo) if _extension_permitida(archivo.filename or '') else None
    if formato is None:
        raise ErrorAlmacenamiento(MENSAJE_FORMATO)
    extension, content_type = formato

    backend = _backend()
    try:
        return backend.guardar(archivo.stream, f'{uuid.uuid4().hex}.{extension}', content_type)
    except backend.ERRORES:
        current_app.logger.exception('No se pudo guardar la foto (backend %s)', current_app.config.get('FOTOS_BACKEND'))
        raise ErrorAlmacenamiento(MENSAJE_FALLO) from None


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


def borrar_foto(url):
    """
    Borra una foto propia; las URLs externas o ajenas se ignoran.

    Un fallo se registra en el log y no se propaga: un problema del
    almacenamiento no debe impedir guardar la mascota.

    Returns:
        bool: True si la foto era propia y ya no existe.
    """
    backend = _backend()
    clave = _clave_propia(backend, url)
    if clave is None:
        return False
    try:
        backend.borrar(clave)
    except backend.ERRORES:
        current_app.logger.exception('No se pudo borrar la foto %s', url)
        return False
    return True
