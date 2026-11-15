# Auditoría del frontend

Fecha: 15 de noviembre de 2026 · Estado de partida: `main` en `860233d`.

## Alcance y método

La auditoría la hicieron seis agentes en paralelo y en solo lectura, sobre la app
en local (`python run.py`, `FLASK_ENV=development`, CSRF activo) con los datos de
`scripts_bd/02_seed.sql`:

| Agente | Herramienta | Ámbito | Hallazgos |
|---|---|---|---|
| Usabilidad (`USA`) | `design:design-critique` (heurísticas de Nielsen) | Flujos completos de adoptante y admin | 28 |
| Funcionalidad (`FUN`) | `ecc:click-path-audit` | Cada botón, enlace y formulario, de principio a fin | 17 |
| QA en navegador (`QA`) | `ecc:browser-qa` | Consola, CSP, rendimiento, 375/768/1280 px, CSRF | 14 |
| Accesibilidad (`A11Y`) | agente `ecc:a11y-architect` | WCAG 2.2 AA sobre plantillas, CSS y JS | 22 |
| Diseño visual (`DIS`) | `ecc:design-system`, `ecc:make-interfaces-feel-better`, `frontend-design` | Tokens, componentes, estados, dirección visual | 23 |
| Textos (`TXT`) | `design:ux-copy` | Microcopy en español | 45 |
| **Total en bruto** | | | **149** |

Al deduplicarlos y agruparlos quedan **50 problemas** (`P-NN`). Cada uno
indica los hallazgos de origen; el detalle de cada hallazgo, con pasos para
reproducirlo y propuesta de solución, está en los anexos.

**Limitaciones**

- La revisión de accesibilidad es estática (código y contraste calculado);
  los puntos marcados «a verificar en navegador» siguen abiertos.
- No se usó Lighthouse (no hay Chrome estable instalado): las métricas salen
  de Playwright con un perfil equivalente (Slow 4G, CPU 4×).
- Los errores 429 (límite de login) y 400 por CSRF caducado se identificaron
  en el código y en las respuestas por defecto de Flask-Limiter y Flask-WTF.
  No se reprodujeron en vivo para no agotar el límite compartido entre agentes.
- Las capturas citadas en los anexos están en una carpeta temporal y no se
  incluyen en el repositorio.

## Resumen

| Gravedad | Problemas consolidados | Hallazgos en bruto |
|---|---|---|
| Crítica | 1 | 2 |
| Alta | 14 | 23 |
| Media | 28 | 67 |
| Baja | 7 | 57 |
| **Total** | **50** | **149** |

Lo más grave está en la **lógica del flujo de adopción**: estados de mascota y
solicitud incorrectos, validación del cuestionario y confirmaciones del admin.
Le siguen los **formularios que pierden lo escrito** y las **páginas de error
por defecto en inglés**. La parte técnica está sana: 0 errores de consola,
0 violaciones de CSP, CLS 0 y ningún desbordamiento horizontal. La deuda de
diseño es de coherencia (Bootstrap sin tematizar), no de roturas.

### Top 10 por impacto en el usuario

| # | Problema | Gravedad | Esfuerzo | Quién lo sufre |
|---|---|---|---|---|
| 1 | **P-01** Rechazar una solicitud deja la mascota «En proceso» para siempre y la saca del catálogo | Crítica | S | Mascotas que nadie puede volver a solicitar; el admin no puede deshacerlo desde la web |
| 2 | **P-02** Los formularios se vacían ante cualquier error (registro, login, alta y edición de mascota) | Alta | M | Todos los usuarios; además incumple WCAG 3.3.7 |
| 3 | **P-03** Páginas 404/405/500, CSRF caducado y 429 por defecto, en inglés y sin navegación | Alta | M | Quien tarda más de una hora en el cuestionario lo pierde entero |
| 4 | **P-04** El cuestionario no se valida en el servidor: un envío vacío se acepta y bloquea la mascota | Alta | M | Otros adoptantes y el admin |
| 5 | **P-05** Una solicitud bloquea la mascota para todos; con varias pendientes, al aprobar una las demás quedan colgadas | Alta | M | Adoptantes sin alternativa; el admin rechaza a mano |
| 6 | **P-06** Aprobar y rechazar con un solo clic, sin confirmación, y con el formulario visible en solicitudes ya resueltas | Alta | S | Admin: error irreversible con un clic |
| 7 | **P-07** Se pierde `next` al iniciar sesión o registrarse desde una mascota | Alta | S | Adoptante nuevo: acaba en la portada y pierde la mascota |
| 8 | **P-08** Editar una mascota sin foto o sin raza rellena «None» y no deja guardar | Alta | S | Admin |
| 9 | **P-09** Subir una foto sin S3 configurado da error 500 y se pierde el formulario | Alta | S | Admin (en entornos sin S3) |
| 10 | **P-10** Respuestas del cuestionario mostradas como códigos internos («8+», «espera») | Alta | S | Admin al decidir; adoptante al revisar su solicitud |

Les siguen las barreras de accesibilidad de los formularios (**P-12**
cuestionario sin `fieldset` y **P-13** bordes de campo con contraste de 1,3:1)
y la coherencia visual (**P-14**, **P-15**).

## Problemas consolidados

Esfuerzo: S (horas), M (1-2 días), L (más). Área: F = funcionalidad,
U = usabilidad, A = accesibilidad, V = diseño visual, T = textos,
R = rendimiento, Q = calidad/tests.

### Crítica

| ID | Problema | Esf. | Área | Hallazgos de origen |
|---|---|---|---|---|
| P-01 | `Solicitud.rechazar` no devuelve la mascota a `disponible`: queda «En proceso» y fuera del catálogo. El aviso de rechazo tampoco da contexto (`app/models.py:383`, `app/routes/solicitudes.py:207`) | S | F U T | USA-01, FUN-01, TXT-25 |

### Alta

| ID | Problema | Esf. | Área | Hallazgos de origen |
|---|---|---|---|---|
| P-02 | Los formularios pierden lo escrito tras un error de validación o de imagen; al editar se vuelve en silencio a los valores anteriores (`auth.py:70-151`, `mascotas.py:186-320`) | M | F U A | USA-04, USA-05, FUN-07, A11Y-01 |
| P-03 | Sin manejadores propios para 400 (CSRF), 403, 404, 405, 429 y 500: página de Werkzeug en inglés, `lang=en`, sin estilos ni salida. El token CSRF caduca a los 3600 s y el cuestionario es largo; el e2e comprueba el texto en inglés | M | F U A T | QA-01, TXT-01, TXT-02, TXT-03, FUN-11, USA-15, A11Y-14 |
| P-04 | El cuestionario no se valida en el servidor; acepta envíos vacíos o incoherentes y guarda «No» en lo no contestado | M | F U | FUN-05, USA-08 |
| P-05 | Modelo de solicitudes: la primera saca la mascota del catálogo y no hay cola ni alternativa. Con varias pendientes, al aprobar una las otras siguen «Pendiente» y no se pueden aprobar | M | F U | FUN-02, USA-02 |
| P-06 | Aprobar y rechazar sin confirmación ni motivo; la pantalla de revisión muestra el formulario en solicitudes resueltas; una acción desconocida redirige sin mensaje | S | F U A T | USA-06, USA-25, TXT-04, FUN-08, FUN-09, A11Y-17 |
| P-07 | `next` se pierde: «Inicia sesión para adoptar» no lo pasa, el login no lo conserva y el registro no inicia sesión | S | F U | USA-03, FUN-04 |
| P-08 | Editar una mascota sin foto o sin raza: el formulario muestra «None», no deja guardar y puede guardar «Raza: None» | S | F | FUN-03 |
| P-09 | Subir una foto válida sin S3 configurado da error 500 (TypeError) | S | F | FUN-06 |
| P-10 | Respuestas del cuestionario mostradas con valores internos y etiquetas telegráficas | S | U T | USA-10, TXT-05, TXT-38 |
| P-11 | No hay recuperación de contraseña (requiere envío de correo) | L | U | USA-07 |
| P-12 | Radios del cuestionario sin `fieldset`/`legend`; `label for="tiene_jardin"` apunta a un id inexistente | S | A | A11Y-02 |
| P-13 | Bordes de `form-control`/`form-select` con contraste de 1,30:1 y de checkbox/radio con 1,84:1 (WCAG 1.4.11 pide 3:1) | S | A | A11Y-03 |
| P-14 | Color sin sistema: el azul de Bootstrap `#0d6efd` convive con la paleta teal (`--bs-*` sin redefinir) y hay dos colores de texto base (`#023047` / `#212529`) | S | V | DIS-01, DIS-02 |
| P-15 | Botones fragmentados: 6 alturas, 4 radios, `!important` que rompe `btn-lg`, primaria y secundaria con el mismo peso, CTA a ancho completo | M | V | DIS-03, DIS-14, DIS-15 |

### Media

| ID | Problema | Esf. | Área | Hallazgos de origen |
|---|---|---|---|---|
| P-16 | Errores de formulario solo como flash arriba: sin `aria-invalid` ni `aria-describedby`, foco sin gestionar, todos los flash con `role="alert"` y fuera de `<main>`, instrucciones solo en placeholder | M | U A | USA-19, A11Y-04, A11Y-12, A11Y-16 |
| P-17 | Foco poco visible en campos y navbar: `.form-control:focus{outline:0}` de Bootstrap pisa el `:focus-visible` propio | S | A | QA-05 |
| P-18 | El cuestionario del seed usa claves distintas de las de la app (campos vacíos y «✗ No garantiza…»); otros datos del seed incoherentes | S | Q U | FUN-16, QA-06, USA-24 |
| P-19 | Componentes sin patrón: 5 variantes de tarjeta de mascota, `.card img {height:180px}` global, cabeceras, badges de estado, filtros segmentados y rejilla del catálogo desalineada | M | V | DIS-05, DIS-07, DIS-09, DIS-10, DIS-11, DIS-13, QA-13 |
| P-20 | Estados de interacción ausentes o anulados (hover, active, tarjetas) y sin estado de carga ni protección visual contra el doble envío | S | V U | DIS-04 |
| P-21 | 10 `style=` en línea y un `<style>` en `index.html` (mantienen `'unsafe-inline'` en `style-src`), y CSS muerto | S | V Q | DIS-06 |
| P-22 | Identidad y pulido: Arial con pesos que no existen, marca con emoji, placeholder sin foto de un tercero, radios y sombras sin tokens, ritmo vertical irregular, footer que no baja al fondo, alertas usadas como contenedor, sin base para modo oscuro | M | V | DIS-08, DIS-16 a DIS-23 |
| P-23 | Tablas de admin: en 375 px Estado y Acciones quedan fuera de la vista sin indicación; columna oculta a ≤ 768 px; sin `caption`, `scope` ni `aria-sort`; poco pulidas | M | U A V | QA-02, A11Y-09, A11Y-10, DIS-12 |
| P-24 | Estados sin «qué pasa ahora»: pendiente, aprobada, rechazada, ficha en proceso o adoptada y confirmación de envío vaga | S | U T | USA-12, TXT-14, TXT-15, TXT-17 |
| P-25 | El adoptante no puede retirar su solicitud, y el cuestionario no avisa de que no se puede modificar | M | U T | USA-13, TXT-16 |
| P-26 | Fechas y horas en UTC mostradas como locales | S | U T | USA-14, TXT-06 |
| P-27 | Cuestionario largo y con fallos de redacción: mezcla tú/usted, rangos de horas solapados, opciones de emergencia veterinaria mal redactadas, riesgo de pérdida | M | U T | USA-09, TXT-07, TXT-08, TXT-43 |
| P-28 | Orientación del admin: sin punto de entrada ni contador de pendientes; listado de solicitudes poco orientado a la tarea | S | U | USA-16, USA-17 |
| P-29 | Cambiar a mano el estado de una mascota en el formulario esquiva el flujo de solicitudes | M | F U | USA-18 |
| P-30 | Catálogo en móvil: los filtros ocupan la pantalla antes que las mascotas; no hay recuento de resultados | S | U | USA-20 |
| P-31 | Especie en texto libre: «Perro» y «perro» salen como dos opciones del filtro | S | F T | FUN-12, QA-11, TXT-44 |
| P-32 | Foto: archivo y URL a la vez sin regla visible; errores de foto sin causa ni solución | S | U T | USA-23, TXT-21, TXT-29 |
| P-33 | La dirección se pide como «necesaria para solicitudes», pero no se usa ni se puede completar después | M | U T | USA-11, TXT-23 |
| P-34 | Encabezados y títulos: sin `h1` en 12 de las 13 páginas, saltos de nivel, títulos de pestaña incoherentes y landmarks mejorables | M | A T | A11Y-11, A11Y-22, TXT-40 |
| P-35 | Enlaces: doce «Ver Detalles» idénticos, enlaces «aquí» y enlaces en el texto sin subrayado (contraste de 1,49:1 con el texto) | S | A T | A11Y-05, A11Y-06, TXT-26, TXT-42 |
| P-36 | Sin `autocomplete` en los campos personales ni de autenticación | S | A | A11Y-07 |
| P-37 | Filtros y paginación: el estado activo es solo visual (`aria-current` mal colocado o ausente) y el grupo no tiene nombre | S | A | A11Y-08, A11Y-15 |
| P-38 | Hero de inicio: texto blanco sobre foto sin contraste garantizado; es el LCP (1,96 s en móvil), una imagen de fondo de 150 KB de un tercero sin preload ni variantes | S | A R | A11Y-13, QA-03 |
| P-39 | Imágenes de mascotas sin `width`/`height`, `loading="lazy"` ni `srcset`; textos alternativos mejorables | S | R A | QA-04, A11Y-19 |
| P-40 | Los e2e cubren 6 flujos; faltan la revisión por el admin, el registro, el login fallido o 429, las páginas de error, la edición con foto y las tablas en móvil | M | Q | QA-14 |
| P-41 | Estados vacíos que culpan a filtros inexistentes, ignoran el filtro activo o muestran valores internos; parámetros inválidos sin aviso | S | U T | TXT-18, TXT-19, TXT-27, FUN-14 |
| P-42 | Coherencia del vocabulario: Title Case, el recorrido de adopción con cinco nombres, «Panel Admin», el mensaje al adoptante con tres nombres, concordancia de género, «Email»/«correo», calcos («exitosamente») | M | T | TXT-09 a TXT-13, TXT-33, TXT-37, TXT-45, USA-26 |
| P-43 | Microcopy puntual: confirmación de borrado, asterisco sin leyenda, regla de especie, placeholders como instrucciones, mensajes de Google, permiso denegado, login requerido, «Contacta al administrador» sin contacto, edad sin unidad, portada | S | T U | TXT-20, TXT-22, TXT-24, TXT-30 a TXT-32, TXT-34 a TXT-36, TXT-39, TXT-41, USA-28 |

### Baja

| ID | Problema | Esf. | Área | Hallazgos de origen |
|---|---|---|---|---|
| P-44 | Volver a solicitar una mascota ya solicitada dice «ya no está disponible» en vez de «ya tienes una solicitud» | S | U T | USA-21, QA-12 |
| P-45 | El admin ve «Solicitar adopción» y puede solicitar, pero no tiene «Mis solicitudes» | S | F U | USA-27, FUN-10 |
| P-46 | Se ofrece «Eliminar» en mascotas que no se pueden eliminar, sin alternativa | S | U T | USA-22, TXT-28 |
| P-47 | Producción: sin compresión ni caché larga para estáticos, CSS de CDN que bloquea el render y logo de Google de 33 KB | S | R | QA-07, QA-08, QA-09 |
| P-48 | Accesibilidad menor: emoji decorativos leídos, `.step-number` con contraste justo, reflow a 320 px por verificar | S | A | A11Y-18, A11Y-20, A11Y-21 |
| P-49 | Detalles funcionales: la edad 0 no se muestra, los filtros del panel pierden el orden, «Volver al catálogo» pierde los filtros, ordenación sin desempate (riesgo) | S | F | FUN-13, FUN-15, FUN-17 |
| P-50 | La API devuelve 404 en HTML cuando el id no es numérico (fuera del frontend web; se anota para el bloque de errores) | S | Q | QA-10 |

## Lo que funciona bien

- Probadas 21 URLs × 3 viewports × 3 roles: 0 errores de JavaScript, 0 avisos
  de consola, 0 violaciones de CSP, 0 peticiones fallidas y SRI correcto en
  Bootstrap.
- CLS 0 y TBT 0 en todas las páginas, también con CPU 4×; INP del menú móvil
  de 16 ms.
- Ningún desbordamiento horizontal a 375, 768 y 1280 px. Menú móvil y «Saltar
  al contenido» funcionan.
- Tras cerrar sesión, «Atrás» no muestra contenido privado; los formularios
  con CSRF válido funcionan.
- Los permisos (adoptante en rutas admin, solicitudes ajenas) y la
  prevención de doble adopción en el servidor funcionan. Los e2e existentes
  pasan 6/6.

## Direcciones visuales (para el comité)

Las propuso el agente de diseño (detalle en el anexo D):

- **A. Evolucionar:** paleta actual y Bootstrap, con los tokens conectados a
  `--bs-*` y los componentes unificados en macros. Coherencia sin identidad
  nueva. 2-4 días.
- **B. «Ficha de acogida»:** el animal como protagonista, con paleta verde
  pino y amarillo collar y tipografía display para los nombres. Requiere
  compilar Bootstrap con Sass. 1,5-2 semanas.
- **C. Sistema propio sin Bootstrap en la parte pública:** maquetación
  editorial, modo oscuro y CSP sin `'unsafe-inline'`. 3-5 semanas, riesgo alto.

El agente recomienda A como primer paso, porque sirve de base para B o C.

## Datos de prueba creados durante la auditoría

En la base de datos local (no en el seed) quedan:

- Usuarios: `usabilidad-1@test.local`, `func-1@test.local`, `func-2@test.local`,
  `func-3@test.local` y dos `qa-<timestamp>@test.local`.
- Mascotas 9 («UsaPrueba») y 10-12 (`QA-Func-A/B/C`) con sus solicitudes. La
  web no deja borrarlas porque tienen solicitudes, y varias están bloqueadas
  «En proceso» por P-01.
- Una solicitud real de un usuario `qa-*` sobre Lys (mascota 8 del seed), que
  la ha sacado del catálogo.

Para volver al estado del seed: `docker compose down -v`, `docker compose up -d`,
`flask --app run db upgrade` y cargar `scripts_bd/02_seed.sql` de nuevo.

## Línea base de métricas («antes»)

Medidas con Playwright en frío (caché desactivada, contexto nuevo por página).
\*Perfil «móvil»: 375×812, red tipo Slow 4G de Lighthouse (RTT 150 ms, 1,6 Mbps) + CPU 4×. «Escritorio»: 1350×900 sin throttling.
INP aproximado = duración del evento al pulsar el botón hamburguesa (en escritorio no aplica).
Peso = bytes transferidos (`encodedDataLength`), sin compresión porque Werkzeug no comprime.

| Página | Rol | LCP móvil* (ms) | Elemento LCP | FCP móvil (ms) | CLS | TBT (ms) | INP toggler (ms) | Peso frío (KB) | Imágenes (KB) | Peticiones | LCP escritorio (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| inicio (`/`) | anon | 1964 | DIV.hero-home text-center mb-5 | 1020 | 0 | 0 | 16 | 331.1 | 266.9 | 9 | 144 |
| catalogo (`/mascotas/catalogo`) | anon | 1352 | H2 | 1352 | 0 | 0 | 16 | 294.3 | 230.2 | 12 | 108 |
| detalle-mascota (`/mascotas/1`) | anon | 896 | IMG unsplash/photo-1558788353-f76d92427f16 | 880 | 0 | 0 | 16 | 108.7 | 37.1 | 6 | 120 |
| login (`/auth/login`) | anon | 664 | A.navbar-brand | 664 | 0 | 0 | 16 | 91.8 | 33.5 | 6 | 124 |
| inicio-adoptante (`/`) | adoptante | 2032 | DIV.hero-home text-center mb-5 | 1156 | 0 | 0 | 16 | 344.8 | 266.8 | 9 | 156 |
| nueva-solicitud (`/solicitudes/nueva/1`) | adoptante | 672 | DIV.alert alert-info | 672 | 0 | 0 | 16 | 66.2 | 0.0 | 5 | 128 |
| mis-solicitudes (`/solicitudes/mis-solicitudes`) | adoptante | 860 | IMG unsplash/photo-1505628346881-b72b27e84530 | 760 | 0 | 0 | 16 | 108.9 | 47.5 | 6 | 124 |
| detalle-solicitud (`/solicitudes/detalle/1`) | adoptante | 908 | IMG unsplash/photo-1505628346881-b72b27e84530 | 880 | 0 | 0 | 16 | 122.1 | 47.5 | 6 | 140 |
| admin-mascotas (`/mascotas/admin`) | admin | 608 | H2 | 608 | 0 | 0 | 16 | 99.0 | 0.0 | 5 | 136 |
| admin-mascota-nueva (`/mascotas/admin/nueva`) | admin | 708 | A.navbar-brand | 708 | 0 | 0 | 16 | 76.3 | 0.0 | 5 | 124 |
| admin-mascota-editar (`/mascotas/admin/editar/1`) | admin | 744 | A.navbar-brand | 744 | 0 | 0 | 16 | 101.4 | 37.1 | 6 | 116 |
| admin-solicitudes (`/solicitudes/admin`) | admin | 716 | H2 | 716 | 0 | 0 | 16 | 81.6 | 0.0 | 5 | 112 |
| admin-revisar (`/solicitudes/admin/revisar/2`) | admin | 788 | IMG unsplash/photo-1558788353-f76d92427f16 | 748 | 0 | 0 | 16 | 98.0 | 37.1 | 6 | 136 |
| admin-detalle-solicitud (`/solicitudes/detalle/3`) | admin | 800 | IMG unsplash/photo-1568572933382-74d440642117 | 776 | 0 | 0 | 16 | 95.9 | 34.5 | 6 | 112 |

Notas de interpretación (desarrollo vs. producción):
- TTFB local ≈ 3–15 ms; en producción (gunicorn + red real) el TTFB subirá y todo el LCP se desplaza en consecuencia.
- Ningún LCP supera 2,5 s en este perfil, pero **inicio está a ~0,5 s del umbral** (1,96–2,03 s) y depende de una
  imagen de fondo de 150 KB en un tercero (ver QA-03).
- Peso dominado por imágenes de Unsplash (inicio 267 KB de 331 KB; catálogo 230 KB de 294 KB).
- Werkzeug no comprime (HTML de `/mascotas/admin` = 47 KB) y sirve `/static` con `Cache-Control: no-cache`; gunicorn
  en producción se comportaría igual porque no hay compresión ni caché configuradas en la app (ver QA-07).
- Peticiones por página: 5–12 (HTML, Bootstrap CSS+JS de jsDelivr, styles.css, app.js e imágenes).

## Anexos: informes completos de los agentes

Se reproducen sin cambios. Las rutas a capturas y scripts apuntan a la carpeta temporal de la sesión de auditoría.

---

## Anexo A · Usabilidad


Agente: Usabilidad · Fecha: 2026-11-15 · Método: `design:design-critique` + 10 heurísticas de Nielsen
aplicadas sobre recorridos reales con Playwright (Chromium, 1366×900 y 390×844) contra
http://localhost:5000 con datos del seed.

- Capturas: `<carpeta-auditoria>/usabilidad/capturas/`
  (en adelante `capturas/`).
- Scripts reproducibles: `fase_a.py` (anónimo + registro) y `fase_b.py` (admin, adoptante, revisión) en la misma carpeta.
- Logins usados: 3 (admin, juan.perez, usuario propio); estado guardado en `estado/`.

### Datos creados durante la auditoría (no son del seed)

| Qué | Detalle |
|---|---|
| Usuario | `usabilidad-1@test.local` (adoptante) |
| Mascota | id 9 «UsaPrueba» (Hurón). Queda en `en_proceso` y oculta del catálogo por el hallazgo USA-01 |
| Solicitud | #4 del usuario anterior sobre la mascota 9, **rechazada** por el admin (sin comentario) |

No se ha aprobado/rechazado ni editado nada del seed (solo se abrieron por GET `revisar/1` y `revisar/2`).

---

### Resumen de la crítica (design-critique)

**Impresión general.** El portal comunica bien su propósito (hero + catálogo con fotos grandes) y los
flujos felices funcionan, pero el ciclo de vida de una adopción está incompleto: el sistema no informa ni
guía al usuario en los estados intermedios (pendiente, rechazada, en proceso), pierde contexto y datos
en los errores y el panel admin permite decisiones irreversibles sin salvaguardas. El problema más grave
es de flujo: rechazar una solicitud deja a la mascota bloqueada para siempre.

**Jerarquía visual.**
- Lo primero que se ve: en escritorio, el hero/las fotos (correcto). En móvil, el catálogo muestra solo el
  bloque de filtros en todo el primer viewport (incorrecto: el contenido son las mascotas).
- En el detalle de mascota el CTA principal está bien destacado cuando existe; cuando no existe (en proceso
  / adoptado) la página termina sin ninguna acción.
- En la revisión admin, «Aprobar» y «Rechazar» tienen el mismo peso y tamaño, pegados, sin confirmación.

**Lo que funciona bien.**
- Catálogo claro, tarjetas escaneables, filtros con etiquetas y botón «Limpiar filtros»; estado vacío con salida.
- Botones «← Volver a …» contextuales en todas las vistas de detalle.
- Mensajes flash tras cada acción (registro, envío, rechazo) y redirección a «Mis solicitudes» tras enviar.
- Control de permisos con mensaje comprensible (adoptante en panel admin, solicitud ajena).
- `login_required` conserva `next` cuando se entra por URL protegida.
- El cuestionario está agrupado en secciones con encabezados y marca los obligatorios con `*`.

---

### Hallazgos

Formato: pantalla/archivo:línea · problema · impacto · evidencia · heurística · gravedad · esfuerzo · propuesta.

#### Crítica

##### USA-01 — Rechazar una solicitud deja a la mascota «En proceso» para siempre
- **Dónde:** `app/models.py:383-395` (`Solicitud.rechazar` no toca la mascota); `app/routes/solicitudes.py:449-451`; `app/routes/solicitudes.py:325` (al solicitar se marca `en_proceso`).
- **Problema:** al crear la solicitud la mascota pasa a `en_proceso` y desaparece del catálogo; al rechazarla no vuelve a `disponible`. El flash solo dice «Solicitud rechazada.» sin avisar de que la mascota sigue bloqueada.
- **Impacto:** cada rechazo saca silenciosamente a una mascota del catálogo público; ningún otro adoptante puede solicitarla. El admin solo lo descubre si revisa el listado y edita el estado a mano (y nada se lo indica).
- **Evidencia:** `fase_b.py` → mascota 9 tras rechazar la solicitud #4: badge «En proceso de adopción», 0 apariciones en el catálogo. Capturas `capturas/d02_admin_tras_rechazar.png`, `capturas/d03_mascota_tras_rechazo.png`, `capturas/d05_usuario_mascota_tras_rechazo.png`.
- **Heurística:** #1 Visibilidad del estado del sistema; #5 Prevención de errores; #2 Coincidencia con el mundo real.
- **Gravedad:** crítica · **Esfuerzo:** S
- **Propuesta:** en `rechazar()`, si la mascota no tiene otras solicitudes pendientes, volver a `disponible`; mostrar en el flash el nuevo estado («Toby vuelve a estar disponible en el catálogo»). Añadir test.

#### Alta

##### USA-02 — Una sola solicitud bloquea la mascota para todos, sin cola ni alternativa
- **Dónde:** `app/routes/solicitudes.py:322-329`; `app/templates/mascotas/detalle.html:196-211`.
- **Problema:** la primera solicitud (aunque sea de baja calidad, ver USA-08) retira la mascota del catálogo. Otros interesados ven «En proceso de adopción» sin poder solicitar, apuntarse a una lista ni recibir aviso.
- **Impacto:** el refugio pierde candidatos; el admin no puede comparar solicitudes; un adoptante poco serio bloquea la mascota hasta que se revise.
- **Evidencia:** `capturas/a05_detalle_en_proceso.png` (Toby: la página termina sin acción). Paso: solicitar cualquier mascota → desaparece de `/mascotas/catalogo`.
- **Heurística:** #3 Control y libertad; #7 Flexibilidad.
- **Gravedad:** alta · **Esfuerzo:** M
- **Propuesta:** decisión de producto: o bien admitir varias solicitudes pendientes por mascota (estado `en_proceso` solo al aprobar/preseleccionar), o bien ofrecer en el detalle «Avísame si vuelve a estar disponible» y enlace a mascotas similares.

##### USA-03 — Se pierde el contexto al iniciar sesión o registrarse desde una mascota
- **Dónde:** `app/templates/mascotas/detalle.html:206` (enlace a `auth.login` sin `next`); `app/routes/auth.py:101-102` (tras registrarse redirige a login, sin `next` ni inicio de sesión automático); `app/routes/auth.py:158-162`.
- **Problema:** el usuario anónimo pulsa «Inicia sesión para adoptar» en la ficha de Lys, inicia sesión y aterriza en la portada; si no tenía cuenta, el CTA ni siquiera ofrece registrarse y, tras registrarse, vuelve a login y luego a la portada.
- **Impacto:** el embudo principal (ver mascota → solicitar) se rompe justo en el punto de conversión; el usuario tiene que volver a buscar la mascota (3-5 clics extra).
- **Evidencia:** `fase_a.py` → `CTA anónimo href: /auth/login`; `fase_b.py` → login desde `/mascotas/9` termina en `http://localhost:5000/` (`capturas/c01_tras_login_desde_detalle.png`); `capturas/a12_tras_registro.png`.
- **Heurística:** #6 Reconocer antes que recordar; #7 Eficiencia; #3 Control.
- **Gravedad:** alta · **Esfuerzo:** S
- **Propuesta:** `url_for('auth.login', next=url_for('solicitudes.nueva', mascota_id=...))`; propagar `next` a registro y, tras registrarse, iniciar sesión automáticamente y redirigir a `next`. Añadir «¿No tienes cuenta? Regístrate» bajo el CTA.

##### USA-04 — El formulario de registro se vacía al fallar la validación
- **Dónde:** `app/routes/auth.py:69-79` y `104-108` (`render_template` sin datos); `app/templates/auth/registro.html:80-125` (inputs sin `value`).
- **Problema:** con contraseñas que no coinciden se borran email, nombre, apellidos, teléfono y dirección.
- **Impacto:** hay que reescribir 7 campos por un error en uno; abandono en el alta.
- **Evidencia:** `capturas/a11_registro_error_datos_perdidos.png`; `fase_a.py` imprime `valores tras error: ['', '', '', '']`.
- **Heurística:** #5 Prevención de errores; #9 Ayudar a recuperarse de errores.
- **Gravedad:** alta · **Esfuerzo:** S
- **Propuesta:** pasar `request.form` a la plantilla y rellenar `value` (excepto contraseñas); validar coincidencia de contraseñas también en cliente; mostrar el error junto al campo.

##### USA-05 — Alta y edición de mascota pierden lo escrito ante cualquier error
- **Dónde:** `app/routes/mascotas.py:185-218` (alta: `mascota=None`), `:204` y `:301` (`redirect(request.url)` si la imagen no es válida), `:282-320` (edición: se re-renderiza con los valores de BD, no con los editados); `app/__init__.py:170-174` (413 también redirige).
- **Problema:** una descripción de 5 caracteres (el HTML no tiene `minlength`) devuelve el formulario vacío; en edición se descartan los cambios; una foto demasiado grande o con formato no permitido vacía todo.
- **Impacto:** el personal del refugio reescribe la ficha completa; riesgo de abandonar el alta o de publicar fichas incompletas.
- **Evidencia:** `capturas/b08_admin_nueva_error_datos_perdidos.png`; `fase_b.py` → `tras error alta: ['La descripción debe tener al menos 10 caracteres.'] ['', '', '', '']`.
- **Heurística:** #5 Prevención de errores; #9 Recuperación de errores.
- **Gravedad:** alta · **Esfuerzo:** M
- **Propuesta:** re-renderizar con los valores enviados (objeto de formulario o Flask-WTF); `minlength="2"`/`minlength="10"` en el HTML; nunca `redirect` tras error de validación.

##### USA-06 — Aprobar/rechazar es irreversible y no pide confirmación ni motivo
- **Dónde:** `app/templates/solicitudes/admin/revisar.html:244-251`; `app/routes/solicitudes.py:438-453`.
- **Problema:** dos botones grandes contiguos, del mismo tamaño, envían la decisión al primer clic; el comentario es opcional también al rechazar. No hay deshacer.
- **Impacto:** un clic equivocado adopta la mascota a la persona incorrecta (y la marca `adoptado`) o rechaza sin explicación; el adoptante recibe «Rechazada» sin motivo (`capturas/d04_mis_solicitudes_rechazada.png`).
- **Evidencia:** `fase_b.py` → `diálogos de confirmación al rechazar: []`; `capturas/d01_admin_revisar_propia.png`, `capturas/d02_admin_tras_rechazar.png`.
- **Heurística:** #5 Prevención de errores; #3 Control y libertad.
- **Gravedad:** alta · **Esfuerzo:** S
- **Propuesta:** `data-confirmar` (ya existe en `app.js`) con texto específico («¿Aprobar la adopción de Toby por Juan Pérez? La mascota pasará a Adoptada»); comentario obligatorio al rechazar; separar visualmente los botones.

##### USA-07 — No existe recuperación de contraseña
- **Dónde:** `app/templates/auth/login.html` (sin enlace); `app/routes/auth.py` (sin ruta).
- **Problema:** no hay «¿Olvidaste tu contraseña?» ni ningún camino alternativo salvo Google.
- **Impacto:** un adoptante con solicitudes en curso que olvida la contraseña pierde el acceso a su seguimiento; único recurso: contactar al refugio por fuera (y la web no da contacto).
- **Evidencia:** `capturas/a09_login.png`.
- **Heurística:** #9 Ayudar a recuperarse de errores; #10 Ayuda.
- **Gravedad:** alta · **Esfuerzo:** L (requiere envío de correo y token)
- **Propuesta:** flujo de restablecimiento por email con token caducable; mientras tanto, al menos un texto con el contacto del refugio.

#### Media

##### USA-08 — El cuestionario acepta respuestas incoherentes o vacías de contenido
- **Dónde:** `app/routes/solicitudes.py:298-311` (sin validación de servidor); `app/templates/solicitudes/nueva.html:74-78` y `121-149`.
- **Problema:** se aceptan «No tiene otras mascotas» + «Un gato de 3 años», «x» como experiencia y motivo, y «No puedo garantizarlo» en ambos compromisos; tampoco hay validación de servidor de los obligatorios.
- **Impacto:** el admin recibe solicitudes inservibles que, además, bloquean la mascota (USA-02); el adoptante no sabe que su respuesta le descalifica.
- **Evidencia:** `capturas/c09_detalle_solicitud_usuario.png` (solicitud #4 enviada con esas respuestas); `fase_b.py` → «¡Solicitud enviada con éxito…».
- **Heurística:** #5 Prevención de errores.
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** validar en servidor obligatorios y longitudes mínimas (p. ej. 30 caracteres en texto libre con contador); mostrar «Si tiene mascotas…» solo si se marca «Sí»; si se marca «No puedo garantizarlo», avisar en línea de lo que implica antes de enviar.

##### USA-09 — Carga cognitiva y riesgo de pérdida en el cuestionario
- **Dónde:** `app/templates/solicitudes/nueva.html` (completo; `:161-169` botones).
- **Problema:** 12 preguntas en una página larga sin indicar duración ni progreso; los compromisos son radios con una opción negativa en vez de casillas de aceptación; no se pre-rellenan datos ya conocidos (teléfono, dirección); «Cancelar» tiene el mismo peso que «Enviar» y descarta todo sin aviso; no hay borrador.
- **Impacto:** fatiga y abandono, especialmente en móvil (`capturas/c05_cuestionario_movil.png`); pérdida de respuestas largas por un clic en Cancelar o caducidad de sesión.
- **Evidencia:** `capturas/c04_cuestionario.png`.
- **Heurística:** #8 Diseño minimalista; #5 Prevención de errores; #6 Reconocer antes que recordar.
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** texto inicial «5 minutos · 3 secciones»; compromisos como checkbox obligatorios; Cancelar como enlace secundario con confirmación si hay cambios; guardar borrador en `localStorage` por mascota.

##### USA-10 — Las respuestas se muestran como códigos internos
- **Dónde:** `app/templates/solicitudes/detalle.html:389-393`; `app/templates/solicitudes/admin/revisar.html:194-195`.
- **Problema:** «Horas solo al día: 8+», «Emergencia veterinaria: espera» / «consulta» / «veterinario» en lugar de la frase que eligió el usuario.
- **Impacto:** el admin interpreta mal la respuesta clave para decidir («espera» ¿a qué?); el adoptante no reconoce lo que respondió.
- **Evidencia:** `capturas/c09_detalle_solicitud_usuario.png`.
- **Heurística:** #2 Coincidencia con el mundo real; #4 Consistencia.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** diccionario de etiquetas compartido entre formulario y vistas (o filtro Jinja); destacar en revisión las respuestas de riesgo (>8 h solo, «Esperaría», compromisos en «No»).

##### USA-11 — La dirección se pide como «necesaria» pero nunca se usa ni se puede completar después
- **Dónde:** `app/templates/auth/registro.html:107-112`; ninguna plantilla muestra `direccion` (grep vacío); no hay página de perfil.
- **Problema:** el registro dice «Necesaria para solicitudes de adopción» pero es opcional, no se pide al solicitar y el admin no la ve al revisar. Los usuarios de Google no tienen teléfono ni dirección y no pueden añadirlos.
- **Impacto:** el admin no tiene datos para contactar o valorar la vivienda; mensaje engañoso para el usuario.
- **Evidencia:** `capturas/a10_registro.png`, `capturas/b04_admin_revisar_seed.png` (solicitante sin dirección).
- **Heurística:** #2 Coincidencia con el mundo real; #4 Consistencia.
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** página «Mi perfil»; en el cuestionario, bloque «Tus datos de contacto» pre-rellenado y editable; mostrar dirección y teléfono en revisión.

##### USA-12 — Estados sin «qué pasa ahora» (pendiente, aprobada, rechazada, en proceso)
- **Dónde:** `app/templates/solicitudes/mis_solicitudes.html:207-236`; `app/templates/mascotas/detalle.html:140-146` y `196-211`.
- **Problema:** «Pendiente de revisión» sin plazo orientativo; «¡Aprobada!» sin próximos pasos (recogida, contacto, documentación); «Rechazada» sin sugerencia de alternativa; en la ficha de una mascota que el propio usuario ha solicitado solo aparece «En proceso de adopción», sin «Tu solicitud está pendiente · Ver».
- **Impacto:** incertidumbre y consultas al refugio; el usuario aprobado no sabe cómo seguir.
- **Evidencia:** `capturas/c08_mis_solicitudes_pendiente.png`, `capturas/d04_mis_solicitudes_rechazada.png`, `capturas/c10_detalle_mascota_tras_solicitar.png`, `capturas/e01_juan_mis_solicitudes.png`.
- **Heurística:** #1 Visibilidad del estado; #10 Ayuda.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** texto de ayuda por estado (plazo medio, contacto del refugio, enlace al catálogo tras rechazo); en el detalle de mascota, aviso con enlace a la solicitud propia.

##### USA-13 — No se puede retirar una solicitud
- **Dónde:** `app/routes/solicitudes.py` (sin ruta); `app/templates/solicitudes/mis_solicitudes.html`, `detalle.html`.
- **Problema:** el adoptante que cambia de opinión no puede cancelar; la mascota queda bloqueada (USA-02) hasta que el admin la rechace (y entonces sigue bloqueada, USA-01).
- **Impacto:** bloqueos innecesarios y trabajo extra para el admin.
- **Evidencia:** `capturas/c08_mis_solicitudes_pendiente.png` (solo «Ver Detalles»).
- **Heurística:** #3 Control y libertad del usuario.
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** acción «Retirar solicitud» (con confirmación) mientras esté pendiente, que libere la mascota.

##### USA-14 — Las horas se muestran en UTC como si fueran locales
- **Dónde:** `app/templates/solicitudes/detalle.html:318` y `:323`; `mis_solicitudes.html:220`, `:227`; `admin/lista.html:74`.
- **Problema:** solicitud enviada a las 14:53 (CET) aparece «a las 13:53». Cerca de medianoche, la fecha también es errónea.
- **Impacto:** confusión sobre cuándo se envió/revisó; desconfianza en el sistema.
- **Evidencia:** `capturas/c09_detalle_solicitud_usuario.png` («15/11/2026 a las 13:53»; `date` local: 14:54 CET).
- **Heurística:** #2 Coincidencia con el mundo real.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** filtro Jinja que convierta a `Europe/Madrid` (zoneinfo) antes de formatear.

##### USA-15 — Páginas de error genéricas, en inglés y sin navegación
- **Dónde:** `app/__init__.py` (solo hay manejador para 413).
- **Problema:** `/mascotas/99999` devuelve la página 404 por defecto de Werkzeug («Not Found… check your spelling»), sin cabecera, ni enlace al catálogo.
- **Impacto:** el usuario que llega por un enlace viejo a una mascota borrada/adoptada queda en un callejón sin salida.
- **Evidencia:** `capturas/a07_404.png`.
- **Heurística:** #9 Recuperación de errores; #4 Consistencia.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** plantillas 404/403/500 que extiendan `base.html`, en español, con enlace a «Ver mascotas disponibles».

##### USA-16 — Orientación del admin: sin punto de entrada ni indicación de pendientes
- **Dónde:** `app/routes/auth.py:158-162` (admin aterriza en la portada pública); `app/templates/base.html:46-74` (paneles escondidos en el desplegable con el nombre); `base.html:35-41` (solo Inicio y Mascotas marcan página actual).
- **Problema:** tras iniciar sesión el admin ve la portada de adoptantes; para trabajar debe abrir un desplegable con su nombre; ningún sitio indica cuántas solicitudes esperan revisión; en las páginas admin y «Mis solicitudes» ningún elemento del menú aparece como activo.
- **Impacto:** clics extra en cada sesión; solicitudes pendientes que pasan desapercibidas (y bloquean mascotas).
- **Evidencia:** `capturas/b01_admin_mascotas.png`, `capturas/b02_admin_solicitudes.png`; `fase_b.py` → login admin redirige a `/`.
- **Heurística:** #1 Visibilidad del estado; #6 Reconocer antes que recordar; #7 Eficiencia.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** redirigir admin a `/solicitudes/admin?estado=pendiente`; enlaces «Solicitudes (N)» y «Mascotas» visibles en la barra para admin; «Mis solicitudes» visible en la barra para adoptantes; `aria-current`/clase activa en todas las secciones.

##### USA-17 — Listado de solicitudes poco orientado a la tarea
- **Dónde:** `app/templates/solicitudes/admin/lista.html:20-37` y `:86-105`.
- **Problema:** por defecto muestra «Todas» (la tarea es revisar pendientes); los filtros no muestran contadores; no se puede ordenar; la acción «Revisar» es un icono de check en círculo que se lee como «Aprobar» (solo `title` como pista); desde el panel de mascotas no se llega a las solicitudes de una mascota «En Proceso».
- **Impacto:** el admin duda antes de pulsar el check; tiene que filtrar en cada visita; no puede saber qué solicitud mantiene una mascota en proceso.
- **Evidencia:** `capturas/b02_admin_solicitudes.png`, `capturas/b03_admin_solicitudes_pendientes.png`, `capturas/b01_admin_mascotas.png`.
- **Heurística:** #7 Eficiencia; #2 Coincidencia con el mundo real; #6 Reconocer.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** filtro por defecto «Pendientes (N)»; botón con texto «Revisar»; en la tabla de mascotas, enlace del badge «En Proceso» a su solicitud.

##### USA-18 — La edición manual del estado de la mascota esquiva el flujo de solicitudes
- **Dónde:** `app/templates/mascotas/admin/form.html:269-281`; `app/routes/mascotas.py:331`.
- **Problema:** el admin puede pasar una mascota de «En Proceso» a «Disponible» o «Adoptado» sin aviso de que hay una solicitud pendiente/aprobada; es además la única forma de reparar USA-01.
- **Impacto:** estados incoherentes (mascota disponible con solicitud pendiente; adoptada sin adoptante) que confunden a adoptantes y al propio admin (ver USA-24 en el seed).
- **Evidencia:** `capturas/b10_admin_editar.png`.
- **Heurística:** #5 Prevención de errores; #1 Visibilidad.
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** mostrar junto al selector las solicitudes asociadas y pedir confirmación si el cambio contradice una solicitud; idealmente, derivar el estado de las solicitudes.

##### USA-19 — Errores de formulario solo como flash en la parte superior
- **Dónde:** `auth/registro.html`, `mascotas/admin/form.html`, `solicitudes/nueva.html` (sin `is-invalid`/`invalid-feedback`); rutas en `auth.py:69-79`, `mascotas.py:185-218`.
- **Problema:** el error aparece arriba, lejos del campo (en el formulario de mascota, a una pantalla de distancia), sin marcar el campo; los requisitos (nombre ≥ 2, contraseña ≥ 8 en registro está, descripción ≥ 10 solo como texto) no se validan en cliente.
- **Impacto:** el usuario tiene que buscar qué campo falla; ciclos de envío-error repetidos.
- **Evidencia:** `capturas/b08_admin_nueva_error_datos_perdidos.png`, `capturas/a11_registro_error_datos_perdidos.png`.
- **Heurística:** #9 Recuperación de errores; #5 Prevención.
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** errores por campo con clases de Bootstrap; atributos `minlength`/`pattern` coherentes con el servidor; foco en el primer campo erróneo.

##### USA-20 — Catálogo: en móvil los filtros tapan las mascotas; sin recuento de resultados
- **Dónde:** `app/templates/mascotas/catalogo.html:14-62`; `app/routes/mascotas.py:51-56`.
- **Problema:** a 390 px el bloque de filtros ocupa todo el primer viewport y no se ve ninguna mascota; no se indica cuántas mascotas coinciden; el filtro de edad excluye en silencio las mascotas sin edad registrada.
- **Impacto:** primera impresión en móvil de «formulario», no de «mascotas»; el usuario no sabe si el filtro ha funcionado.
- **Evidencia:** `capturas/a13_catalogo_movil.png`, `capturas/a02_catalogo.png`.
- **Heurística:** #8 Diseño minimalista; #1 Visibilidad del estado.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** filtros plegables en móvil («Filtrar (2)»); línea «7 mascotas disponibles · filtros: Perro, Grande»; incluir edad desconocida o indicarlo.

#### Baja

##### USA-21 — Mensaje equivocado al volver a «Solicitar» una mascota ya solicitada
- **Dónde:** `app/routes/solicitudes.py:282-294` (la comprobación de disponibilidad va antes que la de solicitud existente).
- **Problema:** el propio solicitante recibe «Esta mascota ya no está disponible para adopción.» en vez de «Ya has enviado una solicitud».
- **Evidencia:** `fase_b.py` → `reentrar a nueva: …/mascotas/9 ['Esta mascota ya no está disponible para adopción.']`.
- **Heurística:** #1 Visibilidad; #9.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** invertir el orden de las comprobaciones y enlazar a la solicitud existente.

##### USA-22 — Botón «Eliminar» ofrecido cuando la eliminación no está permitida
- **Dónde:** `app/templates/mascotas/admin/lista.html:152-164`; `app/routes/mascotas.py:366-369`.
- **Problema:** todas las filas muestran la papelera; si la mascota tiene solicitudes, tras confirmar en un `confirm()` nativo genérico llega un error.
- **Impacto:** acción inútil y mensaje de error evitable.
- **Evidencia:** `capturas/b01_admin_mascotas.png` (Toby y Calcetines tienen solicitudes y muestran papelera).
- **Heurística:** #5 Prevención de errores.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** deshabilitar con explicación («Tiene solicitudes») o sustituir por «Archivar».

##### USA-23 — Foto: archivo y URL a la vez sin regla visible
- **Dónde:** `app/templates/mascotas/admin/form.html:293-311`; `app/routes/mascotas.py:197-209`.
- **Problema:** se pueden rellenar ambos; no se explica que el archivo tiene prioridad; vaciar la URL borra la foto sin decirlo; no hay vista previa del archivo elegido.
- **Evidencia:** `capturas/b07_admin_nueva_vacia.png`, `capturas/b10_admin_editar.png`.
- **Heurística:** #5; #1.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** selector «Subir archivo / Usar URL», casilla «Quitar foto» explícita y vista previa.

##### USA-24 — Datos del seed incoherentes que deslucen la demo
- **Dónde:** `scripts_bd/02_seed.sql:25` y `:33-36`; `app/__init__.py:198-200`.
- **Problema:** Toby tiene una solicitud aprobada pero está «En proceso»; Calcetines tiene una solicitud pendiente pero está «Disponible»; los cuestionarios del seed usan claves (`experiencia`, `vivienda`) distintas de las de la app, por lo que la revisión aparece vacía y con «✗ No garantiza…»; la portada muestra «0 Adopciones exitosas».
- **Evidencia:** `capturas/b05_admin_revisar_resuelta_1.png`, `capturas/e02_juan_detalle_solicitud.png`, `capturas/a01_inicio.png`.
- **Heurística:** #4 Consistencia; #2.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** alinear estados y claves del seed; ocultar contadores a 0 en la portada.

##### USA-25 — La página «Revisar» de una solicitud ya resuelta muestra el formulario de decisión
- **Dónde:** `app/templates/solicitudes/admin/revisar.html:171` y `:235-252`; `app/routes/solicitudes.py:430-436`.
- **Problema:** `/solicitudes/admin/revisar/1` (aprobada) muestra «Aprobar/Rechazar» activos y no indica el estado actual; solo al enviar avisa de que ya estaba revisada.
- **Evidencia:** `capturas/b05_admin_revisar_resuelta_1.png`; `fase_b.py` → `revisar resuelta 1 200 botones: 2`.
- **Heurística:** #1 Visibilidad; #5.
- **Gravedad:** baja (solo accesible por URL directa) · **Esfuerzo:** S
- **Propuesta:** si no está pendiente, redirigir al detalle o mostrar el estado sin formulario; mostrar siempre el badge de estado en la revisión.

##### USA-26 — Etiquetas y orden inconsistentes entre flujos
- **Dónde:** `index.html:220-222` («Ver Perfil»), `catalogo.html:91-92` («Ver Detalles»), `solicitudes/detalle.html:294-296` («Ver Perfil Completo»); `app/__init__.py:205` (portada ordena por `id`) vs `mascotas.py:59` (catálogo por `fecha_ingreso`); badges «Pendiente» vs «Pendiente de revisión», «¡Aprobada!» vs «Aprobada».
- **Problema:** la misma acción y el mismo estado se nombran distinto; «Últimas incorporaciones» no coincide con el orden del catálogo.
- **Evidencia:** `capturas/a01_inicio.png` vs `capturas/a02_catalogo.png`.
- **Heurística:** #4 Consistencia y estándares.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** macro Jinja única para tarjeta de mascota y para badge de estado; ordenar la portada por `fecha_ingreso`.

##### USA-27 — El admin ve «Solicitar Adopción» pero no tiene «Mis solicitudes»
- **Dónde:** `app/templates/mascotas/detalle.html:198-204`; `app/templates/base.html:52-66`.
- **Problema:** el admin puede enviar una solicitud y bloquear la mascota, pero su menú no incluye «Mis solicitudes».
- **Evidencia:** lectura de plantillas; reproducible iniciando sesión como admin y abriendo una mascota disponible.
- **Heurística:** #4 Consistencia; #5.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** ocultar el CTA a administradores o mostrar «Mis solicitudes» también para ellos.

##### USA-28 — La portada sugiere que hay que registrarse antes de explorar
- **Dónde:** `app/templates/index.html:233-255`.
- **Problema:** el proceso empieza por «1 Regístrate» y luego «2 Explora», aunque explorar es público; el último paso «Adopta – Espera la aprobación» no explica qué ocurre tras aprobar.
- **Evidencia:** `capturas/a01_inicio.png`.
- **Heurística:** #2 Coincidencia con el mundo real; #10 Ayuda.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** Explora → Solicita (te pediremos crear cuenta) → Revisamos → Conócelo y llévatelo a casa.

---

### Recuento por gravedad

| Gravedad | Nº | IDs |
|---|---|---|
| Crítica | 1 | USA-01 |
| Alta | 6 | USA-02 a USA-07 |
| Media | 13 | USA-08 a USA-20 |
| Baja | 8 | USA-21 a USA-28 |
| **Total** | **28** | |

### Prioridades recomendadas
1. **USA-01** (S): liberar la mascota al rechazar; es un fallo de flujo que vacía el catálogo con el uso.
2. **USA-03 + USA-04 + USA-05** (S/M): conservar contexto y datos en login, registro y formularios admin.
3. **USA-06 + USA-10 + USA-25** (S): revisión admin segura y legible (confirmación, motivo obligatorio, etiquetas legibles, estado visible).
4. **USA-02 + USA-13** (M): replantear el bloqueo por una única solicitud y permitir retirarla.
5. **USA-12 + USA-16** (S): estados con «qué pasa ahora» y punto de entrada del admin con pendientes.

### Solapes posibles con otros agentes
- USA-15 (páginas de error) y USA-20 (móvil) pueden coincidir con QA técnico/responsive.
- USA-19 (errores por campo) roza accesibilidad (asociación error-campo) y microcopy.
- USA-26 roza microcopy/diseño visual; aquí se reporta por la incoherencia entre flujos.

---

## Anexo B · Funcionalidad


Método: lectura de `app/routes/*.py`, `app/models.py` y plantillas, y recorrido real con Playwright
(scripts `s1_anonimo.py`, `s2_admin_mascotas.py`, `s3_solicitudes.py`/`s3b`/`s3c`, `s4_final.py` en esta carpeta;
capturas en `capturas/`). Base: http://localhost:5000, seed + datos propios `QA-Func-*` y `func-N@test.local`.

### Mapa de estado (resumen)

```
Mascota.estado
  disponible --(solicitudes.nueva: marcar_en_proceso)--> en_proceso   [sale del catálogo y bloquea nuevas solicitudes]
  en_proceso --(admin_revisar aprobar: Solicitud.aprobar -> marcar_adoptado)--> adoptado
  en_proceso --(admin_revisar rechazar: Solicitud.rechazar)--> en_proceso   <- NO hay transición de vuelta
  cualquiera --(admin_editar, select "estado")--> cualquiera   [sin mirar solicitudes]
Solicitud.estado: pendiente -> aprobada | rechazada (las demás pendientes de la mascota no se tocan)
```

### Hallazgos

#### FUN-01 · Rechazar una solicitud deja la mascota bloqueada «En proceso» para siempre
- **Dónde**: `app/models.py:383-395` (`Solicitud.rechazar`), `app/routes/solicitudes.py:207-209` (rama `rechazar`), `app/models.py:260-263` (`marcar_en_proceso`) y `app/routes/solicitudes.py:39-42` (`nueva` exige `esta_disponible()`).
- **Problema**: al crear la primera solicitud la mascota pasa a `en_proceso` (sale del catálogo, que filtra `estado='disponible'`). Al rechazarla no se vuelve a `disponible`. Patrón «Missing State Transition».
- **Impacto**: cada rechazo saca a una mascota del catálogo para siempre. Nadie más puede solicitarla y en su ficha sigue apareciendo «En proceso de adopción». Solo se arregla si el admin edita el estado a mano.
- **Evidencia** (reproducido): admin crea `QA-Func-A` (id 10) → `func-1` la solicita (solicitud 6) → ficha: «En proceso de adopción» → admin: Panel Solicitudes → Revisar #6 → «Rechazar Solicitud» → flash info «Solicitud rechazada.» → `/mascotas/10` sigue «En proceso de adopción»; no aparece en `/mascotas/catalogo?especie=Perro&tamano=Mediano`; `func-2` en `/solicitudes/nueva/10` → redirige a la ficha con el aviso «Esta mascota ya no está disponible para adopción.». Captura `capturas/mascota_bloqueada_tras_rechazo.png`.
- **Gravedad**: crítica · **Esfuerzo**: S
- **Propuesta**: en `rechazar`, si la mascota está `en_proceso` y no le quedan solicitudes pendientes, devolverla a `disponible` en la misma transacción. Añadir un test.

#### FUN-02 · Varias solicitudes pendientes sobre una mascota: al aprobar una, las demás quedan «Pendiente» y no se pueden aprobar
- **Dónde**: `app/models.py:365-381` (`aprobar`), `app/routes/solicitudes.py:198-205`; `app/routes/mascotas.py:331` (el estado se edita libremente).
- **Problema**: el flujo normal solo permite una solicitud por mascota (FUN-01). Pero si el admin devuelve la mascota a «Disponible» desde Editar (la única forma de desbloquearla), o con datos como los del seed (Calcetines está `disponible` con una solicitud pendiente), pueden convivir varias pendientes. Al aprobar una, las demás no se rechazan: el adoptante sigue viendo «Pendiente de revisión», el panel las sigue listando y, si se intenta aprobarlas, sale «X ya ha sido adoptado.».
- **Impacto**: hay adoptantes esperando algo que ya no puede pasar, y el admin tiene que rechazarlas una por una.
- **Evidencia** (reproducido): `func-1` solicita `QA-Func-B` (id 11, solicitud 8) → admin Editar B → Estado «Disponible» → Guardar (antes hay que vaciar «URL externa», véase FUN-03) → `func-2` solicita B (solicitud 9) → admin aprueba la 8 → B «Adoptado»; la 9 sigue en `/solicitudes/admin?estado=pendiente` → «Aprobar» en la 9 → flash warning «QA-Func-B ya ha sido adoptado.» → hubo que rechazarla a mano.
- **Gravedad**: alta · **Esfuerzo**: S
- **Propuesta**: en `aprobar`, rechazar automáticamente (con un comentario estándar) las demás pendientes de la misma mascota. En `admin_editar`, impedir los cambios de estado incoherentes con las solicitudes, o avisar de ellos (p. ej. pasar a «disponible» una mascota que tiene una solicitud aprobada).

#### FUN-03 · Editar una mascota sin foto (o sin raza) es imposible o guarda el texto «None»
- **Dónde**: `app/templates/mascotas/admin/form.html:43` y `:113` (`value="{{ mascota.raza if mascota else '' }}"`, igual con `foto_url`).
- **Problema**: si el campo es `NULL`, Jinja escribe `None`. El campo `type="url"` con valor «None» bloquea el envío en el navegador («Please enter a URL») y en el servidor da el error «La URL de la foto debe empezar por https://». Si se vacía la foto y se guarda, la raza se guarda como la cadena `"None"` y la ficha pública muestra «Raza: None».
- **Impacto**: el botón «Guardar Cambios» no hace nada en las mascotas sin foto, y es justo lo que pasa con todas las creadas con S3 sin configurar. Además se corrompen datos.
- **Evidencia** (reproducido): crear `QA-Func-SinRaza` solo con nombre, especie y descripción → Editar → `#raza`='None' y `#foto_url`='None' → «Guardar Cambios» no navega (`:invalid` en foto_url) → con validación desactivada: flash «La URL de la foto debe empezar por https://» → vaciando la URL: se guarda y `/mascotas/<id>` muestra «Raza: None». Captura `capturas/editar_foto_none.png`.
- **Gravedad**: alta · **Esfuerzo**: S
- **Propuesta**: usar `{{ mascota.raza or '' }}` y `{{ mascota.foto_url or '' }}` (y revisar los demás campos opcionales). Añadir un test de edición de una mascota con campos nulos.

#### FUN-04 · El parámetro `next` se pierde al iniciar sesión
- **Dónde**: `app/templates/auth/login.html:12` (`action="{{ url_for('auth.login') }}"` sin la query); `app/routes/auth.py:158` lee `request.args['next']`. También `app/templates/mascotas/detalle.html` (enlace «Inicia sesión para adoptar» → `/auth/login` sin `next`).
- **Problema**: `login_required` redirige a `/auth/login?next=...`, pero el formulario envía el POST a `/auth/login` y la query se pierde. La lógica de `es_redireccion_segura` nunca llega a usarse desde la web.
- **Impacto**: quien intentaba adoptar acaba en la portada después de iniciar sesión y tiene que buscar otra vez la mascota.
- **Evidencia** (reproducido): anónimo → `/solicitudes/mis-solicitudes` → `/auth/login?next=%2Fsolicitudes%2Fmis-solicitudes` (flash info correcto) → login como `func-1` → aterriza en `http://localhost:5000/`. Captura `capturas/login_next_perdido.png`.
- **Gravedad**: alta · **Esfuerzo**: S
- **Propuesta**: `action="{{ url_for('auth.login', next=request.args.get('next')) }}"` (o un campo oculto `next`), y en la ficha `url_for('auth.login', next=url_for('solicitudes.nueva', mascota_id=...))`. Añadir un test e2e.

#### FUN-05 · El cuestionario de adopción no se valida en el servidor
- **Dónde**: `app/routes/solicitudes.py:51-87`.
- **Problema**: solo valida el atributo `required` del HTML. Un POST sin campos crea la solicitud, saca la mascota del catálogo (FUN-01) y muestra «¡Solicitud enviada con éxito!». Los radios ausentes se guardan como «No» (`== 'si'`), así que «no responde» y «no se compromete» quedan iguales.
- **Impacto**: llegan al admin solicitudes vacías («Tipo: », «Propiedad: ») que además bloquean la mascota. Cualquier fallo del JS o del navegador basta para que pase.
- **Evidencia** (reproducido): `func-3` → `/solicitudes/nueva/12` (QA-Func-C) → con validación de cliente desactivada → «Enviar Solicitud» vacío → flash success; en Revisar: «Tipo: | Propiedad: | Jardín: No | Otras mascotas: No». Captura `capturas/solicitud_vacia_aceptada.png`.
- **Gravedad**: alta · **Esfuerzo**: M
- **Propuesta**: validar en el servidor los obligatorios y los valores permitidos (listas de los `select`/radios). Si hay error, volver a mostrar el formulario con los datos y el mensaje (código 400).

#### FUN-06 · Subir una foto válida con S3 sin configurar da error 500
- **Dónde**: `app/s3.py:63-85` (`upload_to_s3` sin `try`), llamado en `app/routes/mascotas.py:200-204` y `:297-302`.
- **Problema**: sin bucket ni credenciales, `upload_fileobj` lanza una excepción (`TypeError ... NoneType`) que nadie captura.
- **Impacto**: al crear o editar con foto, el admin ve una página de error (el depurador de Werkzeug en desarrollo, un 500 genérico en producción) y pierde todo el formulario. El campo de archivo no avisa de que la subida no está disponible.
- **Evidencia** (reproducido): Nueva mascota con todos los campos + PNG de 20×20 → respuesta 500 «TypeError: expected string or bytes-like object, got 'NoneType'». Captura `capturas/nueva_mascota_png_sin_s3.png`. No se creó la mascota.
- **Gravedad**: alta · **Esfuerzo**: S
- **Propuesta**: ocultar o desactivar el campo de archivo si falta la configuración de S3. Capturar `BotoCoreError`/`ClientError`/config ausente, registrar el error en `current_app.logger` y mostrar un flash genérico conservando los datos.

#### FUN-07 · Los formularios pierden lo escrito al fallar una validación
- **Dónde**: `app/routes/auth.py:69-79,108` (registro), `:136-151` (login: se pierde el email); `app/routes/mascotas.py:185-218` (nueva: `render_template(..., mascota=None)`), `:282-320` (editar: se muestran los valores de la BD, no los enviados); `:204` y `:301` (`redirect(request.url)` con archivo no válido, que se pierde también en editar).
- **Problema**: las plantillas no leen `request.form`.
- **Impacto**: un solo error (contraseñas distintas, descripción de 9 caracteres, edad 31, URL http) obliga a escribirlo todo de nuevo. Al editar es peor: los cambios vuelven en silencio a los valores anteriores y parece que «no se guardó».
- **Evidencia** (reproducido): Registro con todos los campos y la confirmación distinta → flash danger y todos los campos vacíos (`capturas/registro_reenvio_pierde_datos.png`). Nueva mascota con nombre «Q» (y con los otros 8 casos probados) → todos los campos vacíos y casillas desmarcadas (`capturas/nueva_mascota_reenvio_pierde_datos.png`). Editar QA-Func-A: nombre «QA-Func-A-editado», raza «Galgo» y descripción «corta» → al volver, nombre «QA-Func-A» y raza «Mestizo» (`capturas/editar_reenvio_revierte.png`). Archivo .txt → flash «Formato de imagen no permitido» y formulario vacío.
- **Gravedad**: media · **Esfuerzo**: M
- **Propuesta**: volver a mostrar el formulario con los valores enviados (`request.form.get(...)` como valor de cada campo, o pasar a Flask-WTF `FlaskForm`, que ya está en el stack) y nunca redirigir después de un error de validación.

#### FUN-08 · La revisión de una solicitud ya resuelta sigue mostrando «Aprobar» y «Rechazar», y no hay confirmación
- **Dónde**: `app/templates/solicitudes/admin/revisar.html:110-127`; `app/routes/solicitudes.py:185-188`.
- **Problema**: la petición GET pinta los botones aunque la solicitud no esté pendiente; solo el POST lo comprueba. Además, aprobar o rechazar es irreversible y no lleva `data-confirmar`, a diferencia de Eliminar.
- **Impacto**: el admin escribe un comentario, pulsa y le sale «Esta solicitud ya ha sido revisada.»; el comentario se pierde. Un clic equivocado en «Rechazar» no tiene vuelta atrás y además bloquea la mascota (FUN-01).
- **Evidencia** (reproducido): `/solicitudes/admin/revisar/6` (ya rechazada) → aparece el botón Aprobar (`capturas/revisar_resuelta_con_botones.png`) → al pulsarlo, flash warning «Esta solicitud ya ha sido revisada.».
- **Gravedad**: media · **Esfuerzo**: S
- **Propuesta**: si no está pendiente, mostrar el estado, quién la revisó y cuándo, en lugar del formulario. Añadir `data-confirmar` a los dos botones (con un `<form>` por botón o comprobando el `submitter` en `app.js`).

#### FUN-09 · Una acción desconocida en Revisar redirige sin ningún mensaje
- **Dónde**: `app/routes/solicitudes.py:196-211` (no hay `else`).
- **Evidencia** (reproducido): en la solicitud 5, cambiar el `value` del botón a «otra» y enviar → `/solicitudes/admin` sin flash; la solicitud sigue pendiente.
- **Impacto**: parece que se guardó algo cuando no se ha guardado nada (poco probable sin manipular la página, pero se podría disparar tras un cambio de la plantilla).
- **Gravedad**: baja · **Esfuerzo**: S · **Propuesta**: `else: flash('Acción no válida.', 'danger')` y responder con 400.

#### FUN-10 · El administrador puede solicitar adoptar y no tiene acceso a «Mis solicitudes»
- **Dónde**: `app/templates/mascotas/detalle.html:235-243`; `app/routes/solicitudes.py:20-21` (solo `login_required`); `app/templates/base.html:52-66` (el admin no tiene el enlace).
- **Evidencia** (reproducido): el admin ve «Solicitar Adopción» en `/mascotas/14` y `/solicitudes/nueva/14` le muestra el formulario. Puede enviarlo, pero su menú no tiene «Mis Solicitudes» (la URL funciona si se escribe a mano). Además podría aprobar su propia solicitud.
- **Gravedad**: baja · **Esfuerzo**: S · **Propuesta**: decidir la regla. Lo razonable es ocultar el botón y rechazar `nueva` para los admins con un flash.

#### FUN-11 · Errores 404, 400 (CSRF) y 429 con la página por defecto en inglés, sin navegación
- **Dónde**: `app/__init__.py` (solo hay manejador para 413).
- **Evidencia** (reproducido): `/mascotas/99999` y `/solicitudes/detalle/999999` → «404 Not Found … The requested URL was not found on the server». Logout con token alterado (equivale a una sesión caducada) → «400 Bad Request — The CSRF token is invalid.» (`capturas/csrf_invalido.png`). El 429 del límite de login también usa la página por defecto de Flask-Limiter (visto en el código; no lo agoté a propósito).
- **Impacto**: el usuario se queda en una página sin menú ni salida. Con CSRF caducado pierde el formulario sin entender por qué.
- **Gravedad**: media · **Esfuerzo**: S
- **Propuesta**: plantillas `errors/404.html`, `400.html`, `429.html` y `500.html` que extiendan `base.html`. Para `CSRFError`: un flash «La sesión ha caducado, vuelve a intentarlo» y redirigir al referer.

#### FUN-12 · El filtro de especie distingue mayúsculas: «Perro» y «perro» salen como dos opciones
- **Dónde**: `app/routes/mascotas.py:174-175` (especie es texto libre) y `:65-71` (`distinct`).
- **Evidencia** (reproducido): crear una mascota con especie «perro» → en el selector del catálogo salen «Conejo, Gato, Perro, perro». Al filtrar «Perro» no aparece esa mascota.
- **Gravedad**: media · **Esfuerzo**: S
- **Propuesta**: un `select` con valores cerrados (como el tamaño y el sexo) o normalizar la especie al guardar (`.strip().capitalize()`).

#### FUN-13 · Una mascota con edad 0 no muestra la edad
- **Dónde**: `catalogo.html:81`, `detalle.html:201`, `mascotas/admin/lista.html` (columna Edad) usan `{% if mascota.edad_aprox %}`.
- **Evidencia** (reproducido): `QA-Func-Edad0` (edad 0) → en la lista admin sale «-» y en la ficha no hay fila «Edad aproximada». El formulario sí acepta 0.
- **Gravedad**: baja · **Esfuerzo**: S · **Propuesta**: `{% if mascota.edad_aprox is not none %}` y un texto «menos de 1 año».

#### FUN-14 · Estados vacíos que confunden y parámetros inválidos que no se avisan
- **Dónde**: `mascotas/admin/lista.html` (vacío = «No hay mascotas registradas / Comienza añadiendo…»), `catalogo.html:98-104`, `app/routes/mascotas.py:51-56,114-123`, `solicitudes.py:149-150`.
- **Evidencia** (reproducido): `/mascotas/admin?estado=adoptado` sin resultados, `?estado=foo` o `?page=999` → «No hay mascotas registradas» aunque haya más de 20 (`capturas/admin_mascotas_page999.png`). En el catálogo, `?page=999` sin filtros → «No se encontraron mascotas que coincidan con los filtros aplicados» (`capturas/catalogo_page999.png`) y sin paginación para volver. `?edad=abc` se ignora en silencio; `?sexo=foo` da una lista vacía.
- **Gravedad**: baja · **Esfuerzo**: S
- **Propuesta**: distinguir «no hay mascotas» de «no hay resultados con este filtro» o «página fuera de rango» (o redirigir a la última página). Validar `estado` y `sexo` contra listas permitidas.

#### FUN-15 · Los filtros de estado del panel de mascotas pierden el orden; «Volver al catálogo» pierde los filtros
- **Dónde**: `mascotas/admin/lista.html:21-36` (los enlaces de estado no llevan `orden`/`dir`); `mascotas/detalle.html:153` (`url_for('mascotas.catalogo')` sin argumentos).
- **Evidencia** (reproducido): `/mascotas/admin?orden=nombre&dir=desc` → clic en «Disponibles» → `?estado=disponible` (el orden vuelve a ID ascendente). Catálogo `?especie=Gato` → Ver Detalles → «Volver al catálogo» → `/mascotas/catalogo` con «Todas».
- **Gravedad**: baja · **Esfuerzo**: S
- **Propuesta**: conservar `orden`/`dir` en los enlaces de estado. En la ficha, volver con `request.referrer` si es del catálogo, o pasar los filtros como `next`.

#### FUN-16 · El cuestionario del seed no coincide con las claves que usa la app
- **Dónde**: `scripts_bd/02_seed.sql:33-36` (claves `experiencia` y `vivienda`) frente a `solicitudes/detalle.html` y `revisar.html` (`vivienda_tipo`, `experiencia_previa`…). Además, en el seed Toby está `en_proceso` con una solicitud **aprobada** (debería estar `adoptado`) y Calcetines está `disponible` con una **pendiente**.
- **Impacto**: en desarrollo y en las demos, las solicitudes del seed salen con el cuestionario vacío y en estados contradictorios. Eso esconde o confunde los problemas reales (FUN-01/02).
- **Gravedad**: baja · **Esfuerzo**: S · **Propuesta**: alinear el seed con el modelo y con las transiciones de estado.

#### FUN-17 (riesgo, no reproducido) · Ordenar por una columna con valores repetidos no tiene criterio de desempate
- **Dónde**: `app/routes/mascotas.py:137-145`, `solicitudes.py:153` (`order_by(fecha_solicitud.desc())`).
- **Detalle**: al paginar con `orden=especie` (o con fechas iguales), PostgreSQL no garantiza un orden estable, así que una fila puede repetirse o saltarse entre páginas. Con 21 mascotas, páginas 1 y 2, no se repitió ninguna (21/21 únicas).
- **Gravedad**: baja · **Esfuerzo**: S · **Propuesta**: añadir `Mascota.id` / `Solicitud.id` como segundo criterio.

### Probado y correcto
- Filtros combinados del catálogo (especie+tamaño, especie+sexo+edad) y combinaciones sin resultados con su mensaje. `page=abc` vuelve a 1.
- La paginación del catálogo conserva los filtros; al filtrar desde la página 2 se vuelve a la 1.
- Permisos: un adoptante en `/mascotas/admin`, `/admin/nueva`, `/admin/editar/<id>`, `/solicitudes/admin`, `/admin/revisar/<id>` → redirige al catálogo con flash danger. La solicitud ajena en `/solicitudes/detalle/<id>` → flash danger. Un POST de adoptante a revisar no cambia nada.
- Doble POST simultáneo de la misma solicitud → solo se crea una (la restricción única y la comprobación de disponibilidad funcionan). Al volver al formulario después de enviarlo, se redirige con aviso.
- Registro: email ya existente (también en mayúsculas) → al login con warning. El nombre con solo espacios se rechaza. Los mensajes flash tienen la categoría correcta y no se duplican.
- Logout por POST con CSRF. Atrás después del logout no muestra páginas privadas.
- Eliminar pide confirmación (si se cancela no se borra). Una mascota con solicitudes no se puede eliminar (flash danger). Las validaciones de edad, URL https y descripción del servidor funcionan.
- Aprobar una solicitud pone la mascota en «Adoptado» y la saca del catálogo. Reintentar sobre una solicitud resuelta se bloquea.

### Datos de prueba que quedan en la BD
- Usuarios: `func-1@test.local`, `func-2@test.local`, `func-3@test.local` (contraseña del seed). No hay borrado de usuarios en la web.
- Mascotas que no se pueden borrar desde el panel (tienen solicitudes; el borrado lo impide por diseño): `QA-Func-A` (id 10, en_proceso, solicitud 6 rechazada), `QA-Func-B` (id 11, adoptado, solicitudes 8 aprobada y 9 rechazada), `QA-Func-C` (id 12, en_proceso, solicitud 5 **pendiente** y vacía, de func-3).
- Borradas correctamente: QA-Func-P1…P6, Edad0, Doble, SinRaza. No se modificó ningún dato del seed.

---

## Anexo C · QA en navegador


Fecha: 2026-11-15 · Entorno: http://localhost:5000 (servidor de desarrollo Werkzeug, SQL echo, datos del seed)
Herramientas: Playwright 1.x (Chromium headless) desde `venv/bin/python`, CDP para red/throttling. Las herramientas
`chrome-devtools` (Lighthouse) no se pudieron usar: no hay Google Chrome estable instalado (`/opt/google/chrome/chrome`).

Carpeta de trabajo: `<carpeta-auditoria>/qa`
- Capturas por página y viewport: `<carpeta-auditoria>/qa/capturas/<pagina>-<375|768|1280>.png` (63 capturas de página completa)
- Capturas de foco: `<carpeta-auditoria>/qa/capturas/foco/`, resúmenes `<carpeta-auditoria>/qa/capturas/foco-resumen.png` y `<carpeta-auditoria>/qa/capturas/foco-estable-resumen.png`
- Datos crudos: `resultados.json` (consola, CSP, red, desbordes por página×viewport), `metricas_frio.json`, `formularios.log`, `foco.log`, `e2e.log`
- Scripts reproducibles: `<carpeta-auditoria>/qa/scripts/`

### Resumen

| Gravedad | Nº |
|---|---|
| Crítica | 0 |
| Alta | 1 |
| Media | 6 |
| Baja | 7 |

**Lo que está bien (sin hallazgos):** 21 URLs × 3 viewports (63 cargas) como anónimo, adoptante y admin:
0 errores de JavaScript, 0 avisos de consola, **0 violaciones de CSP**, 0 peticiones fallidas, 0 respuestas 4xx/5xx
(salvo los 404 provocados a propósito). SRI correcto en Bootstrap CSS/JS (jsDelivr, `crossorigin=anonymous`).
Ningún desbordamiento horizontal a nivel de página en 375/768/1280 (`scrollWidth == clientWidth` en todas).
CLS = 0 y TBT = 0 en todas las páginas, también con CPU 4×. Menú móvil funcional. «Saltar al contenido» funciona.
Tras cerrar sesión, el botón Atrás no muestra contenido privado (redirige a login). Envío real de formularios
con CSRF válido correcto (registro y solicitud).

**E2E existentes (`tests/e2e/test_flujos.py`): 6/6 en verde** (6,95 s; `<carpeta-auditoria>/qa/e2e.log`).

### Métricas por página (línea base «antes»)

Medidas con Playwright en frío (caché desactivada, contexto nuevo por página).
\*Perfil «móvil»: 375×812, red tipo Slow 4G de Lighthouse (RTT 150 ms, 1,6 Mbps) + CPU 4×. «Escritorio»: 1350×900 sin throttling.
INP aproximado = duración del evento al pulsar el botón hamburguesa (en escritorio no aplica).
Peso = bytes transferidos (`encodedDataLength`), sin compresión porque Werkzeug no comprime.

| Página | Rol | LCP móvil* (ms) | Elemento LCP | FCP móvil (ms) | CLS | TBT (ms) | INP toggler (ms) | Peso frío (KB) | Imágenes (KB) | Peticiones | LCP escritorio (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| inicio (`/`) | anon | 1964 | DIV.hero-home text-center mb-5 | 1020 | 0 | 0 | 16 | 331.1 | 266.9 | 9 | 144 |
| catalogo (`/mascotas/catalogo`) | anon | 1352 | H2 | 1352 | 0 | 0 | 16 | 294.3 | 230.2 | 12 | 108 |
| detalle-mascota (`/mascotas/1`) | anon | 896 | IMG unsplash/photo-1558788353-f76d92427f16 | 880 | 0 | 0 | 16 | 108.7 | 37.1 | 6 | 120 |
| login (`/auth/login`) | anon | 664 | A.navbar-brand | 664 | 0 | 0 | 16 | 91.8 | 33.5 | 6 | 124 |
| inicio-adoptante (`/`) | adoptante | 2032 | DIV.hero-home text-center mb-5 | 1156 | 0 | 0 | 16 | 344.8 | 266.8 | 9 | 156 |
| nueva-solicitud (`/solicitudes/nueva/1`) | adoptante | 672 | DIV.alert alert-info | 672 | 0 | 0 | 16 | 66.2 | 0.0 | 5 | 128 |
| mis-solicitudes (`/solicitudes/mis-solicitudes`) | adoptante | 860 | IMG unsplash/photo-1505628346881-b72b27e84530 | 760 | 0 | 0 | 16 | 108.9 | 47.5 | 6 | 124 |
| detalle-solicitud (`/solicitudes/detalle/1`) | adoptante | 908 | IMG unsplash/photo-1505628346881-b72b27e84530 | 880 | 0 | 0 | 16 | 122.1 | 47.5 | 6 | 140 |
| admin-mascotas (`/mascotas/admin`) | admin | 608 | H2 | 608 | 0 | 0 | 16 | 99.0 | 0.0 | 5 | 136 |
| admin-mascota-nueva (`/mascotas/admin/nueva`) | admin | 708 | A.navbar-brand | 708 | 0 | 0 | 16 | 76.3 | 0.0 | 5 | 124 |
| admin-mascota-editar (`/mascotas/admin/editar/1`) | admin | 744 | A.navbar-brand | 744 | 0 | 0 | 16 | 101.4 | 37.1 | 6 | 116 |
| admin-solicitudes (`/solicitudes/admin`) | admin | 716 | H2 | 716 | 0 | 0 | 16 | 81.6 | 0.0 | 5 | 112 |
| admin-revisar (`/solicitudes/admin/revisar/2`) | admin | 788 | IMG unsplash/photo-1558788353-f76d92427f16 | 748 | 0 | 0 | 16 | 98.0 | 37.1 | 6 | 136 |
| admin-detalle-solicitud (`/solicitudes/detalle/3`) | admin | 800 | IMG unsplash/photo-1568572933382-74d440642117 | 776 | 0 | 0 | 16 | 95.9 | 34.5 | 6 | 112 |

Notas de interpretación (desarrollo vs. producción):
- TTFB local ≈ 3–15 ms; en producción (gunicorn + red real) el TTFB subirá y todo el LCP se desplaza en consecuencia.
- Ningún LCP supera 2,5 s en este perfil, pero **inicio está a ~0,5 s del umbral** (1,96–2,03 s) y depende de una
  imagen de fondo de 150 KB en un tercero (ver QA-03).
- Peso dominado por imágenes de Unsplash (inicio 267 KB de 331 KB; catálogo 230 KB de 294 KB).
- Werkzeug no comprime (HTML de `/mascotas/admin` = 47 KB) y sirve `/static` con `Cache-Control: no-cache`; gunicorn
  en producción se comportaría igual porque no hay compresión ni caché configuradas en la app (ver QA-07).
- Peticiones por página: 5–12 (HTML, Bootstrap CSS+JS de jsDelivr, styles.css, app.js e imágenes).

### Hallazgos

#### QA-01 · Páginas de error sin plantilla: CSRF caducado/ausente muestra un 400 en inglés sin navegación
- **Pantalla / archivo:** cualquier formulario POST; `app/__init__.py:169-176` (solo hay `errorhandler(413)`; no hay manejador para `CSRFError`, 404, 405, 429 ni 500).
- **Problema:** con token ausente, manipulado o con la sesión perdida/caducada, el usuario recibe la página por defecto de Werkzeug:
  «Bad Request — The CSRF token is missing. / is invalid. / The CSRF session token is missing.» En inglés, sin estilos,
  sin cabecera ni enlace para volver. Lo mismo para 404 (`/no-existe`, `/mascotas/99999`) y 405 (`GET /auth/logout`).
  `WTF_CSRF_TIME_LIMIT` no está configurado (por defecto 3600 s): quien tarde más de 1 h en rellenar el cuestionario de adopción
  (largo, con textos libres) llegará a esta pantalla.
- **Impacto:** el usuario no entiende qué pasó ni cómo seguir; sensación de app rota. El Atrás del navegador sí conservó
  los datos del cuestionario en Chromium (comprobado), pero el usuario no recibe esa indicación y en otros navegadores/móviles puede perderlos.
- **Evidencia:** `capturas/csrf-ausente-1280.png`, `capturas/csrf-invalido-1280.png`, `capturas/csrf-sesion-caducada-1280.png`,
  `capturas/csrf-sesion-caducada-375.png`, `capturas/solicitud-csrf-invalido-1280.png`, `capturas/404-1280.png`, `capturas/mascota-404-375.png`; pasos en `formularios.log` (A1–A3, D).
- **Gravedad:** alta · **Esfuerzo:** M
- **Propuesta:** `@app.errorhandler(CSRFError)` que haga `flash('Tu sesión ha caducado. Vuelve a enviar el formulario.', 'warning')` y
  redirija a `request.referrer`/misma URL (o renderice el formulario de nuevo con los datos); plantillas `errors/404.html`, `403`, `405`, `429`, `500`
  que extiendan `base.html` en español. Valorar `WTF_CSRF_TIME_LIMIT = None` (token ligado a la sesión) o mayor. Actualizar el e2e que
  hoy afirma el texto inglés (`tests/e2e/test_flujos.py:105`).

#### QA-02 · Tablas de administración en móvil: las columnas Estado y Acciones quedan fuera de la vista
- **Pantalla / archivo:** `/mascotas/admin` y `/solicitudes/admin` a 375 px; `app/templates/mascotas/admin/lista.html:54`, `app/templates/solicitudes/admin/lista.html:49`.
- **Problema:** `.table-responsive` mide 321 px de ancho visible con contenido de 516 px (mascotas) y 425 px (solicitudes). Los badges de estado aparecen
  cortados («Rechaza…», «Pendient…») y los botones Editar/Eliminar/Revisar no se ven; no hay ningún indicador de que se puede desplazar.
- **Impacto:** en móvil el administrador no descubre cómo editar, borrar o revisar; lee estados truncados.
- **Evidencia:** `capturas/admin-mascotas-375.png`, `capturas/admin-solicitudes-375.png` (y `-768` para comparar).
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** por debajo de `md`, presentar cada fila como tarjeta (`d-md-none`/`d-none d-md-table`), o mover Acciones a la primera columna,
  ocultar columnas secundarias (Especie, Tamaño, Edad) con `d-none d-sm-table-cell` y añadir sombra/gradiente de desplazamiento.

#### QA-03 · LCP de inicio: imagen de fondo CSS de 150 KB en un tercero, descubierta tarde y sin variantes por tamaño
- **Pantalla / archivo:** `/`; `app/templates/index.html:150-153` (`.hero-home { background: … url('https://images.unsplash.com/photo-1450778869180…?w=1200&h=500&fit=crop') }` en un `<style>` de la plantilla).
- **Problema:** el elemento LCP es `div.hero-home`. La imagen (1200×500, 149,5 KB) solo se pide tras parsear el CSS, no tiene `preload`/`fetchpriority`,
  se sirve igual a un móvil de 375 px y depende de images.unsplash.com (nueva conexión TLS). LCP móvil 1,96–2,03 s con servidor local; en producción
  con TTFB real superará previsiblemente los 2,5 s.
- **Impacto:** primera impresión lenta de la página de entrada; el 45 % del peso de inicio es esta imagen.
- **Evidencia:** `metricas_frio.json` (inicio, inicio-adoptante); petición `photo-1450778869180…` (149,5 KB) en `resultados.json`; `capturas/inicio-375.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** servir la imagen desde `/static` en WebP/AVIF con variantes (≈800 px móvil, 1600 px escritorio); usar `<img fetchpriority="high">`
  con `srcset/sizes` + `object-fit: cover` en lugar de `background`, o `<link rel="preload" as="image" imagesrcset=…>`; mover el CSS a `styles.css`.

#### QA-04 · Imágenes de mascotas sin width/height, sin lazy-load y sin srcset
- **Pantalla / archivo:** catálogo, inicio, mis solicitudes, detalle; `app/templates/mascotas/catalogo.html:70`, `index.html:76`, `mascotas/detalle.html:19`,
  `solicitudes/detalle.html:25`, `solicitudes/mis_solicitudes.html:19`, `solicitudes/admin/revisar.html:19`, `mascotas/admin/form.html:120`.
- **Problema:** ninguna `<img>` lleva `width`/`height` ni `loading="lazy"`/`decoding="async"`. Todas piden `?w=400` fijo (natural 400×533–600) para
  mostrarse a 300×180 o 351×250 recortadas. En el catálogo móvil se descargan las 7 fotos (230 KB) aunque solo 1 está en pantalla, compitiendo
  con el CSS: FCP móvil del catálogo 1,35 s frente a 0,66 s del login. Hoy CLS = 0 solo porque la altura la fijan reglas CSS/`style` inline.
- **Impacto:** más datos móviles y peor FCP/LCP en el listado; riesgo de saltos de diseño si cambia el CSS.
- **Evidencia:** `resultados.json` → `imgsNoDim`/`imgs` por página; `metricas_frio.json` (catálogo: 12 peticiones, 230 KB de imágenes).
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** añadir `width`/`height` (o `aspect-ratio`), `loading="lazy" decoding="async"` a partir de la 2.ª tarjeta (la primera visible sin lazy),
  y `srcset` con `?w=300/600&fit=crop&h=…` (Unsplash) o miniaturas generadas con Pillow al subir a S3.

#### QA-05 · Foco poco visible en campos de formulario y enlaces del navbar
- **Pantalla / archivo:** login, registro, catálogo (filtros), solicitud, formularios admin, navbar; `app/static/css/styles.css:69-77` y `:161-164`.
- **Problema:** el `outline: 3px` de `input:focus-visible`/`select:focus-visible` (especificidad 0,1,1) pierde frente a `.form-control:focus { outline: 0 }`
  de Bootstrap (0,2,0). Resultado medido: `input` → solo borde #8ecae6 + halo `rgba(142,202,230,.25)` (casi invisible sobre blanco); `select` → halo azul Bootstrap
  al 25 % (estilo distinto); `.nav-link` → halo azul 25 % sobre el navbar azul claro. Botones y enlaces normales sí muestran el contorno de 3 px.
- **Impacto:** quien navega con teclado pierde la posición en los formularios clave (login, cuestionario). (Evaluación WCAG detallada: la hace otro agente.)
- **Evidencia:** `capturas/foco-estable-resumen.png` (password, select, nav-link, hamburguesa), `capturas/foco/*.png`, `foco.log`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** `.form-control:focus-visible, .form-select:focus-visible, .form-check-input:focus-visible, .nav-link:focus-visible { outline: 3px solid var(--color-dark); outline-offset: 2px; }`
  o subir el halo a un color de contraste ≥ 3:1.

#### QA-06 · Cuestionario de solicitudes mostrado vacío y con «✗ No garantiza…» cuando el dato falta
- **Pantalla / archivo:** `/solicitudes/admin/revisar/2`, `/solicitudes/detalle/1`; `app/templates/solicitudes/admin/revisar.html:55-56` (y siguientes); `scripts_bd/02_seed.sql:34-36`.
- **Problema:** el seed guarda `{"experiencia": …, "vivienda": …}` pero las plantillas leen `vivienda_tipo`, `vivienda_propia`, `experiencia_previa`, `compromiso_gastos`…
  Se muestran etiquetas sin valor («Tipo:», «Experiencia previa:») y, peor, los compromisos ausentes se pintan como «✗ No garantiza cubrir gastos / dedicar tiempo».
- **Impacto:** el admin puede rechazar una solicitud por un «No» que el solicitante nunca dio. En producción afecta a cualquier solicitud antigua o con claves que falten.
- **Evidencia:** `capturas/admin-revisar-375.png`, `capturas/detalle-solicitud-375.png`, `capturas/admin-detalle-solicitud-1280.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** en plantilla distinguir «Sin respuesta» de «No» (`{% if x is none %}`); alinear las claves del seed con el formulario actual.

#### QA-07 · Sin compresión ni caché de larga duración para HTML y estáticos
- **Pantalla / archivo:** todas; `app/__init__.py`, `config.py`, `gunicorn.conf.py` (no hay Flask-Compress, WhiteNoise ni `SEND_FILE_MAX_AGE_DEFAULT`).
- **Problema:** `/static/css/styles.css` → `Cache-Control: no-cache` (revalidación 304 en cada navegación); HTML sin gzip/br (admin-mascotas 47 KB).
  En desarrollo es esperable; el riesgo es que en producción gunicorn sirve igual si no hay un proxy que lo haga (el repo no lo incluye).
- **Impacto:** una petición de revalidación extra por recurso y página; HTML 3–5× más pesado en móvil.
- **Evidencia:** `curl -sI http://localhost:5000/static/css/styles.css`; columna «Peso» de la tabla.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** WhiteNoise (compresión + `max-age` largo con nombres con hash) o Flask-Compress + `SEND_FILE_MAX_AGE_DEFAULT` con cache busting (`?v=`); documentarlo en `docs/DESPLIEGUE.md` si lo hace el proxy.

#### QA-08 · CSS de Bootstrap en CDN bloquea el render y obliga a abrir conexiones a 3 orígenes externos
- **Pantalla / archivo:** todas; `app/templates/base.html:10-11`.
- **Problema:** `bootstrap.min.css` (30 KB) en jsDelivr es bloqueante; además se conectan images.unsplash.com y developers.google.com sin `preconnect`.
  Con RTT 150 ms el FCP móvil queda en 0,61–1,35 s. Bootstrap 5.3.0 (hay versiones de parche posteriores de la 5.3).
- **Impacto:** pequeño retraso del primer pintado; dependencia de disponibilidad de terceros (si jsDelivr cae, la web queda sin estilos ni menú móvil).
- **Evidencia:** `resultados.json` → `headBlocking`; `metricas_frio.json` (FCP).
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** `<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>` y para Unsplash, o servir Bootstrap desde `/static` (también simplifica la CSP).

#### QA-09 · Logo de Google enlazado desde developers.google.com: 33 KB para un icono de 24 px
- **Pantalla / archivo:** `/auth/login`; `app/templates/auth/login.html:48`.
- **Problema:** PNG 200×204 (33,5 KB, 36 % del peso del login) mostrado a 24×24, servido por un tercero (hotlinking).
- **Impacto:** peso innecesario y dependencia externa en la página de acceso.
- **Evidencia:** `metricas_frio.json` (login: imágenes 33,5 KB), `resultados.json` (`nat 200x204`, `disp 24x24`).
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** SVG oficial «G» en `/static/img/` o inline con `aria-hidden="true"` y `width/height=18`.

#### QA-10 · La API devuelve 404 en HTML cuando el id no es numérico
- **Pantalla / archivo:** `GET /api/mascotas/abc` → 404 `text/html` (página Werkzeug); `GET /api/mascotas/99999` sí devuelve `{"error": "Recurso no encontrado"}`.
- **Problema:** contradice la convención del proyecto (errores siempre JSON; parámetros numéricos inválidos → 400).
- **Impacto:** clientes de la API que parsean JSON fallan.
- **Evidencia:** `curl -s -w '%{content_type}' http://localhost:5000/api/mascotas/abc`.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** manejador 404 del blueprint/app que responda JSON para rutas `/api/`, o rutas con `<id>` string que validen y devuelvan 400.

#### QA-11 · El filtro «Especie» del catálogo ofrece «Perro» y «perro» como opciones distintas
- **Pantalla / archivo:** `/mascotas/catalogo` (select `#especie`); `app/routes/mascotas.py` (lista de especies distintas, sensible a mayúsculas).
- **Problema:** opciones «Todas, Gato, Perro, perro» (`foco.log`, catalogo-1280 tab7). Puede venir de datos creados por otro agente, pero la app no normaliza.
- **Impacto:** filtrar por «Perro» oculta mascotas guardadas como «perro».
- **Evidencia:** `foco.log`.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** normalizar `especie` al guardar (`.strip().capitalize()`) y filtrar con `func.lower()`.

#### QA-12 · Tras solicitar una mascota, volver a solicitarla dice «ya no está disponible» en vez de «ya tienes una solicitud»
- **Pantalla / archivo:** `/solicitudes/nueva/<id>`; `app/routes/solicitudes.py:24-93`.
- **Problema:** enviar una solicitud pasa la mascota a no disponible; si el mismo usuario vuelve, se le redirige a la ficha con «Esta mascota ya no está disponible para adopción».
- **Impacto:** confunde al solicitante (parece que otro se la ha llevado).
- **Evidencia:** `formularios.log` (D2).
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** comprobar primero si el usuario ya tiene solicitud para esa mascota y enlazar a su detalle.

#### QA-13 · Catálogo a 768 px: la rejilla de tarjetas queda más estrecha y desalineada respecto al bloque de filtros
- **Pantalla / archivo:** `/mascotas/catalogo` a 768 px; `app/templates/mascotas/catalogo.html` (columnas de la rejilla).
- **Problema:** dos columnas de ~300 px centradas con ~38 px de margen extra a cada lado frente a la tarjeta de filtros, que ocupa todo el ancho.
- **Impacto:** cosmético; desaprovecha espacio en tablet.
- **Evidencia:** `capturas/catalogo-768.png`.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** revisar las clases `col-*`/`justify-content-center` de la rejilla (p. ej. `row-cols-1 row-cols-sm-2 row-cols-lg-3 g-4`).

#### QA-14 · Los e2e cubren 6 flujos; faltan los de más riesgo en navegador
- **Pantalla / archivo:** `tests/e2e/test_flujos.py`.
- **Problema:** cubiertos: filtro del catálogo, envío de solicitud, alta/borrado de mascota con confirm, logout desde el menú, menú móvil, POST sin CSRF.
  **No cubiertos:** registro; login fallido y bloqueo 429; páginas 404/403/500 y CSRF caducado con mensaje en español (hoy el test fija el texto inglés, línea 105);
  admin revisa/aprueba/rechaza solicitud; edición de mascota y subida de foto (límite 5 MB → 413); ordenación/paginación/filtros del panel admin;
  «Mis solicitudes» y detalle; acceso denegado (adoptante → /mascotas/admin, solicitud ajena); tablas admin en 375 px; Atrás tras logout; foco visible con teclado;
  flujo Google OAuth (al menos el redirect).
- **Impacto:** regresiones en el flujo de admin y en las páginas de error pasarían el CI.
- **Evidencia:** `e2e.log` (6 passed).
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** añadir como mínimo: revisión de solicitud por admin, registro→login, 404/CSRF con plantilla propia, tabla admin móvil (acciones visibles).

### Efectos en datos compartidos (para el organizador)
- Se crearon 2 usuarios propios de QA `qa-<timestamp>@test.local`.
- Con ese usuario se envió **una solicitud real para Lys (mascota 8)**; la app pasó a Lys a no disponible, por lo que el catálogo muestra una mascota menos
  que el seed original. No se hizo ninguna acción de admin que escriba ni se tocó la BD directamente.
- Inicios de sesión usados: admin ×1, adoptante ×1, QA ×2. Ningún 429.

---

## Anexo D · Diseño visual


Agente: Diseño visual · Fecha: 2026-11-15 · Modo: solo lectura (no se ha modificado el repo ni escrito datos).

Método: lectura de `app/static/css/styles.css` (330 líneas), las 16 plantillas y `base.html`; Playwright (Chromium) a 1280 px y 375 px
con sesión guardada (1 login por usuario); volcado de estilos computados de todos los nodos visibles por página
(`estilos_computados.json`) y sondeo de estados hover/active/focus (`estados.json`).

Carpeta de evidencias: `<carpeta-auditoria>/diseno/`
(capturas en `capturas/`, scripts `login.py`, `capturas.py`, `estados.py`).

Rutas cubiertas: `/`, `/mascotas/`, `/mascotas/1`, `/mascotas/3`, `/mascotas/?especie=Loro` (vacío), `/auth/login`, `/auth/registro`,
`/mascotas/admin`, `/mascotas/admin/nueva`, `/mascotas/admin/editar/1`, `/solicitudes/admin`, `/solicitudes/admin/revisar/2`,
`/solicitudes/detalle/1` (admin y adoptante), `/solicitudes/mis-solicitudes`, `/solicitudes/nueva/1`.

---

### 1. Inventario de tokens

#### 1.1 Variables declaradas (`styles.css:10-19`)

| Variable | Valor | Uso real |
|---|---|---|
| `--color-primary` | `#219ebc` | **No se usa en CSS** (solo comentario). Aparece *hardcoded* 6 veces en `index.html` (SVG `fill` x3, `.step-number`). |
| `--color-secondary` | `#8ecae6` | navbar, `.btn-light`, foco de `.form-control`, placeholders de placehold.co |
| `--color-dark` | `#023047` | texto de `body`, navbar, footer, outline de foco |
| `--color-light` | `#f1f8fb` | fondo de `body` |
| `--color-white` | `#ffffff` | cards, footer |
| `--color-primary-dark` | `#1a7a94` | `.btn-primary` (fondo real del botón principal) |
| `--color-primary-darker` | `#145f73` | hover de `.btn-primary` |

Ninguna variable se conecta con las de Bootstrap (`--bs-primary`, `--bs-body-color`, `--bs-link-color`, `--bs-border-radius`…),
así que todo componente de Bootstrap que no se haya sobrescrito a mano conserva el tema por defecto.

#### 1.2 Colores computados en pantalla (todas las páginas, 1280 px)

**Texto (10 valores):** `#212529` (1088 nodos, Bootstrap) · `#023047` (551, sistema) · `#fff` (137) · `rgba(33,37,41,.75)` (67, `text-muted`) ·
`rgba(0,0,0,.65)` (18) · `#055160` (18, alert-info) · `#000` (13) · **`#0d6efd` (11, azul Bootstrap)** · `#6c757d` (9) · `#f8f9fa` (1).

**Fondos (11 valores):** `#fff` · `#8ecae6` · `#1a7a94` · `#198754` (success) · `#6c757d` (secondary) · `#023047` · `#219ebc` · `#cff4fc` (info) ·
`#ffc107` (warning) · **`#0d6efd`** · `#dc3545` (danger).

**Hex sueltos en código fuera de variables:** `#7ab9d4` (hover btn-light, `styles.css:97`), `#6c757d` (`styles.css:194`), `#dc3545` x2
(`styles.css:222-223`), `white` (`styles.css:213`, `index.html:155,165`), `fill="red"` (`mascotas/admin/lista.html:155`), `#219ebc` x4 (`index.html`),
`rgba(2,48,71,.4/.5)` (hero), `rgba(142,202,230,.25)` (foco input).

Conclusión: paleta declarada de 7 tokens, pero **≈17 colores distintos** llegan a pantalla; 6 son de Bootstrap sin mapear
(azul `#0d6efd`, gris `#212529`/`#6c757d`, verde, amarillo, rojo, cian de alertas).

#### 1.3 Tipografía

- Familia: **una sola**, `Arial, Helvetica, sans-serif` (`styles.css:27`). Sin webfont.
- Tamaños computados (10): 64 · 32 · 28 · 24 · 20 · 16 · 14 · 12.25 · 12 · 10.5 px. Los de 12.25 y 10.5 son `.badge`/`small` anidados en `.small`.
- Pesos computados: 400 (1513), 700 (273), **500 (124)** y **300 (3)**. Arial no tiene 500 ni 300: los títulos de Bootstrap (`h1-h6` = 500) y `.lead` (300)
  se renderizan a 400 → titulares "finos", menos peso que el nombre de la marca.
- Interlineado: el de Bootstrap (1.5 cuerpo, 1.2 títulos); ninguno propio.
- Escala propia: no existe; mezcla `px` (16, 14, 42, 18, 24) y `rem` (1.5, 1.2, 1.25, 0.9, 0.875).

#### 1.4 Espaciado, radios, sombras

- Espaciado: utilidades de Bootstrap en plantillas + valores sueltos en CSS: 20px/40px (navbar), 15px/30px (btn-primary), 15px (card-body),
  20px (grid gap), 30px, 80px/40px, 100px/20px (hero). No hay escala propia.
- Radios computados (6 bases): 4px (btn-sm), **5px** (btn-primary, alert — propio), **6px** (Bootstrap por defecto), **8px** (card propio, btn-lg),
  **10px** (hero), 50% (pasos). Ninguno en variable.
- Sombras (3 distintas para lo mismo, "tarjeta"): `0 2px 6px rgba(0,0,0,.1)` (`.card`, propia) · `0 .125rem .25rem rgba(0,0,0,.075)` (`shadow-sm`)
  · `0 .5rem 1rem rgba(0,0,0,.15)` (`shadow`, login/registro).
- Transiciones: solo las de Bootstrap (`.15s ease-in-out` en botones e inputs); ninguna propia. No hay `transition: all` ni `will-change`.
- Modo oscuro: no existe.

#### 1.5 Estilos en línea y CSS embebido

10 atributos `style=` en 8 plantillas + 1 bloque `<style>` en `index.html:149-192`:

| Archivo:línea | Estilo |
|---|---|
| `index.html:76` | `height: 250px; object-fit: cover` |
| `solicitudes/mis_solicitudes.html:19` | `height: 200px; object-fit: cover` |
| `solicitudes/detalle.html:25` | `height: 250px; object-fit: cover` |
| `solicitudes/admin/revisar.html:19` | `height: 200px; object-fit: cover` |
| `mascotas/detalle.html:47`, `solicitudes/detalle.html:75,98,126` | `width: 40%` / `30%` en `<th>` |
| `mascotas/admin/form.html:120` | `max-height: 150px` |
| `auth/login.html:49` | `width/height: 24px; object-fit: contain` |
| `index.html:149-192` | `<style>` con `.hero-home`, `.step-number` (`#219ebc`, `white`), `.icon-box` |

Son la razón documentada de `'unsafe-inline'` en `style-src` de la CSP (`app/__init__.py:44-48`).

#### 1.6 Uso de clases Bootstrap (conteo en plantillas)

`text-muted` 40 · `btn-primary` 20 · `badge` 18 · `btn-light` 10 · `btn-lg` 11 · `btn-outline-secondary` 8 · `btn-outline-dark` 6 ·
`shadow-sm` 5 · `bg-success/warning/secondary` 5 c/u · `btn-outline-primary` 3 · `bg-danger` 3 · `shadow` 2 · `bg-primary` 1 · `btn-success`/`btn-danger` 1.

---

### 2. Hallazgos

Formato: pantalla o archivo:línea · problema · impacto · evidencia · gravedad · esfuerzo · propuesta.

#### DIS-01 · Azul por defecto de Bootstrap (`#0d6efd`) conviviendo con la paleta teal
- **Dónde:** `index.html:138` (CTA `bg-primary`), `index.html:98`, `solicitudes/mis_solicitudes.html:63`, `solicitudes/detalle.html:36`
  (`btn-outline-primary`), enlaces de texto en `auth/login.html:58` y `auth/registro.html:77`, página activa de `macros/paginacion.html:22`.
- **Problema:** `.btn-primary` se recolorea a mano con `!important`, pero `--bs-primary`/`--bs-link-color` no se redefinen; todo lo demás
  "primary" sale en el azul eléctrico de Bootstrap. En inicio, el bloque CTA final es un rectángulo `#0d6efd` con un botón `#8ecae6`.
- **Impacto:** dos azules de marca que compiten; el bloque más grande de color de la home no es de la marca; los enlaces parecen de otra web.
- **Evidencia:** `capturas/inicio_1280.png` (bloque "¿Listo para cambiar una vida?" y botones "Ver Perfil"), `capturas/login_1280.png`
  ("Regístrate aquí"), `capturas/mis_solicitudes_1280.png` ("Ver Detalles"); 11 nodos de texto y 3 fondos `rgb(13,110,253)` en `estilos_computados.json`.
- **Gravedad:** alta · **Esfuerzo:** S
- **Propuesta:** en `:root` definir `--bs-primary`, `--bs-primary-rgb`, `--bs-link-color(-rgb)`, `--bs-link-hover-color` y las variables
  `--bs-btn-*` de `.btn-primary`/`.btn-outline-primary` y `.pagination` a partir de `--color-primary-dark`; o compilar Bootstrap con Sass y
  `$primary`. Eliminar después los `!important` de `styles.css:56-66`.

#### DIS-02 · Dos colores de texto base según el contenedor
- **Dónde:** `styles.css:26` (`body { color: #023047 }`) frente a `.card`, `.table`, `h*` dentro de cards que usan `--bs-body-color` (`#212529`).
- **Problema:** fuera de tarjetas el texto es azul noche; dentro de tarjetas y tablas es gris carbón. Títulos de página idénticos salen en
  colores distintos (`h2` "Mascotas Disponibles…" `#023047` vs `h2` "Iniciar Sesión" `#212529`; `h5` "Lys" `#023047` vs `h5` "Características" `#212529`).
- **Impacto:** la marca pierde su tono; la página parece montada a trozos. Leve pero omnipresente (1088 vs 551 nodos).
- **Evidencia:** `estilos_computados.json` (colors); comparar `capturas/catalogo_1280.png` y `capturas/detalle_1280.png`.
- **Gravedad:** alta · **Esfuerzo:** S
- **Propuesta:** fijar `--bs-body-color`, `--bs-emphasis-color`, `--bs-heading-color`, `--bs-card-color`, `--bs-table-color` y
  `--bs-secondary-color` (para `text-muted`) desde `--color-dark`; borrar las reglas `color: var(--color-dark)` repetidas de `.card-title`, `.card-text`, `.form-label`.

#### DIS-03 · Sistema de botones fragmentado (6 alturas, 4 radios, `btn-lg` roto)
- **Dónde:** `styles.css:56-62` (`.btn-primary { padding: 15px 30px; font-size: 16px; border-radius: 5px; border: none !important }`),
  `styles.css:90-94` (`.btn-light { border: none !important }`), `styles.css:237-246` (`.d-flex.gap-2 .btn { font-size: 1.25rem … }`).
- **Problema:** la regla de `.btn-primary` pisa las variables de tamaño, así que `btn-lg`/`btn-sm` no tienen efecto en el botón principal
  y cualquier `btn-primary` mide 54 px. El selector `.d-flex.gap-2 .btn` cambia el tamaño de los botones según la utilidad de layout del padre.
  Medidas reales: 31, 36 (`btn-light` sin borde), 38, 46, 48 y 54 px; radios 4/5/6/8 px; tipografía 14/16/20 px.
- **Impacto:** en la home los dos CTA del hero tienen distinto tamaño de letra (16 vs 20 px) y radio (5 vs 8); en el catálogo "Filtrar"
  (20 px) es más grande que "Ver Detalles" (16 px); "← Volver" (36 px) es 2 px más bajo que un botón bordeado a su lado. Sensación de falta de oficio.
- **Evidencia:** `capturas/inicio_1280.png` (hero), `capturas/catalogo_1280.png`, `capturas/admin_mascotas_1280.png` ("Todas" 15/30 px de padding
  frente a 6/12 px del resto del grupo); `estilos_computados.json` → comps `.btn`.
- **Gravedad:** alta · **Esfuerzo:** M
- **Propuesta:** definir una escala de 3 tamaños (sm 32 / md 40 / lg 48 px) vía `--bs-btn-padding-*`, `--bs-btn-font-size`, `--bs-btn-border-radius`
  en `.btn` y variantes, sin `!important`; borrar `.d-flex.gap-2 .btn` y `.card-body .btn-group .btn`; mantener el borde (transparente) en `btn-light`.

#### DIS-04 · Estados de interacción ausentes o anulados
- **Dónde:** `styles.css:192-195` (hover de filtros anulado a propósito), `styles.css:57,65` (`!important` en `background-color` de `.btn-primary`
  anula `:active` y la variable de `:disabled`), `.card` sin estado hover aunque la tarjeta entera es la unidad de navegación.
- **Problema:** medido con Playwright: filtro `btn-outline-secondary` reposo = hover (`transparent`/`#6c757d`); `btn-primary` active = hover
  (`#145f73`), sin hundimiento ni cambio; tarjeta de mascota sin cambio de sombra/elevación al pasar. No hay estado loading en ningún envío
  (los botones "Enviar Solicitud", "Crear Mascota", "Aprobar" no se deshabilitan ni muestran spinner).
- **Impacto:** los segmentos de filtro no parecen pulsables; los envíos no dan acuse visual → dobles clics; la interfaz se siente estática.
- **Evidencia:** `estados.json` (`filtro_reposo` vs `filtro_hover`, `btnprim_hover` vs `btnprim_active`, `card_reposo` vs `card_hover`),
  `capturas/estado_card_hover.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** hover sutil en segmentos (fondo `--color-light`), `:active { transform: scale(.97) }` con `transition-property: transform, background-color`
  (respetando `prefers-reduced-motion`), hover de tarjeta con sombra un nivel más alta y enlace de "tarjeta completa" (`.stretched-link`);
  estado `is-loading` (`disabled` + spinner) añadido desde `app.js` en `submit`.

#### DIS-05 · Dos (en realidad cinco) versiones de la tarjeta de mascota
- **Dónde:** `index.html:74-104` vs `mascotas/catalogo.html:68-94`; además `mis_solicitudes.html:18-23`, `solicitudes/detalle.html:24-39`, `solicitudes/admin/revisar.html:18-27`.
- **Problema:** foto 250 / 180 / 200 / 250 / 200 px; metadatos como badges grises (inicio) o texto con `•` (catálogo); separador `•` vs `-`;
  CTA "Ver Perfil" contorno azul Bootstrap vs "Ver Detalles" relleno teal; grid `row/col-md-4` vs `.cards-grid`.
- **Impacto:** el mismo objeto (una mascota) se reconoce peor entre pantallas; la home y el catálogo parecen de productos distintos.
- **Evidencia:** `capturas/inicio_1280.png` vs `capturas/catalogo_1280.png` vs `capturas/mis_solicitudes_1280.png`.
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** macro Jinja `tarjeta_mascota(mascota, variante)` en `templates/macros/`, foto con `aspect-ratio: 4/3` en vez de alturas fijas,
  un único formato de metadatos y un único CTA.

#### DIS-06 · Estilos en línea, `<style>` embebido y CSS muerto
- **Dónde:** ver tabla 1.5; `styles.css:171-189` (`.hero` sin uso, con `https://placehold.co/1200x400`).
- **Problema:** dimensiones de imagen y colores definidos en plantillas (`#219ebc` repetido 4 veces en `index.html`), fuera del sistema;
  la regla `.hero` no se usa (la home usa `.hero-home` embebido).
- **Impacto:** cambios de marca requieren tocar plantillas; obliga a mantener `'unsafe-inline'` en `style-src` de la CSP.
- **Evidencia:** `grep -rn 'style="' app/templates` (10 resultados), `index.html:149-192`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** mover todo a `styles.css` con clases (`.foto-mascota--lg`, `.tabla-ficha th { width: 40% }`, `.logo-proveedor`), borrar `.hero`,
  `fill="currentColor"` + clase de color en los SVG; luego retirar `'unsafe-inline'` (coordinar con el agente de QA/seguridad).

#### DIS-07 · Selector global `.card img { height: 180px }` que obliga a parches
- **Dónde:** `styles.css:109-113`; parches en `styles.css:326-331` (`.mascota-detail-img` con 4 `!important`) y los `style="height:…"` de 1.5.
- **Problema:** toda imagen dentro de cualquier `.card` queda a 180 px; cada pantalla lo combate con línea o `!important`. La regla
  `styles.css:309-313` también redefine `.col-md-4` de Bootstrap globalmente.
- **Impacto:** fragilidad: una imagen nueva en una card (logo, avatar, miniatura) se deforma; especificidad en escalada.
- **Evidencia:** fragmentos citados; `capturas/admin_revisar_1280.png` (foto a 200 px por estilo en línea).
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** clase específica `.tarjeta-mascota__foto { aspect-ratio: 4/3; object-fit: cover; width: 100% }` y no estilar elementos por anidamiento;
  no sobrescribir clases de grid de Bootstrap.

#### DIS-08 · Tipografía sin personalidad ni jerarquía real
- **Dónde:** `styles.css:27`; títulos Bootstrap con `font-weight: 500`.
- **Problema:** Arial sola; los pesos 500/300 caen a 400, así que `h2` de 32 px se ve "fino" al lado de la marca en negrita y de `nav-link`
  en negrita; 10 tamaños sin escala (10.5 y 12.25 px en badges de la home).
- **Impacto:** jerarquía plana, aspecto de prototipo; badges de 10.5 px difíciles de leer.
- **Evidencia:** `capturas/inicio_1280.png` ("Nuestras Últimas Incorporaciones" más ligero que "Portal de Adopción"), `estilos_computados.json` (sizes, weights).
- **Gravedad:** media · **Esfuerzo:** M
- **Propuesta:** familia web con 400/600/700 reales (p. ej. Atkinson Hyperlegible para cuerpo, pensada para legibilidad, + una display con carácter;
  ver direcciones), escala modular 1.25 (14/16/20/25/31/39 px) en variables `--fs-*`, `--bs-headings-font-weight: 600`, badge mínimo 12 px.

#### DIS-09 · Cabeceras de página sin patrón
- **Dónde:** `catalogo.html:9`, `mascotas/admin/lista.html:9` (h2 izquierda + subtítulo), `solicitudes/detalle.html:47` y `admin/revisar.html:171`
  (h3 dentro de la card), `solicitudes/nueva.html:16-17` y `mascotas/admin/form.html:18` (h2 centrado dentro de card + h4 gris), `auth/*` (h2 centrado).
- **Problema:** el título de página cambia de nivel (h1 solo en la home, h2/h3 en el resto), de tamaño (28/32 px), de alineación y de contenedor;
  subtítulos de sección alternan `h5` normal y `h6.text-muted`; el botón "← Volver" queda alineado al contenedor mientras el formulario está
  centrado en `col-8`, con bordes izquierdos que no coinciden.
- **Impacto:** el usuario no tiene un ancla visual constante; las pantallas de detalle parecen menos importantes que los listados.
- **Evidencia:** `capturas/nueva_solicitud_1280.png` (botón volver vs card centrada), `capturas/admin_revisar_1280.png`, `capturas/catalogo_1280.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** macro `cabecera_pagina(titulo, subtitulo, volver_url, accion)` con un único estilo (h1, alineado a la izquierda, volver como
  enlace-miga encima), usada en todas las páginas; secciones internas siempre `h2` de la escala.

#### DIS-10 · Badges de estado sin semántica propia
- **Dónde:** `mascotas/detalle.html:34-40`, `mascotas/admin/lista.html:127-133`, `solicitudes/admin/lista.html:77-83`,
  `solicitudes/detalle.html:51-57`, `mis_solicitudes.html:29-35`; badges informativos `bg-secondary` en `index.html:88-97`.
- **Problema:** colores genéricos de Bootstrap (verde/amarillo/rojo/gris) ajenos a la paleta; el mismo estado con textos distintos
  ("Disponible" / "Disponible para adopción", "Pendiente" / "Pendiente de revisión" / "¡Aprobada!"); tres tamaños (10.5/12/16 px con `fs-6`);
  y el gris de "Adoptado" es el mismo que el de los badges neutros "2 años · Pequeño" de la home.
- **Impacto:** el estado, que es el dato clave para adoptante y administrador, no se lee de forma consistente; "Adoptado" parece una etiqueta más.
- **Evidencia:** `capturas/admin_mascotas_1280.png`, `capturas/admin_solicitudes_1280.png`, `capturas/inicio_1280.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** macro `badge_estado(estado)` con mapa único estado→(texto, token) y tokens `--estado-disponible/-proceso/-adoptado/-pendiente/-aprobada/-rechazada`
  derivados de la paleta (fondo claro + texto oscuro, con punto o icono además del color); badges neutros con otro estilo (contorno).

#### DIS-11 · La rejilla del catálogo no casa con el contenedor
- **Dónde:** `styles.css:131-144` (`repeat(auto-fill, minmax(250px, 300px))` + `justify-content: start`).
- **Problema:** a 1280 px caben 3 columnas de 300 px y quedan ~176 px vacíos a la derecha, desalineados con la tarjeta de filtros de ancho completo;
  a 375 px las tarjetas (máx. 300 px) quedan centradas y más estrechas que el filtro (sangría de ~27 px por lado).
- **Impacto:** la página principal del producto se ve descuadrada; en móvil las fotos se ven más pequeñas de lo posible.
- **Evidencia:** `capturas/catalogo_1280.png`, `capturas/catalogo_375.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** `grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr))` y eliminar la media query de `justify-content`.

#### DIS-12 · Tablas de administración poco pulidas
- **Dónde:** `mascotas/admin/lista.html:55-169`, `solicitudes/admin/lista.html:50-110`, `styles.css:210-224, 272-279`.
- **Problema:** celdas con `vertical-align: top` (el texto queda arriba y los botones de 38 px y badges debajo de la línea base);
  "Edad" sin unidad; fecha en `small` (otro tamaño); indicador ▲▼ solo en la columna activa (las demás no parecen ordenables);
  botones de acción de 34×38 px (28,8×38 a 375 px); icono de eliminar con `fill="red"` (`#ff0000`, fuera de paleta, `lista.html:155`);
  el hover rojo depende del texto del atributo `title="Eliminar"` (`styles.css:221`); "Total" y paginación dentro de la card en mascotas y fuera en solicitudes (`solicitudes/admin/lista.html:114`).
- **Impacto:** lectura más lenta de filas; dependencia frágil del copy para el estilo; aspecto poco cuidado en la herramienta de trabajo diaria.
- **Evidencia:** `capturas/admin_mascotas_1280.png`, `capturas/estado_fila_hover_eliminar.png`, `capturas/estado_fila_hover_editar.png`, `estados.json` (`fila_valign`, `accion_btn_size_375`).
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** `table.align-middle`, `font-variant-numeric: tabular-nums` en ID/edad/fecha, icono ⇅ tenue en columnas ordenables,
  clase `.btn-accion--peligro` en vez de `[title=…]`, `fill="currentColor"`, botones de acción ≥ 40×40 px, pie de tabla común (total + paginación).

#### DIS-13 · Filtros de estado: control segmentado con dos lenguajes
- **Dónde:** `mascotas/admin/lista.html:25-42`, `solicitudes/admin/lista.html:20-37`.
- **Problema:** segmento activo `btn-primary` teal relleno (padding 15/30 px por DIS-03) y los inactivos `btn-outline-secondary` gris Bootstrap
  (`#6c757d`, padding 6/12 px); sin hover (DIS-04). El gris no pertenece a la paleta y el contraste visual entre activo e inactivo es extremo.
- **Impacto:** parece un grupo de botones descompuesto más que un filtro; sin feedback al pasar.
- **Evidencia:** `capturas/admin_mascotas_1280.png`, `capturas/admin_solicitudes_1280.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** componente `.filtro-segmentado` (o `nav-pills`) con tokens propios: inactivo texto `--color-dark` sobre blanco, hover `--color-light`,
  activo teal; mostrar recuento por estado en cada segmento.

#### DIS-14 · Botón "+ Nueva Mascota" a ancho completo en escritorio
- **Dónde:** `mascotas/admin/lista.html:13` (`w-100 w-md-auto`; `w-md-auto` no existe en Bootstrap 5).
- **Problema:** el botón ocupa los 356 px de la columna y 54 px de alto a cualquier ancho; pesa visualmente más que el título.
- **Impacto:** jerarquía invertida en la cabecera del panel.
- **Evidencia:** `capturas/admin_mascotas_1280.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** `w-100` solo en móvil con una clase propia (`@media (min-width: 768px) { width: auto }`), o integrarlo en la macro de cabecera (DIS-09).

#### DIS-15 · Acciones primaria y secundaria con el mismo peso
- **Dónde:** `solicitudes/nueva.html:162-171`, `mascotas/admin/form.html:150-159` (Enviar/Crear + Cancelar a 50 %, Cancelar relleno azul claro),
  `solicitudes/admin/revisar.html:119-126` (Aprobar verde y Rechazar rojo a 50 %, 20 px), `catalogo.html:53-56` (Filtrar / Limpiar).
- **Problema:** las parejas de botones se reparten el ancho a partes iguales y la acción secundaria va rellena; la decisión destructiva
  (rechazar) tiene la misma prominencia que la afirmativa, ambas en colores Bootstrap.
- **Impacto:** más riesgo de pulsar la acción equivocada; el CTA principal no destaca.
- **Evidencia:** `capturas/nueva_solicitud_1280.png`, `capturas/admin_revisar_1280.png`, `capturas/catalogo_1280.png`.
- **Gravedad:** media · **Esfuerzo:** S
- **Propuesta:** primario relleno con ancho por contenido (o completo solo en móvil), secundario como botón de contorno/enlace;
  en revisar, "Aprobar" primario y "Rechazar" de contorno en tono de peligro.

#### DIS-16 · El footer no queda pegado al fondo en páginas cortas
- **Dónde:** `base.html:109` (`<footer class="text-center py-4 mt-5">`) frente a `styles.css:157` (`margin-top: auto`).
- **Problema:** `.mt-5` lleva `!important` y anula el `margin-top: auto` del layout flex; en páginas cortas aparece una franja de fondo bajo el footer.
- **Impacto:** acabado descuidado en login, panel de solicitudes y estados vacíos.
- **Evidencia:** `capturas/admin_solicitudes_1280.png` y `capturas/login_1280.png` (franja clara bajo el footer azul).
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** quitar `mt-5` del footer (el espacio ya lo da `main.my-4`) o usar `mt-auto`.

#### DIS-17 · Radios y sombras sin tokens
- **Dónde:** `styles.css:59,103,104,148`, `index.html:153` (hero 10 px), clases `shadow`/`shadow-sm` en plantillas.
- **Problema:** 5 radios base (4/5/6/8/10 px) y 3 sombras distintas para "tarjeta"; tarjetas de inicio con `shadow-sm`, catálogo con la sombra propia,
  login con `shadow` fuerte.
- **Impacto:** superficies que deberían ser iguales se perciben a distintas alturas; incoherencia sutil acumulada.
- **Evidencia:** `estilos_computados.json` (radii, shadows); `capturas/login_1280.png` vs `capturas/catalogo_1280.png`.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** `--radius-sm: 6px; --radius-md: 10px; --radius-lg: 16px` mapeados a `--bs-border-radius*`; dos sombras (`--sombra-1` reposo, `--sombra-2` hover/overlay)
  con capas transparentes; quitar `shadow`/`shadow-sm` de plantillas.

#### DIS-18 · Ritmo vertical y alineaciones irregulares
- **Dónde:** `index.html:110-134` (bloque "Proceso": `p-5` + `mb-4` en columnas + margen de `<p>` → ~90 px abajo vs 48 px arriba);
  `mis_solicitudes.html:42-54` (dos fechas en párrafos separados por 16 px); `solicitudes/nueva.html` (etiqueta de dos líneas en
  "emergencia veterinaria" desalinea los dos `select` de la fila); `mascotas/detalle.html` (columna de foto termina mucho antes que la ficha).
- **Impacto:** composición que "baila"; bloques con más aire abajo que arriba se perciben sin terminar.
- **Evidencia:** `capturas/inicio_1280.png`, `capturas/mis_solicitudes_1280.png`, `capturas/nueva_solicitud_1280.png`, `capturas/detalle_1280.png`.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** escala de espaciado (`--esp-1..8` sobre 4/8 px), `> :last-child { margin-bottom: 0 }` en contenedores, filas de formulario
  con `align-items-end`, fechas en una sola línea de metadatos, foto `position: sticky` en el detalle.

#### DIS-19 · Placeholder sin foto genérico y dependiente de un tercero
- **Dónde:** `index.html:78`, `catalogo.html:72`, `mascotas/detalle.html:21`, `mis_solicitudes.html:21`, `solicitudes/detalle.html:27` (placehold.co);
  `solicitudes/admin/revisar.html:18-20` sin rama `else` (sin foto no hay nada).
- **Problema:** la imagen de relleno es la palabra de la especie en grande sobre azul claro servida por `placehold.co`; si el servicio cae se ve
  una imagen rota; cada plantilla pide un tamaño distinto. En revisar la tarjeta pierde la imagen y cambia de forma.
- **Impacto:** las mascotas sin foto parecen "rotas" o de segunda; dependencia externa visible en la parte más emocional del producto.
- **Evidencia:** `capturas/estado_placeholder.png` (simulado sustituyendo el `src` en el navegador; no se tocaron datos).
- **Gravedad:** baja · **Esfuerzo:** M
- **Propuesta:** SVG locales en `app/static/img/` (silueta por especie + genérica) con el fondo de la marca y servidos con la misma proporción que las fotos.

#### DIS-20 · Detalles de pulido (make-interfaces-feel-better)
| Principio | Antes | Después |
|---|---|---|
| Ajuste de titulares | "Encuentra a tu Compañero / Perfecto" deja una palabra huérfana (`inicio_1280.png`) | `h1,h2,h3 { text-wrap: balance }`; `p { text-wrap: pretty }` |
| Números tabulares | IDs, edades, fechas y contadores de la home con cifras proporcionales | `.table, .estadistica { font-variant-numeric: tabular-nums }` |
| Contorno de imágenes | Fotos claras (Nala sobre fondo blanco) se funden con la card blanca | `img.foto { outline: 1px solid rgba(0,0,0,.08); outline-offset: -1px }` |
| Suavizado | sin `-webkit-font-smoothing` | `html { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale }` |
| Pulsación | sin estado `:active` | `scale(.97)` 120 ms en `.btn`, desactivado con `prefers-reduced-motion` |
| Radio concéntrico | Card 8 px con imagen superior; hero 10 px; botones 5 px dentro de cards de 8 px | radios desde tokens (DIS-17) |
| Iconos | SVG de estadísticas con `fill="#219ebc"` fijo | `fill="currentColor"` + clase de color |
- **Gravedad:** baja · **Esfuerzo:** S

#### DIS-21 · Marca resuelta con un emoji y una barra sobredimensionada
- **Dónde:** `base.html:26` (`🐾 Portal de Adopción`), `styles.css:31-34` (navbar `padding: 20px 40px`, 86 px de alto).
- **Problema:** el logotipo es un emoji cuyo dibujo y color dependen del sistema (azul en Linux/Noto, marrón en Apple, otro en Windows);
  la navbar azul claro ocupa 86 px y la marca es solo texto Arial en negrita.
- **Impacto:** identidad no controlable; no hay activo de marca reutilizable (favicon, OG image).
- **Evidencia:** `capturas/inicio_1280.png`, `capturas/inicio_375.png`.
- **Gravedad:** baja · **Esfuerzo:** M
- **Propuesta:** isotipo SVG propio (huella o silueta) con `currentColor`, favicon a juego, navbar a 64 px.

#### DIS-22 · Alertas informativas cian usadas como contenedor de contenido
- **Dónde:** `solicitudes/nueva.html:21-23`, `mis_solicitudes.html:57-59`, `solicitudes/detalle.html:160-163`, estados vacíos
  (`catalogo.html:99-104`, `mascotas/admin/lista.html:180-187`, `solicitudes/admin/lista.html:118-123`, `mis_solicitudes.html:73-80`).
- **Problema:** el cian de `alert-info` (`#cff4fc`/`#055160`) no pertenece a la paleta y se usa para intro de formulario, comentarios
  del administrador y estados vacíos (con `<hr>` interno), es decir, para tres cosas distintas con el mismo aspecto de aviso.
- **Impacto:** ruido cromático; los estados vacíos parecen errores en lugar de invitaciones a actuar.
- **Evidencia:** `capturas/nueva_solicitud_1280.png`, `capturas/mis_solicitudes_1280.png`, `capturas/catalogo_vacio_1280.png`.
- **Gravedad:** baja · **Esfuerzo:** S
- **Propuesta:** componente `.estado-vacio` (ilustración + texto + botón), bloque "nota del refugio" con borde izquierdo teal para comentarios,
  `--bs-info-*` mapeado a la paleta para los flashes.

#### DIS-23 · Sin modo oscuro ni base para tematizar
- **Dónde:** `styles.css` completo (colores fijos, ninguna regla `prefers-color-scheme`); Bootstrap 5.3 ya soporta `data-bs-theme`.
- **Problema/impacto:** no es un fallo hoy, pero con colores fijos y `!important` no es posible añadirlo sin reescribir; señal de que no hay capa de tokens.
- **Evidencia:** `grep -c prefers-color-scheme app/static/css/styles.css` → 0.
- **Gravedad:** baja · **Esfuerzo:** M (tras DIS-01/02/17)
- **Propuesta:** construir los tokens semánticos (`--superficie`, `--texto`, `--borde`, `--acento`) y solo entonces valorar `data-bs-theme="dark"`.

#### Puntuación del sistema (ecc:design-system, modo auditoría, 0-10)

| Dimensión | Nota | Motivo principal |
|---|---|---|
| Consistencia de color | 3 | 7 tokens declarados, ~17 colores en pantalla (DIS-01/02) |
| Jerarquía tipográfica | 4 | Arial, pesos 500 inexistentes, 10 tamaños (DIS-08/09) |
| Ritmo de espaciado | 5 | utilidades Bootstrap correctas, valores sueltos en CSS (DIS-18) |
| Consistencia de componentes | 3 | botones, tarjetas y badges con varias versiones (DIS-03/05/10) |
| Responsive | 6 | funciona, con descuadres en grid (DIS-11) |
| Modo oscuro | 0 | no existe (DIS-23) |
| Animación | 4 | solo transiciones Bootstrap; nada gratuito, pero sin feedback (DIS-04) |
| Accesibilidad visual | 7 | foco visible y contraste cuidados en navbar/botones; objetivos pequeños en tablas |
| Densidad | 6 | razonable; panel admin podría ser más compacto |
| Pulido | 3 | hover/active/loading ausentes, footer, placeholders (DIS-04/16/19/20) |

#### Observaciones fuera de mi ámbito (para el organizador)
- `/solicitudes/admin/revisar/2` muestra vacías las respuestas "Tipo", "Propiedad", "Experiencia previa", "Horas solo/a", "Emergencia veterinaria"
  y "Motivación" de la solicitud del seed (`capturas/admin_revisar_1280.png`): posible desajuste de claves del cuestionario → agente funcional.
- La foto del seed de "Toby (Beagle)" es un chow-chow con gafas (`capturas/mis_solicitudes_1280.png`) → contenido/seed.
- Durante la auditoría apareció en el catálogo una mascota "QA-Func-Doble" creada por otro agente; las capturas posteriores pueden incluirla.

---

### 3. Dirección visual

#### Valoración de la identidad actual
Lo que hay es **Bootstrap 5 por defecto con una capa de color encima** ("Azul claro/medio/oscuro" de una paleta popular de coolors):
hero con foto oscurecida y titular centrado, fila de tres tarjetas de estadística con icono, rejilla de tarjetas iguales, "Proceso en 4 pasos"
con círculos numerados y banda CTA final. Es la plantilla genérica de landing, y nada en ella dice "refugio de animales" salvo las fotos y el emoji.
Tiene una base valiosa: el contraste de la navbar y del botón principal ya se corrigió con criterio, el foco visible es sólido y las fotos de
los animales son buenas. Lo que falta no es decoración sino **un sistema** (tokens conectados a Bootstrap, componentes únicos) y **un punto de vista**.

El público es doble: adoptantes (decisión emocional, móvil, quieren conocer al animal) y personal del refugio (tarea repetitiva, escritorio,
quieren estados claros). La identidad debería poner al animal en primer plano en la parte pública y ser sobria y eficiente en el panel.

#### Dirección A — "Evolucionar": el sistema actual, ordenado
- **Idea:** mantener la paleta azul noche/teal/cielo y Bootstrap, pero conectarla de verdad: tokens en `:root` mapeados a `--bs-*`, una escala tipográfica,
  macros de tarjeta/badge/cabecera, estados de interacción. Tipografía: Atkinson Hyperlegible (cuerpo y títulos a 700), elegida por legibilidad para un público amplio.
- **Tokens:** `#023047` tinta · `#1a7a94` acción · `#8ecae6` cielo (superficies de apoyo, no botones) · `#f1f8fb` fondo · estados derivados del teal/ámbar/rojo propios.
- **Qué cambia a la vista:** coherencia, no carácter; seguirá leyéndose como "una app Bootstrap bien hecha".
- **Coste:** S-M, 2-4 días. Resuelve DIS-01..18 y 20, 22. Riesgo bajo; tests de accesibilidad existentes siguen valiendo.

#### Dirección B — "Ficha de acogida": el animal como protagonista
- **Idea:** inspirarse en el material real de un refugio — la ficha del animal en la jaula, la chapa del collar, el sello de "adoptado".
  Tarjetas con foto grande (4:5, retrato), nombre en tipografía display de gran tamaño, datos como chapas pequeñas con icono
  (edad, tamaño, sexo, vacunado), sello de estado en la esquina de la foto. Detalle en dos columnas con foto pegajosa y la historia del animal antes que la tabla.
  Panel admin sobrio en la misma paleta, sin decoración.
- **Paleta (alejada del azul genérico y de los tópicos crema/terracota):** verde pino `#1F4E46` (marca, acción) · amarillo collar `#F2B705` (acento puntual: sellos, "nuevo")
  · tinta `#17211F` · piedra `#E7EBE9` (superficies) · blanco `#FFFFFF` · rojo arcilla `#B3412E` solo para peligro.
- **Tipo:** display con carácter y redondez (p. ej. Bricolage Grotesque 700) para nombres y titulares; Atkinson Hyperlegible para todo lo demás.
- **Un único gesto memorable:** el nombre del animal enorme sobre la foto en el detalle; todo lo demás, silencioso.
- **Coste:** M-L, 1,5-2 semanas: Bootstrap compilado con Sass (`$primary`, `$font-family-*`, radios), rediseño de inicio/catálogo/detalle,
  set de iconos e ilustraciones de placeholder, actualización de e2e y de `tests/test_accesibilidad.py` si cambian estructuras. Riesgo medio.

#### Dirección C — Sistema propio sin Bootstrap en la parte pública
- **Idea:** tokens CSS propios (capas `@layer`, custom properties, `clamp()` para tipografía fluida), componentes pequeños escritos a medida;
  Bootstrap queda solo en el panel admin (o se elimina del todo). Permite una maquetación editorial: catálogo en mosaico con tamaños variados,
  home que abre con un animal concreto ("Hoy busca casa: Calcetines") en lugar del hero genérico.
- **Ventajas:** control total, CSS más ligero, modo oscuro y CSP sin `'unsafe-inline'` desde el diseño; identidad inconfundible.
- **Coste:** L, 3-5 semanas; reescritura de todas las plantillas públicas, JS propio para menú móvil/desplegable, pruebas e2e y de accesibilidad
  rehechas. Riesgo alto para un proyecto mantenido por una persona; solo tiene sentido si la identidad es un objetivo de producto.

#### Recomendación para el comité
Hacer **A primero en cualquier caso** (es la base de tokens que B y C necesitan y corrige los hallazgos altos), y decidir B como evolución
de la capa visual sobre esa base. C solo si se quiere abandonar Bootstrap por otros motivos (peso, CSP, mantenimiento).

---

## Anexo E · Accesibilidad


Alcance: revisión estática de `app/templates/**`, `styles.css`, `app.js` y las rutas que renderizan formularios. Lo ya cubierto por `tests/test_accesibilidad.py` (alt, nombre accesible de enlaces y botones, aria-hidden en SVG, label for, lang="es", enlace de salto) NO se repite.
Contrastes calculados a mano (luminancia relativa WCAG) con los colores de `styles.css` y de Bootstrap 5.3.0. Lo que solo se confirma en navegador va marcado «a verificar en navegador».

Resumen: 22 hallazgos. Crítica 0 · Alta 3 · Media 12 · Baja 7.

Lo que SÍ está bien (no requiere acción): foco visible global (outline 3px #023047, 7.7:1 sobre la navbar y >14:1 sobre blanco); no hay cabecera fija, por lo que 2.4.11 se cumple; título `<title>` distinto por página; `lang="es"`; navbar con `aria-label`, toggler con `aria-expanded`/`aria-controls`; `aria-current="page"` en Inicio/Mascotas; botones de icono con nombre; objetivos táctiles ≥ 24 px (botones sm de tabla ≈ 29–34 × 31 px); contrastes de btn-primary (#1a7a94 con blanco 4,93:1; #145f73 7,2:1), navbar (#023047 sobre #8ecae6 7,7:1), footer (13,9:1), badges (success 4,53; danger 4,53; secondary 4,69; warning con texto oscuro alto), text-muted (≈6,7:1), alertas de Bootstrap (>7:1); confirmación de borrado con `window.confirm` (accesible de forma nativa).

---

### A11Y-01 · Los errores de servidor borran lo que el usuario escribió
- Pantalla/archivo: registro, login, alta y edición de mascota. `app/routes/auth.py:70-79,108,137-151`; `app/routes/mascotas.py:186-218,284-320`; redirecciones en `mascotas.py:204,301`; plantillas `auth/registro.html`, `auth/login.html`, `mascotas/admin/form.html`.
- Criterio: 3.3.7 Entrada redundante (A en 2.2), 3.3.3 Sugerencias ante errores.
- Problema: `render_template('auth/registro.html')` se llama sin pasar `request.form`, y los inputs no tienen `value=`. Tras un error (contraseñas distintas, contraseña corta) hay que reescribir los 7 campos. En login se pierde el email. En alta de mascota se pierden todos los campos. En edición se vuelve a pintar el objeto de BD, así que se descartan los cambios. Un formato de imagen no válido hace `redirect(request.url)` y vacía el formulario completo.
- Impacto: personas con discapacidad motriz, con baja visión (usan ampliación) o cognitiva, y usuarios de lector de pantalla o dictado. Reescribir todo es una barrera real y a menudo abandonan.
- Evidencia: `return render_template('auth/registro.html')` en las 4 ramas de error; el input de email no tiene `value`.
- Gravedad: alta · Esfuerzo: M
- Solución: pasar `request.form` a la plantilla y rellenar `value="{{ form.get('x','') }}"` (excepto contraseñas). En edición, preferir el valor enviado sobre el de BD. Para el error de imagen, renderizar en vez de redirigir.
- Test: POST con datos no válidos y comprobar que el email/nombre reaparecen en el HTML.

### A11Y-02 · Grupos de radios sin `fieldset`/`legend` y `label for` huérfano
- Pantalla: `solicitudes/nueva.html:51-72` (jardín, otras mascotas) y `:121-149` (compromisos).
- Criterio: 1.3.1 Información y relaciones, 4.1.2, 3.3.2 Etiquetas o instrucciones.
- Problema: la pregunta es un `<label for="tiene_jardin">` y no existe ningún elemento con ese id, así que la etiqueta no está asociada a nada. Los radios quedan sin el nombre del grupo. En «Compromisos» las opciones se leen «No puedo garantizarlo» sin saber de qué.
- Impacto: usuarios de lector de pantalla oyen «Sí, botón de opción 1 de 2» sin pregunta. Los usuarios de control por voz y los de lupa también pierden el contexto.
- Evidencia: `<label for="tiene_jardin" class="form-label">¿Tiene jardín o patio? *</label>` seguido de `id="jardin_si"` y `id="jardin_no"`.
- Gravedad: alta · Esfuerzo: S
- Solución: `<fieldset><legend class="form-label fs-6">¿Tiene jardín o patio? *</legend> …radios… </fieldset>`. En compromisos, añadir un `legend` por bloque («Gastos veterinarios», «Tiempo diario»).
- Test: ampliar `Analizador` para exigir que todo `input[type=radio]` con el mismo `name` esté dentro de un `fieldset` con `legend`, y que ningún `label[for]` apunte a un id inexistente.

### A11Y-03 · Bordes de campos y casillas sin contraste (1.4.11)
- Pantallas: todos los formularios (`form-control`, `form-select`, `form-check-input`). `styles.css:161-164` solo cambia el borde en foco.
- Criterio: 1.4.11 Contraste de elementos no textuales (3:1).
- Problema: el borde por defecto de Bootstrap 5.3 en `.form-control`/`.form-select` es #dee2e6, que da 1,30:1 sobre el blanco. El de `.form-check-input` es rgba(0,0,0,.25) ≈ #bfbfbf, 1,84:1. Los límites del control son lo único que lo identifica como campo.
- Impacto: personas con baja visión o con sensibilidad al contraste no distinguen dónde está el campo, ni si un radio o checkbox está sin marcar.
- Evidencia: L(#dee2e6)=0,757 → 1,05/0,807 = 1,30:1. L(#bfbfbf)=0,521 → 1,05/0,571 = 1,84:1. El `border-color` en foco (#8ecae6) da 1,79:1, aunque ahí ayuda el outline de 3px.
- Gravedad: alta · Esfuerzo: S
- Solución: en `styles.css`, `.form-control, .form-select, .form-check-input { border-color: #6c757d; }` (4,69:1 sobre blanco). Valorar también el borde de `.card` (ahora `border: none`).
- Test: no es posible con HTML; añadir una prueba que lea `styles.css` y compruebe que esa regla existe.

### A11Y-04 · Errores no asociados a campos y foco sin gestionar tras el envío
- Pantallas: `auth/login.html`, `auth/registro.html`, `mascotas/admin/form.html` (todos los errores llegan por `flash()`).
- Criterio: 3.3.1 Identificación de errores, 1.3.1, 4.1.3 Mensajes de estado, 2.4.3 Orden del foco.
- Problema: el error es un banner genérico arriba; ningún campo lleva `aria-invalid="true"` ni `aria-describedby`. No se mueve el foco al banner ni a un resumen. Además `autofocus` en el email de login/registro hace que, tras el error, el foco salte al primer campo y el lector de pantalla se salte el mensaje (el `role="alert"` de una página recién cargada se anuncia de forma inconsistente: a verificar en navegador con NVDA/VoiceOver).
- Impacto: usuarios de lector de pantalla y de ampliación, que no ven el banner superior ni saben qué campo corregir.
- Evidencia: `<input type="email" ... required autofocus>`, sin `aria-describedby`; las rutas solo llaman a `flash(...)`.
- Gravedad: media · Esfuerzo: M
- Solución: pasar un dict `errores` a la plantilla; por campo, `<div id="email-error" class="invalid-feedback d-block">` + `aria-invalid="true" aria-describedby="email-error"`; resumen de errores con `tabindex="-1"` que reciba el foco en `app.js` cuando exista `[data-resumen-errores]`. Quitar `autofocus` cuando hay errores (o del todo).
- Test: POST inválido y comprobar `aria-invalid`.

### A11Y-05 · Enlaces idénticos «Ver Detalles / Ver Perfil / Ver Detalles» repetidos
- Pantallas: `mascotas/catalogo.html:91-92`, `index.html:98-100`, `solicitudes/mis_solicitudes.html:63-65`, `solicitudes/detalle.html:36`.
- Criterio: 2.4.4 Propósito del enlace (en contexto); anti-patrón «Click here» del proyecto.
- Problema: en el listado de enlaces de un lector de pantalla aparecen 12 veces «Ver Detalles» sin contexto. El encabezado de la tarjeta no cuenta como contexto programático (solo lo son el párrafo, el elemento de lista o la celda).
- Impacto: usuarios de lector de pantalla que navegan por lista de enlaces, y de control por voz («pulsar Ver Detalles» es ambiguo).
- Evidencia: `<a ... class="btn btn-primary w-100">Ver Detalles</a>`.
- Gravedad: media · Esfuerzo: S
- Solución: `aria-label="Ver detalles de {{ mascota.nombre }}"` (el nombre visible «Ver Detalles» debe quedar contenido al inicio, por 2.5.3), o `aria-labelledby` con id del título y del enlace.
- Test: comprobar que en el catálogo no hay dos enlaces con el mismo nombre accesible y distinto `href`.

### A11Y-06 · Enlaces dentro de texto sin subrayado, distinguibles solo por color
- Archivos: `auth/login.html:58` («Regístrate aquí»), `auth/registro.html:77` («Inicia sesión aquí»); ambos con `text-decoration-none` dentro de `<p class="text-muted">`.
- Criterio: 1.4.1 Uso del color.
- Problema: el enlace (#0d6efd) y el texto que lo rodea (≈#595c5f) solo se diferencian por tono. El contraste entre ambos es ≈1,5:1, por debajo de los 3:1 exigidos si no hay otra pista.
- Impacto: personas con daltonismo o baja visión no ven que es un enlace.
- Evidencia: L(#0d6efd)=0,183, L(texto muted)=0,106 → (0,233)/(0,156)=1,49:1.
- Gravedad: media · Esfuerzo: S
- Solución: quitar `text-decoration-none` (o añadir `fw-bold` + subrayado). Lo mismo para los `<a>` de cabecera de tabla (ver A11Y-09).
- Test: buscar `text-decoration-none` en enlaces dentro de `<p>`.

### A11Y-07 · Sin `autocomplete` en campos personales ni de autenticación
- Archivos: `auth/login.html:17,24`; `auth/registro.html:17,25,32,39,46,54,61`.
- Criterio: 1.3.5 Identificar el propósito de la entrada (AA); 3.3.8 Autenticación accesible.
- Problema: no hay ningún atributo `autocomplete`. Debería haber `username`/`email`, `current-password`, `given-name`, `family-name`, `tel`, `street-address` y `new-password` (×2). El campo «nombre» y «apellidos» están separados y se pueden mapear.
- Impacto: personas con discapacidad cognitiva o motriz que dependen del autocompletado y del gestor de contraseñas. La autenticación (3.3.8) no bloquea el pegado, pero sin `autocomplete` los gestores funcionan peor.
- Evidencia: `<input type="password" ... id="password" name="password" placeholder="Tu contraseña" required>`.
- Gravedad: media · Esfuerzo: S
- Solución: añadir los valores de `autocomplete` indicados. Mantener Google como alternativa (ya existe).
- Test: exigir `autocomplete` en `input[type=email|tel|password]` de login y registro.

### A11Y-08 · Filtros por estado: estado activo solo visual y grupo sin nombre
- Archivos: `mascotas/admin/lista.html:25-42`, `solicitudes/admin/lista.html:20-37`.
- Criterio: 1.4.1 Uso del color, 4.1.2 Nombre, función, valor, 1.3.1.
- Problema: el filtro activo se señala con `btn-primary` (relleno) frente a `btn-outline-secondary` (contorno), sin `aria-current`. El `role="group"` no tiene nombre accesible (el `<h5>` «Filtrar por Estado» no está asociado). Además `styles.css:192-195` anula el hover de `btn-outline-secondary` (queda transparente, sin feedback).
- Impacto: usuarios de lector de pantalla no saben qué filtro está aplicado.
- Evidencia: `<div class="btn-group ... " role="group">` y `class="btn {% if estado_filtro == 'disponible' %}btn-primary{% else %}...`.
- Gravedad: media · Esfuerzo: S
- Solución: `aria-current="true"` en el enlace activo y `aria-labelledby` del grupo apuntando al `<h5>` (con id). Añadir un hover visible (borde/fondo).
- Test: en `/mascotas/admin?estado=disponible` comprobar un único `aria-current`.

### A11Y-09 · Tablas de datos sin `caption`, sin `scope` y ordenación sin `aria-sort`
- Archivos: `mascotas/admin/lista.html:55-116`, `solicitudes/admin/lista.html:50-60`, `mascotas/detalle.html:44`, `solicitudes/detalle.html:72,95,123`.
- Criterio: 1.3.1, 4.1.2, 1.4.1.
- Problema: (a) ninguna `<table>` tiene `<caption>` ni `aria-label`; (b) los `<th>` de columna y de fila no llevan `scope` (los clave/valor de detalle usan `<th>` como cabecera de fila, `scope="row"`); (c) las columnas ordenables son enlaces con las glifos ▲/▼ en el texto (se leen «triángulo negro hacia arriba») y sin `aria-sort` en el `<th>`; (d) los enlaces de cabecera tienen `text-dark text-decoration-none`, de modo que no se ve que son ordenables salvo por el cursor.
- Impacto: usuarios de lector de pantalla: no se anuncia la tabla ni la ordenación vigente; con lupa no hay pista de que la cabecera sea interactiva.
- Evidencia: `<a href="...orden='id'..." class="text-dark text-decoration-none">ID {% if orden_campo == 'id' %}▲...`.
- Gravedad: media · Esfuerzo: M
- Solución: `<caption class="visually-hidden">Mascotas del refugio</caption>`; `scope="col"`/`scope="row"`; `aria-sort="ascending|descending"` en el `th` activo; glifos en `<span aria-hidden="true">`; subrayado o icono visible en los enlaces de cabecera.
- Test: toda `<table>` tiene `caption`; todo `th` tiene `scope`.

### A11Y-10 · A ≤ 768 px se oculta una columna de la tabla y las regiones con scroll no son enfocables
- Archivo: `styles.css:290-306`.
- Criterio: 1.4.10 Reflow (pérdida de información al ampliar), 1.3.1, 2.1.1.
- Problema: `.table th:nth-child(4), .table td:nth-child(4) { display:none }` esconde «Raza» (admin mascotas) y «Fecha» (admin solicitudes). Al ampliar al 200–400 % en escritorio el viewport efectivo es ≤ 768 px y esa columna desaparece también para los lectores de pantalla. Además `.table-responsive` se desplaza horizontalmente sin `tabindex`/`role`/nombre.
- Impacto: personas con baja visión que usan zoom pierden datos; los usuarios de teclado puede que no puedan desplazar la tabla (Chrome sí enfoca regiones con scroll; a verificar en Firefox/Safari).
- Evidencia: `.table th:nth-child(4), .table td:nth-child(4) { display: none; }`.
- Gravedad: media · Esfuerzo: M
- Solución: no ocultar columnas; dejar que `.table-responsive` haga el scroll, o convertir las filas en tarjetas en móvil. Añadir `tabindex="0" role="region" aria-label="Tabla de mascotas"` al contenedor.
- Test: no automatizable con parser; comprobar en e2e a 640 px que las cabeceras visibles son las mismas.

### A11Y-11 · Jerarquía de encabezados: sin `h1` en 12 de las 13 páginas, saltos y cifras como `h3`
- Archivos: todas las plantillas salvo `index.html` empiezan en `<h2>` (`catalogo.html:9`, `login.html:10`, `detalle.html:31`, etc.). `index.html:34,47,60` usa `<h3>` para cifras (`{{ total_mascotas }}`), antes del `<h2>` de la línea 70, y salta a `<h5>` en las tarjetas (`:82`, `:115`). `mis_solicitudes.html:25` y `solicitudes/detalle.html:47,71,94` saltan de h2/h3 a h5/h6; `nueva.html:19` usa h4 tras h2.
- Criterio: 1.3.1 y 2.4.6 (técnica H42/G141).
- Problema: sin `h1` la navegación por encabezados no tiene raíz. Hay saltos de nivel, y un «número» como encabezado no describe contenido. Los pasos del proceso (`index.html:113-132`) son `div`s con un número, no una lista ordenada.
- Impacto: usuarios de lector de pantalla que navegan por encabezados (tecla H).
- Evidencia: `<h2>Mascotas Disponibles para Adopción</h2>` sin `<h1>` en el catálogo.
- Gravedad: media · Esfuerzo: M
- Solución: un `<h1>` por página (cambiar los `h2` de título a `h1`), niveles consecutivos (`h5.card-title` → `h2`/`h3` con clase visual), cifras en `<p class="h3">` o `<dl>`, pasos en `<ol>`.
- Test: añadir al `Analizador` «exactamente un h1» y «sin saltos de nivel».

### A11Y-12 · Mensajes flash: anuncio, ubicación y foco
- Archivo: `base.html:89-101`.
- Criterio: 4.1.3 Mensajes de estado, 1.3.1 (contenido fuera de landmarks), 2.4.3.
- Problema: (a) todos los flash llevan `role="alert"` (asertivo), incluso «Bienvenido» o «Sesión cerrada», que deberían ser `role="status"`; (b) el bloque está fuera de `<main>` y el enlace «Saltar al contenido» (`#contenido`) lo salta; (c) al cerrar un aviso con el botón, Bootstrap lo elimina y el foco se pierde en `<body>`; (d) los `role="alert"` estáticos de las páginas (`catalogo.html:99`, `mis_solicitudes.html:73`, etc.) no son mensajes dinámicos.
- Impacto: usuarios de lector de pantalla (anuncios interrumpen sin necesidad o no se oyen) y de teclado (pérdida de foco).
- Evidencia: `<div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">`.
- Gravedad: media · Esfuerzo: S
- Solución: `role="alert"` solo para `danger`/`warning`, `role="status"` para el resto; mover el bloque dentro de `<main>` antes del contenido; en `app.js`, al cerrarse un aviso, devolver el foco a `main`; quitar `role="alert"` a los avisos estáticos.
- Test: flash `success` con `role="status"`.

### A11Y-13 · Texto blanco sobre foto del héroe: contraste no garantizado
- Archivo: `index.html:150-156` (CSS inline), `:9-18`.
- Criterio: 1.4.3 Contraste mínimo, 1.4.11.
- Problema: el texto blanco (`.lead`, 20 px, peso 300, no es «texto grande») y el botón `btn-outline-light` se asientan sobre una foto externa con una capa rgba(2,48,71,.5). En el peor caso (zonas blancas de la foto) el fondo resultante es ≈#80979f: L≈0,296 → blanco 3,04:1 (<4,5). Si la imagen de Unsplash no carga, el fondo es #f1f8fb con la capa, ≈3,2:1.
- Impacto: personas con baja visión; en móvil con brillo alto.
- Evidencia: `linear-gradient(rgba(2,48,71,0.5), rgba(2,48,71,0.5)), url('https://images.unsplash.com/...')`.
- Gravedad: media · Esfuerzo: S · A verificar en navegador (depende de la foto).
- Solución: subir la capa a ≥ .65–.7 (blanco sobre #6b8591 baja a ≈ 4,3:1; con .75 supera 4,5:1 en el peor caso), y poner `background-color: var(--color-dark)` de reserva.
- Test: no automatizable.

### A11Y-14 · Páginas de error (404, 403, 429, 500) sin plantilla propia
- Archivo: `app/__init__.py:170` (solo hay manejador de 413); no existen plantillas `404.html`, etc.
- Criterio: 3.1.1 Idioma de la página, 2.4.2 Título, 3.2.3 Navegación coherente, 2.4.5.
- Problema: se muestran las páginas por defecto de Werkzeug/Flask-Limiter: en inglés, sin `lang`, sin navegación ni enlace de vuelta.
- Impacto: personas con lector de pantalla (pronunciación en inglés errónea) y con discapacidad cognitiva (sin salida clara).
- Evidencia: `grep errorhandler` devuelve solo el 413.
- Gravedad: media · Esfuerzo: M
- Solución: `errorhandler` para 403/404/429/500 que renderice `errores/error.html` extendiendo `base.html` con h1 y enlaces a inicio/catálogo.
- Test: `client.get('/no-existe')` → HTML con `lang="es"` y `<h1>`.

### A11Y-15 · Paginación: `aria-current` en el `<li>` y enlaces solo con números
- Archivo: `macros/paginacion.html:22,25`.
- Criterio: 4.1.2, 2.4.4.
- Problema: `aria-current="page"` está en el `<li>`, no en el elemento que contiene el texto; varios lectores no lo anuncian. Los enlaces «2», «3» no dicen a qué se refieren. «Anterior/Siguiente» deshabilitados son `<span>` sin `aria-disabled`.
- Impacto: usuarios de lector de pantalla.
- Evidencia: `<li class="page-item active" aria-current="page"><span class="page-link">{{ numero }}</span></li>`.
- Gravedad: baja · Esfuerzo: S
- Solución: `aria-current="page"` en el `<span class="page-link">`; `aria-label="Página {{ numero }}"`; `aria-disabled="true"` en los deshabilitados.
- Test: la página actual tiene `aria-current` en el `span`.

### A11Y-16 · Instrucciones solo en placeholder o `<small>` sin asociar
- Archivos: `auth/registro.html:19,48,55`; `mascotas/admin/form.html:101`; `solicitudes/nueva.html:157`; `solicitudes/admin/revisar.html:116`.
- Criterio: 3.3.2 Etiquetas o instrucciones, 1.3.1.
- Problema: el requisito de la contraseña («Mínimo 8 caracteres») solo está en el placeholder y desaparece al escribir. Las ayudas en `<small class="text-muted">` no están vinculadas con `aria-describedby`. El asterisco `*` de «obligatorio» no se explica en ninguna página. Los placeholders de ejemplo («Juan», «666123456») pueden confundirse con valores.
- Impacto: usuarios con discapacidad cognitiva o memoria limitada, y de lector de pantalla (no oyen la ayuda).
- Evidencia: `placeholder="Mínimo 8 caracteres" minlength="8"`.
- Gravedad: media · Esfuerzo: S
- Solución: `<small id="password-ayuda">` + `aria-describedby`; leyenda «Los campos con * son obligatorios» al inicio del formulario.
- Test: todo `small` de ayuda dentro de un `.mb-3` con input tiene id referenciado por `aria-describedby`.

### A11Y-17 · Sin confirmación ni revisión en acciones irreversibles
- Archivos: `solicitudes/admin/revisar.html:119-126`; `solicitudes/nueva.html:161-170`.
- Criterio: 3.3.4 Prevención de errores (legales, financieros, de datos).
- Problema: «Aprobar» y «Rechazar» cambian el estado de forma definitiva (la ruta responde «ya ha sido revisada» después) y no piden confirmación, a diferencia del borrado, que sí usa `data-confirmar`. El envío de la solicitud (que incluye compromisos) tampoco tiene paso de revisión.
- Impacto: personas con discapacidad motriz o cognitiva que pulsan por error el botón contiguo (están pegados, 8 px).
- Evidencia: `<button type="submit" name="accion" value="rechazar" class="btn btn-danger flex-grow-1">` sin `data-confirmar` en el `<form>`.
- Gravedad: baja · Esfuerzo: S
- Solución: reutilizar `data-confirmar` (ya soportado por `app.js`); en `app.js`, usar `event.submitter` para un mensaje por botón.
- Test: `data-confirmar` presente en el formulario de revisión.

### A11Y-18 · Emoji y glifos decorativos leídos por el lector de pantalla
- Archivos: `base.html:26` (🐾), `catalogo.html:85` y similares (•), «← Volver» (`detalle.html:9`, `form.html:9`, `nueva.html:9`, etc.), «+ Nueva Mascota» (`lista.html:14`), «✓/✗» en botones y textos (`revisar.html:57-94,121,124`), «Sí ✓» (`mascotas/detalle.html:76,80`).
- Criterio: 1.1.1 (ruido), buenas prácticas.
- Problema: se anuncia «patas de animal», «flecha hacia la izquierda», «signo más», «marca de verificación», lo que ensucia el nombre del enlace/botón.
- Impacto: usuarios de lector de pantalla.
- Gravedad: baja · Esfuerzo: S
- Solución: envolver en `<span aria-hidden="true">`. En «✓ Se compromete…» el texto ya dice el significado.
- Test: opcional.

### A11Y-19 · Textos alternativos de las fotos de mascotas
- Archivos: `catalogo.html:70,73`, `index.html:76,79`, `mis_solicitudes.html:19,22`, `solicitudes/detalle.html:25,28`, `form.html:120` («Foto actual»).
- Criterio: 1.1.1.
- Problema: `alt` es solo el nombre, justo encima de un `<h5>` con el mismo nombre (lectura doble). La imagen de reserva `placehold.co/...?text=Perro` lleva el mismo alt aunque no es una foto de la mascota. En «Foto actual» no se dice de quién. La foto de `revisar.html:19` no tiene reserva.
- Impacto: usuarios de lector de pantalla (redundancia) y usuarios ciegos (no hay descripción real).
- Gravedad: baja · Esfuerzo: S
- Solución: en las tarjetas con título, `alt=""` (decorativa) o `alt="Foto de {{ nombre }}, {{ especie }}"`; en la reserva, `alt=""`; en detalle de mascota, `alt="Foto de {{ nombre }}"`. Permitir al admin añadir una descripción.
- Test: no hay alt duplicado exacto del `h5` adyacente (difícil), o alt vacío en placeholders.

### A11Y-20 · `.step-number` y SVG con #219ebc: contraste justo
- Archivo: `index.html:158-170,30,43,56`.
- Criterio: 1.4.3 / 1.4.11.
- Problema: blanco sobre #219ebc = 3,14:1 (L=0,284 → 1,05/0,334). Pasa solo porque el número es 24 px en negrita (texto grande, umbral 3:1). El comentario de `styles.css:16` ya reconoce que #219ebc con blanco no cumple 4,5:1.
- Impacto: personas con baja visión; si alguien reduce el tamaño de letra deja de ser «grande».
- Gravedad: baja · Esfuerzo: S
- Solución: usar `var(--color-primary-dark)` (4,93:1).

### A11Y-21 · Reflow a 320 px y unidades en `px` (verificar)
- Archivos: `styles.css:31-34,251-260` (`.navbar` padding 20px 40px / 15px 20px, `.navbar-brand` 1.2 rem nowrap), `.card-text {font-size: 14px}`, `.btn-primary {font-size:16px}`.
- Criterio: 1.4.10 Reflow, 1.4.4 Cambio de tamaño del texto.
- Problema: a 320 px el contenedor útil ≈ 280 px; la marca «🐾 Portal de Adopción» (≈200 px) + toggler (≈56 px) + padding 40 px queda al límite, y Bootstrap permitirá que el toggler baje de línea, sin scroll horizontal pero con aspecto roto. Los tamaños fijos en px ignoran el tamaño de letra preferido del navegador (el zoom sí funciona).
- Impacto: baja visión con ampliación al 400 %, o con tamaño de fuente aumentado en el sistema.
- Gravedad: baja · Esfuerzo: S · A verificar en navegador (320 px, 400 % de zoom; la regla `.col-md-4` del bloque ≤768 px parece inocua).
- Solución: usar `rem` y `padding` con `clamp()`; permitir que `.navbar-brand` envuelva (`white-space: normal`).

### A11Y-22 · Landmarks y navegación: detalles menores
- Archivo: `base.html:23-87`; `catalogo.html:20`.
- Criterio: 1.3.1, 2.4.1, 4.1.2.
- Problema: (a) la `<nav>` no está dentro de un `<header>`, por lo que no hay landmark `banner`; (b) los enlaces «Iniciar Sesión» y «Registrarse» y los de los paneles no marcan `aria-current` en su propia página; (c) el desplegable de usuario se anuncia solo con el nombre («Aarón, botón»), sin indicar que es un menú (`href="#"` + `role="button"`); (d) el formulario de filtros del catálogo no es un landmark `search` ni lleva `aria-label`; (e) el catálogo no anuncia el número de resultados tras filtrar, y las tarjetas están en `div`s en lugar de una lista.
- Impacto: usuarios de lector de pantalla.
- Gravedad: baja · Esfuerzo: S
- Solución: `<header>` alrededor de la nav; `aria-current` en login/registro; `aria-label="Menú de usuario, {{ nombre }}"` o texto oculto «Menú de»; `role="search"` en el formulario de filtros; `<ul>` para las tarjetas y `<p aria-live="polite">N mascotas encontradas</p>`.
- Test: `role="search"` en el catálogo, landmark `banner`.

---

### Propuestas de ampliación de `tests/test_accesibilidad.py`
Resumen de las comprobaciones factibles con el `Analizador` actual: un único `h1` y sin saltos de nivel (A11Y-11); radios agrupados en `fieldset/legend` y ausencia de `label[for]` huérfano (A11Y-02); `autocomplete` en login/registro (A11Y-07); `caption` y `scope` en tablas (A11Y-09); `aria-current` único en filtros y paginación (A11Y-08, A11Y-15); `role="status"` para flash no críticos (A11Y-12); páginas de error con `lang` y `h1` (A11Y-14); persistencia de valores tras POST inválido (A11Y-01).
Todas las demás (contraste, reflow, foco real) requieren navegador: Playwright + axe-core en `tests/e2e/` cubriría contraste (A11Y-03, A11Y-13, A11Y-20) y reflow a 320 px (A11Y-10, A11Y-21).

---

## Anexo F · Textos


Agente: Textos (microcopy) · Fecha: 2026-11-15 · Método: lectura de `app/templates/**`, `flash()` de
`app/routes/*.py`, `app/decorators.py`, `app/__init__.py` y `app/static/js/app.js`, más peticiones GET
anónimas a http://localhost:5000 para comprobar las páginas de error (no se inició sesión ni se enviaron
formularios). Skill aplicada: `design:ux-copy` (claro, conciso, coherente, útil, humano; errores = qué
pasó + por qué + cómo arreglarlo; estados vacíos = qué es + por qué está vacío + cómo empezar;
confirmaciones = acción concreta + consecuencia + botones con verbo).

### Resumen

| Gravedad | N.º | IDs |
|---|---|---|
| Crítica | 0 | — |
| Alta | 5 | TXT-01 a TXT-05 |
| Media | 20 | TXT-06 a TXT-25 |
| Baja | 20 | TXT-26 a TXT-45 |
| **Total** | **45** | |

Patrones de fondo: (1) las respuestas de error de Flask/Werkzeug/Flask-Limiter/Flask-WTF salen en inglés;
(2) valores internos y nombres de campo técnicos llegan al usuario; (3) mayúsculas a la inglesa (Title
Case) en casi todos los botones y encabezados; (4) mezcla de tú/usted y de géneros; (5) los estados de
la solicitud no dicen al adoptante qué pasa después.

---

### Gravedad alta

#### TXT-01 · Páginas de error 404/405/500 en inglés y sin salida
- **Dónde:** `app/__init__.py:170` (solo existe manejador para 413). Afecta a toda `db.get_or_404()`
  (`app/routes/mascotas.py:94,266,364`, `app/routes/solicitudes.py:37,124,188`) y a cualquier URL mal
  escrita. Pantalla: comprobado con `GET /no-existe` y `GET /mascotas/999999`.
- **Texto actual:** «404 Not Found — Not Found — The requested URL was not found on the server. If you
  entered the URL manually please check your spelling and try again.» (página con `lang=en`, sin
  cabecera ni navegación). Lo mismo para 500 «Internal Server Error» y 405.
- **Problema:** idioma distinto al del sitio, tono técnico, sin marca ni enlace para volver.
- **Impacto:** un adoptante que sigue un enlace antiguo a una mascota ya borrada cree que la web está
  rota y abandona; en un 500 no sabe si su solicitud se envió.
- **Texto propuesto (plantillas `errors/404.html`, `errors/500.html` que extiendan `base.html`):**
  - 404 — Título: «No encontramos esta página» · Cuerpo: «Puede que la mascota ya no esté en el
    catálogo o que el enlace sea incorrecto.» · Botones: «Ver mascotas disponibles» / «Ir al inicio».
  - 500 — Título: «Algo ha fallado» · Cuerpo: «No hemos podido completar la acción por un problema
    nuestro. Vuelve a intentarlo dentro de unos minutos. Si estabas enviando una solicitud, comprueba
    en Mis solicitudes si se ha guardado.» · Botón: «Ir al inicio».
  - 405 (reutilizar la 404 o): «Esta acción no está disponible desde aquí.»
- **Gravedad:** alta · **Esfuerzo:** M

#### TXT-02 · Bloqueo por demasiados intentos de inicio de sesión en inglés
- **Dónde:** `app/routes/auth.py:115` (`@limiter.limit`), `config.py:52` (`5 per minute`); no hay
  manejador 429. Pantalla: Iniciar sesión tras 5 intentos en un minuto. (No se reprodujo para no gastar
  el límite compartido; es la respuesta por defecto de Flask-Limiter.)
- **Texto actual:** «429 Too Many Requests — 5 per 1 minute».
- **Problema:** inglés, jerga técnica, no dice cuánto esperar ni qué hacer.
- **Impacto:** quien ha olvidado la contraseña (justo el usuario más frustrado) recibe un muro en inglés.
- **Texto propuesto:** volver a `auth/login.html` con aviso: «Has hecho demasiados intentos. Espera un
  minuto y vuelve a intentarlo.» (categoría `warning`).
- **Gravedad:** alta · **Esfuerzo:** S

#### TXT-03 · Error de token CSRF caducado en inglés (se pierde el cuestionario)
- **Dónde:** `app/__init__.py:92` (`csrf.init_app`) sin manejador de `CSRFError`; todos los formularios
  POST, sobre todo `solicitudes/nueva.html:26` (cuestionario largo).
- **Texto actual:** «400 Bad Request — The CSRF token has expired.» (por defecto de Flask-WTF; también
  «The CSRF token is missing.»).
- **Problema:** inglés, jerga («CSRF token»), y no dice que hay que recargar.
- **Impacto:** quien tarda más de una hora en rellenar el cuestionario pierde las respuestas y ve un
  error incomprensible.
- **Texto propuesto:** redirigir a la misma página con aviso: «Tu sesión ha caducado por seguridad.
  Vuelve a enviar el formulario.» (y, si es posible, conservar los datos).
- **Gravedad:** alta · **Esfuerzo:** S

#### TXT-04 · Aprobar o rechazar una solicitud no pide confirmación
- **Dónde:** `app/templates/solicitudes/admin/revisar.html:120-125`; `app/static/js/app.js:4-8` solo
  confirma formularios con `data-confirmar` (únicamente el de eliminar mascota). Pantalla: Revisar
  solicitud (admin).
- **Texto actual:** botones «✓ Aprobar Adopción» y «✗ Rechazar Solicitud», sin diálogo.
- **Problema:** acción irreversible (aprobar marca la mascota como adoptada; rechazar es definitivo y
  el mensaje queda visible para el solicitante) sin confirmación; además los dos botones nombran
  objetos distintos (adopción/solicitud).
- **Impacto:** un clic equivocado decide una adopción sin vuelta atrás.
- **Texto propuesto:** botones «Aprobar solicitud» / «Rechazar solicitud». Confirmaciones (el JS debe
  leer `event.submitter.dataset.confirmar`):
  - «¿Aprobar la solicitud de {nombre} para {mascota}? {mascota} pasará a «Adoptada» y se cerrarán sus
    demás solicitudes. No se puede deshacer.»
  - «¿Rechazar la solicitud de {nombre} para {mascota}? {nombre} verá el rechazo y tu comentario. No se
    puede deshacer.»
  (Ajustar «se cerrarán sus demás solicitudes» a lo que haga realmente el modelo.)
- **Gravedad:** alta · **Esfuerzo:** M

#### TXT-05 · Respuestas del cuestionario mostradas con valores internos
- **Dónde:** `app/templates/solicitudes/detalle.html:99,103,131,135` y
  `app/templates/solicitudes/admin/revisar.html:55-56,69-70`; valores definidos en
  `app/templates/solicitudes/nueva.html:35-37,95-97,105-107`. Pantallas: Detalle de solicitud
  (adoptante y admin) y Revisar solicitud.
- **Texto actual:** «Horas solo al día: 0-4» / «4-8» / «8+»; «Emergencia veterinaria: veterinario» /
  «consulta» / «espera»; «Tipo de vivienda: Finca» (el usuario eligió «Finca/Campo»); «Propiedad:
  Propia».
- **Problema:** se muestra el `value` del `<option>`, no la etiqueta que eligió el usuario; «espera» o
  «8+» no se entienden fuera de contexto.
- **Impacto:** el administrador decide una adopción leyendo códigos; el adoptante no reconoce sus
  propias respuestas.
- **Texto propuesto:** mapear valor → etiqueta (un diccionario compartido entre formulario y vistas):
  `0-4` → «Menos de 4 horas», `4-8` → «Entre 4 y 8 horas», `8+` → «Más de 8 horas»;
  `veterinario` → «Lo llevaría al veterinario de inmediato», `consulta` → «Consultaría primero en
  internet», `espera` → «Esperaría a ver cómo evoluciona»; `finca` → «Finca o casa de campo»;
  `propia`/`alquilada` → «Propia»/«De alquiler».
- **Gravedad:** alta · **Esfuerzo:** S

---

### Gravedad media

#### TXT-06 · Fechas y horas en UTC sin indicarlo
- **Dónde:** `solicitudes/detalle.html:60,65`; `solicitudes/mis_solicitudes.html:44,51`;
  `solicitudes/admin/lista.html:74`. Las fechas se guardan con `utcnow()` (UTC sin zona).
- **Texto actual:** «Solicitud enviada el 15/11/2026 a las 09:00» (hora UTC).
- **Problema:** en España la hora mostrada va 1-2 horas por detrás; cerca de medianoche, incluso el
  día es otro.
- **Impacto:** el adoptante ve una hora que no coincide con la de envío y desconfía.
- **Texto propuesto:** convertir a `Europe/Madrid` antes de formatear (filtro Jinja) y mantener
  «Enviada el 15/11/2026 a las 10:00». Si no se convierte, al menos «a las 09:00 (UTC)».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-07 · Mezcla de tú y usted en el cuestionario de adopción
- **Dónde:** `solicitudes/nueva.html:51,63,75` (usted) frente a `:86,102,112` y el resto del sitio (tú).
- **Texto actual:** «¿Tiene jardín o patio?», «¿Tiene otras mascotas actualmente?», «Si tiene mascotas,
  especifica (especie, edad, vacunadas)» (mezcla dentro de la misma frase); frente a «¿Tienes
  experiencia previa…?», «¿Cómo actuarías…?».
- **Problema:** tratamiento incoherente; «¿Tiene jardín?» puede leerse como «¿la mascota tiene…?».
- **Impacto:** el formulario más importante del sitio parece descuidado.
- **Texto propuesto:** «¿Tienes jardín o patio?», «¿Tienes otras mascotas?», «Si tienes otras
  mascotas, cuéntanos cuáles (especie, edad y si están vacunadas)».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-08 · «¿Cuántas horas al día estaría solo/a?»: sujeto ambiguo y rangos solapados
- **Dónde:** `solicitudes/nueva.html:92,95-97`; reflejo en `solicitudes/detalle.html:131`
  («Horas solo al día:») y `solicitudes/admin/revisar.html:69` («Horas solo/a:»).
- **Texto actual:** «¿Cuántas horas al día estaría solo/a? *» con opciones «0-4 horas», «4-8 horas»,
  «Más de 8 horas».
- **Problema:** no queda claro si «solo/a» es la persona o la mascota; «4» está en dos rangos; el
  guion debería ser «–» o mejor texto.
- **Impacto:** respuestas poco fiables para la evaluación.
- **Texto propuesto:** «¿Cuántas horas al día pasaría {{ mascota.nombre }} sin compañía?» · «Menos de 4
  horas» / «Entre 4 y 8 horas» / «Más de 8 horas». En las vistas: «Horas al día sin compañía:».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-09 · Concordancia de género con las mascotas
- **Dónde:** `mascotas/detalle.html:39` («Adoptado»), `:75` («Vacunado:»), `:79` («Esterilizado:»);
  `mascotas/admin/lista.html:28,40,132` (filtro «Todas» + «Adoptados»; insignia «Adoptado»);
  `mascotas/admin/form.html:89,132,143`; `app/routes/solicitudes.py:202` («{mascota} ya ha sido
  adoptado.»).
- **Texto actual:** «Adoptado», «Vacunado: Sí ✓», «Luna ya ha sido adoptado.»; filtros «Todas ·
  Disponibles · En Proceso · Adoptados».
- **Problema:** para hembras se lee «Luna… Adoptado»; el filtro mezcla femenino (las mascotas) y
  masculino.
- **Impacto:** sensación de dejadez justo en la ficha de la mascota.
- **Texto propuesto:** usar sustantivos neutros en etiquetas: «Vacunas: Al día / Pendientes»,
  «Esterilización: Sí / No»; estado «Adoptada» (concordando con «mascota») en filtros e insignias:
  «Todas · Disponibles · En proceso · Adoptadas»; o concordar con `mascota.sexo` cuando se conozca.
  Flash: «{mascota} ya tiene una adopción aprobada.»
- **Gravedad:** media · **Esfuerzo:** M

#### TXT-10 · Mayúsculas a la inglesa (Title Case) en botones y encabezados
- **Dónde:** prácticamente todas las plantillas. Ejemplos: `index.html:9` «Encuentra a tu Compañero
  Perfecto», `:13` «Ver Mascotas Disponibles», `:70` «Nuestras Últimas Incorporaciones», `:142`
  «Comenzar Ahora»; `base.html:53-56,61,70,78` «Panel Admin Mascotas», «Mis Solicitudes», «Cerrar
  Sesión», «Iniciar Sesión»; `auth/registro.html:10,60` «Crear Cuenta», «Confirmar Contraseña»;
  `mascotas/catalogo.html:9,19`; `mascotas/detalle.html:94` «Solicitar Adopción»;
  `mascotas/admin/form.html:19,48,152` «Edad Aproximada (años)», «Guardar Cambios», «Crear Mascota»;
  `solicitudes/nueva.html:18,28,82,152,164`; `solicitudes/detalle.html:37,71,92,94,122,161,170`;
  `solicitudes/admin/revisar.html:46,50,121,124`; listas admin «Filtrar por Estado», «En Proceso».
- **Problema:** en español solo va mayúscula la primera palabra (y nombres propios); el uso inglés
  además es inconsistente («Limpiar filtros», «Volver al catálogo» sí van bien).
- **Impacto:** lectura menos natural, aspecto de traducción.
- **Texto propuesto:** frase con mayúscula inicial: «Encuentra a tu compañero perfecto», «Ver mascotas
  disponibles», «Cerrar sesión», «Iniciar sesión», «Mis solicitudes», «Crear cuenta», «Confirmar
  contraseña», «Solicitar adopción», «Guardar cambios», «En proceso», etc.
- **Gravedad:** media · **Esfuerzo:** M

#### TXT-11 · El recorrido de adopción cambia de nombre en cada paso
- **Dónde:** `mascotas/detalle.html:94` «Solicitar Adopción», `:101` «Inicia sesión para adoptar»;
  `solicitudes/nueva.html:3` (título) «Solicitar Adopción», `:18` «Solicitud de Adopción», `:164`
  «Enviar Solicitud»; `index.html:115-131` pasos «Regístrate · Explora · Solicita · Adopta».
- **Problema:** verbo distinto en botón/título/envío; el invitado lee «adoptar» (sugiere inmediatez) y el
  paso 4 «Adopta» se describe como «Espera la aprobación».
- **Impacto:** expectativas equivocadas sobre qué ocurre al pulsar.
- **Texto propuesto:** término fijo «solicitud de adopción» / verbo «Solicitar adopción».
  Botón ficha: «Solicitar adopción» · Invitado: «Inicia sesión para solicitar la adopción» · Título del
  formulario: «Solicitar la adopción de {mascota}» · Envío: «Enviar solicitud». Pasos de inicio:
  «1. Crea tu cuenta · 2. Elige una mascota · 3. Envía tu solicitud · 4. Espera nuestra respuesta».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-12 · «Panel Admin» y sus variantes
- **Dónde:** `base.html:53-56` «Panel Admin Mascotas» / «Panel Admin Solicitudes»;
  `mascotas/admin/lista.html:4,9` «Panel Admin - Mascotas» / «Panel de Administración - Mascotas»;
  `solicitudes/admin/lista.html:4,9`; `mascotas/admin/form.html:3,9` «… - Panel Admin», «← Volver al
  panel»; `solicitudes/detalle.html:10` «← Volver al panel admin»; `solicitudes/admin/revisar.html:9`
  «← Volver al panel de solicitudes».
- **Problema:** abreviatura «Admin», cinco formas para dos pantallas, guion como separador; «Volver al
  panel admin» no dice cuál.
- **Impacto:** el personal del refugio duda de dónde está y adónde vuelve.
- **Texto propuesto:** menú «Gestionar mascotas» / «Gestionar solicitudes»; h2 «Gestión de mascotas» /
  «Gestión de solicitudes»; enlaces de vuelta «← Volver a gestión de mascotas» / «← Volver a gestión de
  solicitudes».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-13 · El mensaje al adoptante se llama de tres formas
- **Dónde:** `solicitudes/admin/revisar.html:113,116` «Comentarios para el solicitante»;
  `solicitudes/detalle.html:161` «Comentarios del Administrador»; `solicitudes/mis_solicitudes.html:58`
  «Comentarios del admin:».
- **Problema:** jerga interna («admin») ante el adoptante y nombre distinto en cada pantalla.
- **Impacto:** el adoptante no sabe quién le escribe.
- **Texto propuesto:** admin: «Mensaje para {nombre} (opcional)» + ayuda «Lo verá en el detalle de su
  solicitud.»; adoptante: «Mensaje del refugio».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-14 · Estados de la solicitud sin siguiente paso para el adoptante
- **Dónde:** `solicitudes/mis_solicitudes.html:33-39`; `solicitudes/detalle.html:51-57`.
- **Texto actual:** «Pendiente de revisión» · «¡Aprobada!» · «Rechazada».
- **Problema:** la insignia no orienta: ¿cuánto tarda?, ¿qué hago si me aprueban?, ¿puedo pedir otra?
  La app no envía correos, así que esta pantalla es el único canal.
- **Impacto:** incertidumbre y consultas al refugio; un rechazo seco sin empatía.
- **Texto propuesto (línea bajo la insignia):**
  - Pendiente: «Estamos revisando tu solicitud. Consulta esta página para ver la respuesta.»
  - Aprobada: «¡Enhorabuena! El refugio se pondrá en contacto contigo para organizar la entrega de
    {mascota}.» (ajustar al proceso real)
  - Rechazada: «Esta vez no ha podido ser. Puedes solicitar la adopción de otra mascota del catálogo.»
    + enlace «Ver mascotas disponibles».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-15 · Confirmación de envío de la solicitud vaga y repetitiva
- **Dónde:** `app/routes/solicitudes.py:89`.
- **Texto actual:** «¡Solicitud enviada con éxito para Luna! Revisaremos tu solicitud pronto.»
- **Problema:** «solicitud» dos veces, «pronto» no fija expectativas, no dice dónde seguirla (no hay
  aviso por correo).
- **Impacto:** el usuario espera un correo que no llega.
- **Texto propuesto:** «Hemos recibido tu solicitud para adoptar a Luna. Puedes seguir su estado en
  esta página.» (aparece ya en Mis solicitudes).
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-16 · El cuestionario no avisa de que la solicitud no se puede modificar ni retirar
- **Dónde:** `solicitudes/nueva.html:21-23` (intro) y `:163-165` (botón). No existe ruta para editar ni
  cancelar.
- **Texto actual:** «¡Gracias por tu interés! Por favor, completa este cuestionario para que podamos
  conocerte mejor y asegurar que Luna encuentre el hogar perfecto.»
- **Problema:** no anticipa lo que pasa al enviar (definitivo, una sola solicitud por mascota, la
  mascota deja de aparecer en el catálogo).
- **Impacto:** envíos precipitados sin posibilidad de corregir.
- **Texto propuesto:** intro: «Gracias por querer adoptar a Luna. Responde estas preguntas para que
  podamos conocerte (unos 5 minutos). Revisa tus respuestas antes de enviar: después no podrás
  cambiarlas.»
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-17 · Ficha de una mascota en proceso o adoptada sin explicación
- **Dónde:** `mascotas/detalle.html:34-40` (insignias) y `:90-105` (CTA solo si está disponible).
- **Texto actual:** «En proceso de adopción» / «Adoptado», y ningún botón.
- **Problema:** el usuario (que llega por un enlace o desde Mis solicitudes) no sabe si aún puede
  solicitarla ni qué hacer.
- **Impacto:** callejón sin salida.
- **Texto propuesto:** en proceso: «Luna ya tiene una solicitud en revisión. Mientras tanto, conoce a
  otras mascotas que buscan hogar.» + «Ver mascotas disponibles». Adoptada: «¡Luna ya ha encontrado
  hogar!» + mismo enlace.
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-18 · Estado vacío del catálogo culpa a los filtros aunque no haya filtros
- **Dónde:** `mascotas/catalogo.html:99-104`.
- **Texto actual:** «No hay mascotas disponibles / No se encontraron mascotas que coincidan con los
  filtros aplicados. / Intenta limpiar los filtros…».
- **Problema:** se muestra igual con o sin filtros.
- **Impacto:** sin filtros, el usuario pulsa «limpiar filtros» y vuelve a lo mismo.
- **Texto propuesto:** con filtros: «Ninguna mascota coincide con estos filtros. Prueba a quitar alguno
  o [ver todas las mascotas].» · Sin filtros: «Ahora mismo no hay mascotas en adopción. Vuelve pronto:
  llegan nuevas cada semana.» (ajustar la promesa a la realidad del refugio).
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-19 · Estado vacío de gestión de mascotas ignora el filtro de estado
- **Dónde:** `mascotas/admin/lista.html:180-187`.
- **Texto actual:** «No hay mascotas registradas / Comienza añadiendo una nueva mascota al sistema.»
- **Problema:** con el filtro «Adoptados» sin resultados dice que no hay ninguna mascota.
- **Impacto:** el administrador cree que se han borrado datos.
- **Texto propuesto:** con filtro: «No hay mascotas adoptadas.» + «Ver todas». Sin filtro: «Aún no hay
  mascotas. Añade la primera para que aparezca en el catálogo.» + «Añadir mascota».
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-20 · Confirmación de borrado poco específica
- **Dónde:** `mascotas/admin/lista.html:162` (`data-confirmar`), mostrada con `window.confirm`
  (`app/static/js/app.js:6`).
- **Texto actual:** «¿Estás seguro de eliminar a Max?»
- **Problema:** no dice la consecuencia (se borra la foto de S3, irreversible); «seguro» en masculino.
- **Impacto:** borrados accidentales sin vuelta atrás.
- **Texto propuesto:** «¿Eliminar a Max? Se borrarán su ficha y su foto. Esta acción no se puede
  deshacer.»
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-21 · Errores de foto sin causa ni solución
- **Dónde:** `app/routes/mascotas.py:203,300`; `app/__init__.py:172`; campo en
  `mascotas/admin/form.html:106-107` (sin texto de ayuda; `accept="image/*"` admite más formatos de los
  permitidos).
- **Texto actual:** «Formato de imagen no permitido» (sin punto) · «El archivo es demasiado grande.
  Máximo 5MB.»
- **Problema:** no dice qué formatos valen; el mismo mensaje sale si el contenido no es una imagen
  válida; «5MB» sin espacio; ninguna ayuda previa en el campo.
- **Impacto:** prueba y error, y se pierden los datos del formulario en cada intento (redirección).
- **Texto propuesto:** ayuda bajo el campo: «JPG, PNG, GIF o WebP. Máximo 5 MB.» · Error de formato:
  «No hemos podido usar esa imagen. Sube un archivo JPG, PNG, GIF o WebP.» · 413: «La foto pesa más de
  5 MB. Elige una imagen más pequeña.»
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-22 · Asterisco de obligatorio sin leyenda y opcionales marcados dos veces
- **Dónde:** `auth/registro.html:16,24,53,60`; `mascotas/admin/form.html:27,34,97`;
  `solicitudes/nueva.html:32,42,51,63,86,92,102,112`; y a la vez `solicitudes/nueva.html:152`
  «Referencias (Opcional)» + `:157` «Opcional, pero…».
- **Problema:** nunca se explica qué significa «*»; en el cuestionario conviven dos convenciones.
- **Impacto:** dudas sobre qué hay que rellenar; ruido.
- **Texto propuesto:** como casi todo es obligatorio, marcar solo lo opcional: «Apellidos (opcional)»,
  «Teléfono (opcional)», «Referencias (opcional)»; o añadir al inicio de cada formulario «Los campos con
  * son obligatorios.». Ayuda de referencias: «Nos ayudan a revisar tu solicitud más rápido.»
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-23 · Registro: «Dirección — Necesaria para solicitudes de adopción» no es cierto
- **Dónde:** `auth/registro.html:48`.
- **Problema:** el campo es opcional y `solicitudes.nueva` no comprueba la dirección; quien se registra
  con Google ni siquiera la tiene y puede solicitar.
- **Impacto:** fricción innecesaria (el usuario cree que debe darla) o desconfianza al ver que no se pide.
- **Texto propuesto:** «Dirección (opcional)» + ayuda «Nos ayuda a valorar tu solicitud.»; o hacerla
  realmente obligatoria al solicitar y decirlo allí.
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-24 · Cuenta desactivada: «Contacta al administrador» sin forma de contacto
- **Dónde:** `app/routes/auth.py:150,220`.
- **Texto actual:** «Tu cuenta ha sido desactivada. Contacta al administrador.»
- **Problema:** no hay correo, teléfono ni página de contacto en el sitio; «contactar a» es americano
  (en el resto del sitio la variante es la de España).
- **Impacto:** el usuario no tiene salida.
- **Texto propuesto:** «Tu cuenta está desactivada. Si crees que es un error, escríbenos a
  {correo del refugio}.» (añadir el contacto también al pie).
- **Gravedad:** media · **Esfuerzo:** S

#### TXT-25 · Rechazo de solicitud: aviso sin contexto (y la mascota queda «en proceso»)
- **Dónde:** `app/routes/solicitudes.py:209`; modelo `Solicitud.rechazar` en `app/models.py:383-395` no
  devuelve la mascota a «disponible».
- **Texto actual:** «Solicitud rechazada.»
- **Problema:** con varias solicitudes en pantalla no dice cuál; tampoco informa del estado en que queda
  la mascota (sigue «En proceso» y fuera del catálogo; esto último es un hallazgo funcional que debe
  confirmar el agente de funcionalidad).
- **Impacto:** el administrador no sabe que debe cambiar el estado de la mascota a mano.
- **Texto propuesto:** «Has rechazado la solicitud de Juan para Luna.» (+ si se mantiene el
  comportamiento: «Luna sigue «En proceso»: cámbiala a «Disponible» si quieres que vuelva al
  catálogo.»).
- **Gravedad:** media · **Esfuerzo:** S

---

### Gravedad baja

#### TXT-26 · Tres textos para el mismo enlace a la ficha
- **Dónde:** `index.html:99` «Ver Perfil»; `mascotas/catalogo.html:92` «Ver Detalles»;
  `solicitudes/detalle.html:37` «Ver Perfil Completo». (`solicitudes/mis_solicitudes.html:64` «Ver
  Detalles» lleva a la solicitud, no a la mascota.)
- **Problema/impacto:** el mismo destino con nombres distintos y el mismo nombre con destinos distintos.
- **Propuesto:** a la ficha: «Conocer a {nombre}» o «Ver ficha»; a la solicitud: «Ver solicitud».
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-27 · Estado vacío de solicitudes (admin) con valor interno
- **Dónde:** `solicitudes/admin/lista.html:118-123`.
- **Texto actual:** «No se encontraron solicitudes con estado "pendiente".»
- **Propuesto:** «No hay solicitudes pendientes.» / «aprobadas» / «rechazadas»; sin filtro: «Todavía no
  ha llegado ninguna solicitud.»
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-28 · No se puede eliminar: sin alternativa y con comillas inglesas
- **Dónde:** `app/routes/mascotas.py:368` (también `:238,337,376`).
- **Texto actual:** «No se puede eliminar "Max" porque tiene solicitudes de adopción asociadas.»
- **Propuesto:** «No puedes eliminar a Max porque tiene solicitudes. Si ya no está en el refugio,
  cambia su estado a «Adoptada».» Usar comillas «» o ninguna con nombres propios.
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-29 · Foto por URL: prioridad no explicada
- **Dónde:** `mascotas/admin/form.html:110-114`; lógica «archivo > URL» en `app/routes/mascotas.py:198`.
- **Texto actual:** «O proporciona una URL externa:» (en edición, prerrellenado con la URL de S3).
- **Problema:** no dice que el archivo subido sustituye a la URL; dos puntos en una etiqueta.
- **Propuesto:** etiqueta «O pega el enlace de una imagen» + ayuda «Debe empezar por https://. Si subes
  un archivo, se usará el archivo.»
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-30 · «La especie es obligatoria.» no corresponde a la regla
- **Dónde:** `app/routes/mascotas.py:189-190,286-287` (exige ≥ 2 caracteres).
- **Propuesto:** «Indica la especie (al menos 2 letras), por ejemplo «Perro».»
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-31 · Placeholders usados como instrucciones
- **Dónde:** `auth/registro.html:55` «Mínimo 8 caracteres»; `auth/login.html:25` «Tu contraseña»;
  `auth/registro.html:62` «Repite tu contraseña».
- **Problema:** la regla desaparece al escribir; los otros repiten la etiqueta.
- **Propuesto:** ayuda visible bajo el campo: «Al menos 8 caracteres.»; quitar placeholders redundantes.
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-32 · Mensajes de inicio con Google poco útiles y con errores tipográficos
- **Dónde:** `app/routes/auth.py:197,203,209,241`.
- **Texto actual:** «Error al obtener información de Google» (sin punto); «Tu email de Google no está
  verificado.»; «Bienvenido, Ana!» (falta «¡»).
- **Propuesto:** «No hemos podido obtener tus datos de Google. Inténtalo de nuevo o inicia sesión con tu
  correo.» · «Tu cuenta de Google no tiene el correo verificado. Verifícalo en Google o regístrate con
  tu correo.» · «¡Hola, Ana!»
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-33 · Fórmulas con género masculino por defecto
- **Dónde:** `app/routes/auth.py:155,241` «¡Bienvenido, …!»; `index.html:139` «¿Listo para cambiar una
  vida?»; `mascotas/admin/lista.html:162` «¿Estás seguro…?».
- **Propuesto:** «¡Hola, Ana!» · «¿Quieres cambiar una vida?» · «¿Eliminar a Max?…» (ver TXT-20).
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-34 · Permiso denegado: dos versiones e informal
- **Dónde:** `app/decorators.py:15` «No tienes permisos para acceder a esta sección» (sin punto);
  `app/routes/solicitudes.py:128` «No tienes permiso para ver esta solicitud.»
- **Propuesto:** «Esta página es solo para el equipo del refugio.» · «Solo puedes ver tus propias
  solicitudes.»
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-35 · Aviso de inicio de sesión requerido genérico
- **Dónde:** `app/__init__.py:98`.
- **Texto actual:** «Por favor, inicia sesión para acceder a esta página.»
- **Propuesto:** «Inicia sesión para continuar. ¿No tienes cuenta? Regístrate en un minuto.» (el
  enlace en la página de login ya existe).
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-36 · Abreviatura «Ej:» sin punto
- **Dónde:** `mascotas/catalogo.html:50`; `mascotas/admin/form.html:29,36,43,50`;
  `solicitudes/nueva.html:77`.
- **Propuesto:** «Ej.: Max» o «Por ejemplo, Max».
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-37 · «Email» frente a «correo electrónico»
- **Dónde:** `auth/login.html:16`; `auth/registro.html:16,19`; `solicitudes/detalle.html:79`;
  `app/routes/auth.py:70,83,137,145,209`.
- **Problema:** anglicismo (la RAE recomienda «correo electrónico» o «correo»); conviene decidirlo y
  aplicarlo en todo el sitio.
- **Propuesto:** etiqueta «Correo electrónico»; mensajes con «correo» («Correo o contraseña
  incorrectos.»).
- **Gravedad:** baja · **Esfuerzo:** M

#### TXT-38 · Etiquetas telegráficas en el detalle de la solicitud
- **Dónde:** `solicitudes/detalle.html:98-152`; `solicitudes/admin/revisar.html:55-96`.
- **Texto actual:** «Compromiso gastos:», «Compromiso tiempo:», «Tiene jardín:», «Detalles de
  mascotas:», «Propiedad:»; en revisar «Jardín:», «Otras mascotas:», «Tipo:».
- **Problema:** abreviadas y distintas entre las dos vistas y respecto a las preguntas originales.
- **Propuesto:** reutilizar una etiqueta corta común: «Se compromete a cubrir los gastos», «Se
  compromete a dedicarle tiempo», «Jardín o patio», «Otras mascotas en casa», «Vivienda propia o de
  alquiler».
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-39 · Página de inicio: textos imprecisos
- **Dónde:** `index.html:61` «Familias registradas» (cuenta personas adoptantes); `:128-131` paso 4
  «Adopta / Espera la aprobación»; `:142` «Comenzar Ahora»; `:16` y `base.html:81` «Registrarse» frente a
  `:115` «Regístrate».
- **Propuesto:** «Personas registradas»; ver TXT-11 para los pasos; CTA «Crear mi cuenta».
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-40 · Títulos de pestaña incoherentes
- **Dónde:** `solicitudes/nueva.html:3` «Solicitar Adopción - Luna»; `solicitudes/detalle.html:3`
  «Solicitud #3 - Luna»; `solicitudes/admin/revisar.html:3` «Revisar Solicitud #3»;
  `mascotas/admin/form.html:3` «Editar Mascota - Panel Admin»; el resto acaba en «- Portal de Adopción».
- **Propuesto:** patrón «{Página} · Portal de Adopción»: «Solicitar la adopción de Luna · Portal de
  Adopción», «Editar a Luna · Gestión de mascotas», etc.
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-41 · Tabla de gestión: edad sin unidad y guiones para vacíos
- **Dónde:** `mascotas/admin/lista.html:123-125`.
- **Texto actual:** «3», «-».
- **Propuesto:** «3 años» y «—» o «Sin dato».
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-42 · Login/registro: textos redundantes y enlaces «aquí»
- **Dónde:** `auth/login.html:46,50` «O continúa con:» + «Continuar con Google»; `:58` «Regístrate
  aquí»; `auth/registro.html:77` «Inicia sesión aquí».
- **Propuesto:** separador «o» + «Continuar con Google»; «¿No tienes cuenta? Regístrate»; «¿Ya tienes
  cuenta? Inicia sesión».
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-43 · Opciones de «emergencia veterinaria» mal redactadas
- **Dónde:** `solicitudes/nueva.html:105-107`.
- **Texto actual:** «Llevaría inmediatamente al veterinario» (falta el objeto), «Consultaría online
  primero», «Esperaría a ver evolución».
- **Propuesto:** «Lo llevaría al veterinario de inmediato», «Consultaría primero en internet»,
  «Esperaría a ver cómo evoluciona».
- **Gravedad:** baja · **Esfuerzo:** S

#### TXT-44 · Especie en texto libre genera variantes en el filtro del catálogo
- **Dónde:** `mascotas/admin/form.html:34-36` (input libre, «Ej: Perro, Gato»); filtro en
  `mascotas/catalogo.html:25-27`.
- **Problema:** «perro», «Perro» y «Perros» aparecerían como opciones distintas.
- **Propuesto:** desplegable con lista cerrada («Perro», «Gato», «Conejo», «Otra») o normalizar la
  mayúscula al guardar.
- **Gravedad:** baja · **Esfuerzo:** M

#### TXT-45 · Mensajes de éxito con calcos («exitosamente», «exitoso»)
- **Dónde:** `app/routes/mascotas.py:238,337,376`; `app/routes/auth.py:101,107`.
- **Texto actual:** «Mascota "Max" creada exitosamente.», «¡Registro exitoso! Ya puedes iniciar
  sesión.», «No se pudo crear el usuario. Inténtalo de nuevo.»
- **Propuesto:** «Max se ha añadido al catálogo.», «Cambios de Max guardados.», «Max se ha eliminado.»,
  «Cuenta creada. Ya puedes iniciar sesión.», «No hemos podido crear tu cuenta. Inténtalo de nuevo.»
- **Gravedad:** baja · **Esfuerzo:** S

---

### Mini guía de estilo propuesta

**Voz:** cercana, cálida y clara, como una persona voluntaria del refugio. Alegre en los éxitos sin
exagerar; empática y concreta en los errores y rechazos; directa en el panel de gestión.

**Tratamiento:** tú en todo el sitio público y en los mensajes al adoptante (nunca usted). En el panel de
gestión también tú, dirigido al personal. Variante: español de España («contactar con», «móvil»,
«alquiler»).

**Mayúsculas:** solo la primera palabra y los nombres propios («Mis solicitudes», «Cerrar sesión»).
Estados en minúscula salvo al inicio de la insignia («En proceso»).

**Botones y enlaces:** infinitivo y objeto concreto («Enviar solicitud», «Guardar cambios», «Añadir
mascota»); nada de «Enviar»/«Aceptar» genéricos. El texto en imperativo se reserva para instrucciones
(«Revisa tus respuestas…»). Evitar «aquí» como texto de enlace.

**Errores:** qué ha pasado + cómo arreglarlo, sin culpar («No hemos podido…», «Elige…»). Nunca códigos,
inglés ni nombres de campo internos. Punto final siempre.

**Confirmaciones:** pregunta con la acción y el objeto («¿Eliminar a Max?») + consecuencia («No se puede
deshacer.»). Nada de «¿Estás seguro?».

**Estados vacíos:** qué es + por qué está vacío + acción siguiente con botón.

**Género:** evitar el masculino genérico cuando haya alternativa («¡Hola, Ana!», «¿Quieres…?»); para
mascotas, concordar con «mascota» (femenino) en estados y filtros o con su sexo si se conoce; preferir
sustantivos neutros en etiquetas («Vacunas», «Esterilización»). Evitar «/a».

**Formatos:** fechas `dd/mm/aaaa`, hora local de España `HH:MM`; unidades con espacio («5 MB», «3 años»);
rangos con «entre X e Y»; comillas latinas «»; abreviatura «Ej.:».

**Vocabulario fijo**

| Usar | Evitar |
|---|---|
| solicitud de adopción · Solicitar adopción | solicitud/adopción alternados, «adoptar» como botón |
| mascota (femenino en estados: «Adoptada», «Disponible», «En proceso») | «Adoptado» para todas |
| refugio · equipo del refugio · Mensaje del refugio | admin, administrador, Panel Admin |
| Gestión de mascotas / Gestión de solicitudes | Panel de Administración - … |
| correo electrónico · correo | email, e-mail |
| Iniciar sesión · Cerrar sesión · Crear cuenta | Login, Registrarse/Regístrate mezclados |
| Ver ficha (mascota) · Ver solicitud | Ver Perfil, Ver Detalles, Ver Perfil Completo |
| Pendiente · Aprobada · Rechazada | valores internos (`pendiente`, `en_proceso`) |
| se ha guardado, se ha añadido | exitosamente, exitoso, con éxito |
| (opcional) junto a la etiqueta | asterisco sin leyenda |
| en internet | online |
