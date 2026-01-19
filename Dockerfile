# Roleta Cloud - Dockerfile
FROM python:3.11-slim

# Labels
LABEL maintainer="Roleta Cloud"
LABEL version="1.0.0"

# Criar usuário não-root
RUN useradd -m -s /bin/bash appuser

# Diretório de trabalho
WORKDIR /app

# Copiar requirements primeiro (cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY --chown=appuser:appuser . .

# Variáveis de ambiente padrão
ENV WS_HOST=0.0.0.0
ENV WS_PORT=8765
ENV SSL_ENABLED=false
ENV AUTH_ENABLED=false

# Expor porta
EXPOSE 8765

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.connect(('localhost', 8765)); s.close()" || exit 1

# Rodar como usuário não-root
USER appuser

# Comando
CMD ["python", "main.py"]
