"""
Regla de adopción (ADR-0004): las solicitudes se admiten en paralelo y el
estado de la mascota lo decide solo este módulo.

- La mascota sigue `disponible` mientras tenga solicitudes pendientes.
- Aprobar una solicitud adopta la mascota y rechaza las demás pendientes.
- Rechazar solo cambia esa solicitud.
- El admin solo puede marcarla «adoptada fuera del portal» (con los mismos
  efectos que una aprobación sobre las pendientes) o deshacer eso.
- «Tiene solicitudes en curso» se deriva del recuento de pendientes; no se
  guarda.

Las rutas web y la API usan estas funciones; cada una hace su propio commit.
Todas bloquean antes la fila de la mascota (`SELECT … FOR UPDATE`) y vuelven
a leer los datos, para que dos peticiones simultáneas no adopten dos veces ni
dejen pendientes colgadas.

Si la regla no permite la operación lanzan una subclase de `ErrorAdopcion`
tras hacer rollback. Ese rollback descarta también cualquier cambio sin
confirmar que el llamador tuviera en la sesión: no hay que llamarlas con
cambios pendientes que se quieran conservar.
"""

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, InvalidRequestError, NoResultFound

from app import db
from app.models import Mascota, Solicitud

COMENTARIO_RECHAZO_AUTOMATICO = (
    'Gracias por tu interés. Esta mascota ya ha encontrado un hogar, así que '
    'tu solicitud se ha cerrado. Te animamos a conocer a los demás animales del catálogo.'
)


# Nombre de la restricción única (usuario_id, mascota_id) en app/models.py
RESTRICCION_UNICA = 'unique_usuario_mascota'


class ErrorAdopcion(Exception):
    """Operación no permitida por la regla de adopción; `mensaje` es apto para el usuario."""

    mensaje = 'No se ha podido completar la operación.'

    def __init__(self):
        super().__init__(self.mensaje)


class MascotaNoEncontrada(ErrorAdopcion):
    """La mascota no existe (p. ej. se borró mientras tanto); las rutas responden 404."""

    mensaje = 'Mascota no encontrada'


class SolicitudNoEncontrada(ErrorAdopcion):
    """La solicitud ya no existe (p. ej. se borró en cascada); las rutas responden 404."""

    mensaje = 'Solicitud no encontrada'


class MascotaNoDisponible(ErrorAdopcion):
    mensaje = 'Esta mascota ya no está disponible para adopción.'


class SolicitudDuplicada(ErrorAdopcion):
    mensaje = 'Ya has enviado una solicitud para esta mascota.'


class SolicitudYaRevisada(ErrorAdopcion):
    mensaje = 'Esta solicitud ya ha sido revisada.'


class MascotaYaAdoptada(ErrorAdopcion):
    mensaje = 'Esta mascota ya ha sido adoptada.'


class TransicionNoPermitida(ErrorAdopcion):
    mensaje = 'Este cambio de estado no está permitido.'


def consulta_mascota_bloqueada(mascota_id):
    """
    SELECT de la mascota con bloqueo de fila hasta el commit.

    `populate_existing` sustituye la copia en memoria por la leída tras el
    bloqueo, que puede haber cambiado mientras se esperaba. SQLite ignora
    `FOR UPDATE` (bloquea la base entera al escribir).
    """
    return (
        select(Mascota)
        .where(Mascota.id == mascota_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _bloquear_mascota(mascota_id):
    try:
        return db.session.execute(consulta_mascota_bloqueada(mascota_id)).scalar_one()
    except NoResultFound:
        db.session.rollback()
        raise MascotaNoEncontrada() from None


def _releer(solicitud):
    """
    Vuelve a leer la solicitud tras el bloqueo: otra transacción pudo resolverla.

    No hace falta bloquear también la solicitud: toda operación que la cambia
    bloquea antes la fila de su mascota, y eso ya las serializa.

    Raises:
        SolicitudNoEncontrada: se borró mientras tanto (refresh no la encuentra).
        SolicitudYaRevisada: ya no está pendiente.
    """
    try:
        db.session.refresh(solicitud)
    except InvalidRequestError:
        db.session.rollback()
        raise SolicitudNoEncontrada() from None
    if not solicitud.esta_pendiente():
        db.session.rollback()
        raise SolicitudYaRevisada()


def _cerrar_pendientes(mascota, admin_id, excepto_id=None):
    """Rechaza con el comentario estándar las pendientes de la mascota, salvo `excepto_id`."""
    consulta = select(Solicitud).where(
        Solicitud.mascota_id == mascota.id,
        Solicitud.estado == 'pendiente',
    ).execution_options(populate_existing=True)
    if excepto_id is not None:
        consulta = consulta.where(Solicitud.id != excepto_id)
    for solicitud in db.session.scalars(consulta):
        solicitud.registrar_revision('rechazada', admin_id, COMENTARIO_RECHAZO_AUTOMATICO)


def _confirmar():
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def es_solicitud_duplicada(error):
    """
    True si el IntegrityError viene de la restricción única (usuario, mascota).

    psycopg 3 da el nombre de la restricción en `diag.constraint_name`; SQLite
    (tests) solo lo indica en el texto del error, con las columnas.
    """
    diag = getattr(error.orig, 'diag', None)
    if diag is not None:
        return diag.constraint_name == RESTRICCION_UNICA
    texto = str(error.orig)
    return RESTRICCION_UNICA in texto or \
        'UNIQUE constraint failed: solicitudes.usuario_id, solicitudes.mascota_id' in texto


def crear_solicitud(usuario_id, mascota_id, cuestionario):
    """
    Crea una solicitud pendiente; la mascota no cambia de estado.

    El bloqueo evita crear una pendiente sobre una mascota que se está
    adoptando en ese momento: la aprobación no la vería al cerrar las demás.

    Raises:
        MascotaNoEncontrada: la mascota no existe.
        MascotaNoDisponible: la mascota no está `disponible`.
        SolicitudDuplicada: el usuario ya la había solicitado.
        IntegrityError: cualquier otra restricción (se registra y se relanza).
    """
    mascota = _bloquear_mascota(mascota_id)
    if not mascota.esta_disponible():
        db.session.rollback()
        raise MascotaNoDisponible()

    solicitud = Solicitud(usuario_id=usuario_id, mascota_id=mascota_id, cuestionario=cuestionario)
    db.session.add(solicitud)
    try:
        _confirmar()
    except IntegrityError as error:
        # La restricción única protege también de dos envíos simultáneos
        if es_solicitud_duplicada(error):
            raise SolicitudDuplicada() from error
        current_app.logger.exception('Error de integridad al crear la solicitud')
        raise
    return solicitud


def aprobar(solicitud, admin_id, comentario=None):
    """
    Aprueba la solicitud, adopta la mascota y rechaza las demás pendientes,
    todo en un solo commit.

    Raises:
        MascotaNoEncontrada: la mascota ya no existe.
        SolicitudNoEncontrada: la solicitud ya no existe.
        SolicitudYaRevisada: la solicitud ya no está pendiente.
        MascotaYaAdoptada: la mascota ya estaba adoptada; no cambia nada.
    """
    mascota = _bloquear_mascota(solicitud.mascota_id)
    _releer(solicitud)
    if mascota.estado == 'adoptado':
        db.session.rollback()
        raise MascotaYaAdoptada()

    solicitud.registrar_revision('aprobada', admin_id, comentario)
    mascota.marcar_adoptado()
    _cerrar_pendientes(mascota, admin_id, excepto_id=solicitud.id)
    _confirmar()


def rechazar(solicitud, admin_id, comentario=None):
    """
    Rechaza solo esta solicitud; la mascota no cambia.

    Raises:
        MascotaNoEncontrada: la mascota ya no existe.
        SolicitudNoEncontrada: la solicitud ya no existe.
        SolicitudYaRevisada: la solicitud ya no está pendiente.
    """
    _bloquear_mascota(solicitud.mascota_id)
    _releer(solicitud)
    solicitud.registrar_revision('rechazada', admin_id, comentario)
    _confirmar()


def adoptar_fuera_del_portal(mascota, admin_id):
    """
    Marca la mascota como adoptada sin solicitud aprobada y rechaza sus
    pendientes, igual que una aprobación, en un solo commit.

    Raises:
        MascotaNoEncontrada: la mascota ya no existe.
        MascotaYaAdoptada: ya estaba adoptada; no cambia nada.
    """
    mascota = _bloquear_mascota(mascota.id)
    if mascota.estado == 'adoptado':
        db.session.rollback()
        raise MascotaYaAdoptada()

    mascota.marcar_adoptado()
    _cerrar_pendientes(mascota, admin_id)
    _confirmar()


def puede_volver_a_disponible(mascota):
    """True si la mascota está adoptada y ninguna solicitud aprobada la adoptó (fue fuera del portal)."""
    if mascota.estado != 'adoptado':
        return False
    aprobada = db.session.scalar(
        select(Solicitud.id).where(Solicitud.mascota_id == mascota.id, Solicitud.estado == 'aprobada').limit(1)
    )
    return aprobada is None


def volver_a_disponible(mascota):
    """
    Deshace una adopción fuera del portal y la mascota vuelve al catálogo.

    Las solicitudes que se rechazaron al marcarla no se reabren.

    Raises:
        MascotaNoEncontrada: la mascota ya no existe.
        TransicionNoPermitida: no está adoptada o la adoptó una solicitud
            aprobada (esa adopción no se deshace desde aquí); no cambia nada.
    """
    mascota = _bloquear_mascota(mascota.id)
    if not puede_volver_a_disponible(mascota):
        db.session.rollback()
        raise TransicionNoPermitida()

    mascota.estado = 'disponible'
    _confirmar()


def pendientes_por_mascota(mascota_ids):
    """
    Número de solicitudes pendientes de cada mascota, con una sola consulta
    agregada (sin N+1). Las mascotas sin pendientes no aparecen.

    Returns:
        dict: {mascota_id: número de pendientes}
    """
    if not mascota_ids:
        return {}
    consulta = (
        select(Solicitud.mascota_id, func.count())
        .where(Solicitud.mascota_id.in_(mascota_ids), Solicitud.estado == 'pendiente')
        .group_by(Solicitud.mascota_id)
    )
    return dict(db.session.execute(consulta).all())
