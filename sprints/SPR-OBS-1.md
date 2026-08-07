# SPR-OBS-1 — Produção legível por agentes (fecha o loop de feedback sem SSH)

## Meta
- **Prioridade:** P1 · **Deps:** nenhuma · **Locks:** `health_server`, `docker-compose.yml`
- **Base:** origin/main no kickoff

## Dor
O ciclo zero-humano (adendo `2026-08-06-fluxo-zero-humano.md`) integra e ativa sem humano,
mas os agentes ainda **não conseguem LER produção**: para saber "qual commit está rodando?",
"quais flags estão ligadas?", "o relógio shadow está acumulando eventos?", hoje seria preciso
SSH — que é proibido a sprints por segurança estrutural. Sem isso, gates temporais (7d do T4,
30d do V6B) não são verificáveis por agente, e a "evidência de produção" continua dependendo
de humano.

## Tarefa
Estender o `health_server` existente com um endpoint de estado agregado (ex.: `GET /health/agent`),
retornando JSON com:
1. `commit_sha` do código em execução (injetado no build/deploy — ex.: env `GIT_SHA` gravada
   pelo script de deploy do systemd timer) e timestamp do deploy;
2. snapshot das flags `SDA_*` efetivas (nome → valor, lido por-chamada como manda o inviolável);
3. contadores mínimos dos relógios shadow: nº de linhas em `phase_events` + timestamp do
   primeiro/último evento (é o que prova que o gate T4 está contando);
4. sem dado sensível (sem DSN, sem paths, sem tokens). Read-only. Se o endpoint exigir
   auth hoje, um token estático via env flag default-OFF (`SDA_AGENT_HEALTH_TOKEN`).

## Critério de pronto (DoD)
- [ ] Endpoint responde local (teste unitário + teste de contrato do JSON).
- [ ] Flag default-OFF na compose (`SDA_AGENT_HEALTH=0`) — comportamento novo atrás de flag.
- [ ] `pytest tests/` verde + lints; adendo em `docs/iso/adendos/`.
- [ ] PR `SPR-OBS-1:` com auto-merge armado + PR de ativação (`flag/ativar-agent-health`) na
      sequência (shadow/read-only ⇒ ativação imediata pela política).
- [ ] Documentar no adendo COMO um agente consulta (curl do endpoint público/WSS host).

## Rollback
`SDA_AGENT_HEALTH=0` + redeploy (~4min) ou revert do PR.

## Log
- 2026-08-06: brief criado pela sessão de governança (fix-fluxo-ci-governanca) como peça
  final do ciclo zero-humano: agente escreve (PR) → integra (auto-merge) → ativa (PR de flag)
  → **lê produção (este sprint)** → decide o próximo passo sem humano.
