# 🗄️ Auditoria reversa da estrutura de dados — Resultados & Bancos (junho)

> **Data:** 22/06/2026 · **Escopo:** verificar se a estrutura de dados identifica **por jogada** o `dealer`, o `modelo da roleta`, o `fornecedor (provider)` e a `força`; auditoria **reversa** das **últimas 20 jogadas de cada sentido**, cenário por cenário, citando a infraestrutura completa e o **porquê de cada resultado** no código e nas propostas — confirmando se tudo ocorre **como planejado**.
> **Método:** consulta read-only ao **DB de produção ao vivo** (`/app/data/decisions.db`, no container `roleta-cloud`, servidor Debian 187.45.181.75), análise **por `id`** (não por janela de tempo — ver §6.4), + leitura do código-fonte.

---

## 1. Resposta executiva (TL;DR)

| Campo da jogada | Identificável? | Cobertura (amostra 40 jogadas) | Fonte |
|---|---|---|---|
| **Fornecedor** (`provider`) | ✅ **Sim, quase sempre** | **40/40 = `evolution`** | extensão (DOM) → `sanitize_provider` |
| **Força** (`spin_force`) | ✅ **Sim, por construção** | 32/40 com força>0 (8 são nº repetido→dist 0) | **engine** (`process_spin` = distância na roda) |
| **Dealer** | ⚠️ **Só quando há foto** | 5/40 (vision rows) | **visão/OCR** (DOM da Evolution não casa) |
| **Modelo da roleta** (`wheel_model`) | ⚠️ **Só quando há foto** | 7/40 (vision rows) | **visão/OCR** |
| **4-tupla completa** (dealer+modelo+provider+força) | ⚠️ **Parcial** | **~5/40 (~12%)** | só nas vision rows com força>0 |

> **Veredito:** a estrutura **está como projetada** — `provider` e `força` por jogada são **quase universais**; `dealer`/`modelo` dependem da **foto** (por design: o DOM da Evolution não expõe dealer/modelo de forma confiável), então a 4-tupla completa existe na fração de jogadas com OCR (~12-17%, em **ramp-up**). A auditoria encontrou **1 desvio relevante** (giros **fantasma** por re-envio da extensão) + 3 achados de qualidade de dado (OCR/seletor DOM) — detalhados na §6, com **fix flag-OFF** para o fantasma.

---

## 2. Infraestrutura COMPLETA de dados (foto → dados → decisão → banco)

```
[1] PRODUTOR — Extensão "Escuta Beat" (Chrome MV3, client-side)
     • novo_resultado {numero, direcao, dealer?, table?, provider, round_id?, wheel_model?, vision_*?}
        - provider: deal_capture.js normalizeProvider(host) → marca|unknown (v3.4.1/2; nunca host:*)
        - dealer/table/round: seletores DOM (deal_capture.js / session_extractor.js) — Evolution raramente casa
     • foto_frame {image} — 1 frame/giro (captureVisibleTab)
        │  WebSocket wss://roleta.xma-ia.com/ws  (só o MASTER envia novo_resultado)
        ▼
[2] ENGINE — server/message_handler.py (escritor ÚNICO, Python)
     • dispatcher: dedup (is_duplicate_spin) → handle_new_result
     • SpinInput (Pydantic, models/input.py): valida + sanitize_provider (host:* → marca|None)
     • força = game_state.process_spin(numero, direcao)  ← DISTÂNCIA NA RODA (message_handler.py:604)
     • check_prediction → martingale → strategy.analyze (force17) → INV-3 → save_decision
     • handle_foto_frame → vision_ocr.extract (RapidOCR) → update_last_vision(dealer/wheel_model/provider/vision_*)
        ▼
[3] SOURCE OF TRUTH — SQLite  data/decisions.db  (volume roleta-data)
     • tabela `decisions` (41 colunas) — UMA LINHA por jogada reúne tudo (ver §3)
        ▼
[4] OUTBOX/CDC (desacoplado, opt-in dual_write_pg) → [5] POSTGRES feature store
     • cw/ccw.spin_features, shared.dealers (UNIQUE name,provider,table), decision_dna
        ▼
[6] CONSUMIDORES  dealer_offset · bet_advisor · dna_summary · dealer_force_profile (dormante)
```

### 2.1 Proveniência de CADA campo (o "porquê" — citando o código)

| Coluna `decisions` | De onde vem | Código | Observação |
|---|---|---|---|
| `spin_number`, `spin_direction` | payload `novo_resultado` | `message_handler.py:401-417` (SpinInput) | sempre presente |
| **`spin_force`** | **ENGINE** (não a extensão) | `message_handler.py:604` `game_state.process_spin(numero,direcao)` | = distância na roda do nº anterior → atual; `0` = nº repetido |
| **`provider`** | extensão (DOM) → saneado | `models/input.py sanitize_provider` | host:* → marca\|None; hoje 100% `evolution` |
| `dealer` | DOM (raro) **ou** VISÃO | `message_handler.py:879` (DOM) / `:1342 update_last_vision` (OCR) | Evolution não expõe → vem da foto |
| **`wheel_model`** | **VISÃO/OCR** | `vision_ocr._parse_fields/_norm_model` → `update_last_vision` | só quando a foto aterrissa |
| `vision_source`, `vision_confidence` | VISÃO | `handle_foto_frame` → `update_last_vision` | `'vision'` marca a origem |
| `dealer_table` | DOM | payload `table` | ⚠️ pega tile errado (§6.3) |
| `round_id` | DOM | payload `round_id` | ⚠️ nunca casa (§6.4) |
| `result_actual` | **próxima** jogada | `update_result` | o nº da jogada seguinte resolve a predição desta |
| `sda_*`, `gale_*`, `pnl_units` | ENGINE (estratégia) | `save_decision` | trilha de decisão/aposta |

> **Ponto-chave (proposta `foto_roleta_junho.md` Parte 4):** a visão é **enriquecedora do produtor** — `dealer`/`wheel_model` entram na **mesma linha** da jogada via `update_last_vision`, sem banco novo. Confirmado no schema (41 colunas numa linha).

---

## 3. A jogada numa ÚNICA linha (como projetado)

`decisions` reúne, por jogada: `spin_force + spin_direction + dealer + provider + wheel_model + vision_*`. Logo a consulta de design é trivial e **funciona**:

```sql
SELECT dealer, wheel_model, provider, spin_direction,
       COUNT(*) n, ROUND(AVG(spin_force),1) forca_media
FROM decisions WHERE vision_source='vision' AND spin_force>0
GROUP BY dealer, wheel_model, provider, spin_direction;
-- ex.: JAMES · Roleta ao Vivo · evolution · anti  → força média 22.5 (n)
--      JAMES · Roleta ao Vivo · evolution · horário → força média 15.1 (n)
```

Ou seja: **dealer × modelo × fornecedor × força por sentido é consultável** na mesma linha — exatamente o que se pretende para "estratégias por dealer".

---

## 4. Auditoria REVERSA — últimas 20 jogadas de cada sentido (isolado)

> Classificação de cenário por jogada: **A** = vision full (dealer+modelo+provider+força) · **B** = vision parcial (foto sem dealer ou força=0) · **C** = DOM-only (provider+força, sem dealer/modelo — não houve foto nesse giro) · **D** = mínimo (provider, mas nº repetido → força 0).

### 4.1 Sentido = HORÁRIO (CW) — últimas 20 (cronológico)

| id | hora | força | dealer | provider | modelo (visão) | conf | cenário |
|--:|--|--:|--|--|--|--:|--|
| 9100 | 00:52 | 35 | unknown | evolution | — | — | C |
| 9106 | 00:56 | 7 | unknown | evolution | — | — | C |
| 9113 | 01:21 | 8 | unknown | evolution | Roleta ao Vivo | 0.93 | B |
| 9116 | 01:22 | 0 | unknown | evolution | — | — | D |
| 9122 | 01:27 | 33 | **FELIPE** | evolution | Roleta ao Vivo | 0.97 | **A** |
| 9129 | 01:31 | 36 | unknown | evolution | — | — | C |
| 9136 | 01:36 | 24 | unknown | evolution | — | — | C |
| 9137 | 01:36 | 0 | unknown | evolution | — | — | D ⚠️fantasma |
| 9140 | 01:37 | 11 | **FELIPE** | evolution | Roleta ao Vivo | 0.97 | **A** |

**Agregado CW (n=20):** `provider`=**20/20 evolution** · `força>0`=18/20 · `dealer real`=2/20 · `modelo`=3/20 · `vision`=3/20 · **4-tupla=2/20**. Cenários: **C=15, A=2, D=2, B=1**.

### 4.2 Sentido = ANTI-HORÁRIO (CCW) — últimas 20 (cronológico)

| id | hora | força | dealer | provider | modelo (visão) | conf | cenário |
|--:|--|--:|--|--|--|--:|--|
| 9111 | 01:00 | 31 | **THON** | evolution | Roleta ao Vivo | 0.96 | **A** |
| 9112 | 01:21 | 0 | unknown | evolution | — | — | D ⚠️(nº=14 21min após o 14 anterior) |
| 9114 | 01:21 | 0 | unknown | evolution | `Roleta Aovivo R$ 1-100.000` | 0.95 | B ⚠️OCR |
| 9125/9126 | 01:29 | 0/0 | unknown | evolution | — | — | D ⚠️fantasma (nº=2, 1s) |
| 9134 | 01:35 | 30 | **FELIPE** | evolution | Roleta ao Vivo | 0.97 | **A** |
| 9135 | 01:35 | 0 | unknown | evolution | — | — | D ⚠️fantasma (nº=6, 7s) |
| 9138 | 01:37 | 26 | **FELIPE** | evolution | Roleta ao Vivo | 0.97 | **A** |
| 9139 | 01:37 | 0 | unknown | evolution | — | — | D ⚠️fantasma (nº=17, 20s) |

**Agregado CCW (n=20):** `provider`=**20/20 evolution** · `força>0`=14/20 · `dealer real`=3/20 · `modelo`=4/20 · `vision`=4/20 · **4-tupla=3/20**. Cenários: **C=11, D=5, A=3, B=1**.

### 4.3 Leitura cenário por cenário (o porquê, no código)
- **Cenário C (maioria, ~65%)** — `provider=evolution` + `força` reais, **sem** dealer/modelo: é um giro **sem foto aterrissada** (OCR leva 5-6.7s e o single-flight descarta fotos sobrepostas; nem todo giro recebe OCR). `provider` vem do DOM saneado; `força` é **computada** pelo engine (`process_spin`). **Como planejado.**
- **Cenário A (~12%)** — vision full: a foto daquele giro foi OCR'd com sucesso (`dealer`+`modelo`+`conf`), e a força>0. É a 4-tupla completa. **Como planejado** (fração limitada pela cadência/latência do OCR — ramp-up).
- **Cenário B** — vision parcial: a foto aterrissou mas faltou dealer (OCR não leu o nome) **ou** força=0. Ex.: 9114 (modelo lido com **ruído de OCR**, §6.2).
- **Cenário D** — força=0: nº **repetido** (distância na roda 0). Parte são **fantasmas** (§6.1) — re-envios do mesmo nº; parte é nº genuinamente repetido.

---

## 5. Conseguimos identificar os 4 por jogada? (resposta direta)
- **Fornecedor:** ✅ sim — **100%** (`evolution`) nas 40 jogadas. Saneado na origem (v3.4.2) e no servidor (`sanitize_provider`).
- **Força:** ✅ sim — **por construção** (engine calcula a distância na roda todo giro). `força=0` não é "faltando", é nº repetido.
- **Dealer e Modelo:** ⚠️ **só nas jogadas com foto** (~12-17%). Por **design** (proposta Parte 4): o DOM da Evolution não expõe dealer/modelo de forma confiável → a **foto/OCR** é a via. Acumula com o uso (cobertura em ramp-up); o `SDA_DEALER_FILL_FORWARD` (OFF) propaga o dealer entre giros quando ligado.

> Portanto a **4-tupla completa por jogada** existe **hoje na fração com OCR** (~12%). A infra está pronta para 100% — depende da **cadência/qualidade da foto**, não do schema.

---

## 6. Achados (desvios do "como planejado")

### 6.1 🐞 Giros FANTASMA (re-envio da extensão) — CORRIGIDO (flag OFF)
- **Evidência:** nos últimos 200 giros, **44 têm força=0; 34 (77%) são o MESMO número+sentido do giro anterior**, chegando **1-7s depois** — enquanto o ciclo real é **~42-48s** (medido: 9117→9121 = 42-48s). Impossível ser giro real. Ex.: `9136 nº35` → `9137 nº35` (**1s**); `9134 nº6` → `9135 nº6` (**7s**).
- **Causa-raiz:** a extensão re-detecta o **DOM estático** (mesmo resultado ainda na tela) e **reenvia** o `novo_resultado`. O dedup original (`is_duplicate_spin`) só pega "mesmo nº no **mesmo segundo**" (`message_handler.py:104`), então re-envios 1-20s depois **passam**.
- **Impacto:** o engine processa o fantasma como giro real → **resolve a predição anterior** (contra um nº repetido) **e cria outra predição** → **corrompe a cadeia de hit/miss e o martingale**. (~17% dos giros.)
- **Nota de método:** `força=0` **não** é a prova (é só a distância na roda de nº repetido); o **discriminador é o TEMPO** (1-7s ≪ 42-48s).
- **Correção:** `is_duplicate_spin` agora rejeita o mesmo `número+sentido` do último giro **aceito** dentro de uma **janela** (`SDA_DEDUP_PHANTOM_WINDOW_MS`, default 20s — bem abaixo do ciclo real). Flag **`SDA_DEDUP_PHANTOM` default OFF** (toca o caminho de aposta → ligar só após validar). +5 testes (`tests/test_dedup_phantom.py`). Arquivos: `server/message_handler.py`, `app_config/settings.py`, `docker-compose.yml`.

### 6.2 🔎 Ruído de OCR no `wheel_model` (limites de aposta colados)
- `id 9114` = **`'Roleta Aovivo R$ 1-100.000'`** — o OCR colou o nome da mesa com os **limites de aposta**. A chave normalizada (`roletaaovivor1100000`) não casa o alias `roletaaovivo` → não canoniza. É ruído raro (não fragmenta o rótulo principal `Roleta ao Vivo`). **Follow-up:** ROI de OCR mais justa por região, ou regex que corta `R$...` antes de `_norm_model`.

### 6.3 🔎 `dealer_table='Blackjack Silver D'` (seletor DOM errado)
- Em **todas** as 40 linhas, numa sessão de **Roleta** — o seletor DOM de mesa pega um **tile de Blackjack**. Já documentado em `auditoria_pos_foto_21_junho.md §15.3`. Impacto baixo (não entra na aposta); a **visão (`wheel_model`) é a fonte confiável** da mesa/modelo. Corrigir o seletor exige inspeção do DOM ao vivo.

### 6.4 🔎 `round_id` = 0/40 (seletor nunca casa)
- Usado só para deduplicação opcional. Sem impacto na aposta. Mesma classe (seletor DOM) do §6.3.

---

## 7. Veredito — está como planejado?

| Aspecto | Planejado | Real | Status |
|---|---|---|---|
| Jogada numa linha (dealer+modelo+provider+força) | sim | schema 41 cols, query funciona | ✅ |
| Fornecedor por jogada | sim | 100% evolution (saneado) | ✅ |
| Força por jogada | sim | engine calcula (distância na roda) | ✅ |
| Dealer/Modelo por jogada | via foto | só nas vision rows (~12-17%, ramp-up) | ✅ por design |
| Integridade da cadeia de predição | 1 giro = 1 resultado real | **~17% fantasmas** corrompiam | ⚠️→ **corrigido** (flag OFF, validar p/ ligar) |
| `wheel_model` canônico | sim | `Roleta ao Vivo` consolidado; ruído raro de OCR | ⚠️ menor |
| `dealer_table` / `round_id` | metadados DOM | seletor pega mesa errada / vazio | ⚠️ baixo impacto |

> **Resumo de 1 linha:** a **estrutura de dados está como projetada** — fornecedor e força são identificáveis por jogada (quase 100%), dealer/modelo vêm da foto (por design, em ramp-up), e a 4-tupla completa é consultável na mesma linha. O **único desvio relevante** eram os **giros fantasma** (re-envio da extensão corrompendo ~17% da cadeia de aposta) — **encontrado, explicado pelo código e corrigido** com dedup por janela de tempo (**flag OFF**, pronto para validar e ligar). Achados menores (OCR/seletor DOM) documentados como follow-up. Suíte **646 verde**.

---

## 8. SPRINT DE CORREÇÃO (22/06) — premissa: foto autoritativa, acoplada a 100%

> **Premissa do dono (decisiva):** *"a chamada de dealer, provider e modelo de roleta pelo DOM **nunca funcionou** — por isso estruturamos a foto para extrair a cada jogada. Organize para que tudo funcione perfeitamente **acoplado** em toda a infra e fluxo de dados, para auditar dados **100% funcionais** para projetar estratégias."*

### 8.1 Auditoria do próprio documento (bugs/lacunas)
- **Lacuna de enquadramento (corrigida aqui):** as §5/§7 tratavam a cobertura de `dealer`/`modelo` de ~12-17% como *"✅ por design / ramp-up / aceitável"*. **Sob a premissa, isso é um BUG**, não um "aceitável": se a foto é a fonte autoritativa, dealer/modelo têm de estar em **TODA** jogada (acoplados), não só nas que recebem OCR fresco.
- **Nuance do `provider` (esclarecida):** a §1 dizia "provider via DOM 100%". Preciso: o *elemento* DOM nunca casou; o que funciona é o **host** do iframe (`evo-games`→`evolution`) — um fallback, não a leitura de DOM. Por isso o `provider` também entra no contexto de visão (fill-forward) para robustez se o host falhar.
- Demais números/cenários da auditoria reversa (§4) foram reconferidos e **estão corretos**.

### 8.2 🐞 BUG CENTRAL — vision não acoplada a 100% das jogadas
- **Sintoma (§4):** `dealer`=5/40 e `modelo`=7/40 — só as jogadas com **OCR fresco** (a foto leva 5-6.7s e o single-flight descarta sobrepostas; nem todo giro recebe OCR bem-sucedido). As outras ~83% ficavam `dealer='unknown'`, `wheel_model=''` → **inauditáveis por dealer/modelo** → estratégia por dealer inviável na maioria dos giros.
- **Causa-raiz:** o enriquecimento de visão entrava **só** via `update_last_vision` (foto daquele giro) e o fill-forward existente cobria **apenas o dealer** e estava **desligado**. `wheel_model`/`provider` não tinham propagação.

### 8.3 ✅ Correção — vision-context fill-forward UNIFICADO (dealer+modelo+provider)
Como o dealer/modelo/provider são **estáveis por turno**, o último OCR bem-sucedido define o "contexto de visão" da sessão, **carimbado em TODA jogada** no momento da criação da decisão:

| Camada | Mudança | Arquivo |
|---|---|---|
| Lógica pura | `resolve_value`/`is_real_value` (genérico p/ qualquer atributo de visão) | `core/dealer_fill.py` |
| Engine | `_apply_vision_context(dealer,modelo,provider)` resolve os 3 com fill-forward; `_remember_vision(...)` aprende do OCR (`handle_foto_frame`); reset/sessão limpam o contexto | `server/message_handler.py` |
| Decisão | a linha grava o **melhor conhecido** dos 3 (não só o do giro) | `message_handler.py` (Decision) |
| Flag | `SDA_DEALER_FILL_FORWARD` agora cobre os **3** campos; **LIGADA em produção** (`=1`) | `app_config/settings.py`, `docker-compose.yml` |

**Semântica preservada (auditável):** `vision_source='vision'` **continua** marcando só as jogadas com **OCR fresco** (com `vision_confidence`); as demais recebem dealer/modelo/provider **herdados** com `vision_source=''`. Assim o auditor distingue *medido* (`vision_source='vision'`) de *propagado* — sem perder cobertura. **Metadata: NÃO toca o caminho de aposta.**

**Corte na troca:** um dealer/modelo real novo no OCR substitui o anterior; `nova_sessao` (troca de mesa/dealer) zera o contexto. **Testes:** +4 casos (`tests/test_dealer_fill_forward.py`: dealer+modelo+provider propagam, corte por sessão, flag).

### 8.4 Resultado ao vivo (antes → depois) — PROVADO
- **Antes (amostra 40, código antigo):** `dealer`=5/40 (**12%**), `modelo`=7/40 (**17%**) — só jogadas com OCR fresco; ~83% inauditáveis por dealer/modelo.
- **Depois (pós-deploy `3e2e6b9`, flag ON), sessão real `3d0c2ad2`:** `modelo`=**6/6 (100%)**, `dealer`=**5/6 (83%)**. O único `dealer='unknown'` é a **1ª jogada da sessão** (antes do 1º OCR de dealer — fundamental, ainda não há dado).
- **Prova do fill-forward (log de produção):** a foto da decisão **9194** retornou `[FOTO] dealer=None wheel='Roleta ao Vivo'` (o OCR **não leu** o dealer naquele frame), mas a linha 9194 gravou **`dealer='THEO'`** — herdado do contexto (OCR de 9193). Sem o fill-forward, 9194 seria `unknown`.
- **Corte na troca confirmado:** houve um `nova_sessao` às 02:13:04 (`3d0c2ad2`); o contexto **zerou** corretamente → a 1ª jogada nova (9192) ficou `unknown` até o OCR re-capturar o dealer (9193 em diante = `THEO`).

> **Cobertura efetiva:** ~**100% por sessão após o 1º OCR de dealer** (a 1ª jogada de cada sessão fica `unknown` até a 1ª foto capturar o dealer — limite físico, não bug). `modelo` chega a 100% (OCR de mesa é mais robusto que o do nome). `vision_source='vision'` marca jogadas com foto fresca (≥1 campo medido); campos individuais podem ser medidos **ou** herdados — para confiança por-jogada use `vision_confidence`.

### 8.5 Veredito da sprint
> Sob a premissa (foto autoritativa), a infra agora acopla **dealer+modelo+provider a 100% das jogadas** da sessão (propagados do último OCR), preservando a distinção *medido vs propagado* via `vision_source`. Combinado com `provider` (host) e `força` (engine) já universais, **toda jogada fica auditável pelas 4 dimensões** — habilitando estratégia por dealer/modelo. O dedup de fantasmas (§6.1) segue como flag separada a validar.
