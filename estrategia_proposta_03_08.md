# 🎯 Estratégia Proposta 03/08 — V5 "17/21 por sentido" (documento FINAL de produção)

> **Data:** 03/08/2026 · **Status:** APROVADO PARA EXECUÇÃO — aguardando comando de go-live do dono
> **Decisão executiva:** go-live **SEM fase shadow**; a validação comparativa 17×21 é **embarcada em produção** (contrafactuais pareados por giro, por sentido).
> **Origem:** proposta do dono (assinatura de forças + regiões) + 3 pareceres paralelos (debatedor PRÓ · debatedor CONTRA · auditor de arquitetura), consolidados por esta sessão.
> **Metodologia:** `evolução_24_junho.md` (1 sprint = 1 worktree = 1 PR) · Invioláveis do repo respeitados integralmente.

---

## 0. Sumário executivo — o que muda em 1 parágrafo

A aposta de produção passa de `force17` (união ~15#) para o modo novo **`v5_1721`**: **3 regiões disjuntas** compostas *assinatura-primeiro* por sentido — **R1** = cluster de força de gravidade-7 de máxima cobertura (o braço que concentrou 61% dos hits em 03/08, hoje subordinado como C2 residual, promovido a primário), **R2** = 2º cluster condicionado à tendência acelerando/freando (Theil–Sen, só o sinal), **R3** = região mais fria **do mesmo sentido** (corrige violação real encontrada: o C3 atual mistura cw+ccw). A saída é **SEMPRE 17 números distintos (7+5+5) OU 21 números distintos (7+7+7)** — nunca outro N —, escolhida no momento da aposta por um **seletor por sentido**: **após miss → 21; após hit → 17** (regra do dono, enquadrada como cobertura adaptativa tipo-ACI). A cada giro o sistema grava os contrafactuais `would_hit_17`/`would_hit_21` no `decision_dna` existente — **a arquitetura de povoamento de dados permanece exatamente a mesma** (zero migração, zero coluna nova). Rollback = 1 linha de compose (`SDA_BET_PAIR=force17`), ~3 min.

---

## 1. A regra do jogo (invariantes da estratégia nova)

| # | Invariante | Mecanismo |
|---|---|---|
| 1 | Saída **sempre** 17 ou 21 números **distintos** | União exata garantida por gap circular uniforme ≥7 entre centros + raios por modo; `len(set(numbers)) == coverage_n` validado por fuzz 25k no DoD |
| 2 | **Conjuntos aninhados**: `C17 ⊂ C21` na mesma jogada | Centros calculados UMA vez (independentes do modo); só os raios mudam (R2/R3: 3→2). Sem isso o contrafactual pareado seria inválido (exigência do parecer estatístico) |
| 3 | **Isolamento estrito por sentido** | Forças de R1/R2 e resultados de R3 vêm exclusivamente de `cw_history`/`ccw_history` do sentido corrente. Estado do seletor: um por sentido |
| 4 | **INV-3** intocado | Indicação `APOSTAR` sempre emitida; warmup emite tríade-prior; vetos continuam só como `min()` no stake |
| 5 | **Validação no momento da aposta** | Toda decisão V5 registra modo escolhido + coberturas 17 E 21 congeladas ANTES do resultado; pós-resultado grava `would_hit_17/21` — comparação pareada, mesma jogada, sem ruído de amostragem |

---

## 2. Composer — especificação paramétrica CRAVADA (parecer PRÓ, consolidado)

### 2.1 Constantes (→ `strategies/regions_v5.py`, padrão `REGIONS_V4_*`)

| Constante | Valor | Justificativa |
|---|---:|---|
| `V5_R1_WINDOW` | **8** | Dobra a janela C2 atual (4): expõe ≥2 modos de força sem cruzar troca de dealer |
| `V5_GRAVITY` | **7** | Poço ±3 ≡ raio da região; valor já sintonizado (`REGIONS_V4_GRAVITY`) |
| `V5_TS_WINDOW` | **5** | Janela Theil–Sen mínima robusta para inclinação |
| `V5_TS_DEADBAND` | **1.0** casa/giro | ≈1σ do ruído do slope (M=5, forças inteiras); endurecido de 0,5→1,0 por ser go-live sem shadow |
| `V5_R2_CLAMP` | **8** | R2 fica no mesmo arco de assinatura de R1 (±8); além disso é regime do R3 |
| `V5_R3_WINDOW` | **12** | 5 é esparso demais em 37 casas; 12 discrimina frio sem cruzar dealer — **por sentido** |
| `V5_R3_PAINT_RADIUS` | **3** | Escala de pintura do heatmap triangular = escala das regiões |
| `V5_DISJOINT_GAP` | **7** (uniforme, nos 2 modos) | = 2·3+1; centros idênticos nos 2 modos ⇒ nesting `C17⊂C21` garantido; reusa a lógica testada de `_regions_disjoint` |
| `V5_RADII_21` / `V5_RADII_17` | **(3,3,3)** / **(3,2,2)** | 7+7+7=21 · 7+5+5=17; **R1 nunca encolhe** (braço de maior sinal); R2/R3 cedem 2 números cada no modo-17 |
| `V5_WARMUP_MIN_RESULTS` | **3** por sentido | 1ª composição plena com ≥2 forças; abaixo disso → tríade-prior |
| `V5_PRIOR_OFFSET` | **10** | Âncora do warmup (reusa `BAYESIAN_DEFAULT` existente) |
| `V5_WARMUP_TRIAD` | **{0, +12, +24}** | 3 centros equiespaçados (gaps 12/12/13 ≥7) → disjuntos sempre, INV-3 garantido sem dado algum |
| Tie-break R1/R2 | cobertura↓ → mais recente → \|f\|↑ → idx↑ | Determinístico e reprodutível (anti look-ahead B5) |
| Tie-break R3 | menor calor → mais distante de {R1,R2} → menor idx | Determinístico, robusto a empates |

### 2.2 Algoritmo `compose_v5(direction, mode)` (funções puras, módulo novo)

```
1. WARMUP  — se resultados(sentido) < 3: tríade-prior ancorada em apply_force(last, 10)
             com offsets {0,+12,+24}; raios conforme mode. Retorna 17 ou 21 distintos.
2. R1      — scan de cobertura gravidade-7 sobre as últimas 8 forças DO SENTIDO
             (SEM o filtro residual do C1 — inversão de prioridade); tie-break acima.
             R1 NUNCA se move na disjunção.
3. R2      — slope = theil_sen(últimas 5 forças); resíduo = forças fora do poço-7 de R1.
             • |slope| > 1.0  → 2º cluster gravidade-7 no LADO do sinal do slope (resíduo)
             • |slope| ≤ 1.0  → RAMO DEFAULT: 2º cluster mais denso do resíduo (puro)
             • resíduo vazio  → sintetiza R1_force ± 7 (lado = sign(slope), senão +)
             clamp circular a ±8 de R1; empurra via nearest_non_overlapping (gap 7).
4. R3      — heatmap triangular (raio de pintura 3) sobre os últimos 12 resultados
             DO MESMO SENTIDO; centro mais frio disjunto de {R1,R2} (gap 7); cede sempre.
5. SAÍDA   — raios (3,3,3) se mode=21, (3,2,2) se mode=17.
             Garantia: len(set(numbers)) == mode; C17 ⊂ C21 (mesmos centros).
```

> **Correção embutida (débito real de produção):** o C3 do V4 vigente consome `game_state.recent_results` — deque **global** que mistura cw+ccw (`state/game.py` l.421-423/465 → `message_handler.py` l.842-848 → `sda17.py` l.571). O R3 do V5 usa exclusivamente o buffer do sentido corrente.

---

## 3. Seletor 17↔21 — especificação CRAVADA (regra do dono + guardrails do parecer estatístico)

### 3.1 Regra e estado (por sentido, dentro do `adaptive_state`)

| Constante | Valor | Justificativa |
|---|---:|---|
| `V5_MODE_DEFAULT` | **17** | Estado inicial/pós-reset: sem miss ainda, a regra do dono não dispara; menor exposição sem informação |
| Transição MISS | **→ 21** e permanece 21 enquanto vier miss | Regra literal do dono: "após miss, a jogada de 21 tem mais força" — memoryless, dirigida pelo último resultado resolvido do sentido |
| Transição HIT | **→ 17** | Pós-hit concentra (breakeven 47,2%) |
| `V5_MAX_21_PER_SESSION_DIR` | **5** | Teto de jogadas-21 por sessão×sentido; ao atingir → `LOCK17` até reset de dealer. Dano incremental máximo vs always-17 = 5×4u = **20u/sessão/sentido** |
| Stop-loss sessão (−30u, existente) | força **17** (`LOCK17`) | Integração com CUT/stop vigentes: veto nunca vira cobertura mais cara |
| Flip | usa **hit REAL da cobertura apostada** | Mesma disciplina ISO obrig. #3 do block_gale (hit real, não proxy de distância); giro fantasma/fase incerta não flipa |
| Round-trip | persistido em `state.json` (adaptive_state v1.9) | Restart retoma o modo; reset de dealer → 17/17 |

> Registro de divergência (para o ADENDO): o parecer estatístico recomendou cap de **1** jogada-21 consecutiva (alternância pós-miss; perde −114u vs −122u da regra literal em streak de 6 misses). Decisão do estruturador: **manter a regra literal do dono** — o experimento mede a hipótese real, não uma diluição — com o teto de sessão (5) e o fail-fast (§5.3) como limitadores de dano.

### 3.2 Enquadramento estatístico (por que a regra é defensável)

A regra é o limite binário de um **ACI de 2 níveis** (Adaptive Conformal Inference, Gibbs & Candès 2021): alargar o conjunto de predição quando o erro recente sobe é legítimo para controle de cobertura. **Limitação honesta:** ACI controla cobertura, não EV — a economia é julgada pelos limiares do §5.

---

## 4. Matemática honesta (breakevens e limiar de superioridade)

- Payout 35:1, 1u/número: breakeven **17# = 47,22%** · **21# = 58,33%** · união atual ~15 = 42,8%.
- **Limiar exato da escalada** (mesma jogada, conjuntos aninhados): sendo `r = P(resultado ∈ C21\C17 | pós-miss)` a massa capturada pelos 4 números extras, o P&L diferencial é `E[Δ] = 36r − 4` ⇒ **escalar só é superior a ficar no 17 se `r > 1/9 ≈ 11,11pp`**.
- Equivalências: com p17 pós-miss = 38,3%, o 21 pós-miss precisa de ≥ **49,41%** para bater o 17; ≥ **58,33%** para não perder isolado.
- EV comparativo (Monte Carlo 600k trajetórias, 200 giros, flat cap=1):

| Cenário | always-17 | always-21 | seletor |
|---|---:|---:|---:|
| i.i.d. uniforme | −92u | −114u | −99u |
| hit proporcional atual (38,3%) | −642u | −794u | −700u |
| hipótese do dono (p21\|miss = 58,33%) | −642u | −417u | **−397u** |

> Leitura: **se** a hipótese do dono se confirmar nos 4 números extras, o seletor é a melhor política das três. Se não, perde ~9% a mais que always-17 — dano limitado pelos guardrails. Exposição média do seletor ≈ 18,5u/giro (+23,5% na jogada-21 vs 17u; +~40% vs união ~15 atual).

---

## 5. Validação embarcada em produção (substitui o shadow)

### 5.1 Contrafactuais por giro (arquitetura de dados INALTERADA)

A cada decisão V5, o `pending_prediction` congela `v5_cov17`, `v5_cov21`, `v5_mode` (sobrevive a restart — já persiste no state.json). Pós-resultado, 3 chamadas ao **`dna_log_feature` existente** (nenhuma mudança de schema):

| feature_name | raw | bucket | hit |
|---|---|---|---|
| `v5_would_hit_17` | 0/1 | "hit"/"miss" | resultado ∈ cov17 |
| `v5_would_hit_21` | 0/1 | "hit"/"miss" | resultado ∈ cov21 |
| `v5_coverage_mode` | 17/21 | "17"/"21" | hit real da aposta |

Derivados analíticos (via `dna_summary`/SQL, por sentido): `ring_only = would_hit_21 ∧ ¬would_hit_17`; jogadas-21 ≡ contexto pós-miss; Δ P&L pareado = `36·ring_only − 4` por jogada escalada.

### 5.2 Prova ponto-a-ponto: povoamento de dados permanece o mesmo

| Superfície | Mudança | Evidência |
|---|---|---|
| `decisions` (SQLite, fonte da verdade) | **nenhuma coluna** | `sda_numbers`/`sda_centers`/`sda_regions` são JSON com N variável desde sempre (produção já gravou N=12/14/17/21) |
| Migrações Alembic | **zero** | nada a migrar; sem interseção com lock de schema |
| `decision_dna` | só **rows** novas (3 feature_names) | `dna_log_feature` é genérico por design |
| `dna_realize_lifts` / `SDA_DNA_REALIZE` | nenhuma | realize é agnóstico a feature_name, processa da ponta |
| PG réplica / outbox / vetores / `session_id` | nenhuma | nenhum campo novo a mapear |
| `state.json` | chaves aditivas em `adaptive_state` + `pending` | `load()` usa `data.get(chave, default)` em tudo; código antigo ignora chave extra (tolerância bidirecional verificada) |
| Payloads WS | aditivos no meta existente | clientes antigos ignoram campos novos |

### 5.3 Critérios de desligamento pré-registrados (constam do ADENDO do go-live; avaliação por sentido)

| Checkpoint (jogadas-21/sentido) | Critério | Ação |
|---:|---|---|
| **50** (fail-fast) | `ring_only ≤ 5` (lift ≤10% < 11,11%) **ou** `hit21 ≤ 29` (≤58%) **ou** Δ acumulado vs always-17 ≤ **−100u** | `SDA_BET_PAIR=force17` (rollback 1 linha, ~3min) |
| **150** (referência `MIN_N_PROMOTE`) | Δ pareado com IC Newcombe **não** excluindo 11,1pp | rollback idem |
| **600** (confirmação) | manter só se `ring_only ≥ 85` (≥14,17%) **e** `hit21 ≥ 378` (≥63,0%) | decisão definitiva |

---

## 6. Mapa de mudança arquivo-por-arquivo (o quê e por quê)

> Estratégia de encaixe: **novo valor do enum `SDA_BET_PAIR` (`v5_1721`)** — não flag paralela. O dispatch por modo já existe (`_engine_apply_selection`, 5 modos); o V4 continua gerando os 21 centros upstream (testes V4 intactos, rollback vivo); rollback = trocar 1 env.

| Arquivo | Mudança | Por quê |
|---|---|---|
| **`strategies/regions_v5.py`** (NOVO, ~200-250 l., funções puras) | `theil_sen_sign()`, `gravity_scan()` (scan gravidade-7 ranqueado sobre TODAS as forças, sem filtro residual), `cold_center()` (frieza POR SENTIDO), `nearest_non_overlapping` reusado com gap 7, `compose_v5()` | Não inchar `message_handler.py` (Gap D.1/ISO #8) nem `sda17.py` (1686 l.); testável isolado; constantes §2.1 |
| **`strategies/sda17.py`** | + `_v5_coverage_mode={"cw":17,"ccw":17}`; + `note_coverage_outcome(direction, hit)` (miss→21/hit→17); + `v5_coverage_mode(direction)`; `get_adaptive_state()`/`load_adaptive_state()` com a chave nova validada (∈{17,21}, default 17; versão 1.8→1.9); `reset_adaptive()` → 17/17 | Estado do seletor com round-trip **automático** (save/load/reset já sincronizam adaptive_state — zero diff em `game.py`) |
| **`server/message_handler.py`** (4 pontos cirúrgicos) | ① ramo `v5_1721` em `_engine_apply_selection`: forças+recentes DO SENTIDO (mesma fonte do force17), `compose_v5` 2× (17 e 21), aplica a do modo corrente como `final_numbers`+`_cs_meta` (labels r1/r2/r3) · ② `pending` += `v5_cov17/v5_cov21/v5_mode` · ③ pós-resultado: 3 `dna_log_feature` (§5.1) · ④ flip `note_coverage_outcome` com hit REAL, antes do snapshot do adaptive_state (guardado por `pending.v5_mode`) | Wiring mínimo no caminho já existente; contrafactuais congelados antes do resultado |
| `server/message_handler.py` (fallback calibração) | incluir `v5_1721` na condição de **raio 8 (17#)** | Sem isso, a 1ª oportunidade por sentido cairia no else de raio 10 (21#) — incoerente com default 17 |
| **`app_config/settings.py`** | `bet_pair_mode()`: adicionar `"v5_1721"` ao conjunto válido + docstring | Leitura por-chamada preservada (ISO #1); parâmetros do composer são constantes de módulo (padrão `REGIONS_V4_*`) |
| **`docker-compose.yml`** (só no sprint de go-live) | `SDA_BET_PAIR=${SDA_BET_PAIR:-v5_1721}` + comentário com breakevens (17→47,2% / 21→58,3%) e rollback (`force17`) | Padrão idêntico ao go-live do force17; compose versionado é a fonte (ISO #4) |
| **`frontend/index.html`** (2 linhas) | rótulo "Região (17#):" → "Região:"; `(17#)` estático → dinâmico | `app.js` já sobrescreve com `(${coverage_n}#)` — zero mudança de JS obrigatória |
| **`tests/`** | novos: fuzz 25k (N exato ∈{17,21}, disjunção, nesting, isolamento por sentido), seletor (miss/hit/cap/lock/round-trip/reset), fallback 17#, DNA features | DoD §7 |
| **`Manutenabilidade_iso.md`** | ADENDO por sprint (formato §8) | Exigência de ciclo |

**O que explicitamente NÃO muda:** `state/game.py` (save/load/reset genéricos), `database/sqlite_repo.py`, migrações, `state/block_gale.py` (N já é parâmetro: `stake = unidade × N` flui com 17/21 sem diff), `strategies/c_selection.py` (force17 intacto = rollback vivo), `_ensure_nonempty_coverage` (agnóstica), extensão Chrome, PG/outbox/vetores, `analyze()`/V4 upstream.

---

## 7. Sprints (1 sprint = 1 worktree = 1 PR · briefs pelo `_BRIEF_TEMPLATE.md`)

### SPR-V5A — Motor V5 17/21 + seletor pós-miss + contrafactuais (esforço M-L, ~70%)
- **Locks:** BLK-G, `strategies/`, `server/message_handler.py`, `app_config/settings.py`, `frontend/index.html`, `tests/`. Sem lock de schema/alembic.
- **Conteúdo:** tudo do §6 exceto a compose. Modo completo porém **inerte** (compose segue `force17`).
- **DoD verificável:**
  1. Suíte completa verde com default **e** com `SDA_BET_PAIR=v5_1721` forçado;
  2. Fuzz 25k: `len(set(numbers)) ∈ {17,21}` exato · 3 regiões disjuntas (gap 7) · `C17 ⊂ C21` · isolamento por sentido (históricos cw≠ccw injetados);
  3. Seletor: miss→21/hit→17 por sentido independente · cap 5 → LOCK17 · round-trip save→load · reset dealer → 17/17;
  4. `v5_would_hit_17/21` + `v5_coverage_mode` no `decision_dna` com `direction` preenchido, visíveis no `dna_summary()`;
  5. Fallback de calibração em v5 = 17# (regressão nova);
  6. `python tools/lint_silent_except.py` limpo (ou `--update` justificado);
  7. ADENDO ISO **antes** do PR.
- **Testes existentes:** `test_regions_v4_13_06.py` **não quebra** (V4 upstream intacto); `test_c_selection.py` **não quebra** (force17 intocado); `test_wiring_c_gale.py` +1 entrada no enum se houver tabela fechada; `test_ws_overlay_contract.py` +1 caso aditivo.

### SPR-V5B — Go-live na compose + verificação de produção (esforço S; depende de V5A merged/deployado)
- **Locks:** `docker-compose.yml`, `Manutenabilidade_iso.md`.
- **Conteúdo:** troca do default `SDA_BET_PAIR` → `v5_1721` + comentários de rollback/breakeven; ADENDO com evidência de produção + critérios §5.3 registrados.
- **DoD (sem ssh):** em ≤~4min o dashboard mostra card "3 Regiões" com `(17#)`; após 1º miss de um sentido → `(21#)` na jogada seguinte DESSE sentido; hit → volta `(17#)`; stake 17u/21u (G1); `acao=APOSTAR` contínuo.

### SPR-V5C — Replay retroativo 41k decisões (OPCIONAL, paralelo, S-M; recomendado: executar em paralelo ao V5A)
- Adaptar `tools/backtest_from_db.py` (que hoje é agregação pós-hoc, NÃO replay) para pontuar `would_hit_17/21` retroativamente sobre `spin_force`/`result_actual` por `spin_direction`/`session_id`. Antecipa o veredicto econômico sem esperar as ~150 jogadas-21 de produção. **Não bloqueia o go-live.**

---

## 12. Auditoria UX/frontend + registro de implantação (04/08 — V5A+V5B colapsados, GO-LIVE)

> Ordem do dono (04/08): 17 usa os MESMOS centros do 21 (só R2/R3 encolhem 7→5 — já era o §2.2);
> auditar a organização frontend/UX contra os contratos desta proposta nas 4 superfícies; implantar
> tudo live num único ciclo. SPR-V5A e V5B foram executados juntos nesta branch (1 PR).

### 12.1 Superfícies auditadas e veredito

| Superfície | Arquivo | Contrato consumido | Veredito pré-fix |
|---|---|---|---|
| Extensão — expandida | `extension/content.js` `buildForce17HTML` | `sugestao.regioes[{label,center,radius,status}]` + `force17.{coverage_n,dir_bias}` | ✅ payload-driven (nº de regiões e cobertura derivam do payload) — só a classe CSS era hardcoded c1/c2/c3 (gap 2) |
| Extensão — minimizada | `content.js` heartbeat `state_sync` | `centrosFromSugestao(lastSugestao)` → fallback | ⚠️ gap 3: cold-start caía direto em `pending_prediction.centers` ([C1,C2,C3] V4 crus) |
| Extensão — botão nativo (popup) | `popup.html/js` | resumo (não desenha regiões) | ✅ sem mudança necessária |
| Glass Box / dashboard | `frontend/app.js` `updateForce17` + `frontend/index.html` | `force17` block do overlay (`engine_overlay_fields`) | ⚠️ gap 1: cores por label fixas c1/c2/c3; rótulo estático "(17#)" mentiria no modo 21 |

**Contrato de saída (decisão de arquitetura):** o meta V5 REUSA o bloco `force17` do overlay
(`regioes`/`c1_force`/`coverage_n`/`numeros`) com labels novos `r1/r2/r3` + campo aditivo
`v5_mode` (17|21). Nenhum canal novo, nenhum campo removido → force17 clássico byte-idêntico
(coberto por teste `test_force17_classico_sem_v5_mode`).

### 12.2 Fixes aplicados (3 gaps → fechados)

1. **`frontend/app.js`**: paleta por mapa `{c1,c2,c3,r1,r2,r3}` com fallback `#e0e0e0` — r1=verde `#06d6a0` (primário), r2=azul `#118ab2` (tendência), r3=amarelo `#ffd166` (fria).
2. **`extension/content.js`**: classe dinâmica `eb-rc-${label}`; badge `V5·17#/21#` no header quando `force17.v5_mode` presente; cold-start do minimizado prefere `data.regioes` (estratégia ATIVA) antes de `pending_prediction.centers`.
3. **`frontend/index.html`**: "Região (17#):"→"Região:"; `#f17-cov` inicia `(--)` (populado por `coverage_n` real: 17 ou 21).
4. **`extension/manifest.json`**: **3.7.0 → 3.8.0** (changelog V5 no description). ⚠️ Extensão é unpacked local — **o operador precisa recarregar em `chrome://extensions`** (não vai pelo deploy Debian).

Warmup: o composer marca `status:"aquecendo"` nas 3 regiões → as vistas já exibem ⏳ sem código novo.

### 12.3 O que foi implantado (diff real desta branch)

| Camada | Arquivo | Mudança |
|---|---|---|
| Motor | `strategies/regions_v5.py` **(novo)** | composer puro §2 completo: gravity_scan, Theil–Sen, cold_center por sentido, disjunção gap 7, nesting C17⊂C21, warmup tríade INV-3 |
| Seletor | `strategies/sda17.py` | `_v5_mode`/`_v5_count21` + 3 métodos + adaptive_state **v1.9** (get/load validado/reset) |
| Enum | `app_config/settings.py` | `bet_pair_mode()` aceita `v5_1721` |
| Wiring | `server/message_handler.py` | ramo v5 auto-contido em `_engine_apply_selection` (early-return, centers V4 preservados); stash stop-loss→LOCK17; inject `v5_mode/cov17/cov21` + contagem de emissão real; flip pós-hit-real; 3 features DNA (`v5_would_hit_17/21`, `v5_coverage_mode`); fallback calibração raio 8; passthrough `v5_mode` no overlay |
| Overlay | `state/game.py` | passthrough `v5_mode` (aditivo) em `engine_overlay_fields` |
| Go-live | `docker-compose.yml` | default `SDA_BET_PAIR=v5_1721` + breakevens/rollback no comentário |
| UI | 4 arquivos §12.2 | gaps 1–3 + manifest 3.8.0 |
| Testes | `tests/test_regions_v5.py` **(novo)** | 31 testes (fuzz 5k, Theil–Sen, seletor, enum, wiring); pins atualizados (`test_dir13_lock_total`, `test_quick_wins`); suíte **764 passed** |
| Docs | `Manutenabilidade_iso.md` | ADENDO 04/08 (A–E) |

**Arquitetura de povoamento de dados: INALTERADA** (zero migração; DNA/outbox/PG byte-idênticos — invariante da ordem do dono verificado: `database/`, `workers/`, `alembic/` sem diff).

### 12.4 Validação econômica no momento da aposta (recap §5)

Os contrafactuais `v5_would_hit_17/21` são congelados no pending ANTES do giro e realizados com o
número real — a comparação 17×21 é **pareada por giro** (mesmos centros, mesma jogada), exatamente
a validação que o dono pediu ("após uma jogada miss tenho certeza que a jogada com 21 tem mais
força"): se os 4 números extras do modo-21 capturarem >11,1pp de hit-rate nas jogadas pós-miss,
o seletor está pagando; senão, desligamento §5.3 (`SDA_BET_PAIR=force17`, ~3 min, sem revert de código).

---

## 8. Conformidade ISO (o que cada sprint DEVE cumprir — `Manutenabilidade_iso.md`)

Lista canônica = Obrigações do ADENDO 17/06 (l.235-258) + deltas 18/06 (l.460-471) + template (`sprints/_BRIEF_TEMPLATE.md` l.37-70):

1. Flags **por-chamada**, nunca cachear (`bet_pair_mode()` lê env a cada decisão);
2. **INV-3** inviolável (indicação sempre; moduladores só `min()` no stake);
3. **Hit REAL**, não proxy de distância (vale para block_gale E para o flip do seletor);
4. Rollback via **compose versionado** (deploy faz `git reset --hard origin/main`; sem `.env` no host);
5. `GALE_CAP` permanece **1** no go-live;
6. Campo de motor novo → round-trip **`save()`+`load()`+`reset_session()`** (atendido via adaptive_state + `reset_adaptive`);
7. Novo `except` defensivo → `tools/lint_silent_except.py --update`;
8. Não inchar `message_handler.py` (composer vive em `strategies/regions_v5.py`);
9. Overlay **aditivo** (nunca remover/renomear chave de payload);
10. **ADENDO obrigatório** no formato dos ciclos: A. capacidades novas → B. bugs/auditoria → C. impacto ISO por característica → D. scorecard delta → E. obrigações/rollback + evidência de testes (contagem da suíte) e de produção;
11. Closeout do template: validação colada no Log → ADENDO antes do PR → code-review pós-implantação → commit com trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` → push + **PR sem merge** pelo executor → `graphify update .` local sem commitar `graphify-out/`.

---

## 9. Go-live no servidor Debian (mecânica verificada; ZERO ação manual no host)

**Mecanismo:** `roleta-deploy.timer` (a cada ~2min) → `roleta-deploy-pull.sh`: fetch → `git reset --hard origin/main` → `docker compose build` → `alembic upgrade head` → `up -d` → healthcheck 3×5s em `:8766/health` → **rollback automático para `last_good`** se build/migração/health falharem → sync `frontend/` → nginx reload. Push→prod ≈ **3-4min**.

**Sequência:**
1. **Merge PR SPR-V5A** → deploy automático **inócuo** (modo não referenciado na compose). Verificação: dashboard `https://roleta.xma-ia.com` pulsando, força17 normal, `APOSTAR` contínuo.
2. Observar ≥1 ciclo de operação (estabilidade do código novo dormante).
3. **Merge PR SPR-V5B** (compose → `v5_1721`) → `up -d` recria o container com o env novo (~3-4min).
4. Verificação (sem ssh, dashboard): `(17#)` → miss → `(21#)` no mesmo sentido → hit → `(17#)`; stake 17u/21u; INV-3 vivo.
5. **Rollbacks:** rápido = PR de 1 linha (`force17`, ~3min; estado `v5_coverage_mode` fica dormante e inócuo) · estrutural = `git revert` dos PRs (state.json tolerante nos 2 sentidos temporais: `load()` usa `.get(default)`; código antigo ignora chave extra) · automático = script restaura `last_good` se o container não subir saudável.

**Nota:** `:8766` (health/metrics) não é público — a garantia vem do healthcheck+rollback autônomo do deploy + Docker healthcheck + dashboard como prova viva (mesmo regime de todos os go-lives anteriores).

---

## 10. Riscos residuais e controles (go-live sem shadow)

| # | Risco | Controle embarcado |
|---|---|---|
| 1 | **Econômico**: breakeven 21#=58,3% vs hit histórico 38-47%; tese pós-miss não validada; teses análogas já foram revertidas (voto 17/06; exato-17 18/06) | Contrafactuais pareados desde o giro 1; **desligamento pré-registrado** (§5.3: checkpoints 50/150/600, limiar 11,1pp Newcombe); rollback 1 linha ~3min |
| 2 | Exposição +23,5% na jogada-21 (21u vs 17u; +~40% vs união ~15) | Flat `GALE_CAP=1` + solvency-guard + stop-loss −30u → LOCK17 + teto 5 jogadas-21/sessão/sentido (dano máx. incremental 20u) |
| 3 | Bug de geometria direto em produção | Fuzz 25k no DoD (N exato, disjunção, nesting, isolamento); `_ensure_nonempty_coverage`; INV-3 estrutural; rollback automático do deploy |
| 4 | Cold-start pós-reset de dealer | Tríade-prior determinística (INV-3); modo volta a 17; fallback calibração 17# |
| 5 | Flip com fase incerta/giro fantasma | Flip só com hit REAL do pending resolvido; dedup/reconciliação de fase ortogonais e já ativos |
| 6 | Observabilidade sem ssh | Dashboard mostra N/hit/stake em tempo real; auditoria dos contrafactuais = obrigação do ADENDO V5B (ciclo seguinte consulta `decision_dna` contra §5.3) |

---

## 11. Decisões cravadas (encerrando os pontos abertos dos pareceres)

| # | Ponto | Decisão |
|---|---|---|
| 1 | Janelas/parâmetros do composer | W=8 · Theil–Sen M=5 · δ=1,0 · clamp ±8 · K frio=12 · pintura 3 (§2.1) |
| 2 | R2: 2º pico global ou excluindo R1? | **Excluindo o poço de R1** (resíduo) — separação semântica antes da geométrica |
| 3 | Nome do modo / labels | `v5_1721` · labels `r1/r2/r3` no meta existente |
| 4 | Critério de desligamento | Aceito e pré-registrado (§5.3) — consta do ADENDO do V5B |
| 5 | SPR-V5C | Executar **em paralelo** (não bloqueante) |
| 6 | Modo no boundary/restart | **Persistido** (round-trip completo); reset de dealer → 17/17 |
| 7 | Cap de 21 consecutivos | Regra **literal** do dono (permanece 21 enquanto miss), limitada pelo teto de sessão (5) — divergência do parecer estatístico registrada em §3.1 |
| 8 | Default/warmup | **17** (regra do dono só dispara após miss; menor exposição sem informação) |

---

> **Pronto para execução.** Próximo comando do dono dispara: abertura dos briefs SPR-V5A/V5B (+V5C paralelo) no `sprints/BOARD.md` via Diretor e execução do SPR-V5A em worktree próprio. Nenhuma linha de código de produção foi alterada por este documento.

---

## 13. V5.1 "assinatura-4" (05/08 — spec exata do operador, flag `SDA_V5_SIG4`)

Revisão da semântica dos 3 centros após operação real do go-live 04/08. Geometria, seletor 17↔21,
flip pós-miss, LOCK17 e contrafactuais permanecem intactos — muda SÓ como R1/R2/R3 são escolhidos:

| Pergunta do operador | Centro | Implementação (`strategies/regions_v5.py`, `spec4=True`) |
|---|---|---|
| "Qual a força-assinatura padrão de gravidade 7 que cobre o maior cluster das últimas forças?" | **R1** | cluster gravidade-7 de máxima cobertura nas últimas **4** forças do sentido-alvo (era 8) |
| "O sistema está acelerando ou freando? Qual a 2ª força de gravidade 7 com maior chance dentro da variação?" | **R2** | **projeção do próprio R1**: `r1_force + clamp(round(slope Theil–Sen janela 4), ±8)` — acelerando → região adiante; freando → atrás; neutro → disjunção empurra p/ +7 |
| "Qual região foi menos visitada?" | **R3** | região **menos visitada** da divisão FIXA da roda em 6 regiões (5×6 + 1×7, ordem física a partir do zero), placar `region6_counts` contando TODOS os giros dos DOIS sentidos + histórico |

- **Isolamento por sentido (INV-1):** R1/R2 usam apenas forças do sentido da PRÓXIMA jogada;
  R3 usa ambos os sentidos (regra explícita do dono para a região fria).
- **Ordem e não-sobreposição:** população sempre R1 → R2 → R3; sobreposição resolve para a região
  disjunta mais próxima da indicada (R3 usa snap entre os 6 centros fixos idx 3/9/15/21/27/33).
- **Badge 17/21 (ext 3.9.0):** círculo verde brilhante `#39ff14` com o modo do seletor junto aos
  3 centros nas 3 vistas (expandida/minimizada/Glass Box) — o operador sabe na hora se aposta 17 ou 21.
- **Broadcast da sugestão (`SDA_SUGESTAO_BROADCAST`):** a msg `sugestao` por-giro agora chega a
  viewers/Glass Box (antes só o MASTER a recebia — era o "sugestão não aparece em toda rodada").
- **Rollback:** `SDA_V5_SIG4=0` volta o composer ao §2 byte-idêntico; `SDA_SUGESTAO_BROADCAST=0`
  volta o transporte master-only. Ambos por-chamada, sem redeploy de imagem (só restart).
- Detalhes de auditoria/regressão: ADENDO 05/08 em `Manutenabilidade_iso.md`.
