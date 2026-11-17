"""
Blueprint de rutas para la gestión de mascotas.

Este módulo maneja:
- Catálogo público de mascotas disponibles (sin autenticación)
- Vista detalle de cada mascota
- Panel de administración con CRUD completo (solo admin)
"""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import adopciones, db, fotos
from app.adopciones import consulta_mascota_bloqueada
from app.decorators import admin_required
from app.models import Mascota
from app.routes.auth import MENSAJE_REVISAR

# Crear blueprint
bp = Blueprint('mascotas', __name__, url_prefix='/mascotas')

# Estados por los que se puede filtrar la lista del panel admin
ESTADOS_FILTRABLES = ('disponible', 'adoptado')

# Campos del formulario de mascota del panel admin
CAMPOS_TEXTO_MASCOTA = ('nombre', 'especie', 'raza', 'edad_aprox', 'sexo', 'tamano', 'descripcion', 'foto_url')
CASILLAS_MASCOTA = ('vacunado', 'esterilizado')

# Rango de edad aproximada admitido (años)
EDAD_MINIMA = 0
EDAD_MAXIMA = 30

# Margen para el resto de campos del formulario dentro de MAX_CONTENT_LENGTH
MARGEN_PETICION_FOTO = 64 * 1024


@bp.route('/')
@bp.route('/catalogo')
def catalogo():
    """
    Catálogo público de mascotas disponibles.

    Muestra todas las mascotas en estado 'disponible'.
    Permite filtrar por especie, tamaño, sexo y edad.
    Accesible sin autenticación.
    """
    # Obtener parámetros de filtrado
    especie_filtro = request.args.get('especie', '')
    tamano_filtro = request.args.get('tamano', '')
    sexo_filtro = request.args.get('sexo', '')
    edad_filtro = request.args.get('edad', '')

    # Query base: solo mascotas disponibles
    query = Mascota.query.filter_by(estado='disponible')

    # Aplicar filtros si existen
    if especie_filtro:
        query = query.filter(Mascota.especie == especie_filtro)

    if tamano_filtro:
        query = query.filter(Mascota.tamano == tamano_filtro)

    if sexo_filtro:
        query = query.filter(Mascota.sexo == sexo_filtro)

    if edad_filtro:
        try:
            edad_max = int(edad_filtro)
            query = query.filter(Mascota.edad_aprox <= edad_max)
        except ValueError:
            pass  # Ignorar si el filtro de edad no es válido

    # Ordenar por fecha de ingreso (más recientes primero)
    pagina = query.order_by(Mascota.fecha_ingreso.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=current_app.config['CATALOGO_POR_PAGINA'],
        error_out=False,
    )

    # Obtener lista de especies únicas disponibles
    especies_disponibles = db.session.query(Mascota.especie)\
        .filter_by(estado='disponible')\
        .distinct()\
        .order_by(Mascota.especie)\
        .all()
    especies_disponibles = [esp[0] for esp in especies_disponibles if esp[0]]

    return render_template('mascotas/catalogo.html',
                         mascotas=pagina.items,
                         pagina=pagina,
                         pendientes=adopciones.pendientes_por_mascota([m.id for m in pagina.items]),
                         especies_disponibles=especies_disponibles,
                         especie_filtro=especie_filtro,
                         tamano_filtro=tamano_filtro,
                         sexo_filtro=sexo_filtro,
                         edad_filtro=edad_filtro)


@bp.route('/<int:mascota_id>')
def detalle(mascota_id):
    """
    Vista detalle de una mascota específica.

    Muestra toda la información de la mascota.
    Accesible sin autenticación.

    Args:
        mascota_id (int): ID de la mascota
    """
    mascota = db.get_or_404(Mascota, mascota_id)
    pendientes = adopciones.pendientes_por_mascota([mascota.id]).get(mascota.id, 0)
    return render_template('mascotas/detalle.html', mascota=mascota, pendientes=pendientes)


# ==================== RUTAS DE ADMINISTRACIÓN ====================
# Requieren autenticación y rol de admin

@bp.route('/admin')
@login_required
@admin_required
def admin_lista():
    """
    Panel de administración: lista de todas las mascotas.

    Muestra todas las mascotas (disponibles y adoptadas).
    Solo accesible para administradores.
    Permite ordenar por cualquier columna.
    """

    # Obtener parámetros de URL
    estado_filtro = request.args.get('estado', '')
    if estado_filtro not in ESTADOS_FILTRABLES:
        estado_filtro = ''  # en_proceso ya no lo usa el flujo (ADR-0004)
    orden_campo = request.args.get('orden', 'id')  # Campo por el cual ordenar
    orden_dir = request.args.get('dir', 'asc')  # Dirección: asc o desc

    # Query base
    query = Mascota.query

    # Aplicar filtro de estado si existe
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)

    # Mapeo de nombres de columnas a atributos del modelo
    columnas_validas = {
        'id': Mascota.id,
        'nombre': Mascota.nombre,
        'especie': Mascota.especie,
        'raza': Mascota.raza,
        'edad': Mascota.edad_aprox,
        'tamano': Mascota.tamano,
        'estado': Mascota.estado
    }

    # Aplicar ordenamiento
    if orden_campo in columnas_validas:
        columna = columnas_validas[orden_campo]
        if orden_dir == 'desc':
            query = query.order_by(columna.desc())
        else:
            query = query.order_by(columna.asc())
    else:
        # Orden por defecto
        query = query.order_by(Mascota.id.asc())

    pagina = query.paginate(
        page=request.args.get('page', 1, type=int),
        per_page=current_app.config['ADMIN_POR_PAGINA'],
        error_out=False,
    )

    return render_template('mascotas/admin/lista.html',
                         mascotas=pagina.items,
                         pagina=pagina,
                         estado_filtro=estado_filtro,
                         orden_campo=orden_campo,
                         orden_dir=orden_dir)


@bp.route('/admin/nueva', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_nueva():
    """
    Crear una nueva mascota.

    GET: Muestra formulario de creación
    POST: Procesa y guarda la nueva mascota
    Solo accesible para administradores.
    """
    if request.method == 'POST':
        valores = _leer_formulario_mascota()
        errores, datos = _validar_mascota(valores, request.files.get('foto'))
        if errores:
            flash(MENSAJE_REVISAR, 'danger')
            return _formulario_nueva(valores, errores, 400)

        nueva_mascota = Mascota(**datos, estado='disponible')
        try:
            db.session.add(nueva_mascota)
            db.session.commit()
            flash(f'Mascota "{nueva_mascota.nombre}" creada exitosamente.', 'success')
            return redirect(url_for('mascotas.admin_lista'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al crear la mascota')
            flash('No se pudo crear la mascota. Inténtalo de nuevo.', 'danger')
            return _formulario_nueva(valores)

    # GET: Mostrar formulario vacío
    return _formulario_nueva()


def _leer_formulario_mascota():
    """Valores enviados en el formulario de mascota (texto sin espacios alrededor)."""
    valores = {campo: request.form.get(campo, '').strip() for campo in CAMPOS_TEXTO_MASCOTA}
    valores.update({campo: request.form.get(campo) == 'on' for campo in CASILLAS_MASCOTA})
    return valores


def _valores_de_mascota(mascota):
    """Valores del formulario a partir de la mascota guardada (los campos NULL, vacíos)."""
    valores = {campo: getattr(mascota, campo) or '' for campo in CAMPOS_TEXTO_MASCOTA}
    valores['edad_aprox'] = '' if mascota.edad_aprox is None else str(mascota.edad_aprox)
    valores.update({campo: bool(getattr(mascota, campo)) for campo in CASILLAS_MASCOTA})
    return valores


def _validar_mascota(valores, foto):
    """
    Valida el formulario de mascota.

    La foto subida tiene prioridad sobre la URL, que entonces no se valida.
    Si todo lo demás es válido, sube la foto: su formato se comprueba al
    subirla, así que no queda ninguna subida huérfana por un error en otro
    campo.

    Returns:
        tuple: (errores, datos). `errores` es un dict campo → mensaje (el
        contrato `valores`/`errores`); `datos`, los atributos de la mascota,
        solo válidos si no hay errores.
    """
    errores = {}
    if len(valores['nombre']) < 2:
        errores['nombre'] = 'El nombre debe tener al menos 2 caracteres.'
    # Se valida la especie tal como la guardará el modelo: su validador lanza
    # ValueError si queda vacía o no cabe (p. ej. solo invisibles, o «ß» → «Ss»)
    especie = Mascota.normalizar_especie(valores['especie'])
    if len(especie) < 2:
        errores['especie'] = 'La especie es obligatoria.'
    elif len(especie) > Mascota.LONGITUD_ESPECIE:
        errores['especie'] = f'La especie no puede superar {Mascota.LONGITUD_ESPECIE} caracteres.'
    if len(valores['descripcion']) < 10:
        errores['descripcion'] = 'La descripción debe tener al menos 10 caracteres.'

    edad = None
    if valores['edad_aprox']:
        try:
            edad = int(valores['edad_aprox'])
        except ValueError:
            errores['edad_aprox'] = 'La edad debe ser un número válido.'
        else:
            if not EDAD_MINIMA <= edad <= EDAD_MAXIMA:
                errores['edad_aprox'] = f'La edad debe estar entre {EDAD_MINIMA} y {EDAD_MAXIMA} años.'

    hay_archivo = bool(foto and foto.filename)
    foto_url = valores['foto_url'] or None
    if not hay_archivo and foto_url and not fotos.es_url_imagen_valida(foto_url):
        errores['foto_url'] = 'La URL de la foto debe empezar por https://'

    if not errores and hay_archivo:
        try:
            foto_url = fotos.guardar_foto(foto)
        except fotos.ErrorAlmacenamiento as error:
            errores['foto'] = error.mensaje

    datos = {
        'nombre': valores['nombre'],
        'especie': especie,
        'raza': valores['raza'] or None,
        'edad_aprox': edad,
        'sexo': valores['sexo'] or None,
        'tamano': valores['tamano'] or None,
        'descripcion': valores['descripcion'],
        'foto_url': foto_url,
        'vacunado': valores['vacunado'],
        'esterilizado': valores['esterilizado'],
    }
    return errores, datos


def _contexto_formulario(valores, errores):
    """
    Contexto común del formulario de mascota.

    `foto_descartada` avisa de que hay que volver a elegir la foto: el
    navegador no puede conservar un archivo al volver a pintar el formulario.
    `max_bytes_foto` deja margen bajo MAX_CONTENT_LENGTH, que limita la
    petición entera y no solo el archivo.
    """
    foto = request.files.get('foto')
    limite = current_app.config['MAX_CONTENT_LENGTH']
    return {
        'valores': valores,
        'errores': errores or {},
        'foto_descartada': bool(foto and foto.filename),
        'max_bytes_foto': limite - MARGEN_PETICION_FOTO,
        'max_mb_foto': limite // (1024 * 1024),
    }


def _formulario_nueva(valores=None, errores=None, codigo=200):
    """Formulario de alta con los valores enviados y los errores por campo."""
    return render_template('mascotas/admin/form.html', mascota=None,
                           **_contexto_formulario(valores or {}, errores)), codigo


def _formulario_edicion(mascota, valores=None, errores=None, codigo=200):
    """
    Formulario de edición con las acciones de estado que permite la regla de
    adopción. Los valores enviados tienen prioridad sobre los guardados.
    """
    return render_template(
        'mascotas/admin/form.html',
        mascota=mascota,
        **_contexto_formulario(valores or _valores_de_mascota(mascota), errores),
        pendientes=adopciones.pendientes_por_mascota([mascota.id]).get(mascota.id, 0),
        puede_volver_a_disponible=adopciones.puede_volver_a_disponible(mascota),
    ), codigo


@bp.route('/admin/editar/<int:mascota_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_editar(mascota_id):
    """
    Editar una mascota existente.

    GET: Muestra formulario con datos actuales
    POST: Procesa y guarda los cambios. El estado no se edita aquí: lo
    cambian el flujo de solicitudes o las acciones de estado (ADR-0004).
    Solo accesible para administradores.

    Args:
        mascota_id (int): ID de la mascota a editar
    """

    # Obtener la mascota
    mascota = db.get_or_404(Mascota, mascota_id)

    if request.method == 'POST':
        valores = _leer_formulario_mascota()
        errores, datos = _validar_mascota(valores, request.files.get('foto'))
        if errores:
            flash(MENSAJE_REVISAR, 'danger')
            return _formulario_edicion(mascota, valores, errores, 400)

        # Una foto nueva (subida o URL distinta) sustituye a la anterior
        if datos['foto_url'] != mascota.foto_url:
            fotos.borrar_foto(mascota.foto_url)

        for atributo, valor in datos.items():
            setattr(mascota, atributo, valor)

        try:
            db.session.commit()
            flash(f'Mascota "{datos["nombre"]}" actualizada exitosamente.', 'success')
            return redirect(url_for('mascotas.admin_lista'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al actualizar la mascota')
            flash('No se pudo actualizar la mascota. Inténtalo de nuevo.', 'danger')
            return _formulario_edicion(mascota, valores)

    # GET: Mostrar formulario con datos actuales
    return _formulario_edicion(mascota)


@bp.route('/admin/eliminar/<int:mascota_id>', methods=['POST'])
@login_required
@admin_required
def admin_eliminar(mascota_id):
    """
    Eliminar una mascota.

    Solo accesible para administradores.
    Solo se permite eliminar si no tiene solicitudes asociadas.

    Args:
        mascota_id (int): ID de la mascota a eliminar
    """

    # Bloquear la fila: crear_solicitud también la bloquea, así que no puede
    # entrar una solicitud entre la comprobación y el borrado
    mascota = db.session.execute(consulta_mascota_bloqueada(mascota_id)).scalar_one_or_none()
    if mascota is None:
        abort(404)

    # Verificar si tiene solicitudes asociadas
    if mascota.solicitudes.count() > 0:
        db.session.rollback()
        flash(f'No se puede eliminar "{mascota.nombre}" porque tiene solicitudes de adopción asociadas.', 'danger')
        return redirect(url_for('mascotas.admin_lista'))

    try:
        nombre = mascota.nombre
        fotos.borrar_foto(mascota.foto_url)
        db.session.delete(mascota)
        db.session.commit()
        flash(f'Mascota "{nombre}" eliminada exitosamente.', 'success')
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Error al eliminar la mascota')
        flash('No se pudo eliminar la mascota. Inténtalo de nuevo.', 'danger')

    return redirect(url_for('mascotas.admin_lista'))


@bp.route('/admin/adoptada-fuera/<int:mascota_id>', methods=['POST'])
@login_required
@admin_required
def admin_adoptar_fuera(mascota_id):
    """
    Marca la mascota como adoptada fuera del portal y rechaza sus pendientes.

    Args:
        mascota_id (int): ID de la mascota
    """
    mascota = db.get_or_404(Mascota, mascota_id)
    try:
        adopciones.adoptar_fuera_del_portal(mascota, current_user.id)
    except adopciones.MascotaNoEncontrada:
        abort(404)
    except adopciones.ErrorAdopcion as error:
        flash(error.mensaje, 'warning')
    else:
        flash(f'Mascota "{mascota.nombre}" marcada como adoptada fuera del portal.', 'success')
    return redirect(url_for('mascotas.admin_editar', mascota_id=mascota_id))


@bp.route('/admin/volver-a-disponible/<int:mascota_id>', methods=['POST'])
@login_required
@admin_required
def admin_volver_a_disponible(mascota_id):
    """
    Deshace una adopción fuera del portal: la mascota vuelve al catálogo.

    Args:
        mascota_id (int): ID de la mascota
    """
    mascota = db.get_or_404(Mascota, mascota_id)
    try:
        adopciones.volver_a_disponible(mascota)
    except adopciones.MascotaNoEncontrada:
        abort(404)
    except adopciones.ErrorAdopcion as error:
        flash(error.mensaje, 'warning')
    else:
        flash(f'Mascota "{mascota.nombre}" vuelve a estar disponible.', 'success')
    return redirect(url_for('mascotas.admin_editar', mascota_id=mascota_id))
