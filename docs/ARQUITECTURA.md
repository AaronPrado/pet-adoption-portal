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
│ + aprobar(admin_id, comentario) -> None             │
│ + rechazar(admin_id, comentario) -> None            │
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
│ + marcar_en_proceso() -> None                       │
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
- `UNIQUE (usuario_id, mascota_id)`: un usuario solo puede solicitar una vez
  cada mascota.
- Las solicitudes se borran en cascada (`ON DELETE CASCADE`) con su usuario o
  su mascota.
- `cuestionario_json` es JSONB en PostgreSQL.

### Migraciones

El esquema se define en `app/models.py` y se aplica con migraciones de
Alembic (Flask-Migrate) en `migrations/`. La app no crea tablas al arrancar:

```bash
flask --app run db upgrade                       # aplicar migraciones
flask --app run db migrate -m "descripción"      # generar una nueva tras cambiar los modelos
```

---

## Conceptos POO

### 1. Encapsulación
- **Atributos privados:** `Usuario.password_hash` no se accede directamente
- **Métodos públicos:** `set_password()` y `check_password()` controlan el acceso
- **Validación:** Los métodos validan datos antes de modificar atributos

### 2. Abstracción
- **Métodos de alto nivel:** `aprobar()`, `rechazar()`, `marcar_adoptado()`
- **Separación de responsabilidades:** Cada clase tiene una función clara

### 3. Polimorfismo
- **Comportamiento según rol:** `Usuario.is_admin()` devuelve distinto valor
- **Métodos sobrescritos:** `__repr__()` personalizado en cada clase

### 4. Herencia
- **UserMixin:** `Usuario` hereda de `UserMixin` (Flask-Login) y sobrescribe
  `is_active` para que las cuentas desactivadas no puedan iniciar sesión
- **Configuración:** `DevelopmentConfig`, `TestingConfig` y `ProductionConfig`
  heredan de `Config` y redefinen `init_app()`
- **Templates Jinja2:** `base.html` es extendido por otras plantillas

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
│                        # cabeceras de seguridad, /health y errores
├── cli.py               # Comando flask crear-admin
├── models.py            # Modelos SQLAlchemy (Usuario, Mascota, Solicitud)
├── decorators.py        # @admin_required
├── s3.py                # Subida (validada con Pillow) y borrado de fotos en S3
│
├── routes/              # Blueprints
│   ├── auth.py          # Registro, login, logout, OAuth Google
│   ├── mascotas.py      # Catálogo, detalle y CRUD del panel admin
│   ├── solicitudes.py   # Crear, consultar y revisar solicitudes
│   └── api/             # API REST (Flask-RESTX)
│       ├── __init__.py  # Blueprint, Swagger y formato común de errores
│       ├── auth.py      # Login JWT y decorador @jwt_required
│       ├── mascotas.py  # Listado paginado y detalle (público)
│       └── solicitudes.py # Crear y consultar solicitudes (JWT)
│
├── templates/           # Plantillas Jinja2 (heredan de base.html)
│   ├── base.html        # Navegación, avisos, salto al contenido
│   ├── index.html
│   ├── macros/
│   │   └── paginacion.html
│   ├── auth/            # login.html, registro.html
│   ├── mascotas/        # catalogo.html, detalle.html
│   │   └── admin/       # lista.html, form.html
│   └── solicitudes/     # nueva.html, mis_solicitudes.html, detalle.html
│       └── admin/       # lista.html, revisar.html
│
└── static/
    ├── css/styles.css
    └── js/app.js        # Confirmación de borrado (sin JavaScript inline)

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

---

## Integración AWS S3

Las imágenes de mascotas se almacenan en AWS S3:

- **`app/s3.py`**: `upload_to_s3()` y `delete_from_s3()`
- **Validación**: extensión permitida (png, jpg, jpeg, gif, webp), tamaño
  máximo de 5 MB y contenido comprobado con Pillow. El `Content-Type` se
  deduce del contenido, no del que envía el navegador.
- **Nombres únicos**: `mascotas/<uuid>.<ext>`
- **Limpieza**: al editar o eliminar una mascota se borra su foto anterior,
  solo si es un objeto de `mascotas/` de nuestro bucket.
- Las URLs de foto introducidas a mano tienen que ser `https://`.

---

## API REST

API RESTful con autenticación JWT y documentación Swagger automática.

### Endpoints

| Método | Endpoint | Protegido | Descripción |
|--------|----------|-----------|-------------|
| POST | `/api/auth/login` | No | Login, devuelve JWT (máximo 5 intentos por minuto) |
| GET | `/api/mascotas/` | No | Mascotas disponibles, paginadas y filtrables |
| GET | `/api/mascotas/<id>` | No | Detalle de mascota |
| POST | `/api/solicitudes/` | JWT | Crear solicitud (201 con cabecera `Location`) |
| GET | `/api/solicitudes/mias` | JWT | Mis solicitudes |
| GET | `/api/solicitudes/<id>` | JWT | Una solicitud propia (404 si es de otro usuario) |

### Paginación y filtros

`GET /api/mascotas/` acepta `page` y `per_page` (20 por defecto, máximo 100)
y los filtros `especie`, `raza`, `tamano`, `edad_aprox`, `edad_min` y
`edad_max`. El cuerpo es una lista; el total va en la cabecera
`X-Total-Count` y los enlaces a otras páginas en `Link` (RFC 8288).

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
| Formularios | Token CSRF (Flask-WTF) en todos los POST; logout por POST |
| Sesión | Cookies `HttpOnly` y `SameSite=Lax`; `Secure` en producción |
| Login y registro | Login: 5 intentos por minuto por IP; registro: 10 por hora por IP (Flask-Limiter). Contraseñas de 8+ caracteres con hash scrypt |
| Google OAuth | Solo emails verificados por Google; las cuentas desactivadas no entran |
| Cuentas desactivadas | Pierden sesiones abiertas y tokens JWT |
| Redirecciones | `next` solo admite rutas locales |
| Navegador | CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`; sin JavaScript inline; SRI en Bootstrap |
| Errores | Mensajes genéricos al usuario; detalle solo en el log |
| Dependencias | `pip-audit` en cada push |

---

## Tests y CI

- **Unitarios e integración** (`tests/`): pytest con SQLite en memoria; el CI
  exige un 95 % de cobertura de ramas. Incluyen comprobaciones de
  accesibilidad del HTML, recuento de consultas (N+1) y migraciones.
- **End-to-end** (`tests/e2e/`): Playwright en Chromium con la app real y
  CSRF activado; fallan si hay errores de JavaScript o de CSP.
- **GitHub Actions**: tests, `ruff`, `pip-audit`, e2e, migraciones y seed
  contra PostgreSQL 15 y construcción de la imagen Docker.
