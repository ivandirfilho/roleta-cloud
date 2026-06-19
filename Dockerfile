FROM python:3.12-slim

LABEL maintainer="Roleta Cloud Team"
LABEL version="4.4.1"

WORKDIR /app

# Dependências de sistema (VF-0: sqlite3 CLI + jq + strace para debug em produção)
# + libs de runtime do opencv (dep do rapidocr-onnxruntime / vision OCR): libgl1,
#   libglib2.0-0 (core) + libsm6/libxext6/libxrender1 (defensivo). Se faltar, o OCR
#   apenas degrada (is_available=False) sem derrubar o server.
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl sqlite3 jq strace \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && \
    rm -rf /var/lib/apt/lists/*

# Instalar dependências Python primeiro (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fonte
COPY . .

# Criar diretório de dados
RUN mkdir -p /app/data

# Volume para persistência do banco SQLite
VOLUME ["/app/data"]

# Porta do WebSocket
EXPOSE 8765

# Health check (VF-4): usa endpoint HTTP /health no porto interno 8766
# em vez de TCP connect (que polui logs com handshake errors).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8766/health || exit 1

# Variáveis de ambiente padrão
ENV WS_HOST=0.0.0.0
ENV WS_PORT=8765
ENV SSL_ENABLED=false
ENV AUTH_ENABLED=false
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
