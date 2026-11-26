# One image: build the React app, then serve it and the API from Django.

# ---- 1. Build the React app
FROM node:24-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
# Cache mount + long retries, so a slow or flaky network doesn't start from zero.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund --fetch-retries=6 --fetch-timeout=600000
COPY frontend/ ./
RUN npm run build

# ---- 2. Django API + built React app (served by WhiteNoise)
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FRONTEND_DIST=/srv/frontend/dist \
    PORT=8000
WORKDIR /srv/backend

COPY backend/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 10 --timeout 120 -r requirements.txt

# Runtime code (tests, virtualenv and caches are excluded by .dockerignore).
COPY backend/manage.py ./
COPY backend/config/ ./config/
COPY backend/trips/ ./trips/
COPY --from=web /web/dist /srv/frontend/dist

# Run unprivileged.
RUN mkdir -p staticfiles && useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/api/health', timeout=4)"

# Without DJANGO_SECRET_KEY a random one is generated at start-up (the app keeps no
# sessions or signed data). `exec` lets gunicorn receive stop signals directly.
CMD ["sh", "-c", "export DJANGO_SECRET_KEY=\"${DJANGO_SECRET_KEY:-$(python -c 'import secrets; print(secrets.token_urlsafe(50))')}\"; exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-3} --threads 4 --timeout 120 --worker-tmp-dir /dev/shm --no-control-socket --access-logfile -"]
