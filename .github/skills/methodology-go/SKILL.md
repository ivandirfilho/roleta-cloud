---
name: methodology-go
description: Use quando o usuário disser "GO", "RODAR IMPLANTAÇÃO", "implantar metodologia" ou equivalente. Dispara o bootstrap idempotente da metodologia de sprints (scripts/methodology-go.ps1).
---

Gatilho do **GO** — sair da discussão (PLAN) e rodar toda a sequência de implantação da metodologia.

Ao reconhecer o pedido, execute o bootstrap idempotente:

```
pwsh -File scripts/methodology-go.ps1
```

O script (idempotente, seguro de re-rodar):
1. valida o scaffold nativo (`.github/copilot-instructions.md`, `.github/agents/*`, `.github/skills/*`);
2. liga os git hooks versionados (`git config core.hooksPath .githooks`);
3. garante `.gitignore` de `graphify-out/graph.{json,html}`;
4. configura GitHub (branch protection na `main`; `allow_auto_merge`) via `gh` — best-effort;
5. cria o branch `spr/methodology-bootstrap`, commita o scaffold e abre o PR.

Use `-DryRun` para só auditar sem efeitos. Referência: `evolução_24_junho.md` §6, §8.
NUNCA mescle direto em `main`: o bootstrap entrega por PR.
