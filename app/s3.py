import uuid

import boto3
from flask import current_app
from PIL import Image, UnidentifiedImageError

# Carpeta del bucket donde se guardan las fotos de mascotas
PREFIJO_FOTOS = 'mascotas/'

# Formatos que detecta Pillow -> (extensión, Content-Type)
FORMATOS_IMAGEN = {
    'PNG': ('png', 'image/png'),
    'JPEG': ('jpg', 'image/jpeg'),
    'GIF': ('gif', 'image/gif'),
    'WEBP': ('webp', 'image/webp'),
}


def allowed_file(filename):
    """Verifica si la extensión del archivo está permitida."""
    return "." in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def detectar_formato_imagen(file):
    """
    Comprueba el contenido real del archivo con Pillow.

    Returns:
        tuple | None: (extensión, Content-Type) o None si no es una imagen
        permitida. El puntero del archivo queda al principio.
    """
    try:
        with Image.open(file.stream) as imagen:
            formato = imagen.format
            imagen.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return None
    finally:
        file.stream.seek(0)
    return FORMATOS_IMAGEN.get(formato)


def es_url_imagen_valida(url):
    """Una URL de foto introducida a mano debe ser https."""
    return url.lower().startswith('https://')


def _cliente_s3():
    return boto3.client(
        's3',
        aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY'],
        region_name=current_app.config['AWS_S3_REGION']
    )


def _url_base_fotos():
    bucket = current_app.config['AWS_S3_BUCKET']
    region = current_app.config['AWS_S3_REGION']
    return f"https://{bucket}.s3.{region}.amazonaws.com/{PREFIJO_FOTOS}"


def upload_to_s3(file):
    """Sube un archivo a S3 y retorna la URL pública."""
    if not allowed_file(file.filename):
        return None

    # El tipo se deduce del contenido, no del nombre ni del Content-Type que
    # envía el navegador: así no se puede subir HTML con extensión .png
    formato = detectar_formato_imagen(file)
    if formato is None:
        return None
    ext, content_type = formato

    # Nombre único para evitar colisiones
    filename = f"{PREFIJO_FOTOS}{uuid.uuid4().hex}.{ext}"

    _cliente_s3().upload_fileobj(
        file,
        current_app.config['AWS_S3_BUCKET'],
        filename,
        ExtraArgs={'ContentType': content_type}
    )

    return _url_base_fotos() + filename[len(PREFIJO_FOTOS):]


def delete_from_s3(url):
    """
    Elimina una foto de S3 por su URL.

    Solo borra objetos de la carpeta de fotos de nuestro bucket: foto_url
    puede ser una URL externa introducida a mano y no debe permitir borrar
    otras claves.
    """
    base = _url_base_fotos()
    if not url or not url.startswith(base):
        return

    nombre = url[len(base):]
    if not nombre or '/' in nombre:
        return

    _cliente_s3().delete_object(
        Bucket=current_app.config['AWS_S3_BUCKET'],
        Key=PREFIJO_FOTOS + nombre
    )
