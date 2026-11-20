"""
Blueprint de rutas para la gestión de mascotas.

Este módulo maneja:
- Catálogo público de mascotas disponibles (sin autenticación)
- Vista detalle de cada mascota
- Panel de administración con CRUD completo (solo admin)
"""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import exists, select

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

# Opciones de los filtros del catálogo
TAMANOS = (('Pequeño', 'Pequeño'), ('Mediano', 'Mediano'), ('Grande', 'Grande'))
SEXOS = (('Macho', 'Macho'), ('Hembra', 'Hembra'))

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
    # La especie se guarda normalizada: el parámetro se normaliza igual (como en la API)
    especie_filtro = Mascota.normalizar_especie(request.args.get('especie', ''))
    tamano_filtro = request.args.get('tamano', '')
    sexo_filtro = request.args.get('sexo', '')
    edad_filtro = request.args.get('edad', '').strip()

    # Query base: solo mascotas disponibles
    query = Mascota.query.filter_by(estado='disponible')

    # Etiquetas legibles de los filtros aplicados (resumen y estado vacío)
    filtros_activos = []

    if especie_filtro:
        query = query.filter(Mascota.especie == especie_filtro)
        filtros_activos.append(especie_filtro)

    if tamano_filtro:
        query = query.filter(Mascota.tamano == tamano_filtro)
        filtros_activos.append(tamano_filtro)

    if sexo_filtro:
        query = query.filter(Mascota.sexo == sexo_filtro)
        filtros_activos.append(sexo_filtro)

    aviso_edad = None
    if edad_filtro:
        try:
            edad_max = int(edad_filtro)
        except ValueError:
            edad_max = None
        if edad_max is None or not EDAD_MINIMA <= edad_max <= EDAD_MAXIMA:
            # Se avisa y se ignora; fuera de rango también evita un desbordamiento en la BD
            aviso_edad = (f'La edad máxima debe ser un número entero entre {EDAD_MINIMA} y {EDAD_MAXIMA}. '
                          'Se muestran mascotas de todas las edades.')
            edad_filtro = ''
        else:
            query = query.filter(Mascota.edad_aprox <= edad_max)
            filtros_activos.append(f'hasta {edad_max} {"año" if edad_max == 1 else "años"}')

    # Ordenar por fecha de ingreso (más recientes primero)
    pagina = query.order_by(Mascota.fecha_ingreso.desc(), Mascota.id.desc()).paginate(
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
                         especies=[(esp, esp) for esp in especies_disponibles],
                         valores={'especie': especie_filtro, 'tamano': tamano_filtro,
                                  'sexo': sexo_filtro, 'edad': edad_filtro},
                         filtros_activos=filtros_activos,
                         aviso_edad=aviso_edad,
                         tamanos=TAMANOS, sexos=SEXOS,
                         edad_minima=EDAD_MINIMA, edad_maxima=EDAD_MAXIMA)


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
        errores, datos, foto_subida = _validar_mascota(valores, request.files.get('foto'))
        if errores:
            flash(MENSAJE_REVISAR, 'danger')
            return _formulario_nueva(valores, errores, 400)

        nueva_mascota = Mascota(**datos, estado='disponible')
        try:
            db.session.add(nueva_mascota)
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Sin mascota, la foto recién subida quedaría huérfana
            fotos.borrar_foto(foto_subida)
            current_app.logger.exception('Error al crear la mascota')
            flash('No se pudo crear la mascota. Inténtalo de nuevo.', 'danger')
            return _formulario_nueva(valores)
        flash(f'Mascota "{nueva_mascota.nombre}" creada exitosamente.', 'success')
        return redirect(url_for('mascotas.admin_lista'))

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


def _validar_mascota(valores, foto, foto_actual=None):
    """
    Valida el formulario de mascota.

    La foto subida tiene prioridad sobre la URL, que entonces no se valida.
    La URL debe ser https://, salvo que sea la foto propia que ya tiene la
    mascota (`foto_actual`, p. ej. `/fotos/<clave>` del backend local); una
    `http://` heredada se vuelve a validar. Si todo lo demás es válido,
    guarda la foto: su formato se comprueba al guardarla, así que no queda
    ninguna subida huérfana por un error en otro campo. Sin backend o si
    falla el almacenamiento, el error va al campo de la foto (nunca un 500).

    Returns:
        tuple: (errores, datos, foto_subida). `errores` es un dict campo →
        mensaje (el contrato `valores`/`errores`); `datos`, los atributos de
        la mascota, solo válidos si no hay errores; `foto_subida`, la URL de
        la foto guardada en esta petición, o None.
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
    conserva_foto_propia = foto_url == foto_actual and fotos.es_foto_propia(foto_actual)
    if hay_archivo and not fotos.subida_disponible():
        errores['foto'] = fotos.MENSAJE_NO_DISPONIBLE
    elif not hay_archivo and foto_url and not conserva_foto_propia and not fotos.es_url_imagen_valida(foto_url):
        errores['foto_url'] = 'La URL de la foto debe empezar por https://. Copia la dirección completa de la imagen.'

    foto_subida = None
    if not errores and hay_archivo:
        try:
            foto_subida = foto_url = fotos.guardar_foto(foto)
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
    return errores, datos, foto_subida


def _borrar_foto_si_nadie_la_usa(url):
    """
    Borra una foto propia que ya no usa ninguna mascota.

    Se llama después de un commit correcto. Dos fichas pueden compartir
    foto_url (una URL de S3 pegada a mano), o usar variantes distintas de la
    misma foto, y la otra no debe perder su foto: se borran todas las
    variantes o ninguna. Un fallo solo se registra: el cambio ya está
    guardado y la foto, como mucho, queda huérfana.
    """
    if not fotos.es_foto_propia(url):
        return
    try:
        if not db.session.scalar(select(exists().where(Mascota.foto_url.in_(fotos.urls_de_la_foto(url))))):
            fotos.borrar_foto(url)
    except Exception:
        db.session.rollback()
        current_app.logger.exception('No se pudo borrar la foto anterior %s', url)


def _contexto_formulario(valores, errores):
    """
    Contexto común del formulario de mascota.

    `subida_disponible` oculta el campo de archivo si no hay backend de fotos.
    `foto_descartada` avisa de que hay que volver a elegir la foto: el
    navegador no puede conservar un archivo al volver a pintar el formulario.
    `max_bytes_foto` deja margen bajo MAX_CONTENT_LENGTH, que limita la
    petición entera y no solo el archivo.
    """
    foto = request.files.get('foto')
    limite = current_app.config['MAX_CONTENT_LENGTH']
    subida_disponible = fotos.subida_disponible()
    return {
        'valores': valores,
        'errores': errores or {},
        'subida_disponible': subida_disponible,
        'foto_descartada': subida_disponible and bool(foto and foto.filename),
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
        foto_anterior = mascota.foto_url
        errores, datos, foto_subida = _validar_mascota(valores, request.files.get('foto'), foto_anterior)
        if errores:
            flash(MENSAJE_REVISAR, 'danger')
            return _formulario_edicion(mascota, valores, errores, 400)

        for atributo, valor in datos.items():
            setattr(mascota, atributo, valor)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            # La mascota conserva la foto anterior; la nueva quedaría huérfana
            fotos.borrar_foto(foto_subida)
            current_app.logger.exception('Error al actualizar la mascota')
            flash('No se pudo actualizar la mascota. Inténtalo de nuevo.', 'danger')
            return _formulario_edicion(mascota, valores)

        # Solo tras guardar: una foto nueva (subida o URL distinta) sustituye a la anterior
        if datos['foto_url'] != foto_anterior:
            _borrar_foto_si_nadie_la_usa(foto_anterior)
        flash(f'Mascota "{datos["nombre"]}" actualizada exitosamente.', 'success')
        return redirect(url_for('mascotas.admin_lista'))

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

    nombre = mascota.nombre
    foto = mascota.foto_url
    try:
        db.session.delete(mascota)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Error al eliminar la mascota')
        flash('No se pudo eliminar la mascota. Inténtalo de nuevo.', 'danger')
    else:
        # Solo tras borrar la ficha: si el commit falla, la mascota conserva su foto
        _borrar_foto_si_nadie_la_usa(foto)
        flash(f'Mascota "{nombre}" eliminada exitosamente.', 'success')

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
