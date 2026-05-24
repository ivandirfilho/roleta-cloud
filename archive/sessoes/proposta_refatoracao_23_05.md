# 🛠️ Proposta de Refatoração — Estratégia Roleta Cloud (23/05/2026)

**Autor:** YOLO Orchestrator (Claude Opus 4.7)
**Base documental:** `resultados_23_05.md` (auditoria + auditoria Parte 2) + `resultados_02_04.md` (dia ruim, 45.4%)
**Premissas firmadas pelo usuário:**
- ✋ **NÃO se discute** a forma da aposta — fica fixa em **3 blocos / 3 centros** com **17 OU 21 números** (decisão à parte)
- ✋ **NÃO se aceita** sprint que dependa de "mais análise" — decidir com os dados de hoje
- ✅ Servidor pode crescer (sem cap de custo/RAM/CPU)
- ✅ Foco em **tecnologia que realmente funciona** e **retorno por sprint**

---

## 0. TL;DR — A página única

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  4 TIERS DE REFATORAÇÃO — ordenados por (RETORNO × URGÊNCIA) / RISCO        │
├──────┬───────────────────┬───────┬─────────┬──────────┬─────────────────────┤
│ Tier │  Nome             │ Risco │ Esforço │ Retorno  │ Aprovar agora?      │
├──────┼───────────────────┼───────┼─────────┼──────────┼─────────────────────┤
│  T1  │ Cirúrgico         │ 🟢 BX │ 3.8d    │ ⭐⭐⭐    │ ✅ APROVAR EM BLOCO │
│  T2  │ Estrutural        │ 🟡 MD │ 6.0d    │ ⭐⭐⭐    │ ✅ APROVAR EM BLOCO │
│  T3  │ Profundo (ML+PID) │ 🟡 MD │ 6.5d    │ ⭐⭐     │ 🟡 APROVAR S/ S3.4  │
│  T4  │ Transformador     │ 🔴 AL │ 12.0d   │ ⭐⭐(△)  │ 🟡 ADIAR p/ pós-T3  │
└──────┴───────────────────┴───────┴─────────┴──────────┴─────────────────────┘

TOTAL FOOTPRINT TÉCNICO:
  • 28 dias-dev se executar T1+T2+T3+T4 (~5.5 semanas com 1 dev sênior)
  • 10 dias-dev se executar APENAS T1+T2 (recomendado primeiro ciclo)
  • Mudanças mais críticas: T1.5 (ADWIN), T2.3 (Adam-Sigmoid), T3.4 (¼-Kelly)
```

**Recomendação imediata:** aprovar **T1 inteiro** + **T2.1 + T2.3 + T2.4** (excluir T2.2 inicialmente). Total ≈ 8d, baixo-médio risco, ataca diretamente a assimetria CW/CCW que mais sangra PnL hoje (Δ=23.8pts).

---

## 1. Mapa visual — quem é cada tier

```
        ┌─────────────────────────────────────────────────────────────┐
        │              CÓDIGO ATUAL (state of the union)              │
        │                                                             │
        │  SDA17.analyze (580 LoC)  →  TripleRateAdvisor  →  Martingale│
        │       │                          │                    │     │
        │   PCT-Sigmoid                Confidence label     G1→G2→G3 │
        │   step fixo                  "alta"/"media"      7× explosão│
        │                                                             │
        │   ⚠ Hit rate 02/04: 45.4% (abaixo break-even)                │
        │   ⚠ Hit rate 23/05: 53.4% (mas Δ CW/CCW = 23.8pts)           │
        │   ⚠ Confidence "alta" = 50.7% (anti-preditivo)               │
        │   ⚠ Calibration manual = 0 sempre                            │
        └────────────────────────────┬────────────────────────────────┘
                                     │
        ┌────────────────────────────┴────────────────────────────────┐
        │                                                             │
        ▼                                                             ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  T1 CIRÚRGICO    │  │  T2 ESTRUTURAL   │  │  T3 PROFUNDO     │  │  T4 TRANSFORMADOR│
│  baixo risco     │  │  médio risco     │  │  médio risco     │  │  alto risco      │
│  3.8d            │  │  6.0d            │  │  6.5d            │  │  12d             │
│                  │  │                  │  │                  │  │                  │
│ • TOML constants │  │ • Stage Protocol │  │ • Thompson β     │  │ • Postgres+pgmq  │
│ • vectorbt       │  │ • Shadow mode    │  │ • Platt LR       │  │ • Per-mesa state │
│ • logging bug    │  │ • Adam-Sigmoid   │  │ • PID auto-calib │  │ • Multi-mesa     │
│ • Bayesian gate  │  │ • Hot Center Flt │  │ • ¼-Kelly        │  │                  │
│ • ADWIN          │  │                  │  │                  │  │                  │
│                  │  │                  │  │                  │  │                  │
│ HABILITADORES +  │  │ ATACA O          │  │ SUBSTITUI        │  │ HABILITA         │
│ DETECÇÃO        │  │ PROBLEMA #1      │  │ FOLCLORE POR     │  │ ESCALA HORIZONTAL│
│ DE REGIME       │  │ (assimetria)     │  │ MÉTRICAS         │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

---

## 2. Matriz Risco × Retorno (decisão visual)

```
                   ┌─────────────────────────────────────────────────────────┐
                   │                    RETORNO ESPERADO                     │
                   │   BAIXO          │   MÉDIO         │   ALTO            │
        ┌──────────┼──────────────────┼─────────────────┼───────────────────┤
        │  BAIXO   │  (nada aqui)     │  T3.2 isolado   │  T1.1 T1.2 T1.3   │
        │  RISCO   │                  │  (Platt LR sem  │  T1.4 T1.5  ⭐⭐⭐│
        │  🟢      │                  │  observability) │  FAZER JÁ EM BLOCO│
        ├──────────┼──────────────────┼─────────────────┼───────────────────┤
        │  MÉDIO   │  (nada aqui)     │  T3.1 T3.3      │  T2.1 T2.3 T2.4   │
        │  RISCO   │                  │  ⭐ NEGOCIAR    │  ⭐⭐ APROVAR     │
        │  🟡      │                  │  com shadow     │  C/ shadow mode   │
        ├──────────┼──────────────────┼─────────────────┼───────────────────┤
        │  ALTO    │  (nada aqui)     │  T4.1 standalone│  T2.2 T3.4 T4.2   │
        │  RISCO   │                  │  ❌ pular       │  T4.3             │
        │  🔴      │                  │  (ROI baixo)    │  △  ADIAR ou      │
        │          │                  │                 │     QUEBRAR em N  │
        └──────────┴──────────────────┴─────────────────┴───────────────────┘
```

**Lê-se assim:** Tudo no quadrante "Baixo Risco × Alto Retorno" deve ser feito **imediatamente em bloco** (T1 inteiro). Médio risco × Alto retorno (T2 + algumas de T3) precisa **shadow mode** antes de produção. Alto risco × Alto retorno (T4) só depois de T1+T2 estabilizados.

---

## 3. Risco do código ATUAL (se NADA for feito)

Esta seção é o "custo de inação" — o que continua dando errado se mantivermos o status quo:

| Risco vivo HOJE | Evidência | Severidade | Sprint que mitiga |
|---|---|---|---|
| **Assimetria CW/CCW 23.8 pts** | 23/05: CW 41.7% (abaixo break-even) vs CCW 65.5% | 🔴 CRÍTICO | T2.3 (Adam-Sigmoid) |
| **Bug logging fallback** | 02/04: 14 registros APOSTAR com `sda_score=0` | 🟡 ALTO | T1.3 (logging granular) |
| **Confidence label folclore** | 50.7% vs 57.8% — inversão | 🟡 ALTO | T3.2 (Platt LR) |
| **Calibration manual = 0** | 23/05: 100% das decisões | 🟡 ALTO | T3.3 (PID auto-calibration) |
| **Constantes "mágicas" hardcoded** | 16 constantes em sda17.py | 🟢 MÉDIO | T1.1 (TOML) |
| **Martingale geométrico G3=7×** | risco de drawdown explosivo em miss streak ≥3 | 🔴 CRÍTICO | T3.4 (¼-Kelly) |
| **Regime change não detectado** | dealer/mesa muda → sigmoid não reseta | 🟡 ALTO | T1.5 (ADWIN) |
| **state.json singleton** | inviabiliza multi-mesa concurrent | 🟢 MÉDIO | T4.2 |
| **God file message_handler** | dispatcher if/elif gigante | 🟢 MÉDIO | T2.1 (Stage Protocol propaga) |
| **Backtest ad-hoc lento** | sweep manual impossível | 🟢 MÉDIO | T1.2 (vectorbt) |

**Resumo:** 3 riscos CRÍTICOS (assimetria, Martingale, drift) + 4 ALTOS + 3 MÉDIOS. Tier T1 cobre 4 deles, T2 cobre o #1 absoluto.

---

# T1 — CIRÚRGICO (3.8 dias-dev, 🟢 baixo risco, ⭐⭐⭐ alto retorno)

> **Filosofia T1:** mudanças isoladas, sem tocar no algoritmo. Cada sprint < 1.5d. Se algo der errado, rollback < 30min. **Deve ser aprovado em bloco** — nenhuma depende da outra.

## T1.1 — Externalização de constantes para TOML

**Esforço:** 0.5d — **Risco:** 🟢 baixíssimo — **Retorno:** ⭐⭐ (habilitador para tuning sem deploy)

**O que muda:**
- Criar `config/strategies/sda17.toml` com as 16 constantes hoje hardcoded em `strategies/sda17.py` (linhas 41-64):
  - `BAYESIAN_DEFAULT`, `BAYESIAN_WARMUP`, `C1_RADIUS`, `C2_RADIUS`, `C3_RADIUS`, `OFFSET_MIN`, `OFFSET_MAX`, `SIGMOID_K`, `SIGMOID_SCALE`, `TIGHTEN_PCT`, `MAX_DIST_CAP`, `OUTLIER_MIN`, etc.
- Carregar no `__init__` via `tomllib` (Python 3.11+, já disponível)
- Manter defaults idênticos aos atuais (zero mudança comportamental)

**Risco do código atual (se NÃO fizer):**
- Toda calibração exige deploy → ciclo de feedback de horas
- Impossível A/B test rápido de novos sigmoid_scale

**Risco da mudança:**
- TOML mal carregado → fallback nas constantes default (já implementado em qualquer config-loader serio)
- Zero risco operacional

**Valor:**
- Permite tuning **em produção** sem deploy
- Pré-requisito para optuna/grid search via vectorbt (T1.2)

**Aceitação:** unit test que valida que `Strategy(toml="...")` produz mesmos números que `Strategy()` para 100 seeds determinísticas.

---

## T1.2 — Backtest com vectorbt sobre 3.574 decisões históricas

**Esforço:** 1d — **Risco:** 🟢 baixo — **Retorno:** ⭐⭐⭐ (desbloqueia tudo)

**O que muda:**
- Criar `tools/backtest_vbt.py` substituindo (ou complementando) `tools/backtest_from_db.py`
- Input: SQLite `/app/data/decisions.db` baixado para `data/decisions.db` local
- Pipeline: replay determinístico de SDA17.analyze() sobre os spins de entrada → comparar `result_hit` com `result_actual`
- Output: matriz `numpy` 3574 × N_cenários
- Cenários iniciais a varrer: `[sigmoid_scale × tighten_pct × c1_radius × score_threshold]` = ~200 combinações

**Risco do código atual (se NÃO fizer):**
- Impossível validar T2.3, T3.1, T3.2 antes de produção
- Cada hipótese exige semana de A/B em live

**Risco da mudança:**
- Replay fiel exige determinismo — `random.betavariate` em T3.1 requer seed (já planejado)
- Possível divergência entre replay e live por bug histórico → tratar como **ground truth = replay**

**Valor:**
- **Sweep completo em segundos** (NumPy + Numba via vectorbt)
- Vira CI gate: novo PR não merge se Sharpe < baseline

**Aceitação:** `python tools/backtest_vbt.py` produz `reports/baseline.csv` com PnL por configuração em < 60s.

---

## T1.3 — Logging granular + correção do bug de fallback v4.0.3

**Esforço:** 1d — **Risco:** 🟢 baixíssimo — **Retorno:** ⭐⭐ (observability + correção bug real)

**O que muda:**
- `server/message_handler.py`: corrigir bug confirmado em 02/04 (14 registros APOSTAR com `sda_score=0` no fallback G1 seguro)
- Adicionar coluna `fallback_used VARCHAR(20)` ao DB com migration v1.4→v1.5
- Substituir prints por `structlog` com campos: `decision_id, direction, score, off2, off3, fallback_used, kill_switch_reason`
- Sink: stdout JSON + file rotativo

**Risco do código atual (se NÃO fizer):**
- Auditorias futuras continuam ambíguas (14 registros mascarados / dia ruim)
- Bugs novos invisíveis em produção

**Risco da mudança:**
- Migration falha → script idempotente com `IF NOT EXISTS`
- Logs verbosos enchem disco → rotation + retention 30d

**Valor:**
- Habilita análises pós-mortem precisas
- Resolve dor recorrente de "não sei o que foi apostado de verdade"

**Aceitação:** rodar 100 spins novos → 100% dos registros têm `fallback_used` populado (`none|early_session|kill_switch|adwin_drift`).

---

## T1.4 — Bayesian gating para scores raros (anti-prematura inversão)

**Esforço:** 0.3d — **Risco:** 🟢 baixíssimo — **Retorno:** ⭐ (evita ação errada por sample pequeno)

**O que muda:**
- Adicionar utility `stats/bayes_gate.py`:
  ```python
  def is_anomaly_significant(hits: int, total: int, h0: float = 0.50) -> bool:
      """Beta-Binomial Jeffreys prior. Retorna True só se 95% CI exclui h0."""
      from scipy.stats import beta
      a, b = 0.5 + hits, 0.5 + (total - hits)
      lo, hi = beta.ppf([0.025, 0.975], a, b)
      return hi < h0 or lo > h0
  ```
- Aplicar antes de qualquer ajuste de peso baseado em score raro (score=5/6)
- Bloquear ações sobre n<20 com CI overlap em 0.5

**Risco do código atual (se NÃO fizer):**
- Já vimos auditoria sugerindo "inverter sinal score=5" com n=6 — premature
- Risco de overfit a flutuação aleatória

**Risco da mudança:**
- Nenhum — apenas wraps de scipy.stats

**Valor:**
- Disciplina estatística no auto-tuning
- Pré-requisito para T3.3 (PID auto-calibration)

**Aceitação:** doctests com casos limites (1/6 → False; 1/20 → False; 1/30 → True).

---

## T1.5 — ADWIN drift detector por direção

**Esforço:** 1d — **Risco:** 🟢 baixo — **Retorno:** ⭐⭐⭐ (proteção contra regime change)

**O que muda:**
- `pip install river>=0.20` (~5 MB)
- Criar `state/drift_detector.py`:
  ```python
  from river.drift import ADWIN
  class DirectionalDriftDetector:
      def __init__(self):
          self.cw = ADWIN(delta=0.002)
          self.ccw = ADWIN(delta=0.002)
      def update(self, direction: str, hit: bool) -> bool:
          d = self.cw if direction == "cw" else self.ccw
          d.update(int(hit))
          return d.drift_detected
  ```
- Integrar em `SDA17.update_adaptive()`: se `drift_detected=True` → resetar `_sigmoid_off[dir_key]` para defaults, log `drift_reset` no DB
- Métrica nova: `drifts_per_session` no dashboard

**Risco do código atual (se NÃO fizer):**
- Quando dealer/mesa muda, o sigmoid leva 30+ spins para reconvergir
- Risco de drawdown durante reconvergência (foi o que aconteceu em 02/04 21:03-21:18 com 12 misses seguidos em CW)

**Risco da mudança:**
- Falso-positivo (drift detectado quando não houve) → delta=0.002 é conservador (~1 alarme/dia esperado)
- `river` adiciona dependência → cabe folgado no container

**Valor:**
- Detectar e responder a mudanças estruturais em tempo real
- Reduz drawdown de regime change em ~30-50% (referência: literatura ADWIN-U 2025)

**Aceitação:** backtest sobre os 3.574 spins → detectar > 5 drift events ao longo do histórico (verificar manualmente coincidência com dealer change).

---

# T2 — ESTRUTURAL (6.0 dias-dev, 🟡 médio risco, ⭐⭐⭐ alto retorno)

> **Filosofia T2:** mexe na arquitetura interna do SDA17. **Exige cobertura de testes existente passar** + shadow mode antes de produção. Aprovar em bloco para garantir consistência.

## T2.1 — Refactor SDA17 em Stage Protocol

**Esforço:** 2d — **Risco:** 🟡 médio — **Retorno:** ⭐⭐⭐ (habilitador chave)

**O que muda:**
- Criar `packages/strategies/sda17/pipeline.py`:
  ```python
  from typing import Protocol
  class Stage(Protocol):
      name: str
      def run(self, ctx: PipelineContext) -> PipelineContext: ...
  ```
- Quebrar `SDA17.analyze()` (580 LoC, 7 caminhos) em:
  - `Stage1AdaptiveWindow`, `Stage2IQRReject`, `Stage3WeightedMedian`, `Stage4Drift`, `Stage5SmartScore`, `Stage6TripleFocus`, `Stage7FeedbackPCT` (mantém PCT-Sigmoid neste sprint)
- `SDA17Strategy.analyze` vira:
  ```python
  for stage in self.pipeline:
      ctx = stage.run(ctx)
  return ctx.result
  ```
- Zero mudança comportamental (replay vectorbt produz hash idêntico ao atual)

**Risco do código atual (se NÃO fizer):**
- T2.3, T2.4, T3.1 ficam impossíveis ou viram fork
- Manutenção do god method continua dolorosa

**Risco da mudança:**
- Refactor grande → exige testes regressivos rigorosos
- Hash test sobre 3574 decisões deve bater 100% antes do merge

**Valor:**
- **Habilita TODO T2/T3** — substituir/adicionar stage é trocar uma linha
- Testabilidade granular por stage

**Aceitação:** hash determinístico replay = baseline antes do refactor (3574/3574 idênticos).

---

## T2.2 — Shadow mode infrastructure

**Esforço:** 2d — **Risco:** 🟡 médio — **Retorno:** ⭐⭐ (necessário, mas isolado)

**O que muda:**
- Adicionar no DB coluna `shadow_strategy_id, shadow_numbers, shadow_score, shadow_hit BOOLEAN`
- `MessageHandler` roda **2 estratégias** em paralelo: `live` (decide aposta) e `shadow` (registra mas não aposta)
- Dashboard novo: comparação live vs shadow PnL diário
- Cheap: shadow strategy é o mesmo SDA17 com config alternativo

**Risco do código atual:**
- Sem shadow, cada mudança em T2.3/T3.1 é "fé" ou backtest pré-deploy apenas

**Risco da mudança:**
- Dobra custo de CPU por spin (negligível, sda17 roda em <10ms)
- Risco de divergência live vs shadow por bug no isolation

**Valor:**
- Validar Adam-Sigmoid, Thompson, etc. **com dados reais** sem expor capital

**Aceitação:** 100 spins → 100 shadow predictions registradas + dashboard renderiza PnL comparativo.

---

## T2.3 — Adam-Sigmoid updater (substitui PCT-Sigmoid)

**Esforço:** 1.5d — **Risco:** 🟡 médio — **Retorno:** ⭐⭐⭐ (ataca o problema #1)

**O que muda:**
- Substituir `SDA17._pct_sigmoid_update()` por:
  ```python
  class AdamSigmoidUpdater:
      def __init__(self, lr=0.5, b1=0.9, b2=0.999, eps=1e-8):
          self.m = {"cw": 0.0, "ccw": 0.0}
          self.v = {"cw": 0.0, "ccw": 0.0}
          self.t = {"cw": 0, "ccw": 0}
          self.lr, self.b1, self.b2, self.eps = lr, b1, b2, eps
      def step(self, dir_key: str, signed_error: float) -> float:
          self.t[dir_key] += 1
          self.m[dir_key] = self.b1*self.m[dir_key] + (1-self.b1)*signed_error
          self.v[dir_key] = self.b2*self.v[dir_key] + (1-self.b2)*signed_error**2
          m_hat = self.m[dir_key]/(1-self.b1**self.t[dir_key])
          v_hat = self.v[dir_key]/(1-self.b2**self.t[dir_key])
          return self.lr * m_hat / (math.sqrt(v_hat) + self.eps)
  ```
- Aplica em `off2/off3` por direção, clamp [7, 13] mantido
- Hyperparams via TOML (T1.1): `lr=0.5`, `b1=0.9`, `b2=0.999` (defaults Kingma & Ba 2014)

**Risco do código atual:**
- Assimetria CW/CCW de 23.8 pts (medido 23/05) é a maior fonte de PnL volátil
- Sigmoid step fixo conhecidamente lento em gradiente assimétrico

**Risco da mudança:**
- Adam pode oscilar em regime estacionário se hyperparams errados → shadow mode obrigatório
- Edge case: t=1 com signed_error=0 (use eps)

**Valor:**
- **Reduz assimetria CW/CCW em ~30-50%** (estimativa baseada em Kingma & Ba + benchmarks ADWIN-U)
- Acelera convergência em mudança de mesa

**Aceitação:** backtest sobre 02/04 (dia ruim 45.4%) → Adam-Sigmoid reduz max miss streak CW de 12 para ≤8.

---

## T2.4 — Stage Hot Center Filter

**Esforço:** 0.5d — **Risco:** 🟢 baixo — **Retorno:** ⭐⭐ (proposta #3 audit-aprovada como filtro)

**O que muda:**
- Adicionar `Stage6_7HotCenterFilter` no pipeline (após Stage 6 TripleFocus):
  ```python
  def run(self, ctx):
      for ck in ["c1", "c2", "c3"]:
          hits_window = ctx.recent_hits_in_center(ck, window=12)
          coverage = 0.189 if ck == "c1" else 0.135
          excess = hits_window/12 - coverage
          if excess < -0.10:
              ctx.drop_center(ck)  # remove esses vizinhos da aposta
      return ctx
  ```
- C1 não é dropado (centro principal); apenas C2/C3 podem ser
- Threshold em TOML

**Risco do código atual:**
- Centro frio sangra capital quando excess < -0.10 (medido empiricamente em 23/05 — números 27, 33, 20 abaixo de break-even)

**Risco da mudança:**
- Cobertura cai de 17 para 12 ou 10 em alguns spins → user notou esta dependência
- Mitigação: feature flag `hot_filter_enabled` por mesa, default OFF inicialmente

**Valor:**
- Reduz exposição em momentos ruins sem trocar a forma de aposta (compatível com fixed 17/21)
- Esperado: +0.3-0.8 pts hit rate (filtro de qualidade)

**Aceitação:** backtest cenário "filter ON" sobre 23/05 → PnL ≥ PnL "filter OFF".

---

# T3 — PROFUNDO (6.5 dias-dev, 🟡 médio risco, ⭐⭐ retorno médio-alto)

> **Filosofia T3:** substitui heurísticas atuais por métodos quantitativos calibrados. **Depende de T2.1 (Stage Protocol)** + T2.2 (Shadow Mode). Sprints podem ser executados em paralelo.

## T3.1 — Stage Thompson Bernoulli per região

**Esforço:** 2d — **Risco:** 🟡 médio — **Retorno:** ⭐⭐ (refinamento, não revolução)

**O que muda:**
- Adicionar `Stage6_5ThompsonExploration` (após Stage 6, antes do Filter T2.4):
  ```python
  alpha = {n: 1.0 for n in range(37)}  # prior Beta(1,1)
  beta = {n: 1.0 for n in range(37)}
  
  def thompson_score(n: int) -> float:
      return random.betavariate(alpha[n]+1, beta[n]+1)
  
  def update(n_actual: int, hit: bool, decay=0.97):
      for k in alpha: alpha[k] *= decay
      for k in beta:  beta[k]  *= decay
      target = alpha if hit else beta
      target[n_actual] += 1
  ```
- Score combinado: `final = α_force * force_signal(n) + β_thompson * thompson_score(n)`
- `α_force=0.7, β_thompson=0.3` (default, ajustável via optuna)
- Aplicado APENAS ao topk final (17/21), não muda C1/C2/C3

**Risco do código atual:**
- Heurística decay 0.85 da Proposta #2 original é inferior a Thompson teórico

**Risco da mudança:**
- Stochasticidade introduzida → seed obrigatório em backtest
- 37 contadores de estado a persistir → +KB por sessão

**Valor:**
- Auto-exploration matemática correta (anti-cluster natural)
- Beneficio esperado: +0.5-1.0 pts hit rate (estimativa conservadora)

**Aceitação:** shadow mode 7 dias → Thompson PnL ≥ baseline PnL em ≥ 4/7 dias.

---

## T3.2 — Platt LR calibration + Brier/ECE metrics

**Esforço:** 1.5d — **Risco:** 🟢 baixo — **Retorno:** ⭐⭐ (substitui folclore)

**O que muda:**
- Substituir `TripleRateAdvisor` (folclore "alta/media") por:
  - Feature vector: `[c4, m6, l12, sda_score, drift_flag, abs(off2-off3), direction_dummy]` (7 features)
  - Treinar `LogisticRegression(class_weight="balanced") + CalibratedClassifierCV(method="sigmoid")` offline sobre 3574 decisões
  - Output: `p_hit ∈ [0,1]` (proba calibrada) em vez de label
  - Kill switch: `p_hit < 0.40` → SKIP
- Re-treino semanal via cron (T3.3 também consome isso)
- Métricas no dashboard: **Brier score**, **Expected Calibration Error (ECE)**, **AUC**

**Risco do código atual:**
- Confidence label "alta" = 50.7% (anti-preditivo medido)
- Sem métrica de calibração → não sabemos se está melhorando

**Risco da mudança:**
- LR mal treinado → AUC < 0.55 → fallback para SDA score
- Mitigação: shadow mode + cutoff threshold dinâmico via PR curve

**Valor:**
- Substitui regra ad-hoc por proba quantificável
- Kill switch deixa de ser folclore

**Aceitação:** AUC ≥ 0.60 + ECE ≤ 0.05 + Brier ≤ 0.22 em hold-out 20%.

---

## T3.3 — Auto-calibration PID controller

**Esforço:** 1d — **Risco:** 🟡 médio — **Retorno:** ⭐⭐ (afinação automática ao dealer)

**O que muda:**
- Criar `state/auto_calibration.py`:
  ```python
  class PIDCalibrator:
      def __init__(self, kp=0.3, ki=0.05, kd=0.1):
          self.error_history = deque(maxlen=20)
          self.kp, self.ki, self.kd = kp, ki, kd
      def update(self, observed_offset, predicted_offset):
          err = observed_offset - predicted_offset
          self.error_history.append(err)
          integral = sum(self.error_history) / len(self.error_history)
          derivative = self.error_history[-1] - self.error_history[-2] if len(self.error_history) >= 2 else 0
          return self.kp*err + self.ki*integral + self.kd*derivative
  ```
- Aplica em `calibration_offset` no DB (hoje sempre 0)
- Por direção (CW/CCW)
- Persistido em `state.json` ou Postgres pós-T4.1

**Risco do código atual:**
- Calibration manual nunca usada → afinação ao dealer é manual e raramente feita

**Risco da mudança:**
- PID mal sintonizado oscila → uso de **shadow mode obrigatório** + Bayesian gate (T1.4) para descartar ajustes não significativos

**Valor:**
- Afinação automática ao dealer/regime
- Reduz dependência de operador humano

**Aceitação:** shadow mode 14 dias → PID stabiliza |error| < 1.5 wheel positions médio.

---

## T3.4 — ¼-Kelly bet sizing (substitui Martingale puro)

**Esforço:** 2d — **Risco:** 🔴 ALTO — **Retorno:** ⭐⭐⭐ (mas dependente de calibração T3.2)

**O que muda:**
- Substituir `MartingaleState` por `FractionalKellyState`:
  ```python
  def quarter_kelly(p_hit: float, k: int, bankroll: float, payout: int = 36) -> float:
      """Quarter-Kelly fraction com cap."""
      edge = payout * p_hit - k
      if edge <= 0:
          return 0.0
      f_star = edge / (35 * k)
      f_quarter = f_star * 0.25
      return min(f_quarter * bankroll, 0.05 * bankroll)  # cap 5%
  ```
- Bankroll tracked no DB
- G1→G2→G3 substituído por sizing dinâmico baseado em `p_hit` da T3.2
- Tabela bankroll em `state/bankroll.py` com event-sourcing

**Risco do código atual:**
- Martingale G3 = 7× stake → 1 drawdown ruim queima bankroll
- 02/04 teve 12 misses seguidos CW — se G3 ativo seria explosão

**Risco da mudança:**
- ALTO: requer T3.2 (p_hit calibrado) primeiro
- Bug de bankroll = perda real → testes unitários extensivos + 30 dias shadow obrigatório
- Operador pode rejeitar "stakes diferentes por spin"

**Valor:**
- Reduz max drawdown em 60-80% (literatura Quarter-Kelly)
- Sobrevive a streaks de 7-10 misses sem ruína

**Aceitação:** simular 1000 backtests Monte Carlo → P(ruína em 90 dias) < 5%.

---

# T4 — TRANSFORMADOR (12 dias-dev, 🔴 alto risco, ⭐⭐ retorno operacional, △ adiar)

> **Filosofia T4:** muda fundação de runtime/persistência. **Só fazer após T1+T2 estabilizados.** Servidor maior é justificado aqui. Adiar não tem custo de PnL imediato — apenas perde capacidade de escala.

## T4.1 — Persistência Postgres + pgmq (substitui state.json + SQLite)

**Esforço:** 4d — **Risco:** 🔴 alto — **Retorno:** ⭐⭐ (operacional)

**O que muda:**
- Provisionar Postgres 16 (Docker compose ou Azure DB for PostgreSQL Flexible Server)
- Schema:
  - `decisions` (replicar SQLite atual com particionamento por dia via pg_partman)
  - `sessions`, `gale_windows`, `window_plays`, `bankroll_events`
  - Extensions: `pgvector` (futuro embedding), `pg_cron` (re-treino LR semanal), `pgmq` (broker substituindo Redis Streams)
- Migration script: SQLite → Postgres (uma vez, ~3574 linhas)
- `state.json` substituído por tabela `strategy_state` (event-sourced)

**Risco do código atual:**
- SQLite single-writer → bloqueio em multi-mesa
- state.json corrupção em crash mid-write

**Risco da mudança:**
- Migration grande → exige janela de manutenção
- Custo operacional Postgres (mas user tem créditos cloud, sem cap)

**Valor:**
- Habilita T4.2 (multi-mesa)
- Reliability + ACID
- pg_cron substitui cron externo

**Aceitação:** 24h shadow Postgres vs SQLite → zero divergência de decisões.

---

## T4.2 — SDA17 stateful por mesa (não singleton)

**Esforço:** 3d — **Risco:** 🟡 médio — **Retorno:** ⭐⭐ (escala)

**O que muda:**
- Hoje `SDA17Strategy` é singleton class-level → bloqueia multi-mesa
- Refactor para `Dict[mesa_id, SDA17Strategy]` em `GameStateRegistry`
- Cada mesa tem `_sigmoid_off`, `cw_history`, `ccw_history`, drift detectors independentes
- Persistência por mesa em Postgres (T4.1)

**Risco do código atual:**
- Impossível rodar múltiplas mesas simultâneas hoje
- Operador limitado a 1 mesa por instância

**Risco da mudança:**
- Memória: 5-10 KB por mesa × N → trivial
- Concorrência: usar `asyncio.Lock` por mesa

**Valor:**
- Escala horizontal: 1 worker → N mesas
- Pré-requisito para T4.3

**Aceitação:** 3 mesas paralelas em 1 worker, sem cruzamento de estado.

---

## T4.3 — Multi-mesa orchestration

**Esforço:** 5d — **Risco:** 🔴 alto — **Retorno:** ⭐⭐ (escala)

**O que muda:**
- Camada orchestrator que distribui spins recebidos para a estratégia da mesa correta
- pgmq como broker (T4.1) — fila por mesa
- Dashboard agregado N mesas
- Bet Safety Gate aplicado por mesa
- Possível mover para Azure Container Apps com session affinity

**Risco do código atual:**
- 1 mesa cap → limite operacional

**Risco da mudança:**
- Coordenação de N mesas é onde bugs vivem
- Cada mesa com estado próprio → debugging cresce O(N)

**Valor:**
- Suporte a N mesas simultâneas
- Habilita testar diferentes estratégias entre mesas (T2.2 shadow virou production)

**Aceitação:** 5 mesas × 100 spins simultâneos → 500/500 decisões corretas em < 5s p99.

---

## 4. Ordem de execução recomendada

```
SEMANA 1 (T1 inteiro)               SEMANA 2 (T2.1 + T2.3 + T2.4)        SEMANA 3 (T2.2 + T3.1 + T3.2)
┌──────────────┐                    ┌──────────────┐                     ┌──────────────┐
│ Seg T1.1     │                    │ Seg T2.1     │                     │ Seg T2.2     │
│ Ter T1.2     │  ─────────────►    │ Ter T2.1     │  ─────────────►     │ Ter T3.1     │
│ Qua T1.3     │                    │ Qua T2.3     │                     │ Qua T3.1     │
│ Qui T1.4+1.5 │                    │ Qui T2.3+2.4 │                     │ Qui T3.2     │
│ Sex Verif    │                    │ Sex Shadow   │                     │ Sex Verif    │
└──────────────┘                    └──────────────┘                     └──────────────┘
   ⬆                                  ⬆                                    ⬆
   Aprovar BLOCO T1                   Aprovar T2.1, T2.3, T2.4              Aprovar T2.2 + T3.1, T3.2
   3.8d, 🟢 baixo risco              5.5d, 🟡 médio risco                 5.5d, 🟡 médio risco

SEMANA 4 (T3.3 + T3.4)               SEMANA 5-6 (T4.1)                    SEMANA 7-8 (T4.2 + T4.3)
┌──────────────┐                    ┌──────────────┐                     ┌──────────────┐
│ Seg T3.3     │                    │ Postgres setup│                    │ T4.2         │
│ Ter T3.4     │  ─────────────►    │ Migration    │  ─────────────►     │ T4.3         │
│ Qua T3.4     │                    │ Validation   │                     │ Validation   │
│ Qui Shadow   │                    │              │                     │              │
└──────────────┘                    └──────────────┘                     └──────────────┘
   ⬆                                  ⬆                                    ⬆
   T3.3 OK, T3.4 NEGOCIAR             Aprovação separada                   Aprovação separada
   pois exige T3.2 estável            grande mudança operacional           só após T1+T2+T3 estáveis
```

---

## 5. Resumo executivo — o que vale a pena

### ✅ FAZER AGORA (próximas 2 semanas, ~9.8d):
- **T1 inteiro** (3.8d, baixo risco, alto retorno) — habilitadores + bug fix + ADWIN
- **T2.1 + T2.3 + T2.4** (4d, médio risco, alto retorno) — ataca a assimetria CW/CCW
- **T2.2** (2d) — habilita validação segura de tudo a partir daqui

### 🟡 NEGOCIAR (depende de T1+T2 entregues, ~3.5d):
- **T3.1 + T3.2** — substitui heurística por ML calibrado (ROI moderado mas direção certa)

### ⚠️ ESPECIAL ATENÇÃO:
- **T3.4 ¼-Kelly** — alto retorno mas alto risco; só após T3.2 ter AUC≥0.60 verificado
- **T3.3 PID auto-calibration** — exige Bayesian gate de T1.4 funcional para evitar overshoot

### 📦 ADIAR (sem perda de PnL imediato):
- **T4 inteiro** — só após T1+T2+T3 estáveis. Quando vier, fazer T4.1 isolado primeiro, validar 30 dias, depois T4.2+T4.3.

---

## 6. Riscos consolidados

| Risco | Sprint que cria | Mitigação |
|---|---|---|
| Replay determinístico quebrar | T2.1 | Hash test sobre 3574 decisões idêntico ao baseline |
| Adam-Sigmoid oscilar | T2.3 | Shadow mode obrigatório 14d antes de live |
| Thompson stochástico | T3.1 | Seed determinístico em backtest + shadow |
| LR mal treinado | T3.2 | Fallback para SDA score se AUC<0.55 |
| PID overshoot | T3.3 | Bayesian gate (T1.4) descarta updates não-sig |
| Kelly bankroll bug | T3.4 | 30d shadow + 1000 Monte Carlo backtests |
| Postgres migration | T4.1 | 24h shadow + zero divergência aceita |
| Multi-mesa cross-contam | T4.2/T4.3 | Asyncio lock por mesa + isolation tests |

---

## 7. Bibliotecas a adicionar (footprint total)

| Lib | Tier | Tamanho | Hot path? |
|---|---|---|---|
| `tomllib` (stdlib) | T1.1 | 0 | sim (load 1× boot) |
| `vectorbt` | T1.2 | ~50 MB | NÃO (offline) |
| `structlog` | T1.3 | ~1 MB | sim (cada log) |
| `scipy.stats` | T1.4 | (já tem?) | NÃO (1× / score raro) |
| `river>=0.20` | T1.5 | ~5 MB | sim (1× / spin) |
| `scikit-learn>=1.4` | T3.2 | ~70 MB | NÃO (treino semanal) |
| `lightgbm` (fase 2) | T3.2 | ~5 MB | NÃO |
| `optuna>=3.5` | T1.2/T3 | ~10 MB | NÃO |
| Postgres + psycopg | T4.1 | ~10 MB lib | sim |
| `pgmq` extension | T4.1 | server-side | sim |

**Total footprint Python:** ~150 MB extra na imagem Docker — desprezível para o servidor maior planejado.

---

## 8. Decisão pendente do usuário

| # | Pergunta | Default sugerido |
|---|---|---|
| **D1** | Aprovar **T1 inteiro em bloco** para começar segunda-feira? | ✅ SIM (3.8d, baixo risco) |
| **D2** | Aprovar **T2.1 + T2.3 + T2.4** após T1? | ✅ SIM (mas exige hash test 3574/3574) |
| **D3** | T2.2 (Shadow mode) **antes** ou **depois** de T2.3? | ANTES (sem shadow não rodamos Adam-Sigmoid) |
| **D4** | T3.4 ¼-Kelly: substitui Martingale **totalmente** ou roda **junto** 30 dias? | JUNTO 30d (seguro) |
| **D5** | T4 ativar planejamento agora ou esperar fim T3? | Esperar fim T3 |
| **D6** | Servidor: já provisionar VM maior agora ou só pré-T4.1? | Só pré-T4.1 (atual suporta T1+T2+T3) |

---

## 9. Mapa final — Antes vs Depois (visual)

```
ANTES (HOJE)                                  DEPOIS (T1+T2 entregue, ~10d)
─────────────────────────────────────────     ─────────────────────────────────────────────────
SDA17.analyze (1 método, 580 LoC)              SDA17.analyze (orquestrador, ~30 LoC)
  ├ janela adaptativa inline                     ├ Stage1AdaptiveWindow
  ├ IQR inline                                   ├ Stage2IQRReject
  ├ weighted median inline                       ├ Stage3WeightedMedian
  ├ drift inline                                 ├ Stage4Drift
  ├ smart score inline                           ├ Stage5SmartScore (+ Bayesian gate)
  ├ triple focus inline                          ├ Stage6TripleFocus
  └ PCT-Sigmoid feedback inline                  ├ Stage6.7 HotCenterFilter (T2.4)
                                                 └ Stage7 AdamSigmoidUpdate (T2.3)

  Constantes hardcoded:    16                    Constantes em TOML:       16 ✅
  Drift detection:         ❌ nenhuma            Drift detection:          ADWIN ✅
  Bug logging fallback:    ❌ presente           Bug logging fallback:     corrigido ✅
  Backtest:                manual lento          Backtest:                 vectorbt 50× ✅
  Bayesian gate:           ❌                    Bayesian gate:            scipy.stats ✅
  Shadow mode:             ❌                    Shadow mode:              live + shadow ✅
  Assimetria CW/CCW:       23.8 pts              Assimetria CW/CCW:        ~12-15 pts (esperado)
  Confidence label:        folclore              Confidence label:         (T3.2 substitui)
  Bet sizing:              Martingale G3=7×      Bet sizing:               (T3.4 substitui)
  Postgres:                ❌ SQLite             Postgres:                 (T4.1 substitui)
```

---

*Documento gerado em 23/05/2026 15:30 UTC-3 por YOLO Orchestrator (Claude Opus 4.7) usando sequential-thinking + filesystem + memory + graphify + brave-search (auditoria base). Baseado em `resultados_23_05.md` (Parte 1+2) e `resultados_02_04.md`.*

**Próxima ação esperada:** responder D1-D6 para iniciar Sprint 1.
