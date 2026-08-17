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

**Relógios** (verificados AO VIVO 16/08 21:40 por probe read-only autorizado — `resultados_semana_10_08_16_08.md`):
`ativado_audit_shadow = 06/08 (PR #63)` — em produção `SDA_PHASE_EVENT_AUDIT=1` e
`SDA_DIRECTION_VISION_SHADOW=1`; ⚠️ blackout 06→16/08 (incidente 502) zerou a trilha: 289
`phase_events` acumulados desde 16/08 14:31 → **contar o gate T4 a partir de 16/08**, não do merge ·
`ativado_V1V2 = PARCIAL` — `SDA_PHASE_BUFFER_SYNC=1` e `SDA_PHASE_ALT_METRIC=1` ativos;
`SDA_MIN_SPIN_INTERVAL_MS=0` (gate temporal): ext 3.11.0 sincronizada no operador 16/08, **falta o
Reload no Chrome** → PR `flag/ativar-min-spin-interval` só após confirmação do reload.

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
| SPR-V6A | P1 | **READY** | — | ~~V1, V2, V4~~ (todas MERGED) | popup, extensão-JS, alerts, health_server, message_handler-fase, phase_metrics, settings, compose | brief `sprints/SPR-V6A.md` · deps satisfeitas · X5 mergeou 16/08; **fila do lock extensão-JS: SPR-UX-CONN (P0) → V6A** |
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

## Incidente 16/08 — `/ws` 502 · **RESOLVIDO 14:23 UTC (bootstrap via SSH pelo agente, autorizado pelo dono)**

**Causa-raiz final:** merges docs ~02:00 UTC dispararam deploy → gate MIG-0 falhou (`state.json`
nunca migrado ao volume — script de #43 mergeou mas nunca rodou no host: *mergeou ≠ implantado*)
→ rollback recriou o container com imagem que EXIGE `STATE_FILE` → `FileNotFoundError` em
crash-loop → 502. Reboot da VM (~03:34) irrelevante. **Cura:** stop gracioso → `migrate-state-
to-volume.sh` (sha256 verificado) → `install-shim` (D2) → units → tick: alembic 0013, HEALTHCHECK
ok, WS PROBE 101, conf instalado, frontend sync. **Sondas externas: `/health` 200 (v4.4.1) ·
`/ws` 101 · `/metrics` 403 externo (allowlist, por design).** Issue #76 FECHADA com evidência.
Host agora segue `origin/main` sozinho (shim). Follow-up: guard NGINX do D2 deu falso-negativo
com vhost em symlink (→ SPR-D3).

## Família dados & lucro — 16/08 noite (fonte: `resultados_semana_10_08_16_08.md`) · **CICLO FECHADO em ~2h**

Dia 16/08 (único com dados na semana — blackout 06→16/08): **+168,6u** (243 resolvidas, HR 56,8%),
dealer 100% povoado via OCR, espelho PG em tempo real (outbox 4.176, backlog 0). Achados → sprint:
cobertura-21 queimou −78,9u; assinatura do dealer coletada mas FORA do loop de ML; `pnl_units` com
escala mista (E7); Azure = standby frio por snapshot.
**Ativações reais (lote 16/08 noite):** `ativado_dealer_shadow = 16/08 (PR #93)` — `SDA_ERROR_ENGINE=1`
+ `SDA_R2_DEALER_SHADOW=1` defaults na compose (shadow, zero aposta; janela de validação começa no
deploy ~2min pós-merge) · `ativado_dados_total = 16/08 (PRs #89+#95, outra sessão)` —
`SDA_PG_FEATURE_CONTEXT=1` + `SDA_DNA_REALIZE=1` + backfill 5.949 linhas + ACR `success` (gate OIDC
criado) + worker rebuilt · **decisão G7: NÃO adotar `GALE_TIERS`** (1-2-4 cap2 venceu flat em PnL
nos 2 períodos, mas maxDD 1,574× > teto 1,5×) — re-testar com ≥2 semanas de povoamento contínuo.

| SPR | Pri | Status | Branch | Depende de | Locks | PR / Nota |
|---|---|---|---|---|---|---|
| SPR-ML1 | P1 | **MERGED** | ivandirfilho-spr-ml1-exec | — | compose, settings | PR #93 (16/08) · shadow do dealer LIGADO (`SDA_ERROR_ENGINE`+`SDA_R2_DEALER_SHADOW` default 1) + teste do funil DNA · suíte 1255 verde · live (`SDA_R2_DEALER`) só após janela shadow limpa em adendo |
| SPR-G7 | P1 | **DONE** | ivandirfilho-spr-g7-exec | — | BLK-G, staking | PR #94 (16/08) · **recomendação NEGATIVA para tiers** (maxDD 1,574×>1,5×) · entregues: normalização E7 c/ teste, `tools/backtest_staking_tiers.py` (TOTAL n conferido), relatório `docs/backtests/2026-08-16-staking-tiers.md` · zero mudança de runtime · **lock BLK-G liberado** |
| SPR-AZ1 | P2 | **MERGED** | ivandirfilho-spr-az1-exec | — | deploy-azure, docs, scripts | PR #92 + issue #91 (16/08) · sonda `/healthz` no kickoff (Azure standby → 200) · lag snapshot→restore não medível de fora (SSH expirado; registrado) · OIDC destravado em seguida pelo dono (ver #95: ACR `success`) |
| SPR-REL1 | P2 | TODO | — | — | tools, docs | relatório de resultados automatizado (read-only PG→md diário) · brief a escrever |

**Backlog geral**

| SPR | Pri | Status | Branch | Depende de | Locks | PR / Nota |
|---|---|---|---|---|---|---|
| SPR-D4 | P1 | TODO | — | — | deploy, docs | **última milha da EXTENSÃO** (3º caso de *mergeou≠implantado*: entrypoint→conf→extensão): checkout `Desktop\Roleta Cloud` do operador estava 11 PRs atrás (3.9.1) e o Chrome tinha 3 registros mortos de cópias RoletaV11 · candidatos: task agendada `git pull --ff-only` no checkout do operador + aviso de versão no popup (`/health` já expõe versão do servidor; comparar e alertar "extensão desatualizada") · limpeza dos perfis mortos é manual do dono |
| SPR-D3 | P1 | TODO | — | SPR-D2 | deploy | guard `NGINX CONF` do D2: falso `DESTINO INATIVO`/`DEPLOY PARCIAL` quando o vhost ativo é symlink (`nginx -T` lista `sites-enabled/`, guard procura o alvo) → comparar com `readlink -f`; hoje TODO tick com diff de conf marca unit failed ruidosa |
| SPR-D2 | P0 | **MERGED** | spr/SPR-D2 | SPR-D1 | deploy | PRs #81+#82 (16/08, CI verde) · shim imutável + conf-install atômico + harness `TOTAL n` anti-skip · **implantado no host 16/08 14:23 UTC (bootstrap #76 executado)** · lição: *suíte verde ≠ cenário testado* |
| SPR-X5 | P0 | **MERGED** | spr/SPR-X5 | — | extensão-JS, popup | PRs #75+#79 (16/08) · ext **3.11.0** na main · checkout do operador sincronizado p/ 3.11.0 em 16/08 14:35 (estava na 3.9.1! → SPR-D4) · **falta só o Reload no chrome://extensions (Profile 3)** |
| SPR-D1 | P0 | **MERGED** | spr/SPR-D1 | — | deploy, health_server | PRs #74+#77 (16/08) · H1 refutada, self-heal+`/health`+runbook na main · **implantação real aguarda bootstrap do dono (issue #76)** → sucedido por SPR-D2 |
| SPR-U1 | P1 | **MERGED** | spr/SPR-U1 | — | — (docs) | PR #72 (16/08) · 34 achados (1×P0 OV-01, 5×P1) em `docs/ux/2026-08-16-auditoria-ux-front.md` · gerou candidatos SPR-UX-* abaixo |
| SPR-UX-CONN | P0 | TODO | — | SPR-X5 (lock) | extensão-JS, popup | jornada 502/OV-01: minimizado cego a queda de servidor (estado de erro explícito, success:false honesto, fila/descarte visível) · brief a escrever do §7 da auditoria |
| SPR-UX-DESKTOP | P1 | TODO | — | SPR-UX-CONN (lock) | extensão-JS | drag por mouse + clamp, grid slice(-10) newest-first (MN-01), paridade popup×overlay · §7 auditoria |
| SPR-UX-DASH | P1 | TODO | — | — | frontend | Glass Box: backoff+jitter na reconexão, "⚫ ONLINE" glifo, sanitização innerHTML · **paraleliza** (lock frontend disjunto) |
| SPR-UX-POLISH | P2 | TODO | — | SPR-UX-DESKTOP | extensão-JS | P2/P3 da auditoria (por último) |
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
