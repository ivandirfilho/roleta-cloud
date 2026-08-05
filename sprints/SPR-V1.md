# SPR-V1 · Blindagem do servidor: reconciliação de fase e autoridade seguras · Bloco BLK-D/BLK-I · Pri P0

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §3 (furos A/B), §4.1, §7, §10.5, §11.4-A · `fluxo_mental_24.md` §§9-12 · `Manutenabilidade_iso.md`.

## Meta
```text
blocked_by: []
locks:      [message_handler-fase, game-state, phase, phase_metrics, health_server, alerts, settings, compose, tests-DIR]
touches:    [server/message_handler.py, state/game.py, state/phase.py, state/phase_metrics.py,
             server/health_server.py, app_config/settings.py, obs/alerts.yml, docker-compose.yml, tests/]
base_sha:   origin/main
branch:     spr/SPR-V1
```
**Colisão conhecida:** o PR #43 (MIG-0) está aberto e toca `state/game.py`, `app_config/settings.py`,
`docker-compose.yml` e `Manutenabilidade_iso.md`. Se ele mergear enquanto este sprint roda,
**rebase em `origin/main` antes do PR** e re-rode a suíte. SPR-V4 depende deste sprint e serializa
em `server/message_handler.py`: não abra V4 antes deste PR mergear.
**SPR-V2 roda em paralelo** (locks disjuntos: servidor × extensão). O único ponto comum é o
**ADENDO em `Manutenabilidade_iso.md`**: escreva **sempre em append no fim do arquivo**, nunca edite
adendos existentes — assim o conflito, se houver, é trivial de resolver no rebase.

## Setup (worktree próprio — NÃO use o working dir do Diretor)
```text
# a partir de QUALQUER checkout do repo (o caminho abaixo é o checkout principal desta máquina):
git -C "C:\Users\Windows\Desktop\Roleta Cloud" worktree add ..\rc-SPR-V1 spr/SPR-V1
cd ..\rc-SPR-V1
git rev-parse --show-toplevel   # confirme que você NÃO está no worktree do Diretor
git log --oneline -1            # confirme que está no brief publicado pelo Diretor
```
(Se o branch `spr/SPR-V1` não existir no remoto: `git worktree add ..\rc-SPR-V1 -b spr/SPR-V1 origin/main`.)

## Objetivo (1 frase)
Fechar os furos que fazem o servidor **perder a autoridade da fase exatamente quando o cliente está
defasado** — buffer de fase dessincronizado na recuperação de gap, alinhamento por coincidência,
giro fantasma fisicamente impossível, seed do operador apagado por caminhos laterais e fusão de
visão viva sem produtor confiável — sem alterar nenhuma aposta com as flags OFF.

## Contexto mínimo (por que existe)
A direção (horário/anti-horário) **não é lida**: é inferida por alternância determinística ancorada
num seed (`seed_parity`/`seed_n`) e projetada por `spin_seq`. Em produção,
`SDA_SENTIDO_AUTORITATIVO=1` e `SDA_UNCERTAIN_REANCORA=1`. Quando o reconcile falha, o seed zera e o
próximo giro re-ancora **na direção que o cliente mandou** — se o cliente estiver flipado, o servidor
adota a fase errada e ela persiste. Medido em produção: rajadas de 91 `phase_uncertain` e pares
`cw,cw`/`ccw,ccw` no PostgreSQL.

## Âncoras (onde entrar — NÃO faça grep cego)
- Grafo: `graphify.get_neighbors MessageHandler` e `... GameState` **antes** de abrir arquivo.
- `server/message_handler.py:841-880` — DIR4: `phase_advance`, recuperação de gap
  (`:856-864` sincroniza `recent_results` e **não** `_phase_results` ← furo A) e DIR17 (`:870-879`).
- `server/message_handler.py:881-936` — DIR5/DIR7/DIR18: auto-seed, `project_phase`, **fusão com
  `last_direction_event`** (`:916-927`) e substituição de `direcao` (`:934-935`).
- `server/message_handler.py:142-168` — `is_duplicate_spin` (guard 1 no mesmo segundo; guard 2
  `SDA_DEDUP_PHANTOM`); `:167` grava `_last_accept_ts_ms` (**client-time**, não mexer na semântica).
- `server/message_handler.py:76` — `self._last_accept_ts_ms` (campo existente).
- `server/message_handler.py:482-520` — `process_message`: `data_messages` e o **gate de role MASTER**
  (`:494-505`); dedup por `trace_id` e `is_duplicate_spin` (`:507-520`).
- `server/message_handler.py:1595-1604` — `correcao_historico` **zera `seed_parity`/`seed_n`** quando
  não há lock (apaga um `set_seed` recém-confirmado pelo operador).
- `server/message_handler.py:1618-1673` — `handle_new_session` (limpeza pós-reset, DIR14 em `:1630-1637`).
- `server/message_handler.py:1675-1694` — `handle_direction_event` (grava `last_direction_event` sem
  TTL/one-shot/vínculo a giro). `:1696-1715` — `handle_set_seed` (escreve seed + lock direto).
- `state/phase.py:47-77` — `reconcile_shift`: aceita o **primeiro** k com match, e `m` pode valer **1**
  (`m = min(len(prev), len(new)-k)`), ou seja k alto casa por coincidência com ~1/37.
- `state/phase.py:82-88` — `SOURCE_PRIORITY` (`vision`=50 > `deterministic_toggle`=10);
  `:91-...` — `fuse_direction`.
- `state/game.py:241-261` — campos de fase + `_phase_results` (deque maxlen=20).
- `state/game.py:305-413` — `reset_session` (`:347` recria `_phase_results`; `:398-408` DIR16).
- `state/game.py:415-435` / `:481-492` — `process_spin` / `register_history_number` (escritas simétricas).
- `state/game.py:1340-1390` / `:1421-1502` — `save()` / `load()` (round-trip de fase e `_phase_results`).
- `state/phase_metrics.py:10-14` — `_COUNTERS` é **dict fechado**: `incr()` de chave desconhecida é
  **no-op silencioso**.
- `server/health_server.py:120-218` — `_PROM_METRICS` e o refresh das 3 gauges de fase.
- `app_config/settings.py:317-482` — padrão das funções de flag (leitura por chamada).
- `docker-compose.yml:109-186` — bloco `SDA_*` (padrão `${VAR:-default}` + comentário de rollback).
- `obs/alerts.yml:1-170` — grupos existentes (**hoje: zero regra de fase**).
- Testes existentes: `tests/test_dir4_shift.py`, `test_dir13_lock_total.py`, `test_dir16_reset_reancora.py`,
  `test_dir17_uncertain_reanchora.py`, `test_dir19_phase_buffer_separado.py`,
  `test_dir12_metrics_exporter.py` (**asserta o SET EXATO de chaves/gauges — quebra se você
  adicionar métrica sem atualizá-lo**), `test_dir7_fusao_video.py`, `test_dir18_shadow_mode.py`.

## Tarefa (5 blocos — faça **um commit por bloco**, na ordem; PR único)

### Bloco 1 — sincronizar o buffer de fase na recuperação de gap (furo A)
1. `state/game.py`: método público **novo** `sync_phase_buffer(nums: list[int]) -> bool` que espelha
   os números recuperados em `_phase_results` via `appendleft`, na **mesma ordem** que
   `phase_advance` devolve `_inter` (mais antigo → mais recente). Se `_phase_results` estiver ausente
   (estado legado), **logue erro e retorne `False`** — proibido `except Exception: pass`, pois
   esconderia justamente a regressão que este sprint corrige.
2. `server/message_handler.py:856-864`: depois de `spin_seq += _gap` e do loop em `recent_results`,
   chamar `sync_phase_buffer(_inter)` **atrás da flag nova `SDA_PHASE_BUFFER_SYNC` (default OFF,
   leitura por chamada)**; se retornar `False`, incrementar `phase_buffer_missing_total`.
3. Atualizar o **comentário obsoleto** de `:857-859` (ele afirma que sincronizar `recent_results`
   evita `phase_uncertain` falso — desde a DIR19 o alinhamento lê `_phase_results`).
4. `SDA_PHASE_BUFFER_SYNC=1` ⇒ o buffer resultante fica **idêntico** ao `allNumbers` do cliente ⇒ o
   próximo shift alinha com k=1. Essa igualdade é a asserção central do teste novo.

### Bloco 2 — alinhamento com evidência suficiente (falso match em k alto)
1. `state/phase.py::reconcile_shift`: hoje aceita o primeiro k cujo overlap case, mesmo com **m=1**
   (1/37 de coincidência). Introduzir **overlap mínimo** parametrizado (`min_overlap`, default `0`
   = comportamento atual byte-idêntico) e, quando o único match disponível tiver evidência abaixo do
   mínimo, retornar `matched=False` (→ `phase_uncertain` explícito, que é o caminho seguro) em vez de
   inventar k giros. Manter a função **pura e que nunca lança**.
2. Ligar via flag `SDA_PHASE_MIN_OVERLAP` (default **0 = OFF**; valor sugerido em produção: `3`),
   lida por chamada no chamador (`message_handler`), **não** dentro de `phase.py`.
3. Métrica `phase_ambiguo_total` para o caso "havia match, mas sem evidência suficiente" — é o que
   separa "gap grande legítimo" de "coincidência". Documente no brief (Log) o **k máximo realmente
   recuperável** com `allNumbers`=12 e o overlap mínimo escolhido: com `min_overlap=3`, k≤9.
   **Não escreva "k=1..11 sempre recupera"** — é falso; acima do limite o resultado correto é
   `phase_uncertain`, e isso é sucesso, não falha.

### Bloco 3 — gate de plausibilidade física (furo B, DIR21)
1. Campo **novo** `self._last_accept_srv_mono: Optional[float] = None` (inicializado junto de
   `_last_accept_ts_ms`, `message_handler.py:76`). **NÃO reaproveite `_last_accept_ts_ms`** (é
   `Date.now()` do cliente e alimenta uma flag já em produção).
2. Em `is_duplicate_spin`, rejeitar o giro quando `(time.monotonic() - _last_accept_srv_mono)*1000 <
   min_spin_interval_ms()` — flag nova `SDA_MIN_SPIN_INTERVAL_MS` (default **0 = OFF**; produção
   sugerida `15000`). Logar `warning` com o delta e incrementar `spin_implausivel_total`.
   **Relógio monotônico do servidor**: imune a NTP/ajuste do relógio do cliente e do host.
3. `_last_accept_srv_mono` é armado **somente após** o giro atravessar dedup + validação +
   `process_spin` aceito (fim de `handle_novo_resultado`). **Rejeição nunca atualiza o relógio.**
4. `handle_new_session` **zera** `_last_accept_srv_mono` (junto do clear de `_recent_trace_ids`,
   `:1630-1637`) — senão o 1º giro legítimo da mesa nova seria engolido.
5. **Exceção explícita à regra de round-trip**: `_last_accept_srv_mono` **NÃO entra** em
   `save()`/`load()`. `time.monotonic()` só é comparável dentro do mesmo processo; persistir o valor
   produziria comparação sem sentido após restart. Nasce `None` e é limpo no reset — documente isso
   no ADENDO ISO como decisão consciente.
6. Escopo: só `novo_resultado` passa pelo dedup (`:507-520`); `historico_inicial`/`correcao_historico`
   usam `register_history_number` e continuam imunes.
7. Custo aceito e documentado: em troca de mesa **sem** reset, 1 giro real pode ser descartado
   (~44s); o `historico_inicial` seguinte re-ancora. **Não viola INV-3** — nenhuma indicação é
   suprimida; perde-se uma avaliação de outcome.

### Bloco 4 — autoridade: seed preservado, visão fail-close, mutação de fase serializada
1. **`_apply_seed(direction, source, locked=None)`** em `GameState` (ou no handler, mas **um único
   caminho auditável**): `locked=None` **preserva** o estado atual do lock — omitir o campo **nunca**
   destrava o operador. `source="vision"` é **recusado** quando há lock explícito. Migrar
   `handle_set_seed` (`:1696-1715`), o auto-seed da DIR5 (`:899-903`), a reancoragem do DIR17
   (`:876-879`) e o caminho do `correcao_historico` (`:1600-1604`) para esse método — hoje cada um
   escreve `seed_parity`/`seed_n`/`direction_locked` por conta própria.
2. **Fluxo real do operador**: `set_seed` seguido de `correcao_historico` **apaga o seed** recém
   confirmado (`:1600-1604` zera `seed_parity` quando não há lock). Corrigir: uma âncora **confirmada
   pelo operador** sobrevive a uma correção de histórico não-direcional. Teste obrigatório da
   sequência real `set_seed → correcao_historico → novo_resultado`.
3. **Fail-close da visão**: `last_direction_event` **sai da fusão** (`:916-927`). Com
   `SDA_DIRECTION_VISION=1` o resultado tem de ser **idêntico** ao da flag OFF — teste obrigatório
   com a flag ligada provando que `direcao`, `seed_parity`, `spin_seq`, timelines e decisão não
   mudam. A flag fica **congelada em `0`** com comentário na compose: *"não ligar; visão corrige
   âncora, não spin (ver SPR-V7)"*. O evento continua sendo aceito e guardado (SPR-V4 o transforma em
   trilha shadow), mas **não pode mais influenciar spin algum**.
   Motivo: a mesa alterna a cada giro; um veredito correto do giro N é a direção **errada** do N+1 —
   sem TTL/one-shot/vínculo a giro, um evento velho trava a direção autoritativa em ~50% de erro.
4. **Gate de concorrência MASTER**: `set_seed`, `direction_event` e **`nova_sessao`** entram na lista
   de mensagens que exigem role `master` (`:494-505`) — hoje só `novo_resultado`/`historico_inicial`/
   `correcao_historico` exigem. Audite **todas** as mensagens que mutam fase e liste-as no Log.
   Chame isso de **gate de concorrência entre clientes, NÃO de autenticação**: `AUTH_ENABLED=false`
   em produção e nova conexão pode assumir MASTER. Autenticação funcional segue **bloqueadora** de
   qualquer autoridade automática (SPR-V7) e deve ser registrada como dívida no ADENDO.
5. **Eco autoritativo + capability (pré-requisito do SPR-V2 — não é opcional).** Publicar em
   `_engine_overlay_fields()` (`message_handler.py:433-...`, canal aditivo já consumido por
   `sugestao`/`state_sync`) um bloco novo:
   `phase_authority: {enabled: bool, spin_seq: int, direction: "cw"|"ccw", seed_parity: int|null, seed_n: int|null}`.
   - `enabled` é **dinâmico e nominal**: `true` **somente** quando `SDA_SENTIDO_AUTORITATIVO=1` **e**
     `SDA_PHASE_BUFFER_SYNC=1` (lido **por chamada**). Nunca hardcode `true`.
   - Aditivo: cliente antigo ignora campo desconhecido ⇒ nada quebra.
   - **Teste integrado obrigatório**: giro rejeitado pelo gate DIR21 ⇒ o `state_sync` seguinte carrega
     `spin_seq`/`direction` **inalterados** (os de antes da tentativa), permitindo ao cliente do
     SPR-V2 desfazer o flip local. Sem esse eco, o passo 4 da *Ordem de ativação* deixa o servidor
     certo e o popup espelhado — por isso ele é **DoD deste sprint**, não do V2.

### Bloco 5 — telemetria que não mente
1. `state/phase_metrics.py:10-14`: adicionar ao `_COUNTERS` (dict fechado!) as chaves
   `phase_buffer_missing_total`, `phase_ambiguo_total`, `spin_implausivel_total`,
   `alternancia_violada_total`. Sem isso os `incr()` são **no-op silencioso**.
2. **DIR22** (violação de alternância): capturar `prev_last_direction = game_state.last_direction`
   **antes** de `process_spin` e, após o processamento, com a direção **final pós-autoridade**,
   incrementar `alternancia_violada_total` + `warning` quando `direcao == prev_last_direction`.
   Atrás da flag `SDA_PHASE_ALT_METRIC` (default **OFF**, como toda novidade). Não incrementar com
   `prev=None` (histórico não-direcional) nem no 1º giro pós-reset.
3. `server/health_server.py:196-218`: registrar as **4 gauges novas** em `_PROM_METRICS` e no refresh.
4. `tests/test_dir12_metrics_exporter.py`: **atualizar o set exato** de chaves e gauges — sem isso a
   suíte fica vermelha e o PR é inválido.
5. `obs/alerts.yml`: grupo novo de fase (hoje não existe nenhum). Use **`increase()`/`rate()`**, nunca
   valor absoluto (counters em memória zeram a cada restart do container):
   - `RoletaAlternanciaViolada`: `increase(roleta_phase_alternancia_violada_total[1h]) > 2` → warning;
   - `RoletaPhaseUncertainBurst`: `increase(roleta_phase_uncertain_total[30m]) > 5` → warning
     (rajada = furo A regrediu; detecção em ~30min em vez de auditoria manual D+7);
   - `RoletaSpinImplausivel`: `increase(roleta_phase_spin_implausivel_total[1h]) > 3` → warning.
   Documente no Log que reset de sessão e troca de mesa geram violações **legítimas** — o alerta é
   por janela, e a auditoria fina é **particionada por sessão** (query do §5 da proposta).

## Critério de "pronto" (Definition of Done)
- [ ] **B1**: com `SDA_PHASE_BUFFER_SYNC=1`, após um gap de k giros o `_phase_results` fica idêntico
      ao `allNumbers` do cliente e o giro seguinte alinha **sem** `phase_uncertain`. Com a flag OFF,
      comportamento byte-idêntico ao de hoje. `_phase_results` ausente → métrica + log de erro, sem
      sucesso falso (compatível com `test_fallback_phase_advance_se_phase_results_ausente`).
- [ ] **B2**: matriz de gaps `k=0..11` com `min_overlap` OFF (baseline) e ON; para cada k, o resultado
      é *recuperado* ou *`phase_uncertain` explícito* — **nunca** um k inventado por coincidência.
      O k máximo recuperável está escrito no Log com o overlap mínimo usado.
- [ ] **B3**: giro < N ms após o último **aceito** é rejeitado (mesmo com número/direção diferentes);
      `N=0` desliga; relógio do cliente adulterado/regressivo/saltando **não** afeta o gate; rejeição
      **não** atualiza `_last_accept_srv_mono`; `handle_new_session` limpa a âncora (1º giro da mesa
      nova é aceito); `historico_inicial` imune.
- [ ] **B4**: `_apply_seed(..., locked=None)` preserva o lock; `source="vision"` recusado sob lock;
      `set_seed → correcao_historico` preserva a âncora do operador; com `SDA_DIRECTION_VISION=1` o
      resultado é idêntico ao da flag OFF (teste explícito); `set_seed`/`direction_event`/`nova_sessao`
      rejeitados para role não-master com `code=NOT_MASTER`; **`phase_authority` presente no
      `state_sync`**, com `enabled` refletindo as duas flags e `spin_seq`/`direction` **inalterados**
      após um giro rejeitado (teste integrado).
- [ ] **B5**: as 4 chaves novas existem em `_COUNTERS`, aparecem em `/metrics` e
      `test_dir12_metrics_exporter.py` está atualizado e verde; `obs/alerts.yml` tem as 3 regras
      novas e passa em `promtool check rules` (ou validação YAML equivalente, se `promtool` não
      estiver disponível — registre qual usou).
- [ ] **Não-interferência (obrigatório)**: replay determinístico do mesmo conjunto de giros
      **antes × depois**, com **todas as flags novas OFF** → `final_action`, cobertura, stake,
      `timeline_cw/ccw`, `seed_parity`, `seed_n`, `spin_seq` e as linhas de `decisions` **idênticos**.
      Único delta permitido: gauges novas expostas com valor 0 e `phase_authority.enabled=false`.
      **Congele a fixture** (arquivo versionado em `tests/`, lista de giros fixa, sem `random` e sem
      relógio real) e asserte campo a campo — "suíte verde" **não** é evidência de não-interferência.
- [ ] Testes novos em `tests/`: `test_dir20_phase_buffer_sync.py`, `test_dir21_min_spin_interval.py`,
      `test_dir22_alternancia_metrica.py`, `test_dir23_seed_authority.py` (blocos 4).
- [ ] `pytest tests/` **completo** verde (não só `-k`).

## Guardrails (inviolável)
- **INV-3**: a estratégia NUNCA fica sem indicação; vetos modulam stake por `min()`, não suprimem.
  Nada neste sprint toca decisão, cobertura ou stake.
- **Flags default-OFF** na `docker-compose.yml` (`${VAR:-default}` + comentário de rollback), leitura
  **por chamada** — proibido cachear em global/atributo.
- **Sem `except Exception: pass`.** Todo caminho de erro novo incrementa métrica **e** loga. Se você
  criar qualquer `except Exception`, rode `python tools/lint_silent_except.py --update`.
  **Não "conserte" oportunisticamente `except` pré-existentes fora do escopo deste sprint.**
- **Falha de telemetria nunca altera aceitação do giro nem a aposta.**
- Campo de motor novo ⇒ round-trip `save()`+`load()`+`reset_session()`. **Exceção justificada:**
  `_last_accept_srv_mono` (monotônico, válido só no processo) — documentar no ADENDO.
- **Git**: só no worktree/branch `spr/SPR-V1`; **NUNCA** push/checkout/reset/merge em `main`.
  Entregue por **PR**; não faça merge. Aborte se o working tree começar sujo.
- **Produção intocável**: sem SSH/systemd/edição no host; nada de `docker compose up` em produção.
- Sem segredo em commit; sem comando destrutivo; **não commitar `graphify-out/`**.

## Validação (rode e cole o resultado no Log)
```
python -m pytest tests/ -k "dir20 or dir21 or dir22 or dir23 or dir4 or dir12 or dir13 or dir16 or dir17 or dir19 or dir7 or dir18" -v
python -m pytest tests/            # suíte COMPLETA — obrigatória
python tools/lint_silent_except.py --update   # só se criou except Exception
promtool check rules obs/alerts.yml           # ou validação YAML equivalente
```

## Rollback (ISO — sempre documentar; execução é do **operador**, não deste sprint)
Reverter SEM perda: **flags default-OFF** (`SDA_PHASE_BUFFER_SYNC=0`, `SDA_MIN_SPIN_INTERVAL_MS=0`,
`SDA_PHASE_MIN_OVERLAP=0`, `SDA_PHASE_ALT_METRIC=0`) + `docker compose up -d` (minutos) **OU**
`git revert` do PR (~2min pós-merge). Sem migração de schema ⇒ nada a "descer".
O fail-close da visão (Bloco 4.3) é **remoção de caminho**, não flag: seu rollback é `git revert`.

## Ordem de ativação em produção (runbook do **Diretor/operador** — **NÃO** é DoD nem tarefa deste sprint)
> ⚠️ O executor **não executa nada desta seção**. Ela vai colada no corpo do PR, para o operador.
1. Merge com **todas as flags OFF** (comportamento byte-idêntico).
2. `SDA_PHASE_BUFFER_SYNC=1` (+ `SDA_PHASE_MIN_OVERLAP=3`) → 48h com ≥5 gaps provocados
   (minimizar a janela 5-8min, 2-3×/dia, ausência ≤11 giros). Passa se: zero `phase_uncertain` nos
   gaps com overlap suficiente, zero rajada DIR17 ≥3 giros.
3. **Instalar a extensão do SPR-V2** e confirmar a reconciliação contínua no cliente.
4. **Só então** `SDA_MIN_SPIN_INTERVAL_MS=15000`. *Motivo:* com cliente antigo, o servidor rejeita o
   fantasma mas o cliente **não desfaz o flip local** — servidor certo, popup espelhado. O passo 3
   fecha essa janela. +48h: descartes visíveis, zero descarte com delta >20s, `spins_received` em
   24h dentro de ±10% do baseline.
5. `SDA_PHASE_ALT_METRIC=1` (telemetria) e auditoria D+1/D+3/D+7 particionada por sessão.

## Conformidade ISO (marque ANTES de abrir o PR — `Manutenabilidade_iso.md`)
- [ ] Atrás de **flag default-OFF** na compose (ISO obrig. #4); leitura por-chamada (não cachear).
- [ ] **Aditivo/retro-compatível**; nenhuma chave de contrato WS removida/renomeada.
- [ ] **INV-3** intacto; **suíte completa verde** (`pytest tests/`).
- [ ] Novo `except Exception` → `python tools/lint_silent_except.py --update`.
- [ ] Campo de motor novo → round-trip `save()`+`load()`+`reset_session()` (exceção documentada acima).
- [ ] Não mexeu em `extension/` (se mexeu, você saiu do escopo — pare e avise o Diretor).

## Closeout (a ORDEM importa — não commitar antes de gerar o log)
1. Rodar a **Validação** (incl. suíte completa verde) e colar o resultado no `## Log`.
2. **ADENDO ISO** em `Manutenabilidade_iso.md`: capacidades novas, impacto por característica
   (Confiabilidade/Manutenibilidade/Segurança), scorecard delta, obrigações, **Rollback**, e as
   decisões conscientes: `_last_accept_srv_mono` fora do round-trip; visão fail-close;
   `AUTH_ENABLED=false` como dívida bloqueadora de V7.
3. **Code-review pós-implantação** (subagent `code-review`) → corrigir antes do PR.
4. **Append** no `## Log` (data · status · o que mudou · validação · arquivos).
5. `graphify update .` só local → **NÃO commitar `graphify-out/`**.
6. `git status` → commitar **tudo** (código + ADENDO + este brief com o Log) em `spr/SPR-V1`,
   um commit por bloco, trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
7. `git push -u origin spr/SPR-V1` e **abrir PR** (NÃO fazer merge). Cole no corpo do PR a
   **Ordem de ativação** acima.
8. `store_memory` do achado durável (escopo repository) e avisar o Diretor: *"PR de SPR-V1 aberto"*.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
### 2026-08-05 · ENTREGUE (PR aberto, sem merge) · Executor

**Resumo.** 5 blocos implementados; 4 flags novas **default-OFF**. B1: `GameState.sync_phase_buffer()`
chamado no gap do DIR4 + limpeza do buffer na correção de histórico (`SDA_PHASE_BUFFER_SYNC`). B2:
`_reconcile_shift_ex`/`phase_advance_ex` com `min_overlap` + detecção de ambiguidade
(`SDA_PHASE_MIN_OVERLAP`). B3: `_last_accept_srv_mono` + `_is_implausible_spin()`
(`SDA_MIN_SPIN_INTERVAL_MS`). B4: `_apply_seed(..., locked=None)` como caminho único, `set_seed`
preservando lock, reprojeção da âncora do operador na re-ancoragem, role-gate MASTER para
`set_seed`/`direction_event`/`nova_sessao`, fail-close da visão, bloco `phase_authority` no overlay.
B5: 4 contadores + 4 gauges + 3 alertas + métrica de alternância (`SDA_PHASE_ALT_METRIC`).

**Fronteira medida (correção do Diretor confirmada).** `m = min(len(prev), 12 - k)`; com
`min_overlap=3` gaps até **k=9** são recuperáveis; de k=10 em diante `phase_uncertain` é a resposta
CORRETA. Matriz `k=0..11` em `test_dir22_alternancia_metrica.py`.

**Validação.** Suíte completa **883 passed, 9 skipped, 1 xfailed** (baseline era 796/9/1 → +87 testes).
`python tools/lint_silent_except.py --update` → baseline atualizado (12 arquivos), `test_lint_clean_run`
verde. `promtool` **indisponível** na máquina do executor: `obs/alerts.yml` validado por parse YAML +
checagem estrutural (4 grupos, 21 regras, todas com `alert`/`expr`/`labels`/`annotations`) — **validar
com `promtool check rules` no CI/host antes de aplicar**.

**Não-interferência.** `tests/fixtures/spr_v1_replay_baseline.json` congelada rodando o harness contra o
código **pristino** (edições em `git stash`); `test_v1_nao_interferencia_replay.py` re-executa e compara
campo a campo (nunca regenera). Com as 4 flags OFF: 21 decisões idênticas em ação, cobertura, stake,
timelines, `spin_seq`, `seed_parity`/`seed_n` e ambos os buffers.

**Desvios conscientes** (detalhados no ADENDO §G): (1) `_last_accept_srv_mono` fora de `save()`/`load()`
— `time.monotonic()` só é comparável no mesmo processo; (2) gate de plausibilidade em
`_is_implausible_spin()` no `process_message`, **antes** do dedup por `trace_id` (que grava o id ao
checar — rejeitar depois queimaria o reenvio legítimo), e não dentro de `is_duplicate_spin`;
(3) `phase_authority` publicado por `GameState.engine_overlay_fields()`, pois o `state_sync` só funde
essa fonte; (4) fail-close da visão sem flag de reabertura (rollback = `git revert`).

**Arquivos.** `state/phase.py`, `state/game.py`, `state/phase_metrics.py`, `server/message_handler.py`,
`server/health_server.py`, `app_config/settings.py`, `docker-compose.yml`, `obs/alerts.yml`,
`.silent_except_baseline.json`, `Manutenabilidade_iso.md` (ADENDO 05/08), `sprints/SPR-V1.md` (este Log).
Testes: `tests/test_dir20_phase_buffer_sync.py`, `tests/test_dir21_min_spin_interval.py`,
`tests/test_dir22_alternancia_metrica.py`, `tests/test_dir23_seed_authority.py`,
`tests/test_v1_nao_interferencia_replay.py`, `tests/replay_harness_v1.py`,
`tests/fixtures/spr_v1_replay_baseline.json`, `tests/test_dir12_metrics_exporter.py` (atualizado),
`tests/test_dir9_sentido_na_sugestao.py` (atualizado).

**Dívidas.** `AUTH_ENABLED=false` bloqueia o SPR-V7; `handle_history_correction` fora do `state_lock`
(pré-existente, risco de deadlock com `handle_set_seed` — merece sprint próprio).

### 2026-08-05 (adendo) · CODE-REVIEW APLICADO · Executor

O subagente `code-review` devolveu 3 achados reais; os 3 foram corrigidos ANTES do PR.

1. **[ALTA] `min_overlap` insatisfazível com histórico curto** (`state/phase.py`). `m` é limitado por
   `min(len(prev), len(new))`, logo exigir 3 quando só existem 1-2 números tornava a condição
   IMPOSSÍVEL e transformava um alinhamento perfeito e ÚNICO em `phase_uncertain` — que aciona a
   DIR17 e re-ancora a fase na direção do CLIENTE, exatamente o vetor que a B2 existe para fechar.
   Disparava nos giros #2 e #3 depois de TODO `nova_sessao` (o `_phase_results` acabou de ser
   zerado) e com janelas curtas do cliente. **Correção:** teto
   `min_overlap = min(min_overlap, len(prev), len(new))` — a exigência de evidência nunca passa da
   evidência que PODE existir; é a mesma isenção que já valia para `prev` vazio, generalizada.
   Não afeta o caminho legado (`min_overlap=0`) nem a fronteira k=9 (com `prev`=16 e janela 12 o
   teto é inerte: `min(3,16,12)=3`). 6 testes novos, todos validados por mutação (remover o teto
   mata os 6).
2. **[MÉDIA] Branch de `phase_ambiguo_total` sem cobertura real.** O teste antigo usava uma janela
   SEM nenhum alinhamento (`ambiguous=False`) e só afirmava `phase_uncertain_total >= 1`, que o
   caminho pré-existente já satisfazia — apagar a branch nova deixaria a suíte verde. Reescrito
   para um caso que ALINHA (k=9, m=1 de 3 possíveis) e afirma `phase_ambiguo_total == 1`.
3. **[BAIXA] `handle_initial_history` não limpava `_last_accept_srv_mono`**, ao contrário de
   `handle_history_correction` e `handle_new_session`. Mesma descontinuidade, tratamento assimétrico:
   um giro aceito ANTES do histórico podia barrar, por até `SDA_MIN_SPIN_INTERVAL_MS`, o primeiro
   giro ao vivo depois dele. Corrigido.

**Validação pós-correção.** Suíte completa **890 passed, 9 skipped, 1 xfailed** (+7 testes de
regressão). `tools/lint_silent_except.py` OK (129/12, sem novos). Replay congelado continua
byte-idêntico com as flags OFF — a correção não alterou o caminho legado.

**Arquivos do adendo.** `state/phase.py`, `server/message_handler.py`,
`tests/test_dir22_alternancia_metrica.py`, `tests/test_dir23_seed_authority.py`.

### 2026-08-05 (adendo 2) · REBASE SOBRE O SPR-V2 · Executor

O SPR-V2 (PR #52, ext 3.10.0) foi integrado à `main` primeiro — decisão do Diretor, porque o código
da extensão fica **dormente até o reload** do navegador, enquanto as flags do V1 têm efeito imediato.
Branch do V1 rebaseada sobre `origin/main` (`1bc45b7`).

**Rebase limpo, sem conflitos.** O único arquivo em comum era `Manutenabilidade_iso.md` (o V2 inseriu
o ADENDO dele antes do bloco final, o V1 anexa no fim) — os dois ADENDOs coexistem íntegros.
Verificado que o diff `origin/main..HEAD` contém **apenas** os 20 arquivos do V1: `extension/`,
`tests/js/`, `.github/workflows/ci.yml`, `sprints/SPR-V2.md` e `tests/test_dir13_lock_total.py`
(piso de versão do manifest agora comparado por **tupla** `>= 3.9.1`, não por igualdade) continuam
**idênticos à `main`** — nada do V2 foi sobrescrito.

**Revalidação pós-rebase.** `pytest tests/` **890 passed, 9 skipped, 1 xfailed**. O job
`extension-tests` que o V2 acrescentou ao CI (`node --test "tests/js/*.test.js"`) roda agora também
neste PR: **53 passed** local e no CI. PR #53 com todos os checks verdes
(`lint-and-test` 3.11/3.12/3.13 + `extension-tests` + `iso-guardrails` + `ci-ok`) e
`mergeStateStatus: CLEAN`.

**Ordem de rollout (inalterada, confirmada com o Diretor):** flags do V1 no host **antes** da
instalação/reload da extensão 3.10.0 do V2. O servidor endurecido precisa estar de pé quando os
clientes novos chegarem — não o contrário.

### Adendo — contrato `phase_authority` validado contra o SPR-V2 (consumidor)

Follow-up do Diretor após o merge do SPR-V2 (PR #52, `1bc45b7`). Branch rebaseada sobre `origin/main`
**sem conflitos**; V2 preservado integralmente (`extension/`, `tests/js/`, `.github/workflows/ci.yml`,
`sprints/SPR-V2.md`, `tests/test_dir13_lock_total.py` idênticos à `main`).

**Veredito: schema compatível, nenhuma correção de escopo necessária.** O V2 consome três campos
(`enabled`, `direction`, `spin_seq`) e todos casam com o produtor. O que faltava era a *amarra*: até
aqui o V1 testava o schema isolado e o V2 usava fixtures escritas à mão, sem nada garantindo que os
dois lados falassem a mesma língua.

Novo `tests/test_v1_v2_phase_authority_contract.py` (14 testes) fecha isso executando o **canal real**
(`broadcast_heartbeat` -> `state_sync.data`, exatamente onde o V2 lê) e travando: booleano estrito no
JSON (`pa.enabled === true`), vocabulário `cw`/`ccw`, `spin_seq` vivo mesmo sem âncora (a heurística de
ACK depende disso), as 4 combinações de flags e — o achado mais relevante — a **coerência entre
`phase_authority.direction` e `sentido.next_direction`**: o V2 usa as duas fontes no mesmo payload, e
uma divergência o faria oscilar a cada heartbeat. Elas coincidem por um acidente feliz do estado atual
(`opposite(proj(n)) == proj(n+1)`), não por invariante estrutural — daí a asserção E2E.

Cobertura provada por mutação: remover o merge do overlay mata 1 teste, `enabled` como `int` mata 6,
inverter a projeção mata 6. Suítes: Python **904/9/1**, JS do V2 **53 passed**, lint OK.
