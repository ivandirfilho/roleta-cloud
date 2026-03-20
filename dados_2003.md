# 📊 Dados 20/03 — Fluxo de Dados & Preparação para Banco Vetorial

> **Versão:** 3.5.0  
> **Data:** 20/03/2026  
> **Objetivo:** Documentar o fluxo completo de dados desde a captura até a decisão, mapeando cada etapa com seu armazenamento atual (SQLite/memória/transiente), para preparar a migração inteligente ao banco vetorial.

---

## ÍNDICE

1. [Visão Geral do Fluxo](#1-visão-geral-do-fluxo)
2. [ETAPA 1 — Captura (Extensão Chrome)](#2-etapa-1--captura-extensão-chrome)
3. [ETAPA 2 — Recepção e Validação (Servidor)](#3-etapa-2--recepção-e-validação-servidor)
4. [ETAPA 3 — Verificação de Predição Anterior](#4-etapa-3--verificação-de-predição-anterior)
5. [ETAPA 4 — Cálculo de Força e Timeline](#5-etapa-4--cálculo-de-força-e-timeline)
6. [ETAPA 5 — Análise SDA-19 (Estratégia)](#6-etapa-5--análise-sda-19-estratégia)
7. [ETAPA 6 — Kill Switch (Triple Rate Advisor)](#7-etapa-6--kill-switch-triple-rate-advisor)
8. [ETAPA 7 — Decisão Final e Martingale](#8-etapa-7--decisão-final-e-martingale)
9. [ETAPA 8 — Persistência no Banco](#9-etapa-8--persistência-no-banco)
10. [ETAPA 9 — Broadcast (Dashboard + Extensão)](#10-etapa-9--broadcast-dashboard--extensão)
11. [ETAPA 10 — Analytics (Consultas)](#11-etapa-10--analytics-consultas)
12. [Mapa de Armazenamento por Dado](#12-mapa-de-armazenamento-por-dado)
13. [Schema Completo do SQLite Atual](#13-schema-completo-do-sqlite-atual)
14. [Preparação para Banco Vetorial](#14-preparação-para-banco-vetorial)
15. [Arquitetura Alvo: SQLite + VectorDB](#15-arquitetura-alvo-sqlite--vectordb)

---

## 1. VISÃO GERAL DO FLUXO

```
  ROLETA AO VIVO (DOM)
        │
        ▼
┌───────────────────┐
│  EXTENSÃO CHROME  │  content.js + background.js
│  (Escuta Beat)    │  Extrai numero do DOM a cada ~2s
└───────┬───────────┘
        │  WebSocket JSON
        │  {type:"novo_resultado", numero, direcao, trace_id, t_client}
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│                        SERVIDOR PYTHON                                │
│                                                                       │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                │
│  │  VALIDAÇÃO   │──►│  PREDIÇÃO    │──►│  FORÇA      │                │
│  │  Pydantic    │   │  check_pred │   │  process_spin│               │
│  │  SpinInput   │   │  ▲resultado │   │  calc_force  │               │
│  └─────────────┘   └─────────────┘   └──────┬──────┘                │
│                                              │                        │
│  ┌─────────────┐   ┌─────────────┐   ┌──────▼──────┐                │
│  │  DECISÃO    │◄──│  KILL SWITCH │◄──│  SDA-19     │                │
│  │  APOSTAR/   │   │  Triple Rate │   │  IQR+Median │               │
│  │  PULAR      │   │  C4/M6/L12  │   │  +Drift     │               │
│  └──────┬──────┘   └─────────────┘   └─────────────┘                │
│         │                                                             │
│  ┌──────▼──────┐   ┌─────────────┐                                  │
│  │  MARTINGALE │──►│  SQLITE DB  │  decisions, gale_windows,        │
│  │  G1→G2→G3  │   │  27 colunas │  window_plays, sessions          │
│  └──────┬──────┘   └─────────────┘                                  │
│         │                                                             │
└─────────┼─────────────────────────────────────────────────────────────┘
          │  WebSocket broadcast
          ▼
┌─────────────────────┐         ┌─────────────────────┐
│  EXTENSÃO (Overlay)  │         │  DASHBOARD           │
│  Mini-dashboard      │         │  www.roleta.xma-ia   │
│  Região + Gale + $   │         │  Caixa de Vidro      │
│  Confiança bar       │         │  Performance grids   │
└─────────────────────┘         │  Trace steps         │
                                │  Window history      │
                                └─────────────────────┘
```

---

## 2. ETAPA 1 — CAPTURA (Extensão Chrome)

### O que é capturado do DOM

```javascript
// background.js — extractResultsFromPage()
// Seletores DOM configuráveis por mesa:
"[data-role='recent-number']"       → Últimos números da roleta
"[class*='trafficLightText']"       → Status: ABERTO/FECHADO
"[data-role='balance-label-value']" → Saldo da conta
"[data-role='total-bet-label-value']" → Aposta atual na mesa
"[data-role='chip']"                → Ficha ativa
```

### Deduplicação na Extensão

```javascript
// Hash dos 5 primeiros números para detectar novo spin:
const newHash = newNumbers.slice(0, 5).join(',');
if (newHash !== state.lastHash) → NOVO SPIN DETECTADO

// Direção alterna automaticamente a cada spin:
currentDirection = (currentDirection === 'horario') ? 'anti-horario' : 'horario';
```

### Dados enviados ao servidor

```json
{
  "type": "novo_resultado",
  "numero": 17,
  "direcao": "horario",
  "trace_id": "1699999999999-a1b2c3",
  "t_client": 1699999999999,
  "timestamp": 1699999999999,
  "allNumbers": [17, 25, 3, 14, 9, 0, 22, 31, 18, 11, 5, 2],
  "monitoringData": {
    "gameStatus": "FAÇAM SUAS APOSTAS",
    "isOpen": true,
    "balance": 1250.50,
    "currentBet": 100.00,
    "activeChip": 17.00
  }
}
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Persistência |
|------|------|-------------|
| `lastHash` | `chrome.storage.local` | Sessão do navegador |
| `currentDirection` | Variável JS | Volátil (reset na reconexão) |
| `resultsHistory` | `chrome.storage.local` | Últimos 12 números |
| `monitoringData` | `chrome.storage.local` | Snapshot atualizado a cada leitura |

---

## 3. ETAPA 2 — RECEPÇÃO E VALIDAÇÃO (Servidor)

### Validação Pydantic (SpinInput)

```python
# models/input.py
class SpinInput(BaseModel):
    numero:  int            # 0-36 (validado)
    direcao: Literal["horario", "anti-horario"]
    trace_id: str           # 4-36 caracteres
    t_client: int           # Timestamp ms do cliente
```

### Deduplicação no Servidor

```python
# message_handler.py — is_duplicate_spin()
current_hash = f"{numero}_{timestamp // 1000}"  # Granularidade: 1 segundo
if current_hash == self.last_spin_hash:
    return True  # Ignorar — "Spin duplicado ignorado"
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Tipo |
|------|------|------|
| `last_spin_hash` | Memória (`MessageHandler`) | In-memory, por conexão, não persistido |
| Validação | Nenhum | Transiente — falha retorna `ErrorOutput` ao cliente |

---

## 4. ETAPA 3 — VERIFICAÇÃO DE PREDIÇÃO ANTERIOR

### check_prediction() — game.py

Antes de processar o novo spin, o sistema verifica se a predição anterior acertou:

```
ENTRADA: actual_number (o número que acabou de sair)

LEITURA: pending_prediction = {
    "numbers": [12, 35, 3, 26, ...],  # 19 números previstos
    "direction": "cw",                 # Direção-alvo
    "center": 14,                      # Centro previsto
    "predicted_force": 7,              # Força prevista
    "bet_placed": true                 # Se apostou de fato
}

CÁLCULO: hit = actual_number IN numbers → True/False

ESCRITA (SEMPRE):
  → performance_sda17_{direction}.appendleft(hit)  # deque(maxlen=12)

ESCRITA (SOMENTE SE bet_placed=True):
  → performance_bet_{direction}.appendleft(hit)     # deque(maxlen=12)

LIMPA: pending_prediction = None
```

### 4 Listas de Performance

```
┌──────────────────────────────────────────────────────────┐
│  performance_sda17_cw   [✓ ✗ ✓ ✓ ✗ ✓ ✗ ✓ ✓ ✗ ✓ ✗]   │  ← TODAS predições CW
│  performance_sda17_ccw  [✗ ✓ ✗ ✓ ✓ ✗ ✓ ✗ ✓ ✓ ✗ ✓]   │  ← TODAS predições CCW
│  performance_bet_cw     [✓ ✓ ✗ ✓ ✗ ✓ ✓ ✗ ✓ ✓ ✗ ✓]   │  ← Só quando APOSTOU CW
│  performance_bet_ccw    [✗ ✓ ✓ ✗ ✓ ✓ ✗ ✓ ✗ ✓ ✓ ✗]   │  ← Só quando APOSTOU CCW
└──────────────────────────────────────────────────────────┘
  Cada lista: deque(maxlen=12), index 0 = mais recente
  Alimenta: Triple Rate (SDA17 lists) e Martingale (bet lists)
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Tipo |
|------|------|------|
| `pending_prediction` | `state.json` (campo de GameState) | Persistido (atômico) |
| `performance_sda17_cw/ccw` | `state.json` | Persistido |
| `performance_bet_cw/ccw` | `state.json` | Persistido |
| `hit` (resultado) | Atualiza `decisions.result_hit` da decisão anterior | SQLite |

---

## 5. ETAPA 4 — CÁLCULO DE FORÇA E TIMELINE

### process_spin() — game.py + roulette.py

```
ENTRADA: numero=17, direcao="horario"

CÁLCULO DE FORÇA (distância circular na roda europeia):
  from_pos = WHEEL_SEQUENCE.index(last_number)  # Ex: index do 25 = 12
  to_pos   = WHEEL_SEQUENCE.index(numero)        # Ex: index do 17 = 5

  Se direcao == "horario":
    force = (to_pos - from_pos) % 37   # Distância no sentido horário
  Senão:
    force = (from_pos - to_pos) % 37   # Distância no sentido anti-horário

ESCRITA NA TIMELINE:
  Se direcao == "horario":
    timeline_cw.forces.appendleft(force)    # deque(maxlen=45)
  Senão:
    timeline_ccw.forces.appendleft(force)   # deque(maxlen=45)

ATUALIZA:
  last_number = numero
  last_direction = direcao
  game_state.save()  → state.json (escrita atômica)
```

### Roda Europeia — Sequência Física (37 slots)

```
WHEEL_SEQUENCE = [
  0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36,
  11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9,
  22, 18, 29, 7, 28, 12, 35, 3, 26
]
# Index 0 = slot do zero, Index 5 = slot do 21, etc.
# A "força" é a distância em slots entre dois números consecutivos
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Tipo |
|------|------|------|
| `timeline_cw.forces` | `state.json` | Persistido, deque(maxlen=45) |
| `timeline_ccw.forces` | `state.json` | Persistido, deque(maxlen=45) |
| `last_number` | `state.json` | Persistido |
| `last_direction` | `state.json` | Persistido |
| `force` | `decisions.spin_force` | SQLite (gravado na ETAPA 8) |

---

## 6. ETAPA 5 — ANÁLISE SDA-19 (Estratégia)

### Pipeline Completo — sda17.py

```
ENTRADA:
  timeline: Timeline (forces[0:45], index 0 = mais recente)
  last_number: int (posição atual na roda)

═══════════════════════════════════════════════════════════

PASSO 1 — JANELA ADAPTATIVA
  Tenta janelas: [7, 5, 3] forças
  Critério: clean_count ≥ max(2, window // 2)
  Usa a maior janela viável

                    ▼

PASSO 2 — FILTRO IQR (Rejeição de Outliers)
  Se N < 4: usa todas as forças (skip IQR)
  Senão:
    Q1 = sorted_forces[N // 4]
    Q3 = sorted_forces[3N // 4]
    IQR = Q3 - Q1
    Mantém: Q1 - 1.5·IQR ≤ force ≤ Q3 + 1.5·IQR
    Fallback: se removeu > 2/N, mantém todas
  Saída: clean = [(force, idx), ...]

                    ▼

PASSO 3 — MEDIANA PONDERADA (Decay Exponencial)
  Para cada (force, idx) em clean:
    weight = 0.8^idx        # Mais recente = maior peso
    repeats = max(1, int(weight × 10))
    Adiciona `force` repetido `repeats` vezes
  predicted_force = median(expanded_list)
  Pesos: pos0=10rep → pos1=8rep → pos2=6rep → pos3=5rep → ...

                    ▼

PASSO 4 — DETECÇÃO DE DRIFT (Tendência)
  last3 = forces[:3]
  diffs = [last3[0]-last3[1], last3[1]-last3[2]]
  Se TODOS diffs > 0 (crescente): drift_adj = int(sum(diffs) × 0.5)
  Se TODOS diffs < 0 (decrescente): drift_adj = int(sum(diffs) × 0.5)
  Senão: drift_adj = 0
  predicted_force = clamp(predicted_force + drift_adj, 1, 37)

                    ▼

PASSO 5 — SMART SCORE (Confiança 1-6)
  survival_rate = len(clean) / n
  spread = max(clean) - min(clean)
  tightness = max(0, 1 - spread/15)
  stable_bonus = 1 se drift_adj == 0
  score = clamp(int(survival_rate × 3 + tightness × 3 + stable_bonus), 1, 6)

                    ▼

PASSO 6 — CENTRO E REGIÃO (19 números)
  center = apply_force(last_number, predicted_force, direction)
  numbers = get_neighbors(center, 9)  # 9 à esquerda + centro + 9 à direita
  = 19 números = 51.4% de cobertura da roda

═══════════════════════════════════════════════════════════

SAÍDA: StrategyResult
  should_bet: bool          # Sempre True se dados suficientes
  numbers: List[int]        # 19 números (região)
  center: int               # Número central previsto
  score: int                # 1-6 (confiança)
  visual: str               # "4─17─2" (representação visual)
  details: {
    "predicted_force": int,
    "drift_adjustment": int,
    "survival_rate": float,
    "tightness": float,
    "window_used": int,
    "clean_count": int,
    "outliers_removed": int
  }
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Tipo |
|------|------|------|
| `should_bet` | `decisions.sda_should_bet` | SQLite |
| `score` | `decisions.sda_score` | SQLite |
| `center` | `decisions.sda_center` | SQLite |
| `numbers` | `decisions.sda_numbers` (JSON) | SQLite |
| `predicted_force` | `decisions.sda_predicted_force` | SQLite |
| `details` | Dentro do `trace` WebSocket | Transiente |

---

## 7. ETAPA 6 — KILL SWITCH (Triple Rate Advisor)

### bet_advisor.py — TripleRateAdvisor

```
ENTRADA:
  performance: List[bool]  # performance_sda17 da direção alvo (últimos 12)
  sda_score: int            # Score do SDA-19 (1-6)

═══════════════════════════════════════════════════════════

CÁLCULO DAS 3 TAXAS:

  C4 (Curto prazo)  = sum(performance[:4])  / 4    # Últimos 4 resultados
  M6 (Médio prazo)  = sum(performance[:6])  / 6    # Últimos 6 resultados
  L12 (Longo prazo) = sum(performance[:12]) / 12   # Últimos 12 resultados

═══════════════════════════════════════════════════════════

REGRA DE VETO (Kill Switch):

  ┌───────────────────────────────────────────────┐
  │  VETAR (PULAR) se AMBAS condições:            │
  │    1. C4 == 0%  (zero acertos nos últimos 4)  │
  │    2. sda_score ≤ 2  (dados muito dispersos)  │
  │                                                │
  │  TODOS os outros casos → APROVAR (APOSTAR)    │
  └───────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════

CONFIANÇA:
  "alta"  → C4 ≥ M6 ≥ L12 AND C4 > 0 (tendência positiva estável)
  "media" → C4 > 0 OR score > 2 (algum sinal positivo)
  "baixa" → Condição de veto ativa

═══════════════════════════════════════════════════════════

SAÍDA: BetAdvice
  should_bet: bool        # True/False
  confidence: str         # "alta" | "media" | "baixa"
  reason: str             # Explicação em português
  c4_rate: float          # 0.0 a 1.0
  m6_rate: float          # 0.0 a 1.0
  l12_rate: float         # 0.0 a 1.0
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Tipo |
|------|------|------|
| `should_bet` | `decisions.tr_should_bet` | SQLite |
| `confidence` | `decisions.tr_confidence` | SQLite |
| `reason` | `decisions.tr_reason` | SQLite |
| `c4_rate` | `decisions.tr_c4_rate` | SQLite |
| `m6_rate` | `decisions.tr_m6_rate` | SQLite |
| `l12_rate` | `decisions.tr_l12_rate` | SQLite |

---

## 8. ETAPA 7 — DECISÃO FINAL E MARTINGALE

### Lógica de Decisão

```
SE SDA19.should_bet == True:
    SE TripleRate.should_bet == True:
        acao = "APOSTAR"
        bet_placed = True
        reason = "SDA17 + Triple Rate aprovaram"
    SENÃO:
        acao = "PULAR"
        bet_placed = False
        reason = "Triple Rate vetou: " + advice.reason
SENÃO:
    acao = "PULAR" (ou "AGUARDAR" se dados insuficientes)
    bet_placed = False
    reason = "SDA sem predição"
```

### Martingale (2 instâncias independentes: CW e CCW)

```
┌─────────────────────────────────────────────────────────────┐
│                  MARTINGALE STATE                             │
│                                                               │
│  level: 1|2|3          window_hits: 0-5                      │
│  window_count: 0-5     total_stops: N (lifetime)             │
│                                                               │
│  JANELA DE 5 JOGADAS:                                        │
│  ┌───┬───┬───┬───┬───┐                                      │
│  │ 1 │ 2 │ 3 │ 4 │ 5 │  ← Cada slot = 1 spin apostado      │
│  └───┴───┴───┴───┴───┘                                      │
│                                                               │
│  Ao completar 5 plays:                                       │
│    3+ acertos (≥60%) → SUCESSO → Volta ao G1                │
│    2- acertos (<60%) → ESCALAR → Próximo nível              │
│                                                               │
│  VALORES POR NÍVEL:                                          │
│    G1 = R$19/slot (1x)                                       │
│    G2 = R$38/slot (2x)                                       │
│    G3 = R$76/slot (4x)                                       │
│    G3 falha → STOP (volta G1, incrementa total_stops)        │
│                                                               │
│  PERSISTÊNCIA:                                                │
│    In-memory: state.json (martingale_cw, martingale_ccw)     │
│    Banco: gale_windows + window_plays (histórico completo)   │
└─────────────────────────────────────────────────────────────┘
```

### Montagem da Resposta (SuggestionOutput)

```json
{
  "type": "sugestao",
  "data": {
    "acao": "APOSTAR",
    "numeros": [12, 35, 3, 26, 0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11],
    "centro": 2,
    "regiao": "4─2─21",
    "ultimo_numero": 17,
    "confianca": 80,
    "martingale": "1x",
    "aposta": 19,
    "gale_level": 1,
    "gale_display": "G1 2/5",
    "estrategia": "SDA-19",
    "score": 4,
    "trace_id": "abc12345",
    "t_server": 1705571100050,
    "bet_advice": {
      "should_bet": true,
      "confidence": "alta",
      "reason": "Tendência positiva estável",
      "c4_rate": 0.75,
      "m6_rate": 0.67,
      "l12_rate": 0.58
    },
    "action_reason": "SDA17 + Triple Rate aprovaram"
  }
}
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Tipo |
|------|------|------|
| `martingale_cw/ccw` | `state.json` | Persistido (level, hits, count) |
| `acao` | `decisions.final_action` | SQLite |
| `reason` | `decisions.action_reason` | SQLite |
| `gale_level` | `decisions.gale_level` | SQLite |
| `gale_window_hits` | `decisions.gale_window_hits` | SQLite |
| `gale_window_count` | `decisions.gale_window_count` | SQLite |
| `gale_bet_value` | `decisions.gale_bet_value` | SQLite |
| `pending_prediction` | `state.json` | Persistido (para verificar no próximo spin) |

---

## 9. ETAPA 8 — PERSISTÊNCIA NO BANCO

### save_decision() → SQLite (27 colunas)

```sql
INSERT INTO decisions (
  -- Contexto do Spin
  timestamp, session_id,
  spin_number, spin_direction, spin_force,

  -- Triple Rate Advisor
  tr_should_bet, tr_confidence, tr_reason,
  tr_c4_rate, tr_m6_rate, tr_l12_rate,

  -- Estratégia SDA-19
  sda_should_bet, sda_score, sda_center,
  sda_numbers,              -- JSON: [12,35,3,26,...]
  sda_predicted_force,

  -- Decisão Final
  final_action,             -- "APOSTAR" ou "PULAR"
  action_reason,

  -- Estado Martingale
  gale_level, gale_window_hits, gale_window_count, gale_bet_value,

  -- Resultado (preenchido no PRÓXIMO spin)
  result_hit,               -- NULL → True/False
  result_actual,            -- NULL → 0-36

  -- Calibração (legado)
  calibration_offset, calibration_error,

  -- Snapshot
  performance_snapshot      -- JSON: [true, false, true, ...]
)
```

### track_gale_window() → SQLite

```sql
-- Nova janela (window_count == 1):
INSERT INTO gale_windows (direction, gale_level, started_at,
  sda17_rate_at_start, bet_rate_at_start, calibration_offset)

-- Cada jogada:
INSERT INTO window_plays (window_id, play_number, timestamp,
  spin_number, spin_direction, spin_force, center_predicted,
  hit, actual_number, sda_score, tr_confidence, tr_reason)

-- Transição (completou 5 plays):
UPDATE gale_windows SET ended_at=?, total_hits=?, total_plays=?,
  result=?, next_level=? WHERE id=?
```

### 💾 Resumo do banco nesta etapa

| Tabela | Registros/spin | Dados |
|--------|:--------------:|-------|
| `decisions` | 1 | 27 colunas com contexto completo |
| `gale_windows` | 0 ou 1 | Criada na 1ª play, fechada na 5ª |
| `window_plays` | 0 ou 1 | Uma play por spin apostado |
| `sessions` | 0 | Atualizada no final da sessão |

---

## 10. ETAPA 9 — BROADCAST (Dashboard + Extensão)

### Para a Extensão (Overlay)

```
TIPO: sugestao (resposta direta ao MASTER que enviou o spin)

                  ┌───────────────────────────────┐
                  │     OVERLAY (content.js)       │
                  ├───────────────────────────────┤
                  │  🎯 APOSTAR [14]              │  ← acao + centro
                  │  Centro 14 com cobertura      │  ← regiao
                  │  G1 2/5          R$19         │  ← gale_display + aposta
                  │  ████████░░ 80%               │  ← confianca (progress bar)
                  │  Atualizado: 10:40:50         │  ← timestamp
                  └───────────────────────────────┘
```

### Para o Dashboard (www.roleta.xma-ia.com)

```
TIPO 1: state_sync (heartbeat a cada ~1s)
  → last_number, martingale_cw/ccw, performance (4 listas), window_history

TIPO 2: trace (detalhes do pipeline, enviado a cada spin processado)
  → steps[]: received → processed → analyzed → triple_rate → sent
  → spin: {numero, direcao, force}
  → result: {acao, centro, score, numeros, trend}
  → performance: {sda17: {cw, ccw}, bet: {cw, ccw}}
  → state: {timeline_cw, timeline_ccw, last_number}
```

### Caixa de Vidro — O que mostra

```
┌─────────────────────────────────────────────────────────────────┐
│  CAIXA DE VIDRO (app.js)                                        │
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  ESCUTA  │──►│ SERVIDOR │──►│  SDA-19  │──►│ OVERLAY  │    │
│  │  (beat)  │   │ (python) │   │(análise) │   │(decisão) │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│                                                                  │
│  Último spin: [17] ↩ Horário   Força: 7   Latência: 23ms      │
│                                                                  │
│  Performance SDA17:         Performance Apostas:                │
│  CW:  ■■□■□■■□■■□■  58%    CW:  ■■■□■■■□■■□■  75%            │
│  CCW: □■□■■□■□■■□■  50%    CCW: □□■□■■□■□■■□  42%            │
│                                                                  │
│  Janelas Gale CW:           Janelas Gale CCW:                   │
│  G1: ●●○●● SUCESSO          G1: ●○●○● ESCALOU                  │
│  G1: ●●●○● SUCESSO          G2: ○●●●○ SUCESSO                  │
│                                                                  │
│  Logs: [10:40:50] APOSTAR Centro 14 Score 4 G1 2/5             │
└─────────────────────────────────────────────────────────────────┘
```

### 💾 Armazenamento nesta etapa

| Dado | Onde | Tipo |
|------|------|------|
| Mensagens WebSocket | Nenhum (wire) | Transiente |
| State sync | Nenhum | Reconstruído de GameState a cada 1s |
| Trace | Nenhum | Construído e descartado |

---

## 11. ETAPA 10 — ANALYTICS (Consultas)

### Endpoints disponíveis via WebSocket

| Endpoint | Fonte | Retorno |
|----------|-------|---------|
| `get_analytics_summary` | `decisions` | total, bets, hits, rate, gale por nível, vetos TR |
| `get_sessions_list` | `sessions` JOIN `decisions` | Lista sessões com métricas |
| `get_gale_history` | `gale_windows` + `window_plays` | Histórico janelas por direção |
| `get_performance_timeline` | `decisions` GROUP BY hora/dia | Tendência temporal |
| `get_decision_log` | `decisions` | Últimas N decisões com todos campos |

### Queries de Agregação (SQLite)

```sql
-- Resumo geral
SELECT COUNT(*) total, SUM(CASE WHEN final_action='APOSTAR' THEN 1 END) bets,
       SUM(result_hit) hits, AVG(result_hit)*100 hit_rate FROM decisions;

-- Performance por nível Gale
SELECT gale_level, COUNT(*) total, SUM(result_hit) hits,
       ROUND(AVG(result_hit)*100,1) rate
FROM decisions WHERE final_action='APOSTAR' GROUP BY gale_level;

-- Timeline horária
SELECT strftime('%Y-%m-%d %H:00', timestamp) period,
       COUNT(*) total, SUM(CASE WHEN final_action='APOSTAR' THEN 1 END) bets,
       SUM(result_hit) hits, ROUND(AVG(sda_score),1) avg_score
FROM decisions GROUP BY period ORDER BY period DESC LIMIT 48;

-- Análise de vetos do Triple Rate
SELECT COUNT(*) vetoed, SUM(result_hit) would_have_hit
FROM decisions WHERE tr_should_bet=0 AND sda_should_bet=1;
```

---

## 12. MAPA DE ARMAZENAMENTO POR DADO

### 🔴 In-Memory + state.json (Estado Volátil Persistido)

| Campo | Tipo | maxlen | Usado por |
|-------|------|--------|-----------|
| `timeline_cw.forces` | deque[int] | 45 | SDA-19 |
| `timeline_ccw.forces` | deque[int] | 45 | SDA-19 |
| `performance_sda17_cw` | deque[bool] | 12 | Triple Rate |
| `performance_sda17_ccw` | deque[bool] | 12 | Triple Rate |
| `performance_bet_cw` | deque[bool] | 12 | Martingale |
| `performance_bet_ccw` | deque[bool] | 12 | Martingale |
| `martingale_cw` | MartingaleState | — | Decisão |
| `martingale_ccw` | MartingaleState | — | Decisão |
| `pending_prediction` | Dict | — | check_prediction |
| `last_number` | int | — | process_spin |
| `last_direction` | str | — | process_spin |
| `last_spin_hash` | str | — | Deduplicação |

### 🔵 SQLite (data/decisions.db) — Persistência Permanente

| Tabela | Colunas | Registros típicos | Propósito |
|--------|:-------:|:------------------:|-----------|
| `decisions` | 27 | ~2.000+ | Log completo de cada decisão |
| `gale_windows` | 12 | ~200+ | Janelas Martingale completas |
| `window_plays` | 13 | ~800+ | Jogadas individuais nas janelas |
| `sessions` | 9 | ~50+ | Resumo por sessão |

### 🟡 Transiente (WebSocket only)

| Mensagem | Campos-chave | Destino |
|----------|-------------|---------|
| `sugestao` | acao, centro, numeros, gale, confianca | Extensão overlay |
| `state_sync` | performance, martingale, window_history | Dashboard + extensão |
| `trace` | steps[], spin, result, performance | Dashboard |
| `role_assigned` | role, connection_id | Extensão |
| `ack` | message, original_type | Extensão |
| `error` | code, message | Extensão |

---

## 13. SCHEMA COMPLETO DO SQLITE ATUAL

### Tabela: `decisions` (27 colunas)

```
┌────────────────────────┬──────────┬──────────────────────────────────────┐
│ Coluna                  │ Tipo     │ Descrição                            │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ id                      │ INT PK   │ Auto-increment                       │
│ timestamp               │ DATETIME │ Momento da decisão                   │
│ session_id              │ TEXT FK  │ → sessions.id                        │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ spin_number             │ INTEGER  │ 0-36                                 │
│ spin_direction          │ TEXT     │ "horario" / "anti-horario"           │
│ spin_force              │ INTEGER  │ Distância circular calculada         │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ tr_should_bet           │ BOOLEAN  │ Kill Switch aprovação                │
│ tr_confidence           │ TEXT     │ "alta" / "media" / "baixa"           │
│ tr_reason               │ TEXT     │ Explicação do veredito               │
│ tr_c4_rate              │ REAL     │ 0.0-1.0 (curto prazo)                │
│ tr_m6_rate              │ REAL     │ 0.0-1.0 (médio prazo)                │
│ tr_l12_rate             │ REAL     │ 0.0-1.0 (longo prazo)                │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ sda_should_bet          │ BOOLEAN  │ SDA-19 recomendação                  │
│ sda_score               │ INTEGER  │ 1-6 (confiança)                      │
│ sda_center              │ INTEGER  │ Número central previsto              │
│ sda_numbers             │ TEXT     │ JSON: 19 números da região           │
│ sda_predicted_force     │ INTEGER  │ Força prevista pelo SDA              │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ final_action            │ TEXT     │ "APOSTAR" / "PULAR"                  │
│ action_reason           │ TEXT     │ Razão final                          │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ gale_level              │ INTEGER  │ 1, 2 ou 3                            │
│ gale_window_hits        │ INTEGER  │ Acertos na janela atual              │
│ gale_window_count       │ INTEGER  │ Jogadas na janela atual (0-5)        │
│ gale_bet_value          │ INTEGER  │ R$19, R$38 ou R$76                   │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ result_hit              │ BOOLEAN  │ NULL → preenchido no próximo spin    │
│ result_actual           │ INTEGER  │ NULL → número real que saiu          │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ calibration_offset      │ INTEGER  │ 0 (desativado)                       │
│ calibration_error       │ INTEGER  │ NULL (legado)                        │
├────────────────────────┼──────────┼──────────────────────────────────────┤
│ performance_snapshot    │ TEXT     │ JSON: últimos 12 resultados          │
└────────────────────────┴──────────┴──────────────────────────────────────┘
```

### Tabela: `gale_windows` (12 colunas)

```
┌────────────────────────┬──────────┬──────────────────────────────────────┐
│ id                      │ INT PK   │ Auto-increment                       │
│ direction               │ TEXT     │ "cw" / "ccw"                         │
│ gale_level              │ INTEGER  │ 1, 2 ou 3                            │
│ started_at              │ DATETIME │ Início da janela                     │
│ ended_at                │ DATETIME │ NULL se ativa                        │
│ total_hits              │ INTEGER  │ Acertos na janela                    │
│ total_plays             │ INTEGER  │ Jogadas (max 5)                      │
│ result                  │ TEXT     │ "success" / "escalated" / "stop"     │
│ next_level              │ INTEGER  │ Nível após a janela                  │
│ sda17_rate_at_start     │ REAL     │ Taxa SDA no início                   │
│ bet_rate_at_start       │ REAL     │ Taxa apostas no início               │
│ calibration_offset      │ INTEGER  │ 0                                    │
└────────────────────────┴──────────┴──────────────────────────────────────┘

UNIQUE INDEX: idx_gale_windows_active ON (direction) WHERE ended_at IS NULL
→ Garante apenas 1 janela ativa por direção
```

### Tabela: `window_plays` (13 colunas)

```
┌────────────────────────┬──────────┬──────────────────────────────────────┐
│ id                      │ INT PK   │ Auto-increment                       │
│ window_id               │ INT FK   │ → gale_windows.id                    │
│ play_number             │ INTEGER  │ 1 a 5                                │
│ timestamp               │ DATETIME │ Momento da jogada                    │
│ spin_number             │ INTEGER  │ 0-36                                 │
│ spin_direction          │ TEXT     │ "horario" / "anti-horario"           │
│ spin_force              │ INTEGER  │ Força calculada                      │
│ center_predicted        │ INTEGER  │ Centro previsto pelo SDA             │
│ hit                     │ BOOLEAN  │ Acertou a região?                    │
│ actual_number           │ INTEGER  │ Número real                          │
│ sda_score               │ INTEGER  │ Score no momento                     │
│ tr_confidence           │ TEXT     │ Confiança do Triple Rate             │
│ tr_reason               │ TEXT     │ Razão do Triple Rate                 │
└────────────────────────┴──────────┴──────────────────────────────────────┘
```

### Tabela: `sessions` (9 colunas)

```
┌────────────────────────┬──────────┬──────────────────────────────────────┐
│ id                      │ TEXT PK  │ UUID[:8]                             │
│ start_time              │ DATETIME │ Início da sessão                     │
│ end_time                │ DATETIME │ NULL se ativa                        │
│ total_spins             │ INTEGER  │ Total de spins na sessão             │
│ total_bets              │ INTEGER  │ Total de apostas                     │
│ total_hits              │ INTEGER  │ Total de acertos                     │
│ total_profit            │ REAL     │ Lucro acumulado                      │
│ max_gale_reached        │ INTEGER  │ Maior nível Gale atingido            │
│ total_stops             │ INTEGER  │ Vezes que Gale parou (G3 falha)      │
└────────────────────────┴──────────┴──────────────────────────────────────┘
```

### Índices (10 total)

```sql
CREATE INDEX idx_decisions_session    ON decisions(session_id);
CREATE INDEX idx_decisions_timestamp  ON decisions(timestamp);
CREATE INDEX idx_decisions_action     ON decisions(final_action);
CREATE INDEX idx_decisions_gale       ON decisions(gale_level);
CREATE INDEX idx_gale_windows_direction ON gale_windows(direction);
CREATE INDEX idx_gale_windows_level   ON gale_windows(gale_level);
CREATE INDEX idx_gale_windows_started ON gale_windows(started_at);
CREATE INDEX idx_window_plays_window  ON window_plays(window_id);
CREATE UNIQUE INDEX idx_gale_windows_active ON gale_windows(direction) WHERE ended_at IS NULL;
```

---

## 14. PREPARAÇÃO PARA BANCO VETORIAL

### Estado Atual: `archive/vector_store.py` (LanceDB)

O código já existe preparado mas **desativado**. Ativação planejada quando volume > 5.000 decisões verificadas.

### Embedding Atual (7 dimensões, normalizado [0,1])

```
┌──────────────────────────────────────────────────────────┐
│  VETOR DE 7 DIMENSÕES (vector_store.py)                  │
│                                                           │
│  [0] force_mean      = mean(forces) / 37                 │
│  [1] force_std       = std(forces) / 18                  │
│  [2] force_trend     = (f[0]-f[-1]) / len(f) / 36 + 0.5 │
│  [3] force_range     = (max-min) / 37                    │
│  [4] sda_score       = score / 6                         │
│  [5] gale_level      = level / 4                         │
│  [6] hit_rate_c4     = hit_rate (direto 0-1)             │
│                                                           │
│  Uso: search_similar(forces, sda, gale, hit_rate, k=20)  │
│  Retorna: hit_rate dos 20 mais similares                 │
│  Confiança: alta(≥15 && ≥60%), media(≥10 && ≥45%), baixa │
└──────────────────────────────────────────────────────────┘
```

### O que FALTA para um Embedding Inteligente

O embedding de 7D é um bom começo, mas **muito limitado**. Para uma estratégia vetorial robusta, precisamos expandir para **28-32 dimensões** capturando TODOS os contextos da decisão:

### Proposta: Embedding de 32 Dimensões

```
═══════════════════════════════════════════════════════════════
GRUPO 1: DINÂMICA DE FORÇAS (8D)
═══════════════════════════════════════════════════════════════
[0]  force_mean          = mean(last 7 forces) / 37
[1]  force_std           = std(last 7 forces) / 18
[2]  force_trend         = slope linear regression / 36 + 0.5
[3]  force_range         = (max - min) / 37
[4]  force_momentum      = (mean(forces[:3]) - mean(forces[3:])) / 37 + 0.5
[5]  force_acceleration  = (forces[0] - 2*forces[1] + forces[2]) / 74 + 0.5
[6]  force_last          = forces[0] / 37
[7]  force_entropy       = Shannon entropy das forças / log(7)

═══════════════════════════════════════════════════════════════
GRUPO 2: ESTADO DA ESTRATÉGIA (6D)
═══════════════════════════════════════════════════════════════
[8]  sda_score           = score / 6
[9]  sda_survival        = clean_count / window_used
[10] sda_tightness       = 1 - spread / 15
[11] sda_drift           = abs(drift_adj) / 18
[12] sda_predicted_force = predicted / 37
[13] sda_outliers        = outliers_removed / window_used

═══════════════════════════════════════════════════════════════
GRUPO 3: PERFORMANCE TEMPORAL (6D)
═══════════════════════════════════════════════════════════════
[14] c4_rate             = rate curto prazo (0-1)
[15] m6_rate             = rate médio prazo (0-1)
[16] l12_rate            = rate longo prazo (0-1)
[17] perf_trend          = (c4 - l12) normalizado (-1 a 1) → (0 a 1)
[18] streak_current      = len(streak atual) / 12
[19] streak_type         = 1.0 se winning streak, 0.0 se losing

═══════════════════════════════════════════════════════════════
GRUPO 4: ESTADO MARTINGALE (4D)
═══════════════════════════════════════════════════════════════
[20] gale_level          = level / 3
[21] gale_window_progress = window_count / 5
[22] gale_window_rate    = window_hits / max(1, window_count)
[23] gale_total_stops    = min(total_stops, 10) / 10

═══════════════════════════════════════════════════════════════
GRUPO 5: PADRÃO WIN/LOSS (4D)
═══════════════════════════════════════════════════════════════
[24] win_clustering      = (wins adjacentes) / max(1, total_wins)
[25] run_length_avg      = mean(comprimento das runs) / 12
[26] pattern_entropy     = Shannon entropy do padrão W/L / log(12)
[27] recovery_speed      = média de spins até sair de losing streak / 5

═══════════════════════════════════════════════════════════════
GRUPO 6: CONTEXTO TEMPORAL (4D)
═══════════════════════════════════════════════════════════════
[28] session_progress    = spins_na_sessão / 200 (normalizado)
[29] session_hit_rate    = taxa acumulada da sessão (0-1)
[30] hour_sin            = sin(2π × hora / 24)  → captura ciclicidade
[31] hour_cos            = cos(2π × hora / 24)  → captura ciclicidade
```

### O que o Banco Vetorial pode encontrar que o SQLite NÃO pode

```
┌─────────────────────────────────────────────────────────────────────┐
│                     SQLite vs VectorDB                               │
├────────────────────────────┬────────────────────────────────────────┤
│  SQLite (atual)            │  VectorDB (objetivo)                   │
├────────────────────────────┼────────────────────────────────────────┤
│  WHERE score >= 4          │  "Situações SIMILARES a esta"          │
│  Busca exata por campo     │  Busca por similaridade multidim.      │
│  GROUP BY hora, nível      │  Clusters naturais nos dados           │
│  AVG, SUM, COUNT           │  Distância vetorial (L2, cosseno)      │
│  Filtra por valor exato    │  Encontra padrões fuzzy                │
│  JOIN entre tabelas        │  Embedding unificado do contexto       │
│  Agregação temporal fixa   │  Detecção de anomalias                 │
│  Não detecta padrões       │  "Esta sequência de forças parece..."  │
│  Não correlaciona dims     │  Correlação entre TODAS as dims        │
│  Não generaliza            │  Generaliza para situações novas       │
└────────────────────────────┴────────────────────────────────────────┘
```

### Casos de Uso Concretos do VectorDB

```
CASO 1: VALIDAÇÃO DE APOSTA
  Input: Embedding 32D do estado atual
  Query: "Encontre as 50 decisões mais similares"
  Output: hit_rate dessas 50 decisões
  → Se hit_rate > 65%: REFORÇA aposta (SDA + VectorDB concordam)
  → Se hit_rate < 35%: VETA aposta (mesmo que SDA aprove)
  → Se 35-65%: Confia no SDA + Triple Rate normalmente

CASO 2: DETECÇÃO DE REGIME
  Input: Últimos 20 embeddings da sessão
  Query: "A qual cluster esses pontos pertencem?"
  Output: cluster_id → "regime favorável" / "regime adverso"
  → Ajusta agressividade do Martingale por regime

CASO 3: PREDIÇÃO DE GALE OUTCOME
  Input: Embedding do início da janela Gale
  Query: "Janelas similares tiveram que resultado?"
  Output: probabilidade de sucesso/escalada/stop
  → Se P(stop) > 50%: Reduz aposta preventivamente

CASO 4: EARLY WARNING
  Input: Sequência de embeddings (últimos 5 spins)
  Query: "Esta trajetória é similar a trajetórias pré-loss?"
  Output: distância a clusters de "antes de perder"
  → Alerta visual no dashboard quando trajetória é perigosa
```

---

## 15. ARQUITETURA ALVO: SQLite + VectorDB

### Fase 1 (Atual): SQLite Only

```
Spin → SDA-19 → Triple Rate → Decisão → SQLite (27 cols)
                                            │
                                    Analytics queries
```

### Fase 2 (Próxima): SQLite + VectorDB em Paralelo

```
Spin → SDA-19 → Triple Rate ──┬──► Decisão → SQLite (27 cols)
                               │                │
                               │           compute_embedding(32D)
                               │                │
                               │                ▼
                               │          VectorDB (LanceDB)
                               │                │
                               │         search_similar(k=50)
                               │                │
                               ▼                ▼
                          ┌─────────────────────────┐
                          │  DECISÃO ENRIQUECIDA     │
                          │                          │
                          │  SDA-19 score: 4         │
                          │  Triple Rate: alta       │
                          │  VectorDB hit_rate: 72%  │  ← NOVO
                          │  VectorDB confiança: 50  │  ← NOVO
                          │  Regime atual: favorável  │  ← NOVO
                          │                          │
                          │  → APOSTAR (tripla conf.) │
                          └─────────────────────────┘
```

### Fase 3 (Futuro): Estratégia Híbrida

```
┌──────────────────────────────────────────────────────────────┐
│  PIPELINE DE DECISÃO v2.0                                     │
│                                                               │
│  1. SDA-19 analisa forças     → should_bet, score, center     │
│  2. Triple Rate analisa perf  → should_bet, confidence        │
│  3. VectorDB busca similares  → historical_hit_rate           │  ← NOVO
│  4. Regime Detector           → current_regime                │  ← NOVO
│  5. Gale Predictor            → P(success), P(stop)           │  ← NOVO
│  6. Ensemble Decision         → Voto ponderado dos 5 sinais  │  ← NOVO
│                                                               │
│  Pesos do ensemble:                                           │
│    SDA-19:       30%                                          │
│    Triple Rate:  20%                                          │
│    VectorDB:     25%                                          │
│    Regime:       15%                                          │
│    Gale Pred:    10%                                          │
└──────────────────────────────────────────────────────────────┘
```

### Dados que precisam ser coletados AGORA para alimentar o VectorDB

Para que a Fase 2 funcione com qualidade, precisamos **enriquecer cada decisão** com campos extras que hoje NÃO são salvos:

```
┌──────────────────────────────────────────────────────────────┐
│  CAMPOS NOVOS NECESSÁRIOS (adicionar ao save_decision)       │
│                                                               │
│  1. forces_snapshot: JSON     # Últimas 7 forças da timeline │
│  2. sda_survival_rate: REAL   # Taxa de sobrevivência IQR    │
│  3. sda_tightness: REAL       # Dispersão das forças limpas  │
│  4. sda_drift_adj: INTEGER    # Ajuste de drift aplicado     │
│  5. streak_length: INTEGER    # Comprimento da streak atual  │
│  6. streak_type: TEXT         # "win" / "loss"               │
│  7. session_spin_count: INT   # Número do spin na sessão     │
│  8. session_hit_rate: REAL    # Taxa acumulada da sessão     │
│                                                               │
│  Total: 8 colunas extras → 35 colunas no decisions           │
│  Estas colunas alimentam diretamente o embedding de 32D      │
└──────────────────────────────────────────────────────────────┘
```

### Plano de Implementação

```
SPRINT V1 — COLETA (preparação)
  □ Adicionar 8 colunas extras ao schema decisions
  □ Modificar save_decision() para incluir novos dados
  □ Criar migration SQL para alterar tabela existente
  □ Acumular ≥5.000 decisões com dados completos

SPRINT V2 — EMBEDDING (infraestrutura)
  □ Refatorar vector_store.py: 7D → 32D embedding
  □ Implementar compute_embedding_v2() com 6 grupos
  □ Migrar dados existentes (recalcular embeddings)
  □ Benchmark: LanceDB vs ChromaDB vs FAISS

SPRINT V3 — INTEGRAÇÃO (estratégia)
  □ VectorDB como "segundo parecer" no pipeline
  □ Dashboard: mostrar hit_rate histórico similar
  □ A/B testing: com vs sem VectorDB
  □ Ensemble Decision com pesos configuráveis

SPRINT V4 — REGIME DETECTION (avançado)
  □ Clustering automático (K-Means / DBSCAN)
  □ Regime Detector: classificar sessão atual
  □ Gale Predictor: P(outcome) por contexto
  □ Early Warning: trajetória pré-loss detection
```

---

> **Documento gerado em:** 20/03/2026  
> **Base:** Análise completa do filesystem + código-fonte  
> **Software:** Roleta Cloud v3.5.0  
> **Objetivo:** Estruturar dados para migração inteligente SQLite → SQLite + VectorDB  
> **Próximo passo:** Implementar SPRINT V1 (coleta dos 8 campos extras)
