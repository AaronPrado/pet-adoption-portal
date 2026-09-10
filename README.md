# 🐾 Portal de Adopción de Mascotas

[![Tests](https://github.com/AaronPrado/pet-adoption-portal/actions/workflows/tests.yml/badge.svg)](https://github.com/AaronPrado/pet-adoption-portal/actions/workflows/tests.yml)

Los refugios de animales gestionan las adopciones de forma manual, lo que genera
ineficiencias y dificulta el seguimiento de las solicitudes. Este proyecto
digitaliza el proceso completo en una aplicación web con Flask: catálogo público,
solicitudes con seguimiento de estado, panel de administración, control de acceso
por roles y API REST documentada.

![Portal de Adopción](docs/index.png)

## Funcionalidades

### Usuarios
- Registro e inicio de sesión, con opción de Google (OAuth 2.0)
- Autenticación segura con hash de contraseñas
- Control de acceso por roles (administrador / adoptante)
- Historial de solicitudes

![Login](docs/login.png)

### Mascotas
- Catálogo público y vista detallada
- CRUD completo desde el panel de administración
- Subida de imágenes a AWS S3 o URL externa
- Cambio automático de estado según el proceso de adopción

![Catálogo](docs/catalogo.png)

### Solicitudes
- Formulario con cuestionario de evaluación
- Gestión de estados (pendiente, aceptada, rechazada) y comentarios del administrador

![Solicitud](docs/solicitud.png)

### API REST
- Endpoints públicos para consultar mascotas
- Autenticación JWT para endpoints protegidos
- Documentación interactiva con Swagger UI (`/api/docs`)

![API](docs/api.png)

## Stack

| Capa            | Tecnología                                                                 |
| --------------- | -------------------------------------------------------------------------- |
| Backend         | Python 3.12, Flask 3.0, Flask-SQLAlchemy, Flask-Login, Flask-RESTX, Jinja2 |
| Autenticación   | Authlib (Google OAuth 2.0), PyJWT                                          |
| Base de datos   | PostgreSQL 15                                                              |
| Almacenamiento  | AWS S3 (boto3)                                                             |
| Frontend        | HTML5, CSS3, Bootstrap 5                                                   |
| Infraestructura | Docker y Docker Compose, Gunicorn, GitHub Actions                          |

## Instalación

Requisitos: Python 3.12, Docker y Docker Compose.

```bash
git clone https://github.com/AaronPrado/pet-adoption-portal.git
cd pet-adoption-portal
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
python run.py
```

Disponible en <http://localhost:5000>.

### Variables de entorno

Crea un `.env` en la raíz (ver `.env.example`):

```
GOOGLE_CLIENT_ID=tu_client_id
GOOGLE_CLIENT_SECRET=tu_client_secret
AWS_ACCESS_KEY_ID=tu_access_key
AWS_SECRET_ACCESS_KEY=tu_secret_key
AWS_S3_BUCKET=nombre_bucket
AWS_S3_REGION=eu-west-1
JWT_SECRET_KEY=clave_secreta_para_tokens
```

**Google OAuth:** proyecto en [Google Cloud Console](https://console.cloud.google.com/)
con OAuth 2.0 y `http://localhost:5000/auth/google/callback` como URI de redirección.

**AWS S3:** bucket con acceso público de lectura y usuario IAM con permisos
`PutObject`, `GetObject` y `DeleteObject`.

## Tests

```bash
python -m pytest
python -m pytest --cov=app --cov-report=html
```

Se ejecutan automáticamente en GitHub Actions en cada push.

## Estructura

```
app/
├── models.py
├── decorators.py
├── s3.py
├── routes/api/
├── templates/
└── static/
docs/          scripts_bd/    tests/
config.py      run.py         docker-compose.yml
```

## Contexto

Desarrollado como proyecto del módulo de Programación Orientada a Objetos del
Curso de Especialización Superior en Desarrollo de Aplicaciones en Python
(IES Muralla Romana, Lugo).

## Autor

Aarón Prado Darriba — [LinkedIn](https://linkedin.com/in/aaron-prado-darriba)

## Licencia

MIT