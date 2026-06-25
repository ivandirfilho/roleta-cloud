# resultados_22_junho — Levantamento das últimas 50 jogadas por sentido + auditoria de arquitetura e desempenho

**Data:** 2026-06-22 21:23 BRT · **Autor:** auditoria por engenharia reversa (DB ao vivo)
**Fonte:** snapshot consistente de `decisions.db` (produção `187.45.181.75`, container `roleta-cloud`),
`sqlite3 .backup` → `dec_snap_22.db` (11,8 MB, **9.471** decisões, 21/jan → 22/jun 21:23).
**Era da estratégia atual (geometria V3 / `regions_v4`):** desde **2026-06-14** (3.096 linhas).

> Método: nada de achismo. Cada número abaixo sai de query SQL sobre o snapshot e cada afirmação
> de comportamento é ancorada no código (`server/message_handler.py`, schema `decisions`).

---

## 0. Sumário executivo (TL;DR)

1. **Correção semântica que muda TUDO (provada 405/405):** a coluna `spin_direction` é a direção do
   **spin-gatilho observado**, não da aposta. A aposta mira o **sentido oposto** e resolve no **próximo
   spin**. Logo: `spin_direction='horario'` ⇒ **aposta = ANTI-HORÁRIO (CCW)**; `spin_direction='anti-horario'`
   ⇒ **aposta = HORÁRIO (CW)**. Qualquer análise que agrupe pela coluna crua inverte o sentido.
2. **O "edge anti-horário de +3090u" é um artefato de UM dia (19/06).** Esse dia tem 1 sessão dominante,
   dealer `unknown` em 302/313 linhas e o número **8 saindo 45×/313 (14,4%, ~12σ)** — impossível numa
   roleta justa. É replay/feed corrompido, **não** edge.
3. **Desempenho real (era `regions_v4` SEM o 19/06): os dois sentidos perdem.**
   ANTI-HORÁRIO 45,7% hr (−2,8% ROI, ~breakeven) · HORÁRIO 41,4% hr (−13,2% ROI). HORÁRIO é o vazamento.
4. **Hoje (22/06):** −81,1u em 2.587u apostados (−3,1% ROI), hr 42,2%. O stop-loss por sessão segura
   cada sessão em ~−40u. ANTI +141,8u vs HORÁRIO −222,9u, mas com **hit-rate idêntica (~42%)** — a
   diferença de PnL é **variância de staking** (Anti-Mart), não edge de acerto.
5. **Forças por dealer:** o pipeline **CAPTURA** (dealer+força+sentido+resultado, ~80% de cobertura
   agora vs 5,7% histórico) mas **NÃO USA** (`SDA_DEALER_OFFSET=0`, `dealer_force_profile` dormente).
   A força média por dealer (~14–20) **não separa** edge; o sinal útil seria dealer×sentido — ignorado.

**Veredito:** a estratégia, hoje, é uma **perdedora de margem pequena** mantida “quase de pé” pela
de-risking (CUT score<4 ×0.10 + stop-loss 1u). O suposto edge anti-horário **não se sustenta** fora do
dia corrompido. A maior alavanca não-explorada é o **gating por dealer×sentido**, cujos dados já existem.

---

## 1. Arquitetura — dados, tecnologia e resultados

### 1.1 Tabela `decisions` (1 linha por spin-gatilho)
Cinco blocos numa única linha — permite engenharia reversa completa de cada jogada:

| Bloco | Colunas | Significado |
|---|---|---|
| Contexto do spin | `spin_number`, `spin_direction`, `spin_force`, `dealer`, `dealer_table`, `provider`, `wheel_model`, `vision_*` | Spin observado + metadados da FOTO/OCR |
| Triple Rate Advisor | `tr_should_bet`, `tr_confidence`, `tr_reason`, `tr_c4_rate`, `tr_m6_rate`, `tr_l12_rate` | Hit-rate rolante (4/6/12) → conselho cauteloso |
| Proposta SDA17 | `sda_should_bet`, `sda_score`, `sda_center`, `sda_centers`, `sda_numbers`, `sda_regions`, `sda_offset(_type)`, `sda_predicted_force` | Geometria `regions_v4`: 3 satélites C1/C2/C3 (offsets KDE), N cobertos |
| Decisão + staking | `final_action`, `action_reason`, `gale_level`, `gale_bet_value`, `gale_window_*` | Ação e **porquê** textual; `gale_bet_value` = **stake REAL** (LEDGER FIX 12/06) |
| Resultado | `result_hit`, `result_actual`, `result_region`, `calibration_error`, `pnl_units` | Acerto/erro, número que resolveu, distância em casas, P&L real |

Tabelas-irmãs: `decision_dna`, `gale_windows`, `window_plays`, `sessions`.

### 1.2 Pipeline de tecnologia (fluxo por spin)
```
spin chega (numero, direcao, force, foto→dealer/wheel via OCR)
      │
      ├─ check_prediction(numero)  → resolve a APOSTA ANTERIOR (last_decision_id):
      │        update_result(result_hit, result_actual=numero, calibration_error, result_region)
      │
      ├─ Triple Rate Advisor  → should_bet / confidence / rates
      ├─ SDA17.analyze        → score, centers[C1,C2,C3], regions_v4, numbers (N≈13–17)
      │
      ├─ INV-3 GLOBAL: SEMPRE indica aposta (exceto 1ª oportunidade do sentido = PULAR;
      │                2ª = fallback N=21). Vetos NÃO suprimem — modulam STAKE:
      │        score<4 → ×0.10 (CUT-POLICY v1) · TR cauteloso → ×0.10 · stop-loss sessão → 1u
      │
      └─ store_prediction(target_direction = OPOSTO do spin) → grava Decision
```

### 1.3 Semântica de resultado — **PROVADA por engenharia reversa**
Código (`message_handler.py:526-527` e `:918-927`): a aposta usa `target_direction` (oposto do spin
observado) e o resultado da linha é gravado quando **o próximo spin chega**. Verificação empírica no
snapshot (linhas id>9000):

- `result_actual[t] == spin_number[t+1]` → **405/405 = 100%** ✅
- direção alterna entre linhas consecutivas → **86%**

⇒ **Cada linha resolve no spin seguinte, na direção oposta ao seu `spin_direction`.** Esta é a base de
toda a re-rotulagem deste relatório.

---

## 2. Últimas 50 jogadas **por sentido da aposta** (isolado)

> Rotulado por **direção apostada** (= oposto de `spin_direction`), que é o que o owner “joga”.
> Janela: hoje 22/06, ~18:16→21:22. `APOSTAR` resolvidas. Breakeven N=17 = **47,2%**.

### 2.1 BET = ANTI-HORÁRIO (CCW)  · *(spin-gatilho = horário)*
```
n=50  hit-rate=32,0%  Δ=−15,2pp  | staked=246u  pnl=−104,6u  ROI=−42,5%  pnl/jogada=−2,09u
  por classe de stake (porque a ação foi modulada):
    stoploss_1u  n=33  hr=33,3%  staked= 33u  pnl=  −6,4u   ← sessão já no stop-loss → 1u
    full_stake   n=14  hr=21,4%  staked=209u  pnl=−101,0u   ← VAZAMENTO: convicção score≥4 falhou
    cut<4 ×0.10  n= 3  hr=66,7%  staked=  4u  pnl=  +2,8u
```
**Leitura:** o sentido normalmente “bom” (anti) **colapsou na última hora**: 14 apostas de convicção a
21,4% derreteram −101u. A de-risking limitou o resto.

### 2.2 BET = HORÁRIO (CW)  · *(spin-gatilho = anti-horário)*
```
n=50  hit-rate=46,0%  Δ=−1,2pp  | staked=235u  pnl=−8,9u  ROI=−3,8%  pnl/jogada=−0,18u
  por classe de stake:
    stoploss_1u  n=31  hr=45,2%  staked= 31u  pnl= −1,0u
    full_stake   n=13  hr=38,5%  staked=193u  pnl=−13,0u
    cut<4 ×0.10  n= 6  hr=66,7%  staked= 11u  pnl= +5,0u
```
**Leitura:** ~breakeven no acerto (46%), praticamente flat no bankroll (−8,9u) — a de-risking fez o
trabalho de conter o sentido historicamente pior.

> Observação de variância: 50 jogadas é janela curta. Estes números são o “agora”, não a tendência —
> ver §5 para a era completa.

### 2.3 Amostra crua (últimas jogadas BET ANTI-HORÁRIO, spin-gatilho=horário) — o colapso da última hora
```
id    hh:mm:ss  sc g stk hit act err dealer  F   classe
9445  21:03:18  5 1  12  Y  19   1  OLIVER  10  full_stake
9447  21:04:56  5 1  13  Y   2   2  OLIVER  18  full_stake
9449  21:06:34  5 1  17  n  19   8  OLIVER  29  full_stake
9453  21:09:46  4 1  17  Y   6   7  OLIVER   6  full_stake
9457  21:12:55  4 1  14  n   9   5  OLIVER  24  full_stake
9459  21:14:31  4 1  16  n  33   6  OLIVER   5  full_stake
9461  21:16:07  4 1  16  n   1   3  OLIVER  17  full_stake
9464  21:17:41  4 1  17  n   5   4  OLIVER  20  full_stake
9466  21:19:22  4 1  17  n   5   4  OLIVER   9  full_stake
9468  21:20:53  4 1  17  n  22   5  OLIVER   8  full_stake
9470  21:22:31  4 1  12  n   7   4  OLIVER  17  full_stake
```
Os 3 primeiros (score 5) acertaram; a partir de 9457 vieram **7 misses seguidos** de convicção (score 4,
14–17u) → −101u. É o que derruba o sentido na janela das últimas 50.

---

## 3. Engenharia reversa — por que ACERTAMOS e por que ERRAMOS

Quatro exemplares reais (linha completa) ilustram cada caminho de decisão:

**(A) FULL-STAKE HIT — id 9467 · BET ANTI · dealer OLIVER**
`score=4 center=32 centers=[32,22,13] regions_v4` → `numbers=[6,7,9,11,13,14,18,22,27,29,30,31,36]`
`stake=13u` → `actual=9 region=C2 err=1 pnl=+23u`.
*Porquê acertou:* o próximo spin (9) caiu no satélite **C2** (centro 22, offset −10), dentro da cobertura.

**(B) FULL-STAKE MISS — id 9468 · BET HORÁRIO · dealer OLIVER**
`score=4` mas `TR c4=0%` (4 últimas falharam) → ainda assim **stake cheio 17u** → `actual=22 miss err=5 pnl=−17u`.
*Porquê errou e por que doeu:* **buraco de política** — CUT-POLICY só corta por `score<4`; um score=4 com
TR sinalizando 0% recente **não** é de-riscado. Convicção “cega” = −17u.

**(C) CUT score<4 MISS — id 9460 · BET ANTI**
`score=3 → ×0.10 stake=2u` → `actual=15 miss err=7 pnl=−2u`. *De-risking funcionou:* erro de 7 casas,
perda contida a 2u.

**(D) NEAR-MISS estrutural — id 9432 · BET ANTI · STOP-LOSS 1u**
`centers=[8,26,25]` mas `numbers` cobre só vizinhança de C2/C3 (26/25); **C1=8 NÃO foi apostado**
(SDA_BET_PAIR=c2c3). `actual=8` (= o centro nominal!) → `err=0` porém **miss**.
*Achado:* sob `bet_pair`, o pocket mais provável (C1) pode ficar **fora** da aposta → existem “misses com
err=0”. Custa acertos.

**Síntese causal:**
- *Acertos* vêm de o próximo spin cair num dos 3 satélites `regions_v4`; o sentido **anti** acerta um
  pouco mais (45,7% era vs 41,4% horário).
- *Erros* concentram-se em **HORÁRIO full-stake** (41,4%) e em **score=4 com TR ruim** não cortado (B), além
  do **C1 fora da cobertura** sob bet_pair (D). Calibração nos misses: só 15–22% são “near” (≤2 casas);
  a maioria erra 3–7 casas (região inteira fora).

---

## 4. O que foi PROPOSTO e NÃO foi alcançado

| Proposta da estratégia | Realidade nos dados | Gap |
|---|---|---|
| “Edge no anti-horário” (CCW +EV) | Era s/ 19/06: ANTI 45,7% (−2,8% ROI) — **abaixo** do breakeven 47,2% | Edge **não comprovado**; é ~breakeven negativo. O +EV vinha do dia corrompido |
| “Horário é −EV, abster/menor stake” | HORÁRIO 41,4% (−13,2% ROI) | ✔ confirmado, mas **ainda se aposta cheio** nele (14 full-stake hoje, −101u) |
| “CUT score<4 protege” | Funciona (cut perde só 2–5u) | ✔; porém **não cobre** score=4 com TR=0% (exemplar B) |
| “Stop-loss segura a sessão” | Cada sessão hoje ~−40u, depois 1u | ✔ por sessão, **mas reseta a cada nova sessão** → bleed recomeça |
| “Forças por dealer” | Capturado ~80%, **não usado** na geometria | Sinal dealer×sentido existe e é ignorado |
| Anti-Martingale agrega ganho | gale quase nunca passa de nível 1 (31/661); gale=2 deu −121u | Staking não entrega edge; PnL+ vem de **variância** |

---

## 5. O artefato de 19/06 e o desempenho REAL da era

**19/06 (BET ANTI full-stake): n=313, hr=74,1%, +3262u — corrompido:**
- 1 sessão domina: `84f121e8` = **222/313**; dealer `unknown` em **302/313**; `vision='none'` em 297.
- Distribuição de `result_actual` impossível: **8→45× (14,4%)**, 12→38× (12,1%) sobre 313 spins
  (esperado ~2,7% cada; 8 está a ~12σ). ⇒ replay/feed travado, **não** roleta real.

**Era `regions_v4` (06-14→22) SEM o 19/06 — o número honesto:**
```
  BET ANTI-HORÁRIO (CCW)   n=348  hr=45,7%  pnl= −171,6u  ROI= −2,8%   (quase breakeven)
  BET HORÁRIO    (CW)      n=372  hr=41,4%  pnl= −870,7u  ROI=−13,2%   (vazamento)
```
**Série temporal full-stake por dia (acha a inversão e o outlier):**
```
dia        ANTI(CCW)  n / hr / pnl        HORÁRIO(CW) n / hr / pnl
06-14      97  55,7%  −68,6u              106 54,7% −147,7u
06-15      34  52,9%  −66,0u               36 50,0% −108,0u
06-17      45  44,4%  +55,0u               46 21,7% −340,0u
06-18      91  35,2% −178,0u               85 41,2%  +22,0u
06-19     313  74,1% +3262,0u  ← ARTEFATO  87 35,6% −154,0u
06-21      10  20,0%  −65,0u               14 28,6%  −59,0u
06-22      71  46,5% +151,0u               85 34,1% −238,0u
```
ANTI é negativo em quase todos os dias reais; HORÁRIO é negativo em **todos**. O verde só aparece no dia
corrompido.

---

## 6. Forças por dealer — está conseguindo analisar?

**Captura: SIM (recente).** Cobertura de `dealer` nas últimas 400 apostas = **79,5%** (vs **5,7%**
all-time). O motor de visão (OCR foto→dealer/mesa, fill-forward 22/06) populou o campo.

**Uso na estratégia: NÃO.** `SDA_DEALER_OFFSET=0` e `dealer_force_profile` dormentes; a geometria
`regions_v4` é idêntica para qualquer dealer. A **força média por dealer não separa edge** (todos ~14–20,
σ≈10–13). O sinal acionável é **dealer×sentido (hit-rate)**, e ele é forte:

```
dealer       BET dir       n   avgF   hr%    vsBE     pnl
JONES        HORÁRIO(CW)  21   14,2  52,4   +5,2    +2,7
JAMES        ANTI(CCW)    43   17,0  46,5   −0,7  +127,2   ← PnL+ por variância de stake (hr<BE)
OLIVER       HORÁRIO(CW)  51   17,6  45,1   −2,1    −3,3
KAIO JORGE   ANTI(CCW)    21   18,3  42,9   −4,4    −3,7
JAMES        HORÁRIO(CW)  48   19,4  37,5   −9,7   −44,1
OLIVER       ANTI(CCW)    45   17,2  35,6  −11,7   −45,7
JONES        ANTI(CCW)    24   16,0  29,2  −18,1    −6,3
KAIO JORGE   HORÁRIO(CW)  20   18,6  20,0  −27,2   −99,9   ← KAIO em horário = ralo
```
**Conclusões:** (1) há heterogeneidade dealer×sentido grande (KAIO horário 20% vs JONES horário 52%);
(2) nenhum par cruza o breakeven com folga e n robusto — é cedo (dados só dos últimos ~2 dias);
(3) **a maior alavanca não-explorada** é ligar um gate dealer×sentido (n≥30) que suspenda full-stake
onde o par é historicamente fraco. Hoje a estratégia é cega a isso.

---

## 7. Desempenho atual — veredito

**Hoje 22/06 (bankroll real, todas as jogadas resolvidas):**
```
TOTAL: n=391  hr=42,2%  staked=2.587u  pnl=−81,1u  ROI=−3,1%
   BET ANTI-HORÁRIO  n=189  hr=42,3%  pnl=+141,8u
   BET HORÁRIO       n=202  hr=42,1%  pnl=−222,9u     (hr idêntica → divergência = staking/variância)
sessões: a maioria ~−40u e batendo stop-loss (SL 23–53 jogadas/sessão); 2 sessões verdes (+66,7 / +2,3)
```

**Quadro geral:** estratégia **levemente negativa**, sobrevivendo pela de-risking. Não há edge robusto
acima de breakeven em nenhum sentido quando se remove o dia corrompido. HORÁRIO é o vazamento crônico;
ANTI é ~breakeven. A variância de staking (Anti-Mart) ocasionalmente pinta PnL positivo sem hit-rate
correspondente — é ruído, não vantagem.

---

## 8. Recomendações (priorizadas por alavancagem)

1. **Cortar full-stake em HORÁRIO (CW):** −13,2% ROI consistente. Aplicar `×0.10`/abster por padrão no
   sentido CW até que um gate prove o contrário. (maior ganho imediato)
2. **Fechar o buraco do exemplar B:** estender CUT-POLICY para `score=4 AND tr_c4_rate==0` (ou TR
   decrescente) → de-riscar convicção contradita pelo advisor.
3. **Ativar gate dealer×sentido (dados já existem, ~80%):** suspender full-stake em pares fracos
   (ex.: KAIO horário). Começar em sombra/telemetria até n≥30 por par.
4. **Stop-loss persistente entre sessões** (ou por dealer/turno) — hoje reseta e o bleed recomeça a cada
   reconexão.
5. **Quarentenar 19/06** de qualquer backtest/treino — contamina médias (e a memória “edge anti”).
6. **Revisar `SDA_BET_PAIR=c2c3`** que tira C1 (centro mais provável) da cobertura → misses com err=0.

---

### Apêndice — reprodutibilidade
- Snapshot: `ssh root@187.45.181.75 'sqlite3 …/decisions.db ".backup /tmp/dec_snap_22.db"'` → `scp`.
- Scripts: `analise_22.py` (50/sentido cru), `analise_22c.py` (re-rotulado por aposta + prova semântica),
  `analise_22d.py` (artefato 19/06, era sem outlier, hoje, gale) — em
  `~/.copilot/session-state/…/files/`.
- Breakeven N=17 = 17/36 = 47,22%. PnL = `pnl_units` (stake real pós-modulação, LEDGER FIX 12/06).
