# Task Pré-Implementação — SmartGale v6

> **Data:** 28/Mar/2026 18:05  
> **Base:** `pre_implantacao_estudo.md` — Simulação com 100 apostas reais + 1.761 total  
> **Premissa fixa:** 3 centros × 7 números = 21 números SEMPRE  
> **Status:** APROVADO PARA IMPLEMENTAÇÃO

---

## RESUMO DAS TAREFAS

| # | Task | Prioridade | Arquivo Principal | Impacto |
|---|------|:----------:|:-----------------:|---------|
| 1 | **TASK-E3**: Confiança no get_gale() | P0 | `state/game.py` | "alta"→G1, protege contra spike regression |
| 2 | **TASK-E2**: Remover teto por score | P1 | `state/game.py` | Score 3 (58.1% HR) liberado para escalação |
| 3 | **TASK-E4**: Log distância ao centro | P2 | `server/message_handler.py` | Diagnóstico, sem impacto na decisão |

---

## TASK-E3 [P0]: Confiança "alta" Força G1 no SmartGale

### Justificativa (dados reais)
- **"media"** (c4 < m6): 51.2% HR (100 apostas), 50.5% HR (1.761 apostas)
- **"alta"** (c4 ≥ m6): 47.4% HR (100 apostas), 46.4% HR (1.761 apostas)
- **Inversão CONSISTENTE** em TODAS as amostras — "alta" é pior por 3.8-4.1 pontos
- **Root cause:** "alta" = c4≥m6 = spike de curto prazo → regression to mean → previsões piores

### Alterações

**Arquivo: `state/game.py`** — método `get_gale()`
- Adicionar parâmetro `confidence: str = "media"`
- Nova Regra 6: `confidence == "alta"` → `max_gale = 1` (proteção spike)
- Nova Regra 6b: `confidence == "baixa"` → `max_gale = 1` (dados ruins)
- Atualizar docstring da classe MartingaleState

**Arquivo: `server/message_handler.py`** — chamada get_gale()
- Passar `confidence=advice.confidence` na chamada `mg.get_gale()`

**Arquivo: `core/engine.py`** — chamada get_gale()
- Passar `confidence=advice.confidence` na chamada `mg.get_gale()`

### Testes necessários
- `test_confidence_alta_forces_g1` — "alta" → G1 mesmo com streak alto
- `test_confidence_media_allows_escalation` — "media" → permite G2/G3
- `test_confidence_baixa_forces_g1` — "baixa" → G1

---

## TASK-E2 [P1]: Remover Teto por Score no SmartGale

### Justificativa (dados reais)
- Score 3 = **58.1% HR** (31 apostas) — quase break-even, mas atual SmartGale limita a G1
- Score 4 = 44.4% HR (63 apostas) — permite G2 mas performa pior
- Score 5-6 = ~40% HR — liberava G3, resultado destrutivo
- **Score NÃO é preditor confiável de HR** — variação entre períodos é enorme

### Alterações

**Arquivo: `state/game.py`** — método `get_gale()`
- Remover Regra 1 (teto por score) completamente
- max_gale agora definido por: confiança (E3) + c4_rate (R4) + streak (R2)
- Atualizar docstring removendo referência a score ceiling

### Testes necessários
- `test_score_no_longer_limits_gale` — score=2 com streak=3 → G3 (não G1)
- `test_score_high_no_longer_unlocks_g3` — score≥5 sem streak não libera G3

---

## TASK-E4 [P2]: Log Distância ao Centro

### Justificativa (dados reais)
- HITs: distância média **6.9 casas** do centro
- MISSes: distância média **11.1 casas** do centro
- Diferença de **4.2 casas** — sinal existe, útil para diagnóstico

### Alterações

**Arquivo: `server/message_handler.py`** — após `check_prediction()`
- Quando `hit_result is not None` e há `pending`, calcular distância mínima do `result_actual` aos `sda_centers` preditos
- Logar via `logger.info()` a distância para monitoramento
- NÃO altera decisões — apenas diagnóstico

---

## BUGS CORRIGIDOS NESTA IMPLEMENTAÇÃO

| ID | Bug | Arquivo | Resolução |
|----|-----|---------|-----------|
| BUG-E3-001 | `get_gale()` sem parâmetro `confidence` | `state/game.py:54` | Adicionado parâmetro + Regra 6 |
| BUG-E3-002 | `message_handler` não passa `confidence` | `message_handler.py:236` | Pipeline atualizado |
| BUG-E3-003 | `engine.py` não passa `confidence` | `engine.py:105` | Pipeline atualizado |
| BUG-E2-001 | Score 3 limitado a G1 (58.1% HR penalizado) | `state/game.py:57-62` | Regra de score removida |
| BUG-E2-002 | Score 5-6 liberava G3 (~40% HR destrutivo) | `state/game.py:61-62` | Regra de score removida |

## MELHORIAS IMPLANTADAS

| ID | Melhoria | Impacto |
|----|----------|---------|
| MEL-E3-001 | Confiança como filtro de gale | Protege contra spike regression em "alta" |
| MEL-E2-001 | Gale independe de score | Score não-preditivo removido da decisão de gale |
| MEL-E4-001 | Log de distância ao centro | Diagnóstico de qualidade da predição |

---

## VERSÃO RESULTANTE

**SmartGale v6** — Anti-Martingale com Confiança

Regras (em ordem de prioridade):
1. ~~Regra 1 — Teto por Score: REMOVIDA~~
2. **Regra 6 [NOVA] — Proteção por Confiança:**
   - "alta" → max_gale = 1 (spike regression)
   - "baixa" → max_gale = 1 (dados ruins)
   - "media" → max_gale = 3 (estável, escalação liberada)
3. **Regra 4 — C4 Advisor:** C4 rate < 15% → forçar G1
4. **Regra 2 — Anti-Martingale:** streak global ≥3→G3, ≥2→G2, else→G1
5. **Regra 3 — Reset:** MISS → G1 imediato
6. **Regra 5 — Take-Profit:** G3+HIT → reset G1

---

> **Documento de task para implementação imediata**  
> **Referência:** `pre_implantacao_estudo.md` (simulações e auditoria completa)
