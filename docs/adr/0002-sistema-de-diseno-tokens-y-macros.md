# ADR-0002: Sistema de diseño propio: tokens CSS, macros Jinja e identidad neutra personalizable

**Fecha**: 2026-11-15
**Estado**: aceptada
**Decisores**: propietario del proyecto, tras un comité de decisiones con revisión de arquitectura

## Contexto

La auditoría encontró dos colores de texto base, el azul de Bootstrap mezclado
con la paleta propia, botones de 6 alturas, 5 variantes de tarjeta de mascota,
10 estilos en línea y ningún componente reutilizable salvo la paginación.
Ningún formulario asocia los errores a sus campos. Con ADR-0001 desaparece
Bootstrap como sistema. La identidad tiene que lucir en un portfolio y, a la
vez, ser lo bastante neutra para que cualquier protectora vea que encaja.

## Decisión

Se define un sistema pequeño y propio con tres piezas:

- **Tokens** en custom properties de CSS (color, tipografía, espaciado, radios,
  sombras y foco), organizados con `@layer reset, tokens, base, componentes,
  utilidades`.
- **Componentes como macros Jinja** en `app/templates/macros/`: `campo` (con
  `label`, valor enviado, `aria-invalid`, `aria-describedby` y
  `autocomplete`), `grupo_opciones` (`fieldset` y `legend`), `boton`,
  `tarjeta_mascota`, `badge_estado`, `cabecera_pagina`, `tabla`, `estado_vacio`
  y `avisos`.
- **Identidad neutra y personalizable**: la marca (nombre del refugio, logo
  SVG y color de acento) se define en un solo sitio, los tokens de marca y la
  configuración de la app, para adaptarla a cada protectora sin tocar
  plantillas.

La tipografía va autoalojada en `app/static/fonts/`. El protagonismo visual es
de las fotos de los animales. No hay modo oscuro en esta iteración.

## Alternativas consideradas

### Evolucionar el actual sobre Bootstrap (dirección A)
- **A favor**: es lo más barato.
- **En contra**: depende de Bootstrap, descartado en ADR-0001.
- **Por qué no**: es incompatible con ADR-0001.

### Identidad marcada («ficha de acogida», dirección B completa)
- **A favor**: es lo más memorable para el portfolio.
- **En contra**: una paleta y una tipografía muy personales le restan encaje
  para otras protectoras.
- **Por qué no**: el propietario quiere una base relativamente genérica.
  Conviene quedarse con lo que funciona para cualquier refugio: el animal como
  protagonista y una tipografía para los nombres.

### Sistema editorial con modo oscuro (dirección C)
- **A favor**: identidad propia y tematizable.
- **En contra**: 3-5 semanas, riesgo alto, y el modo oscuro duplica el
  contraste que hay que verificar.
- **Por qué no**: las cinco voces consultadas lo descartan para esta
  iteración.

## Consecuencias

### Positivas
- Un solo sitio para cada decisión visual: P-14, P-15, P-17, P-19, P-20, P-21 y
  P-22 se resuelven por construcción.
- La macro `campo` es el mecanismo común para P-02 (conservar valores), P-12,
  P-16 y P-36.
- Personalizar el portal para otra protectora es un cambio de configuración.

### Negativas
- Hay que escribir y mantener unas 900 líneas de CSS y 9 macros.
- Las plantillas existentes se reescriben para usar las macros.

### Riesgos
- **Que las macros y el CSS se desincronicen.** Mitigación: tests en
  `tests/test_accesibilidad.py` que rendericen cada macro y comprueben sus
  atributos.
- **Contraste insuficiente de un color de acento personalizado.** Mitigación:
  un test que calcule el contraste de los tokens de marca frente a los fondos
  (4,5:1 en texto y 3:1 en bordes de controles).
- **Coste de LCP de las fuentes web.** Mitigación: un máximo de dos familias en
  WOFF2 con subconjunto latino y `font-display: swap`.
