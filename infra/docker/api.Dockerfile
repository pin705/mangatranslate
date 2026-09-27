# Build from the repo root: docker build -f infra/docker/api.Dockerfile -t mangatranslate-api .
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN useradd --system --uid 10001 --home /srv app
WORKDIR /srv/api
COPY services/api/pyproject.toml ./
RUN pip install uv && uv pip install --system -r pyproject.toml
COPY services/api/alembic.ini ./
COPY services/api/migrations ./migrations
COPY services/api/mtapi ./mtapi
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# Migrations run as a separate one-shot step (`alembic upgrade head`) before rolling out new API containers.
CMD ["sh", "-c", "exec uvicorn mtapi.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-2} --no-server-header"]
