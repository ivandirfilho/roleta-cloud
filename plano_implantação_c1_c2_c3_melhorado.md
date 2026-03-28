# Plano de Implantação — M15-ADA (C1/C2/C3 Melhorado)

> **Tipo:** Memorial Descritivo + Plano de Tarefas  
> **Status:** Estudo Pré-Implantação (Nenhuma alteração no software)  
> **Referência:** analise_c1_c2_c3.md — Partes 18-22  
> **Migração:** SDA-21 (21 números, offset fixo) → M15-ADA (17 números, offset adaptativo)

---

## 1. RESUMO EXECUTIVO

### 1.1 Objetivo

Migrar o sistema Roleta Cloud da estratégia **SDA-21** (3 centros × raio 3 = 21 números, offset fixo de 12) para a estratégia **M15-ADA** (C1 raio 3 + C2/C3 raio 2 = 17 números, offset adaptativo por direção).

### 1.2 Motivação (Resultados do Estudo)

| Métrica | SDA-21 (Atual) | M15-ADA (Proposto) | Diferença |
|:--------|:--------------:|:------------------:|:---------:|
| Números apostados | 21 | 17 | -4 |
| Break-even HR | 58.3% | 47.2% | -11.1pp |
| HR observado (simulação) | 52.5% | 51.4% | -1.1pp |
| EV por jogada | -R$2.10 | **+R$1.51** | +R$3.61 |
| EV em 100 jogadas | -R$210 | **+R$151** | +R$361 |

### 1.3 Princípio Fundamental

> **Menos números com maior precisão é mais lucrativo que mais números com menor precisão.**

O M15-ADA aposta 4 números a menos por jogada (economia de R$4/jogada), mas mantém HR praticamente igual. O break-even 11pp mais baixo transforma EV negativo em positivo.

---

## 2. ARQUITETURA ATUAL DO SISTEMA

### 2.1 Fluxo de Dados Completo (Estado Atual)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FLUXO DE DADOS — SDA-21 ATUAL                       │
│                                                                             │
│  EXTENSÃO (content.js)                                                      │
│  ├── Captura número da roleta (DOM scraping)                               │
│  ├── Detecta direção (horário/anti-horário)                                │
│  └── Envia via WebSocket: {type:"novo_resultado", numero:N, direcao:D}     │
│       │                                                                     │
│       ▼                                                                     │
│  SERVER (message_handler.py)                                                │
│  ├── process_message() → handle_new_result()                               │
│  ├── Valida input via Pydantic (SpinInput)                                 │
│  ├── check_prediction(numero) → hit/miss da jogada anterior               │
│  ├── Atualiza Martingale (update + sync_global)                            │
│  ├── process_spin(numero, direcao) → calcula força, adiciona à timeline    │
│  ├── strategy.analyze(timeline, last_number, WHEEL_SEQUENCE)               │
│  │    │                                                                     │
│  │    ▼                                                                     │
│  │  STRATEGY (sda17.py)                                                    │
│  │  ├── Janela adaptativa: 7→5→3 forças                                   │
│  │  ├── _predict_robust(forces):                                           │
│  │  │   ├── IQR Outlier Rejection                                          │
│  │  │   ├── Weighted Median (decay=0.8)                                    │
│  │  │   ├── Drift Detection                                                │
│  │  │   └── Smart Score (1-6)                                              │
│  │  ├── predicted_force → C1 = _apply_force(last_num, pred_force, dir)     │
│  │  ├── max_force → C2 = _apply_force(last_num, max_force, dir)           │
│  │  ├── min_force → C3 = _apply_force(last_num, min_force, dir)           │
│  │  ├── _ensure_diversity(C1,C2,C3): MIN_SEPARATION=7, SPREAD_OFFSET=12   │
│  │  ├── get_neighbors(center, 3, wheel) para CADA centro = 7 nums cada    │
│  │  ├── Se <18 nums: _force_spread() → C2=C1+12, C3=C1-12               │
│  │  ├── Se ainda <18: expandir raio para 4                                │
│  │  └── Retorna StrategyResult(numbers=[21 nums], center=C1, ...)         │
│  │                                                                         │
│  ├── get_bet_advice(sda_score) → Triple Rate Advisor (vetar ou não)       │
│  ├── SmartGale.get_gale(score, c4_rate, confidence) → nível 1/2/3        │
│  ├── store_prediction(numbers, direction, center, ...)                     │
│  ├── Salva Decision no banco (db_service.save_decision)                   │
│  ├── Envia overlay_response via WebSocket (type:"sugestao")               │
│  └── Broadcast trace_broadcast (type:"trace") para dashboard              │
│       │                                                                     │
│       ├──────────────────────┐                                              │
│       ▼                      ▼                                              │
│  EXTENSÃO (content.js)   DASHBOARD (frontend/)                             │
│  ├── Recebe sugestão     ├── Recebe trace                                  │
│  ├── Mostra overlay:     ├── Mostra resultados:                            │
│  │   - Ação (APOSTAR)    │   - Ação, Centro, Região                        │
│  │   - Região (visual)   │   - Performance (12 squares)                    │
│  │   - Gale (G1/G2/G3)  │   - Timeline status                            │
│  │   - Aposta (R$21)     │   - Score SDA                                  │
│  └── Última número       └── Gale display                                  │
│                                                                             │
│  DATABASE (decisions.db)                                                    │
│  ├── decisions: sda_center, sda_centers, sda_numbers, gale_bet_value       │
│  ├── sessions: stats agregados                                              │
│  ├── gale_windows: janelas de martingale                                   │
│  └── window_plays: jogadas individuais                                      │
│                                                                             │
│  STATE (state.json)                                                         │
│  ├── version: "1.5.0"                                                      │
│  ├── timeline_cw/ccw: {direction, forces[], max_size}                      │
│  ├── performance_sda17_cw/ccw: [bool, ...]                                │
│  ├── performance_bet_cw/ccw: [bool, ...]                                  │
│  ├── martingale_cw/ccw: {level, consecutive_hits, ...}                    │
│  └── pending_prediction: {numbers, direction, center, centers, ...}        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Mapa de Arquivos do Sistema

```
Roleta Cloud/
├── main.py                          # Entry point — inicia servidor WebSocket
├── app_config/
│   └── settings.py                  # Configurações (host, port, game params)
├── core/
│   ├── engine.py                    # Motor principal (orquestração)
│   ├── roulette.py                  # WHEEL_SEQUENCE, constantes da roleta
│   └── logging_config.py            # Configuração de logging
├── strategies/
│   ├── base.py                      # StrategyBase + StrategyResult (dataclass)
│   └── sda17.py                     # ★ SDA-21 Strategy (ARQUIVO PRINCIPAL)
├── state/
│   ├── game.py                      # ★ GameState + MartingaleState
│   ├── timeline.py                  # Timeline (deque de forças)
│   └── bet_advisor.py               # TripleRateAdvisor (Kill Switch)
├── server/
│   ├── websocket.py                 # Servidor WebSocket (asyncio)
│   ├── message_handler.py           # ★ Processamento de mensagens
│   ├── connection_manager.py        # Gerenciador de conexões
│   ├── extractor_service.py         # Serviço de extração
│   └── analytics_handler.py         # Handler de analytics
├── database/
│   ├── models.py                    # ★ Decision, Session, GaleWindow, WindowPlay
│   ├── service.py                   # DatabaseService (alto nível)
│   ├── repository.py                # Interface repositório
│   └── sqlite_repo.py              # Implementação SQLite
├── models/
│   ├── input.py                     # SpinInput (Pydantic)
│   ├── output.py                    # ErrorOutput (Pydantic)
│   └── trace.py                     # TraceContext
├── frontend/
│   ├── index.html                   # ★ Dashboard Glass Box
│   ├── app.js                       # ★ Lógica do dashboard (WebSocket client)
│   └── style.css                    # Estilos do dashboard
├── extension/
│   ├── manifest.json                # Configuração da extensão Chrome
│   ├── background.js                # Service worker
│   ├── content.js                   # ★ Overlay na página da roleta
│   ├── overlay.css                  # Estilos do overlay
│   └── popup.html/js               # Popup da extensão
├── data/
│   └── decisions.db                 # ★ Banco de dados principal
└── state.json                       # ★ Estado persistente do jogo
```

**Legenda:** ★ = Arquivo que será modificado na migração

### 2.3 Descrição Detalhada dos Componentes Atuais

#### 2.3.1 Estratégia SDA-21 (`strategies/sda17.py`)

**Classe:** `SDA17Strategy` (herda de `StrategyBase`)

**Constantes:**
```python
MIN_SEPARATION = 7    # Distância mínima entre centros (garante zero overlap)
SPREAD_OFFSET = 12    # Offset de redistribuição (~120° = 12/37 posições)
MAX_FORCE_THRESHOLD = 30  # Forças acima disso são invertidas
num_neighbors = 3     # Raio de vizinhança = 3 (7 números por centro)
```

**Fluxo do `analyze()`:**

1. **Janela Adaptativa** (linhas 52-58): Tenta window=7, depois 5, depois 3
2. **`_predict_robust()`** (linhas 177-252): Pipeline IQR → Weighted Median → Drift → Score
3. **Early-session fallback** (linhas 89-115): Se `valid_forces < 5` → SDA-19 (1 centro × raio 9 = 19 nums)
4. **Triple Focus** (linhas 117-134):
   - C1 = `_apply_force(last_number, predicted_force, direction)` — mediana ponderada
   - C2 = `_apply_force(last_number, max_force, direction)` — força máxima
   - C3 = `_apply_force(last_number, min_force, direction)` — força mínima
5. **Diversificação** (linhas 126-141):
   - `_ensure_diversity()`: Se centros muito próximos, usa SPREAD_OFFSET=12
   - Se `len(numbers) < 18`: `_force_spread()` força C2=C1+12, C3=C1-12
   - Se ainda `< 18`: Aumenta raio para `num_neighbors + 1 = 4`
6. **Retorno**: `StrategyResult(numbers=[21 nums], center=C1, score, visual, details)`

**Problema:** C2 e C3 são calculados com max/min das forças, mas frequentemente caem muito perto de C1, ativando _ensure_diversity que SEMPRE força offset=12. Na prática, o sistema já funciona como "Vec120 fixo".

#### 2.3.2 Base da Estratégia (`strategies/base.py`)

**`get_neighbors(center, radius, wheel_sequence)`:**
```python
for offset in range(-radius, radius + 1):
    idx = (center_idx + offset) % wheel_size
    neighbors.append(wheel_sequence[idx])
```
- Raio 3 → 7 números (center ± 3)
- Raio 2 → 5 números (center ± 2)
- **Não precisa de alteração** — já aceita raio como parâmetro

#### 2.3.3 Estado do Jogo (`state/game.py`)

**MartingaleState:**
```python
BET_VALUES = {1: 21, 2: 42, 3: 63}  # R$ por nível de gale
```
- Nível 1: R$21 (1 × 21 números)
- Nível 2: R$42 (2 × 21 números)  
- Nível 3: R$63 (3 × 21 números)

**GameState:**
- `timeline_cw/ccw`: Timelines de forças por direção
- `performance_sda17_cw/ccw`: Histórico de acertos SDA (deque maxlen=12)
- `performance_bet_cw/ccw`: Histórico de apostas reais
- `martingale_cw/ccw`: Estado do Martingale por direção
- `pending_prediction`: Última predição para verificar
- `store_prediction()`: Salva predição com numbers, direction, center, sda_centers
- `check_prediction()`: Verifica hit/miss contra `pending_prediction.numbers`
- **state.json version: "1.5.0"**

#### 2.3.4 Handler de Mensagens (`server/message_handler.py`)

**`handle_new_result()`** — Função principal (linhas 132-418):
1. Valida input → `SpinInput`
2. Verifica predição anterior → `check_prediction()`
3. Atualiza Martingale → `martingale.update(hit)`
4. Processa spin → `process_spin(numero, direcao)`
5. Analisa com estratégia → `strategy.analyze(target_timeline, last_number, WHEEL)`
6. Triple Rate Advisor → `get_bet_advice(sda_score)`
7. SmartGale → `get_gale(score, c4_rate, confidence)`
8. `store_prediction(result.numbers, ...)`
9. Salva Decision no DB → `db_service.save_decision(decision)`
10. Envia `overlay_response` → extensão
11. Broadcast `trace_broadcast` → dashboard

**Dados enviados ao overlay (linhas 359-382):**
```python
overlay_response = {
    "type": "sugestao",
    "data": {
        "acao": acao,
        "numeros": result.numbers,         # Lista de números
        "centro": result.center,            # C1
        "centros": result.details.get("centers", [result.center]),  # [C1,C2,C3]
        "regiao": result.visual,            # "[C1] [C2] [C3]"
        "aposta": mg.current_bet,           # R$ valor da aposta
        "gale_level": mg.level,             # 1, 2 ou 3
        "estrategia": self.strategy.name,   # "SDA-21"
        ...
    }
}
```

#### 2.3.5 Banco de Dados (`database/models.py`)

**Tabela `decisions`:**
```
sda_center: int         → C1 (centro primário)
sda_centers: List[int]  → [C1, C2, C3]
sda_numbers: List[int]  → Todos os números apostados (21 ou 19)
gale_bet_value: int     → Valor da aposta (default=17, mas setado pelo BET_VALUES=21)
```

#### 2.3.6 Frontend Dashboard (`frontend/`)

**index.html** — Mostra:
- Ação (APOSTAR/PULAR) com cor verde/amarelo
- Centro (C1) — campo `result-center`
- Região (todos os números) — campo `result-region`
- Score SDA — campo `result-score`
- Performance squares (12 por direção × 4 listas)

**app.js** — `updateResultDisplay()` (linhas 264-271):
```javascript
el.resultCenter.textContent = result.centro;
el.resultRegion.textContent = result.numeros?.join(', ') || '--';
```

#### 2.3.7 Extensão/Overlay (`extension/content.js`)

**Overlay mostra:**
- Status (APOSTAR/PULAR/AGUARDANDO)
- Último número
- Região: `sugestao.regiao` (visual string) ou `Centros: C1, C2, C3`
- Gale display
- Aposta: `sugestao.aposta`

**Linha 466:**
```javascript
regiao.textContent = sugestao.regiao || `Centros: ${(sugestao.centros || [sugestao.centro]).join(', ')}`;
```

---

## 3. ARQUITETURA PROPOSTA — M15-ADA

### 3.1 Descrição da Estratégia M15-ADA

**Nome:** M15 Vec120 Adaptive Dual Algorithm  
**Conceito:** Offset adaptativo por direção — CW usa ErrDriven, CCW usa Bayesiano

```
┌────────────────────────────────────────────────────────────────────────┐
│                     M15-ADA — ARQUITETURA                              │
│                                                                        │
│  ENTRADA: sentido (CW/CCW), C1 (mediana ponderada), histórico         │
│                                                                        │
│  ┌─────────────────────────┐   ┌─────────────────────────┐            │
│  │    MÓDULO CW            │   │    MÓDULO CCW           │            │
│  │  (ErrDriven)            │   │  (Bayesiano)            │            │
│  │                         │   │                         │            │
│  │  EMA = α×erro + (1-α)  │   │  Para cada off 7..17:   │            │
│  │        × EMA_ant        │   │    hits = count_retro() │            │
│  │                         │   │  offset = argmax(hits)  │            │
│  │  α = 0.25               │   │  janela = 12 jogadas    │            │
│  │  EMA_init = 12          │   │  default = 14           │            │
│  │  Range: [8, 16]         │   │  warm-up = 5 jogadas    │            │
│  └───────────┬─────────────┘   └───────────┬─────────────┘            │
│              │ offset                       │ offset                   │
│              └──────────────┬───────────────┘                          │
│                             ▼                                          │
│  ┌──────────────────────────────────────────────────────────┐          │
│  │  POSICIONAMENTO                                          │          │
│  │                                                          │          │
│  │  C1 = mediana ponderada (INALTERADO)          raio = 3  │          │
│  │  C2 = WHEEL[(pos_C1 + offset) % 37]           raio = 2  │          │
│  │  C3 = WHEEL[(pos_C1 - offset) % 37]           raio = 2  │          │
│  │                                                          │          │
│  │  Cobertura = vizinhos(C1,3) ∪ vizinhos(C2,2) ∪          │          │
│  │              vizinhos(C3,2) = 7 + 5 + 5 = 17 números    │          │
│  └──────────────────────────────────────────────────────────┘          │
│                                                                        │
│  SAÍDA: StrategyResult(numbers=[17 nums], center=C1, ...)              │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Diferenças Chave SDA-21 → M15-ADA

| Aspecto | SDA-21 (Atual) | M15-ADA (Proposto) |
|:--------|:---------------|:-------------------|
| C1 cálculo | Mediana ponderada | **Inalterado** |
| C1 raio | 3 (7 números) | **Inalterado** |
| C2 cálculo | `_apply_force(max_force)` | `WHEEL[(pos_C1 + offset) % 37]` |
| C2 raio | 3 (7 números) | **2 (5 números)** |
| C3 cálculo | `_apply_force(min_force)` | `WHEEL[(pos_C1 - offset) % 37]` |
| C3 raio | 3 (7 números) | **2 (5 números)** |
| Offset | Fixo 12 (via _ensure_diversity) | **Adaptativo por direção** |
| Total números | 21 | **17** |
| _ensure_diversity | MIN_SEPARATION=7 | **Removido** (offset garante separação) |
| _force_spread | Se <18 nums | **Removido** (17 é o target) |
| Check <18 | Expandir raio para 4 | **Removido** |
| BET_VALUES | {1:21, 2:42, 3:63} | **{1:17, 2:34, 3:51}** |
| State version | 1.5.0 | **1.6.0** (com estado adaptativo) |
| Nome | SDA-21 | **M15-ADA** |
| Novo estado | — | **cw_ema, ccw_adaptive_history** |

### 3.3 Fluxo de Dados Proposto

```
┌─────────────────────────────────────────────────────────────────────┐
│                FLUXO MODIFICADO — M15-ADA                           │
│                                                                     │
│  1. message_handler recebe novo spin                                │
│  2. check_prediction(numero) → hit/miss                            │
│  3. ★ NOVO: strategy.update_adaptive(direction, c1, actual_result) │
│     │  CW: atualiza EMA com erro = circ_dist(c1, resultado)       │
│     │  CCW: adiciona (c1, resultado) ao histórico bayesiano        │
│  4. process_spin(numero, direcao)                                  │
│  5. strategy.analyze(timeline, last_number, wheel, direction)      │
│     │  ★ NOVO: recebe direction para selecionar algoritmo          │
│     │                                                               │
│     │  Pipeline interno:                                            │
│     │  a) _predict_robust() → predicted_force, score (inalterado) │
│     │  b) C1 = _apply_force(last_num, pred_force, dir)            │
│     │  c) ★ offset = _get_adaptive_offset(direction)              │
│     │     │  CW: clamp(round(ema), 8, 16)                        │
│     │     │  CCW: bayesian_retrospec(window=12) ou default=14     │
│     │  d) C2 = WHEEL[(pos_C1 + offset) % 37]                     │
│     │  e) C3 = WHEEL[(pos_C1 - offset) % 37]                     │
│     │  f) nums = neighbors(C1,3) ∪ neighbors(C2,2) ∪ neigh(C3,2) │
│     │  g) Retorna StrategyResult(numbers=[17], center=C1, ...)    │
│  6. Triple Rate, SmartGale (inalterados)                           │
│  7. store_prediction (com 17 números)                              │
│  8. Envia overlay_response (numeros=[17], aposta=R$17)             │
│  9. Broadcast trace (com offset info para debug)                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. INVENTÁRIO DETALHADO DE ALTERAÇÕES POR ARQUIVO

### 4.1 `strategies/sda17.py` — ALTERAÇÃO PRINCIPAL

**Impacto:** ALTO | **Risco:** MÉDIO | **Complexidade:** ALTA

#### 4.1.1 Mudanças nas Constantes (linhas 24-32)

**Antes:**
```python
MIN_SEPARATION = 7
SPREAD_OFFSET = 12
MAX_FORCE_THRESHOLD = 30

def __init__(self):
    super().__init__(name="SDA-21", num_neighbors=3)
    self.min_forces = 3
    self.default_window = 7
    self.decay = 0.8
    self.description = "IQR + Weighted Median + Drift, Triple Focus 21 números"
```

**Depois:**
```python
MAX_FORCE_THRESHOLD = 30

# M15-ADA: Constantes adaptativas
CW_ALPHA = 0.25           # Taxa de aprendizado EMA (CW)
CW_EMA_INIT = 12.0        # EMA inicial (CW)
CW_OFFSET_MIN = 8         # Offset mínimo (CW)
CW_OFFSET_MAX = 16        # Offset máximo (CW)
CCW_WINDOW = 12            # Janela bayesiana (CCW)
CCW_DEFAULT_OFFSET = 14    # Offset padrão durante warm-up (CCW)
CCW_WARMUP = 5             # Jogadas mínimas antes de adaptar (CCW)
CCW_OFFSET_MIN = 7         # Offset mínimo candidato (CCW)
CCW_OFFSET_MAX = 17        # Offset máximo candidato (CCW)
C2_RADIUS = 2              # Raio de C2 (5 números)
C3_RADIUS = 2              # Raio de C3 (5 números)

def __init__(self):
    super().__init__(name="M15-ADA", num_neighbors=3)  # C1 mantém raio 3
    self.min_forces = 3
    self.default_window = 7
    self.decay = 0.8
    self.description = "Adaptive Dual Algorithm, Triple Focus 17 números"
    # Estado adaptativo
    self.cw_ema = self.CW_EMA_INIT
    self.ccw_history = []  # [(c1, resultado), ...]
```

#### 4.1.2 Novo Método: `_get_adaptive_offset(direction)` 

```python
def _get_adaptive_offset(self, direction: str) -> int:
    """
    Retorna offset adaptativo baseado na direção.
    CW: ErrDriven (EMA de erro) — converge para offsets menores (8-10)
    CCW: Bayesiano retrospectivo — converge para offsets maiores (14-15)
    """
    if direction in ("cw", "horario"):
        return max(self.CW_OFFSET_MIN, min(self.CW_OFFSET_MAX, round(self.cw_ema)))
    else:
        return self._bayesian_offset()

def _bayesian_offset(self) -> int:
    """Bayesiano: testa todos offsets contra janela recente, retorna o melhor."""
    if len(self.ccw_history) < self.CCW_WARMUP:
        return self.CCW_DEFAULT_OFFSET
    
    window = self.ccw_history[-self.CCW_WINDOW:]
    best_off = self.CCW_DEFAULT_OFFSET
    best_hits = -1
    
    for test_off in range(self.CCW_OFFSET_MIN, self.CCW_OFFSET_MAX + 1):
        hits = 0
        for c1, result in window:
            # Simular cobertura com este offset
            c1_idx = self._wheel_index(c1)
            c2 = self._wheel_at((c1_idx + test_off) % 37)
            c3 = self._wheel_at((c1_idx - test_off) % 37)
            coverage = set(self.get_neighbors(c1, self.num_neighbors, self._wheel))
            coverage |= set(self.get_neighbors(c2, self.C2_RADIUS, self._wheel))
            coverage |= set(self.get_neighbors(c3, self.C3_RADIUS, self._wheel))
            if result in coverage:
                hits += 1
        if hits > best_hits:
            best_hits = hits
            best_off = test_off
    
    return best_off
```

#### 4.1.3 Novo Método: `update_adaptive(direction, c1, actual_result)`

```python
def update_adaptive(self, direction: str, c1: int, actual_result: int, 
                    wheel_sequence: List[int]) -> None:
    """
    Atualiza estado adaptativo após resultado conhecido.
    Deve ser chamado ANTES de analyze() do próximo spin.
    """
    if direction in ("cw", "horario"):
        # ErrDriven: atualizar EMA com erro
        error = self._circ_dist(c1, actual_result, wheel_sequence)
        self.cw_ema = self.CW_ALPHA * error + (1 - self.CW_ALPHA) * self.cw_ema
    else:
        # Bayesiano: adicionar ao histórico
        self.ccw_history.append((c1, actual_result))
        # Limitar histórico a 2× janela para não crescer indefinidamente
        max_history = self.CCW_WINDOW * 2
        if len(self.ccw_history) > max_history:
            self.ccw_history = self.ccw_history[-max_history:]
```

#### 4.1.4 Mudanças no `analyze()` (linhas 117-175)

**REMOVER:**
- Cálculo de C2 via `_apply_force(max_force)` (linha 121)
- Cálculo de C3 via `_apply_force(min_force)` (linha 124)
- `_ensure_diversity()` (linha 127)
- Check `len(numbers) < 18` e `_force_spread()` (linhas 136-141)
- Check secundário `len(numbers) < 18` com `num_neighbors + 1` (linhas 144-148)

**ADICIONAR:**
```python
# === M15-ADA: Triple Focus com offset adaptativo ===
c1 = self._apply_force(last_number, predicted_force, timeline.direction, wheel_sequence)

# Offset adaptativo baseado na direção
offset = self._get_adaptive_offset(timeline.direction)

# C2 e C3 posicionados simetricamente em relação a C1
c1_idx = wheel_sequence.index(c1)
wheel_size = len(wheel_sequence)
c2 = wheel_sequence[(c1_idx + offset) % wheel_size]
c3 = wheel_sequence[(c1_idx - offset) % wheel_size]

# Agregar números com raios assimétricos
nums = set()
nums |= set(self.get_neighbors(c1, self.num_neighbors, wheel_sequence))  # 7 nums
nums |= set(self.get_neighbors(c2, self.C2_RADIUS, wheel_sequence))      # 5 nums
nums |= set(self.get_neighbors(c3, self.C3_RADIUS, wheel_sequence))      # 5 nums
numbers = sorted(nums)  # Esperado: 17 (pode ser menos se houver overlap)
```

#### 4.1.5 Atualização do `details` no Retorno

**Adicionar ao dicionário `details`:**
```python
"offset": offset,
"offset_type": "errdriven" if timeline.direction in ("cw", "horario") else "bayesian",
"cw_ema": round(self.cw_ema, 2),
"ccw_history_size": len(self.ccw_history),
```

#### 4.1.6 Métodos a REMOVER

- `_ensure_diversity()` (linhas 304-334) — Não é mais necessário; offset adaptativo garante separação
- `_force_spread()` (linhas 336-348) — Não há mais mínimo de 18 números
- `calculate_momentum_offset()` (linhas 254-281) — Já estava desabilitado (momentum removido)

#### 4.1.7 Novo Método: Serialização do Estado Adaptativo

```python
def get_adaptive_state(self) -> Dict[str, Any]:
    """Retorna estado adaptativo para persistência."""
    return {
        "cw_ema": self.cw_ema,
        "ccw_history": self.ccw_history
    }

def load_adaptive_state(self, state: Dict[str, Any]) -> None:
    """Carrega estado adaptativo de persistência."""
    self.cw_ema = state.get("cw_ema", self.CW_EMA_INIT)
    self.ccw_history = state.get("ccw_history", [])
```

#### 4.1.8 Atualização da Assinatura de `analyze()`

**Antes:**
```python
def analyze(self, timeline, last_number, wheel_sequence, calibration=0, error_history=None):
```

**Nota:** A assinatura NÃO precisa mudar. O `timeline.direction` já está disponível dentro do objeto Timeline e é usado para `_apply_force()`. O M15-ADA usa `timeline.direction` para decidir qual algoritmo adaptativo usar.

---

### 4.2 `state/game.py` — ALTERAÇÃO MÉDIA

**Impacto:** MÉDIO | **Risco:** BAIXO | **Complexidade:** BAIXA

#### 4.2.1 MartingaleState.BET_VALUES (linha 39)

**Antes:**
```python
BET_VALUES: ClassVar[Dict[int, int]] = {1: 21, 2: 42, 3: 63}
```

**Depois:**
```python
BET_VALUES: ClassVar[Dict[int, int]] = {1: 17, 2: 34, 3: 51}
```

**Impacto downstream:**
- `current_bet` property retornará 17/34/51
- overlay exibirá R$17 em vez de R$21
- Decision.gale_bet_value registrará 17/34/51

#### 4.2.2 Estado Adaptativo no GameState

Adicionar ao `save()` e `load()`:

```python
# No save() — adicionar ao dict 'data':
"adaptive_state": self._adaptive_state if hasattr(self, '_adaptive_state') else {}

# No load() — restaurar:
gs._adaptive_state = data.get("adaptive_state", {})
```

**OU** (alternativa mais limpa): O estado adaptativo vive na estratégia, não no GameState. O message_handler chama `strategy.get_adaptive_state()` no save e `strategy.load_adaptive_state()` no load. Essa é a abordagem preferida pois mantém a separação de responsabilidades.

#### 4.2.3 Migração de Versão do state.json

**De:** `version: "1.5.0"` → **Para:** `version: "1.6.0"`

No `load()`, adicionar migração:
```python
# MIGRAÇÃO v1.5 -> v1.6
if version_tuple < (1, 6, 0):
    # Adicionar estado adaptativo vazio (será populado durante operação)
    # BET_VALUES mudam automaticamente (são ClassVar, não persistidos)
    pass
```

**Nota:** A migração é transparente — o estado adaptativo começa vazio e o sistema vai construindo conforme novas jogadas chegam. Não há dados a migrar.

#### 4.2.4 Docstrings da Classe MartingaleState

Atualizar docstring (linha 20-33) de:
```
Gales: 1× (R$21), 2× (R$42), 3× (R$63)
```
Para:
```
Gales: 1× (R$17), 2× (R$34), 3× (R$51)
```

---

### 4.3 `server/message_handler.py` — ALTERAÇÃO MÉDIA

**Impacto:** MÉDIO | **Risco:** BAIXO | **Complexidade:** MÉDIA

#### 4.3.1 Chamar `update_adaptive()` após verificação de resultado

No `handle_new_result()`, APÓS `check_prediction()` e ANTES de `process_spin()`:

**Inserir entre linhas ~153 e ~204:**
```python
# ★ M15-ADA: Atualizar estado adaptativo com resultado real
if pending and hit_result is not None and result_should_bet_was_true:
    bet_direction = pending.get("direction", "")
    c1_predicted = pending.get("center", 0)
    if c1_predicted > 0:
        self.strategy.update_adaptive(
            bet_direction, c1_predicted, numero, roulette.WHEEL_SEQUENCE
        )
```

**Ponto de inserção exato:** Após o bloco de atualização do Martingale (linha ~167) e antes de `process_spin()` (linha 205).

#### 4.3.2 Persistir Estado Adaptativo

No `save()` do game_state, incluir o estado adaptativo da estratégia:

**Opção A (simples):** Salvar junto com state.json
```python
# Após game_state.save()
adaptive_state = self.strategy.get_adaptive_state()
# Salvar em state.json via game_state ou em arquivo separado
```

**Opção B (limpa):** Arquivo separado `adaptive_state.json`
```python
import json
adaptive_path = settings.base_dir / "adaptive_state.json"
with open(adaptive_path, 'w') as f:
    json.dump(self.strategy.get_adaptive_state(), f)
```

**Recomendação:** Opção A (embutido no state.json) é mais simples e atômica.

#### 4.3.3 Restaurar Estado Adaptativo no Startup

No construtor do `MessageHandler` ou no `main.py`, após criar a estratégia:
```python
# Restaurar estado adaptativo (se existir)
state_data = game_state.to_dict()  # ou load from file
adaptive = state_data.get("adaptive_state", {})
strategy.load_adaptive_state(adaptive)
```

#### 4.3.4 Incluir Offset Info no Trace Broadcast

No `trace_broadcast` (linhas 388-417), adicionar ao `result`:
```python
"result": {
    ...
    "offset": result.details.get("offset", 12),
    "offset_type": result.details.get("offset_type", "fixed"),
    "cw_ema": result.details.get("cw_ema", 12.0),
}
```

---

### 4.4 `database/models.py` — ALTERAÇÃO MÍNIMA

**Impacto:** BAIXO | **Risco:** BAIXO | **Complexidade:** BAIXA

#### 4.4.1 Decision.gale_bet_value Default

**Antes:**
```python
gale_bet_value: int = 17
```

**Nota:** O default já é 17! Porém na prática era setado pelo MartingaleState.current_bet (21). Com a mudança do BET_VALUES, o valor real será 17. O default do campo não precisa mudar.

#### 4.4.2 Novo Campo Opcional (para análise)

**Considerar adicionar:**
```python
sda_offset: int = 0              # Offset usado nesta jogada
sda_offset_type: str = ""        # "errdriven" ou "bayesian"
```

Isso permite análise pós-fato de como os offsets evoluíram. **Opcional** — pode ser adicionado em versão futura.

---

### 4.5 `frontend/app.js` — ALTERAÇÃO BAIXA

**Impacto:** BAIXO | **Risco:** BAIXO | **Complexidade:** BAIXA

#### 4.5.1 Atualizar Display de Números (updateResultDisplay)

**Antes (linhas 264-271):**
```javascript
el.resultRegion.textContent = result.numeros?.join(', ') || '--';
```

**Depois:** (manter compatível — os números ainda são uma lista)
```javascript
// Números agora são 17 em vez de 21 — display funciona igual
el.resultRegion.textContent = result.numeros?.join(', ') || '--';
```

**Nota:** O display de números é genérico (join com vírgula). Funciona para qualquer quantidade. **Nenhuma alteração obrigatória** no app.js.

#### 4.5.2 Evolução Futura: Agrupar C1/C2/C3

Para melhor visualização, **opcionalmente** evoluir para:
```javascript
if (result.centros && result.centros.length >= 3) {
    const c1 = result.centros[0], c2 = result.centros[1], c3 = result.centros[2];
    el.resultRegion.innerHTML = 
        `<b>[${c1}±3]</b> | <b>[${c2}±2]</b> | <b>[${c3}±2]</b>`;
}
```

Isso mostra os centros com seus raios, facilitando a compreensão visual. **Não é obrigatório para o MVP.**

---

### 4.6 `frontend/index.html` — SEM ALTERAÇÃO OBRIGATÓRIA

Os elementos existentes (`result-center`, `result-region`, `result-score`) já funcionam com 17 números. Nenhuma mudança de HTML é necessária para o MVP.

**Evolução opcional:** Adicionar campo de offset para debug:
```html
<div class="detail"><span>Offset:</span><span id="result-offset">--</span></div>
```

---

### 4.7 `extension/content.js` — ALTERAÇÃO MÍNIMA

**Impacto:** BAIXO | **Risco:** BAIXO | **Complexidade:** BAIXA

#### 4.7.1 Aposta Default (linha 72)

**Antes:**
```javascript
R$ <span id="eb-aposta">17</span>
```

**Nota:** O default já é 17! E o valor real vem de `sugestao.aposta` (que virá como 17 do backend). **Nenhuma alteração necessária.**

#### 4.7.2 Região Display (linha 466)

```javascript
regiao.textContent = sugestao.regiao || `Centros: ${(sugestao.centros || [sugestao.centro]).join(', ')}`;
```

O `sugestao.regiao` virá como `"[C1] [C2] [C3]"` (do `result.visual` no backend). **Funciona sem alteração.**

---

### 4.8 `app_config/settings.py` — ALTERAÇÃO OPCIONAL

**Considerar adicionar:**
```python
class AdaptiveSettings(BaseSettings):
    cw_alpha: float = 0.25
    cw_ema_init: float = 12.0
    cw_offset_min: int = 8
    cw_offset_max: int = 16
    ccw_window: int = 12
    ccw_default_offset: int = 14
    ccw_warmup: int = 5
    c2_radius: int = 2
    c3_radius: int = 2

class Settings(BaseSettings):
    ...
    adaptive: AdaptiveSettings = Field(default_factory=AdaptiveSettings)
```

**Benefício:** Permite tunar parâmetros via variáveis de ambiente sem alterar código.
**Alternativa:** Manter como constantes na classe da estratégia (mais simples para MVP).

---

### 4.9 `state.json` — MIGRAÇÃO AUTOMÁTICA

**Antes (v1.5.0):**
```json
{
    "version": "1.5.0",
    "last_number": 17,
    "last_direction": "horario",
    "timeline_cw": {...},
    "timeline_ccw": {...},
    "performance_sda17_cw": [...],
    "performance_sda17_ccw": [...],
    "performance_bet_cw": [...],
    "performance_bet_ccw": [...],
    "martingale_cw": {...},
    "martingale_ccw": {...},
    "pending_prediction": {...}
}
```

**Depois (v1.6.0):**
```json
{
    "version": "1.6.0",
    "last_number": 17,
    "last_direction": "horario",
    "timeline_cw": {...},
    "timeline_ccw": {...},
    "performance_sda17_cw": [...],
    "performance_sda17_ccw": [...],
    "performance_bet_cw": [...],
    "performance_bet_ccw": [...],
    "martingale_cw": {...},
    "martingale_ccw": {...},
    "pending_prediction": {...},
    "adaptive_state": {
        "cw_ema": 12.0,
        "ccw_history": []
    }
}
```

---

## 5. IMPACTO EM COMPONENTES NÃO MODIFICADOS

### 5.1 Componentes que NÃO Mudam

| Componente | Arquivo | Razão |
|:-----------|:--------|:------|
| Pipeline de predição | `_predict_robust()` | C1 cálculo inalterado |
| Wheel Sequence | `core/roulette.py` | Constante física |
| Timeline | `state/timeline.py` | Apenas armazena forças |
| Triple Rate Advisor | `state/bet_advisor.py` | Analisa performance, não números |
| WebSocket Server | `server/websocket.py` | Transport layer |
| Connection Manager | `server/connection_manager.py` | Gerenciamento de conexões |
| Extractor Service | `server/extractor_service.py` | Captura de dados da mesa |
| Analytics Handler | `server/analytics_handler.py` | Queries ao banco |
| Input/Output Models | `models/*.py` | Validação de I/O |
| SQLite Repository | `database/sqlite_repo.py` | Schema não muda |
| Background Script | `extension/background.js` | Comunicação Chrome |

### 5.2 Verificação de Compatibilidade

| Interface | Antes | Depois | Compatível? |
|:----------|:------|:-------|:-----------:|
| `StrategyResult.numbers` | `List[int]` (21 items) | `List[int]` (17 items) | ✅ |
| `StrategyResult.center` | `int` (C1) | `int` (C1) | ✅ |
| `StrategyResult.details["centers"]` | `[C1,C2,C3]` | `[C1,C2,C3]` | ✅ |
| `overlay_response.numeros` | 21 números | 17 números | ✅ |
| `overlay_response.aposta` | 21 | 17 | ✅ |
| `trace_broadcast.result.numeros` | 21 números | 17 números | ✅ |
| `Decision.sda_numbers` | 21 números | 17 números | ✅ |
| `pending_prediction.numbers` | 21 números | 17 números | ✅ |
| `check_prediction()` | `actual in numbers` | `actual in numbers` | ✅ |

**Conclusão:** A migração é backward-compatible em todas as interfaces. Nenhum consumidor precisa saber que agora são 17 números em vez de 21.

---

## 6. PLANO DE TESTES

### 6.1 Testes Unitários

| # | Teste | Arquivo | Descrição |
|:-:|:------|:--------|:----------|
| T1 | `test_c2_c3_radius` | strategies/sda17.py | C2 e C3 retornam 5 números cada (raio 2) |
| T2 | `test_total_coverage` | strategies/sda17.py | Total ≤ 17 números (pode ser menos com overlap) |
| T3 | `test_errdriven_convergence` | strategies/sda17.py | EMA converge para ~8-10 com dados CW |
| T4 | `test_bayesian_convergence` | strategies/sda17.py | Offset converge para ~14-15 com dados CCW |
| T5 | `test_adaptive_persistence` | strategies/sda17.py | save/load do estado adaptativo |
| T6 | `test_bet_values` | state/game.py | BET_VALUES = {1:17, 2:34, 3:51} |
| T7 | `test_state_migration` | state/game.py | v1.5.0 → v1.6.0 sem erro |
| T8 | `test_ccw_warmup` | strategies/sda17.py | Offset=14 durante warm-up CCW |

### 6.2 Testes de Integração

| # | Teste | Descrição |
|:-:|:------|:----------|
| I1 | `test_full_spin_cycle` | Processar spin → analyze → verify → next spin |
| I2 | `test_adaptive_update_flow` | Verificar que update_adaptive é chamado no fluxo |
| I3 | `test_overlay_response` | Verificar que overlay recebe 17 números e R$17 |
| I4 | `test_trace_broadcast` | Verificar que trace contém offset info |
| I5 | `test_db_decision_logging` | Verificar que Decision salva corretamente com 17 números |

### 6.3 Teste de Regressão

| # | Teste | Descrição |
|:-:|:------|:----------|
| R1 | `test_sda19_fallback` | SDA-19 (early-session) continua funcionando com raio 9 |
| R2 | `test_performance_tracking` | SDA17 e BET performance tracking inalterado |
| R3 | `test_kill_switch` | Triple Rate Advisor continua vetando corretamente |
| R4 | `test_martingale_flow` | Gale 1→2→3 funciona com novos BET_VALUES |

---

## 7. TAREFAS DE IMPLANTAÇÃO

### 7.1 Lista de Tarefas (Ordem de Execução)

```
FASE 1: CORE (Estratégia)
├── T01: Adicionar constantes M15-ADA ao sda17.py
├── T02: Implementar _get_adaptive_offset()
├── T03: Implementar _bayesian_offset()
├── T04: Implementar update_adaptive()
├── T05: Implementar get_adaptive_state() / load_adaptive_state()
├── T06: Refatorar analyze() para usar offset adaptativo e raios assimétricos
├── T07: Remover _ensure_diversity(), _force_spread(), calculate_momentum_offset()
├── T08: Atualizar docstrings e nome da classe (SDA-21 → M15-ADA)
└── T09: Helper methods (_circ_dist, _wheel_index, _wheel_at)

FASE 2: ESTADO (Persistência)
├── T10: Atualizar BET_VALUES em MartingaleState
├── T11: Adicionar adaptive_state ao save()/load() do GameState
├── T12: Implementar migração v1.5.0 → v1.6.0
└── T13: Atualizar docstrings do MartingaleState

FASE 3: SERVIDOR (Integração)
├── T14: Inserir chamada update_adaptive() no handle_new_result()
├── T15: Persistir estado adaptativo no fluxo de save
├── T16: Restaurar estado adaptativo no startup
├── T17: Adicionar offset info ao trace_broadcast
└── T18: Verificar compatibilidade do overlay_response

FASE 4: FRONTEND (Display)
├── T19: (Opcional) Agrupar C1/C2/C3 no dashboard
└── T20: (Opcional) Adicionar campo de offset para debug

FASE 5: TESTES
├── T21: Executar suite de testes existente
├── T22: Criar testes unitários para novos métodos
├── T23: Teste de integração end-to-end
└── T24: Teste de regressão (SDA-19 fallback, Kill Switch, Martingale)

FASE 6: VALIDAÇÃO
├── T25: Shadow mode — comparar M15-ADA vs SDA-21 em 50+ jogadas
├── T26: Verificar logs de offset evolution
└── T27: Confirmar EV positivo em produção
```

### 7.2 Dependências entre Tarefas

```
T01 ──→ T02 ──→ T06
T01 ──→ T03 ──→ T06
T01 ──→ T04
T01 ──→ T05 ──→ T11 ──→ T15
T01 ──→ T09 ──→ T02, T03, T04
T06 ──→ T07
T10 ──→ T13
T04 ──→ T14
T05 ──→ T16
T06 ──→ T17, T18
T14 ──→ T21-T27
```

### 7.3 Estimativa de Impacto por Arquivo

| Arquivo | Linhas Alteradas | Linhas Adicionadas | Linhas Removidas | Risco |
|:--------|:----------------:|:------------------:|:----------------:|:-----:|
| `strategies/sda17.py` | ~30 | ~80 | ~60 | MÉDIO |
| `state/game.py` | ~10 | ~15 | ~0 | BAIXO |
| `server/message_handler.py` | ~5 | ~15 | ~0 | BAIXO |
| `database/models.py` | ~0 | ~2 (opcional) | ~0 | MÍNIMO |
| `frontend/app.js` | ~0 | ~5 (opcional) | ~0 | MÍNIMO |
| `frontend/index.html` | ~0 | ~3 (opcional) | ~0 | MÍNIMO |
| `extension/content.js` | ~0 | ~0 | ~0 | NENHUM |
| `app_config/settings.py` | ~0 | ~12 (opcional) | ~0 | MÍNIMO |
| **TOTAL** | **~45** | **~132** | **~60** | **BAIXO-MÉDIO** |

---

## 8. ROLLBACK PLAN

### 8.1 Estratégia de Rollback

Caso o M15-ADA apresente resultados inferiores em produção:

1. **Git revert:** Todo o código estará em um branch separado. `git revert` volta ao SDA-21.
2. **state.json:** A migração v1.6.0 é forward-compatible. Reverter para v1.5.0:
   - Simplesmente ignorar o campo `adaptive_state` (não afeta nada)
   - Ou deletar `state.json` e deixar resetar
3. **BET_VALUES:** Voltar de {1:17, 2:34, 3:51} para {1:21, 2:42, 3:63}
4. **Database:** Decisões salvas com 17 números são válidas historicamente. Não precisam de rollback.

### 8.2 Feature Flag (Recomendado)

Implementar flag para alternar entre estratégias sem deploy:

```python
# app_config/settings.py
class GameSettings(BaseSettings):
    strategy_mode: str = "m15_ada"  # "sda_21" ou "m15_ada"
```

```python
# strategies/sda17.py
def analyze(self, ...):
    if settings.game.strategy_mode == "sda_21":
        return self._analyze_sda21(...)  # Código original preservado
    else:
        return self._analyze_m15_ada(...)  # Novo código
```

---

## 9. MÉTRICAS DE SUCESSO

### 9.1 Critérios para Validação

| Métrica | Mínimo Aceitável | Target | Método de Verificação |
|:--------|:----------------:|:------:|:---------------------|
| HR Total | > 47.2% | > 50% | 100+ jogadas em produção |
| HR CW | > 50% | > 55% | 50+ jogadas CW |
| HR CCW | > 40% | > 45% | 50+ jogadas CCW |
| EV/jogada | > R$0 | > R$1 | Cálculo: HR×36 - 17 |
| Convergência CW | < 15 jogadas | ~10 | Monitorar EMA evolution |
| Convergência CCW | < 40 jogadas | ~30 | Monitorar offset evolution |
| Uptime | 100% | 100% | Sem crashes/erros |

### 9.2 Monitoramento Pós-Implantação

1. **Primeiras 20 jogadas:** Verificar que offsets estão sendo calculados (não fixos)
2. **Primeiras 50 jogadas:** Verificar convergência do EMA (CW) e Bayesian (CCW)
3. **Primeiras 100 jogadas:** Comparar HR real vs simulação (51.4% target)
4. **Ongoing:** Dashboard de offset evolution (futuro)

---

## 10. CHECKLIST PRÉ-IMPLANTAÇÃO

- [ ] Documento de análise finalizado (analise_c1_c2_c3.md Partes 18-22) ✅
- [ ] Plano de implantação aprovado (este documento) 
- [ ] Branch criado: `feature/m15-ada`
- [ ] Backup do state.json atual
- [ ] Testes existentes passando (baseline)
- [ ] Implementação das Fases 1-3
- [ ] Testes novos escritos e passando (Fase 5)
- [ ] Shadow mode validado (Fase 6, T25)
- [ ] Deploy em produção
- [ ] Monitoramento 100+ jogadas

---

## 11. AUDITORIA DE BUGS — `main.py`

> **Escopo:** Entry point do sistema (78 LOC)  
> **Arquivo:** `main.py` + dependências diretas (`server/websocket.py`)  
> **Método:** Análise estática linha a linha + verificação de edge cases

### 11.1 Bugs Encontrados

| ID | Severidade | Linha | Descrição | Impacto |
|----|:----------:|:-----:|-----------|---------|
| BUG-MAIN-001 | 🟡 Médio | 51-52 | `signal.SIGTERM` não existe no Windows. Em dev local Windows, o handler falha silenciosamente (registra mas nunca dispara). Em produção Docker (Linux), funciona normalmente. | Shutdown graceful não funciona em dev Windows via `docker stop` ou `taskkill`. |
| BUG-MAIN-002 | 🟡 Médio | 51+73 | **Double shutdown potencial:** `signal.SIGINT` (linha 51) e `except KeyboardInterrupt` (linha 72) ambos capturam Ctrl+C. O `asyncio.run()` internamente também instala handler SIGINT. Race condition: `handle_shutdown()` pode executar 2×, tentando `game_state.save()` e `db_service.end_session()` duas vezes. | Corrupção de state.json (escrita dupla concorrente) ou erro no DB (sessão já finalizada). |
| BUG-MAIN-003 | 🔵 Baixo | 57 | `open("VERSION", "r")` usa path relativo ao CWD. Se executado de diretório diferente (ex: `python src/main.py` ou Docker com WORKDIR diferente), o VERSION não é encontrado e a versão mostra "unknown". | Cosmético — não afeta funcionalidade. |
| BUG-MAIN-004 | 🟡 Médio | 35 | `game_state.save()` no signal handler sem try/except. Se falhar (disco cheio, permissão), a sessão no DB não será finalizada (linhas 37-43 não executam). | Perda de estado + sessão DB não fechada = stats incorretos. |
| BUG-MAIN-005 | 🟡 Médio | 45 | `sys.exit(0)` dentro de signal handler em asyncio event loop. `sys.exit()` levanta `SystemExit`, que interrompe abruptamente o event loop sem cleanup de tasks async, WebSocket connections, ou DB connections. | Conexões WebSocket não fecham gracefully; clientes recebem disconnect abrupto sem motivo. |
| BUG-MAIN-006 | 🔵 Baixo | 27 | `from server.websocket import game_state` faz `GameState.load()` durante **import time** (websocket.py:28). Se state.json corrompido, o erro ocorre antes de `main()` executar, sem log configurado. | Error handling limitado — `GameState.load()` já tem try/except mas sem logging (logger não existe ainda). |
| BUG-MAIN-007 | 🔵 Info | 38-39 | Imports lazy dentro do signal handler (`from database.service import db_service`). Se o módulo tiver erro de importação, o shutdown será incompleto silenciosamente. | Risco teórico — na prática o módulo já foi importado anteriormente. |

### 11.2 Análise Detalhada dos Bugs Críticos

#### BUG-MAIN-002: Double Shutdown (Race Condition)

```python
# FLUXO ATUAL (com bug):

# 1. Usuário pressiona Ctrl+C
# 2. Python entrega SIGINT ao signal handler registrado na linha 51
# 3. handle_shutdown() executa → game_state.save() → sys.exit(0)
# 4. sys.exit(0) levanta SystemExit
# 5. SystemExit NÃO é KeyboardInterrupt → except na linha 72 NÃO captura
# → Resultado: shutdown executa 1x (OK neste caso)

# MAS: asyncio.run() instala seu PRÓPRIO handler SIGINT que chama loop.stop()
# Se o asyncio handler executa ANTES do nosso:
# 1. asyncio cancela tasks → KeyboardInterrupt propaga
# 2. except KeyboardInterrupt (linha 72) captura
# 3. handle_shutdown(None, None) executa (2ª vez)
# → Resultado: shutdown executa 2x (BUG!)
```

**Correção recomendada:**
```python
# SUBSTITUIR linhas 32-45 + 70-73 por:

_shutdown_called = False

def handle_shutdown(signum, frame):
    global _shutdown_called
    if _shutdown_called:
        return  # Prevenir double shutdown
    _shutdown_called = True
    
    logger.info("shutdown_requested", signal=signum)
    try:
        game_state.save()
    except Exception as e:
        logger.error(f"Erro ao salvar estado: {e}")
    
    try:
        from database.service import db_service
        from server.websocket import message_handler
        if hasattr(message_handler, 'current_session_id') and message_handler.current_session_id:
            db_service.end_session(message_handler.current_session_id)
    except Exception as e:
        logger.warning(f"Erro ao finalizar sessão: {e}")
    
    logger.info("state_saved")
    sys.exit(0)
```

#### BUG-MAIN-005: sys.exit() em asyncio

**Correção ideal (para implementação futura):**
```python
async def start_server():
    ...
    stop_event = asyncio.Event()
    
    def request_shutdown(signum, frame):
        stop_event.set()
    
    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    
    async with websockets.serve(...):
        await stop_event.wait()  # Espera sinal de shutdown
    
    # Cleanup graceful DENTRO do event loop
    game_state.save()
    db_service.end_session(...)
```

### 11.3 Classificação por Prioridade para M15-ADA

| Prioridade | Bug | Ação na Implantação |
|:----------:|-----|:-------------------:|
| **P1** | BUG-MAIN-002 | Corrigir — flag `_shutdown_called` previne double save do novo adaptive_state |
| **P1** | BUG-MAIN-004 | Corrigir — try/except no save() garante que adaptive_state não corrompe |
| **P2** | BUG-MAIN-005 | Postergar — requer refactor significativo do startup; não bloqueia M15-ADA |
| **P3** | BUG-MAIN-001 | Postergar — produção é Docker/Linux; irrelevante para M15-ADA |
| **P3** | BUG-MAIN-003 | Postergar — cosmético |
| **P4** | BUG-MAIN-006/007 | Informativo — não requer ação |

### 11.4 Impacto dos Bugs no M15-ADA

O **BUG-MAIN-002** é particularmente relevante para o M15-ADA porque:

1. O novo `adaptive_state` (cw_ema + ccw_history) será persistido no `game_state.save()`
2. Se `save()` executar 2× concorrentemente (double shutdown), o state.json pode ficar corrompido
3. A flag `_shutdown_called` é uma proteção simples e essencial

O **BUG-MAIN-004** é relevante porque:
1. Se `game_state.save()` falhar no shutdown, o adaptive_state (EMA e histórico bayesiano) será perdido
2. Na próxima sessão, o sistema volta ao warm-up (~30 jogadas CCW para convergir)
3. Com try/except, pelo menos a sessão DB é finalizada corretamente

---

## 12. DIRETRIZES ISO/IEC 25010 PARA O M15-ADA

> **Referência:** Manutenabilidade_iso.md — Scorecard atual: 7.9/10

### 12.1 Impacto por Característica ISO

| # | Característica | Score Atual | Impacto M15-ADA | Score Esperado | Ação |
|:-:|:--------------|:----------:|:---------------:|:--------------:|:-----|
| 1 | Adequação Funcional | 8.7 | ↑ Positivo | **9.0** | M15-ADA adiciona adaptação inteligente por direção |
| 2 | Eficiência | 8.7 | → Neutro | 8.7 | Pipeline O(n) mantido; Bayesian O(11×12) = O(132) — desprezível |
| 3 | Compatibilidade | 7.0 | → Neutro | 7.0 | Interfaces WebSocket inalteradas |
| 4 | Usabilidade | 8.0 | ↑ Positivo | **8.2** | Offset info no trace melhora diagnóstico |
| 5 | Confiabilidade | 8.5 | → Neutro | 8.5 | Migração state.json transparente |
| 6 | Segurança | 6.5 | → Neutro | 6.5 | Sem mudanças em auth/crypto |
| 7 | Manutenibilidade | 7.5 | ↑↓ Misto | **7.5** | +Testabilidade (novos testes) / -Complexidade (novo estado) |
| 8 | Portabilidade | 8.0 | → Neutro | 8.0 | Docker/ENV inalterados |

### 12.2 Requisitos de Conformidade para Cada Mudança

#### 12.2.1 Adequação Funcional

| Requisito ISO | Aplicação no M15-ADA | Verificação |
|:-------------|:--------------------|:-----------|
| **Completude:** Todas as funções necessárias estão implementadas | `_get_adaptive_offset()`, `update_adaptive()`, `_bayesian_offset()` devem cobrir TODOS os cenários (CW/CCW/warm-up/edge cases) | Testes unitários T2-T8 |
| **Correção:** Resultados corretos | offset range [7,17] para CCW, [8,16] para CW; EMA convergence testada | Teste T3, T4 com dados reais |
| **Pertinência:** Sem funcionalidade desnecessária | Remover `_ensure_diversity()`, `_force_spread()`, `calculate_momentum_offset()` — código morto | Code review + grep por referências |

#### 12.2.2 Eficiência de Desempenho

| Requisito ISO | Aplicação no M15-ADA | Verificação |
|:-------------|:--------------------|:-----------|
| **Tempo:** Latência < 50ms mantida | Bayesian: 11 offsets × 12 jogadas × O(17) coverage check = ~2.200 ops — ~0.1ms | Benchmark com TraceContext |
| **Recursos:** Memória controlada | `ccw_history` limitado a 2×window = 24 entries (tuplas de 2 ints) | Verificar no código |
| **Capacidade:** Sem degradação com volume | EMA é O(1) por jogada; Bayesian é O(11×W) — W fixo em 12 | Análise de complexidade |

#### 12.2.3 Confiabilidade

| Requisito ISO | Aplicação no M15-ADA | Verificação |
|:-------------|:--------------------|:-----------|
| **Maturidade:** Tratamento de exceções | `_get_adaptive_offset()` com fallback para offset fixo se erro | Try/except em cada novo método |
| **Disponibilidade:** Sem interrupção | Migração v1.5→v1.6 transparente; adaptive_state vazio = warm-up natural | Teste de migração T7 |
| **Tolerância:** Dados corrompidos | `load_adaptive_state()` com valores default se JSON inválido | Teste com state.json corrompido |
| **Recuperabilidade:** Estado restaurável | `get_adaptive_state()` salva EMA + histórico; `load_adaptive_state()` restaura | Teste T5 |

#### 12.2.4 Manutenibilidade

| Requisito ISO | Aplicação no M15-ADA | Verificação |
|:-------------|:--------------------|:-----------|
| **Modularidade:** Baixo acoplamento | Estado adaptativo DENTRO da estratégia (não no GameState) | Review de dependências |
| **Reusabilidade:** Componentes reutilizáveis | `_bayesian_offset()` e `_errdriven_offset()` podem ser usados por futuras estratégias | Interface clara |
| **Analisabilidade:** Offset info nos logs | `result.details["offset"]`, `result.details["offset_type"]`, `result.details["cw_ema"]` | Verificar trace_broadcast |
| **Modificabilidade:** Parâmetros configuráveis | Constantes de classe (CW_ALPHA, CCW_WINDOW, etc.) — não hardcoded em métodos | Code review |
| **Testabilidade:** Novos testes | 8 testes unitários (T1-T8) + 5 integração (I1-I5) + 4 regressão (R1-R4) | pytest suite |

### 12.3 Checklist ISO/IEC 25010 Pré-Deploy

```
ADEQUAÇÃO FUNCIONAL
[ ] Todos os cenários de offset cobertos (CW/CCW/warm-up/edge)
[ ] Fallback SDA-19 continua funcionando com raio 9
[ ] 17 números retornados (não 21)
[ ] Código morto removido (_ensure_diversity, _force_spread, calc_momentum)

EFICIÊNCIA
[ ] Latência < 50ms confirmada via TraceContext
[ ] ccw_history limitado a 24 entries
[ ] Nenhum loop infinito nos novos métodos

CONFIABILIDADE
[ ] Migração v1.5→v1.6 testada (load de state.json v1.5)
[ ] adaptive_state vazio → warm-up funciona
[ ] state.json corrompido → fallback para defaults
[ ] BUG-MAIN-002 corrigido (flag _shutdown_called)
[ ] BUG-MAIN-004 corrigido (try/except no save)

SEGURANÇA
[ ] Nenhum dado sensível exposto nos novos campos de trace
[ ] offset_type não revela lógica interna para clientes não confiáveis

MANUTENIBILIDADE
[ ] Docstrings em todos os novos métodos
[ ] Type hints completos
[ ] Testes escritos e passando (T1-T8, I1-I5, R1-R4)
[ ] Constantes parametrizáveis (não hardcoded em métodos)

PORTABILIDADE
[ ] Docker funciona com nova versão
[ ] ENV vars não alteradas (backward compatible)
```

---

## 13. ANOTAÇÕES PÓS-IMPLANTAÇÃO PARA `Manutenabilidade_iso.md`

> **Instruções:** Após a implantação do M15-ADA, as seguintes alterações devem ser feitas no documento `Manutenabilidade_iso.md` para manter a conformidade ISO/IEC 25010 atualizada.

### 13.1 Alterações na PARTE I — Arquitetura

#### Seção 1 — Visão Geral (linha 17)

**Substituir:**
```
aplica análise estatística com a estratégia proprietária SDA-19
```
**Por:**
```
aplica análise estatística com a estratégia proprietária M15-ADA (Adaptive Dual Algorithm)
```

#### Seção 2 — Estrutura de Diretórios (linhas 72-73)

**Substituir:**
```
│   └── sda17.py                     # SDA-19 (IQR + Weighted Median + Drift)
```
**Por:**
```
│   └── sda17.py                     # M15-ADA (IQR + Weighted Median + Drift + Adaptive Offset)
```

#### Seção 3 — Diagrama de Componentes (linhas 167-174)

**Substituir bloco strategies/:**
```
│  strategies/    │  │  ├── game.py (GameState)     │
│  sda17.py       │  │  │   • Duas timelines        │
│  • IQR filter   │  │  │   • 4 listas performance  │
│  • Weighted Med │  │  │   • 2 Martingales (CW/CCW)│
│  • Drift detect │  │  │   • Persistência atômica  │
│  • Smart Score  │  │  ├── timeline.py (deque)     │
│  • 19 números   │  │  └── bet_advisor.py          │
```
**Por:**
```
│  strategies/    │  │  ├── game.py (GameState)     │
│  sda17.py       │  │  │   • Duas timelines        │
│  • IQR filter   │  │  │   • 4 listas performance  │
│  • Weighted Med │  │  │   • 2 Martingales (CW/CCW)│
│  • Drift detect │  │  │   • Persistência atômica  │
│  • Smart Score  │  │  │   • Adaptive state (EMA+  │
│  • Adaptive Off │  │  │     Bayesian history)      │
│  • 17 números   │  │  ├── timeline.py (deque)     │
│  (CW:ErrDriven  │  │  └── bet_advisor.py          │
│   CCW:Bayesian) │  │                              │
```

#### Seção 4 — Fluxo de Dados (linha 240-245)

**Substituir:**
```
6.                                   SDA-19 analyze(target_timeline)
                                     ├── IQR outlier rejection
                                     ├── Weighted median (decay=0.8)
                                     ├── Drift detection
                                     ├── Smart Score (1-6)
                                     └── 19 vizinhos do centro
```
**Por:**
```
5.5                                  ★ M15-ADA: update_adaptive(direction, c1, resultado)
                                     ├── CW: EMA = 0.25×erro + 0.75×EMA (ErrDriven)
                                     └── CCW: append (c1, resultado) ao histórico

6.                                   M15-ADA analyze(target_timeline)
                                     ├── IQR outlier rejection
                                     ├── Weighted median (decay=0.8)
                                     ├── Drift detection
                                     ├── Smart Score (1-6)
                                     ├── C1 = _apply_force(pred_force) [raio 3 = 7 nums]
                                     ├── offset = _get_adaptive_offset(direction)
                                     │   ├── CW: clamp(round(EMA), 8, 16)
                                     │   └── CCW: argmax retrospectivo (janela 12)
                                     ├── C2 = WHEEL[(C1 + offset)] [raio 2 = 5 nums]
                                     ├── C3 = WHEEL[(C1 - offset)] [raio 2 = 5 nums]
                                     └── Total: 17 números (7+5+5)
```

#### Seção 6 — Pipeline de Decisão (linhas 316-354)

**Adicionar após Smart Score:**
```
                    ┌─────────▼──────────┐
                    │  Adaptive Offset   │  CW: EMA(α=0.25) → offset [8,16]
                    │  (M15-ADA)          │  CCW: Bayesian(w=12) → offset [7,17]
                    └─────────┬──────────┘
                              │ {C1 raio 3, C2 raio 2, C3 raio 2}
```

**Substituir:**
```
                    │  • 19 números   │
```
**Por:**
```
                    │  • 17 números   │
                    │  • Adapt. Offset│
```

### 13.2 Alterações na PARTE II — Análise ISO

#### Seção 1.1 — Completude Funcional (tabela, linha ~601)

**Adicionar linha:**
```
| Offset adaptativo por direção | ✅ Completo | M15-ADA: CW=ErrDriven(α=0.25), CCW=Bayesian(w=12), persistência estado |
```

#### Seção 1.2 — Correção Funcional (tabela, linha ~612)

**Adicionar linhas:**
```
| Offset CW converge para 6-8 | ✅ | Simulação 52 jogadas: EMA estabiliza em ~10 jogadas |
| Offset CCW converge para 14-15 | ✅ | Simulação 53 jogadas: Bayesian estabiliza em ~30 jogadas |
| 17 números = 7+5+5 | ✅ | C1 raio 3, C2/C3 raio 2, verificado em testes |
```

#### Seção 2.1 — Comportamento Temporal (tabela, linha ~639)

**Adicionar linha:**
```
| Overhead M15-ADA (Bayesian) | < 0.1ms | 11 offsets × 12 jogadas × O(17) = ~2.200 ops triviais |
```

#### Seção 7.1 — Modularidade (diagrama, linha ~855)

**Atualizar:**
```
strategies/sda17.py  ──► strategies.base, state.timeline       [2] ✅ Bom
```
**Para:**
```
strategies/sda17.py  ──► strategies.base, state.timeline       [2] ✅ Bom
                         + estado adaptativo interno (EMA, history)
```

#### Seção 7.3 — Cobertura de Testes (tabela, linha ~908)

**Atualizar:**
```
| `strategies/sda17.py` | 280+ | `test_sda17.py` (56+) + `test_m15ada.py` (XX) | ✅ Boa |
```

### 13.3 Alterações na PARTE IV — Bugs

**Adicionar novos bugs encontrados:**

```
| BUG-MAIN-001 | `main.py` | 🟡 Média | `signal.SIGTERM` não funciona no Windows — shutdown não responde a `docker stop` em dev local Windows | 51-52 |
| BUG-MAIN-002 | `main.py` | 🟡 Média | Double shutdown: SIGINT handler + KeyboardInterrupt ambos chamam `handle_shutdown()` — race condition com asyncio | 51+73 |
| BUG-MAIN-004 | `main.py` | 🟡 Média | `game_state.save()` no signal handler sem try/except — falha no save impede finalização da sessão DB | 35 |
| BUG-MAIN-005 | `main.py` | 🟡 Média | `sys.exit(0)` em signal handler interrompe asyncio event loop abruptamente — WebSocket connections não fecham gracefully | 45 |
```

**Adicionar correções aplicadas (após implantação):**

```
| BUG-MAIN-002 | `main.py` | ~~🟡 Média~~ ✅ CORRIGIDO | Flag `_shutdown_called` previne double shutdown (M15-ADA implantação) | 32-45 |
| BUG-MAIN-004 | `main.py` | ~~🟡 Média~~ ✅ CORRIGIDO | try/except em game_state.save() no handler (M15-ADA implantação) | 35 |
```

### 13.4 Alterações na PARTE III — Scorecard

**Atualizar tabela de scores:**

```
| 1 | **Adequação Funcional** | Completude, Correção, Pertinência | **9.0** ↑ | 🟢 |
```

**Atualizar nota geral:**
```
**Nota Geral Ponderada: 8.0 / 10** *(+0.1 após M15-ADA)*
```

### 13.5 Alterações na PARTE V — Mapa de Conformidade

**Atualizar Adequação Funcional:**
```
| **Adequação Funcional** | Pipeline M15-ADA (17 nums, adaptive offset), Kill Switch, SmartGale v6, DB logging, Analytics, Fallback early-session | ✅ Colunas mortas resolvidas com schema v1.6 |
```

### 13.6 Alterações na PARTE VI — Conclusão

**Adicionar ao "Pontos Fortes":**
```
6. **Adaptação inteligente** — M15-ADA usa algoritmo diferente por direção (ErrDriven CW / Bayesian CCW)
7. **EV positivo** — 17 números com HR 51.4% = +R$1.51/jogada (break-even 47.2%)
```

### 13.7 Atualização do Rodapé

```
> **Atualizado em:** [DATA DA IMPLANTAÇÃO] (M15-ADA: 17 números adaptativo + 4 bugs main.py + state v1.6.0)
> **Software:** Roleta Cloud v4.0.0 | ~5.700 LOC | 37 arquivos Python
> **Correções aplicadas:** [...anteriores...] + M15-ADA implantação + BUG-MAIN-002/004 corrigidos
```

---

## 14. VERSÃO DO DOCUMENTO

| Versão | Data | Alteração |
|:------:|:----:|:----------|
| 1.0 | 29/Mar/2026 | Criação inicial — Seções 1-10 (Memorial Descritivo + Tarefas) |
| 1.1 | 29/Mar/2026 | Adição Seções 11-13 (Auditoria main.py + ISO 25010 + Pós-Implantação) |

---

> **Documento atualizado em:** 29/Mar/2026  
> **Tipo:** Estudo Pré-Implantação — Memorial Descritivo FINAL  
> **Nenhuma alteração no software**  
> **Referências:** analise_c1_c2_c3.md (Partes 1-22), strategies/sda17.py, state/game.py, main.py, Manutenabilidade_iso.md  
> **Metodologia:** Sequential Thinking MCP + Filesystem MCP + Deep Code Analysis + Auditoria ISO/IEC 25010  
> **Bugs encontrados:** 7 em main.py (2 priorizados para correção junto com M15-ADA)  
> **Tarefas totais:** 27 (Seção 7) + 2 correções main.py = 29 tarefas
