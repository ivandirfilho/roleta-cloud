# Próximos Passos — 10/06/2026

> Avaliação de dev senior da estrutura atual (repo local + servidor Debian de produção),
> baseada em: grafo do código (`graphify-out/`, 2326 nodes @ `e7461a7`), **grafo novo do
> servidor** (`server_snapshot/graphify-out/`, 66 nodes / 92 edges / 7 communities),
> inspeção SSH profunda de `187.45.181.75` e CI do GitHub.

---

## 1. Contexto operacional (o que mudou desde 27/05)

| Fato | Evidência |
|---|---|
| Servidor ficou **desligado de 30/05 14:30 até 10/06 18:40** (11 dias) | `last -x reboot`, journal do boot anterior |
| Produção == `origin/main` (`e7461a7`, merge PR #6) | `git log` no servidor; pull-deploy a cada 2 min funcionando |
| Apenas **129 decisões novas desde 27/05** (total 5347 no SQLite) | `decisions.db` |
| 8 containers healthy, RAM 1.4/6.9 GB, disco 10% | `docker ps`, `free`, `df` |
| Alerta `RoletaDnaRealizeLagHigh` firing = consequência do downtime, não bug | Prometheus `/alerts` |

O sistema **funciona**: spin chegou às 18:48, decisão 5340 criada em 375ms, dual-write
SQLite→outbox→PG ok, outbox `processed=2706 / failed=0`.

---

## 2. Snapshot da arquitetura de produção (grafo do servidor)

```
Chrome ext v3.1.1 ──wss──> nginx:443 (roleta.xma-ia.com, cert ok até 06/07)
                              └─> roleta-cloud :8765/:8766 (v4.4.0)
                                    ├─ state.json + SQLite decisions.db (3.3MB) ← FONTE PRIMÁRIA
                                    └─ OutboxPublisher ─> PG shared.outbox ─> cdc-worker
                                                            └─> cw/ccw spins_vectors + spin_features
Observabilidade: Prometheus(14 rules) → Alertmanager → webhook; Grafana local + Grafana Cloud
Deploy: systemd timer 2min (git pull + compose up)  |  Gap-check: cron 1min → textfile → node-exporter
Backup: wal-g cron */30min → ⚠ MORTO desde 25/05
```

Artefatos novos para análises futuras:
- `server_snapshot/01..08_*.md` — inventário versionável do servidor (sem secrets)
- `server_snapshot/graphify-out/graph.{json,html}` + `GRAPH_REPORT.md` — grafo navegável

---

## 3. O que CORRIGIR (e porquê) — prioridade P0, esta semana

### P0.1 — Backup do PG morto + SQLite sem backup nenhum 🔴
- **Evidência:** `/var/log/wal-g/backup.log` parado em **25/05 04:30**; cron `*/30` existe
  mas não produz linha nova; `backups/pg/` vazio. E o **SQLite (`decisions.db`), que é a
  fonte primária do produto, não tem backup algum** — só o PG (réplica) tinha.
- **Porquê é o item nº 1:** todo o resto é recuperável (código está no git, infra é
  reproduzível); os 5347 registros de decisões/sessões **não são**. Risco de perda total.
- **Ação:** investigar por que o wal-g parou (provável env/credencial do storage pós-algo);
  validar um `wal-g backup-push` manual + **um restore de teste**; adicionar dump diário do
  `decisions.db` (`sqlite3 .backup` + rotação 7d) no mesmo cron; alerta Prometheus
  `RoletaBackupStale` (textfile com timestamp do último backup — padrão já existente no gap-check).

### P0.2 — Migrations não aplicadas em produção (alembic 0006 < repo 0008) 🔴
- **Evidência:** `shared.alembic_version = 0006_spin_features`; repo tem
  `0007_deal_dealer_table` e `0008_decision_dna`; `roleta-deploy-pull.sh` **não roda alembic**.
- **Porquê:** o pull-deploy atualiza código mas não schema → todo código novo que depende de
  0007/0008 roda contra schema velho. É drift silencioso — exatamente a classe de erro do
  B-10 (falha engolida). As colunas DEAL no PG e a tabela `decision_dna` PG não existem em prod.
- **Ação:** rodar `docker compose run --rm roleta-cloud alembic upgrade head` (procedimento
  já validado em memória de deploy); adicionar step `alembic upgrade head` no
  `roleta-deploy-pull.sh` **antes** do `compose up`, com healthcheck de rollback.

### P0.3 — CI vermelho em `main` desde 27/05 🔴
- **Evidência:** runs `26490411079` e `26488571806` failed; causa:
  `psycopg2.errors.UndefinedTable: relation "cw.spins_vectors" does not exist` em
  `tests/test_cdc_worker.py`. O bootstrap do `ci.yml` cria schemas/extensão mas **nunca roda
  `alembic upgrade head`**. Local: 347 passed (testes cdc são skipped sem PG).
- **Porquê:** CI vermelho permanente = cegueira; qualquer regressão nova fica invisível.
  Mesma causa-raiz do P0.2 (migrations esquecidas), confirmando o padrão.
- **Ação:** adicionar `alembic upgrade head` após o bootstrap de schemas no `ci.yml`
  (1 linha; `ROLETA_PG_DSN` já está no env). Critério: matrix 3.11/12/13 verde.

### P0.4 — Segurança do host: porta aberta + brute-force ativo 🔴
- **Evidência:** `sshd -T`: `permitrootlogin yes` + `passwordauthentication yes`; **sem
  fail2ban**; iptables `INPUT policy ACCEPT` (sem firewall); `node-exporter *:9100` exposto
  ao mundo; journal de 30/05 mostra brute-force contínuo de IPs estrangeiros; 118 pacotes
  atualizáveis; senha do PG **hardcoded em `/usr/local/bin/roleta-gap-check.sh`**.
- **Porquê:** servidor fica dias sem supervisão (vide downtime de 11 dias sem ninguém notar).
  Root+password+sem-rate-limit é a combinação que termina em mineração de cripto. A senha
  hardcoded num script root-readable vira pivô se houver qualquer leitura de arquivo.
- **Ação (≈40 min):** `PermitRootLogin prohibit-password` + `PasswordAuthentication no`
  (chave já funciona — sessão atual usa BatchMode); instalar fail2ban; ufw allow 22/80/443 +
  deny default; bind node-exporter em 127.0.0.1 (o grafana-agent scrape é local);
  mover a senha para `/etc/roleta/gap-check.env` (chmod 600) + `EnvironmentFile`/source e
  **rotacionar a senha do PG** depois; `apt upgrade` em janela controlada.

---

## 4. O que CORRIGIR — prioridade P1, próxima semana

### P1.1 — DEAL capture morto em produção (dealer = 'unknown' em 5352/5352) 🟠
- **Evidência:** `SELECT dealer, count(*)` → `('unknown', 5352)`; log live:
  `[DEAL] dealer=None provider='host:www.roleta.xma-ia.com' table=None round=None` —
  **mesmo após** SP-11..15, audit 27/05 e PR #6 (hydrate from frames).
- **Porquê importa:** toda a linha de valor "offset prior por dealer" (SP-15), ranking de
  dealer e análises por mesa está produzindo **zero dado** há 2 semanas. Ou se conserta a
  captura ou se admite que o funil ML avançado não tem matéria-prima.
- **Diagnóstico provável (do grafo + memória):** `table_id`/`provider` vêm na URL do iframe
  Evolution (`_detectedFrames`), mas o fallback atual reporta `host:` da página = frames da
  Evolution não estão sendo detectados, **ou a extensão não foi recarregada no Chrome do
  operador** (manifest 3.1.1 exige reload manual em `chrome://extensions`).
- **Ação:** 1) confirmar versão carregada no Chrome do operador; 2) logar `_detectedFrames`
  completo num spin real; 3) se iframe Evolution não aparece, revisar `all_frames`/permissões
  de host no manifest; 4) só então retomar SP-15 (offset prior) com dado real.

### P1.2 — `models/spin_autoencoder.joblib` untracked no servidor 🟠
- **Evidência:** `git status` no servidor: `?? models/spin_autoencoder.joblib` (1.3KB, 25/05).
- **Porquê:** mesmo padrão do hazard documentado de `server/configs/mesas/` — qualquer
  `git clean`/stash no deploy destrói artefato de runtime. Modelo de 1.3KB treinado com
  pouquíssimo dado também levanta a questão: está sendo usado? Vale a pena re-treinar?
- **Ação:** mover para o volume `roleta-data` (ou versionar com hash no repo, é minúsculo);
  adicionar `models/*.joblib` ao `.gitignore` + nota no runbook de deploy.

### P1.3 — Schemas AGE vazios (cw_graph/ccw_graph = 0 rows) 🟡
- **Evidência:** `ag_label_vertex/edge = 0` em ambos; extensão AGE carregada na imagem
  custom `roleta/postgres-stack:pg15-age15` (1GB).
- **Porquê:** complexidade paga sem retorno — imagem custom maior, migrations mais frágeis
  (AGE quebra CI se entrar nos testes), zero queries de grafo em produção.
- **Ação (decisão de produto):** ou popular os grafos AGE com um caso de uso concreto
  (ex.: transições dealer→número para o offset prior), ou **remover AGE** e simplificar
  para `pgvector/pgvector:pg15` oficial — alinharia produção com o CI e reduziria 40% da imagem.

---

## 5. O que vale a pena IMPLEMENTAR (P2 — depois da fundação)

| # | Item | Porquê vale | Pré-requisito |
|---|---|---|---|
| 1 | **NEW-09: bisect da regressão hit-rate 47.69→43.95** (FeatureStore/Regime opt-in) | Único item do blueprint 26/05 que mexe direto no KPI do produto; estava aguardando 24h de tráfego pós-B10 — agora que o servidor voltou, agendar | 24h de tráfego novo |
| 2 | **Dealer offset prior com dado real** (retomada SP-15) | Era a aposta de maior alpha do blueprint; hoje é inerte por falta de dado | P1.1 resolvido |
| 3 | **Backup-aware boot check** (systemd unit pós-boot: valida wal-g + alembic head + extensão conectada, publica métrica `roleta_boot_sanity`) | O downtime de 11 dias passou despercebido; um "boot sanity" tornaria visível qualquer item degradado ao religar | P0.1, P0.2 |
| 4 | **`alembic upgrade` + smoke-test no deploy pull** (transformar P0.2 em pipeline permanente) | Elimina a classe inteira de drift código×schema | P0.2 |
| 5 | **Ramp de cobertura CI 50%→60%** (SP-34.1) | Barato, já existe infra; só faz sentido com CI verde | P0.3 |
| 6 | **unattended-upgrades (security-only)** | Servidor fica semanas sem login; patches críticos automáticos reduzem janela de exposição | P0.4 |

### O que explicitamente NÃO fazer agora
- **Novas features de ML/estratégia** (REGION-05+, ML-03+): o funil de dados está entupido
  (dealer=unknown, migrations faltando). Feature nova agora = mais código inerte.
- **Upgrade de imagens Grafana 10.4/Prometheus 2.51** (2 anos): funcionais, sem CVE crítico
  exposto (tudo em 127.0.0.1 atrás do nginx); custo/benefício ruim frente a P0.
- **Refactors estruturais**: a suite (347 testes) e o grafo de código mostram módulos bem
  separados (server/, state/, database/, core/); não há dívida estrutural urgente.

---

## 6. Ordem de execução sugerida

```
Dia 1:  P0.4 (hardening SSH+fw, 40min) → P0.1 (wal-g + dump SQLite + restore-teste)
Dia 2:  P0.2 (alembic prod + deploy script) → P0.3 (CI verde)
Dia 3+: P1.1 (DEAL live debug com operador) → P1.2 (joblib) → decisão P1.3 (AGE: usar ou remover)
Semana 2: P2.1 (bisect NEW-09 com tráfego acumulado) → P2.2..6
```

Racional da ordem: **proteger o dado → destravar o schema → recuperar visibilidade (CI) →
reabrir o funil de dados (DEAL) → só então otimizar o modelo.** Cada item de P2 fica
estritamente atrás do seu pré-requisito de P0/P1 — implementar antes disso é construir
sobre areia.

---

## 7. Riscos aceitos conscientemente
- Imagens de observabilidade defasadas (2 anos) — mitigado por bind exclusivo em localhost.
- `passwordauthentication` continuará até validar acesso por chave de TODOS os dispositivos
  do operador (não trancar a porta com a chave dentro).
- AGE permanece instalado até a decisão de produto do P1.3.

## Apêndice — evidências coletadas em 10/06
- Grafo do servidor: `server_snapshot/graphify-out/graph.html` (66 nodes, 92 edges, 7 communities)
- Inventário: `server_snapshot/0[1-8]_*.md`
- CI failing: runs `26490411079` (main, 27/05) — `UndefinedTable cw.spins_vectors`
- Suite local: `347 passed, 9 skipped, 1 xfailed` (10/06)
- SQLite: decisions=5347, sessions=150, decision_dna=791, gale_windows=961, window_plays=3889;
  calibration fill pós-27/05 = 89/129 (69%)
- PG: cw.spins_vectors=816, ccw=831, spin_features=531/533, outbox processed=2706/failed=0
- wal-g: último `DONE` em 2026-05-25T04:30Z
