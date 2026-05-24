# Roleta Cloud — postgres-stack
# PG15 + pgvector + Apache AGE + TimescaleDB
# Usado em DEV (Windows local) e PROD (Debian HostDime) — paridade absoluta.

FROM pgvector/pgvector:pg15

ARG AGE_VERSION=PG15/v1.5.0-rc0
ARG TSDB_VERSION=2.17.2

ENV DEBIAN_FRONTEND=noninteractive

# --- build deps + Apache AGE + TimescaleDB ----------------------------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        flex \
        bison \
        git \
        gnupg \
        lsb-release \
        postgresql-server-dev-15; \
    # Apache AGE \
    git clone --depth 1 --branch ${AGE_VERSION} https://github.com/apache/age.git /tmp/age; \
    cd /tmp/age; \
    make PG_CONFIG=/usr/lib/postgresql/15/bin/pg_config; \
    make PG_CONFIG=/usr/lib/postgresql/15/bin/pg_config install; \
    cd /; rm -rf /tmp/age; \
    # TimescaleDB Apache-2 \
    curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor -o /usr/share/keyrings/timescaledb.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/debian/ $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/timescaledb.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends timescaledb-2-postgresql-15=${TSDB_VERSION}*; \
    # cleanup \
    apt-get purge -y --auto-remove build-essential git flex bison postgresql-server-dev-15; \
    rm -rf /var/lib/apt/lists/*

# --- pré-load das libs no shared_preload_libraries via init script ---------
COPY init/ /docker-entrypoint-initdb.d/

# --- tunings padrão (sobrescritos por compose env se necessário) -----------
ENV POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale=C"

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD pg_isready -U postgres || exit 1

LABEL org.opencontainers.image.title="roleta-postgres-stack"
LABEL org.opencontainers.image.description="PG15 + pgvector + Apache AGE + TimescaleDB para Roleta Cloud"
LABEL org.opencontainers.image.source="https://github.com/ivandirfilho/roleta-cloud"
