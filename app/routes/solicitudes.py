"""
Blueprint de rutas para la gestión de solicitudes de adopción.

Este módulo maneja:
- Creación de solicitudes con cuestionario (usuarios autenticados)
- Visualización de solicitudes del usuario
- Panel de administración para revisar solicitudes
- Aprobación/rechazo de solicitudes (solo admin)
"""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app import db
from app.decorators import admin_required
from app.models import Mascota, Solicitud

# Crear blueprint
bp = Blueprint('solicitudes', __name__, url_prefix='/solicitudes')


@bp.route('/nueva/<int:mascota_id>', methods=['GET', 'POST'])
@login_required
def nueva(mascota_id):
    """
    Crear nueva solicitud de adopción con cuestionario.

    Muestra formulario con preguntas sobre el adoptante.
    Solo usuarios autenticados pueden solicitar.
    No se puede solicitar la misma mascota dos veces.

    Args:
        mascota_id (int): ID de la mascota a adoptar
    """
    mascota = db.get_or_404(Mascota, mascota_id)

    # Verificar que la mascota esté disponible
    if not mascota.esta_disponible():
        flash('Esta mascota ya no está disponible para adopción.', 'warning')
        return redirect(url_for('mascotas.detalle', mascota_id=mascota_id))

    # Verificar si el usuario ya tiene una solicitud para esta mascota
    solicitud_existente = Solicitud.query.filter_by(
        usuario_id=current_user.id,
        mascota_id=mascota_id
    ).first()

    if solicitud_existente:
        flash('Ya has enviado una solicitud para esta mascota.', 'info')
        return redirect(url_for('solicitudes.mis_solicitudes'))

    if request.method == 'POST':
        # Recoger respuestas del cuestionario
        cuestionario = {
            'vivienda_tipo': request.form.get('vivienda_tipo'),
            'vivienda_propia': request.form.get('vivienda_propia'),
            'tiene_jardin': request.form.get('tiene_jardin') == 'si',
            'tiene_mascotas': request.form.get('tiene_mascotas') == 'si',
            'mascotas_detalles': request.form.get('mascotas_detalles', ''),
            'experiencia_previa': request.form.get('experiencia_previa'),
            'horas_solo': request.form.get('horas_solo'),
            'motivo_adopcion': request.form.get('motivo_adopcion'),
            'compromiso_gastos': request.form.get('compromiso_gastos') == 'si',
            'compromiso_tiempo': request.form.get('compromiso_tiempo') == 'si',
            'emergencia_veterinaria': request.form.get('emergencia_veterinaria'),
            'referencias': request.form.get('referencias', '')
        }

        # Crear la solicitud
        solicitud = Solicitud(
            usuario_id=current_user.id,
            mascota_id=mascota_id,
            cuestionario=cuestionario
        )

        db.session.add(solicitud)

        # Marcar la mascota como "en proceso" (hace commit de ambos cambios).
        # La restricción única protege de dos envíos simultáneos.
        try:
            mascota.marcar_en_proceso()
        except IntegrityError:
            db.session.rollback()
            flash('Ya has enviado una solicitud para esta mascota.', 'info')
            return redirect(url_for('solicitudes.mis_solicitudes'))

        flash(f'¡Solicitud enviada con éxito para {mascota.nombre}! Revisaremos tu solicitud pronto.', 'success')
        return redirect(url_for('solicitudes.mis_solicitudes'))

    return render_template('solicitudes/nueva.html', mascota=mascota)


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

    return render_template('solicitudes/detalle.html', solicitud=solicitud)


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
        # Una solicitud ya resuelta no se puede volver a aprobar o rechazar
        if not solicitud.esta_pendiente():
            flash('Esta solicitud ya ha sido revisada.', 'warning')
            return redirect(url_for('solicitudes.admin_lista'))

        accion = request.form.get('accion')
        comentarios = request.form.get('comentarios', '')

        if accion == 'aprobar':
            # Evita dos adopciones de la misma mascota
            if solicitud.mascota.estado == 'adoptado':
                flash(f'{solicitud.mascota.nombre} ya ha sido adoptado.', 'warning')
                return redirect(url_for('solicitudes.admin_lista'))
            solicitud.aprobar(current_user.id, comentarios)
            flash(f'Solicitud aprobada. {solicitud.usuario.nombre} ha adoptado a {solicitud.mascota.nombre}.',
                  'success')
        elif accion == 'rechazar':
            solicitud.rechazar(current_user.id, comentarios)
            flash('Solicitud rechazada.', 'info')

        return redirect(url_for('solicitudes.admin_lista'))

    return render_template('solicitudes/admin/revisar.html', solicitud=solicitud)
