# Fuentes autoalojadas

Se sirven desde aquí para no depender de terceros (ADR-0002). Solo subconjunto
latino, en WOFF2; los `@font-face` están en `app/static/css/marca.css`.

| Archivo | Familia | Origen |
|---|---|---|
| `atkinson-hyperlegible-latin-400-normal.woff2` | Atkinson Hyperlegible 400 | `@fontsource/atkinson-hyperlegible@5.3.0` |
| `atkinson-hyperlegible-latin-700-normal.woff2` | Atkinson Hyperlegible 700 | `@fontsource/atkinson-hyperlegible@5.3.0` |
| `fraunces-latin-wght-normal.woff2` | Fraunces variable, eje `wght` 100-900 | `@fontsource-variable/fraunces@5.3.0` |

Descargadas de `https://cdn.jsdelivr.net/npm/<paquete>@5.3.0/files/<archivo>`.

Licencia: SIL Open Font License 1.1 (OFL), en `LICENSE-atkinson-hyperlegible.txt`
y `LICENSE-fraunces.txt`, copiadas del `LICENSE` de cada paquete. La OFL permite
usarlas, incrustarlas y redistribuirlas con la aplicación; no permite venderlas
sueltas.
