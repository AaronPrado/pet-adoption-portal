"""
Blueprint de rutas para la gestión de solicitudes de adopción.

Este módulo maneja:
- Creación de solicitudes con cuestionario (usuarios autenticados)
- Visualización de solicitudes del usuario
- Panel de administración para revisar solicitudes
- Aprobación/rechazo de solicitudes (solo admin)
"""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from app import adopciones, cuestionario, db
from app.decorators import admin_required
from app.models import Mascota, Solicitud

# Mensaje general cuando el cuestionario tiene errores en sus campos
MENSAJE_REVISAR = 'Revisa los campos marcados.'

# Crear blueprint
bp = Blueprint('solicitudes', __name__, url_prefix='/solicitudes')


def mostrar_cuestionario(mascota, valores=None, errores=None, codigo=200):
    """
    Renderiza el cuestionario con los valores enviados y los errores por
    campo (contrato `valores`/`errores`).
    """
    return render_template('solicitudes/nueva.html', mascota=mascota, preguntas=cuestionario.PREGUNTAS,
                           valores=valores or {}, errores=errores or {}), codigo


@bp.route('/nueva/<int:mascota_id>', methods=['GET', 'POST'])
@login_required
def nueva(mascota_id):
    """
    Crear nueva solicitud de adopción con cuestionario.

    Muestra formulario con preguntas sobre el adoptante.
    Solo usuarios autenticados pueden solicitar.
    No se puede solicitar la misma mascota dos veces.
    Ante un cuestionario inválido vuelve a mostrar el formulario con lo
    escrito y los errores de cada campo, responde 400 y no crea la solicitud.

    Args:
        mascota_id (int): ID de la mascota a adoptar
    """
    mascota = db.get_or_404(Mascota, mascota_id)

    # Verificar que la mascota esté disponible
    if not mascota.esta_disponible():
        flash(adopciones.MascotaNoDisponible.mensaje, 'warning')
        return redirect(url_for('mascotas.detalle', mascota_id=mascota_id))

    # Verificar si el usuario ya tiene una solicitud para esta mascota
    solicitud_existente = Solicitud.query.filter_by(
        usuario_id=current_user.id,
        mascota_id=mascota_id
    ).first()

    if solicitud_existente:
        flash(adopciones.SolicitudDuplicada.mensaje, 'info')
        return redirect(url_for('solicitudes.mis_solicitudes'))

    if request.method == 'POST':
        # Validar antes de crear: un envío inválido no crea la solicitud (P-04)
        valores = {campo: request.form.get(campo, '') for campo in cuestionario.PREGUNTAS}
        respuestas, errores = cuestionario.validar(valores)
        if errores:
            flash(MENSAJE_REVISAR, 'danger')
            # Se repinta como mucho un carácter de más, para que se note que se pasó
            repintar = {campo: valor[:cuestionario.LONGITUD_MAXIMA + 1] for campo, valor in valores.items()}
            return mostrar_cuestionario(mascota, repintar, errores, 400)

        # La mascota sigue disponible: admite más solicitudes en paralelo
        try:
            adopciones.crear_solicitud(current_user.id, mascota_id, respuestas)
        except adopciones.SolicitudDuplicada as error:
            flash(error.mensaje, 'info')
            return redirect(url_for('solicitudes.mis_solicitudes'))
        except adopciones.MascotaNoDisponible as error:
            flash(error.mensaje, 'warning')
            return redirect(url_for('mascotas.detalle', mascota_id=mascota_id))
        except adopciones.MascotaNoEncontrada:
            abort(404)

        flash(f'¡Solicitud enviada con éxito para {mascota.nombre}! Revisaremos tu solicitud pronto.', 'success')
        return redirect(url_for('solicitudes.mis_solicitudes'))

    return mostrar_cuestionario(mascota)


@bp.route('/mis-solicitudes')
@login_required
def mis_solicitudes():
    """
    Lista de solicitudes del usuario actual.

    Muestra todas las solicitudes creadas por el usuario
    con su estado actual (pendiente, aprobada, rechazada).
    """
    solicitudes = Solicitud.query.options(joinedload(Solicitud.mascota))\
        .filter_by(usuario_id=current_user.id)\
        .order_by(Solicitud.fecha_solicitud.desc())\
        .all()

    return render_template('solicitudes/mis_solicitudes.html', solicitudes=solicitudes)


@bp.route('/detalle/<int:solicitud_id>')
@login_required
def detalle(solicitud_id):
    """
    Ver detalle de una solicitud específica.

    Muestra el cuestionario completo y el estado.
    Solo el usuario que creó la solicitud o admin pueden verla.

    Args:
        solicitud_id (int): ID de la solicitud
    """
    solicitud = db.get_or_404(Solicitud, solicitud_id)

    # Verificar permisos: solo el dueño o admin pueden ver
    if not current_user.is_admin() and solicitud.usuario_id != current_user.id:
        flash('No tienes permiso para ver esta solicitud.', 'danger')
        return redirect(url_for('solicitudes.mis_solicitudes'))

    return render_template('solicitudes/detalle.html', solicitud=solicitud, secciones=cuestionario.SECCIONES)


# Rutas de ADMINISTRACIÓN
# Requieren autenticación y rol de admin

@bp.route('/admin')
@login_required
@admin_required
def admin_lista():
    """
    Panel de administración: lista de todas las solicitudes.

    Muestra todas las solicitudes con filtro por estado.
    Solo accesible para administradores.
    """

    # Obtener filtro de estado si existe
    estado_filtro = request.args.get('estado', '')

    # Query base
    # Cargar mascota y usuario en la misma consulta: la plantilla los muestra
    # en cada fila y, si no, se hacían dos consultas más por solicitud
    query = Solicitud.query.options(joinedload(Solicitud.mascota), joinedload(Solicitud.usuario))

    # Aplicar filtro de estado si existe
    if estado_filtro:
        query = query.filter_by(estado=estado_filtro)

    # Ordenar por fecha (más recientes primero)
    pagina = query.order_by(Solicitud.fecha_solicitud.desc()).paginate(
        page=request.args.get('page', 1, type=int),
        per_page=current_app.config['ADMIN_POR_PAGINA'],
        error_out=False,
    )

    return render_template('solicitudes/admin/lista.html',
                         solicitudes=pagina.items,
                         pagina=pagina,
                         estado_filtro=estado_filtro)


@bp.route('/admin/revisar/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_revisar(solicitud_id):
    """
    Revisar y aprobar/rechazar una solicitud.

    Muestra el detalle completo y permite al admin
    aprobar o rechazar con comentarios.
    Solo accesible para administradores.

    Args:
        solicitud_id (int): ID de la solicitud
    """

    solicitud = db.get_or_404(Solicitud, solicitud_id)

    if request.method == 'POST':
        accion = request.form.get('accion')
        comentarios = request.form.get('comentarios', '')

        # Aprobar adopta la mascota y rechaza las demás pendientes; rechazar
        # solo cambia esta solicitud (app.adopciones)
        try:
            if accion == 'aprobar':
                adopciones.aprobar(solicitud, current_user.id, comentarios)
                flash(f'Solicitud aprobada. {solicitud.usuario.nombre} ha adoptado a {solicitud.mascota.nombre}. '
                      'Las demás solicitudes pendientes se han rechazado.', 'success')
            elif accion == 'rechazar':
                adopciones.rechazar(solicitud, current_user.id, comentarios)
                flash('Solicitud rechazada.', 'info')
        except (adopciones.MascotaNoEncontrada, adopciones.SolicitudNoEncontrada):
            abort(404)
        except (adopciones.MascotaYaAdoptada, adopciones.SolicitudYaRevisada) as error:
            flash(error.mensaje, 'warning')

        return redirect(url_for('solicitudes.admin_lista'))

    return render_template('solicitudes/admin/revisar.html', solicitud=solicitud,
                           secciones=cuestionario.SECCIONES)
