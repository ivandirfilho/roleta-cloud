# BOARD — Estado vivo dos sprints (o Diretor atualiza AQUI)

> Definição canônica dos sprints = `fluxo_mental_24.md` §7. Este arquivo = **estado**. Mantê-lo pequeno.
> **Commitar+push** este arquivo e o brief ANTES de lançar um executor (senão um novo Diretor não os vê).

**Estados:** `TODO → READY` (brief pronto) `→ DOING → REVIEW` (PR aberto) `→ MERGED/DONE` · ou `BLOCKED`
· ou **`WAITING_HUMAN_EVIDENCE`** (código entregue; falta medição de campo com operador — ex.: SPR-V3-B).
**Branch:** o Copilot gera `ivandirfilho-*`; o Executor **renomeia para `spr/SPR-XXX` no kickoff**
(tool `rename_branch`) ou o Diretor registra o branch real na linha do sprint — linha sem branch
rastreável = sprint invisível. **Título do PR começa com `SPR-XXX:`** (é assim que `gh pr list`
mapeia PR↔sprint sem editar o board a cada push).
**Paralelo só com `Locks` disjuntos — inclui PRs ABERTOS, não só sprints DOING.** Antes de abrir PR:
`gh pr list` + diff de arquivos; colisão de lock → serializa (não abre silo paralelo).
`schema/alembic` e `BLK-G` serializam entre si (numeração de migração / cérebro da estratégia colidem).
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
`ativado_V1V2 = PENDENTE` (⚠️ auditoria 06/08: em produção `SDA_PHASE_BUFFER_SYNC=0` e
`SDA_MIN_SPIN_INTERVAL_MS=0` — o código dos merges V1/V2 está deployado porém **inerte**; ligar
buffer-sync → confirmar ext 3.10.0 instalada → só então o gate temporal → registrar a data aqui) ·
`ativado_audit_shadow = PENDENTE` (`SDA_PHASE_EVENT_AUDIT=0` **e** `SDA_DIRECTION_VISION_SHADOW=0` →
os 7 dias do gate T4 ainda NÃO começaram a contar).

**Fila de integração 06/08 — AUTOMÁTICA desde 06/08 à noite:** auto-merge armado em #60, #61, #58
(mergeiam sozinhos com `ci-ok` verde; `strict` OFF por design). **#43** fica FORA do auto-merge:
39 arquivos misturando MIG-0+Azure+ISO → fatiar em PRs pequenos antes.
⚠️ #58/#60 colidem em `message_handler.py`+`outbox_integration.py`+baseline; o que mergear depois
fica CONFLICTING → Diretor delega resolução a um executor. `main` vermelho pós-merge → issue
`main-red` abre sozinha e vira sessão de agente.
**Ativação:** PR `flag/ativar-audit-shadow` liga `SDA_PHASE_EVENT_AUDIT=1` +
`SDA_DIRECTION_VISION_SHADOW=1` (shadow por design, zero efeito em aposta) → merge inicia o
relógio de 7d do gate T4. Registrar `ativado_audit_shadow=<data do merge>` no próximo lote.

| SPR | Pri | Status | Branch | Depende de | Locks | PR / Nota |
|---|---|---|---|---|---|---|
| SPR-V1 | P0 | **MERGED** | ivandirfilho-didactic-broccoli | — | message_handler-fase, game-state, phase, phase_metrics, health_server, alerts, settings, compose | PRs #53+#54 (05-06/08) · flags default-OFF: ativação pendente (ver Relógios) |
| SPR-V2 | P0 | **MERGED** | ivandirfilho-studious-disco | — | extensão-JS, popup, manifest | PR #52 (05/08) · ext **3.10.0** mergeada; instalação no operador NÃO confirmada |
| SPR-V3 | P1 | **WAITING_HUMAN_EVIDENCE** | ivandirfilho-scaling-bassoon | **SPR-V2** | tools/vision_spike | V3-A MERGED PR #56 (06/08) · V3-B = medição de campo com operador |
| SPR-V4 | P1 | **MERGED** | ivandirfilho-turbo-waffle | **SPR-V1** | message_handler-fase, sqlite_repo, game-state, phase_metrics, health_server, alerts, settings, compose | PR #55 (06/08) · trilha `phase_events` shadow-only, audit flag OFF |
| SPR-V6A | P1 | **READY** | — | ~~V1, V2, V4~~ (todas MERGED) | popup, extensão-JS, alerts, health_server, message_handler-fase, phase_metrics, settings, compose | brief `sprints/SPR-V6A.md` · deps satisfeitas em 06/08 · #58 mergeou 06/08; agora aguarda **SPR-X5** (lock extensão-JS/popup) |
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

## Incidente 16/08 — `/ws` 502 (Glass Box OFFLINE × HostDime "online")

Evidência externa (Diretor 16/08 ~03:46Z): nginx vivo (`/`→200), `location /health` NEM existe
(404), `/ws`→**502** = upstream 127.0.0.1:8765 morto; CI main verde, merges recentes docs-only
⇒ NÃO é regressão de código; suspeitas: WS morto c/ health vivo (H1) / timer-entrypoint (H2) /
NOOP-gap do deploy (tick sem healthcheck não ressuscita container). Tratamento: **SPR-D1**.

**Backlog geral**

| SPR | Pri | Status | Branch | Depende de | Locks | PR / Nota |
|---|---|---|---|---|---|---|
| SPR-X5 | P0 | **DOING** | brief em `spr/SPR-X5` → sessão executora | — | extensão-JS, popup | racetrack-guia acesa no overlay minimizado (pedido operador 16/08) · **serializa com V6A/X1..X4/V5** (lock extensão-JS) |
| SPR-D1 | P0 | **DOING** | brief em `spr/SPR-D1` → sessão executora (**Opus**) | — | deploy, health_server | incidente 16/08 (seção acima): diagnóstico + `/health` no nginx + self-heal NOOP + runbook · fix-forward pelo próprio merge |
| SPR-U1 | P1 | **DOING** | brief em `spr/SPR-U1` → sessão executora | — | — (docs novo) | auditoria UX sênior das 4 superfícies (Glass Box, popup, overlay exp/min) · saída = achados + sprints candidatos |
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
