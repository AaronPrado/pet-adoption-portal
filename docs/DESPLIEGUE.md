# Despliegue

Guía para publicar el portal en cualquier plataforma que ejecute contenedores
Docker (o, sin Docker, cualquier PaaS compatible con `Procfile`).

## 1. Requisitos

- PostgreSQL 15 o superior.
- Para subir fotos, un bucket de S3 con lectura pública o un volumen
  persistente (ver «Fotos» en el punto 6). Sin ninguno de los dos, las fotos
  se indican con URLs de imágenes externas.
- Redis si se ejecuta más de un worker o más de una instancia (ver punto 4).

## 2. Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `SECRET_KEY` | Sí | Sesiones y CSRF. Mínimo 32 bytes. |
| `JWT_SECRET_KEY` | Sí | Firma de los tokens de la API. Mínimo 32 bytes. |
| `DATABASE_URL` | Sí | `postgresql://usuario:clave@host:5432/bd` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Para login con Google | Añade `https://<tu-dominio>/auth/google/callback` como URI de redirección en Google Cloud Console. |
| `FOTOS_BACKEND` | Para subir fotos | `s3` o `local`. Sin definir (o vacía), no hay subida y el formulario solo admite URLs `https://`. |
| `FOTOS_DIR` | Con `FOTOS_BACKEND=local` | Ruta de un volumen persistente. La app no arranca en producción con `local` sin ella. |
| `FOTOS_MAX_PIXELES` | No | Píxeles máximos de una foto subida (por defecto 40 000 000). Limita la memoria de cada subida: ver «Memoria por worker» en el punto 6. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_S3_REGION` | Con `FOTOS_BACKEND=s3` | Usuario IAM con `PutObject` y `DeleteObject` sobre `mascotas/*`. Sin `AWS_S3_BUCKET`, la subida se oculta. |
| `AWS_S3_ENDPOINT_URL` | No | Servicio compatible con S3 (MinIO, Cloudflare R2...). Las URLs de las fotos quedan como `<endpoint>/<bucket>/mascotas/<clave>`, así que el bucket debe ser legible por esa ruta. |
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

### Migraciones de datos

La migración `0002` (ADR-0004) cambia el estado de mascotas y solicitudes con
`UPDATE` que no bloquean filas. Aplícala sin revisiones de solicitudes en
curso: en una ventana de mantenimiento o con la app parada. Su downgrade es
parcial: no reabre las solicitudes que rechazó.

La migración `0003` (P-31) normaliza `mascotas.especie` («perro» → «Perro»)
con el mismo criterio que el modelo. Solo toca esa columna y es idempotente,
así que se puede aplicar con la app en marcha. Su downgrade no hace nada: es
irreversible, porque no guarda cómo estaba escrita cada especie, pero inocuo,
porque la versión anterior acepta las especies normalizadas.

Si una especie quedaría vacía (solo espacios o invisibles) o con más de 50
caracteres, la migración no la cambia y deja un aviso `WARNING` en su salida
con el valor y los id de las mascotas. **Corrige esas mascotas a mano** (en el
panel o con un `UPDATE`) después de migrar: si no, al editarlas el modelo
rechazaría la especie y no se podrían guardar.

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
- **Fotos.** La mayoría de los PaaS tienen un **disco efímero**: lo que se
  escribe en el contenedor (incluido `instance/fotos`) se borra en cada
  despliegue o reinicio. Usa `FOTOS_BACKEND=s3` o, con `FOTOS_BACKEND=local`,
  monta un volumen persistente y apunta `FOTOS_DIR` a él (por eso producción
  exige `FOTOS_DIR`). Con Docker: `-v fotos:/datos/fotos -e FOTOS_DIR=/datos/fotos`.
  Solo el proceso de la app debe poder escribir en `FOTOS_DIR` (propietario el
  usuario sin privilegios de la imagen, sin escritura para otros). Incluye ese
  directorio en las copias de seguridad.
- **Tres objetos por foto.** Cada foto subida se guarda como tres variantes
  WebP (400, 800 y 1200 px de ancho), así que el número de archivos u
  objetos del bucket es el triple que el de fotos. Tenlo en cuenta en los
  límites de objetos o de peticiones del proveedor y en el tamaño del
  volumen; al ser WebP recodificado, las tres juntas suelen ocupar menos que
  el original.
- **Memoria por worker.** Cada foto subida se decodifica entera en memoria
  para reprocesarla. Con el límite por defecto (`FOTOS_MAX_PIXELES`, 40 MP),
  el pico medido por subida es de unos 210 MB por encima del consumo base
  del worker con un PNG RGB y de unos 340 MB con un PNG con transparencia;
  un JPEG pesa mucho menos porque se decodifica ya reducido. El worker parte
  de unos 100 MB. Calcula unos 450 MB por worker que pueda estar procesando
  una subida a la vez, o baja `FOTOS_MAX_PIXELES` si la máquina va justa
  (la memoria es proporcional: unos 8,5 bytes por píxel en el peor caso).
- **Backend explícito.** Las variables `AWS_*` no activan nada por sí solas:
  sin `FOTOS_BACKEND=s3`, la subida de fotos queda desactivada y el formulario
  solo admite URLs.
- **Cambiar de `local` a `s3`.** Las fotos ya guardadas (`/fotos/<clave>`) no
  se migran al bucket ni se borran: se siguen sirviendo mientras exista su
  directorio y la app no las borrará al editar o eliminar la mascota. Cópialas
  y actualiza `foto_url` a mano si quieres retirarlas.

## 7. Revertir una versión

1. Vuelve a desplegar la imagen anterior.
2. Si la versión nueva incluía migraciones incompatibles con la anterior,
   revierte primero el esquema: `flask --app run db downgrade <revisión>`.
   Para evitarlo, haz los cambios de esquema en dos pasos (añadir columna y
   desplegar; dejar de usar la antigua y eliminarla en un despliegue
   posterior).
