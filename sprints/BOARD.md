# BOARD — Estado vivo dos sprints (o Diretor atualiza AQUI)

> Definição canônica dos sprints = `fluxo_mental_24.md` §7. Este arquivo = **estado**. Mantê-lo pequeno.
> **Commitar+push** este arquivo e o brief ANTES de lançar um executor (senão um novo Diretor não os vê).

**Estados:** `TODO → READY` (brief pronto) `→ DOING → REVIEW` (PR aberto) `→ MERGED/DONE` · ou `BLOCKED`
· ou **`WAITING_HUMAN_EVIDENCE`** (código entregue; falta medição de campo com operador — ex.: SPR-V3-B).
**Branch:** `spr/SPR-*` · **1 executor = 1 worktree** (`git worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main`).
**Paralelo só com `Locks` disjuntos.** `schema/alembic` e `BLK-G` serializam entre si (numeração de migração / cérebro da estratégia colidem).
**Locks canônicos** (nomes iguais = mesmo lock; não invente sinônimos): `extensão-JS` (≡ "extensão (JS)",
cobre `extension/*.js`, popup e manifest) · `message_handler-fase` · `game-state` · `phase` ·
`sqlite_repo` · `schema/alembic` · `phase_metrics` · `health_server` · `alerts` · `settings` ·
`compose` · `BLK-*`. **`Locks` tem de cobrir todos os `touches` do brief.**

**Resumir como Diretor (sessão nova):** `git fetch origin --prune`; ler este board; p/ cada sprint `DOING/REVIEW` rodar `git diff --stat origin/main...origin/spr/SPR-*` + ler o tail do log em `sprints/SPR-*.md` + `gh pr list` + `memory.search_nodes`.

## Família SPR-V — seletor de sentido (proposta `proposta_seletor_sentido_03_08.md` §§10-11, PR #45)

Ordem de execução: **V1 ∥ V2** → V3 → V4 → V6A → *(decisão humana com dados)* → V5 → V6B → *(SPR-V8 + gate T4)* → V7.
Ordem de **ativação em produção** (≠ ordem de merge): V1 com flags OFF → `SDA_PHASE_BUFFER_SYNC=1` →
instalar a extensão do V2 → só então `SDA_MIN_SPIN_INTERVAL_MS=15000`.
*(Ligar o gate temporal antes do V2 deixa o servidor certo e o popup espelhado: o cliente antigo não
desfaz o flip local do fantasma rejeitado. Por isso o V1 publica `state_sync.phase_authority` e o V2 o
consome para reverter o flip.)*

**Relógios que o Diretor precisa registrar aqui quando começarem** (senão os gates não são auditáveis):
`ativado_V1V2 = <data>` (buffer-sync ON **e** ext 3.10.0 instalada → inicia a janela de 30d do V6B) ·
`ativado_audit_shadow = <data>` (`SDA_PHASE_EVENT_AUDIT=1` **e** `SDA_DIRECTION_VISION_SHADOW=1` →
inicia os 7 dias do gate T4).

| SPR | Pri | Status | Branch | Depende de | Locks | PR / Nota |
|---|---|---|---|---|---|---|
| SPR-V1 | P0 | **READY** | spr/SPR-V1 | — | message_handler-fase, game-state, phase, phase_metrics, health_server, alerts, settings, compose | brief `sprints/SPR-V1.md` · ⚠️ rebase se o PR #43 mergear (toca game.py/settings/compose) |
| SPR-V2 | P0 | **READY** | spr/SPR-V2 | — | extensão-JS, popup, manifest | brief `sprints/SPR-V2.md` · locks disjuntos de V1 → paralelo seguro · base real = ext 3.9.1 → **3.10.0** |
| SPR-V3 | P1 | TODO | — | **SPR-V2** | tools/vision_spike | brief `sprints/SPR-V3.md` · V3-A = DoD do PR (não toca `extension/`); V3-B = campo → `WAITING_HUMAN_EVIDENCE` |
| SPR-V4 | P1 | TODO | — | **SPR-V1** | message_handler-fase, sqlite_repo, game-state, phase_metrics, health_server, alerts, settings, compose | brief `sprints/SPR-V4.md` · **serializa com SPR-G2** (sqlite_repo + message_handler) · SQLite, **sem Alembic** |
| SPR-V6A | P1 | TODO | — | **V1, V2, V4** | popup, extensão-JS, alerts, health_server, message_handler-fase, phase_metrics, settings, compose | brief `sprints/SPR-V6A.md` · maior ganho por custo · **nenhuma ação automática** · ingere o `client_health` do V2 |
| SPR-V5 | P2 | **BLOCKED** | — | V2, **V3=GO**, V4, **V6A** | extensão-JS, manifest, popup | brief `sprints/SPR-V5.md` · destrava só com os 4 números do GO em `tools/vision_spike/RESULTADO.md` · **dono do controle positivo do T4** |
| SPR-V6B | P2 | **BLOCKED** | — | V1+V2 ativos + **≥30d limpos** + snapshot sanitizado | job-auditoria | brief `sprints/SPR-V6B.md` · saída = `mirror_suspect`, nunca `set_seed` · **sem acesso ao PG produtivo, zero DDL** |
| SPR-V8 | P2 | TODO | — | — | auth, settings, compose, extensão-JS | **brief a escrever** quando V5 entrar em voo · hardening de autenticação/role: token no handshake + envio pela extensão + role derivada do token · **pré-requisito duro do SPR-V7** |
| SPR-V7 | P3 | **BLOCKED** | — | V5 + **SPR-V8** + **gate T4** | phase, game-state, message_handler-fase, settings, phase_metrics, alerts, compose | brief `sprints/SPR-V7.md` · corrige **âncora futura**, nunca o spin · `SDA_DIRECTION_VISION` congelada em 0 |

**Gate T4 (destrava V7):** ≥7d **contados a partir de `ativado_audit_shadow`** E ≥2000 vereditos em
shadow com V1/V2 ligados e âncora confirmada · **cobertura medida ANTES de concordância**
(`vereditos_emitidos / giros_elegíveis`) · agree ≥99,5% · 100% dos desacordos auditados na trilha
`phase_events` · controle positivo (harness do **SPR-V5**) com seed espelhado **em replay/sessão
sintética (nunca em produção — INV-3 faz a aposta sair)** · nenhum caso em que K=3 teria corrigido
errado · `stale+selfcontradict` <1% · cobertura ≥60% dos giros com aba visível.
**Evidência**: o Diretor cola no board as queries usadas, os denominadores, as datas e o `sha` do
algoritmo. Gate sem denominador registrado **não** conta.

**Backlog geral**

| SPR | Pri | Status | Branch | Depende de | Locks | PR / Nota |
|---|---|---|---|---|---|---|
| SPR-G2 | P0 | TODO | — | — | schema, alembic, BLK-I, sqlite_repo, message_handler | ⚠️ **brief desatualizado**: manda criar `0010_*`, mas a head já é **0013**. Revisar antes de voltar a READY · **serializa com SPR-V4** |
| SPR-S1 | P0 | TODO | — | **SPR-G2** | BLK-G (análise) | — |
| SPR-G1 | P1 | TODO | — | — | versioning, docs | — |
| SPR-G3 | P1 | TODO | — | — | deploy, compose, BLK-K | — |
| SPR-S2 | P1 | TODO | — | **SPR-G2** | BLK-G, BLK-E | — |
| SPR-S3 | P1 | TODO | — | — | BLK-D, BLK-G | — |
| SPR-S4 | P1 | TODO | — | — | BLK-D | — |
| SPR-S6 | P1 | TODO | — | — | BLK-L (harness) | — |
| SPR-T4 | P1 | TODO | — | — | BLK-E, ingest | — |
| SPR-X3 | P1 | TODO | — | — | extensão-JS | ⚠️ serializa com V2/V6A/V5 |
| SPR-S5 | P2 | TODO | — | — | BLK-D | — |
| SPR-G4 | P2 | TODO | — | — | schema, alembic | serializa c/ SPR-G2 |
| SPR-G5 | P2 | TODO | — | — | docs, feature_flags | — |
| SPR-G6 | P2 | TODO | — | — | docs | — |
| SPR-T1 | P2 | TODO | — | — | BLK-G | — |
| SPR-T2 | P2 | TODO | — | — | BLK-G | — |
| SPR-T3 | P2 | TODO | — | — | BLK-I | — |
| SPR-T6 | P2 | TODO | — | — | repo-hygiene | — |
| SPR-X1 | P2 | TODO | — | — | extensão-JS | ⚠️ serializa com V2/V6A/V5 |
| SPR-X2 | P2 | TODO | — | — | extensão-JS, BLK-D | ⚠️ serializa com V2/V6A/V5 |
| SPR-X4 | P2 | TODO | — | — | extensão-JS | ⚠️ serializa com V2/V6A/V5 |
| SPR-O1 | P2 | TODO | — | — | obs | — |
| SPR-T7 | P2 | TODO | — | — | BLK-D | ISO §D.1 (sem alterar comportamento) |

<!-- DIRETOR: ao mudar status, atualize só a linha. base_sha/owner ficam no cabeçalho do brief. -->
