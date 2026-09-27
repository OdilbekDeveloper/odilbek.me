# syntax=docker/dockerfile:1

# Two stages. The builder holds uv, the Tailwind binary and every build-time step; the runtime
# image receives only the virtualenv, the application and its collected static files.

FROM python:3.13-slim AS builder

# Pinned, so the resolver cannot change under an unchanged commit.
RUN pip install --no-cache-dir uv==0.11.4

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, from the two files that decide them, so editing code keeps this layer cached.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY manage.py ./
COPY config/ config/
COPY apps/ apps/
COPY templates/ templates/
COPY static/ static/
COPY assets/ assets/
COPY locale/ locale/

# Build the CSS and collect static files. Settings must import to do either, so this one step gets
# throwaway values; they are not part of the image's environment and nothing connects to a database.
# The Tailwind binary is deleted afterwards and never reaches the runtime image.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=image-build-only \
    DJANGO_ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    sh -c ".venv/bin/python manage.py tailwind build \
        && .venv/bin/python manage.py collectstatic --noinput" \
    && rm -rf .django_tailwind_cli


FROM python:3.13-slim

# WeasyPrint's system libraries, needed from Phase 8 (resume PDFs). Installed now so the image's
# shape is settled early. The fonts are the self-hosted families chosen in Phase 3.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

WORKDIR /app

# Root-owned and read-only to the process: the app user can run the code but not change it.
# Nothing is written to disk at runtime; media goes to object storage.
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

USER app

EXPOSE 8000

CMD ["gunicorn", "--config", "config/gunicorn.conf.py", "config.wsgi"]
