# ADR-0004: Solicitudes en paralelo y estados de la mascota derivados del flujo

**Fecha**: 2026-11-15
**Estado**: aceptada
**Decisores**: propietario del proyecto, tras un comité de decisiones con revisión de arquitectura

## Contexto

Hoy la primera solicitud pasa la mascota a `en_proceso` y la saca del catálogo
(`app/routes/solicitudes.py:83` y, duplicado, `app/routes/api/solicitudes.py:90`).
Rechazarla no la devuelve a `disponible`, así que queda bloqueada para
siempre (P-01, crítica). Con varias pendientes, al aprobar una las demás se
quedan colgadas (P-05). Además, el admin puede cambiar el estado a mano y
saltarse el flujo (P-29). La escéptica señaló que P-01 y P-05 tienen la misma
causa: hay que fijar la regla completa antes de arreglar cualquiera de los dos.

## Decisión

Las solicitudes se admiten en paralelo y el estado de la mascota lo decide
solo el flujo:

- **Mascota:** `disponible` hasta que se aprueba una solicitud, y entonces
  pasa a `adoptado`. Mientras tiene solicitudes pendientes sigue en el
  catálogo con el aviso «Tiene solicitudes en curso», que se deriva del
  recuento de pendientes y no se guarda en la base de datos. El flujo deja
  de asignar `en_proceso`.
- **Aprobar** una solicitud adopta la mascota y rechaza automáticamente las
  demás pendientes, con un comentario estándar para cada adoptante.
- **Rechazar** solo cambia esa solicitud; la mascota no cambia.
- El admin solo puede cambiar el estado a mano a «Adoptada fuera del portal»,
  con los mismos efectos que una aprobación sobre las pendientes, o volver de
  ahí a `disponible`.
- La regla vive en una sola función de dominio, en `app/models.py` o un
  servicio, que usan tanto la web como la API. La aprobación bloquea la fila
  de la mascota (`SELECT … FOR UPDATE`) para que dos aprobaciones simultáneas
  no adopten dos veces.

Una migración de datos de Alembic adapta las filas existentes. Las mascotas
en `en_proceso` con una solicitud aprobada pasan a `adoptado`, y el resto a
`disponible`. Después se rechazan las solicitudes pendientes de todas las
mascotas adoptadas, con el comentario estándar y `revisado_por` vacío (las
cierra el sistema, no un admin). El downgrade devuelve a `en_proceso` las
mascotas disponibles con pendientes, pero no reabre esas solicitudes. El
esquema no cambia: el `CHECK` sigue admitiendo el valor.

## Alternativas consideradas

### Reserva exclusiva (corregir solo el rechazo)
- **A favor**: es el cambio mínimo.
- **En contra**: los demás interesados no pueden hacer nada mientras una
  solicitud está pendiente, y una solicitud vacía bloquea la mascota (P-04).
- **Por qué no**: para una protectora es peor tener menos solicitudes por
  animal.

### Cola por orden de llegada
- **A favor**: un orden justo y explícito.
- **En contra**: necesita migración de esquema (posición en la cola) y más
  pantallas, y la protectora no suele elegir por orden de llegada, sino por
  idoneidad.
- **Por qué no**: más coste por una regla que no refleja cómo se decide.

## Consecuencias

### Positivas
- Se resuelven P-01, P-05 y P-29, y se elimina la lógica duplicada entre la
  web y la API.
- Más solicitudes por animal, y el admin compara candidatos.

### Negativas
- El catálogo tiene que contar las pendientes, con una consulta agregada sin
  N+1 (`tests/test_rendimiento.py`).
- Hay que cambiar los textos y los estados que ve el adoptante (P-24).
- El valor `en_proceso` queda sin uso en el `CHECK` hasta una limpieza
  posterior.

### Riesgos
- **Aprobaciones concurrentes.** Mitigación: el bloqueo de fila y un test que
  aprueba dos solicitudes de la misma mascota.
- **La API cambia de comportamiento** (deja de devolver `en_proceso`).
  Mitigación: se documenta en el PR y en `docs/ARQUITECTURA.md`; el contrato
  de errores no cambia.
- **Retirar una solicitud (P-25) necesitaría un estado nuevo.** Queda fuera
  de esta ADR.
