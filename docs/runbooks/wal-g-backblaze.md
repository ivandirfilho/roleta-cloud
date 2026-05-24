# S4-BAK — Backup PG com WAL-G + Backblaze B2

**Status: doc-only. Aguarda credenciais B2 do usuario.**

## Por que B2

- Mais barato que S3 (~$0.005/GB/mes).
- Compativel com S3 API => WAL-G funciona com `WALG_S3_PREFIX`.
- Egress gratis para Cloudflare/Bandwidth Alliance.

## Pre-requisitos (acao do usuario)

1. Criar conta em https://www.backblaze.com/b2/
2. Criar bucket `roleta-cloud-pg-backup` (private, encryption-at-rest on).
3. Gerar Application Key restrita ao bucket:
   - keyId
   - applicationKey
   - endpoint (`s3.us-west-XXX.backblazeb2.com`)

## Instalacao no Debian

```bash
# 1. Baixar WAL-G binario
cd /opt
sudo wget https://github.com/wal-g/wal-g/releases/latest/download/wal-g-pg-ubuntu-20.04-amd64.tar.gz
sudo tar xzf wal-g-pg-*.tar.gz
sudo mv wal-g-pg-ubuntu-20.04-amd64 /usr/local/bin/wal-g
sudo chmod +x /usr/local/bin/wal-g

# 2. Configurar env (substituir <X>)
sudo tee /etc/wal-g/env <<EOF
WALG_S3_PREFIX=s3://roleta-cloud-pg-backup
AWS_ACCESS_KEY_ID=<keyId>
AWS_SECRET_ACCESS_KEY=<applicationKey>
AWS_ENDPOINT=https://<endpoint>
AWS_S3_FORCE_PATH_STYLE=true
WALG_COMPRESSION_METHOD=brotli
PGHOST=/var/run/postgresql
PGUSER=postgres
EOF
sudo chmod 600 /etc/wal-g/env

# 3. Configurar postgresql.conf
sudo -u postgres psql -c "ALTER SYSTEM SET archive_mode = on;"
sudo -u postgres psql -c "ALTER SYSTEM SET archive_command = '. /etc/wal-g/env && /usr/local/bin/wal-g wal-push %p';"
sudo -u postgres psql -c "ALTER SYSTEM SET archive_timeout = '60s';"
sudo systemctl restart postgresql

# 4. Primeiro base backup
sudo bash -c '. /etc/wal-g/env && wal-g backup-push /var/lib/postgresql/15/main'

# 5. Cron diario
echo "0 3 * * * root . /etc/wal-g/env && wal-g backup-push /var/lib/postgresql/15/main" | sudo tee /etc/cron.d/walg-backup
```

## Restore (DR)

```bash
sudo systemctl stop postgresql
sudo -u postgres rm -rf /var/lib/postgresql/15/main/*
sudo -u postgres bash -c '. /etc/wal-g/env && wal-g backup-fetch /var/lib/postgresql/15/main LATEST'
sudo -u postgres touch /var/lib/postgresql/15/main/recovery.signal
sudo systemctl start postgresql
```

## Validacao mensal

- Restore em VM secundaria.
- Rodar `pg_dump | wc -l` e comparar contagem com prod.
- Documentar RTO atingido.

## Custo estimado

| Item              | Custo/mes (B2)        |
|-------------------|------------------------|
| 10 GB storage     | $0.05                  |
| 50 GB WAL/mes     | $0.25                  |
| Download mensal   | $0.10 (1GB validacao) |
| **Total**         | **<$1/mes**            |
