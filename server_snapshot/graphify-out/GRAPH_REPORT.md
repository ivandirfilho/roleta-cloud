# Graph Report - server_snapshot  (2026-06-12)

## Corpus Check
- 9 files · ~1,753 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 159 nodes · 176 edges · 14 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b1875a03`
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
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]

## God Nodes (most connected - your core abstractions)
1. `Servidor Debian xmaiajpvm (187.45.181.75)` - 15 edges
2. `Docker Engine + compose roleta-cloud_default` - 10 edges
3. `SQLite decisions.db 3.3MB (fonte primaria)` - 8 edges
4. `Docker — Containers e Infraestrutura` - 7 edges
5. `PostgreSQL (roleta-pg)` - 7 edges
6. `Aplicação Roleta Cloud — Runtime` - 7 edges
7. `container roleta-cloud (302MB, healthy, 512MB lim)` - 7 edges
8. `container roleta-prometheus v2.51.2` - 7 edges
9. `DB roleta 13MB (alembic 0006_spin_features)` - 7 edges
10. `Segurança` - 6 edges

## Surprising Connections (you probably didn't know these)
- `Servidor Debian xmaiajpvm (187.45.181.75)` ----> `roleta-deploy.timer (pull-deploy main a cada 2min)`  [EXTRACTED]
  server_snapshot/01_sistema.md → server_snapshot/03_servicos_host.md
- `Servidor Debian xmaiajpvm (187.45.181.75)` ----> `certbot.timer (renovacao diaria)`  [EXTRACTED]
  server_snapshot/01_sistema.md → server_snapshot/03_servicos_host.md
- `tools/gap_detector.py (in-container)` ----> `SQLite decisions.db 3.3MB (fonte primaria)`  [EXTRACTED]
  server_snapshot/03_servicos_host.md → server_snapshot/05_database.md
- `Servidor Debian xmaiajpvm (187.45.181.75)` ----> `nginx (host) :80/:443`  [EXTRACTED]
  server_snapshot/01_sistema.md → server_snapshot/04_nginx_tls.md
- `Servidor Debian xmaiajpvm (187.45.181.75)` ----> `sshd :22 publico (root+password LIGADOS)`  [EXTRACTED]
  server_snapshot/01_sistema.md → server_snapshot/08_seguranca.md

## Communities (14 total, 0 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.17
Nodes (17): Alertmanager webhook -> health_server, container roleta-alertmanager v0.27.0, container roleta-grafana 10.4.2, container node-exporter v1.8.2, container roleta-pg (pg15 + AGE + pgvector), container pg-exporter v0.15.0, container roleta-prometheus v2.51.2, Docker Engine + compose roleta-cloud_default (+9 more)

### Community 1 - "Community 1"
Cohesion: 0.16
Nodes (14): FIRING: RoletaDnaRealizeLagHigh (pos-downtime), RISCO: 118 pacotes atualizaveis, DOWNTIME 30/05 14:30 -> 10/06 18:40 (11 dias desligado), grafana-agent (host) remote_write, Grafana Cloud prod-sa-east-1, Servidor Debian xmaiajpvm (187.45.181.75), RISCO: sem fail2ban, RISCO: iptables INPUT policy ACCEPT (sem firewall) (+6 more)

### Community 2 - "Community 2"
Cohesion: 0.11
Nodes (20): container roleta-cloud (302MB, healthy, 512MB lim), Cert Let's Encrypt (expira 2026-07-06), certbot.timer (renovacao diaria), BUG: dealer/table/round=None em producao pos-PR#6, CRITICO: dealer='unknown' em 5352/5352 decisoes (DEAL morto), roleta.xma-ia.com (+ www), Extensao Chrome (cliente, captura spins+dealMeta), migration 0007_deal_dealer_table (nao aplicada) (+12 more)

### Community 3 - "Community 3"
Cohesion: 0.14
Nodes (13): code:block1 (NAMES                 IMAGE                                 ), code:block2 (REPOSITORY                                      TAG         ), code:block3 (VOLUME NAME                      DRIVER), code:block4 (NAME                   DRIVER), code:block5 (roleta-cloud              restart=unless-stopped  health=hea), code:block6 (NAME                  CPU %     MEM USAGE / LIMIT), Containers, Docker — Containers e Infraestrutura (+5 more)

### Community 4 - "Community 4"
Cohesion: 0.38
Nodes (7): container roleta-cdc-worker (healthy), extensao Apache AGE (cw_graph/ccw_graph VAZIOS), extensao pgvector (embeddings), DB roleta 13MB (alembic 0006_spin_features), schema ccw (spins_vectors=831, spin_features=533), schema cw (spins_vectors=816, spin_features=531), schema shared (outbox=2711, feature_flags, strategy_versions)

### Community 5 - "Community 5"
Cohesion: 0.29
Nodes (8): CI main VERMELHO desde 27/05 (cdc tests: cw.spins_vectors inexistente), server/configs/mesas/ (runtime, untracked), /usr/local/bin/roleta-deploy-pull.sh, roleta-deploy.timer (pull-deploy main a cada 2min), RISCO: models/spin_autoencoder.joblib untracked no servidor, migration 0008_decision_dna (nao aplicada), CRITICO: alembic prod=0006 < repo=0008 (deploy nao roda alembic), /root/roleta-cloud @ e7461a7 (= origin/main)

### Community 6 - "Community 6"
Cohesion: 0.14
Nodes (13): Alembic version, code:block1 (shared.outbox = 5), code:block2 (processed = 2706), code:block3 (nenhum), code:block4 (2026-06-10 18:51:09.081719+00), code:block5 (0006_spin_features), code:block6 (spins_total = tabela inexistente), Estatisticas de dominio (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.14
Nodes (13): Aplicação Roleta Cloud — Runtime, Arquivos não versionados relevantes, code:block1 (e7461a7 Merge pull request #6 from ivandirfilho/copilot/fix-), code:block2 (?? models/spin_autoencoder.joblib), code:block3 (ROLETA_PG_DSN), code:block4 (.), code:block5 ({"status": "ok", "uptime_sec": 619, "version": "4.4.0", "ts"), code:block6 (total 8) (+5 more)

### Community 8 - "Community 8"
Cohesion: 0.17
Nodes (11): code:block1 (port 22), code:block2 (0), code:block3 (fail2ban NAO instalado), code:block4 (Chain INPUT (policy ACCEPT)), code:block5 (118 pacotes atualizáveis), fail2ban, Segurança, SSHD config efetiva (itens chave) (+3 more)

### Community 9 - "Community 9"
Cohesion: 0.20
Nodes (9): code:block1 (containerd.service), code:block2 (roleta-deploy.service Wed 2026-06-10 18:51:15), code:block3 (* * * * * /usr/local/bin/roleta-gap-check.sh), code:block4 (0.0.0.0:22 "sshd"), Crontab root, Portas escutando, Services rodando, Serviços do Host (fora do Docker) (+1 more)

### Community 10 - "Community 10"
Cohesion: 0.20
Nodes (9): Alertas ativos agora, code:block1 (prometheus http://localhost:9090/metrics up), code:block2 (RoletaAdaptiveStateLost inactive), code:block3 (1 alertas), code:block4 (active), Grafana-agent (cloud remoto), Observabilidade — Prometheus / Grafana / Alertmanager, Regras de alerta carregadas (+1 more)

### Community 11 - "Community 11"
Cohesion: 0.25
Nodes (7): Certificados (certbot), code:block1 (roleta), code:block2 (server_name roleta.xma-ia.com www.roleta.xma-ia.com;), code:block3 (Certificate Name: roleta.xma-ia.com), Nginx + TLS, server_name + proxy_pass por site, Sites habilitados

### Community 12 - "Community 12"
Cohesion: 0.29
Nodes (6): Automação do host, Backups, Containers (8, todos healthy), Deltas funcionais de 12/06 (resumo), Servidor Debian 187.45.181.75 — Inventário 12/06/2026 23:20 UTC, Volumes

### Community 13 - "Community 13"
Cohesion: 0.50
Nodes (3): code:block1 (reboot   system boot  6.1.0-13-amd64   Wed Jun 10 18:40   st), Historico de boots (wtmp), Servidor Debian — Sistema

## Knowledge Gaps
- **61 isolated node(s):** `code:block1 (reboot   system boot  6.1.0-13-amd64   Wed Jun 10 18:40   st)`, `code:block1 (NAMES                 IMAGE                                 )`, `code:block2 (REPOSITORY                                      TAG         )`, `code:block3 (VOLUME NAME                      DRIVER)`, `code:block4 (NAME                   DRIVER)` (+56 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Docker Engine + compose roleta-cloud_default` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `Servidor Debian xmaiajpvm (187.45.181.75)` connect `Community 1` to `Community 0`, `Community 2`, `Community 5`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Why does `container roleta-cloud (302MB, healthy, 512MB lim)` connect `Community 2` to `Community 0`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **What connects `code:block1 (reboot   system boot  6.1.0-13-amd64   Wed Jun 10 18:40   st)`, `code:block1 (NAMES                 IMAGE                                 )`, `code:block2 (REPOSITORY                                      TAG         )` to the rest of the system?**
  _61 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.11052631578947368 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._
- **Should `Community 6` be split into smaller, more focused modules?**
  _Cohesion score 0.14285714285714285 - nodes in this community are weakly interconnected._