"""
Reprocesado de las fotos subidas con Pillow (ADR-0003).

Nunca se guarda el archivo tal como llega: se decodifica y se vuelve a
codificar en WebP, de modo que no sobrevive nada que no sean los píxeles.
- Solo se aceptan los decodificadores de FORMATOS: el tipo sale del
  contenido, no del nombre ni del Content-Type.
- Más píxeles que `max_pixeles` (FOTOS_MAX_PIXELES) o que
  Image.MAX_IMAGE_PIXELS es un error, comprobado antes de decodificar. Pillow
  sigue lanzando DecompressionBombError a partir del doble de su límite.
- Ningún lado puede pasar de MAX_LADO, el máximo de WebP.
- Se aplica la orientación EXIF, el perfil ICC se convierte a sRGB y
  después se descartan todos los metadatos (EXIF con el GPS, XMP, ICC).
- La transparencia se aplana sobre blanco, el fondo de las fichas: así toda
  foto queda en RGB y se ve igual en cualquier fondo.
- De un GIF o WebP animado solo se conserva la primera imagen.

Memoria: se mantiene como mucho la imagen decodificada y una copia
convertida a la vez, y las variantes se generan en cadena (1200 → 800 →
400), cada una reduciendo la anterior.
"""

import io
import logging

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

# Anchos de las variantes, de menor a mayor. La última es la foto principal
ANCHOS = (400, 800, 1200)

FORMATOS = ('PNG', 'JPEG', 'GIF', 'WEBP')

# Máximo de WebP por lado
MAX_LADO = 16383

FONDO_TRANSPARENCIA = (255, 255, 255)

CALIDAD_WEBP = 82

# Modos de los que se convierte el perfil ICC (entrada → salida). Los
# grises necesitarían un perfil de gris de salida: se quedan sin convertir
MODOS_ICC = {'RGB': 'RGB', 'RGBA': 'RGBA', 'CMYK': 'RGB'}

# Errores de Pillow con un archivo dañado, truncado o malicioso
ERRORES_PILLOW = (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError)

logger = logging.getLogger(__name__)


class ImagenNoValida(Exception):
    """El archivo no es una imagen permitida o no se puede decodificar."""


class ImagenDemasiadoGrande(ImagenNoValida):
    """Algún lado pasa de MAX_LADO: el mensaje al usuario es otro."""


def _comprobar_tamano(imagen, max_pixeles):
    """Con la cabecera basta: open() todavía no ha decodificado nada."""
    if max(imagen.size) > MAX_LADO:
        raise ImagenDemasiadoGrande(f'{imagen.width}x{imagen.height}')
    pixeles = imagen.width * imagen.height
    for limite in (max_pixeles, Image.MAX_IMAGE_PIXELS):
        if limite and pixeles > limite:
            raise ImagenNoValida(f'{pixeles} píxeles, más que {limite}')


def _a_srgb(imagen, icc):
    """Convierte los colores del perfil ICC a sRGB; si no se puede, deja la imagen igual."""
    salida = MODOS_ICC.get(imagen.mode)
    if salida is None:
        return imagen
    try:
        origen = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        destino = ImageCms.createProfile('sRGB')
        if salida == imagen.mode:
            ImageCms.profileToProfile(imagen, origen, destino, outputMode=salida, inPlace=True)
            return imagen
        return ImageCms.profileToProfile(imagen, origen, destino, outputMode=salida)
    except (ImageCms.PyCMSError, OSError, ValueError, TypeError):
        logger.warning('No se pudo convertir el perfil de color a sRGB; se usa sin convertir', exc_info=True)
        return imagen


def _a_8_bits(imagen):
    """Gris de 16 o 32 bits (modos I): escalar a 0-255 antes de convertir, o sale blanco."""
    if not imagen.mode.startswith('I'):
        return imagen
    return imagen.convert('I').point(lambda valor: valor * (1 / 256)).convert('L')


def _a_rgb(imagen):
    """RGB sin canal alfa; lo transparente queda del color de FONDO_TRANSPARENCIA."""
    if imagen.mode in ('RGBA', 'LA', 'PA', 'P') or 'transparency' in imagen.info:
        # Sin copiar si ya es RGBA: es la imagen más grande que se maneja
        rgba = imagen if imagen.mode == 'RGBA' else imagen.convert('RGBA')
        fondo = Image.new('RGB', rgba.size, FONDO_TRANSPARENCIA)
        fondo.paste(rgba, mask=rgba.getchannel('A'))
        return fondo
    if imagen.mode == 'RGB':
        return imagen
    return imagen.convert('RGB')


def _decodificar(stream, max_pixeles):
    """Imagen en RGB sRGB, ya orientada y sin metadatos."""
    with Image.open(stream, formats=FORMATOS) as imagen:
        _comprobar_tamano(imagen, max_pixeles)
        # JPEG: decodificar ya reducido si sobra resolución (menos memoria)
        imagen.draft('RGB', (ANCHOS[-1], ANCHOS[-1]))
        imagen.load()
        # Sin dejar viva la imagen sin girar
        ImageOps.exif_transpose(imagen, in_place=True)
        icc = imagen.info.get('icc_profile')
        convertida = _a_srgb(imagen, icc) if icc else imagen
        convertida = _a_rgb(_a_8_bits(convertida))
    convertida.info = {}
    return convertida


def _webp(imagen):
    buffer = io.BytesIO()
    # Sin exif, xmp ni icc_profile: Pillow solo los escribe si se le pasan
    imagen.save(buffer, format='WEBP', quality=CALIDAD_WEBP)
    return buffer.getvalue()


def procesar(stream, max_pixeles=None):
    """
    Reprocesa una imagen subida y genera sus variantes.

    Args:
        stream: archivo con la imagen.
        max_pixeles (int | None): límite de píxeles además del de Pillow.

    Returns:
        dict: ancho → bytes WebP, para cada ancho de ANCHOS (de menor a
        mayor). Una imagen más estrecha que un ancho no se amplía: esa
        variante conserva su tamaño.

    Raises:
        ImagenDemasiadoGrande: algún lado pasa de MAX_LADO.
        ImagenNoValida: formato no permitido, demasiados píxeles o archivo
        dañado.
    """
    try:
        imagen = _decodificar(stream, max_pixeles)
        variantes = {}
        for ancho in reversed(ANCHOS):
            # En el sitio y a partir de la anterior; thumbnail nunca amplía
            imagen.thumbnail((ancho, imagen.height), Image.Resampling.LANCZOS)
            variantes[ancho] = _webp(imagen)
    except ERRORES_PILLOW as error:
        raise ImagenNoValida(str(error)) from None
    return {ancho: variantes[ancho] for ancho in ANCHOS}
