FROM ghcr.io/astral-sh/uv:python3.12-bookworm

WORKDIR /app
COPY pyproject.toml .
COPY src ./src
RUN uv pip install --system .

ENV PYTHONPATH=/app/src
WORKDIR /app/src

RUN useradd --create-home --uid 1000 kgent \
    && mkdir -p /app/data \
    && chown -R kgent:kgent /app
USER kgent

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
