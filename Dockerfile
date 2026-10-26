FROM python:3.13-slim
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Layer 1: third-party dependencies. It is rebuilt only when pyproject.toml
# changes, because it uses a stub package and an empty README.
COPY pyproject.toml ./
RUN mkdir -p src/chemstock \
    && touch src/chemstock/__init__.py README.md \
    && pip install --no-cache-dir "setuptools>=68" \
    && pip install --no-cache-dir --no-build-isolation .

# Layer 2: the real application code. Fast: nothing is downloaded.
COPY README.md ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps --no-build-isolation --force-reinstall .

COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "chemstock.main:app", "--host", "0.0.0.0", "--port", "8000"]
