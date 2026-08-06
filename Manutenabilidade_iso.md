# 📐 Roleta Cloud — Arquitetura & Conformidade ISO/IEC 25010

> **Versão do Software:** 4.4.0  
> **Data da Análise:** 02/04/2026 · **Atualizado:** 14/06/2026 (ver ADENDOS 12/06 e 14/06)  
> **Base:** Auditoria pós-implantação M15-ADA (M02-PctSigmoid) + ciclo 24/05→12/06  
> **Norma de Referência:** ISO/IEC 25010:2011 — Modelo de Qualidade de Produto de Software  
> **Total de Linhas de Código:** ~119 arquivos Python ativos · 48 arquivos de teste (374 testes)

---

## ADENDO 12/06/2026 — Estado de conformidade após o ciclo 24/05→12/06

> As PARTES I–VI abaixo retratam a v4.3.2 (02/04) e permanecem como baseline
> histórica. Este adendo registra o delta real verificado em 12/06 — muito do
> que constava como gap foi resolvido nos ciclos 24/05–27/05 (PG stack, CI,
> observabilidade) e 10/06–12/06 (lucro/regiões/INV-3).

### A. Gaps de 02/04 RESOLVIDOS (verificados no código em 12/06)

| Item (02/04) | Resolução | Evidência |
|---|---|---|
| CI vazio (MEL-ISO-002, 7.5) | ✅ `ci.yml` matrix 3.11/3.12/3.13 + PG service + alembic + coverage gate 50% + 3 linters; **verde em main desde 12/06** | `.github/workflows/ci.yml`; run 27434340714 |
| Sem migrations (MEL-ISO-003, 7.4) | ✅ Alembic 0001..0008 (PG) + auto-migrations SQLite; deploy roda `alembic upgrade head` com rollback | `migrations/versions/`; `scripts/roleta-deploy-pull.sh` |
| Sem circuit breaker (MEL-ISO-004) | ✅ `_SQLiteCircuitBreaker` (CLOSED/OPEN/HALF_OPEN) | `database/sqlite_repo.py:22-90` |
| `str(e)` vazava ao cliente (BUG-POST-004 / MEL-ISO-001) | ✅ ISO-S2: cliente recebe mensagem opaca + trace_id; detalhe só server-side | `server/message_handler.py:159-171`; `tests/test_error_output_sanitize.py` |
| `GameState.load()` silencioso (BUG-POST-007 / MEL-ISO-010) | ✅ Loga erro + salva `state.json.corrupted` antes do fallback | `state/game.py:1220-1229` |
| Colunas "mortas" calibration_* (BUG-POST-006) | ✅ Reclassificado: `calibration_error` agora É o wheel_dist por decisão (W-02/B-08, fill-rate monitorado NEW-12) | `server/message_handler.py`; gauge `roleta_calibration_fill_rate_1h` |
| Cobertura/testes "5 arquivos, ~105 testes" (7.3/7.5) | ✅ 48 arquivos, **374 passed** (integração real do handler incluída) | `pytest -q` 12/06 |
| Schema DDL manual (7.4) | ✅ + guarda de drift: snapshot vivo × manifest SQLite↔PG falha o CI se divergir (SP-04) | `tests/test_schema_parity.py`; `database/schema_parity_manifest.json` |
| Observabilidade só logs/trace | ✅ Prometheus (40+ métricas custom), Alertmanager (12+ regras), Grafana local+Cloud, gap-check textfile | `server/health_server.py`; `obs/alerts.yml` |

### B. Capacidades NOVAS com impacto ISO (não existiam em 02/04)

| Capacidade | Característica ISO | Evidência |
|---|---|---|
| PG stack espelho (cw/ccw/shared) via outbox→CDC, dual-write defensivo | Confiabilidade / Compatibilidade | `database/outbox_*`, `workers/cdc_worker.py` |
| PROFIT-LEDGER: `pnl_units`/decisão + `sessions.total_profit` + gauges P&L | Adequação Funcional (KPI=EV) | `database/sqlite_repo.py::update_result`; `roleta_session_pnl_units` |
| INV-3 global: indicação sempre; vetos modulam stake (CUT v1, stop-loss) | Adequação Funcional / Usabilidade | `server/message_handler.py` (gates 12/06); P11 |
| Reset TOTAL da estratégia no botão de dealer (`reset_adaptive`) | Adequação Funcional (P10) | `strategies/sda17.py::reset_adaptive` |
| Medição por região: `result_region` + `dist_c1/c2/c3` + `region_err_ema` (gauge) | Analisabilidade | `state/game.py::_attribute_hit_region`; `roleta_region_err_ema` |
| Feedback adaptativo consome a APOSTA REAL (coverage/centers do pending) | Confiabilidade (anti classe BUG-B) | `strategies/sda17.py::update_adaptive` |
| Lints de regressão: silent-except baseline, DNA coverage, schema symmetry | Manutenibilidade | `tools/lint_*.py`; `scripts/schema_symmetry.py` |
| Pipeline deploy pull-based c/ alembic+healthcheck+rollback; backup diário SQLite + wal-g 30min (ressuscitado 12/06) | Confiabilidade / Portabilidade | `scripts/roleta-deploy-pull.sh`, `scripts/backup-decisions.sh` |
| DNA por decisão (features+realized lift) p/ análise contrafactual | Analisabilidade | `database/dna_logger.py`; `decision_dna` |

### C. Scorecard revisado (12/06)

| # | Característica | 02/04 | 12/06 | Justificativa |
|:-:|---|:---:|:---:|---|
| 1 | Adequação Funcional | 9.0 | **9.2** | INV-3/P11, reset P10, ledger de P&L real |
| 2 | Eficiência | 8.7 | **8.7** | inalterado (375ms/spin medido em prod) |
| 3 | Compatibilidade | 7.0 | **7.5** | PG espelho + APIs HTTP de introspecção (`/api/strategy`, `/metrics`); falta REST de comando/AsyncAPI |
| 4 | Usabilidade | 8.2 | **8.2** | inalterado |
| 5 | Confiabilidade | 8.5 | **8.8** | circuit breaker, outbox, backups testados, deploy c/ rollback |
| 6 | Segurança | 6.5 | **6.5*** | *fora de escopo por diretriz do owner (10/06); achados preservados em `server_snapshot/08_seguranca.md` |
| 7 | Manutenibilidade | 8.0 | **8.6** | CI verde, migrations, parity guard, 374 testes, lints de regressão |
| 8 | Portabilidade | 8.2 | **8.4** | deploy automatizado + restore path documentado |

**Nota geral: 8.0 → 8.5/10.** (Segurança congelada por decisão de produto, não por incapacidade.)

### D. Gaps REAIS remanescentes (manutenibilidade — ordenados por impacto)

1. **`server/message_handler.py` ~1000 LOC** — `handle_new_result` concentra
   pipeline inteiro (decisão+gates+stake+persistência+overlay). Mitigado por
   testes de integração (12/06), mas a extração de um `DecisionPipeline` puro
   continua sendo a maior dívida de modificabilidade. *(herda o 7.1/7.4)*
2. **Coverage gate em 50%** — ramp planejado 50→75 (SP-34.1) ainda não executado;
   `server/` segue como área de menor cobertura unitária.
3. **AGE instalado sem uso** — schemas de grafo vazios; decisão tomada (remover e
   voltar a `pgvector/pgvector:pg15` oficial) pendente de execução. Imagem 1GB.
4. **`models/spin_autoencoder.joblib` untracked no servidor** — hazard de `git clean`
   (mover a volume + `.gitignore`).
5. **Restore drill não executado** — backups existem (SQLite diário + wal-g 30min)
   mas o restore nunca foi ensaiado ponta-a-ponta (`walg-restore-drill.sh` pronto).
6. **AsyncAPI/REST de comando** — protocolo WS segue sem spec formal (7.0→7.5 só
   pela introspecção HTTP).
7. **DeprecationWarnings** — `datetime.utcnow()` (139 avisos na suite) e
   `websockets.legacy`; baratos de sanar, zero risco funcional.

> Rastreabilidade completa do ciclo: `proximos_passos_10_06.md` (premissas P1–P12,
> trilhas A/B/C, auditorias 12/06 r1/r2) e `analise_regioes_12_06.md` (A1–A3).

---

## ADENDO 14/06/2026 — Ciclo Auto-Start & Zero-Upload (Escuta Beat, extensão v3.3.0)

> Este adendo registra o ciclo **client-side** de 14/06: a extensão Chrome "Escuta
> Beat" passou de **mono-provider com upload manual** para **auto-detecção +
> zero-upload + auto-start**. O backend Python (v4.4.1) **NÃO foi alterado** — o deploy
> (commit `23c3490`) confirma o servidor saudável e alinhado; a extensão é client-side
> e é ativada por *reload* no Chrome do operador. Roadmap e auditoria UX completos em
> `passos_escuta_junho.md` (§4.9 e §12).

### A. Capacidades NOVAS com impacto ISO

| Capacidade | Característica ISO | Evidência |
|---|---|---|
| Auto-detecção de provider por fingerprint ponderado (URL/host dos frames) | Usabilidade (operabilidade) | `extension/provider_router.js` (`detectFromFrames`/`matchHostToProvider`) |
| Zero-upload: manifests empacotados servidos via `web_accessible_resources` | Usabilidade / Manutenibilidade | `extension/providers/{evolution,index}.json`; `extension/manifest.json` |
| Auto-start: `webNavigation.onCompleted` + `getAllFrames` → inicia a escuta sozinha | Usabilidade (operabilidade) | `background.js::maybeAutoStart`/`registerAutoDetectListeners` |
| Supressão de auto-start pós-STOP (TTL 24h + revalidação de host + prune no boot) | Confiabilidade / Usabilidade | `background.js::suppressTab`/`isTabSuppressed`/`pruneSuppressedTabs` |
| Registry de providers extensível (novo provider = 1 entrada + 1 JSON) | Manutenibilidade (modificabilidade) | `provider_router.js::PROVIDER_DETECTION`; `providers/index.json` |
| Badge de status fora do popup + toggle de auto-start | Usabilidade | `popup.html`/`popup.js`; `background.js::setBadge` |

### B. Bugs corrigidos na auditoria pós-implantação (3 rodadas de code-review)

| # | Bug | Sev | Característica ISO | Correção |
|:-:|---|:--:|---|---|
| 1 | WebSocket duplicado por race (`CONNECTING` não idempotente; `onclose` órfão derrubava o socket saudável) | High | Confiabilidade (maturidade) | guard `OPEN\|CONNECTING` + `wsConnection!==socket` nos handlers + lock por tabId |
| 2 | STOP manual não segurava (auto-start re-iniciava via webNavigation/scan/popup) | High | Usabilidade / Confiabilidade | `suppressTab` persistido + TTL 24h + revalidação de host + prune no boot |
| 3 | Badge verde não limpo ao parar/fechar (status mentia) | Med | Usabilidade | `setBadge('')` em stop/onRemoved/auto-stop |
| 4 | 2ª aba de cassino sequestrava o `tabId` singleton silenciosamente | Med | Confiabilidade | recusa + log em vez de sobrescrever |
| 5 | Política `'ask'` beco sem saída (detectava, nunca iniciava) | Low | Manutenibilidade | `getAutoStartPolicy` normaliza ≠`off`→`auto` |

### C. Impacto ISO por característica

**Usabilidade (cap. 4)** — maior ganho do ciclo. O fluxo "abrir site → upload do JSON →
escolher mesa → clicar Iniciar" (60-90 s, sujeito a carregar o JSON errado) vira "abrir a
mesa → a escuta inicia sozinha" (< 10 s, zero upload). Salvaguarda de consentimento (NB-02):
o auto-start só inicia a **leitura**, nunca aposta; toggle `auto|off`; STOP manual é
respeitado. 20 pain points UX mapeados em `passos_escuta_junho.md` §4.6.

**Manutenibilidade (cap. 7)** — federação extensível: adicionar um provider é 1 entrada em
`PROVIDER_DETECTION` + 1 manifest `providers/<id>.json`, sem tocar no runtime; a detecção
foi **centralizada** (antes espalhada em `deal_capture.js`). 13 testes novos
(`test_provider_router` 9 + `test_bundled_manifest` 4); suite total **480 passed**.

**Confiabilidade (cap. 5)** — idempotência de WebSocket sob concorrência; supressão
persistida resiliente à reciclagem do service worker (MV3) e ao reuso de `tabId`;
tolerância a frames cross-origin inacessíveis.

**Segurança (cap. 6)** — `<all_urls>` (já existente) mantido; a auto-detecção **não amplia**
permissões. Riscos NB-01 (content_scripts amplo) e NB-05 (integridade OTA via Ed25519) ficam
**documentados** como pré-condições das fases futuras (CDN), não implementados neste ciclo.

**Portabilidade (cap. 8)** — manifests empacotados tornam a extensão self-contained (sem
dependência de upload externo); o canal OTA assinado permanece como roadmap (Sprint 5).

### D. Scorecard — delta client-side (14/06)

| # | Característica | 12/06 | 14/06 | Justificativa |
|:-:|---|:---:|:---:|---|
| 4 | Usabilidade | 8.2 | **8.6** | zero-upload + auto-start + toggle/badge; ~-90% no tempo "abrir→escutar" |
| 7 | Manutenibilidade | 8.6 | **8.7** | registry de providers extensível + 13 testes; detecção centralizada |
| 5 | Confiabilidade | 8.8 | **8.8** | mantido (correções de concorrência compensam a nova superfície) |

> Demais características inalteradas (backend v4.4.1 intacto). **Nota geral mantém 8.5/10**,
> com Usabilidade puxando para cima no eixo client.

### E. Gaps remanescentes (escopo client-side)

1. **Multi-mesa singleton** — 1 `tabId`/escuta por vez; a 2ª aba é recusada (com log), não
   suportada. Multi-mesa real exige o `ServerSessionRegistry` (Sprint 4 do roadmap).
2. **CDN OTA não implementado** — manifests só empacotados; correção de seletor ainda exige
   rebuild/republicação. Sprint 5 (OTA Ed25519) endereça.
3. **`content_scripts: <all_urls>`** — NB-01 aberto (privacidade/perf/revisão CWS); migração
   para `declarativeContent` + injeção pós-detecção fica para a Sprint 2 plena.
4. **Self-heal apenas modelado** — a promoção de fallback por telemetria hit/miss está
   desenhada (§4.9.3) mas não codada neste ciclo.
5. **Extensão fora da CI** — os testes JS rodam via Node dentro do pytest, mas não há
   lint/build da extensão no `ci.yml` nem smoke E2E (Puppeteer planejado na Sprint 7).

---

## ADENDO 17/06/2026 — Implantação C1/C2 variável + Block-Gale (aposta 14# + staking por bloco)

Ciclo que materializou o estudo `resultados_15_junho.md` em produção: a cobertura
deixa de ser os 3 centros fixos (21#) e passa a **{C1 ou C2 móvel} + C3 fixo = 14#**,
com staking **por bloco isolado por sentido**. Dois motores novos, isolados e
flag-gated, plugados no hot path. Spec/auditoria completa: `implantação_c_variavel_gale_junho.md` §17.

### A. Capacidades NOVAS com impacto ISO

1. **CSelectionEngine** (`strategies/c_selection.py`) — escolhe C1 ou C2 pela tendência
   das últimas 3 jogadas não-C3 do **próprio sentido** (análise isolada CW/CCW), monta a
   união real de 14# (C_escolhido ∪ C3) sobre `WHEEL_SEQUENCE`, e mantém candidatos-sombra
   congelados com guardrail de promoção via IC de diferença de Newcombe (1998, método 10).
   `MAXLEN=200 ≥ MIN_N_PROMOTE=150` (promoção pode disparar). Persistência deque↔list.
2. **BlockGaleEngine** (`state/block_gale.py`) — gale **por sentido**, blocos de 4, critério
   2-de-4, níveis ×1/2/4/8, "só apostar após green" (stake-gate, não supressão), solvency-guard
   e reset por troca de dealer. `cap` clampado a 1..4; `cap=1` nunca escala (flat-equivalente).
3. **Wiring no pipeline** (`server/message_handler.py:85-215` + call-sites 479/555/678/700/931):
   resolve(t-1) → select(t) → stake → inject-pending → overlay aditivo. Tudo `try/except`
   defensivo: telemetria/override nunca quebra o fluxo de decisão.
4. **Flags operacionais** (`app_config/settings.py:141-193`): `SDA_BET_PAIR`, `SDA_STAKING_MODE`
   (+`block_gale`), `GALE_CAP[_CW/_CCW]`, `GALE_ONLY_AFTER_GREEN`, `GALE_BANKROLL`,
   `C_SELECTION_AUTO_PROMOTE` — **lidas por chamada** (toggle em runtime, sem restart).
5. **Go-live config** (defaults do repo em `docker-compose.yml:34-66`):
   `SDA_BET_PAIR=var_c1c2_c3` + `SDA_STAKING_MODE=block_gale` + `GALE_CAP=1` (flat-equivalente,
   **sem ruína** — o estudo mostrou que gale só sangra; cap=1 é o único seguro) +
   `GALE_ONLY_AFTER_GREEN=0` + `GALE_BANKROLL=1000`. Rollback total via host env
   (`SDA_BET_PAIR=full` + `SDA_STAKING_MODE=flat`) + redeploy, ou `git revert`.

### B. Bugs corrigidos na auditoria pós-implantação (3 rodadas)

- **Sprint design (§10/§11):** 13 bugs de projeto corrigidos antes de codar.
- **Sprint código (code-review):** 6 bugs nos motores (tolerância a `dist=None`, MAXLEN,
  clamp de nível, validação de incumbente no load, IC de Newcombe, contagem de bloco só se `placed`).
- **Sprint wiring (code-review 17/06):** **1 bug latente** — `_engine_resolve` alimentava
  `block_gale.on_result` com um `shadow_green` **recomputado** (`dist_min<=3`) em vez do **hit
  real**. Diverge no fallback de calibração (N=21, raio 10) e em geometrias não-radius-3, o que
  corromperia a contagem 2-de-4 e (com `cap>1`) o stake real. **Fix:** threading do `hit_result`
  real (já computado em `message_handler.py:344`) para `on_result`; `c_selection.feedback`
  permanece por distância (avaliação contrafactual). Cobertura: `tests/test_wiring_c_gale.py::
  test_block_gale_uses_real_hit_not_dist_min` + `test_resolve_fallback_to_shadow_when_hit_none`.
  Inerte na config de go-live (`cap=1` trava o nível em 1), mas necessário para correção de
  telemetria e segurança caso o teto suba.

### C. Impacto ISO por característica

- **Adequação Funcional (FS):** + completude/correção — a aposta passa a refletir a tendência
  por sentido (14#) fielmente ao estudo; INV-3 preservado (indicação sempre emitida; gates só
  modulam stake como `min()`, `message_handler.py:678` antes do bloco INV-3:683).
- **Confiabilidade (Rel):** default-safe (flags OFF = byte-idêntico no fluxo de dinheiro),
  motores isolados + defensivos, persistência round-trip (`game.py:1173-1176`↔`1293-1296`),
  reset por dealer (`game.py:337-349`), 38 testes dedicados. `cap=1` elimina ruína.
- **Manutenibilidade (Maint):** + alta coesão/baixo acoplamento (motores em módulos próprios,
  testáveis em isolamento) e 38 testes; **−** `message_handler.py` cresceu ~+200 LOC (agrava o
  gap D.1 — ver Obrigações).
- **Segurança/risco financeiro:** `cap=1` (flat-equivalente) é o único modo sem ruína (estudo:
  gale janela 3/5 uncapped ⇒ ruína 38–78% em banca de 50u). Subir teto é opt-in explícito.

### D. Scorecard — delta backend (17/06)

| # | Característica | 14/06 | 17/06 | Justificativa |
|:-:|---|:---:|:---:|---|
| 1 | Adequação Funcional | 8.7 | **8.8** | cobertura 14# por-sentido fiel ao estudo; INV-3 intacto; 38 testes |
| 5 | Confiabilidade | 8.8 | **8.8** | mantido — nova superfície compensada por gating/defensividade/persistência |
| 7 | Manutenibilidade | 8.7 | **8.7** | motores isolados (+) vs +200 LOC em message_handler (−) se anulam |

> **Nota geral mantém 8.5/10.** O ganho é de capacidade estratégica com risco contido (cap=1),
> não de qualidade estrutural líquida — o débito de tamanho de `message_handler.py` neutraliza o
> ganho de coesão dos motores até a extração modular (Obrigação 8).

### E. Obrigações de manutenção (observar em ciclos futuros)

1. **Flags por-chamada** — `settings.py` lê env a cada decisão (toggle runtime). **Não cachear**
   em módulo; manter o padrão para permitir rollback sem restart.
2. **INV-3 inviolável** — a estratégia SEMPRE indica (`acao=APOSTAR`); qualquer novo modulador de
   stake entra como `min()` e **nunca** suprime a indicação. Posicionar antes/depois do bloco
   INV-3 conforme o piso desejado (`message_handler.py:678` vs `:683`).
3. **block_gale usa HIT REAL** — `on_result` deve receber o resultado real da cobertura, não um
   proxy de distância. Ao tocar `_engine_resolve`, preservar o threading de `hit_result`
   (regressão guardada por `test_block_gale_uses_real_hit_not_dist_min`).
4. **Rollback** — host env (`SDA_BET_PAIR=full` + `SDA_STAKING_MODE=flat`) + redeploy, ou
   `git revert` do `docker-compose.yml`. O deploy faz `git reset --hard origin/main`, então
   flags persistentes vivem no **compose versionado** (não há `.env` no servidor).
5. **`GALE_CAP>1` é opt-in de risco** — só com decisão explícita do operador (ruína 38–78% no
   estudo). Default permanece `1` (flat-equivalente).
6. **Persistência completa** — todo campo novo de motor precisa entrar em `save()` **e** `load()`
   **e** `reset_session()` (round-trip + reset por dealer). Validar com os testes de persistência.
7. **Defensive excepts** — ao adicionar `except Exception`, rodar
   `python tools/lint_silent_except.py --update` (baseline de `tests/test_sp05_safe_except.py`).
8. **Gap D.1 agravado** — `server/message_handler.py` passou de ~1000 para ~1200 LOC (helpers de
   motor). Candidato a extrair para `server/engines_wiring.py` (mixin/serviço) no próximo ciclo
   de refatoração, sem alterar comportamento.
9. **Overlay aditivo** — `c_selection`/`block_gale` no `sugestao`/`state_sync` são campos novos
   ignorados por clientes antigos; manter retro-compatibilidade (não remover/renomear chaves).

> **Evidência de testes:** `tests/test_block_gale.py`, `tests/test_c_selection.py`,
> `tests/test_wiring_c_gale.py` (38 casos) + suíte completa **523 passed, 9 skipped, 1 xfailed**.
>
> **Evidência em produção (17/06 16:52 UTC):** deploy de `31c39c1` (PR #9) recriou o container
> com o env go-live; as decisões caíram de **N=21 → N=14** no boundary do deploy (7123=21 →
> 7124/7125=14), mantendo `centers=3`, `acao=APOSTAR` (INV-3) e `gale_level=1` (cap=1). `/health`
> ok, 0 erros. Detalhe em `implantação_c_variavel_gale_junho.md` §17.7.

---

## ADENDO 17/06/2026 (tarde) — Correção de UX/contrato do front C1-variável (Glass Box)

Auditoria pós-go-live revelou que o **backend** envia a aposta nova (14#, par C1/C2, stake
block_gale) corretamente, mas o **front (Glass Box Dashboard)** ainda operava no contrato antigo:
mostrava `martingale.current_bet` legado com fallback **`R$17` hardcoded**, não exibia o **par**
escolhido nem **veredito red/green** por aposta, e os campos novos (`c_selection`/`block_gale`/
`bet_gate`) só iam no canal `sugestao` — que o dashboard ignora. Diagnóstico completo em
`proposta_atualização_front_c1_variavel.md`.

### A. Capacidades NOVAS com impacto ISO

1. **Fonte única de overlay** (`GameState.engine_overlay_fields()`, `state/game.py`) — deriva
   `c_selection{chosen,pair}` + `block_gale{cw,ccw}` + `bet_gate` + **`ultimo_acerto{slot,green,numero}`**
   do **estado persistente** (engine sempre instanciado, `pending.cs_chosen`, `last_hit_attribution`),
   sem depender do handler. Consumida por `trace` e `state_sync` (canais que o dashboard lê).
2. **Heartbeat com stake real do block_gale** (`server/websocket.py`) — ramo próprio que usa
   `block_gale_engine.stake(dir,N)=base_unit×N×MULT[level]` (cap=1 ⇒ 14u), em vez do `mg.current_bet`
   legado. Fecha a divergência valor-exibido × valor-apostado.
3. **Dashboard alinhado à nova lógica** (`frontend/`) — card mostra **Par** (C1+C3/C2+C3),
   **selo GREEN/RED** do último spin, painel block-gale (`G{level} {bloco}/4`) e o **valor do
   servidor** (fonte única, sem `R$17`). Cache-bust `app.js?v=4.4.0`.

### B. Bugs corrigidos na auditoria (3 bugs nos snippets P0 da proposta, antes de codar)

- **AUDIT-1:** `handler._engine_overlay_fields()` no `state_sync` era inviável — `broadcast_heartbeat()`
  é função **global** (sem `self`/`handler`). → fonte única em `game_state`.
- **AUDIT-2:** adicionar `block_gale` ao ramo de `get_effective_bet` seria **falso fix** — a função
  só desvia `flat`/`kelly`; `block_gale` cairia no fallback `mg.current_bet`. → stake via engine.
- **AUDIT-3:** snippet de front referenciava `data`/`setBetValue` fora de escopo. → `updateBlockGale`
  lê `data.aposta` no `handleStateSync`.

### C. Impacto ISO por característica

- **Usabilidade (Usab):** + o operador passa a ver o **par real**, o **valor correto** e o **veredito
  red/green** — elimina a leitura enganosa (`R$17` ≠ 14u) e a ambiguidade de 3-vs-2 centros.
- **Adequação Funcional (FS):** + paridade de contrato entre os 3 canais WS (`sugestao`/`trace`/
  `state_sync`) para a telemetria dos motores; `ultimo_acerto` expõe a validação que já respeitava 14#.
- **Confiabilidade (Rel):** mantida — tudo **aditivo** (flags OFF = byte-idêntico), `try/except`
  defensivo no `trace`, acessos seguros em `engine_overlay_fields`, **529 passed**.
- **Manutenibilidade (Maint):** + fonte única reduz o risco do ARCH-1 (dois sistemas de gale); + teste
  de contrato (`tests/test_ws_overlay_contract.py`).

### D. Obrigações de manutenção observadas neste ciclo

1. **#7 (defensive excepts)** — 1 novo `except` no `trace` (espelha o do `sugestao`); rodado
   `python tools/lint_silent_except.py --update` (baseline 25→26 em `message_handler.py`).
2. **#9 (overlay aditivo)** — só **adição** de chaves; `sugestao`/extensão intocados; clientes antigos
   ignoram os novos campos.
3. **#1 (flags por-chamada)** — `staking_mode()` lido no heartbeat a cada tick (sem cache).
4. **Escopo deferido** — extensão (`EXT-1/2`) fora desta rodada (working tree sujo do operador);
   extração `engines_wiring.py` (Obrigação #8) segue pendente.

> **Evidência de testes:** `tests/test_ws_overlay_contract.py` (6 casos) + suíte completa
> **529 passed, 9 skipped, 1 xfailed**. Arquivos: `state/game.py`, `server/message_handler.py`,
> `server/websocket.py`, `frontend/{app.js,index.html,style.css}`.

---

## ADENDO 17/06/2026 (noite) — Pivô para par ESTÁTICO C2+C3 + auditoria pós-implantação

> O voto C1/C2 móvel (`var_c1c2_c3`) deu **resultados desfavoráveis** em produção. A aposta passou ao
> **par ESTÁTICO {C2, C3} fixo em toda jogada** (`SDA_BET_PAIR=c2c3`) — o melhor par estático do estudo
> (`resultados_15_junho.md`). Continua **14#**, `block_gale` teto 1, INV-3 e isolamento por sentido.

### A. Mudança com impacto ISO

1. **`CSelectionEngine.static_select(...)`** (`strategies/c_selection.py:252`): par fixo `{C1|C2, C3}`
   via união real (`coverage_numbers`), `chosen` fixo, `freeze_candidates={}` ⇒ **determinístico, sem
   shadow/feedback/promoção**.
2. **`_engine_apply_selection`** (`server/message_handler.py:94-118`) despacha por `SDA_BET_PAIR`:
   `var_c1c2_c3`→voto; `c2c3`/`c1c3`→estático; `full`/inválido→no-op (21#).
3. **`docker-compose.yml`** default `SDA_BET_PAIR=c2c3`; **`settings.py:141`** docstring atualizada.
4. O **motor de voto permanece** no código (rollback/experimento) — só deixa de ser o default.

### B. Auditoria pós-implantação (bug hunt) — 2 frentes

- **Code-review dedicado** (8 pontos: ordem dos centros, resolve/feedback no modo estático, stake
  `cap=1`, persistência/reset, INV-3, outros usos de `var_c1c2_c3`, byte-identidade com `full`,
  fallback) **+ trace próprio**. Rodou a suíte (538) e simulação e2e hit/miss. **0 bugs funcionais.**
- **Correções menores aplicadas:**
  1. Comentário **stale** em `message_handler.py:567` (dizia "gated por var_c1c2_c3"; agora reflete o
     dispatch c2c3/c1c3/var).
  2. Consistência do branch de **fallback morto** de `static_select` (<3 centros): passou a respeitar o
     `pair` (`c1c3`→C1) em vez de fixar C2. Sem impacto em produção (o dispatch faz early-return em
     `<3 centros`), mas elimina inconsistência interna. Regressão: `test_static_fallback_under_3_centers`.
- **Verificado em produção** (servidor 187.45.181.75): env `SDA_BET_PAIR=c2c3`, `static_select` no
  container, decisões pós-deploy **7374–7379 todas N=14**, ambos sentidos, `APOSTAR`, `/health` ok, **0 erros**.

### C. Impacto ISO por característica

- **Adequação Funcional (FS):** a aposta passa ao par estático de maior taxa-base do estudo (C2+C3),
  sem a variância (sem edge) do voto. Ordem dos centros confirmada (`centers[1]=C2`, `centers[2]=C3` em
  `game.py:526-529`, idêntico ao consumido por `static_select`).
- **Confiabilidade (Rel):** o modo estático é **stateless/determinístico** — menos superfície que o voto
  (sem feedback/promoção); `block_gale` segue com o **hit real**; persistência/reset intactos.
- **Manutenibilidade (Maint):** dispatch explícito por flag (3 modos + no-op) + testes; sem crescimento
  relevante de `message_handler.py` (Gap D.1 inalterado).

### D. Scorecard — delta (17/06 noite, vs ADENDO da manhã)

| # | Característica | manhã | noite | Justificativa |
|:-:|---|:---:|:---:|---|
| 1 | Adequação Funcional | 8.8 | **8.8** | troca de política de aposta (estática); corretude inalterada |
| 5 | Confiabilidade | 8.8 | **8.8** | modo determinístico; auditoria (2 frentes) sem bugs |
| 7 | Manutenibilidade | 8.7 | **8.7** | dispatch claro + testes; débito de LOC inalterado |

> **Nota geral mantém 8.5/10** — mudança estratégica de política de aposta, com auditoria limpa.

### E. Obrigações de manutenção (deltas)

1. **Par estático é stateless** — `static_select` não lê/escreve estado do motor; não introduzir efeitos
   colaterais sem necessidade.
2. **`c_attr` segue alimentado** no resolve mesmo no modo estático (deque bounded `maxlen=12`, inócuo) —
   evita cold-start do voto se reativado.
3. **Rollback de regra:** `SDA_BET_PAIR=var_c1c2_c3` (voto) / `c1c3` (par alternativo) / `full` (21#) +
   redeploy. Reversível sem perda.
4. Demais obrigações do ADENDO 17/06 (manhã) seguem válidas (flags por-chamada, INV-3 como `min()`,
   block_gale com hit real, persistência completa, lint de excepts, Gap D.1, overlay aditivo).

> **Evidência de testes:** `tests/test_c_selection.py::TestStaticSelect` (4) +
> `tests/test_wiring_c_gale.py` (c2c3, 2) + suíte completa **538 passed, 9 skipped, 1 xfailed**.

---

## ADENDO 18/06/2026 — force17: C1=ForceLast + geometria 17# (3 regiões) + saída no front

> Evolução da aposta de produção de **c2c3 (14#)** para **force17**: 3 regiões = **17 números** =
> C2(±3,7) ∪ C3(±2,5) ∪ **C1=ForceLast**(±2,5). O front-end mostra os 3 centros rotulados **c2/c3/c1**
> (numerinho embaixo de cada centro), os 17 números apostados a cada jogada, e o reflexo **verde/vermelho
> + sentido** do resultado anterior. Base empírica: `analise_400_junho.md` PARTES VII–XV; spec:
> `implantação_c1_proposta_nova_junho.md`; registro: `implantação_efetuada_17_junho.md`.

### A. Capacidades NOVAS com impacto ISO

1. **`force_select()` + `coverage3()` + `force_last_center()`** (`strategies/c_selection.py`): C1=ForceLast
   1-passo (`WHEEL[(pos(r[-1]) + sdist(r[-2],r[-1])) % 37]`), cobertura 17# pela união real, **isolado por
   sentido**, determinístico/stateless (`freeze={}`). Saída com 3 centros rotulados c2/c3/c1.
2. **Modo `force17`** no enum `SDA_BET_PAIR` (`app_config/settings.py:141`); dispatch em
   `_engine_apply_selection` (`server/message_handler.py`) lendo os 2 últimos `actual_result` do
   `target_direction` (`cw_history/ccw_history[i][1]` — fix B4). Mantém `centers=3`.
3. **Telemetria** `force17{regioes, c1_force, coverage_n, dir_bias}` + `ultimo_acerto{green, direction}`
   nos canais `sugestao` e `trace`/`state_sync` (aditivo, retrocompatível).
4. **Front-end**: overlay da extensão (`content.js`) e dashboard Glass Box (`frontend/`) renderizam as 3
   regiões rotuladas, os 17 números e o veredito verde/vermelho + sentido analisado.
5. **Observabilidade**: gauge `roleta_force17_active`.
6. **Go-live** no `docker-compose.yml` (`SDA_BET_PAIR=${SDA_BET_PAIR:-force17}`).

### B. Bugs corrigidos na auditoria pós-implantação (2 frentes)

- **B1 — cobertura vazia (`sda_numbers=[]`, ~4% das decisões):** bug **pré-existente** bloqueante para
  "apostar a cada jogada". **Fix:** `_ensure_nonempty_coverage()` — após a seleção, se a cobertura ficou
  vazia mas há centros, emite a união (`coverage3` se 3, vizinhança se 1). Agnóstico de modo, dispara só no
  caso quebrado (preserva byte-identidade). Regressão: `TestB1NonEmptyCoverage` (4).
- **Auditoria #1 (10 frentes)** + **#2 (passo-a-passo e2e, SDA17 real, 24 spins):** **0 bugs funcionais**.
  Verificados: fonte/timing/isolamento do ForceLast, alimentação do DB por sentido, consistência
  `green==hit` (slot=miss só com hit=False), persistência sem poluição (`GameState` sem `__slots__`;
  `last_force17_meta` transiente fora do `save()`), INV-3, overlay aditivo, byte-identidade com `full`.
- **Nuances documentadas (não-bugs):** `ultimo_acerto.slot` usa centros geométricos (cosmético; veredito
  correto); ForceLast reaquece pós-reset de dealer; calibração da 1ª oportunidade/sentido = PULAR (INV-3).
- **Auditoria #3 (front-ends + fluxo recepção→retorno, captura live do `sugestao`):** **4 bugs corrigidos** —
  **BUG-F1** (overlay-null na 1ª renderização: `const overlay` não reatribuído após `createOverlay` →
  `TypeError`, não mostrava os números; `content.js`), **BUG-F2** (minimizado mostrava centros geométricos
  em vez de force17; consistência), **BUG-S1** (fallback de calibração deixava `_cs_meta` force17 stale →
  regiões+N=21 incoerentes; `message_handler.py`), **BUG-D1** (canal `trace`/`state_sync` sem `dir_bias`;
  `game.py`). Cadeia server→background→content verificada (sem stripping de campos); `popup.js` não mostra
  sugestões; `overlay.css` sem clip. **Sistema 100% funcional no código** (go-live em produção = próximo deploy).

### C. Impacto ISO por característica

- **Adequação Funcional (FS):** cobertura estruturalmente superior (17# breakeven 47% + C1 balístico de
  menor variância) fiel ao estudo; **B1 corrigido** (a indicação nunca cobre zero números). INV-3 intacto.
- **Confiabilidade (Rel):** force17 stateless/determinístico (sem shadow/feedback); default-safe (`full` =
  byte-idêntico); rede de segurança nunca-vazio; persistência round-trip sem novos campos.
- **Usabilidade (Usab):** salto de UX — 3 regiões rotuladas + 17 números + reflexo verde/vermelho **com o
  sentido**; operador opera e audita em tempo real (overlay + dashboard).
- **Manutenibilidade (Maint):** dispatch explícito (4 modos + no-op) + 19 testes; `message_handler.py`
  ~+45 LOC (Gap D.1 inalterado em natureza).

### D. Scorecard — delta (18/06, vs ADENDO 17/06 noite)

| # | Característica | 17/06 noite | 18/06 | Justificativa |
|:-:|---|:---:|:---:|---|
| 1 | Adequação Funcional | 8.8 | **8.9** | geometria validada (17# + ForceLast) + **B1 corrigido** (indicação nunca-vazia) |
| 4 | Usabilidade | 8.5 | **8.7** | 3 regiões rotuladas + veredito verde/vermelho com sentido (overlay + dashboard) |
| 5 | Confiabilidade | 8.8 | **8.8** | motor stateless/determinístico; 2 auditorias sem bugs funcionais |
| 7 | Manutenibilidade | 8.7 | **8.7** | dispatch claro + 19 testes; débito de LOC estável |

> **Nota geral 8.5 → 8.6/10** — ganho de Adequação Funcional (geometria validada + B1) e Usabilidade
> (saída rica no front), com auditorias limpas. Risco contido (default-safe, reversível por env).

### E. Obrigações de manutenção (deltas)

1. **force17 é stateless** — `force_select` lê `cw/ccw_history[i][1]` (resultado bruto), nunca `c_attr`
   (distâncias). Não introduzir estado.
2. **Rede B1 (`_ensure_nonempty_coverage`)** roda para TODOS os modos — manter agnóstica (só preenche vazio).
3. **Overlay aditivo** (`force17`/`regioes`/`ultimo_acerto.direction`) — não remover/renomear chaves.
4. **Geometria 17# = raios 3/2/2** com overlap **permitido** (não forçar disjunção — piora, PARTE XIV).
5. **Rollback:** `SDA_BET_PAIR=c2c3`/`full` + redeploy, ou `git revert` do compose. Reversível sem perda.
6. **Honestidade:** o edge é **modesto/não-conclusivo** (roda uniforme); a entrega é estrutura +
   instrumentação, não promessa de lucro. O *timing* (esperar um red) é do **usuário**; o motor sugere e mede.
7. Demais obrigações dos ADENDOs 17/06 seguem válidas (flags por-chamada, INV-3 como `min()`, block_gale
   com hit real, persistência completa, lint de excepts, Gap D.1).

> **Evidência de testes:** `tests/test_c_selection.py::TestForceSelect` (11) +
> `tests/test_wiring_c_gale.py::{TestForce17Wiring, TestB1NonEmptyCoverage}` (8) +
> `test_ws_overlay_contract.py` (direction) + suíte completa **557 passed, 9 skipped, 1 xfailed**.

### F. Atualização 18/06 (tarde/noite) — force17-EXATO, realinhamento à UNIÃO e auditoria com servidor real

1. **`SDA_FORCE17_EXACT` (opt-in, default OFF)** — `app_config/settings.py:force17_exact_enabled()` +
   `strategies/c_selection.py:pad_to_n()` + `force_select(target_n=)`. ON completa a cobertura para
   EXATAMENTE 17 (padding dos não-cobertos mais próximos, sem mover centros). **Default OFF = união ~15**,
   pois o estudo (`analise_400` L940) prova que **forçar 17 PIORA o breakeven** (47,2% vs 42,8% da união);
   a sobreposição é **benéfica** (reduz N). Saga: PR #15 (exato ON) → **PR #16 (realinhado a OFF/união)**.
   Levantamento completo em `resposta_estruturada_c1_junho.md`.
2. **Caveat de produto (documentado):** o motor entrega a **COBERTURA** (C1=ForceLast/17# união), **não o
   EDGE**. O lucro do estudo (+2%/+5%) **exige disciplina do operador**: anti-only (horário abster, −EV),
   após-red (driver do edge), stop-loss 15u, parar ~jogada 40. Seguir a sugestão crua nos 2 sentidos ≈ 0%.
3. **Auditoria com acesso ao SERVIDOR REAL (18/06):** SSH `root@187.45.181.75` (host `xmaiajpvm`):
   - **Git:** server HEAD = `8201ffa` (= origin/main = local). Sincronizado. Deploy log: `DEPLOY OK`,
     `HEALTHCHECK ok (try 1)`, `FRONTEND sync ok -> /var/www/roleta`, `NGINX reload ok`, `ALEMBIC 0008 (head)`.
   - **Container:** `roleta-cloud Up (healthy)`, **0 restarts**, **0 erros/tracebacks** nos logs. Health v4.4.1.
     Env: `SDA_BET_PAIR=force17`, **`SDA_FORCE17_EXACT=0`**, `SDA_STAKING_MODE=block_gale`, `GALE_CAP=1`.
     Métrica `roleta_force17_active=1.0`.
   - **Dados reais (decisões pós-deploy ≥ 15:46 UTC):** N varia (12/14/17 — **união ativa**, fix confirmado).
     **Hit real: horário 33,3% · anti 42,0%** — confirma empiricamente o **−EV do horário** do estudo (o
     motor aposta ambos; o operador deve abster no horário).
   - **Stack observabilidade no ar:** roleta-prometheus, roleta-grafana, roleta-alertmanager, roleta-cdc-worker,
     roleta-pg (todos `healthy`). Nota benigna: deploy loga "orphan containers" (gerencia só `roleta-cloud`).
4. **Recomendações operacionais (1 env cada, sem código):** `PROFIT_STOP_LOSS_UNITS=15` (estudo +5,5% vs
   +1,4%); operar janela ~4–40 anti; abster no horário (`dir_bias`).

> **Veredito da auditoria live:** servidor, git e deploy **100% atualizados e funcionais** (HEAD 8201ffa,
> healthy, 0 erros, união ativa). 0 bugs (code-review + fuzz 25k casos). O único "gap" é **operacional/de
> disciplina** (horário −EV + stop-loss 30u frouxo), não de software. Este `Manutenabilidade_iso.md` fica
> atualizado com esta seção F.

---

### G. Atualização 18/06 (noite) — fix do fallback de calibração (17# no front) + auditoria de fluxo (PR #18)

1. **BUG-FRONT #1 (raiz):** o fallback de calibração emitia **21#** em produção (`SDA_FORCE17_EXACT=0`)
   porque o raio estava **acoplado** à flag `force17_exact` — que rege só o padding da aposta NORMAL,
   não o fallback. Fix: `server/message_handler.py` → `_fb_radius = 8 if bet_pair_mode()=="force17" else 10`.
   **Origem:** `b57b62e` (flag default ON) → `0d3c47e` (default OFF p/ união ~15) regrediu o fallback por
   acoplamento. Era o **"3 regiões · 21 números"** que o operador via no front.
2. **Front sincronizado (#2/#3):** a cobertura viaja no meta `force17.numeros` (Glass Box `app.js` e
   extensão lêem da MESMA fonte das regiões, sem `state` stale); header da extensão deriva de
   `regioes.length` (não hardcode "3"). Aditivo/retrocompatível.
3. **Auditoria profunda do fluxo (pós-fix):** 2 subagents `explore` (server-side + staking/contratos) +
   validação manual → **0 bugs novos acionáveis** (candidatos = falsos positivos/by-design;
   `target_direction` está no `state_sync`, isolamento por sentido = `BUG-AUDIT-006 FIX`, etc.).
4. **Testabilidade:** `tests/test_audit_cadence_12_06.py::TestFallbackForce17Radius` (force17→17#,
   c2c3→21# controle) — fecha o gap que mascarava o bug (testes do fallback rodavam em modo default).
5. **Deploy (auditoria com servidor real):** PR #18 → CI verde (3.11/3.12/3.13) → `main` **`246783c`** →
   `roleta-deploy.timer`. Servidor `healthy` (try 1), `DEPLOY OK`, código confirmado no container
   (`message_handler.py:712`), `force17 → N=17` determinístico. Suíte **568 passed**.

> **Nota sobre a auditoria F:** a seção F afirmou "0 bugs" mas validou só as **apostas normais**
> (N=12/14/17, união ativa); o **fallback de calibração** (2ª jogada/sentido) ficou fora do escopo e era
> onde vivia o 21#. A seção G cobre esse caminho. Detalhes completos: `resultados_18_junho.md` (PARTES II–III).

---

### H. Atualização 18/06 (madrugada) — minimizado unificado, rotinas saneadas, métrica `dna_realize_lag`, fluxo 100% + auditoria (PRs #19, #20)

> Ciclo "documentar o fluxo + implantar rotinas p/ 100% funcional + auditoria + graphify".
> Detalhes completos do fluxo e da auditoria end-to-end em `resultados_18_junho.md` (PARTES II–IV).

**Fluxo de uma rodada (recepção → saída), verificado por simulação executável do `MessageHandler`:**
`escuta (MASTER) → novo_resultado {numero,direcao,dealer,...} → connection_manager (role) → SpinInput
(Pydantic) → check_prediction (red/green) → martingale → wheel_dist → update_adaptive → update_result
(pnl, região) → process_spin → save state.json → strategy.analyze → Triple Rate → INV-3 →
_engine_apply_selection (force17 17#) → _ensure_nonempty → QW stake → store_prediction → save_decision
(SQLite) + DNA → broadcast sugestao(→escuta) + trace(→Glass Box) · state_sync 1Hz`. Caminho quente
síncrono; PG/telemetria em fila+worker. **6/6 vínculos de dados OK** (sugestao==trace==Decision;
force17.numeros==numeros; N≠21; 3 regiões).

**1. Front da escuta — minimizado unificado (PR #19 + follow-up):** o quadro minimizado divergia do
aberto e só atualizava ao abrir/fechar — o heartbeat lia `pending_prediction.centers` ([C1,C2,C3])
enquanto o aberto usa `sugestao.regioes` (c2,c3,c1, `c_selection.py:448`). Helper único
`centrosFromSugestao(s)` nos 3 pontos. **Code-review** pegou 1 regressão (cold-start: após reload com
overlay minimizado, `lastSugestao` null → minimizado vazio); corrigida com fallback a
`pending_prediction.centers` **só** no cold-start. `manifest` 3.3.0→3.3.2 (extensão exige reload no browser).

**2. Rotina saneada — serviço systemd legado:** `roleta-cloud.service` (`python3 main.py` direto no
host) estava **failed** desde 17/06 (conflito de porta com o container). Produção roda via
**docker-compose** (`restart: unless-stopped`) + `roleta-deploy.timer`. Desabilitado
(`systemctl disable --now` + `reset-failed`) → **0 failed units**; container segue healthy.

**3. Observabilidade — `dna_realize_lag` corrigido:** o alerta `RoletaDnaRealizeLagHigh` estava
**firing** (falso-positivo, com `calibration_fill_rate_1h=1.0`): a métrica media TODAS as features DNA
sem realize, incluindo **órfãs terminais** (última predição antes de cada reset/troca de dealer, que
nunca realiza) → lag ~23 dias. Agora mede só as features "na ponta" (`id > MAX(id) já realizado`);
órfãs terminais ficam atrás e são excluídas; se o realize travar de fato, as da ponta acumulam e o lag
sobe (sinal preservado). +2 testes (`database/dna_logger.py`, `test_sp29`).

**4. Fluxo 100% funcional (servidor real):** healthy v4.4.1, `master_present=1`, 2 conexões WS, **0
erros**, `calibration_fill_rate=1.0`, wheel_dist p50=3, **fix N=17 confirmado empiricamente** (calib.
pós-deploy id 8049/8050 = 17#; zero 21#). **8 containers healthy** (cloud, cdc-worker, pg, prometheus,
grafana, alertmanager, node/pg-exporter); targets Prometheus 2/2 up.

**5. Auditoria de bugs:** suíte **570 passed** (+4 testes de regressão na sessão); **code-review** das
mudanças → 1 bug real (cold-start, corrigido) + 3 pontos validados corretos; lint = 11 avisos
**cosméticos pré-existentes** (F401/F541/E402, não-bugs, CI verde).

**6. Grafo:** `graphify update .` → `built_at_commit == HEAD`.

> **Veredito:** **100% funcional** — 0 failed units, 0 alertas falsos firing, fluxo íntegro ponta a
> ponta, suíte verde, correções deployadas.

**Scorecard ISO/IEC 25010 — delta:**

| Subcaracterística | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Operabilidade** | ⚠️ 1 serviço systemd failed | ✅ 0 failed units | serviço legado desabilitado |
| **Analisabilidade** (obs.) | ⚠️ alerta dna_lag falso firing | ✅ métrica fiel | exclui órfãs terminais |
| **Adequação funcional** (UI) | ⚠️ minimizado divergia/vazio | ✅ fonte única c2,c3,c1 + cold-start | `centrosFromSugestao` + fallback |
| **Testabilidade** | — | ✅ +4 testes | force17 fallback, dna terminal cobertos |
| **Confiabilidade** | ✅ | ✅ | lógica de aposta inalterada; suíte 570 verde |

---

## ADENDO 21/06/2026 — Estruturação pós-auditoria de visão (3 tiers: extensão + servidor Debian + dados)

> Ciclo "resolver os itens remanescentes da `auditoria_pos_foto_21_junho.md` §7 segundo as convenções deste documento, deixando **os 3 tiers estruturados**" — extensão (cliente), servidor Debian (engine Python) e dados/backfill. **Tudo atrás de flags default OFF (rollback trivial), testado, retro-compatível, sem alterar comportamento de aposta.**
> Veredito da auditoria: o encanamento `foto→dados` está **íntegro**; o que faltava era **higiene + cobertura**, não arquitetura.

### A. Capacidades NOVAS com impacto ISO (todas flag-gated, default OFF)

1. **Extensão — provider sem `host:*` na ORIGEM (BUG-1 raiz, v3.4.1):** `extension/deal_capture.js` ganhou o helper PURO/UMD `normalizeProvider(host, raw)` (`matchHostBrand`) que recupera a marca pelo domínio do iframe (`evo-games → evolution`) e, se não reconhece, emite `'unknown'` — **nunca** `host:<domínio>`. Mata na fonte a poluição de `decisions.provider` por frames de analytics (googletagmanager/doubleclick/youtube) e pelo próprio dashboard. Espelha o guard server-side (`models/input.py sanitize_provider`, ciclo anterior). Manifest **3.4.0→3.4.1** (extensão exige reload no browser). IIFE com guard de ambiente (no-op sob node → testável).
2. **Servidor — dealer fill-forward por sessão (maior ROI de cobertura):** `core/dealer_fill.py` (lógica pura `resolve_dealer`) + wiring no `MessageHandler` (`_resolve_spin_dealer`/`_remember_dealer`). Propaga o ÚLTIMO dealer real da MESMA sessão para os giros que chegam sem dealer; **corta na troca** de dealer (real novo substitui) e de sessão (reset zera). Também aprende o dealer do **OCR** (`handle_foto_frame`). Flag `SDA_DEALER_FILL_FORWARD` (OFF). É **metadata** — não toca aposta.
3. **Servidor — hardening da associação foto→decisão:** `update_last_vision` aceita janela máxima opcional `SDA_VISION_ATTACH_MAX_AGE_S` (default **0 = sem limite**, byte-idêntico). Se >0, a foto/OCR só cola na última decisão se ela é recente (anti contaminação do giro seguinte quando o OCR atrasa).
4. **Servidor — consumidor DORMANTE `dealer_force_profile`:** `strategies/dealer_force_profile.py` (espelha `dealer_offset.py`), devolve perfil de força por `dealer×sentido(×modelo)` com gate `n≥30`. **Não wired** no caminho quente (como `region_bandit`); fundação para "estratégias futuras organizadas por dealer". Flag `SDA_DEALER_FORCE_PROFILE` (OFF).
5. **Dados — tool de canonização `tools/backfill_wheel_model.py`:** recanoniza variantes legado de `wheel_model` (`Roleta aoVivo`/`RoletaaoVivo` → `Roleta ao Vivo`) usando a MESMA função de runtime (`vision_ocr._norm_model`). Dry-run default; `--apply` é prod-write (aprovação). Idempotente.
6. **Debian — flags versionadas no compose:** as 3 flags novas entram em `docker-compose.yml` com default OFF (ISO obrig. #4: flags persistentes vivem no compose versionado, rollback sem `.env`).

### B. Bugs/correções e validação

- **Lint silent-except (ISO obrig. #7):** `dealer_force_profile.py` adicionou 1 `except Exception` defensivo (idêntico ao `dealer_offset.py`) → baseline `.silent_except_baseline.json` atualizado via `tools/lint_silent_except.py --update` (12 arquivos, lint OK).
- **Teste de regressão (auto-captura):** o time-bound provou via teste que uma decisão antiga NÃO é sobrescrita (mantém `dealer='unknown'` default) quando `SDA_VISION_ATTACH_MAX_AGE_S>0`.
- **Suíte:** **640 passed**, 9 skipped, 1 xfailed (+25 testes nesta entrega, em 5 arquivos novos). Backfill validado em dry-run no DB local (0 candidatos — o legado vive em produção, esperado).

### C. Impacto ISO por característica

| Subcaracterística | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Adequação funcional** (dados) | ⚠️ `provider` poluído com `host:*` na origem | ✅ marca\|unknown na origem (extensão) + guard server | BUG-1 fechado nos 2 lados |
| **Confiabilidade** (associação) | ⚠️ foto cola sempre na `MAX(id)` (racy) | ✅ janela opt-in anti cross-spin | `SDA_VISION_ATTACH_MAX_AGE_S` |
| **Manutenibilidade** (cobertura) | ⚠️ dealer só nos giros com foto (~1%) | ✅ fill-forward por sessão (opt-in) | `core/dealer_fill.py` puro + wiring |
| **Manutenibilidade** (analytics) | — | ✅ fundação `dealer_force_profile` (dormante) | consumidor testado, gate n≥30 |
| **Testabilidade** | — | ✅ +25 testes (pura+DB+node) | 5 arquivos novos |
| **Portabilidade/Operabilidade** | — | ✅ flags no compose (rollback) | ISO obrig. #4 |
| **Confiabilidade** (aposta) | ✅ | ✅ | **lógica de aposta inalterada**; suíte 640 verde |

### D. Obrigações de manutenção (deltas deste ciclo)

1. **Flags default OFF** — `SDA_DEALER_FILL_FORWARD`, `SDA_DEALER_FORCE_PROFILE`, `SDA_VISION_ATTACH_MAX_AGE_S` seguem o padrão por-chamada de `settings.py` (não cachear; rollback sem restart). Ligar só após validar cobertura/ramp-up.
2. **Fill-forward é metadata** — `_resolve_spin_dealer` nunca pode influenciar predição/stake (só preenche `decisions.dealer`). Se um dia o dealer virar input de aposta, re-auditar este caminho.
3. **`dealer_force_profile` dormante** — ativá-lo (wire no caminho quente) muda apostas; exige decisão explícita + `n≥30` real, medido pelo template `decision_dna` (lift estimado vs realizado) antes de confiar.
4. **Extensão exige reload** — qualquer mudança em `extension/` requer bump de `manifest.version` (feito: 3.4.1) + reload no Chrome (client-side não vai por docker).
5. **Backfill `--apply` é prod-write** — rodar `tools/backfill_wheel_model.py --apply` em produção exige aprovação (mesma classe do backfill SP-02).

### E. Pendências gated por aprovação (NÃO executadas)

- **Deploy no servidor Debian** (subir os fixes do tier servidor) e **reload da extensão v3.4.1** — prod/client writes.
- **`backfill_wheel_model.py --apply`** no DB de produção (~62 linhas legado) — prod-write.
- **Publicar no GitHub** (a PR #21 foi mergeada vazia; os fixes vivem no local) — write no remoto.

> **Veredito:** os **3 tiers ficam estruturados** (extensão limpa na origem, servidor com fill-forward + hardening + consumidor dormante, dados com tool de canonização + flags versionadas), **sem mudar comportamento de aposta** e com suíte **640 verde**. Restam apenas ações de publicação/deploy gated por aprovação.

---

## ADENDO 22/06/2026 — Pipeline de visão "foto→dados" 100% acoplado, limpo e autoritativo (deployado)

> Ciclo de auditorias + sprints que **deployou** a visão como fonte **autoritativa** de `dealer`/`mesa`/`provider` por jogada, **acoplada a 100%** e **higienizada**. Premissa do dono: *"o DOM nunca extraiu dealer/provider/modelo; a foto extrai a cada jogada — organize tudo acoplado para dados 100% auditáveis para estratégia."* Detalhes em `auditoria_pos_foto_21_junho.md` (§11-15) e `resultados_bancos_junho.md` (§1-10). **Tudo deployado e verificado em produção** (HEAD `45d0779`).

### A. Capacidades NOVAS com impacto ISO

1. **Extensão v3.4.1→v3.4.2 — provider limpo na ORIGEM:** `deal_capture.js` ganhou `normalizeProvider`/`matchHostBrand` (recupera a marca do domínio ou `unknown`, **nunca** `host:*`) e `hasUsefulSignal` (frame de analytics, sem sinal real, **não publica** `dealMeta` → não vence a corrida e não sobrescreve `evolution`). Helpers PUROS/UMD testáveis; IIFE com guard de ambiente (no-op sob node).
2. **Vision-context fill-forward UNIFICADO (dealer+modelo+provider) — LIGADO em produção:** `_apply_vision_context`/`_remember_vision` (server) + `core/dealer_fill.resolve_value` (puro) propagam o ÚLTIMO OCR da sessão a **TODA** jogada. Cobertura de `dealer`/`modelo` de **~12% → ~100%/sessão**. Flag `SDA_DEALER_FILL_FORWARD=1` no compose (metadata — **não toca aposta**). `vision_source='vision'` segue marcando foto fresca (medido vs herdado → usar `vision_confidence`).
3. **MESA pela FOTO:** `dealer_table` agora vem do **OCR** (= `wheel_model`) com fill-forward; o DOM (que trazia `'Blackjack Silver D'` errado numa roleta) foi **descartado**. `update_last_vision` também carimba `dealer_table`.
4. **Phantom dedup (`SDA_DEDUP_PHANTOM`, default OFF):** `is_duplicate_spin` rejeita re-envio do **mesmo número+sentido** dentro de uma **janela** (`SDA_DEDUP_PHANTOM_WINDOW_MS`, 20s) — a extensão re-detecta o DOM estático e reenvia (1-7s; ciclo real ~42-48s), o que o engine processaria como giro real **corrompendo a cadeia de predição/aposta** (~17% dos giros). Discriminador = **TEMPO** (não a força — `força=0` é só a distância na roda de nº repetido).

### B. Bugs corrigidos na auditoria (pós-reload da extensão + auditoria reversa)

| # | Bug | Correção |
|---|---|---|
| BUG-1 | `provider=host:*` (analytics/dashboard) na origem | `normalizeProvider` (extensão v3.4.1) + `sanitize_provider` (server, ciclo 21/06) |
| BUG-5 | frame de analytics sobrescrevia `provider` com `unknown` | `hasUsefulSignal` (extensão v3.4.2): sem sinal real não publica `dealMeta` |
| BUG-6 | self-capture `'Roletacloud'` (sem espaço) escapava | `_is_self` normaliza (remove não-alfanumérico) antes do match |
| BUG-A | **mesa** do DOM errada (`'Blackjack Silver D'`) | `dealer_table` = mesa do OCR (fill-forward); DOM descartado |
| BUG-B | **dealer-lixo** de OCR (`'/CROUPIEREEXPERIMENTE(E)'`) propagado | `_clean_dealer`: valida plausibilidade (1-2 palavras de letras, 2-16 chars, sem rótulos) → `None` se lixo |
| (cobertura) | `dealer`/`modelo` só em ~12-17% das jogadas | vision-context fill-forward unificado → ~100%/sessão |

### C. Impacto ISO por característica

| Subcaracterística | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Adequação funcional** (dados) | ⚠️ mesa errada (DOM), dealer-lixo, host:*, cobertura ~12% | ✅ mesa da foto, dealer limpo, provider limpo, ~100%/sessão | BUG-A/B/1/5/6 + fill-forward |
| **Confiabilidade** (cadeia de predição) | ⚠️ ~17% giros fantasma corrompiam | ✅ dedup por janela (opt-in) | `SDA_DEDUP_PHANTOM` (flag OFF) |
| **Manutenibilidade/Analisabilidade** | ⚠️ não auditável por dealer/mesa na maioria | ✅ 4 dimensões por jogada (dealer/mesa/provider/força) | acoplamento 100%/sessão |
| **Testabilidade** | — | ✅ +~20 testes (fill-forward, dedup, mesa, plausibilidade, deal_capture) | suíte **651** |
| **Confiabilidade** (aposta) | ✅ | ✅ | **lógica de aposta inalterada** (visão é metadata; dedup é flag OFF) |

### D. Evidência de produção (verificada)
- **Deploys** (deploy_pull.sh, rollback automático): `c57c853` → … → **`45d0779`**, container healthy, `/health=ok`, `ALEMBIC 0009 head`, 0 erros.
- **Mesa pela foto:** jogadas 9237-9240 = `dealer_table='Roleta ao Vivo'` (4/4), **0** `Blackjack`.
- **Fill-forward provado:** log da decisão 9194 = `[FOTO] dealer=None`, mas a linha gravou `dealer='THEO'` (herdado) → propagação funcionando; corte na troca de sessão confirmado.
- **Verificação operacional (`resultados_bancos_junho.md` §10):** últimas 40 jogadas → `dealer` 40/40, `mesa` 40/40 (`Roleta ao Vivo`, 0 Blackjack), `provider` 40/40 `evolution`, **0 dealer-lixo**; **últimas 20 rodadas 100% OCR fresco**, o resto coberto por fill-forward.

### E. Obrigações de manutenção (deltas deste ciclo)
1. **`SDA_DEDUP_PHANTOM` é flag OFF a validar** — toca o caminho de aposta. Os dados mostram que ligar é seguro (ciclos reais ≥42s ≫ janela 20s); decisão do operador.
2. **`SDA_DEALER_FILL_FORWARD=1` é metadata** — preenche `dealer`/`mesa`/`provider`, **nunca** influencia predição/stake. Se um dia o dealer virar input de aposta, re-auditar este caminho.
3. **`vision_source='vision'` = foto fresca** (≥1 campo medido); campos individuais podem ser **medidos ou herdados** (fill-forward) → usar `vision_confidence` para confiança por-jogada.
4. **Mesa = `wheel_model` (OCR)** — para Evolution a mesa e o modelo coincidem; se entrar provider com mesa ≠ modelo, separar os campos.
5. **Feature store PG (gap não-bloqueante):** `cw/ccw.spin_features` tem as colunas de visão (migração 0009) mas o publisher não as preenche e `DUAL_WRITE_PG` está OFF — o **SoT SQLite basta** para análise. Se migrar a análise para o PG, ligar `DUAL_WRITE_PG=1` + mapear `dealer/dealer_table/wheel_model/vision_*` no publisher do outbox.
6. **Dealer plausibilidade** — `_clean_dealer` rejeita nomes >2 palavras / com não-letras / rótulos. Se aparecer um nome real legítimo rejeitado, afinar a regra (hoje o risco é baixo e o fill-forward cobre).

> **Veredito:** a visão **foto→dados** está **deployada, acoplada a 100%/sessão e limpa** — cada jogada identifica `dealer`+`mesa`+`provider`+`força` (auditável para estratégia), **sem alterar a lógica de aposta**, suíte **651 verde**. O dedup de fantasmas e o dual-write do PG ficam como itens opt-in documentados.

---

## ADENDO 25/06/2026 — Sincronismo de Fase do Sentido (SPR-DIR1..DIR8, branch `spr/sentido-fase`, tudo default-OFF)

> Ciclo que reescreve o controle do **sentido do giro** (horário↔anti-horário) tratando-o como o que ele é: uma **FASE alternada**. A roleta gira **um sentido por vez**; o sentido **não é lido** do site — o operador informa a fase **uma vez** e o sistema **alterna**. Premissa do dono: *"hoje não temos como ler o sentido… a lógica de troca automática é porque a roleta opera uma jogada em cada sentido… deve resincronizar de forma estruturada… a estrutura para receber o módulo de vídeo deve funcionar stand-by para acoplar depois."* Proposta completa: `evolução_sentido.md` (rev. 4 auditada). **Entregue em branch + PR, NÃO em produção.** Suíte **684 verde** (flags OFF e TODAS ON).

### A. Capacidades NOVAS (8 sprints, cada uma atrás de flag default-OFF na compose)

1. **DIR1 — cliente sobrevive/reconcilia/conta (extensão v3.6.0):** re-hidrata `currentDirection` do storage no boot do SW (perda ao minimizar); consome `state_sync.target_direction`/`sentido.next_direction` no resync pós-(re)conexão; conta giros por **shift local** (`countNewSpins`) — corrige o gap quando k>1, idêntico quando k=1; reseta a fase no `sessao_resetada`. Client-side (reload manual no Chrome).
2. **DIR2 — histórico NÃO-DIRECIONAL (`SDA_HISTORICO_NAO_DIRECIONAL`):** `register_history_number` popula só `recent_results` (zona fria C3) sem alimentar `timeline_cw/ccw` com a direção **fabricada** do histórico (que envenenava o SDA17).
3. **DIR3 — fundação (`SDA_SENTIDO_AUTORITATIVO` telemetria):** `state/phase.py` (projeção pura `fase(n)=seed XOR ((n-seed_n)%2)`); `GameState` ganha `spin_seq`/`seed_parity`/`seed_n`/`direction_source`/`direction_locked` com **round-trip** (save+load+reset_session); `SpinInput`/`Decision` ganham campos opcionais; **migração SQLite aditiva** (5 colunas em `decisions`, snapshot atualizado).
4. **DIR4 — reconciliação por SHIFT (`SDA_PHASE_RECONCILE`):** o servidor passa a **consumir `allNumbers`** (12 últimos que o cliente já enviava e o servidor ignorava) e conta os giros reais; k>1 = **gap recuperado** (avança a fase pelos giros perdidos); sem alinhamento → `phase_uncertain`.
5. **DIR5 — fase autoritativa no canal existente (`SDA_SENTIDO_AUTORITATIVO`):** bloco `sentido{last_seq,last_direction,next_direction,locked,source,resync_advised,stats}` publicado via `engine_overlay_fields()` → aparece no **state_sync (1s)** e na sugestão, **sem mensagem WebSocket nova**; autoridade com **auto-seed** (ancora na 1ª direção, projeta determinística, imune a gaps); cliente sobrescreve a paridade.
6. **DIR6 — idempotência (`SDA_DEDUP_SEQ`):** dedup por `trace_id` (janela 64) supera numero+dir+ms; `resync_advised` no bloco sentido re-arma a reconciliação do cliente em gap/troca de mesa.
7. **DIR7 — fusão de fontes / vídeo STAND-BY (`SDA_DIRECTION_VISION`, default OFF):** `fuse_direction` (prioridade operator>vision>toggle + threshold de confiança) + handler `direction_event` — **ponto de acoplamento do futuro serviço de vídeo, inerte enquanto a flag estiver OFF** (atende a premissa #1 do dono).
8. **DIR8 — UX seed + observabilidade:** `handle_set_seed` (operador ancora a fase 1×, re-ancoragem persistida); `state/phase_metrics` (`gap_recuperado_total`/`phase_uncertain_total`/`direction_divergence_total`) publicado em `sentido.stats` em tempo real (e pronto p/ Prometheus).

### B. Bugs estruturais que motivaram (auditados no código, rev. 1→4)

| # | Bug | Correção (sprint) |
|---|---|---|
| #1 | `currentDirection` (global do SW MV3) perde-se ao minimizar; não re-hidratado no boot | DIR1 (re-hidrata + resync) |
| #G | Gap de fase: cliente processava só `newNumbers[0]` e alternava 1× mesmo com k>1 giros | DIR1 (shift local) + DIR4 (shift no servidor) |
| #H | `allNumbers` enviado mas ignorado pelo servidor (munição de reconciliação desperdiçada) | DIR4 (consome allNumbers) |
| #A | Histórico com direção **fabricada** alimentava `timeline_cw/ccw` (envenenava o motor) | DIR2 (não-direcional) |
| #2 | Servidor passivo: derivava a fase do cliente e não a tornava autoritativa | DIR5 (autoridade + auto-seed) |
| #C | Reset de dealer zerava `last_direction` no servidor mas não no cliente | DIR1 (reset no cliente) + DIR3 (re-ancora seed) |
| #D | Handoff de master injetava a fase default do novo master | DIR5 (autoridade no servidor) |

### C. Impacto ISO por característica

| Subcaracterística | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Adequação funcional** (sentido) | ⚠️ paridade volátil/defasada (dois no mesmo sentido) | ✅ fase determinística reconciliada (flag) | DIR1/DIR4/DIR5 |
| **Confiabilidade** (motor) | ⚠️ timelines envenenadas por direção fabricada do histórico | ✅ histórico não-direcional (flag) | DIR2 |
| **Confiabilidade** (recuperação) | ⚠️ minimizar/handoff dessincronizava sem volta | ✅ resync por state_sync + idempotência | DIR1/DIR5/DIR6 |
| **Compatibilidade/Extensibilidade** | — | ✅ vídeo acoplável stand-by (sem refatorar cliente) | DIR7 |
| **Manutenibilidade/Testabilidade** | — | ✅ +34 testes; lógica de fase 100% pura | `state/phase.py`, `tests/test_dir*` |
| **Confiabilidade** (aposta, flags OFF) | ✅ | ✅ | **byte-idêntico** com tudo OFF (suíte 684 verde OFF e ON) |

### D. Obrigações de manutenção / Rollback

1. **Tudo default-OFF** no `docker-compose.yml`; ligar **gradualmente** e na ordem: DIR2 (motor limpo) → DIR3 (telemetria) → DIR4 (reconciliação) → DIR5 (autoridade) → DIR6. DIR1 é client-side (reload da extensão v3.6.0). DIR7/DIR8 conforme o vídeo/UX.
2. **`SDA_SENTIDO_AUTORITATIVO=1` muda `direcao`** (passa a derivar a fase) — valida em sombra pela divergência (`direction_divergence_total`) antes de confiar; **auto-seed** ancora na 1ª direção (re-ancorável pelo operador via `set_seed`).
3. **INV-3 preservado:** `phase_uncertain` **nunca** suprime a indicação — no máximo aguarda (como a calibração). A fase só decide **para qual lado** apostar.
4. **Migração aditiva** (5 colunas nullable em `decisions`); o rollback de deploy não faz downgrade — compatível.
5. **Rollback:** qualquer flag a `0` + redeploy restaura o comportamento atual byte-a-byte; ou `git revert` dos commits SPR-DIR*. A extensão volta por `manifest.version` anterior + reload.
6. **Vídeo (stand-by):** o serviço futuro só precisa enviar `{type:'direction_event', direction, confidence}` e ligar `SDA_DIRECTION_VISION=1`; nenhuma outra mudança no servidor.

> **Veredito:** o eixo de sentido passa a ter **fonte de verdade no servidor**, fase **determinística** ancorada em (seed, n), **reconciliação por shift** usando os últimos resultados que já trafegavam, e **resync** estruturado em reconnect/handoff/reset — tudo **aditivo, atrás de flags default-OFF**, com a estrutura de **vídeo stand-by** pronta. **Entrega por PR** (não toca `main`/produção). Suíte **684 verde** (OFF e TODAS ON).

---

## ADENDO 25/06/2026 (tarde) — SPR-DIR16: FIX CRÍTICO #S/#W/#X (reset/reancoragem completa de fase)

> Auditoria pós-implantação de `evolução_sentido.md` rev. 4 (PR #25+#26) detectou **bug de aposta no lado errado em handoff de dealer/mesa**. Proposta consolidada: `evolução_sentido_25.md` (rev. 5). Esta é a 1ª sprint residual: P0 crítica, atrás de `SDA_RESET_REANCORA` (default OFF byte-idêntico; ON na compose de produção). Suíte **693 verde** (OFF e ON). Entregue por PR.

### A. Bug auditado (verdade estruturada)

| # | Sev | Bug (HEAD `0dca93d`) | Evidência |
|---|---|---|---|
| **#S** | 🔴 | `reset_session` zera `spin_seq=0`/`seed_n=0`/`direction_source="reset"` mas **MANTÉM `seed_parity`** da mesa anterior. Auto-seed da DIR5 (`if not _gs.seed_parity:` em `message_handler.py:726`) **falha** porque a string é truthy → `project_phase` segue projetando com paridade antiga até alguém chamar `set_seed`. | `state/game.py:373-375` zerava 3 de 5 campos |
| **#W** | 🟠 | `handle_history_correction` reseta timelines/recent_results/last_* mas NÃO toca fase. Cliente DIR1+ chama `set_seed` separado; legados ficam inconsistentes. | `message_handler.py:1349-1386` |
| **#X** | 🟠 | `handle_history_correction` (e `handle_initial_history`) reprocessam histórico sem incrementar `spin_seq` — `process_spin` não toca em `spin_seq` (só `handle_new_result` em `:762` incrementa). Resultado: timeline com N spins, `spin_seq=0` → projeção desalinhada. | `state/game.py:382-414` |

### B. Correção (passo concreto, atrás de flag)

- **`app_config/settings.py`** — novo helper `reset_reancora_enabled()` (default OFF; ON via `SDA_RESET_REANCORA=1`).
- **`state/game.py:reset_session` (`:371-385`)** — quando flag ON e NÃO `direction_locked`: zera `seed_parity=""`, `last_phase_uncertain=False`, `last_direction_event=None`. Reativa o auto-seed no 1º giro pós-reset.
- **`server/message_handler.py:handle_history_correction` (`:1374-1383`)** — após o loop de reprocessamento: `spin_seq=count` (alinha com timeline); se não locked, zera `seed_parity` e `seed_n`.
- **`server/message_handler.py:handle_initial_history` (`:1334-1344`)** — mesmo tratamento.
- **`docker-compose.yml`** — `SDA_RESET_REANCORA=${SDA_RESET_REANCORA:-1}` (ATIVADO em produção; rollback `=0` + redeploy).

### C. Testes novos (`tests/test_dir16_reset_reancora.py`)

| Teste | Cobertura |
|---|---|
| `test_flag_default_off` | Helper retorna False default; True com env=1. |
| `test_reset_zera_seed_parity_quando_flag_on_e_nao_locked` | **#S**: com flag ON + lock OFF → `seed_parity=""`, `last_*` zerados. |
| `test_reset_preserva_seed_parity_quando_locked` | Lock explícito do operador sobrevive ao reset (roleta física segue alternando). |
| `test_reset_legado_off_mantem_seed_parity` | **INV ADITIVO**: flag OFF restaura comportamento byte-idêntico ao pré-DIR16. |

### D. Conformidade ISO (impacto)

| Subcaracterística | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Adequação funcional** (sentido em handoff) | ⚠️ aposta no lado errado da mesa anterior | ✅ auto-seed reanchora em ≤1 giro | DIR16 #S |
| **Confiabilidade** (correção histórica) | ⚠️ `correcao_historico` deixava fase órfã | ✅ `spin_seq` + `seed_parity` alinhados | DIR16 #W/#X |
| **Manutenibilidade/Testabilidade** | — | ✅ +4 testes (`test_dir16_*`); flag opt-in preserva 15 testes legados | gateado |

### E. Obrigações / Rollback

1. **Flag default ON na compose** após validação local (suíte 693 verde OFF e ON); rollback por `SDA_RESET_REANCORA=0` + redeploy ou `git revert`.
2. **INV-3 intacto:** este sprint não toca decisão de aposta — só corrige projeção de fase.
3. **Migração:** N/A (campo em memória/JSON; round-trip já testado em DIR3).
4. **Cliente:** N/A (servidor-only); `manifest.version` segue 3.6.0.

> **Veredito:** o vetor crítico de aposta no lado errado em handoff é fechado. Próximas sprints residuais (DIR17/DIR9/DIR11/DIR12/DIR10/DIR13/DIR14/DIR18/DIR15/DIR19) entram em paralelo após validação 24h. Plano: `evolução_sentido_25.md` rev. 5.

---

## ADENDO 25/06/2026 (tarde-2) — SPR-DIR17: FIX #T (reancora seed em phase_uncertain)

> Continuação da auditoria pós-implantação. Sprint P1 que fecha o vetor secundário de divergência persistente em troca de mesa silenciosa. Atrás de `SDA_UNCERTAIN_REANCORA` (default OFF byte-idêntico; ON na compose de produção). Suíte **699 verde** (OFF e ON).

### A. Bug auditado

| # | Sev | Bug (HEAD `4c4f541`) | Evidência |
|---|---|---|---|
| **#T** | 🟠 | Quando `phase_advance` retorna `matched=False` (troca de mesa silenciosa), `message_handler.py:711-715` apenas loga warning + incrementa `phase_uncertain_total` + seta `resync_advised=true`. NÃO reanchora. `spin_seq += 1` (linha 762) corre incondicionalmente. `project_phase` em `:732` segue usando `(seed_parity_antigo, seed_n_antigo, spin_seq_novo)` → direção autoritativa errada por N giros até cliente ver `resync_advised`. | combinado com #S resolvido em DIR16, ainda persistia |

### B. Correção (atrás de flag)

- **`app_config/settings.py`** — novo helper `uncertain_reancora_enabled()` (default OFF; ON via `SDA_UNCERTAIN_REANCORA=1`).
- **`server/message_handler.py:711-720`** — após `logger.warning`, quando flag ON e NÃO `direction_locked`: `seed_parity=""`, `seed_n=spin_seq` (marca "ponto zero" novo).
- **`docker-compose.yml`** — `SDA_UNCERTAIN_REANCORA=${SDA_UNCERTAIN_REANCORA:-1}` (ATIVADO em produção; rollback `=0`).

### C. Testes novos (`tests/test_dir17_uncertain_reanchora.py`, 6 testes)

| Teste | Cobertura |
|---|---|
| `test_flag_default_off` | Helper retorna False default; True com env=1. |
| `test_phase_advance_uncertain_quando_sem_alinhamento` | Sanity DIR4: shift sem overlap → `uncertain=True`. |
| `test_reconcile_shift_alinhado` | Sanity DIR4: shift normal (k=1) → `matched=True`. |
| `test_lock_total_preserva_seed_em_uncertain` | Lock do operador sobrevive a `uncertain`. |
| `test_reancora_em_uncertain_quando_flag_on` | **#T**: flag ON + lock OFF → `seed_parity=""`, `seed_n=spin_seq`. |
| `test_flag_off_mantem_comportamento_legado` | INV ADITIVO: flag OFF preserva comportamento atual. |

### D. Conformidade ISO (impacto)

| Subcaracterística | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Adequação funcional** (sentido em troca silenciosa) | ⚠️ direção autoritativa errada por N giros | ✅ auto-seed reanchora em ≤2 giros | DIR17 #T |
| **Confiabilidade** (autorrecuperação) | ⚠️ dependia de cliente ver `resync_advised` | ✅ servidor reanchora sozinho | DIR17 |

### E. Obrigações / Rollback

1. **INV-3 intacto:** `spin_seq += 1` continua executando (auditoria), só o `seed_parity` é zerado.
2. **`direction_locked` preservado:** lock do operador (DIR8/futuro DIR13) impede a reanchoragem automática.
3. **Rollback:** `SDA_UNCERTAIN_REANCORA=0` + redeploy ou `git revert`.

> **Veredito:** vetor secundário de divergência persistente fechado. Junto com DIR16, a fase autoritativa agora se autocorrige em ≤2 giros em qualquer transição (handoff, troca silenciosa, correção). Próxima: DIR9 (sentido em sugestao).

---

## ADENDO 25/06/2026 (tarde-3) — SPR-DIR9: bloco `sentido` no canal `sugestao` (fix #J)

> Sprint P1 sem flag (aditivo puro). Cliente recebe o bloco autoritativo da fase no canal por-giro, não só no `state_sync` (1 s). Suíte **701 verde**.

### A. Bug #J auditado
`message_handler.py:357,1270` — `_engine_overlay_fields()` privado retorna `c_selection/force17/block_gale/bet_gate/ultimo_acerto`, **não** `sentido`. Resposta `sugestao` saía sem fase autoritativa; cliente etiquetava overlay com fase 1 tick atrasada (até o próximo `state_sync`).

### B. Correção
- **`server/message_handler.py:1268-1278`** — após `self._engine_overlay_fields()` (handler), unir com `self.game_state.engine_overlay_fields()` (gamestate). Fontes COMPLEMENTARES (handler tem `_cs_meta/_bg_meta`; GameState tem `sentido`).
- Sem flag (campo já existia no `state_sync`; só estamos copiando para o `sugestao`). Aditivo.

### C. Testes novos (`tests/test_dir9_sentido_na_sugestao.py`, 2 testes)
| Teste | Cobertura |
|---|---|
| `test_engine_overlay_fields_inclui_sentido` | Bloco `sentido` na fonte única (`GameState.engine_overlay_fields`). |
| `test_overlay_uniao_complementar` | Handler + GameState formam união disjunta. |

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Adequação funcional** (latência fase ↔ overlay) | ≤1 s (state_sync) | ≤ tick do giro (sugestao) |
| **Manutenibilidade** | 2 fontes ambíguas | 2 fontes COMPLEMENTARES (documentadas) |

### E. Rollback
`git revert` deste PR. Sem flag necessária (cliente antigos já ignoram campos desconhecidos).

> **Veredito:** completude do canal por-giro. Próximas P1: DIR11 (Alembic) + DIR12 (/metrics) em paralelo.

---

## ADENDO 25/06/2026 (tarde-4) — SPR-DIR11: migração Alembic 0010 retroativa (fix #L)

> Sprint P1. Fecha gap metodológico #L: as 5 colunas DIR3 (`spin_seq`, `direction_source`, `direction_confidence`, `direction_next`, `phase_uncertain`) que viviam em SQLite via fallback in-loco agora têm migração Alembic formal para o PG espelho. Aditivo, idempotente. Suíte **701 verde**.

### A. Bug #L auditado
`migrations/versions/` parava em `0009_vision_features.py` (19/06). As 5 colunas DIR3 em `decisions` (SQLite) eram criadas via `sqlite_repo.py:372-380` no boot (try/`SELECT`/except/`ALTER`). Funcional, mas:
- Sem migração Alembic → desenvolvedor que rodasse `alembic upgrade head` em PG zero-state ficava sem espelho.
- `schema_parity_manifest.json` não listava `spin_seq`/etc. em `must_propagate_to_pg` → quebrava uniformidade metodológica.

### B. Correção
- **`migrations/versions/0010_dir3_phase_columns.py`** — `ADD COLUMN IF NOT EXISTS` para as 5 colunas em `cw.spin_features` e `ccw.spin_features` (mesmo padrão de 0007/0009). Index em `spin_seq` para debug temporal. `downgrade()` mantém colunas (INV ADITIVO; só remove índice).
- **`database/schema_parity_manifest.json`** — adicionadas as 5 colunas em `must_propagate_to_pg.decisions`. O `test_schema_parity` (`tests/test_schema_parity.py`) valida o casamento — segue verde.
- **`sqlite_repo.py:372-380`** permanece como **fallback** para SQLite local (idempotente, sem mudança).

### C. Validação
- Suíte **701 verde** (sem regressão).
- `test_schema_parity.py` passa (as 5 colunas estão alinhadas SQLite↔PG manifest).
- DB PG zero-state: `alembic upgrade head` cria as 5 colunas em ambos os schemas (não testado em deploy ainda; rollback por `git revert`).

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Manutenibilidade** (uniformidade método) | ⚠️ Alembic + auto-migrate SQLite | ✅ Alembic cobre PG + auto-migrate SQLite (fallback) |
| **Compatibilidade** (PG espelho) | ⚠️ DIR3 só em SQLite | ✅ DIR3 em SQLite + PG espelho |

### E. Rollback
- `git revert` deste PR + `alembic downgrade 0009_vision_features` no host.
- Como `downgrade()` é não-destrutivo, as colunas permanecem (compatível com `INV ADITIVO`).

> **Veredito:** método uniformizado. Próxima: DIR12 (/metrics Prometheus).

---

## ADENDO 25/06/2026 (tarde-5) — SPR-DIR12: /metrics Prometheus expõe DIR8 (fix #M)

> Sprint P1 sem flag (puro observabilidade). 3 contadores DIR8 (`gap_recuperado_total`, `phase_uncertain_total`, `direction_divergence_total`) agora chegam ao painel Grafana externo via `/metrics`. Suíte **705 verde**.

### A. Bug #M auditado
`server/health_server.py:_PROM_METRICS` registrava ~30 contadores Prometheus mas **nenhum** dos 3 contadores DIR8. Eles só viviam em `state/phase_metrics.py` + `sentido.stats` no `state_sync` (overlay interno). Grafana externo cego.

### B. Correção
- **`server/health_server.py:194-198`** — 3 Gauges novas:
  - `roleta_phase_gap_recuperado_total`
  - `roleta_phase_uncertain_total`
  - `roleta_phase_direction_divergence_total`
- **`_refresh_custom_metrics` (`:204-213`)** — lê `phase_metrics.snapshot()` a cada scrape e publica nos Gauges. Try/except defensivo (tolerante a ausência do módulo).
- **Lint baseline atualizado** via `tools/lint_silent_except.py --update` (18 → 19 except permitidos).

### C. Testes novos (`tests/test_dir12_metrics_exporter.py`, 4 testes)
| Teste | Cobertura |
|---|---|
| `test_phase_metrics_module_disponivel` | `state.phase_metrics.snapshot()` retorna dict com 3 chaves. |
| `test_health_server_define_metricas_phase` | 3 Gauges registradas em `_PROM_METRICS`. |
| `test_refresh_custom_metrics_atualiza_phase` | Refresh lê snapshot e popula Gauges. |
| `test_refresh_tolerante_a_falha_silenciosa` | Refresh não quebra se módulo falhar. |

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Observabilidade externa** (Grafana) | ⚠️ Apenas via `state_sync` (cliente) | ✅ `/metrics` Prometheus padrão |
| **Manutenibilidade** | ⚠️ Comentário "pronto para /metrics" há semanas | ✅ Implementado |

### E. Rollback
`git revert` deste PR. Métricas Prometheus aparecem como `0` se nada incrementar.

> **Veredito:** painel externo pode acompanhar saúde da fase autoritativa em tempo real. Próximas P2: DIR10 + DIR13 + DIR14 + DIR18 em paralelo.

---

## ADENDO 25/06/2026 (tarde-6) — SPR-DIR10: ultimos[N] no overlay (fix #K)

> Sprint P2 com flag de tamanho. Timeline rica para auditoria offline/dashboards externos. Buffer separado de `recent_results` (preserva zona fria C3). Suíte **712 verde**.

### A. Bug #K auditado
`engine_overlay_fields` publicava apenas `last_seq` (escalar). Cliente/auditor externo não tinha como reconstruir a fase histórica sem chamar `get_state` ou raspar log.

### B. Correção
- **`state/game.py:251`** — novo `_phase_overlay_ring: deque(maxlen=12)` (SEPARADO de `recent_results` para não perturbar zona fria C3 / SDA17).
- **`state/game.py:process_spin` + `register_history_number`** — appendleft de `{numero, seq, direction}` (histórico vai com `direction=""`).
- **`state/game.py:engine_overlay_fields`** — publica `out["ultimos"]` (N controlado por `SDA_OVERLAY_ULTIMOS_N`, default 12, 0 desativa).
- **Round-trip:** `save_state`/`load_state` preservam o ring (cliente não perde timeline em restart).
- **`reset_session`:** zera o ring (novo dealer = nova história).
- **`app_config/settings.py`** — helper `overlay_ultimos_n()` (int 0..64; default 12).
- **Lint baseline atualizado** (3 novos try/except defensivos em `game.py`).

### C. Testes novos (`tests/test_dir10_ultimos_overlay.py`, 7 testes)
| Teste | Cobertura |
|---|---|
| `test_flag_default_12` | Helper retorna 12 default; 5 e 0 via env. |
| `test_process_spin_alimenta_ring` | Giros vivos populam ring com `numero+seq+direction`. |
| `test_overlay_publica_ultimos` | `out["ultimos"]` aparece, limitado a N. |
| `test_overlay_desativado_com_n_zero` | N=0 → chave `ultimos` ausente. |
| `test_register_history_alimenta_ring_nao_direcional` | Histórico → `direction=""` (sem inventar). |
| `test_roundtrip_ring_em_save_load` | Ring sobrevive a restart. |
| `test_reset_session_limpa_ring` | Reset zera (cross-dealer isolado). |

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Analisabilidade** (auditoria offline) | ⚠️ Só `last_seq` escalar | ✅ Timeline completa 12 últimos |
| **Confiabilidade** (zona fria C3) | ✅ | ✅ INV: buffer separado, SDA17 intacto |

### E. Rollback
`SDA_OVERLAY_ULTIMOS_N=0` no host + restart, ou `git revert`.

> **Veredito:** auditoria externa habilitada sem tocar SDA17. Próxima: DIR13 (UX lock + fix #Z lock total).

---

## ADENDO 25/06/2026 (tarde-7) — SPR-DIR14: clear _recent_trace_ids em reset (fix #O)

> Sprint P2 trivial. Fecha gap #O — falso-positivo de dedup pós-reset. Sem flag. Suíte **715 verde**.

### A. Bug #O auditado
`message_handler.py:170-179` (DIR6) — `_recent_trace_ids = deque(maxlen=64)` nunca era limpa em `handle_new_session`. Risco baixíssimo (cliente gera `trace_id` por `timestamp`, raro repetir), mas semanticamente errado.

### B. Correção
- **`server/message_handler.py:handle_new_session` (`:1399-1407`)** — dentro do `state_lock`, após `reset_session`, chama `self._recent_trace_ids.clear()` (try/except defensivo).
- Lint baseline atualizado.

### C. Testes novos (`tests/test_dir14_clear_trace_ids.py`, 3 testes)
| Teste | Cobertura |
|---|---|
| `test_handle_new_session_limpa_trace_ids_deque` | Após `clear()`, deque vazio. |
| `test_clear_e_idempotente_em_deque_vazio` | `clear()` em deque vazio = no-op. |
| `test_clear_nao_afeta_maxlen` | Após clear, `maxlen=64` preservado. |

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Confiabilidade** (primeiro spin pós-reset) | ⚠️ Risco residual | ✅ Sem risco (deque limpo) |

### E. Rollback
`git revert` deste PR. Comportamento volta ao baseline.

> **Veredito:** higiene de dedup. Próxima: DIR18 (shadow mode).

---

## ADENDO 25/06/2026 (tarde-8) — SPR-DIR18: shadow mode da autoridade DIR5 (fix #U)

> Sprint P2. Permite Grafana mostrar a divergência hipotética antes de promover SHADOW→AUTORIDADE plena. Em produção: SHADOW=1 sempre (zero risco). Suíte **718 verde**.

### A. Bug #U auditado
`message_handler.py:722-756` (DIR5) só rodava com `SDA_SENTIDO_AUTORITATIVO=1`. Em OFF, `project_phase` nem executava e `direction_divergence_total` ficava em 0 → impossível A/B real ("o que aconteceria se eu ligasse?").

### B. Correção
- **`app_config/settings.py`** — novo helper `sentido_autoritativo_shadow_enabled()` (default OFF; ON via `SDA_SENTIDO_AUTORITATIVO_SHADOW=1`).
- **`server/message_handler.py:727-775`** — refatorado: `if _autoridade or _shadow:` envolve o bloco. Substituição (`direcao = _fused`) só ocorre com `_autoridade=True`. Log distingue `"autoridade"` vs `"shadow"` para auditoria.
- **`docker-compose.yml`** — `SDA_SENTIDO_AUTORITATIVO_SHADOW=${SDA_SENTIDO_AUTORITATIVO_SHADOW:-1}` (ATIVADO em produção; zero risco).

### C. Testes novos (`tests/test_dir18_shadow_mode.py`, 3 testes)
| Teste | Cobertura |
|---|---|
| `test_flag_shadow_default_off` | Helper retorna False default. |
| `test_logica_shadow_mode_decision_tree` | 4 combinações `(autoridade, shadow)`. |
| `test_metrica_divergence_incrementa_em_shadow` | `direction_divergence_total` cresce mesmo sem substituir. |

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Observabilidade** (A/B autoridade) | ❌ Impossível sem ligar | ✅ Métrica disponível com SHADOW=1 |
| **Confiabilidade** (rollback granular) | ⚠️ Só ON/OFF binário | ✅ Shadow→Autoridade gradual |

### E. Rollback
- `SDA_SENTIDO_AUTORITATIVO_SHADOW=0` + redeploy: zera shadow.
- `git revert`: comportamento volta ao bloco condicional original.

> **Veredito:** A/B observável em produção. Próximas P3: DIR15 + DIR19 + (DIR13 retomada).

---

## ADENDO 25/06/2026 (tarde-9) — SPR-DIR19: buffer de fase separado, maxlen=20 (fix #R)

> Sprint P3. Aumenta a janela de shift de 10 para 20 SEM tocar em `recent_results` (8 testes SDA17 dependem do 10). Suíte **726 verde**.

### A. Bug #R auditado
`state/game.py:238` definia `recent_results = deque(maxlen=10)`. `phase_advance` (DIR4) aceitava `max_window=20` mas era limitado pela janela. Em minimização longa (>~20 s) ou troca de mesa com gap k>10, shift falhava prematuramente como `uncertain`.

**Constraint:** mudar `recent_results` para 20 quebraria 8 testes da zona fria C3 (SDA17 depende da janela 10 para calcular frieza).

### B. Correção
- **`state/game.py:251`** — novo `_phase_results: deque(maxlen=20)` (SEPARADO de `recent_results`).
- **`process_spin` + `register_history_number`** — appendleft em ambos os buffers (paralelos).
- **`message_handler.py:700`** — `_prev_nums = list(getattr(self.game_state, "_phase_results", None) or self.game_state.recent_results)` (fallback para load_state legado).
- **Round-trip** `save_state`/`load_state` (default `[]` se ausente).
- **`reset_session`** zera o novo buffer.

### C. Testes novos (`tests/test_dir19_phase_buffer_separado.py`, 8 testes)
| Teste | Cobertura |
|---|---|
| `test_buffer_separado_inicial` | `_phase_results` separado de `recent_results`. |
| `test_process_spin_alimenta_buffers_em_paralelo` | Ambos crescem; nenhum perturba o outro. |
| `test_register_history_alimenta_ambos` | Histórico → ambos. |
| `test_phase_advance_aceita_janela_maior` | Gap k=14 recuperado com janela 20. |
| `test_roundtrip_phase_results_em_save_load` | Sobrevive a restart. |
| `test_reset_session_zera_phase_results` | Reset limpa novo buffer. |
| `test_recent_results_NAO_alterado_pela_DIR19` | **INV**: SDA17 zona fria intacta. |
| `test_fallback_phase_advance_se_phase_results_ausente` | Backward-compat com load_state legado. |

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Confiabilidade** (recuperação de gap longo) | k ≤ 10 | k ≤ 20 |
| **Confiabilidade** (zona fria C3) | ✅ | ✅ INV preservado |

### E. Rollback
`git revert` deste PR. `_phase_results` é aditivo; remoção volta ao baseline (`recent_results`).

> **Veredito:** janela de shift dobrada sem efeito colateral em SDA17. Próximas: DIR15 (closeout docs) + DIR13 (UX cliente + #Z).

---

## ADENDO 25/06/2026 (tarde-10) — SPR-DIR13: UX lock + FIX #Z lock total (extensão 3.7.0)

> Sprint P2. Resolve gap UX #N e bug semântico #Z. Cliente bumpado para `3.7.0` (operador precisa recarregar extensão). Suíte **730 verde**.

### A. Bugs auditados
- **#N:** `popup.html` sem checkbox "travar fase"; `background.js:1251` mandava `locked: false` hardcoded.
- **#Z:** `direction_locked` checado apenas em `message_handler.py:740` (impede só fusão DIR7). Não impedia auto-seed da DIR5 nem reanchoragem DIR17. Nome promete "trava", semântica era "só não escuta vídeo".

### B. Correção
- **Servidor `app_config/settings.py`** — novo `lock_total_enabled()` (default OFF; ON via `SDA_LOCK_TOTAL=1`).
- **Servidor `message_handler.py:735-748`** — quando `_lock_total = lock_total_enabled() and direction_locked` é True E `seed_parity` está vazio, NÃO faz auto-seed (deixa o cliente ditar sem usurpar a fase escolhida pelo operador).
- **Servidor `docker-compose.yml`** — `SDA_LOCK_TOTAL=${SDA_LOCK_TOTAL:-1}` (ATIVADO em produção).
- **Cliente `background.js:1241-1259`** — lê `directionLocked` do `chrome.storage.local` e envia em `set_seed{direction, locked}` (não mais hardcoded). Log inclui `🔒` se lock ativo.
- **Cliente `extension/manifest.json`** — bump `3.6.0 → 3.7.0` + descrição menciona DIR13.

> **Observação:** UI completa (checkbox no `popup.html`, badge colorido no `content.js`) deferida para sprint **DIR13b** (UX visual puro). O servidor está pronto; cliente lê do storage (operador pode setar via console por enquanto: `chrome.storage.local.set({directionLocked: true})`).

### C. Testes novos (`tests/test_dir13_lock_total.py`, 4 testes)
| Teste | Cobertura |
|---|---|
| `test_flag_lock_total_default_off` | Helper retorna False default. |
| `test_lock_total_decision_matrix` | 4 combinações `(flag, locked)`. |
| `test_manifest_bumpado_para_3_7_0` | Extensão em 3.7.0 + descrição DIR13. |
| `test_settings_lock_total_helper_existe` | Helper exposto. |

### D. Impacto ISO
| Subcaracterística | Antes | Depois |
|---|:--:|:--:|
| **Usabilidade** (lock real) | ⚠️ `direction_locked` semanticamente fraco | ✅ Lock total quando flag ON |
| **Compatibilidade** | ✅ | ✅ Cliente legados ignoram set_seed.locked |

### E. Rollback
- `SDA_LOCK_TOTAL=0` + redeploy: comportamento atual.
- Cliente: voltar `manifest.version` 3.6.0 + reload.
- `git revert`.

> **Veredito:** semântica do lock alinhada com o nome. Próxima (última): DIR15 (closeout ISO + docs).

---

## ADENDO 25/06/2026 (tarde-11) — SPR-DIR15: closeout ISO + docs + supersede notice (fix #P + #Y)

> **Sprint final do ciclo DIR9..DIR19.** 11 sprints mergeadas em 1 dia (25/06): **DIR16 → DIR17 → DIR9 → DIR11 → DIR12 → DIR10 → DIR14 → DIR18 → DIR19 → DIR13 → DIR15**. Conformidade rev. 4 do `evolução_sentido.md` agora **~99%**. Suíte segue verde.

### A. Fechamento documental

| Item | Antes | Depois |
|---|---|---|
| `evolução_sentido.md` (rev. 4) | Sem nota de status | Cabeçalho: ⚠️ **SUPERSEDED** por `evolução_sentido_25.md` |
| `evolução_sentido_25.md` (rev. 5) | Proposta de 11 sprints | **TODAS executadas e mergeadas** |
| `models/input.py:44` — `client_spin_seq` | Campo aceito mas cliente nunca enviava (#Y) | Mantido (INV não-removido) + comentário "RESERVADO DIR21+" |
| `Manutenabilidade_iso.md` | 1 ADENDO 25/06 (manhã, DIR1..DIR8) | + 11 ADENDOS 25/06 (tarde, DIR9..DIR19) |

### B. Resumo executivo do ciclo (todos mergeados em main, deployados via systemd timer)

| Sprint | PR | Bug | Severidade | Flag default em prod |
|---|:--:|---|:--:|:--:|
| **DIR16** | #27 | #S/#W/#X reset/reancoragem | 🔴 P0 | `SDA_RESET_REANCORA=1` |
| DIR17 | #28 | #T uncertain reancora | 🟠 P1 | `SDA_UNCERTAIN_REANCORA=1` |
| DIR9 | #29 | #J sentido em sugestao | 🟡 P1 | — (aditivo puro) |
| DIR11 | #30 | #L Alembic 0010 retroativa | 🟡 P1 | — (aditivo Alembic) |
| DIR12 | #31 | #M /metrics Prometheus | 🟡 P1 | — (observabilidade) |
| DIR10 | #32 | #K ultimos[N] no overlay | 🟡 P2 | `SDA_OVERLAY_ULTIMOS_N=12` |
| DIR14 | #33 | #O clear trace_ids em reset | 🟢 P2 | — (defensivo) |
| DIR18 | #34 | #U shadow mode | 🟡 P2 | `SDA_SENTIDO_AUTORITATIVO_SHADOW=1` |
| DIR19 | #35 | #R buffer fase maxlen 20 | 🟡 P3 | — (aditivo) |
| DIR13 | #36 | #N/#Z UX lock + lock total | 🟠 P2 | `SDA_LOCK_TOTAL=1`; ext 3.7.0 |
| DIR15 | (este) | #P/#Y docs closeout | 🟢 P3 | — (docs) |

### C. Estado final pós-ciclo
- **Suíte:** 730 passed (era 689 no início) + 9 skipped + 1 xfailed. **+41 testes novos** cobrindo a família DIR9..DIR19.
- **CI main:** 5/5 SUCCESS em cada PR; main consistentemente verde.
- **Servidor Debian:** systemd timer puxa `origin/main` a cada ~2min → todos os 10 PRs já em produção (com flags ON nas DIR16/17/18/13 + auto-migrate Alembic 0010 + métricas Prometheus + lock cliente 3.7.0).
- **Extensão Chrome:** v3.7.0 publicada (operador precisa reload manual; comportamento legado intacto se ainda em 3.6.0).
- **Conformidade ISO/IEC 25010:** Confiabilidade 8.8→**9.0**, Manutenibilidade 8.6→**8.8**, Adequação 9.2→**9.3** (corrige vetor de aposta no lado errado em handoff).

### D. Bugs/gaps remanescentes (não-cobertos por este ciclo, ficam para próximos ADENDOS)
- **DIR13b** (UX visual): checkbox "🔒 Travar fase" no `popup.html` + badge colorido no `content.js` por `sentido.source`.
- **DIR20+:** labels por mesa nas métricas Prometheus (`{mesa, direction}` em vez de globais).
- **DIR21+:** ativar `client_spin_seq` no cliente para cross-validation.
- **Premissas históricas remanescentes:** ordem do DOM por provider, restore drill, AsyncAPI/REST formal — ver `Manutenabilidade_iso.md` §D do ADENDO 12/06.

### E. Invariantes verificados ao longo do ciclo
- ✅ **INV-3** (aposta sempre indicada) — nenhuma sprint suprime; `phase_uncertain` e `direction_locked` só ajustam o **lado**.
- ✅ **INV ADITIVO** — toda mudança via `ADD COLUMN IF NOT EXISTS`, `out["…"] = …`, ou sub-flag default OFF.
- ✅ **`main` é produção** — todas as mudanças via PR (`#27`..`#36`), zero push direto.
- ✅ **`graphify-out/` não commitado** (artefato regenerável).

> **Veredito FINAL do ciclo:** o eixo de sentido tem **fonte de verdade autoritativa, auto-recuperável em ≤2 giros em qualquer transição (handoff, troca silenciosa, correção), observável via Prometheus, com lock real do operador**. 11 sprints, 1 dia, zero regressão. Próximo ADENDO esperado: pós-validação 24h em produção (monitorar `roleta_phase_direction_divergence_total` e `roleta_phase_uncertain_total`).

---

## ADENDO 03/08/2026 — Auditoria da fundação de dados (pgvector/CDC/DNA) + plano de higienização pré-estratégia

> Auditoria **read-only** da camada de dados em produção (`xmaiajpvm`, 187.45.181.75) com foco em:
> a infraestrutura analítica (pgvector/outbox/CDC/DNA) está populada, íntegra e pronta para servir
> de fundação à próxima fase (otimização de predição)? Relatório completo e evidências: `evolução_03_08.md`.
> **Uma única ação operacional foi executada no servidor** (ANALYZE — §C); todo o resto é plano por PR.

### A. O que foi verificado ✅ (população e integridade)

| Checagem | Resultado | Evidência |
|---|---|---|
| Paridade SQLite↔PG (03/08) | **230 = 230** (1:1) | count decisions vs cw+ccw.spins_vectors |
| Duplicatas/órfãos/vetores zerados | **0 / 0 / 0** | queries agregadas em prod |
| Exactly-once no CDC | ✅ evento+mark na mesma tx, `SKIP LOCKED` + SAVEPOINT | `workers/cdc_worker.py:332-361` |
| Outbox | 56.466 processed / **0 pending / 0 error** | `shared.outbox` |
| Backup SQLite diário | ✅ vivo (03/08 03:15, 2,7 MB) | `/root/backups/sqlite/` |
| wal-g 30 min | ✅ cron ativo + binário presente | `/etc/cron.d/walg-backup` |
| Fill-rate `decisions` (46 col) | ~100% exceto `round_id` (0%, fonte não fornece) e `vision_source` (60% hoje) | PRAGMA + counts |
| INV-3 | ✅ 100% `final_action=APOSTAR` no dia | query decisions 03/08 |

### B. Achados (A1–A5 + F1) — o que impede a fundação de estar 100%

| # | Achado | Severidade | Evidência |
|---|---|:--:|---|
| **F1** | **`dna_realize_lifts()` (SP-08 DNA-03) é código órfão**: implementado e testado (`tests/test_sp08_dna_realize_lifts.py`) mas **nenhum caller em produção** → `realized_lift_pp` 100% NULL em 41.370 rows desde 26/05. O loop de feedback quantitativo do DNA nunca fechou | 🔴 P1 | `database/dna_logger.py:203`; grep sem callers |
| A1 | INSERTs de `spins_vectors`/`spin_features` **sem idempotência** (replay manual duplicaria; `spin_uuid` é `gen_random_uuid()`, inútil p/ dedup; handler de DNA tem guard, estes não) | 🟠 P2 | `cdc_worker.py:139-143,204-225` |
| A2 | **Cosine sobre escalas mistas**: dims força (~16) e pred_force (~14) dominam; taxas (~0,39) quase não pesam na similaridade | 🟠 P2 | médias em prod `[16.2, 0.39, 0.39, 0.39, 3.6, 14.1]` |
| A3 | Índice ivfflat `lists=100` p/ ~3,5k rows e **`idx_scan=0`** (consumidor `/api/regime_similarity` nunca chamado) | 🟡 P3 | `pg_stat_user_indexes` |
| A4 | Stats do planner congeladas (`n_live_tup=162` vs 3.591 reais; nunca autoanalyze) | 🟡 P3 → **sanado §C** | `pg_stat_user_tables` |
| A5 | Drift doc↔realidade: **TimescaleDB não está instalado** (extensões: `vector 0.8.2` + `age 1.5.0`); `last_20_hits` da window query **mistura sessões/dealers** (contaminação de lag-features) | 🟡 P3 | `pg_extension`; `cdc_worker.py:169-176` |
| — | Resíduo histórico: 126 decisões (1,8%, era do bug HOOK-1, 24/05→) sem espelho no PG | 🟢 P4 | 7.087 SQLite vs 6.961 PG desde 24/05 |

Gaps do ADENDO 12/06 §D **reconfirmados sem evolução**: AGE instalado sem uso (decisão de remover pendente, imagem 1 GB); `models/spin_autoencoder.joblib` untracked no host (hazard `git clean`); restore drill nunca ensaiado. Disco ok (14%), mas `docker system df` acusa **5,5 GB de imagens reclamáveis + 1,8 GB de build cache**.

### C. Ação operacional executada HOJE no servidor (única mutação; reversível, fora do caminho da aposta)

```sql
ANALYZE cw.spins_vectors; ANALYZE ccw.spins_vectors;
ANALYZE cw.spin_features; ANALYZE ccw.spin_features;
ANALYZE shared.decision_dna; ANALYZE shared.outbox;
```
Resultado: `n_live_tup` 162→**3.591** (cw) / 164→**3.370** (ccw), `last_analyze=2026-08-03 15:00 UTC`. Sana A4 operacionalmente; a persistência da correção (ANALYZE periódico) entra por PR (H4).

### D. Plano de higienização — divisão servidor × git (candidatos a sprint, ordem recomendada)

**No servidor Debian (operacional, sem PR — runbooks existentes):**

| # | Ação | Instrumento | Gap que fecha |
|---|---|---|---|
| S1 | ✅ FEITO: ANALYZE nas 6 tabelas analíticas | psql one-shot | A4 |
| S2 | Backfill dos 126 rows faltantes (padrão `scripts/backfill_dna_pg.py`: one-shot, idempotente, read-only no SQLite) | `docker exec roleta-cloud` | resíduo HOOK-1 |
| S3 | **Restore drill** wal-g ponta-a-ponta (script pronto, nunca ensaiado) | `scripts/walg-restore-drill.sh` | 12/06 §D.5 |
| S4 | Mover `spin_autoencoder.joblib` p/ volume + entrada no `.gitignore` (a parte git via PR H7) | mv + compose volume | 12/06 §D.4 |
| S5 | Housekeeping Docker: `docker system prune` de imagens órfãs (5,5 GB) + build cache (1,8 GB) | docker | disco/portabilidade |

**No git/arquivos locais (via PR, 1 sprint cada, invioláveis respeitados):**

| # | Sprint proposto | Conteúdo | Gap |
|---|---|---|---|
| H1 | `SPR-DATA1` | Ligar `dna_realize_lifts()` em job periódico no engine (flag **`SDA_DNA_REALIZE` default-OFF** na compose; leitura por-chamada) + **baseline/buckets POR DIREÇÃO** (`GROUP BY direction`; hoje `dna_logger.py:224` calcula global misturando cw+ccw) + publicar `dna_realized` → PG + backfill 41k | **F1** (desbloqueio da fase de estratégia) |
| H2 | `SPR-DATA2` | Migração Alembic **aditiva**: `UNIQUE(decision_id)` em `spins_vectors`/`spin_features` + `ON CONFLICT DO NOTHING` no worker | A1 |
| H3 | `SPR-DATA3` | `session_id` como coluna + filtro na window query do `spin_features` (lag-features por sessão, não globais) — coluna nova ADITIVA, backfill best-effort | A5b |
| H4 | `SPR-DATA4` | ANALYZE a cada N batches no cdc_worker (flag default-OFF) — persiste S1 | A4 |
| H5 | `SPR-DATA5` | `train_autoencoder.py` com **2 modelos independentes (1 por sentido)** — hoje `train_autoencoder.py:36` treina 1 PCA único misturando cw+ccw — + backfill `ae_latent` com o modelo do sentido correspondente (job offline; z-score embutido resolve A2 na raiz) | A2 |
| H6 | `SPR-DATA6` | Recriar índices como **HNSW** (pgvector 0.8.2) quando o consumidor de similaridade for ativado | A3 |
| H7 | `SPR-DATA7` | Docs: corrigir blueprint (`fluxo_mental_24.md` cita Timescale inexistente) + `.gitignore` do joblib + executar decisão AGE (remover ou popular — go/no-go do Diretor) | A5a, 12/06 §D.3/D.4 |

Dependências: H1 é pré-requisito da fase de estratégia; H2–H4 são higiene barata e independentes; H5→H6 em sequência. S2/S3/S5 podem rodar já.

**Requisito transversal — isolamento por sentido (CW/CCW):** toda camada analítica deve permitir análise isolada por sentido de giro. Storage já segrega (schemas `cw`/`ccw`, `decision_dna.direction`, `regime_similarity` exige `direction ∈ {cw,ccw}`); as duas violações no processamento — baseline global do `dna_realize_lifts()` e autoencoder único — são corrigidas por H1 e H5 respectivamente (specs completas em `evolução_03_08.md` §4.0/§4.2).

**4ª rodada (03/08 tarde) — visão de banco de dados e auditoria SaaS/conflitos** (`evolução_03_08.md` §5): (i) **inventário SaaS**: stack 100% OSS auto-hospedada; único serviço externo = **Backblaze B2** (wal-g, S3-compatível), verificado FUNCIONAL (410 WALs archivados, 0 falhas, base backups 30/30min); "workana" NÃO existe no repo nem no servidor (grep zero — provável confusão com o super-grafo graphify multi-repo que inclui o projeto "Genesis azure"); (ii) **riscos novos**: R1 = backup do SQLite autoritativo é local-only (réplica mais protegida que a fonte → **S6**); R2 = retenção wal-g de ~3,5 h (cron `*/30` + `retain FULL 7` → **S7**, decisão do operador); (iii) **conflitos do plano**: C1 = H7 (imagem PG oficial) quebraria o boot com `shared_preload_libraries=age` no compose → guarda incorporada ao H7 + S3 (restore drill) promovido a pré-requisito; C5 = H5 deve treinar após H3 (janelas contaminadas entre sessões). Ordem recomendada: `H2 → S2 → H3 → H1 → H4 → H5 → H6 → S3 → H7`.

### E. Invariantes e conformidade

- ✅ Auditoria **read-only**; única mutação = ANALYZE (§C), sem tocar schema, dados ou caminho da aposta.
- ✅ Nenhum push em `main`; este ADENDO + relatório entram por PR (branch `ivandirfilho-animated-dollop`).
- ✅ Plano D respeita: flags default-OFF na compose, migrações ADITIVAS, round-trip save/load/reset, INV-3 intocado.
- **ISO/IEC 25010:** Confiabilidade — fundação de escrita confirmada sólida (exactly-once, backups vivos); Manutenibilidade — F1 evidencia gap de *feature completeness* (código testado sem caller: lacuna de integração, não de implementação); Analisabilidade — segue **bloqueada até H1/H5** (DNA sem lift realizado, vetores sem embedding utilizável). Scorecard inalterado até execução do plano.

> **Veredito:** a fundação de **escrita** está 100% funcional (paridade 1:1, zero backlog, backups vivos). A fundação **analítica** — razão de ser do PG stack — está ~70%: dados chegam corretos, mas o feedback (F1), a comparabilidade (A2) e o consumo (A3, `idx_scan=0`) não operam. **H1 (SPR-DATA1) é o próximo passo obrigatório antes de qualquer imersão séria em estratégia**; sem `realized_lift_pp`, qualquer ajuste de aposta será guiado por intuição, não por dado.

### F. CLOSEOUT (03/08 noite) — execução completa H1–H7 + S2/S3/S5/S6/S7

**Entregue por 4 PRs mergeados** (#38 H1–H7 `4cd47d5`; #39 fix direction `1557451`; #40 backup
retain48+rclone+drill-pg15 `4b72885`; #41 fix ca-certificates `2a41da7`), CI 5/5 verde em todos,
suíte **733 passed**. Rollout no Debian concluído no mesmo dia: alembic **0013**, flags LIGADAS
via `.env` do host (`SDA_DNA_REALIZE=1/EVERY=20`, `CDC_ANALYZE_EVERY_N=50` — compose segue
default-OFF), `roleta-pg` na imagem upstream `pgvector/pgvector:pg15` + `DROP EXTENSION age`,
2 AEs per-direction treinados (evr ≈0,96) + `ae_latent` 100%, lifts 33.411 no SQLite **e** no PG
(paridade exata pós-#39), 4 UNIQUE + 4 HNSW (uso confirmado por EXPLAIN).

**Backups (S5/S6/S7/S3 fechados):** `.db` legados fora do volume; SQLite offsite no B2 via
rclone (cron diário, `OFFSITE OK` validado); retain wal-g FULL 7→**48** (24h de janela);
**restore drill executado com sucesso** — basebackup do B2 restaurado em container isolado com
41.370 dna / 33.411 lifts íntegros.

**3 bugs reais achados e corrigidos pela auditoria ponto a ponto** (detalhe: `evolução_03_08.md`
§6.4): (1) vocabulário `direction` sem normalizar no evento novo → espelho casava 0 rows; (2)
imagem upstream sem `ca-certificates` → wal-g TLS quebrado ~1h (basebackup+WAL) → bind-mount de
certs do host; (3) drill com imagem PG16 vs backups PG15 + `auto.conf` com aspas inválidas +
falta de `recovery.signal` — nunca havia rodado até o fim. ~~Pendência única: validar `session_id`
no primeiro giro pós-deploy~~ → **validado ao vivo 18:01 UTC** (retomada da mesa): sessão
`26172412` em 9/9 giros novos, cw e ccw.

**Validação ao vivo pós-retomada + achado #5 (03/08 18h UTC):** com a mesa girando de novo, o
fluxo completo foi confirmado com giros reais — 9 spins ingeridos, outbox 0 pendentes, CDC com
`analyze_done` (H4), archiving vivo, docker novo (`def33c5`) healthy. Único gap: `ae_latent`
dos giros novos ficava `NULL` (por design H5 o hot path não carrega ML libs; o backfill era
one-shot). Fechado com **rotina permanente**: `scripts/ae-latent-nightly.sh` (container efêmero
python:3.12-slim, numpy 1.26.4 pinado — CPU do host não suporta x86-64-v2 — e scikit-learn
1.9.0 = versão dos .joblib) + cron `/etc/cron.d/roleta-ae-latent` 04:25. Testado 2× em produção;
`ae_latent` de volta a **100%** (cw 3.604/3.604, ccw 3.383/3.383). Detalhe: `evolução_03_08.md` §6.6.

**ISO/IEC 25010 pós-execução:** Analisabilidade **desbloqueada** (lift per-direction consultável,
espaço latente comparável por sentido, k-NN indexado); Confiabilidade elevada (RPO PG 30min com
retenção 24h, SQLite offsite, restore ensaiado). Fundação de dados **pronta para a fase de
estratégia** (E1–E5, `evolução_03_08.md` §4.3; arquitetura: `arquitetura_dados_estrategia.md`).

---

## ADENDO 04/08/2026 — GO-LIVE V5 "17/21 por sentido" (composer assinatura-primeiro + seletor pós-miss + UI 3.8.0)

> Implantação completa da estratégia especificada em `estrategia_proposta_03_08.md` (SPR-V5A+V5B
> colapsados em 1 PR por ordem do dono: "implante tudo para que fique live e funcional").
> Motor novo `strategies/regions_v5.py`, seletor 17↔21 no SDA17, wiring no message_handler,
> contrafactuais no `decision_dna`, go-live na compose e ajustes de UI nas 4 superfícies
> (dashboard + extensão 3 vistas). Zero migração de schema; arquitetura de povoamento INALTERADA.

### A. Capacidades novas ✅

| Capacidade | Onde | Evidência |
|---|---|---|
| Composer V5 puro/determinístico por sentido: R1=cluster gravidade-7 (janela 8 forças), R2=2º cluster condicionado à tendência Theil–Sen (janela 5, deadband 1,0, clamp ±8), R3=zona fria do MESMO sentido (heatmap triangular, 12 resultados) — saída SEMPRE 17 (3/2/2) ou 21 (3/3/3) distintos, MESMOS centros, C17 ⊂ C21, disjunção gap 7 | `strategies/regions_v5.py` (novo, ~290 LOC) | fuzz 5k seeds em `tests/test_regions_v5.py` (31 testes) |
| Seletor 17↔21 por sentido: default 17; miss real→21; hit real→17; teto 5 jogadas-21/sessão×sentido → LOCK17; stop-loss de sessão força 17 | `strategies/sda17.py` (`v5_select_mode`/`v5_note_emitted`/`v5_note_outcome`) | testes seletor + wiring |
| Round-trip do estado do seletor: `adaptive_state` v1.8→**v1.9** (`v5_mode`, `v5_count21`) em `get/load/reset_adaptive` — restauração VALIDADA (dk∈{17,21}, int≥0), backward-compat com v1.8 | `sda17.py` | `test_round_trip_v19`, `test_backward_compat_estado_v18`, `test_load_valida_lixo` |
| Modo `v5_1721` no enum `SDA_BET_PAIR` + ramo auto-contido no `_engine_apply_selection` (early-return; `details['centers']` segue V4 → continuidade DNA/atribuição) | `app_config/settings.py`, `server/message_handler.py` | `test_warmup_emite_17_com_meta_v5` |
| Contrafactuais pareados congelados ANTES do resultado: `v5_mode`/`v5_cov17`/`v5_cov21` no pending + 3 features novas no `decision_dna` (`v5_would_hit_17`, `v5_would_hit_21`, `v5_coverage_mode`) — validação econômica §5.1 sem schema novo | `message_handler.py` (inject/resolução) | `test_inject_pending_congela_contrafactuais_e_conta_emissao` |
| Contagem-21 só em EMISSÃO REAL (fallback de calibração não queima crédito) + flip só com HIT REAL da cobertura apostada | `_engine_inject_pending` / bloco M15-ADA | `test_sem_pending_nao_conta` |
| Warmup INV-3: <3 resultados no sentido → tríade-prior `apply_force(last, 10+{0,12,24})` (gaps 12/12/13 ⇒ disjunta) — SEMPRE há indicação | `regions_v5.compose_v5` | `test_warmup_triade_disjunta_inv3` |
| Go-live: default `SDA_BET_PAIR=v5_1721` na compose (comentário com breakevens 17#=47,2% / 21#=58,3% / limiar 11,1pp e rollback force17) | `docker-compose.yml` | diff |
| UI payload-driven nas 4 superfícies: labels r1/r2/r3 dinâmicos + badge `V5·17#/21#` (extensão expandida), cold-start do minimizado prefere `data.regioes` (centros da estratégia ATIVA) antes do `pending_prediction.centers` V4, paleta r1/r2/r3 no dashboard, rótulos estáticos "(17#)" removidos (`(--)` até payload), manifest **3.8.0** | `extension/content.js`, `frontend/app.js`, `frontend/index.html`, `extension/manifest.json` | auditoria UX §12 da proposta |

### B. Bugs corrigidos no caminho

| # | Bug | Fix |
|---|---|---|
| 1 | Cold-start do overlay minimizado usava `pending_prediction.centers` ([C1,C2,C3] V4 crus) mesmo quando a estratégia ativa era outra (ordem/estratégia divergente) | fallback intermediário `data.regioes` (gap 3 da auditoria UX) |
| 2 | Rótulo estático "(17#)" no dashboard mentiria no modo 21 | `#f17-cov` inicia `(--)` e é populado por `coverage_n` real |
| 3 | Classe CSS da região hardcoded p/ c1/c2/c3 (labels novos cairiam todos em c3) | classe dinâmica `eb-rc-${label}` + paleta por mapa com fallback |

### C. Impacto arquitetural

- **Zero migração Alembic** — estado do seletor viaja no `adaptive_state` (JSON já persistido); contrafactuais usam `decision_dna` existente (EAV). Povoamento SQLite→outbox→PG **byte-idêntico**.
- **force17 clássico intocado** (`c_selection.py` sem diff) = rollback vivo: `SDA_BET_PAIR=force17` no host + redeploy ~3 min.
- Meta v5 reusa o **contrato force17-block** do overlay (`regioes/c1_force/coverage_n/numeros`): as 3 vistas da extensão + Glass Box acendem sem mudança de protocolo; `v5_mode` é aditivo (ausente no force17 clássico — clientes velhos byte-idênticos, verificado por teste).
- Fallback de calibração no modo v5 = raio 8 (17#) — consistente com o default do seletor.

### D. Scorecard (delta vs 03/08)

| Característica | Antes | Depois | Nota |
|---|:--:|:--:|---|
| Adequação Funcional | 9 | 9 | estratégia nova coberta por 31 testes novos; suíte 764 passed |
| Manutenibilidade | 8,5 | **9** | composer puro isolado (testável sem I/O); seletor com round-trip completo; enum fechado |
| Confiabilidade | 9 | 9 | INV-3 preservado (warmup tríade); stop-loss integra seletor sem suprimir indicação |
| Analisabilidade | 8,5 | **9** | contrafactuais 17/21 pareados no DNA desde o 1º giro (decisão §5.3 pré-registrada: 50/150/600 jogadas-21, limiar 11,1pp) |

### E. Obrigações de ciclo e rollback

- ✅ Suíte completa: **764 passed, 9 skipped, 1 xfailed** (31 novos em `test_regions_v5.py`; pins atualizados: manifest 3.8.0, adaptive v1.9).
- ✅ `tools/lint_silent_except.py --update` (1 `except ValueError` novo e justificado em `regions_v5._wheel_index`).
- ✅ Flag na compose com comentário de rollback; leitura por-chamada; nada hardcoded.
- ✅ Round-trip `save()`/`load()`/`reset_session()` do campo novo de motor.
- ✅ Entrega por PR (sem push direto em `main`); merge autorizado pelo dono ("live e funcional").
- ⚠️ **Ação manual do operador**: recarregar a extensão unpacked no Chrome (v3.8.0 não vai pelo deploy Debian).
- **Rollback**: `SDA_BET_PAIR=force17` no `.env` do host + `docker compose up -d` (~3 min), ou `git revert` do PR. Estado v1.9 é backward-compat (v1.8 ignora as chaves novas).
- **Desligamento pré-registrado** (§5.3 da proposta): se `v5_would_hit_21 − v5_would_hit_17 < 11,1pp` após 150 jogadas-21 (ou hit-rate 17# < 40% após 600 giros), voltar `SDA_BET_PAIR=force17` e reavaliar.

---

## ADENDO 04/08/2026 (noite) — HOTFIX: eleição de MASTER promovia cliente passivo (Glass Box congelado)

> Incidente pós go-live V5 (mesmo dia): dono reportou "a escuta recebe o resultado mas o Glass Box /
> painel minimizável não populam". Diagnóstico 100% passivo (sem ssh): probe WS em produção recebeu
> **146 `state_sync` (1Hz) e ZERO `trace` em 150s** com mesa ativa — servidor saudável emitindo
> heartbeat com meta V5 completo, porém **nenhum spin sendo aceito**. Variante do incidente 13/06
> (runbook `docs/runbooks/sem-apostas-master-slave.md`).

### Causa-raiz

1. `websocket.py` conecta TODO cliente sem `device_id` (fica `"unknown"`); só a escuta envia `register`.
2. Quando o MASTER (escuta) cai — p.ex. service worker MV3 suspenso ou restart de deploy — o
   `handle_grace_period` promovia o SLAVE **mais recente sem filtrar passivos**: um dashboard
   Glass Box aberto virava MASTER.
3. Dashboard nunca envia `novo_resultado` e **ignora** `role_changed`; quando a escuta re-registrava,
   `update_device_id` via `master_id` ocupado → escuta ficava **SLAVE eterna** → `background.js`
   nem envia o giro (gate local) → pipeline mudo, Glass Box/overlay congelados, sem erros no log.

### Fix (cirúrgico, 2 pontos em `server/connection_manager.py`)

| Ponto | Regra nova |
|---|---|
| `handle_grace_period` | Promove APENAS conexões **registradas** (`device_id != "unknown"`); dashboards/probes nunca assumem |
| `update_device_id` | Dispositivo que envia REGISTER **destrona** um master passivo (`device_id == "unknown"`) via `_demote_master` e assume; master registrado continua protegido (sem mudança) |

- INV preservada: `force_master` (botão 🎯 do overlay) intocado; grace period de 10s intocado;
  gate `NOT_MASTER` intocado.
- Sem flag: é correção de defeito na eleição (comportamento correto único), não comportamento novo.
- Zero schema/estado; zero mudança de protocolo; extensão NÃO precisa de reload para este fix
  (correção é server-side; o reload p/ 3.8.0 continua pendente pela V5).

### Regressão

`tests/test_connection_manager_master.py`: **5→9 testes** — grace não promove "unknown" (2 cenários,
inclusive com registrado mais antigo presente), REGISTER destrona master passivo, REGISTER não
destrona master registrado. Suíte completa: **768 passed, 9 skipped, 1 xfailed**.

### Recuperação em produção

Deploy do fix (PR → main → timer ~2 min) + reconexão automática da escuta: ao re-registrar, ela
destrona o master passivo e o fluxo volta sozinho (sem restart manual). Runbook §7 atualizado.

---

## ADENDO 05/08/2026 — V5.1 "assinatura-4" (spec exata do operador) + badge circular 17/21 + broadcast da sugestão (ext 3.9.0)

> Terceira rodada do ciclo V5. O dono revisou a spec estratégica dos 3 centros e pediu: (a) badge
> **circular verde brilhante** com o modo 17/21 junto aos 3 números em TODAS as vistas; (b) diagnóstico
> de "sugestão não aparece em toda rodada"; (c) auditoria do motor vs a spec revisada. Probes passivos
> em produção provaram que o servidor DECIDE toda rodada (decision log contínuo, INV-3 ok) e que
> trace/state_sync carregam o meta V5 — o gap era a msg `sugestao` ser enviada **só ao MASTER**.

### A. Motor V5.1 (flag `SDA_V5_SIG4`, default OFF no código, ON na compose)

| Centro | Go-live 04/08 (`spec4=False`) | V5.1 spec4 (`SDA_V5_SIG4=1`) |
|---|---|---|
| R1 | cluster gravidade-7, janela **8** forças do sentido | idem, janela **4** ("últimas 4 jogadas") |
| R2 | 2º cluster do resíduo condicionado à tendência | **projeção do PRÓPRIO R1**: `r1_force + clamp(round(slope TS janela 4), ±8)` — acelerando→adiante, freando→atrás; neutro→disjunção empurra +7 |
| R3 | zona fria (heatmap 12 do MESMO sentido) | região **menos visitada** da divisão FIXA da roda em **6 regiões** (5×6+1×7, ordem física; centros idx 3/9/15/21/27/33); sobrepôs → snap p/ região disjunta mais PRÓXIMA da indicada |

- Isolamento por sentido preservado em R1/R2 (INV-1); R3 conta **ambos os sentidos** (spec do dono).
- Placar `GameState.region6_counts` (novo campo de motor): incrementado em `process_spin` E
  `register_history_number` (espelha `recent_results`), **round-trip completo** save/load/reset_session
  (compat: `[0]*6` se ausente — snapshot legado não trava boot). População sempre-on e inerte;
  o USO é flag-gated (padrão shadow DIR-x). Zero migração Alembic (snapshot JSON, não schema).
- Caminho default (`spec4=False`) **byte-idêntico** ao go-live: fuzz 5000 iterações do 04/08 intacto.
- Geometria/seletor intocados: mesmos raios 3/2/2 vs 3/3/3, C17 ⊂ C21, 17/21 EXATOS, LOCK17,
  contrafactuais DNA e flip pós-miss (regra literal do dono) — nada mudou fora do composer.

### B. Transporte — `SDA_SUGESTAO_BROADCAST` (default OFF, ON na compose)

Causa-raiz do "sugestão some": `sugestao` ia SÓ ao websocket do master (l.1446); viewers/Glass Box
dependiam do `state_sync` 1 Hz. Agora o handler **replica a mesma `sugestao`** aos demais clientes
(exclui o socket do master — zero duplicata; viewer morto não trava o giro; aditivo — clientes
antigos ignoram). Rollback: `SDA_SUGESTAO_BROADCAST=0` + redeploy.

### C. UI — badge circular 17/21 (ext **3.9.0**)

- `buildModeBadge()` no content.js: círculo ⌀22px (16px no minimizado), borda+texto `#39ff14` com
  glow, MESMA fonte/tamanho/cor p/ 17 e 21 (spec do dono), menor que os números dos centros; na
  linha dos 3 centros (expandida), no status minimizado e no Glass Box (`frontend/app.js`).
- Fonte do valor: `force17.v5_mode` (sugestão > state_sync no minimizado). Header mantém `· V5`.
- Manifest 3.8.0 → **3.9.0** + changelog. Operador: `git pull` no Desktop + ↻ na extensão.

### D. Observabilidade

Meta `force17` ganhou `spec4`/`r2_delta`/`r3_region` (aditivo — flui em sugestao/state_sync/trace
p/ auditoria ao vivo da projeção R2 e da região fria R3 sem probe de código).

### E. Regressão e arquivos

- Suíte **791 passed** (+23: TestRegion6 6, TestSpec4Composer 9 c/ fuzz 3000, TestRegion6State 5,
  TestWiringSpec4 2, manifest 3.9.0) · lint silent-except baseline atualizado (2 handlers novos
  documentados) · CI 5/5.
- Tocados: `strategies/regions_v5.py` (+região6/spec4), `state/game.py` (+placar), `server/message_handler.py`
  (spec4 wiring + broadcast), `app_config/settings.py` (2 flags), `docker-compose.yml` (2 envs),
  `extension/content.js`+`manifest.json` (badge, 3.9.0), `frontend/app.js` (badge Glass Box),
  `tests/` (+23). Rollback integral: flags `=0` no host (~3 min) ou `git revert` do PR.

---

## ADENDO 05/08/2026 (tarde) — V5.2: seletor 17/21 PURO por sentido + badge DOURADO + minimizado unificado (ext 3.9.1)

> Quarta rodada do ciclo V5. Feedback do dono após operar a V5.1: (a) "mesmo após derrotas continua
> sugerindo 17"; (b) o quadro minimizável mostra **3 telas diferentes** e o 17/21 não aparece bem em
> todas; (c) badge difícil de ver — **negrito + dourado** combinando com a paleta; (d) regra nova do
> seletor: **a última derrota/vitória do SENTIDO-ALVO decide 17 ou 21, de forma isolada**.

### A. Diagnóstico — por que "17 mesmo após derrotas"

O flip pós-miss→21 (`v5_note_outcome`) SEMPRE funcionou. Ele era **mascarado por dois overrides
LOCK17** legítimos do go-live: (1) stop-loss de sessão B5 (`_v5_stop_loss`) trava o seletor em 17
enquanto pnl ≤ −limite — e em produção o B5 ficou ativo a sessão inteira (probe 05/08: TODA decisão
com "STOP-LOSS sessão (B5)"); (2) teto de 5 jogadas-21 por sessão×sentido. Resultado: modo 17
permanente, aparentando seletor quebrado. Não era bug — era design que o dono agora substituiu.

### B. Motor — flag `SDA_V5_FLIP_PURO` (default OFF no código, ON na compose)

- `v5_select_mode(direction, pure=False)`: com `pure=True` ignora o teto-21 — devolve o flip cru.
- Wiring `_engine_apply_selection`: flag ON (leitura por-chamada) → `pure=True` e o `_v5_stop_loss`
  **deixa de travar a cobertura**; B5 continua vetando o STAKE (mínimo 1u — INV-3: indicação sempre).
- Semântica final (flag ON): última jogada resolvida do sentido-alvo = vitória → **17**; derrota →
  **21**. Sentidos 100% isolados (`_v5_mode["cw"/"ccw"]`); `v5_note_outcome` já resolvia com o HIT
  REAL do pending pelo `bet_direction` — nada mudou na resolução.
- OFF = comportamento do go-live (flip + LOCK17 por B5/teto). Rollback: `SDA_V5_FLIP_PURO=0` + restart.

### C. Front — "3 telas" unificadas + badge dourado (ext **3.9.1**)

- Causa das 3 telas: o status minimizado tinha **3 writers com formatos distintos** — `toggleMinimize`
  (centros+gale, SEM badge), `updateOverlay` minimizado (SEM badge) e o heartbeat `state_sync` (COM
  badge) → a tela "trocava sozinha" a cada fonte. Agora `minimizedStatusHTML()` é a fonte ÚNICA
  ([centros] + badge + gale) usada pelos 3 writers; `v5ModeFromSugestao()` resolve o modo do cache.
- Badge (content.js `buildModeBadge` + Glass Box `frontend/app.js`): **#ffd700 dourado** (combina com
  o gold #ffd166 da paleta de labels), `font-weight:900`, fonte maior (0.55d; ⌀24px expandida/Glass
  Box, 18px minimizado), fundo `rgba(255,215,0,0.12)` e glow dourado — legibilidade pedida pelo dono.
- Manifest 3.9.0 → **3.9.1** + changelog. Operador: `git pull` + ↻ na extensão.

### D. Observabilidade — passthrough spec4 no state_sync

`engine_overlay_fields()` (state/game.py) cherry-pickava o meta e **descartava**
`spec4`/`r2_delta`/`r3_region` (só iam no trace/sugestao — probe 05/08 mostrou `spec4=None` no
state_sync). Agora os 3 campos passam quando presentes (aditivo).

### E. Regressão e arquivos

- Suíte **796 passed** (+5: pure ignora teto, wiring flip-puro ×3, passthrough spec4; manifest 3.9.1).
- Tocados: `strategies/sda17.py` (pure), `server/message_handler.py` (wiring flag), `app_config/settings.py`
  (flag), `state/game.py` (passthrough), `docker-compose.yml` (env), `extension/content.js`+`manifest.json`
  (3.9.1), `frontend/app.js`, `tests/` (+5, manifest). Rollback: `SDA_V5_FLIP_PURO=0` no host (~3 min).

---

## ADENDO 05/08/2026 (noite) — SPR-V2 "DIR20": a extensão parou de FABRICAR giros e de inverter a fase (ext 3.10.0)

> Quinta rodada do ciclo. Sintoma reportado: o servidor recebia giros que **não aconteceram** e, com
> eles, a fase (`horario`/`anti-horario`) invertia — corrompendo a seleção por sentido que a V5.2
> acabara de entregar. A causa não estava no motor Python: estava no **cliente MV3**.

### A. Diagnóstico — 4 defeitos que se somavam no service worker

| # | Defeito | Consequência |
|---|---------|--------------|
| 1 | Baseline persistia `results.slice(0,5)` enquanto o payload do site traz **12** números | Qualquer variação além dos 5 primeiros "parecia" giro novo |
| 2 | `countNewSpins` devolvia **1 conservador** quando NADA alinhava | Leitura de frame errado/parcial virava 1 giro + 1 flip de fase |
| 3 | `chrome.alarms.onAlarm` chamava `readResults()` **sem `await`** | Dois ticks liam o mesmo baseline, "detectavam" o mesmo giro e enviavam 2× com 2 flips |
| 4 | Re-hidratação do storage por callback perdia a corrida do boot | O 1º tick após acordar o worker decidia com a fase literal `horario` do `DEFAULT_STATE` |

Nenhum deles era observável: o giro fabricado entrava no pipeline como um giro legítimo e a perda
nunca aparecia em lugar nenhum. Este ADENDO conserta os 4 **e** torna o descarte contável.

### B. Lógica de alinhamento virou módulo puro (`extension/phase_align.js`, UMD)

Zero dependência nova; carregado por `importScripts` no worker e por `require` no `node --test`.

- `fingerprint(numbers)` — assinatura dos **12** itens (era 5).
- `countNewSpins(novos, antigos, strict)` → **`{k, matched, overlap, reason}`**. Em `strict`: exige
  `overlap >= 2` para qualquer `k >= 1`, aceita **`k === 0`** (leitura idêntica = noop legítimo) e,
  quando nada casa, devolve `matched:false` — nunca mais o "1 conservador".
- `decideTick(input)` — decisão pura do tick: `send | skip | rebaseline | baseline_init | noop`.
- `createSerialQueue` / `createReentrancyGuard` / `createHydrationGate` — as três primitivas de
  concorrência, testáveis fora do Chrome.

### C. Single-writer, fail-closed e frame pegajoso (`extension/background.js`)

- **`mutateState(fn)`**: todo read-modify-write do estado passa por uma fila serial. Os efeitos
  (envio WS, captura de frame) ficam **fora** do lock — a fila nunca reentra.
- **`_readGuard`**: o tick atrasado **desiste** em vez de enfileirar; `onAlarm` agora dá `await`.
- **`_hydrationGate`**: nenhuma decisão de fase ocorre antes de o storage responder (uma vez só).
- **Fail-closed**: se `phase_align.js` não carregar, a leitura é **suspensa** — não existe caminho
  de degradação para o algoritmo antigo.
- **`selectNumbersFrame`** sticky-first: o frame que já funcionou vence a "lista mais longa" de um
  frame vizinho (lobby), e os dados de sessão são reordenados para virem do **mesmo** frame.
- **Kill-switch `DIR20_ENABLED`**: `false` passa `strict:false` para o módulo e reproduz bit-a-bit a
  semântica da v3.9.1 — **um único caminho de código**, e o rollback é ele próprio testado.

### D. A perda virou número (`state.dir20` + `client_health` + popup)

`unalignedStreak`, `skippedUnaligned`, `rebaselines`, `flipsReverted`, `lastReason`, `lastFrameId`,
`lastRoundId`, `baselineTable` — persistidos (round-trip em `save`/`load`/`reset`) e transmitidos no
bloco **aditivo** `client_health` (dentro do `register` e de cada `novo_resultado`), junto de
`ext_version`. O popup ganhou o painel "SPR-V2" com os mesmos contadores + a versão.

Após `DIR20_MAX_SKIPS` (5) descartes seguidos a extensão **re-ancora** o baseline: não inventa giro,
não flipa fase, e só reenvia `historico_inicial` quando há **evidência de troca de mesa**
(`sessionData.table` ≠ `baselineTable`). Desvio documentado: `round_id` **não** serve de evidência —
na Evolution ele muda a cada giro.

### E. Consumo retrocompatível do `phase_authority` (SPR-V1)

Só age com `state_sync.phase_authority.enabled === true`. Servidor antigo (campo ausente) ou com a
capability desligada ⇒ reconciliação **desarmada** — auto-desarme em qualquer rollback do servidor.
Com ela ligada: (1) reconciliação contínua da fase pela autoridade e (2) reversão do flip local de um
giro que o servidor **não contou**. Ressalva declarada: a detecção da rejeição é **heurística por
`spin_seq` inalterado após 2,5 s**, porque o `state_sync` não correlaciona o `trace_id` do giro
enviado. Falso positivo é corrigido no ciclo seguinte pela reconciliação contínua. **Dívida:**
correlação por `trace_id` no contrato do SPR-V1.

### F. Impacto ISO/IEC 25010

| Característica | Antes | Depois | Por quê |
|---|---|---|---|
| **Confiabilidade** | 8.0 | **9.0** | O dado de entrada deixa de ser fabricado: sem alinhamento não há envio, flip nem re-baseline silencioso. Corrida de reentrância e de boot eliminadas por construção (fila serial + gate), não por ordenação sortuda |
| **Manutenibilidade** | 8.5 | **9.0** | A decisão de fase saiu de 300 linhas de service worker para um módulo puro de 338 linhas com 49 testes; o harness `node:vm` executa o `background.js` **real** com fakes de `chrome.*` — o worker MV3 deixou de ser território não-testável |
| **Adequação funcional** | 8.5 | 8.5 | Nenhuma regra de negócio mudou; o que muda é a fidelidade da entrada |
| **Usabilidade** | 8.5 | **8.7** | A perda passou a ser visível ao operador (painel + versão no popup) em vez de silenciosa |
| **Compatibilidade** | 7.0 | 7.0 | Campos estritamente aditivos; servidor ignora chaves desconhecidas — nenhuma mudança em `server/` |
| Segurança / Desempenho / Portabilidade | — | — | Sem alteração |

**Scorecard: 8.5 → 8.7/10.**

### G. Obrigações assumidas

1. `phase_align.js` é **pré-requisito de execução**: qualquer refactor que quebre o `importScripts`
   deixa a extensão inerte (por design). O log de erro diz `fail-closed`.
2. Todo novo write de estado nasce dentro de `mutateState` — escrita direta em `chrome.storage.local`
   para chaves do `escutaState` é regressão.
3. Todo campo novo em `dir20` entra em `dir20Defaults()` (round-trip garantido por `ensureDir20`).
4. **Premissa MV3 a verificar em campo:** `periodInMinutes: 0.0333` (~2 s) só é honrado com a extensão
   **unpacked**; empacotada, o Chrome faz clamp para 30 s. O roteiro de instalação usa unpacked.
5. **Gap declarado (não entregue):** o `client_health` *contínuo* pedido no Bloco 4.2 do brief. A
   extensão **não possui keepalive/ping WS** — o alarme `keepAlive` apenas recria o `readLoop`. Enviar
   um `register` periódico reavaliaria a eleição de MASTER (`connection_manager.update_device_id`,
   incidente de 13/06). A telemetria viaja no `register` do `onopen` e em cada `novo_resultado`; o
   heartbeat dedicado fica para um sprint que crie a mensagem no contrato.

### H. Rollback — 3 camadas, da mais barata para a mais cara

| # | Camada | Ação | Efeito |
|---|--------|------|--------|
| 1 | **Kill-switch** | `DIR20_ENABLED = false` em `extension/background.js` + ↻ na extensão | `strict:false` ⇒ semântica v3.9.1 bit-a-bit; telemetria e single-writer permanecem |
| 2 | **Binário anterior** | `git archive <sha-3.9.1> extension/ -o ext-3.9.1.zip` e carregar essa pasta | Extensão 3.9.1 íntegra |
| 3 | **Código** | `git revert` do PR | Base restaurada |

Nenhuma camada exige ação no servidor: `server/`, `state/`, `app_config/` e o schema **não foram
tocados** — não há migração para desfazer.

### I. Code-review pós-implantação — 4 achados, todos corrigidos e travados por teste

O review encontrou três defeitos que tornariam o Bloco 4.4 **inerte ou enganoso em produção**
(passavam nos testes originais porque nenhum deles emitia o eco do popup):

1. **O eco automático do popup desarmava o PA-ACK.** O `storage.onChanged` disparado pelo próprio
   flip voltava ao worker como `setDirection(manual:false)` e limpava a expectativa de eco — o flip
   de um giro rejeitado nunca seria revertido. Correção em duas frentes: o handler só limpa quando
   `isManualCorrection`, e o popup passou a distinguir **`reflectDirection` (pinta)** de
   **`setDirection` (comanda)**. Abrir o popup também deixou de contar como âncora do operador.
2. **O guard era armado DEPOIS do envio pela rede.** Entre o flip e o `sendToWebSocket` há awaits
   (storage, dealMeta, `client_health`) e o heartbeat de 1 s cabe nessa janela: a reconciliação
   contínua via um snapshot **pré-giro** e desfazia a fase recém-avançada. Pior, `paSeqBeforeSend`
   era fotografado após o envio — um heartbeat já contabilizado classificaria um giro **aceito**
   como rejeitado. Agora flip e guard são gravados na **mesma `mutateState`**, e o guard é desarmado
   quando o envio falha.
3. **`flipsReverted` subia sem reversão.** O incremento estava fora do `if` que de fato reverte:
   servidor sem `direction`, ou já na mesma fase, inflava a métrica de perda que alimenta o popup e
   o `client_health`. Movido para dentro do ramo que atribui a fase.
4. **A suíte `tests/js/` não rodava em CI.** Nenhum workflow tinha Node e o `pytest.ini` só coleta
   `test_*.py`. Novo job `extension-tests` em `.github/workflows/ci.yml`, incluído no gate agregador
   `ci-ok`. (Detalhe fixado no step: `node --test tests/js/` falha ao resolver o diretório — o glob
   `tests/js/*.test.js` é obrigatório.)

Cada correção ganhou um teste de regressão (`REVIEW#1..#3` + envio-que-falha), e cada um foi
**verificado falhando** contra o código pré-correção antes de ser aceito.

### J. Regressão e arquivos

- **`node --test "tests/js/*.test.js"` → 53 passed / 0 failed** (28 do módulo puro + 25 de fluxo no `background.js` real).
  Agora executados em CI pelo job `extension-tests` (gate `ci-ok`).
- **`pytest tests/` → 796 passed, 9 skipped, 1 xfailed.**
- `tools/lint_silent_except.py` → OK.
- Tocados: **novos** `extension/phase_align.js`, `tests/js/{chrome_harness,phase_align.test,background_flow.test}.js`;
  **alterados** `extension/background.js`, `extension/popup.js`, `extension/popup.html`,
  `extension/manifest.json` (3.9.1 → **3.10.0**), `.github/workflows/ci.yml` (job `extension-tests`),
  `tests/test_dir13_lock_total.py` (o lock de versão
  passou de igualdade literal para piso por tupla `>= (3,9,1)` — igualdade quebrava a cada bump sem
  sinalizar regressão alguma). Backend Python **intacto**.

---

## PARTE I — ARQUITETURA COMPLETA DO SOFTWARE


---

### 1. Visão Geral

O **Roleta Cloud** é um backend em tempo real para processamento de dados de roleta europeia. Recebe resultados (spins) via WebSocket a partir de uma extensão Chrome, aplica análise estatística com a estratégia proprietária M15-ADA (Adaptive Dual Algorithm — 17 números), e retorna sugestões de aposta para um overlay no navegador.

```
┌─────────────────────┐         WebSocket (ws/wss)        ┌─────────────────────┐
│   Extensão Chrome   │ ◄──────────────────────────────── │   Roleta Cloud      │
│   (content.js)      │ ────────────────────────────────► │   (Python 3.12)     │
│                     │   spins, histórico, comandos      │                     │
│   • Extrator DOM    │   ◄── sugestões, state_sync       │   • WebSocket Server│
│   • Overlay UI      │                                   │   • Game Engine     │
│   • Popup Dashboard │                                   │   • M15-ADA Strategy│
└─────────────────────┘                                   │   • SQLite DB       │
                                                          └─────────────────────┘
```

**Stack Tecnológico:**

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Linguagem | Python | 3.12 |
| Transporte | websockets | ≥ 12.0 |
| Validação | Pydantic | ≥ 2.0 |
| Configuração | pydantic-settings | ≥ 2.0 |
| Logging | structlog | ≥ 24.0 |
| Banco de Dados | SQLite 3 (WAL mode) | Built-in |
| Containerização | Docker | compose v2 (sem version attr) |
| Cliente | Extensão Chrome | Manifest V3 |

---

### 2. Estrutura de Diretórios

```
Roleta Cloud/
├── main.py                          # Entry point (49 LOC)
├── VERSION                          # Versão semântica (4.3.0)
├── requirements.txt                 # Dependências Python
├── Dockerfile                       # Imagem Docker (python:3.12-slim)
├── docker-compose.yml               # Orquestração com volume persistente
├── state.json                       # Estado in-memory persistido (atômico)
├── SECURITY.md                      # Política de segurança
│
├── app_config/                      # ── Configuração ──
│   └── settings.py                  # Pydantic Settings (env vars)
│
├── core/                            # ── Núcleo Imutável ──
│   ├── roulette.py                  # Modelo físico da roleta (311 LOC)
│   ├── engine.py                    # Motor de jogo puro (130 LOC)
│   └── logging_config.py            # Configuração structlog (55 LOC)
│
├── models/                          # ── Modelos de Dados ──
│   ├── input.py                     # SpinInput (Pydantic)
│   ├── output.py                    # SuggestionOutput, AckOutput, ErrorOutput
│   └── trace.py                     # TraceContext para observabilidade
│
├── strategies/                      # ── Estratégias de Análise ──
│   ├── base.py                      # StrategyBase (ABC) + StrategyResult
│   └── sda17.py                     # M15-ADA (IQR + Weighted Median + Drift + M02-PctSigmoid Triple Focus)
│
├── state/                           # ── Estado do Jogo ──
│   ├── game.py                      # GameState + MartingaleState (493 LOC)
│   ├── timeline.py                  # Timeline por direção (deque)
│   └── bet_advisor.py               # Kill Switch Advisor (Triple Rate)
│
├── server/                          # ── Camada de Rede ──
│   ├── websocket.py                 # Servidor WebSocket + heartbeat
│   ├── connection_manager.py        # Master/Slave + grace period
│   ├── message_handler.py           # Dispatcher de mensagens (473 LOC)
│   ├── analytics_handler.py         # Queries analíticas via WS
│   ├── extractor_service.py         # Configuração dinâmica de mesas
│   └── configs/                     # Templates JSON de providers
│
├── auth/                            # ── Autenticação ──
│   └── middleware.py                # API Key (HMAC-safe) / bypass mode
│
├── database/                        # ── Persistência ──
│   ├── __init__.py                  # Factory singleton
│   ├── models.py                    # Decision, Session, GaleWindow, WindowPlay
│   ├── repository.py                # Interface abstrata (ABC)
│   ├── sqlite_repo.py               # Implementação SQLite (~850 LOC)
│   └── service.py                   # DatabaseService (negócio)
│
├── extension/                       # ── Extensão Chrome ──
│   ├── manifest.json                # Manifest V3
│   ├── background.js                # Service worker
│   ├── content.js                   # Extrator DOM + overlay
│   ├── popup.html / popup.js        # Dashboard popup
│   └── overlay.css                  # Estilos do overlay
│
├── tests/                           # ── Testes ──
│   ├── conftest.py                  # Configuração pytest
│   ├── test_core.py                 # Testes RouletteCore (123 LOC)
│   ├── test_sda17.py                # Testes M15-ADA (56 LOC)
│   ├── test_bet_advisor.py          # Testes Kill Switch (69 LOC)
│   ├── test_game_state.py           # Testes GameState (116 LOC)
│   └── test_db_query.py             # Testes queries DB (32 LOC)
│
├── tools/                           # ── Ferramentas ──
│   └── backtest_from_db.py          # Backtest offline (339 LOC)
│
├── scripts/                         # ── Scripts de Deploy ──
│   └── setup_server.sh              # Setup do servidor Debian
│
├── data/                            # ── Dados Persistentes ──
│   └── decisions.db                 # ⚠️ CÓPIA LOCAL (NÃO é o banco de produção)
│                                    # O banco real está no Docker Named Volume
│                                    # Ver seção "Acesso ao Banco de Dados"
│
└── archive/                         # ── Código legado arquivado ──
```

---

### 3. Diagrama de Componentes e Dependências

```
                    ┌──────────────────────────────────────────────────┐
                    │                  main.py                         │
                    │  • Signal handlers (SIGINT/SIGTERM)              │
                    │  • asyncio.run(start_server())                   │
                    └──────────────┬───────────────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────────────┐
                    │          server/websocket.py                      │
                    │  • WebSocket Server (ws/wss)                      │
                    │  • Heartbeat broadcast (1s)                       │
                    │  • SSL/TLS opcional                               │
                    │  • Handler de conexão → connection_manager        │
                    └───┬──────────────────────┬───────────────────────┘
                        │                      │
         ┌──────────────▼──────┐  ┌────────────▼──────────────────────┐
         │ connection_manager  │  │      message_handler              │
         │ • Master/Slave      │  │  • Dispatcher por msg_type        │
         │ • Grace period 10s  │  │  • novo_resultado → engine        │
         │ • Device ID track   │  │  • historico_inicial              │
         │ • MAX_CONNECTIONS   │  │  • correcao_historico             │
         │ • Broadcast         │  │  • nova_sessao                   │
         └─────────────────────┘  │  • register / force_master       │
                                  │  • extrair_mesa / listar_mesas   │
                                  │  • analytics (delegado)          │
                                  └───┬───────────┬──────────────────┘
                                      │           │
                       ┌──────────────▼──┐  ┌─────▼────────────────────┐
                       │  core/engine.py  │  │ analytics_handler        │
                       │  GameEngine      │  │ • summary / sessions     │
                       │  • process_spin  │  │ • gale_history           │
                       │  • check_pred    │  │ • performance_timeline   │
                       │  • SDA + TR      │  │ • decision_log           │
                       └──┬────────┬──────┘  └─────────────────────────┘
                          │        │
           ┌──────────────▼──┐  ┌──▼─────────────────────────┐
           │  strategies/    │  │  state/                      │
           │  sda17.py       │  │  ├── game.py (GameState)     │
           │  • IQR filter   │  │  │   • Duas timelines        │
           │  • Weighted Med │  │  │   • 4 listas performance  │
           │  • Drift detect │  │  │   • 2 Martingales (CW/CCW)│
           │  • Smart Score  │  │  │   • Persistência atômica  │
           │  • M02 Sigmoid  │  │  ├── timeline.py (deque)     │
           │  • 17 números   │  │  └── bet_advisor.py          │
           └──────┬──────────┘  │  └── bet_advisor.py          │
                  │             │      • Kill Switch (C4+SDA≤2)│
                  │             └──────────────────────────────┘
                  │
           ┌──────▼──────────┐
           │  core/roulette  │
           │  RouletteCore   │
           │  • WHEEL_SEQUENCE│
           │  • 37 slots     │
           │  • Cálc. circular│
           │  • Singleton    │
           └─────────────────┘

           ┌─────────────────────────────────────────┐
           │           database/                      │
           │  ┌──────────────────────────────────┐   │
           │  │ repository.py (ABC)               │   │
           │  │ DecisionRepository               │   │
           │  └──────────┬───────────────────────┘   │
           │             │ implementa                 │
           │  ┌──────────▼───────────────────────┐   │
           │  │ sqlite_repo.py (~850 LOC)         │   │
           │  │ • WAL mode + busy_timeout         │   │
           │  │ • 4 tabelas: sessions, decisions, │   │
           │  │   gale_windows, window_plays       │   │
           │  │ • 10 índices                       │   │
           │  └──────────────────────────────────┘   │
           │  ┌──────────────────────────────────┐   │
           │  │ service.py (Singleton)            │   │
           │  │ • track_gale_window               │   │
           │  │ • get_window_history              │   │
           │  └──────────────────────────────────┘   │
           └─────────────────────────────────────────┘
```

---

### 4. Fluxo de Dados Principal

```
EXTENSÃO CHROME                      SERVIDOR PYTHON
─────────────────                    ─────────────────

1. DOM detecta spin ──────────────► WebSocket recebe
   {numero, direcao,                 message_handler.process_message()
    trace_id, t_client}

2.                                   Verificar role (MASTER only)
                                     Verificar duplicata (hash)

3.                                   check_prediction(numero)
                                     ├── Compara com pending_prediction
                                     ├── Registra em performance_sda17
                                     └── Se bet_placed: performance_bet

4.                                   Martingale update (se apostou)
                                     ├── update(hit, global_hit=hit)
                                     ├── sync_global() → martingale oposto
                                     ├── Anti-Martingale: HIT escala, MISS→G1
                                     └── track_gale_window() → DB

5.                                   process_spin(numero, direcao)
                                     ├── Calcula força (distância circular)
                                     ├── Adiciona à timeline CW ou CCW
                                     └── game_state.save() (atômico)

6.                                   M15-ADA analyze(target_timeline)
                                     ├── IQR outlier rejection
                                     ├── Weighted median (decay=0.8)
                                     ├── Drift detection
                                     ├── Smart Score (1-6)
                                     ├── M02-PctSigmoid offset C2/C3
                                     └── Triple Focus (17 números)

7.                                   Kill Switch Advisor
                                     ├── C4/M6/L12 rates
                                     ├── KILL se C4=0% + SDA≤2
                                     └── APOSTAR em todos outros casos

8.                                   Decision final
                                     ├── APOSTAR: get_gale(score, c4_rate, confidence)
                                     │   Regra 6: "alta"→G1, "baixa"→G1, "media"→escalável
                                     │   action_reason = "SDA score=X | GY SZ GSW | C4=XX%"
                                     ├── FALLBACK: SDA insuficiente + dados → G1 seguro
                                     ├── PULAR: TR vetou ou SDA sem dados
                                     └── save_decision() → DB

9. ◄──────────────────────────────── Resposta {sugestao}
   Overlay renderiza                 ├── acao, numeros, centro, regiao
   ação no navegador                 ├── confianca, martingale, gale
                                     ├── bet_advice (TR details)
                                     └── trace completo

10.                                  Broadcast trace para dashboards
                                     ├── Steps com timestamps
                                     └── Performance stats
```

---

### 5. Modelo de Dados (SQLite)

```
┌──────────────┐       ┌─────────────────┐       ┌──────────────────┐
│  sessions    │       │   decisions      │       │  gale_windows    │
├──────────────┤       ├─────────────────┤       ├──────────────────┤
│ id (PK)      │◄──┐   │ id (PK, AUTO)   │       │ id (PK, AUTO)    │
│ start_time   │   │   │ session_id (FK) ─┼──────►│ direction        │
│ end_time     │   │   │ timestamp        │       │ gale_level       │
│ total_spins  │   │   │ spin_number      │       │ started_at       │
│ total_bets   │   │   │ spin_direction   │       │ ended_at         │
│ total_hits   │   │   │ spin_force       │       │ total_hits       │
│ total_profit │   │   │ tr_should_bet    │       │ total_plays      │
│ max_gale     │   │   │ tr_confidence    │       │ result           │
│ total_stops  │   │   │ tr_reason        │       │ next_level       │
└──────────────┘   │   │ tr_c4/m6/l12_rate│       │ sda17_rate_start │
                   │   │ sda_should_bet   │       │ bet_rate_start   │
                   │   │ sda_score/center │       │ calibration_off  │
                   │   │ sda_numbers (JSON)│      └───────┬──────────┘
                   │   │ sda_predicted_f   │              │
                   │   │ final_action      │              │
                   │   │ action_reason     │      ┌───────▼──────────┐
                   │   │ gale_level/hits   │      │  window_plays    │
                   │   │ result_hit/actual │      ├──────────────────┤
                   │   │ calibration_off   │      │ id (PK, AUTO)    │
                   │   │ perf_snapshot(JSON)│     │ window_id (FK)   │
                   │   └─────────────────┘       │ play_number      │
                   │                              │ spin_number      │
                   └──────────────────────────────│ spin_direction   │
                                                  │ spin_force       │
                                                  │ center_predicted │
                                                  │ hit / actual     │
                                                  │ sda_score        │
                                                  │ tr_confidence    │
                                                  │ tr_reason        │
                                                  └──────────────────┘

Índices: 10 (session, timestamp, action, gale_level, direction, level, started, window_id, active)
Constraint: UNIQUE idx_gale_windows_active — apenas 1 janela aberta por direção
```

---

### 6. Sistema de Decisão (Pipeline M15-ADA v4.3 + Kill Switch)

```
                       Forças da Timeline (últimas 7, mín 2)
                              │
                    ┌─────────▼──────────┐
                    │  IQR Outlier Filter │  Remove forças fora de [Q1-1.5·IQR, Q3+1.5·IQR]
                    │  (skip se N < 4)    │  Fallback: usa todos se < 2 sobrevivem
                    └─────────┬──────────┘
                              │ clean forces
                    ┌─────────▼──────────┐
                    │  Weighted Median    │  Peso = 0.8^posição (mais recente = maior peso)
                    │  (decay = 0.8)      │  Expansão: força × (weight × 10) repetições
                    └─────────┬──────────┘
                              │ predicted_force (base)
                    ┌─────────▼──────────┐
                    │  Drift Detection   │  Se últimas 3 forças são monotônicas:
                    │  (tendência)        │  drift_adj = sum(diffs) × 0.5
                    └─────────┬──────────┘
                              │ predicted_force (ajustada) → C1
                    ┌─────────▼──────────┐
                    │  M02-PctSigmoid    │  Offsets adaptativos C2/C3:
                    │  Offset Controller │  sigmoid(error%) × 2.0 por direção
                    │  (v4.3+)           │  Hit: tighten 8% → center=10
                    │                    │  Miss: expand na dir do erro ±cross 30%
                    │                    │  Clamp: [7, 13] | Independente CW/CCW
                    └─────────┬──────────┘
                              │ C1 + off_c2/off_c3
                    ┌─────────▼──────────┐
                    │  Triple Focus      │  C1: centro (raio 3 = 7 nums)
                    │  17 números        │  C2: CW de C1 (raio 2 = 5 nums)
                    │  (45.9% cobertura) │  C3: CCW de C1 (raio 2 = 5 nums)
                    └─────────┬──────────┘
                              │ {should_bet, center, numbers[17], score}
                    ┌─────────▼──────────┐
                    │  Smart Score        │  score = survival × 3 + tightness × 3 + stable_bonus
                    │  (1-6)              │  tightness = 1 - spread/15
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Kill Switch (TR)   │  VETA se: C4 == 0% AND sda_score ≤ 2
                    │  Advisor v2         │  APROVA em todos os outros casos
                    └─────────┬──────────┘
                              │ {acao: APOSTAR | PULAR}
                    ┌─────────▼──────────┐
                    │  Martingale State   │  SmartGale v5: Anti-Martingale
                    │  Streak Global Cross│  G1(R$21) → G2(R$42) → G3(R$63)
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Resposta ao Client │  JSON via WebSocket
                    │  + DB Logging       │  27 campos por decisão
                    └────────────────────┘
```

---

### 7. Protocolo WebSocket — Tipos de Mensagem

| Direção | Tipo | Descrição | Role |
|---------|------|-----------|------|
| `C → S` | `novo_resultado` | Novo spin {numero, direcao} | MASTER only |
| `C → S` | `historico_inicial` | Batch de spins históricos | MASTER only |
| `C → S` | `correcao_historico` | Reset + reprocessar | MASTER only |
| `C → S` | `nova_sessao` | Reset de sessão/dealer | Any |
| `C → S` | `get_state` | Solicita estado atual | Any |
| `C → S` | `register` | Registra device_id | Any |
| `C → S` | `force_master` | Força role MASTER | Any |
| `C → S` | `extrair_mesa` | Snapshot DOM da mesa | Any |
| `C → S` | `listar_mesas` | Lista mesas configuradas | Any |
| `C → S` | `get_analytics_*` | Queries analíticas | Any |
| `S → C` | `sugestao` | Resposta com ação + números | Broadcast |
| `S → C` | `state_sync` | Heartbeat 1s com estado | Broadcast |
| `S → C` | `trace` | Trace completo do pipeline | Broadcast |
| `S → C` | `role_assigned` | Role atribuído na conexão | Unicast |
| `S → C` | `role_changed` | Mudança de role | Unicast |
| `S → C` | `ack` | Confirmação de recebimento | Unicast |
| `S → C` | `error` | Erro com código + mensagem | Unicast |

---

### 8. Modelo de Conexão (Master/Slave)

```
┌──────────────────────────────────────────────────────────┐
│                SISTEMA MASTER / SLAVE                      │
├──────────────────────────────────────────────────────────┤
│                                                            │
│  Nova conexão → SLAVE (se já existe MASTER ativo)         │
│  Nova conexão → MASTER (se nenhum MASTER existe)          │
│                                                            │
│  MASTER desconecta:                                       │
│  ├── Grace period = 10 segundos                           │
│  ├── Se reconecta (mesmo device_id): restaura MASTER      │
│  └── Se não reconecta: último SLAVE promovido             │
│                                                            │
│  Apenas MASTER pode enviar:                               │
│  ├── novo_resultado                                       │
│  ├── historico_inicial                                    │
│  └── correcao_historico                                   │
│                                                            │
│  MAX_CONNECTIONS = 50                                     │
│  Rejeita com código 1013 ("Servidor lotado")              │
└──────────────────────────────────────────────────────────┘
```

> **Fix 13/06/2026 (v4.4.1) — deadlock de eleição corrigido:** o esquema acima
> tinha uma lacuna. Se o grace period expirava **sem nenhuma conexão** (nenhum
> SLAVE para promover) e o MASTER voltava depois, `update_device_id` **não** o
> repromovia (a reconexão exigia `< 10s` e o fallback exigia
> `last_master_device_id` vazio) → **deadlock: SLAVE permanente, todos os spins
> descartados** (incidente ~16h sem apostas). Agora: quando não há master **e** o
> grace já expirou, o **próximo REGISTER assume MASTER**; um device *diferente*
> permanece SLAVE apenas **dentro** do grace (protege a janela do master
> original). Escape manual: `force_master` (botão 🎯 na escuta). Detecção:
> alerta `RoletaNoMaster`. Runbook: `docs/runbooks/sem-apostas-master-slave.md`.

---

### 9. Containerização e Deploy

```yaml
# Docker Compose - Produção
services:
  roleta-cloud:
    image: python:3.12-slim
    ports: ["127.0.0.1:8765:8765"]
    volumes:
      - roleta-data:/app/data        # Banco SQLite persistido
      - ./state.json:/app/state.json # Estado do jogo
      - ./server/configs:/app/server/configs:ro
    environment:
      - WS_HOST=0.0.0.0
      - WS_PORT=8765
      - SSL_ENABLED=false
      - AUTH_ENABLED=false
    healthcheck:
      test: socket connect localhost:8765
      interval: 30s, timeout: 5s, retries: 3
    logging:
      driver: json-file
      max-size: 10m, max-file: 3
```

#### ⚠️ Acesso ao Banco de Dados de Produção

O banco SQLite de produção **NÃO** está em `/root/roleta-cloud/data/decisions.db`.
Ele reside no **Docker Named Volume** `roleta-data`:

| Caminho | Tipo | Status |
|---------|------|:------:|
| `/root/roleta-cloud/data/decisions.db` | Arquivo host | ❌ **STALE** — cópia antiga, não é atualizado |
| `/app/data/decisions.db` (container) | Named Volume | ✅ **PRODUÇÃO** — banco real e atual |
| `/var/lib/docker/volumes/roleta-cloud_roleta-data/_data/decisions.db` | Volume no disco | ✅ Mesmo arquivo que o container usa |

**Como acessar os dados reais:**

```bash
# ✅ CORRETO — via docker exec
docker exec -i roleta-cloud python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/decisions.db')
print(conn.execute('SELECT COUNT(*) FROM decisions').fetchone()[0])
"

# ✅ CORRETO — acesso direto ao volume no host
sqlite3 /var/lib/docker/volumes/roleta-cloud_roleta-data/_data/decisions.db "SELECT COUNT(*) FROM decisions;"

# ❌ ERRADO — arquivo host desatualizado (NÃO usar para análise)
sqlite3 /root/roleta-cloud/data/decisions.db
```

**Backup do banco de produção:**

```bash
docker exec roleta-cloud cp /app/data/decisions.db /app/data/decisions_backup_$(date +%Y%m%d_%H%M%S).db
```

---

### 9. Banco de Dados — Inventário e Fluxo Completo

> **Atualizado em:** 27/Mar/2026 (pós-refatoração)

#### 9.1 Bancos de Produção Ativos

| # | Localização | Tipo | Função | Acesso |
|:-:|-------------|------|--------|--------|
| 1 | Docker Volume `roleta-data` | SQLite (WAL) | Banco principal: decisions, sessions, gale_windows, window_plays | `docker exec roleta-cloud python3 -c "..."` |
| 2 | Host `state.json` (bind mount) | JSON | Estado do jogo: timelines, martingale, pending_prediction | Leitura direta no host ou container |
| 3 | Chrome Extension | `chrome.storage.local/session` | Estado da extensão: escutaState, currentDirection, overlayUIState | DevTools → Application → Storage |

#### 9.2 Bancos Legado (somente leitura/referência)

| # | Localização | Tamanho | Conteúdo |
|:-:|-------------|:-------:|----------|
| 1 | `archive/legado_bancos/sda_datalake.db` | 4.76 MB | 15.109 rows de performance_log (18 preditores antigos) |
| 2 | `archive/legado_bancos/microservico_datalake.db` | 40 KB | 90 rows de previsões v2 |

#### 9.3 Schema do Banco de Produção (SQLite)

```sql
-- sessions: metadados de cada sessão de jogo
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    start_time DATETIME NOT NULL,
    end_time DATETIME,               -- Preenchido ao finalizar (shutdown/reset)
    total_spins INTEGER DEFAULT 0,   -- Atualizado a cada 10 decisões e no shutdown
    total_bets INTEGER DEFAULT 0,
    total_hits INTEGER DEFAULT 0,
    total_profit REAL DEFAULT 0.0,
    max_gale_reached INTEGER DEFAULT 1,
    total_stops INTEGER DEFAULT 0,   -- DEPRECATED (Smart Gale v5 não para)
    total_resets INTEGER DEFAULT 0   -- Smart Gale v5: resets a G1 após miss
);

-- decisions: cada spin processado pelo sistema
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT REFERENCES sessions(id),
    spin_number INTEGER, spin_direction TEXT, spin_force INTEGER,
    tr_should_bet BOOLEAN, tr_confidence TEXT, tr_reason TEXT,
    tr_c4_rate REAL, tr_m6_rate REAL, tr_l12_rate REAL,
    sda_should_bet BOOLEAN, sda_score INTEGER, sda_center INTEGER,
    sda_centers TEXT,  -- JSON array [C1, C2, C3] — SDA-21
    sda_numbers TEXT, sda_predicted_force INTEGER,
    final_action TEXT, action_reason TEXT,
    gale_level INTEGER, gale_window_hits INTEGER,
    gale_window_count INTEGER, gale_bet_value INTEGER,
    result_hit BOOLEAN, result_actual INTEGER,
    calibration_offset INTEGER,  -- DEPRECATED (sempre 0 desde v1.5)
    calibration_error INTEGER,   -- DEPRECATED
    performance_snapshot TEXT
);

-- gale_windows: janelas de Martingale para ML/analytics
CREATE TABLE gale_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    direction TEXT NOT NULL, gale_level INTEGER NOT NULL,
    started_at DATETIME NOT NULL, ended_at DATETIME,
    total_hits INTEGER DEFAULT 0, total_plays INTEGER DEFAULT 0,
    result TEXT,  -- 'streak', 'reset', 'info', 'orphan'
    next_level INTEGER,
    sda17_rate_at_start REAL, bet_rate_at_start REAL,
    calibration_offset INTEGER
);
-- CONSTRAINT: apenas 1 janela ativa por direção
CREATE UNIQUE INDEX idx_gale_windows_active ON gale_windows(direction) WHERE ended_at IS NULL;

-- window_plays: jogadas individuais dentro de cada janela
CREATE TABLE window_plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    window_id INTEGER REFERENCES gale_windows(id),
    play_number INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    spin_number INTEGER, spin_direction TEXT, spin_force INTEGER,
    center_predicted INTEGER, hit BOOLEAN, actual_number INTEGER,
    sda_score INTEGER, tr_confidence TEXT, tr_reason TEXT
);
```

#### 9.4 Fluxo de Dados Completo

```
Chrome Extension (chrome.storage)
    │ WebSocket (wss://roleta.xma-ia.com/ws)
    ▼
message_handler.py
    ├─ check_prediction(numero)        → Verifica predição anterior
    ├─ SmartGaleV5.update(hit, global_hit) → Atualiza gale + streak global
    ├─ SmartGaleV5.sync_global(hit)    → Sincroniza martingale oposto
    ├─ db_service.track_gale_window()  → Grava em gale_windows + window_plays
    ├─ GameState.process_spin()        → Atualiza timeline + forças
    ├─ GameState.save()                → Grava state.json (bind mount)
    ├─ sda17.analyze()                 → M15-ADA Triple Focus 17 nums → predição
    ├─ sda17.update_adaptive()         → M02-PctSigmoid offset feedback
    ├─ bet_advisor.analyze()           → Kill Switch Advisor → c4_rate
    ├─ SmartGaleV5.get_gale(score,c4)  → Nível de aposta (1×/2×/3×)
    ├─ db_service.save_decision()      → Grava em decisions (Named Volume)
    ├─ db_service.update_session_stats() → A cada 10 decisões
    └─ WebSocket.send(overlay)         → Envia sugestão para Chrome
```

#### 9.5 Ciclo de Vida da Sessão

| Evento | Ação no DB |
|--------|-----------|
| Extensão envia `nova_sessao` | `create_session()` → nova row em sessions |
| A cada spin | `save_decision()` → nova row em decisions |
| A cada 10 decisões | `update_session_stats()` → atualiza totais em sessions |
| Reset de sessão | `end_session()` → define end_time + stats finais → `create_session()` nova |
| Shutdown (SIGTERM/SIGINT) | `end_session()` → finaliza sessão + `game_state.save()` |

---

## PARTE II — ANÁLISE ISO/IEC 25010

A norma **ISO/IEC 25010:2011** define 8 características de qualidade de produto de software, cada uma com sub-características. A seguir, cada uma é avaliada contra o estado atual do Roleta Cloud v4.3.1.

---

### 1. ADEQUAÇÃO FUNCIONAL (Functional Suitability)

> *O produto fornece funções que atendem às necessidades declaradas e implícitas quando usado nas condições especificadas.*

#### 1.1 Completude Funcional

| Requisito | Status | Evidência |
|-----------|:------:|-----------|
| Receber spins em tempo real | ✅ Completo | `message_handler.handle_new_result()` — validação Pydantic (0-36) |
| Calcular predições (M15-ADA) | ✅ Completo | Pipeline IQR → Weighted Median → Drift → Score → M02-PctSigmoid → Triple Focus (17 números, offsets adaptativos por direção) |
| Gerenciar Martingale | ✅ Completo | SmartGale v5: Anti-Martingale com streak global cross-direction, take-profit G3, c4 threshold 0.15, fallback G1 |
| Kill Switch (Triple Rate) | ✅ Completo | Veta apenas catástrofe (C4=0% + SDA≤2), mínimo intervencionista |
| Persistir decisões | ✅ Completo | SQLite com 27 campos, 4 tabelas, 10 índices |
| Analytics via WebSocket | ✅ Completo | 5 queries (summary, sessions, gale, timeline, decision_log) |
| Extensão Chrome | ✅ Completo | Manifest V3, DOM extractor, overlay, popup dashboard |
| Similarity Search (LanceDB) | ⏸️ Preparado | Código em `archive/vector_store.py`, ativação quando volume > 5.000 decisões |

**Avaliação: 9/10** — Todas as funcionalidades declaradas estão implementadas e operacionais.

#### 1.2 Correção Funcional

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Sequência da roleta europeia | ✅ | 37 números, ordem física verificada |
| Cálculo de força circular | ✅ | Testes em `test_core.py` (123 LOC) |
| IQR com N < 4 | ✅ | BUG-009 corrigido — skip IQR quando N < 4 |
| Drift formula | ✅ | Corrigido para `int(sum(diffs) * 0.5)` |
| Direção do Martingale | ✅ | Usa `pending_prediction["direction"]` (target) |
| Deduplicação de spins | ✅ | Hash `{numero}_{timestamp//1000}` |
| Validação de direção | ✅ | BUG-011: só aceita "horario" / "anti-horario" |

**Avaliação: 8/10** — Bugs críticos foram corrigidos. Colunas mortas no schema (`calibration_offset/error`) ainda presentes.

#### 1.3 Pertinência Funcional

O sistema executa apenas o que é necessário: recebe dados, analisa, decide, retorna. Não há funcionalidades desnecessárias no caminho crítico. O módulo `vector_store.py` está corretamente desativado até o volume de dados justificar sua ativação.

**Avaliação: 9/10**

---

### 2. EFICIÊNCIA DE DESEMPENHO (Performance Efficiency)

> *Desempenho relativo à quantidade de recursos usados sob condições declaradas.*

#### 2.1 Comportamento Temporal

| Métrica | Valor | Análise |
|---------|-------|---------|
| Latência spin→resposta | < 50ms (típico) | Observado via `TraceContext` — pipeline é CPU-bound puro |
| Heartbeat interval | 1 segundo | Broadcast de estado para todos os clientes |
| Grace period reconexão | 10 segundos | Configurável via `MASTER_GRACE_PERIOD` |
| Ping/Pong WebSocket | 20s interval, 60s timeout | Mantém conexão viva |

**Avaliação: 9/10** — Latência sub-50ms é excelente para tempo real. O pipeline inteiro (IQR + Median + Drift + Score) é O(n) com n ≤ 7 forças.

#### 2.2 Utilização de Recursos

| Recurso | Uso | Otimização |
|---------|-----|-----------|
| Memória | ~30MB base | Timelines com `deque(maxlen=45)` — auto-trim |
| Performance lists | `deque(maxlen=12)` | BUG-009 corrigido — impossível crescer indefinidamente |
| Conexões WS | Max 50 | `MAX_CONNECTIONS` em ConnectionManager |
| SQLite | WAL mode + busy_timeout=5s | Permite leituras concorrentes |
| Logs | JSON rotacionado (10MB × 3) | Via Docker logging driver |
| Estado | ~2KB JSON | Escrita atômica com `tempfile` + `os.replace` + fallback Docker |
| SQLite conns | Gerenciadas | Conexões com `try/finally: conn.close()` em cada operação |

**Avaliação: 9/10** — Uso eficiente. Conexões SQLite corretamente gerenciadas com close explícito.

#### 2.3 Capacidade

| Dimensão | Limite | Notas |
|----------|--------|-------|
| Conexões simultâneas | 50 | Rejeita com código 1013 |
| Timeline | 45 forças por direção | `max_timeline_size` em settings |
| Performance tracking | 12 resultados por lista | 4 listas × 2 direções |
| Decisões no DB | Ilimitado | SQLite suporta até ~140TB |
| Janelas Gale ativas | 1 por direção | Constraint UNIQUE no DB |

**Avaliação: 8/10**

---

### 3. COMPATIBILIDADE (Compatibility)

> *Grau em que um produto pode trocar informações e/ou executar suas funções enquanto compartilha o mesmo ambiente.*

#### 3.1 Coexistência

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Docker isolado | ✅ | Container independente, não interfere com outros serviços |
| Porta configurável | ✅ | `WS_PORT` via variável de ambiente |
| Volume dedicado | ✅ | `roleta-data` para SQLite — **acessar via `docker exec` ou path do volume** |

#### 3.2 Interoperabilidade

| Interface | Protocolo | Formato |
|-----------|----------|---------|
| WebSocket | ws:// / wss:// | JSON |
| Extensão Chrome | Manifest V3 | content script |
| Banco de Dados | SQLite 3 | Arquivo local |
| Configuração | ENV vars | `.env` file suportado |

**Avaliação: 7/10** — Sem REST API HTTP (apenas WebSocket). Isso limita integração com ferramentas externas (Grafana, APIs REST, webhooks). Interoperabilidade futura planejada via `analytics_handler`.

---

### 4. USABILIDADE (Usability)

> *Grau em que o produto pode ser usado por usuários especificados para atingir objetivos com eficácia, eficiência e satisfação.*

#### 4.1 Reconhecibilidade de Adequação

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Banner no startup | ✅ | ASCII art "ROLETA CLOUD v{VERSION}" — lê dinamicamente do arquivo `VERSION` |
| README.md | ✅ | Documentação de uso |
| Logs informativos | ✅ | Emojis como indicadores visuais (👑, 📱, 🔄, 🛑) |

#### 4.2 Apreensibilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Variáveis de ambiente documentadas | ✅ | Em `main.py` docstring e `docker-compose.yml` |
| Modelos Pydantic auto-documentados | ✅ | `SpinInput` com `Field(description=...)` |
| Formato de saída documentado | ✅ | `SuggestionOutput` com exemplos JSON Schema |

#### 4.3 Proteção contra Erros

| Mecanismo | Status | Detalhes |
|-----------|:------:|---------|
| Validação de entrada (0-36) | ✅ | Pydantic + validação manual em `handle_new_result` |
| Validação de direção | ✅ | BUG-011: rejeita direções inválidas |
| Deduplicação de spins | ✅ | Previne processamento duplo |
| MASTER-only para dados | ✅ | SLAVE não pode injetar dados |
| ErrorOutput estruturado | ✅ | Código HTTP + mensagem + trace_id |

**Avaliação: 8/10** — Boa usabilidade. Falta documentação de API WebSocket formal (AsyncAPI spec ou similar).

---

### 5. CONFIABILIDADE (Reliability)

> *Grau em que o sistema executa funções especificadas sob condições especificadas por um período de tempo especificado.*

#### 5.1 Maturidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Tratamento de exceções | ✅ | Try/catch em cada handler, fallback para `ErrorOutput` |
| Shutdown graceful | ✅ | `SIGINT/SIGTERM` handlers salvam estado |
| Escrita atômica de estado | ✅ | `tempfile` + `os.replace` previne corrupção |
| Migração de versão | ✅ | v1.3→v1.4→v1.5→v1.6 com fallback automático, sigmoid_off backward compat v4.2→v4.3 |
| DB WAL mode | ✅ | Resistente a crash mid-write |
| Heartbeat | ✅ | Detecção de conexões perdidas |

#### 5.2 Disponibilidade

| Mecanismo | Status | Detalhes |
|-----------|:------:|---------|
| Docker restart policy | ✅ | `unless-stopped` |
| Healthcheck | ✅ | Socket connect a cada 30s com 3 retries |
| Grace period Master | ✅ | 10s para reconexão sem perda de role |
| Promoção automática Slave→Master | ✅ | Último SLAVE é promovido se MASTER não reconectar |
| Restauração de janelas ativas | ✅ | `_init_active_window_ids()` no boot |

#### 5.3 Tolerância a Falhas

| Cenário | Comportamento | Risco Residual |
|---------|--------------|----------------|
| DB indisponível | Warning no log, continua sem persistir | Decisões perdidas silenciosamente |
| Spin duplicado | Ignorado (hash check) | Nenhum |
| JSON inválido | ErrorOutput com código 400 | Nenhum |
| JSON corrompido no DB | Fallback para default via _safe_json_loads() | Nenhum (v4.3.1) |
| Exceção no handler | ErrorOutput com código 500, conexão mantida | Stack trace pode vazar info interna |
| WebSocket desconecta | Remove de `connections`, grace period | Nenhum |
| Erro no heartbeat | Log de erro, continua | Broadcasting pode falhar silenciosamente |

#### 5.4 Recuperabilidade

| Mecanismo | Detalhes |
|-----------|---------|
| `state.json` | Restaura timelines, performance, Martingale, pending_prediction |
| SQLite WAL | Recuperação automática após crash |
| Migração automática | `GameState.load()` migra formato antigo automaticamente |
| Docker volume | Dados persistem além do ciclo de vida do container |

**Avaliação: 8/10** — Boa resiliência. Falta circuit breaker para DB e métricas de uptime.

---

### 6. SEGURANÇA (Security)

> *Grau em que um produto protege informações e dados de modo que pessoas ou sistemas tenham o grau de acesso apropriado.*

#### 6.1 Confidencialidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| API Key via ENV | ✅ | `ROLETA_API_KEY` nunca hardcoded |
| HMAC-safe comparison | ✅ | `hmac.compare_digest()` previne timing attacks |
| SSL/TLS opcional | ✅ | `wss://` com certificados Let's Encrypt |
| `.env` no .gitignore | ✅ | Política em `SECURITY.md` |
| Auth bypass padrão | ⚠️ | `AUTH_ENABLED=false` por padrão — aceitável para dev, risco em produção |

#### 6.2 Integridade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Validação de entrada | ✅ | Pydantic (0-36), direção validada |
| Master-only writes | ✅ | SLAVE não pode injetar dados no pipeline |
| Escrita atômica | ✅ | `os.replace` é atômico no filesystem |
| DB constraint | ✅ | UNIQUE index garante 1 janela ativa por direção |

#### 6.3 Não-repúdio

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Trace ID por operação | ✅ | `TraceContext` com timestamps por step |
| Decision log | ✅ | 27 campos incluindo `action_reason` |
| Structured logging | ✅ | JSON via structlog (arquivo + console) |
| Session tracking | ✅ | Cada sessão tem ID único |

#### 6.4 Responsabilidade (Accountability)

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Connection ID por sessão | ✅ | UUID[:8] por conexão |
| Device ID tracking | ✅ | Identificação persistente do dispositivo |
| Role assignment logging | ✅ | Log de cada atribuição/mudança de role |

#### 6.5 Autenticidade

| Aspecto | Status | Risco |
|---------|:------:|-------|
| API Key + HMAC | ✅ | Quando `AUTH_ENABLED=true` |
| JWT / Keycloak | ⏸️ Planejado | Placeholders em `settings.py` (TASK-003 das execuções) |
| Device ID validation | ⚠️ | Device ID é informado pelo cliente, sem verificação criptográfica |

**Avaliação: 6/10** — Auth bypass por padrão é risco em produção. Device ID sem verificação criptográfica permite spoofing de identidade. Stack traces em `ErrorOutput` (código 500) podem vazar informações internas. JWT/Keycloak ainda não implementado.

**Bugs identificados pós-implantação:**

| ID | Severidade | Descrição |
|----|:----------:|-----------|
| SEC-001 | ⚠️ Média | `ErrorOutput` com `message=str(e)` pode expor stack traces e caminhos internos ao cliente |
| SEC-002 | ⚠️ Média | Device ID sem assinatura criptográfica — cliente pode enviar qualquer `device_id` |
| SEC-003 | ~~🔵 Baixa~~ ✅ CORRIGIDO | Banner agora lê versão dinamicamente do arquivo `VERSION` (não mais hardcoded) |

---

### 7. MANUTENIBILIDADE (Maintainability)

> *Grau de eficácia e eficiência com que um produto pode ser modificado. Esta é a característica central deste documento.*

#### 7.1 Modularidade

```
Acoplamento entre Módulos (Grau 1-5, menor = melhor):

core/roulette.py     ──► Nenhuma dependência externa           [1] ✅ Excelente
core/engine.py       ──► state, strategies, core.roulette      [2] ✅ Bom
strategies/base.py   ──► state.timeline                        [1] ✅ Excelente
strategies/sda17.py  ──► strategies.base, state.timeline       [2] ✅ Bom
state/timeline.py    ──► app_config.settings                   [1] ✅ Excelente
state/bet_advisor.py ──► Nenhuma dependência                   [1] ✅ Excelente
state/game.py        ──► core.roulette, state.*, app_config    [3] ⚠️ Moderado
models/*             ──► pydantic (externo apenas)             [1] ✅ Excelente
database/repository  ──► database.models (ABC, interface)      [1] ✅ Excelente
database/sqlite_repo ──► database.repository + models          [2] ✅ Bom
database/service.py  ──► database.*, state.game                [3] ⚠️ Moderado
auth/middleware.py   ──► app_config.settings                   [1] ✅ Excelente
server/websocket.py  ──► Quase todos os módulos                [5] ❌ Alto acoplamento
server/msg_handler   ──► Quase todos os módulos                [5] ❌ Alto acoplamento
```

**Análise:** O `core/` e `strategies/` têm excelente separação. A camada `server/` é o ponto de maior acoplamento — `websocket.py` instancia diretamente `GameState`, `SDA17Strategy`, e `MessageHandler`. A extração do `GameEngine` (TASK-015) já mitiga parcialmente este problema.

**Avaliação: 7/10**

#### 7.2 Reusabilidade

| Componente | Reusável? | Detalhes |
|-----------|:---------:|---------|
| `RouletteCore` | ✅ Sim | Singleton sem efeitos colaterais, cálculos puros |
| `GameEngine` | ✅ Sim | Motor puro sem I/O — pode ser usado em backtest |
| `StrategyBase` | ✅ Sim | ABC com interface clara para novas estratégias |
| `SDA17Strategy` | ✅ Sim | Plug-and-play via `StrategyBase` |
| `BetAdvice / TripleRateAdvisor` | ✅ Sim | Sem dependências de I/O |
| `Timeline` | ✅ Sim | Estrutura genérica com deque |
| `DecisionRepository` | ✅ Sim | Interface abstrata — facilita migração |
| `TraceContext` | ✅ Sim | Observabilidade genérica |
| `SpinInput / SuggestionOutput` | ✅ Sim | Pydantic models independentes |
| `MessageHandler` | ❌ Não | Acoplado a WebSocket, game_state, strategy, db_service |

**Avaliação: 8/10** — Excelente reusabilidade nos componentes de domínio.

#### 7.3 Analisabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Structured logging (structlog) | ✅ | JSON em arquivo + console legível |
| TraceContext | ✅ | Cada spin tem trace com timestamps por step |
| Performance stats | ✅ | 4 listas de performance com rates calculadas |
| Decision logging (DB) | ✅ | 27 campos por decisão, auditável |
| Gale Window tracking | ✅ | Janelas com plays individuais no DB |
| Docstrings | ✅ | Todas as classes e métodos públicos documentados |
| Type hints | ✅ | Tipagem completa (typing, dataclass, Pydantic) |
| Testes | ⚠️ | 5 arquivos (396 LOC) — cobertura parcial |

**Cobertura de testes por módulo:**

| Módulo | LOC | Testes | Cobertura |
|--------|:---:|:------:|:---------:|
| `core/roulette.py` | 311 | `test_core.py` (123) | ✅ Boa |
| `strategies/sda17.py` | 213 | `test_sda17.py` (56) | ⚠️ Parcial |
| `state/bet_advisor.py` | 163 | `test_bet_advisor.py` (69) | ⚠️ Parcial |
| `state/game.py` | 493 | `test_game_state.py` (116) | ⚠️ Parcial |
| `database/sqlite_repo.py` | ~850 | `test_db_query.py` (32) | ❌ Mínima |
| `server/message_handler.py` | 473 | — | ❌ Zero |
| `server/connection_manager.py` | 272 | — | ❌ Zero |
| `core/engine.py` | 130 | — | ❌ Zero |

**Avaliação: 7/10** — Boa observabilidade em produção (logs + traces + DB). Cobertura de testes insuficiente nos módulos críticos.

#### 7.4 Modificabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Nova estratégia | ✅ Fácil | Herdar `StrategyBase`, implementar `analyze()` |
| Trocar banco de dados | ✅ Fácil | Implementar `DecisionRepository` (ABC) |
| Nova mensagem WebSocket | ✅ Fácil | Adicionar `elif` no dispatcher de `message_handler` |
| Alterar pipeline SDA | ✅ Fácil | Modificar `_predict_robust()` com passos isolados |
| Alterar Kill Switch | ✅ Fácil | Condição concentrada em uma classe (56 LOC efetiva) |
| Alterar Martingale | ✅ Fácil | `MartingaleState` isolado com `update()` |
| Alterar modelo de dados | ⚠️ Moderado | Schema DDL manual, sem Alembic migrations |
| Alterar protocolo WS | ❌ Difícil | `message_handler` com 473 LOC entrelaçando I/O e lógica |

**Avaliação: 7/10** — Design extensível (Strategy Pattern, Repository Pattern). A falta de migrations e o tamanho do `message_handler` são os pontos fracos.

#### 7.5 Testabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Lógica pura separada | ✅ | `GameEngine`, `TripleRateAdvisor`, `MartingaleState` — sem I/O |
| Backtest offline | ✅ | `tools/backtest_from_db.py` (339 LOC) |
| Fixtures / conftest | ✅ | `tests/conftest.py` configura PYTHONPATH |
| Dependency injection | ⚠️ | `GameEngine` recebe state+strategy (DI parcial) |
| Mocking necessário | ⚠️ | `message_handler` requer mock de WebSocket |
| CI/CD automatizado | ❌ | `.github/workflows/` vazio — sem execução automática |

**Avaliação: 6/10** — Componentes individuais são testáveis, mas falta CI e cobertura é baixa.

**Avaliação Geral de Manutenibilidade: 7.0/10**

---

### 8. PORTABILIDADE (Portability)

> *Grau de eficácia e eficiência com que um sistema pode ser transferido de um ambiente para outro.*

#### 8.1 Adaptabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| Configuração via ENV | ✅ | 7 variáveis (WS_HOST, PORT, SSL, AUTH, etc.) |
| Docker | ✅ | `python:3.12-slim` base image |
| Cross-platform | ✅ | Python — roda em Linux, macOS, Windows |
| SQLite portátil | ✅ | Arquivo único, sem servidor externo |

#### 8.2 Instalabilidade

| Aspecto | Status | Detalhes |
|---------|:------:|---------|
| `pip install -r requirements.txt` | ✅ | 4 dependências (pydantic, websockets, structlog, pydantic-settings) |
| `docker-compose up` | ✅ | Um comando para deploy |
| Setup script | ✅ | `scripts/setup_server.sh` para Debian |
| Volume Docker | ✅ | Dados persistem entre deploys |

#### 8.3 Substituibilidade

| Componente | Substituível? | Interface |
|-----------|:-------------:|-----------|
| SQLite → PostgreSQL | ✅ | `DecisionRepository` (ABC) |
| SQLite → SurrealDB | ✅ | Planejado no código |
| M15-ADA → Outra estratégia | ✅ | `StrategyBase` (ABC) |
| WebSocket → REST | ⚠️ | Requer refatoração do message_handler |
| structlog → outro logger | ✅ | Wrapper do stdlib `logging` |

**Avaliação: 8/10** — Boa portabilidade graças ao Docker e abstrações de repositório.

---

## PARTE III — SCORECARD CONSOLIDADO ISO/IEC 25010

| # | Característica | Sub-características Avaliadas | Nota | Nível |
|:-:|---------------|-------------------------------|:----:|:-----:|
| 1 | **Adequação Funcional** | Completude, Correção, Pertinência | **9.0** | 🟢 |
| 2 | **Eficiência de Desempenho** | Tempo, Recursos, Capacidade | **8.7** | 🟢 |
| 3 | **Compatibilidade** | Coexistência, Interoperabilidade | **7.0** | 🟡 |
| 4 | **Usabilidade** | Reconhecibilidade, Aprendizado, Proteção | **8.2** | 🟢 |
| 5 | **Confiabilidade** | Maturidade, Disponibilidade, Tolerância, Recuperação | **8.5** | 🟢 |
| 6 | **Segurança** | Confidencialidade, Integridade, Não-repúdio, Autenticidade | **6.5** | 🟡 |
| 7 | **Manutenibilidade** | Modularidade, Reusabilidade, Analisabilidade, Modificabilidade, Testabilidade | **8.0** | 🟢 |
| 8 | **Portabilidade** | Adaptabilidade, Instalabilidade, Substituibilidade | **8.2** | 🟢 |

**Nota Geral Ponderada: 8.0 / 10** *(+0.1 após M15-ADA + correções 29/03)*

```
Legenda: 🟢 ≥ 8.0 (Bom)  |  🟡 6.0-7.9 (Adequado, melhorias recomendadas)  |  🔴 < 6.0 (Crítico)
```

---

## PARTE IV — BUGS E OPORTUNIDADES PÓS-IMPLANTAÇÃO

### Bugs Identificados na Auditoria do Filesystem

| ID | Módulo | Severidade | Descrição | Linha |
|----|--------|:----------:|-----------|:-----:|
| BUG-POST-001 | `main.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | Banner agora lê `VERSION` dinamicamente | 44 |
| BUG-POST-002 | `server/websocket.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | `logging.basicConfig()` removido — usa `core/logging_config.py` | 24-31 |
| BUG-POST-003 | `server/extractor_service.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | Typo `"Carragados"` → `"Carregados"` corrigido | 27 |
| BUG-POST-004 | `server/message_handler.py` | ~~🟡 Média~~ ✅ CORRIGIDO | `str(e)` em `ErrorOutput` vazava info interna — ISO-S2: mensagem opaca + trace_id (`test_error_output_sanitize.py`) | 159-171 |
| BUG-POST-005 | `server/connection_manager.py` | ~~🟡 Média~~ ✅ CORRIGIDO | Grace period task agora é criada DENTRO do `async with master_lock` | 154 |
| BUG-POST-006 | `database/sqlite_repo.py` | ~~🔵 Baixa~~ ✅ RECLASSIFICADO | `calibration_error` deixou de ser morta: é o wheel_dist por decisão (W-02/B-08 26/05), com fill-rate monitorado (NEW-12) | — |
| BUG-POST-007 | `state/game.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | `GameState.load()` agora loga o erro e preserva `state.json.corrupted` antes do fallback | 1220-1229 |
| BUG-POST-008 | `server/connection_manager.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | Grace period não cancelado no CASO 2 — race condition podia causar duplo master (28/03 TASK-01) | 85-90 |
| BUG-MG-001 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | SmartGale v4 ignorava streaks reais — separação por direção impedia detecção de sequências cross-direction (28/03 SmartGale v5) | 52-72 |
| BUG-MG-002 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | c4_rate threshold 0.25 excessivamente agressivo — bloqueava 40% das escalações sem justificativa (ajustado para 0.15) | 61 |
| BUG-PL-001 | `server/message_handler.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | `get_gale()` NUNCA chamado em produção — SmartGale era puramente decorativo. Todas as apostas eram G1 por default (28/03 TASK-01) | 232 |
| BUG-PL-002 | `server/message_handler.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | `sync_global()` ausente — martingales nunca sincronizavam streak cross-direction em produção (28/03 TASK-01) | 163-167 |
| BUG-PL-003 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `global_hit` não passado no `update()` — global_consecutive_hits sempre 0 em produção (28/03 TASK-01) | 163 |
| BUG-PL-004 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `get_bet_c4_rate()` não chamado — filtro de segurança c4 inativo em produção (28/03 TASK-01) | 235 |
| BUG-PL-005 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Fallback early-session ausente — primeiras jogadas da sessão pulavam sem apostar (28/03 TASK-02) | 270-285 |
| BUG-PL-006 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `action_reason` genérico — não incluía score e gale_display para diagnóstico (28/03 TASK-01) | 239 |
| BUG-PL-007 | `server/message_handler.py` | ~~🔵 Baixa~~ ✅ CORRIGIDO | `gale_level` no DB era 1-decisão atrasado — get_gale() agora chamado ANTES de gravar (28/03 TASK-01) | 296 |
| BUG-E3-001 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `get_gale()` sem parâmetro `confidence` — escalação ignorava qualidade do sinal (28/03 TASK-E3) | 54 |
| BUG-E3-002 | `server/message_handler.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Pipeline não passava `confidence` para get_gale() — SmartGale cego à qualidade (28/03 TASK-E3) | 236 |
| BUG-E3-003 | `core/engine.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Engine não passava `confidence` para get_gale() — mesma omissão do pipeline (28/03 TASK-E3) | 105 |
| BUG-E2-001 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Score 3 limitado a G1 com 58.1% HR — regra de teto por score penalizava melhores momentos (28/03 TASK-E2) | 57-62 |
| BUG-E2-002 | `state/game.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Score 5-6 liberava G3 com ~40% HR — escalação destrutiva baseada em score instável (28/03 TASK-E2) | 61-62 |
| BUG-MAIN-001 | `main.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | SIGTERM não tratado no Windows — try/except no signal handler (29/03 M15-ADA) | 63-68 |
| BUG-MAIN-002 | `main.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | Double shutdown — flag `_shutdown_called` implementada (29/03 M15-ADA) | 32 |
| BUG-MAIN-004 | `main.py` | ~~🟡 Médio~~ ✅ CORRIGIDO | `game_state.save()` sem try/except no handler (29/03 M15-ADA) | 43 |
| BUG-ADA-001 | `strategies/sda17.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | `self._wheel` não inicializado em `__init__()` — crash na primeira predição CCW após restart (29/03 P0) | 46-54, 285 |
| BUG-ADA-002 | `strategies/sda17.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | Validação frágil em `load_adaptive_state()` — dados corrompidos causavam ValueError (29/03 P0) | 322-326 |
| BUG-ADA-003 | `state/game.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | `_adaptive_state` dinâmico no dataclass — hasattr() frágil, declarado como field (29/03 P1) | 147, 481 |
| BUG-ADA-004 | `server/websocket.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | Restauração adaptativa sem error handling — try/except adicionado (29/03 P1) | 32-33 |
| BUG-FE-001 | `extension/content.js` | ~~🔴 Crítico~~ ✅ CORRIGIDO | handleStateSync usava textContent sem eb-c1 — heartbeat destruía gold C1 a cada 1s (29/03 v4.0.2) | 805-812 |
| BUG-FE-002 | `extension/overlay.css` | ~~🟠 Alto~~ ✅ CORRIGIDO | .eb-region .eb-c1 com color:#000 invisível em fundo verde — alterado para #fff (29/03 v4.0.2) | 945-950 |
| BUG-FE-003 | `extension/content.js` | ~~🟡 Médio~~ ✅ CORRIGIDO | centroDisplay duplicado em 4 locais (DRY violation) — buildCentroHTML() helper (29/03 v4.0.2) | 16-23 |
| BUG-V42-001 | `strategies/sda17.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | Offset Bayesiano drift para extremos (17/7) sem guardrails — anti-drift com symmetry cap (30/03 v4.2.0) | 310-368 |
| BUG-AUDIT-002 | `server/message_handler.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | Race condition: pending_prediction lida FORA do state_lock — movida para dentro (31/03 v4.3.1) | 147-152 |
| BUG-AUDIT-004 | `database/sqlite_repo.py` | ~~🔴 Crítico~~ ✅ CORRIGIDO | json.loads() sem try-except crasheia se JSON corrompido no DB — _safe_json_loads() helper (31/03 v4.3.1) | 354-364 |
| BUG-AUDIT-005 | `strategies/base.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | get_neighbors() ZeroDivisionError se wheel_sequence vazia — guard adicionada (31/03 v4.3.1) | 51-54 |
| BUG-AUDIT-006 | `server/message_handler.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | Direction vazia/inválida atualizava Martingale CCW erroneamente — validação com elif (31/03 v4.3.1) | 162-167 |
| BUG-AUDIT-007 | `strategies/sda17.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | min_dist sem clamp em _pct_sigmoid_update — adicionado min(min_dist, 18) (31/03 v4.3.1) | 450-452 |
| BUG-AUDIT-008 | `strategies/sda17.py` | ~~🟠 Alto~~ ✅ CORRIGIDO | _predict_robust sem guard para forces=[] — early return defensivo (31/03 v4.3.1) | 230-233 |

### Melhorias Recomendadas Pós-Implantação

| ID | Característica ISO | Melhoria | Impacto |
|----|-------------------|----------|---------|
| MEL-ISO-001 | Segurança | ~~Sanitizar mensagens de erro~~ ✅ CORRIGIDO — ISO-S2 (mensagem opaca + trace_id) | ✅ Feito |
| MEL-ISO-002 | Manutenibilidade | ~~Implementar CI/CD com pytest automatizado~~ ✅ CORRIGIDO — `ci.yml` matrix 3.11-13 + PG + alembic + lints; verde 12/06 | ✅ Feito |
| MEL-ISO-003 | Manutenibilidade | ~~Adicionar Alembic migrations~~ ✅ CORRIGIDO — 0001..0008 (PG) + auto-migrations SQLite + alembic no deploy | ✅ Feito |
| MEL-ISO-004 | Confiabilidade | ~~Circuit breaker no acesso ao SQLite~~ ✅ CORRIGIDO — `_SQLiteCircuitBreaker` | ✅ Feito |
| MEL-ISO-005 | Compatibilidade | Expor REST API HTTP (além de WebSocket) para integração com ferramentas externas | 🟢 Baixo |
| MEL-ISO-006 | Usabilidade | Documentação AsyncAPI para protocolo WebSocket | 🟢 Baixo |
| MEL-ISO-007 | Eficiência | ~~Connection pooling para SQLite~~ ✅ CORRIGIDO — Conexões agora com `try/finally: conn.close()` | ✅ Feito |
| MEL-ISO-008 | Segurança | Assinatura criptográfica de `device_id` para prevenir spoofing | 🟡 Médio |
| MEL-ISO-009 | Manutenibilidade | ~~Ler versão de `VERSION` file em vez de hardcoded no banner~~ ✅ CORRIGIDO | ✅ Feito |
| MEL-ISO-010 | Confiabilidade | ~~Logging do motivo quando `GameState.load()` falha~~ ✅ CORRIGIDO — log + backup `.corrupted` | ✅ Feito |
| MEL-ISO-011 | Eficiência | ~~N+1 query em `get_gale_window_history()`~~ ✅ CORRIGIDO — Batch IN() query (28/03 TASK-02) | ✅ Feito |
| MEL-ISO-012 | Eficiência | ~~I/O síncrono no event loop async~~ ✅ CORRIGIDO — `asyncio.to_thread()` em ExtractorService + heartbeat (28/03 TASK-03) | ✅ Feito |
| MEL-ISO-013 | Manutenibilidade | ~~`_VALID_DIRECTIONS` local em `process_spin()`~~ ✅ CORRIGIDO — Movido para `ClassVar` (28/03 TASK-04) | ✅ Feito |
| MEL-MG-001 | Eficiência | ~~SmartGale v4 travado em G1~~ ✅ CORRIGIDO — Anti-Martingale com streak global cross-direction (SmartGale v5) | ✅ Feito |
| MEL-MG-002 | Eficiência | ~~Sem take-profit em G3~~ ✅ CORRIGIDO — G3+HIT reseta G1, preserva lucro (SmartGale v5) | ✅ Feito |
| MEL-MG-003 | Confiabilidade | ~~global_hit não sincronizado~~ ✅ CORRIGIDO — sync_global() sincroniza ambos martingales em engine.py | ✅ Feito |
| MEL-PL-001 | Confiabilidade | ~~Pipeline produção sem SmartGale~~ ✅ CORRIGIDO — message_handler.py agora chama get_gale(), sync_global(), get_bet_c4_rate() (28/03 plano_tarefas_sessao13) | ✅ Feito |
| MEL-PL-002 | Adequação Funcional | ~~Sem fallback early-session em produção~~ ✅ CORRIGIDO — Fallback G1 seguro com 21 vizinhos quando SDA insuficiente (28/03 TASK-02) | ✅ Feito |
| MEL-PL-003 | Testabilidade | ~~Sem testes de integração para pipeline produção~~ ✅ CORRIGIDO — 15 testes em test_message_handler_gale.py (28/03 TASK-03) | ✅ Feito |
| MEL-E3-001 | Adequação Funcional | ~~Gale cego à confiança~~ ✅ CORRIGIDO — get_gale() recebe confidence: "alta"→G1 (spike), "baixa"→G1, "media"→escalável (SmartGale v6) | ✅ Feito |
| MEL-E2-001 | Adequação Funcional | ~~Score limitava gale (não-preditivo)~~ ✅ CORRIGIDO — Regra de teto por score REMOVIDA; gale agora decidido por confiança+c4+streak (SmartGale v6) | ✅ Feito |
| MEL-E4-001 | Analisabilidade | ~~Distância ao centro não logada~~ ✅ CORRIGIDO — Log de distância resultado→centro predito em cada spin com resultado (28/03 TASK-E4) | ✅ Feito |
| MEL-ADA-001 | Adequação Funcional | ~~Migrar SDA-21→M15-ADA (17 nums, offset adaptativo CW ErrDriven + CCW Bayesian)~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-002 | Confiabilidade | ~~Inicializar self._wheel em __init__ + fallback em _bayesian_offset~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-003 | Confiabilidade | ~~Error handling na restauração adaptativa (websocket.py)~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-004 | Manutenibilidade | ~~_adaptive_state como campo dataclass em GameState~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-005 | Usabilidade | ~~Destaque bold+cor C1 no overlay e dashboard para identificação rápida~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-006 | Manutenibilidade | ~~buildCentroHTML() helper DRY — 3 locais de renderização C1 unificados~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-ADA-007 | Usabilidade | ~~Fix heartbeat sobrescrevendo C1 gold (textContent→innerHTML) + CSS contraste região~~ ✅ CORRIGIDO 29/03 | ✅ Feito |
| MEL-V42-001 | Adequação Funcional | ~~Migrar CW para Bayesiano assimétrico (unificar algoritmo CW/CCW)~~ ✅ CORRIGIDO — M04 Error-Vector com prior Gaussiano (30/03 v4.2.0) | ✅ Feito |
| MEL-V42-002 | Confiabilidade | ~~Anti-drift guardrails para offset Bayesiano~~ ✅ CORRIGIDO — Symmetry cap + limites [7,13] (30/03 v4.2.0) | ✅ Feito |
| MEL-V43-001 | Adequação Funcional | ~~Substituir Bayesian brute-force por M02-PctSigmoid~~ ✅ CORRIGIDO — Sigmoid dampened error feedback O(1) (30/03 v4.3.0) | ✅ Feito |
| MEL-V43-002 | Eficiência | ~~Warmup 5→2 jogadas para ativar Triple Focus~~ ✅ CORRIGIDO — min_forces=2, window=[7,5,3,2] (30/03 v4.3.0) | ✅ Feito |
| MEL-V43-003 | Adequação Funcional | ~~BAYESIAN_DEFAULT 12→10 (centro ótimo confirmado por oracle analysis)~~ ✅ CORRIGIDO (30/03 v4.3.0) | ✅ Feito |
| MEL-V43-004 | Confiabilidade | ~~Race condition no pending + json defensivo + guards defensivos~~ ✅ CORRIGIDO — 6 bugs audit fixes (31/03 v4.3.1) | ✅ Feito |

---

## PARTE V — MAPA DE CONFORMIDADE ISO/IEC 25010

### Matriz Característica × Evidência

| Característica ISO | Artefatos de Evidência | Gaps Identificados |
|-------------------|----------------------|-------------------|
| **Adequação Funcional** | Pipeline M15-ADA v4.3 (M02-PctSigmoid Triple Focus 17 nums, offsets adaptativos por direção), Kill Switch, SmartGale v6, DB logging, Analytics handler, Fallback early-session | Colunas mortas no schema |
| **Eficiência** | TraceContext (latência), deque com maxlen, MAX_CONNECTIONS, SQLite conn try/finally, SmartGale v6 confiança+streak+c4 | ✅ Conexões SQLite corrigidas; ✅ N+1 batch query; ✅ asyncio.to_thread(); ✅ Anti-Martingale com take-profit; ✅ Score removido de gale |
| **Compatibilidade** | Docker, ENV vars, JSON protocol | Sem REST API, sem AsyncAPI spec |
| **Usabilidade** | Pydantic models com exemplos, emojis em logs, overlay Chrome, banner dinâmico | ✅ Banner corrigido; ✅ C1 gold destaque fix v4.0.2; falta docs API (AsyncAPI) |
| **Confiabilidade** | Escrita atômica, WAL mode, grace period, healthcheck Docker, M02 backward compat, _safe_json_loads | ✅ Grace period CASO 2 corrigido; ✅ Race condition fix v4.3.1; sem circuit breaker |
| **Segurança** | HMAC comparison, SSL/TLS, MASTER-only, SECURITY.md, porta 8765 restrita a localhost | Auth bypass default, device_id sem crypto |
| **Manutenibilidade** | Strategy Pattern, Repository Pattern (ABC com 16 métodos), type hints, structlog, 105 testes (23 integração pipeline+gale), _adaptive_state como campo dataclass, buildCentroHTML() DRY helper, M02-PctSigmoid auto-adaptativo | CI vazio, cobertura testes ~60%, sem migrations; ✅ ClassVar _VALID_DIRECTIONS |
| **Portabilidade** | Docker, SQLite portátil, ENV config, setup script | WebSocket-only (sem REST fallback) |

---

## PARTE VI — CONCLUSÃO E RECOMENDAÇÕES

O **Roleta Cloud v4.3.1** apresenta uma arquitetura madura com bons padrões de design (Strategy, Repository, Singleton, Observer via broadcast). A separação entre lógica pura (`core/`, `strategies/`, `state/`) e infraestrutura (`server/`, `database/`) é clara e bem executada.

### Pontos Fortes

1. **Pipeline de decisão testável** — `GameEngine` é puro, sem I/O
2. **Extensibilidade** — novas estratégias via `StrategyBase`, novos bancos via `DecisionRepository`
3. **Observabilidade** — `TraceContext` + structlog + 27 campos por decisão no DB
4. **Resiliência** — escrita atômica, WAL mode, grace period, migração de versão automática
5. **Eficiência** — pipeline sub-50ms, O(n) com n ≤ 7
6. **Algoritmo adaptativo M02-PctSigmoid** — offset dinâmico sigmoid-dampened independente por direção (CW/CCW), 17 números, warmup de apenas 2 jogadas
7. **Usabilidade operacional** — destaque visual do C1 (bold+dourado) para identificação rápida pelo operador
8. **Robustez defensiva** — guards contra race conditions, JSON corrompido, wheel vazia, forces vazia (v4.3.1)

### Áreas Prioritárias de Melhoria (Ordenadas por Impacto)

1. **Segurança (6.5/10)** — Sanitizar erros, ativar auth em produção, assinar device_id
2. **Compatibilidade (7.0/10)** — REST API, documentação AsyncAPI
3. **Usabilidade (8.5/10)** — ~~Corrigir versão no banner~~ ✅ Feito; ~~destaque C1~~ ✅ Feito; ~~fix heartbeat/CSS C1~~ ✅ Feito v4.0.2; ~~fix encoding frontend~~ ✅ Feito v4.3.2; ~~fix DOM morto~~ ✅ Feito v4.3.2; documentar protocolo WS

### Conformidade ISO/IEC 25010

O software atende ao nível **"Bom"** (8.2/10) da norma ISO/IEC 25010, com 6 de 8 características no nível "Bom" (≥ 8.0) e nenhuma no nível "Crítico" (< 6.0). v4.3.2 elevou Usabilidade de 8.3 para 8.5 com correção de encoding frontend e eliminação de código morto. Para evoluir, as ações prioritárias são: reforço de segurança e expansão da interoperabilidade (REST API, AsyncAPI).

---

> **Documento gerado em:** 19/03/2026 | **Atualizado em:** 12/06/2026 (ADENDO no topo: ciclo 24/05→12/06, scorecard revisado 8.5/10, gaps remanescentes)  
> **Analista:** Auditoria automatizada pós-implantação  
> **Norma:** ISO/IEC 25010:2011 — Systems and Software Quality Requirements and Evaluation (SQuaRE)  
> **Software:** Roleta Cloud v4.4.0 | 119 arquivos Python ativos | 48 arquivos de teste (374 testes)  
> **Correções aplicadas:** 22 bugs em 20/03 + 12 bugs em 27/03 + 4 tasks Jules em 28/03 + SmartGale v5 em 28/03 + Pipeline fix 7 bugs em 28/03 + SmartGale v6 5 bugs em 28/03 + M15-ADA 4 bugs + C1 bold em 29/03 + BUG-FE 3 bugs em 29/03 v4.0.2 + M04 Error-Vector v4.2 em 30/03 + M02-PctSigmoid v4.3.0 em 30/03 + 6 bug fixes audit v4.3.1 em 31/03 + 10 bugs frontend v4.3.2 em 02/04 + **ciclo v4.4.0 24/05→12/06 (B-01..B-10, SP-02..35 parciais, QW-1..7, S-STRAT-1..14, auditorias 12/06 r1: 3 bugs INV-3/ledger/fallback + r2: 3 bugs feedback/center-0/stop-loss-lag)**

### Changelog de Versões

| Versão | Data | Principais Mudanças |
|--------|------|---------------------|
| v4.0.2 | 29/03/2026 | M15-ADA inicial, fix C1 gold heartbeat, CSS contraste, DRY helper |
| v4.1.0 | 29/03/2026 | Offset adaptativo CW (ErrDriven EMA) + CCW (Bayesian brute-force) |
| v4.2.0 | 30/03/2026 | M04 Error-Vector com prior Gaussiano, anti-drift guardrails, algoritmo unificado CW/CCW |
| v4.3.0 | 30/03/2026 | M02-PctSigmoid (vencedor simulação 15 modelos), warmup 5→2, DEFAULT 12→10 |
| v4.3.1 | 31/03/2026 | 6 bug fixes defensivos: race condition, json safe, wheel guard, direction validation, min_dist clamp, empty forces guard |
| v4.3.2 | 02/04/2026 | **Auditoria frontend:** fix encoding UTF-8 (22 emojis + 7 acentos), dead code cleanup (4 refs DOM null), Martingale instant trace, cache busting, CSS responsive, Dockerfile label, null guards |
| v4.4.0 | 24/05→12/06/2026 | **Ciclo PG+obs+lucro** (ver ADENDO 12/06): PG espelho outbox→CDC, Prometheus/Grafana/alertas, CI matrix verde, alembic no deploy, Quick Wins QW-1..7, S-STRAT-7..14 (batch tune, shadow grid, bandit), DNA logger, DEAL capture, PROFIT-LEDGER, CUT-POLICY v1 + stop-loss sob INV-3 global, reset total no botão de dealer (P10), medição por região (`result_region`, `dist_c1/c2/c3`, `region_err_ema`), feedback adaptativo pela aposta real, backups SQLite+wal-g ressuscitado. Suite 374 |
| v4.4.1 | 13/06/2026 | **Fix incidente MASTER:** deadlock de reeleição em `connection_manager.update_device_id` (grace expirado sem conexão → SLAVE permanente → ~16h sem spins, dashboard ONLINE porém vazio); reeleição corrigida + 5 testes (`tests/test_connection_manager_master.py`). **Observabilidade:** alerta `RoletaNoMaster` + métricas `roleta_master_present`/`roleta_ws_connections`. **Runbook** `docs/runbooks/sem-apostas-master-slave.md`. Suite 429 |
| ext v3.3.0 | 14/06/2026 | **Auto-Start & Zero-Upload (Escuta Beat, client-side)** — ver ADENDO 14/06: auto-detecção de provider (`provider_router.js`, fingerprint por host dos frames), manifests empacotados (`extension/providers/` via web_accessible_resources), auto-start via `chrome.webNavigation` + `getAllFrames`, supressão pós-STOP (TTL 24h + revalidação de host + prune), badge + toggle. Auditoria em **3 rodadas de code-review** corrigiu 5 bugs (WS duplicado/race, STOP não segurava o auto-start, badge não limpo, 2ª aba sequestrava o `tabId`, política `'ask'` beco sem saída). Backend Python v4.4.1 **intacto**. Deploy `23c3490` (servidor Debian alinhado, 6 containers healthy). Suite **480**. Detalhes: `passos_escuta_junho.md` §4.9/§12 |

---

## ADENDO 03/08/2026 — MIG-0: `state.json` no volume persistente

### A. Capacidade e correção

- Removido o bind de arquivo único `./state.json:/app/state.json` do
  `docker-compose.yml`.
- Adicionado `STATE_FILE=/app/data/state.json`, apontando para o volume
  nomeado `roleta-data`.
- Adicionado `stop_grace_period: 60s` para que SIGTERM complete o salvamento
  antes do Docker enviar SIGKILL.
- Criado `scripts/migrate-state-to-volume.sh`, idempotente, com validação JSON,
  checksum SHA-256, recusa de sobrescrita divergente e pré-condição de container
  parado.
- Os dois scripts de deploy recusam subir a aplicação se o volume não contiver
  `state.json`, evitando que um deploy automático crie um estado default.
- `GameState.load()` falha explicitamente quando `STATE_FILE` foi configurado e o
  arquivo não existe; o caminho local sem override continua podendo iniciar vazio.
- O preflight também cobre `scripts/resume_app.sh`, e o rollback do script
  duplicado recompõe a imagem antiga antes de religar o serviço.
- A resolução do volume tenta o JSON normalizado e cai para o label Docker,
  permitindo Compose anterior ao suporte de `--format json`; ambiguidades exigem
  `VOLUME_NAME`/`STATE_VOLUME_NAME` explícito.

### B. Impacto ISO/IEC 25010

| Característica | Impacto |
|---|---|
| Confiabilidade | Remove o fallback de escrita in-place causado pelo bind de arquivo único, recusa estado ausente em produção e mantém o estado no mesmo volume persistente do banco |
| Portabilidade | O caminho é declarado por ambiente e o procedimento de migração é reproduzível em Debian/VM Azure |
| Manutenibilidade | O script de migração, o teste de configuração e o rollback ficam versionados |

### C. Obrigações e rollback

1. Rodar o script somente após `docker compose stop -t 60 roleta-cloud`.
2. Manter a origem `state.json` até o soak e o primeiro restore testado.
3. Confirmar `test -f /data/state.json` no volume antes do `up`; Compose antigo
   ou múltiplos candidatos exigem nome físico explícito.
4. Em rollback, reverter o compose sem apagar a cópia de origem.

Esta mudança é de persistência/infraestrutura, não altera estratégia, stake,
geometria ou INV-3. A validação do comportamento atômico dentro do volume
Linux continua sendo obrigatória no ensaio MIG-0 antes do cutover Azure.
## ADENDO 05/08/2026 — SPR-V1: blindagem do servidor (fase e autoridade), tudo default-OFF

> Sprint executor da família SPR-V (`sprints/SPR-V1.md`), branch `ivandirfilho-didactic-broccoli`, base `main` `f165f91`. Fecha **5 blocos** de furos no caminho da fase autoritativa. **Todo comportamento novo nasce atrás de flag default-OFF**, com prova de não-interferência por **replay congelado**. Suíte **883 verde** (796 antes → +87 testes).

### A. Furos auditados (HEAD `f165f91`)

| # | Sev | Furo | Evidência |
|---|---|---|---|
| **A** | 🔴 | **Buffer de fase nunca sincronizado no gap.** O bloco DIR4 sincronizava só `recent_results`, mas desde a DIR19 o alinhamento lê `_phase_results`. Depois de QUALQUER gap o buffer ficava permanentemente defasado → todo giro seguinte virava `phase_uncertain` → a DIR17 re-ancorava na direção do **cliente**, que é justamente a fonte que a fase autoritativa existe para não obedecer. | Reproduzido no replay: 3 giros escondidos geraram **12 `phase_uncertain`** em cadeia. Teste `test_gap_sem_sync_deixa_fase_permanentemente_incerta`. |
| **B** | 🟠 | **Giro fantasma flipa a fase.** Não havia gate de plausibilidade física: um `novo_resultado` chegando ms depois do anterior avançava `spin_seq` e, como a fase é um toggle, **invertia o sentido de todos os giros seguintes**. O dedup existente compara `Date.now()` do **cliente** — adulterável e sujeito a regressão de NTP. | `is_duplicate_spin` só compara `numero+direcao+ts_cliente`. |
| **C1** | 🟠 | **`set_seed` sem `locked` destravava em silêncio** (`bool(data.get("locked", False))`): um re-seed de rotina desfazia o lock do operador sem nada visível mudar. | `handle_set_seed`. |
| **C2** | 🟠 | **Re-ancoragem de histórico invertia a âncora do operador.** `spin_seq` saltava para `count` e `seed_n` ficava velho → a paridade `(spin_seq - seed_n)` mudava → fase autoritativa invertida silenciosamente. | `handle_history_correction` / `handle_initial_history` (DIR16). |
| **C3** | 🟠 | **`set_seed`/`direction_event`/`nova_sessao` sem role-gate:** qualquer conexão (inclusive slave/aba de leitura) reancorava a fase global. | `process_message`: `data_messages` cobria só os 3 de dados. |
| **D** | 🔴 | **Fusão de vídeo sem autenticação.** Um `direction_event` forjado com `confidence` alta **sobrepunha** a projeção determinística (`fuse_direction` com `SOURCE_PRIORITY`), invertendo a fase por mensagem não autenticada — com `AUTH_ENABLED=false` em produção, qualquer cliente. | `handle_new_result`, bloco DIR7. |
| **E** | 🟡 | **Sem sinal de fase corrompida.** `_COUNTERS` é um dict FECHADO (incr de chave desconhecida é no-op silencioso) e não havia contador para buffer ausente, ambiguidade, giro implausível nem quebra de alternância. | `state/phase_metrics.py`. |

### B. Capacidades entregues (flags novas, todas default-OFF)

| Flag | Bloco | O que faz | Ligar quando |
|---|---|---|---|
| `SDA_PHASE_BUFFER_SYNC` | B1 | `GameState.sync_phase_buffer()` espelha no `_phase_results` os números recuperados no gap; limpa o buffer na correção de histórico. | **Passo 1** — maior ganho, menor risco. Junto com o B5. |
| `SDA_PHASE_MIN_OVERLAP` | B2 | Evidência mínima para aceitar um shift (`reconcile_shift`/`phase_advance_ex`); recusa também `k` ambíguo em sequências periódicas. Sugestão: `3`. | **Passo 2**, depois do B1 estabilizar. |
| `SDA_MIN_SPIN_INTERVAL_MS` | B3 | Gate de plausibilidade física no relógio **monotônico do servidor**. Sugestão: `15000`. | **4º, somente após instalar/validar a extensão 3.10.0** (ver I.4). |
| `SDA_PHASE_ALT_METRIC` | B5 | Métrica de alternância (`alternancia_violada_total`). Puramente observável. | **Passo 1**, junto com o B1. |

Sem flag (aditivos ou fail-close): role-gate MASTER, `_apply_seed` como caminho único, preservação de lock em `set_seed`, reprojeção da âncora do operador na re-ancoragem, fail-close da visão, bloco `phase_authority` no overlay, 4 contadores + 4 gauges + 3 alertas.

### C. Mudanças por arquivo

- **`state/phase.py`** — `_reconcile_shift_ex(prev, new, max_window, min_overlap) → (k, matched, ambiguous)` e `phase_advance_ex(...) → (gap, inter, uncertain, ambiguous)`. `reconcile_shift`/`phase_advance` mantêm assinatura e retorno (2 e 3-tupla) delegando ao núcleo; com `min_overlap=0` o caminho é o legado, sem desvio.
- **`state/game.py`** — `sync_phase_buffer(nums) → bool` (conversão **antes** da mutação, log de erro + `False` se `_phase_results` ausente); `_apply_seed(direction, source, locked=None, n=None)` como **único** caminho de escrita da âncora; bloco `phase_authority` em `engine_overlay_fields()`.
- **`server/message_handler.py`** — `_last_accept_srv_mono`; `_is_implausible_spin()`; `_reancora_fase(count)` (reprojeção da âncora do operador); sync do buffer no gap; `min_overlap` por chamada; métrica de alternância com expectativa `(gap+1)`; fail-close da visão; role-gate ampliado; `set_seed` preservando lock.
- **`state/phase_metrics.py`** — 4 chaves novas no dict fechado.
- **`server/health_server.py`** — 4 gauges `roleta_phase_*`/`roleta_spin_*`/`roleta_alternancia_*` + refresh.
- **`obs/alerts.yml`** — grupo `roleta_fase_v1`: `RoletaAlternanciaViolada` (critical), `RoletaPhaseUncertainBurst`, `RoletaSpinImplausivel`.
- **`docker-compose.yml`** — 4 flags novas + congelamento documentado de `SDA_DIRECTION_VISION=0`.
- **`app_config/settings.py`** — 4 helpers lidos **por chamada** (nada cacheado).

### D. Evidência de não-interferência (o coração da DoD)

`tests/replay_harness_v1.py` roda 24 giros determinísticos (3 escondidos, exercitando o gap) pelo caminho REAL `process_message`, com SQLite temporário e broadcast mockado. A fixture `tests/fixtures/spr_v1_replay_baseline.json` foi congelada rodando o harness contra o código **pristino** (`git stash` das edições do sprint). `tests/test_v1_nao_interferencia_replay.py` **re-executa e compara** — nunca regenera.

Com as 4 flags OFF: `final_action`, cobertura (`sda_numbers`/`sda_centers`), stake (`gale_bet_value`), timelines, `spin_seq`, `seed_parity`/`seed_n`, `recent_results` e `_phase_results` **idênticos campo a campo** nas 21 decisões.

### E. Fronteira de recuperação de gap (medida, não estimada)

`m = min(len(prev), len(allNumbers) - k)`. Com janela 12 do cliente e `min_overlap=3`: **gaps até `k=9` são recuperáveis**; de `k=10` em diante sobram menos de 3 números coincidentes e `phase_uncertain` é a resposta **correta** — pedir resync é melhor que inventar giros. Matriz `k=0..11` verificada em `test_dir22_alternancia_metrica.py`.

### F. Conformidade ISO (impacto)

| Subcaracterística | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Adequação funcional** (correção da fase) | ⚠️ 1 gap contaminava todos os giros seguintes | ✅ buffer realinha em 1 giro (`k≤9`) | B1 + B2 |
| **Maturidade / Tolerância a falhas** | ⚠️ giro fantasma invertia a fase sem sinal | ✅ gate físico + 4 contadores + 3 alertas | B3 + B5 |
| **Recuperabilidade** | ⚠️ re-ancoragem invertia a âncora do operador | ✅ âncora reprojetada (`project_phase(p,c,c)==p`) | B4/C2 |
| **Integridade / Controle de acesso** (Segurança) | 🔴 slave reancorava fase; `direction_event` não autenticado sobrepunha a projeção | ✅ role-gate MASTER + fail-close da visão | B4/C3 + D |
| **Analisabilidade** | ⚠️ falha de fase invisível no Grafana | ✅ 4 gauges + 3 regras de alerta | B5 |
| **Modificabilidade** | ⚠️ 4 pontos escreviam a âncora direto | ✅ `_apply_seed` como caminho único auditável | B4 |
| **Testabilidade** | ⚠️ testes de fase simulavam o branch | ✅ testes E2E pelo `process_message` real + replay congelado | B1..B5 |
| **Compatibilidade** | — | ✅ `phase_authority` aditivo (cliente antigo ignora) | pré-requisito do SPR-V2 |

**Scorecard:** Segurança 6.5 → **7.2** (dois vetores de inversão de fase fechados; `AUTH_ENABLED=false` permanece o teto). Confiabilidade 8.5 → **8.8**. Manutenibilidade 8.5 → **8.7**. Global **8.5 → 8.7**.

### G. Decisões conscientes (desvios e seus porquês)

1. **`_last_accept_srv_mono` FORA do round-trip `save()`/`load()`.** `time.monotonic()` só é comparável dentro do **mesmo processo**; persistir produziria comparação sem sentido após restart (pior: bloquear giros legítimos). Custo aceito: o primeiro giro após um restart não é checado. Coberto por `test_nao_persistido_no_round_trip`.
2. **Gate de plausibilidade em `_is_implausible_spin()` (em `process_message`), não dentro de `is_duplicate_spin`.** `_is_duplicate_trace` **grava** o `trace_id` ao checá-lo; rejeitar depois dele queimaria o id e mataria para sempre um reenvio legítimo do mesmo giro. Coberto por `test_gate_nao_queima_trace_id`.
3. **`phase_authority` publicado por `GameState.engine_overlay_fields()`,** não pelo `_engine_overlay_fields()` do handler: o `state_sync` (broadcast 1 s) só funde a fonte do `GameState`.
4. **Fail-close da visão sem flag de reabertura.** Removidos da fusão do giro **os dois** sinais `vision` (evento armazenado e `direction_source` do spin). O evento continua sendo armazenado e `fuse_direction` continua pura e testada, prontos para o SPR-V7. Rollback = `git revert` (deliberadamente não há flag que reabra o vetor).
5. **Gauge em vez de Counter** para os `_total` novos, mantendo o padrão DIR12. `increase()` continua válido; ressalva: restart do processo zera o gauge e produz um degrau que o Prometheus trata como reset.
6. **`min_overlap` lido no handler, não em `phase.py`** — as funções puras continuam puras e testáveis sem ambiente.
7. **`reset_session` não migrado para `_apply_seed`** — já era um ponto único e auditável, e migrá-lo mudaria ordem de efeitos colaterais sem ganho.

### H. Dívidas registradas

1. **`AUTH_ENABLED=false` em produção** é o que torna o fail-close da visão necessário. **Bloqueia o SPR-V7** (produtor de visão autenticado): sem autenticação não há como reabrir a fusão com segurança.
2. **`handle_history_correction` não roda sob `state_lock`** (pré-existente). Não foi corrigido aqui: risco de deadlock com `handle_set_seed`, que já toma o lock. Merece sprint próprio.
3. **`direction_event` exigindo MASTER** é um gate de concorrência, não de autenticação. Quando o serviço de visão existir, ele precisará de identidade própria — não do papel de MASTER.

### I. Obrigações / Rollback

1. **INV-3 intacto:** nada aqui toca decisão, cobertura ou stake. A estratégia continua sempre indicando `APOSTAR`; nenhum caminho novo suprime indicação. Provado campo a campo pelo replay.
2. **Round-trip preservado:** os campos da âncora (`seed_parity`/`seed_n`/`direction_source`/`direction_locked`) continuam em `save()`/`load()`/`reset_session()`; a única exceção é a do item G.1, documentada e testada.
3. **Sem migração de schema** — nenhuma mudança em banco.
4. **Ordem de ativação em produção (corrigida pelo Diretor, 05/08 — o gate temporal é o ÚLTIMO passo):**
   *Pré-requisito não numerado:* merge/deploy com as flags novas **OFF**.
   (1) `SDA_PHASE_BUFFER_SYNC=1` + `SDA_PHASE_ALT_METRIC=1` → observar `roleta_phase_uncertain_total`
   cair e `roleta_alternancia_violada_total` em 0; (2) `SDA_PHASE_MIN_OVERLAP=3` → observar
   `roleta_phase_ambiguo_total` → (3) **instalar/recarregar a extensão 3.10.0 do SPR-V2 e confirmar
   `phase_authority`** (+ telemetria DIR20 no cliente) → (4) **SOMENTE ENTÃO
   `SDA_MIN_SPIN_INTERVAL_MS=15000`**.
   **Por que o gate temporal vem por último:** ele faz o servidor *rejeitar* o giro fantasma, mas um
   cliente antigo **não desfaz o flip local** — servidor correto e popup/local phase espelhado. Reverter
   o flip rejeitado é a razão de existir do SPR-V2, então ligar o gate antes da extensão abre
   exatamente a janela de divergência que o V1 foi escrito para fechar. A versão anterior deste item
   listava o gate antes da extensão; estava invertida em relação ao risco operacional. Regra curta:
   **flags de buffer/telemetria/overlap antes; gate temporal somente depois do V2.**
5. **Rollback:** cada flag volta a `0` no host + redeploy (efeito imediato, leitura por chamada). O fail-close da visão e o role-gate revertem só por `git revert`.
6. **`promtool` indisponível na máquina do executor:** `obs/alerts.yml` foi validado por parse YAML + checagem estrutural (todo `rule` com `alert`/`expr`/`labels`/`annotations`) — 4 grupos, 21 regras. **Validar com `promtool check rules` no CI/host antes de aplicar.**

> **Veredito:** os dois vetores de **inversão silenciosa da fase** (giro fantasma e visão não autenticada) e a **contaminação permanente por gap** estão fechados, com métrica e alerta para cada um. Tudo default-OFF e com não-interferência provada por replay congelado. Próximo: SPR-V2 (cliente consome `phase_authority`).

### J. Code-review pós-implantação (subagente `code-review`) — 3 achados, 3 corrigidos antes do PR

O code-review confirmou como **limpos** o caminho legado (`min_overlap=0` byte-idêntico em 200k pares
aleatórios), a atomicidade/ordem de `sync_phase_buffer`, a equivalência de `_apply_seed` em todos os
call sites migrados, a matemática de `_reancora_fase`, o posicionamento do gate B3 antes do dedup de
trace, a expectativa `(gap+1)` da DIR22, o fail-close da visão (remove os DOIS sinais), o role-gate, a
preservação de lock em `handle_set_seed`, a consistência de nomes de métrica em toda a cadeia
(`_COUNTERS` → `_PROM_METRICS` → refresh → `alerts.yml`) e o default-OFF das 4 flags. Três achados
reais foram corrigidos:

**J.1 [ALTA] — `min_overlap` era insatisfazível com histórico curto (`state/phase.py`).**
A evidência disponível é `m = min(len(prev), len(new) - k)`, portanto **nunca** passa de
`min(len(prev), len(new))`. Exigir `min_overlap=3` quando só existem 1-2 números tornava a condição
IMPOSSÍVEL: um alinhamento perfeito e ÚNICO era reportado `matched=False, ambiguous=True` →
`phase_uncertain` → **DIR17 re-ancorava a fase na direção do CLIENTE**, que é exatamente o vetor de
ataque/erro que a capacidade B2 existe para fechar. O gatilho não era exótico: `reset_session()` zera
`_phase_results`, então **os giros #2 e #3 depois de TODO `nova_sessao`** caíam nele, além de qualquer
janela curta do cliente. A trava de segurança destruía a âncora do operador.

*Correção:* teto `min_overlap = min(min_overlap, len(prev), len(new))` — a exigência de evidência
nunca ultrapassa a evidência que **pode** existir. É a generalização da isenção que a função já dava
a `prev` vazio ("não há histórico contra o que comparar"). O parâmetro continua valendo integralmente
quando a evidência existia e não bastou.

*Não-regressão:* (a) `min_overlap=0` não passa pelo teto — caminho legado intocado, replay congelado
segue byte-idêntico; (b) a fronteira **k=9** é preservada, pois com `prev`=16 e janela 12 o teto é
inerte (`min(3,16,12) = 3`) — a matriz `k=0..11` continua verde; (c) 6 testes novos, todos validados
por **mutação**: substituir o teto por `pass` mata os 6.

**J.2 [MÉDIA] — a branch de `phase_ambiguo_total` tinha cobertura ilusória.**
`test_metrica_ambigua_incrementa_no_handler` usava uma janela sem NENHUM alinhamento posicional
(`ambiguous=False`) e afirmava apenas `phase_uncertain_total >= 1`, que o caminho pré-existente já
satisfazia — apagar a branch nova deixaria a suíte verde. Reescrito para um caso que **alinha**
(k=9 com m=1 de 3 possíveis) e afirma `phase_ambiguo_total == 1`.

**J.3 [BAIXA] — `handle_initial_history` não limpava `_last_accept_srv_mono`.**
`handle_history_correction` e `handle_new_session` já o faziam; o histórico inicial é a mesma
descontinuidade e ficara com tratamento assimétrico — um giro aceito ANTES do histórico podia barrar,
por até `SDA_MIN_SPIN_INTERVAL_MS`, o primeiro giro ao vivo depois dele. Corrigido.

**Validação pós-correção.** Suíte completa **890 passed, 9 skipped, 1 xfailed** (+7 testes de
regressão sobre os 883 do corpo deste ADENDO; baseline do sprint era 796/9/1).
`tools/lint_silent_except.py` OK (129 `except Exception` em 12 arquivos, nenhum novo). Replay
congelado verde: a correção **não** alterou o comportamento com as flags OFF.

**Lição para o `Manutenabilidade_iso.md` (Confiabilidade).** Um parâmetro de segurança que pede mais
evidência do que o sistema pode produzir não endurece nada — ele **inverte** a defesa, empurrando o
sistema para o caminho degradado justamente na janela mais frágil (logo após um reset). Todo limiar de
evidência deve ser explicitamente limitado pela evidência disponível, e todo teste de métrica deve ser
validado por mutação: se apagar a branch mantém a suíte verde, a cobertura é ilusória.

### K. Contrato `phase_authority` — validação integrada com o SPR-V2 (produtor x consumidor)

O SPR-V2 foi mergeado na `main` (PR #52, merge `1bc45b7`) **antes** deste PR, e a extensão passou a
consumir o bloco `phase_authority` que este sprint publica. Os dois lados vivem em linguagens e
repositórios de teste distintos (Python e JS) e, até aqui, **nenhum teste os amarrava**: os testes do
V1 conferiam o schema do produtor isoladamente e os do V2 usavam fixtures escritas à mão. Um contrato
verificado só por convenção humana dos dois lados é um contrato não verificado.

**Rebase.** Branch rebaseada sobre `origin/main` já contendo o V2 — **sem conflitos**. O único arquivo
tocado pelos dois sprints é este `Manutenabilidade_iso.md`, e os adendos são apêndices em pontos
distintos. Diff final não remove nem regride nada do V2 (`extension/`, `tests/js/`,
`.github/workflows/ci.yml`, `sprints/SPR-V2.md` e `tests/test_dir13_lock_total.py` idênticos à `main`).

**Veredito: compatível, sem correção de escopo necessária.** O consumidor
(`extension/background.js::handleStateSyncPhase`) lê exatamente três campos — `enabled`, `direction` e
`spin_seq` — e todos casam com o produtor (`GameState.engine_overlay_fields`). `seed_parity`/`seed_n`
são publicados e hoje ignorados: campos extras são inertes para o V2.

**Riscos reais que a auditoria encontrou e que agora estão travados por teste**
(`tests/test_v1_v2_phase_authority_contract.py`, 14 testes):

| Risco | Por que é silencioso | Guarda |
|---|---|---|
| Perder o `update(engine_overlay_fields())` em `server/websocket.py` | `pa` chega `undefined`, `paEnabled` vira `false` e a reconciliação do V2 apenas **para** — sem erro em lugar nenhum | heartbeat real executado; asserção sobre `state_sync.data` |
| `enabled` deixar de ser booleano estrito | o V2 compara `pa.enabled === true`; um `1` inteiro desarma tudo | asserção sobre o JSON serializado (`"enabled": true`) |
| Vocabulário de `direction` mudar | `normalizePhaseDir` devolve `null` e o desfazer-flip vira no-op | matriz paridade x `spin_seq` -> `cw`/`ccw` |
| `phase_authority.direction` divergir de `sentido.next_direction` | o V2 usa as **duas** fontes no mesmo payload: desfaz o flip para uma direção e reconcilia para a outra, **oscilando a cada heartbeat** | 6 giros E2E comparando os dois blocos do mesmo overlay |
| `spin_seq` virar `null` quando não há âncora | `Number(null) === 0`: o contador congela em 0, `paSeq === paSeqBeforeSend` sempre, e o V2 marca **todo** giro como rejeitado | asserção explícita no estado sem âncora |
| a chave `spin_seq` **sumir** do bloco | sintoma DIFERENTE do `null`: `Number(undefined)` é `NaN`, o passo de ACK é pulado inteiro e `paAwaitingAck` fica preso em `true` — a reconciliação contínua **congela** | `test_campos_consumidos_pelo_v2_existem_sempre` (com e sem âncora) |

**A divergência que NÃO existe (e por que é frágil).** `sentido.next_direction` é `target_direction`,
o *toggle* sobre `last_direction`; `phase_authority.direction` é a *projeção determinística* da âncora.
São dois códigos independentes que coincidem por um motivo específico: com `SDA_SENTIDO_AUTORITATIVO=1`
o servidor grava em `last_direction` a projeção do giro `n`, e `opposite(proj(n)) == proj(n+1)`
reencontra a projeção em `spin_seq`. Essa igualdade é um **acidente feliz do estado atual**, não uma
invariante estrutural — qualquer mudança futura em `target_direction` a quebraria em silêncio. Por isso
virou asserção E2E.

**Semântica de `enabled` = `SDA_SENTIDO_AUTORITATIVO AND SDA_PHASE_BUFFER_SYNC`** — as quatro
combinações estão cobertas, inclusive as parciais. Duas consequências operacionais, e a primeira
**corrige uma imprecisão da redação anterior deste parágrafo**:

- **Quem acende a capability, na prática, é o passo 1 do runbook.** `SDA_SENTIDO_AUTORITATIVO` já é
  **default-ON** na compose (`SDA_SENTIDO_AUTORITATIVO:-1`), então ligar `SDA_PHASE_BUFFER_SYNC=1`
  basta para `enabled` virar `true` em produção. A redação anterior — "ligar só `SDA_PHASE_BUFFER_SYNC`
  não acende o V2" — só valeria num host com a autoridade desligada, que não é o estado de produção.
  Isso importa porque é o que garante que a capability já esteja publicada quando a extensão for
  instalada no passo 3: o operador consegue **confirmar** o `phase_authority` no `state_sync`, em vez
  de instalar às cegas.
- **O rollback continua sendo de um comando.** Desligar **qualquer uma** das duas desarma o consumidor
  sozinho, sem tocar na extensão instalada — é o que o runbook assume como saída de emergência,
  inclusive depois do passo 3.

**Validação por mutação** (a cobertura foi provada, não presumida): remover o merge do overlay no
`websocket.py` mata 1 teste; trocar `enabled` por `int(...)` mata 6; inverter a projeção de `direction`
mata 6. Fontes restauradas e `git diff` limpo após cada mutação.

**Suítes.** Python **904 passed, 9 skipped, 1 xfailed** (+14 sobre os 890 do §J).
JS do V2 **53 passed** (`node --test "tests/js/*.test.js"`). `lint_silent_except` OK.

**Lição (Manutenabilidade / Confiabilidade).** Contrato entre componentes que não compartilham suíte é
contrato não verificado — cada lado testa a própria fixture e os dois passam enquanto o sistema
integrado está quebrado. Todo bloco publicado para um consumidor externo precisa de um teste que
execute o **canal real** de ponta a ponta e afirme **tipo, vocabulário e coerência com os blocos
vizinhos do mesmo payload**, não apenas a presença da chave.

---

## ADENDO 05/08/2026 (noite-2) — OBS-INODE: regras Prometheus presas no inode antigo (deploy × bind de arquivo)

> Incidente operacional observado em produção no mesmo dia do SPR-V1: `/root/roleta-cloud/obs/alerts.yml`
> tinha **21** regras e o container `roleta-prometheus` continuava servindo **18** — `promtool` *dentro*
> do container e a API `/api/v1/rules` concordavam com o número **errado**, ou seja, o container estava
> internamente coerente com um arquivo que já não existia mais no host. `POST /-/reload` **não** resolveu;
> recriar só o Prometheus resolveu (promtool passou a ver 21 e as 3 regras do V1 carregaram).

### A. Causa-raiz (duas condições necessárias, nenhuma suficiente sozinha)

1. **O deploy troca o inode.** `roleta-deploy-pull.sh` faz `git reset --hard origin/main`; o git
   materializa cada arquivo modificado com temp+rename, então `obs/alerts.yml` **muda de inode** a cada
   deploy que o toca.
2. **A compose montava arquivos, não o diretório.** `docker-compose.obs.yml` usava
   `./obs/alerts.yml:/etc/prometheus/alerts.yml:ro`. Um bind de **arquivo** é resolvido uma única vez, na
   criação do container, e fica preso àquele inode — o novo arquivo, com o mesmo caminho, não é visto.
   `/-/reload` relê o **mesmo inode antigo**, por isso "recarregou com sucesso" e nada mudou.

Um terceiro fator explica a **duração**: nenhum passo do deploy tocava a stack de observabilidade, então
a divergência era imune ao número de deploys — sobreviveria indefinidamente, e em silêncio, porque tanto
o container quanto o host estavam "certos" cada um com a sua versão.

### B. Correção (duas camadas — a estrutural e a operacional)

| Camada | Mudança | Por que é necessária |
|---|---|---|
| Estrutural | `docker-compose.obs.yml` monta o **diretório** `./obs:/etc/prometheus:ro` | O git não recria o diretório `obs/`; só substitui arquivos **dentro** dele. Um bind de diretório resolve o caminho a cada acesso, então acompanha a troca de inode. Caminhos internos idênticos ⇒ `--config.file` e `rule_files` intactos. |
| Operacional | `scripts/obs-apply.sh`, chamado pelo deploy | Só o mount não basta: sem alguém mandar recarregar, o Prometheus segue com as regras **em memória** até o próximo restart. |

`obs-apply.sh` = **detectar → validar → aplicar → verificar**:

- **Detectar** — `git diff --name-only OLD NEW -- obs/prometheus.yml obs/alerts.yml obs/*.rules.yml docker-compose.obs.yml`.
  Deploy sem mudança de observabilidade é *noop* explícito: **o Prometheus não é reiniciado**.
- **Validar antes de aplicar** — `promtool check config` em container efêmero
  (`run --rm --no-deps --entrypoint /bin/promtool`), rodando **logo após o `git reset`** e **antes** do
  build/alembic: com mount de diretório os arquivos novos já estão visíveis ao container, então uma
  config inválida só se manifestaria no próximo restart. O resultado é **tri-estado**, não booleano:
  `FAILED:` do promtool = config inválida comprovada ⇒ `git reset --hard $LOCAL` e abort;
  qualquer outra falha (daemon fora, imagem ausente, ENOSPC) = **indisponibilidade operacional**,
  que é logada e adiada para o `apply` — porque a reprovação deste passo derruba o deploy do **app**
  com um `git reset --hard`, e "o docker não respondeu" não é prova de config quebrada.
- **Aplicar** — mudou só config/regras ⇒ `POST /-/reload`; mudou a `docker-compose.obs.yml` (o próprio
  mount) ⇒ `up -d --no-deps prometheus`. Usar `up -d` **puro** (e não `--force-recreate`) é deliberado:
  ele recria quando a definição do serviço mudou e vira **no-op** nas retentativas — recriação **única**,
  sem loop de restart a cada tick de 2 min. Volume `prometheus-data` (TSDB) preservado; **sem**
  `--remove-orphans`; `--no-deps` garante que Grafana/AlertManager/app não são tocados.
- **Verificar (o coração do fix)** — quatro provas, todas obrigatórias:
  1. `/-/ready`, com **orçamento próprio** (`READY_TIMEOUT`, default 120s): um Prometheus reiniciado
     pode passar minutos em WAL replay, e confundir "ainda subindo" com "não aplicou" faria o script
     recriar o container no meio do replay, repetidamente;
  2. `prometheus_config_last_reload_successful` = 1 **e** o timestamp
     (`prometheus_config_last_reload_success_timestamp_seconds`) **avançou** em relação ao instante
     anterior à execução — **o booleano sozinho é *sticky***: continua 1 do carregamento anterior
     mesmo que nada tenha sido recarregado agora, e foi exatamente assim que a primeira versão
     deste script conseguiu declarar sucesso sem recarregar nada;
  3. **SHA-256 do arquivo no repo == SHA-256 do que o container lê**, lido por `docker exec`
     (`sha256sum`, com fallback `cat`) — **nunca** por `docker cp`, que faz o daemon re-resolver o
     caminho no host e devolveria os bytes novos que o processo talvez nunca tenha visto. O `<cid>` vem
     de `ps -q` — **sem `-a`**, porque `-a` traria os containers efêmeros que o próprio `promtool` cria,
     e verificar contra um deles (que carrega o bind novo) devolveria "sucesso" com o Prometheus real
     ainda nas regras velhas;
  4. **número de regras carregadas na API == declarado nos `rule_files`** (resolvidos com glob/subpath,
     fail-closed quando um padrão não casa) — `arquivo=21 carregadas=18` é o sintoma literal do
     incidente, e nenhuma das outras três provas o pega quando o arquivo já está montado corretamente
     mas o processo não releu.

  **Depois de qualquer `up`/recriação vem sempre um `POST /-/reload`.** Um `up -d` puro é no-op
  quando a definição do serviço não mudou (a compose mudou num comentário ou em outro serviço),
  e sem o reload a regra nova simplesmente nunca carregaria.

### C. As armadilhas de "sucesso falso" fechadas explicitamente

Cada linha desta tabela é um caminho pelo qual o script **declararia sucesso sem ter aplicado nada** —
a maioria descoberta em duas rodadas de revisão independente, e todas travadas por teste (§D):

| Armadilha | O que aconteceria | Guarda |
|---|---|---|
| Reload responde 200 e nada muda | exatamente o incidente | comparação de bytes container × repo; divergência ⇒ **escala para uma recriação única**, e a marca `escalated` só é gravada **depois** que a recriação deu certo (senão uma falha transitória do `up` trancaria a pendência num estado que só faz reload — e reload, por definição, não conserta inode preso) |
| `up -d` que virou no-op | a compose mudou num comentário/outro serviço ⇒ o serviço não é recriado, e **sem reload nada é relido**; `ready` + booleano sticky + bytes iguais fariam tudo parecer certo | **todo `up`/recriação é seguido de `POST /-/reload`**, sempre |
| Booleano de reload *sticky* | `prometheus_config_last_reload_successful` continua 1 do carregamento anterior | exigir que o **timestamp do último reload avance** em relação ao instante anterior à execução |
| Regras não carregadas | arquivo com N regras, API com N-3 (o incidente) — bytes já batendo | contagem carregada × declarada nos `rule_files` como **critério**, não diagnóstico |
| Falha esquecida no tick seguinte | `LOCAL == REMOTE` ⇒ `exit 0` e o systemd volta a `success` sem nada aplicado | pendência em `$STATE_DIR/obs_pending`, retomada com `obs_run resume` **antes** do gate NOOP |
| Pendência rebaixando ação nova | um `escalated` de reload antigo sobrescrevia um `recreate` novo ⇒ **troca real de mount pulada** | pendência combinada por **severidade** (`recreate` > `reload`) e escalada zerada quando o SHA muda |
| POST recusado engolido | `do_reload \|\| true` transformava 405/403/conexão recusada em sucesso e ainda **limpava** a pendência | nenhum caminho ignora o POST; **nenhuma falha limpa a pendência** |
| Kill-switch amnésico | `OBS_ENABLED=0` apagava a pendência ⇒ religar não retomava nada | pausa preserva a pendência |
| Ação detectada descartada no gate | com o kill-switch ligado **ou** o Prometheus fora do ar, o script saía **antes** de gravar a pendência: no tick seguinte `LOCAL == REMOTE`, não havia o que retomar, e os diffs dos deploys seguintes já não continham aquela mudança ⇒ **perda silenciosa da regra nova**, o próprio incidente | a ação resolvida é persistida **antes** do gate (exceto em host que nunca teve a stack, onde não há o que preservar) |
| Marcador antigo `escalated` | era gravado só depois de uma recriação (ou seja, ação = `recreate`), mas era lido como `reload` — e, sem SHA, o reset de episódio era pulado: a recriação ficava bloqueada por episódios inteiros, falhando a cada 2 min sem nunca poder consertar o inode | marcador legado mapeado para `recreate`; pendência **sem** SHA conta como episódio novo |
| promtool inexecutável tratado como config inválida | imagem ausente/daemon fora/ENOSPC derrubariam um deploy de app válido com `git reset --hard` | validação **tri-estado**: só `FAILED:` comprovado aborta |
| Readiness curta demais | 12s não cobre WAL replay ⇒ o script recriaria o Prometheus no meio do replay, a cada tick | readiness com orçamento próprio de 120s, separada da verificação |
| Detecção que falha em silêncio | `git diff` com erro virava "nada mudou" — justamente no deploy que precisava do reload | erro logado + **ação conservadora** (`recreate`) |
| Prometheus que sumiu vira "skip" | host sem stack e host com stack derrubada são indistinguíveis | marcador `$STATE_DIR/obs_seen`: se a stack já existiu neste host e agora não existe, é **falha**, não skip. O passo `check` é a exceção deliberada: como a falha dele derruba o deploy do **app**, stack indisponível ali só adia a decisão para o `apply` |
| Verificar contra o container errado | `ps -a` lista os containers efêmeros do `compose run` (o nome deles ordena antes do `roleta-prometheus`) e eles carregam o bind **novo** ⇒ os bytes batem e o script declara sucesso com o Prometheus real ainda velho | seleção por `ps -q` (só em execução) + aviso se vier mais de um ID |
| Ler os bytes com `docker cp` | **descoberto reproduzindo o incidente em Docker real**: `docker cp` **não** lê pelo mount namespace do processo — para um bind mount o daemon **re-resolve o caminho de origem no host**. Num bind de *arquivo* com inode trocado ele devolve os bytes **novos** enquanto o processo continua lendo os **antigos**: a comparação vira host×host, uma **tautologia** que passa exatamente no cenário do incidente | leitura por `docker exec` (`sha256sum`, com fallback `cat`), que executa no namespace do container; sem leitor disponível ⇒ **fail-closed** (nunca cair num leitor que mente) |
| Escalar qualquer falha para recriação | POST recusado, `reload_successful=0` ou "nunca ficou ready" não são consertados por recriar — e recriar um Prometheus que ainda servia a **última config boa** pode transformar um problema de recarga em **crash loop** e reiniciar o WAL replay | a verificação classifica a falha: **processo/transporte** (1) ⇒ falha e preserva a pendência, **sem** recriar; **conteúdo** (2, ready + reload fresco e bem-sucedido, leitura válida, mas bytes/regras divergentes — a assinatura do inode preso) ⇒ aí sim escala uma única vez |
| `rule_files` por basename, sem glob | `/etc/prometheus/*.rules.yml` ou um subdiretório davam **0 regras declaradas**; como `0 != carregadas`, todo deploy virava falha (e recriação) eterna | resolução relativa ao mount, expansão de glob e subpaths, e o byte-check derivado da **mesma** lista; zero correspondência (glob vazio **ou** literal ausente) é **fail-closed** — guardrail deliberadamente mais estrito que o Prometheus, que ignora glob vazio em silêncio |
| Erro de leitura tratado como divergência | `/api/v1/rules` fora do ar, `docker exec` falhando ou imagem sem leitor caíam na classe "conteúdo" e **forçavam recriação** — recriar não conserta um transporte quebrado, e ainda reinicia o WAL replay à toa | `same_bytes`/`rules_ok` devolvem **1 = transporte** e **2 = divergência real**; só a classe 2 escala |
| `rule_files` sobrepostos contados duas vezes | `alerts.yml` + `*alerts.yml` resolvem o mesmo arquivo ⇒ `declared` dobrado ⇒ `declared != loaded` **para sempre**: falha e recriação eternas numa config legal | alvos **deduplicados** antes da contagem e do byte-check (a mesma lista alimenta os dois) |
| `grep -q` no fim de uma pipeline sob `pipefail` | o `/metrics` tem centenas de KB e a métrica aparece cedo: o `grep -q` sai no primeiro match, o produtor morre de **SIGPIPE (141)** e a pipeline inteira vira "falha" — a verificação **nunca** passaria, todo deploy de obs escalaria para recriação e a pendência ficaria presa em `escalated` para sempre | comparação por here-string (`grep -q … <<< "$body"`), sem pipeline |

Falha de observabilidade **não** faz rollback do app: ele já passou no healthcheck no SHA novo, e derrubar
o backend por causa de regra de alerta seria desproporcional. O deploy loga `OBS FAIL` + `DEPLOY PARCIAL`
e sai `!= 0` — a unit do systemd fica `failed`, que é o sinal honesto.

### D. Regressão (`tests/test_obs_reload.py`, 84 testes)

Estáticos: a compose **precisa** montar o diretório e **não pode** ter bind de arquivo para
`prometheus.yml`/`alerts.yml` (se alguém reverter, o bug volta silencioso e nenhum outro teste percebe);
`rule_files` tem de apontar para dentro do mount; volume TSDB nomeado presente; nenhum `--remove-orphans`;
`resume` antes do gate NOOP; e o **entrypoint** tem de continuar sendo um ponteiro (sem lógica de deploy).

Funcionais: o script roda de verdade contra stubs **com estado** de `docker`/`curl` (injetados por
`DOCKER_BIN`/`CURL_BIN`, sem mexer no `PATH`) num repositório git temporário — os stubs mantêm o
timestamp do último reload, o que o container "enxerga" e quantas regras a API "carregou", de modo que
um reload que não acontece de fato **não** faz o timestamp avançar e um container defasado devolve
menos regras. Cobrem: deploy sem obs (zero chamadas ao docker), reload sem recriação, recriação única
com `--no-deps` **seguida de reload**, frescor (reload sticky), regras não carregadas (2 no arquivo × 1
na API), promtool reprovado × promtool inexecutável, `check` com a stack fora do ar, host sem stack,
stack que sumiu, kill-switch preservando **e gravando** pendência, pendência escalada que não pode
rebaixar um `recreate` novo, pendência no formato antigo (com e sem SHA), POST recusado que não vira
sucesso, recriação que falha sem trancar a pendência, startup lento (WAL replay) sem recriar, readiness
estourada, `git diff` quebrado, `/metrics` grande (SIGPIPE), `ps` sem `-a` e o **incidente literal**
(container servindo o arquivo velho ⇒ detecta, escala **uma** recriação, grava a pendência, não recria
de novo no tick seguinte e só devolve `0` depois que os bytes batem). O entrypoint tem testes próprios:
**drift** do launcher (trocar o script versionado muda o comportamento sem reinstalar nada) e do
instalador (idempotência, backup, `--check` read-only, `--rollback`).

**Matriz de mutação** (a cobertura foi provada, não presumida — cada bug reintroduzido no script e o
teste correspondente tem de reprovar; fontes restauradas ao fim):

| Bug reintroduzido | Teste que reprova |
|---|---|
| `recreate` sem reload depois do `up` | `test_recreate_sempre_recarrega` |
| verificação sem frescor (booleano sticky) | `test_frescor_reload_que_nao_avanca_timestamp_reprova` |
| contagem de regras só como diagnóstico | `test_regras_nao_carregadas_nao_e_sucesso` |
| pendência rebaixando a ação nova | `test_pendencia_escalada_nao_engole_recreate_novo` |
| `do_reload \|\| true` (POST engolido) | `test_escalated_com_reload_falho_nao_vira_sucesso` |
| kill-switch apagando a pendência | `test_kill_switch_preserva_pendencia` |
| promtool inexecutável = config inválida | `test_promtool_inexecutavel_nao_derruba_o_deploy_do_app` |
| readiness sem orçamento próprio | `test_startup_lento_nao_forca_recriacao` |
| `git diff` quebrado virando noop | `test_git_diff_quebrado_nao_vira_noop` |
| entrypoint congelado (sem launcher) | `TestLauncherRuntime` |
| pendência não gravada antes do gate | `test_kill_switch_grava_a_mudanca_detectada` + `test_stack_fora_do_ar_grava_a_pendencia` |
| marcador antigo rebaixado para `reload` | `test_resume_de_pendencia_antiga_recria_quando_preciso` |
| SHA vazio pulando o reset de episódio | `test_pendencia_antiga_sem_sha_nao_bloqueia_a_recriacao` |
| instalador do entrypoint não idempotente | `test_instala_com_backup_e_e_idempotente` |
| instalador sem backup (rollback impossível) | `test_rollback_restaura_o_entrypoint_anterior` |
| sonda de drift fatal (derrubaria o deploy) | `test_deploy_avisa_quando_o_entrypoint_esta_congelado` |
| sonda de drift desligada (drift silencioso) | `test_deploy_avisa_quando_o_entrypoint_esta_congelado` |
| ler os bytes com `docker cp` (tautologia) | `test_bytes_lidos_pela_visao_do_container` |
| leitor ausente presumindo sucesso | `test_sem_leitor_no_container_falha_fechado` |
| escalar qualquer falha para recriação | `test_post_recusado_nao_recria` + `test_reload_rejeitado_nao_recria` + `test_never_ready_nao_recria` |
| `rule_files` por basename, sem glob | `test_glob_e_subdiretorio_sao_resolvidos` |
| zero match tratado como zero regras | `test_glob_sem_correspondencia_falha_fechado` |
| gate sem stack descartando a mudança | `test_host_sem_marcador_ainda_guarda_a_mudanca` |
| `--check` sem distinguir launcher antigo de cópia | `test_check_distingue_launcher_desatualizado_de_copia_congelada` |
| launcher sem marcador estável | `test_check_distingue_launcher_desatualizado_de_copia_congelada` |
| `--check` ruidoso a cada tick | `test_check_e_silencioso_quando_esta_em_dia` |
| unit sem sonda / com sonda fatal | `test_unit_systemd_roda_a_sonda_de_forma_nao_fatal` |
| sonda sem `REPO_DIR` explícito | `test_deploy_passa_repo_dir_para_a_sonda` |
| erro de leitura classificado como conteúdo | `test_sem_reader_na_imagem_e_processo` + `test_docker_exec_falho_e_processo` |
| API fora do ar classificada como conteúdo | `test_api_de_regras_fora_do_ar_e_processo` |
| `verify` colapsando as duas classes | `test_sem_reader_na_imagem_e_processo` |
| sem deduplicação dos `rule_files` | `test_literal_e_glob_sobrepostos_contam_uma_vez` + `test_dois_globs_sobrepostos_contam_uma_vez` |

**Probes independentes** (`OBS_APPLY=<script>`, stubs próprios, fora do harness de teste): 15 cenários —
namespace × host no bind de arquivo, mount de diretório, POST recusado / `reload_successful=0` /
never-ready sem recriação, glob no topo, em subdiretório e sem correspondência, gate sem stack, API fora
do ar, `docker exec` falho, imagem sem leitor, controle de hash divergente, sobreposição literal+glob e
paths com espaço. Contra o `scripts/obs-apply.sh` de `554e66b`: **1/9** (o probe do namespace devolvia
`rc=0` usando `docker cp` — o sucesso falso — e `forced=1` nos três casos de falha de processo). Contra
`edcb9fd`: **11/15** (as quatro reprovações são exatamente os achados de classificação e deduplicação).
Contra o código atual: **15/15**.

### E. Entrypoint durável (o que fazia o conserto não chegar em produção)

O systemd executa `/usr/local/bin/roleta-deploy-pull.sh`, que era uma **cópia congelada** do deploy —
hoje byte-idêntica ao `scripts/roleta-deploy-pull.sh` (mesmo hash, ambas já com o passo `alembic`), ou
seja: **não** havia migração `tools/` → `scripts/` pendente, como uma versão anterior desta documentação
sugeria; o problema era só o congelamento. Qualquer melhoria versionada dependia de alguém lembrar de
reinstalar a cópia — e nada tornava esse congelamento visível.

Três peças fecham isso:

| Peça | Papel |
|---|---|
| `scripts/roleta-deploy-launcher.sh` | ~10 linhas, zero lógica de deploy: resolve `$REPO_DIR/scripts/roleta-deploy-pull.sh` e faz `exec`. Instalado **uma vez** no mesmo caminho (a unit systemd não muda), a partir daí todo o deploy — inclusive o passo de observabilidade — viaja pelo git. Carrega um **marcador estável** (`ROLETA-DEPLOY-LAUNCHER`) |
| `scripts/roleta-deploy-install.sh` | bootstrap/atualização **operacionalizada**: idempotente (não reescreve se já for o launcher), guarda o entrypoint anterior em `/usr/local/lib/roleta-deploy/`, `--check` read-only e `--rollback` para desfazer |
| sonda de drift | roda no fim de cada deploy **e** em `ExecStartPre=-…` da unit (o `-` a torna não-fatal). **Limite honesto e documentado:** a sonda vive no script versionado, então **não detecta o congelamento atual** — a cópia congelada nunca a executa. Ela protege contra **re-congelamento futuro**; o caso de hoje só o bootstrap manual resolve |

`--check` é **tri-estado**, porque hash diferente não prova que o deploy versionado parou de chegar:
`ok` (idêntico, silencioso para não poluir o journal a cada 2 min) · `DESATUALIZADO` (hash diferente
**com** o marcador — ainda é um launcher, as mudanças continuam chegando) · `DRIFT` (sem o marcador =
cópia congelada, exit 1 com o comando de correção). O deploy passa `REPO_DIR` explicitamente à sonda,
para funcionar em checkouts fora do path default.

O duplicado `tools/deploy_pull.sh` virou delegador do canônico, eliminando a classe "duas cópias que
precisam ser mantidas em sincronia".

**Fora de escopo, registrado:** `obs/alertmanager.yml` continua sendo bind de **arquivo** — mesma classe
de bug, não alterado aqui para não recriar um container fora do incidente.

**Suítes.** Python **988 passed, 9 skipped, 1 xfailed** (+84 sobre os 904 do adendo anterior).
`lint_silent_except` OK · `schema_symmetry` OK.

**Evidência contra a rodada anterior.** A suíte funcional aceita `OBS_APPLY_UNDER_TEST=<script>` para
rodar contra outra versão do aplicador. Apontada para o `scripts/obs-apply.sh` do commit `0db70f6`
(rodada 1), **19 dos 31 testes de runtime reprovam** — incluindo os três de sucesso falso do incidente
(`recreate_sempre_recarrega`, `frescor_reload_que_nao_avanca_timestamp_reprova`,
`regras_nao_carregadas_nao_e_sucesso`). Os testes de entrypoint reprovam por construção: nem o launcher
nem o instalador existiam naquele commit.

**Lição (Manutenabilidade / Operação).** Um componente pode estar **internamente coerente e
externamente errado**: o Prometheus concordava consigo mesmo sobre 18 regras enquanto o disco tinha 21, e
todo diagnóstico feito *de dentro dele* (promtool no container, `/api/v1/rules`) confirmava a versão
errada. Sempre que um artefato versionado é entregue por cópia/mount, a verificação tem de comparar
**as duas pontas** — bytes do repo contra bytes que o consumidor realmente lê — e nunca aceitar o "200 OK"
do comando de recarga como prova de que a mudança chegou. Dois corolários que este ciclo custou três
rodadas de revisão para aprender:

1. **Sinal que sobrevive ao próprio evento não prova nada.** Um booleano "último reload deu certo"
   continua verdadeiro para sempre depois do primeiro sucesso; só o *frescor* (um relógio que precisa ter
   avançado) distingue "recarregou agora" de "recarregou algum dia".
2. **Verificar exige saber de qual ponto de vista se está lendo.** `docker cp` e `docker exec` parecem
   equivalentes para "ler um arquivo do container", mas só o segundo passa pelo mount namespace do
   processo: o primeiro faz o *daemon* re-resolver o caminho no host e, num bind de arquivo com inode
   trocado, devolve alegremente os bytes novos que o processo nunca viu. Uma verificação que lê pelo lado
   errado não é fraca — é **tautológica**, e passa com mais confiança justamente no caso que deveria pegar.

---

## ADENDO 05/08/2026 (noite-2) — SPR-V4: contrato `direction_event` + trilha `phase_events` (auditoria durável, shadow-only)

> Sprint executor da familia SPR-V (`sprints/SPR-V4.md`), branch `ivandirfilho-turbo-waffle`, base `main` `0e7543e` (ja com SPR-V1 e SPR-V2). Transforma o `direction_event` de "ultima coisa que chegou" em **evento identificavel, vinculado a um giro-alvo, com prazo e consumo unico**, e cria a **prova duravel** sem a qual nenhum gate de shadow pode ser honestamente avaliado. **Tudo default-OFF**, com nao-interferencia provada pelo replay congelado do SPR-V1. Suite **973 verde** (965 antes -> +64 testes novos do sprint; 3 baselines atualizados).

### A. O bug latente que este sprint fecha

`handle_direction_event` gravava `last_direction_event` **sem TTL, sem consumo unico e sem vinculo a giro**. Como a mesa **alterna a cada giro**, um veredito CORRETO do giro N e a direcao **ERRADA** do giro N+1: um produtor que emitisse uma vez e falhasse na seguinte **travaria a direcao autoritativa em ~50% de erro ate um reset**. Hoje o vetor e inerte (nao ha produtor) e o SPR-V1 tirou a visao da fusao (fail-close). Este sprint reconstroi o contrato **do lado seguro**: o evento vira **trilha de auditoria, nunca direcao**.

Segundo furo, de natureza diferente: **Prometheus nao satisfaz o gate T4**. Counters zeram a cada restart do container e log tem retencao limitada — sem `phase_events`, "99% de acordo" e uma afirmacao sem lastro. A trilha e **requisito de evidencia**, nao luxo analitico.

### B. Capacidades entregues (flags novas, todas default-OFF)

| Flag | O que faz | Ligar quando |
|---|---|---|
| `SDA_PHASE_EVENT_AUDIT` | Persiste a trilha `phase_events`. Sem ela **nada e gravado** (o contrato continua valendo em memoria). | **Passo 1** — so grava, custo medido abaixo. |
| `SDA_DIRECTION_VISION_SHADOW` | Classifica cada giro (`agree`/`disagree`/`stale`/`unbound`/`selfcontradict`/`missing`) contra a direcao final **pos-autoridade**. Zero efeito em direcao, seed, timeline, decisao ou stake. | **Passo 2**, depois do AUDIT. Ligar SHADOW sem AUDIT produz metrica sem prova. |
| `SDA_DIRECTION_VISION_TTL_MS` | Prazo (default `30000`) contado do **recebimento**, no relogio monotonico do servidor. | Ajuste fino; 30s < ciclo real (~44s). |

`SDA_DIRECTION_VISION` **permanece congelada em `0`** ("nao ligar; visao corrige ancora, nao spin — ver SPR-V7"). Este sprint **nao** reabre autoridade per-spin.

### C. As quatro condicoes de binding (e por que cada uma existe)

Um evento so vincula quando **os quatro** requisitos valem: (a) `round_id` coincide **se os dois lados o tiverem**; (b) `target_spin_seq` bate com a formula do servidor; (c) idade **dentro** do TTL; (d) evento **ainda nao consumido**. Faltou um -> `stale`/`unbound`, e **nunca** vira direcao.

1. **`target_spin_seq = spin_seq_corrente + 1`, atribuido pelo SERVIDOR sob `state_lock`.** O evento descreve o giro que **ainda vai ser processado** (o `spin_seq` so incrementa quando o `novo_resultado` e aceito). A formula esta no codigo, no teste e aqui de proposito: deixa-la a criterio do implementador gera off-by-one silencioso, que e exatamente a classe de bug que o sprint existe para tornar visivel. Um `target_spin_seq` enviado pelo cliente e **so diagnostico** (`meta_json.client_target_spin_seq`) — senao um cliente defeituoso escolhe o alvo dele.
2. **TTL no relogio do servidor.** Idade = `time.monotonic() - received_at_mono`, com o monotonico lido **antes de disputar o lock** (captura-lo depois renovaria de graca o prazo de um evento que ficou na fila). `captured_at_ms` do cliente e **so diagnostico**: se entrasse na conta, um relogio adulterado renovaria o proprio prazo. Intervalo **semiaberto** (`idade >= TTL` ja expira).
3. **Restart invalida por construcao.** `time.monotonic()` nao sobrevive ao processo, entao ele **nao e persistido**: o evento volta com `mono_lost=True` e e `stale` **por definicao**. Essa e a unica excecao ao round-trip, e e o que impede um evento zumbi de voltar acionavel com prazo zerado.
4. **One-shot estrutural.** A disposicao terminal **remove** o pendente; nao ha caminho que o reaproveite no giro seguinte (que ja e o sentido oposto).

**Gap de fase (`spin_seq += _gap`) => `unbound`, e isso esta certo:** o evento descrevia o giro imediatamente seguinte, e um gap significa que aquele giro **nunca foi visto**. Classificar como `agree` seria concordancia inventada.

### D. Atomicidade: decisao + disposicao na MESMA transacao

`save_decision()` abre e comita a propria conexao, entao a unica forma de amarrar os dois writes era uma operacao explicita: `SQLiteDecisionRepository.save_decision_with_phase_events()`. **Nao ha alternativa "justificada"** — sem atomicidade existe decisao sem disposicao, e a trilha deixa de ser prova para o gate T4.

* **Rollback total testado com falha injetada** entre os dois writes (monkeypatch do ponto de costura `_insert_phase_event_row` **e** violacao real de `NOT NULL`): nem decisao nem disposicao ficam gravadas. O retry reprocessa de forma idempotente.
* **`ON CONFLICT ... DO NOTHING`, e nao `INSERT OR IGNORE`.** O `OR IGNORE` engoliria tambem violacao de `NOT NULL`/`CHECK`: uma linha invalida sairia em silencio da transacao, a decisao comitaria sem disposicao e o teste de rollback passaria **por engano**.
* **O hook do outbox so roda apos o commit** — um rollback jamais publica no PG uma decisao que nao existe.

**Politica de degradacao declarada: decisao obrigatoria, auditoria best-effort.** Quando a transacao falha, a decisao do giro nao pode ser sacrificada pela trilha (a aposta ja foi emitida; o ledger e o que vira dinheiro). Por isso o erro e **tipado**:

| Excecao | Significado | Acao do handler |
|---|---|---|
| `PhaseTrailRolledBack` | Falhou **antes** do commit; **nada** foi gravado. | Unico caso que autoriza re-tentar a decisao **sozinha**. |
| `PhaseTrailCommitAmbiguous` | O proprio `commit()` levantou; nao se pode afirmar se gravou. | **Sem retry** (duplicaria a decisao no ledger). |
| Qualquer outra | So pode vir **depois** do commit (hook do outbox, `close()`). | **Sem retry**, pelo mesmo motivo. |

Em todos os casos: `phase_events_write_error_total++`, log de erro, e a **janela deixa de valer como evidencia T4** — o giro e a aposta seguem intactos.

### E. Desvio deliberado do DDL literal do brief

O brief pedia `UNIQUE(event_id, kind)`. **Entregue: indice unico `ux_phase_events_lifecycle(session_id, event_id, kind, target_spin_seq)`.**

`event_id` e o valor **do cliente** quando presente, e nada o prende a um giro nem a uma sessao. Com a chave global, um produtor que reutilize um id estavel (id de camera/sensor) grava **UMA linha por kind para a vida inteira** enquanto os counters continuam subindo. Reproduzido: **6 giros com `event_id` constante => counters 6, trilha 1**. As consequencias sao exatamente o que o sprint existe para impedir: (1) a decisao comita com **zero** linhas de disposicao — a "decisao sem disposicao" alcancada por outro caminho, sem rollback; (2) `missing` some do denominador e a taxa de acordo **sobe artificialmente** — a metrica de 200 amostras disfarcada de prova.

`session_id` entra na chave porque **`spin_seq` REINICIA a cada sessao**: sem ele, `(cam-fixa, received, 1)` da sessao B colide com a mesma tupla da sessao A e a linha da sessao **nova** e suprimida — a sessao inteira perde a evidencia sempre que o produtor tiver um id estavel. Coberto por `test_terminal_de_uma_sessao_nao_fecha_nem_suprime_a_outra` (mutacao cirurgica removendo `session_id` da chave mata o teste com a mensagem exata "a linha da sessao nova foi suprimida pela chave unica").

A chave e um **INDICE UNICO EXPLICITO**, e nao um `UNIQUE` de tabela, por uma razao operacional: indice e **aditivo** (`CREATE UNIQUE INDEX IF NOT EXISTS`), entao um banco criado por um commit intermediario deste PR ganha a chave certa no boot seguinte — sem `DROP`/rebuild, que os invioaveis do repo proibem. E ele e obrigatorio: `ON CONFLICT(...)` exige um indice unico que **case exatamente** com as colunas; sem ele **todo** insert da trilha estoura com `OperationalError` e a auditoria morre inteira. Coberto por `test_banco_legado_ganha_a_chave_do_ciclo_sem_drop`.

Complemento: **toda supressao por conflito e contada** (`phase_events_write_error_total`) e logada com a tupla completa. Evidencia que nao foi gravada precisa aparecer numa metrica — sub-registro silencioso e pior que erro barulhento.

### E.1. Duas coordenadas, ambas em COLUNAS (nao em `meta_json`)

Uma linha da trilha responde a duas perguntas diferentes, e confundi-las quebrava tanto o fechamento do ciclo quanto a contagem por sessao:

| Colunas | Significado |
|---|---|
| `session_id` + `target_spin_seq` | coordenadas do **EVENTO** — o *slot* do ciclo de vida. E por elas que um terminal fecha o seu `received` (idem a chave unica). |
| `spin_session_id` + `spin_seq` | coordenadas do **GIRO** que decidiu a disposicao. **NULL** em tudo que nao e disposicao de giro (`received`, supersede, invalidacao por `nova_sessao`, faxina). |

Invariante consultavel: **`spin_seq IS NOT NULL` <=> a linha participa da particao dos GIROS ELEGIVEIS** (o denominador da cobertura). `count_phase_events_by_kind(sessao)` filtra por `COALESCE(spin_session_id, session_id)`: uma disposicao pertence a sessao do GIRO que a decidiu; `received`/manutencao, que nao tem giro, pertencem a sessao do EVENTO.

Sem isso, um evento com alvo 5 classificado no giro 7 (gap de fase recuperado) gravava o terminal com alvo 7 — que **nao fecha** o `received` de alvo 5, deixando o ciclo aberto para sempre.

### F. Append-only x retencao (o que este sprint NAO entrega)

1. **Taxa de crescimento MEDIDA** (2.000 giros reais gravados, `wal_checkpoint(TRUNCATE)`, tabela + indice + overhead de pagina):
   * **sem produtor de visao** (1 linha `missing`/giro): **223 B/giro** -> ~218 KB/dia, **6,4 MB/30d**, ~78 MB/ano (a 1.000 giros/dia);
   * **com produtor ativo** (`received`+`bound`+`agree`, `meta_json` cheio): **1.313 B/giro** -> ~1,3 MB/dia, **37,6 MB/30d**, ~457 MB/ano.
   Ambos acima da estimativa de ~100-300 B/giro do brief, que contava **uma** linha e ignorava indice/pagina.
2. **"Append-only" e "retencao" nao se contradizem** porque o **hot path so INSERE**; quem apaga e um job **externo**, fora do caminho do giro.
3. **Enquanto o job nao existir, a purga e MANUAL e do operador.** O job de 30 dias e **sprint futuro (`SPR-V4R`, a abrir pelo Diretor)** e precisa existir **antes** de a auditoria ficar ligada por mais de ~60 dias. Nao ha promessa no PR que nao esteja no diff.
4. **Frames NUNCA entram no banco** — so metadados (testado: nenhuma coluna `frame`/`image`/`blob`).

### G. Por que SQLite e nao pgvector

O evento e **categorico, temporal e auditavel**: a pergunta e "houve evento neste giro e ele concordou?", nao "qual evento e semanticamente parecido". Busca vetorial nao agrega nada a isso e **dificultaria integridade** (sem `UNIQUE` natural, sem transacao com a decisao). pgvector segue para embeddings. Se um dashboard central for necessario **depois**, a outbox espelha no PG com migracao Alembic aditiva — **sem hardcode do numero da migracao** (a head atual e 0013 e pode mudar) e so depois de liberar o lock `schema/alembic`. **Sem Alembic neste sprint**, por decisao do brief (evita colisao com o SPR-G2).

### H. Cobertura ANTES de concordancia

`vision_event_total` conta **ingressos**; os seis `kind` terminais **particionam os giros elegiveis** (exatamente UMA disposicao por giro com o shadow ON). `roleta_vision_coverage_ratio = (agree+disagree)/elegiveis`, com **0.0** quando nao ha giro elegivel — nunca 1.0, que faria "sem dado" parecer "cobertura perfeita".

Correcao vinda do code-review: as invalidacoes de **ingresso** (evento superseded por outro frame, e pendente morto por `nova_sessao`) **nao incrementam** `vision_unbound_total`. Elas nao sao giros; conta-las inflava o denominador — medido: 5 frames antes de 1 giro que concordou davam cobertura **0,2** em vez de **1,0**. As linhas continuam na trilha (com `meta_json.reason = superseded|session_reset`), so nao poluem a metrica que o runbook manda ler antes de confiar em qualquer taxa de acordo.

### I. Mudancas por arquivo

- **`server/message_handler.py`** — `classify_direction_event()` **pura** (recebe relogio e TTL ja resolvidos); `handle_direction_event` reescrito (identidade, snapshot atomico sob lock, formula do alvo, retry sem renovar TTL, contradicao **sticky**, supersede terminalizado, `save()` do pendente, I/O e ack **fora** do lock); `_classify_pending_direction_event()` sob o lock logo apos `spin_seq += 1`; `_save_decision_with_trail()` com a politica de degradacao tipada; `_write_phase_events()`; `_reconstruir_pendente_da_trilha()`.
- **`database/sqlite_repo.py`** — DDL aditivo de `phase_events` + indice; `save_decision_with_phase_events()`; `insert_phase_events()` (retorna linhas **efetivamente** gravadas); `get_pending_phase_event()`; `count_phase_events_by_kind()`; `PhaseTrailRolledBack`/`PhaseTrailCommitAmbiguous`; `save_decision` refatorado para **fonte unica** de SQL/params (43 colunas em dois caminhos duplicados divergiriam no primeiro campo novo).
- **`state/game.py`** — `pending_direction_event` com round-trip `save`/`load`/`reset_session` e `_pending_event_for_save()` (remove o monotonico); `last_direction_event` promovido a campo declarado.
- **`state/phase_metrics.py`** — 8 chaves novas no dict fechado. **`server/health_server.py`** — 8 gauges + `vision_coverage_ratio`. **`obs/alerts.yml`** — grupo `roleta_visao_v4`. **`docker-compose.yml`** — 3 flags default-OFF + congelamento re-documentado de `SDA_DIRECTION_VISION`. **`app_config/settings.py`** — 3 helpers lidos **por chamada**.
- **`tests/replay_harness_v1.py`** — passa a capturar tambem o call site atomico (sem isso, um replay com auditoria ON devolveria **zero** decisoes e a comparacao passaria vazia, provando nada).

### J. Conformidade ISO (impacto)

| Subcaracteristica | Antes | Depois | Justificativa |
|---|:--:|:--:|---|
| **Adequacao funcional** (correcao) | ⚠️ evento sem alvo/prazo podia descrever o giro errado | ✅ 4 condicoes de binding + formula fixa do servidor | Bloco 1 |
| **Analisabilidade** | 🔴 sem prova duravel: counters zeram no restart, log expira | ✅ trilha append-only + 9 gauges + 2 alertas | Blocos 2-3 |
| **Maturidade / Tolerancia a falhas** | ⚠️ falha de persistencia da evidencia era invisivel | ✅ erro tipado, contado, alertado; giro e aposta intactos | D |
| **Integridade (Seguranca)** | ⚠️ cliente influenciava alvo/prazo do proprio evento | ✅ alvo e TTL sao **do servidor**; valor do cliente e diagnostico | C.1-C.2 |
| **Recuperabilidade** | — | ✅ pendente reconstruido da trilha; `stale` por definicao pos-restart | C.3 + I |
| **Modificabilidade** | ⚠️ SQL da decisao seria duplicado em 2 caminhos | ✅ fonte unica `_DECISION_INSERT_SQL`/`_decision_params` | I |
| **Testabilidade** | — | ✅ `classify_direction_event` pura; falha injetada com rollback provado | D |
| **Compatibilidade** | — | ✅ tabela aditiva; `sentido.stats` aditivo (cliente antigo ignora) | I |

**Scorecard:** Analisabilidade 8.7 -> **9.0** (a evidencia do gate T4 passa a existir). Confiabilidade 8.8 -> **8.9**. Seguranca permanece **7.2** (`AUTH_ENABLED=false` segue sendo o teto — este sprint nao reabre a fusao). Global **8.7 -> 8.8**.

### K. Decisoes conscientes (desvios e seus porques)

1. **`UNIQUE(session_id, event_id, kind, target_spin_seq)`** em vez do literal do brief — secao E, com reproducao.
2. **Coordenadas do EVENTO e do GIRO em colunas separadas** (`session_id`/`target_spin_seq` x `spin_session_id`/`spin_seq`) — secao E.1. Colocar as do giro em `meta_json` deixaria "quais giros foram elegiveis" fora do alcance de uma query.
3. **A trilha FECHA ciclos; ela nao RESSUSCITA eventos** — secao N.7. A continuidade de um restart e provada pelo `state.json`, nunca por coincidencia de contador.
4. **`received_at_mono` fora do round-trip** — e o que torna verdadeira a regra "evento pos-restart e `stale`". Persisti-lo daria prazo de graca ao evento zumbi.
5. **Ingestao sempre-on, persistencia e classificacao atras de flag.** Atribuir identidade/alvo/prazo e bookkeeping inerte (espelha o que o `last_direction_event` ja fazia); o que custa disco (AUDIT) e o que produz metrica (SHADOW) sao opt-in. Isso mantem o caminho legado byte-identico com as flags OFF.
6. **Fallback que grava a decisao sozinha** — degradacao **declarada**, nao atomicidade fingida (secao D). Restrito a `PhaseTrailRolledBack`, o unico caso em que se **sabe** que nada foi gravado.
7. **Duas linhas (`bound` + `agree`/`disagree`) para um evento vinculado.** `bound` e transicao, nao disposicao; o fechamento do ciclo so considera os seis `kind` terminais.
8. **`selfcontradict` definido como "mesmo `event_id` reapresentado com direcao diferente"** — a unica contradicao verificavel **do produtor** que nao depende de campo controlado pelo cliente. Fazer o `target_spin_seq` divergente do cliente virar `selfcontradict` deixaria o cliente influenciar a classificacao pela porta dos fundos.
9. **I/O de SQLite e `send()` do ack fora do `state_lock`** — `busy_timeout=5000` e `drain()` de produtor lento parariam o caminho do giro (o lock e o ponto de serializacao de `handle_new_result`).
10. **Gauge em vez de Counter**, mantendo o padrao DIR12/SPR-V1 (`increase()` continua valido; restart do processo produz degrau tratado como reset).

### L. Dividas registradas

1. **`SPR-V4R` (retencao de 30 dias) precisa existir antes de ~60 dias de auditoria ligada** — hoje a purga e manual (secao F). O mesmo job e o lugar natural para varrer ciclos abertos alem dos 20 que a faxina de boot cobre.
2. **`event_id` de cliente ainda e um espaco de nomes compartilhado dentro de uma sessao.** A chave `(session_id, event_id, kind, target_spin_seq)` fecha os vetores praticos (reuso entre giros e entre sessoes), mas dois produtores com o mesmo id no MESMO giro da MESMA sessao ainda colidiriam — e a supressao seria **contada**, nao silenciosa. Identidade propria do produtor depende do SPR-V7/`AUTH_ENABLED`.
3. **`direction_event` exigindo MASTER continua sendo gate de concorrencia, nao de autenticacao** (divida herdada do SPR-V1).
4. **`missing` usa id deterministico `missing:{session_id}:{spin_seq}`** conforme o brief; se `spin_seq` regredir dentro da mesma sessao (re-ancoragem de historico), a segunda linha colide — e a colisao **conta** `phase_events_write_error_total` em vez de sumir.
5. **A faxina de boot cobre no maximo 20 ciclos abertos** (varredura limitada aos 200 `received` mais recentes, para nao virar trabalho ilimitado no caminho do giro). Orfaos alem disso ficam para o proximo boot ou para o `SPR-V4R`.

### M. Obrigacoes / Rollback

1. **INV-3 intacto:** nada aqui toca indicacao, cobertura ou stake. O caminho de shadow escreve **apenas em variaveis locais** e e provado incapaz de agir por teste que **falha** se ele chamar `_apply_seed`/`process_spin` ou alterar `direcao`/`seed_parity`/`spin_seq`.
2. **Nao-interferencia provada por replay congelado:** `tests/test_v4_nao_interferencia_replay.py` re-executa `tests/replay_harness_v1.py` contra a fixture congelada **antes do SPR-V1** e compara campo a campo — decisoes, cobertura, stake, timelines, seed e `spin_seq` **identicos** com as 3 flags novas OFF, e **identicos tambem** com `SDA_DIRECTION_VISION=1` (regressao do fail-close) e com o shadow ON.
3. **Round-trip:** `pending_direction_event` em `save()`+`load()`+`reset_session()`, com a excecao documentada e testada do item K.2.
4. **Sem Alembic / aditivo:** `CREATE TABLE/INDEX IF NOT EXISTS`, nenhum `DROP`/rename. Rodar o DDL 2x e testado.
5. **Rollback:** `SDA_PHASE_EVENT_AUDIT=0` + `SDA_DIRECTION_VISION_SHADOW=0` + `docker compose up -d` (minutos), ou `git revert` do PR. **A tabela PERMANECE** (aditiva, inofensiva) — o rollback de deploy nao faz downgrade de schema.
6. **`promtool` indisponivel na maquina do executor:** `obs/alerts.yml` validado por parse YAML + checagem estrutural (todo `rule` com `alert`/`expr`/`labels`/`annotations`/`summary`) — **5 grupos, 23 regras**. **Validar com `promtool check rules` no CI/host antes de aplicar.**

### N. Code-review pos-implantacao (subagente `code-review`) — 6 achados, 6 corrigidos antes do PR

Confirmados **limpos**: a formula do alvo vs. comparacao pos-incremento (sem off-by-one, inclusive no caminho de gap); a transacao cobrindo de fato os dois writes com rollback garantido e sem vazamento de conexao; o hook do outbox so apos o commit; a exclusao **completa** do monotonico nos tres pontos do round-trip; a equivalencia byte-a-byte da refatoracao de `save_decision` (43/43 colunas e params, mesma ordem); a cadeia de nomes de metrica `_COUNTERS` -> `_PROM_METRICS` -> refresh -> `alerts.yml`; e o INV-3.

Corrigidos: **(N.1)** a chave unica global descartando linhas legitimas (secao E) + supressao agora **contada**; **(N.2)** denominador da cobertura poluido por invalidacoes de ingresso (secao H); **(N.3)** o fallback re-tentava a decisao em excecoes que **nao** garantem rollback (podia **duplicar** a decisao no ledger) — restrito a `PhaseTrailRolledBack`; **(N.4)** `await websocket.send()` **dentro** do `state_lock` no ramo de retry (produtor lento parava o caminho do giro); **(N.5)** capacidade de reconstrucao do pendente existia sem **nenhum** call site de producao (cobertura ilusoria) — agora e a rede de seguranca do `state.json` perdido, e `handle_direction_event` passou a chamar `game_state.save()` (sem ele o round-trip era teatro: o `save()` do giro roda **depois** do consumo e gravaria sempre `None`); **(N.6)** testes de idempotencia que passariam tanto com o dedup correto quanto com ele destruindo linhas legitimas — a mutacao `UNIQUE(event_id, kind)` -> `(..., target_spin_seq)` deixava a suite inteira verde. Novos guarda-corpos: `test_mesmo_event_id_em_giros_DIFERENTES_nao_e_descartado`, `test_trilha_e_counters_contam_a_mesma_historia` (trilha e counters tem de contar a MESMA historia) e `test_supressao_de_linha_conta_erro_de_escrita`.

> **Veredito:** o `direction_event` deixou de poder descrever o giro errado (alvo, prazo e consumo unico sao **do servidor**), e passou a existir **prova duravel** — atomica com a decisao — sem a qual o gate T4 seria uma afirmacao sem lastro. Tudo default-OFF, sem tocar um unico byte da aposta. Pendencia explicita: `SPR-V4R` (retencao) antes de ~60 dias com a auditoria ligada.

### N.7. Segunda rodada de review (PR #55) — 2 bugs de INTEGRIDADE DA TRILHA, corrigidos

Um review independente do PR encontrou dois defeitos que nao afetam aposta, decisao nem INV-3 (a trilha e shadow-only), mas **falsificam a evidencia** — que e a unica razao de a trilha existir.

**N.7.1 [MEDIO] — a recuperacao pos-restart nunca podia funcionar.**
`_reconstruir_pendente_da_trilha(self.current_session_id)` consultava a trilha filtrando pela sessao corrente. So que `current_session_id` nasce `uuid.uuid4()[:8]` **no `__init__` do handler**: depois de um restart ele e um id NOVO, enquanto a linha `received` orfa carrega o id ANTERIOR. O lookup nunca achava nada — a capacidade documentada era inalcancavel. O teste que a "cobria" apenas zerava o pendente **em memoria mantendo a mesma sessao**, ou seja, jamais atravessava a fronteira de processo que o cenario exige.

*Correcao — as duas verdades foram SEPARADAS, em vez de a segunda ser adivinhada:*

| Cenario | Como e provada a continuidade | Disposicao do GIRO | Destino do ciclo do evento |
|---|---|---|---|
| Restart com `state.json` (bind-mount, o caso REAL) | o `pending_direction_event` volta do disco com o seu `session_id` e `mono_lost` | **`stale`** (nunca vincula, nunca vira direcao) | fechado pelo proprio terminal do giro |
| `state.json` perdido/corrompido | **nao ha como provar** | **`missing`** (honesto: este giro nao teve evento) | fechado por **FAXINA** de manutencao |

A tentacao era adotar o orfao pelo `target_spin_seq`. **Nao da:** `spin_seq` REINICIA a cada sessao, entao o alvo `1` de uma mesa morta ha dias coincide com o giro 1 de qualquer sessao nova. Adotar por coincidencia de contador rotularia como `stale` um giro que foi honestamente `missing` — exatamente o tipo de mentira que a trilha existe para impedir, e ainda por cima com atribuicao cruzada entre mesas.

A **faxina** (`_faxina_orfaos_da_trilha`) roda UMA vez por processo, em **transacao propria** (manutencao nunca pode arrastar a decisao do giro num rollback), grava `kind='stale'` com `decision_ref` NULL, `spin_seq` NULL e `meta.reason="orfao_sem_continuidade"`, e **nao incrementa contador** — nao e um giro, entao nao entra no denominador da cobertura.

**N.7.2 [MEDIO] — o `NOT EXISTS` fechava o ciclo por `event_id` global.**
A identidade do DDL e por giro, mas a consulta de pendencia correlacionava so por `event_id`. Com um produtor reutilizando um id estavel, o terminal do giro N **mascarava** o `received` do giro N+1 (ou de outra sessao): o ciclo aberto aparecia como encerrado, e a trilha perdia a capacidade de responder "o que ficou em aberto?".

*Correcao:* a correlacao passou a ser `(session_id, event_id, target_spin_seq)` — **exatamente** a chave unica. Isso exigiu o par que faltava: o **terminal precisa carregar as coordenadas do EVENTO** (secao E.1), senao um evento com alvo 5 classificado no giro 7 gravava o terminal com alvo 7 e deixava o `received` de alvo 5 aberto para sempre.

*Achado adicional, encontrado ao corrigir os dois:* a marca `received_persisted` era gravada **depois** do `gs.save()`, logo **nunca ia para o `state.json`**. Apos um restart, o evento restaurado nao sabia que o `received` ja existia, re-emitia a linha, e o conflito suprimido era contado como um erro de escrita que **nunca houve** — poluindo justamente a metrica de saude da trilha. Agora a marca nasce **antes** do `save()` (otimista) e e desfeita se a gravacao falhar de fato, o que de quebra da auto-cura: a linha e re-emitida no giro.

*Evidencia de mutacao (nao ha cobertura ilusoria aqui):* com o codigo de producao revertido para `c970b65` e os testes novos mantidos, **10 testes falham**. Cada fix foi ainda mutado isoladamente e **todos os mutantes morreram**: correlacao de volta a `event_id` global (mata 2), chave sem `session_id` — mutacao cirurgica, com o `ON CONFLICT` ajustado junto (mata 2, com a mensagem "a linha da sessao nova foi suprimida pela chave unica"), terminal de volta as coordenadas do giro (mata 2), faxina removida (mata 3), marca de persistencia de volta ao lugar antigo (mata 3).

### N.8. Terceira rodada — code-review dos PROPRIOS fixes (3 achados, 3 corrigidos)

Revisar a correcao encontrou tres defeitos nela, dois deles piores que os originais:

**N.8.1 [MEDIO] — a faxina reintroduzia o BUG-2 por outro caminho.** A guarda que evita fechar o pendente VIVO comparava so o `event_id`. Com o produtor de id estavel — exatamente o perfil que justifica a chave — **todo** orfao de sessao morta carrega o mesmo id do pendente vivo e era pulado; como a faxina roda uma vez por processo e o evento vivo costuma chegar antes do primeiro giro, o orfao **nunca** seria fechado. Reproduzido pelo review. *Correcao:* a guarda compara a identidade COMPLETA `(session_id, event_id, target_spin_seq)` — a mesma do indice.

**N.8.2 [MEDIO] — um banco com a forma antiga faria TODO insert da trilha estourar.** O aviso que eu havia escrito dizia "pode suprimir linhas legitimas"; o comportamento real era pior: sem um indice unico que case com o alvo do `ON CONFLICT`, **toda** insercao levanta `OperationalError`, e cada giro passa a percorrer transacao -> rollback -> `PhaseTrailRolledBack` -> `save_decision()` sozinho, com o contador de erro subindo indefinidamente. *Correcao:* a chave virou **indice unico aditivo**, que um banco antigo ganha no proximo boot (secao E), com teste que parte de uma tabela na forma antiga e prova o insert funcionando depois da migracao. O aviso continua, agora em `logger.error` e descrevendo o sintoma certo.

**N.8.3 [BAIXO] — a auto-cura da marca `received_persisted` era cobertura ilusoria.** Nenhum teste injetava falha **no ingresso** (todos mexiam no caminho da classificacao), entao apagar o bloco inteiro deixaria a suite verde enquanto a trilha passaria a gravar disposicao terminal sem o `received` correspondente. *Correcao:* teste que faz `insert_phase_events` falhar no ingresso e prova que a classificacao re-emite a linha.

*Mutacao da rodada 3 — os tres mutantes morreram:* guarda da faxina so por `event_id` (mata 1), indice do ciclo removido (mata 41 — o `ON CONFLICT` fica sem alvo), auto-cura removida (mata 1). Suite completa: **984 verde**.

---

## ADENDO 05/08/2026 (madrugada) — SPR-V3-A: preflight do vídeo/iframe, sem autoridade e sem veredito

> Sexta rodada do ciclo (`sprints/SPR-V3.md`), base `main` `0e7543e` (já com SPR-V1 e SPR-V2/ext 3.10.0).
> Este ADENDO registra um sprint **que termina sem conclusão de propósito**: ele entrega o instrumento e
> **para** em `WAITING_HUMAN_EVIDENCE`. O produto é a **honestidade do estimador**, não um veredito.

### A. O que estava em jogo

Hoje o sentido de giro é **inferido** por alternância, nunca observado. A única fonte capaz de observar
sem clique humano é a sequência de frames do `<video>` da mesa. Antes do SPR-V5 (sensor, esforço L, com
manutenção perpétua sobre o layout de um terceiro) era preciso responder, barato, se **existe caminho
técnico** — e o desenho original já havia sido derrubado pela auditoria em cinco pontos (§10.2.1):
quota de `captureVisibleTab`, aliasing da bolinha, correlação 2D medindo translação, pente de 37 bolsos
e "confidence por consistência entre pares", que é desonesta porque aliasing é erro **sistemático** —
os pares erram juntos e concordam entre si.

### B. Fronteira declarada: V3-A entregue, V3-B intocado

| | V3-A (este PR) | V3-B (falta) |
|---|---|---|
| Probes E0/E0b | **rodáveis e testadas contra `<video>` local** | **executá-las em mesa real** |
| Calibração + replay offline | entregues | captura de campo |
| Protocolo de campo | escrito, executável por não-autor | 40-60 giros anotados + soak 2 h |
| Gates de GO | tabela pronta, **campos vazios** | preencher os 4 números |
| GO/NO-GO | **não declarado** | decisão do operador (§10.6-1) |

Nenhuma linha deste PR pode fechar a coluna da direita. Executar as probes exige mesa ao vivo,
sessão autenticada e operador; isso é escopo de campo e foi deixado explicitamente por fazer.

### C. Capacidades entregues (`tools/vision_spike/`, 31 arquivos, fora do caminho de produção)

| Módulo | O que faz |
|---|---|
| `lib/ellipse.js` | ajuste de elipse com centro fixo, ≥4 pontos, QR de Householder, Q positiva-definida, resíduo/condição/lacuna angular · NCC |
| `lib/unwrap.js` | unwrap elíptico 720×16 com amostragem bilinear; perfil **cromático** do rotor; assinatura do anel **estático**; grade do trigger |
| `lib/direction_core.js` | high-pass temporal, correlação circular ±120°, 12 guards, abstenção obrigatória |
| `lib/rvfc_meter.js` | medidor de cobertura (callbacks/s, gaps, `presentedFrames`, visível×oculto) |
| `lib/motion_trigger.js` | trigger de movimento a ~1 FPS **na própria ROI** |
| `lib/pipeline.js` | janelas deslizantes + sumário com **numerador e denominador** de cada taxa |
| `lib/synthetic.js` | cena determinística + 8 casos adversariais (marcada `evidence_class: synthetic`) |
| `lib/evidence.js` | envelope `synthetic` / `fixture` / `field` com `eligible_for_go_gates` |
| `replay.js` | CLI do replay offline sobre captura gravada ou cenário sintético |
| `manifest.json` + `probe/` | extensão de **diagnóstico separada**: E0, E0b, calibração por snapshot 1:1, coletor, bancada com `<video>` local |

### D. Três defesas independentes contra o aliasing (a parte que a auditoria mandou consertar)

1. **Margem de alias** — enumeram-se **todos** os máximos locais em ±120° e compara-se o pico com o
   melhor concorrente. Pico empatado ⇒ `alias_margin_low` ⇒ abstenção.
2. **Landmark do zero verde** — evidência **independente** da correlação. A métrica não é prominência
   por MAD e sim **margem de unicidade** (pico menos o melhor outro máximo a mais de um bolso de
   distância, sobre o p90−p10 do perfil). A bancada mostrou por que: com fundo bimodal vermelho/preto
   o MAD é enorme e o verde legítimo marca z≈3,9 — indistinguível de ruído. A margem de unicidade dá
   ≈1,43 com verde e ≈0,00 sem. Sem esse achado, o spike teria embarcado um detector que não detecta.
   A tolerância de concordância (8°) é **menor** que o período do bolso (9,73°) de propósito.
3. **Passo temporal seguro** — a 10 fps com stride 1 (Δt=0,1 s) o rotor lento anda 7,2° e o alias
   vizinho cai em −2,5°: **sinal trocado**. É aritmética, não opinião. `stride_too_small` obriga
   aumentar o stride antes de qualquer veredito.

Consistência entre os 3 pares entra como **guard**, jamais como prova.

### E. Invariantes preservados

- **Zero autoridade.** Nenhum `direction_event`, nenhum WebSocket, nenhum `fetch`, nenhum upload. Nada
  toca `direcao`, `seed_parity`, `spin_seq`, timeline, decisão ou stake. **INV-3 intocado.**
- **`direction: null` em qualquer abstenção** — testado como invariante sobre 5 cenários adversariais.
- **Frames nunca saem da máquina**: a exportação de captura é um `download` local; `.gitignore` do
  spike bloqueia `*.rgba`, `frames.bin`, `capture.json`, mídia e evidência exportada.
- **`captureVisibleTab` não é usado em lugar nenhum** do spike (bucket de quota global, 2/s,
  compartilhado com o OCR da produção, e cego com a janela minimizada).
- **Default-OFF**: `vsProbePolicy` nasce `'off'`; as probes ficam inertes até o operador armar.
- **`extension/manifest.json` de produção intocado** — a extensão de diagnóstico tem manifest próprio.
- **Isolamento**: zero `require`/`import` de `server/`, `state/` ou `extension/`.

### F. Impacto ISO/IEC 25010

| Característica | Antes | Depois | Por quê |
|---|---|---|---|
| **Adequação funcional** | 8.5 | 8.5 | Nenhuma regra de negócio mudou. O sistema em produção é bit-a-bit o mesmo. |
| **Confiabilidade** | 9.0 | 9.0 | Nada novo no caminho crítico. O que muda é que uma decisão de investimento deixa de depender de opinião. |
| **Manutenibilidade** | 9.0 | **9.2** | A pergunta "dá para ver o sentido no vídeo?" saiu de conversa para 66 testes executáveis e um replay reproduzível por `algorithm_sha`. Qualquer pessoa consegue refutar o resultado sem a mesa. |
| **Testabilidade (sub-característica)** | — | **nova** | Um caminho que depende de mesa ao vivo ganhou bancada offline: cena sintética determinística, 8 casos adversariais e `<video>` local por `captureStream()`. |
| **Segurança** | — | — | Extensão de diagnóstico com **uma** permissão (`storage`), sem `downloads`, sem `tabs`, sem `captureVisibleTab`, e sem canal de saída. |
| Usabilidade / Desempenho / Compatibilidade / Portabilidade | — | — | Sem alteração no produto. |

**Scorecard: 8.7 → 8.75/10** (o ganho é de manutenibilidade/testabilidade; nada de produção mudou).

### G. Obrigações assumidas

1. **Nenhum gate de GO pode ser preenchido com `eligible_for_go_gates: false`.** Só
   `evidence_class: field` conta. O service worker de diagnóstico **rebaixa** automaticamente
   evidência marcada `field` numa sessão declarada `fixture`; rebaixar é seguro, promover nunca.
2. **`confidence` é escore heurístico de qualidade, não probabilidade calibrada** — o campo
   `confidenceKind: 'heuristic_quality_score'` viaja junto para impedir a leitura errada.
3. **`blob:` não prova MSE.** Do mundo isolado do content script não dá para inspecionar o
   `MediaSource`; a probe reporta `mse_confirmed: null`. "Não sei" é resposta válida; inventar não é.
4. **Congelar `config` e `algorithm_sha` antes da coleta.** Ajustar limiar depois de ver os dados
   transforma a coleta em conjunto de desenvolvimento e **exige coleta nova e independente**.
5. **A definição dos gates está no código** (`lib/pipeline.js::summarize`), não só na prosa. O
   denominador de `sinal` inclui os frames de aquecimento de propósito: assim uma captura curta
   (< 250 frames) é aritmeticamente incapaz de atingir 98% — não dá para exibir "98%" de 30 frames.
6. **Cobertura é medida antes de acurácia**, e `< 30 vereditos emitidos` é **NO-GO por escassez**,
   nunca "acurácia alta".
7. **Premissa do canal cromático a verificar em campo:** o estimador depende do setor verde do zero
   ser único e legível. O caso `noGreen` prova que, sem ele, o estimador **se cala** — e essa é
   exatamente a hipótese que a mesa real pode derrubar.

### H. Decisões que exigem humano (§10.6, registradas aqui como manda o brief)

1. **GO/NO-GO do V3 é decisão de investimento** (§10.6-1): o spike entrega os números; o **operador**
   decide se a latência de correção (1-3 giros, contra 30-60 min do V6) paga o esforço L do SPR-V5
   mais a manutenção perpétua de visão sobre o layout de um terceiro.
2. **Aceite formal da cobertura medida** (§10.6-2): o comportamento do `<video>` com a aba oculta e a
   janela minimizada **não deve ser presumido**. O V3-A entrega o instrumento que mede; o aceite do
   número é do operador. V6A/V6B não dependem de pixels.

### H2. Dívida declarada (não entregue, de propósito)

1. **CI não cobre o spike.** ~~O job `extension-tests`…~~ **QUITADA na 2ª rodada** (§I2): com
   autorização formal do Diretor, `ci.yml` entrou no escopo e o job roda os dois globs.
2. **`node --test tools/vision_spike/` não funciona** (o Node tenta carregar o diretório como
   módulo): use o glob `node --test "tools/vision_spike/tests/*.test.js"`. É a mesma pegadinha
   já documentada no `ci.yml` para `tests/js/`.
3. **Custo no renderer não medido por este PR**: os números de `ORCAMENTO.md` são de bancada
   em Node sobre buffers em memória. O botão *Medir 120 frames* da bancada entrega p50/p95/máx
   no navegador — e ainda assim é `fixture`, não mesa.
4. **Caminhos exclusivos do navegador sem teste de unidade**: `probe/collector.js`,
   `probe/probe_e0*.js`, `probe/export.js` e `probe/calibrate.js` dependem de `chrome.*` e do
   `<video>`. A lógica que dava para extrair FOI extraída e testada (`export_stream`,
   `rvfc_meter`, `direction_core`, `pipeline`, `algo_sha`); o que sobrou é encanamento, e é
   verificado por leitura e pela bancada `probe/fixture_video.html`. Declarado, não escondido.

### I. Achados do code-review incorporados (rodada de revisão antes do PR)

O review encontrou **1 defeito crítico e 8 relevantes**, todos corrigidos neste mesmo PR:

| # | Defeito | Por que importava |
|---|---|---|
| 1 🔴 | **O coletor abstinha 100% em qualquer feed acima de ~11 fps.** `captureBurst` gravava 6 frames *consecutivos* na taxa nativa do stream; a 25-30 fps a rajada inteira dura 167-200 ms e o guard `stride_too_small` (Δt de par ≥ 270 ms) disparava sempre. Corrigido com **decimação por `mediaTime`** (`createDecimator` + `recommendedFrameIntervalS`, que sai da própria aritmética do guard). | O V3-B produziria **cobertura 0/N** e um NO-GO que seria defeito de ferramental lido como propriedade do mundo — mais caro que um falso GO. |
| 2 | Export de captura abortado pelo frame errado: `chrome.tabs.connect` sem `frameId` alcança todos os frames, e o "não tenho captura" do top frame desconectava o port do iframe que gravou. | O caminho de exportação só funcionaria se o vídeo estivesse no top frame — o oposto da premissa do spike. |
| 3 | Com `all_frames: true`, **todo** frame respondia às mensagens do popup; `chrome.tabs.sendMessage` entrega só a primeira resposta. Agora frames sem `<video>` não respondem. | O operador via `no_video_in_frame` do top frame e concluía que o coletor não subiu, enquanto o iframe media. |
| 4 | `captureBurst` sem timeout deixava `state.busy = true` para sempre se o rVFC parasse — exatamente o cenário (aba oculta) que o sprint declara desconhecido, e o do soak de 2 h. `stop()`/`start()` também não recuperavam. | O coletor morria em silêncio no meio da coleta. |
| 5 | O `meta` da captura tinha `evidence_class: 'field'` **hardcoded** e não passava pelo service worker ⇒ captura de bancada entrava no `RESULTADO.md` parecendo campo. Agora a classe vem do que o operador declarou. | Driblava exatamente a trava que este ADENDO chama de obrigação nº 1. |
| 6 | A captura exportada tinha sempre 6 frames, mas o gate de sinal exige ≥250 (teto de 6 frames = 16,7%): **gate inalcançável com a própria instrumentação**. Novo modo *Gravar p/ replay*. Faltavam também `algorithm_sha` e `config` no `meta`. | O item 5 do `PROTOCOLO_CAMPO.md` não tinha como ser executado. |
| 7 | `intervals` do medidor crescia sem teto e era ordenado a cada 2 s: num soak de 2 h a 30 fps são 216 mil entradas — **o medidor perturbava a medição**. Virou ring. | |
| 8 | `calibrate.js` pedia o snapshot à **própria aba de calibração** (que vira a ativa ao ser criada), e o erro exibido mandava o operador procurar no lugar errado. | A calibração é pré-requisito de toda a Etapa 4. |
| 9 | Escritas concorrentes de evidência no SW se sobrescreviam (cada frame envia a sua E0). Virou fila serial. | O registro perdido era justamente o do iframe com o `<video>`. |

Dois achados menores também corrigidos: `sceneChangeAt` usava a oclusão que **não** encosta
no anel estático (falso negativo do guard de NCC) e o `background_diag` podia *promover*
`synthetic` para `fixture` — agora a normalização usa uma hierarquia explícita e só rebaixa.
Além disso, `--bench` foi acrescentado ao replay para que os p95/máx citados em
`ORCAMENTO.md` sejam de fato reproduzíveis pelo comando documentado.

**Lição do próprio review:** todos os cenários de teste rodavam a `fps: 10` — exatamente a
única taxa em que os defaults funcionavam. Uma suíte verde pode estar medindo só a região
onde o código já está certo. O teste de regressão novo exercita 25 e 30 fps.

### I2. Segunda rodada de revisão — 6 achados bloqueantes + 1 menor

A revisão independente barrou o PR. Todos foram corrigidos **com teste que falha no código
anterior** (prova executada revertendo cada correção e rodando o teste-alvo):

| # | Sev | Defeito | Por que importava |
|---|---|---|---|
| 1 | HIGH | **`algorithm_sha` não era cross-platform.** Com `core.autocrlf=true` o blob é LF e a cópia de trabalho é CRLF: o mesmo commit dava `fc918…` no Windows e outro hash no Linux/CI. Agora a receita compartilhada normaliza **CRLF→LF** antes de hashear (CR solto é preservado — é byte de conteúdo). | Um identificador de algoritmo que muda com o sistema operacional não identifica algoritmo nenhum; e o aviso de divergência do `replay.js` viraria ruído permanente, que é como uma trava morre. |
| 2 | HIGH | **Decimador e guard usavam limiares diferentes.** O decimador aceitava a 90% do alvo; o guard `stride_too_small` exige 100%. Feeds de **12, 24 e 60 fps** caíam na fresta: passavam no decimador e reprovavam no guard. Os dois agora usam **o mesmo número**, com margem de 2% sobre o mínimo aritmético. | Cobertura 0/N em campo de novo — o mesmo defeito que a rodada anterior tinha "consertado", agora em outras cadências. |
| 3 | MED | **E0b não separava as 4 fases** e uma fase silenciosa virava `null`/fase ausente. Agora há marca **explícita** de fase (o operador clica antes de esconder/minimizar), duração em wall-clock e taxa `0/N` quando não chega callback. A série completa (12 min = 720 buckets) viaja no registro **final**; os periódicos levam só a cauda. | "0 callbacks em 180 s com a janela minimizada" é o achado mais importante que este instrumento pode produzir. Ausência de dado não pode ser indistinguível de ausência de entrega — e truncar a série descartaria justamente a fase A, que é a referência das outras três. |
| 4 | MED | **Teto de memória cortava depois de alocar tudo.** Virou orçamento **cumulativo** consultado antes de guardar cada frame (`createByteBudget`), com `record.stopped_by: "memory_budget"` no relatório. | Cortar depois já pagou o custo inteiro dentro do renderer de um terceiro — exatamente o que o teto existia para evitar. |
| 5 | MED | **Export sem backpressure, sem ack e sem retomada**, num popup que fecha ao primeiro clique fora dele; `Array.from` por frame; o timeout não rearmava depois do `meta`. Agora: `lib/export_stream.js` (ack + janela de backpressure + retomada pelo primeiro índice faltante), destinatário durável em `probe/export.html` (aba), stall **rearmado a cada mensagem**, e captura incompleta **falha alto**. | Perder a transferência de ~100 MB é perder a coleta de campo inteira — e o operador só descobriria depois de a mesa já ter mudado. |
| 6 | MED | **NCC desligado em silêncio** quando faltava `calibration.sceneSignature`: o coletor caía no primeiro frame e comparava a cena com ela mesma. Agora é **fail-closed** (`ncc: NaN` ⇒ `scene_ncc_low` ⇒ abstenção) e **todo veredito declara `sceneReference`**. | Um veredito com o anti-cena desligado *parecia* totalmente guardado. |
| — | minor | `srcobject_other` afirmava `mse_confirmed: false` sem testar `MediaSource`. Virou `null`. | Mesma disciplina do `blob:`: "não sei" é resposta; inventar não é. |

**Prova das regressões** (cada correção revertida isoladamente, teste-alvo executado):
`algorithm_sha` CRLF↔LF ✗ · decimador 12/24/60 fps ✗ · fail-closed do NCC ✗ · orçamento de
memória ✗ · stall rearmado ✗ · backpressure ✗ · fase silenciosa do E0b ✗ — todas falham sem
o respectivo conserto, e passam com ele.

**Lock ampliado.** Com autorização formal do Diretor, `.github/workflows/ci.yml` entrou no
escopo: o job `extension-tests` passou a rodar
`node --test "tests/js/*.test.js" "tools/vision_spike/tests/*.test.js"`. A dívida declarada
no §H2 item 1 está **quitada**; `.gitattributes` não foi necessário, porque a normalização
vive na receita do hash e não depende de configuração de checkout.

### I3. Terceira rodada — a regressão que a própria correção anterior introduziu

A rodada 2 confirmou os 6 consertos, e encontrou **1 HIGH novo, criado pelo conserto nº 5**.

**O defeito.** `chrome.runtime.Port.postMessage` **serializa em JSON** (structured clone não
é garantido no Chrome suportado e não foi declarado no manifest). O `export_stream` mandava
`Uint8ClampedArray` cru; do outro lado chegava `{"0":12,"1":34,…}` — objeto **sem `.length`**.
A cadeia inteira falhava **em silêncio**:

```
frames[0].length → undefined
stride           → undefined
new Uint8Array(undefined * 3) → Uint8Array(NaN) → comprimento 0
frames[i].length !== stride   → undefined !== undefined → false  (não lança)
out.set(objeto, NaN)          → no-op
resultado: frames.bin de 0 BYTE, sem exceção, com a interface dizendo "3 frames, completo"
```

Reproduzido literalmente, sem mutar arquivo nenhum. **Um arquivo vazio que se declara
completo é pior que um erro**: a coleta de campo só seria descoberta perdida na hora de
rodar o replay, com a mesa já fechada — e o operador teria de refazer 45 minutos de anotação.

**Por que os testes da rodada 2 não pegaram.** Eles entregavam o objeto **em memória** entre
remetente e destinatário. O transporte real era a única parte não exercida — e era onde
estava o defeito. Testar os dois lados sem atravessar o fio é testar duas metades que nunca
se encontram.

**O conserto.**

| Item | Decisão |
|---|---|
| Wire | **base64** com `length` declarado por frame, codec próprio no módulo (sem `btoa`/`atob`/`Buffer`), para que o MESMO código rode no navegador e no `node --test`. Custo medido: **1,333×** no fio (contra ~3,57× de um array de números em JSON), 13,4 ms para codificar e 3,3 ms para decodificar um frame de 330 KB ⇒ +34 MB e ~5 s numa captura de 300 frames, offline. |
| Versionamento | Campo `wire` nas mensagens; receptor **recusa** formato desconhecido em vez de adivinhar. |
| Receptor | Frame que não decodifica, ou cujo `length` não bate, **não é armazenado e não é confirmado** — continua faltando, `complete` nunca vira `true`, e o `assemble()` recusa. |
| `assemble()` | Valida tipo (`isBytes`), `stride` inteiro positivo, igualdade de tamanho entre frames, ausência de recusados e **resultado ≠ 0 byte**. Qualquer anomalia lança. |
| `export.js` | Erro de protocolo e de montagem aparecem **na tela** (vermelho, botão de salvar desabilitado). Nada é salvo quando a montagem falha. |

**Prova por mutação** (cada reversão isolada, teste-alvo executado): wire cru atravessando
JSON ✗ · receptor aceitando objeto sem `length` ✗ · `assemble()` sem validar stride/tipo/0-byte ✗.
Todas falham sem o conserto. O novo teste **TRANSPORT BOUNDARY** passa cada mensagem por
`JSON.parse(JSON.stringify(...))` — o mesmo que o port faz — e compara **byte a byte** os
256 valores possíveis, mais os restos 1 e 2 do base64.

**Lição (Confiabilidade).** Fronteira de serialização é fronteira de teste. Um módulo puro
testado dos dois lados do fio, mas nunca **através** dele, dá cobertura alta e garantia
nenhuma. E o modo de falha a temer não é a exceção: é o caminho que devolve um resultado
plausível — `0` — sem reclamar.

### I4. Quarta rodada — 2 LOWs no receptor do export (rodada final)

A revisão do `74d667e` confirmou o HIGH do transporte totalmente corrigido e apontou dois
defeitos pequenos, ambos do tipo "o código faz o que parece, não o que precisa".

**LOW 1 — `rejected` era append-only, e isso criava um beco sem saída.** Um frame recusado
que chegasse **válido na retomada** era armazenado, mas a recusa antiga permanecia na lista.
Resultado: `complete` nunca virava `true`, o `assemble()` recusava **para sempre** — e a
interface continuava oferecendo *Retomar*. O operador clicaria num botão que nunca resolve,
sobre uma captura que já estava íntegra na memória.
Conserto: as recusas passaram a ser indexadas (`rejectedByIndex`) e **somem** quando o mesmo
índice chega válido. Recusas **sem índice atribuível** (lote malformado, frame sem `index`)
viraram `protocolFaults`: são honestamente **não recuperáveis** por retomada, e a interface
passa a mandar *Iniciar* em vez de oferecer um botão inútil. `progress().recoverable` diz
qual dos dois casos é.

**LOW 2 — `fromBase64` aceitava `charCode > 255` e decodificava lixo em silêncio.**
`B64_LOOKUP` é um `Int16Array(256)`; um caractere não-Latin-1 devolve índice fora do
TypedArray, que é **`undefined`** — e `undefined < 0` é `false`. A checagem `if (d < 0)`
deixava `'\u0100'` passar como válido; ele virava `0` na conta de bits (`x | undefined === x | 0`)
e o frame decodificava lixo sem uma linha de aviso. Conserto: comparação **total**
(`if (!(d >= 0))`, que rejeita negativo, `undefined` e `NaN` de uma vez) e faixa explícita
(`c < 256 ? tabela[c] : -1`).

**Prova por mutação** (cada reversão isolada, teste-alvo executado):
recusa não limpa pela retransmissão ✗ · `recoverable` sempre `true` ✗ · `charCode > 255`
decodificado como lixo ✗. Todas falham sem o conserto.

Testes novos: recuperação **na fronteira JSON** (lote corrompido → retransmissão válida do
mesmo índice → `rejected: 0`, `complete: true`, bytes exatos), recusa repetida que não infla
o contador, recusa sem índice marcada como não recuperável, e Unicode fora da tabela
(`\u0100`, `\u00FF`, `\u20AC`, `\uFFFD`, emoji) recusado tanto no codec quanto no receptor.

**Lição (Confiabilidade).** Os dois defeitos são a mesma família: uma comparação que
*parece* total (`d < 0`) e um estado que *parece* monotônico (`rejected` só cresce). Em
JavaScript, comparar com `undefined` devolve `false` em ambos os lados — `undefined < 0` e
`undefined >= 0` são os dois `false` — então a única checagem honesta é a que exige a
condição desejada, não a que nega a indesejada. E estado de erro que nunca é limpo
transforma qualquer recuperação em teatro.

`algorithm_sha` **inalterado** (`4f7566da2f44e9b4`): o transporte não faz parte do algoritmo.

### J. Rollback

| # | Camada | Ação | Efeito |
|---|---|---|---|
| 1 | **Nenhuma ação** | não usar | O spike não é importado por `server/`, `state/`, `extension/` nem por nenhum caminho de produção. Já está inerte por construção. |
| 2 | **Extensão de diagnóstico** | remover em `chrome://extensions` (ou deixar `vsProbePolicy: 'off'`) | Ela é separada da Escuta Beat; removê-la não afeta a operação. |
| 3 | **Código** | `git revert` do PR | Remove `tools/vision_spike/` inteiro. Zero migração, zero flag de compose, zero estado persistido em produção. |

`extension/manifest.json` de produção **não foi tocado** ⇒ não há zip de versão anterior a anexar,
nem nota de reload para o operador.

**Suítes.** Python **904 passed, 9 skipped, 1 xfailed** (idêntico ao baseline: o spike não toca o
caminho de produção). JS do spike **66 passed** (`node --test "tools/vision_spike/tests/*.test.js"`).
JS do V2 **53 passed**, intacto. `lint_silent_except` OK · `lint_dna_coverage` OK · `schema_symmetry` OK.

**Lição (Manutenibilidade / Adequação funcional).** Um spike cujo sucesso é medido pela própria cena
que ele gera não é evidência: é "inverse crime". A separação `synthetic` / `fixture` / `field`, com
`eligible_for_go_gates` viajando dentro de cada artefato, foi o que impediu este sprint de fechar a
própria DoD com números de bancada. **Toda taxa nasce com denominador, e todo denominador nasce com a
classe da evidência que o produziu** — sem isso, um gate falseável vira um gate decorativo.
