---
name: sprint-executor
description: Use quando o usuário pedir para executar/implementar um sprint do Roleta Cloud (sprints/SPR-*.md). Injeta a sequência, a Definition of Done, os rituais ISO e o closeout (worktree → PR).
---

Quando pedirem para executar um sprint `sprints/SPR-XXX.md`:

1. Abra o brief e leia `Meta` (deps/locks), `Âncoras`, `Tarefa`, `Critério de pronto`, `Rollback`.
2. **Worktree/branch próprios:** em sessão Copilot, use o worktree da sessão e **renomeie o branch para `spr/SPR-XXX`** (tool `rename_branch`); fora dela: `git worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main`. Nunca no working dir do Diretor.
3. Implemente respeitando os invioláveis (`.github/copilot-instructions.md`): INV-3 · flag default-OFF na compose · migração Alembic aditiva · persistência `save`/`load`/`reset_session` · não commitar `graphify-out/`.
4. **Valide:** teste-alvo + **suíte completa** (`pytest tests/`) verde; se novo `except`, `python tools/lint_silent_except.py --update`.
5. **ISO:** escreva o **ADENDO** como arquivo novo `docs/iso/adendos/AAAA-MM-DD-<slug>.md` (convenção no README da pasta) — NÃO apendar em `Manutenabilidade_iso.md`; append no `## Log` do brief. **Não edite `sprints/BOARD.md`** (é do Diretor).
6. **Lock check anti-silo:** `gh pr list` + arquivos dos PRs abertos; se colidir com seu diff, serialize (não abra PR paralelo).
7. **Entregue:** commit (trailer Co-authored-by Copilot) → push → **abrir PR com título `SPR-XXX: <resumo>`** → **armar auto-merge** `gh pr merge --auto --squash <nº>` (nunca `--admin`/merge manual). NUNCA push/merge em `main`.
8. **Flag shadow/audit criada?** Abra também o PR de ativação (`flag/ativar-<slug>`: default `:-1}` na compose + adendo + auto-merge). Flag de comportamento espera janela shadow limpa.

Detalhes: `fluxo_mental_24.md` §9, §12 · agente `sprint-executor`.
