# Resultados da semana — 10/08 → 16/08/2026

> **Autor:** Diretor de Sprints (sessão 16/08 noite) · **Método:** probe **read-only** no servidor de
> produção (`root@187.45.181.75`, autorizado pelo dono; precedente `resultados_bancos_junho.md` e
> `plano_migracao_03_08.md` §14.8) + queries SQLite/PG ao vivo + simulação local sobre a série real +
> relatórios de agentes (grafo, Azure, semana git).
> **HEAD de produção no momento do probe:** `b29233a` (PR #88) — deploy em dia com a `main`.
> **Não existe `resultados_10_08.md`**: a base desta análise é o **período** 10/08→16/08 no banco
> autoritativo (`decisions.db`) + espelho PG + o que a `main` mergeou na janela.

---

## 1. Veredito executivo (1 tela)

| Pergunta do dono | Resposta curta | Evidência |
|---|---|---|
| A estratégia está valendo a pena? | **No dia 16/08, SIM: +168,6u (243 jogadas, HR 56,8%)** — mas é 1 dia; o histórico flat era −4,71% ROI. Não extrapolar. | §4, §6 |
| Ela evolui a cada jogada? | **Estrutura de aprendizado SIM (loop DNA→lift ativo, 81,6% das linhas com lift realizado); hit-rate intra-dia NÃO subiu** (59,5%→56,0%→55,8% por bloco de 100). | §4 |
| A print do app povoa o nome do dealer? | **SIM — 100%** (301/301 decisões do dia com `dealer` e `vision_source`). | §5 |
| A assinatura do dealer é validada e usada pela IA/ML? | **NÃO.** Coletada e espelhada (0 nulos no PG), mas `SDA_R2_DEALER_SHADOW=0`, `SDA_ERROR_ENGINE=0`, `SDA_DEALER_FORCE_PROFILE=0` e o DNA **não tem feature de dealer**. Vantagem desperdiçada → **SPR-ML1**. | §5 |
| Debian está povoando local em tempo real? | **SIM** — SQLite autoritativo gravando (id 12004), outbox 4.176 eventos no dia, backlog **0**, CDC saudável. | §3 |
| Azure está sendo povoada em tempo real? | **NÃO (por design atual): é standby frio** por snapshot a cada 10 min (timer ativo no host) + poll 2 min na VM; PG analítico Azure vazio; workflow de imagens `skipped` (gate ausente) → **SPR-AZ1**. | §8 |
| Martingale ×2 (5+5+5) dá lucro? | Na série real do dia: o esquema 5×1→5×2→5×4 **≈ flat** (streak máx = 5, quase não engaja). Escaladas curtas (×2 pós-2-misses) renderam **+33%** com risco limitado; ×2 clássico rendeu +155% mas com drawdown 2,6× pior. **Só entra em produção após backtest completo** → **SPR-G7**. | §7 |

---

## 2. Povoamento da semana — a verdade dura

**A semana teve APENAS 1 dia de dados.** O incidente `/ws 502` (causa-raiz MIG-0, ver board §Incidente
16/08) manteve o pipeline **cego de 06/08 23:13 até 16/08 14:31**:

| Fronteira | id | timestamp |
|---|---|---|
| Última decisão antes do blackout | 11703 | 2026-08-06T23:13:18 |
| Primeira decisão pós-recuperação | 11704 | 2026-08-16T14:31:13 |

Povoamento desde a recuperação (16/08 14:31 → 17/08 00:35 UTC):

| Dia (UTC) | Decisões | Resolvidas | Hits | HR | PnL (u) |
|---|---|---|---|---|---|
| 16/08 | 255 | 203 | 116 | **57,1%** | **+170,1** |
| 17/08 (madrugada) | 46 | 40 | 22 | 55,0% | −1,5 |
| **Total janela** | **301** | **243** | **138** | **56,8%** | **+168,6** |

14 sessões, 278 apostas, `max_gale_reached=1` (block-gale cap 1 = flat, conforme flag).
Total geral do banco: **12.004 decisões** desde 21/01/2026.

**Implicação:** "resultados da semana" = resultados de ~10h de operação. Todo o resto do documento
deve ser lido com esse denominador. A lição do incidente ("mergeou ≠ implantado") já virou regra e
sprint (D2/D3/D4).

---

## 3. Estruturas de dados & IA/ML — funcionais?

**SIM, ponta a ponta, com 1 ressalva de qualidade (E7 abaixo).** Verificado ao vivo:

```
Extensão 3.11.0 ──wss──▶ websocket/message_handler ──▶ SQLite decisions.db (id 12004) ✅
                                   │                        │ outbox best-effort
                                   ▼                        ▼
                            state.json (volume)      shared.outbox: 4.176 eventos dia 16 · backlog 0 ✅
                                                            │ LISTEN/NOTIFY
                                                            ▼
                                              cdc-worker (healthy, 21h up) ✅
                                                            ▼
              PG15+pgvector: cw.spin_features 3.599 · ccw 3.349 (dealer: 0 nulos) ✅
                             cw.spins_vectors 4.270 · ccw 4.038 (ae_latent p/ k-NN) ✅
                             shared.decision_dna 54.350 (44.344 com realized_lift = 81,6%) ✅
```

- **Flags de dados ativas em produção** (env real do container): `SDA_DNA_REALIZE=1` (a cada 20),
  `SDA_VISION_OCR=1`, `SDA_DEALER_FILL_FORWARD=1`, `SDA_PHASE_EVENT_AUDIT=1`,
  `SDA_DIRECTION_VISION_SHADOW=1`, `SDA_PHASE_BUFFER_SYNC=1`, `SDA_PHASE_ALT_METRIC=1`,
  `SDA_SENTIDO_AUTORITATIVO=1`, staking `block_gale` + `GALE_CAP=1`.
- **Trilha de fase**: `phase_events` = 289 linhas (shadow do sentido) — o relógio efetivo do gate T4
  começou 16/08 (blackout comeu o período desde o merge da flag em 06/08).
- **Dormentes** (existem, não rodam): `SDA_ERROR_ENGINE=0`, `SDA_R2_DEALER_SHADOW=0`,
  `SDA_R2_DEALER=0`, `SDA_DEALER_FORCE_PROFILE=0`, `SDA_PG_FEATURE_CONTEXT=0`.
- **E7 (achado de qualidade, novo):** `pnl_units` mistura **escalas** — há linhas com PnL total do
  giro (+19/−17) e linhas com PnL por unidade (+1,12/−1,0). O agregado +168,6u é direcionalmente
  correto, mas backtests precisam normalizar antes (tarefa 0 do **SPR-G7**).

---

## 4. A estratégia está evoluindo a cada jogada?

Duas respostas diferentes — e as duas importam:

**(a) O mecanismo de evolução está ligado e povoando.** Cada jogada gera DNA (301 linhas/feature no
dia: `sda_score`, `tr_c4_rate`, `region_C1..C3`, `hit_region`, `kill_v4`, `v5_coverage_mode`,
`v5_would_hit_17/21`…) e o loop H1 (`dna_realize_lifts` a cada 20 resultados) está **preenchendo
`realized_lift_pp`** (233/243 no dia; 81,6% do histórico). O seletor **v5 flip-puro 17/21** adapta a
cobertura pela última jogada do sentido-alvo, e os contrafactuais `v5_would_hit_17/21` estão sendo
gravados para auditar essa escolha. Ou seja: **a máquina de aprender está operando**.

**(b) O resultado por jogada NÃO mostrou melhora intra-dia.** Por blocos de ~100 ids:

| Bloco | n resolvidas | HR | PnL (u) |
|---|---|---|---|
| 11700 | 79 | 59,5% | −24,3 |
| 11800 | 75 | 56,0% | +158,7 |
| 11900 | 86 | 55,8% | +49,1 |
| 12000 (parcial) | 3 | 33% | −15,0 |

HR levemente **decrescente** enquanto o PnL melhora — o ganho veio da **seleção de cobertura**
(17 vs 21) e do mix de dealers, não de acerto crescente. Com n=243 nada disso é significância; a
tendência real precisa de semanas de povoamento contínuo (agora garantido pelo self-heal do D1/D2).

---

## 5. Dealer: OCR, assinatura e uso pela IA

- **Povoamento da print (app → OCR → dado): PERFEITO.** 301/301 decisões com `dealer`,
  `vision_source` e `wheel_model`; espelho PG com **0 nulos** de dealer na semana
  (`cw`: 0/3.599 · `ccw`: 0/3.349). O fill-forward (`SDA_DEALER_FILL_FORWARD=1`) está fazendo o
  trabalho de acoplar cada jogada ao dealer da sessão.
- **Assinatura do dealer sendo validada? NÃO.** As três pontas que transformariam o dado em
  vantagem estão OFF em produção: `SDA_ERROR_ENGINE=0` (classificação do processo do erro),
  `SDA_R2_DEALER_SHADOW=0` (bandit Thompson dealer×sentido em paper), `SDA_DEALER_FORCE_PROFILE=0`
  (perfil de força n≥30). E o `decision_dna` **não registrou nenhuma feature `dealer_*`** na semana.
- **O dado já discrimina** (recorte do dia, n≥15 por célula):

| Dealer × sentido | n | HR | PnL (u) |
|---|---|---|---|
| STEPHEN × horário | 24 | **70,8%** | +127,1 |
| STEPHEN × anti | 23 | **65,2%** | +121,5 |
| DIEGO × horário | 21 | 61,9% | +55,5 |
| DIEGO × anti | 21 | 57,1% | +48,1 |
| JESSICA × anti | 17 | 58,8% | −12,7 |
| VICTORIA × anti | 16 | 56,3% | −35,4 |
| JESSICA/ELINE/VICTORIA × demais | 66 | 40–50% | −105,2 |

STEPHEN+DIEGO = **+352,2u**; o resto = **−183,6u**. É exatamente o padrão que o balanço de agosto
já apontava (gate dealer×sentido como única alavanca positiva). **Ação:** ligar o shadow do
dealer-aware AGORA (zero efeito em aposta, INV-3 intacto) → **SPR-ML1**; decisão de live só depois
da janela shadow.

---

## 6. Lucro ou prejuízo — e onde vaza

**Dia 16/08: LUCRO de +168,6u** (banca de referência 1.000u → +16,9% no dia). Decomposição:

| Recorte | n | HR | PnL (u) | Breakeven teórico |
|---|---|---|---|---|
| Cobertura **17** | 145 | 55,2% | **+247,4** | 47,2% ✅ folga de 8pp |
| Cobertura **21** | 98 | 59,2% | **−78,9** | 58,3% ⚠️ no fio — e PnL negativo (E7: payouts efetivos < nominais em parte das linhas) |
| Horário | 126 | 57,9% | +127,0 | — |
| Anti-horário | 117 | 55,6% | +41,6 | — |

**A maior alavanca de lucro não é apostar mais — é escalar MENOS para 21.** A cobertura-21 operou
no breakeven e queimou 79u do lucro que a 17 gerou. O seletor v5 flip-puro (miss→21) está pagando
caro pelos 4 números extras em regime onde a 17 já acerta 55%. Auditar essa régua entra no
**SPR-G7** (junto da normalização E7), usando os contrafactuais `v5_would_hit_17/21` já gravados.

Derrotas em sequência (base p/ qualquer gale): dist `{1:29, 2:21, 3:7, 4:2, 5:1}` — **streak máximo
do dia = 5**.

---

## 7. Martingale — simulações sobre a série real do dia

Simulei sobre as **243 jogadas reais em ordem cronológica** (multiplicador aplicado ao stake da
jogada; nível = derrotas consecutivas antes dela):

| Esquema | PnL (u) | maxStake | risco máx num run | maxDD |
|---|---|---|---|---|
| A) **Flat (produção hoje, cap 1)** | +168,6 | 21 | 78 | −145 |
| B) Martingale ×2 clássico (teto 5) | **+430,6** | 168 | 335 | **−377** |
| C) **Blocos do dono: 5×1 → 5×2 → 5×4** | +170,0 | 21 | 78 | −145 |
| D) Escada suave 1,1,2,2,3 | +225,0 | 42 | 124 | −178 |
| E) ×2 só após 2 derrotas seguidas (teto ×2) | +224,1 | 42 | 122 | −178 |
| F) Block-gale ×2 cap 2 (1,2,4) | +406,6 | 84 | 227 | −315 |
| G) Blocos do dono só na cobertura-17 | +168,6 | 21 | — | — |
| H) E) aplicado só na cobertura-17 | +206,6 | 34 | — | — |
| I) E) aplicado só em dealers positivos (STEPHEN/DIEGO) | +226,8 | — | — | — |

Leitura honesta:

1. **O esquema proposto (5 normais → 5 dobrados → 5 dobrados de novo) é inócuo na prática**: ele só
   engaja no 6º miss consecutivo, e o dia inteiro teve **um único** streak de 5. Resultado ≈ flat.
   Se a intenção é proteção psicológica com upside, os gatilhos precisam ser mais curtos.
2. **Martingale clássico multiplicou o lucro (+155%) — e o risco (DD −377u = 37% da banca de 1.000u)**.
   Num dia espelhado ao contrário (43% HR em vez de 57%), essas perdas dobram na mesma proporção:
   multiplicador amplifica os DOIS lados; **não cria edge, só move variância**. O histórico
   (backtest de junho: gale −77u vs flat +99u nas mesmas jogadas) prova que em regime ruim ele sangra.
3. **Melhor razão retorno/risco da amostra: E/H/I** — escalada ×2 disparando após 2 misses, teto ×2,
   de preferência restrita à cobertura-17 (breakeven folgado) e/ou a dealers com HR>55%:
   +33% de PnL com maxStake 34–42u e DD próximo do flat.
4. **Nada disso vai para produção por 1 dia de amostra.** O caminho ISO: **SPR-G7** roda os esquemas
   sobre TODO o histórico (com E7 normalizado, recortes dealer×sentido×cobertura, risco de ruína
   Monte-Carlo) e, só se vencer com DD aceitável, implementa `GALE_TIERS` atrás de flag
   **default-equivalente-ao-atual** (cap 1) — ligar é outro PR, com janela shadow. INV-3 intacto:
   tiers modulam stake, indicação continua sempre `APOSTAR`.

---

## 8. Azure — povoada em tempo real?

**Não. Hoje é um standby frio de RPO ~10 min, e metade da esteira está desligada por gate:**

| Elo | Estado verificado |
|---|---|
| Snapshot HostDime → Blob (SQLite+state.json) | ✅ timer `roleta-hostdime-snapshot` ATIVO no host (roda a cada 10 min; último tick 2 min antes do probe) |
| Poll Azure ← Blob (restore em `/opt/roleta/standby`) | ⚠️ desenhado p/ 2 min; VM responde (Caddy up, `/healthz` é o path — `/health` dá 404), freshness interna **não comprovada de fora** → SPR-AZ1 mede |
| Imagens app/CDC → ACR (`acr-image.yml`) | ❌ **`skipped` em todos os runs** — repo variable `AZURE_PUBLISH_ENABLED` **não existe** e secrets OIDC (`AZURE_CLIENT_ID/TENANT/SUBSCRIPTION`) **não existem** (criação é do dono) |
| PG analítico Azure | ❌ vazio (dual-write OFF por design pré-cutover) |
| Autoridade | HostDime segue **único escritor**; promoção Azure = freeze+cutover manual (correto) |

**Conclusão:** a estrutura está *preparada e viva*, mas o povoamento é por snapshot (quase-real-time
de dados frios), não replicação em tempo real — e continuará assim até o dono criar os secrets OIDC
+ variable de gate. **SPR-AZ1** entrega a medição de freshness ponta-a-ponta, a sonda `/healthz` no
kickoff e a issue com o passo-a-passo exato para o dono.

---

## 9. Sprints abertos nesta análise (executores `gpt-5.6-luna`) + ativações

| Sprint | O quê | Por quê (dado que sustenta) |
|---|---|---|
| **SPR-ML1** (P1) | Ligar `SDA_ERROR_ENGINE=1` + `SDA_R2_DEALER_SHADOW=1` (defaults na compose + espelho Azure + adendo) e validar o funil no DNA | Dealer 100% coletado e 0% usado; células dealer×sentido já separam +352u vs −184u (§5) |
| **SPR-G7** (P1) | Backtest honesto de staking multi-tier (blocos 5-5-5 do dono, ×2-pós-2, 1-2-4) + auditoria E7 (`pnl_units`) + régua 17/21; implementação `GALE_TIERS` flag-OFF só se vencer | §6 (cobertura-21 −78,9u), §7 (sims), E7 |
| **SPR-AZ1** (P2) | Freshness real do standby Azure + sonda `/healthz` no kickoff + issue OIDC p/ dono | §8 (gate ausente, runs skipped) |
| **SPR-REL1** (P2, TODO) | Automatizar este relatório (script read-only PG→md diário) | Este documento levou 1 sessão de Diretor; deve custar 1 comando |

**Ativações corrigidas no board** (probe ao vivo): `ativado_audit_shadow` na real ligou **06/08 (PR
#63)** — mas o blackout zerou a trilha: gate T4 conta de **16/08**; `SDA_PHASE_BUFFER_SYNC=1` já
ativo; falta só o **Reload da extensão no Chrome** (3.11.0 já sincronizada) para habilitar o PR de
ativação do gate temporal (`SDA_MIN_SPIN_INTERVAL_MS=15000`).

---

## 10. Pendências e riscos

1. **Amostra de 1 dia** — toda conclusão de performance aqui é preliminar; com o self-heal (D1/D2) a
   próxima semana deve vir inteira, e aí a régua evolutiva (§4b) vale de verdade.
2. **E7 (`pnl_units` com escala mista)** — corrigir a leitura antes de qualquer decisão de staking.
3. **Reload da extensão** no Chrome do operador (última milha X5/D4) — sem isso o gate temporal
   anti-fantasma não pode ligar.
4. **Cobertura-21 no fio do breakeven** — maior vazamento identificado; tratar no G7 antes de
   qualquer martingale.
5. **Azure sem gate OIDC** — povoamento contínuo de imagem/deploy depende de ação do dono (issue do
   SPR-AZ1).
