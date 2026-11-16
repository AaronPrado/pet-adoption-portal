"""
Blueprint de rutas para la gestión de mascotas.

Este módulo maneja:
- Catálogo público de mascotas disponibles (sin autenticación)
- Vista detalle de cada mascota
- Panel de administración con CRUD completo (solo admin)
"""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import adopciones, db
from app.decorators import admin_required
from app.models import Mascota
from app.s3 import delete_from_s3, es_url_imagen_valida, upload_to_s3

# Crear blueprint
bp = Blueprint('mascotas', __name__, url_prefix='/mascotas')

# Estados por los que se puede filtrar la lista del panel admin
ESTADOS_FILTRABLES = ('disponible', 'adoptado')


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
        # Obtener datos del formulario
        nombre = request.form.get('nombre', '').strip()
        especie = request.form.get('especie', '').strip()
        raza = request.form.get('raza', '').strip()
        edad_aprox = request.form.get('edad_aprox', '')
        sexo = request.form.get('sexo', '').strip()
        tamano = request.form.get('tamano', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        vacunado = request.form.get('vacunado') == 'on'
        esterilizado = request.form.get('esterilizado') == 'on'

        # Validaciones básicas
        if not nombre or len(nombre) < 2:
            flash('El nombre debe tener al menos 2 caracteres.', 'danger')
            return render_template('mascotas/admin/form.html', mascota=None)

        if not especie or len(especie) < 2:
            flash('La especie es obligatoria.', 'danger')
            return render_template('mascotas/admin/form.html', mascota=None)

        if not descripcion or len(descripcion) < 10:
            flash('La descripción debe tener al menos 10 caracteres.', 'danger')
            return render_template('mascotas/admin/form.html', mascota=None)

        # Manejar foto: prioridad archivo > URL
        foto_url = None
        foto = request.files.get('foto')
        if foto and foto.filename:
            foto_url = upload_to_s3(foto)
            if not foto_url:
                flash('Formato de imagen no permitido', 'danger')
                return redirect(request.url)
        else:
            foto_url = request.form.get('foto_url', '').strip() or None
            if foto_url and not es_url_imagen_valida(foto_url):
                flash('La URL de la foto debe empezar por https://', 'danger')
                return render_template('mascotas/admin/form.html', mascota=None)
        # Convertir edad a entero
        try:
            edad_aprox = int(edad_aprox) if edad_aprox else None
            if edad_aprox is not None and (edad_aprox < 0 or edad_aprox > 30):
                flash('La edad debe estar entre 0 y 30 años.', 'danger')
                return render_template('mascotas/admin/form.html', mascota=None)
        except ValueError:
            flash('La edad debe ser un número válido.', 'danger')
            return render_template('mascotas/admin/form.html', mascota=None)

        # Crear nueva mascota
        nueva_mascota = Mascota(
            nombre=nombre,
            especie=especie,
            descripcion=descripcion,
            raza=raza if raza else None,
            edad_aprox=edad_aprox,
            sexo=sexo if sexo else None,
            tamano=tamano if tamano else None,
            foto_url=foto_url if foto_url else None,
            vacunado=vacunado,
            esterilizado=esterilizado,
            estado='disponible'
        )

        try:
            db.session.add(nueva_mascota)
            db.session.commit()
            flash(f'Mascota "{nombre}" creada exitosamente.', 'success')
            return redirect(url_for('mascotas.admin_lista'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al crear la mascota')
            flash('No se pudo crear la mascota. Inténtalo de nuevo.', 'danger')
            return render_template('mascotas/admin/form.html', mascota=None)

    # GET: Mostrar formulario vacío
    return render_template('mascotas/admin/form.html', mascota=None)


def _formulario_edicion(mascota):
    """Formulario de edición con las acciones de estado que permite la regla de adopción."""
    return render_template(
        'mascotas/admin/form.html',
        mascota=mascota,
        pendientes=adopciones.pendientes_por_mascota([mascota.id]).get(mascota.id, 0),
        puede_volver_a_disponible=adopciones.puede_volver_a_disponible(mascota),
    )


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
        # Obtener datos del formulario
        nombre = request.form.get('nombre', '').strip()
        especie = request.form.get('especie', '').strip()
        raza = request.form.get('raza', '').strip()
        edad_aprox = request.form.get('edad_aprox', '')
        sexo = request.form.get('sexo', '').strip()
        tamano = request.form.get('tamano', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        vacunado = request.form.get('vacunado') == 'on'
        esterilizado = request.form.get('esterilizado') == 'on'

        # Validaciones básicas
        if not nombre or len(nombre) < 2:
            flash('El nombre debe tener al menos 2 caracteres.', 'danger')
            return _formulario_edicion(mascota)

        if not especie or len(especie) < 2:
            flash('La especie es obligatoria.', 'danger')
            return _formulario_edicion(mascota)

        if not descripcion or len(descripcion) < 10:
            flash('La descripción debe tener al menos 10 caracteres.', 'danger')
            return _formulario_edicion(mascota)

        # Manejar foto: prioridad archivo > URL
        foto_url = None
        foto = request.files.get('foto')
        if foto and foto.filename:
            foto_url = upload_to_s3(foto)
            if not foto_url:
                flash('Formato de imagen no permitido', 'danger')
                return redirect(request.url)
            delete_from_s3(mascota.foto_url)
        else:
            foto_url = request.form.get('foto_url', '').strip() or None
            if foto_url and not es_url_imagen_valida(foto_url):
                flash('La URL de la foto debe empezar por https://', 'danger')
                return _formulario_edicion(mascota)
            # Si cambió la URL, borrar la antigua de S3
            if foto_url != mascota.foto_url:
                delete_from_s3(mascota.foto_url)

        # Convertir edad a entero
        try:
            edad_aprox = int(edad_aprox) if edad_aprox else None
            if edad_aprox is not None and (edad_aprox < 0 or edad_aprox > 30):
                flash('La edad debe estar entre 0 y 30 años.', 'danger')
                return _formulario_edicion(mascota)
        except ValueError:
            flash('La edad debe ser un número válido.', 'danger')
            return _formulario_edicion(mascota)

        # Actualizar datos
        mascota.nombre = nombre
        mascota.especie = especie
        mascota.raza = raza if raza else None
        mascota.edad_aprox = edad_aprox
        mascota.sexo = sexo if sexo else None
        mascota.tamano = tamano if tamano else None
        mascota.descripcion = descripcion
        mascota.foto_url = foto_url if foto_url else None
        mascota.vacunado = vacunado
        mascota.esterilizado = esterilizado

        try:
            db.session.commit()
            flash(f'Mascota "{nombre}" actualizada exitosamente.', 'success')
            return redirect(url_for('mascotas.admin_lista'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception('Error al actualizar la mascota')
            flash('No se pudo actualizar la mascota. Inténtalo de nuevo.', 'danger')
            return _formulario_edicion(mascota)

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

    # Obtener la mascota
    mascota = db.get_or_404(Mascota, mascota_id)

    # Verificar si tiene solicitudes asociadas
    if mascota.solicitudes.count() > 0:
        flash(f'No se puede eliminar "{mascota.nombre}" porque tiene solicitudes de adopción asociadas.', 'danger')
        return redirect(url_for('mascotas.admin_lista'))

    try:
        nombre = mascota.nombre
        delete_from_s3(mascota.foto_url)
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
