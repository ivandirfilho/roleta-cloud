# CDC worker image — S5 do plano_implentacao_pos_sessao_24_05.md.
# Imagem minima: python:3.12-slim + psycopg2-binary + workers/cdc_worker.py.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --quiet --no-cache-dir \
    "psycopg2-binary>=2.9,<3.0"

COPY workers/ /app/workers/

RUN useradd --no-create-home --uid 65532 worker
USER worker

CMD ["python", "-m", "workers.cdc_worker"]
