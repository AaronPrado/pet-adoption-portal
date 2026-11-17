# ADR-0001: Frontend renderizado en servidor con CSS propio, sin Bootstrap, migrado por fases

**Fecha**: 2026-11-15
**Estado**: aceptada
**Decisores**: propietario del proyecto, tras un comité de decisiones con revisión de arquitectura

## Contexto

El frontend usa Jinja2 con Bootstrap 5 por CDN porque lo exigía el proyecto de
clase. El objetivo ahora es que sea pieza de portfolio y que pueda usarlo una
protectora real. Lo mantiene una sola persona, y no se negocian la CSP estricta
sin JS inline, el CSRF en los POST, WCAG 2.2 AA, la API REST ni la cobertura de
ramas ≥ 95 %. La auditoría (`docs/auditoria-frontend.md`) muestra que 8 de los
10 problemas principales son de dominio o de formularios, y que la deuda visual
viene de usar Bootstrap sin tematizar (P-14, P-15, P-19, P-21, P-22).

## Decisión

Se mantienen el renderizado en servidor con Jinja2 y las rutas web actuales, y
Bootstrap se sustituye por CSS propio (ADR-0002) y JS vanilla de mejora
progresiva en `app/static/js/`, sin paso de build ni Node. La migración va por
fases: primero la parte pública y después el panel de administración, que
mientras tanto usa Bootstrap servido desde `app/static/vendor/` (no desde la
CDN). No se añaden htmx ni Alpine.js: solo entrarían con su propia ADR, ante un
caso concreto que lo justifique.

## Alternativas consideradas

### Jinja + Bootstrap tematizado con `--bs-*`
- **A favor**: 2-4 días, casi no rompe tests y el menú móvil y el desplegable
  siguen siendo accesibles sin trabajo extra.
- **En contra**: sigue pareciendo Bootstrap; para la dirección visual completa
  haría falta compilarlo con Sass.
- **Por qué no**: tres de las cinco voces consultadas votaron por esta opción,
  pero el propietario prioriza la calidad y la identidad para el portfolio. Su
  ventaja de seguridad (quitar la CDN) también se consigue en la fase
  intermedia vendorizando Bootstrap.

### SPA en React o Vue sobre la API
- **A favor**: es lo más vistoso en un portfolio.
- **En contra**: 20-25 días; ~8 endpoints nuevos (registro, sesión, CRUD de
  admin, revisión); hay que replantear la autenticación en el navegador,
  añadir SSR para el SEO del catálogo, meter Node en el Dockerfile y el CI, y
  rehacer ~1.500 líneas de tests. `test_accesibilidad.py` deja de servir.
- **Por qué no**: no resuelve ninguno de los 50 problemas y multiplica la
  superficie para una sola persona. Las cinco voces consultadas la descartan.

### CSS propio con htmx y/o Alpine.js
- **A favor**: interactividad parcial sin recargar la página.
- **En contra**: htmx inyecta estilos inline salvo que se configure, Alpine
  necesita su build CSP sin expresiones inline, y no hay hoy un problema que
  lo pida (`app.js` tiene 9 líneas).
- **Por qué no**: complejidad sin beneficio en esta iteración.

## Consecuencias

### Positivas
- La CSP queda en `'self'`, sin CDN y, tras P-21, sin `'unsafe-inline'` en
  `style-src`.
- `test_accesibilidad.py`, los tests de rutas y la API se mantienen.
- El HTML que se sirve es el que se prueba: todo funciona sin JS.

### Negativas
- Hay que reimplementar el menú móvil y el desplegable de usuario (unas 60
  líneas de JS) con foco, `Escape` y `aria-expanded` correctos.
- Durante la fase intermedia conviven dos capas de CSS: las páginas públicas
  heredan de una base nueva y las de administración de una base con Bootstrap.
- Unos 8-10 días de trabajo en 10-12 PRs, frente a 2-4 de la alternativa.
- Se rompen algunos selectores de los e2e (`.card`, `.dropdown`), que hay que
  actualizar en cada PR.

### Riesgos
- **Que el rediseño se coma la iteración.** Mitigación: el orden de ADR-0005
  (primero dominio y formularios) y PRs por grupo de páginas que se pueden
  entregar uno a uno.
- **Regresiones de accesibilidad en los componentes propios.** Mitigación:
  tests de teclado en Playwright para el menú y los diálogos, más una revisión
  de accesibilidad en cada PR de interfaz.
