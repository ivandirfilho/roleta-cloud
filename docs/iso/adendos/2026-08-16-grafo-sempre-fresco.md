# ADENDO 16/08/2026 — Grafo sempre-fresco: kickoff auto-atualiza; super-grafo sai do git

**Origem:** incidente reportado por sessão de análise de dados 16/08 22:32 — agente novo
encontrou (a) worktree sem grafo local (artefato gitignored → toda sessão nasce sem) e
(b) `super_graph/graphify-out/graph.json` VERSIONADO e congelado no commit de 14/06
(4.475 nós, 2 meses defasado), que ele leu como "o último grafo real".

## 1. Diagnóstico

O agente estava CERTO na honestidade — e a configuração estava errada em três pontos:

1. **Frescor era responsabilidade difusa** ("mantenha o grafo fresco") — cada sessão
   deveria decidir rodar `graphify update .`, e nenhuma rodava.
2. **O check de frescor da skill era inoperante**: `graph.json` não carrega
   `built_at_commit` — a comparação prometida nunca funcionou.
3. **A única cópia versionada era a pior**: super-grafo de 8,7 MB, parado desde 14/06 —
   violava o próprio princípio do repo ("NÃO commitar graphify-out") por outro caminho.

**Fato decisivo medido:** build completo do grafo deste repo = **5s** (incremental 3s).
Toda a complexidade de caches/artefatos/CI seria over-engineering.

## 2. O que mudou

| Peça | Antes | Agora |
|---|---|---|
| `scripts/agent-kickoff.ps1` §5 | checava metadata (inexistente) e SUGERIA update | **roda `graphify update .`** (~5s) — toda sessão nasce com grafo do HEAD |
| `super_graph/graphify-out/` | versionado, 14/06, 8,7 MB | **removido do git** + gitignore; README explica regeneração (`rebuild_super_graph.ps1`) |
| `.github/copilot-instructions.md` / `AGENTS.md` | "grafo primeiro / mantenha fresco" | "kickoff garante o frescor; grafo = artefato derivado, nunca verdade" |
| Skill user-level `graphify-first` | check de frescor por metadata | atualizada no estate: worktree novo = sem grafo é NORMAL; kickoff resolve |

## 3. Como reverter

`git revert` (kickoff volta a só checar; super-grafo stale NÃO volta — regenerável).

## 4. Lição ISO (25010 Manutenibilidade / 14764)

Artefato derivado versionado sem pipeline de atualização é **documentação que mente com
autoridade**. Ou o artefato tem dono automático (como o kickoff agora é dono do grafo
local), ou não pode existir no git. E: meça antes de arquitetar — o "problema de cache
de grafo" custava 5 segundos.
