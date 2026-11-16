# 🐾 Portal de Adopción de Mascotas

[![Tests](https://github.com/AaronPrado/pet-adoption-portal/actions/workflows/tests.yml/badge.svg)](https://github.com/AaronPrado/pet-adoption-portal/actions/workflows/tests.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Cobertura 99 %](https://img.shields.io/badge/cobertura%20de%20ramas-99%25-brightgreen)
[![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green)](LICENSE)

Los refugios de animales gestionan las adopciones de forma manual, lo que genera
ineficiencias y dificulta el seguimiento de las solicitudes. Este proyecto
digitaliza el proceso completo en una aplicación web con Flask: catálogo público,
solicitudes con seguimiento de estado, panel de administración, control de acceso
por roles y API REST documentada.

![Portal de Adopción](docs/index.png)

## Contenido

- [Funcionalidades](#funcionalidades)
- [Stack](#stack)
- [Puesta en marcha](#puesta-en-marcha)
- [API REST](#api-rest-1)
- [Seguridad](#seguridad)
- [Tests y calidad](#tests-y-calidad)
- [Despliegue](#despliegue)
- [Estructura](#estructura)

## Funcionalidades

### Usuarios
- Registro e inicio de sesión, también con Google (OAuth 2.0)
- Roles de administrador y adoptante
- Historial de solicitudes con su estado

![Login](docs/login.png)

### Mascotas
- Catálogo público con filtros por especie, tamaño, sexo y edad, paginado
- Vista detallada de cada mascota
- Alta, edición y baja desde el panel de administración
- Fotos subidas a AWS S3 o enlazadas por URL
- El estado cambia solo según el proceso de adopción (disponible → adoptado)

![Catálogo](docs/catalogo.png)

### Solicitudes
- Cuestionario de evaluación del adoptante
- Revisión por el administrador: aprobar (con confirmación y un mensaje
  opcional) o rechazar con un motivo obligatorio, que ve el solicitante
- Varias personas pueden solicitar la misma mascota a la vez; al aprobar una
  solicitud se rechazan automáticamente las demás
- Una solicitud por usuario y mascota, y una sola adopción por mascota

![Solicitud](docs/solicitud.png)

### API REST
- Consulta pública de mascotas, con paginación y filtros
- Solicitudes protegidas con JWT
- Documentación interactiva con Swagger UI en `/api/docs` (solo en desarrollo)

![API](docs/api.png)

## Stack

| Capa            | Tecnología                                                                 |
| --------------- | -------------------------------------------------------------------------- |
| Backend         | Python 3.12, Flask 3.1, Flask-SQLAlchemy, Flask-Login, Flask-RESTX, Jinja2  |
| Base de datos   | PostgreSQL 15, SQLAlchemy 2.1, psycopg 3, migraciones con Flask-Migrate     |
| Autenticación   | Authlib (Google OAuth 2.0), PyJWT, Flask-WTF (CSRF), Flask-Limiter          |
| Almacenamiento  | AWS S3 (boto3), Pillow para validar imágenes                               |
| Frontend        | HTML5, CSS3, Bootstrap 5                                                   |
| Calidad         | pytest, Playwright, ruff, pip-audit, GitHub Actions                        |
| Infraestructura | Docker, Docker Compose, Gunicorn                                           |

## Puesta en marcha

Requisitos: Python 3.12, Docker y Docker Compose.

```bash
git clone https://github.com/AaronPrado/pet-adoption-portal.git
cd pet-adoption-portal
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
docker compose up -d          # PostgreSQL y Adminer
flask --app run db upgrade    # crea las tablas
python run.py
```

La app queda en <http://localhost:5000> y Adminer, para ver la base de datos,
en <http://localhost:8080>.

### Datos de prueba

```bash
docker compose exec -T postgres psql -U admin -d adopciones_db < scripts_bd/02_seed.sql
```

Crea mascotas, solicitudes y usuarios con la contraseña `password123`, entre
ellos el administrador `admin@refugio.com`. Es solo para desarrollo local: en
cualquier otro entorno crea el administrador con

```bash
flask --app run crear-admin
```

### Variables de entorno

`.env.example` trae todas las variables comentadas. Para desarrollar basta con
`FLASK_ENV=development`; el resto solo hace falta para algunas funciones:

| Variables | Para qué |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Login con Google. En [Google Cloud Console](https://console.cloud.google.com/), añade `http://localhost:5000/auth/google/callback` como URI de redirección. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_S3_REGION` | Subir fotos. Bucket con lectura pública y usuario IAM con `PutObject` y `DeleteObject` sobre `mascotas/*`. Sin ellas, las fotos se indican por URL. |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Obligatorias en producción (mínimo 32 bytes). En desarrollo hay valores por defecto. |

### Cambios en la base de datos

El esquema se define en `app/models.py`. Tras modificarlo, genera y aplica la
migración:

```bash
flask --app run db migrate -m "descripción del cambio"
flask --app run db upgrade
```

Si tu base de datos local se creó con el antiguo `scripts_bd/01_schema.sql`, ya
tiene el esquema de la primera migración: márcala una vez con
`flask --app run db stamp 0001`.

## API REST

| Método | Endpoint | Auth | Descripción |
|---|---|---|---|
| POST | `/api/auth/login` | — | Devuelve un JWT |
| GET | `/api/mascotas/` | — | Mascotas disponibles, paginadas y filtrables |
| GET | `/api/mascotas/<id>` | — | Detalle de una mascota |
| POST | `/api/solicitudes/` | JWT | Crea una solicitud |
| GET | `/api/solicitudes/mias` | JWT | Solicitudes del usuario |
| GET | `/api/solicitudes/<id>` | JWT | Una solicitud propia |

```bash
TOKEN=$(curl -s -X POST localhost:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "juan.perez@email.com", "password": "password123"}' | jq -r .token)

curl -i "localhost:5000/api/mascotas/?especie=Perro&edad_max=5&per_page=10"
curl localhost:5000/api/solicitudes/mias -H "Authorization: Bearer $TOKEN"
```

El total de resultados va en la cabecera `X-Total-Count` y los enlaces a otras
páginas en `Link`. Los errores siempre tienen la forma `{"error": "mensaje"}`.
Más detalles en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md#api-rest).

## Seguridad

- Protección CSRF en todos los formularios y cierre de sesión por POST
- Cookies `HttpOnly` y `SameSite`, y `Secure` en producción
- Content Security Policy y cabeceras de seguridad; sin JavaScript inline
- Límite de 5 intentos de login por minuto (web y API) y de 10 registros por hora
- Contraseñas con hash scrypt; login con Google solo con email verificado
- Desactivar una cuenta cierra sus sesiones e invalida sus tokens
- Fotos validadas por su contenido antes de subirlas a S3
- La app no arranca en producción sin secretos de al menos 32 bytes

El detalle por capas está en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md#seguridad).

## Tests y calidad

```bash
python -m pytest                                          # tests unitarios y de integración
python -m pytest --cov=app --cov-branch --cov-report=html # con informe de cobertura
ruff check .                                              # lint
```

Los tests end-to-end abren la app en Chromium con Playwright y van aparte:

```bash
python -m playwright install chromium
python -m pytest -m e2e
```

En cada push y pull request, GitHub Actions ejecuta:

| Job | Qué comprueba |
|---|---|
| `test` | Tests con un mínimo de 95 % de cobertura de ramas, ruff y pip-audit |
| `migraciones` | Migraciones, datos de prueba y downgrade contra PostgreSQL 15 |
| `imagen` | Que la imagen Docker de producción se construye |
| `e2e` | Flujos completos en Chromium (fallan si hay errores de JavaScript o de CSP) |

Los cuatro son obligatorios para fusionar en `main`.

## Despliegue

El proyecto incluye `Dockerfile` (multi-stage, usuario sin privilegios y
health check), `gunicorn.conf.py` y `Procfile`:

```bash
docker build -t pet-adoption-portal .
docker run --rm --env-file .env.produccion pet-adoption-portal flask --app run db upgrade
docker run -d --env-file .env.produccion -p 8000:8000 pet-adoption-portal
```

Las variables de producción, el proxy inverso, Redis y los pasos del primer
despliegue están en [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md).

## Estructura

```
app/
├── __init__.py        # Application Factory, extensiones y cabeceras de seguridad
├── models.py          # Usuario, Mascota, Solicitud
├── adopciones.py      # Regla de adopción (solicitudes en paralelo)
├── routes/            # Blueprints web (auth, mascotas, solicitudes)
│   └── api/           # API REST con Flask-RESTX
├── templates/         # Plantillas Jinja2
├── static/            # CSS y JavaScript
├── s3.py              # Subida y borrado de fotos
└── cli.py             # flask crear-admin
migrations/            # Migraciones de Alembic
tests/                 # pytest; tests/e2e con Playwright
docs/                  # Arquitectura, despliegue y capturas
scripts_bd/            # Datos de prueba
config.py              # Configuración por entornos
Dockerfile, gunicorn.conf.py, Procfile, docker-compose.yml
```

La arquitectura, el modelo de datos y los conceptos de POO aplicados se
explican en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## Contexto

Desarrollado como proyecto del módulo de Programación Orientada a Objetos del
Curso de Especialización Superior en Desarrollo de Aplicaciones en Python
(IES Muralla Romana, Lugo).

## Autor

Aarón Prado Darriba — [LinkedIn](https://linkedin.com/in/aaron-prado-darriba)

## Licencia

[MIT](LICENSE)
