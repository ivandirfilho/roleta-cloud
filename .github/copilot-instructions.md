# Roleta Cloud — instruções do repositório (auto-carregadas em toda sessão)

> Backend de roleta em tempo real (WebSocket + SQLite, Docker no Debian) + extensão Chrome "Escuta Beat".
> **Contrato operacional completo (camadas local/git/Debian, ciclo zero-humano, anti-conflito): `AGENTS.md` na raiz.**
> Blueprint completo: `fluxo_mental_24.md`. Metodologia de sprints: `evolução_24_junho.md`. Board: `sprints/BOARD.md`.

## Ritual de abertura (OBRIGATÓRIO — antes da primeira ação de QUALQUER tarefa)
1. Rode `pwsh -File scripts/agent-kickoff.ps1` (~10s, read-only): te dá main-red, PRs
   abertos (lock check), últimos merges, estado REAL de produção (endpoints), frescor do
   grafo e o tail do board. **Não pergunte ao usuário nada que esse output já responde.**
2. Orientação profunda: `AGENTS.md` (contrato + mapa de leitura §5) e, para código,
   grafo local (`graphify query --graph graphify-out/graph.json`) ANTES de grep/leitura ampla.
3. Estado de produção NUNCA por suposição: endpoints `/health`/`/metrics` + issues
   abertas. Servidor é intocável (sem ssh) — se a causa exigir host, é issue para o dono.

## Invioláveis (toda mudança)
- **INV-3:** a estratégia SEMPRE indica `APOSTAR`; um veto entra como `min()` no stake e **nunca** suprime a indicação.
- **Flags na compose:** comportamento novo nasce **atrás de flag default-OFF** em `docker-compose.yml`; leitura por-chamada (não cachear); nada hardcoded.
- **Migração Alembic ADITIVA/retro-compatível** (o rollback de deploy NÃO faz downgrade de schema).
- **Persistência round-trip:** campo de motor novo entra em `save()` + `load()` + `reset_session()`.
- **`main` é produção:** o systemd timer puxa `origin/main` e faz deploy em ~2 min. NUNCA push/checkout/reset/merge direto em `main`; entregue por **PR**. Sem ssh/host/deploy a partir de um sprint.
- **Espelho Azure no MESMO PR:** flag nova/alterada em `docker-compose.yml` → sincronize `deploy/azure/compose.azure.yml` (contrato `tests/test_azure_pre_cutover.py` falha se divergir).
- **Workflow novo com secrets externos nasce GATEADO** por repo variable default-OFF (ex.: `if: ${{ vars.X_ENABLED == '1' }}`) — senão a main fica vermelha no primeiro push pós-merge.
- **NÃO commitar `graphify-out/`** (artefato pesado, regenerável); rode `graphify update .` apenas localmente.
- **Última milha é parte da entrega ("mergeou ≠ implantado" é bug de esteira):** todo artefato consumido FORA do git precisa de mecanismo de sincronização automática no mesmo desenho — host Debian (entrypoint+`roleta.conf`: coberto pelo shim do SPR-D2, que segue `origin/main` a cada tick) e máquina do operador (extensão Chrome carregada de `Desktop\Roleta Cloud\extension`: até o SPR-D4, o merge em `extension/` só chega com `git pull` no checkout + Reload no Chrome — registre essa pendência no PR/board).

## Fluxo de sprints (Diretor ↔ Executor) — ciclo zero-humano
- **Diretor** orquestra (mantém `sprints/BOARD.md` + briefs), NÃO implementa. **Só o Diretor edita o BOARD** (em lote, pós-integração) — Executor nunca, para não virar ímã de conflito.
- **Executor** = 1 sprint por vez, no worktree da própria sessão: renomeie o branch para `spr/SPR-XXX` (tool `rename_branch`) no kickoff, valide pela DoD, escreva o **ADENDO como arquivo novo** em `docs/iso/adendos/AAAA-MM-DD-<slug>.md` (convenção no README da pasta; NÃO apendar em `Manutenabilidade_iso.md`), **abra PR com base `main`** (`gh pr create --base main`; confira `baseRefName==main` — base `spr/*` não tem proteção e o auto-merge executa NA HORA sem CI) com título **`SPR-XXX:`** e **arme auto-merge** (`gh pr merge --auto --squash <nº>`) — o PR mergeia sozinho quando `ci-ok` ficar verde. NUNCA `--admin`/bypass; NUNCA merge manual.
- **Lock check pré-PR (anti-silo):** `gh pr list` + arquivos dos PRs abertos; se seu diff colide com PR aberto, serialize (aguarde/rebase) em vez de abrir PR paralelo.
- **Ativação também é PR — nunca "ação humana pendente":** sprint com flag default-OFF só está entregue quando a flag liga. Política: flags **shadow/audit** (sem efeito em aposta) ligam IMEDIATAMENTE via PR de ativação (branch `flag/ativar-<slug>`, muda o default na compose + adendo + auto-merge); flags de **comportamento** ligam após janela shadow limpa registrada em adendo. Deploy ~2min pós-merge; rollback = revert (~4min).
- **main vermelho pós-merge:** o CI abre issue `main-red` sozinho → vira sessão de agente (revert ou fix-forward). Rede de segurança: `ci-ok` required + matrix completa no push de main + tudo nasce flag-OFF + revert barato (strict OFF por design, para o auto-merge fluir sem humano).
- Detalhes operacionais: `fluxo_mental_24.md` §6, §9–§12. Aberturas/painel/GO: `evolução_24_junho.md` §0, §6, §8.

## Convenções
- Grafo primeiro (`graphify`) antes de `grep` cego; mantenha o grafo fresco mas NÃO o commite.
- Suíte verde (`pytest tests/`) + lints (`tools/lint_silent_except.py --update` se novo `except`) antes do PR.
- Commits com trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
