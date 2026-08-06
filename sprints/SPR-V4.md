# SPR-V4 · Contrato `direction_event` + trilha `phase_events` (SQLite, append-only, shadow-only) · Bloco BLK-D/BLK-I · Pri P1

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §10.2.2-5 (bug latente), §10.4, §10.5, §11.4-C/D, §11.6.

## Meta
```text
blocked_by: [SPR-V1]                # semântica (fail-close da visão + _apply_seed) E lock de message_handler
locks:      [message_handler-fase, sqlite_repo, game-state, phase_metrics, health_server, alerts,
             settings, compose, tests]
touches:    [server/message_handler.py, database/sqlite_repo.py, state/game.py, state/phase_metrics.py,
             server/health_server.py, obs/alerts.yml, app_config/settings.py, docker-compose.yml, tests/]
base_sha:   origin/main             # rebasear após o merge do SPR-V1
branch:     spr/SPR-V4
```
**Serialização obrigatória:** SPR-G2 também toca `database/sqlite_repo.py` e
`server/message_handler.py`. **Não rode em paralelo com SPR-G2.** Confirme com o Diretor qual dos dois
está em voo antes de começar. **Sem Alembic nesta fase** (a trilha nasce em SQLite local) —
justamente para não disputar o lock `schema/alembic`.

## Setup (worktree próprio)
```text
git -C "C:\Users\Windows\Desktop\Roleta Cloud" worktree add ..\rc-SPR-V4 spr/SPR-V4
cd ..\rc-SPR-V4
```

## Objetivo (1 frase)
Transformar `direction_event` de "última coisa que chegou" em **evento identificável, vinculado a um
giro-alvo, com prazo de validade e consumo único** — e criar a **prova durável** (`phase_events`) sem
a qual nenhum gate de shadow pode ser honestamente avaliado.

## Contexto mínimo (por que existe — o bug latente)
`handle_direction_event` (`server/message_handler.py:1675-1694`) grava `last_direction_event`
**sem TTL, sem consumo único, sem vínculo a giro**. Como a mesa **alterna a cada giro**, um veredito
CORRETO do giro N é a direção **ERRADA** do giro N+1: se um produtor emitir uma vez e falhar na
seguinte, o evento velho **trava a direção autoritativa** em ~50% de erro até um reset. Hoje é inerte
(não há produtor) e o SPR-V1 **remove esse caminho da fusão** (fail-close). Este sprint reconstrói o
contrato **do lado seguro**: o evento vira **trilha de auditoria**, nunca direção.
Além disso, Prometheus **não** satisfaz o gate T4: counters zeram a cada restart do container e logs
têm retenção limitada. `phase_events` é **requisito de evidência**, não luxo analítico.

## Âncoras (onde entrar)
- `server/message_handler.py:1675-1694` — `handle_direction_event` (ponto de ingresso).
- `server/message_handler.py:881-936` — bloco de autoridade/fusão; após o SPR-V1 a visão **não**
  participa. **Não reintroduza.**
- `server/message_handler.py:937-956` — `process_spin`, `spin_seq += 1`, `game_state.save()`
  (é aqui que existe o "giro-alvo" e a fronteira transacional da decisão).
- `server/message_handler.py:494-505` — gate de role MASTER (o SPR-V1 já colocou `direction_event` lá).
- `server/message_handler.py:1618-1673` — `handle_new_session` (o que precisa ser invalidado no reset).
- `state/game.py:241-261` / `:305-413` / `:1340-1502` — campos de fase, `reset_session`, `save`/`load`.
- `database/sqlite_repo.py:172-290` — DDL `CREATE TABLE/INDEX IF NOT EXISTS` (**padrão a copiar**);
  `:300-400` — bloco de migração in-code idempotente (produção usa este caminho além do Alembic);
  `:402-486` — `save_decision()` **abre e comita a própria conexão** (leia antes de decidir como
  amarrar disposição terminal + decisão).
- `state/phase_metrics.py:10-14` — `_COUNTERS` é dict fechado (chave desconhecida = no-op).
- `server/health_server.py:120-218` — `_PROM_METRICS` + refresh.
- `tests/test_dir12_metrics_exporter.py` — **asserta o SET EXATO** de chaves/gauges.
- `tests/test_dir7_fusao_video.py`, `test_dir18_shadow_mode.py` — comportamento de fusão/shadow.

## Tarefa

### Bloco 1 — contrato do evento (identidade, alvo, prazo, consumo único)
Payload aceito (campos extras ignorados; ausência tolerada):
```json
{ "type": "direction_event", "event_id": "uuid", "round_id": "id-quando-disponivel",
  "direction": "cw", "confidence": 0.97, "captured_at_ms": 1760000000000,
  "frame_count": 6, "sensor_version": "r1", "calibration_id": "cal-..." }
```
1. O **servidor** acrescenta `session_id`, `received_at_mono` e — **decisão obrigatória** — atribui
   `target_spin_seq` **ele próprio, sob `state_lock`**, com a **fórmula fixa**:
   `target_spin_seq = spin_seq_corrente + 1` (o evento descreve o giro **que ainda vai ser
   processado**; `spin_seq` só é incrementado quando o `novo_resultado` é aceito).
   Escreva essa fórmula no ADENDO e no teste — deixá-la a critério do implementador gera off-by-one
   silencioso, que é exatamente a classe de bug que este sprint existe para tornar visível.
   Um `target_spin_seq` enviado pelo cliente é **apenas diagnóstico** e nunca autoritativo (senão um
   cliente defeituoso escolhe o alvo dele).
2. **Identidade**: `event_id` ausente ⇒ o **servidor gera** um UUID no ingresso (a coluna é
   `NOT NULL`). O ID do cliente, quando presente, é preservado; **nunca** rejeite o evento por falta
   de ID — apenas registre `meta_json.event_id_origin = "server"|"client"`.
3. **Prazo — relógio do servidor, não do cliente**: a idade é `time.monotonic() - received_at_mono`,
   contada **a partir do recebimento**. `captured_at_ms` do cliente é **somente diagnóstico**
   (`meta_json`) e nunca entra no cálculo do TTL — senão um cliente com relógio adulterado renova o
   próprio prazo.
4. Binding só vale quando os **quatro** requisitos são satisfeitos: (a) `round_id` coincide, se ambos
   os lados o tiverem; (b) `target_spin_seq` bate com a fórmula acima; (c) idade dentro do TTL
   (`SDA_DIRECTION_VISION_TTL_MS`, default `30000` — menor que o ciclo de ~44s); (d) o evento **ainda
   não foi consumido** (one-shot). Faltou um? → `stale`/`unbound`. **Nunca vira direção.**
5. **TTL após restart**: `time.monotonic()` não sobrevive ao processo. Um evento pendente
   reconstruído após restart é **`stale` por definição** — jamais volta a ser acionável. Documente.
6. **Corrida `direction_event` × `novo_resultado`**: o snapshot de `session_id`/`round_id`/`spin_seq`
   usado para o binding é tirado **atomicamente** sob `state_lock`. Descreva no Log qual ordem você
   garantiu.
7. `handle_new_session` invalida qualquer evento pendente.
8. Se houver cache em `GameState` (ex.: `last_direction_event` ou um pendente), ele entra em
   `save()` + `load()` + `reset_session()` — round-trip obrigatório. **Exceção:** `received_at_mono`
   **não** é persistido (monotônico), o que é justamente o que torna o item 5 verdadeiro.

### Bloco 2 — trilha `phase_events` (SQLite, append-only)
1. DDL **aditivo** (`CREATE TABLE/INDEX IF NOT EXISTS`), no padrão de `database/sqlite_repo.py:172-290`:
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
CREATE INDEX ix_phase_events_session_spin ON phase_events(session_id, target_spin_seq);
```
2. `kind` ∈ `received | bound | agree | disagree | stale | unbound | missing | selfcontradict`.
   Cada transição é **uma linha imutável**; `UNIQUE(event_id, kind)` torna retry **idempotente**.
   Para `missing`, o servidor gera um ID **determinístico** por sessão/giro.
3. `received` é inserido no ingresso; a **disposição terminal** (`agree`/`disagree`/…) é anexada na
   **mesma fronteira transacional** que persiste a decisão do giro. `save_decision()`
   (`sqlite_repo.py:402-486`) abre a própria conexão — **crie uma operação explícita que grave decisão
   e disposição na mesma conexão/transação. Não há alternativa "justificada"**: sem atomicidade,
   existe decisão sem disposição, e a trilha deixa de ser prova para o gate T4.
   Teste obrigatório: **falha injetada entre os dois writes ⇒ rollback total** (nem decisão nem
   disposição ficam gravadas), e o retry reprocessa de forma idempotente via `UNIQUE(event_id, kind)`.
   Um evento pendente é reconstruído da última linha `received` sem disposição terminal.
4. **Append-only no hot path.** Este sprint **não entrega** o job de retenção: o hot path só insere.
   A retenção de 30 dias é **sprint futuro** (`SPR-V4R`, a abrir pelo Diretor) e precisa existir
   **antes** de a auditoria ficar ligada por mais de ~60 dias. Escreva no ADENDO: (a) a taxa de
   crescimento medida (bytes/giro × giros/dia); (b) que "append-only" e "retenção" não se contradizem
   porque só um job externo apaga; (c) que enquanto o job não existir, a purga é **manual e do
   operador**. Não prometa no PR o que não está no diff.
5. **Frames nunca entram no banco** — somente metadados (~100-300 bytes/giro).
6. **Por que não pgvector:** o evento é categórico, temporal e auditável; busca vetorial não agrega e
   dificultaria integridade. pgvector segue para embeddings. Se um dashboard central for necessário
   **depois**, a outbox espelha no PG com migração Alembic aditiva — **não hardcode o número da
   migração** (a head atual é 0013 e pode mudar) e só depois de liberar o lock `schema/alembic`.

### Bloco 3 — shadow e observabilidade
1. Flag `SDA_DIRECTION_VISION_SHADOW` (default **OFF**): a cada `novo_resultado`, compara o evento
   **fresco e bound** com a direção final **pós-autoridade** e grava `agree`/`disagree`.
   **Zero efeito** em direção, seed, timeline, decisão ou stake.
2. Flag `SDA_PHASE_EVENT_AUDIT` (default **OFF**): persiste a trilha. Sem ela, nada é gravado.
3. Counters (adicionar ao dict fechado `_COUNTERS`): `vision_event_total`, `vision_agree_total`,
   `vision_disagree_total`, `vision_stale_total`, `vision_unbound_total`,
   `vision_selfcontradict_total`, `vision_missing_total`, `phase_events_write_error_total`.
4. Gauges correspondentes em `server/health_server.py` + **atualizar o set exato** em
   `tests/test_dir12_metrics_exporter.py`.
5. `obs/alerts.yml`: `RoletaVisionStaleAlto` e `RoletaPhaseEventsWriteError` por `increase()`.
6. **`SDA_DIRECTION_VISION` permanece congelada em `0`**, com o comentário na compose: *"não ligar;
   visão corrige âncora, não spin (ver SPR-V7)"*. Este sprint **não** reabre autoridade per-spin.
7. **Cobertura antes de concordância**: exponha `vision_event_total` **por giro elegível** (quantos
   giros tiveram evento vs. total) — sem cobertura, "99% de acordo" é métrica de 200 amostras
   disfarçada de prova.

## Critério de "pronto" (Definition of Done)
- [ ] Evento **sem `event_id`** recebe UUID do servidor e é gravado normalmente (`event_id_origin`
      registrado); evento fora do TTL, com `round_id`/`target_spin_seq` divergente ou já consumido
      → classificado (`stale`/`unbound`) e **nunca** vira direção. Teste por caso.
- [ ] `target_spin_seq` = `spin_seq_corrente + 1`, atribuído pelo **servidor** sob `state_lock`;
      valor do cliente não influencia (teste com cliente mandando alvo errado).
- [ ] TTL usa **`received_at_mono` do servidor**; `captured_at_ms` adulterado (passado ou futuro)
      **não** altera a classificação (teste).
- [ ] Evento pendente sobrevivente a restart é tratado como `stale` (teste).
- [ ] `phase_events` criada de forma **aditiva e idempotente** (rodar 2× não quebra); retry do mesmo
      `(event_id, kind)` não duplica.
- [ ] **Atomicidade**: decisão do giro e disposição terminal na **mesma transação**; falha injetada
      entre os dois writes ⇒ **rollback total** (teste).
- [ ] **Falha de escrita da trilha não altera aceitação do giro nem a aposta** — incrementa
      `phase_events_write_error_total`, loga erro, e **invalida a janela como evidência T4** (teste
      com o banco/handle indisponível).
- [ ] **Shadow não pode agir**: teste com monkeypatch que **falha** se o caminho de shadow chamar
      `_apply_seed`, `process_spin` ou alterar `direcao`/`seed_parity`/`spin_seq`.
- [ ] **Não-interferência**: replay determinístico antes × depois com **todas as flags novas OFF** →
      decisões, cobertura, `final_action`, stake, timelines, seed e `spin_seq` idênticos.
- [ ] Com `SDA_DIRECTION_VISION=1` (congelada) o resultado continua **idêntico** ao da flag OFF
      (regressão do fail-close do SPR-V1).
- [ ] Counters/gauges novos expostos; `test_dir12_metrics_exporter.py` atualizado e verde.
- [ ] `pytest tests/` completo verde.

## Guardrails (inviolável)
- **INV-3** intacto: nada aqui toca indicação, cobertura ou stake.
- **Flags default-OFF** na compose (`${VAR:-default}` + comentário de rollback), leitura **por chamada**.
- **Aditivo**: `CREATE ... IF NOT EXISTS`; nenhum `DROP`/rename; rollback desliga a flag e **preserva
  a tabela** (o rollback de deploy não faz downgrade).
- **Sem `except Exception: pass`**; erro de trilha é contado e logado. Novo `except Exception` →
  `python tools/lint_silent_except.py --update`. Não corrija `except` fora do escopo.
- **Sem Alembic neste sprint** (evita colisão com SPR-G2 no lock `schema/alembic`).
- Campo de motor novo → round-trip `save()`+`load()`+`reset_session()`.
- **Git**: só no worktree/branch `spr/SPR-V4`; **NUNCA** main; entregue por **PR**; sem SSH/host/prod.
- **Não commitar `graphify-out/`**.

## Validação
```
python -m pytest tests/ -k "vision or phase_event or dir7 or dir12 or dir18" -v
python -m pytest tests/                     # suíte COMPLETA
sqlite3 <db-de-teste> "SELECT kind, COUNT(*) FROM phase_events GROUP BY 1;"
sqlite3 <db-de-teste> ".schema phase_events"
promtool check rules obs/alerts.yml         # ou validação YAML equivalente
```

## Rollback (ISO)
`SDA_PHASE_EVENT_AUDIT=0` + `SDA_DIRECTION_VISION_SHADOW=0` + `docker compose up -d` (minutos) ou
`git revert` do PR. A tabela **permanece** (aditiva, inofensiva). Nenhum downgrade de schema.

## Conformidade ISO
- [ ] Flags default-OFF; leitura por-chamada. [ ] Aditivo/retro-compatível.
- [ ] **INV-3** intacto; suíte completa verde. [ ] `lint_silent_except` se houver novo `except`.
- [ ] Round-trip `save/load/reset` de qualquer campo de motor novo.
- [ ] ADENDO ISO registra: por que SQLite e não pgvector; append-only × retenção por job;
      `target_spin_seq` autoritativo do servidor; TTL inválido após restart.

## Closeout
1. Validação → `## Log`. 2. **ADENDO ISO**. 3. `code-review`. 4. Append no Log.
5. `graphify update .` local (não commitar). 6. Commit em `spr/SPR-V4` (trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`), incluindo ADENDO + este brief.
7. `git push -u origin spr/SPR-V4` + **abrir PR**. 8. `store_memory` + avisar o Diretor:
*"PR de SPR-V4 aberto"*.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
- **2026-08-05 · CONCLUÍDO (PR aberto) · SPR-V4: contrato `direction_event` + trilha `phase_events`.**
  **Entregue:** (1) evento com identidade (`event_id` do cliente preservado; UUID do servidor quando
  ausente, origem em `meta_json.event_id_origin`), **giro-alvo do servidor** sob `state_lock` pela
  fórmula fixa `target_spin_seq = spin_seq_corrente + 1`, **TTL no relógio monotônico do servidor**
  (`SDA_DIRECTION_VISION_TTL_MS=30000`, intervalo semiaberto, `captured_at_ms` do cliente só
  diagnóstico) e **consumo único estrutural**; (2) trilha `phase_events` SQLite append-only com
  **atomicidade decisão+disposição na MESMA transação** (`save_decision_with_phase_events`, rollback
  total provado com falha injetada, retry idempotente); (3) shadow + 8 counters, 9 gauges, 2 alertas,
  3 flags default-OFF na compose.
  **Ordem garantida na corrida `direction_event` × `novo_resultado`:** o snapshot de
  `session_id`/`spin_seq` e a atribuição do alvo acontecem **dentro** do `state_lock`; a
  classificação acontece **também dentro** do lock, logo após `spin_seq += 1` (portanto já com a
  direção final pós-autoridade), e devolve as linhas numa **variável local** da função — nunca em
  `self` — para que dois giros jamais disputem a mesma disposição. I/O de SQLite e `send()` do ack
  ficam **fora** do lock (`busy_timeout=5000` e `drain()` de produtor lento parariam o caminho do giro).
  **Desvio deliberado do DDL do brief:** `UNIQUE(event_id, kind, target_spin_seq)` em vez de
  `UNIQUE(event_id, kind)` — com a chave global, um produtor reutilizando um `event_id` estável
  gravava 1 linha por kind para a vida inteira (reproduzido: 6 giros → counters 6, trilha 1),
  fazendo a decisão comitar sem disposição e a taxa de acordo subir artificialmente. Justificativa
  completa no ADENDO §E. Supressões por conflito agora **contam** `phase_events_write_error_total`.
  **Validação:** `pytest tests/` **973 verde** (965 antes; +64 testes do sprint, 3 baselines
  atualizados: `test_dir12` set exato, `test_dir9` `sentido.stats`, `.silent_except_baseline.json` e
  `schema_sqlite_snapshot.json`). Replay congelado do SPR-V1 **byte-idêntico** com as flags novas OFF,
  com `SDA_DIRECTION_VISION=1` e com o shadow ON. `obs/alerts.yml` validado por parse YAML +
  estrutural (5 grupos, 23 regras; `promtool` ausente na máquina — validar no CI/host).
  `sqlite3 .schema phase_events` + `SELECT kind, COUNT(*) GROUP BY 1` conferidos ponta a ponta.
  **Crescimento MEDIDO (2.000 giros):** 223 B/giro sem produtor de visão (6,4 MB/30d a 1.000
  giros/dia) e 1.313 B/giro com produtor ativo (37,6 MB/30d). **Retenção NÃO entregue** — abrir
  `SPR-V4R` antes de ~60 dias com a auditoria ligada; até lá a purga é manual e do operador.
  **Code-review:** 6 achados, 6 corrigidos antes do PR (chave única global; denominador da cobertura
  poluído por invalidações de ingresso; fallback que podia duplicar a decisão no ledger; `await send`
  dentro do lock; reconstrução do pendente sem call site de produção + `save()` ausente no ingresso;
  testes de idempotência com cobertura ilusória). Detalhe no ADENDO §N.
  **Arquivos:** `server/message_handler.py`, `database/sqlite_repo.py`, `database/service.py`,
  `state/game.py`, `state/phase_metrics.py`, `server/health_server.py`, `app_config/settings.py`,
  `obs/alerts.yml`, `docker-compose.yml`, `tests/replay_harness_v1.py`,
  `tests/test_v4_direction_event_contract.py`, `tests/test_v4_phase_events_trail.py`,
  `tests/test_v4_nao_interferencia_replay.py`, `tests/test_dir12_metrics_exporter.py`,
  `tests/test_dir9_sentido_na_sugestao.py`, `Manutenabilidade_iso.md`.

- **2026-08-05 (noite-2) · FIX no MESMO PR (#55) · 2 bugs de integridade da trilha achados por review independente.**
  **(1) Recuperação pós-restart era inalcançável.** `_reconstruir_pendente_da_trilha` filtrava
  pela sessão corrente, mas `current_session_id` nasce UUID NOVO no `__init__` — a linha `received`
  órfã tem o id ANTERIOR. O teste que a "cobria" só zerava o pendente em memória mantendo a MESMA
  sessão (nunca atravessava a fronteira de processo). **Corrigido separando as duas verdades:**
  com `state.json` (bind-mount, o caso real) a continuidade é PROVADA e o evento antigo vira
  **`stale`**; sem `state.json` não há como provar, então o giro é **`missing`** (honesto) e o órfão
  é encerrado por **FAXINA** de manutenção — transação própria, `decision_ref` NULL, `spin_seq` NULL,
  sem contador. **Não há adoção de órfão por coincidência de `target_spin_seq`**: o contador REINICIA
  a cada sessão, então o alvo 1 de uma mesa morta coincide com o giro 1 de qualquer sessão nova —
  adotar rotularia como `stale` um giro honestamente `missing` (atribuição cruzada entre mesas).
  **(2) `NOT EXISTS` fechava o ciclo por `event_id` GLOBAL**, mas a identidade é por giro: com
  `event_id` reutilizado, o terminal do giro N mascarava o `received` do N+1/de outra sessão.
  **Corrigido** para correlacionar por `(session_id, event_id, target_spin_seq)` = a chave única.
  Isso exigiu o par que faltava: o **terminal passou a carregar as coordenadas do EVENTO**, com as
  do GIRO em **colunas próprias** (`spin_session_id`/`spin_seq`) — senão um evento de alvo 5
  classificado no giro 7 gravava terminal com alvo 7 e deixava o `received` de alvo 5 aberto.
  Invariante consultável: `spin_seq IS NOT NULL` ⇔ a linha é disposição de GIRO (denominador da
  cobertura). `UNIQUE` passou a `(session_id, event_id, kind, target_spin_seq)` — sem `session_id`
  o giro 1 da sessão B colidia com o da sessão A e a linha da sessão NOVA era suprimida.
  **Bônus achado no caminho:** `received_persisted` era marcado DEPOIS do `gs.save()`, então nunca
  ia ao `state.json` — após restart a linha era re-emitida e o conflito suprimido contava como erro
  de escrita inexistente. Agora nasce antes do `save()` e é desfeito se a gravação falhar (auto-cura).
  **Validação:** `pytest tests/` **981 verde** (973 antes). **Mutação:** com o código de produção
  revertido para `c970b65` e os testes novos mantidos, **10 testes falham**; cada fix mutado
  isoladamente **matou o mutante** (correlação global: 2; `UNIQUE` sem sessão, mutação cirúrgica: 2;
  terminal com coordenadas do giro: 2; faxina removida: 3; marca de persistência no lugar antigo: 3).
  `promtool` segue ausente — `obs/alerts.yml` inalterado nesta rodada. INV-3/shadow/flags intactos.
  **Arquivos:** `database/sqlite_repo.py`, `database/service.py`, `server/message_handler.py`,
  `database/schema_sqlite_snapshot.json`, `.silent_except_baseline.json`,
  `tests/test_v4_phase_events_trail.py`, `Manutenabilidade_iso.md`.
  **Code-review dos próprios fixes (3ª rodada, 3 achados, 3 corrigidos):** (a) a guarda da faxina
  comparava só o `event_id` e, com produtor de id estável, pulava TODO órfão de sessão morta —
  passou a comparar a identidade completa `(session_id, event_id, target_spin_seq)`; (b) num banco
  com a forma antiga, o `ON CONFLICT` ficava sem alvo e **todo** insert da trilha estourava
  (auditoria 100% morta + erro por giro) — a chave virou **índice único ADITIVO**
  (`ux_phase_events_lifecycle`), que um banco antigo ganha no boot seguinte sem DROP, com teste
  partindo da tabela na forma antiga; (c) a auto-cura da marca `received_persisted` era cobertura
  ilusória (nenhum teste injetava falha no INGRESSO) — teste adicionado.
  **Mutação da 3ª rodada:** guarda só por `event_id` (mata 1), índice do ciclo removido (mata 41),
  auto-cura removida (mata 1). Suíte final: **984 verde**.
