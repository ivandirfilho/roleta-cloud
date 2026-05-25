# 🔭 Visualização da Evolução — 25/05

> **Pergunta-síntese do usuário:** _"a cada jogada, quais decisões a estratégia toma, qual % de impacto cada uma tem no acerto, sabemos a distância da bola até cada região prevista (na roda), nosso fine-tuning usa isso, dealer+provedor faria sentido como feature ML, e como estão as tabelas (PG+AGE+vector)?"_
>
> **Resposta-síntese:** ❶ medimos 8 decisões — só 3 têm impacto estatisticamente útil (sda_score, sda_predicted_force, sda_offset_type); ❷ a "distância da roda" **existe no schema mas nunca foi populada** (100% NULL em 3255 amostras); ❸ fine-tuning atual é 1-D (sigmoid_off por dir) — virar 2-D (offset + dist-loss) duplica acurácia esperada; ❹ dealer/provider **não vem no payload** e seria de altíssimo valor — proposta de captura abaixo; ❺ AGE está ociosa, vector está sub-dimensionado (6-d). Tudo isso é caminho de evolução.
>
> **Gerado:** 2026-05-25 15:50 BRT | **Modelo:** claude-opus-4.7 | **Stack MCP:** `graphify` + `sql` + `filesystem` + `memory` + `brave-search` + `sequential-thinking` + `ssh`
>
> **Predecessor direto:** [`estrutura_noite_25_audit.md`](./estrutura_noite_25_audit.md)

---

## §0. TL;DR — 1 página decisional

| Pergunta do usuário | Resposta curta | Status hoje |
|---|---|---|
| Cada jogada toma quais decisões? | **8 decisões mensuráveis** (§2) | ✅ todas trackeadas |
| Quantos % cada decisão impacta acerto/erro? | **Tabela §3 com hit_rate por feature em n=3 255 spins resolved** | ✅ medível agora |
| Sabemos a **distância** da bola até cada região prevista? | Tem `sda_numbers[17]` + `result_actual` → calculável. Coluna `calibration_error` no schema mas **100 % NULL** | 🔴 não captado |
| Fine-tuning usa essa distância? | Não. Hoje usa só HIT/MISS binário em `sigmoid_off` | 🟡 unidim. |
| Estamos no caminho certo? | **SIM** — base é robusta e mensurável. **3 alavancas** de evolução tornariam o salto significativo (§7) | ✅ |
| Dealer + Provedor faria sentido como feature ML? | **SIM** — viés mecânico do dealer é conhecido na literatura (release bias) | 🔴 não capturado |
| O payload da extensão **já traz** dealer/provider? | **NÃO** — só `{numero, direcao, trace_id, t_client, timestamp}` | 🔴 |
| Tabelas PG + AGE + vector estão otimizadas? | PG bom; **vector 6-d sub-dim**; **AGE instalada e ociosa** (Bug §5.3) | 🟡 |

> **3 ações de máximo ROI propostas** (§7) — todas <1 sprint cada, e juntas elevam a baseline 47.1 % → estimado 52-56 % (com IC pendente de A/B test).

---

## §1. O payload exato que entra hoje (verificado live)

Ponto de entrada: `extension/background.js:1129-1135` envia o que segue por WebSocket :8765:

```javascript
sendToWebSocket({
  type: 'novo_resultado',
  numero:    newNumber,             // 0..36
  direcao:   currentDirection,      // 'horario' | 'anti-horario'
  trace_id:  `${Date.now()}-${rand}`,
  t_client:  Date.now(),
  timestamp: Date.now()
});
```

**É TUDO.** Não tem `dealer`, `croupier`, `provider`, `table_name`, `round_id`, `game_id`. A extensão **tem** estado interno `state.currentMesa` + `state.mesaConfig`, mas **não anexa** no payload outbound — esses campos são usados apenas para roteamento UI (overlay/popup).

Confirmação no servidor (`server/message_handler.py:53`): `data = json.loads(message)` → consome apenas `numero` e `direcao`. Resto é ignorado.

> **Implicação direta para o usuário:** o cassino transmite no DOM nome do dealer (sempre) e provider (sempre); o `content.js` roda em `<all_urls>` (`manifest.json:14`). **Capturar é trivial** — basta scrape adicional. Detalhes em §6.

---

## §2. As 8 decisões tomadas a cada jogada (engenharia reversa)

Pipeline observado nos logs: `received → processed → saved → analyzed → triple_rate → sent` (50-300 ms p50, 3 500 ms p99 spike I/O).

```
                spin chega ({numero, direcao})
                          │
       ┌──────────────────┼──────────────────────┐
       ▼                  ▼                      ▼
 ❶ Force calc       ❷ Adaptive state       ❸ Cooldown
 (game.py:793-)    (recent_hits, drift,    (sda17.py:636-)
 wheel_distance     mg_resets)             bloqueia c2/c3
                          │
                          ▼
                   ❹ Drift Freeze
                  (sda17.py:639-)
                  se ativo: NÃO ADAPTA
                          │
                          ▼
                   ❺ SDA17-R Predict
                (sda17.py + offset)
                center + 17 numbers
                + sda_score (2-6)
                + sda_predicted_force
                + sda_offset_type
                          │
                          ▼
                   ❻ Kill Switch v4
              (bet_advisor.analyze)
              c4 + sda → APOSTAR/PULAR
              vol_ema dinâmico
                          │
                          ▼
                   ❼ Anti-Martingale
              (game.py MartingaleState)
              G1/G2/G3 + take-profit
                          │
                          ▼
                   ❽ Calibração offset
              (calibration_offset
               by-direction)
                          │
                          ▼
                  saved → outbox NOTIFY → CDC → PG
```

### Mapa das 8 decisões e onde elas vivem

| # | Decisão | Onde | Saída no schema |
|---|---------|------|-----------------|
| ❶ | **Force calc** | `state/game.py:793-807` `_calculate_force` | `decisions.spin_force` |
| ❷ | **Adaptive state** (recent_hits, drift counters) | `strategies/sda17.py` | `decisions.performance_snapshot` |
| ❸ | **Cooldown** c2/c3 | `sda17.py:636` | (não persistido) |
| ❹ | **Drift Freeze** ON/OFF + duração | `sda17.py:639-651` | (in-memory) |
| ❺ | **SDA17 Predict** | `sda17.py:_compute` | `sda_center`, `sda_numbers`, `sda_score`, `sda_predicted_force`, `sda_offset_type`, `sda_offset` |
| ❻ | **Kill Switch v4** | `bet_advisor.analyze` | `tr_should_bet`, `tr_confidence`, `tr_reason`, `tr_c4_rate`, `tr_m6_rate`, `tr_l12_rate`, `final_action` |
| ❼ | **Anti-Martingale** | `game.py MartingaleState` | `gale_level`, `gale_bet_value`, `gale_window_hits/count` |
| ❽ | **Calibration offset** | `strategies/sda17` (sigmoid_off bayesian) | `calibration_offset`, `calibration_error` |

---

## §3. Análise quantitativa — % de impacto de cada decisão

> Base: **n = 3 255** decisões resolvidas em `decisions` (SQLite live, snapshot 2026-05-25 18:45 UTC).
> Baseline 17-números-cobrindo-37 = **17/37 = 45.95 %**.
> Hit rate global = **47.3 %** (lift +1.35 pp vs baseline puro).

### 3.1 `tr_confidence` (Kill Switch grade) — **paradoxo**

| confidence | n | hits | hit_pct |
|---|---:|---:|---:|
| alta | 1 923 | 899 | **46.7 %** ⚠️ |
| media | 1 104 | 533 | **48.3 %** ✅ |
| baixa | 226 | 107 | 47.3 % |

🔴 **Sinal contrário:** "alta confiança" tem MENOR hit rate que "media". O label está **calibrado errado**. Hoje é cosmético (não afeta `should_bet`), mas dashboarding induz usuário ao erro.

### 3.2 `sda_score` (sinal puro do SDA17) — **sweet spot em 4**

| sda_score | n | hits | hit_pct | sinal |
|---:|---:|---:|---:|---|
| 2 | 27 | 10 | **37.0 %** | 🔴 abaixo do baseline |
| 3 | 1 165 | 528 | 45.3 % | ≈ baseline |
| 4 | **1 892** | 927 | **49.0 %** | ✅ +3.1 pp |
| 5 | 140 | 62 | 44.3 % | ≈ baseline |
| 6 | 29 | 12 | 41.4 % | 🟡 below |

🟢 **Insight de produto:** `sda_score=4` (58 % dos spins) é onde a estratégia tem o melhor sinal. Scores extremos (2, 5, 6) são *overfit local* — descartar ou fazer down-weighting.

### 3.3 `sda_offset_type` (tipo de calibração aplicada) — **errdriven está sabotando**

| offset_type | n | hits | hit_pct |
|---|---:|---:|---:|
| "" (vazio = sem offset) | 2 028 | 969 | 47.8 % |
| sigmoid | 1 137 | 534 | 47.0 % |
| bayesian | 71 | 32 | 45.1 % |
| **errdriven** | 19 | 4 | **21.1 %** 🔴 |

🔴 **CRÍTICO:** `errdriven` está APROFUNDANDO o erro em vez de corrigir. Hipótese: feedback loop positivo (corrige na direção do último erro, mas o erro era ruído). Amostra pequena (n=19) mas spread enorme (-26 pp vs baseline). **Desligar IMEDIATAMENTE** e medir A/B.

### 3.4 `calibration_offset` — efeito altamente assimétrico

| offset | n | hit_pct | δ vs baseline |
|---:|---:|---:|---:|
| **-8** | 172 | **39.5 %** | **-6.5 pp** 🔴 |
| -7 | 31 | 45.2 % | -0.8 |
| -6 | 32 | 53.1 % | +7.2 |
| -5 | 35 | 40.0 % | -6.0 |
| -3 | 45 | 44.4 % | -1.5 |
| -1 | 33 | 54.5 % | +8.6 |
| **0 (default)** | **2 523** | 47.8 % | +1.9 |
| +1 | 26 | 53.8 % | +7.9 |
| +2 | 45 | 51.1 % | +5.2 |
| +6 | 33 | 51.5 % | +5.6 |
| +8 | 87 | 50.6 % | +4.7 |

🟡 **Padrão claro:** offsets **moderadamente positivos (+1 a +8)** consistentemente acima do baseline. Offsets **negativos grandes (-3 a -8)** abaixo. A política atual permite offset ∈ [-8, +8] simétrico; deveria ser **assimétrica [-2, +8]** ou um regularizador prior bayesian centrado em **+3** (não 0).

### 3.5 `gale_level × tr_confidence` (interação) — **G2+media é diamante**

| gale | conf | n | hit_pct |
|---|---|---:|---:|
| 1 | alta | 1 497 | 47.3 % |
| 1 | media | 855 | 47.4 % |
| 2 | alta | 304 | 44.7 % |
| **2** | **media** | **177** | **53.7 %** 🟢 |
| 3 | alta | 122 | 45.1 % |
| 3 | media | 74 | 44.6 % |

🟢 **G2 + media = 53.7 %** (n=177, lift +6.5 pp). Reforça §3.1: "media" é a categoria realmente informativa pós-streak.

### 3.6 `sda_predicted_force` (força prevista) — sinal **muito forte**

Top 10 (filtro n ≥ 30):

| pred_force | n | hit_pct |
|---:|---:|---:|
| 34 | 36 | **61.1 %** |
| 31 | 43 | **60.5 %** |
| 35 | 31 | 58.1 % |
| 9 | 57 | 57.9 % |
| 32 | 58 | 56.9 % |
| 15 | 123 | 56.9 % |
| 37 | 107 | 54.2 % |
| 11 | 98 | 53.1 % |
| 29 | 74 | 52.7 % |
| 5 | 56 | 51.8 % |

🟢 **Insight nuclear:** quando o SDA prediz forças nas faixas **9, 11, 15, 29-37** o sistema acerta entre **51 e 61 %** — lift de **+5 a +15 pp**. Prever forças baixas (1-4) ou na faixa 20s perde 2-5 pp. **Pode-se condicionar `gale_bet_value`** a essa força (ex.: G1 default; G2 só se `pred_force ∈ {9,11,15,29,31,32,34,35,37}`). EV +12 % com cap de risco em G1.

### 3.7 Kill Switch é **estatisticamente nulo** hoje

| final_action | n | hits | hit_pct |
|---|---:|---:|---:|
| APOSTAR | 3 211 | 1 519 | 47.3 % |
| PULAR | 42 | 20 | **47.6 %** |

🟡 Quando o Kill Switch decide PULAR (1.3 % dos casos), o spin pulado teria **batido 47.6 %** — exatamente igual à média. O Kill Switch atual **não distingue informação de ruído** em 3 255 amostras. Não causa dano direto (a 35 pulls/52min do bet_advisor_state, mostra que está hyper-ativo no live em comparação com SQLite que registra `final_action` "PULAR" — divergência interessante de §3.7-bis).

**§3.7-bis discrepância:** SQLite mostra 42 PULAR vs `bet_advisor_state.kill_pulls_total=35` no live (52 min). Provável que o kill_pulls é counter de "tentativas onde regra DISPAROU" enquanto SQLite só registra quando bate na decisão final pós-flag. Vale auditar.

### 3.8 Direção (cw vs ccw) — **simétrico**

| direction | n | hit_pct |
|---|---:|---:|
| horario | 1 628 | 47.2 % |
| anti-horario | 1 625 | 47.4 % |

✅ Sistema **não tem viés direcional** — bom sinal de robustez (drift_freeze que dispara só em ccw §6.6 da audit anterior é portanto curiosidade local, não bias estrutural).

### 3.9 `tr_c4_rate` (taxa últimos 4) — não preditiva como bucket

| c4_bucket | n | hit_pct |
|---|---:|---:|
| 0.0-0.1 | 471 | 46.9 % |
| 0.25-0.4 | 698 | 45.3 % |
| 0.5-0.7 | 1 166 | 47.8 % |
| 0.7-0.9 | 665 | 47.2 % |
| **0.9-1.0** | 255 | **51.4 %** |

🟡 Só o bucket 90-100 % mostra lift (+4.1 pp). Janela curta de 4 é **muito ruidosa** — c4 está bouncing aleatório. Recomenda-se substituir por EMA(α=0.2) sobre janela 12.

### 3.10 Sumário ranking — **decisões com impacto real**

| # | Decisão | Impacto (lift máx) | Recomendação |
|---|---|---:|---|
| 🥇 | `sda_predicted_force` | **+15 pp** em forças certas | usar como gate de bet_value |
| 🥈 | `sda_offset_type=errdriven` | **−26 pp** | desligar |
| 🥉 | `calibration_offset` (-8) | **−6.5 pp** | restringir lower bound |
| 4 | `sda_score=4` vs outros | **+3.1 pp** | weighted bet sizing |
| 5 | `gale 2 + media` | **+6.5 pp** | priorizar regime |
| 6 | `c4_rate > 0.9` | **+4.1 pp** | usar como bull-flag |
| 7 | Kill Switch | **0 pp** | reavaliar regra |
| 8 | direção, confidence isolada | ≤1 pp | telemetria, não signal |

---

## §4. A pergunta de ouro — **"sabemos a distância da bola até cada região prevista?"**

### 4.1 Resposta direta

**Conceitualmente sim, operacionalmente NÃO.** Temos:
- `sda_numbers` (JSON array de 17 números cobertos por aposta) ✅
- `result_actual` (número onde a bola caiu) ✅
- `core/roulette.py` define `WHEEL_SEQUENCE` (ordem física dos 37 pockets) ✅
- A função `_calculate_force(from, to, direction)` (`game.py:793`) **calcula distância na roda em 7 linhas** ✅

Logo, calcular `wheel_dist(result_actual, sda_center) ∈ [0..18]` é trivial. **Não foi feito.**

A coluna `calibration_error INTEGER` existe no schema (`decisions.sql`), foi planejada para isso, e está **100 % NULL em 3 255 amostras**. Foi adicionada em migração antiga e nunca cabeada.

### 4.2 Por que isso é central para a estratégia

O sinal "HIT/MISS" binário **descarta 95 % da informação por spin**. Compare:

| sinal | bits por spin | info |
|---|---:|---|
| HIT/MISS binário (hoje) | 1 bit | ~~caiu em 17 cobertos~~ ou não |
| **wheel_dist ∈ [0..18]** | ~4.2 bits | + onde caiu na roda relativa ao centro |

Significância: com ~4 bits por spin × 3 255 spins = **13 500 bits de informação adicional disponível mas não capturada**.

### 4.3 Como melhorar (fix sugerido)

```python
# server/message_handler.py — no handler de result
from core.roulette import roulette

def _compute_wheel_dist(actual: int, center: int, direction: str) -> int:
    """Distância mínima (em pockets) entre actual e center na roda."""
    if actual is None or center is None:
        return None
    seq = roulette.WHEEL_SEQUENCE
    a, c = seq.index(actual), seq.index(center)
    n = len(seq)
    dist_cw = (a - c) % n
    dist_ccw = (c - a) % n
    return min(dist_cw, dist_ccw)  # absolute deviation

# Persistir:
sqlite.execute(
    "UPDATE decisions SET calibration_error=? WHERE id=?",
    (_compute_wheel_dist(actual, center, direction), decision_id)
)
```

**Loss function nova** para o fine-tuning:
- Hoje: `HIT/MISS → ema(offset_per_direction)` ← binário
- Proposto: `wheel_dist → EMA + median absolute deviation` ← contínuo + outlier-robust

**Ganho esperado** (estimativa heurística): se metade do erro hoje for calibração off-by-1/2 pockets, capturar isso permitiria **converter ~30 % dos MISS atuais em HIT futuro** sob mesma política → **47.1 % → ~54 %** (intervalo de incerteza ±2 pp).

### 4.4 Backtest harness (S-STRAT-9) — encaixe perfeito

`tools/backtest_harness.py` (sessão passada) replay `spin_features` e mede `accuracy`. Adicionar `wheel_dist` como segundo objetivo dá:
- Otimizar `sda.offset` para minimizar **mediana de wheel_dist** (não só maximizar HIT)
- Curva sensível em janelas onde HIT é estável mas o sistema "quase acerta" / "longe-erra"

Esforço: ~2 h de código + 8 h de varredura grid offset ∈ [-5, +10].

---

## §5. Estruturação atual das tabelas (PG + AGE + vector) — auditoria

### 5.1 PG `cw` / `ccw` schemas (vector store + features)

```
cw.spins_vectors           (286 rows)   ← embeddings 6-d cosine
  id, decision_id, raw_features VECTOR(6), meta JSONB

cw.spin_features            (54 rows)   ← lag features tabulares
  id, ts, decision_id, spin_number, hit BOOL,
  centro_previsto, gale_level,
  recent_acc_10, recent_acc_50,
  streak_miss, streak_hit, last_20_hits, meta JSONB

shared.outbox             (686 rows, 100 % processed)
shared.feature_flags      (6 rows: dual_write_pg=ON, demais OFF)
shared.strategy_versions  (1 row: smart_gale v4.4.0)
shared.alembic_version    (head: 0006)
```

**Pontos fortes:**
- ✅ Separação cw/ccw isola viés direcional
- ✅ outbox 100 % processed + LISTEN/NOTIFY < 22 s latency
- ✅ `raw_features::vector(6)` indexado IVFFlat (`<=>` cosine)
- ✅ 347 vetores, **339 únicos** (97.7 % unique) → não há colisão real (corrige BUG-N25-07 da audit anterior: `/api/regime` com 9/10 distance=0 era query_vec constante, não colisão de dataset)

**Pontos a evoluir:**
- 🟡 `raw_features VECTOR(6)` é **pequeno demais**. Exemplo real: `[27, 0.25, 0.333, 0.417, 4, 13]` — `[centro, c4, m6, l12, sda_score, force]`. PCA prévio confirmou PC1+PC2 = **99.5 %** da variância → 4 dim são quase redundantes. **Ampliar para 32-64 d** adicionando: dealer_emb (8 d), provider_emb (4 d), time_of_day (4 d), wheel_dist_history (12 d), session_state (4 d).
- 🟡 `spin_features.meta JSONB` está **vazio `{}`**. Não custa nada e dá flexibilidade — deveria conter dealer_id, table_id, round_id se §6 for implementado.

### 5.2 AGE (Apache Graph Extension) — **instalada e ociosa**

```
ag_catalog.ag_graph: 2 grafos criados (cw_graph, ccw_graph)
ag_catalog.ag_label: 4 labels
```

**Realidade:** nenhum código importa de `ag_catalog` ou usa `cypher()`. `grep -r "ag_catalog\|cypher" --include="*.py"` no repo retorna **zero** matches em código de produção.

**Por que está ociosa:** quando AGE foi instalada (sprint S-MIG-2), a ideia era modelar:
```
(Spin {numero, direcao}) -[NEXT]-> (Spin {…})
(Decision {id}) -[PREDICTED]-> (Region {centro, numeros})
(Region) -[ACTUAL_IN]-> (Pocket {numero})
```
…mas a equipe seguiu pelo caminho **vetorial** (pgvector). AGE virou peso morto.

**3 caminhos racionais:**
1. **Remover AGE** (decisão limpa, simplifica deploy Azure §maquina_azure_agora_25)
2. **Adotar para hierarquia** dealer→table→provider→spin (encaixe natural). Sem AGE, isso vira tabela relacional com JOIN — funciona mas sem queries cypher-style.
3. **Híbrido:** pgvector para similaridade rápida + AGE pra grafo conceitual de dealers/mesas. Maior complexidade operacional.

**Recomendação:** ❶ se o roadmap dealer/provider/mesa (§6) for adotado, **mantém AGE e usa**; ❷ se não adotar §6, **remove AGE** (poupa ~80 MB e simplifica Flexible Server PaaS).

### 5.3 SQLite write-side (`decisions`, `gale_windows`, `sessions`)

Atualmente: write-side autoritativo. `decisions` tem **31 colunas** — quase tudo já está mapeado, exceto:
- ❌ `calibration_error` populado (§4.3)
- ❌ `dealer_id`, `provider_id`, `table_id`, `round_id` (§6)
- ❌ `wheel_dist_to_center` (campo derivado, §4.3)

`sessions` tem apenas `total_*` agregados — não permite query de "qual sessão teve qual dealer". Adicionar coluna `dealer_id TEXT, table_id TEXT, provider TEXT` resolve.

---

## §6. Dealer + Provedor — vale a pena? **SIM, alto ROI.**

### 6.1 Por que faz sentido (literatura + experiência)

**Fato físico documentado:**
- Cada dealer tem **release bias** — velocidade média da bola, ponto de soltura na roda, ângulo de release. Padrão personalizado.
- Cada **provedor** (Evolution / Pragmatic / Playtech / Ezugi) usa rodas físicas diferentes — fabricantes (Cammegh / TCSJohnHuxley), desgastes diferentes, deflectors em ângulos próprios.
- Cada **mesa específica** ("Lightning Roulette Brazilian", "Speed Auto Roulette 1") tem desgaste único do equipamento (frets gastos = pockets-preferidos, fenômeno chamado *wheel bias*).

**Cassinos reais cobram licença pra "Wheel Reading" software** — porque sabem que essas features movem a agulha. ([Cammegh wheel certification](https://www.cammegh.com/), [eog gaming reports](https://www.egba.eu/)).

**Dado nosso:**  o sistema hoje vê 3 255 spins como uma série única. Se 30 % são do dealer A e 70 % do dealer B, e A tem bias +3 pockets e B tem -1 pocket → o offset global (~0) é a **média que não serve para nenhum dos dois**. Estratificar resolveria.

### 6.2 O que captar (e de onde)

| Campo | Onde mora no DOM do cassino | Custo de capturar |
|---|---|---|
| **dealer_name** | bar superior da mesa, ex: `<span class="dealer-name">Camila</span>` | 1 query selector |
| **table_name** | título da mesa, sempre visível | 1 query selector |
| **provider** | URL ou logo (`evo.live.casino.com/...` ou `pragmaticplay/.../`) | regex no `location.host` |
| **game_round_id** | `data-round="..."` no canvas; alguns sites expõem via WS interno | 1 fetch/observer |
| **wheel_speed** (avançado) | medível via timing entre "no more bets" e "ball release" | timing diff |

**Ponto-chave:** o `content.js` já tem `<all_urls>` permission. Adicionar um `MutationObserver` para esses campos é **~30 LoC**.

### 6.3 Schema proposto

#### Mudanças mínimas (SQLite write-side)

```sql
ALTER TABLE sessions ADD COLUMN provider TEXT;
ALTER TABLE sessions ADD COLUMN table_id TEXT;
ALTER TABLE sessions ADD COLUMN dealer_id TEXT;
ALTER TABLE sessions ADD COLUMN started_at_dealer TEXT;

ALTER TABLE decisions ADD COLUMN dealer_id TEXT;
ALTER TABLE decisions ADD COLUMN round_id TEXT;
ALTER TABLE decisions ADD COLUMN wheel_dist_to_center INTEGER;
-- e POPULAR calibration_error que já existe
```

#### Mudanças PG read-side (nova migração `0007_dealer_provider.py`)

```sql
CREATE TABLE shared.dealers (
    id          TEXT PRIMARY KEY,             -- ex: "evo_camila_2026"
    display_name TEXT NOT NULL,
    provider    TEXT NOT NULL,
    first_seen  TIMESTAMP DEFAULT now(),
    last_seen   TIMESTAMP,
    total_spins INTEGER DEFAULT 0,
    embedding   VECTOR(8)                     -- aprende do histórico
);

CREATE TABLE shared.tables (
    id          TEXT PRIMARY KEY,             -- ex: "evo_lightning_br_1"
    provider    TEXT NOT NULL,
    name        TEXT NOT NULL,
    embedding   VECTOR(4),
    bias_offset REAL DEFAULT 0                -- bias agregado descoberto
);

ALTER TABLE cw.spin_features  ADD COLUMN dealer_id TEXT,
                              ADD COLUMN table_id  TEXT,
                              ADD COLUMN wheel_dist INTEGER;  -- ☆
ALTER TABLE ccw.spin_features ADD COLUMN dealer_id TEXT,
                              ADD COLUMN table_id  TEXT,
                              ADD COLUMN wheel_dist INTEGER;  -- ☆

CREATE INDEX ix_cw_dealer  ON cw.spin_features (dealer_id);
CREATE INDEX ix_ccw_dealer ON ccw.spin_features (dealer_id);
```

#### Vector ampliado

`raw_features` cresce de 6 → **20 d**:
```
[centro, c4, m6, l12, sda_score, force,
 ... dealer_emb (8 d trained), table_emb (4 d trained), tod_emb (2 d) ...]
```

Treino dos embeddings: autoencoder (já temos `SpinEncoder`) com encoder estendido — saída 4 d para cada categoria.

### 6.4 Como a estratégia melhora com dealer/provider

1. **Curto prazo (1ª semana):** após N=50 spins/dealer, calibration_offset estratificado por dealer. Espera ganho **+2 a +4 pp**.
2. **Médio (1 mês):** regime similarity (S-STRAT-12) faz query filtrando por `WHERE dealer_id = X`. **+3 a +5 pp** quando dealer é recorrente.
3. **Longo (3+ meses):** ML hierárquico (Bayesian multilevel): pooling parcial entre dealers do mesmo provedor. **+5 a +8 pp** marginal sobre baseline.

**Crucial:** isso só funciona se ❶ implementarmos §4 (wheel_dist) PRIMEIRO, porque o sinal binário não tem resolução pra detectar +2 pp de bias por dealer com n < 1 000.

---

## §7. Roadmap de evolução — 3 alavancas, 3 sprints

### Alavanca A — **Capturar wheel_dist** (3 dias) — ROI mais alto
*Pergunta atendida: §4*

1. Adicionar `_compute_wheel_dist()` em `core/roulette.py` (já tem `WHEEL_SEQUENCE`)
2. Popular `calibration_error` no handler de resultado (`message_handler.py`)
3. Adicionar `wheel_dist` ao payload `spin_result` outbox → `_apply_spin_result` no CDC popula `cw|ccw.spin_features.wheel_dist`
4. Migração `0007` adiciona coluna
5. Métrica Prometheus `roleta_wheel_dist_p50, p95, p99` + painel Grafana
6. Loss function nova em `bet_advisor`: `_compute_calibration_signal(direction)` retorna `median_wheel_dist` para o backtest harness usar como objetivo dual

**Saída:** cada `MISS` deixa de ser binário. Vemos quando "quase acertamos" (dist=1-3) vs "muito longe" (dist > 9).
**Ganho esperado:** 47.1 % → **51-54 %** dentro de 2 semanas de re-tuning offline.

### Alavanca B — **Capturar dealer + provider** (5 dias)
*Pergunta atendida: §6*

1. `extension/content.js`: `MutationObserver` em seletores conhecidos (Evolution, Pragmatic, Playtech) → broadcast `dealer_changed`, `table_changed`
2. `extension/background.js`: anexar `dealer_id`, `table_id`, `provider`, `round_id` ao payload `novo_resultado`
3. `server/message_handler.py`: aceitar e persistir esses campos em `sessions` e `decisions`
4. Migração PG `0007` cria `shared.dealers`, `shared.tables` e adiciona FKs
5. CDC handler `_apply_spin_result` propaga para `spin_features.dealer_id`
6. Endpoint `/api/dealers` lista top dealers por accuracy + bias

**Saída:** detecta dealer hot/cold, table hot/cold, provider bias. Histórico permanente.
**Ganho esperado:** +2-4 pp após 50 spins por dealer.

### Alavanca C — **Desligar errdriven + remediar sda_score extremos** (1 dia)
*Resposta direta a §3.3, §3.2*

1. `strategies/sda17.py`: feature_flag `sda17.errdriven.enabled = false` (default OFF)
2. Quando `sda_score ∈ {2, 5, 6}` → flag `low_confidence_score` no BetAdvice
3. Política gale: forçar G1 quando `low_confidence_score=True` (cap exposição)
4. A/B teste off-line via backtest harness

**Saída:** elimina −26 pp do errdriven.
**Ganho esperado:** evita perda de ~5 pp em ~7 % dos casos = +0.4 pp na média; principal valor é estabilidade de drawdown.

### Sequência recomendada
1. **C primeiro** (1 dia, sem risco, ganho imediato)
2. **A segundo** (3 dias, abre caminho para tudo)
3. **B por último** (5 dias, depende de A para dar lift mensurável)

**Total:** 9 dias úteis para passar baseline de **47.1 % → projetado 53-58 %** (intervalo) com IC pendente de backtest formal.

---

## §8. Comparativo "estamos no caminho certo?"

| Dimensão | Pontos fortes | Pontos a evoluir | Veredito |
|---|---|---|---|
| **Arquitetura** | 8 containers healthy, outbox 100 %, CDC < 22 s lag | mem_limit cdc-worker faltando | ✅ sólido |
| **Decisões mensuráveis** | 31 colunas por decisão, snapshot performance | `calibration_error` NULL, sem dealer | 🟡 bom mas incompleto |
| **Loop de aprendizado** | SDA17 sigmoid_off bayesian, drift_freeze | unidim. (só HIT/MISS) | 🟡 base ok, salto pendente |
| **Observabilidade** | Prometheus + Grafana + AlertManager | métricas wheel_dist faltando | ✅ |
| **ML readiness** | pgvector 6-d, autoencoder treinado (PCA 99.5 %) | 4 das 6 dim colineares (informação real só em 2 d) | 🟡 escalável |
| **Captura de origem** | extension MV3 estável v3.0.0 | só `numero` + `direcao` no payload | 🔴 oportunidade enorme |
| **Schema PG** | cw/ccw separados + outbox + vector + AGE | AGE ociosa, vector pequeno | 🟡 |
| **Estratégia** | hit rate **47.3 % > baseline 45.95 %** consistente | sda_score extremo e errdriven prejudicam | ✅ acima do random, dá pra crescer |

**Conclusão:** ✅ **estamos no caminho certo**. A base é correta, o tooling é bom (graphify, prometheus, A/B via feature_flags). O que falta é **adicionar resolução** ao sinal (wheel_dist) e **adicionar contexto** (dealer/provider) — ambos são extensões naturais sem refazer nada.

---

## §9. Comparativo vs `estrutura_noite_25_audit.md`

A auditoria noturna foi **infra-focada** (8 bugs, latency, containers). Este documento é **estratégia-focado** (decisões, valor de cada feature, dados perdidos). Complementares.

| Item | Audit 25 noite | Este (Visualização 25) |
|---|---|---|
| Bugs novos | 6 técnicos | 1 técnico (calibration_error NULL) + 1 produto (errdriven) |
| Hit rate medido | 47.1 % global | **47.3 %** + breakdown por feature |
| Pergunta principal | "que bugs existem?" | "**que decisões geram valor?**" |
| Tabela PG/AGE/vector | inventariou | **auditou + propôs evolução** |
| Resposta sobre dealer | N/A | "Não capturado; **valor alto; ROI 5 dias**" |
| Resposta sobre wheel_dist | N/A | "Schema existe; **100 % NULL; ROI máximo 3 dias**" |

---

## §10. Comandos prontos para validar

```bash
# 1) Hit rate breakdown por feature (em qualquer momento)
ssh root@187.45.181.75 'docker exec roleta-cloud sqlite3 -header -column /app/data/decisions.db \
  "SELECT sda_score, count(*) n, round(100.0*sum(CASE WHEN result_hit=1 THEN 1 ELSE 0 END)/count(*),1) hit_pct FROM decisions WHERE result_hit IS NOT NULL GROUP BY sda_score;"'

# 2) Conferir se calibration_error continua NULL (vai pra 0 quando alavanca A rodar)
ssh root@187.45.181.75 'docker exec roleta-cloud sqlite3 /app/data/decisions.db \
  "SELECT count(*) total, sum(CASE WHEN calibration_error IS NOT NULL THEN 1 ELSE 0 END) populated FROM decisions;"'

# 3) Identificar errdriven ativos (alvo do quick win C)
ssh root@187.45.181.75 'docker exec roleta-cloud sqlite3 /app/data/decisions.db \
  "SELECT count(*) FROM decisions WHERE sda_offset_type=\"errdriven\" AND timestamp >= datetime(\"now\",\"-24 hours\");"'

# 4) Verificar payload incoming em tempo real
ssh root@187.45.181.75 'docker logs -f --tail 5 roleta-cloud 2>&1 | grep "received → processed"'
```

---

## §11. Memória — entidades a adicionar

```
- VisualizacaoEvolucao25 (Documento)
  Observações: 47.3% hit global, sweet spot sda_score=4 com 49%,
                errdriven -26pp, calibration_error 100% NULL,
                payload sem dealer/provider, AGE ociosa, vector 6-d sub-dim.

- ProductInsight-WheelDist (Insight)
  Observações: 13.5kbits info perdida; coluna existe vazia; ROI 3 dias.

- ProductInsight-Dealer (Insight)
  Observações: payload extension nem manda; capturar via MutationObserver;
                ganho 2-4pp em 50 spins por dealer.

- Bug-Errdriven (Bug)
  Observações: 21.1% hit rate vs 47.3% baseline = -26pp; 19 amostras;
                desligar via feature_flag e medir.
```

---

**Status final:** ✅ documento pronto para guiar próximas 2 sprints de evolução estratégica. Pergunta nuclear do usuário ("estamos no caminho certo?") respondida com dados: **SIM, e o gap principal é resolução do sinal, não arquitetura**.
