---
name: sprint-status
description: Use quando o usuário pedir "status" dos sprints do Roleta Cloud. Cruza sprints/BOARD.md com os PRs abertos e a CI, devolvendo um painel de 1 tela.
---

Quando pedirem **"status"**, rode o painel e resuma em 1 tela:

```
pwsh -File scripts/sprint-status.ps1
```

O script mostra, por sprint: estado no board (`sprints/BOARD.md`), PR aberto (`gh pr list`) e status de CI.
Em seguida, destaque o que **pede o usuário**: PRs `merge-ready` (CI verde) e itens `flag-ready` (mergeados, esperando ligar a flag na `docker-compose.yml`).

Se `gh` não estiver disponível, mostre só o board e avise.
