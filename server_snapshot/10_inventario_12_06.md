# Servidor Debian 187.45.181.75 — Inventário 12/06/2026 23:20 UTC

> Atualiza o snapshot de 10/06 após o ciclo completo de 12/06 (16 commits,
> 86eda30→b1875a0). Árvore completa: `09_arvore_completa_12_06.txt` (426 arquivos).

## Containers (8, todos healthy)
| Container | Imagem | Função |
|---|---|---|
| roleta-cloud | roleta-cloud-roleta-cloud (build local) | app WS 8765 + HTTP 8766; SQLite fonte primária |
| roleta-cdc-worker | roleta/cdc-worker:latest | outbox→PG (spin_features, spin_result, **dna_feature, dna_realized** novos 12/06) |
| roleta-pg | roleta/postgres-stack:pg15-age15 | PG espelho (alembic **0008**; shared.decision_dna populada 12/06: 2051+) |
| roleta-prometheus | prom/prometheus:v2.51.2 | **16 rules** (+RoletaSessionPnlLow, +RoletaAllTimePnlDropFast 12/06) |
| roleta-grafana | grafana/grafana:10.4.2 | dashboards: overview, dna-regions, shadow-grid, **roleta-profit (novo 12/06)** |
| roleta-alertmanager | prom/alertmanager:v0.27.0 | webhook → app |
| node-exporter / pg-exporter | v1.8.2 / v0.15.0 | host + PG metrics |

## Automação do host
| Mecanismo | Estado 12/06 |
|---|---|
| `roleta-deploy.timer` (2min) → `/usr/local/bin/roleta-deploy-pull.sh` | **roda `alembic upgrade head`** antes do up (novo 12/06; backup .bak-1206) |
| `/etc/cron.d/walg-backup` (*/30min, via **/bin/bash** — fix 12/06) | **VIVO** (morto 25/05→12/06; root cause: +x perdido por git reset) |
| `/etc/cron.d/roleta-backup-decisions` (03:15 UTC, novo 12/06) | dump diário SQLite + rotação 7d + textfile metric |
| `roleta-gap-check.sh` (cron 1min) | textfile p/ node-exporter |

## Backups
- `/root/backups/sqlite/decisions_*.db.gz` — **restore drill PASS 12/06** (integrity ok)
- wal-g → B2: basebackups 30/30min, `wal-verify integrity FOUND` (cadeia 32 WALs)
- `/root/backups/artifacts/spin_autoencoder.joblib` — cópia de segurança (P4.4)

## Volumes
`roleta-cloud_roleta-data` (SQLite/state), `roleta_pgdata_prod`, prometheus/grafana/alertmanager-data.

## Deltas funcionais de 12/06 (resumo)
INV-3 global (indicação sempre; vetos modulam stake) · PROFIT-LEDGER (pnl_units,
total_profit, gauges) · stop-loss −30u sem lag · reset TOTAL da estratégia no botão ·
medição por região (result_region, dist_c1/c2/c3, region_err_ema+n) · feedback pela
aposta real · DNA→PG assíncrono (fila+worker; incidente 9.6s corrigido com
keepalives/timeout/retry) · backfill histórico region/pnl (4240/4240) · CI verde
(alembic + AGE best-effort + coverage gate 70).
