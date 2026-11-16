"""
Blueprint de autenticación: registro, login, logout.

Este módulo maneja todas las rutas relacionadas con la autenticación
de usuarios en el sistema.
"""

from urllib.parse import urlparse

from authlib.integrations.base_client.errors import OAuthError
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db, limiter, oauth
from app.models import Usuario

# Longitud mínima de contraseña en el registro
PASSWORD_MIN_LENGTH = 8


def limite_login():
    """Límite de intentos de login, leído de la configuración."""
    return current_app.config['RATELIMIT_LOGIN']


def limite_registro():
    """Límite de registros, leído de la configuración (el registro inicia sesión)."""
    return current_app.config['RATELIMIT_REGISTRO']


def es_redireccion_segura(destino):
    """
    Comprueba que `destino` es una ruta relativa de este sitio.

    Rechaza URLs absolutas y las que el navegador interpreta como otro
    dominio aunque empiecen por '/' (//evil.com, /\\evil.com).
    """
    if not destino or '\\' in destino or not destino.startswith('/') or destino.startswith('//'):
        return False
    # Los navegadores descartan tabuladores y saltos de línea de las URLs:
    # «/\t/evil.com» acabaría siendo «//evil.com». Se rechaza cualquier
    # espacio o carácter no imprimible (controles C0, DEL...)
    if any(caracter.isspace() or not caracter.isprintable() for caracter in destino):
        return False
    partes = urlparse(destino)
    return not partes.scheme and not partes.netloc


def next_seguro():
    """
    Devuelve el `next` de la petición (formulario o query) si es una ruta
    local segura, o None en caso contrario.
    """
    destino = request.form.get('next') or request.args.get('next')
    return destino if es_redireccion_segura(destino) else None


def redirigir_tras_login(destino, por_defecto='index'):
    """Redirige a `destino` si es seguro o, si no, a la vista `por_defecto`."""
    if es_redireccion_segura(destino):
        return redirect(destino)
    return redirect(url_for(por_defecto))


# Clave de la sesión donde se guarda `next` durante el login con Google
SESION_NEXT_GOOGLE = 'next_google'

# Mensaje general cuando el formulario tiene errores en sus campos
MENSAJE_REVISAR = 'Revisa los campos marcados.'

# Campos del registro que se vuelven a mostrar tras un error (nunca la contraseña)
CAMPOS_REGISTRO = ('email', 'nombre', 'apellidos', 'telefono', 'direccion')


# Crear blueprint
bp = Blueprint('auth', __name__, url_prefix='/auth')


def mostrar_formulario(plantilla, valores=None, errores=None, next_page=None, codigo=200):
    """
    Renderiza un formulario de autenticación con los valores enviados, los
    errores por campo (contrato `valores`/`errores`) y el `next` seguro.
    """
    return render_template(plantilla, valores=valores or {}, errores=errores or {},
                           next=next_page), codigo


def validar_registro(valores, password, password_confirm):
    """Devuelve un dict campo → mensaje con los errores del registro."""
    errores = {}
    if not valores['email']:
        errores['email'] = 'El email es obligatorio.'
    if not valores['nombre']:
        errores['nombre'] = 'El nombre es obligatorio.'
    if not password:
        errores['password'] = 'La contraseña es obligatoria.'
    elif len(password) < PASSWORD_MIN_LENGTH:
        errores['password'] = f'La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.'
    if password and password != password_confirm:
        errores['password_confirm'] = 'Las contraseñas no coinciden.'
    return errores


@bp.route('/registro', methods=['GET', 'POST'])
@limiter.limit(limite_registro, methods=['POST'])
def registro():
    """
    Ruta de registro de nuevos usuarios.

    GET: Muestra el formulario de registro
    POST: Crea el usuario, inicia su sesión y redirige a `next` (si es
    seguro) o al inicio. Ante un error de validación vuelve a mostrar el
    formulario con los datos enviados (salvo las contraseñas) y responde 400.

    Returns:
        Template renderizado o redirección
    """
    # Si el usuario ya está autenticado, redirigir al inicio
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    next_page = next_seguro()

    if request.method == 'POST':
        # Obtener datos del formulario
        valores = {campo: request.form.get(campo, '').strip() for campo in CAMPOS_REGISTRO}
        valores['email'] = valores['email'].lower()
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        errores = validar_registro(valores, password, password_confirm)
        if errores:
            flash(MENSAJE_REVISAR, 'danger')
            return mostrar_formulario('auth/registro.html', valores, errores, next_page, 400)

        # Verificar si el email ya existe
        if Usuario.query.filter_by(email=valores['email']).first():
            flash('El email ya está registrado. Intenta iniciar sesión.', 'warning')
            return redirect(url_for('auth.login', next=next_page))

        # Crear nuevo usuario
        try:
            nuevo_usuario = Usuario(
                email=valores['email'],
                nombre=valores['nombre'],
                password=password,
                rol='adoptante'  # Por defecto todos son adoptantes
            )
            nuevo_usuario.apellidos = valores['apellidos']
            nuevo_usuario.telefono = valores['telefono']
            nuevo_usuario.direccion = valores['direccion']

            db.session.add(nuevo_usuario)
            db.session.commit()

        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al crear usuario')
            flash('No se pudo crear el usuario. Inténtalo de nuevo.', 'danger')
            return mostrar_formulario('auth/registro.html', valores, next_page=next_page)

        login_user(nuevo_usuario)
        flash(f'¡Registro exitoso! Bienvenido, {nuevo_usuario.nombre}.', 'success')
        return redirigir_tras_login(next_page)

    # GET: Mostrar formulario
    return mostrar_formulario('auth/registro.html', next_page=next_page)


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(limite_login, methods=['POST'])
def login():
    """
    Ruta de inicio de sesión.

    GET: Muestra el formulario de login. Si la query trae un `next` seguro
    (lo añade login_required), lo guarda en un campo oculto.
    POST: Autentica al usuario y redirige a `next` (si es seguro) o al
    inicio. Si falta el email o la contraseña, vuelve a mostrar el
    formulario con el email y el error de cada campo y responde 400. Con
    credenciales incorrectas o una cuenta desactivada lo muestra de nuevo
    con el email y un mensaje general.

    Returns:
        Template renderizado o redirección
    """
    # Si el usuario ya está autenticado, redirigir al inicio
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    # `next` llega en la query (login_required) y viaja en un campo oculto
    next_page = next_seguro()

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        remember = request.form.get('remember', False)  # Checkbox "Recordarme"
        valores = {'email': email}

        # Validaciones básicas
        errores = {}
        if not email:
            errores['email'] = 'El email es obligatorio.'
        if not password:
            errores['password'] = 'La contraseña es obligatoria.'
        if errores:
            flash(MENSAJE_REVISAR, 'danger')
            return mostrar_formulario('auth/login.html', valores, errores, next_page, 400)

        # Buscar usuario por email
        usuario = Usuario.query.filter_by(email=email).first()

        # Verificar credenciales (mensaje común: no revela si el email existe)
        if usuario is None or not usuario.check_password(password):
            flash('Email o contraseña incorrectos.', 'danger')
            return mostrar_formulario('auth/login.html', valores, next_page=next_page)

        # Verificar si la cuenta está activa
        if not usuario.activo:
            flash('Tu cuenta ha sido desactivada. Contacta al administrador.', 'warning')
            return mostrar_formulario('auth/login.html', valores, next_page=next_page)

        # Login exitoso
        login_user(usuario, remember=remember)
        flash(f'¡Bienvenido, {usuario.nombre}!', 'success')

        # Redirigir a la página que intentaba acceder o al inicio
        return redirigir_tras_login(next_page)

    # GET: Mostrar formulario
    return mostrar_formulario('auth/login.html', next_page=next_page)


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
    """Inicia el flujo OAuth con Google y guarda `next` (si es seguro) en la sesión."""
    next_page = next_seguro()
    if next_page:
        session[SESION_NEXT_GOOGLE] = next_page
    else:
        session.pop(SESION_NEXT_GOOGLE, None)
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@bp.route('/google/callback')
def google_callback():
    """Callback de Google OAuth"""
    # `next` se usa una sola vez; se revalida por si la sesión es antigua
    next_page = session.pop(SESION_NEXT_GOOGLE, None)
    if not es_redireccion_segura(next_page):
        next_page = None

    try:
        token = oauth.google.authorize_access_token()
    except OAuthError:
        # El usuario canceló el consentimiento o el state no coincide
        flash('No se pudo completar el inicio de sesión con Google.', 'danger')
        return redirect(url_for('auth.login', next=next_page))

    user_info = token.get('userinfo')

    if not user_info or not user_info.get('email'):
        flash('Error al obtener información de Google', 'danger')
        return redirect(url_for('auth.login', next=next_page))

    # Solo se confía en el email si Google lo ha verificado: se usa para
    # enlazar la cuenta de Google con una cuenta local existente
    if not user_info.get('email_verified'):
        flash('Tu email de Google no está verificado.', 'danger')
        return redirect(url_for('auth.login', next=next_page))

    email = user_info['email'].strip().lower()

    # Buscar primero por la identidad de Google y después por email
    usuario = Usuario.query.filter_by(oauth_id=user_info['sub']).first() or \
        Usuario.query.filter_by(email=email).first()

    if usuario:
        if not usuario.activo:
            flash('Tu cuenta ha sido desactivada. Contacta al administrador.', 'warning')
            return redirect(url_for('auth.login', next=next_page))

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
    return redirigir_tras_login(next_page, por_defecto='mascotas.catalogo')
