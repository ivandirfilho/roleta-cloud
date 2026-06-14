# 💰 flat_kelly_junho — Staking Flat/Kelly por sentido (substituir o Gale)

> **Tipo:** documento de HANDOFF / especificação para sprints. **NÃO contém alterações de código.**
> Outro agente, em outra sessão, vai implementar/testar a partir daqui.
> **Autor da análise:** sessão de auditoria V4 (14/06). **Base de dados:** ~340 jogadas V4 reais (servidor Debian, `decisions.db`).
> **Resumo de 1 linha:** o staking atual (Gale/SmartGale 17/34/51) está **destruindo valor**; trocar por **flat ou Kelly fracionário, isolado por sentido**, é a mudança de **maior confiança e maior impacto** encontrada nos estudos.
>
> **Atualização 14/06 (dev senior):** refs `file:line` revalidadas contra o código atual; questão "pnl por-número vs total" **RESOLVIDA** (= TOTAL/N); adicionados **§6 — arquitetura `StakingPolicy`** (a parte de código a organizar), **§7 — sprints com GANHO por etapa** e **§7.1 — ROI por implantação**.

---

## 1. Objetivo e escopo

Especificar, em **regras de negócio**, como substituir o **staking variável (Gale anti-martingale)** por **flat** (stake constante) ou **Kelly fracionário** (stake proporcional ao edge estimado), **por sentido (CW/CCW independentes)**, mantendo a geometria V4 (3 regiões / 21 números) e a regra de produto INV-3 (sempre indicar aposta).

Fora de escopo aqui: alterar geometria (C1/C2/C3), seleção de combinação, ou timing condicional — **os estudos provaram que timing por vitória/derrota é ruído** (independência estatística; ver §2.3).

---

## 2. Evidência — por que flat/Kelly > Gale (a "lógica encontrada")

### 2.1 P&L realizado: o Gale perde; flat ganha nas MESMAS apostas
Sobre ~309 jogadas V4 resolvidas (flat = 1u/número, payout 36):

| Estratégia de staking (mesma geometria 21) | P&L | Observação |
|---|---|---|
| **Gale/SmartGale ao vivo (17/34/51)** | **−77u** 🔴 | é o que roda hoje |
| **Flat (constante)** | **+99u** 🟢 | mesmas apostas, sem escalar |
| Diferença (custo do Gale) | **~176u** | só pela forma de apostar |

→ O hit-rate dos 21 é **59,0%** (break-even 58,3%) → **levemente positivo em flat**, mas o **Gale converte isso em prejuízo** porque escala o stake (34/51u) e uma derrota no nível alto devolve todo o ganho da sequência.

### 2.2 Por sentido (a pedido) — o Gale perde nos DOIS
| Sentido | hit-rate | Baseline flat-21 (teste OOS) | Gale ao vivo |
|---|---|---|---|
| Horária | 59,8% | **+1,24 u/aposta** | negativo |
| Anti-horária | 59,0% | **+4,25 u/aposta** | negativo |

→ Não há assimetria de sentido sob V4 (59,8% ≈ 59,0%), mas **em ambos** o flat supera o Gale. Justifica **estado de staking independente por sentido** (já existe: `martingale_cw`/`martingale_ccw`).

### 2.3 Por que NÃO existe staking "inteligente" por streak (base estatística)
- Autocorrelação lag-1 da série vitória/derrota ≈ **0** em todos os combos e nos 2 sentidos (−0,09 a +0,04). `P(win|após derrota) ≈ P(win|após vitória) ≈ P(win)`.
- Busca de 91 regras condicionais (combo × streak) com **split treino/teste**: toda regra boa no treino **desabou out-of-sample** (ex.: melhor treino +3,67 → teste −0,65).
- **Conclusão:** as jogadas são **independentes**. Qualquer escalonamento por sequência (martingale/anti-martingale) **não muda o EV** — só **aumenta a variância e o risco de ruína**. Por isso o Gale só piora.

### 2.4 Bug adicional: os valores do Gale são da era "17 números"
`BET_VALUES = {1:17, 2:34, 3:51}` foram desenhados quando a aposta era **17 números** (17u = 1u/número). Com a V4 (**21 números**), esses valores **não foram revisados** — o stake não escala com a geometria. A spec flat/Kelly deve definir o stake em função de **N (nº de números)**, não em valores fixos legados.

✅ **RESOLVIDO (validação de código 14/06):** `gale_bet_value` é o stake **TOTAL** distribuído pelos N números — `database/sqlite_repo.py:485-507` calcula `pnl_units = stake·(36/N − 1)` no hit e `−stake` no miss. Logo, 17u "total" ÷ 21 números = **0,81u/número** hoje (era 1u/número quando N=17 — o per-number *encolheu* na migração 17→21 sem revisar `BET_VALUES`). A spec flat deve fixar **`U` por número** e derivar `stake_total = U·N` (default proposto: **U=1u → 21u total na V4**).

---

## 3. Como o staking funciona HOJE (mapa do código)

A pilha de staking atual tem **3 camadas** empilhadas (todas no caminho de `handle_new_result`):

```
[1] MartingaleState (Gale)  ──►  [2] get_effective_bet (QW-1/QW-2)  ──►  [3] overrides de veto (stop-loss/CUT/TR)
    state/game.py:21-175           state/game.py:1008-1090                 server/message_handler.py:413-540
    define base_bet (17/34/51)      modula base_bet (×frac ou ×weight)      reduz ao MENOR stake (INV-3)
                                                                              │
                                                                              ▼
                                              gale_bet_value = effective_bet  (message_handler.py:600-601)
                                                                              │
                                                                              ▼  enviado ao front: "aposta" (:748)
```

### Camada [1] — `MartingaleState` (Gale) · `state/game.py:21-175`
- `BET_VALUES = {1:17, 2:34, 3:51}` (linha **40**) → `current_bet` por nível (linha **43-44**).
- `get_gale(score, c4_rate, confidence)` (linha **55-105**): **anti-martingale** — escala o nível pelo `global_consecutive_hits` (streak de vitórias): `≥3→G3, ≥2→G2, senão G1` (linha **86-95**), com teto `max_gale` (1 em sinal fraco; 2 sob PROFIT_CUT_V1; 3 default).
- `update(hit)` (linha **107-145**): **qualquer derrota → reset G1** (linha 134-135); hit em G3 → take-profit reset.
- **Este é o mecanismo que sangra:** stake variável 17→34→51 por sequência de vitórias. Há um por sentido: `martingale_cw` / `martingale_ccw` (`game.py:218-220`).

### Camada [2] — `get_effective_bet(direction, strategy)` · `state/game.py:1008-1090`
- Pega `base_bet = mg.current_bet` (linha **1028**), escolhe `mg` por sentido (linha **1027**).
- **QW-1 minimizer** (linha **1050-1070**): se `should_minimize(direction)` → força `level=1` e `effective = base_bet × stake_fraction` (default 0.10, `[sda17.minimizer] stake_fraction`).
- **QW-2 weight** (linha **1072-1085**): se `level==1`, multiplica por `get_stake_weight(direction)`.
- Retorna `effective_bet`/`base_bet`/`multiplier`/`mode`.

### Camada [3] — Orquestração + vetos · `server/message_handler.py:413-540`
- `mg.get_gale(...)` (linha **427**) — dispara a escalação do Gale.
- `_stake_override` (linha **413, 431-442, 476-480**): stop-loss (B5) / CUT-v1 (score<4) / Triple Rate cauteloso → fração mínima (INV-3, nunca zera a indicação).
- `get_effective_bet(...)` (linha **494**) — aplica camada [2].
- `_stake_override` aplicado **após** QW, vale o **menor** stake (linha **529-534**).
- **Stake final gravado:** `gale_bet_value = stake_info["effective_bet"]` (linha **600-601**), em `decisions.gale_bet_value` (stake real auditável).
- **Enviado ao front:** `"aposta": stake_info["effective_bet"]`, `"gale_display"`, `"stake_mode"` (linha **748-753**).

### Onde o P&L é calculado (unidade — RESOLVIDO)
- `db_service.update_result(...)` (message_handler.py:**296/565**) grava `pnl_units` na decisão anterior. ✅ **Confirmado (14/06):** a fórmula está em `database/sqlite_repo.py:485-507` e trata `gale_bet_value` como **stake TOTAL** distribuído por N (`pnl = stake·(36/N − 1)` no hit; `−stake` no miss). Logo a unidade do flat/Kelly é **stake total = `U·N`** (ver §2.4 e P10).

---

## 4. Regras de negócio — Flat/Kelly por sentido (o "como implantar")

> Princípio central (provado nos estudos): **o stake NÃO deve depender de vitórias/derrotas recentes** (são independentes). Deve depender, no máximo, do **edge estimado por sentido** (Kelly) — e mesmo esse edge é hoje ~0/incerto, então **flat é o default seguro**.

### RN-1 — Modo de staking selecionável (flag)
Um seletor `staking_mode ∈ {gale, flat, kelly}` (env `SDA_STAKING_MODE`, default **`gale`** até validar; promover via shadow). `gale` = comportamento atual (rollback trivial).

### RN-2 — FLAT (default recomendado)
- **Stake constante por jogada**, independente de streak/nível/Gale: `stake = U` (unidade base configurável), idealmente expresso como **`U` por número × `N` números** para escalar com a geometria (21 hoje).
- **Sem escalação e sem reset-por-nível.** O nível do martingale fica **fixo em 1** (ou é ignorado).
- **Por sentido:** o mesmo `U` vale para CW e CCW (sem edge comprovado para diferenciar). Estrutura por sentido mantida só para isolamento de estado.

### RN-3 — KELLY fracionário (refinamento opcional, por sentido)
- Para a combinação apostada de `N` números (payout 36), com prob. estimada `p̂` (hit-rate **rolling** daquele sentido):
  - net-odds `b = (36 − N) / N`
  - fração Kelly `f* = p̂ − (1 − p̂) / b` ; **stake = bankroll × (k · f*)** com **k = ½ ou ¼** (Kelly fracionário, controla variância).
- **Cap** rígido (ex.: stake ≤ 2% do bankroll) e **floor** INV-3 (≥ 1u).
- **Se `f* ≤ 0`** (p̂ ≤ break-even `N/36`): stake = **mínimo** (INV-3 mantém a indicação; **nunca** escala para "recuperar").
- **Por sentido:** `p̂_cw` e `p̂_ccw` independentes → dois `f*` → dois stakes. (Espelha o isolamento CW/CCW já existente.)
- ⚠️ **Correção da auditoria 14/06 (fonte do `p̂`):** o `rolling_rate` exposto hoje por `should_minimize` usa `_recent_hit_rate` com **janela = 30** (`[sda17.minimizer].window`), **não** ≥100. Para Kelly, usar uma **janela própria longa** (`[sda17.staking].kelly_window`, default 100) sobre o buffer `_recent_hits` (cap 100) via novo método `rolling_hit_rate(direction, window)`. **Se `p̂` for `None`** (warmup `< warmup_n`=10 amostras): Kelly **se comporta como flat** (stake constante), nunca trava sem indicação.
- **Bankroll:** não há ledger de banca ao vivo (só `pnl_units` agregado). Até existir, usar `[sda17.staking].kelly_bankroll` (proxy configurável) como base do `f*`. **Enquanto `f*≈0` (sem edge), Kelly ≈ stake mínimo** — por isso `flat` é o default e Kelly fica atrás de flag + validação shadow (S4).

### RN-4 — INV-3 preservado (inviolável)
Sempre há indicação de aposta; o stake mínimo é **1u**. Nenhum modo zera a indicação. Os vetos atuais (stop-loss, CUT-v1, TR) **continuam válidos como redutores de stake** (compatíveis com flat/Kelly — eles só diminuem, nunca escalam).

### RN-5 — Anti-ruína (substitui o "take-profit/reset" do Gale)
Sem escalação por streak, o controle de risco vira: **cap de stake por jogada** (RN-3) + **stop-loss de sessão** (já existe, B5) + opcional **stop-win de sessão**. **Proibido** qualquer multiplicador por sequência de W/L.

### RN-6 — Interação com QW-1 (minimizer) e QW-2 (weight)
As modulações QW vivem em `get_effective_bet` (`state/game.py:1050-1085`). **Decisão da auditoria 14/06:** para garantir "stake constante" de verdade, **`flat` NÃO aplica QW-1 nem QW-2** (stake puro = `U·N`); **`kelly` também não** (o `f*` já é a modulação por edge — acumular QW seria dupla contagem). Os modos novos retornam cedo no dispatcher, **antes** do bloco QW. Detalhe por modulação:
- **QW-2 (stake_weight, `clamp(rate/0.472, 0.3, 1.5)` → até ×1.5)**: **amplifica** por rolling-rate; quebraria o stake constante do flat → **excluído** de flat/kelly.
- **QW-1 (minimizer, ×`stake_fraction` 0.10)**: é redutor; poderia coexistir, mas para manter o flat **previsível e testável** fica **fora** também. A proteção equivalente (cortar stake em sinal fraco) continua via os **vetos** (`_stake_override`: stop-loss/CUT-v1/TR) aplicados **depois** do dispatcher em `message_handler.py:529-534` — esses **só reduzem** (compatíveis com RN-4).
- **Gale** mantém QW-1/QW-2 **inalterados** (byte-idêntico).

---

## 5. Pontos de correção no código (para o agente — NÃO alterados aqui)

| # | Arquivo : linha | O que está lá hoje | Mudança proposta (flat/kelly) |
|---|---|---|---|
| P1 | `state/game.py:40,43-44` `BET_VALUES`/`current_bet` | nível→17/34/51 | sob `flat/kelly`, `current_bet` retorna o stake **constante** (flat) ou **Kelly** — não `BET_VALUES[level]`. Manter `BET_VALUES` só p/ modo `gale`. |
| P2 | `state/game.py:55-105` `get_gale()` | escala nível por streak | sob `flat/kelly`, **não escalar**: `level` fixo em 1 (ou função vira no-op). É o ponto que elimina o sangramento. |
| P3 | `state/game.py:107-145` `update()` | reset/escala por hit/miss | sob `flat/kelly`, manter `level=1` sempre; manter só contadores p/ telemetria. |
| P4 | `state/game.py:1008-1090` `get_effective_bet()` | QW-1/QW-2 sobre `base_bet` | **ponto natural do Kelly**: já recebe `direction` e `strategy` (tem `rolling_rate` via `should_minimize`/`get_stake_weight`). Calcular aqui o stake flat/Kelly por sentido. QW-1/QW-2 podem virar parte do Kelly ou coexistir como redutores. |
| P5 | `server/message_handler.py:427` `mg.get_gale(...)` | dispara escalação | sob `flat/kelly`, **pular** a chamada (ou get_gale no-op). |
| P6 | `server/message_handler.py:600-601` `gale_bet_value=` | grava stake efetivo | inalterado (continua gravando `effective_bet`); só muda a fonte do valor. **Renomear conceito** "gale_bet_value"→"stake" é cosmético/opcional. |
| P7 | `server/message_handler.py:748-753` payload front | `aposta`/`gale_display`/`stake_mode` | `stake_mode` deve refletir `flat`/`kelly`; `gale_display` perde sentido em flat (exibir "FLAT" ou o f* do Kelly). |
| P8 | `app_config/settings.py` | flags existentes | adicionar `staking_mode()` (env `SDA_STAKING_MODE`, default `gale`). |
| P9 | `config/strategy.toml [sda17.minimizer]` | `stake_fraction` | adicionar `[sda17.staking]`: `unit`, `kelly_fraction` (k), `kelly_cap`, `kelly_window`, `kelly_bankroll`. |
| P10 | `database/sqlite_repo.py:485-507` cálculo de `pnl_units` | **RESOLVIDO**: stake = `gale_bet_value` **TOTAL** distribuído por N (`pnl=stake·(36/N−1)` no hit, `−stake` no miss) | **Sem mudança de fórmula.** Flat/Kelly só precisam gravar `gale_bet_value` = stake total escolhido; a unidade do flat passa a ser `U·N`. |
| P11 | `state/game.py:1072-1085` QW-2 `stake_weight` | amplifica `base_bet` (w até ~1.5) por rolling-rate | sob **flat**: ignorar/clampar QW-2 a ≤1.0 (senão quebra stake constante); QW-1 (×0.10) pode ficar como redutor. Sob **kelly**: QW-1/QW-2 **subsumidos** pelo `f*` (não acumular). Ver **RN-6**. |

### 5.1 Auditoria pré-implantação (14/06) — bugs encontrados e corrigidos no plano
Antes de implantar, revisei o spec **contra o código vivo**. Bugs/gaps no plano original — todos **corrigidos acima**:
1. **Janela do `p̂` errada (crítico p/ Kelly):** o doc dizia "janela ≥100", mas o `rolling_rate` de `should_minimize` usa `_recent_hit_rate` → `h[-window:]` com **`window=30`** (`sda17.minimizer.window`). O buffer `_recent_hits` guarda 100, mas a taxa amostra **30**. → Kelly ganhou janela própria `kelly_window` (default 100) + método `rolling_hit_rate(dir, window)`. (RN-3)
2. **`p̂ = None` no warmup não tratado:** `_recent_hit_rate` devolve `None` enquanto `< warmup_n` (10). Kelly precisa de fallback → **comporta-se como flat** nesse caso. (RN-3)
3. **`get_effective_bet` não recebia `N`:** flat = `U·N`, mas a assinatura era `(direction, strategy)`. → **+param `n_numbers`**, com o caller passando `len(final_numbers)` (confirmado: `sda_numbers=final_numbers` em `message_handler.py:587`, então o N casa com o do `pnl_units`). (P4/§6.2)
4. **Bankroll do Kelly sem fonte:** não há ledger de banca ao vivo. → `kelly_bankroll` (proxy configurável) + nota de que `f*≈0` hoje ⇒ Kelly ≈ floor. (RN-3/§6.4)
5. **Ambiguidade QW sob flat:** "QW-1 pode permanecer" tornava o flat não-determinístico. → flat/kelly **retornam antes** do bloco QW (stake puro); proteção fica nos **vetos** pós-dispatcher. (RN-6)

**Não-bugs confirmados (OK para implantar):** `pnl_units` já é TOTAL/N (P10); `gale` permanece **byte-idêntico** via early-return no dispatcher; isolamento CW/CCW preservado (`martingale_cw`/`ccw` + `_recent_hits` por sentido).

---

## 6. Arquitetura — a parte de código a organizar (padrão `StakingPolicy`)

> A tabela §5 (P1–P11) lista *correções pontuais*. Aplicá-las "soltas" espalharia `if staking_mode == …` por `state/game.py` (5 pontos) + `server/message_handler.py` (2 pontos), multiplicando ramos e ameaçando o rollback byte-idêntico. **Recomendação de dev senior:** isolar a decisão de stake atrás de **uma única abstração** (Strategy pattern). `gale`/`flat`/`kelly` viram 3 implementações intercambiáveis; o resto do código **não sabe** qual está ativa.

### 6.1 Novo módulo `staking/policy.py` (contrato — não implementação)
```python
# staking/policy.py  (NOVO — contrato/esboço, não diff final)
@dataclass
class StakeContext:
    direction: str            # "cw" | "ccw"  (target)
    n_numbers: int            # geometria VIVA (21 na V4) — vem de sda_numbers
    base_unit: float          # U por número  ([sda17.staking].unit)
    mg: "MartingaleState"     # estado por sentido (Gale escala; flat/kelly só leem p/ isolamento)
    rolling_rate: float | None  # p̂ do sentido (janela `kelly_window`, NÃO a de 30 do QW-1) — só Kelly usa; None no warmup → trata como flat
    bankroll: float | None      # base do Kelly (proxy `kelly_bankroll` até haver ledger de banca)

@dataclass
class StakeResult:            # mesmo shape que get_effective_bet já retorna hoje
    effective_bet: int
    base_bet: int
    multiplier: float
    mode: str                 # "gale" | "flat" | "kelly" | "minimizer" | "veto_min"
    rolling_rate: float | None = None

class StakingPolicy(Protocol):
    name: str
    def pre_decision(self, mg) -> None: ...           # Gale: get_gale(); flat/kelly: NO-OP
    def compute(self, ctx: StakeContext) -> StakeResult: ...

class GaleStaking:   # = comportamento ATUAL (encapsula BET_VALUES + get_gale + QW-1/QW-2)
class FlatStaking:   # stake_total = round(base_unit * n_numbers); level travado em 1
class KellyStaking:  # b=(36-N)/N; f*=p̂-(1-p̂)/b; stake=clamp(round(bankroll*k*f*), 1, round(cap*bankroll)); p̂ None|f*≤0 → flat/floor

def make_staking_policy(mode: str) -> StakingPolicy:
    return {"gale": GaleStaking, "flat": FlatStaking,
            "kelly": KellyStaking}.get(mode, GaleStaking)()
```

### 6.2 Ponto de injeção único (blast-radius mínimo)
```
message_handler.py:427  mg.get_gale(...)              →  policy.pre_decision(mg)          # flat/kelly = no-op
state/game.py:1008      get_effective_bet(dir, strat, **n_numbers**) → policy.compute(StakeContext(...)) # +param n_numbers=len(final_numbers)
message_handler.py:600  gale_bet_value = effective    →  INALTERADO (já lê stake_info["effective_bet"])
message_handler.py:748  payload "aposta"/"stake_mode" →  INALTERADO (mode vem de policy.name)
```
→ `GaleStaking` reusa o cálculo de hoje **sem alteração** ⇒ `SDA_STAKING_MODE=gale` é **byte-idêntico** (rollback trivial). `flat`/`kelly` **nunca** tocam `BET_VALUES`/`get_gale`.

### 6.3 Onde cada P (§5) cai na nova arquitetura
| P | Hoje (espalhado) | Na arquitetura `StakingPolicy` |
|---|---|---|
| P1 `BET_VALUES` | `game.py:40` | **dentro de `GaleStaking`** (flat/kelly não usam) |
| P2 `get_gale` | `game.py:55` | `GaleStaking.pre_decision`; flat/kelly `pre_decision` = no-op |
| P3 `update` | `game.py:107` | só `GaleStaking` escala; flat/kelly mantêm `level=1` |
| P4 `get_effective_bet` | `game.py:1008` | vira **dispatcher**: `policy.compute(ctx)` |
| P5 `get_gale` call | `mh:427` | `policy.pre_decision(mg)` |
| P6 `gale_bet_value` | `mh:600` | inalterado |
| P7 payload | `mh:748` | `stake_mode = policy.name`; `gale_display`="FLAT"/f* |
| P8 settings flag | `settings.py` | `staking_mode()->str` (enum, ver §6.4) |
| P9 config | `strategy.toml` | `[sda17.staking]` via `strategy._cfg.get("sda17.staking", k, default)` |
| P10 pnl unidade | `sqlite_repo.py:485` | **RESOLVIDO**: stake TOTAL/N (nenhuma mudança de fórmula) |
| P11 QW sob flat/kelly | `game.py:1072` | flat/kelly **retornam antes** do bloco QW (sem QW-1/QW-2); vetos pós-dispatcher seguem reduzindo (RN-6) |

### 6.4 Snippets de flag/config prontos (copiar)
```python
# app_config/settings.py — enum de 3 valores (NÃO é o padrão _enabled()->bool das outras flags)
def staking_mode() -> str:
    v = os.environ.get("SDA_STAKING_MODE", "gale").strip().lower()
    return v if v in ("gale", "flat", "kelly") else "gale"
```
```toml
# config/strategy.toml
[sda17.staking]
unit           = 1.0    # U por número; stake_total = round(unit * n_numbers) → 21u na V4
kelly_fraction = 0.5    # half-Kelly (¼ p/ mais conservador sob edge incerto)
kelly_cap      = 0.02   # ≤2% do bankroll por jogada (mais rígido que os 5% de mercado)
kelly_window   = 100    # janela LONGA de p̂ por sentido (≠ os 30 do QW-1 minimizer)
kelly_bankroll = 100.0  # proxy de banca p/ dimensionar o Kelly (até haver ledger real)
```

---

## 7. Plano de sprints — implantação e GANHO por etapa

> Sequência incremental; cada sprint tem *exit-criteria* e rollback de **1 env-var**. **S1–S3 implantados (commit 7d9bce8)**; **S5 promovido em 14/06** — produção migrada `gale → flat` via `docker-compose.yml` (`SDA_STAKING_MODE=${SDA_STAKING_MODE:-flat}`); o **S4 (shadow OOS) foi dispensado por decisão do operador** ("estamos migrando de gale"). Rollback: `SDA_STAKING_MODE=gale` no host + redeploy.

| Sprint | Entrega | Toca (§5/§6) | Exit-criteria / testes | **GANHO (o que ganhamos)** | Rollback |
|---|---|---|---|---|---|
| **S0** · Fundação & verdade de dados | Confirma pnl=TOTAL/N; decide `U` (1u/nº×21=**21u** vs 17u legado); harness de backtest sobre `decisions.db` | P10 | Backtest reproduz **−77u** (gale) e **+99u** (flat) nas 309 jogadas | **Base de verdade auditável** + valores "mágicos" justificados. **Risco zero** (nada em prod) | n/a |
| **S1** · Flag + **Flat puro** (`StakingPolicy`) | Cria `staking/policy.py`; `get_effective_bet` vira dispatcher; `pre_decision` no-op p/ flat; flag `SDA_STAKING_MODE` (default `gale`) | P1–P5, P8 | Stake constante toda jogada; INV-3 ok; `mode=gale` byte-idêntico | **Para o sangramento:** swing **~+176u** (de −77u → +99u) nas mesmas apostas; **variância e risco de ruína despencam** | `SDA_STAKING_MODE=gale` |
| **S2** · Telemetria / ledger / front | `stake_mode='flat'`; `gale_display`→"FLAT"; `pnl_units` correto no payload e DB | P6, P7, P10 | `stake_mode` certo no front; `pnl_units` bate com o backtest | **Observabilidade:** permite comparar shadow P&L com confiança (sem isto, S4 é cego) | reverte payload |
| **S3** · **Kelly por sentido** | `KellyStaking`: `f*` com `p̂` rolling por sentido + `[sda17.staking]` cap/floor; half-Kelly | P4, P9, P11 | `f*≤0 → stake mín`; cap respeitado; CW/CCW usam `p̂` próprio | **Teto de upside:** half-Kelly ≈ **75% do crescimento a ½ da variância**; pronto p/ quando houver edge real (dealer-bias) | `SDA_STAKING_MODE=flat` |
| **S4** · Shadow A/B (validação OOS) | Calcula stake `flat`/`kelly` em paralelo ao `gale` vivo; loga P&L comparado por N dias | telemetria S2 | `P&L_shadow(flat) > P&L_gale` com folga, **fora-da-amostra** | **Prova OOS antes de promover** — evita repetir o erro do Gale (bom in-sample, ruim OOS — §2.3) | ⏭️ **DISPENSADO** (decisão do operador 14/06 — migração direta) |
| **S5** · Promoção | ✅ **FEITO 14/06**: `docker-compose.yml` → `SDA_STAKING_MODE=${SDA_STAKING_MODE:-flat}` (default do código segue `gale`); deploy via `roleta-deploy.timer` no Debian | P8 (compose) | `docker compose config` resolve `SDA_STAKING_MODE: flat`; CI verde | **Captura REAL do swing em produção;** `gale` = rollback de 1 env-var | `SDA_STAKING_MODE=gale` no host + redeploy, ou git revert |

### 7.1 Ganhos por implantação — visão consolidada (ROI)
- **Imediato (S1):** maior alavanca dos estudos — converter o staking de **−77u → +99u** nas mesmas 309 jogadas (**~176u de swing**), só mudando *como* aposta. É **gestão de variância**, não edge mágico (ver caveats §8).
- **Risco (S1+S3):** fim do martingale por streak → **drawdown e probabilidade de ruína caem** (martingale janela 3/5 uncapped tinha ruína **38–78%** em banca 50u; flat remove isso).
- **Operacional (S2):** ledger/telemetria corretos → decisões futuras baseadas em **P&L real**, não estimado.
- **Estratégico (S3+S4):** infra de Kelly fracionário pronta; no dia em que a captura de `dealer` der `f*>0` sustentável, o **upside** já tem caminho seguro (cap 2%, half-Kelly) **sem reescrever staking**.
- **Reversibilidade (todas):** cada etapa é **1 env-var de rollback**; `gale` nunca é apagado até a promoção provar superioridade OOS.

---

## 8. Invariantes, testes e caveats

**Invariantes (não quebrar):**
- **INV-3:** sempre indica aposta; stake mínimo 1u; nenhum modo zera.
- **Isolamento CW/CCW:** estado de staking por sentido permanece independente.
- **Rollback:** `SDA_STAKING_MODE=gale` reproduz exatamente o comportamento atual.

**Testes recomendados:**
- flat: stake idêntico em toda jogada, independente de W/L streak (e independente de `mg.level` herdado 2/3).
- flat: `stake_total = round(unit·N)`; sob N=21 e unit=1 → 21u; vetos (stop-loss/CUT) ainda reduzem.
- kelly: `f*≤0 → stake mínimo (1u)`; cap `round(kelly_cap·bankroll)` respeitado; por sentido usa `p̂` correto.
- kelly: `p̂=None` (warmup) → cai no flat (não trava, não escala).
- propriedade: nenhum modo (flat/kelly) escala stake por sequência de vitórias/derrotas.
- snapshot rollback: `gale` **byte-idêntico** ao atual (mesmo `effective_bet` para o mesmo estado).

**Caveats honestos (registrar no doc do agente):**
- Os P&L de flat (+99u/+282u) são **in-sample** sobre ~340 jogadas; **nenhum edge é estatisticamente significativo** (IC cruzam o break-even). O ganho **robusto** do flat vs gale é de **gestão de variância**, não de edge.
- Em roda justa, **nenhum staking cria EV positivo** — flat/Kelly **minimizam a sangria** (não geram lucro mágico). O único caminho para EV+ real é **viés físico/dealer** (exige corrigir a captura do `dealer`, hoje grava "unknown") — fora do escopo deste doc, mas é o pré-requisito para o Kelly um dia ter `f*>0` sustentável.

---

### Apêndice — fluxo resumido do stake (hoje × proposto)
```
HOJE (gale):    streak de vitórias → 17/34/51 → QW mod → veto min → effective_bet
PROPOSTO(flat): U constante (×N) ──────────────→ (veto min) ─────→ effective_bet
PROPOSTO(kelly):p̂_sentido → f*·k (cap/floor) ──→ (veto min) ─────→ effective_bet
```
