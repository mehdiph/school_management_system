# ---------------------------------------------------------------------------
# Base image: matches the Python version this project was developed with
# (Python 3.12.3, confirmed via `python --version`).
# "slim" = Debian without the extra build tooling of the full image.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Don't write .pyc files (no benefit in a container that's rebuilt each time)
# and don't buffer stdout/stderr (so `docker compose logs` shows output live).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---------------------------------------------------------------------------
# System dependencies.
#
# WeasyPrint doesn't render PDFs in pure Python — it calls into Cairo and
# Pango (C libraries) through cffi. These packages provide that at runtime.
# We do NOT need a Persian font here: Vazirmatn ships inside the project
# itself (report/static/report/fonts/) and is copied in with the source.
#
# libpq5 is the PostgreSQL client library. psycopg2-binary bundles its own
# copy, but installing libpq5 explicitly avoids relying on that undocumented
# implementation detail.
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    fontconfig \
    shared-mime-info \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Package index. Defaults to PyPI; override at build time where PyPI is
# unreliable (PIP_INDEX_URL in .env, passed through by docker-compose.yml).
# Keeping it an ARG means this Dockerfile still works unchanged anywhere
# PyPI is directly reachable.
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout 60 --retries 10 -r requirements.txt

# Now copy the rest of the project.
COPY . .

# Run as a non-root user inside the container (defense in depth: if the app
# is ever compromised, it isn't running as root).
RUN useradd --create-home --uid 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Gunicorn's default port; docker-compose.yml (next phase) will map it.
EXPOSE 8000

# Use production settings unless docker-compose.yml overrides this.
ENV DJANGO_SETTINGS_MODULE=teachlog.config.settings.production

# Plain `gunicorn`, no migrate/collectstatic here — those are explicit,
# separate commands you run yourself (docker compose exec web ...), per the
# plan for this phase. We'll automate that later, once it's proven to work
# manually.
CMD ["gunicorn", "teachlog.wsgi:application", "--bind", "0.0.0.0:8000"]