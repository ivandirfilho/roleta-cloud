# Roleta Cloud — instruções do repositório (auto-carregadas em toda sessão)

> Backend de roleta em tempo real (WebSocket + SQLite, Docker no Debian) + extensão Chrome "Escuta Beat".
> Blueprint completo: `fluxo_mental_24.md`. Metodologia de sprints: `evolução_24_junho.md`. Board: `sprints/BOARD.md`.

## Invioláveis (toda mudança)
- **INV-3:** a estratégia SEMPRE indica `APOSTAR`; um veto entra como `min()` no stake e **nunca** suprime a indicação.
- **Flags na compose:** comportamento novo nasce **atrás de flag default-OFF** em `docker-compose.yml`; leitura por-chamada (não cachear); nada hardcoded.
- **Migração Alembic ADITIVA/retro-compatível** (o rollback de deploy NÃO faz downgrade de schema).
- **Persistência round-trip:** campo de motor novo entra em `save()` + `load()` + `reset_session()`.
- **`main` é produção:** o systemd timer puxa `origin/main` e faz deploy em ~2 min. NUNCA push/checkout/reset/merge direto em `main`; entregue por **PR**. Sem ssh/host/deploy a partir de um sprint.
- **NÃO commitar `graphify-out/`** (artefato pesado, regenerável); rode `graphify update .` apenas localmente.

## Fluxo de sprints (Diretor ↔ Executor)
- **Diretor** orquestra (mantém `sprints/BOARD.md` + briefs), NÃO implementa.
- **Executor** = 1 sprint por vez, em **worktree próprio** (`git worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main`), valida pela DoD, escreve o **ADENDO** em `Manutenabilidade_iso.md`, e **abre PR** (não faz merge).
- Detalhes operacionais: `fluxo_mental_24.md` §6, §9–§12. Aberturas/painel/GO: `evolução_24_junho.md` §0, §6, §8.

## Convenções
- Grafo primeiro (`graphify`) antes de `grep` cego; mantenha o grafo fresco mas NÃO o commite.
- Suíte verde (`pytest tests/`) + lints (`tools/lint_silent_except.py --update` se novo `except`) antes do PR.
- Commits com trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
