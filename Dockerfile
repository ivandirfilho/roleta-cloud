FROM python:3.12-slim

LABEL maintainer="Roleta Cloud Team"
LABEL version="4.0.1"

WORKDIR /app

# Dependências de sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
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

# Health check — verifica se o processo Python está rodando
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('localhost', 8765)); s.close()" || exit 1

# Variáveis de ambiente padrão
ENV WS_HOST=0.0.0.0
ENV WS_PORT=8765
ENV SSL_ENABLED=false
ENV AUTH_ENABLED=false
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
