# SPR-V7 · Autoridade limitada à correção da ÂNCORA futura · Bloco BLK-D/BLK-I · Pri P3 **condicional**

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `proposta_seletor_sentido_03_08.md` §10.2.3, §10.4 (matriz pode/nunca), §10.5, §11.3, §11.4-F, §11.6.

## 🚫 STATUS: BLOCKED — não execute
```text
blocked_by: [SPR-V5 (merged + shadow rodando), Gate T4 integral, autenticação/role-gate funcional]
```
Destrava **somente** quando o Diretor registrar no `sprints/BOARD.md` **todos** os itens:

**Gate T4 (integral, falseável):**
- ≥**7 dias corridos** E ≥**2000 vereditos** em shadow, **com V1/V2 ligados e âncora confirmada**
  (shadow contra referência corrompida é ruído, não shadow);
- **cobertura é medida ANTES de concordância** (200 bursts com 2 erros = "99%" é escassez disfarçada);
- `agree` ≥**99,5%** entre os eventos emitidos;
- **100% dos desacordos auditados** pela trilha `phase_events` (o ring local é evidência auxiliar);
- **controle positivo** com âncora deliberadamente espelhada — executado em **replay, sessão sintética
  ou projeção shadow paralela**. ⚠️ **NUNCA** espelhe o seed produtivo: com INV-3 a aposta sai, então
  um seed produtivo deliberadamente errado **muda o lado da aposta real com dinheiro**;
- **nenhum caso** em que K=3 coerentes teria corrigido errado;
- `stale + selfcontradict` <1%;
- cobertura ≥60% dos giros com aba visível (se a aba fica visível <30% do tempo de operação, **o
  programa não paga — encerrar**);
- beat de 2s e SW sem degradação.

**Bloqueadores independentes do T4:**
- **Autenticação funcional (`SPR-V8`, a abrir pelo Diretor)**: hoje `AUTH_ENABLED=false` e
  `verify_auth(None)` significa que simplesmente ligar auth **rejeitaria todas as conexões**; o token
  precisa ser extraído do handshake e enviado pela extensão. O gate MASTER do SPR-V1 é
  **concorrência entre clientes, não autorização**. Sem auth funcional, **não** existe autoridade
  automática. Aceite do `SPR-V8`: conexão com token válido aceita; token ausente/inválido rejeitada
  com código próprio; role derivada do token (não do primeiro a chegar); rollout atrás de flag
  default-OFF; suíte completa verde.
- **SPR-V4 mergeado e ativo** (trilha durável é a prova; Prometheus não serve — counters zeram no
  restart do container). O relógio dos 7 dias começa quando `SDA_PHASE_EVENT_AUDIT=1` **e**
  `SDA_DIRECTION_VISION_SHADOW=1` estão ativos, com a data registrada no board.
- **Controle positivo** já entregue pelo `SPR-V5` (item 6 daquele brief): harness de replay/sessão
  sintética com âncora espelhada. Ele é **insumo** deste gate, não tarefa deste sprint.
- Decisão humana registrada (§10.6).

Se você é um executor e chegou aqui sem isso no board: **pare e avise o Diretor.**

## Meta (preencher quando destravar)
```text
blocked_by: [SPR-V5, SPR-V8 (auth), Gate T4 integral]
locks:      [message_handler-fase, game-state, phase, settings, phase_metrics, alerts, tests]
touches:    [state/phase.py, state/game.py, server/message_handler.py, app_config/settings.py,
             state/phase_metrics.py, server/health_server.py, obs/alerts.yml, docker-compose.yml, tests/]
base_sha:   origin/main
branch:     spr/SPR-V7
```

## Objetivo (1 frase)
Permitir que evidência acumulada corrija a **âncora do próximo giro** — de forma auditável, reversível
e limitada — **sem jamais** tocar o giro corrente.

## Matriz pode/nunca (invariável — copiada de §10.4)
**NUNCA toca:** `direcao` do spin corrente · `spin_seq` · `timeline_cw/ccw` · decisão/stake (INV-3) ·
seed com `direction_locked=true`.
**SÓ PODE tocar:** `seed_parity` / `seed_n` / `direction_source`, pelo **mesmo caminho auditável do
`set_seed`** (`_apply_seed(..., source="vision")`, criado no SPR-V1).
**Razão de ser:** autoridade per-spin foi **rejeitada** — um erro contamina timeline, população
estratégica e a **aposta real**, sem des-inserir. Uma correção de âncora pode ser acumulada,
auditada e revertida. Pior caso do detector espelhado: a alternância fica *perfeita* no banco e o
DIR22 **não vê nada** — por isso o controle positivo é obrigatório.

## Tarefa (quando destravar)
1. Guard-rail com **todos** os parâmetros por flag (default-OFF, leitura por chamada):
   `SDA_VISION_ANCHOR_FIX=0`, `SDA_VISION_ANCHOR_K=3`, `SDA_VISION_ANCHOR_MIN_CONF=0.8`,
   `SDA_VISION_ANCHOR_REFRACT=10`.
2. Regra: **K=3 desacordos consecutivos coerentes** com `confidence ≥0,8` ⇒ solicita `_apply_seed`
   para o **giro seguinte**. Histerese; **refratário de 10 giros**; **máximo 1 correção automática por
   sessão** (a 2ª exige clique do operador); **auto-desqualificação** se o próprio sensor violar a
   alternância; **lock manual vence sempre**; alerta Prometheus **por evento de correção**.
3. **Semântica exata do "próximo giro" (escreva a fórmula no ADENDO e no teste):** a correção calcula
   o par `(seed_parity, seed_n)` tal que `project_phase(spin_seq_corrente + 1)` produza a direção
   observada — **sem** alterar `spin_seq` nem a `direcao` já gravada do giro corrente. Deixar isso a
   critério do implementador é convite a off-by-one silencioso, exatamente a classe de bug que este
   programa existe para eliminar.
4. **Protocolo idempotente intent → persistência → aplicação:** grave primeiro a **intenção** em
   `phase_events` (`kind='anchor_fix_intent'`, com a evidência), depois aplique via `_apply_seed`,
   depois grave `kind='anchor_fix_applied'` — decisão e disposição na **mesma transação**, como no
   SPR-V4. Crash entre as etapas ⇒ ao reiniciar, `intent` sem `applied` é **descartado** (nunca
   reaplicado às cegas) e o fato é logado. Teste de falha injetada em **cada** fronteira.
5. **Round-trip obrigatório**: `streak`, candidato, refratário, contagem de correções e a evidência
   entram em `save()` + `load()` + `reset_session()` (`state/game.py:1340-1502`, `:305-413`).
6. **Regressão do fail-close da visão (herdada do SPR-V1):** este sprint volta a tocar
   `message_handler.py`. Repita o teste explícito: com `SDA_DIRECTION_VISION=1` e
   `SDA_VISION_ANCHOR_FIX=0`, o resultado é **idêntico** ao da flag OFF. A flag
   `SDA_DIRECTION_VISION` permanece **congelada em 0** — autoridade per-spin segue rejeitada.
7. **Canário (T5)**: uma sessão por vez, no máximo 1 correção, e o **operador confirma o resultado**.

## Critério de "pronto" (Definition of Done)
- [ ] Com a flag OFF, comportamento **byte-idêntico** (replay antes × depois).
- [ ] K, confidence mínima, histerese, refratário e "máx. 1/sessão" testados **por caso**.
- [ ] `direction_locked=true` ⇒ **nenhuma** correção, em nenhuma circunstância (teste).
- [ ] Correção só afeta o **próximo** giro; o giro corrente permanece intocado (teste explícito de
      `direcao`, `spin_seq` e timelines) e a **fórmula do par `(seed_parity, seed_n)` está no ADENDO**.
- [ ] Protocolo `intent → apply → applied` idempotente; falha injetada em cada fronteira ⇒ nenhuma
      correção meio-aplicada; `intent` órfão pós-restart é descartado e logado (teste).
- [ ] Round-trip completo de todo estado novo (`save`/`load`/`reset_session`).
- [ ] Auto-desqualificação do sensor que viola a alternância (teste).
- [ ] Com `SDA_DIRECTION_VISION=1` e `SDA_VISION_ANCHOR_FIX=0` o resultado é **idêntico** ao da flag
      OFF (regressão do fail-close do SPR-V1).
- [ ] Alerta por evento de correção + linha na trilha com evidência.
- [ ] Controle positivo (harness do SPR-V5) executado em **replay/sessão sintética**, nunca em produção.
- [ ] **Não-interferência** com fixture congelada e asserção campo a campo, flags novas OFF.
- [ ] `pytest tests/` completo verde.

## Validação (rode e cole o resultado no Log)
```
python -m pytest tests/                       # suíte COMPLETA
python tools/lint_silent_except.py --update   # só se criou except Exception
promtool check rules obs/alerts.yml           # ou validação YAML equivalente
```

## Stop-conditions com a flag ativa (obrigatórias no ADENDO)
- **1 correção de âncora errada** ⇒ flag `=0` **imediato**.
- `disagree` >1% sustentado por 24h ⇒ **volta a shadow**.
- **>1 correção por sessão tentada** ⇒ é bug: desligar.

## Guardrails (inviolável)
- **INV-3** intacto: a estratégia sempre indica; vetos entram como `min()` no stake.
- Flags default-OFF; leitura por chamada; nada hardcoded.
- Round-trip `save`/`load`/`reset_session` de **todo** campo de motor novo.
- **Git**: só no worktree/branch `spr/SPR-V7`; **NUNCA** main; entregue por **PR**; sem SSH/host/prod.
- Sem `except Exception: pass`; **não commitar `graphify-out/`**.

## Rollback (ISO — execução é do **operador**, não deste sprint)
`SDA_VISION_ANCHOR_FIX=0` + `docker compose up -d` (minutos) ou `git revert` do PR. O estado
persistido é aditivo e inerte com a flag OFF.

## Closeout
Validação → **ADENDO ISO** (incl. stop-conditions, canário e o registro de que auth funcional era
pré-requisito) → `code-review` → Log → `graphify update` local → commit em `spr/SPR-V7` (trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`) → push → **abrir PR** →
`store_memory` → avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
