# ADR-0003: Almacenamiento de fotos con backend local en desarrollo y S3 en producción

**Fecha**: 2026-11-15
**Estado**: aceptada
**Decisores**: propietario del proyecto, tras un comité de decisiones con revisión de arquitectura

## Contexto

`app/s3.py` sube las fotos a AWS S3 con boto3. No hay cuenta de AWS ni
credenciales, y subir una foto sin S3 configurado da un error 500 (P-09,
`s3.py:75-80` llamado desde `mascotas.py:201` y `:298`). El propietario quiere
usar AWS S3 en producción cuando tenga cuenta, y trabajar en local mientras
tanto. Las fotos tienen además dos problemas: se sirven sin variantes de
tamaño (P-38, P-39) y pueden llevar EXIF con la ubicación GPS de las casas de
acogida.

## Decisión

El almacenamiento de fotos pasa a ser una interfaz con dos backends elegidos
por configuración:

- **`local`**: el de desarrollo y los tests. Guarda en `instance/fotos/` y la
  app lo sirve con una ruta propia. No necesita credenciales.
- **`s3`**: el de producción, sobre el boto3 actual. Admite `endpoint_url`
  opcional, así que sirve igual para cualquier servicio compatible.

Sin backend configurado, el formulario oculta la subida y deja indicar una
URL; un fallo al subir se muestra como un error del campo, sin error 500.

Al subir, la foto se reprocesa siempre con Pillow:
- se quitan los metadatos EXIF;
- se limita el tamaño en píxeles con `Image.MAX_IMAGE_PIXELS`;
- se comprueba el tipo real del archivo;
- se generan las variantes WebP para `srcset` (400, 800 y 1200 px);
- se guardan con nombre aleatorio.

Las URLs externas `https://` siguen admitiéndose.

## Alternativas consideradas

### Solo compatible con S3 (Cloudflare R2 en producción, MinIO en local)
- **A favor**: un único camino de código y R2 tiene una capa gratuita.
- **En contra**: obliga a levantar MinIO en desarrollo, y R2 no es el
  proveedor que prefiere el propietario.
- **Por qué no**: el backend `s3` con `endpoint_url` ya deja abierta esta vía
  sin imponerla.

### Cloudinary u otro servicio de imágenes
- **A favor**: redimensiona por su cuenta.
- **En contra**: otro SDK, límites del plan gratuito y reescribir el módulo
  entero.
- **Por qué no**: más dependencia por menos control.

### Solo URLs externas
- **A favor**: cero infraestructura.
- **En contra**: enlaces que se rompen, posible rastreo y peor experiencia
  para el admin.
- **Por qué no**: se pierde una funcionalidad que una protectora necesita.

## Consecuencias

### Positivas
- Se puede desarrollar y probar sin cuenta en la nube, y pasar a AWS S3 solo
  cambiando la configuración.
- Se arregla P-09 por diseño y se preparan P-38 y P-39 con las variantes.
- Desaparece la fuga de ubicación por EXIF.

### Negativas
- Hay que mantener dos backends y sus tests, y reescribir buena parte de
  `test_s3.py`.
- Cada foto pasa a ser 3 o 4 objetos (las variantes).
- Habrá que cambiar el nombre de `app/s3.py` y de las funciones
  `upload_to_s3`/`delete_from_s3` a nombres neutros.

### Riesgos
- **Usar el backend `local` en un PaaS con disco efímero, que borra las fotos
  en cada despliegue.** Mitigación: en producción solo se acepta `local` si se
  configura una ruta de volumen persistente explícita. Además se documenta en
  `docs/DESPLIEGUE.md` y se añade un comando `flask exportar-fotos` para
  copias de seguridad.
- **Que cambien las URLs guardadas en `foto_url`.** Mitigación: se mantiene la
  columna y se distinguen las URLs externas de las claves internas, sin
  migración de esquema.
