# super_graph — gerador do super-grafo multi-projeto

Scripts que fundem os grafos por-repo (Roleta Cloud, Genesis, android, server_snapshot,
backbone `_INFRA_`) num super-grafo de visão cruzada.

## ⚠️ A saída NÃO é versionada (lição 16/08)

`super_graph/graphify-out/` ficou 2 meses congelada no git (build de 14/06) e virou
**armadilha**: agentes a encontravam como "o último grafo real" e raciocinavam sobre
arquitetura defasada. Grafo é **artefato derivado** — a verdade é o código.

- **Grafo do repo atual:** `scripts/agent-kickoff.ps1` já roda `graphify update .`
  (~5s) em toda abertura de sessão — sempre fresco, nunca commitado.
- **Super-grafo (visão cross-repo):** regenere sob demanda com
  `pwsh -File super_graph/rebuild_super_graph.ps1` — a saída fica local
  (gitignored) e alimenta o MCP global (`~/.graphify/global-graph.json`).
