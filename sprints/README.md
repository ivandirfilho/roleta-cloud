# Sprints — guia rápido (metodologia Roleta Cloud)

> Como você (gestor) e os agentes operam. Visão completa: `../evolução_24_junho.md` e `../fluxo_mental_24.md`.

## PLAN → GO
- **PLAN** (discussão, sem código): `Shift+Tab` entra/sai do plan mode. Você fala dores/estruturas; o **Diretor** vira sprints.
- **GO** ("rodar"): autopilot executa tudo, **sem aprovação no meio**. A segurança é **estrutural** (branch protection, flags default-OFF, git hooks, sandbox), não por prompts.

## Aberturas de conversa
| Você diz | Resultado |
|---|---|
| `Dor: <descrição>` | vira 1+ sprint (brief + linha no board) |
| `Plano para <tema>` | plan mode: sprints + ordem/paralelismo + riscos |
| `Status` | painel (board × `gh pr list` × CI) — `pwsh scripts/sprint-status.ps1` |
| `Auditar o plano` | rubber-duck / code-review antes do GO |
| `Rodar SPR-X[,Y,Z]` | GO (autopilot) |

## Papéis
- **Diretor** (`--agent sprint-director`): orquestra, mantém `BOARD.md` + briefs, NÃO implementa.
- **Executor** (`--agent sprint-executor` ou `/delegate`): 1 sprint, worktree próprio, valida pela DoD, ADENDO ISO, **abre PR**.

## Arquivos
- `BOARD.md` — estado vivo dos sprints. · `_BRIEF_TEMPLATE.md` — template. · `SPR-*.md` — briefs.
- `../.github/{copilot-instructions.md,agents,skills}` — nativo (auto-carrega; `/delegate` herda).
- `../.githooks/` — guardrails (ative: `git config core.hooksPath .githooks`). · `../scripts/methodology-go.ps1` — bootstrap.

## Acompanhar N sprints (dia a dia)
Cada sprint = 1 branch `spr/SPR-*` = 1 PR = 1 linha no board. Paralelo seguro = `locks` disjuntos.
Peça **"status"** a qualquer momento; o que **pede você** é merge-ready (CI verde) ou flag-ready (mergeado, esperando ligar a flag).
