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
from sqlalchemy import case
from sqlalchemy.orm import joinedload

from app import adopciones, cuestionario, db
from app.decorators import admin_required
from app.errores import INICIO, pagina_error
from app.models import ETIQUETAS_ESTADO, Mascota, Solicitud

# Tras enviar el cuestionario (P-24): qué pasa ahora y dónde verlo. La app no
# envía correos, así que la respuesta solo llega a «Mis solicitudes».
MENSAJE_RECIBIDA = ('Hemos recibido tu solicitud para adoptar a {nombre}. El refugio revisará tus '
                    'respuestas y te contestará en esta página, donde puedes seguir su estado.')
# Quien vuelve a solicitar la misma mascota (P-44); la API mantiene su mensaje
MENSAJE_YA_SOLICITADA = 'Ya tienes una solicitud para {nombre}.'
MENSAJE_ACCION_NO_VALIDA = 'Acción no válida.'
MENSAJE_MOTIVO = 'Escribe el motivo del rechazo: el solicitante lo verá.'
# El refugio gestiona las solicitudes, no las envía (P-45)
TITULO_ADMIN_NO_SOLICITA = 'Las cuentas del refugio no pueden solicitar adopciones'
MENSAJE_ADMIN_NO_SOLICITA = ('Con la cuenta del refugio revisas las solicitudes para adoptar a {nombre}, '
                             'pero no puedes enviar una. Para adoptar, usa una cuenta personal.')
GESTIONAR_SOLICITUDES = ('Gestionar solicitudes', 'solicitudes.admin_lista')
# Filtros de la lista: (valor de `estado`, texto); '' es «Todas»
FILTROS_ESTADO = (('', 'Todas'), ('pendiente', 'Pendientes'), ('aprobada', 'Aprobadas'),
                  ('rechazada', 'Rechazadas'))

# Tope del mensaje al aprobar y del motivo al rechazar (el mismo que las respuestas)
LONGITUD_MAXIMA = cuestionario.LONGITUD_MAXIMA
MENSAJE_LARGO = f'El texto no puede superar los {LONGITUD_MAXIMA} caracteres.'

# Crear blueprint
bp = Blueprint('solicitudes', __name__, url_prefix='/solicitudes')


def mostrar_cuestionario(mascota, valores=None, errores=None, codigo=200):
    """
    Renderiza el cuestionario con los valores enviados y los errores por
    campo (contrato `valores`/`errores`). Las preguntas salen de
    `app/cuestionario.py`, la única fuente.
    """
    errores = errores or {}
    return render_template('solicitudes/nueva.html', mascota=mascota, secciones=cuestionario.SECCIONES,
                           resumen=cuestionario.resumen_de_errores(errores),
                           valores=valores or {}, errores=errores), codigo


def solicitud_propia(mascota_id):
    """La solicitud del usuario actual para esa mascota, o None."""
    return db.session.scalar(db.select(Solicitud).filter_by(usuario_id=current_user.id, mascota_id=mascota_id))


def ir_a_solicitud_propia(nombre, solicitud):
    """Avisa de que ya la solicitó y lleva a esa solicitud (a la lista si ya no existe)."""
    flash(MENSAJE_YA_SOLICITADA.format(nombre=nombre), 'info')
    if solicitud is None:
        return redirect(url_for('solicitudes.mis_solicitudes'))
    return redirect(url_for('solicitudes.detalle', solicitud_id=solicitud.id))


@bp.route('/nueva/<int:mascota_id>', methods=['GET', 'POST'])
@login_required
def nueva(mascota_id):
    """
    Crear nueva solicitud de adopción con cuestionario.

    Muestra formulario con preguntas sobre el adoptante.
    Solo usuarios autenticados pueden solicitar.
    No se puede solicitar la misma mascota dos veces: quien ya la solicitó
    va a su solicitud, aunque la mascota ya no esté disponible (P-44).
    Ante un cuestionario inválido vuelve a mostrar el formulario con lo
    escrito y los errores de cada campo, responde 400 y no crea la solicitud.

    Args:
        mascota_id (int): ID de la mascota a adoptar
    """
    mascota = db.get_or_404(Mascota, mascota_id)
    # El rollback de un error de adopciones expira la mascota
    nombre = mascota.nombre

    # El admin revisa solicitudes (y podría aprobar la suya): 403 propio (P-45)
    if current_user.is_admin():
        return pagina_error(403, TITULO_ADMIN_NO_SOLICITA, MENSAJE_ADMIN_NO_SOLICITA.format(nombre=nombre),
                            salidas=(GESTIONAR_SOLICITUDES, INICIO),
                            primera=(f'Volver a la ficha de {nombre}',
                                     url_for('mascotas.detalle', mascota_id=mascota_id)))

    # Antes que la disponibilidad: si su solicitud se aprobó, la mascota ya no está disponible
    solicitud_existente = solicitud_propia(mascota_id)
    if solicitud_existente:
        return ir_a_solicitud_propia(nombre, solicitud_existente)

    if not mascota.esta_disponible():
        flash(adopciones.MascotaNoDisponible.mensaje, 'warning')
        return redirect(url_for('mascotas.detalle', mascota_id=mascota_id))

    if request.method == 'POST':
        # Validar antes de crear: un envío inválido no crea la solicitud (P-04)
        valores = {campo: request.form.get(campo, '') for campo in cuestionario.PREGUNTAS}
        respuestas, errores = cuestionario.validar(valores)
        if errores:
            # Se repinta como mucho un carácter de más, para que se note que se pasó
            repintar = {campo: valor[:cuestionario.LONGITUD_MAXIMA + 1] for campo, valor in valores.items()}
            return mostrar_cuestionario(mascota, repintar, errores, 400)

        # La mascota sigue disponible: admite más solicitudes en paralelo
        try:
            adopciones.crear_solicitud(current_user.id, mascota_id, respuestas)
        except adopciones.SolicitudDuplicada:
            # Otro envío suyo llegó antes (la restricción única lo detecta)
            return ir_a_solicitud_propia(nombre, solicitud_propia(mascota_id))
        except adopciones.MascotaNoDisponible as error:
            flash(error.mensaje, 'warning')
            return redirect(url_for('mascotas.detalle', mascota_id=mascota_id))
        except adopciones.MascotaNoEncontrada:
            abort(404)

        flash(MENSAJE_RECIBIDA.format(nombre=nombre), 'success')
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
    Gestión de solicitudes: lista paginada con filtro por estado.

    Las pendientes van primero, de la más antigua a la más reciente, para
    que ninguna espere de más (P-28); las resueltas, después y de la más
    reciente a la más antigua. Un estado desconocido se trata como «Todas».
    Solo accesible para administradores.
    """
    estado_filtro = request.args.get('estado', '')
    if estado_filtro not in ETIQUETAS_ESTADO['solicitud']:
        estado_filtro = ''

    # Mascota y solicitante en la misma consulta: la plantilla los muestra en
    # cada fila (sin N+1, tests/test_rendimiento.py)
    consulta = db.select(Solicitud).options(joinedload(Solicitud.mascota), joinedload(Solicitud.usuario))
    if estado_filtro:
        consulta = consulta.where(Solicitud.estado == estado_filtro)
    consulta = consulta.order_by(*orden_de_lista(estado_filtro))

    pagina = db.paginate(consulta, page=request.args.get('page', 1, type=int),
                         per_page=current_app.config['ADMIN_POR_PAGINA'], error_out=False)

    return render_template('solicitudes/admin/lista.html', solicitudes=pagina.items, pagina=pagina,
                           estado_filtro=estado_filtro, filtros=FILTROS_ESTADO)


def orden_de_lista(estado):
    """
    Criterios de orden de la lista: pendientes de la más antigua a la más
    reciente; resueltas de la más reciente a la más antigua. El id desempata
    para que la paginación sea estable.
    """
    if estado == 'pendiente':
        return Solicitud.fecha_solicitud.asc(), Solicitud.id.asc()
    if estado:
        return Solicitud.fecha_solicitud.desc(), Solicitud.id.desc()
    pendiente = Solicitud.estado == 'pendiente'
    return (case((pendiente, 0), else_=1), case((pendiente, Solicitud.fecha_solicitud)).asc(),
            case((pendiente, Solicitud.id)).asc(), Solicitud.fecha_solicitud.desc(), Solicitud.id.desc())


@bp.route('/admin/revisar/<int:solicitud_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_revisar(solicitud_id):
    """
    Revisar y aprobar/rechazar una solicitud.

    Muestra el detalle completo y permite al admin aprobar (con un mensaje
    opcional y confirmación) o rechazar (con motivo obligatorio). Una
    solicitud ya resuelta se muestra con su estado, sin formulario.
    Solo accesible para administradores.

    Responde 400 ante una acción desconocida, un rechazo sin motivo o un
    texto de más de `LONGITUD_MAXIMA` caracteres; en estos dos casos
    conserva lo escrito (recortado) y marca el campo.

    Args:
        solicitud_id (int): ID de la solicitud
    """

    solicitud = db.get_or_404(Solicitud, solicitud_id, options=[
        joinedload(Solicitud.mascota), joinedload(Solicitud.usuario), joinedload(Solicitud.revisor)])

    if request.method == 'GET':
        return mostrar_revision(solicitud)

    accion = request.form.get('accion')
    if accion not in ('aprobar', 'rechazar'):
        flash(MENSAJE_ACCION_NO_VALIDA, 'danger')
        return mostrar_revision(solicitud, codigo=400)

    # Una resuelta ya no tiene formulario: se avisa antes de validar el motivo
    # (app.adopciones lo vuelve a comprobar con la fila bloqueada)
    if not solicitud.esta_pendiente():
        flash(adopciones.SolicitudYaRevisada.mensaje, 'warning')
        return redirect(url_for('solicitudes.admin_revisar', solicitud_id=solicitud.id))

    valores = {campo: request.form.get(campo, '') for campo in ('comentarios', 'motivo')}
    errores = validar_decision(accion, valores)
    if errores:
        # El resumen de errores de la plantilla avisa y lleva al campo. Como en
        # el cuestionario, se repinta como mucho un carácter de más
        repintar = {campo: valor[:LONGITUD_MAXIMA + 1] for campo, valor in valores.items()}
        return mostrar_revision(solicitud, repintar, errores, 400)

    # Aprobar adopta la mascota y rechaza las demás pendientes; rechazar
    # solo cambia esta solicitud (app.adopciones)
    try:
        if accion == 'aprobar':
            adopciones.aprobar(solicitud, current_user.id, valores['comentarios'].strip() or None)
            flash(f'Solicitud aprobada. {solicitud.usuario.nombre} ha adoptado a {solicitud.mascota.nombre}. '
                  'Las demás solicitudes pendientes se han rechazado.', 'success')
        else:
            adopciones.rechazar(solicitud, current_user.id, valores['motivo'].strip())
            flash('Solicitud rechazada.', 'info')
    except (adopciones.MascotaNoEncontrada, adopciones.SolicitudNoEncontrada):
        abort(404)
    except (adopciones.MascotaYaAdoptada, adopciones.SolicitudYaRevisada) as error:
        flash(error.mensaje, 'warning')
        return redirect(url_for('solicitudes.admin_revisar', solicitud_id=solicitud.id))

    return redirect(url_for('solicitudes.admin_lista'))


def validar_decision(accion, valores):
    """
    Errores del texto que acompaña a la decisión (contrato `errores`).

    Aprobar admite un mensaje opcional (`comentarios`); rechazar exige un
    motivo (`motivo`). Ninguno puede superar `LONGITUD_MAXIMA` caracteres.
    """
    campo = 'motivo' if accion == 'rechazar' else 'comentarios'
    texto = valores[campo].strip()
    if campo == 'motivo' and not texto:
        return {campo: MENSAJE_MOTIVO}
    if len(texto) > LONGITUD_MAXIMA:
        return {campo: MENSAJE_LARGO}
    return {}


def otras_solicitudes(solicitud):
    """
    Las demás solicitudes de la misma mascota, con su solicitante en la
    misma consulta: primero las pendientes y, dentro de cada grupo, de la más
    antigua a la más reciente.
    """
    pendiente = Solicitud.estado == 'pendiente'
    consulta = (db.select(Solicitud).options(joinedload(Solicitud.usuario))
                .where(Solicitud.mascota_id == solicitud.mascota_id, Solicitud.id != solicitud.id)
                .order_by(case((pendiente, 0), else_=1), Solicitud.fecha_solicitud, Solicitud.id))
    return db.session.scalars(consulta).all()


def mostrar_revision(solicitud, valores=None, errores=None, codigo=200):
    """
    Renderiza la revisión con el contrato `valores`/`errores`.

    `otras` son las demás candidatas de la mascota; `otras_pendientes`, las
    que se rechazarán al aprobar esta (sale en el aviso y en la confirmación
    de «Aprobar»).
    """
    otras = otras_solicitudes(solicitud)
    otras_pendientes = sum(otra.esta_pendiente() for otra in otras) if solicitud.esta_pendiente() else 0
    return render_template('solicitudes/admin/revisar.html', solicitud=solicitud,
                           secciones=cuestionario.SECCIONES, otras=otras, otras_pendientes=otras_pendientes,
                           longitud_maxima=LONGITUD_MAXIMA, valores=valores or {},
                           errores=errores or {}), codigo
