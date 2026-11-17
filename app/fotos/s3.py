"""
Backend `s3`: AWS S3 o un servicio compatible con S3.

Con AWS_S3_ENDPOINT_URL (MinIO, Cloudflare R2...) las URLs públicas usan el
estilo de ruta `<endpoint>/<bucket>/mascotas/<clave>`; sin él, las de AWS.
"""

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app

# Carpeta del bucket donde se guardan las fotos de mascotas
PREFIJO_FOTOS = 'mascotas/'

ERRORES = (BotoCoreError, ClientError)


def _cliente():
    return boto3.client(
        's3',
        aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY'],
        region_name=current_app.config['AWS_S3_REGION'],
        endpoint_url=current_app.config.get('AWS_S3_ENDPOINT_URL') or None,
    )


def _url_base():
    bucket = current_app.config['AWS_S3_BUCKET']
    endpoint = current_app.config.get('AWS_S3_ENDPOINT_URL')
    if endpoint:
        return f"{endpoint.rstrip('/')}/{bucket}/{PREFIJO_FOTOS}"
    return f"https://{bucket}.s3.{current_app.config['AWS_S3_REGION']}.amazonaws.com/{PREFIJO_FOTOS}"


def disponible():
    return bool(current_app.config.get('AWS_S3_BUCKET'))


def guardar(stream, clave, content_type):
    _cliente().upload_fileobj(
        stream,
        current_app.config['AWS_S3_BUCKET'],
        PREFIJO_FOTOS + clave,
        ExtraArgs={'ContentType': content_type},
    )
    return _url_base() + clave


def nombre_en_url(url):
    """Lo que sigue a la carpeta de fotos de nuestro bucket, o None si la URL es ajena."""
    if not url or not disponible():
        return None
    base = _url_base()
    if not url.startswith(base):
        return None
    return url[len(base):]


def borrar(nombre):
    _cliente().delete_object(Bucket=current_app.config['AWS_S3_BUCKET'], Key=PREFIJO_FOTOS + nombre)
