# Imágenes de la portada

`hero-640.webp` (640×377) y `hero-1280.webp` (1280×753): un perro y un gato
tumbados sobre la hierba. Son las dos variantes del `<img>` principal de
`index.html` (`srcset` 640w/1280w).

**Origen:** foto de Unsplash (images.unsplash.com/photo-1450778869180-41d0601e046e),
licencia Unsplash: uso libre sin atribución obligatoria.

## Regenerar las variantes

A partir del original (relación 1280:753), con Pillow. Las variantes no llevan
metadatos: Pillow no copia EXIF ni perfiles ICC salvo que se le pida.

```python
from PIL import Image

original = Image.open("original.jpg").convert("RGB")
for ancho in (640, 1280):
    alto = round(original.height * ancho / original.width)
    original.resize((ancho, alto), Image.LANCZOS).save(
        f"hero-{ancho}.webp", "WEBP", quality=80, method=6
    )
```

Si cambias las medidas, actualiza `width`/`height` del `<img>` en
`app/templates/index.html` (los de la variante más grande).
