# 🔬 Sugestões de Melhorias — Roleta Cloud v3.5.0

> **Data:** 26/03/2026  
> **Base:** `analise_de_resultados.md` + auditoria profunda do código-fonte  
> **Escopo:** Estratégia SDA-19, Triple Rate Advisor, Martingale, Pipeline de Dados  
> **Nota:** Este documento é apenas estudo — nenhuma alteração no programa foi realizada.

---

## PARTE I — MELHORIAS NA ESTRATÉGIA SDA-19

---

### MEL-01: Correção do Cálculo de Quartis do IQR

**Problema Identificado:**
O cálculo de Q1 e Q3 usa divisão inteira simples em vez de percentis reais:

```python
# Código atual (sda17.py:114-115)
q1 = sorted_f[n // 4]
q3 = sorted_f[min(n - 1, 3 * n // 4)]
```

Para n=7: `q1 = sorted_f[1]` e `q3 = sorted_f[5]`, o que não corresponde ao 25º e 75º percentis verdadeiros. Com janelas pequenas (3-7 forças), o erro de arredondamento pode incluir/excluir forças na fronteira.

**Sugestão:**
Usar `statistics.quantiles()` do Python 3.10+ ou interpolação linear manual:
```python
# Proposta
from statistics import quantiles
q1, _, q3 = quantiles(sorted_f, n=4)
```

**Impacto Esperado:** Filtragem IQR mais precisa → menos remoção indevida de forças válidas → +1-2pp na taxa de acerto.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ `statistics.quantiles()` requer `n >= 2` dados. Para n=3, `quantiles(data, n=4)` pode gerar `StatisticsError`. **Mitigação:** Manter o bypass de IQR para n<4 já existente (linha 110).
- ⚠️ Resultado retornado como `float` em vez de `int`. O cálculo de `lower_bound` e `upper_bound` continuará funcionando pois a comparação `<=` aceita float×int. **Sem risco.**
- ✅ Não altera a interface pública de `_predict_robust()`.

---

### MEL-02: Detecção de Previsão "Travada" (Stuck Prediction)

**Problema Identificado:**
Na sessão atual, IDs 2371 e 2373 geraram a **mesma previsão** (centro=20, força=19) consecutivamente, ambas falhando. Não existe mecanismo para detectar ou corrigir repetição de centro.

O fenômeno ocorre quando a weighted median converge para um valor estável que não reflete mudanças nos dados recentes — a timeline tem forças consistentes que produzem sempre o mesmo output.

**Sugestão:**
Adicionar rastreamento dos últimos N centros preditos e, se o mesmo centro aparece 3+ vezes consecutivas, aplicar uma perturbação:

```python
# Em SDA17Strategy.__init__()
self._last_centers = deque(maxlen=5)

# Em analyze(), antes de retornar
self._last_centers.append(center_number)
if len(self._last_centers) >= 3 and len(set(list(self._last_centers)[-3:])) == 1:
    # Perturbação: shift center ±2 posições aleatoriamente
    offset = random.choice([-2, -1, 1, 2])
    center_number = wheel_sequence[(wheel_sequence.index(center_number) + offset) % 37]
    numbers = self.get_neighbors(center_number, self.num_neighbors, wheel_sequence)
```

**Impacto Esperado:** Evitar sequências de 3+ erros com a mesma previsão. Na sessão analisada, teria evitado 1-2 erros consecutivos.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Uso de `random`:** Introduz não-determinismo. Duas execuções com os mesmos dados podem gerar resultados diferentes, dificultando debug e backtest. **Mitigação:** Usar perturbação determinística (ex: alternar +2/-2 baseado em paridade do spin number).
- ⚠️ **State no strategy:** `_last_centers` é estado mutável na estratégia. Se a estratégia for compartilhada entre direções, centros CW e CCW se misturam. **Mitigação:** Usar dois deques (`_last_centers_cw`, `_last_centers_ccw`) ou passar a direção como parâmetro.
- ⚠️ **Falso positivo:** Se a timeline realmente tem padrão estável com centro correto, a perturbação PIORA o resultado. **Mitigação:** Só perturbar se as últimas 3 previsões com o mesmo centro foram ALL misses (verificar via performance).
- ✅ Não altera `_predict_robust()` — perturbação aplicada pós-pipeline.

**Sugestão Revisada (pós-auditoria):**
Só aplicar perturbação quando as últimas 3 previsões com mesmo centro foram **todas erros**. Usar dois deques separados por direção. Perturbação determinística (offset = +2 se spin par, -2 se ímpar).

---

### MEL-03: Ajuste do Fator de Decay (Weighted Median)

**Problema Identificado:**
O decay atual é `0.8`, gerando pesos:
- Posição 0 (mais recente): 1.0 → 10 repetições
- Posição 1: 0.8 → 8 repetições
- Posição 2: 0.64 → 6 repetições
- Posição 3: 0.512 → 5 repetições
- Posição 4: 0.41 → 4 repetições
- Posição 5: 0.33 → 3 repetições
- Posição 6: 0.26 → 2 repetições

A posição 0 tem 5× o peso da posição 6. Com forças voláteis, o dado mais recente domina excessivamente, causando previsões que "saltam" entre extremos.

Na análise: forças CW variaram de 7 a 33 (amplitude=26), e a mediana ponderada convergiu para ~10, ignorando as forças altas.

**Sugestão A (Conservadora):** Reduzir decay para `0.7` — mais peso no recente, reage mais rápido a mudanças.

**Sugestão B (Moderada):** Aumentar decay para `0.9` — distribuição mais uniforme, menos sensível a outliers recentes.

**Sugestão C (Adaptativa):** Decay variável baseado na dispersão:
```python
spread = max(forces) - min(forces)
adaptive_decay = 0.7 if spread > 15 else 0.9
```

**Impacto Esperado:** Melhor adaptação a regimes de força variável.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Sugestão A (decay=0.7):** Risco de overfitting ao último dado. Se a força mais recente foi anômala (ex: bola bateu no separador), a previsão inteira desvia. **Risco médio.**
- ⚠️ **Sugestão B (decay=0.9):** Risco de reagir lento a mudanças reais de regime (ex: dealer trocou). **Risco baixo.**
- ⚠️ **Sugestão C (adaptativa):** Risco de **oscilação de regime** — se spread oscila entre 14-16, decay alterna entre 0.7/0.9 a cada spin, criando instabilidade. **Mitigação:** Usar histerese (só muda decay se spread ultrapassar limiar por 3+ spins consecutivos).
- ✅ Nenhuma alteração na interface pública.

---

### MEL-04: Expansão de Cobertura para 21 Números

**Problema Identificado:**
A cobertura atual de 19 números (51.4%) está gerando taxa de acerto global de 46.6% — ou seja, 4.8pp **abaixo** do que seria a performance aleatória com a mesma cobertura. Isso sugere que a predição de centro está sistematicamente deslocada.

Expandir para 21 números (56.8%) aumentaria a tolerância a erros de força.

**Sugestão:**
Alterar `num_neighbors` de 9 para 10:
```python
# sda17.py:24
super().__init__(name="SDA-19", num_neighbors=10)  # Era 9 → agora 10
# Resultado: 10 + 1 + 10 = 21 números = 56.8% da roda
```

**Impacto Esperado:** +5pp direto na taxa de acerto (cobertura mecânica). A previsão de força teria mais margem de erro antes de causar miss.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Custo financeiro:** Cada aposta cobre 21 em vez de 19 números. Se o stake é R$1/número, a aposta sobe de R$19 para R$21 (+10.5%). O payout (35:1 em cada número) continua igual, mas o **lucro por acerto cai de R$16 para R$14**. **Risco financeiro calculável.**
- ⚠️ **Impacto no Martingale:** `BET_VALUES` em `game.py:35` está hardcoded como `{1: 19, 2: 38, 3: 76}`. Se cobertura mudar para 21, os valores de aposta precisam atualizar para `{1: 21, 2: 42, 3: 84}`. **Bug se esquecer de atualizar — aposta sub-cobre os números.**
- ⚠️ **Nome da estratégia:** "SDA-19" refere-se a 19 números. Renomear para "SDA-21" se mudar. Impacto em logs, DB (coluna `sda_score` não muda, mas documentação sim).
- ✅ `get_neighbors()` aceita qualquer radius — alteração é trivial.

---

### MEL-05: Aprimoramento do Drift Detection

**Problema Identificado:**
O drift detection atual (linhas 138-148 do `sda17.py`) verifica apenas se as 3 últimas forças formam sequência monotônica crescente ou decrescente. A extrapolação usa `sum(diffs) * 0.5`.

Limitações:
1. Requer monotonicidade **estrita** — se as forças são [15, 14, 14], `diffs = [1, 0]`, nem ambos `> 0` nem ambos `< 0` → drift=0.
2. O multiplicador fixo de 0.5 pode sub/sobre-extrapolar.
3. Usa apenas as 3 últimas forças brutas (antes do IQR), que podem incluir outliers.

Na sessão atual, o drift pode ter inflado previsões CCW para 19 quando a realidade era 10-16.

**Sugestão:**
```python
# Usar forças LIMPAS (pós-IQR) para drift
clean_forces = [f for f, _ in clean][:3]  # 3 mais recentes limpas
if len(clean_forces) >= 3:
    diffs = [clean_forces[i] - clean_forces[i+1] for i in range(2)]
    if all(d > 0 for d in diffs) or all(d < 0 for d in diffs):
        # Multiplicador proporcional à magnitude
        avg_diff = sum(diffs) / len(diffs)
        drift_adj = int(avg_diff * 0.4)  # Reduzido de 0.5 para 0.4
```

**Impacto Esperado:** Drift mais conservador e baseado em dados limpos → menos inflação de previsão.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Ordem das forças limpas:** Após IQR, `clean` pode ter gaps nos índices. Se forças [0,1,2,3,4,5,6] viraram clean = [0,2,4] (posições), os "3 mais recentes limpos" são posições 0,2,4 — que podem não ser consecutivos temporalmente. **Mitigação:** Ordenar `clean` por `orig_idx` antes de extrair.
- ⚠️ **Com n<4 (sem IQR):** `clean = forces` completo. Funciona normalmente.
- ⚠️ **Multiplicador 0.4 vs 0.5:** Diferença marginal. Pode não ser perceptível com datasets pequenos. **Risco baixo.**
- ✅ Clamping `max(1, min(37, ...))` continua protegendo contra overflow.

---

### MEL-06: Score Formula Baseada em Dados

**Problema Identificado:**
O score atual é calculado por:
```python
score = min(6, max(1, int(survival * 3 + tightness * 3 + stable_bonus)))
```

Onde:
- `survival` = porcentagem de forças que sobreviveram ao IQR (0-1)
- `tightness` = `max(0, 1 - spread/15)` (0-1)
- `stable_bonus` = 1 se drift=0, senão 0

Na sessão analisada, **todos** os scores ativos foram 3-4. O score nunca variou significativamente, e a variação que existiu não correlacionou com acerto/erro.

**Sugestão:**
Incluir um componente **histórico** no score:
```python
# Adicionar: taxa de acerto recente da direção como fator
recent_hit_rate = sum(last_5_results) / len(last_5_results) if last_5_results else 0.5
score = min(6, max(1, int(
    survival * 2 +
    tightness * 2 +
    recent_hit_rate * 2 +
    stable_bonus
)))
```

**Impacto Esperado:** Score mais discriminativo → Kill Switch e confiança do Triple Rate com melhor calibração.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Acoplamento circular:** Se o score influencia a decisão de apostar, e a decisão de apostar influencia os resultados, que por sua vez influenciam o score... há risco de **feedback loop**. Em teoria: baixo score → menos apostas → menos dados → score instável. **Mitigação:** O Triple Rate já quase nunca veta (kill switch requer score ≤ 2 E C4=0%), então o feedback loop é fraco.
- ⚠️ **Dependência cross-module:** `analyze()` na estratégia precisaria receber `last_5_results`, que é estado do `game.py`. Atualmente a estratégia é pura (sem estado de jogo). **Risco arquitetural:** Viola separação de concerns. **Alternativa:** Calcular o score ajustado no `engine.py` DEPOIS de receber o `StrategyResult`, sem modificar a estratégia.
- ✅ Clamping `min(6, max(1, ...))` continua válido.

---

## PARTE II — MELHORIAS NO TRIPLE RATE ADVISOR

---

### MEL-07: Kill Switch com Gradiente em Vez de Binário

**Problema Identificado:**
O Kill Switch atual é extremamente permissivo — só ativa quando C4=0% **E** SDA Score ≤ 2. Na prática, quase nunca dispara. Na sessão analisada, houve sequências de 3+ erros consecutivos que não foram vetadas.

**Sugestão:**
Adicionar um nível intermediário de cautela sem vetar completamente:

```python
# KILL SWITCH (existente)
if len(performance) >= 4 and c4 == 0 and sda_score <= 2:
    return BetAdvice(should_bet=False, confidence="baixa", ...)

# NOVO: MODO CAUTELA (reduz agressividade)
if len(performance) >= 4 and c4 <= 0.25 and m6 <= 0.33:
    return BetAdvice(should_bet=True, confidence="baixa",
        reason=f"⚠️ CAUTELA: C4={c4:.0%}, M6={m6:.0%} — apostar com stake mínimo")
```

A confiança "baixa" poderia ser usada pelo overlay para sinalizar ao usuário que a aposta é de risco elevado.

**Impacto Esperado:** Melhor gestão de risco psicológica para o usuário, sem alterar a lógica de aposta automática.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Sem efeito real no backend:** Se `should_bet=True`, o sistema continua apostando igual. A confiança "baixa" só aparece no overlay. Para ter impacto real, o Martingale deveria respeitar a confiança e reduzir stake. **Mitigação:** Integrar confiança ao cálculo de `current_bet` no `MartingaleState`.
- ⚠️ **Interação com confiança "alta":** Se adicionarmos "cautela" como confidence="baixa" mas should_bet=True, as métricas de confiança misturam "kill switch vetou" (baixa, should_bet=False) com "cautela" (baixa, should_bet=True). **Mitigação:** Usar confidence="cautela" como valor separado.
- ✅ Não altera o comportamento do kill switch existente — é aditivo.

---

### MEL-08: Expansão da Janela de Performance

**Problema Identificado:**
As deques de performance (`performance_sda17_cw/ccw`) têm `maxlen=12`. Isso significa que o Triple Rate analisa no máximo os últimos 12 resultados. Com apostas alternando entre CW/CCW, são efetivamente ~6 resultados por direção nos últimos 12 spins.

O L12 (taxa de 12) usa todos os 12 disponíveis, mas C4 e M6 operam com dados muito recentes que podem ser ruidosos.

**Sugestão:**
Expandir `maxlen` de 12 para 24:
```python
# game.py:141-142
performance_sda17_cw: deque = field(default_factory=lambda: deque(maxlen=24))
performance_sda17_ccw: deque = field(default_factory=lambda: deque(maxlen=24))
```

E adicionar uma taxa L24 ao Triple Rate para visão de prazo mais longo.

**Impacto Esperado:** Triple Rate com base estatística mais robusta (mais dados por direção).

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Compatibilidade de state.json:** O `GameState.save()` serializa as deques. Se o formato mudar de maxlen=12 para maxlen=24, o `load()` precisa lidar com dados antigos (deques menores). **Verificação:** `deque.from_dict()` já aceita qualquer tamanho — o maxlen é aplicado na construção. **Sem risco** se o maxlen é definido no `field(default_factory=...)`.
- ⚠️ **Performance_snapshot no DB:** O campo `performance_snapshot` armazena a lista como JSON. Com 24 elementos, o campo cresce ~2×. **Impacto negligível** (de ~50 bytes para ~100 bytes por registro).
- ⚠️ **Métricas L12 → L24:** Se adicionar nova taxa, `bet_advisor.py` precisa adaptar a lógica de confiança. As comparações `c4 >= m6 >= l12` mudariam para `c4 >= m6 >= l12 >= l24`. **Risco de introduzir confiança "alta" em cenários de queda de longo prazo.** **Mitigação:** Manter L12 como limite do advisor, usar L24 apenas para dashboard.
- ✅ Não quebra a serialização existente.

---

## PARTE III — MELHORIAS NO MARTINGALE

---

### MEL-09: Janela de Avaliação Adaptativa

**Problema Identificado:**
O Martingale avalia em janelas fixas de 5 spins (`WINDOW_SIZE=5`), exigindo 3+ hits para manter/descer (`MIN_HITS_TO_PASS=3`). Isso é 60% de taxa mínima.

Porém, a cobertura é 51.4%, e a taxa global é 46.6%. Exigir 60% é mais rigoroso que a performance real. Na prática, o Martingale escala frequentemente de G1→G2→G3 e dispara STOPs desnecessários.

**Sugestão:**
Reduzir `MIN_HITS_TO_PASS` de 3 para 2, ou expandir `WINDOW_SIZE` de 5 para 7 com `MIN_HITS_TO_PASS=3`:

| Cenário | WINDOW | MIN_HITS | Taxa Mínima | Compatível com 46.6%? |
|---------|:------:|:--------:|:-----------:|:---------------------:|
| Atual | 5 | 3 | 60% | ❌ (acima da média) |
| Opção A | 5 | 2 | 40% | ✅ |
| Opção B | 7 | 3 | 43% | ✅ |

**Impacto Esperado:** Menos escalações desnecessárias G1→G2→G3, menor risco financeiro acumulado.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Opção A (5/2):** Permite que janelas com 2/5 = 40% de acerto se mantenham em G1. Com cobertura de 51.4%, isso está abaixo do aleatório → pode perpetuar uma estratégia que não funciona. **Risco: tolerância excessiva a má performance.**
- ⚠️ **Opção B (7/3):** Janelas maiores significam mais tempo em cada nível antes de avaliar. Se a estratégia estiver falhando, demora 7 spins (vs 5) para reagir. **Risco: reação mais lenta a mudanças de regime.**
- ⚠️ **Ambas opções:** O campo `gale_window_count` no DB registra plays por janela. Mudar WINDOW_SIZE altera o padrão de dados. Consultas históricas que comparam janelas antigas (5 plays) com novas (7 plays) terão inconsistência. **Mitigação:** Registrar WINDOW_SIZE na tabela `gale_windows` para contexto.
- ✅ Alteração localizada em `MartingaleState` — sem impacto na interface WS.

---

### MEL-10: Martingale Consciente da Direção

**Problema Identificado:**
Na sessão analisada, CW performou a 75% e CCW a 37.5%. No entanto, ambas as direções usam o mesmo esquema de Martingale (mesmos thresholds). Uma direção "quente" e outra "fria" recebem tratamento idêntico.

**Sugestão:**
Permitir que o Martingale de cada direção opere com parâmetros diferentes baseados na performance recente:

```python
# Se a direção está "fria" (performance < 40% em L12):
# → Voltar para G1 independente do resultado
# → Ou: reduzir stake dentro do mesmo Gale level

# Se a direção está "quente" (performance > 60%):  
# → Permitir janelas maiores antes de escalar
```

**Impacto Esperado:** Redução de exposição em direções que estão performando mal, enquanto maximiza ganhos em direções quentes.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Complexidade:** Introduz 2× mais estados (parâmetros por direção). Debugging fica mais difícil. O `state.json` dobra de tamanho para configuração Martingale.
- ⚠️ **Oscilação de regime:** Se CW alterna entre "quente" e "fria" rapidamente, os parâmetros mudam a cada poucos spins. Pode causar inconsistência no gerenciamento de risco. **Mitigação:** Histerese — só muda regime após 10+ spins consistentes.
- ⚠️ **Interação com janelas:** Se uma direção está no meio de uma janela (3/5 spins) e muda de regime, o WINDOW_SIZE muda no meio? Isso corrompe a avaliação. **Mitigação:** Só aplicar novo regime no INÍCIO da próxima janela.
- 🔴 **Risco alto de bugs:** A complexidade adicionada é significativa para ganho incerto. **Recomendação: postergar para uma versão futura**, focar primeiro em MEL-01 a MEL-05.

---

## PARTE IV — MELHORIAS DE OBSERVABILIDADE

---

### MEL-11: Logging Detalhado do Pipeline SDA

**Problema Identificado:**
Atualmente, os detalhes do pipeline SDA (survival_rate, outliers_removed, spread, drift) são salvos no campo `details` do `StrategyResult`, mas **não aparecem nos logs** nem no `performance_snapshot` do DB. Isso dificulta diagnosticar por que uma previsão falhou.

**Sugestão:**
Adicionar log estruturado com os detalhes do pipeline a cada spin processado:
```python
# Em engine.py, após strategy.analyze()
logger.info(f"  SDA Pipeline: survival={result.details.get('survival_rate')}, "
            f"outliers={result.details.get('outliers_removed')}, "
            f"spread={result.details.get('spread')}, "
            f"drift={result.details.get('drift')}, "
            f"method={result.details.get('method')}")
```

E salvar no campo `performance_snapshot` ou em uma nova coluna `sda_details` (JSON).

**Impacto Esperado:** Capacidade de diagnosticar post-mortem cada decisão com dados completos.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Volume de logs:** Com heartbeat a cada 1s e spins a cada ~40s, os logs já são volumosos. Adicionar log por spin (40s) é aceitável. **Sem risco.**
- ⚠️ **Nova coluna no DB:** Adicionar `sda_details TEXT` ao schema requer migration. Sem Alembic, a migration é manual. O `CREATE TABLE IF NOT EXISTS` só executa se a tabela não existe. Para tabelas existentes, precisa `ALTER TABLE`. **Mitigação:** Usar o campo `performance_snapshot` existente (já é JSON) para incluir SDA details, evitando migration.
- ✅ Log é aditivo — não altera comportamento.

---

### MEL-12: Dashboard de Performance por Período

**Problema Identificado:**
O `analytics_handler.py` tem `get_performance_timeline()` que agrupa por hora/dia, mas não há visibilidade real-time de métricas como:
- Taxa de acerto rolling (últimos 20 spins)
- Erro médio de força rolling
- Desvio padrão de forças por timeline

**Sugestão:**
Incluir no `state_sync` (heartbeat de 1s) métricas resumidas:
```python
state_sync["data"]["analytics"] = {
    "rolling_hit_rate_20": ...,
    "avg_force_error_10": ...,
    "timeline_cw_std": ...,
    "timeline_ccw_std": ...,
}
```

**Impacto Esperado:** O overlay e popup dashboard podem exibir indicadores de saúde da estratégia em tempo real.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Performance do heartbeat:** Calcular desvio padrão a cada 1s pode adicionar latência. Com timelines de 45 forças, é O(45) — negligível. **Sem risco.**
- ⚠️ **Tamanho do payload:** Adicionar ~100 bytes ao `state_sync` que é broadcast para todos os clients. Com 2-3 clients e broadcast a 1s, o overhead é ~300 bytes/s. **Negligível.**
- ✅ Alteração aditiva ao `state_sync`, retrocompatível (clients antigos ignoram campos desconhecidos).

---

## PARTE V — MELHORIAS ARQUITETURAIS

---

### MEL-13: Separação do Spread Normalization

**Problema Identificado:**
O cálculo de `tightness` usa `spread / 15` como normalização (linha 154 de `sda17.py`). O valor 15 é hardcoded e arbitrário — não reflete a distribuição real de forças na roda.

Na roda europeia com 37 slots, a força máxima é 18 (metade da roda, caminho mais curto). O spread máximo teórico é 18 (se forças variam de 1 a 18+).

**Sugestão:**
Usar normalização baseada na física da roda:
```python
MAX_FORCE = 18  # Metade da roda europeia (37/2)
tightness = max(0, 1 - spread / MAX_FORCE)
```

**Impacto Esperado:** Score mais calibrado — spreads de 15+ (quase impossíveis na prática) não mais dominam o cálculo.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Forças > 18:** O `_calculate_force()` em `game.py` retorna a distância mínima circular (sempre ≤ 18). Mas o campo `spin_force` no DB mostra valores como 33, 34, 35. **Investigação necessária:** Se a força calculada é `min(cw_dist, ccw_dist)`, o máximo é 18. Mas se é `calculate_distance(from, to, direction)` com direção fixa, pode ser até 36. **Verificar `_calculate_force()` no `game.py` antes de implementar.**
- ⚠️ Se forças podem ser > 18, normalizar por 18 daria tightness negativo (clampado em 0). O `max(0, ...)` protege contra isso. **Sem crash, mas tightness=0 em todos os cenários de alta dispersão.**
- ✅ Alteração de constante — sem risco arquitetural.

---

### MEL-14: Proteção contra Forças Anômalas no Input

**Problema Identificado:**
O `_calculate_force()` em `game.py` calcula a distância entre o número anterior e o atual na direção informada. Se a direção informada pela extensão estiver incorreta (ex: extensão informa "horario" mas o dealer girou anti-horário), a força calculada será `37 - força_real`, potencialmente corrompendo a timeline.

**Sugestão:**
Adicionar validação de sanidade na força calculada:
```python
def _calculate_force(self, from_number, to_number, direction):
    # ... cálculo existente ...
    force = (to_idx - from_idx) % 37  # ou inverso
    
    # Sanity check: força > 30 é improvável fisicamente
    if force > 30:
        logger.warning(f"⚠️ Força anômala detectada: {force} ({from_number}→{to_number}, {direction})")
        # Usar a força mínima em vez da direção informada
        alternative_force = 37 - force
        if alternative_force < force:
            logger.info(f"  Corrigido para {alternative_force} (provável inversão de direção)")
            return alternative_force
    
    return force
```

**Impacto Esperado:** Protege contra dados corrompidos da extensão → timeline mais limpa → previsões mais confiáveis.

**🔍 Auditoria de Bugs da Proposta:**
- ⚠️ **Limiar 30 arbitrário:** Forças entre 19-30 são possíveis (embora menos prováveis que 1-18 para caminho mínimo). O limiar deveria ser ~19 (metade +1) se a intenção é detectar inversão de direção.
- 🔴 **RISCO CRÍTICO:** Se a correção for aplicada, a força armazenada na timeline CW pode ser uma força CCW "corrigida". Isso **corrompe a timeline** — forças de direções diferentes são misturadas. **A correção deveria trocar a direção, não a força.**
- ⚠️ **Dados históricos:** Se implementado, forças futuras terão distribuição diferente das históricas. Backtests com dados antigos ficariam inconsistentes.
- **Recomendação pós-auditoria:** Em vez de corrigir a força, apenas **logar** o warning e registrar um flag `anomalous_force=True` no DB para análise posterior. A correção automática é arriscada demais.

---

## PARTE VI — PRIORIZAÇÃO E ROADMAP SUGERIDO

### Matriz Impacto × Risco

| ID | Melhoria | Impacto | Risco | Complexidade | Prioridade |
|:--:|----------|:-------:|:-----:|:------------:|:----------:|
| MEL-01 | Correção quartis IQR | Médio | Baixo | Baixa | 🔴 **P1** |
| MEL-02 | Detecção stuck prediction | Alto | Médio | Média | 🔴 **P1** |
| MEL-11 | Logging pipeline SDA | Alto | Baixo | Baixa | 🔴 **P1** |
| MEL-05 | Drift com dados limpos | Médio | Baixo | Baixa | 🟡 **P2** |
| MEL-13 | Spread normalization | Baixo | Baixo | Baixa | 🟡 **P2** |
| MEL-03 | Decay adaptativo | Médio | Médio | Média | 🟡 **P2** |
| MEL-08 | Performance window 24 | Médio | Baixo | Baixa | 🟡 **P2** |
| MEL-09 | Martingale window adapt. | Médio | Médio | Média | 🟢 **P3** |
| MEL-04 | Cobertura 21 números | Alto | Médio | Baixa | 🟢 **P3** |
| MEL-12 | Dashboard real-time | Baixo | Baixo | Média | 🟢 **P3** |
| MEL-07 | Kill Switch gradiente | Baixo | Baixo | Baixa | 🟢 **P3** |
| MEL-06 | Score baseado em dados | Médio | Alto | Alta | 🔵 **P4** |
| MEL-14 | Proteção força anômala | Médio | Alto | Média | 🔵 **P4** |
| MEL-10 | Martingale por direção | Baixo | Alto | Alta | 🔵 **P4** |

### Sprint Sugerida

**Sprint 1 (Quick Wins — P1):**
- MEL-01: Trocar cálculo de quartis por `statistics.quantiles()`
- MEL-02: Implementar detecção de stuck prediction (versão auditada: com check de misses)
- MEL-11: Adicionar log estruturado dos detalhes SDA

**Sprint 2 (Refinamentos — P2):**
- MEL-05: Drift detection usando dados pós-IQR
- MEL-13: Spread normalization com MAX_FORCE=18
- MEL-03: Testar decay adaptativo via backtest antes de produção
- MEL-08: Expandir performance deques para maxlen=24

**Sprint 3 (Avaliação Estratégica — P3):**
- MEL-04: Testar cobertura de 21 números via backtest (impacto financeiro)
- MEL-09: Avaliar WINDOW_SIZE via análise do histórico de gale_windows
- MEL-12: Dashboard com métricas rolling

**Sprint 4 (Experimental — P4):**
- MEL-06, MEL-10, MEL-14: Requerem análise mais profunda e backtest extensivo

---

> **Documento gerado em:** 26/03/2026 22:29 UTC  
> **Método:** Análise estática do código + dados de produção + auditoria de bugs por proposta  
> **Fontes:** `strategies/sda17.py`, `state/bet_advisor.py`, `state/game.py`, `core/engine.py`, `core/roulette.py`, `database/sqlite_repo.py`, `data/decisions.db`  
> **Status:** ESTUDO — nenhuma alteração no programa foi realizada
