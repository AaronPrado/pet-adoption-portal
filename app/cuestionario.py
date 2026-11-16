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

from dataclasses import dataclass

# Longitud máxima de las respuestas de texto
LONGITUD_MAXIMA = 2000

SI_NO = (('si', 'Sí'), ('no', 'No'))

MENSAJE_OBLIGATORIO = 'Esta pregunta es obligatoria.'
MENSAJE_OPCION = 'Elige una de las opciones.'
MENSAJE_TEXTO = 'La respuesta no es un texto válido.'
MENSAJE_LARGO = f'La respuesta no puede superar los {LONGITUD_MAXIMA} caracteres.'
MENSAJE_DETALLES = 'Si tienes otras mascotas, cuéntanos cuáles.'


@dataclass(frozen=True)
class Pregunta:
    """
    Una pregunta del cuestionario.

    Attributes:
        texto: enunciado legible.
        opciones: pares (value, etiqueta) o None si la respuesta es libre.
        obligatoria: si debe contestarse siempre.
        si_no: si la respuesta es sí/no y se guarda como booleano.
    """
    texto: str
    opciones: tuple | None = None
    obligatoria: bool = True
    si_no: bool = False

    def etiqueta(self, valor):
        """Etiqueta legible de un `value` («8+» → «Más de 8 horas»), o None."""
        return dict(self.opciones or ()).get(valor)


PREGUNTAS = {
    'vivienda_tipo': Pregunta('Tipo de vivienda', (
        ('casa', 'Casa'), ('apartamento', 'Apartamento'), ('finca', 'Finca/Campo'))),
    'vivienda_propia': Pregunta('¿Es vivienda propia o alquilada?', (
        ('propia', 'Propia'), ('alquilada', 'Alquilada'))),
    'tiene_jardin': Pregunta('¿Tiene jardín o patio?', SI_NO, si_no=True),
    'tiene_mascotas': Pregunta('¿Tiene otras mascotas actualmente?', SI_NO, si_no=True),
    'mascotas_detalles': Pregunta('Otras mascotas (especie, edad, vacunadas)', obligatoria=False),
    'experiencia_previa': Pregunta('¿Tienes experiencia previa con mascotas?'),
    'horas_solo': Pregunta('¿Cuántas horas al día estaría solo/a?', (
        ('0-4', '0-4 horas'), ('4-8', '4-8 horas'), ('8+', 'Más de 8 horas'))),
    'emergencia_veterinaria': Pregunta('¿Cómo actuarías ante una emergencia veterinaria?', (
        ('veterinario', 'Llevaría inmediatamente al veterinario'),
        ('consulta', 'Consultaría online primero'),
        ('espera', 'Esperaría a ver evolución'))),
    'motivo_adopcion': Pregunta('¿Por qué quieres adoptar?'),
    'compromiso_gastos': Pregunta('Compromiso de cubrir gastos veterinarios y cuidados', (
        ('si', 'Se compromete'), ('no', 'No puede garantizarlo')), si_no=True),
    'compromiso_tiempo': Pregunta('Compromiso de dedicar tiempo diario', (
        ('si', 'Se compromete'), ('no', 'No puede garantizarlo')), si_no=True),
    'referencias': Pregunta('Referencias personales o veterinarias', obligatoria=False),
}


def claves_desconocidas(datos):
    """Claves de `datos` que no son preguntas del cuestionario, ordenadas."""
    return sorted(str(clave) for clave in datos if clave not in PREGUNTAS)


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
