# Imagen de producción del portal de adopción
#
#   docker build -t pet-adoption-portal .
#   docker run --env-file .env.produccion -p 8000:8000 pet-adoption-portal
#
# Ver docs/DESPLIEGUE.md

# --- Etapa 1: instalar dependencias en un entorno virtual ---
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Etapa 2: imagen final sin herramientas de compilación ---
FROM python:3.12-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PORT=8000

# Usuario sin privilegios
RUN useradd --create-home --uid 1000 app
WORKDIR /home/app/portal

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app config.py run.py gunicorn.conf.py ./

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')" || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "run:app"]
