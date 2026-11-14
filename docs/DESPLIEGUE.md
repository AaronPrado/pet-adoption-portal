# Despliegue

Guía para publicar el portal en cualquier plataforma que ejecute contenedores
Docker (o, sin Docker, cualquier PaaS compatible con `Procfile`).

## 1. Requisitos

- PostgreSQL 15 o superior.
- Un bucket de S3 con lectura pública para las fotos (opcional: también se
  pueden indicar URLs de imágenes externas).
- Redis si se ejecuta más de un worker o más de una instancia (ver punto 4).

## 2. Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `SECRET_KEY` | Sí | Sesiones y CSRF. Mínimo 32 bytes. |
| `JWT_SECRET_KEY` | Sí | Firma de los tokens de la API. Mínimo 32 bytes. |
| `DATABASE_URL` | Sí | `postgresql://usuario:clave@host:5432/bd` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Para login con Google | Añade `https://<tu-dominio>/auth/google/callback` como URI de redirección en Google Cloud Console. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_S3_REGION` | Para subir fotos | Usuario IAM con `PutObject` y `DeleteObject` sobre `mascotas/*`. |
| `TRUSTED_PROXIES` | Detrás de un proxy | Número de proxies inversos delante de la app (normalmente `1`). |
| `RATELIMIT_STORAGE_URI` | Con varios workers | `redis://host:6379/0` |
| `WEB_CONCURRENCY` | No | Workers de gunicorn (por defecto 2 × CPU + 1). |
| `DB_CONNECT_TIMEOUT` | No | Segundos de espera al conectar con PostgreSQL (por defecto 5). |
| `JWT_EXPIRATION_HOURS` | No | Validez de los tokens de la API (por defecto 24). |

Genera las claves con:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

La app no arranca en producción si falta `SECRET_KEY`, `JWT_SECRET_KEY` o
`DATABASE_URL`, o si alguna clave tiene menos de 32 bytes.

## 3. Con Docker

```bash
docker build -t pet-adoption-portal .

# Aplicar las migraciones (en cada despliegue, antes de arrancar la nueva versión)
docker run --rm --env-file .env.produccion pet-adoption-portal flask --app run db upgrade

# Arrancar
docker run -d --env-file .env.produccion -p 8000:8000 pet-adoption-portal
```

La imagen se ejecuta con un usuario sin privilegios, escucha en el puerto
`PORT` (8000 por defecto) e incluye un `HEALTHCHECK` contra `/health`.

## 4. Con un PaaS (Procfile)

El `Procfile` define:

- `release`: aplica las migraciones antes de cada despliegue.
- `web`: arranca gunicorn con `gunicorn.conf.py`.

## 5. Primer despliegue

1. Crea la base de datos y aplica las migraciones (`flask --app run db upgrade`).
2. Crea el administrador: `flask --app run crear-admin`. No cargues
   `scripts_bd/02_seed.sql`: sus usuarios tienen una contraseña conocida.
3. Comprueba `https://<tu-dominio>/health`: debe devolver `{"status": "ok"}`.

## 6. Comprobaciones de producción

- **Proxy inverso.** Casi todas las plataformas ponen un balanceador delante.
  Sin `TRUSTED_PROXIES`, la app ve la IP del balanceador: el límite de
  intentos de login bloquearía a todos los usuarios a la vez y las
  redirecciones se generarían con `http://`. No lo pongas a un valor mayor
  que el número real de proxies: un cliente podría falsear su IP.
- **Varios workers.** El límite de intentos se guarda en memoria por proceso;
  con varios workers o instancias, usa Redis (`RATELIMIT_STORAGE_URI`).
- **HTTPS.** Las cookies de sesión se marcan `Secure` en producción: la app
  tiene que servirse por HTTPS.
- **Health check.** `/health` devuelve 503 si la base de datos no responde en
  `DB_CONNECT_TIMEOUT` segundos. Úsalo como comprobación de disponibilidad del
  balanceador u orquestador.
- **Swagger.** `/api/docs` está desactivado en producción.

## 7. Revertir una versión

1. Vuelve a desplegar la imagen anterior.
2. Si la versión nueva incluía migraciones incompatibles con la anterior,
   revierte primero el esquema: `flask --app run db downgrade <revisión>`.
   Para evitarlo, haz los cambios de esquema en dos pasos (añadir columna y
   desplegar; dejar de usar la antigua y eliminarla en un despliegue
   posterior).
