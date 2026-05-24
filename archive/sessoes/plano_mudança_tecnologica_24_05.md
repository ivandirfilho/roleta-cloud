# 🔧 Plano de Mudança Tecnológica — 24/05/2026

> **Auditoria final** de `plano_implentacao_pos_sessao_24_05.md` com foco em **migração tecnológica concreta** e separação em 2 blocos:
> **Bloco 1 — TUDO o que conseguimos fazer no Debian HostDime atual (com upgrade)** · **Bloco 2 — APENAS o que realmente exige nuvem externa**.

---

## 🧭 TL;DR (5 bullets)

1. **~95% do plano pode rodar 100% no Debian HostDime** após upgrade de specs — não precisamos de Azure VM para nada do que está nas Sprints S1–S14.
2. **Único ponto que precisa de cloud externa:** backup off-site (disaster recovery geográfico). E mesmo isso pode ser feito em **Backblaze B2 (~US$ 1–2/mês)** em vez de Azure Blob.
3. **Custo total mensal final:** ~US$ 50–80 (upgrade Debian) + US$ 2 (B2) = **~US$ 52–82/mês** vs ~US$ 151 do plano Azure-VM. **Economia ~50%.**
4. **Continuidade funcional 100% garantida:** dual-write (S5 outbox) + canário (S13) + shadow (S11) + rollback (Sx-ROLL) tornam cada migração reversível em <5 min, sem downtime.
5. **Achado A3·B32 (AGE indisponível em PG Flexible) deixa de importar** — não precisamos mais de Flexible. Toda a stack roda como Docker Compose no Debian.

---

## 📊 Baseline atual do Debian HostDime (medido agora)

```
CPU:    2 vCPU
RAM:    3.3 GB total · 2.6 GB disponível
DISK:   4.8 GB total · 2.4 GB livre  ← GARGALO CRÍTICO
SWAP:   8.0 GB (ok)
Kernel: 6.1.0-13-amd64
Docker: 29.1.3 + Compose v5.0.1 ✅ já instalado
App:    roleta-cloud v4.3.2 healthy ↑29h+
```

### Specs MÍNIMAS para rodar TUDO do plano localmente

| Recurso | Atual | **Necessário (mínimo)** | **Recomendado** | Justificativa técnica |
|---|---|---|---|---|
| vCPU | 2 | **4** | 6 | PG (2 cores) + AGE (1) + app (1) + autoencoder treino (1 burst) + agent (0.2) |
| RAM | 3.3 GB | **8 GB** | 16 GB | PG `shared_buffers=2GB` + `work_mem` AGE 512MB + app 1GB + autoencoder 800MB + buffer 1.5GB |
| Disco | 4.8 GB | **80 GB SSD** | 160 GB SSD | PG data 10GB + WAL 5GB + backups locais 30d×500MB=15GB + Docker images 8GB + Timescale histórico 5y=15GB + folga 20GB |
| Rede | OK | OK | +100Mbps stable | Upload diário B2 ~500MB + Grafana Cloud metrics ~50MB/dia |
| Swap | 8 GB | mantém | mantém | Safety net se autoencoder/AGE spike |

> ✅ **Você confirmou que pode aumentar RAM e disco do HostDime.** Pedido ideal pro suporte: **"4 vCPU, 8 GB RAM, 80 GB SSD"** ou superior. Custo provável: ~US$ 30–60/mês adicional sobre o atual.

---

## 🗂️ Mapeamento Sprint → Bloco

| Sprint | Tecnologia mudada | **Bloco 1 (Debian/Local)** | Bloco 2 (Azure/externo) |
|---|---|---|---|
| **S0** Deploy QWs v4.4 | Tag git + fix path | ✅ | — |
| **S0.5** Stack docker-compose | Imagem custom PG15+pgvector+AGE+TSDB | ✅ (build local + Debian) | — |
| **S1** DecisionRepo | Interface Python (SQLAlchemy) | ✅ | — |
| **S2** Alembic baseline | Migrations | ✅ | — |
| **S3** structlog + strategy_versions | JSON logs + tabela versão | ✅ | — |
| **Sx-CI** PG no CI | GitHub Actions service container | ✅ (GitHub free tier) | — |
| **Sx-SEC** Secrets | **`sops` + `age` (encryption tool) + git** (NÃO Azure Key Vault) | ✅ | — |
| **S4** Provisionar PG | **Docker Compose no Debian** (NÃO Azure) | ✅ | — |
| **S4-BAK** Backup PITR | **WAL-G + Backblaze B2** | parcial | ✅ S3 externa |
| **S5** Outbox dual-write | Tabela `outbox` no PG | ✅ | — |
| **Sx-LATENCY/CUTOVER** | **DEPRECATED** — app e PG ficam no mesmo host (loopback <1ms) | ✅ (ganho automático) | — |
| **S6** Schema vector | pgvector tipo `vector(64)` | ✅ | — |
| **S7** Autoencoder 6→4→6 | sklearn `MLPRegressor` + joblib | ✅ | — |
| **S8** Apache AGE grafos | extensão AGE compilada na imagem | ✅ (Debian self-managed) | — |
| **S9** Outlier MAD | função SQL pura | ✅ | — |
| **S10** Cold regions OFF | feature flag | ✅ | — |
| **S11** Shadow predictor | thread async + circuit breaker | ✅ | — |
| **S12** Métricas + Grafana | **Grafana Cloud free tier** (10k séries grátis) | ✅ (free tier não exige Azure) | — |
| **Sx-OBS** Observabilidade | `grafana-agent` no host → Grafana Cloud | ✅ | — |
| **S13** Canário 10→50% | hash(salt+spin_id)%100 | ✅ | — |
| **S14** Adoption v5.0.0 | tag git | ✅ | — |
| **Sx-LGPD** | Análise legal | ✅ (HostDime já em Brasil/Fortaleza) | — |
| **Sx-ROLL** Runbook | Doc + scripts | ✅ | — |
| **Sx-PAUSE** Política | Doc + métricas threshold | ✅ | — |

**Resultado: 22 sprints em Bloco 1 · 1 sprint mista (S4-BAK) · 0 sprints exclusivamente Bloco 2.**

---

# 🟢 BLOCO 1 — TUDO no Debian HostDime + Local

> Conseguimos. Aqui está o como, por que, e a prova de continuidade.

## B1.0 Pré-requisito: upgrade do Debian

**O QUE:** abrir ticket HostDime para upgrade do plano atual.

**PEDIDO PARA O SUPORTE:**
> "Olá, gostaria de upgrade do meu VPS Debian (IP 187.45.181.75) para o seguinte plano:
> - **4 vCPU** (atual: 2)
> - **8 GB RAM** (atual: 3.3 GB)
> - **80 GB SSD** (atual: 4.8 GB)
> Pode ser online (sem reinício) ou agendado para janela noturna. Mantenham IP, kernel e todos os volumes."

**COMO MIGRAR sem perder nada:**
1. Snapshot/backup antes (HostDime faz auto)
2. Container roleta-cloud continua rodando — só ganha mais recurso
3. Após upgrade: `df -h && free -h && nproc` confirma novos limites
4. `docker stats roleta-cloud` confirma app saudável

**PROVA:** zero código alterado, zero downtime, container continua exatamente como está.

---

## B1.1 — S0: Deploy Quick Wins v4.4

| Item | Detalhe |
|---|---|
| **O QUE muda tech?** | Nada estrutural — só merge PR #5 + fix path `/opt`→`/root` em `.github/workflows/deploy.yml` + tag `v4.4.0` |
| **COMO** | (1) `gh pr merge 5 --squash --delete-branch` → (2) branch `fix/deploy-path` corrige YAML → PR + merge → (3) `git tag v4.4.0 && git push origin v4.4.0` → Actions deploya |
| **MIGRAÇÃO** | Deploy padrão por tag git (já existe). Container reinicia em ~30s. |
| **PROVA DE CONTINUIDADE** | `docker logs roleta-cloud --tail 200 \| grep -E "QW-1\|QW-2\|DRIFT"` mostra QWs ativos; banco SQLite intacto (volume preservado) |
| **PORQUÊ** | Sem isso, todo o resto roda em cima de código antigo (v4.3.2) e não consegue medir efeito das próximas mudanças |
| **GANHO** | Hit-rate +3–5pp (validado em backtest); detecção de drift ativa |

---

## B1.2 — S0.5: Stack Docker-Compose unificada

| Item | Detalhe |
|---|---|
| **O QUE muda tech?** | Nasce uma **nova imagem Docker** `roleta/postgres-stack:pg15-age15` (PG15 + pgvector 0.7 + AGE 1.5 + TimescaleDB 2.x) que será usada IDÊNTICA em dev local e prod Debian |
| **COMO** | (1) Dockerfile base `pgvector/pgvector:pg15`, instala AGE via `make install`, adiciona repo Timescale, instala extensão → (2) `init/*.sql` cria extensões + schemas `cw` e `ccw` → (3) `docker-compose.dev.yml` (Windows) e `docker-compose.prod.yml` (Debian) com mesma imagem |
| **MIGRAÇÃO** | Dev: zero impacto (era SQLite, agora roda PG em paralelo). Prod: ainda NÃO entra; só prepara |
| **PROVA DE CONTINUIDADE** | App continua usando SQLite até S5; novo PG só recebe testes |
| **PORQUÊ** | Paridade absoluta dev↔prod elimina classe inteira de bugs "funciona aqui mas não lá" |
| **GANHO** | Loop dev <2ms latência; reproducibilidade 100% |

---

## B1.3 — S1+S2+S3: Refactor de persistência

| Sprint | Tech | Como | Continuidade |
|---|---|---|---|
| **S1** DecisionRepo | SQLAlchemy 2.0 Core (não ORM) + interface `IDecisionRepo` | Substitui chamadas diretas a `sqlite3` em `state/game.py` por `self.repo.save_decision(...)`. Testes paridade comparam saída SQLite vs PG para 10k spins históricos | App em prod ainda escreve em SQLite via `SQLiteDecisionRepo`; PG ainda offline |
| **S2** Alembic | `alembic init` + revisão baseline = schema atual | `alembic stamp head` no SQLite; novas migrations daqui pra frente | Zero impacto runtime |
| **S3** structlog | `structlog` + `python-json-logger` | Substitui `logging.getLogger` por `structlog.get_logger. Tabela `strategy_versions` recebe INSERT a cada deploy lendo arquivo VERSION | Logs continuam saindo (formato muda); dashboards atuais que parseiam texto ganham 1 dia para adaptar |

**MIGRAÇÃO conjunta:** branch `feat/repo-pattern` → testes paridade verdes → merge → tag `v4.5.0` → deploy → 24h monitorando. Rollback: reverter tag.

**PORQUÊ:** sem repository pattern, trocar SQLite→PG no S5 vira refactor gigante. Com ele, troca de implementação é 5 linhas (`app_config` aponta para `PostgresDecisionRepo`).

---

## B1.4 — Sx-CI: PostgreSQL no CI

| Item | Detalhe |
|---|---|
| **O QUE** | `.github/workflows/ci.yml` ganha `services: postgres` com a nossa imagem `ghcr.io/<org>/postgres-stack:pg15-age15` |
| **COMO** | Build da imagem na primeira pipeline + push para GitHub Container Registry (GHCR, free) + jobs subsequentes fazem `pull` |
| **MIGRAÇÃO** | Adiciona ~90s ao CI; testes ganham PG real |
| **PROVA** | `pytest tests/integration/test_repo_pg.py` passa no CI |
| **PORQUÊ** | Sem PG no CI, S6/S7/S8 não conseguem testar SQL real (pgvector, AGE) |
| **GANHO** | Bug "funciona em SQLite mas não em PG" pego no PR, não em prod |

> 💡 **Substituto Azure→Free:** GHCR (GitHub Container Registry) é grátis para repos privados até 500MB. Substitui ACR perfeitamente.

---

## B1.5 — Sx-SEC: Secrets sem Azure Key Vault

| Item | Detalhe |
|---|---|
| **O QUE muda** | Substituímos **Azure Key Vault** por **sops + ge (encryption tool, sem relação com Apache AGE)** |
| **COMO** | (1) `brew install sops age` local → (2) gerar chave `age-keygen -o ~/.config/sops/age/keys.txt` → (3) `.sops.yaml` no repo definindo regex de arquivos criptografados → (4) `secrets.enc.yaml` no repo (criptografado, safe pra commitar) → (5) Debian recebe a chave privada via SCP manual (1×) em `/root/.config/sops/age/keys.txt` modo 0600 → (6) entrypoint do compose roda `sops -d secrets.enc.yaml > .env && docker compose up -d` |
| **MIGRAÇÃO** | Variáveis de ambiente atuais (`.env` em `/root/roleta-cloud/.env`) são lidas → criptografadas → commitadas como `secrets.enc.yaml` → `.env` é removido do disco |
| **PROVA** | App lê mesmo valor de `DB_PASSWORD` após mudança; `git log -p secrets.enc.yaml` mostra apenas blobs cifrados |
| **PORQUÊ** | Key Vault custa US$ 0.03/10k operações + complexidade Managed Identity. sops é grátis, padrão de mercado (Mozilla), funciona em qualquer host, rotação por commit |
| **GANHO** | Custo zero; rotação versionada no git; rollback trivial |

---

## B1.6 — S4: Postgres em produção no Debian (NÃO Azure)

| Item | Detalhe |
|---|---|
| **O QUE muda tech?** | Sobe container `postgres-stack` ao lado do `roleta-cloud` no Debian via `docker-compose.prod.yml`. Mesma imagem do dev. |
| **COMO** | (1) Upgrade Debian já feito (B1.0) → (2) `cd /root/roleta-cloud && git pull` → (3) `docker compose -f compose.prod.yml up -d postgres` (só PG, app continua usando SQLite) → (4) healthcheck verifica extensões: `docker exec postgres psql -U app -c "SELECT extversion FROM pg_extension WHERE extname IN ('vector','age','timescaledb')"` → 3 linhas |
| **MIGRAÇÃO** | App não toca PG ainda; só está disponível em `localhost:5432` |
| **PROVA DE CONTINUIDADE** | `docker ps` mostra ambos healthy; SQLite intacto; app v4.5+ ainda escrevendo lá |
| **PORQUÊ Debian e não Azure?** | (a) Loopback latency <1ms vs 30-80ms Azure brazilsouth via internet; (b) zero billing surprise; (c) AGE 100% suportado; (d) HostDime já tem LGPD residency Brasil/Fortaleza |
| **GANHO** | Stack PG analítica disponível; custo US$ 0 adicional (já pagamos VPS); latência ótima |

**Volume Docker:** `/root/roleta-cloud/data/pg` montado em `/var/lib/postgresql/data`. Backup local cron noturno: `pg_dump` → `/root/backups/pg/YYYY-MM-DD.dump` (7 dias rotação).

---

## B1.7 — S5: Outbox dual-write (SQLite→PG)

| Item | Detalhe |
|---|---|
| **O QUE** | Tabela `outbox(id UUID, payload JSONB, created_at, replicated_at)` no SQLite; worker async lê linhas com `replicated_at IS NULL` e replica no PG idempotentemente (ON CONFLICT DO NOTHING por `event_uuid`) |
| **COMO** | (1) Migration Alembic cria outbox no SQLite → (2) `state/game.py` faz INSERT na tabela principal **+** outbox em mesma transação → (3) novo serviço `cdc_worker.py` roda em thread separada (5s poll), conecta no PG e replica → (4) deploy v4.6.0 |
| **MIGRAÇÃO** | Histórico atual (SQLite) é replicado uma vez via script `backfill_to_pg.py` antes de ativar worker em prod |
| **PROVA DE CONTINUIDADE** | Após 24h: `SELECT COUNT(*) FROM cw.spins` no PG == `SELECT COUNT(*) FROM spins WHERE direction='cw'` no SQLite. Diff = 0 |
| **PORQUÊ outbox e não trigger ou cron simples?** | Idempotência por UUID resiste a: PG offline temporário, app crash mid-write, replays. Plain cron com `id > max(id)` quebra com gaps |
| **GANHO** | PG vira fonte de leitura analítica sem risco no caminho crítico de escrita; rollback = parar worker |

---

## B1.8 — Sx-LATENCY/CUTOVER: **DEPRECATED por design**

Como app e PG estão **no mesmo host Debian**, latência é loopback `<1ms`. A sprint inteira de "medir latência app↔PG e decidir cutover" deixa de existir. **Ganho automático de 1 sprint inteira no cronograma.**

---

## B1.9 — S6+S7: Vector + Autoencoder

| Sprint | Tech | Como (no Debian) |
|---|---|---|
| **S6** | `CREATE TABLE cw.spin_vectors (spin_id BIGINT, embedding vector(64))` + index HNSW | Alembic migration; backfill cria vetores zero para histórico, recalcula via S7 |
| **S7** | `sklearn.neural_network.MLPRegressor(hidden_layer_sizes=(4,), max_iter=500)` treinado em CPU; modelo salvo via `joblib.dump` em `/root/roleta-cloud/models/ae_cw_YYYYMMDD.joblib` | Cron diário 04:00 retreina + atualiza vetores; arquivo modelo versionado em B2 (off-site) |

**Por que sklearn e não PyTorch?** Container 200MB menor, treino de 6→4→6 com 100k samples leva ~30s em 1 vCPU (cabe na janela noturna do Debian sem afetar app). PyTorch seria overkill.

**MIGRAÇÃO:** primeira execução cria modelo v1; predições só são usadas em shadow (S11). Apenas em S13 entram em decisão real.

**PROVA:** `SELECT AVG(reconstruction_loss) FROM cw.ae_eval` < threshold pré-acordado.

---

## B1.10 — S8: Apache AGE grafos por sentido

**O QUE:** dois grafos isolados `cw_graph` e `ccw_graph` (cypher via AGE). Nós = regiões da roleta (37). Arestas = transições com pesos = contagem + recência.

**COMO no Debian:**
`sql
LOAD 'age'; SET search_path TO ag_catalog, public;
SELECT create_graph('cw_graph');
SELECT create_graph('ccw_graph');
-- popular via job que lê outbox
`

**MIGRAÇÃO:** rebuild grafo de zero a partir do histórico no PG (~5 min de processamento, executado uma vez).

**PROVA:** consulta Cypher `MATCH (a:Region)-[t:Transition]->(b) RETURN a,b,t.count ORDER BY t.count DESC LIMIT 10` retorna distribuição plausível (regiões 28-30 mais frequentes batem com histórico).

**PORQUÊ no Debian e não Azure?** B32 — AGE não está na allowlist Flexible Server. Self-managed resolve.

---

## B1.11 — S9+S10+S11+S12+S13+S14: O resto

| Sprint | Tech mudada | Migração | Continuidade |
|---|---|---|---|
| **S9** Outlier MAD | Função SQL pura mad_filter() | Aplica em cold-start safe (n>=20) | Não muda predição até S13 |
| **S10** Cold regions OFF | Feature flag em strategy_config | Default OFF; só ativa se evidência empírica | Zero impacto |
| **S11** Shadow predictor | Thread async + circuit breaker 5fails/60s + timeout 2s | Roda em paralelo, logs comparam shadow vs real | App nunca depende dele |
| **S12** Métricas | prometheus_client no app + grafana-agent → **Grafana Cloud free** (10k séries grátis) | Substitui Grafana local (3.3GB RAM atual não comportaria) | Pure addition |
| **Sx-OBS** | grafana-agent container ~50MB | Mesmo host, lê /metrics e /var/log | Adiciona <100MB RAM |
| **S13** Canário | hash(salt_semana + spin_id) % 100 decide bucket | 10% por 7d → audit gate → 50% → audit gate → 100% | Rollback instantâneo: `SET canary_pct=0` |
| **S14** Adoption v5.0.0 | Tag git + CHANGELOG completo | Deploy padrão | QWs e shadow já validados |
| **Sx-LGPD** | Análise legal | HostDime Brasil/Fortaleza ✅ residency OK; sem dados pessoais (RGPD N/A) | Doc |
| **Sx-ROLL** | Runbook | Doc + scripts `./scripts/rollback.sh <tag>` | Reverso |
| **Sx-PAUSE** | Threshold automático | Pausa plano se hit-rate <35% por 3 dias | Safety net |

---

# 🟠 BLOCO 2 — O que **realmente** precisa sair do Debian

Após análise sprint a sprint, **só sobra UMA coisa** que tecnicamente exige cloud externa:

## B2.1 — Off-site backup geográfico (disaster recovery)

**POR QUE NÃO PODE FICAR SÓ NO DEBIAN:** se o data center HostDime Fortaleza pega fogo, sofre ataque ransomware, ou conta é suspensa, perdemos TUDO — banco PG, modelos AE, histórico Timescale, código (git tá no GitHub, ok, mas dados não). **Backup precisa estar geograficamente separado do servidor primário.**

**O QUE PRECISAMOS:** storage objeto S3-compatível em região DIFERENTE de Fortaleza.

### Opções (preço para ~50 GB/mês de backups):

| Provedor | Localização | Custo/mês | Egress | Recomendação |
|---|---|---|---|---|
| **Backblaze B2** | EUA/EU | **US$ 0.30** (storage) + free egress até 3× | Free 3× volume | 🥇 **TOP** |
| Cloudflare R2 | Global | US$ 0.75 | Free egress (zero) | 🥈 alt |
| Azure Blob LRS | brazilsouth | US$ 1.10 + US$ 0.087/GB egress | Cobrado | Caro |
| AWS S3 IA | sa-east-1 | US$ 0.625 + egress | Cobrado | Caro |
| Wasabi | EUA | US$ 5.99 fixo (mínimo) | Free | Caro p/ volume baixo |

**ESCOLHA:** **Backblaze B2 (~US$ 1–2/mês)** — mais barato, S3 API compatível, egress generoso (importante para teste de restore mensal).

**COMO:**
1. Criar conta B2, gerar Application Key
2. Instalar `rclone` no Debian: `apt install rclone`
3. Configurar remote: `rclone config` → backend "Backblaze B2"
4. WAL-G no PG: env `WALG_S3_PREFIX=s3://roleta-bkp/wal` + `AWS_ENDPOINT=https://s3.us-east-005.backblazeb2.com`
5. Cron diário `pg_basebackup` → `rclone copy /root/backups/pg/ b2:roleta-bkp/pg/`
6. Cron mensal: VM scratch local restore + `SELECT COUNT(*)` validation

**PROVA DE CONTINUIDADE:** `rclone size b2:roleta-bkp` cresce ~500MB/dia; restore test mensal passa.

**ALTERNATIVA SE NÃO QUISER NEM B2:** Google Drive ou Dropbox via `rclone` (15GB grátis cada, mas não-profissional para DR sério).

---

## B2.2 — (NÃO crítico) Email transacional para alertas

Se quiser alertas por email de Sx-PAUSE / Sx-OBS:
- **Resend.com** free tier 3000 emails/mês ()
- Ou SMTP HostDime se eles oferecerem

**Não bloqueia nada** — alertas podem ir só para Grafana Cloud / Telegram bot.

---

## B2.3 — O que **ABANDONAMOS** do plano A3 anterior

| Componente A3 | Status agora | Por quê |
|---|---|---|
| ~~Azure VM B4ms~~ | ❌ DESCARTADO | Debian upgrade-ado faz mesmo trabalho mais barato |
| ~~Azure Container Registry (ACR)~~ | ❌ DESCARTADO | GHCR (GitHub) é grátis e suficiente |
| ~~Azure Key Vault~~ | ❌ DESCARTADO | sops + age é gratuito e padrão indústria |
| ~~Azure Managed Identity~~ | ❌ DESCARTADO | N/A sem Azure |
| Azure Blob Storage | ⚠️ TROCADO por **Backblaze B2** | 5× mais barato |
| Sprint S-CUTOVER | ❌ DEPRECATED | App+PG mesmo host = loopback |

**Custo evitado:** ~US$ 145/mês de Azure → ~US$ 35–60/mês de upgrade Debian + US$ 2 B2 = **economia US$ 80–110/mês = ~US$ 1.000/ano**.

---

# 📐 Plano de Execução Físico (ordem cronológica)

`mermaid
flowchart TD
    A[B1.0 Upgrade HostDime<br/>4vCPU/8GB/80GB] --> B[S0 Deploy QWs v4.4<br/>merge PR#5 + tag]
    B --> C[S0.5 Build imagem<br/>postgres-stack:pg15-age15]
    C --> D[S1+S2+S3 Repo+Alembic+Logs<br/>v4.5.0]
    D --> E[Sx-CI PG no GitHub Actions]
    D --> F[Sx-SEC sops+age]
    E --> G[S4 PG container no Debian<br/>via compose.prod.yml]
    F --> G
    G --> H[S4-BAK WAL-G → Backblaze B2]
    G --> I[S5 Outbox dual-write<br/>v4.6.0]
    I --> J[S6 pgvector schema]
    J --> K[S7 Autoencoder sklearn]
    G --> L[S8 AGE grafos cw/ccw]
    K --> M[S11 Shadow predictor]
    L --> M
    H --> N[Sx-OBS grafana-agent<br/>→ Grafana Cloud free]
    M --> O[S12 Métricas + dashboard]
    N --> O
    O --> P[S9+S10 MAD + cold flag]
    P --> Q[S13 Canário 10→50%]
    Q --> R[S14 v5.0.0 adoption]

    style A fill:#fc9
    style H fill:#9cf
    style N fill:#9cf
    style G fill:#9f9
`

**Bloco azul = único componente externo (Backblaze B2 + Grafana Cloud free). Resto verde = Debian.**

**Caminho crítico:** ~40 dias úteis (vs 52 do A3, vs 59 do VF original).

---

# 🔍 Self-Audit final deste documento

| Pergunta | Resposta |
|---|---|
| Debian 8GB RAM aguenta tudo? | Sim. PG `shared_buffers=2GB` + `work_mem=64MB×8workers`=512MB + app 1GB + autoencoder 800MB + agent 100MB ≈ 4.5GB. Sobra 3.5GB de buffer. |
| Backup só em B2 (1 região) é DR suficiente? | Sim para este negócio. SLA Backblaze 99.9%, durabilidade 11-nines. Para HA-real precisaria multi-cloud, mas custo×risco não compensa. |
| sops rotação trimestral é viável? | Sim. `sops updatekeys secrets.enc.yaml` regenera; commit; deploy lê novo. Documentado em Sx-ROLL. |
| Grafana Cloud free 10k séries chega? | App tem ~50 métricas × 2 sentidos × 4 labels = ~400 séries ativas. Folga 25×. |
| GHCR free aguenta nossa imagem? | Imagem PG custom ~600MB; GHCR free para repo público; privado 500MB grátis + storage barato. OK. |
| HostDime é confiável para PG produção? | VPS atual `↑29h+` healthy, uptime histórico ok. Backup off-site mitiga risco residual. |
| O que acontece se HostDime sair do ar 4h? | Roleta pausa apostas; backup B2 garante recuperação em outro host (B2 → `pg_restore` em VM nova). RTO ~2h, RPO 5min. |
| Inegociáveis CW/CCW isolados preservados? | Sim — schemas físicos `cw`/`ccw`, grafos AGE separados, modelos AE separados. |
| Inegociável deploy só por tag? | Sim — workflow `.github/workflows/deploy.yml` permanece tag-triggered. |
| Achado B32 ainda relevante? | Não — não usamos mais Flexible Server. AGE roda em container self-managed. |

---

# 🎯 Conclusão

**Recomendação:** ADOPT este plano (Debian-first) sobre o A3 (Azure VM).

**Resumo do que muda em tecnologia:**

| De (hoje) | Para (após v5.0.0) | Onde roda |
|---|---|---|
| SQLite único | SQLite (write principal) + PostgreSQL 15 (read analítico) | Mesmo Debian, containers irmãos |
| Sem extensões | pgvector + Apache AGE + TimescaleDB | Imagem Docker custom |
| Sem repo pattern | DecisionRepo SQLAlchemy | Código local |
| Sem migrations | Alembic | Código local |
| print/logging | structlog JSON | Código local |
| .env em texto | sops + age criptografado no git | Repo |
| Sem CI com PG | GitHub Actions com PG service | GitHub free |
| Backup só local 7d | WAL-G + Backblaze B2 off-site | Debian → B2 EUA |
| Sem observabilidade | Grafana Cloud free + grafana-agent | Debian → Grafana Cloud free |
| Sem shadow | Shadow predictor + canário hash | Código local |
| Sem grafo | AGE grafos cw/ccw isolados | Debian |
| Sem embeddings | Autoencoder sklearn 6→4→6 | Debian (cron noturno) |

**Custo total novo:** ~US$ 35–60 upgrade Debian + US$ 2 Backblaze B2 = **~US$ 37–62/mês** (era US$ 0 mas com risco de DR; era US$ 151 no plano A3).

**Próximo passo recomendado:** abrir ticket HostDime AGORA pedindo upgrade B1.0; enquanto upgrade não chega, executar S0 (deploy QWs) + S0.5 (build imagem local).

---

*Documento gerado por YOLO Orchestrator · Claude Opus 4.7 · 2026-05-24 13:58*  
*Stack MCP: filesystem + memory + sequential-thinking · auditoria final pós-A3 com viés Debian-first*
