# Proposta — Seletor de Sentido (horário ⇄ anti-horário): diagnóstico e correção definitiva
**Data:** 03/08 · **Status:** REVISADA E AUDITADA — pareceres independentes incorporados · **Veredito:** GO para fundação V1–V4/V6A; NO-GO atual para autoridade de visão V5/V7 · **Atualização 05/08:** §10 — discussão tecnológica e contrapontos; §11 — auditoria sênior de implementabilidade, capacidade, esforço e gates · **Escopo:** extensão Chrome (`extension/background.js`, `popup`) + engine (`server/message_handler.py`, `state/game.py`, persistência, métricas e alertas)

---

## 1. O sintoma relatado pelo operador

> "Quando sai um resultado do horário a extensão presume que o próximo é anti-horário e o seletor muda.
> Ultimamente tem acontecido algum bug/delay em que o seletor **para de mudar** — e as informações
> começam a chegar do que era horário no anti-horário e vice-versa. A extensão fica às vezes minimizada."

## 2. Evidência quantificada em produção (medida em 03/08, mesa ao vivo)

A alternância cw⇄ccw é uma lei física da mesa (um giro por sentido). Qualquer sequência
`cw,cw` ou `ccw,ccw` no banco é **dado corrompido na fonte**. Auditoria no Postgres:

| Métrica (janela) | Valor | Leitura |
|---|---|---|
| Violações de alternância **hoje** (`LAG` sobre `cw+ccw.spin_features`) | **17 / 420 giros (~4% dos pares)** | bug ativo, recorrente |
| Violações 02/08 | 5 / 81 | idem |
| `phase_uncertain` (logs 7d) | **91×, em rajadas consecutivas** (a cada giro ~44s) | shift falhando em série, não é troca de mesa |
| `DIR17: seed zerado` (logs 7d) | **91×** (1:1 com uncertain) | autoridade re-ancorando **no cliente** a cada giro |
| Divergências corrigidas pela autoridade (7d) | 6× | autoridade funciona quando o seed sobrevive |
| Giro fantasma | nº 20 às 20:40:49 (ccw) **e** 20:40:51 (cw) | mesmo número, 2s de intervalo, direções opostas — fisicamente impossível (ciclo real ~44s) |

> ⚠️ **Sobre o "~4%" (achado da revisão):** a janela `LAG` mede os *pares* que violam — ou seja, as
> **entradas/saídas** do estado de fase invertida. Entre a violação de entrada e a de saída, todos os
> giros alternam certinho **com o rótulo invertido**, e a query não os vê. As 17 violações/dia podem
> representar ~8 janelas de N giros cada: a contaminação real pode ser **10–20% do dia**, não 4%.
> A quantificação por janelas é parte obrigatória desta proposta (§6).

**Conclusão da auditoria:** o sistema DIR1–DIR19 (sentido-fase) já blindou a maior parte do fluxo,
mas **quatro furos específicos** deixam o bug passar — dois no servidor, dois no cliente.

## 2.5 Verificação técnica (05/08): como o sentido é identificado e como o sistema se auto-sincroniza

> Seção adicionada em 05/08 respondendo às duas perguntas fundamentais do operador, com cada
> afirmação verificada no código real (arquivo:linha). É o "manual do mecanismo" que os furos do §3
> exploram e que os fixes do §4 blindam.

### 2.5.1 Como o sentido é identificado — não é leitura, é INFERÊNCIA determinística

**O DOM da Evolution NÃO expõe o sentido.** O extrator lê apenas os números do histórico
(`allNumbers`, 12 últimos) — e o próprio código documenta isso: `state/game.py` l.459–464 marca o
histórico como "contexto NÃO-DIRECIONAL. O histórico do DOM não carrega o sentido real". Não existe
sensor; existe uma **invariante física da mesa**: a roleta gira UM sentido por vez, alternando a cada
giro (horário → anti-horário → horário…).

Disso deriva o modelo de **fase alternada** (DIR3, `state/phase.py` l.1–13):

```
fase(n) = seed_parity            se (n − seed_n) é par
        = oposto(seed_parity)    se (n − seed_n) é ímpar
```

A cadeia de identificação em produção (`SDA_SENTIDO_AUTORITATIVO=1`), na ordem:

| Etapa | Onde vive | O que faz |
|---|---|---|
| **1. Âncora (seed)** | `handle_set_seed`, `message_handler.py` l.1556–1575 | Operador define a fase UMA vez no popup → `seed_parity`+`seed_n`+`source="operator_seed"` (+lock opcional). Persistido (round-trip save/load). |
| **1b. Auto-seed** (fallback) | `message_handler.py` l.782–786 | Sem seed do operador: a **primeira direção observada do cliente** vira âncora (`source="auto_seed"`). |
| **2. Contador** | `spin_seq` (`game.py` l.246), incrementado em l.824 do handler | Conta giros REAIS ao vivo. É o `n` da fórmula. |
| **3. Projeção** | `project_phase`, `phase.py` l.34–44 | Fase determinística de qualquer giro a partir de (seed, n). Função pura, 100% testável. |
| **4. Fusão de fontes** (DIR7 legado) | `fuse_direction`, `phase.py` l.80–122 | O código admite `operator > vision > server > client`, mas isso **não é a arquitetura-alvo**. `SDA_DIRECTION_VISION` deve permanecer `0`: visão não pode escolher o giro corrente; após os gates, no máximo propõe correção da âncora futura. |
| **5. Autoridade** | `message_handler.py` l.811–818 | Se a projeção divergir do `direcao` enviado pelo cliente → **substitui** e incrementa `direction_divergence_total`. O cliente apenas *propõe*; o servidor *decide*. |

**Papel do cliente na identificação:** `currentDirection` local flipa após cada envio
(`background.js` l.1782) e corrige por paridade quando detecta k giros num tick
(l.1713: `sendDir = k ímpar ? currentDirection : flip`). Mas com autoridade ligada isso é só a
proposta — o valor gravado no SQLite/PG é o projetado pelo servidor.

**Limite honesto do modelo (importante):** se a âncora estiver invertida (operador clicou o sentido
errado no seed), o sistema inteiro fica **espelhado de forma consistente** — a alternância continua
perfeita, nenhuma violação aparece, e nada interno detecta. Os únicos corretores de espelho são
**externos**: (a) o operador re-ancorando com 1 clique (`set_seed` re-ancora sem reset — é
re-ancoragem, não recálculo cego); (b) futuramente, uma sequência auditada de observações de visão
propondo correção da **âncora seguinte**, nunca do spin corrente. O gate DIR21/DIR22 desta proposta
detecta **quebra de alternância** (fantasma/duplicata), não espelho.

### 2.5.2 Como se auto-sincroniza — 6 camadas hoje, cada uma com gatilho e alcance próprios

| # | Camada | Onde | Gatilho | O que corrige | Latência |
|---|---|---|---|---|---|
| 1 | **Shift/gap** (DIR4) | servidor, a cada giro | `reconcile_shift` acha k≥2 (`phase.py` l.47–77) | contagem: `spin_seq += gap` → a paridade avança sozinha pelos giros perdidos (handler l.739–747) | imediata |
| 2 | **Re-âncora** (DIR17) | servidor | `phase_uncertain` (shift sem alinhamento) | âncora: zera `seed_parity` → próximo giro alinhado faz auto-seed (l.753–762) | 1 giro |
| 3 | **Autoridade** (DIR5) | servidor, a cada giro | projeção ≠ direção do cliente | a direção do spin individual (l.811–818) | imediata |
| 4 | **Resync por state_sync** (DIR1/DIR6) | cliente | conexão, reset, ou `resync_advised=true` | `currentDirection` ← `sentido.next_direction` do servidor (`background.js` l.576–599) | ≤1s **quando armado** |
| 5 | **Paridade de k local** | cliente, a cada leitura | k par no `countNewSpins` | fase do envio (flip local, l.1713) | imediata |
| 6 | **Re-hidratação do SW** | cliente, boot | service worker acorda | `currentDirection`/`directionSeed` do storage (l.971–976) | no boot |

**Por que mesmo com 6 camadas o seletor quebra** (o elo com o §3):

- A camada 2 re-ancora **na fonte errada**: quando o `uncertain` foi fabricado pelo Furo A (buffer
  `_phase_results` dessincronizado gera uncertain FALSO em série), o DIR17 zera o seed e adota a
  direção do **cliente defasado** como nova verdade. A autoridade passa a projetar a fase invertida
  — com convicção.
- A camada 4 **não é contínua**: só arma em 3 eventos. Se o cliente perder o `resync_advised` (SW
  dormindo no instante do state_sync), fica defasado indefinidamente — exatamente o sintoma
  relatado ("o seletor era para mudar e não muda").
- O giro fantasma (Furos B/C/C2) **incrementa `spin_seq`** — quebra a paridade de TODAS as camadas
  que dependem da contagem (1, 2, 3 e 5 de uma vez).

### 2.5.3 O que a proposta muda em cada camada

| Camada | Hoje | Com a proposta (§4) |
|---|---|---|
| 1 (shift) | recupera gap mas dessincroniza o próprio buffer de comparação (Furo A) | `sync_phase_buffer()` fecha a assimetria → uncertain falso desaparece |
| 2 (re-âncora) | dispara em rajada por uncertain falso; re-ancora no cliente contaminado | volta a disparar **só em troca de mesa real** → âncora estável |
| 3 (autoridade) | projeta certo, mas sobre `spin_seq` corrompível por fantasma | gate DIR21 (relógio monotônico do servidor) barra o fantasma **antes** de incrementar → contador íntegro |
| 4 (resync cliente) | eventual (3 gatilhos) | **contínua**: reconcilia a cada state_sync (1s), condicionada ao capability handshake `sentido.buffer_sync` — auto-desarma em rollback do servidor (fix G) |
| 5 (paridade k) | `countNewSpins` retorna "1 conservador" sem alinhamento → flip errado | retorna `{k, matched}`; sem matched → re-baseline sem flipar às cegas (fix D) |
| 6 (boot SW) | corrida: alarme lê antes da re-hidratação completar | gate de boot: 1º tick espera a re-hidratação (fix F) |

**Hierarquia final de autoridade (quem manda, em ordem):** operador (seed/lock) → projeção
determinística do servidor → cliente (apenas propõe). Vídeo futuro é observador em shadow e, somente
após os gates, candidato a corrigir a âncora do giro seguinte. A
auto-sincronização passa a ter **fechamento de malha em ≤1s** (camada 4 contínua) com fonte de
verdade que não se contamina (camadas 1–3 blindadas).

```mermaid
flowchart TD
    subgraph FISICA["Invariante física"]
        ALT["Mesa alterna sentido a cada giro"]
    end
    subgraph ID["Identificação (servidor)"]
        SEED["Âncora: operator_seed (popup, 1×)<br/>ou auto_seed (1ª direção observada)"]
        SEQ["Contador spin_seq<br/>(giros reais)"]
        PROJ["project_phase(seed, n)<br/>fase determinística"]
        FUSE["projeção + lock/seed<br/>visão sem autoridade per-spin"]
        AUTH["Autoridade DIR5:<br/>substitui direção do cliente se divergir"]
    end
    subgraph SYNC["Auto-sincronização"]
        GAP["DIR4: gap k≥2 → spin_seq += gap<br/>(+ sync_phase_buffer, fix A)"]
        GATE["DIR21: gate monotônico<br/>barra fantasma antes de contar"]
        REANC["DIR17: uncertain real →<br/>re-âncora no próximo giro"]
        SS["state_sync 1s: next_direction →<br/>cliente reconcilia (fix G: contínuo)"]
    end
    CLIENT["Cliente: currentDirection<br/>(propõe, não decide)"]
    ALT --> SEED --> PROJ
    SEQ --> PROJ --> FUSE --> AUTH
    GATE --> SEQ
    GAP --> SEQ
    REANC --> SEED
    AUTH --> SS --> CLIENT
    CLIENT -. "direcao proposta" .-> AUTH
```

### 2.5.4 Fontes tecnológicas: o que observa a direção hoje, o que garante, e o caminho para garantia física

Resposta direta à pergunta do operador — *"foto, vídeo ou dados? o que garante?"* — verificada
componente a componente no código:

| Fonte | Status hoje | O que entrega | Por que NÃO entrega direção |
|---|---|---|---|
| **Dados (DOM)** | ✅ ativa | números do histórico (`allNumbers`), 12 últimos | a Evolution **não expõe o sentido no DOM** — não há atributo/classe/elemento com a direção. `dom_hint` (peso 20 na fusão) existe só como slot: **nenhum código produz esse sinal** |
| **Foto** (`foto_roleta`) | ✅ ativa (`SDA_VISION_OCR=1`) | dealer, mesa, modelo da roda via OCR (`handle_foto_frame` → `vision_ocr.py`) | é **1 frame estático tirado APÓS o resultado** (`background.js` l.1769–1773). Uma foto única não contém movimento — direção exige ≥2 frames para medir deslocamento angular |
| **Vídeo** (DIR7) | 🟡 stand-by (`SDA_DIRECTION_VISION=0`) | o endpoint `handle_direction_event` (l.1535–1554) existe, mas **não está pronto para rollout**: faltam TTL, one-shot, binding ao giro, trilha e role-gate | **não existe produtor**: nenhum módulo captura frames em sequência nem calcula o sentido; ligar a flag atual seria inseguro |
| **Operador** (humano) | ✅ ativa | âncora via popup (`set_seed`) — ele olha a mesa e informa a fase 1× | é o **único sensor físico real do sistema hoje**. Custo: 1 clique; risco: errar o clique (espelho consistente, §2.5.1) |

**Então o que GARANTE, tecnologicamente?** A garantia atual é uma cadeia de 3 elos + 1 alarme:

1. **Invariante física da mesa** (premissa): o lançamento alterna a cada giro. É regra de procedimento
   da Evolution — o sistema não a verifica, **assume**.
2. **Âncora humana correta** (confiança): o operador informa a fase inicial olhando a mesa.
3. **Contagem íntegra** (é isso que esta proposta blinda): se `spin_seq` conta exatamente 1 por giro
   real — sem fantasma (gate DIR21), sem gap mal recuperado (fix A), sem giro duplicado (guard C2) —
   a projeção `seed XOR paridade` é matematicamente correta para sempre.
4. **Alarme de violação** (DIR22): se a premissa 1 quebrar (mesa muda de procedimento) ou os elos 2–3
   falharem, a alternância viola no PG e o alerta dispara em ~30min. **Não previne — detecta.**

> **Em uma frase:** hoje a direção não é observada por nenhum sensor; é *derivada* de uma âncora
> humana + contagem de giros, e o que esta proposta garante é que **a contagem não minta**. A âncora
> continua sendo o operador.

**Caminho para observação física independente** — fase posterior e condicional, fora do escopo deste
PR; a infraestrutura tem componentes reutilizáveis, mas **ainda não está pronta para autoridade**:

1. uma sprint de preflight confirma que a extensão alcança o `<video>` Evolution dentro do iframe;
2. um content script `all_frames` usa `requestVideoFrameCallback`; `captureVisibleTab` fica só como
   fallback diagnóstico, pois tem quota baixa e falha com janela minimizada;
3. Canvas processa localmente ROI elíptica do rotor, unwrap angular, correlação temporal e consenso de
   múltiplos frames; o frame bruto não sai da extensão;
4. o evento leva `event_id`, `round_id` quando disponível, timestamp, confiança e versão do sensor;
5. o servidor valida MASTER, TTL, vínculo a `target_spin_seq` e consumo one-shot, persistindo a
   decisão append-only em `phase_events`;
6. durante shadow, visão apenas mede cobertura/concordância; depois de T0–T4 pode, no máximo, propor
   correção da âncora futura por K desacordos coerentes;
7. `SDA_DIRECTION_VISION` permanece `0`; a aposta nunca consome visão diretamente e o lock do
   operador continua soberano.

## 3. Causa-raiz — a cadeia completa (4 furos que se retroalimentam)

### Furo A (servidor, o mais grave): assimetria de buffer na recuperação de gap — DIR4/DIR19
`server/message_handler.py` l.745–746: quando um gap é recuperado, o código sincroniza os números
intermediários em `recent_results`, **mas não em `_phase_results`** — que é exatamente o buffer
que o DIR19 usa como `prev` na comparação do shift (l.737):

```python
if _gap > 0:
    self.game_state.spin_seq += _gap
    for _n in _inter:
        self.game_state.recent_results.appendleft(_n)   # ← _phase_results NÃO recebe!
```

**Verificação exaustiva da revisão (rev-server):** todos os demais sítios de escrita são simétricos —
`process_spin` (`game.py:423/426`), `register_history_number` (`game.py:465/468`), `reset_session`
(`game.py:337/341`), `save`/`load` round-trip (`game.py:1355/1449/1464-1467`). **A recuperação de gap
é a ÚNICA assimetria do repo.** Agravante: o comentário nas l.740–742 está obsoleto — afirma que
sincronizar `recent_results` evita phase_uncertain falso, mas desde a DIR19 o alinhamento lê
`_phase_results`; a sincronização existente não cumpre mais o propósito declarado.

**Efeito dominó, quantitativamente consistente com os logs:** após 1 gap, `_phase_results` fica com
um "buraco". Como o cliente manda `allNumbers` de **12 itens** (`background.js:1756`) e o reconcile
compara `m = min(len(prev), len(new)-k)` posições (`state/phase.py:47-77`), o buraco só sai da janela
comparada após **~10–11 giros ao vivo** → exatamente as rajadas de `phase_uncertain` consecutivas dos
logs (91×). Com `SDA_UNCERTAIN_REANCORA=1` e `SDA_SENTIDO_AUTORITATIVO=1` (defaults de produção,
compose l.109/140), cada uncertain zera o seed (`message_handler.py:759-762`) e o giro seguinte
auto-seeda **na direção que o cliente mandou** (l.782-786). Ou seja: **a autoridade do servidor é
neutralizada exatamente na janela em que o cliente pode estar defasado.** Se o cliente estiver com a
fase trocada (furos C/C2), o servidor aceita e ancora a fase errada — que persiste até alguém notar.
São os `cw,cw`/`ccw,ccw` do banco.

### Furo B (servidor): dedup não pega o fantasma com direção invertida
O fantasma das 20:40 passou pelos dois guards existentes (`message_handler.py:154-162`):
- guard 1 (`is_duplicate_spin`): mesmo número no **mesmo segundo** — 2s de intervalo escapa;
- guard 2 (`SDA_DEDUP_PHANTOM`, OFF em prod): exige mesmo número **e mesma direção** — o fantasma
  chegou com a direção **oposta** (o cliente flipou a fase no re-envio), então nem ON pegaria.

Falta um guard de **plausibilidade física**: nenhum giro real acontece a menos de ~15s do anterior
(ciclo ~42–48s). Um `novo_resultado` < N segundos após o último aceito é lixo de leitura, sempre.
**Correção factual da revisão:** o `timestamp` que chega ao dedup é `data.get("timestamp", now_ms())`
(`message_handler.py:409`) e a extensão **sempre** envia `Date.now()` do cliente (`background.js:1755`)
— portanto o gate NÃO pode usar esse campo (relógio do Windows do operador; um ajuste NTP > 15s
burlaria a proteção). O gate usa **relógio monotônico do servidor** (§4.1-B).

### Furo C (cliente): leitura parcial/truncada de frame gera reenvio com fase flipada
`extension/background.js` l.1492–1500: entre os frames retornados por `executeScript(allFrames:true)`,
o código pega **o primeiro** que tiver números (`break`). Com a janela minimizada, o Chrome pausa rAF
e aplica throttling intensivo aos timers da página — o app da Evolution re-renderiza em lotes
atrasados, deixando o DOM em estados intermediários entre leituras.

**Mecanismo confirmado pela revisão (rev-extension), variante de cauda** — é a que explica o fantasma
real do banco:

```
leitura N   : [20,5,9,2,7]  → envia 20, fase flipa
leitura N+1 : [20,5,9,2]    (lista truncada na cauda — re-render parcial)
              hash difere (l.1704) → countNewSpins([20,5,9,2],[20,5,9,2,7]):
              k=1..3 falham, k=4 → overlapLen=0 → break (l.122-123) → retorna 1 "conservador"
              → REENVIA o 20 com a fase JÁ FLIPADA  ← o fantasma das 20:40 (2s, direção oposta)
```

`countNewSpins` retorna `1` conservador quando não há alinhamento (l.130) — mas "não alinhou"
significa "leitura suspeita", não "1 giro novo". Cada flap = 1 giro fantasma + 1 flip espúrio.
O caso `k=0` (lista idêntica/truncada — nenhum giro novo) nem existe no loop atual (começa em k=1).
Há ainda a corrida de boot do SW MV3: o alarme pode disparar `readResults` **antes** do callback de
re-hidratação de `currentDirection` (l.974) completar — o primeiro envio pós-acordar pode sair com a
fase literal `'horario'`.

### Furo C2 (cliente, descoberto na revisão): reentrância de `readResults`
`onAlarm` chama `readResults()` **sem await** (l.1063) a cada ~2s. Com o frame throttled
(minimizado), `executeScript` pode levar >2s → **duas execuções concorrentes** leem o mesmo
`lastHash`, ambas detectam o "novo" giro, e **enviam o mesmo giro 2× com 2 flips de fase**.
Mecanismo alternativo/complementar do fantasma de 2s — o fix D sozinho não o cobre; precisa de
guard de reentrância (§4.2-D0).

### Por que "minimizado" piora tudo
Minimizar **não** afeta alarms nem `executeScript` (fatos MV3 verificados) — afeta o **render da
página** (rAF pausado, timers throttled = DOM parcial, furo C), aumenta a duração do `executeScript`
(reentrância, furo C2), mata as globals do SW (corrida de re-hidratação) e gera gaps de leitura cuja
recuperação dispara o furo A no servidor. Os quatro furos se encadeiam.
Nota MV3: `periodInMinutes: 0.0333` (2s) só é honrado em extensão **unpacked** (o deploy real do
operador); empacotada, o Chrome clampa para 30s — premissa documentada no PR (§4.2-H).

## 4. Proposta de correção (cirúrgica, flag-gated, zero mudança de comportamento com flags OFF)

### 4.1 Servidor — `message_handler.py` + `state/game.py` + `state/phase_metrics.py` + `server/health_server.py` + `app_config/settings.py` + `obs/alerts.yml`

**A) Sincronizar o buffer de fase na recuperação de gap** (fix do furo A) — via método público novo
`GameState.sync_phase_buffer(nums)` (encapsula `_phase_results`, com `getattr`-guard e erro
observável; nunca usa `except Exception: pass`, pois esconderia justamente a regressão a corrigir;
compatível com
`test_fallback_phase_advance_se_phase_results_ausente`):

```python
# state/game.py
def sync_phase_buffer(self, nums: list[int]) -> bool:
    """DIR20: espelha números recuperados de gap no buffer de fase (_phase_results).
    Sem isso o próximo reconcile_shift nunca alinha → rajada de phase_uncertain →
    DIR17 re-ancora a autoridade no cliente a cada giro (neutralizada)."""
    buf = getattr(self, "_phase_results", None)
    if buf is None:
        logger.error("[FASE] _phase_results ausente durante sync de gap")
        return False
    for _n in nums:
        buf.appendleft(int(_n))
    return True
```

```python
# server/message_handler.py (~l.739) — comentário obsoleto das l.740-742 atualizado no mesmo diff
if _gap > 0:
    self.game_state.spin_seq += _gap
    phase_metrics.incr("gap_recuperado_total", _gap)
    for _n in _inter:
        self.game_state.recent_results.appendleft(_n)
    if phase_buffer_sync():          # flag SDA_PHASE_BUFFER_SYNC, leitura per-call
        if not self.game_state.sync_phase_buffer(_inter):
            phase_metrics.incr("phase_buffer_missing_total")
```

Ordem verificada: `phase_advance` devolve `_inter` do mais antigo→mais recente (`phase.py:148`);
`appendleft` em loop nessa ordem + o atual em `[0]` via `process_spin` produz o buffer idêntico ao
`allNumbers` do cliente → próximo shift alinha com k=1 (asserção central do teste novo).
Flag: `SDA_PHASE_BUFFER_SYNC` (default **OFF** na compose, liga via `.env` do host). OFF = byte-idêntico.

**B) Gate de plausibilidade física — DIR21** (fix do furo B) em `is_duplicate_spin`, com **relógio
monotônico do servidor** (nunca o `timestamp` do payload, que é `Date.now()` do cliente):

```python
# DIR21: nenhum giro físico acontece < N ms após o anterior (ciclo ~42-48s).
# Relógio MONOTÔNICO do servidor: imune a NTP/ajuste do relógio do cliente E do host.
_min_iv = min_spin_interval_ms()          # flag SDA_MIN_SPIN_INTERVAL_MS, per-call
_now_mono = time.monotonic()
if (_min_iv > 0 and self._last_accept_srv_mono is not None
        and (_now_mono - self._last_accept_srv_mono) * 1000.0 < _min_iv):
    _delta_ms = int((_now_mono - self._last_accept_srv_mono) * 1000)
    logger.warning(f"[FASE] DIR21 spin fisicamente implausivel ignorado: "
                   f"{numero}/{direcao} ({_delta_ms}ms apos o ultimo aceito)")
    phase_metrics.incr("spin_implausivel_total")
    return True
# Não alterar _last_accept_srv_mono dentro do dedup.

# No fim de handle_novo_resultado, somente após validação e process_spin aceito:
self._last_accept_srv_mono = time.monotonic()
```

- Campo **novo** `_last_accept_srv_mono` — NÃO reaproveita `_last_accept_ts_ms` (que é client-time e
  alimenta o phantom-dedup existente; mudar sua semântica alteraria uma flag já em produção).
- `handle_new_session` zera `_last_accept_srv_mono` junto do clear de trace_ids (DIR14,
  `message_handler.py:1490-1497`) — sem isso o 1º giro legítimo da mesa nova chegando <15s do último
  da mesa anterior seria engolido.
- Custo aceito e documentado: em troca de mesa **sem** reset (rara), 1 giro real pode ser descartado
  (~44s de atraso; o `historico_inicial` subsequente re-ancora). Não viola INV-3 — indicação nunca é
  suprimida; perde-se 1 avaliação de outcome, benigno.
- Escopo confirmado: só `novo_resultado` passa pelo dedup (l.428-438); `historico_inicial`/
  `correcao_historico` usam `register_history_number` e são imunes.
- Flag: `SDA_MIN_SPIN_INTERVAL_MS` (default **0=OFF**; produção sugerida: `15000`).

**C) Métrica de violação de alternância — DIR22** (telemetria permanente, sem flag — precedente
DIR3): capturar `prev_last_direction = self.game_state.last_direction` **antes** de `process_spin`;
após o processamento com a direção final (pós-autoridade — é o que chega ao SQLite/PG):

```python
# DIR22: alternância é lei física; violação = corrupção na fonte. Só telemetria.
# Mede PÓS-autoridade: é a métrica da meta "violações no PG por dia".
if prev_last_direction and direcao == prev_last_direction:
    phase_metrics.incr("alternancia_violada_total")
    logger.warning(f"[FASE] DIR22 alternancia violada: {direcao} 2x seguidas (seq={self.game_state.spin_seq})")
```

**Plumbing obrigatório das métricas (sem isso os counters são no-op silencioso):**
- `state/phase_metrics.py`: adicionar `spin_implausivel_total` e `alternancia_violada_total` ao dict
  `_COUNTERS` (l.10-14 — `incr()` ignora chaves desconhecidas!);
- `server/health_server.py` (DIR12): registrar as 2 gauges novas em `_PROM_METRICS`/refresh;
- `tests/test_dir12_metrics_exporter.py`: atualizar o assert do **set exato** de chaves (ficaria
  vermelho sem isso — inviolável "suíte verde antes do PR");
- `obs/alerts.yml` (hoje: **zero** regras de fase): adicionar
  `RoletaAlternanciaViolada: increase(roleta_phase_alternancia_violada_total[1h]) > 2 → warning` e
  `RoletaPhaseUncertainBurst: increase(roleta_phase_uncertain_total[30m]) > 5 → warning` (rajada =
  furo A regrediu; detecção em ~30min em vez de auditoria manual D+7). Counters são em memória e
  zeram a cada restart do container — leitura absoluta engana; só `increase()/rate()` é confiável.

**D) Capability handshake para o fix G do cliente** (1 linha aditiva): quando
`SDA_PHASE_BUFFER_SYNC=1`, o bloco `sentido` do state_sync/overlay passa a incluir
`"buffer_sync": true`. Cliente antigo ignora; o cliente novo só ativa a reconciliação contínua (G)
se o capability estiver presente → **G se auto-desarma em qualquer rollback do servidor** (flag OFF
ou `git revert`), eliminando a dependência meramente procedural da ordem de rollout.

### 4.2 Cliente — `extension/background.js` + popup (v3.8.0 "DIR20-client")

**D0) Guard de reentrância em `readResults`** (fix do furo C2 — barato, ataca o fantasma de 2s):

```js
let _readBusy = false;
async function readResults() {
  if (_readBusy) return;          // tick anterior ainda rodando (frame throttled >2s)
  _readBusy = true;
  try {
    await rehydrated;             // fix F — nunca envia com a fase literal do boot
    ...
  } finally { _readBusy = false; }
}
```

**D) Guard de rollback/leitura parcial** (fix do furo C). `countNewSpins` devolve `{k, matched}`,
com `k=0` incluso (lista idêntica/truncada deslocada = re-render, nenhum giro novo) e proteção
contra falso alinhamento em k alto:

```js
function countNewSpins(newArr, oldArr) {
  if (!Array.isArray(newArr) || newArr.length === 0) return { k: 1, matched: false };
  if (!Array.isArray(oldArr) || oldArr.length === 0) return { k: 1, matched: true }; // 1ª leitura: fluxo intacto
  const maxK = Math.min(newArr.length, 12);
  for (let k = 0; k <= maxK; k++) {
    const overlapLen = Math.min(oldArr.length, newArr.length - k);
    if (overlapLen <= 0) break;
    if (k > 6 && overlapLen < 2) break;   // k alto com 1 número de overlap = 1/37 de falso positivo
    let match = true;
    for (let i = 0; i < overlapLen; i++) {
      if (newArr[k + i] !== oldArr[i]) { match = false; break; }
    }
    if (match) return { k, matched: true };
  }
  return { k: 1, matched: false };        // sem alinhamento = leitura suspeita
}
```

No fluxo (l.~1704), leitura sem alinhamento **não envia, não flipa, não atualiza baseline** — e o
contador de skips é **consecutivo e persistido** (`state.unalignedStreak`, zerado em tick alinhado;
o SW dorme entre ticks, um global não sobreviveria):

```js
const { k: _novos, matched: _aligned } = countNewSpins(newNumbers, _prevResults);
if (!_aligned) {
  state.unalignedStreak = (state.unalignedStreak || 0) + 1;
  state.debug.skippedUnaligned = (state.debug.skippedUnaligned || 0) + 1;
  console.warn(`⚠️ DIR20: leitura sem alinhamento (${state.unalignedStreak}/${DIR20_MAX_SKIPS}) — tick ignorado`);
  if (state.unalignedStreak >= DIR20_MAX_SKIPS) {
    // Re-baseline: aceita a lista como novo estado SEM enviar giro.
    // historico_inicial SÓ com evidência de troca de mesa (table/round mudou em sessionData);
    // gap na mesma mesa = re-baseline SILENCIOSO (o servidor já tem o histórico e recupera gaps).
    ...
    state.unalignedStreak = 0;
  }
  await saveState(state);
  return;
}
state.unalignedStreak = 0;
if (_novos === 0) { await saveState(state); return; }  // re-render idêntico: nada novo
const sendDir = (_novos % 2 === 1) ? currentDirection : phaseFlip(currentDirection);
```

`DIR20_MAX_SKIPS=5` (≈10s no tick de 2s). Kill-switch: constante `DIR20_ENABLED` no topo do
`background.js` — `false` + reload restaura o comportamento v3.7.0 em ~30s, sem git (§5, rollback).

**E) Seleção de frame: sticky-first** (prioridade invertida vs a 1ª versão desta proposta — o
lobby da Evolution pode ter lista MAIS LONGA de outra mesa; "maior lista vence" poderia re-baselinar
na mesa errada em 10s quando combinado com D):

```js
// Prioridade: (1) o MESMO frame da última leitura boa (sticky), se respondeu com números;
//             (2) fallback: a lista mais longa entre os demais.
let best = null, sticky = null;
for (const result of injectionResults) {
  const r = result.result;
  if (!r || !r.numbers || r.numbers.length === 0) continue;
  if (result.frameId === state.lastGoodFrameId) sticky = { ...r, frameId: result.frameId };
  if (!best || r.numbers.length > best.numbers.length) best = { ...r, frameId: result.frameId };
}
const chosen = sticky || best;
if (chosen) { newNumbers = chosen.numbers; totalElementsFound = chosen.elementsFound; state.lastGoodFrameId = chosen.frameId; }
```

`frameId` é estável durante a vida do frame; recriação do iframe = id novo → sticky falha → fallback
pega — degrada com graça.

**F) Eliminar a corrida de boot do SW** — re-hidratação como promise de topo (recriada a cada wake
do SW; `storage.get` resolve `{}` se vazio — sem deadlock), aguardada em **todos** os consumidores:
`readResults` (D0 acima), `socket.onmessage` (l.550 — cobre os handlers de `state_sync`/
`sessao_resetada` que leem `currentDirection`) e `setDirection` (l.1243):

```js
const rehydrated = chrome.storage.local.get(['currentDirection', 'directionSeed']).then((data) => {
  if (data.directionSeed === 'horario' || data.directionSeed === 'anti-horario') directionSeed = data.directionSeed;
  if (data.currentDirection === 'horario' || data.currentDirection === 'anti-horario') currentDirection = data.currentDirection;
});
```

**G) Reconciliação contínua com o servidor — condicionada por capability**: reconciliar
`currentDirection` com `sentido.next_direction` a cada state_sync **somente se**
`sentido.buffer_sync === true` (handshake do §4.1-D) **e** `!sentido.locked` **e** fora da seção
crítica de envio. Seção crítica delimitada explicitamente: flag setada **antes** de computar
`sendDir` e limpa **após** o `storage.set` que persiste o flip — senão um state_sync entre o flip e
a persistência regravaria a direção velha. Com o handshake, `DIR20_TRUST_SERVER` local pode nascer
ON com segurança (auto-desarma em rollback do servidor). Sinergia: quando o DIR21 rejeitar um
fantasma, o state_sync re-cola o cliente na fase autoritativa em ≤1s.

**H) Popup (gate operacional do rollout)**: expor 3 contadores + versão — `skippedUnaligned`,
`rebaselines`, `unalignedStreak` atual e `v3.8.0` (hoje o popup só mostra elements/numbers/error —
sem isso o passo 4 do rollout não tem validação prática). Documentar no PR a premissa **unpacked**
(alarm de 2s; empacotada clampa a 30s → D continua correto, mas re-baseline vira 150s e k>1 vira
norma). Follow-ups aceitos (fora do escopo v3.8.0, registrados): botão de **lock** DIR13 no popup
(pipeline servidor existe fim-a-fim, falta só UI) e aviso visual de flatline do seletor (N giros
sem flip).

### 4.3 O que NÃO muda (garantias)
- **INV-3 intocado**: nada altera indicação/stake — só rotulagem do sentido e dedup de lixo de leitura.
- **Contrato WS intocado**: `novo_resultado{direcao}` idêntico; único campo novo é `sentido.buffer_sync`
  no state_sync (aditivo, cliente antigo ignora).
- **Fluxo de dados intocado**: SQLite → outbox → CDC → PG idêntico; o fix é a montante (fonte).
- **Flags server default-OFF na compose** (`SDA_PHASE_BUFFER_SYNC`, `SDA_MIN_SPIN_INTERVAL_MS=0`),
  padrão `${VAR:-default}` + comentário de rollback, leitura per-call (inviolável do repo).
- **Matriz de coexistência (4 células, verificada):** cliente antigo+servidor novo = seguro (B até
  protege contra os fantasmas do cliente antigo — valor antecipado antes do passo 4); cliente
  novo+servidor antigo = seguro (D/E/F client-side puros; G auto-desarmado pelo handshake ausente).
- **DIR13 lock total respeitado**: com `locked=true`, nem G nem reancoragem tocam a fase do operador.

## 5. Plano de rollout (ordem, critérios falseáveis, stop-conditions)

| # | Passo | Validação (falseável) | Rollback |
|---|---|---|---|
| 1 | PR servidor (A+B+C+D-handshake + plumbing métricas + alertas) com flags OFF → merge → deploy automático | `pytest tests/` verde; caminho de decisão/aposta byte-idêntico com flags OFF (delta permitido: telemetria DIR22 + gauges novas) | `git revert` via PR |
| 2 | Ligar `SDA_PHASE_BUFFER_SYNC=1` no `.env` do host + `docker compose up -d roleta-cloud` | **48h** com exposição mínima de ≥5 gaps recuperáveis: minimizar a janela **5–8min**, 2–3×/dia, limitando a ausência a **≤11 giros**, pois `allNumbers` tem 12 posições. **Passa se:** zero `phase_uncertain` nos gaps com overlap; zero rajadas DIR17 ≥3 giros; métricas por tamanho de gap confirmam o shift. Gap >11 é limite estrutural esperado, não falha do fix. | flag `=0` + `up -d` (minutos) |
| 3 | Ligar `SDA_MIN_SPIN_INTERVAL_MS=15000` | +48h: `spin_implausivel_total` detecta descartes; violações **intra-sessão** caem; zero descarte com delta >20s; `spins_received` em 24h permanece dentro de ±10% do baseline, evitando trocar fantasma por perda silenciosa | flag `=0` + `up -d` |
| 4 | Extensão v3.8.0 (D0+D+E+F+G+H) no Chrome do operador | contadores novos no popup; roteiro numerado (§7); fantasmas somem | zip/tag `ext-v3.7.0` (artefato no PR) + "Load unpacked" (3 linhas documentadas); ou kill-switch `DIR20_ENABLED=false` + reload (~30s) |
| 5 | Auditoria D+1/D+3/D+7 (query LAG **automatizada** — cron diário no host, resultado em log/Grafana) | metas escalonadas: D+1 ≤4 violações; D+3 ≤2; D+7 **≤1/dia com causa atribuída** (cruzar ts com logs DIR22 + resets/trocas de mesa; violação SEM causa = regressão) | — |

> Meta "0/dia" foi rejeitada na revisão: trocas de mesa reais e correções manuais do operador geram
> violações **legítimas** na query agregada (~N/2 por N trocas). O critério final é "≤1/dia com causa
> atribuída" — ou, melhor ainda, 0 violações **intra-sessão** se a query for particionada por sessão.

Query de auditoria contínua (mesma do diagnóstico; agendar via cron):
```sql
WITH seq AS (
  SELECT ts, session_id, dir,
         LAG(dir) OVER (PARTITION BY session_id ORDER BY ts) AS prev_dir
  FROM (
    SELECT ts, session_id, 'cw' AS dir FROM cw.spin_features
    UNION ALL
    SELECT ts, session_id, 'ccw' AS dir FROM ccw.spin_features
  ) u
  WHERE ts > now() - interval '1 day'
)
SELECT session_id,
       count(*) FILTER (WHERE dir = prev_dir) AS violacoes_intra_sessao,
       abs(count(*) FILTER (WHERE dir = 'cw')
           - count(*) FILTER (WHERE dir = 'ccw')) AS desequilibrio_cw_ccw,
       count(*) AS total
FROM seq
GROUP BY session_id;
```

Critério por sessão: `violacoes_intra_sessao = 0` e `desequilibrio_cw_ccw <= 1`, exceto eventos
explicitamente marcados como `phase_uncertain` e com causa auditável.

## 6. Remediação dos dados já contaminados (reformulada pela revisão)

A 1ª versão propunha uma view de *pares* violadores — **subestima estruturalmente**: o par marca a
entrada/saída do estado invertido; os giros DENTRO da janela alternam certinho com rótulo trocado.
Para features per-direction (cw/ccw.spin_features, spins_vectors, lifts), rótulo invertido é
**cross-contamination sistemática** entre as duas populações que o ML trata como distintas — não é
ruído aleatório.

Plano revisado (aditivo, não-destrutivo, ordem obrigatória):
1. **Quantificar primeiro**: view `shared.vw_spins_janela_suspeita` por **janelas entre violações
   consecutivas** (início, fim, n_giros) e medir ∑ giros suspeitos ÷ total (30d). Só então decidir
   materialidade — "4% imaterial" era premissa não verificada.
2. **Anotação durável**: tabela aditiva `shared.spin_quality(ts, flag, motivo)` (migração Alembic
   aditiva; não toca tabelas quentes; sobrevive ao rollback de deploy que não faz downgrade).
   Notebooks/AEs fazem anti-join — sem depender de disciplina de uso de view.
3. **Decisão humana**: excluir vs re-rotular vs ignorar nos lifts/AEs é do **dono do modelo**, após
   o número real do item 1 — não é default embutido nesta proposta. Histórico permanece imutável.

## 7. Testes (matriz ampliada pela revisão)

Servidor (CI, `pytest`):
- `test_dir20_phase_buffer_sync.py` — gap recuperado sincroniza `_phase_results` **na ordem exata**
  (buffer resultante idêntico ao `allNumbers` do cliente — é essa igualdade que faz o shift alinhar);
  próximo giro alinha sem uncertain; flag OFF = comportamento atual; atributo ausente não explode.
- `test_dir21_min_spin_interval.py` — spin < N ms rejeitado (número/direção diferentes); N=0 desliga;
  relógio de cliente **adulterado/regressivo/saltando não afeta o gate** (monotônico do servidor);
  rejeição **não** atualiza `_last_accept_srv_mono`; `handle_new_session` limpa a âncora (1º giro da
  mesa nova aceito); `historico_inicial` imune.
- `test_dir22_alternancia_metrica.py` — incrementa em `cw,cw`; não incrementa em `cw,ccw`, com
  `prev=None` (histórico não-direcional) nem no 1º giro pós-reset (DIR16 zera `last_direction`).
- `test_dir12_metrics_exporter.py` — **atualizar** o set exato de chaves (+2) e gauges expostas.

Cliente (sem harness JS — roteiro **numerado e determinístico** no PR, resultado esperado por passo):
1. Minimizar janela 2min → `skippedUnaligned > 0` no popup e **zero** envio não-alinhado no log do SW.
2. Troca de mesa real → re-baseline em ≤5 ticks + `historico_inicial` (com evidência de troca) e
   **nenhum** `novo_resultado` espúrio.
3. Matar o SW via `chrome://serviceworker-internals` durante giro → 1º envio pós-boot com a fase do
   storage (nunca a literal `'horario'`).
4. Toggle manual de direção durante state_sync divergente → seção crítica respeitada (sem regravação).
5. Contrato: testes existentes `test_dir5/6/8/13/17/19` continuam verdes (fixtures reutilizadas).

## 8. Revisão por agentes em paralelo (03/08) — o que mudou da v1 para esta versão

3 revisores independentes, todos **APROVAR COM MUDANÇAS** (incorporadas):

**Revisor servidor** (verificou linha a linha; confirmou o furo A como única assimetria do repo e a
consistência quantitativa rajada⇔janela-12):
1. *Erro factual na v1*: "timestamp do servidor" — na real é `Date.now()` do cliente
   (`message_handler.py:409` + `background.js:1755`) → gate reescrito com `time.monotonic()` do
   servidor em campo novo `_last_accept_srv_mono` (§4.1-B).
2. Métricas novas seriam **no-op silencioso** (`_COUNTERS` é dict fechado; `incr` ignora chave
   desconhecida) → plumbing obrigatório em `phase_metrics` + `health_server` + `test_dir12` (§4.1-C).
3. Reset não limpava a âncora do gate → clear no `handle_new_session` (§4.1-B).
4. Escrita direta em `_phase_results` de fora → método público `sync_phase_buffer()` (§4.1-A).
5. Comentário obsoleto l.740-742 → atualizado no mesmo diff.

**Revisor extensão MV3** (confirmou o furo C no código com trace exato; refinou o mecanismo):
1. Fantasma real explicado pela variante de **cauda truncada** (não só cabeça) — k=0 no loop pega.
2. **Furo C2 descoberto**: reentrância de `readResults` (onAlarm sem await + executeScript >2s
   quando throttled) = mesmo giro 2× com 2 flips → guard `_readBusy` (§4.2-D0).
3. Prioridade do fix E invertida: sticky frame **antes** de "maior lista" (lobby Evolution pode ter
   lista maior de OUTRA mesa → re-baseline na mesa errada) (§4.2-E).
4. Contador de skips deve ser **consecutivo e persistido** no state (SW dorme) (§4.2-D).
5. `historico_inicial` no re-baseline só com evidência de troca de mesa; senão silencioso (§4.2-D).
6. `await rehydrated` também em `onmessage` e `setDirection` (§4.2-F).
7. Seção crítica de G delimitada explicitamente; falso alinhamento k>6/overlap=1 bloqueado (1/37).
8. Fatos MV3: alarm 2s só unpacked (packed=30s); minimizar não afeta executeScript, afeta o render
   da página (fonte do DOM parcial); keepAlive 15s suficiente; Memory Saver cai no catch sem fantasma.

**Revisor rollout/risco** (verificou compose, alerts.yml, popup, testes):
1. Critério "byte-idêntico" do passo 1 era falso por construção (DIR22 sem flag) → reformulado com
   delta permitido explícito.
2. Passo 2 sem janela/exposição/abort = falso verde por ausência de tráfego → 48h + ≥5 gaps
   provocados + critérios passa/aborta (§5).
3. `obs/alerts.yml` tinha **zero** regras de fase → 2 alertas novos; detecção de regressão em ~30min
   em vez de D+7; counters zeram no restart → só `increase()/rate()`.
4. G dependia da ORDEM do rollout (frágil; rollback do servidor deixaria o cliente novo reconciliando
   contra autoridade neutralizada a cada 1s) → **capability handshake** `sentido.buffer_sync` (§4.1-D).
5. Extensão sem rollback executável → zip/tag `ext-v3.7.0` + kill-switch `DIR20_ENABLED` (§5).
6. Remediação por pares subestima contaminação (real pode ser 10–20%) → janelas entre violações +
   `shared.spin_quality` + quantificação antes da decisão (§6).
7. Meta "0 violações/dia" instável (trocas de mesa legítimas ≈ N/2) → metas escalonadas com
   atribuição de causa (§5).
8. Popup não expunha os contadores do gate do passo 4 → §4.2-H.
9. Gaps registrados como follow-up: botão de lock DIR13 no popup; aviso de flatline do seletor.

**Decisões humanas pendentes (registrar no ADENDO ISO ao implementar):** valor final de
`SDA_MIN_SPIN_INTERVAL_MS` (15000 sugerido) e aceite do custo de 1 giro em troca de mesa sem reset;
meta final de violações/dia com regra de atribuição; destino dos dados históricos contaminados
(dono do modelo, após quantificação §6.1); inclusão do botão de lock na v3.8.0 ou follow-up.

## 9. Resumo executivo

O seletor não "para de mudar" por um único bug: é um **acoplamento de 4 furos** — leitura
parcial/truncada de frame minimizado (cliente fabrica giro fantasma com fase flipada), reentrância
do loop de leitura (mesmo giro 2× com 2 flips), dedup sem plausibilidade física (servidor aceita o
fantasma), e assimetria de buffer no shift (servidor entra em rajada de `phase_uncertain` e re-ancora
a autoridade **no próprio cliente defasado** — a única assimetria de buffer do repo, verificada
exaustivamente). O fix fecha os quatro, atrás de flags com capability handshake, sem tocar contrato
WS, estratégia (INV-3) nem o fluxo SQLite→PG, com alertas de regressão (~30min), rollback executável
em cada etapa (inclusive da extensão) e metas falseáveis: **≤1 violação/dia com causa atribuída**
(hoje: 17 sem causa) e `phase_uncertain` só em troca de mesa real.

---

## 10. Soluções tecnológicas estruturadas (05/08) — parecer do sênior, 3 contrapontos e roadmap SPR-V

> Seção adicionada em 05/08. Papel assumido: **sênior aplicador de tecnologias** propôs 4
> estruturações (E1–E4) sobre a infraestrutura existente; **cada uma foi submetida a um
> agente-contraponto em discussão profunda** (visão computacional, plataforma MV3, arquitetura/risco).
> O resultado consolidado abaixo substitui o rascunho do sênior onde os contrapontos provaram defeito
> — com evidência arquivo:linha, inclusive do código-fonte do Chromium.

### 10.1 As quatro estruturações propostas pelo sênior (rascunho original)

| ID | Estruturação | Ideia central |
|---|---|---|
| **E1** | Sensor de direção no cliente | Burst de 3–4 frames via `captureVisibleTab` a 250–400ms no início do giro → processamento local (offscreen document MV3) → só o veredito `{direction, confidence}` vai ao servidor via `direction_event` (endpoint já pronto, `message_handler.py` l.1535) |
| **E2** | Trigger de início de giro | `MutationObserver` no status da rodada ("FAÇAM SUAS APOSTAS" → fechado) no `content.js` |
| **E3** | Shadow 48h antes de autoridade | Padrão DIR18: sensor roda em produção só medindo concordância; promove com >99% |
| **E4** | Auto-âncora + detecção de espelho | Visão define o seed no 1º giro da sessão e corrige espelho automaticamente |

### 10.2 Os três contrapontos — o que cada agente derrubou e o que construiu

#### 10.2.1 Contraponto VISÃO COMPUTACIONAL (algoritmo/física) — 5 defeitos fatais no E1

| # | Defeito no rascunho | Evidência |
|---|---|---|
| D1 | **Quota do Chrome mata o burst**: `MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND = 2` — burst de 250–400ms nem executa (3ª chamada no mesmo segundo falha) | `chrome/common/extensions/api/tabs.json` l.152–154 (fonte Chromium) |
| D2 | **Aliasing da bolinha**: a 1–3 rev/s, entre frames de 500–600ms a bolinha anda 180–540° → o deslocamento aparente é ruído aleatório (Nyquist) | física do problema |
| D3 | **Correlação de fase 2D mede TRANSLAÇÃO, não rotação** — sem *unwrap* polar antes, o método proposto não responde a pergunta | matemática do método |
| D4 | **Aliasing de padrão**: 37 bolsos ≈ pente de picos a cada 9,73° — correlação trava em múltiplos do período | geometria da roda |
| D5 | **"Confidence por consistência entre pares" é desonesta**: aliasing é erro sistemático — os pares erram JUNTOS e concordam entre si | estatística do estimador |

**Redesenho construtivo (Sensor R — medir o ROTOR, não a bolinha):**
a roda tem **rotor** (disco central com os bolsos, gira a 0,2–0,5 rev/s) e **estator** (anel externo
fixo, pista da bolinha). O rotor anda apenas **36–90° por 600ms** — mensurável sem aliasing na
cadência que a plataforma permite. Prior físico: a bolinha é lançada **contra** o rotor (regra padrão
da mesa) e a bolinha alterna (validado no PG) ⇒ o rotor também alterna (**hipótese H2, a validar no
spike**). Pipeline vencedor: frames → crop na ROI calibrada 256×256 → *guards* de cena (luma, NCC
contra thumbnail da calibração) → **unwrap elíptico** (720 ângulos × 16 raios — a roda em vista
oblíqua é ELIPSE; sem Hough, que é caro e quebra) → perfil angular usando **canal cromático** (o
verde do zero quebra a periodicidade dos 37 bolsos → mata D4) → *high-pass* temporal (mata trava em
overlay estático) → correlação circular 1D ±120° → consistência entre 3 pares + prior de magnitude →
confidence honesta (qualquer guard disparado → ≤0,5, abaixo do piso 0,7 da fusão → **abstenção, nunca
palpite**). Calibração: operador clica centro + 3–4 pontos da borda → ajuste de elipse, salvo com
thumbnail da cena; invalidação automática por NCC <0,6. **Motion blur de frame único NÃO recupera o
sentido** (perfil simétrico — dá orientação e velocidade, nunca a direção): frames múltiplos são
obrigatórios. Acurácia honesta esperada: sinal ≥99% dos vereditos EMITIDOS, cobertura 60–85% (o resto
é abstenção — o toggle cobre).

#### 10.2.2 Contraponto MV3/PLATAFORMA — o caminho de captura certo é outro

1. **Confirma D1** na fonte do Chromium e acrescenta: o bucket da quota é **global por extensão** —
   compartilhado com o `captureAndSendFrame` do OCR (`background.js` l.302–337). Espaçamento mínimo
   seguro ≥600ms; janela minimizada → captura **falha** (já tratado no repo, l.326–329); e falta um
   guard `tab.active` (hoje captura-se a aba ativa da janela, seja ela qual for — lixo inofensivo
   para OCR, veneno para um veredito de direção).
2. **Offscreen document é desnecessário**: o service worker MV3 tem `createImageBitmap` +
   `OffscreenCanvas` nativos — o processamento roda no SW sem permissão nova, sem lifecycle de
   singleton, sem messaging extra. Rejeitado.
3. **O desenho superior é ler o `<video>` no content script** (era a "alternativa descartada 3b"):
   a Evolution entrega a mesa via **WebRTC (`srcObject`) ou MSE** — nenhum dos dois **mancha o
   canvas** (taint é sobre origem CORS de mídia; `getImageData` funciona). O repo **já injeta**
   content script no iframe cross-origin do jogo (`deal_capture.js`, `all_frames: true`,
   manifest l.28–34). Um `direction_sense.js` novo no mesmo padrão ganha: **zero quota** (amostra
   quantos frames quiser), `requestVideoFrameCallback` com timestamps reais do stream (10–15 FPS),
   ROI em coordenadas do vídeo (invariante a zoom/janela/overlay), custo 1–3ms/frame no renderer do
   iframe — sem tocar o SW nem o read-loop. Risco residual: Evolution trocar a entrega por HLS
   cross-origin sem CORS → `SecurityError` **detectável em 1 try/catch** → fallback limpo.
4. **E2 como escrito não funciona**: `content.js` roda SÓ no top frame (manifest l.35–40, sem
   `all_frames`) — o status da rodada vive DENTRO do iframe da Evolution; o observer proposto olharia
   o DOM errado. E é redundante: o poll de 2s já computa `isOpen`/`OPEN|CLOSED` por 3 métodos
   (`background.js` l.1438–1444, l.1969–2010) — a transição OPEN→CLOSED é o "bolinha lançada" com
   ±2s de precisão, de graça. Trigger primário superior: **probe de movimento a ~1 FPS na própria
   ROI do vídeo** (o trigger e o sensor são o mesmo pixel; zero seletores novos para apodrecer).
5. **🔴 Bug de servidor latente (bloqueador de rollout)**: `handle_direction_event` grava
   `last_direction_event` (`message_handler.py` l.1546–1550) **sem TTL, sem consumo único, sem
   vínculo a giro** — e a fusão (l.799–818) o consome sempre que existir. Como a mesa **alterna a
   cada giro**, um veredito CORRETO do giro N é a direção ERRADA do giro N+1: se o sensor emitir uma
   vez e falhar na seguinte (quota, oclusão, janela fechada), o evento velho (prio 50 > toggle 10)
   **trava a direção autoritativa** → ~50% de giros errados até um reset. Hoje é inerte (não há
   produtor), mas é pré-requisito ABSOLUTO antes de qualquer cliente emitir eventos.

#### 10.2.3 Contraponto ARQUITETURA/RISCO — autoridade por-spin morre; nasce autoridade de âncora

1. **Blast radius de uma alucinação com `SDA_DIRECTION_VISION=1`** (cadeia verificada): evento errado
   → fusão flipa o spin → `process_spin` insere na **timeline errada** (`timeline_cw/ccw` —
   contaminação SEM des-inserir) → `target_timeline` seleciona a população oposta →
   `strategy.analyze` → **aposta real no racional errado** (INV-3 garante que a aposta SAI — não há
   abstenção). Pior caso: detector com ROI espelhada erra *consistentemente* → alternância fica
   perfeita no banco → **DIR22 não vê nada**.
2. **Matemática da fusão**: a projeção garante alternância, mas a correção do rótulo CW/CCW é
   **condicionada a uma âncora correta**; portanto não se pode alegar ">99,9%" sem uma referência
   externa. A razão para rejeitar autoridade per-spin é o raio de dano: um erro contamina timeline,
   população estratégica e aposta real; uma correção de âncora futura pode ser acumulada, auditada e
   revertida. Conclusão: **visão corrige âncora, nunca spin**. `SDA_DIRECTION_VISION` fica congelada em
   `0`.
3. **O shadow do E3 não existia**: com a flag OFF o evento é armazenado mas nunca comparado/medido —
   e com `SDA_SENTIDO_AUTORITATIVO=1` (default de produção), ligar a flag antiga ia **direto a
   LIVE**, pulando o próprio estágio que prometia. Precisa de flag intermediária dedicada.
4. **Gate "48h / >99%" é falseável por escassez** (200 bursts com 2 erros = "99%"): substituído por
   janela ≥7 dias E ≥2000 vereditos, concordância ≥99,5% **com V1/V2 ligados e âncora confirmada**
   (senão a referência está podre — shadow contra referência corrompida é ruído, não shadow), cobertura
   medida antes de concordância e 100% dos desacordos persistidos/auditados.
5. **E4 (auto-seed) morre**: economiza 1 clique/sessão e cria âncora automática exatamente no momento
   (início de sessão) em que não há histórico para validar o sensor. O que sobrevive dele: badge de
   `direction_source` no popup + correção de espelho por K inversões coerentes — no SPR-V7, gated.
6. **A alternativa de baixo custo — monitor estatístico server-side**: a infra já existe em produção
   (H1/`SDA_DNA_REALIZE` calcula `realized_lift_pp` por sentido e espelha ao PG). Uma inversão pode
   produzir assinatura mensurável, mas, sem referência externa, estatística **não prova** qual rótulo
   é fisicamente CW/CCW. O monitor deve ser treinado somente após V1/V2, segmentado por
   mesa/dealer/roda/regime e emitir apenas `mirror_suspect`. Ele tem valor como alarme sem pixels e
   funciona com a janela minimizada; não substitui o sensor nem pode chamar `set_seed`.

### 10.3 Síntese do sênior — o que sobrevive, o que muda, o que morre

| Rascunho | Veredito consolidado |
|---|---|
| E1 burst `captureVisibleTab` + offscreen | **REDESENHADO** → sensor primário `direction_sense.js` (content script `all_frames`, lê `<video>` via rVFC, mede o ROTOR com unwrap elíptico + canal cromático); `captureVisibleTab` fica somente para diagnóstico/fallback manual, nunca para autoridade. Offscreen document rejeitado. Frames NUNCA saem da máquina. |
| E2 MutationObserver no `content.js` | **MORTO** → trigger = probe de movimento ~1 FPS na ROI do próprio vídeo; confirmação = transição OPEN→CLOSED que o poll de 2s já entrega; `round_id` (já extraído) vira dedup por rodada. |
| E3 shadow 48h | **ENDURECIDO** → flags dedicadas, V1/V2 ligados, âncora confirmada, trilha `phase_events` e gate ≥7d/≥2000 eventos/≥99,5%/100% desacordos auditados. |
| E4 auto-âncora + espelho | **DIVIDIDO** → auto-seed CORTADO; correção de âncora por K=3 coerentes vira SPR-V7 condicional; badge/alerta operacional vira V6A e monitor estatístico segmentado vira V6B, sem ação automática. |
| (não previsto) | **NOVO pré-requisito**: `event_id + round_id + target_spin_seq + TTL + one-shot` e trilha durável (bug latente §10.2.2-5) — SPR-V4, antes de existir qualquer produtor. |

### 10.4 Desenho final consolidado

**Cadeia do sensor (quando existir, sempre shadow-first):**

```mermaid
flowchart LR
  V["&lt;video&gt; Evolution<br/>(iframe, WebRTC/MSE)"] -->|rVFC 10-15fps| DS[direction_sense.js<br/>content script all_frames]
  DS -->|probe 1fps| TRIG{movimento na ROI?}
  TRIG -->|sim| MED[medição 3-6 frames<br/>unwrap elíptico do ROTOR]
  MED -->|guards OK| VER["veredito<br/>event_id + round_id + direction + conf"]
  MED -->|guard disparou| ABST[abstenção<br/>nada é enviado]
  VER --> BG[background.js] -->|WS compacto| SRV[handle_direction_event<br/>MASTER + TTL + target_spin_seq]
  SRV --> DB[(SQLite phase_events<br/>append-only)] --> SH[shadow: coverage/agree/disagree<br/>stale/missing + alertas]
  SH -.->|"gate T4 (7d, 99,5%)"| ANC[SPR-V7: correção de ÂNCORA<br/>K=3 coerentes, nunca o spin]
  TAINT[SecurityError taint] -.-> FB[captureVisibleTab<br/>diagnóstico manual, sem autoridade]
```

**Esquema de flags (padrão do repo: `${VAR:-default}` na compose, leitura per-call em `settings.py`):**

| Flag | Default | Papel |
|---|---|---|
| `SDA_DIRECTION_VISION` | `0` **congelada para sempre** | Autoridade por-spin. Superseded — comentário na compose: "não ligar; vision corrige âncora, não spin (ver SPR-V7)". |
| `SDA_DIRECTION_VISION_SHADOW` | `0` | Compara evento fresco vs direção final pós-autoridade a cada `novo_resultado`; counters `vision_{event,agree,disagree,stale,selfcontradict}_total`; zero efeito em aposta. |
| `SDA_PHASE_EVENT_AUDIT` | `0` | Persiste `direction_event`, binding e disposição em `phase_events`; necessária para provar cobertura e auditar 100% dos desacordos. |
| `SDA_DIRECTION_VISION_TTL_MS` | `30000` | Frescor (< ciclo de 44s). Evento velho → `stale`, fora de fusão e shadow. Corrige o bug latente. |
| `SDA_VISION_ANCHOR_FIX` | `0` | (SPR-V7) correção de âncora por K coerentes. |
| `SDA_VISION_ANCHOR_K` / `_MIN_CONF` / `_REFRACT` | `3` / `0.8` / `10` | Parâmetros do guard-rail. |
| `SDA_MIRROR_SUSPECT` | `0` | (SPR-V6B) detector estatístico de espelho por janela. |
| `visionSensorPolicy` (storage.local, cliente) | `'off'` | Espelho client-side do padrão `fotoCapturePolicy` (l.285–292) + kill-switch constante. |

**Matriz pode/nunca do vision (invariável):** NUNCA toca `direcao` do spin corrente, `spin_seq`,
`timeline_cw/ccw`, decisão/stake (INV-3), nem seed com `direction_locked=true`. SÓ PODE tocar
`seed_parity/seed_n/direction_source` pelo **mesmo caminho auditável do `set_seed`**
(`source="vision"`), sob K=3 desacordos consecutivos coerentes conf≥0,8, auto-desqualificação se o
próprio sensor violar a alternância, refratário de 10 giros, máx. 1 correção automática/sessão (a 2ª
exige clique), alerta Prometheus por evento.

### 10.5 Sprints — família SPR-V (formato do board; template SPR-G2)

Ordem de execução: **V1 ∥ V2** → V3 → V4 → V6A → *(decisão humana com dados)* → V5 →
V6B → *(gate T4)* → V7. V3 pode preparar o protótipo em paralelo, mas sua medição de produção só é
válida depois de V2.

| SPR | Título | Pri | Depende de | Locks | Tam |
|---|---|---|---|---|---|
| **SPR-V1** | Blindagem servidor: ordem shift→buffer; `_last_accept_srv_mono` só após aceite; `_apply_seed(..., locked=None)` preserva lock; `set_seed/direction_event` somente MASTER; falhas de sync observáveis | P0 | — | message_handler-fase, game-state, phase_metrics, health_server, alerts, settings, tests DIR4/13/17/19/21/22 | M/L |
| **SPR-V2** | Blindagem extensão v3.8.0: hash dos 12 itens; single-writer/mutex para state; overlap estrito; resync; backoff; `unalignedStreak/skippedUnaligned` no payload e popup; lógica pura UMD com `node --test` | P0 | — (código ∥ V1; rollout após V1) | extensão JS, popup | L |
| **SPR-V3** | Spike GO/NO-GO: E0 acesso/taint/cobertura do `<video>` ativo, oculto e minimizado; E1 calibração+replay; E2 40–60 giros rotor-vs-âncora; E3 soak 2h | P1 | SPR-V2 para medição real | extensão/manifest e `tools/vision_spike/`; sem produção autoritativa | S/M |
| **SPR-V4** | Contrato e trilha durável: `event_id + round_id + target_spin_seq + TTL + one-shot`; SQLite append-only `phase_events`; shadow; counters/alertas; congela autoridade per-spin | P1 | SPR-V1; respeitar lock de dados | message_handler-fase, models/sqlite_repo, phase_metrics, health_server, alerts, settings, tests | M |
| **SPR-V6A** | Consistência operacional: alerta de gap por tamanho, stale/missing, descarte não-alinhado e possível espelho; confirmação dupla de seed + badge; nenhuma ação automática | P1 | SPR-V1, V2, V4 | popup, alerts, health_server; leitura de dados | S/M |
| **SPR-V5** | Sensor MVP shadow-only: `direction_sense.js` all_frames, rVFC, ROI/algoritmo aprovado; ring local; policy default off; fallback `captureVisibleTab` somente diagnóstico; sem offscreen document | P2 condicional | SPR-V2, **V3 GO**, V4 | extensão JS, manifest, popup | L |
| **SPR-V6B** | Baseline estatístico segmentado por mesa/dealer/roda/regime; saída somente `mirror_suspect`, nunca correção | P2 | ≥30 dias limpos após V1/V2 | job de auditoria, DNA/PG somente leitura | M |
| **SPR-V7** | Autoridade limitada à âncora futura: K/histerese/refratário/máx. correções; estado em save/load/reset; caminho `_apply_seed`; lock soberano | P3 condicional | SPR-V5 + gate T4 integral | phase/game/message_handler/settings/metrics/alerts/tests | M/L |

**Gates falseáveis:**
- **GO do V3 (destrava V5):** H2 confirmada (rotor alterna 1:1 com a âncora em ≥40 giros anotados) E
  acurácia ≥29/30 nos vereditos com anti-cena ativo E sinal ≥98% no replay E cobertura projetada ≥50%.
  NO-GO → programa de vídeo para; o valor fica coberto por V4+V6A (sunk cost = 1 spike S/M).
- **Gate T4 (destrava V7):** ≥7 dias corridos E ≥2000 vereditos em shadow com V1/V2 ligados e
  âncora confirmada; **cobertura é medida antes de concordância**; agree ≥99,5% entre os eventos
  emitidos; 100% dos desacordos auditados pela trilha `phase_events` (ring local é evidência auxiliar),
  inclusive um controle positivo com âncora deliberadamente espelhada; nenhum caso em que K=3
  coerentes teria corrigido errado; `stale+selfcontradict` <1%; cobertura ≥60% dos giros com aba
  visível (se aba visível <30%
  do tempo de operação → o programa não paga, encerrar); beat de 2s e SW sem degradação.
- **Stop-conditions do V7 ativo:** 1 correção de âncora errada → flag `=0` imediato; disagree >1%
  sustentado 24h → volta a shadow; >1 correção/sessão tentada → bug, desligar.

**Rollbacks:** servidor = flag `=0` + `up -d` (minutos) ou `git revert` via PR (~2min pós-merge);
extensão = 3 camadas (policy `'off'` no popup → kill-switch constante + reload ~30s → zip da versão
anterior anexado a cada PR ~3min).

### 10.6 Decisões que exigem humano (registrar no ADENDO ISO ao implementar)

1. GO/NO-GO do V3 é **decisão de investimento**: o spike entrega os números; o operador decide se a
   latência de correção (1–3 giros vs 30–60min do V6) paga L + manutenção perpétua de visão sobre
   layout de terceiro.
2. Aceite formal da cobertura medida no V3: `captureVisibleTab` é cego com janela minimizada; o
   comportamento do `<video>` oculto/minimizado **não deve ser presumido** — V3 mede se o player
   continua entregando frames. V6A/V6B não dependem de pixels.
3. Limiar do `mirror_suspect` (trade-off falso-positivo × latência) no brief do V6.
4. Manter `SDA_DIRECTION_VISION` congelada (flag morta documentada) vs removê-la em sprint de higiene.
5. As pendências do §8 permanecem (valor de `SDA_MIN_SPIN_INTERVAL_MS`, meta de violações/dia,
   destino dos dados históricos §6).

---

## 11. Auditoria sênior de implementabilidade (05/08) — decisão final

### 11.1 Escopo e método

Esta auditoria responde cinco perguntas: **é tecnicamente possível, cabe na capacidade atual, onde cada
mudança deve viver, qual o risco real e em que ordem implementar**. Foram cruzados:

1. hot path e autoridade em `server/message_handler.py`;
2. projeção e fusão em `state/phase.py`;
3. round-trip/reset em `state/game.py`;
4. loop MV3 em `extension/background.js`, manifesto e content scripts;
5. SQLite, outbox, PostgreSQL CW/CCW, DNA e pgvector;
6. métricas Prometheus, alertas e testes DIR existentes;
7. uma leitura somente leitura de produção;
8. contraponto independente focado em causalidade, rollout e critérios falseáveis.

O resultado é uma revisão de implementação, não uma autorização para ligar visão. O PR desta proposta
é **documental**: define o programa e os gates; cada sprint precisa de brief, worktree, testes, ADENDO
ISO e PR próprio antes de tocar produção.

### 11.2 Evidência de capacidade real

Snapshot de produção usado no parecer:

| Evidência | Estado | Consequência |
|---|---|---|
| Containers | 8 ativos/healthy; `roleta-cloud` saudável | a base operacional suporta rollout flag-gated |
| Flags | autoridade, reconcile, lock, DNA e OCR ON; `SDA_DIRECTION_VISION=0` | a visão está corretamente inerte |
| Autenticação | `AUTH_ENABLED=false` | `direction_event` e `set_seed` precisam de role-gate antes de qualquer produtor; V7 também exige hardening do handshake |
| Host | QEMU, 4 vCPU, sem SSE4.2/AVX2 | visão pesada no servidor é NO-GO; Canvas no cliente é a escolha correta |
| DNA PG | CW 23.086/18.561 realizadas; CCW 21.215/16.964 realizadas | há volume segregado suficiente para auditoria futura |
| `spin_features` PG | CW 3.160; CCW 2.928 | a fundação por sentido existe e está populada |
| Prometheus | séries de fase expostas | V1/V2 podem ser observadas sem SaaS |
| Sintoma recente | 2 `phase_uncertain` + DIR17 em 11s após restart | confirma V1/V2 como P0, não hipótese teórica |

**Capacidade:** o software consegue executar V1–V4 e V6A com a stack atual. Não precisa de serviço de
visão, fila SaaS nem banco adicional. Chrome MV3/Canvas, Python, SQLite, PostgreSQL,
pgvector e Prometheus já cobrem a necessidade. O sensor de vídeo também cabe, mas somente no cliente
e apenas se o preflight V3 provar acesso e cobertura.

### 11.3 Veredito item a item

| Componente | Veredito | Por quê |
|---|---|---|
| **V1 — reconciliação/autoridade** | **GO agora** | corrige causa comprovada; risco controlável com flags e testes por gap |
| **V2 — ingestão MV3** | **GO agora** | fecha fantasma, reentrância, hash parcial e perda silenciosa; sem isso o servidor continua recebendo evidência ruim |
| **V3 — preflight de vídeo** | **GO como experimento** | baixo custo para responder acesso, taint, rotor e cobertura; não produz autoridade |
| **V4 — contrato/trilha** | **GO após V1** | elimina evento velho e cria prova durável para os gates |
| **V6A — consistência operacional** | **GO** | maior ganho por custo; alerta sem alterar fase |
| **V6B — inferência estatística** | **HOLD** | dados atuais ainda podem conter espelho/contaminação; sem referência externa emite apenas suspeita |
| **V5 — sensor shadow** | **NO-GO agora; condicional** | só começa se V3 provar H2, acesso e cobertura |
| **V7 — correção automática de âncora** | **NO-GO agora** | exige V4, estado persistido, autenticação/role-gate e T4 integral |
| Autoridade vision per-spin | **REJEITADA** | um único erro contamina timeline, população estratégica e aposta |
| Processar visão no Debian | **REJEITADO** | CPU inadequada e custo sem benefício; pixels já vivem no navegador |

Portanto, a proposta é **implementável**, mas não está "100% funcional" hoje: a fundação de dados
está operacional; a ressincronização ainda tem falhas ativas; o sensor não existe; e autoridade
automática continua deliberadamente bloqueada.

### 11.4 Desenho técnico obrigatório por fase

#### A. V1 — servidor: corrigir a verdade antes de sofisticar o sensor

1. No servidor, executar `reconcile_shift`, avançar `spin_seq`, sincronizar `_phase_results` com os
   intermediários e só então inserir o giro atual. Testar gaps `k=1..11`; `k>11` deve retornar
   `phase_uncertain` explícito, pois não existe overlap no histórico de 12 números.
2. Criar `_apply_seed(direction, source, locked=None)`. `locked=None` preserva o estado atual; omitir
   o campo nunca destrava o operador. `source="vision"` é recusado quando há lock explícito.
3. Colocar `set_seed` e `direction_event` no gate de mensagens MASTER. Hoje novas conexões assumem
   MASTER e `AUTH_ENABLED=false`; portanto isso evita conflito entre clientes, mas **não substitui
   autenticação**.
4. Armar `_last_accept_srv_mono` somente depois de o giro atravessar dedup, plausibilidade e
   processamento aceito. Rejeição não atualiza o relógio; reset de sessão o limpa.
5. Não esconder erro de buffer com `except Exception: pass`. A ausência de `_phase_results` deve
   incrementar métrica e gerar log de erro sem produzir sucesso falso.

#### B. V2 — extensão: um escritor e um baseline íntegro

1. O fingerprint deve cobrir os **12** números usados pelo alinhamento, não somente os cinco
   primeiros.
2. `countNewSpins` retorna `{k, matched, overlap}`. Sem match, não envia `novo_resultado`, não flipa a
   direção e não atualiza o baseline como se houvesse aceite.
3. Serializar todas as mutações de estado do read-loop, não apenas `readResults`; `getState/saveState`,
   `state_sync`, reidratação e toggle não podem intercalar escrita.
4. Persistir e transmitir `unalignedStreak`, `skippedUnaligned`, motivo do skip, frame/round selecionado
   e versão da extensão. Fix D sem telemetria apenas trocaria giro fantasma por parada silenciosa.
5. Extrair fingerprint, overlap e decisão de re-baseline para módulo UMD puro; validar com
   `node --test`, sem framework ou dependência nova.
6. No rollout, comparar giros recebidos em 24h com baseline: variação maior que ±10% bloqueia avanço.

#### C. V3/V5 — de onde vem o sentido físico

A única fonte tecnológica capaz de observar o sentido sem clique humano é a **sequência de frames do
vídeo Evolution**. DOM fornece números; foto estática não fornece movimento; DNA detecta anomalia
estatística com atraso, mas não prova CW/CCW.

O content script mede o rotor no `<video>`, produz evidência e envia:

```json
{
  "type": "direction_event",
  "event_id": "uuid",
  "round_id": "id-quando-disponivel",
  "direction": "cw",
  "confidence": 0.97,
  "captured_at_ms": 1760000000000,
  "frame_count": 6,
  "sensor_version": "r1",
  "calibration_id": "cal-..."
}
```

O servidor acrescenta `session_id`, `received_at`, `target_spin_seq` e disposição. O binding só vale
quando:

1. `round_id` coincide, se ambos os lados o tiverem;
2. `target_spin_seq` é o esperado;
3. idade está dentro do TTL;
4. o evento ainda não foi consumido.

Evento sem esses quatro requisitos vira `stale/unbound`, nunca direção. Isso é o mecanismo de
auto-sincronização: **evento identificável + giro-alvo + TTL + one-shot**, e não "o frame mais recente".

#### D. V4 — onde persistir e por quê

`phase_events` deve nascer no **SQLite local**, append-only, porque é trilha de controle do hot path e
precisa sobreviver a restart. `received` é inserido no ingresso; a comparação final é anexada na mesma
fronteira transacional que persiste a decisão. Um evento pendente é reconstruído da última linha
`received` sem disposição terminal; se também houver cache em `GameState`, ele entra em
`save/load/reset`. Estrutura mínima:

```sql
CREATE TABLE phase_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  ts_srv_ms INTEGER NOT NULL,
  session_id TEXT NOT NULL,
  round_id TEXT,
  target_spin_seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  source TEXT NOT NULL,
  observed_direction TEXT,
  reference_direction TEXT,
  confidence REAL,
  decision_ref TEXT,
  meta_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(event_id, kind)
);
CREATE INDEX ix_phase_events_session_spin
  ON phase_events(session_id, target_spin_seq);
```

Cada transição acrescenta uma linha imutável: `received`, `bound`, `agree`, `disagree`, `stale`,
`unbound`, `missing` ou `selfcontradict`; a chave `(event_id, kind)` torna retry idempotente. Para
`missing`, o servidor gera um ID determinístico por sessão/giro. Retenção inicial: 30 dias. Frames não
entram no banco; somente metadados.

A criação é aditiva (`CREATE TABLE/INDEX IF NOT EXISTS`). Rollback desliga a flag e preserva a tabela;
não há `DROP` nem downgrade destrutivo.

**Por que não pgvector:** esse evento é categórico, temporal e auditável; busca vetorial não agrega
valor e dificultaria integridade. pgvector permanece para embeddings/vetores de contexto. Se depois
for necessário dashboard histórico central, a outbox pode espelhar `phase_events` no PG com migração
Alembic aditiva **0014** (a cabeça atual é 0013), somente após liberar o lock `schema/alembic`.

#### E. V6 — o que estatística consegue e o que não consegue

DNA por CW/CCW ajuda a encontrar inversões de comportamento, mas sem sensor externo não prova qual
rótulo é fisicamente correto. V6A pode emitir alertas operacionais. V6B só começa após V1/V2 e exige
baseline por mesa, dealer, roda e regime; sua saída é `mirror_suspect`, nunca `set_seed`.

#### F. V7 — correção restrita à âncora futura

Após T4, K desacordos coerentes podem solicitar `_apply_seed` para o giro seguinte. `streak`,
candidato, refratário, contagem de correções e evidência precisam entrar em `save()`, `load()` e
`reset_session()`. Limites: máximo uma correção automática por sessão; segunda tentativa exige
operador; lock manual vence sempre.

### 11.5 Dificuldade e esforço

Estimativa de engenharia, excluindo a janela de observação: S=1–2 dias, M=3–5, L=6–10.

| Fase | Dificuldade | Esforço | Principal risco |
|---|---:|---:|---|
| V1 | M/L | 4–7 dias | ordem do hot path e lock do operador |
| V2 | L | 6–10 dias | concorrência MV3 e regressão silenciosa de ingestão |
| V3 | S/M | 2–4 dias + 40–60 giros | acesso ao vídeo/taint e hipótese rotor↔sentido |
| V4 | M | 3–5 dias | binding correto e escrita sem alongar o hot path |
| V6A | S/M | 2–3 dias | falso alerta sem segmentação de sessão |
| V6B | M | 3–5 dias após 30 dias limpos | confundir correlação com verdade física |
| V5 | L | 6–10 dias + shadow | layout de terceiro, cobertura e calibração |
| V7 | M/L | 4–7 dias + canário | correção errada de âncora |

V1 e V2 podem ser desenvolvidas em paralelo porque os locks são servidor e extensão; o rollout deve
ser V1 antes de V2. V4 não deve disputar `schema/alembic` com SPR-G2; a primeira versão SQLite evita
essa colisão.

### 11.6 Gates de aceite que provam sucesso

| Gate | Prova mínima | Falha/stop-condition |
|---|---|---|
| **T0 — unitário** | Python DIR verde; JS `node --test`; save/load/reset de todo estado novo | qualquer regressão de aposta, lock ou round-trip |
| **T1 — replay de gaps** | casos k=1..11 passam; k>11 classificado; métricas por k | `phase_uncertain` em gap com overlap |
| **T2 — ingestão** | descarte aparece no servidor/popup; hash-12; nenhum envio unaligned | giros recebidos 24h fora de ±10% |
| **T3 — produção base** | 48h; ≥5 gaps provocados; zero rajada DIR17; zero violação intra-sessão sem causa | descarte com delta >20s ou nova rajada |
| **T4 — shadow vision** | ≥7d e ≥2000 eventos; cobertura antes de acordo; agree ≥99,5%; 100% desacordos auditados; controle positivo com seed espelhado | K=3 produziria uma correção errada, cobertura insuficiente ou degradação do beat |
| **T5 — V7 canário** | uma sessão por vez, máx. 1 fix, operador confirma resultado | uma correção errada desliga a flag imediatamente |

Prometheus sozinho não satisfaz T4: counters reiniciam com o container e logs têm retenção limitada.
`phase_events` é requisito de evidência, não luxo analítico.

### 11.7 Segurança, custo e manutenção

1. O compose publica WS/health em loopback, mas a produção está com `AUTH_ENABLED=false`.
2. `verify_auth(None)` significa que simplesmente ligar auth hoje rejeitaria todas as conexões; o token
   precisa ser extraído do handshake e enviado pela extensão em uma tarefa de hardening.
3. Role-gate MASTER entra em V1; autenticação funcional é bloqueador de V7 ou de qualquer exposição
   do endpoint a clientes não confiáveis.
4. Nenhum segredo fica hardcoded; parâmetros novos nascem default-OFF e são lidos por chamada.
5. Não há custo SaaS novo. O custo real é engenharia/manutenção do sensor contra mudanças do layout
   Evolution; por isso V3 existe como stop barato.
6. O armazenamento de eventos é pequeno: ~100–300 bytes por giro; 30 dias é desprezível frente aos
   bancos atuais.

### 11.8 Decisão de implementação

**Implementar:** V1, V2, V3, V4 e V6A, nessa ordem operacional, cada uma com brief e PR próprios.

**Aguardar evidência:** V6B.

**Não implementar ainda:** V5 e V7. V5 só após GO técnico do V3; V7 só após T4, autenticação/role-gate,
round-trip completo e canário. `SDA_DIRECTION_VISION` permanece `0`.

Essa sequência elimina o bug observado e fortalece a fundação de dados sem trocar uma falha visível
por corrupção silenciosa, sem introduzir SaaS e sem permitir que um sensor experimental altere a
estratégia ou a aposta real.
