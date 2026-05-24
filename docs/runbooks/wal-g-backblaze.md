# S4-BAK — Backup PG com WAL-G + Backblaze B2

**Status: 60% — application key armazenada e .env esqueletizado no Debian.
Aguarda do usuario: keyID + bucket name + endpoint.**

## Estado atual em prod (Debian 187.45.181.75)

| Item | Valor / Path | Permissao |
|---|---|---|
| Application Key (secret) | `/root/secrets/b2_application_key` | `-rw------- root:root` |
| WAL-G env esqueleto | `/etc/wal-g/env` | `-rw------- root:root` |
| Test helper | `/usr/local/bin/test-b2.sh` | `-rwxr-xr-x` |
| b2 CLI | `/usr/local/bin/b2` v4.7.0 | system |
| Placeholders pendentes | 3x `TODO_PREENCHER_*` em `/etc/wal-g/env` | — |

**Para destrancar:** preencher os 3 placeholders e rodar `test-b2.sh`.

## Por que B2

- Mais barato que S3 (~$0.005/GB/mes).
- Compativel com S3 API => WAL-G funciona com `WALG_S3_PREFIX`.
- Egress gratis para Cloudflare/Bandwidth Alliance.

## Pre-requisitos (acao do usuario — pendente)

1. Criar conta em https://www.backblaze.com/b2/ — ✅ (chave fornecida)
2. Criar bucket `roleta-cloud-pg-backup` (private, encryption SSE-B2).
   - Pode ser criado pelo script `test-b2.sh` automaticamente.
3. Coletar do painel B2 (https://secure.backblaze.com/app_keys.htm):
   - **keyID** — string ~12-25 chars ao lado da app key. Para Master Key e o Account ID.
   - **endpoint** — string `s3.us-XXX-NNN.backblazeb2.com` mostrada apos criar bucket.

## Ativacao (apos coletar os 3 dados)

```bash
ssh root@187.45.181.75
sudo sed -i 's|TODO_PREENCHER_KEYID|<keyID>|' /etc/wal-g/env
sudo sed -i 's|TODO_PREENCHER_BUCKET|roleta-cloud-pg-backup|' /etc/wal-g/env
sudo sed -i 's|TODO_PREENCHER_ENDPOINT|s3.us-west-004.backblazeb2.com|' /etc/wal-g/env
sudo /usr/local/bin/test-b2.sh
```

Saida esperada: 4 etapas OK + upload de smoke-test/{hostname}-{ts}.txt.

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
