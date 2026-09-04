# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copied first so dependency layers cache across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY seed_admin.py .

# The sandbox subprocess inherits this user. Running as non-root is one of the
# controls SECURITY.md depends on: it closes gap 3 (an escape would otherwise
# inherit the API's read access to .env and every user's uploads).
RUN useradd --create-home --uid 10001 sandbox && chown -R sandbox:sandbox /app
USER sandbox

EXPOSE 8000

# Render injects $PORT; the default keeps `docker run -p 8000:8000` working.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
