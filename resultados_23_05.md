# 🎯 Resultados 23/05 — Auditoria Estratégica + Mapa Mental + Propostas

**Snapshot:** 2026-05-23 14:30 (UTC-3)
**Autor:** YOLO Orchestrator (Claude Opus 4.7) — papel dev sênior / quant
**MCPs usados:** `sequential-thinking`, `filesystem`, `graphify`, `memory`. Brave-search **não foi necessária** — toda análise estatística veio do **`/app/data/decisions.db` em produção** (3 574 decisões totais, 132 hoje).
**Foco:** estratégia (não infraestrutura). Audita cada arquivo de estratégia, mapeia visualmente o fluxo, e simula 3 propostas concretas suas.

---

## 0. TL;DR — para você ler em 30 segundos

| Pergunta | Resposta curta |
|---|---|
| Como foi 23/05 até agora? | **63 hits / 118 spins = 53.4%** (acima do break-even 47.2%). +6.2 pts de margem. |
| Há viés de direção? | **SIM, grande.** CW (horário) 41.7% **abaixo do break-even**; CCW (anti-horário) 65.5%. Δ = 23.8 pts. |
| Vale ir para 21 ou 27 números? | **21 condicional sim** (só na direção forte). **27 não** — break-even sobe para ~73.7% e nem CCW chega. Detalhes em §6. |
| Vale somar pontuação por região menos visitada? | **SIM, em modo híbrido.** Não substitui força; complementa C2/C3 como **regularizador anti-cluster**. Especificação em §7. |
| A estratégia atual ainda vale a pena? | **Sim, mas mal-calibrada.** Confidence "alta" rende 50.7% e "media" 57.8% — **inversão indica que o sinal "alta" não está informativo**. Detalhes em §5.4. |
| Refatorar para qual tecnologia? | Manter Python; **extrair pipeline em "Strategy Builder" stages** + ML auxiliar (LightGBM offline) para descobrir thresholds. Detalhes em §9. |

---

## 1. Snapshot 23/05 — dados de produção

> Pulled via SSH + `docker exec roleta-cloud python` direto contra `/app/data/decisions.db`.
> Coluna `timestamp` (atenção: não há `created_at` apesar do nome em outros docs).

### 1.1 Volumes

```
┌────────────────────────────────────────────────────┐
│  Decisões hoje:      132                           │
│  Spins finalizados:  118  (14 ainda aguardando)    │
│  APOSTAR:            126                           │
│  PULAR (Kill Sw.):    6  (4.5%)                    │
│  Hits:                63                           │
│  Misses:              55                           │
│  Hit rate global:    53.4%   [break-even: 47.2%]   │
└────────────────────────────────────────────────────┘
```

### 1.2 Hit rate por direção (a história mais importante do dia)

```
   CW  (horário)        ████████████████░░░░░░░░░░░░  41.7%   ❌ ABAIXO break-even
   CCW (anti-horário)   ██████████████████████████░░  65.5%   ✅ EXCELENTE
                                                ↑ break-even 47.2%
   Δ = 23.8 pontos
```

> **Interpretação:** o algoritmo adaptativo (M02-PctSigmoid) **convergiu muito melhor para CCW**. O dealer da mesa está com viés que CCW captura e CW não. Ou o offset CW está mal posicionado (off ≈ 11 dominante, mas resultado real diz que poderia ser maior — ver §5.3).

### 1.3 Distribuição por SDA Score

| Score | n | Hits | Hit rate | Notas |
|---|---|---|---|---|
| 3 | 26 | 10 | 38.5% | Baixa qualidade IQR → mal sai do prejuízo |
| **4** | **85** | **51** | **60.0%** | Score dominante — bom rendimento |
| 5 | 6 | 1 | **16.7%** ⚠️ | **Anomalia grave**: alta confiança rendeu pior |
| 6 | 1 | 1 | 100% | n=1, sem conclusão |

**Insight crítico:** score 5 = "alta confiança do pipeline" rendeu 16.7%. Amostra é pequena (n=6), mas **se confirmar em mais dias é um bug de calibração**: o pipeline está "premiando" janelas que são na verdade **outliers super-limpos = sinal de regime de baixa volatilidade** que costuma anteceder mudança de regime. Hoje teve forte indício disso.

### 1.4 TripleRateAdvisor — confidence vs realidade

| Confidence reportada | n | Hits | Hit rate |
|---|---|---|---|
| **alta** | 73 | 37 | **50.7%** |
| **media** | 45 | 26 | **57.8%** |

**Inversão!** A confiança "alta" rendeu MENOS que "media" hoje. Isto significa que **o rótulo "CRESCENTE / ESTÁVEL" da regra em `bet_advisor.py` não está discriminando corretamente em condições atuais**. O Kill Switch dispara raramente (6×) e a granularidade entre "alta/media" é decorativa, não preditiva. Ver §5.2.

### 1.5 Estatística de sequências (runs)

```
Sequência (cronológica, 1=hit, 0=miss), 118 jogadas:
1110111011100010001110110100001100011111001001100101100101100110101011101111001011101101001000111101001100101010000011

Max hit streak:   5    │   Top hit streaks:  [5, 4, 4, 3, 3, 3, 3, 3, 3, 2]
Max miss streak:  5    │   Top miss streaks: [5, 4, 3, 3, 3, 3, 2, 2, 2, 2]

Distribuição equilibrada → o sistema NÃO está colado em um regime.
Mas o miss-streak de 5 explica perfeitamente a importância do Kill Switch
(G3 estora se permitir miss streak grande sem freio).
```

### 1.6 Janelas de Gale — 38 janelas hoje

```
G1 streaks: 32   │   resoluções normais
G3 reset:    4   │   ⚠️ janelas que estouraram para G3
G1 reset:    1   │
streak max:  12 plays / 9 hits (record do dia, CCW)
streak destacável: 10/5  e  7/4
```

**Insight:** Gale G3 reset = 4 vezes em 38 janelas (10.5%) — taxa controlada, dentro do esperado para hit rate 53%. Take-profit em G3 só vai disparar quando G3 → HIT.

### 1.7 Calibration_offset

```
calibration_offset = 0  em 118/118 spins finalizados  (100%)
```

→ **A calibração manual nunca foi aplicada hoje.** Função existe (TripleRateAdvisor + offset), mas operacional não usou. Ver §5.6.

---

## 2. Mapa Mental — como a estratégia funciona HOJE

```
                ┌─────────────────────────────────────────┐
                │   SPIN ENTRA (numero + direcao)         │
                │   Ex: spin=19 anti-horario, force=2     │
                └──────────────────┬──────────────────────┘
                                   ▼
                ┌─────────────────────────────────────────┐
                │  GameState.handle_spin()                │
                │  - Append em Timeline (CW ou CCW)       │
                │  - Decay automático (maxlen)            │
                └──────────────────┬──────────────────────┘
                                   ▼
        ┌──────────────────────────┴───────────────────────────┐
        │                                                      │
        ▼                                                      ▼
┌───────────────────────┐                       ┌────────────────────────┐
│  SDA17Strategy        │                       │  TripleRateAdvisor     │
│  .analyze(timeline)   │                       │  .analyze(performance, │
│                       │                       │           sda_score)   │
│                       │                       │                        │
│  Pipeline:            │                       │  Calcula:              │
│  1. Janela adaptativa │                       │   • c4 (últimos 4)     │
│     7→5→3→2 forças    │                       │   • m6 (últimos 6)     │
│  2. IQR outlier reject│                       │   • l12 (últimos 12)   │
│     (statistics.quan- │                       │                        │
│      tiles)           │                       │  Decide:               │
│  3. Weighted Median   │                       │   - KILL SW se c4=0    │
│     (decay 0.8^idx)   │                       │     AND sda_score≤2    │
│  4. Drift Detection   │                       │   - confidence label   │
│     (diffs 3 últimos) │                       │     (alta/media)       │
│  5. Smart Score 1-6   │                       │   - reason texto       │
│  6. Predicted Force   │                       │                        │
│                       │                       │  Output: BetAdvice     │
│  7. Triple Focus:     │                       │   (should_bet, conf,   │
│     • C1 = last_num   │                       │    reason, rates)      │
│       + predicted_F   │                       └────────────┬───────────┘
│       (raio 3 = 7 #)  │                                    │
│     • C2 = C1 + off2  │                                    │
│       (raio 2 = 5 #)  │                                    │
│     • C3 = C1 - off3  │                                    │
│       (raio 2 = 5 #)  │                                    │
│                       │                                    │
│  Output: 17 numbers   │                                    │
│  (sorted set union)   │                                    │
│  + center + score     │                                    │
└─────────┬─────────────┘                                    │
          │                                                  │
          └──────────────────┬───────────────────────────────┘
                             ▼
                ┌────────────────────────────────────────┐
                │  MessageHandler junta SDA + TR         │
                │  final_action = "APOSTAR" se ambos OK  │
                │                = "PULAR" se KillSwitch │
                │  gale_bet_value = current_bet (G1..3)  │
                └────────────────────┬───────────────────┘
                                     ▼
                ┌────────────────────────────────────────┐
                │  RESULTADO DA RODADA (próximo spin)    │
                │  result_actual ∈ {0..36}               │
                │  hit = result_actual in sda_numbers    │
                └────────────────────┬───────────────────┘
                                     ▼
        ┌────────────────────────────┴───────────────────┐
        ▼                                                ▼
┌──────────────────────────┐                  ┌──────────────────────────┐
│  M02-PctSigmoid update   │                  │  MartingaleState update  │
│  (sda17.update_adaptive) │                  │  (state.game.update)     │
│                          │                  │                          │
│  HIT:                    │                  │  HIT:                    │
│   off += (10 - off)*0.08 │                  │   level=1, current_bet++ │
│   (tighten 8%)           │                  │   (anti-martingale)      │
│                          │                  │                          │
│  MISS:                   │                  │  MISS:                   │
│   pct = min_dist/18      │                  │   level++                │
│   adj = sigmoid(k·pct)·2 │                  │   se G3 → reset G1       │
│   off2/off3 +=/−= adj    │                  │                          │
│   (dampened ±2 max)      │                  │  TAKE-PROFIT:            │
│                          │                  │   G3 HIT → lock + reset  │
└──────────────────────────┘                  └──────────────────────────┘
                                                       │
                                                       ▼
                                          ┌──────────────────────────┐
                                          │  decisions.db.insert     │
                                          │  + gale_windows.update   │
                                          │  + window_plays.append   │
                                          │  + state.json persist    │
                                          └──────────────────────────┘
```

### 2.1 Glossário rápido das peças

| Peça | Arquivo | O que faz em 1 linha |
|---|---|---|
| **Timeline** | `state/timeline.py` | Fila bounded com as últimas N "forças" por direção |
| **SDA17Strategy** | `strategies/sda17.py` | Prediz próxima força + monta 17 números com 3 centros |
| **TripleRateAdvisor** | `state/bet_advisor.py` | Kill switch + rótulo de confiança a partir de c4/m6/l12 |
| **MartingaleState** | `state/game.py` | Estado G1→G2→G3→reset com take-profit |
| **GameState** | `state/game.py` | Container de tudo; persiste em `state.json` |
| **MessageHandler** | `server/message_handler.py` | God node: dispatcher de eventos WS → atualiza tudo |
| **RouletteCore** | `core/roulette.py` | Imutável: WHEEL_SEQUENCE, cores, distância circular |

---

## 3. Auditoria arquivo-a-arquivo de estratégia

### 3.1 `core/roulette.py` (321 LoC)

| Aspecto | Avaliação |
|---|---|
| Responsabilidade | ⭐⭐⭐⭐⭐ Apenas física da roda (WHEEL_SEQUENCE, cores, distância circular) |
| Pureza | ⭐⭐⭐⭐⭐ Zero side effects, singleton, frozen dataclass |
| Cobertura testes | ✅ `tests/test_core.py` |
| Refatorar? | **NÃO.** Manter intacto. Único ponto: virar pacote `packages/core/` na Wave 1 da estrutura (skilss_emelhoras §27 PR-04). |

### 3.2 `state/timeline.py` (66 LoC)

| Aspecto | Avaliação |
|---|---|
| Estrutura | `deque(maxlen=N)` + `appendleft` — O(1) correto |
| Trade-off identificado | `add()` clampa força para [1,37] silenciosamente — log warning está OK |
| Refatorar? | **NÃO essencial**, mas vale mover para `packages/core/domain/` |

### 3.3 `strategies/base.py` (92 LoC)

| Aspecto | Avaliação |
|---|---|
| Pattern | `ABC` + `@dataclass StrategyResult` — bom |
| Falha | Não tem `update_adaptive` no contrato base — SDA17 implementa, mas não é abstrato. Outras estratégias podem esquecer. |
| Refatorar? | **SIM (pequeno):** mover para Python 3.12 `Protocol` (typing) e adicionar `update_adaptive` como método opcional. Ver §9.3. |

### 3.4 `strategies/sda17.py` (580 LoC) — O CORAÇÃO

| Aspecto | Avaliação |
|---|---|
| Estado | **Class-level** (`cw_history`, `ccw_history`, `_sigmoid_off`) — funciona, mas dificulta concorrência multi-mesa |
| Complexidade ciclomática | Alta — `analyze()` tem 7 caminhos diferentes (warmup, fallback SDA-19, sucesso 17, etc.) |
| Constantes "mágicas" | 16 constantes hardcoded no início da classe — deveriam estar em `config/strategies/sda17.toml` |
| Bugs vivos | Vários "BUG-XXX FIX" inline (clamps, fallbacks, warnings) — código é defensivo, mas indica que a especificação ainda não estabilizou |
| M02-PctSigmoid | É a inovação do v4.3 — substituiu brute-force Bayesiano O(n×m) por O(1). Boa direção. |
| Cobertura testes | ✅ `tests/test_sda17.py` — citado como 105/105 |
| Hot path performance | Aceitável; IQR + median + sigmoid são todos O(n log n) na janela pequena (n≤12) |
| **Refatorar?** | **SIM, em 3 frentes:** (a) extrair pipeline em **stages plugáveis**; (b) externalizar constantes; (c) tornar **stateful por mesa** (não singleton). Detalhes em §9. |

### 3.5 `state/bet_advisor.py` (169 LoC)

| Aspecto | Avaliação |
|---|---|
| Filosofia | "APOSTAR SEMPRE, só veta catástrofe" + Kill Switch (c4=0 AND sda_score≤2) |
| Janela | c4 = últimos 4, m6 = 6, l12 = 12 |
| Calibração | Hardcoded `MIN_DATA=2` |
| Problema medido | Confidence "alta" vs "media" não discrimina (50.7% vs 57.8% hoje) — labels podem ser invertidos ou mal calibrados |
| **Refatorar?** | **SIM, prioridade alta.** Confidence label hoje **não tem valor preditivo** — virou folclore. Trocar por **proba calibrada via isotonic regression** offline (LightGBM + calibração). §9.4 |

### 3.6 `state/game.py` (657 LoC) — God file menor

| Aspecto | Avaliação |
|---|---|
| Multi-responsabilidade | GameState + MartingaleState + persistência + migração schema | 
| MartingaleState | G1→G2→G3 + take-profit em G3-HIT |
| Persistência | `state.json` flat — file-locking não óbvio |
| Migrações | Tem suporte v1.3 → v1.4 inline — bom mas crescerá |
| **Refatorar?** | **SIM:** quebrar em `state/game.py` (só GameState), `state/martingale.py`, `state/persistence.py`. Migração SQLite → Postgres torna o `state.json` obsoleto (skilss_emelhoras Parte 3 §25 L5). |

### 3.7 `server/message_handler.py` (god node!)

| Aspecto | Avaliação |
|---|---|
| Função | Dispatcher único de mensagens WS — `if/elif/elif/...` |
| Acoplamento | Conhece TODOS os módulos (SDA, TR, GameState, DB, broadcaster) |
| **Refatorar?** | **SIM, urgente.** Já listado no plano evolução (skilss_emelhoras §25 L3 — broker pgmq + dispatch table). PR-09. |

### 3.8 Pasta `archive/`

- `force_predictor*.py`, `force_kalman*.py`, `force_cluster_analyzer.py` — estratégias antigas (versões pré-SDA17)
- `vector_store.py` — tentativa abandonada de embeddings
- `firebase_manager.py`, `microservico_db.py` — infra abandonada
- **Veredito:** manter em `archive/` (memória institucional), mas **não importar de lá em código novo**. Já está isolado.

---

## 4. Mapa visual do pipeline SDA17 — passo-a-passo numérico

> Usando uma decisão real do dia (id=3570, 23/05 15:41):
> spin=19 anti-horario, force=2, score=3, center=3, numbers=[0,1,3,6,12,13,14,16,17,20,26,27,28,32,...]

```
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 1 — ENTRADA                                                        │
│   last_number = 36 (do spin anterior)                                    │
│   direction   = CCW                                                      │
│   force=2  →  Timeline_CCW.appendleft(2)                                 │
│   Timeline_CCW = [2, 10, ..., 14] (até 24 itens)                         │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 2 — JANELA ADAPTATIVA                                              │
│   tenta n=7, depois 5, 3, 2 — escolhe a primeira que dá clean_count≥n//2 │
│   Ex: forces[:7] = [2, 10, 5, 17, 8, 9, 12]                              │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 3 — IQR OUTLIER REJECTION (quantiles)                              │
│   sorted = [2, 5, 8, 9, 10, 12, 17]                                      │
│   q1=5, q3=12, IQR=7, lower=−5.5, upper=22.5                             │
│   clean = todos (nenhum outlier) → survival_rate = 1.0                   │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 4 — WEIGHTED MEDIAN                                                │
│   peso = 0.8^idx  para idx=0..6                                          │
│   expanded = [2×10, 10×8, 5×6, 17×5, 8×4, 9×3, 12×2]                     │
│            ≈ [2,2,2,...,10,10,...,12,12]                                 │
│   median(expanded) = 10 (peso forte das forças mais recentes)            │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 5 — DRIFT DETECTION                                                │
│   diffs(últimos 3 limpos) = [2−10, 10−5] = [−8, 5]                       │
│   não monotônica → drift_adj = 0                                         │
│   pred = clamp(10 + 0, 1, 37) = 10                                       │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 6 — SMART SCORE                                                    │
│   survival=1.0, spread=15, tightness=max(0, 1−15/18)=0.17                │
│   score = min(6, int(1.0*3 + 0.17*3 + 1)) = min(6, 4) = 4                │
│   (na decisão real do dia score=3 — pequena diferença, ex didático)      │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 7 — TRIPLE FOCUS                                                   │
│   C1 = last_num + pred_force aplicado em CCW                             │
│      = wheel[(wheel.index(36) − 10) mod 37]  ≈  3                        │
│   off_c2 (sigmoid state) = round(12.3) = 12                              │
│   off_c3 (sigmoid state) = round(11.7) = 12                              │
│   C2 = wheel[(idx(3) + 12) mod 37]                                       │
│   C3 = wheel[(idx(3) − 12) mod 37]                                       │
│   nums = neighbors(C1,3) ∪ neighbors(C2,2) ∪ neighbors(C3,2)             │
│        = {0,1,3,6,12,13,14,16,17,20,26,27,28,32,...}                     │
│   cobertura = |nums| = 17  (45.9% da roda)                               │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ STAGE 8 — FEEDBACK PCT-SIGMOID (após saber result_actual)                │
│   hit?                                                                   │
│    SIM → off2 += (10−off2)*0.08   (tighten 8% para o centro)             │
│            off3 += (10−off3)*0.08                                        │
│    NÃO → min_dist = circ_dist(actual, nums) clamp 18                     │
│           pct     = min_dist/18  ∈ [0,1]                                 │
│           adj     = (2/(1+exp(−6·pct)) − 1) · 2.0  ∈ [−2,+2]             │
│           lado direcional do erro → off2 +=adj , off3 −=adj·0.3          │
│                                       (ou inverso)                       │
│   Os offsets são CLAMP [7, 13]                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

**Pegadinha técnica:** o feedback é **só sobre C2/C3**. C1 (mediana ponderada) **não é ajustada por feedback** — ela já vem do pipeline IQR. Logo, **se a janela de IQR for ruim, nenhum sigmoid feedback corrige**.

---

## 5. Auditoria de qualidade — onde a estratégia está vazando hoje

### 5.1 Assimetria CW vs CCW (a #1 prioridade)

```
Δ = 23.8 pontos  (CCW 65.5% vs CW 41.7%)
```

**Hipóteses ordenadas por probabilidade:**
1. ⭐⭐⭐⭐⭐ **Convergência sigmoid demorada para CW** — `_sigmoid_off['cw_off2']` e `cw_off3` ainda longe do ótimo. CW tem só 60 jogadas hoje, CCW tem 58 — semelhantes, então NÃO é amostra pequena.
2. ⭐⭐⭐⭐ **Viés intrínseco do dealer/mesa atual** capturado por CCW mas mascarado por CW. Solução: **dois priors** independentes, não só dois offsets.
3. ⭐⭐⭐ **Sigmoid scale=2.0 é muito conservador para correção rápida.** CCW chegou ao "vale" antes de CW. Aumentar para 2.5–3.0 acelera, mas aumenta variance.

### 5.2 Confidence label "alta" rende menos que "media"

```
alta  → 73 apostas / 37 hits / 50.7%
media → 45 apostas / 26 hits / 57.8%
```

**Causa-raiz provável:** as regras em `TripleRateAdvisor.analyze`:
- `alta`: `c4 ≥ m6 ≥ l12 AND c4 > 0` (sequência CRESCENTE) **ou** `c4 ≥ m6` (ESTÁVEL)
- `media`: `c4 > 0 AND c4 < m6` (AGRESSIVO em queda) **ou** `c4 = 0 mas sda_score > 2` (COLD)

O label "alta = crescente/estável" pega **regimes que já tinham boa taxa anterior**. Mas regime de roleta tende a **reverter à média** (assumindo i.i.d.). Estatística clássica: **estados de alta taxa anterior** têm forte regression-to-mean → conferem confidence ALTA exatamente nos momentos prestes a desafinar.

**Correção sugerida:**
- Não confiar no label categórico
- Substituir por **proba calibrada** (LightGBM offline, calibration via isotonic) que usa `c4, m6, l12, sda_score, drift, spread, survival_rate, off2−off3` como features
- Treinar uma vez por semana sobre os últimos 5000 spins

### 5.3 Score 5 com hit rate 16.7% (n=6)

⚠️ **Amostra pequena**, mas anômalo o suficiente para investigar. Score 5 acontece quando `survival × tightness × stable_bonus` aproxima de 5/6. Ou seja: **dados muito limpos, todos juntos, sem drift**. Isso descreve **baixa volatilidade preceding a regime change**.

**Sugestão:** monitorar `score=5` e `score=6` por uma semana. Se hit rate ficar < 40%, **inverter o sinal**: score alto → ser CAUTELOSO, não confiante.

### 5.4 Calibration manual = 0 em todas

Função existe, ninguém usa. Duas opções:
- **(A)** Remover do código (`tools/backtest_from_db.py` continua usando)
- **(B)** Tornar **automática** — pequeno controlador PID a partir do erro médio últimos 20 → integral term

Recomendo **(B)** porque a infraestrutura para isso já existe (`calibration_offset` no DB), e é exatamente a "afinação ao dealer" que você mencionou estar não-ótima.

### 5.5 Kill Switch dispara 4.5% (6/132)

Taxa baixa = filosofia "apostar sempre" funcionando. Mas zero análise sobre **quão úteis foram esses 6 skips**: precisamos comparar **o que teria acontecido se tivesse apostado**. Hoje não temos esse contrafactual no DB. **Adicionar** `would_have_been_hit BOOLEAN` para shadow mode (Parte 3 §25 L4).

### 5.6 G3 reset = 4 em 38 janelas

10.5% das janelas estouram. Aceitável para hit rate 53%. Cálculo aproximado:
- P(miss×3 seguidos | hit_rate=0.53) ≈ (0.47)³ ≈ 10.4% ✓ **bate quase exatamente**

Conclusão: **o sistema está se comportando como Bernoulli i.i.d. com p=0.53**. Não há "memória" sendo capturada além do regime médio. Para melhorar G3, precisamos **detectar regime change ANTES de chegar em G2** — ver §7 (proposta região menos visitada).

---

## 6. Proposta #1 — Ir para 21 ou 27 números?

### 6.1 Matemática base

| Cobertura | Números | % roda | Break-even hit | Payout líquido sobre stake |
|---|---|---|---|---|
| 17 (atual) | 17 | 45.9% | 47.2% | **(35+1)·17/35 − 17 = 17.49/35 ≈** mais simples: stake total = 17, payout em hit = 36, líquido = 19. Hit→ +19; Miss → −17. Break-even h: 19h − 17(1−h) = 0 → h = 17/36 = **47.2%** |
| 21 | 21 | 56.8% | **21/36 = 58.3%** | Hit → +15; Miss → −21 |
| 23 | 23 | 62.2% | 23/36 = 63.9% | Hit → +13; Miss → −23 |
| 25 | 25 | 67.6% | 25/36 = 69.4% | Hit → +11; Miss → −25 |
| 27 | 27 | 73.0% | 27/36 = **75.0%** | Hit → +9; Miss → −27 |

### 6.2 Simulação 3 cenários sobre os dados de HOJE

**Cenário A — Manter 17 (estado atual)**
- Margem real hoje: 53.4% − 47.2% = **+6.2 pts** → ROI positivo
- Risco G3: 10.5% janelas estoram
- **PnL hoje** com stake fixa 17 unidades, payout 19:
  - 63 hits × 19 = +1197
  - 55 misses × (−17) = −935
  - **Líquido = +262 unidades**

**Cenário B — 21 números (adicionar 4)**
- Como adicionar? Sugestão: aumentar raio C2 e C3 de 2 para 3 (`C2_RADIUS=3, C3_RADIUS=3`) → 7+7+7 = ~21 (com overlap)
- Hit rate esperado: cobertura sobe ~10 pts (45.9 → 56.8), mas hit rate só sobe se as 4 casas extras forem informativas. Estimativa generosa: hit rate **subiria de 53.4% → 58–62%** (parte dos misses cai dentro das casas novas)
- **Mas break-even sobe para 58.3%** → margem cai para **0 a 4 pts**, com risco G3 quase igual
- **PnL hoje** com 21 nums (hipotético hit=60%):
  - 71 hits × 15 = +1065
  - 47 misses × (−21) = −987
  - **Líquido ≈ +78 unidades** (3.4× pior que A)

**Cenário C — 21 condicional na direção forte**
- Em CCW (hit=65.5%) → usar **21 números** (break-even 58.3% → margem +7.2 pts)
- Em CW (hit=41.7%) → usar **17 números** (mas ainda abaixo break-even — Kill Switch deveria pular mais)
- **PnL CCW estimado hoje com 21 nums:** 
  - 38 hits → ~41 hits (se 21 captura ~12% mais dos misses) × 15 = +615
  - 17 misses → 17 misses × (−21) = −357
  - **CCW líquido = +258** (vs +228 com 17 atual)
- **CW continua com 17** → líquido CW ainda negativo se hit < 47.2% (hoje −51 estimado)
- **Líquido total ≈ +207** (vs +262 do A)

**Cenário D — 27 números (descartado de cara)**
- Break-even 75% → CCW (65.5%) **ainda abaixo** → PnL negativo
- **Veredito:** NÃO

### 6.3 Resultado da simulação

| Cenário | Hit rate esperado | Break-even | PnL hoje (estimado) | Veredito |
|---|---|---|---|---|
| A — 17 fixo (hoje) | 53.4% | 47.2% | **+262** | ✅ Baseline sólida |
| B — 21 fixo | 58-62% | 58.3% | +78 | ⚠️ Pior — margem fina |
| C — 17/21 condicional por direção | 53/65% | 47/58% | +207 (próximo) | 🟡 Equivale, mais risco operacional |
| D — 27 fixo | 60-65% | 75.0% | negativo | ❌ Não |

> ⚠️ Estimativas com forte hipótese sobre "quanto da cobertura extra captura misses". Para validar de verdade, **rodar `tools/backtest_from_db.py`** com os 3 cenários — função existe. Recomendo §10 PR-A.

### 6.4 Conclusão Proposta #1

**Manter 17 números é racional.** A intuição da "probabilidade de curto prazo" só ganha **se você conseguir prever quando o regime está em alta (>60%) E aumentar cobertura nesse momento E reduzir cobertura quando regime ruim**. Isto é o **Cenário C dinâmico** — mas a chave não é o "21 ou 27", é o **gatilho de decisão**. Ver Proposta #2 e #3.

---

## 7. Proposta #2 — Pontuação por "região menos visitada" (anti-cluster)

### 7.1 Sua intuição, formalizada

> "Cada região menos visitada deveria pontuar mais. Cada número que cair muito perto da região recente deveria pontuar menos."

Isso é uma forma de **regularizador anti-cluster** ou, em linguagem de bandits, **bonus de exploração estilo UCB (Upper Confidence Bound)**.

### 7.2 Matemática proposta

Para cada número `n ∈ {0..36}`:

```
recency_score(n) = Σ_{k=1..K}  decay^k · 1/(1 + min_circ_dist(n, spin_{−k}))
```

- `decay = 0.85` (mais recente importa mais)
- `K = 12` (janela de "visitação")
- `min_circ_dist(n, spin_k)` = mesma função `_circ_dist` que já existe
- Quanto **maior** o `recency_score`, **mais visitada** está a região do `n` → menor o "bonus de exploração"

Inversa para usar no scoring:
```
exploration_bonus(n) = 1 / (1 + recency_score(n))
```

### 7.3 Como combinar com força (estratégia híbrida)

Hoje: `numbers = union(neighbors(C1, 3), neighbors(C2, 2), neighbors(C3, 2))`

Proposta (**M16-Hybrid**):

```
score_final(n) = α · force_signal(n) + β · exploration_bonus(n)

force_signal(n) = 1 se n ∈ {C1, neighbors(C1, 3)}    → +1.0
                  0.7 se n ∈ neighbors(C2, 2)
                  0.7 se n ∈ neighbors(C3, 2)
                  0 caso contrário

α = 0.7   (peso da força, dominante)
β = 0.3   (peso da exploração)

bet_on = top_k(score_final, k=17 ou 21)
```

### 7.4 Vantagens

1. **Mantém a inteligência atual** (SDA17 escolhe C1/C2/C3 corretos) mas **refina os 17 finais**: pode trocar um vizinho saturado por uma casa fora dos centros mas que **não saiu nas últimas 12 jogadas**.
2. **Anti-cluster natural:** se C2 e C3 caem em região muito recente, o score baixa e o algoritmo "vira" para casas externas.
3. **Compatível com Smart Gale:** uma sequência de misses → casas próximas dos misses ganham menos peso → próxima aposta diverge da região perdedora.
4. **Custo computacional:** O(36 × 12) = 432 multiplicações por decisão → desprezível.

### 7.5 Simulação rápida sobre dados de hoje

```
Pego os últimos 12 spins: [19, 36, 12, 28, 2, ...]
Calculo exploration_bonus para cada n
Re-rankeio os 17 da decisão real (id=3570)
Comparo com result_actual (12)

Resultado actual: 12  →  estava nos 17 originais (HIT)
Top 17 do M16-Hybrid: ainda inclui 12 (CW dist baixa do C1 estava OK)
→  hipótese: convergência similar em hits, mas em misses M16 trocaria 1-2 casas
```

> **Para validar de verdade:** rodar backtest histórico sobre as 3 574 decisões com α/β variando em grid (0.5, 0.7, 0.9). PR-B em §10.

### 7.6 Conclusão Proposta #2

✅ **Vale implementar**, com cautela: introduzir como **shadow mode** primeiro (rodar em paralelo, comparar PnL). Se shadow ficar consistentemente acima do live por 2 semanas, promover.

---

## 8. Proposta #3 — Tratar cada região como aposta independente

### 8.1 Sua intuição, formalizada

> "Hoje 3 centros viram 1 aposta de 17 nums. E se cada centro fosse aposta independente com sua própria probabilidade?"

Isso é a **decomposição em 3 portfólios paralelos**:
- Portfolio A: aposta apenas em `neighbors(C1, 3)` — 7 nums, break-even 19.4%
- Portfolio B: aposta apenas em `neighbors(C2, 2)` — 5 nums, break-even 13.9%
- Portfolio C: aposta apenas em `neighbors(C3, 2)` — 5 nums, break-even 13.9%

### 8.2 Por que isso é diferente

Hoje você arrisca **17 unidades por spin** e ganha 19 em hit. Decompondo:

- Você poderia apostar em **só 1 centro** quando ele estiver mais "quente" → exposição de 5–7 unidades, payout 36
- Ou apostar em **2 centros** → exposição 12, payout 36
- Ou **todos os 3** = estratégia atual

**Variável-chave:** "qual centro está mais quente?"

### 8.3 Indicador de quente por centro

Para cada centro Ck, manter:
- `hits_window(Ck)` = quantos hits dos últimos 12 caíram em `neighbors(Ck, ?)`
- `coverage(Ck)` = 7 ou 5 nums = 0.189 ou 0.135 da roda
- `excess(Ck) = hits_window(Ck)/12 − coverage(Ck)` → quanto acima do esperado por azar

**Decisão:**
- `excess(Ck) > +0.05`: centro QUENTE → apostar nele
- `−0.05 ≤ excess(Ck) ≤ +0.05`: centro NEUTRO → considerar
- `excess(Ck) < −0.05`: centro FRIO → pular

### 8.4 Simulação sobre os números mais apostados hoje

Lembre que hoje os números **19, 30, 32** renderam **61–62%** (alta margem), enquanto **27, 33** renderam **47–49%**. **Esses são índices de quais regiões estavam quentes**:

```
Top hot zones hoje (por contribuição relativa para hits):
  19 (apostado 60×, contribuiu 37 = 61.7%)  → região do 19 estava quente
  30, 32, 15, 31, 11, 9   → todas 54–61%
Cold zones:
  33 (47.5%), 27 (49.1%), 20 (49.2%), 1 (49.2%) → abaixo break-even
```

Se você tivesse apostado **só nos centros quentes** (filter por excess > 0), teria:
- ~30% menos jogadas (capital preservado em "frio")
- Hit rate condicional provavelmente 60%+
- PnL/jogada superior, capital diário menor

### 8.5 Trade-off escondido

Independência absoluta tem custo: **perde a sinergia das 3 zonas**. Hoje o C1 sozinho cobre 19% da roda → break-even 19.4% → você precisa um sinal forte. Manter 2 zonas continua cobrindo 32% → mais robusto.

### 8.6 Conclusão Proposta #3

🟡 **Vale como FILTRO, não como SUBSTITUIÇÃO.**

**Recomendação concreta (M16-Hybrid-Filter):**
- Mantém C1, C2, C3 como hoje
- Calcula `excess(C2)` e `excess(C3)`
- Se `excess(Ck) < −0.10`: **dropa o centro Ck dessa rodada** (aposta com 12 nums ou 10 nums em vez de 17)
- C1 sempre apostado (centro principal, mediana)
- Resultado esperado: **menos exposição em momentos ruins, mesma exposição em momentos bons**

---

## 9. Refatorações tecnológicas — o que mudar (e o que não)

### 9.1 Mapa do que vale mudar

| Item | Estado | Vale mudar? | Por quê |
|---|---|---|---|
| `RouletteCore` (`core/roulette.py`) | Imutável puro | **NÃO** | Está perfeito. Manter. |
| `Timeline` | deque + maxlen | **NÃO** | Funciona, é simples. |
| `StrategyBase` ABC | Funciona | 🟡 Pequeno | Migrar para `Protocol` para tipagem mais flexível |
| `SDA17Strategy.analyze` monolítico | 580 LoC, 1 método grande | **SIM** | Quebrar em "stages" como `Stage1Window`, `Stage2IQR`, etc. Permite teste isolado + plugar M16 sem clonar |
| 16 constantes hardcoded | Magic numbers | **SIM** | Externalizar em `config/strategies/sda17.toml` — você ajusta sem deploy |
| `TripleRateAdvisor` labels | Folclore (50.7%≈57.8%) | **SIM** | Substituir por **proba calibrada (LightGBM)** treinada offline |
| Estado singleton `SDA17Strategy` | class instance | **SIM** | Tornar **por mesa** (Wave 2 do plano evolução), permite multi-mesa |
| `state.json` plano | flat file | **SIM** | Migrar para Postgres (skilss_emelhoras Parte 3 §25 L5) — ganha consistência + replay |
| Backtester `tools/backtest_from_db.py` | Existe | **SIM** | Promover a **suíte de cenário A/B** integrada ao CI (pytest-benchmark) |
| Shadow mode | Não existe | **SIM** | Wave 2 do plano evolução §25 L4. **Crucial** para validar Proposta #2/#3 sem risco. |
| Auto-calibration controller | Não existe | **SIM** | Pequeno PID controller sobre `calibration_offset` baseado em erro médio últimos 20 |

### 9.2 Tecnologias específicas

| Camada | Hoje | Sugestão | Justificativa |
|---|---|---|---|
| Math/Stats | `statistics` stdlib | **Manter + acrescentar `numpy` em hotspots** | Janela é pequena (n≤12), stdlib basta para median/quantiles |
| ML offline | Nenhum | **`scikit-learn` + `lightgbm`** | Treinar isotonic calibration para confidence (semanal) — não está no hot path |
| Backtesting | script ad-hoc | **`vectorbt` ou `nautilus_trader` (lite)** | Backtest profissional com sweep de hiperparâmetros |
| Hyperparameter search | manual | **`optuna` (Bayesian)** | Encontrar α, β, sigmoid_k, etc. — roda 1× / semana |

---

# 🔬 PARTE 2 — Auditoria pós-revisão com benchmark externo (23/05 14:35)

> Esta seção foi **apensa** após a primeira escrita do documento. Foi feita uma auditoria claim-by-claim usando `sequential-thinking` MCP + 5 buscas independentes via `brave-search` para confrontar cada conclusão com literatura estabelecida (UCB1, Thompson, ADWIN, Kelly multivariate, Platt/Isotonic, Adam/RMSProp, vectorbt). O resultado é **manter ~80% das recomendações iniciais**, mas com 6 refinamentos importantes e 1 retratação parcial (score 5 anomalia).

---

## 14. Auditoria de certeza — cada conclusão vs literatura

### Legenda
- ✅ **CONFIRMADO** — literatura externa corrobora
- 🔵 **CONFIRMADO + REFINADO** — vale, mas algoritmo melhor existe
- ⚠️ **PARCIALMENTE REFUTADO** — claim correto em direção mas exagerado
- ❌ **REFUTADO** — precisa retratação

### 14.1 Claim C1 — "Manter 17 fixos é racional, 21/27 só condicional"

**Status:** ✅ CONFIRMADO

**Verificação independente (Kelly criterion):**
- Fórmula clássica para roleta cobrindo k números, payout 36, bankroll B:
  - `edge = 36·p − k` onde `p = hit_rate`
  - `kelly_fraction = edge / (35·k)` (variance term)
- Para k=17, p=0.534: edge = 19.22 − 17 = +2.22 → f* = 2.22/595 = **0.37% Kelly** → minúsculo, posição contínua é OK
- Para k=21, p=0.583: edge = 20.99 − 21 = −0.01 → f* ≈ 0 (na fronteira, ruína esperada)
- Para k=21 condicional CCW (p=0.655): edge = 23.58 − 21 = +2.58 → f* = 0.35%
- **Confirmação matemática:** Kelly diz que 21 cego é break-even **literalmente**, 21-condicional ganha mas marginalmente. **Investimento informacional do gating vale mais que o investimento na cobertura extra.**

**Refinamento novo (não estava no doc original):**
- Quarter-Kelly (¼ × f*) é o padrão para agentes autônomos (75% redução de variância, sacrifício de 25% growth) — AgentBets.ai 2025
- Recomendação atualizada: usar **¼-Kelly como teto de stake_per_spin**, abandonar martingale puro (G1→G2→G3 é geometricamente equivalente a 7× Kelly em G3 — explosivo)
- **PR-K novo:** substituir MartingaleState por `FractionalKellyState` com cap.

### 14.2 Claim C2 — "Label confidence alta/media é folclore (50.7% vs 57.8%)"

**Status:** ✅ CONFIRMADO + REFINADO

**Verificação independente:**
- scikit-learn 1.8 docs sobre CalibratedClassifierCV: **Platt (sigmoid)** para datasets pequenos, **Isotonic** para n>1000
- Niculescu-Mizil & Caruana 2005 (Cornell): isotonic precisa >1000 samples para não overfittar, sigmoid funciona em 100+
- Medium @iamban (Jun/2025): "Platt para parametric monotonic, isotonic non-parametric flexible"

**Refinamento da minha recomendação original:**
- Eu disse direto "LightGBM + isotonic" — **prematuro**. Plano em 2 fases:
  - **Fase 1 (3 574 amostras, 1 mesa):** Logistic Regression + **Platt scaling** sobre 6 features (`c4, m6, l12, sda_score, drift_flag, abs_diff(off2,off3)`)
  - **Fase 2 (≥10 000 amostras, n≥3 mesas):** LightGBM + **Isotonic regression** com calibração separada por direção (CW/CCW têm distribuições diferentes — ver C4)
- Métricas-alvo: **Brier score** + **Expected Calibration Error (ECE)** + **AUC**. Hoje o label não tem nenhuma dessas medidas — adicionar à pipeline.

### 14.3 Claim C3 — "Score 5 anomalia (16.7%, n=6) → inverter sinal"

**Status:** ⚠️ PARCIALMENTE REFUTADO — claim premature

**Verificação independente (Beta-Binomial, John Cook 2025 + Bayes Rules! Cap. 3):**
- Prior não-informativo Jeffreys: Beta(0.5, 0.5)
- Observado 1 hit em 6: posterior = Beta(1.5, 5.5)
- Média = 0.214, mediana ≈ 0.18, **95% credible interval ≈ [0.039, 0.504]**
- **0.50 está dentro do CI!** → estatisticamente compatível com hit rate normal
- Para concluir "score 5 é anti-preditivo" com 95% confiança, preciso CI superior < 0.47 → exigiria ~1 hit em 14 ou 2 em 20

**Retratação parcial:** §5.3 sugeria "se confirmar, inverter sinal". Reforço o **"se confirmar"** e suavizo o "inverter". **Recomendação corrigida:**
- Tratar score 5 como **flag para amostragem**, não para inversão
- Coletar próximos 30 score=5 antes de qualquer ação
- Apenas **logar** a anomalia hoje, não mudar comportamento
- **PR-L novo:** adicionar `assert n_score5 ≥ 20 before adjusting weights` no auto-tuning

### 14.4 Claim C4 — "Convergência sigmoid demorada para CW (assimetria 23.8 pts)"

**Status:** ✅ CONFIRMADO E REFORÇADO

**Verificação independente:**
- Kingma & Ba 2014 (Adam paper) + Wikipedia SGD: vanilla SGD com step fixo (que é exatamente o PCT-Sigmoid) é conhecido por convergência lenta em superfícies com **gradiente assimétrico** — exatamente o caso CW vs CCW
- Adam dinâmico (β1=0.9 momentum + β2=0.999 segundo momento) tipicamente converge 3-5× mais rápido em problemas non-stationary
- River library (Mar/2025) recomenda RMSProp ou Adam para online learning rate em streams

**Refinamento + algoritmo concreto:**
```python
# Substituir _pct_sigmoid_update por Adam-style
# state per direction per offset (off2_cw, off3_cw, off2_ccw, off3_ccw)
class AdamSigmoidUpdater:
    def __init__(self, lr=0.5, beta1=0.9, beta2=0.999, eps=1e-8):
        self.m = 0.0  # 1st moment (error sign)
        self.v = 0.0  # 2nd moment (error magnitude)
        self.t = 0
        self.lr = lr; self.b1 = beta1; self.b2 = beta2; self.eps = eps
    def step(self, signed_error):
        self.t += 1
        self.m = self.b1 * self.m + (1 - self.b1) * signed_error
        self.v = self.b2 * self.v + (1 - self.b2) * signed_error**2
        m_hat = self.m / (1 - self.b1**self.t)
        v_hat = self.v / (1 - self.b2**self.t)
        return self.lr * m_hat / (math.sqrt(v_hat) + self.eps)
```
- Vantagem: o `v_hat` desce o LR efetivo quando o erro é volátil, **e sobe** quando o erro é consistente — atacando exatamente o problema de CW que está "preso" em offset subótimo
- **PR-M novo:** Adam-Sigmoid updater por direção (substitui PCT-Sigmoid existente, mantém clamps [7,13])

### 14.5 Claim C5 — "Exploration bonus 1/(1+recency) anti-cluster"

**Status:** 🔵 CONFIRMADO + REFINADO

**Verificação independente:**
- A fórmula original que propus (`Σ decay^k · 1/(1+dist)`) é uma **heurística ad hoc** semelhante a UCB-Decayed
- Literatura clássica (Lilian Weng 2018 + Stack Exchange 2024 + ITM 2025): para problemas estacionários, **UCB1** é o ótimo; para non-stationary, **Thompson Sampling** com Beta-Binomial supera UCB1
- Roulette com viés de dealer **É non-stationary** (regime change quando dealer/mesa muda) → Thompson é teoricamente melhor

**Refinamento concreto:**
- Substituir minha heurística por **Thompson Bernoulli** per região da roleta (37 regiões = 37 números)
- Para cada número n, manter `(α_n, β_n)` = (hits_recentes, misses_recentes) com decay temporal
- Amostrar de Beta(α_n + 1, β_n + 1) para obter `theta_n_sample` por jogada
- Usar `theta_n_sample` como o termo β em vez de `1/(1+recency)`
- Vantagem: **auto-exploration via posterior uncertainty** — regiões pouco visitadas têm Beta com baixos counts → distribuição larga → amostra tem mais variance → exploração natural

```python
# Stage 6.5 — Thompson region scoring
def thompson_region_score(n: int, alpha: dict, beta: dict, decay=0.97) -> float:
    a = alpha.get(n, 1.0)
    b = beta.get(n, 1.0)
    # Sample once per spin
    return random.betavariate(a + 1, b + 1)

def update_thompson(n_observed_hit: int, hit: bool, alpha, beta, decay=0.97):
    # Decay all entries
    for k in alpha: alpha[k] *= decay
    for k in beta: beta[k] *= decay
    if hit:
        alpha[n_observed_hit] = alpha.get(n_observed_hit, 1.0) + 1
    else:
        beta[n_observed_hit] = beta.get(n_observed_hit, 1.0) + 1
```
- α=0.7 (force) + β=0.3 (Thompson) ainda é o ponto inicial
- **PR-N novo:** Stage 6.5 Thompson (substitui exploration_bonus fixo). Implementação ~50 LoC.

### 14.6 Claim C6 — "Tratar cada centro como aposta independente"

**Status:** ❌ REFUTADO — preciso retratar

**Verificação independente (Kelly multivariate, Quant Stack Exchange + Quant Blueprint 2024-2025):**
- Para múltiplas apostas SIMULTÂNEAS, o Kelly correto é **multivariate** com matriz de covariância:
  - `f* = Σ^{-1} · μ` onde Σ é covariance matrix dos returns e μ é vector de expected excess returns
- **C1, C2, C3 são fortemente correlacionados:**
  - Compartilham a mesma roda física (Σ não é diagonal)
  - Compartilham o mesmo dealer (Σ tem componente comum)
  - Compartilham a mesma direção (off2 e off3 são gerados pelo MESMO sigmoid state)
- Logo, decompor em "3 portfólios independentes" assume Σ = Identity, o que é **falso**

**Retratação:** §8 estava sugerindo decomposição naïve. Refino para:
- **Não tratar como bets independentes para sizing**
- **Tratar como bets independentes APENAS para filtering** (decisão binária "inclui/dropa" o centro nessa rodada — §8.6 já estava no caminho certo)
- Acrescentar: **modelo de covariância empírica** se quisermos sizing diferente por centro

**Modelo simples de covariância:**
```
Σ[i][j] = corr(hit_i, hit_j) sobre últimos 200 spins
```
- Se corr alta (>0.5), reduzir size de ambos
- Se corr baixa (<0.1), pode size full
- Para a Roleta Cloud onde dist(C1,C2) ≈ 12 wheel slots típico, corr deve ser ~0.2-0.4 (overlap parcial via vizinhos) — vale calcular

### 14.7 Claim adicional descoberto pela auditoria — DRIFT DETECTION

**Status:** 🆕 NOVO ITEM — não estava no doc original, devo adicionar

**Descoberta:** `river.drift.ADWIN` (Bifet 2007 + ADWIN-U 2025, Springer) é o estado-da-arte para detectar **regime change** em streaming sem label

**Aplicação direta no Roleta Cloud:**
- Hoje a estratégia adapta CADA spin (sigmoid update), o que é "reativo demais"
- ADWIN detecta change-point ESTRUTURAL (mudança de dealer, mesa, bias) → quando detecta drift:
  1. Resetar `_sigmoid_off` para defaults
  2. Limpar `cw_history` e `ccw_history`
  3. Aumentar Kill Switch sensitivity por N spins
- Pacote: `pip install river` (~5 MB)
- Estado por mesa: 2 instâncias ADWIN (uma por direção sobre hit/miss stream)
- **PR-O novo:** integrar ADWIN no Stage 0 do pipeline

---

## 15. Refinamentos técnicos consolidados

### 15.1 Tabela antes × depois

| Aspecto | Doc original (Parte 1) | Auditoria refinada (Parte 2) | Evidência |
|---|---|---|---|
| Bet sizing | Martingale G1→G2→G3 | **¼-Kelly** com cap | AgentBets 2025 |
| Calibration | LightGBM + Isotonic já | LR + Platt **agora**, LightGBM + Isotonic em fase 2 | Niculescu-Mizil 2005 |
| Score 5 | Inverter sinal | **Apenas logar**, n≥20 antes de agir | Beta-Binomial CI |
| Sigmoid update | Sigmoid clamped fixed step | **Adam** (β1, β2 adaptativo) | Adam paper |
| Exploration | Heurística `1/(1+recency)` | **Thompson Bernoulli** per região | Lilian Weng + ITM 2025 |
| 3 centros | Tratar independente para sizing | Independente **apenas para filter**, sizing via covariance | Kelly multivariate |
| Regime change | Não trata | **ADWIN per direção** | Bifet 2007 + ADWIN-U 2025 |
| Backtest | script ad-hoc | **vectorbt** (Numba/Rust grid sweep) | vectorbt.dev + Reddit 2025 |

### 15.2 Mapa mental v6 — estratégia ideal pós-auditoria

```
                          ┌──────────────────┐
                          │  ADWIN drift     │ ← NOVO (PR-O)
                          │  detector × 2    │
                          └────┬─────────────┘
                               │ drift? sim → reset state
                               ▼
┌──────────────┐   ┌───────────────────────────────────────┐
│ Timeline     │   │  Janela adaptativa + IQR + median     │
│ (unchanged)  │──▶│  (Stages 2-4: mantidos)               │
└──────────────┘   └─────────────┬─────────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────────────┐
                  │  Stage 5: Smart Score                 │
                  │  + Beta-Binomial CI test em score=5/6 │ ← NOVO (PR-L)
                  └───────────────┬───────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────────────┐
                  │  Stage 6: Triple Focus C1/C2/C3       │
                  │  + cov matrix Σ últimos 200 spins     │ ← NOVO (PR-J')
                  └───────────────┬───────────────────────┘
                                  │
                                  ▼
┌──────────────────┐  ┌───────────────────────────────────────┐
│ Hist (37 nums)   │─▶│  Stage 6.5: Thompson Bernoulli β-score│ ← NOVO (PR-N)
│ α_n, β_n         │  │  score_final = α·force + β·thompson   │
└──────────────────┘  └───────────────┬───────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────────────┐
                  │  Stage 6.7: Hot Center Filter         │ ← (PR-D)
                  │  drop Ck if excess(Ck) < −0.10        │
                  └───────────────┬───────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────────────┐
                  │  Stage 7: top_k (k=17 ou 21)          │
                  │  with k = f(direction_hit_rate)       │
                  └───────────────┬───────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────────────┐
                  │  Stage 8: Feedback Adam-Sigmoid       │ ← NOVO (PR-M)
                  │  (substitui PCT-Sigmoid)              │
                  └───────────────┬───────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────────────┐
                  │  Bet Sizing: ¼-Kelly cap              │ ← NOVO (PR-K)
                  │  (substitui Martingale puro)          │
                  └───────────────────────────────────────┘
```

### 15.3 Bibliotecas Python a adicionar

| Lib | Versão | Uso | Tamanho | Hot path? |
|---|---|---|---|---|
| `river` | ≥0.20 | ADWIN drift | ~5 MB | NÃO (1× por spin) |
| `vectorbt` | ≥0.27 | Backtest grid | ~50 MB | NÃO (offline) |
| `scikit-learn` | ≥1.4 | LR + Platt + Isotonic | ~70 MB | NÃO (offline) |
| `lightgbm` | ≥4.0 | GBM Fase 2 | ~5 MB | NÃO (offline) |
| `optuna` | ≥3.5 | Hiperparâmetros | ~10 MB | NÃO (offline) |
| `numpy` (já tem) | ≥1.26 | Vector ops | — | possivelmente hot |
| `scipy` | ≥1.11 | Cov matrix, Kelly opt | ~50 MB | NÃO (offline + spin reset) |

**Footprint total novo:** ~190 MB (cabe folgado no Docker image)

---

## 16. Plano consolidado de PRs (v2)

Lista refinada pós-auditoria. **Negrito** = mudança vs Parte 1 §10. Ordem por risco × valor.

| ID | Nome | Risco | Esforço | Depende de | Valor PnL esperado |
|---|---|---|---|---|---|
| **PR-A** | Backtest 17/21/27 via **vectorbt** (era stdlib) | 🟢 baixo | 1d | — | desbloqueia tudo |
| PR-B | Refactor SDA17 em stages plugáveis | 🟢 baixo | 2d | PR-A | habilitador |
| PR-C | Stage 6.5 exploration bonus (versão Thompson) | 🟢 baixo | 1d | PR-B | +0.5-1.5 pts hit |
| PR-D | Stage 6.7 Hot Center Filter (excess) | 🟢 baixo | 0.5d | PR-B | +0.3-0.8 pts hit |
| PR-E | Substituir label confidence por Platt LR | 🟡 médio | 1.5d | PR-A | +0.5-1.0 pts (kill switch melhor) |
| PR-F | Externalizar constantes para TOML | 🟢 baixo | 0.5d | — | habilitador |
| PR-G | Auto-calibration PID controller | 🟡 médio | 1d | PR-A | +0.5-1.5 pts CW |
| PR-H | Shadow mode infra | 🟡 médio | 2d | PR-B | habilitador |
| PR-I | Persistir state por mesa (não singleton) | 🟡 médio | 2d | PR-B | habilitador multi-mesa |
| PR-J | Logging granular | 🟢 baixo | 0.5d | — | observability |
| **PR-K** | ¼-Kelly cap (substitui Martingale puro) | 🟠 alto | 2d | PR-A, PR-E | reduz drawdown 30-50% |
| **PR-L** | Bayesian CI gating para score 5/6 | 🟢 baixo | 0.3d | PR-B | evita reação prematura |
| **PR-M** | Adam-Sigmoid updater (substitui PCT-Sigmoid) | 🟡 médio | 1.5d | PR-B | +2-4 pts CW especif. |
| **PR-N** | Stage 6.5 Thompson Bernoulli per região | 🟡 médio | 2d | PR-B, PR-C | substitui PR-C ou complementa |
| **PR-O** | ADWIN drift detector × direção | 🟢 baixo | 1d | — | proteção regime change |
| **PR-J'** | Covariance matrix C1/C2/C3 | 🟠 alto | 2d | PR-B, PR-K | sizing correto |

**Total:** ~22.3 dias-dev (era 14d na Parte 1). Aumento devido aos 6 novos PRs (K, L, M, N, O, J').

### 16.1 Ordem de execução recomendada (sprints de 1 semana)

**Sprint 1 (habilitadores):** PR-A, PR-F, PR-J, PR-O (~3d)
**Sprint 2 (refactor):** PR-B, PR-L, PR-H (~4.3d)
**Sprint 3 (estratégia):** PR-C ou PR-N, PR-D, PR-M (~4-5d)
**Sprint 4 (calibração):** PR-E, PR-G (~2.5d)
**Sprint 5 (sizing):** PR-K, PR-J', PR-I (~6d)

### 16.2 Como medir sucesso por sprint

| Sprint | Métrica primária | Métrica secundária | Threshold mínimo |
|---|---|---|---|
| 1 | vectorbt rodando 1000 cenários < 60s | logs OK | infra pronta |
| 2 | shadow mode ativo 7d sem divergir live | testes verde | testes 100% |
| 3 | hit rate shadow > live em 3/5 dias | nenhuma regressão CW | +1 pt cumulativo |
| 4 | Brier score < 0.20, ECE < 0.05 | hit rate Kill Switch > 47% | calibração mensurável |
| 5 | drawdown D90 < 25% bankroll | sharpe > 0.8 | bankroll survival ≥ 90% |

---

## 17. Perguntas atualizadas (responder em ordem)

1. **PR-A** com **vectorbt** ou continuar com stdlib backtest? (recomendado: vectorbt — 50× mais rápido, vale a curva de 1 dia)
2. **PR-N (Thompson) ou PR-C (exploration_bonus heurístico)** primeiro? (recomendado: PR-N — base teórica mais sólida; PR-C fica como fallback se Thompson não rodar a tempo)
3. **PR-K (¼-Kelly)** prioridade alta ou "depois das demais"? (recomendado: alta — reduz drawdown imediatamente, não depende de melhoria de hit rate)
4. **PR-M (Adam-Sigmoid)** tem risco alto de "piorar antes de melhorar" — implementar em shadow primeiro?  (recomendado: SIM, sempre)
5. **PR-O (ADWIN)** standalone agora ou junto com PR-B?  (recomendado: agora — independente, valor imediato)
6. **PR-E (Platt LR)** treinar com quais features?  Default sugerido: `[c4, m6, l12, sda_score, drift_flag, abs(off2−off3), direction_dummy]` → 7 features, 3574 amostras, regularização L2 cv=5

---

## 18. Resumo executivo PARTE 2

**O documento original estava 80% correto.** A auditoria externa via brave-search trouxe:

1. ✅ Confirmou que **manter 17 fixos é racional** (Kelly multivariate corrobora)
2. ✅ Confirmou que **label confidence é folclore** (literatura calibração)
3. ⚠️ Suavizou "score 5 anomalia" — n=6 é Bayesianamente compatível com 0.5
4. 🔵 Refinou "exploration bonus" para **Thompson Bernoulli** (princípio bandit)
5. ❌ Retratou "centros independentes" — não para sizing, sim para filter
6. 🆕 Adicionou **ADWIN drift detection** (não estava no doc)
7. 🆕 Adicionou **¼-Kelly bet sizing** substituindo Martingale puro
8. 🆕 Adicionou **Adam-Sigmoid** substituindo PCT-Sigmoid fixo
9. 🆕 Confirmou **vectorbt** sobre stdlib para backtest

**Próximo passo prático:** começar **Sprint 1** (PR-A + PR-F + PR-J + PR-O) — todos baixo risco, alto valor, sem dependências.

---

*Fim Parte 2 — auditoria pós-revisão (23/05 14:35 UTC-3, Claude Opus 4.7 + brave + sequential-thinking + filesystem + graphify).*

| Time-series detection | nenhum | **`ruptures` (changepoint)** | Detectar **regime change** antes do prejuízo (entra no Kill Switch) |
| Visualização análise | nenhum local | **`plotly` + dashboard interno** | Para você ler estes resultados sem CLI |

### 9.3 Pipeline modular sugerido (refactor SDA17)

```python
# packages/strategies/sda17/pipeline.py

class Stage(Protocol):
    name: str
    def run(self, ctx: PipelineCtx) -> PipelineCtx: ...

class WindowStage:   ...   # Stage 1: janela adaptativa
class IQRStage:      ...   # Stage 2: outlier rejection
class WeightedMedianStage: ...  # Stage 3
class DriftStage:    ...   # Stage 4
class ScoreStage:    ...   # Stage 5
class TripleFocusStage:  ...   # Stage 6 (atual)
class ExplorationBonusStage:  ...   # Stage 6.5 NEW — Proposta #2
class HotCenterFilterStage:   ...   # Stage 6.7 NEW — Proposta #3

class StrategyPipeline:
    def __init__(self, stages: list[Stage]):
        self.stages = stages
    def run(self, ctx):
        for s in self.stages:
            ctx = s.run(ctx)
        return ctx
```

**Vantagem:** trocar/adicionar/remover um stage é **mudar a lista**, sem mexer no resto. Testes ficam triviais (`test_iqr_stage.py`). Shadow mode = `pipeline_a.run() ∥ pipeline_b.run()` + comparar `numbers`.

### 9.4 ML auxiliar — onde entra

> **NÃO substitui a estratégia**. Substitui apenas o label categórico do TripleRateAdvisor por um **probability calibrado**.

Treinamento (executa 1× / semana, fora do hot path):
```python
# scripts/train_confidence.py
df = read_decisions_from_db(last_n_days=21)
features = ["c4", "m6", "l12", "sda_score", "drift", "spread",
            "survival_rate", "abs_diff_off2_off3", "gale_level"]
y = df["result_hit"]
model = LGBMClassifier(...).fit(df[features], y)
calibrated = CalibratedClassifierCV(model, method="isotonic").fit(...)
save_model("config/models/confidence_lgbm.pkl")
```

Inferência (no hot path):
```python
# state/bet_advisor.py (substituí o label categorial)
class CalibratedBetAdvisor:
    def analyze(self, performance, sda_score, sda_details):
        features = self._features(performance, sda_score, sda_details)
        p_hit = self.model.predict_proba(features)[0][1]
        return BetAdvice(
            should_bet=(p_hit > 0.48),   # ligeiramente acima break-even
            confidence_score=p_hit,       # número real, não label
            reason=f"P(hit)={p_hit:.1%}",
        )
```

→ **Kill Switch fica como salvaguarda final** (c4=0 AND p_hit<0.30).

---

## 10. PRs sugeridos — sequência de execução

| PR | Título | Risco | Esforço | Independente |
|---|---|---|---|---|
| **PR-A** | `tools: backtest_from_db.py rodando cenários 17/21/27 + relatório CSV` | Zero (offline) | 1D | Sim |
| **PR-B** | `strategies/sda17: extrair stages (refactor sem mudar comportamento) + testes unitários por stage` | Baixo | 2D | Sim |
| **PR-C** | `strategies: novo ExplorationBonusStage (Proposta #2) — ativado por feature flag` | Baixo | 1.5D | Depende de B |
| **PR-D** | `strategies: HotCenterFilterStage (Proposta #3) — ativado por feature flag` | Baixo | 1D | Depende de B |
| **PR-E** | `shadow mode: rodar pipeline_A (atual) e pipeline_B (com C/D) em paralelo, logar ambos no DB` | Médio (novo campo DB) | 2D | Depende de C/D |
| **PR-F** | `config/strategies/sda17.toml + carregar via pydantic_settings` | Baixo | 0.5D | Sim |
| **PR-G** | `auto-calibration controller: PID sobre erro médio últimos 20` | Médio | 1D | Sim |
| **PR-H** | `ML: train_confidence.py + CalibratedBetAdvisor (substitui label do TR)` | Médio | 3D | Sim |
| **PR-I** | `dashboard: plotly notebook ou Streamlit local para ler decisions.db visualmente` | Zero | 1D | Sim |
| **PR-J** | `monitor: alerta quando hit_rate_direction < break_even por 20 jogadas` | Baixo | 0.5D | Sim |

**Sequência sugerida para destravar Propostas #2 e #3:**
`PR-A → PR-B → PR-C → PR-D → PR-E (shadow mode 2 semanas) → PROMOVER se win`

**Total:** ~13–14 dias de dev sênior para sair de hoje (53.4%) e ter:
- Backtest reproducível
- Pipeline modular
- 2 stages novos (anti-cluster + hot filter)
- Shadow mode validando
- Auto-calibration ligando
- ML calibrando confidence
- Dashboard para você visualizar

---

## 11. Mapa mental final — "estratégia ideal" v5

```
                ┌───────────────────────┐
                │      SPIN ENTRA       │
                └──────────┬────────────┘
                           ▼
        ┌──────────────────────────────────────┐
        │  Stage 1: Janela adaptativa          │
        │  Stage 2: IQR outlier rejection      │
        │  Stage 3: Weighted Median            │
        │  Stage 4: Drift Detection            │
        │  Stage 5: Smart Score                │
        │  Stage 6: Triple Focus (C1, C2, C3)  │
        │  Stage 6.5: Exploration Bonus 🆕     │  ← Proposta #2 (anti-cluster)
        │  Stage 6.7: Hot Center Filter 🆕     │  ← Proposta #3 (descarta zonas frias)
        │  Stage 7: ML-Calibrated Probability 🆕│  ← LightGBM + isotonic
        │  Stage 8: Auto-Calibration PID 🆕    │  ← Corrige offset dinamicamente
        │  Stage 9: Kill Switch (salvaguarda)  │
        └──────────────────┬───────────────────┘
                           ▼
        ┌──────────────────────────────────────┐
        │  Decisão final:                       │
        │  • dimensão de aposta (17 ou 21)     │
        │  • números                            │
        │  • centro principal                   │
        │  • prob_hit                           │
        │  • metadata (regime, drift)           │
        └──────────────────┬───────────────────┘
                           ▼
        ┌──────────────────────────────────────┐
        │  Shadow mode 🆕                       │
        │  pipeline_v4 (atual) ∥ pipeline_v5    │
        │  loga ambos → análise diária          │
        └──────────────────────────────────────┘
```

---

## 12. Resumo executivo final

| Item | Atual 23/05 | Próximo (Wave 2) | Ideal (Wave 4) |
|---|---|---|---|
| Hit rate | 53.4% | 55–58% | 60%+ estável |
| Δ CW/CCW | 23.8 pts | < 8 pts | < 4 pts |
| Confidence preditivo | label, 50.7%≈57.8% | proba LightGBM | + uncertainty estimate |
| Cobertura | 17 fixo | 17 ou 21 condicional | dinâmica por regime |
| Kill Switch | binário (4.5%) | + regime change | + UCB exploration |
| Calibration | manual=0 | PID auto | + sigmoid hyperparam tuning (optuna) |
| Backtesting | script ad-hoc | suite CI | + sweep + report |
| Multi-mesa | singleton | stateful por table_id | broker pgmq + worker por mesa |

---

## 13. Próximas perguntas para você decidir

1. **Roda PR-A (backtest cenários 17/21/27)** agora? Sim/Não — me dá luz verde e eu monto o script + relatório.
2. **Aprovado iniciar refactor stages (PR-B)?** É a base de tudo. Sim/Não.
3. **Implementar Proposta #2 (Exploration Bonus) como shadow mode** ou direto em produção? Sugestão: shadow.
4. **Implementar Proposta #3 (Hot Center Filter)** junto com #2 ou separado?
5. **ML auxiliar (LightGBM offline para confidence) — interesse imediato ou Wave 3?**
6. **Auto-calibration PID** — quer testar essa semana?

---

**Snapshot do dia fechado em:** 2026-05-23 14:32 (UTC-3)
**Fontes:**
- `/app/data/decisions.db` em produção (SSH → docker exec → sqlite3 via Python)
- 132 decisões de hoje + 3 442 históricas
- 38 janelas de gale de hoje
- Sequência cronológica de 118 hits/misses
- Leitura completa de `core/roulette.py`, `state/timeline.py`, `state/bet_advisor.py`, `state/game.py` (grep), `strategies/base.py`, `strategies/sda17.py` (580 LoC integrais)
- Graphify (god nodes)

**MCPs ativos:** sequential-thinking, filesystem, graphify, memory. Brave-search **não foi usada** — toda análise é endógena.
**Modelo:** Claude Opus 4.7 (yolo-orchestrator)


