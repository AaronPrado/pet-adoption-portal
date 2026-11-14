"""
Configuración de la aplicación Flask por entornos.

Este módulo define las clases de configuración para diferentes entornos:
- Config: Configuración base
- DevelopmentConfig: Configuración para desarrollo local
- ProductionConfig: Configuración para producción
- TestingConfig: Configuración para tests

Uso:
    from config import DevelopmentConfig
    app.config.from_object(DevelopmentConfig)
"""

import os

from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()


class Config:
    """
    Configuración base de Flask.

    Atributos compartidos por todos los entornos (desarrollo, producción).
    Las clases hijas heredan y pueden sobrescribir estos valores.
    """

    # SECRET_KEY: Clave secreta para sesiones, CSRF, cookies firmadas.
    # Sin valor por defecto: cada entorno define el suyo y producción lo exige.
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

    # AWS S3
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_S3_BUCKET = os.environ.get('AWS_S3_BUCKET')
    AWS_S3_REGION = os.environ.get('AWS_S3_REGION', 'eu-west-1')

    # JWT (API REST)
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    JWT_EXPIRATION_HOURS = int(os.environ.get('JWT_EXPIRATION_HOURS') or 24)

    # Límite de peticiones (Flask-Limiter). En memoria vale para un solo
    # proceso; con varios workers usar Redis (p. ej. redis://localhost:6379)
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI') or 'memory://'
    RATELIMIT_LOGIN = '5 per minute'

    # Documentación Swagger de la API (/api/docs)
    API_DOCS_ENABLED = True

    # SQLAlchemy: Desactivar tracking de modificaciones (ahorra memoria)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # SQLAlchemy: Mostrar SQL queries en logs (útil para debugging)
    SQLALCHEMY_ECHO = False

    # Flask-Mail: Configuración de email
    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER') or 'noreply@aaronpradoadopciones.com'

    # Upload de archivos: Extensiones permitidas para fotos
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

    # Upload de archivos: Tamaño máximo de archivo (5MB en bytes)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB

    # Cookies: no se envían en peticiones POST desde otros sitios (CSRF)
    # ni son accesibles desde JavaScript
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'

    @classmethod
    def init_app(cls, app):
        """Hook para validaciones específicas de cada entorno."""
        pass


class DevelopmentConfig(Config):
    """
    Configuración para entorno de desarrollo local.

    Características:
    - DEBUG activado (recargar automático + mensajes de error detallados)
    - Base de datos PostgreSQL en Docker (localhost:5432)
    - SQLAlchemy ECHO activado (ver queries SQL en consola)
    """

    DEBUG = True
    TESTING = False

    # Claves solo válidas en local; se pueden sobrescribir desde .env
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-solo-para-desarrollo-local'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'dev-jwt-secret-key-solo-para-desarrollo-local'

    # Base de datos: PostgreSQL en Docker Compose (localhost)
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql://admin:password@localhost:5432/adopciones_db'

    # Mostrar queries SQL en desarrollo para debugging
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """
    Configuración para entorno de producción.

    Características:
    - DEBUG desactivado (seguridad)
    - Base de datos PostgreSQL indicada en DATABASE_URL
    - SQLAlchemy ECHO desactivado (no contaminar logs)
    - SECRET_KEY, JWT_SECRET_KEY y DATABASE_URL obligatorias
    - Swagger desactivado
    """

    DEBUG = False
    TESTING = False

    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')

    # En producción no mostrar queries SQL
    SQLALCHEMY_ECHO = False

    # Cookies solo por HTTPS
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    # No publicar la documentación interactiva de la API
    API_DOCS_ENABLED = False

    # Variables que deben venir del entorno
    REQUIRED_SETTINGS = ('SECRET_KEY', 'JWT_SECRET_KEY', 'SQLALCHEMY_DATABASE_URI')
    MIN_SECRET_BYTES = 32

    @classmethod
    def init_app(cls, app):
        """
        Validaciones adicionales al iniciar la app en producción.

        Args:
            app: Instancia de Flask

        Raises:
            RuntimeError: Si falta alguna variable obligatoria
        """
        super().init_app(app)

        faltan = [k for k in cls.REQUIRED_SETTINGS if not app.config.get(k)]
        if faltan:
            raise RuntimeError(
                'Faltan variables de entorno obligatorias en producción: '
                + ', '.join(faltan)
            )

        # HS256 necesita una clave de al menos 32 bytes (RFC 7518, 3.2)
        for clave in ('SECRET_KEY', 'JWT_SECRET_KEY'):
            if len(app.config[clave].encode()) < cls.MIN_SECRET_BYTES:
                raise RuntimeError(
                    f'{clave} debe tener al menos {cls.MIN_SECRET_BYTES} bytes. '
                    'Genera una con: python -c "import secrets; print(secrets.token_hex(32))"'
                )


class TestingConfig(Config):
    """
    Configuración para tests unitarios con pytest.

    Características:
    - TESTING activado (deshabilita CSRF, etc.)
    - Base de datos SQLite en memoria (rápido, desechable)
    - WTF_CSRF_ENABLED desactivado (facilita tests de formularios)
    """

    DEBUG = False
    TESTING = True

    SECRET_KEY = 'test-secret-key-de-al-menos-32-bytes'
    JWT_SECRET_KEY = 'test-jwt-secret-key-de-al-menos-32-bytes'

    # Base de datos en memoria para tests (SQLite)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'

    # Desactivar CSRF para tests
    WTF_CSRF_ENABLED = False

    # Sin límite de peticiones salvo en los tests que lo activan
    RATELIMIT_ENABLED = False

    # No mostrar queries SQL en tests (ruido en output)
    SQLALCHEMY_ECHO = False


# Diccionario para seleccionar configuración por nombre
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
