"""
Application Factory de Flask.

Este módulo implementa el patrón Application Factory para crear instancias
de la aplicación Flask con diferentes configuraciones.

Ventajas del Application Factory:
- Permite crear múltiples instancias de la app (testing, desarrollo, producción)
- Facilita los tests unitarios
- Evita imports circulares
- Permite configurar extensiones antes de crear la app

Uso:
    from app import create_app
    app = create_app('development')
    app.run()
"""

from authlib.integrations.flask_client import OAuth
from flask import Flask, abort, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text
from werkzeug.middleware.proxy_fix import ProxyFix

from config import config

# Inicializar extensiones (sin vincular a app todavía)
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()
login_manager = LoginManager()
oauth = OAuth()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


# Content Security Policy: scripts, estilos y fuentes solo propios. Bootstrap
# se sirve desde app/static/vendor/ (ADR-0001) y las plantillas no llevan
# estilos en línea (tests/test_plantillas.py), así que no hace falta
# 'unsafe-inline'. Bootstrap JS aplica estilos con el CSSOM, que la CSP permite.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' https: data:; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def create_app(config_name='default'):
    """
    Application Factory: Crea y configura una instancia de Flask.

    Este patrón permite crear múltiples instancias de la aplicación con
    diferentes configuraciones (desarrollo, testing, producción).

    Args:
        config_name (str): Nombre de la configuración a usar.
                           Opciones: 'development', 'production', 'testing', 'default'

    Returns:
        Flask: Instancia configurada de la aplicación Flask
    """

    # Crear instancia de Flask
    app = Flask(__name__)

    # Cargar configuración desde config.py
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)

    # Detrás de un proxy inverso (balanceador, Nginx, plataforma PaaS) la IP
    # del cliente y el esquema https llegan en cabeceras X-Forwarded-*. Solo se
    # confía en ellas si se indica cuántos proxies hay delante: si no, un
    # cliente podría falsearlas para saltarse el límite de intentos de login.
    proxies = app.config['TRUSTED_PROXIES']
    if proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxies, x_proto=proxies, x_host=proxies)

    # Inicializar extensiones con la app
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Configurar Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'  # Ruta de login
    login_manager.login_message = 'Por favor, inicia sesión para acceder a esta página.'
    login_manager.login_message_category = 'info'

    # Configurar OAuth
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

    # Importar modelos
    from app import models

    # User loader para Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        """
        Callback requerido por Flask-Login para cargar un usuario.

        Args:
            user_id (str): ID del usuario como string

        Returns:
            Usuario: Instancia del usuario o None
        """
        usuario = db.session.get(models.Usuario, int(user_id))
        # Una cuenta desactivada pierde también las sesiones ya abiertas
        if usuario is None or not usuario.activo:
            return None
        return usuario

    # Registrar blueprints (rutas)
    from app.routes import auth, fotos, mascotas, solicitudes
    from app.routes.api import bp as api_bp
    app.register_blueprint(auth.bp)
    app.register_blueprint(fotos.bp)
    app.register_blueprint(mascotas.bp)
    app.register_blueprint(solicitudes.bp)
    app.register_blueprint(api_bp)

    # Respuestas del cuestionario con su etiqueta legible en las plantillas
    from app.cuestionario import respuesta_legible
    app.add_template_filter(respuesta_legible)
    # srcset de las variantes de una foto propia ('' para las URLs externas)
    from app.fotos import srcset_foto
    app.add_template_filter(srcset_foto)
    # Etiqueta legible de un estado (macro badge_estado)
    from app.models import AVISO_PENDIENTES, etiqueta_estado
    app.add_template_global(etiqueta_estado)
    app.add_template_global(AVISO_PENDIENTES, 'AVISO_PENDIENTES')
    # Enlaces de orden de la macro tabla y href admitidos en las macros
    from app.enlaces import url_orden, url_pagina, url_segura
    app.add_template_global(url_orden)
    app.add_template_global(url_pagina)
    app.add_template_filter(url_segura)
    # Marca de la protectora y usuario de la navegación (base.html)
    from app.contexto import registrar_contexto
    registrar_contexto(app)

    # La API se autentica con JWT en la cabecera Authorization (no con cookies),
    # por lo que no necesita token CSRF
    csrf.exempt(api_bp)

    # Cabeceras de seguridad en todas las respuestas
    @app.after_request
    def cabeceras_seguridad(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        # Swagger UI usa scripts inline, así que no se le aplica la CSP
        if request.endpoint != 'api.doc':
            response.headers.setdefault('Content-Security-Policy', CSP)
        return response

    # Desactivar Swagger cuando la configuración lo indique (producción)
    if not app.config['API_DOCS_ENABLED']:
        @app.before_request
        def ocultar_docs_api():
            if request.endpoint in ('api.doc', 'api.specs'):
                abort(404)

    # Comandos CLI (flask crear-admin)
    from app.cli import register_commands
    register_commands(app)

    # El esquema de la base de datos se gestiona con migraciones:
    # flask --app run db upgrade

    # Páginas de error de la web (la API conserva su formato JSON)
    from app.errores import registrar_manejadores_errores
    registrar_manejadores_errores(app)

    # Comprobación de salud para el orquestador o el balanceador
    @app.route('/health')
    @limiter.exempt
    def health():
        try:
            db.session.execute(text('SELECT 1'))
        except Exception:
            app.logger.exception('Health check: la base de datos no responde')
            return {'status': 'error', 'database': 'unreachable'}, 503
        return {'status': 'ok'}, 200

    # Ruta de inicio
    @app.route('/')
    def index():
        """
        Página de inicio del portal.

        Muestra estadísticas, mascotas destacadas y el proceso de adopción.
        """
        from app.models import Mascota, Usuario

        # Obtener estadísticas
        total_mascotas = Mascota.query.filter_by(estado='disponible').count()
        total_adoptadas = Mascota.query.filter_by(estado='adoptado').count()
        total_usuarios = Usuario.query.filter_by(rol='adoptante').count()

        # Obtener 3 mascotas destacadas (las más recientes disponibles)
        mascotas_destacadas = Mascota.query.filter_by(estado='disponible')\
            .order_by(Mascota.id.desc())\
            .limit(3)\
            .all()

        return render_template('index.html',
                             total_mascotas=total_mascotas,
                             total_adoptadas=total_adoptadas,
                             total_usuarios=total_usuarios,
                             mascotas_destacadas=mascotas_destacadas)

    return app
