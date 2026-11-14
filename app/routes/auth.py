"""
Blueprint de autenticación: registro, login, logout.

Este módulo maneja todas las rutas relacionadas con la autenticación
de usuarios en el sistema.
"""

from urllib.parse import urlparse

from authlib.integrations.base_client.errors import OAuthError
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app import db, oauth, limiter
from app.models import Usuario

# Longitud mínima de contraseña en el registro
PASSWORD_MIN_LENGTH = 8


def limite_login():
    """Límite de intentos de login, leído de la configuración."""
    return current_app.config['RATELIMIT_LOGIN']


def es_redireccion_segura(destino):
    """
    Comprueba que `destino` es una ruta relativa de este sitio.

    Rechaza URLs absolutas y las que el navegador interpreta como otro
    dominio aunque empiecen por '/' (//evil.com, /\\evil.com).
    """
    if not destino or '\\' in destino or not destino.startswith('/') or destino.startswith('//'):
        return False
    partes = urlparse(destino)
    return not partes.scheme and not partes.netloc


# Crear blueprint
bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.route('/registro', methods=['GET', 'POST'])
def registro():
    """
    Ruta de registro de nuevos usuarios.
    
    GET: Muestra el formulario de registro
    POST: Procesa el registro y crea el usuario
    
    Returns:
        Template renderizado o redirección
    """
    # Si el usuario ya está autenticado, redirigir al inicio
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Obtener datos del formulario
        email = request.form.get('email', '').strip().lower()
        nombre = request.form.get('nombre', '').strip()
        apellidos = request.form.get('apellidos', '').strip()
        telefono = request.form.get('telefono', '').strip()
        direccion = request.form.get('direccion', '').strip()
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        # Validaciones
        if not email or not nombre or not password:
            flash('Email, nombre y contraseña son obligatorios.', 'danger')
            return render_template('auth/registro.html')
        
        if password != password_confirm:
            flash('Las contraseñas no coinciden.', 'danger')
            return render_template('auth/registro.html')
        
        if len(password) < PASSWORD_MIN_LENGTH:
            flash(f'La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.', 'danger')
            return render_template('auth/registro.html')
        
        # Verificar si el email ya existe
        if Usuario.query.filter_by(email=email).first():
            flash('El email ya está registrado. Intenta iniciar sesión.', 'warning')
            return redirect(url_for('auth.login'))
        
        # Crear nuevo usuario
        try:
            nuevo_usuario = Usuario(
                email=email,
                nombre=nombre,
                password=password,
                rol='adoptante'  # Por defecto todos son adoptantes
            )
            nuevo_usuario.apellidos = apellidos
            nuevo_usuario.telefono = telefono
            nuevo_usuario.direccion = direccion
            
            db.session.add(nuevo_usuario)
            db.session.commit()
            
            flash('¡Registro exitoso! Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear usuario: {str(e)}', 'danger')
            return render_template('auth/registro.html')
    
    # GET: Mostrar formulario
    return render_template('auth/registro.html')


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(limite_login, methods=['POST'])
def login():
    """
    Ruta de inicio de sesión.
    
    GET: Muestra el formulario de login
    POST: Autentica al usuario
    
    Returns:
        Template renderizado o redirección
    """
    # Si el usuario ya está autenticado, redirigir al inicio
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = request.form.get('remember', False)  # Checkbox "Recordarme"
        
        # Validaciones básicas
        if not email or not password:
            flash('Email y contraseña son obligatorios.', 'danger')
            return render_template('auth/login.html')
        
        # Buscar usuario por email
        usuario = Usuario.query.filter_by(email=email).first()
        
        # Verificar credenciales
        if usuario is None or not usuario.check_password(password):
            flash('Email o contraseña incorrectos.', 'danger')
            return render_template('auth/login.html')
        
        # Verificar si la cuenta está activa
        if not usuario.activo:
            flash('Tu cuenta ha sido desactivada. Contacta al administrador.', 'warning')
            return render_template('auth/login.html')
        
        # Login exitoso
        login_user(usuario, remember=remember)
        flash(f'¡Bienvenido, {usuario.nombre}!', 'success')
        
        # Redirigir a la página que intentaba acceder o al inicio
        next_page = request.args.get('next')
        if es_redireccion_segura(next_page):
            return redirect(next_page)
        else:
            return redirect(url_for('index'))
    
    # GET: Mostrar formulario
    return render_template('auth/login.html')


@bp.route('/logout', methods=['POST'])
@login_required
def logout():
    """
    Ruta de cierre de sesión.
    
    Cierra la sesión del usuario actual y redirige al inicio.
    
    Returns:
        Redirección a la página de inicio
    """
    logout_user()
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('index'))


@bp.route('/google')
def google_login():
    """Inicia el flujo OAuth con Google"""
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@bp.route('/google/callback')
def google_callback():
    """Callback de Google OAuth"""
    try:
        token = oauth.google.authorize_access_token()
    except OAuthError:
        # El usuario canceló el consentimiento o el state no coincide
        flash('No se pudo completar el inicio de sesión con Google.', 'danger')
        return redirect(url_for('auth.login'))

    user_info = token.get('userinfo')

    if not user_info or not user_info.get('email'):
        flash('Error al obtener información de Google', 'danger')
        return redirect(url_for('auth.login'))

    # Solo se confía en el email si Google lo ha verificado: se usa para
    # enlazar la cuenta de Google con una cuenta local existente
    if not user_info.get('email_verified'):
        flash('Tu email de Google no está verificado.', 'danger')
        return redirect(url_for('auth.login'))

    email = user_info['email'].strip().lower()

    # Buscar primero por la identidad de Google y después por email
    usuario = Usuario.query.filter_by(oauth_id=user_info['sub']).first() or \
        Usuario.query.filter_by(email=email).first()

    if usuario:
        if not usuario.activo:
            flash('Tu cuenta ha sido desactivada. Contacta al administrador.', 'warning')
            return redirect(url_for('auth.login'))

        # Usuario existente - enlazar con Google si aún no lo está
        if not usuario.oauth_id:
            usuario.oauth_id = user_info['sub']
            usuario.oauth_provider = 'google'
            db.session.commit()
    else:
        # Crear nuevo usuario
        usuario = Usuario(
            email=email,
            nombre=user_info.get('given_name', email.split('@')[0]),
            apellidos=user_info.get('family_name', ''),
            oauth_provider='google',
            oauth_id=user_info['sub']
        )
        db.session.add(usuario)
        db.session.commit()

    login_user(usuario)
    flash(f'Bienvenido, {usuario.nombre}!', 'success')
    return redirect(url_for('mascotas.catalogo'))
