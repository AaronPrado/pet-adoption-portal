"""
Cuestionario de adopción: única fuente de sus preguntas, opciones y reglas.

Lo usan el formulario web (`solicitudes/nueva.html`), la ruta que lo recibe
y la API. `validar()` se aplica solo a los envíos nuevos: los cuestionarios
ya guardados no se vuelven a validar.

Formato guardado (sin cambios respecto a los datos existentes):
- Las preguntas de sí/no se guardan como booleanos (`'si'` → True).
- Las de opciones guardan el `value` de la opción (`'8+'`, `'casa'`...).
- Los textos se guardan sin espacios sobrantes.
- Lo que no se contesta se guarda como `None`, nunca como False.
"""

from dataclasses import dataclass, field

# Longitud máxima de las respuestas de texto
LONGITUD_MAXIMA = 2000

SI_NO = (('si', 'Sí'), ('no', 'No'))

MENSAJE_OBLIGATORIO = 'Esta pregunta es obligatoria.'
MENSAJE_OPCION = 'Elige una de las opciones.'
MENSAJE_TEXTO = 'La respuesta no es un texto válido.'
MENSAJE_LARGO = f'La respuesta no puede superar los {LONGITUD_MAXIMA} caracteres.'
MENSAJE_DETALLES = 'Si tienes otras mascotas, cuéntanos cuáles.'

# Lo que se muestra en lugar de una respuesta que falta
SIN_RESPUESTA = 'Sin respuesta'


@dataclass(frozen=True)
class Pregunta:
    """
    Una pregunta del cuestionario.

    Attributes:
        texto: enunciado legible, siempre en forma de pregunta y tuteando
            (el resumen de errores lo antepone al mensaje).
        opciones: pares (value, etiqueta) o None si la respuesta es libre.
            El `value` se guarda en la base de datos: no se cambia.
        obligatoria: si debe contestarse siempre.
        si_no: si la respuesta es sí/no y se guarda como booleano.
        seccion: grupo en el que se muestra la respuesta (obligatorio, por nombre).
        ayuda: pista que acompaña a la pregunta en el formulario, o None.
    """
    texto: str
    opciones: tuple | None = None
    obligatoria: bool = True
    si_no: bool = False
    seccion: str = field(kw_only=True)
    ayuda: str | None = field(default=None, kw_only=True)

    def etiqueta(self, valor):
        """Etiqueta legible de un `value` («8+» → «Más de 8 horas»), o None."""
        return dict(self.opciones or ()).get(valor)


# Secciones en las que se muestran las respuestas, en este orden
VIVIENDA = 'Vivienda'
EXPERIENCIA = 'Experiencia'
COMPROMISOS = 'Motivación y compromisos'

COMPROMETERSE = (('si', 'Sí, me comprometo'), ('no', 'No puedo garantizarlo'))

# Los `value` (primer elemento de cada opción) y las claves no cambian: son los
# datos guardados (tests/test_cuestionario.py::TestFormatoGuardado)
PREGUNTAS = {
    'vivienda_tipo': Pregunta('¿En qué tipo de vivienda vives?', (
        ('casa', 'Casa'), ('apartamento', 'Apartamento'), ('finca', 'Finca o campo')), seccion=VIVIENDA),
    'vivienda_propia': Pregunta('¿Tu vivienda es propia o alquilada?', (
        ('propia', 'Propia'), ('alquilada', 'Alquilada')), seccion=VIVIENDA),
    'tiene_jardin': Pregunta('¿Tienes jardín o patio?', SI_NO, si_no=True, seccion=VIVIENDA),
    'tiene_mascotas': Pregunta('¿Tienes otras mascotas?', SI_NO, si_no=True, seccion=VIVIENDA),
    'mascotas_detalles': Pregunta(
        '¿Qué otras mascotas tienes?', obligatoria=False, seccion=VIVIENDA,
        ayuda='Si tienes otras, dinos de qué especie son, qué edad tienen y si están vacunadas.'),
    'experiencia_previa': Pregunta(
        '¿Tienes experiencia previa con mascotas?', seccion=EXPERIENCIA,
        ayuda='Cuéntanos qué animales has cuidado y durante cuánto tiempo.'),
    'horas_solo': Pregunta('¿Cuántas horas al día pasaría la mascota sin compañía?', (
        ('0-4', 'Menos de 4 horas'), ('4-8', 'De 4 a 8 horas'), ('8+', 'Más de 8 horas')), seccion=EXPERIENCIA),
    'emergencia_veterinaria': Pregunta('¿Qué harías ante una emergencia veterinaria?', (
        ('veterinario', 'Iría al veterinario de inmediato'),
        ('consulta', 'Consultaría primero en internet'),
        ('espera', 'Esperaría a ver cómo evoluciona')), seccion=EXPERIENCIA),
    'motivo_adopcion': Pregunta('¿Por qué quieres adoptar?', seccion=COMPROMISOS,
                                ayuda='Cuéntanos qué puedes ofrecerle.'),
    'compromiso_gastos': Pregunta(
        '¿Te comprometes a cubrir los gastos veterinarios, la alimentación y los cuidados que necesite?',
        COMPROMETERSE, si_no=True, seccion=COMPROMISOS),
    'compromiso_tiempo': Pregunta(
        '¿Te comprometes a dedicarle tiempo cada día para el ejercicio, el juego y la atención?',
        COMPROMETERSE, si_no=True, seccion=COMPROMISOS),
    'referencias': Pregunta(
        '¿Tienes referencias personales o veterinarias?', obligatoria=False, seccion=COMPROMISOS,
        ayuda='Nombre, teléfono y relación contigo (veterinario, familiar, amistad…). '
              'Nos ayudan a revisar tu solicitud más rápido.'),
}


def _agrupar_por_seccion(preguntas):
    """((sección, ((campo, pregunta), ...)), ...) en el orden de `preguntas`."""
    secciones = {}
    for campo, pregunta in preguntas.items():
        secciones.setdefault(pregunta.seccion, []).append((campo, pregunta))
    return tuple((titulo, tuple(campos)) for titulo, campos in secciones.items())


# Las preguntas agrupadas para mostrar las respuestas (solicitudes/_respuestas.html)
SECCIONES = _agrupar_por_seccion(PREGUNTAS)


def claves_desconocidas(datos):
    """Claves de `datos` que no son preguntas del cuestionario, ordenadas."""
    return sorted(str(clave) for clave in datos if clave not in PREGUNTAS)



def resumen_de_errores(errores):
    """
    Textos del resumen de errores del formulario web: cada error precedido
    de su pregunta («¿…? Esta pregunta es obligatoria.»), en el orden del
    formulario y no en el que los añadió `validar()`.

    Args:
        errores: dict campo → mensaje, como lo devuelve `validar()`.

    Returns:
        dict: campo → texto, solo con las preguntas que tienen error.
    """
    return {campo: f'{pregunta.texto} {errores[campo]}'
            for campo, pregunta in PREGUNTAS.items() if campo in errores}

def respuesta_legible(respuestas, campo):
    """
    Texto legible de una respuesta guardada (filtro Jinja `respuesta_legible`).

    Las opciones se muestran con su etiqueta («8+» → «Más de 8 horas») y los
    booleanos de sí/no con la de su opción. Un valor que no es de la lista
    (cuestionarios antiguos) se muestra tal cual, sin error.

    Las plantillas solo preguntan por las claves de `PREGUNTAS`: las claves
    antiguas que no son preguntas no se muestran, y esas preguntas salen como
    `SIN_RESPUESTA` (el seed se corrige en B2.6).

    Args:
        respuestas: `cuestionario_json` de la solicitud (puede no ser un dict).
        campo: clave de la pregunta.

    Returns:
        str: la etiqueta, el texto o `SIN_RESPUESTA` si falta.
    """
    valor = respuestas.get(campo) if isinstance(respuestas, dict) else None
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return SIN_RESPUESTA
    pregunta = PREGUNTAS.get(campo)
    if isinstance(valor, bool):
        if pregunta is not None and pregunta.si_no:
            return pregunta.etiqueta('si' if valor else 'no')
        return 'Sí' if valor else 'No'
    if pregunta is not None and isinstance(valor, str):
        return pregunta.etiqueta(valor) or valor
    return str(valor)


def _validar_respuesta(pregunta, valor):
    """Devuelve (valor limpio, mensaje de error o None) de una respuesta."""
    if valor is None:
        return None, None
    if not isinstance(valor, str):
        return None, MENSAJE_OPCION if pregunta.opciones else MENSAJE_TEXTO
    valor = valor.strip()
    if not valor:
        return None, None
    if pregunta.opciones:
        if pregunta.etiqueta(valor) is None:
            return None, MENSAJE_OPCION
        return (valor == 'si') if pregunta.si_no else valor, None
    if len(valor) > LONGITUD_MAXIMA:
        return None, MENSAJE_LARGO
    # PostgreSQL no admite el carácter NUL en JSONB: guardarlo daría un 500
    if '\x00' in valor:
        return None, MENSAJE_TEXTO
    return valor, None


def validar(datos):
    """
    Valida un envío nuevo del cuestionario.

    Las claves que no son preguntas se ignoran (la API las rechaza antes con
    `claves_desconocidas`). Contestar «sí» a `tiene_mascotas` exige
    `mascotas_detalles`.

    Args:
        datos: mapeo campo → respuesta (`request.form` o el JSON de la API).

    Returns:
        tuple: (limpio, errores). `limpio` tiene todas las preguntas, con
        None en las no contestadas; `errores` es un dict campo → mensaje,
        vacío si el envío es válido.
    """
    limpio, errores = {}, {}
    for campo, pregunta in PREGUNTAS.items():
        valor, error = _validar_respuesta(pregunta, datos.get(campo))
        if error is None and valor is None and pregunta.obligatoria:
            error = MENSAJE_OBLIGATORIO
        if error:
            errores[campo] = error
        limpio[campo] = valor

    if limpio['tiene_mascotas'] is True and limpio['mascotas_detalles'] is None \
            and 'mascotas_detalles' not in errores:
        errores['mascotas_detalles'] = MENSAJE_DETALLES
    return limpio, errores
