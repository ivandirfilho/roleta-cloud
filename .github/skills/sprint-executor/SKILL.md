---
name: sprint-executor
description: Use quando o usuário pedir para executar/implementar um sprint do Roleta Cloud (sprints/SPR-*.md). Injeta a sequência, a Definition of Done, os rituais ISO e o closeout (worktree → PR).
---

Quando pedirem para executar um sprint `sprints/SPR-XXX.md`:

1. Abra o brief e leia `Meta` (deps/locks), `Âncoras`, `Tarefa`, `Critério de pronto`, `Rollback`.
2. **Worktree próprio:** `git worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main` e trabalhe nele (nunca no working dir do Diretor).
3. Implemente respeitando os invioláveis (`.github/copilot-instructions.md`): INV-3 · flag default-OFF na compose · migração Alembic aditiva · persistência `save`/`load`/`reset_session` · não commitar `graphify-out/`.
4. **Valide:** teste-alvo + **suíte completa** (`pytest tests/`) verde; se novo `except`, `python tools/lint_silent_except.py --update`.
5. **ISO:** escreva o **ADENDO** em `Manutenabilidade_iso.md` (capacidades + impacto ISO + obrigações + Rollback); append no `## Log` do brief.
6. **Entregue:** commit em `spr/SPR-XXX` (trailer Co-authored-by Copilot) → `git push -u origin spr/SPR-XXX` → **abrir PR** (não merge). NUNCA push/merge em `main`.

Detalhes: `fluxo_mental_24.md` §9, §12 · agente `sprint-executor`.
