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
