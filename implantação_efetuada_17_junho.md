# 🎯 Implantação EFETUADA — C1=ForceLast / 17# / 3 Regiões (force17) — 17–18/Junho/2026

> **Registro consolidado da implantação executada** que evoluiu a estratégia de produção de
> **c2c3 (14# = C2+C3 estático)** para **force17 (3 regiões = 17 números, com C1 = ForceLast)**,
> com saída no front-end mostrando os 3 centros rotulados (c2/c3/c1), os 17 números apostados a
> cada jogada, e o reflexo verde/vermelho + sentido do resultado anterior.
>
> **Base empírica:** `analise_400_junho.md` (PARTES VII–XV — geometria 17# de menor breakeven).
> **Spec do implementador:** `implantação_c1_proposta_nova_junho.md` (§0–§9, 7 sprints).
> **Bugs/sprints prévios:** `implantação_C1_variavel_junho.md` §17–§19.
>
> **Status:** ✅ **Implementado, testado (557 passed) e go-live no compose** (`SDA_BET_PAIR=force17`).
> Default do **código** permanece `full` (byte-idêntico); o **compose** versionado ativa force17.

---

## 1. Sumário executivo (TL;DR)

| Item | Antes (c2c3) | Depois (force17 — go-live) |
|---|---|---|
| Cobertura por aposta | 14# (C2 ∪ C3, raio 3 cada) | **17# nominal** = C2(±3,7) ∪ C3(±2,5) ∪ **C1=ForceLast**(±2,5); **real ~15** (overlap permitido) |
| 3ª região (C1) | inexistente (c2c3 não usa C1) | **ForceLast** = último resultado do sentido projetado pela última força |
| Saída no front-end | par + centros | **3 regiões rotuladas c2/c3/c1** (numerinho embaixo de cada centro) + **os 17 números** |
| Reflexo do resultado | veredito red/green | **verde/vermelho + SENTIDO analisado** (horário/anti-horário) |
| Aposta | 14 números | **17 números a cada jogada** (INV-3 — sempre sugere) |
| Análise por sentido | isolada | **isolada** (CW prevê CW; CCW prevê CCW) via `cw_history`/`ccw_history` |
| Staking | block_gale cap1 (flat-eq.) | inalterado (flat-equivalente, sem ruína) |
| Cobertura vazia (B1) | ~4% das decisões com `sda_numbers=[]` | **corrigido** (rede de segurança nunca-vazio) |

**O que foi entregue:**
1. **Motor** `force_select()` + `coverage3()` + `force_last_center()` em `strategies/c_selection.py`
   (determinístico, causal, isolado por sentido, stateless).
2. **Modo** `force17` no enum `SDA_BET_PAIR` (`app_config/settings.py`).
3. **Wiring** em `server/message_handler.py` (dispatch + telemetria + rede de segurança B1).
4. **Telemetria** `force17`/`regioes`/`ultimo_acerto{direction}` nos canais `sugestao` e `trace`/`state_sync`.
5. **Front-end**: overlay da extensão (`content.js`) + dashboard Glass Box (`frontend/`) renderizando
   as 3 regiões rotuladas, os 17 números e o veredito verde/vermelho + sentido.
6. **Observabilidade**: gauge Prometheus `roleta_force17_active`.
7. **Go-live** no `docker-compose.yml` (`SDA_BET_PAIR=force17`).
8. **19 testes** novos (`TestForceSelect`, `TestForce17Wiring`, `TestB1NonEmptyCoverage`) +
   suíte completa **557 passed**.

**Honestidade estatística (mantida do estudo):** o edge agregado é **modesto e não-conclusivo**
(roda uniforme χ²=33,3; perm p≈0,03–0,13). A entrega é **estrutura melhor (17# de menor breakeven +
C1 balístico de menor variância) + instrumentação**, não promessa de lucro. A decisão de *quando*
apostar (esperar um red) é do **usuário**; o motor sempre **sugere e mede**.

---

## 2. A estratégia force17 (o que muda no C1)

### 2.1 Definição matemática (determinística, causal, por sentido)
Com os resultados brutos do **mesmo sentido** `r[-1]` (último) e `r[-2]` (penúltimo):
```
forca = sdist(r[-2], r[-1])               # distância circular ASSINADA (−18..+18) na WHEEL_SEQUENCE
C1    = WHEEL[(pos(r[-1]) + forca) % 37]   # ForceLast: projeta o último pela última força
```
- **Raios:** C2 = ±3 (7#), C3 = ±2 (5#), **C1=ForceLast = ±2 (5#)**.
- **Requisito mínimo:** ≥2 resultados do sentido. Antes disso → C1 **"aquecendo"**, cobertura cai
  para C2∪C3 (12–14#) — **nunca vazio**.
- **Fonte (fix B4):** os resultados brutos vêm de `strategies/sda17.py` `cw_history`/`ccw_history`
  = `[(c1, actual_result)]`; o ForceLast lê `[i][1]` (o resultado real), **não** as distâncias do
  `c_attr`. Lê o history do `target_direction` (oposto ao spin recém-jogado → estável e isolado).

### 2.2 Cobertura 17# (união real, sobreposição PERMITIDA)
```
cobertura = vizinhos(C2, ±3) ∪ vizinhos(C3, ±2) ∪ vizinhos(C1=ForceLast, ±2)
```
- **Nominal 7+5+5 = 17**; **real ~15** (overlap médio 1,65; 54% das jogadas têm overlap). **NÃO**
  forçamos disjunção (mover o C1 para não sobrepor **piora** — PARTE XIV). Aposta-se a **união**.
- **Stake flat**, 1u por número **distinto** (sem gale).

### 2.3 Por que ForceLast (validação)
- Única família que **agrega** sobre C2+C3 (assinatura balística do crupiê); regiões frias/quentes,
  lag e drift capturam ≈ acaso.
- Não "prevê" (capta ~13,9% ≈ acaso 13,5%); seu valor é **estrutural**: **reduz a variância**
  (sd 3,39 vs 7,14) e melhora a consistência (4/5 folds positivos).
- Geometria 17# tem **breakeven 47,2%** (vs 58,3% do 21#) — o ganho estrutural mais robusto.

---

## 3. Arquitetura e wiring (mapa do código)

### 3.1 Motor — `strategies/c_selection.py` (novos)
| Símbolo | Papel |
|---|---|
| `_signed_dist(frm,to,wheel)` | distância circular **assinada** (−18..+18); espelha `sda17._signed_dist_idx` |
| `force_last_center(last_results, wheel)` | ForceLast 1-passo; `None` se <2 resultados |
| `coverage3(c2,c3,c1,wheel, r=3/2/2)` | união real C2∪C3∪C1; `c1=None` ⇒ só C2∪C3; **nunca vazio** |
| `CSelectionEngine.force_select(direction, centers, last_results, wheel)` | devolve `CSelection` com `numbers` (17#), `centers=[C1_exib, C2, C3]` e `scoreboard.regioes` rotuladas c2/c3/c1 + `c1_force` + `coverage_n`. `freeze={}` ⇒ sem shadow/feedback (determinístico) |

### 3.2 Settings — `app_config/settings.py`
`bet_pair_mode()` enum += `force17`. Lido por chamada (toggle runtime). Inválido → `full`.

### 3.3 Wiring — `server/message_handler.py`
| Ponto | O que faz |
|---|---|
| `_engine_apply_selection` (branch `force17`) | lê os 2 últimos `actual_result` do `target_direction` (`self.strategy.cw_history/ccw_history`), chama `force_select`, substitui `result.numbers` (17#), mantém `details['centers']=3`. Stasha `_cs_meta['force17']` e `game_state.last_force17_meta` (fonte única p/ dashboard) |
| `_ensure_nonempty_coverage` (novo) | **Sprint 0 / B1**: se a cobertura ficou vazia mas há centros, emite a união (C2∪C3∪C1 se 3, senão vizinhança) — a indicação **nunca cobre zero números** |
| `_engine_overlay_fields` (canal `sugestao`) | emite `force17{regioes, c1_force, coverage_n, dir_bias}`, `regioes` e `ultimo_acerto{slot, green, numero, direction}` |
| `engine_overlay_fields` em `state/game.py` (canal `trace`/`state_sync`) | espelha `force17`/`regioes` (de `last_force17_meta`) + `ultimo_acerto.direction` |

### 3.4 Alimentação do DB por sentido (req. do operador)
O spin chega com `direcao` (validado via `SpinInput`, `message_handler.py:392`). Fluxo:
`check_prediction(numero)` → `update_adaptive(bet_direction, c1, numero)` anexa `numero` ao history do
**sentido da predição** (= o sentido do spin) → `process_spin` seta `last_direction` →
`target_direction` = **oposto** → `analyze` + `force_select` leem o history do `target_direction`.
**Conclusão:** o resultado é gravado no history do sentido correto e o ForceLast é **isolado por
sentido** (CW só usa CW; CCW só usa CCW).

---

## 4. Front-end (a saída pedida)

### 4.1 Overlay da extensão — `extension/content.js`
- `buildForce17HTML(sugestao)`: renderiza os **3 centros** em coluna — número grande e, **embaixo**,
  o **rótulo pequeno** (c2/c3/c1) — na ordem **c2, c3, c1** (pedido do operador), mais os **17 números**
  e o header `🎯 3 regiões · N números · ✅/⚠️ (dir_bias)`.
- `buildVeredito(ultimo_acerto)`: **🟢 VERDE / 🔴 VERMELHO** + **sentido** (horário/anti-horário) +
  número do resultado anterior. Renderizado no novo elemento `#eb-veredito`.
- C1 "aquecendo" ⏳ quando <2 resultados.

### 4.2 Dashboard Glass Box — `frontend/`
- Novo card **"🎯 3 Regiões (17#)"** (`force17-card`): 3 centros coloridos rotulados + os números +
  `coverage_n` + `dir_bias` (`updateForce17`).
- `updateVerdict` agora inclui o **sentido** (· horário / · anti-horário).
- Label do card de resultado atualizado de "Região (14#)" → **"Região (17#)"**.
- Consumido nos canais `trace` e `state_sync` (campos aditivos; clientes antigos ignoram).

---

## 5. Inventário de arquivos

**Modificados (implementação):**
- `strategies/c_selection.py` — `force_last_center` + `coverage3` + `_signed_dist` + `force_select` (+131 linhas).
- `app_config/settings.py` — `bet_pair_mode()` += `force17`.
- `server/message_handler.py` — branch `force17`, `_ensure_nonempty_coverage` (B1), telemetria overlay.
- `state/game.py` — `force17`/`regioes` + `ultimo_acerto.direction` em `engine_overlay_fields`.
- `server/health_server.py` — gauge `roleta_force17_active`.
- `extension/content.js` — render 3 regiões rotuladas + 17 números + veredito verde/vermelho + sentido.
- `frontend/index.html` + `frontend/app.js` — card force17 + `updateForce17` + verdito com sentido.
- `docker-compose.yml` — go-live `SDA_BET_PAIR=${SDA_BET_PAIR:-force17}`.
- `.silent_except_baseline.json` — baseline dos excepts defensivos (rede B1 + gauge).

**Testes:**
- `tests/test_c_selection.py::TestForceSelect` — 11 testes (ForceLast, coverage3, labels, fallback, raios).
- `tests/test_wiring_c_gale.py::TestForce17Wiring` + `::TestB1NonEmptyCoverage` — 8 testes (dispatch, overlay, B1).
- `tests/test_ws_overlay_contract.py` — atualizado p/ `ultimo_acerto.direction`.

---

## 6. Testes e validação

- **Unitários do motor** (`TestForceSelect`): ForceLast `[32,15]→19`; coverage3 nominal 17 / real <17 com
  overlap; fallback "aquecendo" (só C2∪C3, nunca vazio); determinístico/stateless; raios 3/2/2; labels c2/c3/c1.
- **Wiring** (`TestForce17Wiring`): `force17` substitui p/ ≤17 lendo o history do sentido; "aquecendo" sem
  2 resultados; overlay expõe `regioes`+`dir_bias`; flag OFF ⇒ `full` byte-idêntico.
- **B1** (`TestB1NonEmptyCoverage`): cobertura vazia preenchida de 3 centros / 1 centro; intacta quando há
  cobertura; sem centros permanece vazia (1ª jogada → PULAR correto).
- **Suíte completa:** `557 passed, 9 skipped, 1 xfailed` (era 538 — +19 testes force17/B1). Lint de excepts
  defensivos verde (baseline atualizado via `tools/lint_silent_except.py --update`).

---

## 7. Deploy e go-live

`docker-compose.yml` (`services.roleta-cloud.environment`):
```yaml
- SDA_BET_PAIR=${SDA_BET_PAIR:-force17}   # 3 regiões (C1=ForceLast + 17#) — SAÍDA NOVA
- SDA_STAKING_MODE=${SDA_STAKING_MODE:-block_gale}   # cap 1 = flat-equivalente (sem ruína)
- GALE_CAP=${GALE_CAP:-1}
```
**Fluxo:** push em `main` → `systemctl start roleta-deploy.service` (fetch + `git reset --hard origin/main`
+ build + `docker compose up -d`) → container recria lendo os novos defaults.

**Rollback (sem `.env` no host):** `SDA_BET_PAIR=c2c3` (ou `full`) no host env + redeploy, **ou** `git revert`
do commit do compose. As flags persistentes vivem no compose versionado (`${VAR:-default}`).

**Verificação live esperada:** decisões com `N≤17`, overlay com `c1_force`/`regioes`, `/health` v4.x ok,
gauge `roleta_force17_active=1`, 0 tracebacks.

---

*(Seções 8–10: auditorias e estrutura de manutenabilidade — preenchidas nas próximas fases deste sprint.)*

---

## 8. 🔬 Auditoria pós-implantação #1 — software · fluxo de dados · servidor

> Bug hunt profundo após codar. Cada item: **verificação** e **veredito**. Rodou suíte (557) +
> simulação e2e com a **SDA17 real** (24 spins alternando sentido) + inspeção do fluxo de dados.

### 8.1 Frentes auditadas e veredito

| # | Frente | Verificação | Veredito |
|--:|---|---|:--:|
| 1 | **Fonte/timing do ForceLast** | lê `cw_history/ccw_history[-2:][1]` do `target_direction`; `update_adaptive` (msg_handler:495) anexa ao sentido do spin (oposto ao target) ANTES do `analyze` → o history do target não é tocado pelo spin atual | ✅ correto/estável |
| 2 | **Isolamento por sentido** | simulação: `C1` do CW varia `[8,21,18,26,9]` e do CCW `[8,35,35,19,30]` de forma independente | ✅ isolado |
| 3 | **Alimentação do DB por sentido (req. operador)** | spin chega com `direcao` (`SpinInput`); `update_adaptive(bet_direction=pending.direction, …)` grava no history do sentido correto | ✅ correto |
| 4 | **Veredito verde/vermelho** | `_attribute_hit_region` só devolve `slot="miss"` quando `hit=False` (game.py:539); `hit = actual ∈ numbers` (cobertura 17# REAL) → `green == hit` sempre | ✅ consistente |
| 5 | **B1 (N=0 / cobertura vazia)** | `_ensure_nonempty_coverage` preenche de 3 centros (coverage3) ou 1 centro (vizinhança); só a 1ª oportunidade por sentido (timeline=0, cold-start) fica sem aposta — PULAR correto (INV-3) | ✅ corrigido |
| 6 | **INV-3** | force17 só reescreve `result.numbers`; nunca toca `acao`/supressão; gates seguem como `min()` no stake | ✅ preservado |
| 7 | **Byte-identidade (`full`)** | flag OFF ⇒ `_engine_apply_selection` retorna sem tocar cobertura; rede B1 só dispara no caso vazio (bug) | ✅ idêntico |
| 8 | **Persistência** | `GameState` sem `__slots__` (set seguro); `last_force17_meta` transiente **não** entra em `save()`; `load()` usa `getattr` default; force17 é stateless (lê history já persistido) | ✅ sem poluição |
| 9 | **Overlay aditivo** | `force17`/`regioes`/`ultimo_acerto` são campos novos; clientes antigos ignoram; JSON-serializável (`test_overlay_is_json_serializable`) | ✅ retrocompatível |
| 10 | **Consumidores de `bet_pair_mode()`** | só 2 no código (dispatch em `message_handler:103` e gauge em `health_server:207`), ambos cientes de force17; nenhum outro caminho quebra | ✅ contido |

### 8.2 Bug corrigido nesta auditoria

- **B1 — cobertura vazia (`sda_numbers=[]`, ~4% das decisões de calibração):** era **bloqueante** para
  "sugerir/apostar a cada jogada". `_engine_apply_selection` retornava cedo em `<3 centros`, deixando a
  cobertura vazia. **Fix:** novo `_ensure_nonempty_coverage(result)` chamado logo após a seleção — se a
  cobertura ficou vazia mas há centros, emite a união (`coverage3` se 3, vizinhança se 1). **Agnóstico de
  modo**, dispara só no caso quebrado (preserva byte-identidade). Regressão: `TestB1NonEmptyCoverage` (4).

### 8.3 Nuances documentadas (não-bugs)

1. **`ultimo_acerto.slot`** (C1/C2/C3) reflete a atribuição pelos **centros geométricos** do SDA17, não
   pela região ForceLast — é telemetria secundária; o **veredito verde/vermelho continua correto** (= hit
   real na cobertura 17#). Cosmético.
2. **ForceLast "aquecendo" pós-reset de dealer:** a troca de dealer (`handle_new_session`) zera o history
   da estratégia → o C1 reaquece (1–2 jogadas/sentido caindo para C2∪C3). É o comportamento esperado
   (cold-start por dealer); o estudo nota que a força gosta de continuidade, mas o reset por dealer é
   premissa do produto.
3. **Calibração (1ª oportunidade por sentido):** `PULAR`/sem aposta quando `timeline=0` (sem dados) — INV-3
   permite no-bet só nessa 1ª oportunidade; da 2ª em diante o fallback emite cobertura.

> **Conclusão Auditoria #1:** **0 bugs funcionais remanescentes**; 1 bug pré-existente (B1) **corrigido**;
> 3 nuances documentadas. Suíte **557 passed**.

---

## 9. 🛠️ Estrutura pós-implantação (Manutenabilidade ISO/IEC 25010)

> Conformidade registrada como **ADENDO 18/06** em `Manutenabilidade_iso.md` (mesmo padrão dos ciclos
> anteriores: A. capacidades · B. bugs · C. impacto ISO · D. scorecard · E. obrigações).

### 9.1 Rotinas de deploy / Docker (subir a nova saída)
- **Ativação persistente:** default versionado no `docker-compose.yml` (`SDA_BET_PAIR=${SDA_BET_PAIR:-force17}`)
  — mesmo padrão de `SDA_STAKING_MODE`/`SDA_REGIONS_V4` (não há `.env` no host; o auto-deploy faz
  `git reset --hard origin/main`, revertendo edições manuais de arquivos versionados).
- **Pipeline:** push em `main` → `systemctl start roleta-deploy.service` (fetch + reset + build +
  `docker compose up -d`) → container recria lendo os novos defaults.
- **Banco de produção:** Docker **named volume** `roleta-data` (`/app/data/decisions.db` no container;
  `/var/lib/docker/volumes/roleta-cloud_roleta-data/_data/…` no host). **Sem migração** (force17 não muda
  schema — grava `sda_numbers` (17#) e `sda_centers` (3 geométricos) nas colunas existentes).
- **Estado do jogo:** `state.json` (volume). force17 é **stateless** (lê `cw_history/ccw_history` já
  persistidos pelo SDA17); nada novo a persistir. `last_force17_meta` é transiente.
- **Healthcheck:** `/health` (porta 8766) inalterado; gauge novo `roleta_force17_active`.

### 9.2 Obrigações de manutenção (ciclo force17)
1. **force17 é stateless/determinístico** — `force_select` não lê/escreve estado do motor; não introduzir
   efeitos colaterais.
2. **Fonte do ForceLast = `cw_history/ccw_history[i][1]`** (resultado bruto), nunca `c_attr` (distâncias).
   Ao tocar o resolve, preservar.
3. **Rede B1 (`_ensure_nonempty_coverage`)** roda para TODOS os modos — manter agnóstica (só preenche vazio).
4. **Overlay aditivo** (`force17`/`regioes`/`ultimo_acerto.direction`) — não remover/renomear chaves
   (Obrigação ISO #9, retrocompatibilidade com clientes antigos).
5. **Rollback:** `SDA_BET_PAIR=c2c3`/`full` + redeploy, ou `git revert` do compose.
6. **Lint de excepts:** `tools/lint_silent_except.py --update` se adicionar `except` (baseline atualizado).
7. **Geometria 17# = 7+5+5** (raios 3/2/2 em `c_selection.py`); o overlap é **permitido** (não forçar
   disjunção — piora).

### 9.3 Impacto ISO (resumo; detalhe no ADENDO)
- **Adequação Funcional:** cobertura estruturalmente melhor (17# breakeven 47% + C1 balístico) fiel ao
  estudo; INV-3 intacto; 19 testes dedicados; **B1 corrigido** (não havia indicação vazia antes).
- **Confiabilidade:** force17 stateless/determinístico (sem shadow/feedback); default-safe (full = byte-id.);
  persistência sem poluição; rede de segurança nunca-vazio.
- **Usabilidade:** front-end com **3 regiões rotuladas + 17 números + veredito verde/vermelho com sentido**
  — o operador vê a sugestão e o reflexo em tempo real (overlay + dashboard).
- **Manutenibilidade:** dispatch explícito por flag (4 modos + no-op) + 19 testes; `message_handler.py`
  cresce ~+45 LOC (Gap D.1 — candidato à extração futura).

---

## 10. 🔍 Auditoria pós-implantação #2 — passo-a-passo do fluxo (100% funcional)

> Validação end-to-end: a estratégia REAL (SDA17) através de **24 spins alternando sentido**, exercitando
> o ciclo completo `check_prediction → update_adaptive → process_spin → analyze → force_select →
> _ensure_nonempty_coverage → overlays`, com `store_prediction` para resolver o spin seguinte.

### 10.1 Passos do fluxo de dados validados (cada spin)
1. **Entrada:** `{numero, direcao}` chega (extensão) → `SpinInput` valida → dedup.
2. **Resolução t-1:** `check_prediction(numero)` → `last_hit_attribution{slot, numero, dist_*}`; hit = nº ∈ 17#.
3. **Feed DB por sentido:** `update_adaptive(bet_direction, c1, numero)` anexa ao `cw/ccw_history` correto.
4. **Processa spin:** `process_spin` seta `last_direction`; `target_direction` = oposto.
5. **Análise:** `analyze(target_timeline,…)` produz os 3 centros geométricos do SDA17.
6. **force17:** `force_select(target, centers, last_results, wheel)` → ForceLast + cobertura 17# (≤17),
   `centers=[C1_exib, C2, C3]`, `regioes` rotuladas.
7. **Rede B1:** `_ensure_nonempty_coverage` garante não-vazio.
8. **Telemetria:** `_engine_overlay_fields` (→ `sugestao`) e `engine_overlay_fields` (→ `trace`/`state_sync`)
   emitem `force17`/`regioes`/`ultimo_acerto{green, direction}`.
9. **Front-end:** overlay e dashboard renderizam 3 regiões + 17 números + veredito verde/vermelho + sentido.

### 10.2 Evidência (simulação, spins 4–10, seed=7)

| spin | sentido | centros SDA | N | regiões (c2,c3,c1) | C1=ForceLast |
|--:|---|---|:--:|---|:--:|
| 4 | horário | [28,21,33] | 12 | c2=21, c3=33, c1=2 | aquecendo→ok |
| 5 | anti | [30,14,21] | 16 | c2=14, c3=21, c1=32 | 32 |
| 6 | horário | [30,14,21] | 16 | c2=14, c3=21, c1=24 | 24 |
| 7 | anti | [10,22,17] | 17 | c2=22, c3=17, c1=8 | 8 |
| 8 | horário | [21,30,28] | 17 | c2=30, c3=28, c1=14 | 14 |
| 9 | anti | [25,23,35] | 17 | c2=23, c3=35, c1=1 | 1 |
| 10 | horário | [23,9,25] | 16 | c2=9, c3=25, c1=33 | 33 |

### 10.3 Asserts da auditoria #2 (todos ✅)
- **Cobertura nunca vazia** da 2ª oportunidade/sentido em diante (vazios só nas 4 primeiras = cold-start
  por sentido = PULAR correto INV-3).
- **Rótulos sempre `c2, c3, c1`** (ordem pedida pelo operador), numerinho embaixo de cada centro.
- **C1=ForceLast recalculado a cada spin e isolado por sentido** (CW e CCW evoluem independentes).
- **`ultimo_acerto` carrega `direction`** (19 vereditos com sentido) — verde/vermelho + horário/anti.
- **`dir_bias`** marca anti=favorável / horário=desfavorável.
- **`regioes` presentes nos DOIS canais** (`sugestao` e `trace`/`state_sync`).

> **Conclusão Auditoria #2:** o fluxo de dados **valida o que a estratégia propõe** (17# = C2∪C3∪ForceLast,
> isolado por sentido, sempre não-vazio, veredito com sentido) e está **100% funcional** end-to-end.
> Suíte **557 passed, 9 skipped, 1 xfailed**.

---

*Documento gerado em 18/06/2026. Fonte da verdade do código: `main`. Spec empírica: `analise_400_junho.md`
(PARTES VII–XV). Spec do implementador: `implantação_c1_proposta_nova_junho.md`. Conformidade ISO: ADENDO
18/06 em `Manutenabilidade_iso.md`.*

---

## 11. 🔬 Auditoria pós-implementação #3 — front-ends + fluxo recepção→retorno (18/06, tarde)

> Foco pedido: (a) os **17 números** já estão sendo mostrados? (b) a estrutura **c1/c2/c3 embaixo dos
> números** na frente da Escuta (overlay) está informada? (c) **bug hunt no fluxo inteiro** — da recepção
> de um resultado ao retorno — com correção. Validado com captura **live** do payload `sugestao` através do
> `handle_new_result` REAL.

### 11.1 Cadeia do front-end (verificada ponta a ponta)
```
servidor (sugestao) ──WS──▶ extension/background.js:468 (onmessage type=sugestao)
   └▶ sendSuggestionToContentScript(data.data)  [passa o objeto INTEIRO, sem stripping]
      └▶ chrome.tabs.sendMessage(tabId, {action:'updateOverlay', data: sugestao})
         └▶ content.js:743 onMessage ▶ updateOverlay(message.data)
            └▶ buildForce17HTML(sugestao)  → 3 regiões rotuladas c2/c3/c1 + 17 números
            └▶ buildVeredito(sugestao.ultimo_acerto) → 🟢/🔴 + sentido
```
- `regioes`, `force17`, `numeros`, `ultimo_acerto` chegam **intactos** ao `updateOverlay` (background não
  filtra campos). `popup.js` **não** renderiza sugestões (só mapa de cores) — nenhuma superfície stale.
- `overlay.css` `.eb-region` não tem `max-height`/`overflow` → o display das 3 regiões + números **não é
  cortado**; estilos inline em `buildForce17HTML`/`buildVeredito` são auto-contidos (independem do CSS).

### 11.2 Evidência LIVE (payload `sugestao` capturado do `websocket.send`)
Rodando `handle_new_result` REAL (SDA17 + GameState + DB) com `SDA_BET_PAIR=force17`:
```
acao         : APOSTAR
numeros (N)  : 13 -> [3,7,8,10,11,12,13,23,28,29,30,35,36]    # união real (overlap)
centros      : [21, 30, 28]                                    # geométricos (atribuição)
regioes      : [('c2',30,'ok'), ('c3',28,'ok'), ('c1',12,'ok')]   # rotuladas c2/c3/c1
force17      : {coverage_n: 13, dir_bias: 'desfavoravel'}
c1_force     : {value: 12, forca: -7, status:'ok', geo: 21}    # ForceLast ≠ C1 geométrico
ultimo_acerto: {slot:'miss', green: False, numero: 9, direction: 'anti-horario'}
```
> **Confirma:** os números e as 3 regiões rotuladas **estão no payload que vai ao front** e são
> JSON-serializáveis. **N=13** aqui é a **união real** (sobreposição) da geometria **17# nominal** (7+5+5);
> o front mostra o N real (correto pela estratégia — não se força disjunção, que piora).

### 11.3 🐛 Bugs encontrados e CORRIGIDOS nesta auditoria

| # | Sev | Bug | Onde | Correção |
|--:|:--:|---|---|---|
| **BUG-F1** | 🔴 Alta | `updateOverlay` chamava `createOverlay()` mas o `const overlay` continuava `null` (reatribuía `retryOverlay`); a 1ª renderização (overlay ainda inexistente) lançava `TypeError` em `overlay.querySelector` e **não mostrava os 17 números** | `extension/content.js:488` | `let overlay` + **reatribui** `overlay` após `createOverlay()` |
| **BUG-F2** | 🟡 Média | Vista **minimizada**/`toggleMinimize` mostrava os centros **geométricos** (`sugestao.centros`), divergindo da expandida (force17 com C1=ForceLast) | `content.js` (status + toggle) | usa `sugestao.regioes.map(r=>r.center)` quando force17 ativo (consistência) |
| **BUG-S1** | 🟡 Média | Fallback de calibração (`should_bet=False`, timeline>0) **sobrescreve** a cobertura para N=21, mas o `_cs_meta` do force17 podia ficar **stale** → overlay com 3 regiões + `numeros=21` (incoerente) | `server/message_handler.py` (branch fallback) | zera `_cs_meta` e `last_force17_meta` no fallback |
| **BUG-D1** | 🟢 Baixa | Canal `trace`/`state_sync` (dashboard) **não** emitia `dir_bias` (só o canal `sugestao` emitia) → label de viés vazio no Glass Box | `state/game.py` `engine_overlay_fields` | adiciona `dir_bias` (derivado de `target_direction`) ao bloco force17 |

> Nenhum bug **bloqueante** no caminho normal (a aposta de 17# chega ao front). BUG-F1 era o mais relevante
> (impedia a 1ª renderização em cenário de injeção tardia do content script).

### 11.4 Fluxo recepção→retorno (auditado, sem bugs remanescentes)
`novo_resultado` → role-check (master) → dedup → `SpinInput` → `check_prediction` (resolve t-1, veredito) →
`_engine_resolve` (block_gale com hit real; force17 não dispara feedback — `freeze={}`) → `update_adaptive`
(grava no history do sentido) → `process_spin` → `analyze` (3 centros) → **`_engine_apply_selection`
(force17 = 17#)** → `_ensure_nonempty_coverage` (B1) → store/fallback → stake (block_gale + INV-3) → grava
Decision → **monta `sugestao`** (`numeros`+`regioes`+`force17`+`ultimo_acerto`) → `send` → `trace`
(dashboard). **Verificado:** `green==hit` (slot=miss só com hit=False), `cs_chosen=C1`/`freeze={}` não
dispara shadow, persistência sem poluição, INV-3 intacto, payload serializável.

### 11.5 Status "100% funcional e operante"
- **Código/fluxo:** ✅ **100% funcional** — captura live do `sugestao` com 17#/regiões/veredito-com-sentido;
  **559 passed**, 9 skipped, 1 xfailed; `content.js`/`app.js` syntax OK.
- **Front-end (overlay da Escuta):** ✅ mostra as **3 regiões rotuladas c2/c3/c1** (numerinho embaixo de
  cada centro) + os **N números** + **🟢/🔴 + sentido**; bug de 1ª renderização (BUG-F1) corrigido.
- **Produção (servidor Debian):** ✅ **GO-LIVE EXECUTADO** — PR **#14** mergeado em `main` (`7e477df`),
  **CI verde** (lint + suíte em Python 3.11/3.12/3.13). O `roleta-deploy.timer` (a cada 2 min) faz
  `git reset --hard origin/main` + `docker compose build` + `up -d` (healthcheck-gated, **auto-rollback** se
  falhar), recriando o container com `SDA_BET_PAIR=force17`. Deploy leve (build cacheado), mínima interrupção.

> **Conclusão Auditoria #3:** front-ends auditados e **corrigidos** (4 bugs); fluxo recepção→retorno
> **validado live e sem bugs remanescentes**; sistema **100% funcional** e **go-live executado** (PR #14).

### 11.6 Go-live executado (18/06) — verificação e passos do operador
**Servidor (auto-deploy via timer; verificar quando concluir, ~2–3 min após o merge):**
```bash
ssh root@187.45.181.75
docker exec roleta-cloud env | grep SDA_BET_PAIR              # → force17
curl -fsS http://localhost:8766/health                        # v4.x healthy
curl -fsS http://localhost:8766/metrics | grep force17_active # → roleta_force17_active 1
docker exec roleta-cloud sqlite3 /app/data/decisions.db \
  "SELECT id,direction,json_array_length(sda_numbers) FROM decisions ORDER BY id DESC LIMIT 5;"  # N≤17
tail -n 30 /var/log/roleta-deploy.log                          # log do pull-deploy
```
**Extensão (Escuta — roda no navegador do operador, NÃO é deployada pelo servidor):**
> ⚠️ **Recarregar a extensão** para pegar o `content.js` novo: `chrome://extensions` → **Recarregar**
> "Escuta Beat". Só então o overlay passa a renderizar as 3 regiões rotuladas + 17 números + veredito.
**Dashboard Glass Box** (`frontend/`, servido pelo container): atualiza sozinho no deploy.
**Rollback:** `SDA_BET_PAIR=c2c3` (ou `full`) no host + redeploy, ou `git revert` do commit do compose.

---

*Auditoria #3 registrada em 18/06/2026. Evidência: captura live do `sugestao` via `handle_new_result`;
suíte 559 passed. Correções: `content.js` (BUG-F1/F2), `message_handler.py` (BUG-S1), `game.py` (BUG-D1).*

---

## 12. 🔢 Diagnóstico "por que N varia" + force17-EXATO (sempre 17) — 18/06

> Pergunta do operador: *"a lógica é sempre apostar 17 números? o que está ocorrendo que essa numeração
> está variando?"*. Diagnóstico com dados reais (`data/decisions.db`) + correção opcional (default ON).

### 12.1 Causa da variação (não era bug — era a geometria)
`coverage3` (`strategies/c_selection.py`) devolve a **união de conjuntos** das 3 regiões:
```
aposta = vizinhos(C2,±3)=7  ∪  vizinhos(C3,±2)=5  ∪  vizinhos(C1=ForceLast,±2)=5   # 17 nominal
```
A roda tem 37 casas; quando os 3 centros caem **perto**, as vizinhanças **se sobrepõem** e os repetidos
contam **uma vez** → N < 17. Distribuição real observada (decisões force17 de teste):

| N | causa |
|---|---|
| **12–17** | force17 normal — varia com o **overlap** entre C2/C3/C1 (ex.: C2=10,C3=17,C1=5 → união 12; C2=0,C3=10,C1=22 → 17) |
| **21** | calibração/2ª jogada (SDA17 com 1 só centro → fallback `vizinhos(centro,10)`) |
| **0→PULAR** | 1ª jogada de cada sentido (cold-start, sem dados) |

Isso era o comportamento **validado** (`analise_400` PARTE XIV: apostar a união ~15; **mover** o C1 para
desfazer overlap **piora** — quebra o sinal balístico do ForceLast).

### 12.2 Correção: `SDA_FORCE17_EXACT` (default ON) — sempre 17
O operador pediu **17 fixos**. Solução que honra o pedido **sem mover os centros** (preserva o ForceLast):
quando o overlap reduz a união abaixo de 17, **estende as regiões para fora** adicionando os números
não-cobertos **mais próximos** de qualquer centro, até **exatamente 17** (`pad_to_n`). É **aditivo** — a
união validada permanece um subconjunto; nunca remove número validado.

| Componente | Mudança |
|---|---|
| `strategies/c_selection.py` | `pad_to_n(nums, centers, wheel, n)` + `force_select(..., target_n)` (padding p/ N exato) |
| `app_config/settings.py` | `force17_exact_enabled()` — env `SDA_FORCE17_EXACT` (default `1`) |
| `server/message_handler.py` | dispatch passa `target_n=17`; fallback de calibração vira **17** (raio 8) quando exato |
| `docker-compose.yml` | `SDA_FORCE17_EXACT=${SDA_FORCE17_EXACT:-1}` |

**Cobre todos os casos de aposta:** 3 centros (overlap→17), aquecendo (C2∪C3→17), calibração (21→17).
Único caso sem 17 = **1ª jogada por sentido** (zero dados → PULAR, INV-3). Verificação e2e via
`handle_new_result`: **18/18 decisões APOSTAR = N=17** (distribuição `{17: 18}`).

### 12.3 Trade-off e rollback
> ⚠️ **ATUALIZAÇÃO (levantamento C1, `resposta_estruturada_c1_junho.md`):** o default de `SDA_FORCE17_EXACT`
> foi **revertido para OFF (união ~15)** após confirmar no estudo (L940) que **forçar 17 PIORA o breakeven**
> (42,8%→47,2%) — contradiz a base de lucro (cobertura menor). O EXATO virou **opt-in**.

- **OFF (novo default):** **união ~15** — fiel ao estudo (breakeven 42,8%, cobertura enxuta). Cobertura varia 12–17.
- **ON (`SDA_FORCE17_EXACT=1`):** opt-in p/ "sempre 17" (consistência visual), custo breakeven +4,4pts.
- **Testes:** `TestForce17Exact` (5) + wiring exato (3); suíte **566 passed**.

> **Resumo:** a variação era a **geometria de união** (correta/validada). Atendendo ao pedido de "sempre
> 17", o force17-exato completa a cobertura para 17 estendendo as regiões (sem mover centros), reversível
> por env. A 1ª jogada de cada sentido (cold-start) permanece PULAR por falta de dados.

---

*Atualizado 18/06/2026 com force17-EXATO (`SDA_FORCE17_EXACT`, default ON). Suíte 566 passed.*
