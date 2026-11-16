"""normalizar especies

Migración de datos de P-31: la especie se escribía como texto libre y el
filtro del catálogo mostraba «Perro» y «perro» como opciones distintas. Desde
ahora `Mascota` la normaliza al guardar (`@validates('especie')`); esta
migración aplica el mismo criterio a las filas que ya existían. El esquema no
cambia.

- upgrade: cada especie pasa a su forma canónica: caracteres compuestos (NFC),
  sin invisibles de formato (Unicode Cf), sin espacios en los extremos, un
  solo espacio entre palabras y mayúscula solo en la primera letra
  (« PERRO » → «Perro», «cobaya DE Indias» → «Cobaya de indias»). Se hace en
  Python y no en SQL para que el resultado sea idéntico en PostgreSQL y en
  SQLite (`lower()` de SQLite no trata «Ñ» ni las tildes). Es idempotente.
  Si una especie quedaría vacía o con más de 50 caracteres (la longitud de la
  columna; «ß» pasa a «Ss»), no se cambia y se registra un aviso con su valor
  y los id de sus mascotas: hay que corregirlas a mano (docs/DESPLIEGUE.md).
- downgrade: no hace nada. La normalización es irreversible (no se guardó cómo
  estaba escrita cada especie), pero también inocua: el código anterior acepta
  las especies normalizadas.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16 13:43:13.487800

"""
import logging
import unicodedata

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

# Hijo del logger «alembic» de alembic.ini, para que fileConfig no lo desactive
logger = logging.getLogger('alembic.runtime.migration')

# Longitud de mascotas.especie (Mascota.LONGITUD_ESPECIE en la versión 0003)
LONGITUD_ESPECIE = 50


def normalizar_especie(especie):
    """
    Copia literal de app.models.Mascota.normalizar_especie: una migración no
    importa la app, que puede cambiar después. tests/test_migraciones.py
    comprueba que hoy coinciden.
    """
    especie = unicodedata.normalize('NFC', especie)
    especie = ''.join(c for c in especie if unicodedata.category(c) != 'Cf')
    return ' '.join(especie.split()).capitalize()


def upgrade():
    conexion = op.get_bind()
    especies = conexion.execute(sa.text('SELECT DISTINCT especie FROM mascotas')).scalars().all()
    for especie in especies:
        normalizada = normalizar_especie(especie)
        if normalizada == especie:
            continue
        if not normalizada or len(normalizada) > LONGITUD_ESPECIE:
            ids = conexion.execute(
                sa.text('SELECT id FROM mascotas WHERE especie = :especie ORDER BY id'),
                {'especie': especie},
            ).scalars().all()
            logger.warning(
                'Especie %r sin normalizar (quedaría vacía o con más de %d caracteres); '
                'corrígela a mano en las mascotas %s', especie, LONGITUD_ESPECIE, ids)
            continue
        # El WHERE por coincidencia exacta es seguro aunque varios valores
        # distintos («perro», « PERRO ») acaben en el mismo: cada UPDATE solo
        # toca las filas de su valor original, que la lista DISTINCT recoge una
        # vez, y el valor resultante ya está normalizado, así que si se vuelve
        # a encontrar se salta.
        conexion.execute(
            sa.text('UPDATE mascotas SET especie = :normalizada WHERE especie = :especie'),
            {'normalizada': normalizada, 'especie': especie},
        )


def downgrade():
    """Irreversible pero inocua: ver el docstring del módulo."""
