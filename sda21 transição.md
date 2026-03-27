# 🔄 SDA-21 Transição — Documento de Implantação

> **Data:** 27/03/2026  
> **Versão Atual:** SDA-19 (1 centro, 9 vizinhos = 19 números, 51.4%)  
> **Versão Proposta:** SDA-21 (3 centros, 3 vizinhos = até 21 números, 56.8%)  
> **Base:** `analise_de_resultados.md`, `estudo aprofundado de quantidade de numeros.md`, `sugestões de melhorias.md`  
> **Status:** DOCUMENTO DE IMPLANTAÇÃO — nenhuma alteração realizada até aprovação

---

## ÍNDICE

1. [Situação Atual — Fluxo de Dados Completo](#1-situação-atual)
2. [Situação Proposta — Fluxo de Dados SDA-21](#2-situação-proposta)
3. [Mapa de Alterações por Arquivo](#3-mapa-de-alterações)
4. [Detalhamento de Cada Alteração](#4-detalhamento)
5. [Migração do Banco de Dados](#5-migração-db)
6. [Migração do State.json](#6-migração-state)
7. [Melhorias Incluídas (MEL)](#7-melhorias-incluídas)
8. [Ordem de Implementação](#8-ordem)
9. [Auditoria de Bugs](#9-auditoria)
10. [Checklist de Deploy](#10-checklist)

---

## 1. SITUAÇÃO ATUAL — Fluxo de Dados Completo {#1-situação-atual}

### 1.1 Pipeline Atual (SDA-19)

```
Chrome Extension (content.js)
    │
    │  WebSocket: { type: "novo_resultado", numero: 13, direcao: "horario" }
    ▼
server/message_handler.py → handle_new_result() (linha 131)
    │
    ├─ 1. VERIFICAR PREDIÇÃO ANTERIOR
    │     game_state.check_prediction(numero)          → state/game.py:248
    │     Compara: numero ∈ pending_prediction.numbers? → True=HIT, False=MISS
    │     Registra em performance_sda17_cw/ccw (deque maxlen=12)
    │
    ├─ 2. ATUALIZAR MARTINGALE (se havia aposta)
    │     martingale_cw.update(hit) OU martingale_ccw.update(hit)
    │     Janela de 5: 3+ hits → mantém/desce | <3 → escala
    │     BET_VALUES = {1: 19, 2: 38, 3: 76}           → state/game.py:35
    │
    ├─ 3. PROCESSAR SPIN
    │     game_state.process_spin(numero, direcao)      → state/game.py:216
    │     Calcula força: _calculate_force()              → state/game.py:343
    │     Adiciona à timeline: timeline_cw.add(force) ou timeline_ccw.add(force)
    │     Salva estado: game_state.save()                → state.json
    │
    ├─ 4. ANALISAR COM ESTRATÉGIA
    │     strategy.analyze(                              → strategies/sda17.py:30
    │         target_timeline,                           ← timeline OPOSTA ao último spin
    │         last_number,
    │         WHEEL_SEQUENCE,
    │         calibration=0
    │     )
    │     │
    │     ├─ Janela Adaptativa: 7→5→3 forças
    │     ├─ IQR Outlier Rejection                      → sda17.py:108-125
    │     ├─ Weighted Median (decay=0.8)                → sda17.py:127-135
    │     ├─ Drift Detection                            → sda17.py:137-148
    │     ├─ Smart Score                                → sda17.py:150-156
    │     │
    │     ├─ _apply_force(last_number, pred_force, dir) → sda17.py:197
    │     │   └─ Retorna: UM center_number
    │     │
    │     ├─ get_neighbors(center, radius=9)            → base.py:51
    │     │   └─ Retorna: 19 números [centro ± 9 posições]
    │     │
    │     └─ Retorna StrategyResult:
    │         should_bet=True/False
    │         numbers=[19 inteiros]         ← LISTA ÚNICA
    │         center=int                    ← UM CENTRO
    │         score=1-6
    │         visual="4, 21, [2], 25, 17"
    │         details={predicted_force, spread, drift, ...}
    │
    ├─ 5. TRIPLE RATE ADVISOR
    │     game_state.get_bet_advice(sda_score)           → state/bet_advisor.py
    │     Kill Switch: C4=0% AND score≤2 → VETO
    │
    ├─ 6. DECISÃO: APOSTAR ou PULAR
    │     game_state.store_prediction(                   → state/game.py:292
    │         numbers,                                   ← 19 números
    │         target_direction,
    │         center,                                    ← 1 centro (int)
    │         predicted_force,
    │         bet_placed=True/False,
    │         ...
    │     )
    │     Armazena em: self.pending_prediction = {
    │         "numbers": [19 ints],
    │         "direction": str,
    │         "center": int,                             ← UM VALOR
    │         "predicted_force": int,
    │         "bet_placed": bool,
    │         ...
    │     }
    │
    ├─ 7. SALVAR NO BANCO
    │     Decision(                                      → database/models.py:10
    │         sda_center=result.center,                  ← int (1 valor)
    │         sda_numbers=result.numbers,                ← [19 ints]
    │         gale_bet_value=mg.current_bet,             ← 19/38/76
    │         ...
    │     )
    │     db_service.save_decision(decision)             → sqlite_repo.py:191
    │     INSERT INTO decisions ... sda_center INTEGER    → sqlite_repo.py:99
    │
    └─ 8. ENVIAR AO OVERLAY
          overlay_response = {
              "type": "sugestao",
              "data": {
                  "numeros": result.numbers,             ← [19 ints]
                  "centro": result.center,               ← int (1 valor)
                  "regiao": result.visual,               ← "4, 21, [2], 25, 17"
                  "aposta": mg.current_bet,              ← 19/38/76
                  "estrategia": "SDA-19",
                  ...
              }
          }
          → WebSocket → Chrome Extension content.js
          → content.js:375: centro = sugestao.centro
          → content.js:465: `Centro ${sugestao.centro}`
```

### 1.2 Formato do StrategyResult Atual

```python
# strategies/base.py:11
@dataclass
class StrategyResult:
    should_bet: bool = False
    numbers: List[int] = []      # 19 números
    center: int = 0              # 1 centro
    score: int = 0               # 1-6
    visual: str = ""             # "4, 21, [2], 25, 17"
    details: Dict[str, Any] = {} # Pipeline info
```

### 1.3 Formato do pending_prediction Atual

```python
# state/game.py:304
self.pending_prediction = {
    "numbers": [int × 19],
    "direction": "horario" | "anti-horario",
    "center": int,               # UM centro
    "predicted_force": int,
    "bet_placed": bool,
    "tr_confidence": str,
    "tr_reason": str,
    "sda_score": int
}
```

### 1.4 Schema do Banco Atual

```sql
-- database/sqlite_repo.py:78-125
CREATE TABLE decisions (
    ...
    sda_center INTEGER,          -- UM centro (int)
    sda_numbers TEXT,             -- JSON array de 19 inteiros
    ...
    gale_bet_value INTEGER,      -- 19/38/76
    ...
);

-- database/sqlite_repo.py:144-159
CREATE TABLE window_plays (
    ...
    center_predicted INTEGER,    -- UM centro (int)
    ...
);
```

### 1.5 Overlay (Chrome Extension)

```javascript
// extension/content.js
// Linha 375: const centro = overlayState.lastSugestao.centro ?? '--';
// Linha 377: status.textContent = `[${centro}] ${galeText}`;
// Linha 465: regiao.textContent = sugestao.regiao || `Centro ${sugestao.centro}`;
// Linha 480: const centro = sugestao.centro ?? '--';
// Linha 485: status.textContent = `[${centro}] ${galeText}`;
// Linha 787: const centro = data.pending_prediction.center || '--';
```

---

## 2. SITUAÇÃO PROPOSTA — Fluxo de Dados SDA-21 {#2-situação-proposta}

### 2.1 Pipeline Proposto (SDA-21)

```
Chrome Extension (content.js)
    │
    │  WebSocket: { type: "novo_resultado", numero: 13, direcao: "horario" }
    ▼
server/message_handler.py → handle_new_result() (INALTERADO até passo 3)
    │
    ├─ 1-3. IGUAIS AO ATUAL (verificar, martingale, processar spin)
    │        Martingale: BET_VALUES = {1: 21, 2: 42, 3: 84}  ← MUDOU
    │
    ├─ 4. ANALISAR COM ESTRATÉGIA (MUDANÇAS PRINCIPAIS)
    │     strategy.analyze(target_timeline, last_number, WHEEL_SEQUENCE)
    │     │
    │     ├─ Pipeline SDA (IDÊNTICO):
    │     │   IQR + Weighted Median + Drift → predicted_force → C1
    │     │   MEL-01: IQR com statistics.quantiles()        ← MELHORIA
    │     │   MEL-05: Drift com dados limpos (pós-IQR)      ← MELHORIA
    │     │
    │     ├─ NOVO: Cálculo dos 3 Centros
    │     │   forces = timeline.get_last_n(window)
    │     │   C1 = _apply_force(last_number, predicted_force, dir)  ← mediana ponderada
    │     │   C2 = _apply_force(last_number, max(forces), dir)      ← força máxima
    │     │   C3 = _apply_force(last_number, min(forces), dir)      ← força mínima
    │     │
    │     │   # Garantir diversificação mínima
    │     │   if distância(C1, C2) < 4: C2 = deslocar C2
    │     │   if distância(C1, C3) < 4: C3 = deslocar C3
    │     │
    │     ├─ NOVO: Agregar 3 clusters de 7 números
    │     │   nums_c1 = get_neighbors(C1, radius=3)  → 7 números
    │     │   nums_c2 = get_neighbors(C2, radius=3)  → 7 números
    │     │   nums_c3 = get_neighbors(C3, radius=3)  → 7 números
    │     │   numbers = sorted(set(nums_c1) | set(nums_c2) | set(nums_c3))
    │     │   → Resultado: 15-21 números únicos (média ~19)
    │     │
    │     └─ Retorna StrategyResult:
    │         should_bet=True/False
    │         numbers=[15-21 inteiros]       ← LISTA VARIÁVEL
    │         center=C1                      ← CENTRO PRIMÁRIO (compatibilidade)
    │         score=1-6
    │         visual="[C1] [C2] [C3]"       ← NOVO FORMATO
    │         details={
    │             ...,
    │             "centers": [C1, C2, C3],   ← NOVO CAMPO
    │             "forces_used": {            ← NOVO
    │                 "median": pred_force,
    │                 "max": max_force,
    │                 "min": min_force
    │             },
    │             "unique_count": len(numbers),
    │             "overlap": (7*3) - len(numbers)
    │         }
    │
    ├─ 5. TRIPLE RATE ADVISOR (INALTERADO)
    │
    ├─ 6. DECISÃO: APOSTAR ou PULAR
    │     game_state.store_prediction(
    │         numbers,                                    ← 15-21 números
    │         target_direction,
    │         center,                                     ← C1 (int, compatibilidade)
    │         predicted_force,
    │         bet_placed=True/False,
    │         sda_centers=[C1, C2, C3],                   ← NOVO CAMPO
    │         ...
    │     )
    │
    ├─ 7. SALVAR NO BANCO
    │     Decision(
    │         sda_center=C1,                              ← MANTIDO (compatibilidade)
    │         sda_numbers=numbers,                        ← 15-21 números
    │         gale_bet_value=mg.current_bet,              ← 21/42/84
    │         sda_details=json.dumps({                    ← NOVO CAMPO OPCIONAL
    │             "centers": [C1, C2, C3],
    │             "forces_used": {...}
    │         })
    │     )
    │
    └─ 8. ENVIAR AO OVERLAY
          overlay_response = {
              "data": {
                  "numeros": numbers,                     ← 15-21 números
                  "centro": C1,                           ← C1 (compatibilidade)
                  "centros": [C1, C2, C3],                ← NOVO CAMPO
                  "regiao": visual,                       ← Novo formato
                  "aposta": mg.current_bet,               ← 21/42/84
                  "estrategia": "SDA-21",                 ← MUDOU
                  ...
              }
          }
```

### 2.2 Diferenças-Chave: Antes vs Depois

| Aspecto | SDA-19 (Antes) | SDA-21 (Depois) |
|---------|:--------------:|:---------------:|
| Centros | 1 (mediana) | 3 (mediana + max + min) |
| Raio/centro | 9 | 3 |
| Números | 19 fixos | 15-21 variáveis |
| Cobertura | 51.4% fixa | 40.5-56.8% variável |
| BET_VALUES | {1:19, 2:38, 3:76} | {1: dinâmico, 2: ×2, 3: ×4} |
| `center` no resultado | int | int (C1 para compatibilidade) |
| `centers` no resultado | ❌ não existe | [C1, C2, C3] (novo campo) |
| DB `sda_center` | INTEGER | INTEGER (C1, mantido) |
| DB `sda_details` | ❌ não existe | TEXT/JSON (novo campo opcional) |
| Overlay display | `[28]` | `[28] [11] [15]` |
| Stuck prediction | ❌ vulnerável | ✅ protegido nativamente |

### 2.3 Lógica de Diversificação Mínima

```python
# NOVO: Garantir separação entre centros
def _ensure_diversity(self, c1, c2, c3, wheel_sequence, predicted_force):
    """Garante separação mínima de 4 posições entre quaisquer 2 centros."""
    c1_pos = wheel_sequence.index(c1)
    c2_pos = wheel_sequence.index(c2)
    c3_pos = wheel_sequence.index(c3)
    
    def circ_dist(a, b):
        return min((a - b) % 37, (b - a) % 37)
    
    # Se C2 muito perto de C1, deslocar C2 por +5
    if circ_dist(c1_pos, c2_pos) < 4:
        c2 = wheel_sequence[(c1_pos + 7) % 37]
    
    # Se C3 muito perto de C1 ou C2, deslocar C3 por -5
    c2_pos = wheel_sequence.index(c2)  # Recalcular após ajuste
    c3_pos = wheel_sequence.index(c3)
    if circ_dist(c1_pos, c3_pos) < 4 or circ_dist(c2_pos, c3_pos) < 4:
        c3 = wheel_sequence[(c1_pos - 7) % 37]
    
    return c1, c2, c3
```

---

## 3. MAPA DE ALTERAÇÕES POR ARQUIVO {#3-mapa-de-alterações}

### 3.1 Arquivos com Alteração de Código

| # | Arquivo | Tipo | Impacto | Linhas Afetadas |
|:-:|---------|:----:|:-------:|:---------------:|
| 1 | `strategies/sda17.py` | 🔴 Crítico | Pipeline inteiro | 1,11,20,24,28,60-94 |
| 2 | `strategies/base.py` | 🟡 Moderado | StrategyResult | 11-18 |
| 3 | `state/game.py` | 🔴 Crítico | BET_VALUES, store_prediction | 25-27,34-35,42,292-313 |
| 4 | `core/engine.py` | 🟡 Moderado | SpinDecision, store_prediction calls | 22,101-118,127-131 |
| 5 | `server/message_handler.py` | 🟡 Moderado | Decision creation, overlay response | 233-256,274-298,312-333,349-355,478-492 |
| 6 | `database/models.py` | 🟡 Moderado | Decision, WindowPlay | 37,79,192 |
| 7 | `database/sqlite_repo.py` | 🟡 Moderado | Schema migration, save_decision | 96-101,195-237,340,609 |
| 8 | `models/output.py` | 🟢 Baixo | SuggestionOutput | 14,26-28 |
| 9 | `extension/content.js` | 🟡 Moderado | Overlay display | 375,377,465,480,485,787 |

### 3.2 Arquivos SEM Alteração

| Arquivo | Motivo |
|---------|--------|
| `core/roulette.py` | Imutável (constantes físicas) |
| `state/timeline.py` | Parametrizado (funciona com qualquer tamanho) |
| `state/bet_advisor.py` | Independente do número de centros |
| `server/connection_manager.py` | Independente da estratégia |
| `server/websocket.py` | Transport layer |
| `extension/background.js` | Só faz relay de mensagens |
| `app_config/settings.py` | Sem referência a número de centros |
| `Dockerfile` | Genérico |
| `docker-compose.yml` | Genérico |
| `roleta.conf` | Nginx (transport) |

---

## 4. DETALHAMENTO DE CADA ALTERAÇÃO {#4-detalhamento}

### 4.1 `strategies/sda17.py` — Pipeline SDA

#### 4.1.1 Constantes e Nome

```python
# ANTES (linhas 1, 11, 20, 24, 28):
# Roleta Cloud - SDA-19 Strategy (IQR + Weighted Median + Drift)
# Estratégia SDA-19: Sinergia Direcional Avançada — Robust.
# Cobertura: 19 números (1 centro + 9 de cada lado) = 51.4% da roda
super().__init__(name="SDA-19", num_neighbors=9)
self.description = "IQR + Weighted Median + Drift, 19 números"

# DEPOIS:
# Roleta Cloud - SDA-21 Strategy (IQR + Weighted Median + Drift + Triple Focus)
# Estratégia SDA-21: Sinergia Direcional Avançada — Triple Focus.
# Cobertura: até 21 números (3 centros × 3 vizinhos cada) = até 56.8% da roda
super().__init__(name="SDA-21", num_neighbors=3)
self.description = "IQR + Weighted Median + Drift, Triple Focus 21 números"
```

#### 4.1.2 Método `analyze()` — Cálculo dos 3 Centros

```python
# ANTES (linhas 60-94):
center_number = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)
numbers = self.get_neighbors(center_number, self.num_neighbors, wheel_sequence)
visual = self.get_visual_region(center_number, numbers)

return StrategyResult(
    should_bet=True,
    numbers=numbers,
    center=center_number,
    ...
)

# DEPOIS:
# Centro 1: Mediana Ponderada (pipeline SDA)
c1 = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)

# Centro 2: Força Máxima da timeline
max_force = max(forces)
c2 = self._apply_force(last_number, max_force, timeline.direction, wheel_sequence)

# Centro 3: Força Mínima da timeline
min_force = min(forces)
c3 = self._apply_force(last_number, min_force, timeline.direction, wheel_sequence)

# Garantir diversificação mínima
c1, c2, c3 = self._ensure_diversity(c1, c2, c3, wheel_sequence, predicted_force)

# Agregar números dos 3 clusters
nums = set()
for center in [c1, c2, c3]:
    nums |= set(self.get_neighbors(center, self.num_neighbors, wheel_sequence))
numbers = sorted(nums)

visual = self._get_triple_visual(c1, c2, c3, wheel_sequence)

return StrategyResult(
    should_bet=True,
    numbers=numbers,
    center=c1,  # Centro primário para compatibilidade
    score=pred_info.get("score", 3),
    visual=visual,
    details={
        "forces": forces,
        "predicted_force": predicted_force,
        "original_prediction": original_force,
        "method": "triple_focus_iqr_weighted_median",
        "centers": [c1, c2, c3],
        "forces_used": {"median": predicted_force, "max": max_force, "min": min_force},
        "unique_count": len(numbers),
        "overlap": (7 * 3) - len(numbers),
        "clean_count": pred_info.get("clean_count", 0),
        "outliers_removed": pred_info.get("outliers_removed", 0),
        "spread": pred_info.get("spread", 0),
        "drift": pred_info.get("drift", 0),
        "survival_rate": pred_info.get("survival_rate", 1.0),
        "calibration": calibration
    }
)
```

#### 4.1.3 MEL-01: Correção IQR (dentro de `_predict_robust`)

```python
# ANTES (linhas 113-115):
sorted_f = sorted(forces)
q1 = sorted_f[n // 4]
q3 = sorted_f[min(n - 1, 3 * n // 4)]

# DEPOIS:
from statistics import quantiles
sorted_f = sorted(forces)
q1, _, q3 = quantiles(sorted_f, n=4)
```

#### 4.1.4 MEL-05: Drift com Dados Limpos (dentro de `_predict_robust`)

```python
# ANTES (linhas 138-146):
if n >= 3:
    last3 = forces[:3]  # As 3 mais recentes na ordem original
    ...

# DEPOIS:
if n >= 3:
    # Usar forças LIMPAS (pós-IQR) para drift
    clean_sorted_by_idx = sorted(clean, key=lambda x: x[1])  # Ordenar por posição original
    clean_forces_ordered = [f for f, _ in clean_sorted_by_idx[:3]]
    if len(clean_forces_ordered) >= 3:
        last3 = clean_forces_ordered
        ...
```

#### 4.1.5 Novos Métodos

```python
def _ensure_diversity(self, c1, c2, c3, wheel_sequence, predicted_force):
    """Garante separação mínima de 4 posições entre centros."""
    ...

def _get_triple_visual(self, c1, c2, c3, wheel_sequence):
    """Gera visual para 3 centros: '[C1] ... [C2] ... [C3]'"""
    return f"[{c1}] [{c2}] [{c3}]"
```

### 4.2 `strategies/base.py` — StrategyResult

```python
# ANTES (linha 11-18):
@dataclass
class StrategyResult:
    should_bet: bool = False
    numbers: List[int] = field(default_factory=list)
    center: int = 0
    score: int = 0
    visual: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

# DEPOIS (sem quebrar compatibilidade):
@dataclass
class StrategyResult:
    should_bet: bool = False
    numbers: List[int] = field(default_factory=list)
    center: int = 0               # Centro primário (C1) — compatibilidade
    score: int = 0
    visual: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    # Nota: centers completos ficam em details["centers"] = [c1, c2, c3]
```

> **Decisão de design:** NÃO adicionamos `centers: List[int]` ao StrategyResult para não quebrar a interface `StrategyBase.analyze()`. Os centros adicionais ficam em `details["centers"]`. Isso preserva compatibilidade com qualquer outra estratégia futura que use 1 centro.

### 4.3 `state/game.py` — Martingale e store_prediction

#### 4.3.1 BET_VALUES

```python
# ANTES (linhas 25-27, 34-35, 42):
# - GALE 1 = R$19 (5 jogadas)
# - GALE 2 = R$38 (5 jogadas)
# - GALE 3 = R$76 (5 jogadas)
# Valores de aposta por nível (19 números × R$1/R$2/R$4)
BET_VALUES: ClassVar[Dict[int, int]] = {1: 19, 2: 38, 3: 76}
return self.BET_VALUES.get(self.level, 19)

# DEPOIS:
# - GALE 1 = variável (5 jogadas)
# - GALE 2 = variável ×2 (5 jogadas)
# - GALE 3 = variável ×4 (5 jogadas)
# Valor base por nível — o valor real depende de len(numbers)
BET_MULTIPLIER: ClassVar[Dict[int, int]] = {1: 1, 2: 2, 3: 4}
DEFAULT_NUMS: ClassVar[int] = 21  # Número padrão de cobertura
```

> **IMPORTANTE:** Com SDA-21, o número de números únicos varia entre 15-21 por spin. Os BET_VALUES deveriam ser dinâmicos: `aposta = len(numbers) × multiplicador`. Porém, isso exige passar `len(numbers)` ao Martingale, mudança que rompe a interface. **Decisão conservadora:** manter BET_VALUES fixos em {1:21, 2:42, 3:84} como caso máximo. Na prática, quando há sobreposição (≤19 números), o custo real é menor que o registrado.

```python
# DECISÃO CONSERVADORA (recomendada para v1):
BET_VALUES: ClassVar[Dict[int, int]] = {1: 21, 2: 42, 3: 84}
return self.BET_VALUES.get(self.level, 21)
```

#### 4.3.2 store_prediction

```python
# ANTES (linha 292):
def store_prediction(self, numbers, direction, center,
                     predicted_force=0, bet_placed=False,
                     tr_confidence="", tr_reason="", sda_score=0):
    self.pending_prediction = {
        "numbers": numbers,
        "direction": direction,
        "center": center,
        ...
    }

# DEPOIS:
def store_prediction(self, numbers, direction, center,
                     predicted_force=0, bet_placed=False,
                     tr_confidence="", tr_reason="", sda_score=0,
                     sda_centers=None):  # NOVO parâmetro opcional
    self.pending_prediction = {
        "numbers": numbers,
        "direction": direction,
        "center": center,                  # C1 (compatibilidade)
        "centers": sda_centers or [center], # [C1, C2, C3]
        "predicted_force": predicted_force,
        "bet_placed": bet_placed,
        "tr_confidence": tr_confidence,
        "tr_reason": tr_reason,
        "sda_score": sda_score
    }
```

### 4.4 `core/engine.py` — SpinDecision e chamadas

```python
# ANTES (linhas 101-102, 112-113):
self.game_state.store_prediction(
    result.numbers, self.game_state.target_direction, result.center,
    predicted_force=..., bet_placed=True, ...
)

# DEPOIS:
self.game_state.store_prediction(
    result.numbers, self.game_state.target_direction, result.center,
    predicted_force=..., bet_placed=True,
    sda_centers=result.details.get("centers", [result.center]),  # NOVO
    ...
)
```

### 4.5 `server/message_handler.py` — Overlay Response

```python
# ANTES (linhas 312-333):
overlay_response = {
    "data": {
        "numeros": result.numbers,
        "centro": result.center,
        "aposta": mg.current_bet,
        "estrategia": self.strategy.name,
        ...
    }
}

# DEPOIS:
overlay_response = {
    "data": {
        "numeros": result.numbers,
        "centro": result.center,                                   # C1 (compatibilidade)
        "centros": result.details.get("centers", [result.center]), # NOVO
        "aposta": mg.current_bet,
        "estrategia": self.strategy.name,
        ...
    }
}
```

Mesma alteração para: `handle_legacy_spin` (linha ~483) e `trace_broadcast` (linha ~351).

### 4.6 `database/models.py` — Decision Model

```python
# ANTES (linha 37):
sda_center: int = 0

# DEPOIS (compatível — mantém campo antigo, adiciona novo):
sda_center: int = 0                                        # C1 (compatibilidade)
sda_centers: List[int] = field(default_factory=list)       # [C1, C2, C3] — NOVO
```

E em `to_dict()` (linha 79):
```python
"sda_center": self.sda_center,
"sda_centers": self.sda_centers,  # NOVO
```

### 4.7 `database/sqlite_repo.py` — Schema e INSERT

Ver Seção 5 (Migração do Banco).

### 4.8 `models/output.py` — SuggestionOutput

```python
# ANTES (linha 14):
centro: int = Field(default=0, description="Número central da aposta")

# DEPOIS (compatível):
centro: int = Field(default=0, description="Centro primário da aposta (C1)")
centros: List[int] = Field(default_factory=list, description="Centros [C1, C2, C3]")
```

### 4.9 `extension/content.js` — Overlay Display

```javascript
// ANTES (linhas 375, 480, etc.):
const centro = overlayState.lastSugestao.centro ?? '--';
status.textContent = `[${centro}] ${galeText}`;

// DEPOIS:
const centros = overlayState.lastSugestao.centros || [overlayState.lastSugestao.centro];
const centroDisplay = centros.filter(c => c).map(c => `[${c}]`).join(' ');
status.textContent = `${centroDisplay} ${galeText}`;

// ANTES (linha 465):
regiao.textContent = sugestao.regiao || `Centro ${sugestao.centro}`;

// DEPOIS:
regiao.textContent = sugestao.regiao || `Centros: ${(sugestao.centros || [sugestao.centro]).join(', ')}`;

// ANTES (linha 787):
const centro = data.pending_prediction.center || '--';

// DEPOIS:
const centros = data.pending_prediction.centers || [data.pending_prediction.center || '--'];
const centroDisplay = centros.map(c => `[${c}]`).join(' ');
```

---

## 5. MIGRAÇÃO DO BANCO DE DADOS {#5-migração-db}

### 5.1 Estratégia: Aditiva (sem quebra)

```sql
-- Executar ANTES de fazer deploy do novo código
-- Adicionar coluna nova sem remover a antiga

ALTER TABLE decisions ADD COLUMN sda_centers TEXT;  -- JSON: "[c1, c2, c3]"

-- Migrar dados antigos: sda_center → sda_centers (como array de 1 elemento)
UPDATE decisions SET sda_centers = json_array(sda_center) WHERE sda_centers IS NULL;
```

### 5.2 Código em `sqlite_repo.py`

```python
# Adicionar ao _init_schema() após o CREATE TABLE (auto-migration):
try:
    conn.execute("SELECT sda_centers FROM decisions LIMIT 1")
except sqlite3.OperationalError:
    conn.execute("ALTER TABLE decisions ADD COLUMN sda_centers TEXT")
    conn.execute("UPDATE decisions SET sda_centers = json_array(sda_center) WHERE sda_centers IS NULL")
    logger.info("Migration: added sda_centers column to decisions")
```

### 5.3 INSERT Atualizado

```python
# ANTES (sqlite_repo.py:195-237):
# 27 campos no INSERT

# DEPOIS: 28 campos (adicionar sda_centers após sda_center)
# Na tupla: json.dumps(decision.sda_centers)
```

### 5.4 SELECT Atualizado (row_to_decision)

```python
# ANTES (sqlite_repo.py:340):
sda_center=row["sda_center"] or 0,

# DEPOIS:
sda_center=row["sda_center"] or 0,
sda_centers=json.loads(row["sda_centers"]) if row.get("sda_centers") else [row["sda_center"] or 0],
```

---

## 6. MIGRAÇÃO DO STATE.JSON {#6-migração-state}

### 6.1 O que muda

```json
// ANTES (state.json):
{
    "version": "1.5.0",
    "pending_prediction": {
        "center": 28,
        ...
    },
    "martingale_cw": { "current_bet": 19 },
    "martingale_ccw": { "current_bet": 19 }
}

// DEPOIS:
{
    "version": "2.0.0",
    "pending_prediction": {
        "center": 28,
        "centers": [28, 11, 15],
        ...
    },
    "martingale_cw": { "current_bet": 21 },
    "martingale_ccw": { "current_bet": 21 }
}
```

### 6.2 Compatibilidade na Leitura

O `GameState.load()` já é robusto — ignora campos desconhecidos e usa defaults. O campo `centers` em `pending_prediction` é novo e será `None` para estados antigos. O `store_prediction()` com `sda_centers=None` produz `"centers": [center]`, garantindo que o formato esteja sempre correto após a primeira execução.

---

## 7. MELHORIAS INCLUÍDAS (MEL) {#7-melhorias-incluídas}

### 7.1 Melhorias Integradas na Transição

| MEL | Descrição | Onde Aplica | Risco |
|:---:|-----------|-------------|:-----:|
| **MEL-01** | IQR com `statistics.quantiles()` | `sda17.py:113-115` | 🟢 Baixo |
| **MEL-05** | Drift usa forças pós-IQR | `sda17.py:138-146` | 🟢 Baixo |
| **MEL-11** | Log dos detalhes SDA | `engine.py` (novo log) | 🟢 Baixo |
| **MEL-13** | Spread normalizado por MAX_FORCE=18 | `sda17.py:154` | 🟢 Baixo |

### 7.2 Melhorias Descartadas para SDA-21

| MEL | Descrição | Motivo |
|:---:|-----------|--------|
| **MEL-02** | Stuck prediction detection | **Desnecessário** — 3 centros com max/min diversificam nativamente |
| **MEL-04** | Expansão para 21 números | **Substituído** — SDA-21 já cobre até 21 números via 3 centros |

### 7.3 Melhorias Independentes (aplicar separadamente)

| MEL | Descrição | Recomendação |
|:---:|-----------|:------------:|
| **MEL-03** | Decay adaptativo | Backtest antes de produção |
| **MEL-08** | Performance deque 24 | Pode implementar junto |
| **MEL-09** | Martingale window adaptativo | Avaliar após dados SDA-21 |

---

## 8. ORDEM DE IMPLEMENTAÇÃO {#8-ordem}

### Fase 1: Preparação (sem impacto em produção)

```
□ 1.1 Migração do banco (ALTER TABLE)
□ 1.2 Atualizar database/models.py (adicionar sda_centers)
□ 1.3 Atualizar database/sqlite_repo.py (auto-migration + INSERT/SELECT)
□ 1.4 Atualizar models/output.py (adicionar centros)
```

### Fase 2: Backend (mudança core)

```
□ 2.1 Atualizar strategies/sda17.py (pipeline completo SDA-21)
     - MEL-01: IQR fix
     - MEL-05: Drift limpo
     - MEL-13: Spread normalization
     - Triple Focus: 3 centros
     - Diversificação mínima
□ 2.2 Atualizar state/game.py
     - BET_VALUES: {1:21, 2:42, 3:84}
     - store_prediction: novo parâmetro sda_centers
□ 2.3 Atualizar core/engine.py
     - Passar sda_centers no store_prediction
     - MEL-11: Log do pipeline
□ 2.4 Atualizar server/message_handler.py
     - Passar sda_centers no store_prediction
     - Adicionar centros ao overlay_response
     - Adicionar centros ao trace_broadcast
     - Atualizar handle_legacy_spin
```

### Fase 3: Frontend (Chrome Extension)

```
□ 3.1 Atualizar extension/content.js
     - Display de múltiplos centros
     - Fallback para campo "centro" se "centros" não existir
```

### Fase 4: Testes e Deploy

```
□ 4.1 Atualizar tests/test_sda17.py
□ 4.2 Atualizar tests/test_game_state.py
□ 4.3 Rodar testes locais
□ 4.4 Commit + Push
□ 4.5 Deploy no servidor
     - git pull
     - docker compose down
     - docker compose build --no-cache
     - docker compose up -d
□ 4.6 Verificar logs: MASTER assignment, primeiro spin, 3 centros
```

---

## 9. AUDITORIA DE BUGS {#9-auditoria}

### 9.1 Bugs Encontrados no Plano de Transição

| ID | Severidade | Descrição | Mitigação |
|:--:|:----------:|-----------|-----------|
| **BUG-T01** | 🔴 Crítico | `BET_VALUES` fixo em 21, mas `len(numbers)` pode ser 15-20 com sobreposição. Registra custo maior que o real. | **V1:** Aceitar imprecisão (margem de segurança). **V2:** Tornar dinâmico `current_bet = len(numbers) * multiplier`. |
| **BUG-T02** | 🔴 Crítico | `min(forces)` pode ser 0 quando o primeiro spin da sessão não tem anterior (`_calculate_force` retorna 0). Force 0 → centro = último número → cluster C3 começa no ponto de partida. | **Filtrar:** `forces = [f for f in forces if f > 0]` antes de calcular min/max. Se vazio após filtro, usar apenas C1. |
| **BUG-T03** | 🟡 Médio | `quantiles()` do MEL-01 requer `len(data) >= 2`. Com o bypass de IQR existente para `n < 4` (linha 110), isso é protegido. Mas se o bypass for removido acidentalmente, `StatisticsError`. | **Manter** o bypass `if n < 4: skip IQR` exatamente como está. |
| **BUG-T04** | 🟡 Médio | `_ensure_diversity()` pode gerar C2/C3 que NÃO correspondem a nenhuma força real da timeline. São centros "artificiais". | **Aceitável:** O objetivo é maximizar cobertura, não precisão de cada centro individual. Documentar. |
| **BUG-T05** | 🟡 Médio | `sda_centers` no DB pode ser `NULL` para registros antigos. Código precisa lidar com isso no SELECT. | **Mitigação:** `json.loads(row.get("sda_centers") or "[]") or [row["sda_center"]]` |
| **BUG-T06** | 🟡 Médio | `check_prediction()` verifica `actual_number in numbers`. Com 15-21 números variáveis, o backtest com dados antigos (19 fixos) não é comparável diretamente. | **Registrar** `len(numbers)` no campo `sda_details` para contexto. |
| **BUG-T07** | 🟢 Baixo | Overlay mostra `[C1] [C2] [C3]` — pode confundir usuário que espera ver 1 centro. | **UX:** Tooltip explicativo ou toggle para mostrar centros expandidos/colapsados. |
| **BUG-T08** | 🟢 Baixo | `state.json` versão muda de "1.5.0" para "2.0.0". O `GameState.load()` precisa tratar a nova versão. | **Verificar:** `load()` já ignora versão > 1.4 e carrega formato v1.4+. O campo `centers` em `pending_prediction` será ignorado em versões antigas (sem crash). |
| **BUG-T09** | 🟢 Baixo | `handle_initial_history()` e `handle_history_correction()` processam spins sem gerar predição. Quando o primeiro spin após histórico chegar, a timeline pode ter forças com valor 0 (do primeiro spin sem anterior). | **Já existente:** Não é um bug novo. O pipeline SDA já tem `min_forces=3` como requisito. |
| **BUG-T10** | 🟡 Médio | `analytics_handler.py` linha 113 usa `d.sda_center` para dashboard. Precisa atualizar para incluir `sda_centers`. | **Verificar** se o dashboard/analytics usa `sda_center` e adaptar. |

### 9.2 Melhorias Identificadas na Auditoria

| ID | Descrição | Prioridade |
|:--:|-----------|:----------:|
| **IMP-T01** | Adicionar campo `unique_count` (int) ao Decision model para registrar quantos números únicos cada decisão cobriu. Facilita backtests futuros. | 🟡 Média |
| **IMP-T02** | Mover constante `DEFAULT_NUMS = 21` para `app_config/settings.py` para configurabilidade sem alterar código. | 🟢 Baixa |
| **IMP-T03** | Adicionar teste unitário específico para `_ensure_diversity()` com todos os edge cases: centros idênticos, centros adjacentes, centros em extremos da roda. | 🔴 Alta |
| **IMP-T04** | O campo `visual` do `StrategyResult` precisa de novo formato para 3 centros. Proposta: `"[C1:28] [C2:11] [C3:15]"` com os números do cluster logo abaixo no tooltip. | 🟡 Média |
| **IMP-T05** | Considerar logging estruturado (MEL-11): ao processar cada spin, logar qual centro capturou o resultado (`C1`, `C2`, `C3` ou `MISS`). Isso permite analisar a contribuição de cada centro. | 🔴 Alta |

### 9.3 Riscos de Deploy

| Risco | Probabilidade | Impacto | Mitigação |
|-------|:------------:|:-------:|-----------|
| Extension desatualizada (cache) | Alta | Médio | Forçar reload: incrementar versão no `manifest.json` |
| DB migration falha em produção | Baixa | Alto | Rodar migration manualmente via `docker exec` antes do deploy |
| `state.json` incompatível | Baixa | Baixo | `GameState.load()` já tem fallbacks robustos |
| Regressão no pipeline SDA | Média | Alto | Backtest com dados da sessão dab34c61 antes de deploy |
| Sobreposição total (15 nums) reduz cobertura | Média | Médio | Offset mínimo de `_ensure_diversity()` garante ≥19 únicos |

---

## 10. CHECKLIST DE DEPLOY {#10-checklist}

### Pré-Deploy

```
□ Backtest local: rodar simulação com dados da sessão dab34c61
  - SDA-21 deve atingir ≥ 9/15 hits (60%+)
  - Verificar que nenhum resultado gera menos de 15 números
□ Testes unitários passam (pytest)
□ Commit com mensagem: "feat: upgrade SDA-19 → SDA-21 (Triple Focus)"
□ Push para GitHub
```

### Deploy em Produção

```
□ SSH: ssh root@187.45.181.75
□ cd /root/roleta-cloud
□ git pull origin main
□ docker exec roleta-cloud python -c "
    import sqlite3; conn = sqlite3.connect('/data/decisions.db')
    try: conn.execute('SELECT sda_centers FROM decisions LIMIT 1')
    except: conn.execute('ALTER TABLE decisions ADD COLUMN sda_centers TEXT')
    conn.commit(); conn.close(); print('OK')
  "
□ docker compose down
□ docker compose build --no-cache
□ docker compose up -d
□ docker logs roleta-cloud --tail 20  # Verificar startup
```

### Pós-Deploy

```
□ Verificar logs: "SDA-21" aparece no nome da estratégia
□ Verificar overlay: extensão mostra 3 centros
□ Primeiro spin: verificar que pipeline gera [C1, C2, C3]
□ Após 3 spins: verificar que números têm 15-21 itens
□ Após 10 spins: verificar taxa de acerto vs baseline
□ Monitorar por 30 minutos antes de considerar estável
```

---

> **Documento gerado em:** 27/03/2026 16:00 UTC  
> **Método:** Auditoria completa do código-fonte + análise de fluxo de dados + simulação  
> **Fontes:** `strategies/sda17.py`, `strategies/base.py`, `core/engine.py`, `state/game.py`, `server/message_handler.py`, `database/models.py`, `database/sqlite_repo.py`, `models/output.py`, `extension/content.js`  
> **Status:** DOCUMENTO DE IMPLANTAÇÃO — aprovação necessária antes de implementar
