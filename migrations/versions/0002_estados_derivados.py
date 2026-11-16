"""estados derivados

Migración de datos de la ADR-0004 (solicitudes en paralelo): el flujo deja de
usar `en_proceso`. El esquema no cambia; el CHECK sigue admitiendo el valor
para que el downgrade pueda restaurarlo, hasta una limpieza posterior.

- upgrade:
  1. Las mascotas `en_proceso` con una solicitud aprobada pasan a `adoptado`,
     y el resto a `disponible`.
  2. Invariante «adoptado ⇒ sin pendientes»: las solicitudes `pendiente` de
     cualquier mascota `adoptado` (venga de `en_proceso` o ya lo estuviera)
     pasan a `rechazada` con el comentario estándar, `fecha_revision` = ahora
     (UTC sin zona, como `utcnow()`) y `revisado_por` NULL (las cierra el
     sistema, no un admin).
- downgrade: las mascotas `disponible` con solicitudes pendientes vuelven a
  `en_proceso`. No se revierte nada más: las adopciones siguen en `adoptado`
  (con la regla antigua también lo estaban) y las solicitudes rechazadas por
  el paso 2 siguen rechazadas, porque no se distinguen de las demás.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15 16:14:54.589411

"""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

# Copia literal de app.adopciones.COMENTARIO_RECHAZO_AUTOMATICO: una migración
# no importa la app, que puede cambiar después. tests/test_migraciones.py
# comprueba que hoy coinciden.
COMENTARIO_RECHAZO_AUTOMATICO = (
    'Gracias por tu interés. Esta mascota ya ha encontrado un hogar, así que '
    'tu solicitud se ha cerrado. Te animamos a conocer a los demás animales del catálogo.'
)


def upgrade():
    op.execute(
        "UPDATE mascotas SET estado = 'adoptado' "
        "WHERE estado = 'en_proceso' AND EXISTS ("
        "SELECT 1 FROM solicitudes "
        "WHERE solicitudes.mascota_id = mascotas.id AND solicitudes.estado = 'aprobada')"
    )
    op.execute("UPDATE mascotas SET estado = 'disponible' WHERE estado = 'en_proceso'")

    ahora = datetime.now(UTC).replace(tzinfo=None)
    op.execute(
        sa.text(
            "UPDATE solicitudes SET estado = 'rechazada', comentarios_admin = :comentario, "
            "fecha_revision = :ahora, revisado_por = NULL "
            "WHERE estado = 'pendiente' AND mascota_id IN ("
            "SELECT id FROM mascotas WHERE estado = 'adoptado')"
        ).bindparams(
            sa.bindparam('comentario', COMENTARIO_RECHAZO_AUTOMATICO, type_=sa.Text()),
            sa.bindparam('ahora', ahora, type_=sa.DateTime()),
        )
    )


def downgrade():
    op.execute(
        "UPDATE mascotas SET estado = 'en_proceso' "
        "WHERE estado = 'disponible' AND EXISTS ("
        "SELECT 1 FROM solicitudes "
        "WHERE solicitudes.mascota_id = mascotas.id AND solicitudes.estado = 'pendiente')"
    )
