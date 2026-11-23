"""
Fechas en la zona horaria del refugio (P-26).

Las fechas se guardan en UTC sin zona (`utcnow()` de app/models.py). El filtro
Jinja `fecha_local` las trata como UTC y las convierte a `ZONA_HORARIA`
(config.py) antes de formatearlas, con el cambio de hora de invierno y verano
incluido. Los meses salen de una tabla propia para no depender del locale del
sistema.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MESES = ('enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto',
         'septiembre', 'octubre', 'noviembre', 'diciembre')


def fecha_local(valor, zona, con_hora=False):
    """
    Fecha legible en español en la zona `zona`: «15 de noviembre de 2026» o,
    con `con_hora`, «15 de noviembre de 2026, 14:53».

    Un datetime sin zona se toma como UTC. Sin valor devuelve ''. Un valor que
    no es un datetime (un texto, un número) se devuelve tal cual, sin lanzar:
    la plantilla lo escapa y no se pierde el dato.
    """
    if valor is None:
        return ''
    if not isinstance(valor, datetime):
        return valor
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=UTC)
    local = valor.astimezone(ZoneInfo(zona))
    texto = f'{local.day} de {MESES[local.month - 1]} de {local.year}'
    return f'{texto}, {local:%H:%M}' if con_hora else texto


def registrar_filtros(app):
    """
    Registra el filtro `fecha_local` con la `ZONA_HORARIA` de `app`.

    Falla al arrancar si la zona no existe (o si falta `tzdata` donde el
    sistema no tiene base de zonas, como en Windows), no al pintar la primera
    página.
    """
    zona = app.config['ZONA_HORARIA']
    try:
        ZoneInfo(zona)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise RuntimeError(
            f'ZONA_HORARIA no válida: {zona!r}. Usa un nombre de la base IANA, como Europe/Madrid '
            '(y comprueba que tzdata esté instalado).'
        ) from error

    @app.template_filter('fecha_local')
    def filtro_fecha_local(valor, hora=False):
        return fecha_local(valor, zona, con_hora=hora)
