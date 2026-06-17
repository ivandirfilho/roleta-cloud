# Implantação — C1/C2 Variável + Gale (Junho 2026)

> **Auditoria de implantação e proposta de evolução** para operar a estratégia **C1/C2 variável
> (últimas 3 não-C3) + C3 fixo** (14 números) com dois **motores evolutivos acoplados**: um para
> a seleção C1/C2 e outro para o **gale isolado por sentido** (blocos de 4, ×1/2/4/8, opção "só
> jogar após green"). Inclui levantamento completo da arquitetura de dados atual, infraestrutura,
> UX e plano de implantação.
>
> **Base analítica:** `resultados_15_junho.md` (backtest das últimas 100/sentido + controles).
> **Stack MCP:** `sequential-thinking` (desenho dos motores/topologia), `graphify` (grafo fresco
> HEAD `23c3490` → arquitetura/dependências), `memory` (convenções do projeto), `filesystem`.
> **Auditoria de código:** 3 frentes paralelas (dados, estratégia, frontend) + leitura do núcleo
> de estado/decisão. Citações `arquivo:linha` no Apêndice.

---

## 0. TL;DR e decisões de arquitetura

1. **A estratégia operada é a variável C1/C2 (últimas 3 não-C3) + C3 fixo = 14 números.** As
   duplas estáticas e os 21# ficam como modos de referência atrás de flag.
2. **Dois motores, ambos *shadow-first* (não mexem em dinheiro até validarem):**
   - **`CSelectionEngine`** — escolhe C1 ou C2 a cada jogada (C3 fixo) e **evolui** qual regra de
     seleção usar por sentido, via o padrão **shadow-grid + bandit + EMA** que **já existe** no
     código (`state/game.py`). Como o sinal C1/C2 é ~0 (memoryless, provado), o motor **converge
     graciosamente para a melhor dupla** — é uma feature, não um bug.
   - **`BlockGaleEngine`** — gale **isolado por sentido**, blocos de 4, critério 2-de-4,
     ×1/2/4/8, teto configurável, "só após green" opcional. O componente "evolutivo" é um
     **limitador de risco** (NÃO um otimizador de edge): por padrão **fixa flat** e só *permite*
     tetos maiores como **opt-in explícito com aviso**, avaliando risco **em walk-forward** —
     porque o backtest provou que todo teto é −EV e o ×8 arruína.
3. **Acoplamento mínimo e reversível:** ambos entram **atrás de flags** (`SDA_BET_PAIR`,
   `SDA_STAKING_MODE=block_gale` — **novo valor a adicionar** ao enum atual `gale|flat|kelly`,
   cujo **default é `gale`**, logo *flat exige config explícita no deploy*; `GALE_ONLY_AFTER_GREEN`),
   reusando hooks existentes
   (`analyze()`, `update_adaptive()`, `staking_mode()`, `_adaptive_state`, `gale_windows`).
   **INV-3 preservado** (sempre indica; gate/risk modulam stake, não suprimem).
4. **Infra de dados:** reusar `decision_dna` (já tem `hit_region` com `dist_c1/c2/c3`) +
   `state.json::adaptive_state` (persistência quente) + `gale_windows` (auditoria). Uma migration
   `0009` adiciona telemetria; **nenhuma tabela nova no caminho quente**.
5. **UX:** painel de **gale por sentido** (dados já trafegam em `state_sync`), toggle **"só após
   green"**, seletor de **teto de gale** com aviso de risco, e display do **par C1/C2 escolhido +
   placar dos candidatos**.

---

## 1. Auditoria da arquitetura atual

### 1.1 Visão geral (camadas)

```
┌─────────────┐   WS    ┌──────────────────────────┐   call   ┌────────────────┐
│ Extensão    │ ──────▶ │ server/websocket.py      │ ───────▶ │ MessageHandler │
│ "Escuta"    │ ◀────── │  + connection_manager    │ ◀─────── │ (decisão/INV-3)│
│ (Chrome MV3)│ sugestao│  state_sync (1s)         │ overlay  └──────┬─────────┘
└─────────────┘  trace  └──────────────────────────┘                 │
                                                                      ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ strategies/sda17.py  →  StrategyResult{center, numbers, details[centers]}  │
   │ state/game.py        →  GameState (timelines, MartingaleState cw/ccw,      │
   │                          shadow_grid, bandit, _adaptive_state, pending)    │
   │ database/            →  db_service → sqlite_repo (decisions, decision_dna, │
   │                          gale_windows, window_plays, sessions) + PG outbox │
   │ core/roulette.py     →  WHEEL_SEQUENCE, distância circular (fato físico)   │
   └──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Backend — fluxo de decisão (`server/message_handler.py`)

Por spin (`handle_new_result`):
1. **Resolve o spin anterior** e atualiza martingale por direção
   (`martingale_cw.update(hit)` / `martingale_ccw.sync_global`) — `message_handler.py:214-229`.
2. **Atribui a região do resultado** (`_attribute_hit_region`) → `last_hit_attribution`
   (`slot`, `dist_c1/c2/c3`, `dist_min`) e persiste em `decisions.result_region` + DNA
   `hit_region` — `message_handler.py:291-327`.
3. **Chama a estratégia** `strategy.analyze(timeline, last_number, WHEEL, recent_numbers)` →
   `StrategyResult` com `center`, `numbers` (cobertura), `details['centers']=[c1,c2,c3]`,
   `offset`, `offset_c3`.
4. **Decisão final + INV-3:** sempre indica; aplica `staking_mode()` (gale/flat/kelly),
   stop-loss, cut-policy — `message_handler.py:415-515`. **INV-3:** o gate **modula stake**
   (×0,10 / 1u), nunca suprime a indicação.
5. **Stake:** `get_effective_bet()` → `stake_info{effective_bet, base_bet, multiplier, mode}`.
6. **Persiste** a decisão (`db_service.save_decision`) e emite ao cliente:
   - `sugestao` (overlay) — `message_handler.py:744-778`.
   - `trace` (dashboards) com `martingale_cw`/`martingale_ccw` — `message_handler.py:782-815`.
   - `state_sync` (heartbeat 1s) — `server/websocket.py` (já carrega ambos os martingales +
     `window_history` + `pending_prediction`).

### 1.3 Estratégia (`strategies/sda17.py`) — como emite C1/C2/C3

- `analyze()` retorna `StrategyResult` (`strategies/base.py`): `numbers` (17/21#), `center`=C1,
  `details['centers']=[c1,c2,c3]`, `details['offset']`=off C1→C2, `details['offset_c3']`=off C1→C3.
- **Estado isolado por sentido (INV-1):** `cw_history`/`ccw_history`, `_sigmoid_off`
  (`cw_off2`,`cw_off3`,`ccw_off2`,`ccw_off3`), `_region_err_hist` (deque 60/dir), `_region_err_ema`
  (EMA de erro por região/dir).
- **Feedback:** `update_adaptive(direction, c1, actual, wheel, coverage, centers)` →
  `_pct_sigmoid_update()` + `_batch_auto_tune()` (**online tuning a cada 4 spins por sentido** —
  cadência ideal para reuso).
- **Persistência:** `get_adaptive_state()` / `load_adaptive_state()` (dict serializável em
  `state.json`).
- **Cobertura** = união dos raios por região (`get_neighbors(center, raio, wheel)`); hoje 17
  (fat-SAT) ou 21 (V4 disjunto).
- **`region_bandit.choose_region()` existe mas está DORMENTE** (só testes) — gancho pronto para o
  motor C1/C2.

### 1.4 Estado e gale atual (`state/game.py`)

- **`MartingaleState` (Smart Gale v7, Anti-Martingale):** níveis 1/2/3, valores **17/34/51**,
  **escala no streak de VITÓRIAS** (não em perdas), reset no miss, **streak global
  cross-direction**. `game.py:20-176`. **≠ do gale proposto** (blocos de 4, ×1/2/4/8, isolado).
- **Por sentido:** `martingale_cw` / `martingale_ccw` já existem (`game.py:219-220`) — mas
  compartilham o streak global.
- **Infra evolutiva já existente (reuso direto):** `shadow_grid` (4 challengers c/ rotações),
  `_update_shadow_ema_on_spin()` (EMA + sustained + suggestion + auto-promote human-in-the-loop,
  `game.py:588-706`), **bandit ε-greedy** `_update_bandit_on_spin()` (`game.py:710+`).
- **`_adaptive_state`** (dict, `game.py:241`) é persistido em `state.json` (`save()` 1110-1169) —
  **lar natural** do estado dos novos motores.
- **`pending_prediction`** carrega `numbers/center/centers/bet_placed` para resolver no próximo
  spin (`game.py:574-586`).

### 1.5 Infraestrutura de dados

- **`decisions`** (sqlite + PG): contexto do spin, `sda_center`, `sda_centers` (JSON [c1,c2,c3]),
  `sda_offset`, `sda_regions` (JSON), `gale_bet_value` (stake **pós-modulação**, B5),
  `result_region`, `pnl_units` (P&L por decisão), `dealer/provider/round_id`.
- **`decision_dna`** (migration `0008`): features chave por spin — `region_C1/C2/C3`,
  **`hit_region` com `dist_c1/dist_c2/dist_c3/dist_min`** (a matéria-prima exata do voto C1/C2!),
  `final_action`, `hit`, `wheel_dist`. Logado via `database/dna_logger.py`
  (`dna_log_feature`, `dna_update_realized`).
- **`gale_windows` / `window_plays`:** lifecycle de janelas de gale **por sentido** (≤1 aberta/dir
  via índice único `idx_gale_windows_active`), com `create/add_window_play/close`,
  `get_gale_stats` (hit-rate por nível) e `get_window_history`. **Reusável** para auditar o
  block-gale.
- **Sessões + P&L (B5):** `sessions.total_profit`, `get_session_pnl` (gate de stop-loss),
  `update_result` calcula `pnl_units = stake*(36/N − 1)` se hit, `−stake` se miss.
- **Migrations:** `0001_baseline` → `0008_decision_dna` (head atual). Alembic.
- **Persistência de estado:** `state.json` (escrita atômica) com `martingale_cw/ccw`,
  `adaptive_state`, `shadow_grid`, `pending_prediction`, `recent_results`.

### 1.6 Frontend/UX atual (`extension/`)

- **`popup.html`/`popup.js`:** seletor de direção (horário/anti), toggle auto-start, dropdown de
  mesa, painel financeiro (`#apostaValue`/saldo/ficha), grade de resultados.
- **`background.js`:** cliente WebSocket + roteador de mensagens (`sugestao`, `state_sync`,
  `trace`); padrão de toggle config (auto-start) reutilizável para novos toggles.
- **`content.js` + `overlay.css`:** overlay na página do cassino — mostra `acao`, `numeros`,
  centros **[C1][C2][C3]**, `gale_display` (cores g1/g2/g3), `aposta`.
- **Lacunas (a construir):** painel de **gale por sentido** (CW/CCW separados), **toggle "só após
  green"**, **banca/drawdown** ligados ao gale, **placar de candidatos** C1/C2.

### 1.7 Observabilidade

- **Prometheus** (`server/health_server.py` `_PROM_METRICS` + provider em `server/websocket.py`
  boot, cache 30s) — padrão documentado (NEW-12/SP-29/SP-30). Alertas em `obs/alerts.yml`.
- **Grafana** `obs/grafana/dashboards/roleta-dna-regions.json` (regiões/DNA). **Não há** painel de
  banca/gale por sentido.

---

## 2. Situação atual vs alvo (simulação / evolução das variáveis)

| Dimensão | **Hoje (código)** | **Alvo (esta proposta)** |
|---|---|---|
| Cobertura | 17–21 números (3 centros) | **14 números (C1/C2 variável + C3 fixo)** |
| Seleção de regiões | C1+C2+C3 sempre | **C1 ou C2 (voto últimas-3-não-C3) + C3 fixo** |
| Motor de seleção | offsets sigmoid/KDE (geometria) | **`CSelectionEngine`** (shadow+bandit, por sentido) |
| Staking | Anti-Martingale 1/2/3 (17/34/51), streak global | **Block-gale isolado/sentido, ×1/2/4/8, 2-de-4** |
| "Só após green" | não existe | **toggle opcional por sentido** |
| Teto de gale | fixo (G3, com cut p/ G2) | **governado por risco (flat default; G2/G3/G4 opt-in)** |
| Persistência | `MartingaleState` + `adaptive_state` | + `c_selection` + `block_gale` em `adaptive_state` |
| UX gale | overlay único | **painel por sentido + toggles + banca** |

**Evidência que ancora o alvo (de `resultados_15_junho.md`):** 14# baixa o breakeven 58,3%→38,9%;
o voto C1/C2 tem edge ≈0 (χ² memoryless); o gale não muda EV e **arruína** (histórico completo
−1.722u/−458u; janela sem filtro quebrou a banca de R$1.000 → R$−96). **Logo o alvo prioriza:
(a) reduzir 21→14, (b) gate de sentido, (c) staking flat — com os motores como infraestrutura
evolutiva segura, não como fonte de "milagre".**

---

## 3. Motor evolutivo C1/C2 variável — `CSelectionEngine`

### 3.1 Responsabilidade e contrato

Recebe os 3 centros da estratégia e o histórico por sentido; devolve **qual par apostar**
(`{C1|C2, C3}`) e os **14 números**, mais telemetria. **Isolado por sentido.** Não altera a
predição de força/centros do SDA17 — é um **pós-processador de cobertura**.

```python
# strategies/c_selection.py  (NOVO)
@dataclass
class CSelection:
    pair: tuple[str, str]          # ('C1','C3') ou ('C2','C3')
    chosen: str                    # 'C1' | 'C2'
    numbers: list[int]             # 14 (união R das 2 regiões)
    rule: str                      # regra vencedora (ex. 'vote_k3_nonc3')
    scoreboard: dict               # {rule: {hits, n, ema}}  (telemetria)
    confidence: float              # 0..1 (largura do IC / sustained)
    reason: str

class CSelectionEngine:
    def select(self, direction: str, centers: list[int],
               attribution_history: list[dict], wheel: list[int],
               radius: int = 3) -> CSelection: ...
    def feedback(self, direction: str, chosen: str, centers: list[int],
                 actual: int, hit_attr: dict) -> None: ...
    def state_dict(self) -> dict: ...          # -> adaptive_state['c_selection']
    def load_state(self, d: dict) -> None: ...
```

### 3.2 Seleção base (voto últimas-3-não-C3) — determinística

Regra `vote_k3_nonc3` (a sua): janela = últimas **3** jogadas cujo resultado caiu **mais perto de
C1/C2 do que de C3** (`min(|d1|,|d2|) < |d3|`); voto = `C1` se `|d1|<|d2|`, `C2` se `|d2|<|d1|`,
e **empate `|d1|==|d2|` = voto NEUTRO (excluído)** — equidistância é ambígua, forçar C2 enviesaria
a taxa-base (bug corrigido, §10 B12). Decide por **maioria estrita**; **sem maioria estrita →
fallback ao incumbente (`always_strong`)**, registrado como `tie`. Aposta = `{vencedor, C3}`;
números = `neighbors(c_win, R) ∪ neighbors(c3, R)` — **N é a união real** (pode ser <14 se C_win e
C3 se sobrepõem na roda; ver §3.5). Reusa exatamente `dist_c1/c2/c3` de `hit_region` (já no DNA /
`last_hit_attribution`).

### 3.3 Camada evolutiva (shadow + bandit + EMA, human-in-the-loop)

O "motor evolutivo" testa **regras candidatas em paralelo (shadow)**, sem apostar, e elege a
incumbente **por sentido** — **reusando o padrão `_update_shadow_ema_on_spin` / bandit**:

- **Candidatos:** `vote_k2/k3/k4/k5_nonc3`, `always_c2`, `always_strong` (a região com maior
  **taxa-base rolante por sentido**, mantida online a partir das atribuições `hit_region` das
  últimas N jogadas), `hot2`, `cold2`.
- **Shadow SEM look-ahead (bug corrigido, §10 B5):** **no momento da decisão** cada candidato
  **congela** sua escolha+números em `pending_prediction.shadow_candidates`; no spin seguinte
  avaliam-se **exatamente essas escolhas congeladas** (`deque(maxlen=100)` por candidato/sentido).
  Nunca recomputar a escolha após conhecer o resultado.
- **Eleição:** bandit ε-greedy (ε=1 cold-start <10 obs; ε=0,10 maduro) + `sustained` counter.
- **Promoção human-in-the-loop:** só troca a incumbente quando `n ≥ min_n` (realista: **≥150
  apostas/candidato/sentido**, não 100 spins) **e** o **intervalo de Newcombe da DIFERENÇA de duas
  proporções** (incumbente vs candidato) **exclui 0** — **não** comparar dois IC95 isolados, que é
  um erro estatístico (CIs podem se sobrepor e a diferença ainda ser significativa; ref. Newcombe
  1998). Opt-in via `settings.c_selection_auto_promote_enabled` (default **False**).
- **Convergência graciosa (esperada):** como o sinal é ~0 (memoryless) e n é pequeno, o guardrail
  **quase nunca** dispara → o motor **fica em `always_strong`** (a melhor dupla por sentido). É o
  comportamento **correto e seguro** — o motor é **shadow-only** até centenas de amostras
  prospectivas; **não se promete "convergência" operacional com 100 spins**.

### 3.4 Estado / persistência

`state.json::adaptive_state['c_selection']`:
```json
{ "cw": { "incumbent": "always_strong",
          "candidates": { "vote_k3_nonc3": {"hits":[...], "ema": 0.004, "n": 100}, ... },
          "sustained": 0, "suggested": {"rule": "...", "applied": false, "ts": 0} },
  "ccw": { ... } }
```
Telemetria por decisão em `decision_dna`: features novas `c_pair_chosen`, `c_rule`,
`c_scoreboard` (compacto), reaproveitando `dna_log_feature`.

> **Serialização (bug corrigido, §10 B7):** `candidates[*].hits` é `deque(maxlen=100)` e **não é
> serializável em JSON**. `state_dict()` converte deques → listas; `load_state()` reconstrói
> `deque(lista, maxlen=100)`. **Reset (bug corrigido, §10 B8):** `reset_session()` (troca de
> dealer/mesa) deve **limpar** `adaptive_state['c_selection']` e `['block_gale']` (inclusive blocos
> abertos e `last_green`), igual ao que já faz com `shadow_ema`/`bandit`. Teste de round-trip
> `save→load` e de dealer-change.

### 3.5 Guardrails

- **N é a união real (bug corrigido, §10 B10):** se `C_win` e `C3` se sobrepõem na roda
  (`|C_win−C3| ≤ 2R` ⇒ união <14), **aceita-se N variável** — `hit = actual ∈ final_numbers`,
  `pnl_units` usa `len(final_numbers)` (já é o cálculo de `update_result`). **Não** se afirma
  breakeven fixo de 14. Se for desejado padronizar 14, o filler deve ser marcado `FILLER` na
  telemetria (não pertence a C1/C2/C3) para não contaminar `hit_region`/`shadow_green`.
- Se `attribution_history < 3` não-C3 → usa `always_strong` (calibração).
- Respeita INV-3: sempre devolve uma cobertura (nunca "sem indicação").

---

## 4. Motor evolutivo do Gale — `BlockGaleEngine`

### 4.1 Block-gale isolado por sentido

Novo estado por sentido (não substitui o `MartingaleState` existente; entra atrás de
`SDA_STAKING_MODE='block_gale'` — **novo valor do enum**, a adicionar em `app_config.settings.
staking_mode()`, hoje `gale|flat|kelly` com default `gale`):

```python
# state/block_gale.py  (NOVO)
@dataclass
class BlockGaleState:
    direction: str
    level: int = 1                 # 1..cap
    cap: int = 1                   # 1=flat, 2=G2, 3=G3, 4=G4
    block_bets: int = 0            # 0..4  (conta SÓ apostas colocadas)
    block_wins: int = 0
    last_green: bool | None = None # p/ "só após green"
    base_unit: float = 1.0
    MULT = {1:1, 2:2, 3:4, 4:8}

    def should_place(self, only_after_green: bool) -> bool:
        return True if not only_after_green else (self.last_green is True)
    def stake(self) -> float: return self.base_unit * self.MULT[self.level]
    def on_result(self, green: bool, placed: bool) -> dict:
        # SEMPRE atualiza last_green = green (sombra de toda jogada).
        # Só conta o bloco se placed=True (bug corrigido §10 B2):
        #   a cada 4 apostas COLOCADAS: >=2 wins -> level=1;
        #   <=1 -> sobe ate cap; no cap, falha -> level=1 (reinicia, aceita loss).
        ...
```

**Regras exatas (validadas no backtest):** blocos de **4 apostas COLOCADAS** (não spins); **≥2
vitórias → reset/permanece G1**; **≤1 → sobe** (G1→G2→G3→G4 até o teto); **no teto, falha →
reinicia em G1 e aceita o loss**. Stake `×1/2/4/8`. **Isolado por sentido** (dois `BlockGaleState`).

### 4.2 "Só jogar após green" (como **stake-gate**, sem violar INV-3)

Flag `GALE_ONLY_AFTER_GREEN` (por sentido). O **resultado-sombra** da sugestão (green/red da dupla
de 14#) é computado **todo spin** (já temos via `hit_region`), atualizando `last_green`.

> **Correção INV-3 (bug §10 B1):** o "só após green" é um **stake-gate**, **não** uma supressão.
> Quando `last_green` ≠ True, a indicação **continua** com `acao="APOSTAR"` (mesmos números) e
> **stake = 0 (papel)** — o operador vê a sugestão, mas o motor marca `placed=False`. **Não** se
> cria `acao="AGUARDAR_GREEN"` (o `content.js:401-407` só mapeia APOSTAR/PULAR/else → cairia no
> genérico e perderia o alerta). O estado "aguardando green" viaja num **campo aditivo**
> `bet_gate{only_after_green, gated:true, reason}`, renderizado pelo painel novo. Como `placed=False`,
> o **bloco do gale não conta** essa jogada (coerente com o backtest §9.4) e o P&L não muda.

### 4.3 Limitador de risco (o "evolutivo" do gale, **walk-forward**)

Como o gale **não muda o EV** e o teto alto **arruína** (provado), este componente é um
**limitador de risco**, **não** um otimizador de edge:
- **Walk-forward, sem look-ahead (bug §10 B4):** o teto do **próximo** bloco é decidido só com
  dados **anteriores** (prequential); a recomendação é avaliada **out-of-sample**, nunca na mesma
  janela em que vai apostar. Simula `flat/G2/G3/G4` sobre o histórico **já resolvido** do sentido e
  estima `max-drawdown` e `P(ruína)` vs a banca atual.
- **Default e recomendação automática = SEMPRE `flat`.** Tetos >1 são **opt-in explícito** do
  operador (UI, com aviso de ruína); o limitador **nunca sobe o teto sozinho** — só pode **baixá-lo**
  (proteção). Promoção de teto é human-in-the-loop.
- **Guardrail duro:** se `session_pnl < −stop_loss` **ou** drawdown projetado > X% da banca →
  **força flat** (override, reusa o stop-loss B5 existente).

### 4.4 Estado / persistência (reuso de `gale_windows`)

`adaptive_state['block_gale'] = {cw:{level,cap,block_bets,block_wins,last_green,base_unit},
ccw:{...}, governor:{recommended_cap_cw, recommended_cap_ccw, drawdown_est}}`. Cada **bloco
fechado** é auditado em `gale_windows`/`window_plays` (reuso do lifecycle existente, com
`result` ∈ {reset, escalate, cap_reset}). P&L por sentido em `sessions`/`pnl_units`.

### 4.5 Guardrails (anti-ruína)

- Teto **default flat**; subir exige opt-in + limitador (§4.3).
- **`base_unit` correto (bug §10 B6):** o pior caso é um **bloco G4 = 4 apostas × ×8 × N números**.
  Para não exceder a banca num bloco: `base_unit ≤ banca / (N × 8 × 4)` ≈ **0,22%/número** numa
  banca de R$1.000 (não 0,5%, que daria R$2.240 > banca). Recomenda-se margem ainda menor.
- **Solvência (bug §10 B6/B14):** o motor **recusa** qualquer aposta cujo `stake > banca atual`
  (no backtest §9.5 a banca foi a R$−96 porque a simulação não tinha essa trava; **produção não
  pode apostar a descoberto**). `base_unit` é **derivado da banca viva** (recalculado por sessão).
- Stop-loss B5 já existente força `level=1`/stake mínimo.
- Telemetria de **drawdown e maior gale atingido** por sentido (Prometheus + UX).

### 4.6 Interface

```python
class BlockGaleEngine:
    def __init__(self, base_unit, caps={'cw':1,'ccw':1}, only_after_green=False): ...
    def decide(self, direction, shadow_green, bankroll) -> dict: # {place, stake, level, cap}
                                                                 # place=False se !solvente ou gate
    def on_result(self, direction, green, placed) -> dict        # só conta bloco se placed=True
    def governor_recommend(self, direction, resolved_history, bankroll) -> int  # teto, walk-forward
    def state_dict(self)/load_state(self)   # deques->listas; reset_session limpa o estado
```

---

## 5. Acoplamento dos dois motores (pipeline por spin)

```
NOVO_RESULTADO
  └─ resolve spin t-1:
       hit_attr = _attribute_hit_region(centers_{t-1}, actual_t)   # dist_c1/c2/c3, slot
      shadow_green_{t-1} = (actual_t ∈ par_escolhido_{t-1})        # dupla de 14# CONGELADA em t-1
      # avalia escolhas CONGELADAS dos candidatos (pending.shadow_candidates) — sem look-ahead
      CSelectionEngine.feedback(dir, frozen_choices_{t-1}, actual_t, hit_attr)
      BlockGaleEngine.on_result(dir, shadow_green_{t-1}, placed=pending.bet_placed_{t-1})
      persist (decisions.update_result + DNA realized + gale_windows)
  └─ decide spin t:
      result = strategy.analyze(...)                              # centers=[c1,c2,c3], 21#
      sel = CSelectionEngine.select(dir, result.centers, attr_hist, wheel, R)  # {C?,C3}+N≤14#
      gale = BlockGaleEngine.decide(dir, shadow_green=last_green, bankroll=banca)  # {place,stake,..}
      acao, stake = INV3_modulate(sel, gale, stop_loss, cut)      # acao=APOSTAR sempre; stake↓
      store_prediction(numbers=sel.numbers, centers=[c_win, c3],
                       bet_placed=(gale.place and stake>0),        # placed = aposta REAL
                       shadow_candidates=sel.frozen_choices)       # congela p/ feedback s/ leak
      emit sugestao + state_sync (campos novos: c_selection, block_gale por sentido, bet_gate)
```

**Como os motores conversam:** o **resultado-sombra (green/red da dupla de 14#)** é o **contrato
comum** — alimenta o `feedback` do `CSelectionEngine` (em escolhas **congeladas**), o stake-gate
"só após green" e o bloco do `BlockGaleEngine` (que **só conta `placed=True`**). Tudo derivado de
`hit_region`. **A ordem importa:** `feedback`/`on_result` de t-1 ocorrem **antes** do `select`/`decide`
de t (a janela do voto já inclui t-1 resolvido). O **stake do gale flui para `stake_info`/
`gale_bet_value`** para o `pnl_units` refletir o ×mult. Acoplamento **fraco e auditável**: cada
motor tem estado próprio em `adaptive_state`, comunica-se por um booleano.

---

## 6. Infraestrutura de dados — evolução

### 6.1 Reusar (sem migration)
- `decision_dna.hit_region` (`dist_c1/c2/c3`) → entrada do voto e do shadow-green.
- `state.json::adaptive_state` → estado quente dos dois motores (segue `save()` atômico).
- `gale_windows`/`window_plays` → auditoria de blocos do block-gale.
- `sessions.total_profit`/`pnl_units` → banca/drawdown por sentido (já calculado em `update_result`).

### 6.2 Migration `0009_c_selection_gale` — **dual-path SQLite + Alembic/PG** (bug §10 B9)
O sistema faz **dual-write** (SQLite local + Postgres `shared.` via outbox). A migration precisa
dos **dois caminhos**, senão as colunas existem num backend e não no outro:
```sql
-- (1) Alembic 0009 (PG, schema shared):
ALTER TABLE shared.decisions ADD COLUMN bet_pair TEXT;       -- 'C1+C3' | 'C2+C3' | 'full'
ALTER TABLE shared.decisions ADD COLUMN gale_cap INTEGER;    -- 1..4 (teto vigente)
ALTER TABLE shared.decisions ADD COLUMN shadow_green INTEGER;-- 0/1 (gravado na RESOLUÇÃO)
-- (2) Auto-migration SQLite em sqlite_repo.py (ADD COLUMN idempotente p/ DB legado);
-- (3) atualizar o modelo Decision + INSERT/SELECT + payload do outbox;
-- features de telemetria (c_pair_chosen, c_rule, c_scoreboard, gale_level_block) entram como
--   feature_name no decision_dna (EAV, SEM DDL) via dna_log_feature.
```
*Princípio:* a maior parte da telemetria é **EAV no `decision_dna` (sem DDL)**; só 3 colunas em
`decisions` justificam migration (filtros rápidos). `shadow_green` é gravado na **resolução** do
spin (como `result_region`/`pnl_units`), não na criação. **Nenhuma tabela nova no caminho de
decisão.** Teste obrigatório: SQLite legado **sem** as colunas → auto-migrate não quebra.

### 6.3 Persistência quente
`adaptive_state['c_selection']` e `['block_gale']` adicionados ao `save()`/`load()` de
`GameState` (mesma serialização já usada para `shadow_grid`/`suggested_shift`).

---

## 7. UX / Frontend

### 7.1 Painel de gale por sentido (dados já trafegam)
`state_sync` já envia `martingale_cw`/`martingale_ccw` + `window_history` a cada 1s — adicionar
`block_gale_cw`/`block_gale_ccw` (level, cap, block 2/4, banca, drawdown). Novo componente em
`popup.html`/`content.js`:
```
↻ HORÁRIO            ↺ ANTI-HORÁRIO
G2 ×2  bloco 3/4     G1 ×1  bloco 1/4
banca R$ 1.116       banca R$ 1.120
maxDD −R$ 70         maxDD −R$ 84
```
Cores reaproveitam `overlay.css` g1/g2/g3 (+ g4 nova).

### 7.2 Toggle "só após green" + seletor de teto
Seguindo o padrão do toggle auto-start (`popup.js` + `background.js` config handler →
mensagem `set_config` ao servidor):
- **Toggle "Só jogar após green"** (por sentido ou global) → `GALE_ONLY_AFTER_GREEN`. Quando
  *gated*, o overlay mantém `acao=APOSTAR` mas exibe um **badge "aguardando green"** (do campo
  `bet_gate`), e o stake mostrado vai a 0/papel — **não** suprime a indicação (INV-3).
- **Seletor de teto** (Flat / G2 / G3 / G4) com **aviso de risco** ("G4 = ×8, risco de ruína" —
  ancorado no §9.6 do estudo). Default **Flat**; subir o teto é opt-in do operador.

### 7.3 Display C1/C2 escolhido + placar de candidatos
No overlay (`content.js`): destacar **qual par** está apostado (`[C1]·[C3]` ou `[C2]·[C3]`) e um
mini-placar dos candidatos do `CSelectionEngine` (regra incumbente + edge), vindo de
`sugestao.c_selection`.

### 7.4 Mensagens server→client (campos novos, aditivos)
`sugestao.data` e `state_sync.data` ganham (a extensão ignora campos desconhecidos):
```json
"c_selection": {"chosen":"C1","pair":"C1+C3","rule":"always_strong","edge":0.004,"confidence":0.2,
                "n_real": 14},
"bet_gate": {"only_after_green": true, "gated": true, "reason": "última foi red"},
"block_gale": {"cw":{"level":2,"cap":1,"block":"3/4","banca":1116,"maxdd":-70,"placed":true},
               "ccw":{...}}
```
`acao` permanece no enum existente (APOSTAR/PULAR/AGUARDAR); o estado "aguardando green" e o teto
viajam em **campos aditivos** (`bet_gate`, `block_gale`) — a extensão ignora desconhecidos e o
contrato do overlay não quebra.

---

## 8. Plano de implantação (sprints, flags, testes, observabilidade)

| Sprint | Entrega | Flag(s) | Shadow-first? | Testes |
|---|---|---|---|---|
| **SP-A** | Cobertura N≤14 `{C?}+C3` + voto base nonC3 (determinístico) | `SDA_BET_PAIR=var_c1c2_c3` | parcial | `test_c_selection_vote.py` (voto, cobertura união real, empate=tie→incumbente) |
| **SP-B** | `CSelectionEngine` evolutivo (shadow congelado+bandit+EMA, telemetria DNA) | `C_SELECTION_AUTO_PROMOTE=0` | **sim** | `test_c_selection_engine.py` (shadow não aposta; guardrail Newcombe; convergência p/ always_strong; round-trip save/load) |
| **SP-C** | `BlockGaleEngine` isolado/sentido + `SDA_STAKING_MODE=block_gale` + só-após-green (stake-gate) | `SDA_STAKING_MODE`, `GALE_ONLY_AFTER_GREEN` | **sim (paper)** | `test_block_gale.py` (blocos 2-de-4 só `placed`, ×1/2/4/8, reset no teto, isolamento cw/ccw, solvência) |
| **SP-D** | Limitador de risco walk-forward + guardrails (teto, stop-loss, base_unit, solvência) | `GALE_CAP`, `GALE_GOVERNOR=0` | **sim** | `test_gale_governor.py` (default flat; nunca sobe sozinho; força flat em stop-loss; recusa aposta a descoberto) |
| **SP-E** | UX: painel gale/sentido, toggles, seletor teto, placar C1/C2 | — | — | `test_state_sync_fields.py`, smoke da extensão |
| **SP-F** | Migration `0009` + métricas Prometheus + Grafana | — | — | `test_migration_0009.py`, `test_prom_block_gale.py` |

**Princípios de implantação:**
- **Tudo atrás de flag, default = comportamento atual** (21# + anti-mart) até validar.
- **Shadow-first:** os motores **observam e logam** antes de tocar dinheiro; promoção
  human-in-the-loop (opt-in).
- **Métricas** seguindo o padrão `health_server._PROM_METRICS` + provider no boot (cache 30s) +
  alerta em `obs/alerts.yml`: `c_selection_incumbent`, `c_selection_edge_ema`, `block_gale_level`,
  `block_gale_maxdd`, `block_gale_ruin_total`.
- **Deploy** pelo fluxo padrão (push main → CI → `roleta-deploy` timer; DB protegido).

---

## 9. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Motor C1/C2 "aprender" ruído e oscilar | Guardrail **Newcombe** (diferença de proporções) + `min_n`≥150 + human-in-the-loop; converge p/ `always_strong`; shadow-only até centenas de amostras |
| Block-gale arruinar a banca | Default **flat**; limitador walk-forward + stop-loss B5 + `base_unit` **≤0,22%/número** + **trava de solvência** (não aposta a descoberto); aviso UX |
| Quebrar INV-3 (ficar sem indicação) | Ambos sempre devolvem cobertura; "só após green" é **stake-gate** (acao=APOSTAR, stake↓), nunca supressão |
| Acoplamento frágil | Contrato único = resultado-sombra (bool); estado isolado por motor em `adaptive_state` |
| Geometria real ≠ R=3 | Definir se 14# remove C1 (raio 1) ou mantém como bônus; flag de raio |
| Replay/backfill corromper telemetria | Dedup por `(spin_number, dist_c1/c2/c3)` na ingestão (lição do `decisions.db` 15/06) |
| Amostra pequena (100/sentido) | Coletar +200–300 spins limpos/sentido antes de promover qualquer teto/regra |

---

## 10. Auditoria de bugs do design (pré-implementação) e correções

> Revisão dupla: auditoria própria (verificada contra o código) + revisor independente
> (rubber-duck, gpt-5.5). **13 achados**, todos com correção **já aplicada** nas seções acima.
> Cada bug aponta a seção corrigida.

### 10.1 Bloqueantes (mudam o design)

| # | Bug | Por que é perigoso | Correção aplicada |
|---|---|---|---|
| **B1** | "Só após green" criava `acao="AGUARDAR_GREEN"` + stake 0 | `content.js:401-407` só mapeia APOSTAR/PULAR/else → cairia no genérico e **perderia o alerta**; suprimir aposta **viola INV-3** | **Stake-gate**: `acao=APOSTAR` + stake→0 (papel) + campo aditivo `bet_gate`; bloco só conta `placed=True` (§4.2, §5, §7.2/7.4) |
| **B2** | `on_result(green)` contava bloco em spins **sem aposta** | Com "só após green"/stake-gate, escalaria o gale com apostas inexistentes → P&L e `gale_windows` inválidos | API `on_result(green, placed)`; `block_bets/wins` só se `placed`; `pending.bet_placed` no fluxo (§4.1, §4.6, §5) |
| **B3** | `STAKING_MODE=block_gale` | Env var real é `SDA_STAKING_MODE`, enum `gale\|flat\|kelly` (default **gale**); valor inválido **cai em `gale`** → acionaria o anti-martingale antigo | Renomeado p/ `SDA_STAKING_MODE`; "block_gale" **a adicionar ao enum**; flat exige config explícita (§0, §4.1, §8) |
| **B4** | Limitador escolhia teto na **janela recente** (in-sample) | **Data leakage**: pareceria reduzir drawdown por ter visto o resultado; sem poder preditivo | **Walk-forward/prequential**; teto só com dados anteriores; default e auto = **flat**; nunca sobe sozinho (§4.3, §4.6) |
| **B5** | Candidatos do shadow recalculados após o resultado | **Look-ahead**: hit-rate/EMA/bandit artificialmente inflados | Escolhas **congeladas** em `pending.shadow_candidates` no momento da decisão; avaliação das congeladas (§3.3, §5) |
| **B6** | `base_unit ≤0,5%/número` "não estoura a banca" | **Falso**: banca R$1.000 → bloco G4 = 14×R$5×8×4 = **R$2.240 > banca** | `base_unit ≤ banca/(N×8×4)` ≈ **0,22%/número** + **trava de solvência** (recusa aposta > banca) + base derivado da banca viva (§4.5) |

### 10.2 Não-bloqueantes (robustez/correção)

| # | Bug | Por que importa | Correção aplicada |
|---|---|---|---|
| **B7** | `deque(maxlen=100)` em `adaptive_state` | `json.dump()` **quebra** com deque; virar lista sem `maxlen` cresce sem limite | `state_dict()` deque→lista; `load_state()` reconstrói `deque(maxlen)`; teste round-trip (§3.4) |
| **B8** | `reset_session()` não limpava os novos motores | Contamina sinais/blocos/`last_green`/cap entre **dealers/mesas** (bug já corrigido p/ shadow/bandit) | `reset_session` limpa `c_selection`+`block_gale` (§3.4) |
| **B9** | Migration só `ALTER TABLE decisions` | Sistema é **dual-write** SQLite+PG; colunas existiriam num backend só | Migration **dual-path**: Alembic PG `shared.` + auto-migrate SQLite + modelo/insert/select/outbox + teste DB legado (§6.2) |
| **B10** | "Sempre 14 números" + filler | União real pode ser **<14** se C_win∩C3; filler não pertence a C1/C2/C3 e contamina `hit_region` | **N variável**: `hit=actual∈final_numbers`, P&L usa `len`; não afirma breakeven fixo; filler marcado se usado (§3.2, §3.5) |
| **B11** | Guardrail "IC95 da diferença exclui 0" + maturação com n≈30-36 | Comparar dois IC95 isolados é **erro estatístico** (Cumming/Newcombe); n pequeno **nunca matura** | **Intervalo de Newcombe** da diferença de proporções; `min_n`≥150; shadow-only; não promete convergência com 100 spins (§3.3) |
| **B12** | Empate do voto → C2 | Equidistância é **ambígua**; forçar C2 enviesa a taxa-base e os rótulos do shadow | Empate = **voto neutro/excluído**; sem maioria estrita → **incumbente** (`always_strong`), logado `tie` (§3.2) |
| **B13** | Gale posicionado como "governador que escolhe o melhor teto" | Sugere edge onde **não há** (gale não muda EV; arruína) | Renomeado **limitador de risco**; default/auto sempre flat; teto>1 = opt-in com aviso (§0, §4.3) |

**Itens de contrato também endereçados:** ordem `feedback/on_result(t-1)` **antes** de
`select/decide(t)`; `always_strong` = **taxa-base rolante por sentido** das atribuições `hit_region`;
o **stake do gale flui para `stake_info`/`gale_bet_value`** para `pnl_units` refletir o ×mult;
`shadow_green` gravado na **resolução** (não na criação) da decisão.

---

## 11. Sprints de PRÉ-implementação (de-risking antes de tocar produção)

> Estes sprints **vêm antes** dos sprints de feature (§8). Objetivo: **destravar os bugs do §10,
> montar o aparato de validação e os contratos** — sem ainda apostar dinheiro. Cada item diz **o
> que muda**, **por que vale a pena** e o **ganho (tecnologia / usabilidade)**.

### SP-0 · Harness de simulação canônico (fundação)
- **O que muda:** extrair o simulador usado em `resultados_15_junho.md` (voto nonC3, block-gale,
  governador) para um módulo testável `tools/sim_engine.py`, com **paridade byte-a-byte** com os
  números do estudo (horário 256/anti 1472 no G4; flat 716/896).
- **Por que vale:** vira a **fonte única de verdade** para backtest, governador walk-forward e
  testes — elimina divergência entre "doc" e "código".
- **Ganho:** *Tecnologia* — backtest reprodutível e CI-able; *Usabilidade* — números do painel
  batem com o estudo, confiança do operador.

### SP-1 · Contrato de dados + telemetria (sem mudar aposta)
- **O que muda:** migration `0009` **dual-path** (B9); features DNA `c_pair_chosen/c_rule/
  c_scoreboard/shadow_green/gale_*`; `shadow_green` gravado na resolução; dedup anti-replay
  `(spin_number, dist_c1/c2/c3)`.
- **Por que vale:** sem telemetria correta **não dá para validar** os motores em shadow; o replay
  de 15/06 provou que dados sujos invalidam tudo.
- **Ganho:** *Tecnologia* — observabilidade desde o dia 0, DB legado não quebra; *Usabilidade* —
  base limpa para dashboards e auditoria.

### SP-2 · `CSelectionEngine` em SHADOW puro (não muda cobertura)
- **O que muda:** implementar o motor (voto nonC3 + candidatos congelados + Newcombe + persistência
  com deque↔lista + reset_session) rodando **só como sombra/telemetria**; aposta segue 21#.
- **Por que vale:** valida B5/B7/B8/B11/B12 com dados reais **sem risco**; mede o edge real do voto
  prospectivamente (esperado ~0).
- **Ganho:** *Tecnologia* — A/B prospectivo seguro; *Usabilidade* — placar de candidatos visível
  (transparência da decisão).

### SP-3 · Cobertura 14# atrás de flag (primeira mudança de aposta)
- **O que muda:** `SDA_BET_PAIR=var_c1c2_c3` passa a montar `{C_win, C3}` com **N=união real**
  (B10); `pnl_units`/`hit` por `final_numbers`; default continua 21#.
- **Por que vale:** entrega o **principal lever** (21→14, breakeven 58,3%→38,9%) de forma
  reversível e medível.
- **Ganho:** *Tecnologia* — EV correto com N variável; *Usabilidade* — overlay mostra o par
  C1/C2 escolhido + C3 fixo (clareza).

### SP-4 · `BlockGaleEngine` em PAPEL (paper-trading)
- **O que muda:** motor isolado por sentido com `decide(...,bankroll)`/`on_result(green,placed)`,
  stake-gate "só após green" (B1/B2), **trava de solvência** e `base_unit` correto (B6);
  `SDA_STAKING_MODE=block_gale` adicionado ao enum (B3) — mas rodando **flat/papel**.
- **Por que vale:** valida toda a mecânica do gale (blocos, ×mult, isolamento, ruína) **sem
  arriscar banca**, reproduzindo o §9.x ao vivo.
- **Ganho:** *Tecnologia* — gale auditável em `gale_windows`; *Usabilidade* — painel de gale por
  sentido com banca/drawdown reais.

### SP-5 · UX dos painéis + toggles (consumindo o que já trafega)
- **O que muda:** painel **gale por sentido** (de `state_sync`), **toggle "só após green"**
  (stake-gate, badge `bet_gate`), **seletor de teto** com aviso de risco, **placar C1/C2**.
- **Por que vale:** o operador precisa **ver e controlar** o que os motores fazem; o canal
  `state_sync` já carrega quase tudo (custo baixo).
- **Ganho:** *Tecnologia* — campos aditivos, sem quebrar o overlay; *Usabilidade* — controle
  isolado por sentido, decisão explicável, risco do gale **explícito**.

### SP-6 · Limitador de risco walk-forward + guardrails finais
- **O que muda:** limitador (B4/B13) que **só baixa** o teto; integração com stop-loss B5;
  `min_n`/Newcombe ligando a promoção human-in-the-loop (opt-in, default off).
- **Por que vale:** transforma o gale de "loteria" em **risco governado**; o default permanece
  flat (a recomendação honesta do estudo).
- **Ganho:** *Tecnologia* — proteção de banca formal; *Usabilidade* — operador sobe teto só
  conscientemente, com guardrail que nunca o trai.

### SP-7 · Go-live gradual (canary)
- **O que muda:** ativar `var_c1c2_c3` + `block_gale` flat por sentido em **canary** (1 mesa),
  comparar P&L/hit vs 21#/anti-mart por N spins antes de ampliar.
- **Por que vale:** decisão de adoção baseada em **dado prospectivo limpo**, não no recorte de 100.
- **Ganho:** *Tecnologia* — rollout reversível com métricas; *Usabilidade* — migração sem
  surpresa para o operador.

**Resumo dos ganhos (por que vale a pena tudo isso):**
- **Tecnologia:** −33% de exposição por aposta (21→14) com EV correto; motores **shadow-first**
  reusando shadow-grid/bandit/`gale_windows`/`staking_mode` já existentes (baixo custo, alto
  acoplamento com o que há de melhor); telemetria e guardrails que **eliminam ruína por construção**
  (solvência + default flat); backtest reprodutível (SP-0) e DB dual-write consistente.
- **Usabilidade:** decisão **explicável** (par C1/C2 + placar), **controle por sentido** do gale,
  risco **explícito** (aviso de ×8), e nenhuma quebra do overlay (campos aditivos, INV-3 intacto).

---

## 12. Implementação realizada (16/06/2026) — camada de motores (shadow-first)

> **Princípio:** entregou-se a **fundação segura e reversível** dos dois motores como **módulos
> isolados, default-OFF, NÃO acoplados ao caminho quente** (a wiring no `message_handler` que muda
> a aposta ao vivo fica para os sprints de canário §11/SP-7, conforme o design exige). Resultado:
> **zero impacto no comportamento de produção** até que as flags sejam ligadas.

### 12.1 Arquivos criados/alterados
| Arquivo | Tipo | Conteúdo |
|---|---|---|
| `state/block_gale.py` | **novo** | `BlockGaleState` + `BlockGaleEngine` (gale isolado/sentido, blocos de 4, 2-de-4, ×1/2/4/8, stake-gate "só após green", solvência, reset, serialização) |
| `strategies/c_selection.py` | **novo** | `CSelectionEngine` (voto últimas-3-não-C3, cobertura união real, candidatos congelados, Newcombe, persistência deque↔lista, reset) |
| `app_config/settings.py` | **alterado** | `staking_mode()` aceita `block_gale`; novos getters `bet_pair_mode()`, `gale_only_after_green()`, `gale_cap()`, `c_selection_auto_promote_enabled()` — **todos default OFF** |
| `tests/test_block_gale.py` | **novo** | 11 testes (regras, isolamento, solvência, stake-gate, round-trip, clamp) |
| `tests/test_c_selection.py` | **novo** | 17 testes (voto, empate, cobertura, Newcombe, feedback congelado, None-safe, promoção, reset) |

### 12.2 Flags (env), default = comportamento atual
- `SDA_BET_PAIR` = `full` (default) | `var_c1c2_c3` | `c1c3` | `c2c3`
- `SDA_STAKING_MODE` = `gale` (default) | `flat` | `kelly` | `block_gale`
- `GALE_ONLY_AFTER_GREEN` = `0` (default)
- `GALE_CAP` / `GALE_CAP_CW` / `GALE_CAP_CCW` = `1` (flat, default)
- `C_SELECTION_AUTO_PROMOTE` = `0` (default)

### 12.3 Validação
- **`tests/test_block_gale.py` + `tests/test_c_selection.py`: 28 passed.**
- **Suíte completa: 513 passed, 9 skipped, 1 xfailed** (warnings = deprecations pré-existentes de
  `websockets`). **Zero regressão** — a única mudança em código existente é aditiva em `settings.py`.

### 12.4 O que NÃO foi feito (de propósito)
Wiring no `message_handler` (mudar a cobertura/staking ao vivo), migration `0009`, e UX da extensão
— ficam para os sprints de feature (§8) executados **após** a validação shadow/canário, porque
tocam dinheiro real. A fundação aqui é **pré-requisito testado** desses sprints.

### 12.5 Como testar no Debian AGORA (sem tocar produção)
Os motores ainda **não estão ligados** ao servidor (caminho quente). Para validar a lógica de ponta
a ponta no Debian, há duas formas isoladas e seguras (read-only):
```bash
git fetch && git checkout feat/c-variavel-block-gale
# 1) testes unitários (28 dos motores; 513 no total):
python -m pytest tests/test_block_gale.py tests/test_c_selection.py -q
# 2) harness de ponta a ponta (mostra seleção C1/C2 + 14# + gale + banca por sentido):
python tools/sim_c_gale.py --db data/decisions_prod_1206b.db --n 100 --cap 4 --verbose
python tools/sim_c_gale.py --cap 1 --only-after-green      # flat + só-após-green (sintético)
```
`tools/sim_c_gale.py` roda `CSelectionEngine` + `BlockGaleEngine` exatamente como em produção, mas
**fora do servidor** (não escreve no DB, não muda aposta). É o que permite "ver funcionando" antes
do wiring. **Para rodar dentro do fluxo real (Escuta→servidor) ainda falta o wiring (§8/SP-3/SP-4)**,
que muda lógica de aposta e exige revisão/canário.

---

## 13. 2ª sprint de auditoria — pós-implementação (bug hunt no código novo)

> Revisão dupla do código recém-escrito: **code-review independente** (agente, all-tools) +
> auditoria própria. **6 bugs** encontrados e **corrigidos + cobertos por teste**.

### 13.1 Achados próprios (durante a escrita)
| # | Arquivo | Bug | Correção |
|---|---|---|---|
| I-A | `c_selection.py` | `IndexError` se `centers` < 3 (fallback early-session do SDA17) | guard em `select()` → cobertura degradada sem quebrar (`test_select_handles_fewer_than_3_centers`) |
| I-B | `c_selection.py` | `KeyError`/`abs` em atribuição sem `dist_c2/c3` | `.get` + coalescência (depois reforçado por I-2) |

### 13.2 Achados do code-review independente
| # | Sev | Arquivo | Bug | Correção |
|---|---|---|---|---|
| **I-1** | Alto | `c_selection.py` | `MAXLEN=100 < MIN_N_PROMOTE=150` → a deque satura em 100, e a **promoção NUNCA dispara** (feature evolutiva morta); `confidence` saturava em 0,67 | `MAXLEN=200` (≥ `MIN_N_PROMOTE`); `test_autopromote_fires_with_clear_winner` prova que **promove** e `confidence` chega a 1,0 |
| **I-2** | Alto | `c_selection.py` | `_attribute_hit_region` põe `dist_c2/c3 = **None**` (chave existe!) → `abs(None)` quebra `feedback`/`_vote_window` na 1ª jogada de fallback/miss | helper `_ad(x)=abs(x) if x is not None else 99`; `test_tolerates_none_distances` |
| **I-3** | Médio | `block_gale.py`, `c_selection.py` | `from_dict` clampava `cap` mas **não `level`** → `KeyError MULT[level]` em state corrompido/restaurado; `load_state` aceitava `incumbent` inválido → `KeyError` | clamp `level`∈1..4; valida `incumbent ∈ CANDIDATE_RULES`; `test_load_state_clamps_corrupt_level`, `test_load_state_rejects_invalid_incumbent` |

**Verificado correto pelo revisor (sem issue):** contagem de bloco (só `placed`), `last_green` em
toda jogada, flat nunca escala, trava de solvência, fórmula de **Newcombe** (método 10), união de
cobertura (N variável), feedback em escolhas **congeladas** (sem look-ahead), round-trip deque↔lista
(maxlen preservado), `_dk` consistente entre módulos, determinismo, e os getters de `settings.py`.

### 13.3 Estado final
**28 testes dos motores + 513 da suíte, todos verdes.** Os motores estão **prontos para wiring
shadow/canário** (§11) — nenhum bug bloqueante remanescente.

---

## 14. Sprint de deploy + GitHub

### 14.1 O que foi executado
- **Branch:** `feat/c-variavel-block-gale` (a partir de `main`) — **publicado em `origin`** ✅.
- **Commit:** `0bdad55` — `feat(strategy): motores C1/C2 variavel + Block-Gale (shadow-first, default OFF)`.
- **Pull Request:** **#8 aberto** → https://github.com/ivandirfilho/roleta-cloud/pull/8 (revisão) ✅.
- **Arquivos no commit (6, só os da implementação):** `app_config/settings.py`,
  `state/block_gale.py`, `strategies/c_selection.py`, `tests/test_block_gale.py`,
  `tests/test_c_selection.py`, `implantação_c_variavel_gale_junho.md`.
- **Deixados de fora de propósito:** o working tree tinha mudanças **não relacionadas** de
  sessões anteriores (`extension/*`, `scripts/*`, `graphify-out/*`, outros testes/docs) — **não
  foram tocadas** (commit cirúrgico).

### 14.2 Por que é seguro shippar
A camada implementada é **default-OFF e não acoplada ao caminho quente** (os módulos só são
chamados quando as flags forem ligadas + wiring de canário). Logo o **runtime é byte-idêntico**
ao atual ao mergear/subir — risco operacional ~nulo, e totalmente reversível por flag/rollback.

### 14.3 Pendente (HUMANO — irreversível num sistema de dinheiro real)
> Push e PR **feitos**. O que falta é a etapa irreversível, deixada para revisão/decisão humana:
1. **Revisar e mergear o PR #8** em `main` (não auto-mergeado de propósito — é lógica de aposta).
2. **Deploy** auto-segue o merge: `roleta-deploy` (systemd timer, 2min) **ou**
   `systemctl start roleta-deploy.service` (servidor `187.45.181.75`) →
   `git fetch + reset --hard origin/main + docker compose build/up + healthcheck:8766` +
   **rollback `last_good`** em falha. DB protegido. Sobe **inerte** (flags OFF).
3. **Pós-deploy:** confirmar healthcheck `:8766`. Ligar `SDA_BET_PAIR`/`SDA_STAKING_MODE` só na
   fase de canário (§11/SP-7), por mesa, com métricas — **nunca** direto em produção ampla.

### 14.4 Recomendação
Merge **após review** do PR #8; deploy **inerte** (flags OFF) no go-live. Ativação dos motores
segue o §11 (shadow → paper → canário), honrando o veredito do estudo (default flat, gale como
risco governado).

---

## Apêndice — citações de código (auditoria)

**Backend / decisão** — `server/message_handler.py`: `_build_sda_regions` (27-57); martingale
update (214-229); atribuição/DNA `hit_region` (291-327); `analyze()` + INV-3 + `staking_mode`
(415-515); `get_gale` (425-431); overlay `sugestao` (744-778); broadcast `trace` com
`martingale_cw/ccw` (782-815).
**Estado / gale** — `state/game.py`: `MartingaleState` (20-176); `GameState` campos
(179-245); `martingale_cw/ccw` (219-220); `_adaptive_state` (241); `pending_prediction`
(574-586); shadow EMA + auto-promote (588-706); bandit (710+); `save()` (1110-1169).
**Estratégia** — `strategies/sda17.py`: `analyze()`, `update_adaptive()`, `_pct_sigmoid_update()`,
`_batch_auto_tune()` (cadência 4 spins/dir), `get_adaptive_state()`, estado por sentido
(`cw_history`/`ccw_history`/`_sigmoid_off`/`_region_err_hist`/`_region_err_ema`). `strategies/base.py`:
`StrategyResult`. `strategies/region_bandit.py`: `choose_region` (dormente).
**Núcleo** — `core/roulette.py`: `WHEEL_SEQUENCE`, distância circular, `compute_wheel_dist*`.
`state/game.py::_attribute_hit_region` (slot + dist_c1/c2/c3).
**Dados** — `database/service.py` (`save_decision`, `update_result`, `track_gale_window`),
`database/sqlite_repo.py` (`decisions`, `gale_windows`/`window_plays`, `get_gale_stats`,
`get_window_history`, `get_session_pnl`, `update_result` P&L), `database/dna_logger.py`
(`dna_log_feature`, `dna_update_realized`); migrations `0001_baseline`…`0008_decision_dna`.
**Frontend** — `extension/popup.{html,js}` (toggles/seletor de direção/painel financeiro),
`extension/background.js` (WS client, roteador, config toggles), `extension/content.js` +
`overlay.css` (overlay, gale_display, centros). `server/websocket.py` (`state_sync` 1s com
`martingale_cw/ccw`, `window_history`).
**Observabilidade** — `server/health_server.py` (`_PROM_METRICS`), `obs/alerts.yml`,
`obs/grafana/dashboards/roleta-dna-regions.json`.
