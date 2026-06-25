# BOARD — Estado vivo dos sprints (o Diretor atualiza AQUI)

> Definição canônica dos sprints = `fluxo_mental_24.md` §7. Este arquivo = **estado**. Mantê-lo pequeno.
> **Commitar+push** este arquivo e o brief ANTES de lançar um executor (senão um novo Diretor não os vê).

**Estados:** `TODO → READY` (brief pronto) `→ DOING → REVIEW` (PR aberto) `→ MERGED/DONE` · ou `BLOCKED`.
**Branch:** `spr/SPR-*` · **1 executor = 1 worktree** (`git worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main`).
**Paralelo só com `Locks` disjuntos.** `schema/alembic` e `BLK-G` serializam entre si (numeração de migração / cérebro da estratégia colidem).

**Resumir como Diretor (sessão nova):** `git fetch --all`; ler este board; p/ cada sprint `DOING/REVIEW` rodar `git fetch origin spr/SPR-* && git diff --stat origin/main...spr/SPR-*` + ler o tail do log em `sprints/SPR-*.md` + `memory.search_nodes`.

| SPR | Pri | Status | Branch | Depende de | Locks | PR / Nota |
|---|---|---|---|---|---|---|
| SPR-G2 | P0 | **READY** | spr/SPR-G2 | — | schema, alembic, BLK-I | brief `sprints/SPR-G2.md` |
| SPR-S1 | P0 | TODO | — | **SPR-G2** | BLK-G (análise) | — |
| SPR-G1 | P1 | TODO | — | — | versioning, docs | — |
| SPR-G3 | P1 | TODO | — | — | deploy, compose, BLK-K | — |
| SPR-S2 | P1 | TODO | — | **SPR-G2** | BLK-G, BLK-E | — |
| SPR-S3 | P1 | TODO | — | — | BLK-D, BLK-G | — |
| SPR-S4 | P1 | TODO | — | — | BLK-D | — |
| SPR-S6 | P1 | TODO | — | — | BLK-L (harness) | — |
| SPR-T4 | P1 | TODO | — | — | BLK-E, ingest | — |
| SPR-X3 | P1 | TODO | — | — | extensão (JS) | — |
| SPR-S5 | P2 | TODO | — | — | BLK-D | — |
| SPR-G4 | P2 | TODO | — | — | schema, alembic | serializa c/ SPR-G2 |
| SPR-G5 | P2 | TODO | — | — | docs, feature_flags | — |
| SPR-G6 | P2 | TODO | — | — | docs | — |
| SPR-T1 | P2 | TODO | — | — | BLK-G | — |
| SPR-T2 | P2 | TODO | — | — | BLK-G | — |
| SPR-T3 | P2 | TODO | — | — | BLK-I | — |
| SPR-T6 | P2 | TODO | — | — | repo-hygiene | — |
| SPR-X1 | P2 | TODO | — | — | extensão (JS) | — |
| SPR-X2 | P2 | TODO | — | — | extensão, BLK-D | — |
| SPR-X4 | P2 | TODO | — | — | extensão (JS) | — |
| SPR-O1 | P2 | TODO | — | — | obs | — |
| SPR-T7 | P2 | TODO | — | — | BLK-D | ISO §D.1 (sem alterar comportamento) |

<!-- DIRETOR: ao mudar status, atualize só a linha. base_sha/owner ficam no cabeçalho do brief. -->
