# 📉 Resultados 18/06/2026 — Auditoria de produção da estratégia **force17** (17#) ao vivo

> **Objetivo:** analisar, por engenharia reversa das decisões **reais de produção**, o desempenho da
> estratégia **desenvolvida e aplicada hoje** — a migração `c2c3 (14#)` → **`force17` (17#)** — e
> explicar o resultado financeiro do dia, suas causas e o que fazer a seguir.
>
> **Fonte da verdade:** `decisions.db` do container de produção (`187.45.181.75`,
> `/app/data/decisions.db`), lido via `docker exec sqlite3 -json` (read-only, SSH).
> **Janela:** `timestamp LIKE '2026-06-18%'` (UTC) → `00:00:32 → 23:47:17 UTC` (última jogada ≈
> **20:47 BRT**). **507 decisões** persistidas, ids `7449→7955`.
> **Stack MCP usada:** `sequential-thinking` · `memory` · `graphify` (grafo local do projeto) ·
> `filesystem` · `brave-search`. **Data:** 18/06/2026.

---

## 1. Veredito

🔴 **Dia financeiramente NEGATIVO: PnL `−186,07u`, ROI `−6,55%`** (sobre 2.841u apostados; 441 apostas
resolvidas; hit-rate 39,46% vs breakeven médio `N/36 = 41,61%` → **edge agregado −2,15pp**).

🎯 **Mas a estratégia não está "quebrada" — ela foi mal-gateada.** A perda do dia é **inteiramente**
atribuível a **apostar com convicção no sentido HORÁRIO**, que é estruturalmente **−EV** (já
documentado em `resultados_15_junho.md`). O bolsão **+EV** da estratégia — **anti-horário com
convicção** — **funcionou como projetado: ROI `+2,77%` (`+34u`)**, batendo o edge histórico (~+2,7%).

> **Resumo em uma linha:** *a geometria force17 está correta e a metade boa (anti-horário) deu lucro;
> o dia foi para o negativo porque o gating de stake é **simétrico** e armou apostas cheias no sentido
> horário −EV, que sozinho perdeu `−202u`.*

---

## 2. Estratégia desenvolvida e aplicada (o que está no ar)

Migração documentada em `Manutenabilidade_iso.md` §394–493 (ADENDO + "F. Atualização 18/06 tarde/noite"):

| Componente | Implementação | Papel |
|---|---|---|
| Geometria **force17** (17#) | `C2(±3,7) ∪ C3(±2,5) ∪ C1=ForceLast(±2,5)` | aposta = união real de 3 regiões, **isolada por sentido** |
| `force_select()` · `coverage3()` · `force_last_center()` | `strategies/c_selection.py` | C1 = último número que saiu naquele sentido (ForceLast) |
| Modo `force17` | `app_config/settings.py` (`SDA_BET_PAIR`) | enum + dispatch `_engine_apply_selection` |
| Não-vazio | `_ensure_nonempty_coverage()` (`server/message_handler.py`) | fix B1 (evita cobertura vazia) |
| PnL/região | `server/websocket.py:_pnl_snapshot`, `state/game.py:_attribute_hit_region` | `pnl_units` e `result_region` (C1/C2/C3/miss) por decisão |

**Ambiente de produção confirmado por SSH (18/06):** `SDA_BET_PAIR=force17`,
**`SDA_FORCE17_EXACT=0`**, `SDA_STAKING_MODE=block_gale`, **`GALE_CAP=1`** (sem escalada),
métrica `roleta_force17_active=1.0`.

> A geometria é **stateless/determinística**. A aposta paga por número vencedor `35:1 (+ficha) = 36×`
> → **`pnl_hit = stake·(36−N)/N`, `pnl_miss = −stake`** (validado byte-a-byte: id 7953, N=14, stake=1,
> hit → `1·(36−14)/14 = +1,571u` ✓). Breakeven por jogada = **`N/36`** (14# = 38,9%; 17# = 47,2%).
> O **brave-search** confirma o axioma: house edge europeu **2,7% fixo**, *"no betting system changes
> the expected value"* — nenhuma geometria vence a margem; o que decide é **hit-rate × gate de sentido**.

---

## 3. Metodologia

Para cada decisão foram lidos `spin_direction`, `sda_centers` (`[C1,C2,C3]`), `sda_numbers` (cobertura),
`sda_score`, `final_action`, `gale_level`, `gale_bet_value` (stake total em unidades), `result_actual`,
`result_hit`, `result_region`, **`pnl_units`** e `session_id`. As 507 linhas foram exportadas em JSON e
processadas localmente (Python). **Convenção de stake** (inferida e validada do `pnl`):

- **CONVICÇÃO** = `gale_bet_value ≈ N` → **1u por número** (aposta cheia; disparada por `score ≥ 4`).
- **SIMBÓLICA** = `gale_bet_value ∈ {1,2}` → **1u total** (jogada sob veto; INV-3 mantém a indicação).

**Saneamento:** 25 decisões `N=0` são **PULAR/calibração** (`result_hit=NULL`, `pnl=NULL`, fora do
cálculo); 22 resíduos `N=21` (regime antigo) **sem `pnl`**; o núcleo analisado = **441 apostas force17
(N 12–17) resolvidas com `pnl`**.

---

## 4. Resultado global (441 apostas resolvidas)

| Métrica | Valor |
|---|---|
| Hit-rate | **39,46%** (174/441) |
| Breakeven médio (`meanN/36`, meanN≈15,0) | 41,61% |
| Edge | **−2,15pp** |
| Stake total apostado | 2.841u |
| **PnL** | **−186,07u** |
| **ROI** | **−6,55%** |
| PnL médio por aposta | −0,42u |
| Equity (cronológico) | pico **+137u** → fundo **−200u** · **maxDD −337u** |

> Alta variância (swing de +137 a −200). Com `GALE_CAP=1` não há ruína por gale — o resultado é
> puramente hit-rate × gate × stake.

---

## 5. 🔑 Achado central — assimetria de sentido amplificada pelo stake

A perda **não está distribuída**: ela vive no quadrante **horário × convicção**.

### 5.1 Por sentido do giro

| Sentido | n | hit% | breakeven | edge | PnL | ROI |
|---|--:|--:|--:|--:|--:|--:|
| **Anti-horário (CCW)** | 219 | 38,81% | 41,59% | −2,78pp | **+8,56u** | **+0,62%** |
| **Horário (CW)** | 222 | 40,09% | 41,63% | −1,54pp | **−194,64u** | **−13,28%** |

### 5.2 Matriz **sentido × classe de stake** (o diagnóstico)

| Sentido | Classe | n | hit% | edge vs N/36 | PnL | ROI |
|---|---|--:|--:|--:|--:|--:|
| **Anti-horário** | **CONVICÇÃO** (1u/nº) | 84 | **41,67%** | **+1,12pp** | **+34,00u** | **+2,77%** ✅ |
| Anti-horário | Simbólica (1u) | 135 | 37,04% | — | −25,44u | −17,07% |
| **Horário** | **CONVICÇÃO** (1u/nº) | 90 | **34,44%** | **−6,23pp** | **−202,00u** | **−15,33%** 🔴 |
| Horário | Simbólica (1u) | 132 | 43,94% | — | +7,36u | +4,98% |

> **Leitura:** as **90 apostas de convicção no horário perderam −202u** — *mais do que toda a perda do
> dia*. As **84 de convicção no anti-horário renderam +34u (+2,77% ROI, +1,12pp acima do breakeven)** —
> exatamente o edge que o estudo histórico (`resultados_15_junho.md` §28-29) prometeu. As jogadas
> simbólicas (1u) são quase neutras em valor absoluto (stake baixo). **O defeito é o gating de stake
> ser simétrico:** `score ≥ 4` libera aposta cheia **sem olhar o sentido**, armando convicção no lado
> −EV.

### 5.3 ROI por tamanho de cobertura N (apostas de convicção)

| N | n | hit% | ROI | PnL |
|--:|--:|--:|--:|--:|
| 12 | 22 | 22,7% | −31,82% | −84u |
| 13 | 7 | 57,1% | +58,24% | +53u *(ruído, n pequeno)* |
| **14** | 83 | 39,8% | **+2,24%** | +26u |
| 15 | 8 | 25,0% | −40,00% | −48u |
| 16 | 11 | 27,3% | −38,64% | −68u |
| **17** | 43 | 44,2% | −6,43% | −47u |

> Os **N intermediários** (12/15/16, gerados por sobreposição assimétrica entre centros) concentram
> ROI −32 a −40%, porém com amostra pequena. Os dois tamanhos confiáveis: **N=14 lucrativo (+2,24%)**,
> **N=17 levemente negativo (−6,43%)** na janela.

---

## 6. What-if — quanto custou ignorar o gate de sentido

Mantendo **tudo** igual, mexendo **só** no quadrante horário×convicção:

| Cenário | PnL do dia | Δ vs real |
|---|--:|--:|
| **Real (produção 18/06)** | **−186,07u** | — |
| **(A)** Abster horário-convicção (PULAR) | **+15,93u** | **+202,00u** |
| **(B)** Horário-convicção → 1u simbólico | **+2,39u** | **+188,46u** |

> Aplicar o gate de sentido — **já prescrito** em `resultados_15_junho.md` ("apostar no anti,
> pular/stake-mínimo no horário") — teria transformado um dia de **−186u** em **+2 a +16u**. A parte
> +EV operou perfeitamente; **a correção é operacional (gating), não geométrica.**

---

## 7. Conformidade estrutural (o código rodou conforme o design)

| Invariante | Observado | Status |
|---|---|:--:|
| **INV-3** (sempre indica; PULAR só na calibração) | 482× APOSTAR · 25× PULAR (todos `N=0`, `pnl=NULL`) | ✅ |
| **GALE_CAP=1** (sem escalada) | `gale_level` = 1 em 507/507 | ✅ |
| **force17 ativo** (cobertura 17# união) | N∈{12..17} em 460 apostas; `sda_offset_type=regions_v4` (458) | ✅ |
| **PnL fiel** (`stake·(36−N)/N`) | validado byte-a-byte | ✅ |
| Regime antigo residual | 22× `N=21` (sem `pnl`, início do dia) | ⚠️ resquício |

> `dealer` = `unknown` em 507/507 (provider não populou o campo) → `dealer_offset` (SP-15) segue
> **dormente**, como esperado.

---

## 8. Sessões (dealers) e timing intra-sessão

**18 sessões** (blocos de `session_id` = trocas de dealer/reset). Destaques:

| | Sessão | ids | n | hit% | PnL |
|---|---|---|--:|--:|--:|
| 🟢 | S4 `28491d11` | 7545–7606 | 57 | 45,6% | **+147,29u** |
| 🟢 | S5 `565acbfc` | 7607–7616 | 5 | 80,0% | +74,00u |
| 🟢 | S13 `5df6bf00` | 7737–7775 | 34 | 38,2% | +20,00u |
| 🔴 | S16 `10d7b35d` | 7868–7920 | 48 | 41,7% | −47,30u |
| 🔴 | S15 `544cd430` | 7855–7867 | 8 | 0,0% | −46,00u |
| 🔴 | S3 `0e9f0232` | 7505–7544 | 35 | 34,3% | −41,29u |

**Curva intra-sessão** (índice da jogada dentro da sessão):

| Janela | n | hit% | ROI |
|---|--:|--:|--:|
| jogadas 01–05 (cold-start) | 80 | 37,5% | **−12,14%** |
| 06–10 | 70 | 38,6% | +7,48% |
| 11–20 | 110 | 40,0% | +1,98% |
| 21–40 | 122 | 38,5% | −7,65% |
| 41+ (cauda longa) | 59 | 44,1% | **−21,15%** |

> Consistente com as memórias: **cold-start ruim** (01–05) e **degradação na cauda** (41+). O miolo
> 06–20 é o terreno mais saudável.

---

## 9. Atribuição de região (Glass Box)

| Região | nº de greens | Leitura |
|---|--:|---|
| **miss** | 267 | 60,5% das resolvidas |
| **C2** | 92 | maior contribuidor (raio ±3, o mais largo) |
| **C3** | 65 | âncora fixa |
| **C1 = ForceLast** | 17 | menor captura (raio ±2, 1 número de origem) |

> C2 domina os acertos (cobertura mais ampla); C1=ForceLast contribui pouco — coerente com as memórias
> ("C1=ForceLast reduz variância, não é o driver do edge").

---

## 10. Recomendações (priorizadas)

1. 🥇 **Gating ASSIMÉTRICO por sentido (alto impacto, baixo risco).** Liberar **convicção (1u/número)
   apenas no anti-horário**; no **horário**, forçar **stake simbólico 1u** ou **PULAR**. É a tradução
   em código do gate já validado. *What-if: +188 a +202u no dia.* Local provável:
   `server/message_handler.py` (bloco INV-3/stake) + `app_config/settings.py` (flag, ex.
   `SDA_DIR_GATE`, default opt-in).
2. 🥈 **Conter os N intermediários (12/15/16).** Avaliar normalizar a união (offsets) ou tratar
   coberturas `N<14` como sinal de baixa convicção (stake reduzido) — concentraram ROI −32 a −40%.
3. 🥉 **Disciplina de sessão.** Cap ~40 jogadas/sessão e/ou stop-loss por sessão (degradação clara em
   41+, ROI −21%).
4. 🔭 **Telemetria.** Persistir `cs_chosen`/`cs_rule`/stake-class por decisão no `decisions.db` →
   auditoria futura bit-exata e dashboards de gate (hoje a classe de stake é **inferida** do `pnl`).
5. 🧹 Eliminar o resquício `N=21` (regime antigo) do caminho de produção.

---

## 11. Amostra — últimas 10 jogadas resolvidas (engenharia reversa)

| id | sentido | centros [C1,C2,C3] | N | stake | saiu | hit | região | pnl |
|---:|---|---|--:|--:|--:|:--:|:--:|--:|
| 7945 | anti | [34, 26, 22] | 17 | 1 | 35 | ✅ | C2 | +1,118 |
| 7946 | horário | [14, 32, 17] | 13 | 1 | 15 | ✅ | C2 | +1,769 |
| 7947 | anti | [18, 0, 34] | 17 | 1 | 1 | ❌ | miss | −1,000 |
| 7948 | horário | [34, 22, 15] | 13 | 1 | 31 | ✅ | C2 | +1,769 |
| 7949 | anti | [13, 5, 21] | 17 | 1 | 33 | ✅ | C2 | +1,118 |
| 7950 | horário | [10, 27, 29] | 13 | 1 | 6 | ✅ | C2 | +1,769 |
| 7951 | anti | [2, 7, 8] | 17 | 1 | 30 | ✅ | C3 | +1,118 |
| 7952 | horário | [32, 10, 7] | 12 | 1 | 30 | ✅ | C2 | +2,000 |
| 7953 | anti | [26, 24, 2] | 14 | 1 | 1 | ✅ | C2 | +1,571 |
| 7954 | horário | [5, 27, 12] | 17 | 1 | 36 | ✅ | C2 | +1,118 |

> Em cada linha: `sda_numbers` salvo == `cov(C1=ForceLast, C2, C3)`, `result_hit == saiu ∈ sda_numbers`,
> `pnl == stake·(36−N)/N` no green / `−stake` no red. **Fluxo íntegro jogada a jogada.**

---

# 🐛 PARTE II — Auditoria do fluxo de dados Estratégia → Front (bugs pós-refatoração force17)

> **Motivação (relato do operador):** ao sugerir as 3 regiões (C1/C2/C3 = force17/17#), a mensagem
> valida a sugestão anterior (red/green) e envia ao front da **escuta** (2 mostruários: aberto e
> minimizado) e ao **Glass Box**. **Sintoma:** os números exibidos **não correspondem à sugestão** —
> aparecem como **"3 regiões · 21 números"** (a geometria ANTIGA de 21#). Esta parte rastreia o
> contrato com o front, localiza os bugs e aponta a origem na refatoração.

## 12. O contrato Estratégia → Front (2 canais)

`server/message_handler.py:handle_new_result()` emite **dois** payloads por jogada:

| Canal | Onde | Destino | Campos da sugestão |
|---|---|---|---|
| `type:"sugestao"` | `message_handler.py:997-1037` (`websocket.send`) | **Escuta** (extensão) | `data.numeros`, `data.centros`, `data.centro`, `data.regiao`, `data.force17{coverage_n,regioes,dir_bias}` |
| `type:"trace"` (+ `state_sync` heartbeat ~1s) | `message_handler.py:1041-1084` (`broadcast`) | **Glass Box** | `result.numeros`, `result.centros`, `force17`, `regioes`, `ultimo_acerto` |

Ambos derivam de `final_numbers`/`final_centers` (`message_handler.py:649-652`). A telemetria `force17`/
`regioes` vem de `_engine_overlay_fields()` (`message_handler.py:257-275`) e
`game_state.engine_overlay_fields()` (`state/game.py:930-990`), ambas alimentadas por
`last_force17_meta`. **Fluxo da escuta:** `extension/background.js:461-475` (`onmessage`) →
`sendSuggestionToContentScript()` (`background.js:617-644`) → `content.js:750-756` (`updateOverlay`) →
`buildForce17HTML()` (`content.js:29-52`).

## 13. 🥇 BUG #1 (RAIZ) — o fallback de calibração emite **21#** em produção

**Local:** `server/message_handler.py:700-718` (bloco *Fallback early-session* da calibração).

```python
# message_handler.py:701-709
# force17-exato: o fallback de calibração também respeita "sempre 17" (raio 8 = 17#);
# senão mantém o histórico N=21 (raio 10).
_fb_radius = 8 if (bet_pair_mode() == "force17" and force17_exact_enabled()) else 10
fallback_nums = sorted(self.strategy.get_neighbors(center, _fb_radius, roulette.WHEEL_SEQUENCE))
...
final_numbers = list(fallback_nums)   # 21 números → vai para os DOIS canais (sugestao + trace)
```

`get_neighbors(center, R)` devolve `2R+1` números → **R=10 ⇒ 21#**, **R=8 ⇒ 17#**.

**Por que dispara 21# em produção:** o raio só vira 8 (17#) se `force17_exact_enabled()` for `True`.
Mas o ambiente real (confirmado por SSH) roda **`SDA_FORCE17_EXACT=0`** com `SDA_BET_PAIR=force17`
→ cai no `else` → **raio 10 → 21 números**. A flag `force17_exact` governa **a aposta NORMAL**
(forçar a união a exatamente 17 vs. união real ~15 — `settings.py:158-165`); ela foi **reutilizada
indevidamente** para também decidir o raio do **fallback**, acoplando duas decisões independentes.

**Evidência ao vivo (produção, 18/06):**

```
SDA_BET_PAIR=force17 · SDA_FORCE17_EXACT=0
24 decisões hoje com N=21, todas: APOSTAR · "Calibração (1 força no sentido) → N=21 G1"
```

São os 24 (≈22 vistos na §7) registros `N=21` do dia — **não** são "regime antigo": são o
**fallback de calibração de hoje** emitindo a geometria de 21#. Ocorrem na 2ª jogada de cada sentido
após cada reset/troca de dealer (18 sessões → recorrente, o operador vê repetidamente).

### 13.1 Origem na refatoração (git)

| Commit (18/06) | Efeito |
|---|---|
| **`b57b62e`** *"feat(force17): SDA_FORCE17_EXACT … (default **ON**)"* | Introduziu a condição `force17_exact_enabled()` no raio do fallback. Com default **ON**, o fallback usava raio 8 (17#) — **sem bug**. |
| **`0d3c47e`** *"fix(force17): default UNIAO ~15 (SDA_FORCE17_EXACT=0) — realinha ao estudo"* | Mudou o default para **OFF** (correto para a aposta normal: união ~15 baixa o breakeven). **Dano colateral:** por acoplamento, o fallback **regrediu para raio 10 (21#)**. |

> **Diagnóstico:** o `0d3c47e` consertou a aposta normal mas **reabriu** o 21# no fallback, porque a
> linha 705 mistura "forçar 17 na aposta normal" com "raio do fallback de calibração".

### 13.2 Correção recomendada (cirúrgica, baixo risco)

```python
# message_handler.py:705 — desacoplar do force17_exact (que rege a aposta normal, não o fallback)
- _fb_radius = 8 if (bet_pair_mode() == "force17" and force17_exact_enabled()) else 10
+ _fb_radius = 8 if bet_pair_mode() == "force17" else 10
```

Assim, com `SDA_BET_PAIR=force17`, o fallback passa a emitir **17#** sempre, independentemente de
`force17_exact` (que continua OFF para a aposta normal usar união ~15, como o estudo pede).

### 13.3 Por que o CI não pegou (testes legados mascaram a regressão)

A suíte está **verde**, mas isso **esconde** o BUG #1: os testes que cobrem o **fallback de
calibração** são de **12/06 (pré-force17)** e ainda **afirmam N=21**, nunca foram realinhados ao
force17:

| Teste | Asserção | Estado |
|---|---|---|
| `tests/test_b1_b2_b5_12_06.py:121,215` | `get_neighbors(c1, 10)` → `# N=21`; *"fallback N=21 sob a flag"* | legado — **espera 21#** |
| `tests/test_audit_cadence_12_06.py:66` | *"PULAR → **N=21** (calibração 2) → SDA pleno"* | legado — **espera 21#** |
| `tests/test_wiring_c_gale.py:260` | premissa *"fallback de calibração **N=21** raio 10"* | legado — **assume 21#** |

Em contraste, a **aposta normal** tem testes force17-aware **corretos**
(`test_wiring_c_gale.py:157-174`: `test_force17_exact_on_gives_exactly_17` e
`test_force17_exact_off_keeps_union` → união ≤16). **Por isso só o fallback regrediu sem alarme:**
o caminho normal é testado para 17#, o caminho do fallback continua "validado" para 21#. **Recomendação
adicional:** atualizar os testes do fallback para esperar **17#** quando `bet_pair_mode()=="force17"`
e adicionar um teste de regressão explícito do par `SDA_BET_PAIR=force17 + SDA_FORCE17_EXACT=0`.

## 14. 🥈 BUG #2 — Glass Box exibe números **stale** (dessincronizados das regiões)

**Local:** `frontend/app.js:399-423` (`updateForce17`) + `app.js:124-152` (`handleStateSync`).

```javascript
// app.js:414 — números vêm do ESTADO do último trace, não da sugestão corrente
const nums = (state.lastResult && state.lastResult.numeros) || [];
```

`state.lastResult` só é atualizado em `handleTrace()` (`app.js:211`). O heartbeat
`handleStateSync()` (a cada ~1s) **re-renderiza as 3 regiões** com dados frescos
(`app.js:138 → updateForce17(data.force17, data.regioes)`) **mas não atualiza** `state.lastResult`
→ os **centros mudam** enquanto os **números embaixo permanecem do spin anterior**. O veredito
red/green (`updateVerdict`, `app.js:383-395`, fonte `ultimo_acerto`) está **correto**.

**Correção recomendada:** unificar a fonte — emitir os números dentro do meta `force17` e lê-los lá:

```javascript
// app.js:414
- const nums = (state.lastResult && state.lastResult.numeros) || [];
+ const nums = (f17 && f17.numeros) || (state.lastResult && state.lastResult.numeros) || [];
```

acrescentando `"numeros": f17.get("numeros", [])` em `engine_overlay_fields()` (`state/game.py:982`).

## 15. 🥉 BUG #3 — Escuta: "3 regiões" hardcoded + cobertura do fallback

**Local:** `extension/content.js:29-52` (`buildForce17HTML`).

```javascript
const coverageN = f17.coverage_n || numeros.length;            // content.js:33
const header = `... 🎯 3 regiões · ${coverageN} números ...`;  // content.js:47-48  ("3 regiões" fixo)
```

No fallback (BUG #1), o servidor zera `last_force17_meta = None` (`message_handler.py:724`) →
`force17`/`regioes` **não são emitidos** → na extensão `f17 = {}`, `regioes = []`. Então:
`coverageN = numeros.length = 21` e o header imprime literalmente **"🎯 3 regiões · 21 números"** —
**a manifestação exata do relato**, mas **sem** os 3 centros (lista de regiões vazia). Soma-se a
inconsistência do servidor: no fallback `final_centers = [center]` (1 região), não 3.

**Correção recomendada:** (a) header derivar de `regioes.length` (não hardcodar "3 regiões") e tratar
o estado de calibração; (b) idealmente, fazer o fallback emitir 3 regiões coerentes (melhoria maior).
Resolver o **BUG #1** já elimina o "21" do header; o BUG #3 é o acabamento cosmético/contrato.

## 16. Resumo da auditoria de bugs

| # | Sev. | Local | Causa | Efeito no front | Correção |
|---|:--:|---|---|---|---|
| **1** | 🔴 ALTA | `message_handler.py:705` | raio do fallback acoplado a `force17_exact` (OFF em prod) | **21# reais** nos 2 canais (24×/dia) | desacoplar: `8 if bet_pair_mode()=="force17"` |
| **2** | 🟠 MÉDIA | `frontend/app.js:414` | `updateForce17` lê `state.lastResult.numeros` (stale) | números ≠ regiões no Glass Box (heartbeat) | ler `f17.numeros`; emitir `numeros` no meta |
| **3** | 🟡 BAIXA | `extension/content.js:47` | "3 regiões" hardcoded + `coverageN=len` | header "3 regiões · 21 números" no fallback | derivar de `regioes.length` |

**Veredito:** o relato do operador procede e tem **causa-raiz única e identificável** (BUG #1), nascida
do par de commits `b57b62e`→`0d3c47e` (18/06). A geometria force17 das **apostas normais está correta**
(17#/união ~15, §7); o desvio dos "21 números 3 regiões" vem **exclusivamente do fallback de
calibração** + amplificação cosmética no front. **Nenhuma das correções altera a lógica de aposta** —
apenas alinham a cobertura do fallback e a renderização ao contrato force17.

> ✅ **Patches APLICADOS e validados** (ver PARTE III). Estado das correções: BUG #1/#2/#3 corrigidos,
> teste de regressão adicionado, suíte verde (568 passed). Origem e diffs detalhados na PARTE III.

---

# 🛠️ PARTE III — Implementação, auditoria profunda pós-fix e scorecard ISO

> Estruturada segundo `Manutenabilidade_iso.md` (ADENDO datado → mudanças por componente → auditoria com
> servidor real → scorecard ISO/25010 → veredito). **Saga:** correção dos 3 bugs da PARTE II + auditoria
> profunda de TODO o fluxo da estratégia force17 em busca de bugs remanescentes.

## 17. Correções implementadas (force17 — fluxo front)

| Bug | Componente · arquivo:linha | Mudança | Risco |
|---|---|---|---|
| **#1** | `server/message_handler.py:705` | `_fb_radius = 8 if bet_pair_mode()=="force17" else 10` — **desacopla** o raio do fallback de `force17_exact` (que rege só a aposta normal). | Baixo — só afeta o fallback de calibração em modo force17. |
| **#2** | `server/message_handler.py:141,271` · `state/game.py:986` · `frontend/app.js:414` | A cobertura viaja no **meta `force17.numeros`**; o Glass Box lê `f17.numeros` (mesma fonte das regiões), com fallback a `state.lastResult`. | Baixo — aditivo; extensão/Glass Box ignoram campos extras. |
| **#3** | `extension/content.js:47` | Header deriva de `regioes.length` (não hardcode "3"); fallback rotula "calibração". | Nenhum — apenas rótulo. |
| **Teste** | `tests/test_audit_cadence_12_06.py` (`TestFallbackForce17Radius`) | Regressão: `force17`→fallback **17#**; `c2c3`→**21#** (controle). Fecha o gap que mascarava o BUG #1. | — |

**Diff-chave (BUG #1):**
```diff
- _fb_radius = 8 if (bet_pair_mode() == "force17" and force17_exact_enabled()) else 10
+ _fb_radius = 8 if bet_pair_mode() == "force17" else 10
```

## 18. Verificação (pré-deploy)

| Gate | Resultado |
|---|---|
| Suíte completa `pytest -q` | **568 passed · 9 skipped · 1 xfailed** (inclui +2 regressão force17) |
| Regressão BUG #1 | `test_force17_fallback_is_17_not_21` ✅ · `test_non_force17_fallback_keeps_21` ✅ |
| Sintaxe JS | `node --check frontend/app.js` ✅ · `extension/content.js` ✅ |
| Lint | erros `ruff` remanescentes (`game.py:653`, `message_handler.py:415`) são **pré-existentes**, fora das linhas alteradas |

## 19. 🔬 Auditoria profunda pós-fix (todo o fluxo da estratégia)

**Metodologia:** 2 subagents `explore` independentes — (A) fluxo server-side
(`extractor → message_handler → c_selection/sda17 → store_prediction → _engine_resolve/_attribute_hit_region
→ persist`) e (B) staking/INV-3/Block-Gale + contratos front — seguidos de **validação manual cética**
(os agentes Haiku produzem falsos positivos com "impactos" fabricados). ~21 candidatos levantados.

**Veredito: 0 bugs novos acionáveis.** Todos os candidatos relevantes foram refutados por leitura direta:

| Candidato (agente) | Local | Por que NÃO é bug |
|---|---|---|
| `target_direction` ausente no front (ALTA) | `app.js` block_gale | **Presente** no `state_sync` (`websocket.py:401`); o agente só inspecionou o `trace`. O `state_sync` é a fonte canônica (1 Hz). |
| `gale_bet_value` errado em PULAR (ALTA) | `message_handler.py:867` | **By-design** (LEDGER FIX 12/06): só importa em APOSTAR; PULAR tem `pnl=NULL`. |
| off-by-one store/seleção (ALTA) | `message_handler.py` | Ordem real: `_engine_apply_selection`@641 **antes** de `store_prediction`@681 → predição e atribuição usam os MESMOS números (pós-seleção). |
| `_attribute_hit_region`→"C1" (MÉDIA) | `game.py:559` | `_signed` nunca é None p/ nº válidos (0–36); `if not centers: return`@518 protege. Defensivo inalcançável. |
| `_ensure_nonempty_coverage` `else:return` (ALTA) | `message_handler.py:168` | **Intencional**: preserva o `PULAR` da 1ª jogada (preencher quebraria a calibração — confirmado: hoje `N=0` só em PULAR). |
| vazamento c_attr / hit overlap / pnl overlap | `game.py` | `pnl` sobre união real é correto (1 ficha/nº distinto); atribuição por centro mais próximo já foi corrigida em 13/06; isolamento por sentido = `BUG-AUDIT-006 FIX`. |

> **Conclusão:** após as 3 correções, o fluxo de dados da estratégia force17 está **íntegro**. O sistema é
> single-threaded async (sem as "race conditions" especuladas). Os fixes **não alteram a lógica de aposta**
> (geometria, EV, gating) — apenas alinham a cobertura do fallback e a renderização ao contrato force17.

## 20. Scorecard ISO/IEC 25010 — delta (vs PARTE II, pré-fix)

| # | Subcaracterística | Antes | Depois | Justificativa |
|---|---|:--:|:--:|---|
| 1 | **Correção funcional** (fallback) | ❌ 21# em prod (EXACT=0) | ✅ 17# em force17 | Desacoplamento da flag `force17_exact`. |
| 2 | **Consistência** (front↔estratégia) | ⚠️ números ≠ regiões / "3 regiões·21" | ✅ mesma fonte (`force17.numeros`) | Cobertura no meta; header dinâmico. |
| 3 | **Testabilidade** | ❌ fallback force17 sem teste | ✅ regressão dedicada | `TestFallbackForce17Radius` fecha o gap que mascarava o bug. |
| 4 | **Analisabilidade** | ⚠️ origem do 21# difusa | ✅ rastreada (`b57b62e`→`0d3c47e`) | Causa documentada por git-blame. |
| 5 | **Confiabilidade** (lógica de aposta) | ✅ | ✅ (inalterada) | Patches aditivos/cirúrgicos; suíte 568 verde. |

## 21. Deploy

_(preenchido após o deploy — ver §21.1)_

---

## Apêndice — extração e reprodução

```bash
# Extração (produção, read-only) — 18/06 em UTC
ssh root@187.45.181.75 \
  "docker exec roleta-cloud sqlite3 -json /app/data/decisions.db \
   \"SELECT id,timestamp,session_id,spin_direction,sda_score,sda_centers,sda_numbers, \
     final_action,gale_level,gale_bet_value,result_hit,result_actual,result_region,pnl_units \
     FROM decisions WHERE timestamp LIKE '2026-06-18%' ORDER BY id;\""
```

- **Geometria/PnL:** `coverage3()`/`force_last_center()` (`strategies/c_selection.py`),
  `_pnl_snapshot` (`server/websocket.py`), `_attribute_hit_region` (`state/game.py`).
- **Números:** 507 decisões · 441 resolvidas com `pnl` · 66 pendentes (25 = PULAR/calibração) · 18 sessões.
- **Parte II (fluxo front):** contrato em `server/message_handler.py:997-1084`, `_engine_overlay_fields`
  (`:257-275`), `engine_overlay_fields` (`state/game.py:930-990`); escuta em
  `extension/{background.js,content.js,overlay.css}`; Glass Box em `frontend/app.js`. Origem do BUG #1:
  commits `b57b62e` → `0d3c47e` (18/06). Estado prod: `SDA_BET_PAIR=force17`, `SDA_FORCE17_EXACT=0`.
- **Nota de fontes:** o **MCP graphify** servia um *super_graph* alheio ao projeto; usou-se o
  **grafo local** `graphify-out/graph.json` (reconstruído em `graphify update .`, HEAD `e6d7fcb`,
  2974 nós) para ancorar os símbolos. **brave-search** validou a margem da casa (2,7%). A Parte II
  usou 2 subagents `explore` (escuta + Glass Box) com validação direta no código.

*Auditoria gerada em 18/06/2026 — MCP: sequential-thinking · memory · graphify · filesystem · brave-search;
dados via SSH (produção real); Parte II + subagents explore para o fluxo front.*
