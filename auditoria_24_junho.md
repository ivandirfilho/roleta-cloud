# auditoria_24_junho — Auditoria do levantamento 22/06 + arquitetura de dados e estratégia

**Data:** 2026-06-24 · **Autor:** auditoria independente (verificação por reprodução)
**Método:** re-execução das queries sobre **o mesmo snapshot** `dec_snap_22.db` (9.471 decisões,
21/jan→22/jun 21:23) usado em `resultados_22_junho.md`, cruzando cada número com o **código real**
(`server/message_handler.py`, `strategies/sda17.py`, `state/game.py`, `app_config/settings.py`,
`database/sqlite_repo.py`). Stack MCP: graphify · memory · filesystem · sequential-thinking · brave.
SSH à produção (`187.45.181.75:22`) estava **inacessível** nesta auditoria → tudo abaixo vem do snapshot+código.

> Objetivo desta passada: (1) **auditar** o entregável anterior claim-a-claim; (2) **avançar** para uma
> análise de arquitetura de DADOS e de ESTRATÉGIA com uma métrica de edge correta.

---

## 0. TL;DR — o que confirmei, corrigi e descobri

**Confirmado (reproduzido na bit):**
- Semântica `result_actual[t]==spin_number[t+1]` → **405/405 = 100%**. A aposta é o **oposto** de `spin_direction` e resolve no próximo spin. ✅
- Hoje 22/06: **n=391, hr=42,2%, PnL=−81,1u**; CCW(anti) **+141,8u** vs CW(horário) **−222,9u** — bate exato. ✅
- 19/06 é **1 sessão** (`84f121e8`, 239 plays) com **dealer `unknown` em 685/731** → replay/feed travado. Quarentena confirmada. ✅
- Dealer: cobertura **5,7% all-time → 81,0% nas últimas 400** (visão OCR populou). ✅ Mas **não é usada** pela geometria. ✅

**Corrigido (erro metodológico do relatório):**
- ⚠️ **O breakeven único de 47,2% (N=17) está errado** para a era. A cobertura **NÃO é 17** — varia por dia porque flags foram alternadas. Distribuição real de N apostado na era (excl. 19/06): **N=21 → 894 plays, N=14 → 534, N=17 → 473**, + caudas 12/13/15/16. Cada N tem breakeven próprio (`N/36`): 21→58,3%, 17→47,2%, 14→38,9%. Comparar hit-rate agregado a uma linha só mistura geometrias diferentes.
- ⚠️ O rótulo **"geometria regions_v4"** é impreciso: `SDA_REGIONS_V4` tem **default OFF** e é *mutuamente exclusiva* de V2/V3. O que o relatório descreve (offsets-KDE, 3+7+7) é **V2+V3 (N=17)**, não o método `_build_v4_regions` (21#).
- ⚠️ O número "**8 a 14,4% / ~12σ**" do 19/06 é específico do **subconjunto** de 313 anti-full-stake; no dia inteiro (731) o pico é ~8% (12→8,2%, 8→7,9%). Anômalo, mas o 12σ não vale para o dia todo.

**Descoberto (novo, decisivo):**
- 🔴 **Não há edge — e é pior que aleatório.** Removendo TODO o staking (aposta flat 1u por número), o **ROI de cobertura da era (excl. 19/06) = −4,71%**. O baseline de seleção **aleatória** numa roleta justa é **−1/37 = −2,70%** para qualquer N. A estratégia fica **~2pp ABAIXO do aleatório** no agregado → a seleção de números é, em média, levemente **contraproducente**. Como o ROI flat é negativo, **nenhum staking (gale/flat/Kelly) reverte** — eleva a memória "gale invariante" de teoria a número medido.
- 🔴 **`c2c3` (14#) é a PIOR geometria: flat ROI −8,03%.** Tirar o C1 destruiu valor. A escolha de produção "`SDA_BET_PAIR=c2c3` desde 17/06" (docstring `settings.py:145`) foi **ativamente nociva**. O `regions_v4` (21#) também arrasta (−4,70%). **`17# full V2/V3` é o único bucket ~breakeven (−1,50%)** — e é o que está no ar hoje (06-21/22).
- 🟡 **O sinal real é dealer×sentido, e sobrevive à remoção do staking:** `JAMES`×anti **flat ROI +9,3%** (n=43) e `OLIVER`×horário **+7,8%** (n=51) são positivos na **cobertura** (não é variância). Mas **83% da era é `dealer=unknown`** → a alavanca está represada atrás da cobertura de visão.

**Veredito:** a estratégia hoje é **estruturalmente breakeven-a-negativa**; o PnL+ ocasional é variância do Anti-Martingale, não vantagem. As duas alavancas reais são (a) **fixar a geometria em 17# full** (parar de alternar c2c3/21#) e (b) **gate dealer×sentido** quando a visão cobrir n suficiente.

---

## 1. Auditoria do entregável anterior (claim-a-claim)

| Claim de `resultados_22_junho.md` | Veredito | Evidência |
|---|---|---|
| Semântica `spin_direction`=gatilho, aposta=oposto, resolve no próximo | ✅ **Confirmado** | 405/405 reproduzido |
| Hoje −81,1u / 42,2% / CCW +141,8 vs CW −222,9 | ✅ **Exato** | reprodução §F |
| 19/06 corrompido (1 sessão, dealer unknown) | ✅ **Confirmado** | sessão 84f121e8=239; unknown 685/731 |
| "8 a 14,4%/12σ" no 19/06 | ⚠️ **Parcial** | vale p/ subset 313; dia todo ~8% |
| Geometria de produção = "regions_v4 / V3, N=17" | ⚠️ **Rótulo errado** | é V2+V3; `SDA_REGIONS_V4` default OFF; N varia 12–21 |
| Breakeven N=17 = 47,2% como régua única | ⚠️ **Metodologia falha** | N apostado é mix (21/14/17) — breakeven por linha |
| Exemplar D: C1 fora sob `bet_pair=c2c3` | ✅ **Confirmado** | docstring `settings.py:145` + 534 plays N=14 |
| "Ambos os sentidos perdem; horário é o vazamento" | ✅ **Confirmado e reforçado** | flat ROI CCW −3,1% vs CW −6,3% |
| "Edge anti +3090u é artefato do 19/06" | ✅ **Confirmado** | era s/19/06 é negativa nos dois sentidos |
| "Gale não entrega edge; PnL+ é variância" | ✅ **Provado mais forte** | flat ROI (sem staking) = −4,71% |
| Dealer capturado (~80%) mas não usado | ✅ **Confirmado** | 81% últimas-400; `SDA_DEALER_OFFSET`/profile dormentes |
| "CUT score<4 protege; não cobre score=4 c/ TR=0%" | ✅ **Confirmado no código** | `message_handler.py:767` corta só `score<4` |

---

## 2. Arquitetura de DADOS

### 2.1 Tabela `decisions` — 1 linha por spin-gatilho, auto-descritiva da jogada
DDL-base em `database/sqlite_repo.py:186` (spin, Triple Rate, SDA, decisão, gale, resultado) **+ ~15 colunas
adicionadas por `ALTER TABLE` em runtime** (`sqlite_repo.py:300-365`): `sda_centers, sda_offset(_type),
sda_regions, dealer, dealer_table, provider, round_id, result_region, pnl_units, wheel_model, vision_*`.
**Risco:** schema é gerido em **dois lugares** — Alembic (`migrations/versions/0001-0009`) **e** ALTERs imperativos
no repo. Drift é possível; `database/schema_parity_manifest.json` existe justamente para reconciliar.

Tabelas-irmãs: `sessions`, `gale_windows`+`window_plays` (ML-ready de janelas de gale), `decision_dna`
(**32.282 linhas**: `feature_name, feature_value, estimated_lift_pp, realized_lift_pp, confidence_n, wheel_dist`
— telemetria de lift por feature, é onde `region_C1/C2/C3` são emitidos), e o schema `shared.*`
(`spins_vectors, spin_features, dealers, strategy_versions, feature_flags, outbox`).

### 2.2 Lacuna de telemetria (causa-raiz do erro de breakeven)
**A linha de `decisions` NÃO persiste quais flags de estratégia estavam ativas** (`bet_pair`, `regions_v4`,
`geometry_v2/v3`). A geometria só é **inferível** pela contagem de `sda_numbers` — exatamente o que fez uma
régua de breakeven única enganar a análise. **Recomendação:** gravar um `geometry_tag`/`strategy_flags` por
linha (ou usar `shared.feature_flags`/`strategy_versions` de forma consistente) para tornar cada decisão
auto-descritiva e auditável.

### 2.3 Qualidade dos dados
- **Geometria misturada na era** (flags alternadas dia-a-dia — ver tabela §3.2). Qualquer média que não
  fatie por N mistura breakevens distintos.
- **`provider` poluído:** só `evolution` (2.062) é limpo; ~2.100 linhas são `host:*`
  (`roleta.xma-ia.com` 948, `7k…evo-games` 372, `doubleclick`/`googletagmanager`…). 5.230 são NULL. Filtrar antes de agrupar.
- **`dealer`:** 5,7% all-time → 81% recente. Util só agora; histórico é majoritariamente `unknown`.
- **19/06:** quarentenar de qualquer treino/backtest.

---

## 3. Arquitetura de ESTRATÉGIA

### 3.1 Pipeline por spin (`message_handler.handle_*`)
```
spin → check_prediction(numero): resolve a aposta ANTERIOR (update_result: hit, result_actual, err, region, pnl)
     → Triple Rate Advisor (c4/m6/l12)         → should_bet/confidence
     → SDA17.analyze                            → score, centers[C1,C2,C3], numbers (N)
     → INV-3 GLOBAL (sempre indica; só PULA 1ª oportunidade/sentido; 2ª = fallback N=21)
          vetos NÃO suprimem — modulam STAKE:
            stop-loss sessão (PnL ≤ −30u)  → 1u            (settings.py:52, default 30)
            CUT-POLICY v1 (score<4)        → ×0.10         (message_handler.py:767)
            Triple Rate cauteloso          → ×0.10
     → bet_pair override (SDA_BET_PAIR)         → recorta a cobertura final
     → staking (Anti-Martingale / flat / kelly) → gale_bet_value REAL
     → store_prediction(target_direction = OPOSTO do spin)
```

### 3.2 As TRÊS geometrias coexistentes (e a linha do tempo real)
`strategies/sda17.py::analyze` despacha conforme flags (`app_config/settings.py`):

| Geometria | Método | N | Breakeven | Flag (default) |
|---|---|---|---|---|
| **Full V2+V3** | `_geometry_radii`/`_sat_radii` (C1 r1=3, satélites 3/3 ou **4/2** assimétrico) | **17** | 47,2% | `SDA_GEOMETRY_V2=1`, `SDA_SAT_ASYM=1` (ON) |
| **c2c3** | override em `message_handler._apply_bet_pair` (dropa C1) | **14** | 38,9% | `SDA_BET_PAIR=c2c3` (código default `full`) |
| **regions_v4** | `_build_v4_regions`/`_compose_regions_v4` (3 regiões disjuntas r3) | **21** | 58,3% | `SDA_REGIONS_V4=1` (default **OFF**) |

Geometria dominante **por dia** (snapshot, excl. 19/06) — prova o toggling:
```
06-14: N=21 (481)         ← regions_v4 ON
06-15: N=21 (330)         ← regions_v4 ON
06-17: N=14 (297)         ← bet_pair c2c3
06-18: N=14 (185)+17(159) ← transição c2c3→full
06-21: N=17 (106)         ← full V2/V3
06-22: N=17 (178)         ← full V2/V3  (ESTADO ATUAL)
```

### 3.3 Staking — Anti-Martingale (`state/game.py::MartingaleState`)
`BET_VALUES {1:17, 2:34, 3:51}`; escala pelo **streak global** (≥2→G2, ≥3→G3); reset a G1 em qualquer miss;
take-profit em G3. CUT-POLICY v1 **limita gale a 2** (`game.py:80`). **Invariante:** o gale muda a variância,
não o EV — confirmado pelo flat ROI negativo (§4).

### 3.4 Alavancas dormentes (dados existem, código não usa)
- `SDA_DEALER_OFFSET=0` e `dealer_force_profile` (default OFF, `settings.py:241`) — geometria igual p/ todo dealer.
- `region_bandit.choose_region` — features `region_C1/C2/C3` emitidas no DNA, mas **nenhum chamador de produção**.

---

## 4. Análise de EDGE decisiva (metodologia corrigida)

**Problema:** hit-rate agregado vs breakeven único mistura N=14/17/21. **Solução:** medir o **ROI de cobertura
flat** — aposta 1u em cada um dos N números da linha; PnL = `(36−N)` se hit, `−N` se miss. Isso remove
**todo** o efeito de gale/modulação e isola a qualidade da **seleção de números**. Baseline aleatório numa
roleta justa = **−1/37 = −2,70%** para qualquer N.

**Era ≥06-14 (excl. 19/06), 2.288 jogadas resolvidas, por bucket de N:**
```
  N      n    hr%   BE=N/36  edge_pp   flatPnL  flatROI%   galePnL(real)
  12   135   28.1     33.3     -5.2      -252    -15.56      -54.0
  13    93   47.3     36.1    +11.2      +375    +31.02     +158.1   (n baixo)
  14   534   35.8     38.9     -3.1      -600     -8.03     -213.7   ← c2c3 = PIOR
  15    70   37.1     41.7     -4.5      -114    -10.86      -60.6
  16    89   36.0     44.4     -8.5      -272    -19.10     -204.5
  17   473   46.5     47.2     -0.7      -121     -1.50     -299.9   ← full = MENOS RUIM
  21   894   55.6     58.3     -2.7      -882     -4.70     -423.7   ← regions_v4 arrasta
  ALL 2288   45.8    ~48.1            -1866    -4.71    -1098.4
```
**`flat ROI = −4,71%` < `aleatório −2,70%`** → sem edge; pior que aleatório no agregado.

**Por sentido apostado (flat, sem staking):**
```
  CCW(anti)    n=1137  hr=46.6%  avgN=17.3  BE=48.1%  flatROI=-3.07%
  CW(horário)  n=1151  hr=45.0%  avgN=17.3  BE=48.0%  flatROI=-6.33%   ← vazamento
```

**Dealer×sentido (n≥25, flat ROI — sobrevive à remoção do staking):**
```
  JAMES   CCW(anti)    43  hr46.5  flatROI +9.26%   ← sinal real (cobertura, não variância)
  OLIVER  CW(horário)  51  hr45.1  flatROI +7.81%   ← sinal real
  unknown CCW(anti)   957  hr47.4  flatROI -3.54%
  unknown CW(horário) 950  hr46.1  flatROI -6.34%
  JAMES   CW(horário)  48  hr37.5  flatROI -14.29%
  OLIVER  CCW(anti)    45  hr35.6  flatROI -17.12%
```
Heterogeneidade dealer×sentido é grande e **alguns pares são +EV na cobertura** — mas 83% da era é
`unknown`, então a alavanca depende da cobertura de visão crescer.

---

## 5. Recomendações priorizadas (com âncora de código)

1. **Congelar a geometria em `17# full V2/V3`** — parar de alternar `c2c3`/`regions_v4`. c2c3 (−8,0%) e 21# (−4,7%) são piores que o full (−1,5%). Garantir `SDA_BET_PAIR=full`, `SDA_REGIONS_V4=0` em produção. *(maior dano evitado)*
2. **Gravar `geometry_tag`/`strategy_flags` por linha** em `decisions` (lacuna §2.2) — sem isso, toda análise futura volta a inferir N e erra o breakeven.
3. **Cortar full-stake em CW(horário)** por padrão (×0.10/abster) até um gate provar o contrário — −6,3% flat consistente.
4. **Fechar o buraco do exemplar B:** estender CUT-POLICY para `score==4 AND tr_c4_rate==0` (`message_handler.py:767`).
5. **Gate dealer×sentido em sombra** (telemetria) até n≥30/par; suspender full-stake em pares como `KAIO×horário`/`OLIVER×anti`. Dados já existem; só não são lidos.
6. **Stop-loss persistente entre sessões** (hoje reseta a cada reconexão → bleed recomeça).
7. **Quarentenar 19/06** em qualquer treino/backtest/memória de "edge anti".
8. **Aceitar o teto honesto:** mesmo no melhor bucket o edge é ~0. Sem viés explorável de roda, a meta realista é **minimizar perda** (de-risking), não extrair lucro de staking.

---

## 6. Apêndice — reprodutibilidade
- Snapshot: `…/session-state/fbc3705e-…/files/dec_snap_22.db` (idêntico ao de `resultados_22_junho.md`).
- Scripts desta auditoria: `…/session-state/737d9000-…/files/recon.py`, `audit_24.py`, `enrich.py`.
- Métrica-chave: **flat coverage ROI** = `Σ(36−N se hit, senão −N) / Σ N`. Random fair = −1/37 = −2,70%.
- Breakeven por linha = `N/36`. PnL real = `pnl_units` (stake pós-modulação, LEDGER FIX 12/06).
