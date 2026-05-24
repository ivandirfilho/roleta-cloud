# S4-BAK — Backup PG com WAL-G + Backblaze B2

**Status: 100% — operacional em prod desde 2026-05-24.**

WAL-G v3.0.5 instalado no container `roleta-pg` (PG 15.18), `archive_command` ativo,
basebackup diário 02:00 UTC com retenção 7 fulls + lifecycle 30d no bucket.

---

## Estado atual em prod (Debian 187.45.181.75) — validado 2026-05-24

| Item | Valor / Path | Status |
|---|---|---|
| Application Key (escopo bucket) | `/root/secrets/b2_walg_app_key` | `-rw------- root:root` ✅ |
| WAL-G env (no host) | `/etc/wal-g/env` | `chown <pg_uid>:<pg_gid>` `chmod 600` ✅ |
| WAL-G binário (host) | `/root/roleta-cloud/wal-g/wal-g` v3.0.5 | ✅ |
| WAL-G binário (no container) | bind `/usr/local/bin/wal-g` | ✅ via compose |
| WAL-G env (no container) | bind `/etc/wal-g` (ro) | ✅ via compose |
| b2 CLI (host) | `/usr/local/bin/b2` v4.7.0 | ✅ |
| Bucket B2 | `roletacloubucket` (us-east-005) | private + SSE-B2 + lifecycle 30d ✅ |
| `archive_mode` | `on` | ✅ |
| `archive_command` | `. /etc/wal-g/env && /usr/local/bin/wal-g wal-push %p` | ✅ |
| `archive_timeout` | `5min` | ✅ |
| Primeiro basebackup | `base_000000010000000000000002` (~3.8 MB brotli) | ✅ |
| Continuidade WAL | 5 segmentos arquivados sem gaps, status OK | ✅ |
| Smoke restore | 33 MB recuperados, PG_VERSION=15 + base/global/pg_xact OK | ✅ |
| Cron diário | `/etc/cron.d/walg-backup` 02:00 UTC | ✅ |
| Script daily | `scripts/walg-backup-daily.sh` | ✅ |
| Log | `/var/log/wal-g/backup.log` | ✅ |

---

## Por que B2

- Storage barato (~US$ 0.005/GB/mês); egress free p/ Bandwidth Alliance.
- API S3-compatible → WAL-G via `WALG_S3_PREFIX`.
- **Atenção:** B2 S3 API **NÃO aceita Master Application Keys**. Sempre criar uma
  application key dedicada com escopo no bucket. A master fica reservada para o
  `b2 CLI` administrativo.

---

## Reprovisionar do zero (one-shot)

Premissa: bucket B2 existe + você tem keyID (25 chars) + applicationKey + endpoint.

```bash
ssh root@187.45.181.75
cd /root/roleta-cloud

# 1. Baixa wal-g binário (idempotente)
mkdir -p wal-g
[ -f wal-g/wal-g ] || (
  cd /tmp \
    && wget -q https://github.com/wal-g/wal-g/releases/download/v3.0.5/wal-g-pg-ubuntu-22.04-amd64.tar.gz -O walg.tgz \
    && tar xzf walg.tgz \
    && mv wal-g-pg-ubuntu-22.04-amd64 /root/roleta-cloud/wal-g/wal-g \
    && chmod +x /root/roleta-cloud/wal-g/wal-g
)

# 2. Cria /etc/wal-g/env (chmod 600, chown postgres do container)
mkdir -p /etc/wal-g
chmod 755 /etc/wal-g  # postgres precisa atravessar o dir
cat > /etc/wal-g/env <<EOF
export AWS_ACCESS_KEY_ID=<keyID-25chars>
export AWS_SECRET_ACCESS_KEY=<applicationKey>
export WALG_S3_PREFIX=s3://roletacloubucket
export AWS_ENDPOINT=https://s3.us-east-005.backblazeb2.com
export AWS_S3_FORCE_PATH_STYLE=true
export AWS_REGION=us-east-005
export WALG_COMPRESSION_METHOD=brotli
export PGHOST=/var/run/postgresql
export PGUSER=roleta
export PGDATABASE=roleta
EOF
PG_UID=$(docker exec roleta-pg id -u postgres)
PG_GID=$(docker exec roleta-pg id -g postgres)
chown ${PG_UID}:${PG_GID} /etc/wal-g/env
chmod 600 /etc/wal-g/env

# 3. Recreate PG com binds + archive flags
#    (docker-compose.pg.yml já tem os mounts e archive_mode/command/timeout)
docker compose -f docker-compose.pg.yml --env-file .env.pg up -d postgres

# 4. Smoke: valida wal-g auth e primeiro basebackup
docker exec -u postgres roleta-pg bash -c \
  'set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g backup-list'
docker exec -u postgres roleta-pg bash -c \
  'set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g backup-push /var/lib/postgresql/data'

# 5. Instala cron
bash scripts/install-walg-cron.sh
```

---

## Operação diária

### Listar basebackups
```bash
docker exec -u postgres roleta-pg bash -c \
  'set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g backup-list'
```

### Listar WAL segments (gaps?)
```bash
docker exec -u postgres roleta-pg bash -c \
  'set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g wal-show'
```
Coluna `STATUS = OK` confirma 0 gaps. Se aparecer `LOST_SEGMENTS`, **alarmar**.

### Forçar basebackup manual
```bash
/root/roleta-cloud/scripts/walg-backup-daily.sh
tail -n 30 /var/log/wal-g/backup.log
```

### Disk usage no B2
```bash
b2 ls --recursive b2://roletacloubucket | awk '{s+=$3} END {printf "%.2f MB\n", s/1024/1024}'
```

---

## Restore / DR

### Smoke restore (não destrutivo, dir temporário)
```bash
mkdir -p /tmp/walg-restore-test
docker run --rm \
  -v /tmp/walg-restore-test:/restore \
  -v /etc/wal-g:/etc/wal-g:ro \
  -v /root/roleta-cloud/wal-g/wal-g:/usr/local/bin/wal-g:ro \
  --entrypoint /bin/bash roleta/postgres-stack:pg15-age15 \
  -c 'set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g backup-fetch /restore LATEST'

# Validações esperadas:
[ "$(cat /tmp/walg-restore-test/PG_VERSION)" = "15" ] && echo "PG_VERSION OK"
ls /tmp/walg-restore-test/{base,global,pg_xact} >/dev/null && echo "dirs OK"
rm -rf /tmp/walg-restore-test
```

### Restore DESTRUTIVO em prod (PITR)
> 🛑 **WARNING:** apaga `pgdata` atual. Só rodar em janela de manutenção.

```bash
# 1. Stop app + PG
docker compose -f docker-compose.yml stop roleta-cloud roleta-cdc-worker
docker compose -f docker-compose.pg.yml stop postgres

# 2. Snapshot do estado atual (safety net)
docker run --rm -v roleta_pgdata_prod:/data -v /root:/backup alpine \
  tar czf /backup/pgdata-pre-restore-$(date +%s).tgz -C /data .

# 3. Limpa pgdata
docker run --rm -v roleta_pgdata_prod:/data alpine sh -c 'rm -rf /data/*'

# 4. Restore latest (ou nome específico no lugar de LATEST)
PG_UID=$(docker exec roleta-pg id -u postgres 2>/dev/null || echo 999)
PG_GID=$(docker exec roleta-pg id -g postgres 2>/dev/null || echo 999)
docker run --rm \
  -v roleta_pgdata_prod:/var/lib/postgresql/data \
  -v /etc/wal-g:/etc/wal-g:ro \
  -v /root/roleta-cloud/wal-g/wal-g:/usr/local/bin/wal-g:ro \
  --user ${PG_UID}:${PG_GID} \
  --entrypoint /bin/bash roleta/postgres-stack:pg15-age15 \
  -c 'set -a; . /etc/wal-g/env; set +a; /usr/local/bin/wal-g backup-fetch /var/lib/postgresql/data LATEST'

# 5. Marca recovery e habilita restore_command
docker run --rm -v roleta_pgdata_prod:/data alpine sh -c \
  'touch /data/recovery.signal && \
   echo "restore_command = '\''. /etc/wal-g/env && /usr/local/bin/wal-g wal-fetch %f %p'\''" \
     >> /data/postgresql.auto.conf'

# 6. Start
docker compose -f docker-compose.pg.yml up -d postgres
docker logs -f roleta-pg  # acompanhar replay
```

**RTO esperado** (bucket us-east-005 → HostDime BR): ~10 min para basebackup ~50MB
+ ~1 min por dia de WAL a replicar.

---

## Alarmes mínimos (TODO em Sx-OBS)

| Métrica | Condição | Severidade |
|---|---|---|
| `pg_archive_failed_count` | > 0 nos últimos 5 min | CRITICAL |
| último basebackup | > 26h sem rodar | HIGH |
| `wal-show STATUS` | != OK (LOST_SEGMENTS) | CRITICAL |
| B2 bucket size | > 10 GB | LOW (revisar retention) |

Queries Prometheus / Loki estão no runbook `grafana-cloud.md`.

---

## Custo estimado mensal

| Item | B2 |
|---|---|
| 10 GB storage (7 basebackups + 30d WAL) | US$ 0.05 |
| 50 GB egress validação mensal | US$ 0.50 |
| API calls (Class B/C) | US$ 0.10 |
| **Total** | **< US$ 1/mês** |

---

## Decisões arquiteturais

1. **Application key escopada ao bucket**, não Master Key (compatibilidade S3 API +
   blast radius).
2. **Binário wal-g via bind volume** em vez de rebuild da imagem PG: deploy mais rápido,
   upgrade WAL-G sem rebuild. Trade-off: dependência do host — documentar no runbook DR.
3. **`set -a; . env; set +a`** em toda invocação. Apenas `. env` faz source sem
   exportar para o processo child; sem isso, `wal-g` recebe ambiente vazio e dá
   `Failed to find any configured storage`.
4. **`archive_timeout=300` (5 min)** equilibra RPO baixo com I/O extra no B2.
5. **Retention FULL 7** + lifecycle B2 30d: 2 camadas (controle aplicativo + bucket).
6. **`/etc/wal-g` dir com perm 755** (não 700) porque `postgres` user precisa
   atravessar o diretório para ler o arquivo `env` (mesmo que o arquivo seja 600).
