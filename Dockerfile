FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY lector ./lector
COPY templates ./templates
COPY static ./static

RUN useradd --create-home --uid 10001 appuser


FROM base AS test

RUN pip install --no-cache-dir "pytest>=8.3,<9"
COPY tests ./tests

USER appuser
CMD ["pytest", "-q", "-p", "no:cacheprovider"]


FROM base AS runtime

RUN pip install --no-cache-dir "gunicorn>=23,<24"

ENV LECTOR_JOBS_DIR=/tmp/lector-txt-jobs \
    LECTOR_PORT=8000

RUN mkdir -p /tmp/lector-txt-jobs \
    && chown -R appuser:appuser /app /tmp/lector-txt-jobs

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "app:app"]
