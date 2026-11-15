# Plan de mejora del frontend

**Estado:** aprobado · **Fecha:** 2026-11-15

Aplica ADR-0001 a ADR-0005 (`docs/adr/`) sobre los problemas de
`docs/auditoria-frontend.md`. El orden y el alcance de ADR-0005 son
vinculantes: lo que surja fuera de los criterios de aceptación se apunta para
otra iteración.

## 1. Resumen

| Fase (ADR-0005) | Bloques | PRs | Esfuerzo orientativo |
|---|---|---|---|
| 0 · Entorno y documentación | B0.1, B0.2 | 1 | 0,5 días |
| 1 · Dominio | B1.1–B1.5 | 5 | 3 días |
| 2 · Que el usuario no pierda datos | B2.1–B2.7 | 7 | 3,5 días |
| 3 · Base del sistema de diseño | B3.1–B3.6 | 6 | 4 días |
| 4 · Parte pública sin Bootstrap | B4.1–B4.5 | 5 | 4 días |
| 5 · Panel sin Bootstrap | B5.1–B5.4 | 4 | 3 días |
| **Total** | **28 bloques** | **28 PRs** | **~18 días** |

La migración visual (fases 3 a 5) ocupa 15 PRs, más que los 10-12 que se
estimaron. Hay dos motivos: cada página arrastra su accesibilidad, sus textos y
sus e2e, y el límite de ~400 líneas por PR obliga a separar las macros en dos
bloques. `styles.css` se queda solo para el panel durante la fase intermedia.
El CSS nuevo, de unas 900 líneas, se reparte en `app/static/css/sistema.css`,
`marca.css` y `paginas/*.css`.

Los bloques de las fases 1 y 2 se solapan cuando no comparten archivos
(ADR-0005). Cada fase de la 3 en adelante empieza cuando la anterior está
fusionada.

### Ejecución

- **Desarrollo:** un agente por bloque, en su propia rama y worktree aislado,
  con el pipeline indicado (`ecc:orch-*`) y TDD (`ecc:tdd-guide`). Como máximo
  3 bloques en paralelo, siguiendo el grafo de la sección 9.
- **Diseño visual:** los bloques B3.2 y de las fases 4 y 5 iteran con
  `ecc:gan-design`, con un número de iteraciones acotado y `frontend-design`
  como dirección.
- **Revisión** de cada bloque:
  - `ecc:code-reviewer` siempre;
  - `ecc:python-reviewer` si toca Python;
  - `ecc:security-reviewer` si toca formularios, autenticación, CSP o JS;
  - `ecc:a11y-architect` si cambia la interfaz.
- **Doble revisión** (`ecc:santa-method`) en los bloques marcados como de alto
  riesgo.
- **Verificación final:** `ecc:verification-loop`, e2e, y capturas antes y
  después con `ecc:browser-qa` en los bloques que cambian la interfaz.
- **Commits:** revisados con `ecc:commit-reviewer`, en Conventional Commits en
  español y sin atribución a IA.
- **Push, PR y merge:** los haces tú. Al cerrar cada bloque te doy el comando
  de push y el `gh pr create` con su título y su cuerpo.
- **ADR en los worktrees:** las ADR 0001 a 0004 ya están redactadas en el
  checkout principal. Cada bloque las copia en su rama y las incluye en su PR
  (sección 10).

**Comprobaciones en todos los PRs:**
- `ruff check .` limpio.
- `python -m pytest --cov=app --cov-branch` ≥ 95 %.
- `tests/test_accesibilidad.py` y `python -m pytest -m e2e` en verde.
- Sin JavaScript inline ni `onclick`, y con `csrf_token` en cada POST.
- Menos de ~400 líneas cambiadas en `app/`, sin contar los tests ni los
  archivos vendorizados.
- La rama al día con `main` y sin conflictos.

## 2. Tabla de bloques

| Bloque | Problemas | Tamaño | Pipeline | Alto riesgo | Rama | Depende de |
|---|---|---|---|---|---|---|
| B0.1 Entorno local | entorno | S | — (sin PR) | No | — | — |
| B0.2 Auditoría, plan y ADR-0005 | — | S | — | No | `docs/auditoria-frontend` | — |
| B1.1 Solicitudes en paralelo (ADR-0004) | P-01, P-05 | M | orch-change-feature | **Sí** | `feat/solicitudes-en-paralelo` | B0.2 |
| B1.2 Estado de la mascota derivado | P-29 | M | orch-change-feature | **Sí** | `feat/estado-mascota-derivado` | B1.1, B1.5 |
| B1.3 Validar el cuestionario | P-04 | M | orch-fix-defect | **Sí** | `fix/validar-cuestionario` | B1.1 |
| B1.4 Revisión con confirmación | P-06, P-10 | M | orch-change-feature | **Sí** | `feat/revision-con-confirmacion` | B1.3 |
| B1.5 Editar mascota sin «None» | P-08 | S | orch-fix-defect | **Sí** | `fix/editar-mascota-sin-none` | B0.2 |
| B2.1 Formularios de auth y `next` | P-02 (auth), P-07 | M | orch-fix-defect | No (revisión de seguridad de `next`) | `fix/formularios-auth` | B0.2 |
| B2.2 Formulario de mascota que conserva los datos | P-02 (admin) | M | orch-fix-defect | **Sí** | `fix/formulario-mascota-conserva-datos` | B1.2 |
| B2.3 Páginas de error y CSRF | P-03 | M | orch-add-feature | No | `feat/paginas-de-error` | B0.2 |
| B2.4 Almacenamiento de fotos (ADR-0003) | P-09, P-32 | M | orch-change-feature | **Sí** | `feat/almacenamiento-fotos` | B2.2 |
| B2.5 Procesado de fotos | ADR-0003 (EXIF, variantes) | M | orch-add-feature | **Sí** | `feat/procesado-fotos` | B2.4 |
| B2.6 Seed coherente | P-18 | S | orch-fix-defect | No | `chore/seed-coherente` | B1.3 |
| B2.7 Especies normalizadas | P-31 | S | orch-fix-defect | No | `fix/especies-normalizadas` | B1.1 |
| B3.1 Bootstrap vendorizado y CSP (ADR-0001) | P-21, P-47 (parcial) | S | orch-refine-code | **Sí** | `chore/bootstrap-vendorizado-csp` | fase 2 |
| B3.2 Tokens y marca (ADR-0002) | P-13, P-14, P-22 (parcial) | M | orch-add-feature | No | `feat/tokens-diseno` | fase 2 |
| B3.3 Macros de formulario | P-16, P-17, P-20, P-36 (base) | M | orch-add-feature | No | `feat/macros-formulario` | B3.2 |
| B3.4 Macros de componentes | P-15, P-19 (base) | M | orch-add-feature | No | `feat/macros-componentes` | B3.3 |
| B3.5 e2e por áreas | P-40 (preparación) | S | orch-refine-code | No | `test/e2e-por-areas` | fase 2 |
| B3.6 Base nueva y navegación | P-22, P-48 (marca) | M | orch-add-feature | **Sí** | `feat/base-sin-bootstrap` | B3.1, B3.4, B3.5 |
| B4.1 Portada | P-34, P-38, P-42, P-43, P-48 | M | orch-change-feature | No | `feat/rediseno-portada` | B3.6 |
| B4.2 Catálogo y detalle | P-19, P-24, P-35, P-37, P-39, P-41, (P-30) | M | orch-change-feature | No | `feat/rediseno-catalogo` | B3.6 |
| B4.3 Login y registro | P-13, P-16, P-36, P-40, P-42, P-43 | M | orch-change-feature | No | `feat/rediseno-auth` | B3.6 |
| B4.4 Cuestionario | P-12, P-16, P-24, P-27, P-44 | M | orch-change-feature | **Sí** | `feat/rediseno-cuestionario` | B4.2 |
| B4.5 Solicitudes del adoptante | P-24, P-26, P-35, P-41, P-42 | M | orch-change-feature | No | `feat/rediseno-solicitudes-adoptante` | B4.2 |
| B5.1 Lista de mascotas del admin | P-23, P-46, P-43 | M | orch-change-feature | **Sí** | `feat/rediseno-admin-mascotas` | fase 4 |
| B5.2 Formulario de mascota del admin | P-16, P-32, P-40 | M | orch-change-feature | **Sí** | `feat/rediseno-admin-form` | B5.1 |
| B5.3 Solicitudes del admin | P-23, P-28, P-45, P-40 | M | orch-change-feature | **Sí** | `feat/rediseno-admin-solicitudes` | fase 4 |
| B5.4 Retirar Bootstrap | ADR-0001 (cierre) | S | orch-refine-code | **Sí** | `chore/retirar-bootstrap` | B5.2, B5.3 |

**Fuera de alcance (ADR-0005):**
- P-11, P-25, P-47, P-49 y P-50.
- P-30, salvo que salga gratis en B4.2.
- P-33: solo se cambia el texto de ayuda del registro a «Opcional», en B4.3.
- El modo oscuro y la adecuación al RGPD.

## 3. Fase 0 · Entorno y documentación

### B0.1 · Entorno local (sin PR)

**Objetivo:** volver al seed limpio, sin los datos que dejó la auditoría
(mascotas 9-12, usuarios `usabilidad-*`, `qa-*` y `func-*`, y la solicitud
sobre Lys).

```bash
docker compose down -v
docker compose up -d
flask --app run db upgrade
docker compose exec -T postgres psql -U admin -d adopciones_db < scripts_bd/02_seed.sql
python -m pytest && python -m pytest -m e2e && ruff check .
```

- **Cuándo repetirlo:** tras fusionar B1.1 (migración 0002), B2.6 (seed) y
  B2.7 (migración 0003).
- **Aceptación:** `/mascotas/catalogo` muestra solo las mascotas del seed y la
  suite completa está en verde sobre `main`.

### B0.2 · `docs/auditoria-frontend`

**Archivos:**
- `docs/auditoria-frontend.md`;
- `docs/plan-frontend.md` (este documento);
- `docs/adr/0005-priorizacion-iteracion-frontend.md`;
- `docs/adr/README.md`, solo con la fila 0005 (cada PR de ADR añade la suya);
- `docs/adr/template.md`.

Las capturas de la auditoría **no** se commitean: son pruebas temporales, y el
documento ya lo indica.

**Aceptación:** todos los enlaces del índice de ADR resuelven.

## 4. Fase 1 · Dominio

### B1.1 · Solicitudes en paralelo (ADR-0004 entra aquí)

**Archivos:**
- Nuevo `app/adopciones.py`, la única función de dominio, con `crear_solicitud`,
  `aprobar`, `rechazar`, `adoptar_fuera_del_portal` y `volver_a_disponible`.
- `app/models.py`:
  - `:260-268`: se eliminan `marcar_en_proceso` y el `commit` interno de
    `marcar_adoptado`.
  - `:365-395`: `aprobar` y `rechazar`.
- `app/routes/solicitudes.py:71-90` y `:199-209`.
- `app/routes/api/solicitudes.py:80-95`, que deja de duplicar la lógica.
- `app/routes/api/mascotas.py:24` (descripción).
- La migración `migrations/versions/0002_estados_derivados.py`, generada contra
  PostgreSQL.
- `scripts_bd/02_seed.sql:25`: Toby pasa de `en_proceso` a `adoptado`. El CI
  carga el seed después de migrar, así que la migración de datos no lo
  corrige.
- `docs/ARQUITECTURA.md`: la regla nueva y el cambio en la API.
- `docs/adr/0004-*.md` y su fila en el índice.

**Criterios de aceptación:**
- Crear una solicitud deja la mascota en `disponible`. Un segundo usuario puede
  solicitarla, por la web y por la API (201).
- Rechazar solo cambia esa solicitud; la mascota sigue en el catálogo.
- Aprobar hace tres cosas en un solo commit: la mascota pasa a `adoptado`, el
  resto de pendientes pasa a `rechazada` con `COMENTARIO_RECHAZO_AUTOMATICO`, y
  se rellenan `revisado_por` y `fecha_revision`.
- La aprobación bloquea la mascota con `select(Mascota).with_for_update()` y
  vuelve a comprobar el estado tras el bloqueo. Aprobar sobre una mascota ya
  adoptada no cambia nada y muestra un aviso.
- **Migración 0002, upgrade:** las mascotas `en_proceso` con una solicitud
  aprobada pasan a `adoptado`, y el resto a `disponible`.
- **Migración 0002, downgrade:** las mascotas `disponible` con solicitudes
  pendientes vuelven a `en_proceso`. Las adopciones no se revierten; queda
  documentado.
- `flask db check` sigue limpio.

**Tests:**
- `test_solicitudes_logica.py`: rechazo, aprobación con varias pendientes y
  doble aprobación seguida.
- Un test que compila la consulta con el dialecto `postgresql` y comprueba
  `FOR UPDATE`.
- `test_api.py`: segunda solicitud en paralelo.
- `test_migraciones.py`: upgrade y downgrade de 0002 con datos.
- Se adapta el fixture `mascota_en_proceso` de `conftest.py`.

### B1.2 · Estado de la mascota derivado (P-29)

**Archivos:**
- `app/routes/mascotas.py:277` y `:331`.
- `mascotas/admin/form.html`: el selector de estado se sustituye por las
  acciones «Marcar como adoptada fuera del portal» y «Volver a disponible».
- `mascotas/admin/lista.html`: sin el filtro `en_proceso`.
- `catalogo.html` y `mascotas/detalle.html`: aviso «Tiene solicitudes en
  curso».
- `mascotas.py:39-71`: recuento agregado.

**Criterios de aceptación:**
- Un POST con `estado=en_proceso` no lo guarda.
- «Adoptada fuera del portal» rechaza las pendientes igual que una aprobación.
- El catálogo cuenta las pendientes de toda la página con **una** sola consulta
  agregada.

**Tests:**
- `test_mascotas_admin.py`.
- `test_rendimiento.py`: el número de consultas no crece con 12 mascotas.
- `test_mascotas.py`: aparece el aviso.

### B1.3 · Validar el cuestionario (P-04)

**Archivos:**
- Nuevo `app/cuestionario.py`: las preguntas, las opciones con su etiqueta, los
  campos obligatorios y `validar(datos) -> (limpio, errores)`.
- `solicitudes.py:54-69`.
- `api/solicitudes.py:20-31` y `:72-74`.
- `solicitudes/nueva.html`: cambio mínimo, con un resumen de errores y los
  valores repuestos.

**Criterios de aceptación:**
- Un envío vacío o con opciones fuera de la lista devuelve 400, vuelve a
  mostrar el formulario con lo escrito y no crea la solicitud.
- `tiene_mascotas=si` exige `mascotas_detalles`.
- Lo que no se contesta se guarda como `null`, nunca como `False`.
- La API aplica la misma regla, responde 400 con `{"error": "..."}` y rechaza
  las claves desconocidas.
- El cambio de contrato queda en `docs/ARQUITECTURA.md`.

**Tests:**
- Nuevo `tests/test_cuestionario.py`.
- `test_solicitudes.py`.
- `test_api.py` y `test_api_ramas.py`: un cuestionario arbitrario deja de ser
  válido.
- El e2e de envío sigue en verde.

### B1.4 · Revisión con confirmación y respuestas legibles (P-06, P-10)

**Archivos:**
- `solicitudes.py:176-213`.
- `solicitudes/admin/revisar.html`.
- `solicitudes/detalle.html`.
- El filtro `respuesta_legible` en `app/cuestionario.py`.

**Criterios de aceptación:**
- «Aprobar» lleva `data-confirmar`, con el texto «Se rechazarán
  automáticamente N solicitudes pendientes».
- «Rechazar» exige un motivo. Si falta, el error sale asociado al campo, la
  respuesta es 400 y el texto escrito se conserva.
- Una solicitud ya resuelta se muestra sin formulario.
- Una acción desconocida devuelve 400 con «Acción no válida».
- Las respuestas muestran su etiqueta («Más de 8 horas», no `8+`), y la que
  falta aparece como «Sin respuesta».

**Tests:**
- `test_solicitudes.py`: ningún `<form>` en una solicitud resuelta, motivo
  vacío y acción inválida.
- `test_cuestionario.py`: las etiquetas.

### B1.5 · Editar mascota sin «None» (P-08)

**Archivos:**
- `mascotas/admin/form.html`: `{{ mascota.raza or '' }}`, y lo mismo con
  `foto_url`.
- `mascotas.py:325` y `:330`.

**Criterios de aceptación:** con raza y foto a `NULL`, el GET muestra los
campos vacíos. Guardar sin cambios devuelve 302 y deja `raza IS NULL`.

**Tests:** `test_mascotas_admin.py`.

## 5. Fase 2 · Que el usuario no pierda datos

**Contrato común (B2.1, B2.2, B2.4 y B1.3).** Ante un error de validación, la
vista pasa a la plantilla `valores` y `errores` (un `dict` campo → mensaje) y
responde 400. La macro `campo` de la fase 3 consume exactamente este contrato.

### B2.1 · Formularios de auth y `next` (P-02, P-07)

**Archivos:**
- `auth.py:58-165`.
- `auth/login.html` y `auth/registro.html`.
- `mascotas/detalle.html`: «Inicia sesión para adoptar» pasa `next`.

**Criterios de aceptación:**
- Un error en el registro conserva el correo, el nombre, los apellidos, el
  teléfono y la dirección, nunca la contraseña.
- Un login fallido conserva el correo.
- El login mantiene `next`.
- El registro inicia sesión y redirige a un `next` seguro. Un `next` externo se
  ignora (`es_redireccion_segura`).
- El login con Google guarda `next` en la sesión.

**Tests:** `test_auth.py` y `test_auth_ramas.py`.

### B2.2 · Formulario de mascota que conserva los datos (P-02, admin)

**Archivos:**
- `mascotas.py:161-340`: se extraen `_leer_formulario_mascota()` y
  `_validar_mascota()`, y desaparece el código duplicado entre `nueva` y
  `editar`.
- `mascotas/admin/form.html`.

**Criterios de aceptación:**
- Un error de imagen deja de hacer `redirect(request.url)` (`:204`, `:301`). En
  su lugar vuelve a mostrar el formulario con los valores, con 400.
- Al editar, los valores enviados tienen prioridad sobre los guardados.

**Tests:** `test_mascotas_admin.py`, un caso por cada validación.

### B2.3 · Páginas de error y CSRF (P-03)

**Archivos:**
- `app/__init__.py`: manejadores de 400, `CSRFError`, 403, 404, 405, 429 y 500.
- Nueva `templates/errores/error.html`.
- `config.py`: `WTF_CSRF_TIME_LIMIT = None`, así que el token dura lo que dura
  la sesión.
- `tests/e2e/test_flujos.py:104`.
- `.claude/CLAUDE.md` y `docs/ARQUITECTURA.md`.

**Criterios de aceptación:**
- Cada código responde con su estado, `lang="es"`, un `h1` en español, la
  navegación y una salida.
- El error de CSRF explica que la sesión caducó y ofrece «Volver al
  formulario», con un `referrer` del mismo host.
- El 429 lleva `Retry-After`.
- El 500 registra la excepción con `current_app.logger.exception` y muestra un
  mensaje genérico.
- Las respuestas de `/api/` no cambian.

**Tests:**
- `test_errores.py`, con CSRF activado de forma explícita.
- `test_config.py`.
- `test_accesibilidad.py`: añadir las páginas de error.
- e2e: el texto en español.

### B2.4 · Almacenamiento de fotos (ADR-0003 entra aquí; P-09, P-32)

**Archivos:**
- Se elimina `app/s3.py` y se crea el paquete `app/fotos/`:
  - `__init__.py`: `guardar_foto`, `borrar_foto`, `subida_disponible` y
    `ErrorAlmacenamiento`;
  - `local.py`;
  - `s3.py`, con `endpoint_url` opcional.
- La ruta `GET /fotos/<clave>`.
- `config.py`: `FOTOS_BACKEND`, `FOTOS_DIR` y `AWS_S3_ENDPOINT_URL`.
  `ProductionConfig` solo acepta `local` si `FOTOS_DIR` está definido.
- `mascotas.py:197-210` y `:294-310`.
- `form.html`.
- `README.md`, `docs/ARQUITECTURA.md`, `docs/DESPLIEGUE.md` y
  `.claude/CLAUDE.md`.

La columna `foto_url` no cambia. El backend local guarda `/fotos/<uuid>.<ext>`
y S3 la URL completa. Las URLs externas `https://` se siguen distinguiendo.

**Criterios de aceptación:**
- Sin backend configurado, el formulario no muestra la subida.
- Un POST con archivo y sin backend da un error en el campo, con 400, y
  conserva los datos. Nunca un 500.
- Un `ClientError` simulado da un error en el campo y se registra en el log.
- El formulario explica la regla entre archivo y URL, y cada error de foto dice
  la causa y la solución (P-32).

**Tests:** `tests/test_fotos.py` (los dos backends, con `tmp_path`) sustituye a
`test_s3.py`, más `test_config.py` y `test_mascotas_admin.py`.

### B2.5 · Procesado de fotos

**Archivos:**
- `app/fotos/procesado.py`, con Pillow.
- El filtro `srcset_foto`.
- `app/cli.py`: `flask exportar-fotos`.
- `docs/DESPLIEGUE.md` y `.claude/CLAUDE.md`.

**Criterios de aceptación:**
- Un JPEG con EXIF y GPS se guarda sin EXIF.
- Una imagen por encima de `MAX_IMAGE_PIXELS` da un error en el campo.
- Se comprueba el tipo real del archivo.
- Se generan las variantes WebP de 400, 800 y 1200 px con nombre aleatorio, y
  borrar la foto elimina todas.
- `srcset_foto` devuelve `''` para las URLs externas.

**Tests:** `test_fotos.py` y `test_cli.py`.

### B2.6 · Seed coherente (P-18)

**Archivos:** `scripts_bd/02_seed.sql:33-36`, con las claves de
`app/cuestionario.py`.

**Criterios de aceptación:** los cuestionarios del seed pasan `validar()`, y
toda mascota con una solicitud aprobada está `adoptado`.

**Tests:** nuevo `tests/test_seed.py`, que extrae los JSON del SQL. El job
`migraciones` sigue en verde.

### B2.7 · Especies normalizadas (P-31)

**Archivos:**
- `app/models.py`: `@validates('especie')`, que quita espacios y pone la
  mayúscula inicial.
- La migración de datos `0003_normalizar_especies.py`. Su downgrade no hace
  nada (irreversible pero inocuo, y documentado).

**Criterios de aceptación:** el filtro muestra una sola opción para «perro» y
«Perro», y la API guarda «Perro».

**Tests:** `test_mascotas.py`, `test_api.py` y `test_migraciones.py`.

## 6. Fase 3 · Base del sistema de diseño

### B3.1 · Bootstrap vendorizado y CSP (ADR-0001 entra aquí; P-21)

**Archivos:**
- `app/static/vendor/bootstrap/5.3.0/` con su LICENSE y marcado como
  `linguist-vendored`.
- `base.html:10` y `:116`.
- La CSP de `app/__init__.py:43-55`: sin la CDN y sin `'unsafe-inline'`.
- Los 10 `style=` y el `<style>` de `index.html:149`, que pasan a clases.
- `.claude/CLAUDE.md` y `docs/ARQUITECTURA.md`.

**Criterios de aceptación:**
- No sale ninguna petición de CSS o JS a terceros.
- La CSP no contiene `unsafe-inline`.
- Los e2e no registran errores de CSP.

**Tests:**
- `test_seguridad.py`: la CSP.
- Un test nuevo que recorre `app/templates/**/*.html` y no encuentra ni
  `style=` ni `<style`.

### B3.2 · Tokens y marca (ADR-0002 entra aquí)

**Archivos:**
- `app/static/css/sistema.css`, con
  `@layer reset, tokens, base, componentes, utilidades`.
- `app/static/css/marca.css`: el único archivo que cambia cada protectora.
- `app/static/fonts/`: dos familias en WOFF2 con subconjunto latino,
  `font-display: swap` y licencia OFL.
- `config.py`: `MARCA_NOMBRE`, `MARCA_LOGO` y `MARCA_CONTACTO`.

**Criterios de aceptación:** el texto tiene un contraste ≥ 4,5:1 sobre sus
fondos y los bordes de los controles ≥ 3:1 (P-13).

**Tests:** `tests/test_tokens.py`, que lee las custom properties y calcula el
contraste.

### B3.3 · Macros de formulario

**Archivos:**
- `templates/macros/formulario.html`:
  - `campo`: consume `valores` y `errores` y genera `label for`, `aria-invalid`,
    `aria-describedby`, `autocomplete` y la leyenda del asterisco;
  - `grupo_opciones`: `fieldset` y `legend`;
  - `boton`;
  - `avisos`: dentro de `<main>`, con `role="status"` para éxito e información y
    `role="alert"` para los errores.
- `app.js`:
  - foco en el resumen de errores;
  - protección contra el doble envío con `aria-busy`;
  - reactivación en `pageshow`.
- `sistema.css`: `:focus-visible` (P-17).
- `.claude/CLAUDE.md`: estructura de las macros.

**Tests:** `test_accesibilidad.py` renderiza cada macro y comprueba sus
atributos.

### B3.4 · Macros de componentes

**Archivos:** `templates/macros/componentes.html` y su CSS:
- `tarjeta_mascota`: `article`, `width`/`height`, `loading="lazy"`,
  `srcset_foto` y el enlace «Ver a {nombre}».
- `badge_estado`: con texto, no solo color.
- `cabecera_pagina`: con `h1`.
- `tabla`: `caption`, `scope`, `aria-sort` y una región desplazable con nombre
  y `tabindex="0"`.
- `estado_vacio`.

**Tests:** `test_accesibilidad.py`, macro a macro.

### B3.5 · e2e por áreas

**Archivos:** `tests/e2e/test_flujos.py` se reparte en `test_navegacion.py`,
`test_catalogo.py`, `test_solicitud.py` y `test_admin.py`.

**Criterios de aceptación:**
- La solicitud entra por `/mascotas/<id>` y deja de depender de `.card`.
- Se mantienen `#jardin_si` y `data-confirmar`.
- El número de tests es el mismo y están en verde.

### B3.6 · Base nueva y navegación

**Archivos:**
- `base.html` pasa a llamarse `base_bootstrap.html`, y todas las plantillas
  actuales la extienden.
- Nuevo `base.html` sin Bootstrap:
  - enlace para saltar al contenido;
  - logo SVG, sin emoji;
  - menú móvil y desplegable de usuario como *disclosure*, con
    `aria-expanded`, `Escape` y devolución del foco (~60 líneas en `app.js`);
  - pie de página que baja al fondo.
- El context processor de la marca.
- Las páginas de error se migran a la base nueva como piloto.
- `.claude/CLAUDE.md` y `docs/ARQUITECTURA.md`: las dos bases.

**Criterios de aceptación:** sin JS, la navegación se ve y se puede usar. Con
JS, a 375 px el menú se abre y se cierra con el teclado.

**Tests:**
- `test_navegacion.py`: teclado en la 404 a 375 px.
- `test_accesibilidad.py`.

## 7. Fase 4 · Parte pública sin Bootstrap

**Común a todos los bloques:**
- Cada página extiende el `base.html` nuevo y usa las macros.
- Su CSS va en `app/static/css/paginas/<pagina>.css`, así que dos bloques no
  tocan el mismo archivo.
- Cada página tiene un solo `h1` y un título de pestaña coherente (P-34).
- Se aplica el vocabulario de P-42.
- Las comprobaciones de accesibilidad de cada página van en los tests de su
  área.

### B4.1 · Portada

**Archivos:** `index.html`, `paginas/inicio.css` y `app/static/img/hero-*.webp`.

**Criterios de aceptación:**
- El hero es un `<img>` local con variantes de 640 y 1280 px,
  `fetchpriority="high"` y `width`/`height`.
- El texto va sobre un panel con un contraste ≥ 4,5:1, sin pedir nada a
  Unsplash (P-38).
- Los contadores a 0 se ocultan.
- `.step-number` cumple el contraste (P-48).

**e2e:** `test_navegacion.py` cubre el menú y el cierre de sesión.

### B4.2 · Catálogo y detalle

**Archivos:** `catalogo.html`, `mascotas/detalle.html`,
`macros/paginacion.html` y `mascotas.py:51-56`.

**Criterios de aceptación:**
- Los filtros van en un `fieldset` con nombre, y la paginación marca
  `aria-current="page"` (P-37).
- Los enlaces dicen «Ver a Toby» (P-35).
- El estado vacío nombra el filtro activo y ofrece «Quitar filtros»; un valor
  de `edad` inválido muestra un aviso (P-41).
- Una mascota adoptada dice «Ya tiene hogar», y una con solicitudes
  pendientes, «Aún puedes solicitarla» (P-24).
- P-30 entra solo si se resuelve con un `<details>` sin coste extra.

**e2e:** `test_catalogo.py` usa `get_by_role('article')`.

### B4.3 · Login y registro

**Archivos:** las plantillas de `auth/` y los mensajes de `auth.py`.

**Criterios de aceptación:**
- `autocomplete` con `email`, `current-password`, `new-password`,
  `given-name`, `family-name` y `tel` (P-36).
- Errores en el propio campo y foco en el resumen (P-16).
- Los mensajes que remiten al refugio usan `MARCA_CONTACTO` (P-43).
- La dirección pasa a «Opcional» (P-33).

**e2e:** nuevo `test_auth.py`, con registro con `next`, login fallido y la 429
en español (P-40).

### B4.4 · Cuestionario

**Archivos:** `solicitudes/nueva.html`, `solicitudes.py:39-52` y las etiquetas
de `cuestionario.py`.

**Criterios de aceptación:**
- Un `fieldset` por cada grupo de radios, sin el `label` huérfano (P-12).
- Tuteo en todo el cuestionario.
- Rangos de horas sin solapes: «Menos de 4 horas», «De 4 a 8 horas» y «Más de
  8 horas». **Los `value` no cambian**, así que no hace falta migrar datos
  (P-27).
- Si el usuario ya tiene una solicitud para esa mascota, el aviso es «Ya
  tienes una solicitud para Toby» (P-44).
- La confirmación explica qué pasa ahora (P-24).

**e2e:** `test_solicitud.py`, con recorrido por teclado.

### B4.5 · Solicitudes del adoptante

**Archivos:** `mis_solicitudes.html`, `solicitudes/detalle.html`, el filtro
`fecha_local` y `ZONA_HORARIA` en `config.py`.

**Criterios de aceptación:**
- Cada estado tiene su apartado «Qué pasa ahora» (P-24).
- Las fechas se muestran en `Europe/Madrid` con `zoneinfo`; se añade `tzdata`
  a `requirements.txt` (P-26).
- El mensaje del admin se llama siempre «Mensaje del refugio».
- El estado vacío enlaza al catálogo.

**Paralelismo:** B4.1, B4.2 y B4.3 no comparten archivos. B4.4 y B4.5 van
después de B4.2.

## 8. Fase 5 · Panel sin Bootstrap

### B5.1 · Lista de mascotas

**Archivos:** `mascotas/admin/lista.html` y `mascotas.py:101-158`.

**Criterios de aceptación:**
- La tabla usa la macro `tabla`, con `caption`, `scope` y `aria-sort`.
- A 375 px se llega a «Estado» y «Acciones» desplazando la región, y no se
  oculta ninguna columna (P-23).
- «Eliminar» solo aparece si la mascota no tiene solicitudes. Si las tiene, se
  muestra «Tiene N solicitudes» con una alternativa, y el recuento sale de una
  consulta agregada (P-46).
- La confirmación de borrado incluye el nombre (P-43).

**Tests:** `test_rendimiento.py` y `test_admin.py` a 375 px.

### B5.2 · Formulario de mascota

**Archivos:** `mascotas/admin/form.html`.

**Criterios de aceptación:**
- El formulario usa `campo` y `grupo_opciones`.
- La especie se elige con un `datalist`.
- Hay una vista previa de la foto.

**e2e:** editar una mascota subiendo una foto con `FOTOS_BACKEND=local`
(P-40).

### B5.3 · Solicitudes del admin

**Archivos:** `solicitudes/admin/lista.html`, `revisar.html`,
`solicitudes.py:137-213`, `mascotas/detalle.html` y el context processor.

**Criterios de aceptación:**
- El enlace «Panel» lleva el contador de pendientes, y la lista ordena las
  pendientes de más antigua a más reciente (P-28).
- La pantalla de revisión muestra las demás candidatas de la misma mascota.
- El admin no ve «Solicitar adopción» y, si entra en la ruta, recibe un 403
  propio (P-45).

**e2e:** aprobar con confirmación rechaza solas las demás, y rechazar sin
motivo da error (P-40).

### B5.4 · Retirar Bootstrap

**Archivos:**
- Se eliminan `app/static/vendor/bootstrap/`, `base_bootstrap.html` y
  `styles.css`.
- Se actualizan `README.md`, `.claude/CLAUDE.md` y `docs/ARQUITECTURA.md`.

**Tests:** un test comprueba que ninguna plantilla referencia `bootstrap`,
`btn-` ni `col-md`.

## 9. Grafo de dependencias y oleadas

```
B0.2 ─┬─ B1.1 ─┬─ B1.3 ─┬─ B1.4
      │        │        └─ B2.6
      │        ├─ B2.7
      │        └─ B1.2 ── B2.2 ── B2.4 ── B2.5
      ├─ B1.5 ─┘
      ├─ B2.1
      └─ B2.3
(fase 2 fusionada) ─┬─ B3.1 ──────────────────┐
                    ├─ B3.2 ── B3.3 ── B3.4 ──┼─ B3.6 ─┬─ B4.1
                    └─ B3.5 ──────────────────┘        ├─ B4.2 ─┬─ B4.4
                                                       └─ B4.3  └─ B4.5
(fase 4 fusionada) ─┬─ B5.1 ── B5.2 ─┬─ B5.4
                    └─ B5.3 ─────────┘
```

| Oleada | En paralelo (máx. 3) | Motivo de la separación |
|---|---|---|
| 0 | B0.2 (B0.1 en local) | — |
| 1 | B1.1, B1.5, B2.1 | B2.3 sería el cuarto |
| 2 | B1.2, B1.3, B2.3 | B1.2 y B1.3 esperan a B1.1 (`solicitudes.py`, `api/`) |
| 3 | B1.4, B2.2, B2.7 | B2.2 comparte `mascotas.py` y `form.html` con B1.2 |
| 4 | B2.4, B2.6 | B2.4 comparte `mascotas.py` con B2.2 |
| 5 | B2.5 | Mismo paquete `app/fotos/` |
| 6 | B3.1, B3.2, B3.5 | Empieza la fase 3 |
| 7 | B3.3 | `sistema.css` |
| 8 | B3.4 | `sistema.css` |
| 9 | B3.6 | Toca la primera línea de todas las plantillas |
| 10 | B4.1, B4.2, B4.3 | — |
| 11 | B4.4, B4.5 | Dependen del detalle de B4.2 |
| 12 | B5.1, B5.3 | — |
| 13 | B5.2 | Comparte `mascotas.py` con B5.1 |
| 14 | B5.4 | Cierre |

**Estrategia de PRs:** todos salen de `main`, y un bloque empieza cuando su
dependencia está fusionada. Solo se apila para adelantar trabajo (B1.3 sobre
B1.1, B2.4 sobre B2.2 o B3.4 sobre B3.3), y siempre se avisa. En ese caso, al
fusionar el de abajo hay que cerrar y reabrir el siguiente PR para que se
lance el CI, y volver a activar el auto-merge si estaba puesto.

**Orden de merge:** el de las oleadas y, dentro de cada una, de menor a mayor
riesgo. La migración 0002 (B1.1) se fusiona antes que la 0003 (B2.7). Se
fusiona con `gh pr merge <n> --merge`.

## 10. Dónde entra cada ADR

| ADR | Bloque |
|---|---|
| `README.md` (solo la fila 0005) y `template.md` | B0.2 |
| 0005 Priorización | B0.2 |
| 0004 Solicitudes en paralelo | B1.1 |
| 0003 Almacenamiento de fotos | B2.4 |
| 0001 Frontend sin Bootstrap | B3.1 |
| 0002 Sistema de diseño | B3.2 |

Cada PR de ADR añade su fila al índice.

## 11. Riesgos y reversión

| Fase | Riesgo | Mitigación | Reversión |
|---|---|---|---|
| 1 | Migración de datos 0002 | Test de upgrade y downgrade con datos; el CI hace upgrade, seed, `downgrade base` y upgrade | `flask --app run db downgrade 0001` **antes** de desplegar el código anterior, y después revertir el PR. Las adopciones no se revierten (documentado) |
| 1 | Aprobaciones concurrentes | `FOR UPDATE` y nueva comprobación del estado tras el bloqueo | Revertir B1.1 junto con su migración |
| 1 | Cambio de contrato de la API (sin `en_proceso`, cuestionario validado) | Documentado en el PR y en `ARQUITECTURA.md`; el formato de los errores no cambia | Revertir B1.3 por separado |
| 2 | Disco efímero con el backend `local` | En producción, `local` solo con un `FOTOS_DIR` explícito, más `flask exportar-fotos` | `FOTOS_BACKEND=s3`; `foto_url` no cambia de esquema |
| 2 | Token CSRF sin caducidad | Ligado a la sesión, con `SameSite` y protección contra el doble envío | Restaurar `WTF_CSRF_TIME_LIMIT` |
| 3 | La CSP sin `'unsafe-inline'` rompe Bootstrap | Bootstrap usa el CSSOM, y el fixture `errores_js` de los e2e lo detecta | Revertir B3.1 (cambia una línea de la CSP) |
| 3-5 | **Fase intermedia con dos bases** | Cada página se migra cambiando su `extends`; mismas categorías de `flash`; tests de teclado | Revertir el PR de la página: vuelve a `base_bootstrap.html`, que existe hasta B5.4 |
| 4 | Regresiones de accesibilidad | Tests de las macros, `ecc:a11y-architect` y e2e de teclado | Revertir el PR de la página |
| 5 | Algo se queda sin estilo al quitar Bootstrap | Un test busca clases de Bootstrap; revisión visual a 375 y 1280 px | Revertir B5.4 |

## 12. Línea base «después»

Se repite la medición de la auditoría y se compara con su sección «Línea base
de métricas («antes»)».

1. **Métricas por página.** El mismo script de Playwright, con los mismos
   perfiles y páginas, más las de error. Objetivos:
   - LCP de la portada ≤ 1,5 s en móvil;
   - 0 peticiones a la CDN;
   - CLS y TBT siguen en 0.
2. **Hallazgos por gravedad.** El estado de P-01 a P-50: resuelto, parcial o
   fuera de alcance. Se espera:
   - 0 críticos;
   - de los altos, solo queda P-11;
   - de los medios, quedan P-25, P-30 y P-33;
   - de los bajos, quedan P-47 en parte, P-49 y P-50.
3. **Capturas.** Las mismas pantallas a 375 y 1280 px, más las páginas de error
   y el menú abierto.
4. **Indicadores técnicos:**
   - 0 `style=`, y la CSP sin `'unsafe-inline'` ni CDN;
   - 9 macros, cada una con su test;
   - de 6 a unos 16 e2e;
   - 0 violaciones de contraste en los tokens;
   - cobertura de ramas.
