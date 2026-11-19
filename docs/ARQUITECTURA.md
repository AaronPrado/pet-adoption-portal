> Portal de Adopción de Mascotas - Documentación

---

## Diagrama UML de Clases Python

```
┌─────────────────────────────────────────────────────┐
│                    Usuario                          │
│              (hereda de UserMixin)                  │
├─────────────────────────────────────────────────────┤
│ - id: int                                           │
│ - email: str                                        │
│ - password_hash: str (nullable)                     │
│ - nombre: str                                       │
│ - apellidos: str                                    │
│ - telefono: str                                     │
│ - direccion: str                                    │
│ - rol: str                                          │
│ - fecha_registro: datetime                          │
│ - activo: bool                                      │
│ - oauth_provider: str                               │
│ - oauth_id: str (unique)                            │
│ - solicitudes: List[Solicitud]  (relación 1:N)      │
│ - solicitudes_revisadas: List[Solicitud] (relación) │
├─────────────────────────────────────────────────────┤
│ + __init__(email, nombre, password=None, **kwargs)  │
│ + set_password(password: str) -> None               │
│ + check_password(password: str) -> bool             │
│ + is_active -> bool  (propiedad, refleja activo)    │
│ + is_admin() -> bool                                │
│ + __repr__() -> str                                 │
└─────────────────────────────────────────────────────┘
              │ 1
              │
              │ N
              ▼
┌─────────────────────────────────────────────────────┐
│                   Solicitud                         │
├─────────────────────────────────────────────────────┤
│ - id: int                                           │
│ - usuario_id: int (FK -> Usuario)                   │
│ - mascota_id: int (FK -> Mascota)                   │
│ - fecha_solicitud: datetime                         │
│ - estado: str                                       │
│ - cuestionario_json: dict                           │
│ - comentarios_admin: str                            │
│ - fecha_revision: datetime                          │
│ - revisado_por: int (FK -> Usuario)                 │
│ - usuario: Usuario (relación N:1)                   │
│ - mascota: Mascota (relación N:1)                   │
│ - revisor: Usuario (relación N:1)                   │
├─────────────────────────────────────────────────────┤
│ + __init__(usuario_id, mascota_id, cuestionario)    │
│ + registrar_revision(estado, admin_id, comentario)  │
│ + esta_pendiente() -> bool                          │
│ + __repr__() -> str                                 │
└─────────────────────────────────────────────────────┘
              │ N
              │
              │ 1
              ▼
┌─────────────────────────────────────────────────────┐
│                    Mascota                          │
├─────────────────────────────────────────────────────┤
│ - id: int                                           │
│ - nombre: str                                       │
│ - especie: str                                      │
│ - raza: str                                         │
│ - edad_aprox: int                                   │
│ - sexo: str                                         │
│ - tamano: str                                       │
│ - descripcion: str                                  │
│ - estado: str                                       │
│ - foto_url: str                                     │
│ - fecha_ingreso: datetime                           │
│ - vacunado: bool                                    │
│ - esterilizado: bool                                │
│ - solicitudes: List[Solicitud] (relación 1:N)       │
├─────────────────────────────────────────────────────┤
│ + __init__(nombre, especie, descripcion)            │
│ + esta_disponible() -> bool                         │
│ + marcar_adoptado() -> None                         │
│ + tiene_solicitudes_pendientes() -> bool            │
│ + __repr__() -> str                                 │
└─────────────────────────────────────────────────────┘
```

---

## Diagrama de Base de Datos (PostgreSQL)

```
┌─────────────────────────┐
│      USUARIOS           │
├─────────────────────────┤
│ PK id                   │
│    email (UNIQUE)       │
│    password_hash        │
│    nombre               │
│    apellidos            │
│    telefono             │
│    direccion            │
│    rol                  │
│    fecha_registro       │
│    activo               │
│    oauth_provider       │
│    oauth_id (UNIQUE)    │
└─────────────────────────┘
         │ 1
         │
         │ N
         │
┌─────────────────────────┐       ┌─────────────────────────┐
│     SOLICITUDES         │   N   │      MASCOTAS           │
├─────────────────────────┤ ───── ├─────────────────────────┤
│ PK id                   │   1   │ PK id                   │
│ FK usuario_id           │       │    nombre               │
│ FK mascota_id           │       │    especie              │
│    fecha_solicitud      │       │    raza                 │
│    estado               │       │    edad_aprox           │
│    cuestionario_json    │       │    sexo                 │
│    comentarios_admin    │       │    tamano               │
│    fecha_revision       │       │    descripcion          │
│ FK revisado_por         │       │    estado               │
└─────────────────────────┘       │    foto_url             │
                                  │    fecha_ingreso        │
                                  │    vacunado             │
                                  │    esterilizado         │
                                  └─────────────────────────┘
```

### Restricciones

- `usuarios.rol` ∈ {adoptante, admin}; `mascotas.estado` ∈ {disponible,
  en_proceso, adoptado}; `solicitudes.estado` ∈ {pendiente, aprobada,
  rechazada}; `mascotas.sexo`, `mascotas.tamano` y `edad_aprox >= 0` con CHECK.
  El flujo ya no usa `en_proceso` (ADR-0004); el CHECK lo sigue admitiendo
  hasta una limpieza posterior, y la migración `0002` pasó las filas que lo
  tenían a `adoptado` (con solicitud aprobada) o a `disponible`.
- `UNIQUE (usuario_id, mascota_id)`: un usuario solo puede solicitar una vez
  cada mascota.
- Las solicitudes se borran en cascada (`ON DELETE CASCADE`) con su usuario o
  su mascota.
- `cuestionario_json` es JSONB en PostgreSQL.
- `mascotas.especie` es texto libre, pero el modelo la normaliza al asignarla
  (`@validates('especie')` con `Mascota.normalizar_especie`): compone los
  caracteres (NFC), quita los invisibles de formato (Unicode `Cf`, como
  U+200B), quita los espacios de los extremos, deja un solo espacio entre
  palabras y pone mayúscula solo en la primera letra («perro» y « PERRO » →
  «Perro»; «cobaya DE Indias» → «Cobaya de indias»). Lanza `ValueError` si no
  es texto, si queda vacía o si supera `Mascota.LONGITUD_ESPECIE` (50; «ß» pasa
  a «Ss» y alarga el valor). Así el filtro del catálogo muestra una sola opción
  por especie. La migración `0003` normalizó las especies que ya existían
  (P-31).

### Migraciones

El esquema se define en `app/models.py` y se aplica con migraciones de
Alembic (Flask-Migrate) en `migrations/`. La app no crea tablas al arrancar:

```bash
flask --app run db upgrade                       # aplicar migraciones
flask --app run db migrate -m "descripción"      # generar una nueva tras cambiar los modelos
```

### Regla de adopción (ADR-0004)

Las solicitudes se admiten en paralelo y el estado de la mascota lo decide
solo `app/adopciones.py`, que usan las rutas web y la API:

| Operación | Solicitud | Mascota | Otras pendientes |
|-----------|-----------|---------|------------------|
| `crear_solicitud` | `pendiente` | sigue `disponible` | sin cambios |
| `rechazar` | `rechazada` | sin cambios | sin cambios |
| `aprobar` | `aprobada` | `adoptado` | `rechazada` con `COMENTARIO_RECHAZO_AUTOMATICO` |
| `adoptar_fuera_del_portal` | — | `adoptado` | todas `rechazada` con `COMENTARIO_RECHAZO_AUTOMATICO` |
| `volver_a_disponible` | — | `disponible` | sin cambios (las rechazadas no se reabren) |

- Cada operación hace un único commit; si la regla no la permite hace
  rollback, lanza una subclase de `ErrorAdopcion` (`SolicitudYaRevisada`,
  `MascotaYaAdoptada`…) y no cambia nada. La web y la API muestran su
  `mensaje`; `MascotaNoEncontrada` se responde con 404.
- Antes de cambiar nada bloquean la fila de la mascota
  (`SELECT … FOR UPDATE`) y vuelven a leer la mascota y la solicitud, para
  que dos aprobaciones simultáneas no adopten dos veces ni se cree una
  pendiente mientras otra se aprueba.
- Las pendientes que cierra una aprobación llevan en `revisado_por` y
  `fecha_revision` el admin que aprobó. Las que cerró la migración `0002`
  (pendientes de mascotas ya adoptadas) tienen `revisado_por` NULL.
- Invariante: una mascota `adoptado` no tiene solicitudes pendientes.
- El formulario de edición del panel admin no cambia el estado (un POST que
  incluya `estado` lo ignora). En su lugar ofrece dos acciones POST, solo
  para admin: «Marcar como adoptada fuera del portal»
  (`/mascotas/admin/adoptada-fuera/<id>`) en una mascota no adoptada y
  «Volver a disponible» (`/mascotas/admin/volver-a-disponible/<id>`) solo si
  está `adoptado` sin ninguna solicitud aprobada
  (`puede_volver_a_disponible`); una adopción del portal no se deshace.
  La lista del panel solo filtra por `disponible` y `adoptado`; cualquier
  otro valor de `?estado=` se ignora.
- «Tiene solicitudes en curso» (catálogo, detalle y formulario admin) se
  deriva de `pendientes_por_mascota(ids)`: una sola consulta agregada
  (`GROUP BY mascota_id`) para toda la página, sin N+1.
- Borrar una mascota bloquea antes su fila con `consulta_mascota_bloqueada`,
  para que una solicitud creada a la vez no se cuele entre la comprobación de
  solicitudes y el borrado.

---

## Conceptos POO

### 1. Encapsulación
- **Atributos privados:** `Usuario.password_hash` no se accede directamente
- **Métodos públicos:** `set_password()` y `check_password()` controlan el acceso
- **Validación:** Los métodos validan datos antes de modificar atributos

### 2. Abstracción
- **Funciones de dominio:** `aprobar()`, `rechazar()` y las demás de
  `app/adopciones.py` encapsulan la regla de adopción
- **Separación de responsabilidades:** Cada clase tiene una función clara

### 3. Polimorfismo
- **Comportamiento según rol:** `Usuario.is_admin()` devuelve distinto valor
- **Métodos sobrescritos:** `__repr__()` personalizado en cada clase

### 4. Herencia
- **UserMixin:** `Usuario` hereda de `UserMixin` (Flask-Login) y sobrescribe
  `is_active` para que las cuentas desactivadas no puedan iniciar sesión
- **Configuración:** `DevelopmentConfig`, `TestingConfig` y `ProductionConfig`
  heredan de `Config` y redefinen `init_app()`
- **Templates Jinja2:** las páginas extienden `base.html` o, hasta su
  migración, `base_bootstrap.html`

### 5. Decoradores
- **@admin_required:** Decorador personalizado en `app/decorators.py`
- Usa `functools.wraps` para preservar metadatos de la función
- Verifica rol de administrador en rutas protegidas

### 6. Relaciones
- **1:N (uno a muchos):**
  - Un usuario puede tener muchas solicitudes
  - Una mascota puede tener muchas solicitudes
- **N:1 (muchos a uno):**
  - Muchas solicitudes pertenecen a un usuario
  - Muchas solicitudes pertenecen a una mascota


## Estructura de Módulos Flask

```
app/
├── __init__.py          # Application Factory: extensiones (db, migrate, login,
│                        # oauth, csrf, limiter), ProxyFix, blueprints,
│                        # cabeceras de seguridad y /health
├── errores.py           # Páginas de error de la web (la API queda fuera)
├── contexto.py          # Marca (context processor) y usuario de la navegación
├── cli.py               # Comandos flask crear-admin y exportar-fotos
├── models.py            # Modelos SQLAlchemy (Usuario, Mascota, Solicitud)
├── adopciones.py        # Regla de adopción: crear, aprobar y rechazar solicitudes
├── cuestionario.py      # Preguntas, opciones y validación del cuestionario
├── decorators.py        # @admin_required
├── fotos/               # Almacenamiento de fotos (ADR-0003)
│   ├── __init__.py      # guardar_foto, borrar_foto, subida_disponible, srcset_foto, exportar_fotos
│   ├── procesado.py     # Pillow: tipo real, límite de píxeles, sin EXIF, variantes WebP
│   ├── local.py         # Backend local: FOTOS_DIR o instance/fotos
│   └── s3.py            # Backend s3: boto3, endpoint_url opcional
│
├── routes/              # Blueprints
│   ├── auth.py          # Registro, login, logout, OAuth Google
│   ├── fotos.py         # GET /fotos/<clave> (fotos del backend local)
│   ├── mascotas.py      # Catálogo, detalle y CRUD del panel admin
│   ├── solicitudes.py   # Crear, consultar y revisar solicitudes
│   └── api/             # API REST (Flask-RESTX)
│       ├── __init__.py  # Blueprint, Swagger y formato común de errores
│       ├── auth.py      # Login JWT y decorador @jwt_required
│       ├── mascotas.py  # Listado paginado y detalle (público)
│       └── solicitudes.py # Crear y consultar solicitudes (JWT)
│
├── templates/           # Plantillas Jinja2 (heredan de una de las dos bases)
│   ├── base.html        # Base sin Bootstrap (sistema de diseño): páginas migradas
│   ├── base_bootstrap.html  # Base con Bootstrap: páginas aún sin migrar
│   ├── index.html
│   ├── errores/
│   │   └── error.html   # Página común de error (400, CSRF, 403, 404, 405, 429, 500)
│   ├── macros/
│   │   ├── formulario.html  # campo, grupo_opciones, boton, resumen_errores, avisos (ADR-0002)
│   │   └── paginacion.html
│   ├── auth/            # login.html, registro.html
│   ├── mascotas/        # catalogo.html, detalle.html
│   │   └── admin/       # lista.html, form.html
│   └── solicitudes/     # nueva.html, mis_solicitudes.html, detalle.html,
│       │                # _respuestas.html (respuestas legibles, parcial)
│       └── admin/       # lista.html, revisar.html
│
└── static/
    ├── css/
    │   ├── sistema.css  # Sistema de diseño (ADR-0002): tokens, base y componentes
    │   ├── marca.css    # Marca de la protectora: acento y fuentes (solo tokens)
    │   └── styles.css   # Estilos de base_bootstrap.html (se retira con Bootstrap)
    ├── fonts/           # Atkinson Hyperlegible y Fraunces en WOFF2 (OFL)
    ├── js/app.js        # Confirmaciones `data-confirmar`, límite de tamaño de la foto, doble envío,
    │                    # foco en el resumen de errores y menús de base.html (sin JavaScript inline)
    ├── js/con-js.js     # Marca <html> con .con-js antes del primer pintado (head de base.html)
    └── vendor/bootstrap/5.3.0/  # Bootstrap CSS y bundle JS con su LICENSE (ADR-0001), sin CDN

config.py                # Configuración por entornos
migrations/              # Migraciones de Alembic
tests/                   # pytest (unitarios) y tests/e2e (Playwright)
Dockerfile, gunicorn.conf.py, Procfile   # Despliegue (docs/DESPLIEGUE.md)
```

### Configuración por entornos

`config.py` define `DevelopmentConfig`, `TestingConfig` y `ProductionConfig`;
`FLASK_ENV` elige una (production si no se indica). Producción no arranca si
faltan `SECRET_KEY`, `JWT_SECRET_KEY` o `DATABASE_URL`, o si alguna clave
tiene menos de 32 bytes.

### Páginas de error de la web

`app/errores.py` registra los manejadores de 400, `CSRFError`, 403, 404, 405,
413, 429 y 500. Salvo el 413, todos renderizan `errores/error.html`, que
extiende la base sin Bootstrap, `base.html` (`lang="es"`, navegación), con su
código de estado, un `h1` en español (`cabecera_pagina`) y al menos una salida
(`enlace_boton`). 400, 403 y 404 se declaran en la tabla `ERRORES_SIMPLES`;
el resto tiene lógica propia.

| Error | Comportamiento |
|-------|----------------|
| 403 | Ofrece «Iniciar sesión» si el usuario es anónimo |
| 404 | Ofrece «Ver mascotas disponibles» e «Ir al inicio» |
| `CSRFError` (token ausente o no válido) | 400 «Tu sesión ha caducado». Ofrece «Volver al formulario» solo si el `Referer` es de este mismo host y una ruta local segura; si no, solo «Ir al inicio» |
| 405 | Conserva la cabecera `Allow` |
| 413 | Vuelve al formulario (302) con un aviso: el navegador no sigue un `Location` con estado 413. El servidor no lee el cuerpo, así que no puede conservar lo escrito; por eso `app.js` rechaza antes de enviar los archivos que superan `data-max-bytes` (`MAX_CONTENT_LENGTH`) |
| 429 | Añade `Retry-After` calculado con el límite superado (`limiter.current_limit`) y dice cuántos minutos esperar. No se activa `RATELIMIT_HEADERS_ENABLED` para no añadir cabeceras `X-RateLimit-*` a todas las respuestas |
| 500 | Mensaje genérico, sin detalles, y «Ver mis solicitudes» al adoptante. Deshace la transacción. Flask ya registra las excepciones no controladas; el manejador solo registra un `abort(500)` explícito. Si no se puede cargar el usuario (p. ej. sin base de datos), `usuario_nav()` lo trata como anónimo y la página sale completa; si aun así falla la plantilla, responde una página mínima en español |

Las rutas de `/api/` no pasan por estas páginas: el manejador devuelve la
excepción tal cual y la API mantiene su formato `{"error": ...}`. El 413 es la
excepción: se comporta como antes (flask-restx da su propio JSON en sus rutas).

El token CSRF no caduca por tiempo (`WTF_CSRF_TIME_LIMIT = None`): dura lo que
la sesión, para que quien tarde en rellenar el cuestionario no pierda el envío.
Por eso se renueva al iniciar sesión (formulario, registro y Google) y al
cerrarla (`renovar_token_csrf()` en `app/routes/auth.py`).

### Envío de formularios en `app.js`

`app/static/js/app.js` actúa sobre todos los formularios de la web, sin
cambiar las plantillas:

- **Doble envío (P-20):** un formulario POST que se envía de verdad recibe
  `aria-busy="true"` y sus envíos siguientes se cancelan antes de llegar a
  `data-confirmar`, así que tampoco se repite la confirmación. No se
  deshabilita ningún botón, para que llegue al servidor el `name`/`value` del
  que envía. La marca se pone al final de la propagación (en `window`) y solo
  si nadie canceló el evento: cancelar la confirmación no bloquea el
  formulario. Si falla la validación HTML5 (campo obligatorio vacío, foto
  mayor que `data-max-bytes`), el navegador no lanza el evento `submit` y
  tampoco se bloquea. Los formularios GET y los que se abren en otra ventana
  (`target`) no se tocan.
- **Anuncio:** `aria-busy` no lo leen los lectores de pantalla. «Enviando…» se
  escribe en una región `role="status"` con la clase `visually-hidden`, que
  se crea vacía al cargar (una región viva tiene que existir antes de
  cambiar). Un segundo intento se ignora, pero se vuelve a anunciar.
- **Liberación:** si la respuesta no llega (red caída, envío detenido o una
  descarga que no cambia de página), el formulario se libera a los 10 s
  (`LIBERAR_TRAS_MS`) para poder reintentar. Al volver con «Atrás» desde la
  bfcache (`pageshow`) se libera enseguida.
- **Foco:** si la página tiene un `[data-resumen-errores]` (con
  `tabindex="-1"`), recibe el foco al cargar.

Los e2e están en `tests/e2e/test_navegacion.py` y `test_admin.py`. Usan
`/_pruebas/formulario`, una página en HTML plano que solo registra
`tests/e2e/conftest.py`: `test_seguridad.py` comprueba que la app real da 404
ahí. La fixture `retener` deja en espera en el servidor los POST a una ruta,
como un servidor lento, y avisa con un semáforo cuando llegan, sin sondear.
Mientras hay un envío en marcha, Playwright espera a la navegación antes de
cualquier acción o consulta. Por eso `pulsar_seguido` hace los clics y sus
comprobaciones en una sola llamada a `evaluate`. La liberación por tiempo se
prueba con `page.clock` y un envío cancelado (`route.abort`).

---

## Almacenamiento de fotos

Las fotos pasan por la interfaz de `app/fotos/` (ADR-0003), con el backend que
indica `FOTOS_BACKEND`:

| Backend | Dónde guarda | `foto_url` |
|---|---|---|
| `local` | `FOTOS_DIR` o `instance/fotos`; la app las sirve en `GET /fotos/<clave>` | `/fotos/<uuid>-1200.webp` |
| `s3` | Bucket `AWS_S3_BUCKET`, carpeta `mascotas/` (`AWS_S3_ENDPOINT_URL` para servicios compatibles) | URL completa del objeto |
| vacío | No hay subida: el formulario oculta el archivo y solo admite una URL | URL externa `https://` |

- **Interfaz**: `guardar_foto()`, `borrar_foto()`, `subida_disponible()`,
  `urls_de_la_foto()`, `exportar_fotos()` y `ErrorAlmacenamiento`, cuyo
  `mensaje` (causa y solución) se muestra junto al campo. Sin backend o con
  un fallo del servicio (`ClientError`, error de disco) el formulario
  responde 400 y conserva lo escrito; el fallo se registra en el log.
- **Validación**: extensión permitida (png, jpg, jpeg, gif, webp), tamaño
  máximo de 5 MB y tipo real comprobado con Pillow, que solo prueba los
  decodificadores PNG, JPEG, GIF y WebP. Antes de decodificar se rechaza una
  imagen con más píxeles que `FOTOS_MAX_PIXELES` (40 MP por defecto) o que
  `Image.MAX_IMAGE_PIXELS`, que no se modifica y sigue protegiendo por
  encima. Estos rechazos dan el error de formato en el campo; una imagen con
  algún lado de más de 16383 px (el máximo de WebP) da un mensaje propio.
- **Procesado** (`app/fotos/procesado.py`): nunca se guarda el archivo
  original. Se decodifica, se aplica la orientación EXIF
  (`ImageOps.exif_transpose`, en el sitio), el perfil ICC se convierte a
  sRGB con `ImageCms` (si falla, se sigue sin convertir y se registra), los
  grises de 16 bits se escalan a 8, se pasa a RGB y se vuelve a codificar en
  WebP sin ningún metadato (EXIF con el GPS, XMP, perfil ICC). La
  transparencia, también la de un PNG RGB con `tRNS`, se aplana sobre
  blanco, el fondo de las fichas. De un GIF o WebP animado solo queda la
  primera imagen. Para contener la memoria, las variantes se generan en
  cadena (1200 → 800 → 400), reduciendo cada una la anterior, sin copiar el
  original.
- **Variantes**: cada foto son tres objetos WebP con el mismo nombre
  aleatorio, `<uuid hex>-400.webp`, `-800.webp` y `-1200.webp` (anchos
  máximos; nunca se amplía una imagen más pequeña, que entonces se guarda a
  su tamaño). `foto_url` guarda la de 1200, que hace de foto principal: no
  se conserva el original a resolución completa. Si falla la subida de una
  variante, se borran las ya guardadas.
- **`srcset_foto`**: filtro Jinja que devuelve el `srcset` de las tres
  variantes a partir de `foto_url`, sin consultar el almacenamiento, y `''`
  para las URLs externas y las fotos anteriores a las variantes.
- **Nombres**: `<uuid hex>-<400|800|1200>.webp` o, en las fotos anteriores a
  las variantes, `<uuid hex>.<ext>`. Solo se sirven, borran o exportan
  claves con ese formato exacto, así que no se puede salir del directorio ni
  tocar otros objetos del bucket. Las URLs externas `https://` nunca se
  borran.
- **Regla archivo/URL**: el archivo tiene prioridad. La URL debe ser
  `https://`, salvo que sea la foto propia que ya tiene la mascota
  (`/fotos/...` o la URL de S3), que se acepta tal cual; vaciar el campo deja
  la mascota sin foto.
- **Limpieza**: la foto anterior se borra solo después de un commit correcto
  (edición y baja) y si ninguna otra mascota usa la misma `foto_url` ni otra
  variante de la misma foto; se borran entonces todas sus variantes. Si el
  commit falla, se borra la foto recién subida para que no quede huérfana.
  Un fallo al borrar se registra y no afecta a la respuesta.
- **Copias de seguridad**: `flask exportar-fotos <directorio>` copia las
  fotos propias de todas las mascotas, con sus variantes, desde cualquier
  backend (ver `docs/DESPLIEGUE.md`).

---

## Sistema de diseño

El CSS propio sigue la ADR-0002: tokens en custom properties y una identidad
neutra en la que el color lo ponen las fotos de los animales. No hay modo
oscuro. Lo enlaza la base sin Bootstrap, `base.html` (abajo); las páginas aún
sin migrar siguen con `base_bootstrap.html` y `styles.css`.

- `app/static/css/sistema.css` declara `@layer reset, tokens, base,
  componentes, utilidades` y contiene los tokens comunes: color (`--color-*`),
  escala tipográfica (`--texto-xs` a `--texto-3xl`, modular 1,25 sobre 16 px),
  espaciado (`--esp-1` a `--esp-9`, múltiplos de 4 px), radios (`--radio-sm`,
  `-md`, `-lg`), sombras (`--sombra-1` en reposo y `--sombra-2` elevada), foco
  (`--foco-anillo`) y tamaño mínimo de objetivo (`--objetivo-min`, 44 px).
  `--texto-xs` (13 px) es solo para chapas y metadatos, nunca para ayudas ni
  errores. La base pone el fondo, la tinta, los enlaces subrayados y el anillo
  `:focus-visible` (`--foco-anillo` separado `--foco-separacion`) en enlaces,
  botones, campos y todo lo que tenga `tabindex` (P-17). La capa `componentes`
  tiene los formularios y los componentes (abajo).
- `app/static/css/marca.css`, que se enlaza después, es el único archivo que
  cambia cada protectora: el acento (`--marca-acento`, `-fuerte` para hover,
  `-suave` para fondos destacados y `--marca-sobre-acento` para el texto de los
  botones) y las familias tipográficas, con sus `@font-face`. El foco usa el
  acento.
- `app/static/fonts/`: Atkinson Hyperlegible 400 y 700 para el texto y
  Fraunces variable para nombres y titulares, en WOFF2 latino, autoalojadas,
  con `font-display: swap` y licencia OFL (origen y versión en su `README.md`).

| Token | Valor | Contraste |
|-------|-------|-----------|
| `--color-fondo` / `--color-superficie` | `#f5f6f4` / `#ffffff` | — |
| `--color-texto` | `#1c2422` | 14,6:1 sobre el fondo |
| `--color-texto-suave` (y `--color-placeholder`) | `#515b58` | 6,5:1 sobre el fondo; ≥ 5,9:1 sobre los tonos `-suave` |
| `--color-texto-deshabilitado` | `#848d89` | 3,2:1 (WCAG no lo exige) |
| `--color-borde-control` | `#737d79` | 3,9:1 sobre el fondo (≥ 3:1, P-13) |
| `--marca-acento` (y foco) | `#1f5e52` | 7,0:1 sobre el fondo; 7,6:1 con texto blanco |
| `--color-exito` / `-aviso` / `-error` / `-info` | `#1d6b3b` / `#8a4f00` / `#b3261e` / `#1d5a99` | ≥ 5,5:1 sobre fondo, superficie y su tono `-suave` |

Para adaptar el portal a otra protectora se cambia `marca.css` (color y
fuentes) y las variables de entorno `MARCA_NOMBRE`, `MARCA_LOGO` (ruta a un SVG
dentro de `static/`), `MARCA_CONTACTO` y `MARCA_CREDITO` de `config.py`; las
plantillas no se tocan. `tests/test_tokens.py` lee las custom properties de los dos archivos,
resuelve los `var()` y calcula el contraste WCAG de cada par (texto ≥ 4,5:1,
bordes de control y foco ≥ 3:1), así que un acento demasiado claro hace fallar
los tests. También comprueba que cada `@font-face` usa `swap` y que su WOFF2
existe.

Bootstrap y el sistema no conviven en la misma página: cada una carga una
base distinta, así que no hace falta meter Bootstrap en una `@layer`. Si
alguna vez tuvieran que convivir, habría que hacerlo, porque las reglas sin
capa ganan siempre a las de cualquier `@layer` (`@import url(...)
layer(bootstrap);` en una capa declarada la primera).

### Las dos bases (B3.6)

Durante la migración por fases (ADR-0001) hay dos plantillas base. Cada
página extiende una sola; `tests/test_base.py` comprueba cuáles usan la nueva.

| Base | Carga | Quién la usa |
|------|-------|--------------|
| `base.html` | `sistema.css`, `marca.css` y `app.js` | Las páginas migradas al sistema de diseño (hoy, las de error). Toda página nueva o migrada |
| `base_bootstrap.html` | Bootstrap vendorizado con SRI, `styles.css` y `app.js` | Las que aún no se han migrado. Se borra en B5.4, con Bootstrap |

`base.html` tiene los mismos bloques que la antigua (`title`, `extra_css`,
`content` y `extra_js`), así que migrar una página empieza por cambiar su
`{% extends %}`. Lleva:

- **Salto al contenido** hacia `<main id="contenido" tabindex="-1">`, y los
  avisos flash (macro `avisos`) dentro de `<main>`.
- **Marca** de `app/contexto.py`: el context processor `contexto_marca` da
  `marca_nombre` (también en el `<title>`), `marca_logo` y `marca_contacto`.
  Sin `MARCA_LOGO` se pinta una huella SVG con `currentColor`; con él, esa
  imagen (`<img alt="">`, el nombre ya está al lado): una ruta relativa se
  sirve desde `static/` y la URL resultante pasa por `url_segura`.
- **Navegación** con los mismos enlaces que la antigua (anónimo, adoptante y
  admin), `aria-current="page"` en la página actual y «Cerrar Sesión» por
  POST con `csrf_token`. El usuario sale de `usuario_nav()`, que nunca lanza:
  si no se puede cargar (base de datos caída en un 500), se trata como
  anónimo y la traza se registra una sola vez por petición (marca en `g`).
  `errores.py` usa la misma función para elegir las salidas.
- **Menú móvil y menú de usuario** con el patrón *disclosure*: un `<button
  data-desplegable aria-expanded aria-controls>` seguido de su panel. El
  HTML llega cerrado (`aria-expanded="false"`). `con-js.js`, un script
  externo en `<head>` sin `defer`, añade `.con-js` a `<html>` antes del
  primer pintado, y solo entonces el CSS oculta el panel que sigue a un
  botón cerrado: sin JS no se pliega nada, el botón «Menú» no se ve y todo
  funciona. `app.js` abre y cierra los menús: se cierran con `Escape` (el
  foco vuelve al botón), con un clic fuera y cuando el foco sale del botón y
  su panel. Un botón cuyo `aria-controls` no existe se ignora.
  Por debajo de 48 rem la navegación se pliega tras «Menú»; por encima, el
  menú de usuario flota bajo su botón.
- **Pie** que baja al fondo en las páginas cortas (`body.pagina` en flex),
  con «© {año} {marca}» (el año, de `utcnow()`), el contacto si
  `MARCA_CONTACTO` está definido (enlace `mailto:` si es un email) y, debajo,
  el crédito de `MARCA_CREDITO`. Sin definir, el crédito es «Desarrollado
  por Aarón Prado»; vacío, no aparece.

El CSS de la base (`.pagina`, `.contenedor`, `.cabecera-sitio`, `.marca`,
`.navegacion`, `.menu-usuario`, `.pie-sitio`) está al final de la capa
`componentes` de `sistema.css`. A 320 px no hay scroll horizontal, tampoco
con una marca o un nombre de usuario largos, y todos los objetivos miden al
menos `--objetivo-min`. Los e2e de teclado, sin JS, del menú de usuario y del
reflow con textos largos están en `tests/e2e/test_navegacion.py`.

### Macros de formulario

`app/templates/macros/formulario.html` genera los formularios accesibles con
las clases del sistema (`campo`, `boton`, `aviso`...), no las de Bootstrap.
De momento solo `base.html` usa `avisos`: los formularios se migran en la
fase 4 del plan de frontend.

```jinja
{% import "macros/formulario.html" as f %}

<main id="contenido">
  {{ f.avisos() }}
  {{ f.resumen_errores(errores) }}
  <form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    {{ f.leyenda_obligatorios() }}
    {{ f.campo('email', 'Email', valores, errores, tipo='email', obligatorio=true,
               autocomplete='email', ayuda='Te avisaremos aquí de tu solicitud.') }}
    {{ f.campo('password', 'Contraseña', valores, errores, tipo='password',
               obligatorio=true, autocomplete='current-password') }}
    {{ f.campo('sexo', 'Sexo', valores, errores, tipo='select',
               opciones=[('Macho', 'Macho'), ('Hembra', 'Hembra')]) }}
    {{ f.grupo_opciones('jardin', '¿Tienes jardín?', SI_NO, valores, errores, obligatorio=true) }}
    {{ f.boton('Enviar') }}
  </form>
</main>
```

- **`campo(nombre, etiqueta, valores, errores, tipo, ayuda, obligatorio,
  autocomplete, opciones, opcion_vacia, id, filas, atributos)`**: `label for`,
  valor enviado, `required` y asterisco (`aria-hidden`: lo anuncia
  `required`), `aria-invalid="true"` con error y `aria-describedby` hacia
  `<id>-error` y `<id>-ayuda` (en ese orden, solo los que existan). Tipos,
  en lista blanca y sin distinguir mayúsculas: text, email, password, number,
  tel, url, search, date, textarea y select (`opciones` en pares `(value,
  etiqueta)`); cualquier otro se pinta como text. **Un `password` nunca se
  vuelve a rellenar**, ni con `value` en `atributos`. La ayuda es un texto
  visible: el placeholder no sustituye a las instrucciones. `atributos` añade
  `min`, `maxlength`, `inputmode`... con `xmlattr`; es para el desarrollador,
  nunca para datos del usuario, y descarta las claves `on*`.
- **`leyenda_obligatorios()`**: explica el asterisco; una vez, antes del
  primer campo obligatorio.
- **`grupo_opciones(nombre, leyenda, opciones, valores, errores, tipo,
  ayuda, obligatorio)`**: radios (o `tipo='checkbox'`) en `fieldset` y
  `legend`; el error y la ayuda describen el `fieldset` y cada opción lleva
  `aria-invalid`. El `fieldset` tiene id `<nombre>` y `tabindex="-1"`, para
  ser el destino del resumen. Los ids de las opciones son `<nombre>_<value>`,
  como los del cuestionario, con los espacios del value cambiados por `-`.
  Las casillas aceptan una lista en `valores`. `required` solo se pone en
  radios y en una casilla única: HTML no sabe exigir «al menos una».
- **`boton(texto, variante, tipo, nombre, valor, atributos)`**: variantes
  `primario`, `secundario` y `peligro`, siempre con `type` explícito
  (`submit` por defecto). `atributos`, como en `campo`.
- **`resumen_errores(errores, titulo, destinos)`**: lista los errores con un
  enlace `#<campo>` a cada uno, que es el id de `campo` y del `fieldset` de
  `grupo_opciones`. Si un `campo` lleva un `id` distinto de su nombre, se
  pasa en `destinos` (`{'edad': 'edad_aprox'}`). Es un `role="group"` con
  `aria-labelledby` en su título (así se anuncia al recibir el foco),
  `tabindex="-1"` y `data-resumen-errores`: `app.js` le da el foco al cargar.
  Con el resumen, los campos ya no llevan `autofocus`.
- **`avisos(mensajes=None)`**: los mensajes flash (o los pares
  `(categoría, texto)` que se le pasen). Va dentro de `<main>`. `success` e
  `info` usan `role="status"`; `warning` y `danger`, `role="alert"`; otra
  categoría se pinta como información.

Todo el contenido pasa por el escape de Jinja. `tests/test_macros_formulario.py`
renderiza cada macro y comprueba sus atributos, que la contraseña no se
rellena y que el contenido se escapa; `tests/test_tokens.py`, que la capa
`componentes` solo usa tokens de color, el foco visible, los objetivos de
`--objetivo-min`, los estados hover, active, disabled, `aria-busy` e
inválido (P-20) y la utilidad `.visually-hidden` (el mismo nombre que en
Bootstrap), que oculta la región «Enviando…» de `app.js`.

### Macros de componentes

`app/templates/macros/componentes.html` tiene el resto de piezas de las
páginas, con su CSS al final de la capa `componentes`. De momento solo las
usa la página de error (`cabecera_pagina` y `enlace_boton`); el resto de
páginas las adoptan en las fases 4 y 5.

```jinja
{% import "macros/componentes.html" as c %}

{% call c.cabecera_pagina('Mascotas', 'Altas, cambios y estados.', volver_url=url_for('index'),
                          volver_texto='Volver a la portada') %}
  {{ c.enlace_boton('Nueva mascota', url_for('mascotas.admin_nueva')) }}
{% endcall %}

{% if mascotas %}
<ul class="rejilla-tarjetas">
  {% for m in mascotas %}
  <li>{{ c.tarjeta_mascota(m, diferida=loop.index > 3) }}</li>
  {% endfor %}
</ul>
{% else %}
{{ c.estado_vacio('No hay mascotas con esos filtros', 'Prueba a quitar alguno.',
                  url_for('mascotas.catalogo'), 'Ver todas') }}
{% endif %}

{% call c.tabla('mascotas', 'Mascotas del refugio', columnas, orden=(orden_campo, orden_dir),
                endpoint='mascotas.admin_lista', vacia='No hay mascotas.') %}
  {% for m in mascotas %}
  <tr>
    <td class="tabla__columna--numerica">{{ m.id }}</td>
    <th scope="row">{{ m.nombre }}</th>
    <td>{{ c.badge_estado(m.estado) }}</td>
  </tr>
  {% endfor %}
{% endcall %}
```

- **`tarjeta_mascota(mascota, nivel=2, diferida=true, sizes)`**: `article`
  nombrado por su título (`h2` por defecto; `nivel` de 2 a 6), la chapa de
  estado, los datos (especie, raza, edad y tamaño, los que haya) y un único
  enlace «Ver a {nombre}», con aspecto de botón secundario, que hace pulsable
  toda la tarjeta (el nombre y los datos quedan por encima, seleccionables, y
  la tarjeta entera pinta el foco con `:has(:focus-visible)`). La foto lleva `width`/`height`, `srcset_foto` + `sizes`
  (solo en fotos propias con variantes), `alt` «Foto de {nombre}, {especie}» y
  `loading="lazy"`; con `diferida=false` (la primera fila) va sin `lazy` y con
  `fetchpriority="high"`. Sin foto, un marcador propio (huella SVG con
  `role="img"` y `aria-label`), sin imágenes de terceros. La foto va en una
  proporción 4:3 con `object-fit: cover`, sin altos fijos (DIS-07), y las
  tarjetas van en `ul.rejilla-tarjetas`, cuyas columnas llenan el contenedor
  (`minmax(min(--ancho-tarjeta-min, 100%), 1fr)`, QA-13).
- **`badge_estado(estado, tipo='mascota')`**: el estado con texto y un punto
  decorativo; `tipo` es `mascota` o `solicitud`. Las etiquetas salen de
  `ETIQUETAS_ESTADO` en `app/models.py` (la única fuente, a través del global
  de Jinja `etiqueta_estado`), cuyas claves son los valores guardados. El tono
  (`exito`, `aviso`, `error`, `info`) se decide en la macro; un estado
  desconocido se muestra tal cual, escapado y en `neutro`.
- **`cabecera_pagina(titulo, entradilla, volver_url, volver_texto)`**: `h1`,
  entradilla opcional, enlace de volver encima (DIS-09) y, con `{% call %}`,
  un hueco para acciones que en móvil baja y ocupa el ancho (DIS-14).
  `volver_texto` tiene que decir adónde vuelve («Volver al catálogo»): un
  «Volver» suelto no se entiende en la lista de enlaces de un lector de
  pantalla.
- **`tabla(id, caption, columnas, orden, endpoint, vacia, caption_oculto)`**:
  región desplazable con `role="region"`, `aria-labelledby` hacia el
  `caption` (`<id>-titulo`) y `tabindex="0"` (P-23); cabeceras con
  `scope="col"`. Cada columna es un dict con `titulo` y, opcionales, `clave`,
  `ordenable`, `numerica` (cifras tabulares a la derecha) y `oculto` (título
  solo para lectores de pantalla). La columna de `orden=(clave, 'asc'|'desc')`
  lleva `aria-sort`; con `endpoint`, las ordenables enlazan a `?orden=&dir=`
  (los parámetros que ya usa el admin) y su nombre accesible dice qué hará el
  clic («Nombre, ordenar ascendente»). La flecha es decorativa y sin
  opacidad, para no bajar de 3:1. Las filas van en `{% call %}`, con la celda que identifica
  la fila como `<th scope="row">`; sin filas se pinta `vacia`.
- **`estado_vacio(titulo, texto, accion_url, accion_texto, nivel=2)`**:
  título, texto y una acción secundaria opcional.
- **`enlace_boton(texto, url, variante)`** (P-15): un `<a>` con las clases de
  `boton`, para que las llamadas a la acción que navegan midan y pesen lo
  mismo que los botones. Lo que cambia datos sigue siendo un `boton` en un
  formulario POST.

**URLs de las macros (`app/enlaces.py`).**
- `url_orden(endpoint, clave, direccion)`, global de Jinja, construye en
  Python los enlaces de orden de `tabla`. Conserva los filtros de la
  petición, también los repetidos (`request.args.lists()`), quita `page`
  (vuelve a la primera página) y descarta las claves que empiezan por `_`
  (`_external`, `_scheme`, `_anchor`...) y `endpoint`, que chocan con
  `url_for`: `?endpoint=1` daba un 500.
- El filtro `url_segura` valida `enlace_boton`, `volver_url` y `accion_url`.
  Solo admite rutas propias (`/...`, pero no `//` ni `/\`) y `http:`,
  `https:` y `mailto:`, sin distinguir mayúsculas ni tener en cuenta los
  espacios y controles que el navegador ignora (`java\tscript:`). Con
  cualquier otra URL devuelve `''` y **la macro no pinta el enlace**: un `#`
  dejaría un enlace muerto que parece funcionar.

`tests/test_macros_componentes.py` renderiza cada macro y comprueba sus
atributos de accesibilidad, el escape y los casos límite (sin foto, nombre
con caracteres especiales, tabla vacía, estado desconocido), que
`ETIQUETAS_ESTADO` cubre los valores del CHECK de cada tabla y las reglas
clave del CSS (rejilla, proporción de la foto, tonos de chapa, foco de la
tarjeta). `tests/test_enlaces.py` cubre `url_orden` y `url_segura`, con una
petición real a una página con la tabla y `?endpoint=1`.

---

## API REST

API RESTful con autenticación JWT y documentación Swagger automática.

### Endpoints

| Método | Endpoint | Protegido | Descripción |
|--------|----------|-----------|-------------|
| POST | `/api/auth/login` | No | Login, devuelve JWT (máximo 5 intentos por minuto) |
| GET | `/api/mascotas/` | No | Mascotas disponibles, paginadas y filtrables |
| GET | `/api/mascotas/<id>` | No | Detalle de mascota |
| POST | `/api/solicitudes/` | JWT | Crear solicitud (201 con cabecera `Location`); la mascota sigue `disponible`; cuestionario validado |
| GET | `/api/solicitudes/mias` | JWT | Mis solicitudes |
| GET | `/api/solicitudes/<id>` | JWT | Una solicitud propia (404 si es de otro usuario) |

Desde la ADR-0004, `POST /api/solicitudes/` ya no pasa la mascota a
`en_proceso` y varios usuarios pueden solicitar la misma (201 cada uno; 409
si el mismo usuario repite). El campo `estado` de las mascotas solo toma
`disponible` o `adoptado`; 400 «Mascota no disponible» significa que ya está
adoptada. El formato de errores no cambia.

### Cuestionario de adopción (P-04)

`app/cuestionario.py` es la única fuente del cuestionario: preguntas,
opciones (`value` y etiqueta legible), obligatorias y dependencias. La web y
la API validan cada envío nuevo con `validar(datos) -> (limpio, errores)`
**antes** de llamar a `adopciones.crear_solicitud`; un envío inválido no
crea la solicitud. Los cuestionarios ya guardados no se revalidan.

- Obligatorias: todas salvo `mascotas_detalles` y `referencias`.
  `tiene_mascotas="si"` exige `mascotas_detalles`.
- Las preguntas de opciones solo admiten sus `value` (`"casa"`, `"8+"`…) y
  las de sí/no, las **cadenas** `"si"` o `"no"`, como el formulario: un
  booleano JSON (`true`/`false`) da 400. Los textos se recortan, admiten
  hasta 2000 caracteres y no pueden contener el carácter NUL (`\u0000`),
  que PostgreSQL rechaza en JSONB.
- Se guarda el cuestionario limpio, con todas las preguntas: sí/no como
  booleano y lo no contestado como `null`, nunca como `false`.

En la web, un envío inválido responde 400 y vuelve a pintar el formulario
con lo escrito (cada texto, recortado a 2001 caracteres) y el error junto a
cada campo (contrato `valores`/`errores`).

**Cambio de contrato de `POST /api/solicitudes/`.** Antes aceptaba cualquier
objeto plano en `cuestionario`; ahora aplica la misma validación y responde
400 con el formato de siempre:

| Caso | Respuesta 400 |
|------|---------------|
| Falta `cuestionario` o no es un objeto | `{"error": "Datos inválidos"}` |
| Claves que no son preguntas | `{"error": "Cuestionario no válido: campos desconocidos: a, b"}` (hasta 5) |
| Respuestas que faltan o no son válidas | `{"error": "Cuestionario no válido: horas_solo (opción no válida), vivienda_tipo (falta)"}` |

Los motivos posibles son `falta`, `opción no válida`, `texto no válido` (no
es una cadena o contiene NUL) y `demasiado largo`.

El cuestionario se valida antes de buscar la mascota, así que un
cuestionario inválido da 400 aunque la mascota no exista. La respuesta 201
devuelve el cuestionario limpio.

**Respuestas legibles (P-10).** El detalle de la solicitud y la revisión del
admin incluyen el parcial `solicitudes/_respuestas.html`, que recorre
`cuestionario.SECCIONES` (las preguntas de `PREGUNTAS` agrupadas por su
atributo `seccion`, en su orden) y muestra cada respuesta con el filtro Jinja
`respuesta_legible(respuestas, campo)`, registrado en `app/__init__.py`:

- Las opciones salen con su etiqueta («8+» → «Más de 8 horas») y los
  sí/no guardados como booleano, con la de su opción («Se compromete»).
- Lo que falta (o está vacío) sale como «Sin respuesta».
- Un valor que no está en la lista se muestra tal cual, y los datos que no
  son un dict no dan error. Las claves antiguas que no son preguntas no se
  muestran.

### Revisión de solicitudes (P-06)

`POST /solicitudes/admin/revisar/<id>` (web, solo admin) recibe:

| Campo | Uso |
|-------|-----|
| `accion` | `aprobar` o `rechazar`; otro valor o ninguno → 400 «Acción no válida.» |
| `comentarios` | Mensaje opcional al aprobar (vacío se guarda como `NULL`) |
| `motivo` | Obligatorio al rechazar; lo ve el solicitante |

- Los textos se recortan y admiten hasta 2000 caracteres
  (`cuestionario.LONGITUD_MAXIMA`; los `<textarea>` llevan `maxlength`).
- Un rechazo sin motivo o un texto demasiado largo responde 400 y vuelve a
  pintar la revisión con el contrato `valores`/`errores`: lo escrito
  (recortado a 2001 caracteres), `aria-invalid`, `aria-describedby` con el
  error y la pista, y `autofocus` en el campo.
- Aprobar y rechazar son dos formularios, cada uno con `aria-labelledby` a su
  título. El de aprobar lleva `data-confirmar` (`app/static/js/app.js`) con
  sus efectos: la mascota pasa a «Adoptada» y cuántas pendientes se
  rechazarán (`adopciones.pendientes_por_mascota`, sin contar esta). El
  mismo aviso se ve en la página.
- Una solicitud ya resuelta se muestra sin formulario: estado, fecha, quién
  la revisó y el «Mensaje del refugio». Un POST sobre ella avisa «Esta
  solicitud ya ha sido revisada.» y vuelve a la revisión.

Hasta B1.4 el rechazo usaba el campo `comentarios`; es un formulario web
interno, así que la API no cambia.

### Paginación y filtros

`GET /api/mascotas/` acepta `page` y `per_page` (20 por defecto, máximo 100)
y los filtros `especie`, `raza`, `tamano`, `edad_aprox`, `edad_min` y
`edad_max`. El cuerpo es una lista; el total va en la cabecera
`X-Total-Count` y los enlaces a otras páginas en `Link` (RFC 8288).
El filtro `especie` se normaliza con `Mascota.normalizar_especie`, así que
`?especie=perro` encuentra «Perro»; si queda vacío no filtra. El filtro del
catálogo web (`app/routes/mascotas.py`) todavía compara el valor exacto: se
normalizará en B4.2.

### Errores

Todos los errores responden con el mismo formato y el código HTTP adecuado:

```json
{"error": "Recurso no encontrado"}
```

Los errores internos (500) no incluyen detalles de la excepción.

### Autenticación JWT

1. El cliente hace POST a `/api/auth/login` con email y password
2. El servidor devuelve un token JWT
3. El cliente incluye el token en las peticiones protegidas: `Authorization: Bearer <token>`
4. El decorador `@jwt_required` valida el token y extrae el usuario

### Swagger UI

Documentación interactiva disponible en `/api/docs` (desactivada en
producción):
- Prueba de endpoints
- Modelos de request/response
- Autenticación integrada

---

## Seguridad

| Capa | Medida |
|------|--------|
| Formularios | Token CSRF (Flask-WTF) en todos los POST, válido mientras dure la sesión y renovado al iniciarla y cerrarla; logout por POST |
| Sesión | Cookies `HttpOnly` y `SameSite=Lax`; `Secure` en producción |
| Login y registro | Login: 5 intentos por minuto por IP; registro: 10 por hora por IP (Flask-Limiter). Contraseñas de 8+ caracteres con hash scrypt |
| Google OAuth | Solo emails verificados por Google; las cuentas desactivadas no entran |
| Cuentas desactivadas | Pierden sesiones abiertas y tokens JWT |
| Redirecciones | `next` solo admite rutas locales |
| Navegador | CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`; sin JavaScript inline; SRI en Bootstrap |
| Errores | Mensajes genéricos al usuario; detalle solo en el log |
| Dependencias | `pip-audit` en cada push |

### Content Security Policy

`app/__init__.py` (`CSP`) envía la cabecera en todas las respuestas salvo
Swagger UI, que usa scripts inline:

```
default-src 'self'; script-src 'self'; style-src 'self';
img-src 'self' https: data:; font-src 'self'; object-src 'none';
base-uri 'none'; form-action 'self'; frame-ancestors 'none'
```

- **Sin terceros para CSS, JS ni fuentes.** Bootstrap 5.3.0 se sirve desde
  `app/static/vendor/bootstrap/5.3.0/` (ADR-0001), marcado como
  `linguist-vendored` en `.gitattributes`. Mientras dure la migración por
  fases lo cargan las páginas que extienden `base_bootstrap.html`; se retira
  en B5.4.
- **SRI también en local.** `base_bootstrap.html` mantiene `integrity` (el mismo hash que
  publicaba jsDelivr) sin `crossorigin`, que sobra en el mismo origen: si el
  fichero vendorizado cambia o se corrompe, el navegador no lo aplica.
  `tests/test_plantillas.py` comprueba que el hash coincide con el fichero.
- **Sin `'unsafe-inline'`.** Los estilos van en `app/static/css/` (`sistema.css`,
  `marca.css` y, en las páginas sin migrar, `styles.css`);
  `tests/test_plantillas.py` falla si una plantilla tiene `style=` o
  `<style>`. Bootstrap JS (menú móvil, desplegables) aplica estilos con el
  CSSOM (`element.style`), que la CSP no bloquea.
- **Imágenes:** `img-src` admite `https:` por las fotos externas de mascotas.
- **Actualizar Bootstrap.** Descargar `bootstrap.min.css` y
  `bootstrap.bundle.min.js` de la nueva versión a
  `app/static/vendor/bootstrap/<versión>/` (con su `LICENSE`), calcular el
  hash con `openssl dgst -sha384 -binary <fichero> | openssl base64 -A` y
  cambiar en `base_bootstrap.html` la ruta y el `integrity` (`sha384-<hash>`). Después
  borrar la carpeta de la versión anterior. El test de SRI saca la ruta de
  `base_bootstrap.html`, así que falla si el hash no coincide con el fichero.

---

## Tests y CI

- **Unitarios e integración** (`tests/`): pytest con SQLite en memoria; el CI
  exige un 95 % de cobertura de ramas. Incluyen comprobaciones de
  accesibilidad del HTML, recuento de consultas (N+1) y migraciones.
- **End-to-end** (`tests/e2e/`): Playwright en Chromium con la app real y
  CSRF activado; fallan si hay errores de JavaScript o de CSP.
  Un módulo por área (`test_navegacion`, `test_catalogo`, `test_solicitud` y
  `test_admin`), con lo común en `conftest.py`; cada cambio toca solo el de su
  área y localiza por rol, etiqueta o texto, no por clases de Bootstrap.
- **GitHub Actions**: tests, `ruff`, `pip-audit`, e2e, migraciones y seed
  contra PostgreSQL 15 y construcción de la imagen Docker.
