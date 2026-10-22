# syntax=docker/dockerfile:1.7
# PRM: FastAPI + workers. Same image for every service; the command selects the role.

ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=America/Sao_Paulo
# tzdata for America/Sao_Paulo; fonts-dejavu as system fallback (the generator ships its own DejaVu).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

FROM base AS deps
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && /opt/venv/bin/pip check

FROM base AS runtime
ARG APP_UID=1000
ARG APP_GID=1000
ENV PATH=/opt/venv/bin:$PATH
RUN groupadd --gid ${APP_GID} prm && useradd --uid ${APP_UID} --gid prm --create-home --shell /usr/sbin/nologin prm
COPY --from=deps /opt/venv /opt/venv
WORKDIR /app
COPY --chown=prm:prm . .
# Data directories exist with the right owner so named volumes inherit it on first use.
RUN mkdir -p data/store_publish data/datasheet_batches data/integrations data/meetings data/products \
        data/imports data/exports data/backups data/analysis data/tools /mnt/prm-fotos \
    && chown -R prm:prm data /mnt/prm-fotos \
    && chmod +x docker/entrypoint.sh
USER prm
EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
