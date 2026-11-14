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
from flask import Flask, abort, flash, redirect, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

from config import config

# Inicializar extensiones (sin vincular a app todavía)
db = SQLAlchemy()
mail = Mail()
login_manager = LoginManager()
oauth = OAuth()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


# Content Security Policy: solo scripts propios y de jsDelivr (Bootstrap).
# 'unsafe-inline' en estilos se mantiene por los atributos style de las plantillas.
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' https: data:; "
    "font-src 'self' https://cdn.jsdelivr.net; "
    "object-src 'none'; "
    "base-uri 'self'; "
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

    # Inicializar extensiones con la app
    db.init_app(app)
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
    from app.routes import auth, mascotas, solicitudes
    from app.routes.api import bp as api_bp
    app.register_blueprint(auth.bp)
    app.register_blueprint(mascotas.bp)
    app.register_blueprint(solicitudes.bp)
    app.register_blueprint(api_bp)

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

    # Crear tablas en la base de datos si no existen
    with app.app_context():
        db.create_all()

    # Error handler para archivos demasiado grandes
    @app.errorhandler(413)
    def file_too_large(e):
        flash('El archivo es demasiado grande. Máximo 5MB.', 'danger')
        # 302 normal: el navegador no sigue un Location con estado 413
        return redirect(request.url)


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
