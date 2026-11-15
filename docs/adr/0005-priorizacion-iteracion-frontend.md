# ADR-0005: Priorización de la iteración de mejora del frontend

**Fecha**: 2026-11-15
**Estado**: aceptada
**Decisores**: propietario del proyecto, tras un comité de decisiones con revisión de arquitectura

## Contexto

La auditoría deja 50 problemas (1 crítico, 14 altos, 28 medios y 7 bajos). Lo
más grave está en la lógica del flujo de adopción y en los formularios, y
ningún cambio de stack lo arregla. ADR-0001 a ADR-0004 fijan el stack, el
sistema de diseño, el almacenamiento y la regla de las solicitudes. Lo
desarrolla una sola persona, en PRs pequeños.

## Decisión

El orden es primero corrección, luego datos del usuario, luego la base visual y
por último la migración página a página:

1. **Dominio:** P-01, P-05 y P-29 (ADR-0004); P-04, validación del cuestionario
   en el servidor, compartida con la API; P-06 y P-10, revisión con
   confirmación y respuestas legibles; P-08.
2. **Que el usuario no pierda datos:**
   - P-02, formularios que conservan los valores;
   - P-03, páginas de error propias en español y CSRF del cuestionario sin
     caducidad de una hora;
   - P-07 (`next`);
   - P-09 y el almacenamiento (ADR-0003);
   - P-18 (seed coherente) y P-31 (especies normalizadas).
3. **Base del sistema de diseño (ADR-0002):** tokens, base CSS, macros,
   Bootstrap vendorizado para la fase intermedia y eliminación de los estilos
   inline (P-21, CSP sin `'unsafe-inline'`).
4. **Parte pública sin Bootstrap:** portada, catálogo, detalle, login,
   registro, cuestionario y solicitudes del adoptante. Cada página incluye su
   accesibilidad (P-12, P-13, P-16, P-17, P-34 a P-39, P-48), sus textos
   (P-24, P-26, P-27, P-41 a P-44) y sus e2e (P-40).
5. **Panel de administración sin Bootstrap:** P-23, P-28, P-45 y P-46, y se
   retira Bootstrap del proyecto.

**Fuera de esta iteración:**
- P-11, recuperar contraseña: necesita un proveedor de correo.
- P-25, retirar una solicitud: necesita un estado nuevo.
- P-30, filtros del catálogo en móvil: entra solo si sale gratis en la fase 4.
- P-47, ajustes de producción: la CDN desaparece con ADR-0001.
- P-33, la dirección que se pide en el registro y no se usa: en esta
  iteración solo pasa a «Opcional».
- P-49 y P-50, detalles menores.
- El modo oscuro.
- La adecuación al RGPD que señaló la voz crítica (política de privacidad,
  base legal y plazo de borrado de solicitudes), necesaria antes de un uso
  real pero ajena al frontend.

## Alternativas consideradas

### Primero lo visual
- **A favor**: el resultado se ve antes para el portfolio.
- **En contra**: se rediseñan pantallas cuyos estados cambian con ADR-0004, y
  el fallo crítico sigue vivo mientras tanto.
- **Por qué no**: las cinco voces coinciden en corregir primero.

### Dejar P-05 para otra iteración
- **A favor**: menos alcance (lo proponían la escéptica y la pragmática).
- **En contra**: P-01 y P-05 comparten causa, y arreglar solo P-01 obliga a
  migrar dos veces.
- **Por qué no**: el propietario ha decidido la regla (ADR-0004), así que ya
  no hay que adivinar la decisión de negocio.

## Consecuencias

### Positivas
- Los fallos que dañan el uso real desaparecen en los primeros PRs, que no
  dependen del rediseño.
- Las fases 1 y 2 tienen bloques independientes que pueden ir en paralelo.

### Negativas
- Algunas plantillas se tocan dos veces: en las fases 1 y 2 para la lógica, y
  en las fases 4 y 5 para el rediseño.
- El resultado visual llega al final de la iteración.

### Riesgos
- **Trabajo doble en el HTML.** Mitigación: en las fases 1 y 2, cambios
  mínimos en el marcado; la reescritura queda para cuando las macros existan.
- **Que el alcance crezca.** Mitigación: cada bloque tiene criterios de
  aceptación en `docs/plan-frontend.md`, y lo que surja fuera de ellos se
  apunta para otra iteración.
