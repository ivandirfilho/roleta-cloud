# Graph Report - server_snapshot  (2026-06-10)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 66 nodes · 92 edges · 7 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e7461a76`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]

## God Nodes (most connected - your core abstractions)
1. `Servidor Debian xmaiajpvm (187.45.181.75)` - 15 edges
2. `Docker Engine + compose roleta-cloud_default` - 10 edges
3. `SQLite decisions.db 3.3MB (fonte primaria)` - 8 edges
4. `container roleta-cloud (302MB, healthy, 512MB lim)` - 7 edges
5. `container roleta-prometheus v2.51.2` - 7 edges
6. `DB roleta 13MB (alembic 0006_spin_features)` - 7 edges
7. `container roleta-pg (pg15 + AGE + pgvector)` - 6 edges
8. `CRITICO: alembic prod=0006 < repo=0008 (deploy nao roda alembic)` - 5 edges
9. `nginx (host) :80/:443` - 4 edges
10. `/usr/local/bin/roleta-deploy-pull.sh` - 4 edges

## Surprising Connections (you probably didn't know these)
- `Servidor Debian xmaiajpvm (187.45.181.75)` ----> `roleta-deploy.timer (pull-deploy main a cada 2min)`  [EXTRACTED]
  server_snapshot/01_sistema.md → server_snapshot/03_servicos_host.md
- `Servidor Debian xmaiajpvm (187.45.181.75)` ----> `certbot.timer (renovacao diaria)`  [EXTRACTED]
  server_snapshot/01_sistema.md → server_snapshot/03_servicos_host.md
- `tools/gap_detector.py (in-container)` ----> `SQLite decisions.db 3.3MB (fonte primaria)`  [EXTRACTED]
  server_snapshot/03_servicos_host.md → server_snapshot/05_database.md
- `RISCO: POSTGRES_PASSWORD hardcoded em roleta-gap-check.sh` ----> `container roleta-pg (pg15 + AGE + pgvector)`  [EXTRACTED]
  server_snapshot/08_seguranca.md → server_snapshot/02_docker.md
- `container roleta-cloud (302MB, healthy, 512MB lim)` ----> `OutboxPublisher (dual-write SQLite->PG)`  [EXTRACTED]
  server_snapshot/02_docker.md → server_snapshot/06_app_runtime.md

## Communities (7 total, 0 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.21
Nodes (14): FIRING: RoletaDnaRealizeLagHigh (pos-downtime), Alertmanager webhook -> health_server, container roleta-alertmanager v0.27.0, container roleta-grafana 10.4.2, container node-exporter v1.8.2, container roleta-pg (pg15 + AGE + pgvector), container pg-exporter v0.15.0, container roleta-prometheus v2.51.2 (+6 more)

### Community 1 - "Community 1"
Cohesion: 0.18
Nodes (13): RISCO: 118 pacotes atualizaveis, DOWNTIME 30/05 14:30 -> 10/06 18:40 (11 dias desligado), grafana-agent (host) remote_write, Grafana Cloud prod-sa-east-1, Servidor Debian xmaiajpvm (187.45.181.75), RISCO: sem fail2ban, RISCO: iptables INPUT policy ACCEPT (sem firewall), Debian 12 bookworm / kernel 6.1.0-13 (+5 more)

### Community 2 - "Community 2"
Cohesion: 0.22
Nodes (10): Cert Let's Encrypt (expira 2026-07-06), certbot.timer (renovacao diaria), BUG: dealer/table/round=None em producao pos-PR#6, CRITICO: dealer='unknown' em 5352/5352 decisoes (DEAL morto), roleta.xma-ia.com (+ www), Extensao Chrome (cliente, captura spins+dealMeta), migration 0007_deal_dealer_table (nao aplicada), nginx (host) :80/:443 (+2 more)

### Community 3 - "Community 3"
Cohesion: 0.22
Nodes (9): container roleta-cloud (302MB, healthy, 512MB lim), SQLite decisions.db 3.3MB (fonte primaria), CRITICO: SQLite decisions.db (fonte primaria) SEM backup, state.json (estado da roda persistido), decision_dna = 791 rows, gale_windows = 961 rows, sessions = 150 rows, window_plays = 3889 rows (+1 more)

### Community 4 - "Community 4"
Cohesion: 0.32
Nodes (8): container roleta-cdc-worker (healthy), extensao Apache AGE (cw_graph/ccw_graph VAZIOS), extensao pgvector (embeddings), OutboxPublisher (dual-write SQLite->PG), DB roleta 13MB (alembic 0006_spin_features), schema ccw (spins_vectors=831, spin_features=533), schema cw (spins_vectors=816, spin_features=531), schema shared (outbox=2711, feature_flags, strategy_versions)

### Community 5 - "Community 5"
Cohesion: 0.29
Nodes (8): CI main VERMELHO desde 27/05 (cdc tests: cw.spins_vectors inexistente), server/configs/mesas/ (runtime, untracked), /usr/local/bin/roleta-deploy-pull.sh, roleta-deploy.timer (pull-deploy main a cada 2min), RISCO: models/spin_autoencoder.joblib untracked no servidor, migration 0008_decision_dna (nao aplicada), CRITICO: alembic prod=0006 < repo=0008 (deploy nao roda alembic), /root/roleta-cloud @ e7461a7 (= origin/main)

### Community 6 - "Community 6"
Cohesion: 0.50
Nodes (4): cron 1min roleta-gap-check.sh (flock + textfile), tools/gap_detector.py (in-container), RISCO: POSTGRES_PASSWORD hardcoded em roleta-gap-check.sh, node_exporter textfile collector (/var/lib/node_exporter)

## Knowledge Gaps
- **21 isolated node(s):** `Debian 12 bookworm / kernel 6.1.0-13`, `VM QEMU 4 vCPU / 7GB RAM / 79GB disco (10% usado)`, `Grafana Cloud prod-sa-east-1`, `RISCO: iptables INPUT policy ACCEPT (sem firewall)`, `RISCO: node-exporter *:9100 exposto publico` (+16 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `container roleta-pg (pg15 + AGE + pgvector)` connect `Community 0` to `Community 4`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `DB roleta 13MB (alembic 0006_spin_features)` connect `Community 4` to `Community 5`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `Docker Engine + compose roleta-cloud_default` connect `Community 0` to `Community 3`, `Community 4`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **What connects `Debian 12 bookworm / kernel 6.1.0-13`, `VM QEMU 4 vCPU / 7GB RAM / 79GB disco (10% usado)`, `Grafana Cloud prod-sa-east-1` to the rest of the system?**
  _21 weakly-connected nodes found - possible documentation gaps or missing edges._