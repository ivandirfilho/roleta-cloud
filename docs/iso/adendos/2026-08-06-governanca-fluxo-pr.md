# ADENDO 06/08/2026 — Governança do fluxo de PRs (anti-silo)

**Origem:** sessão `ivandirfilho-fix-fluxo-ci-governanca` (diagnóstico de silos de PR).
**Escopo:** processo/CI/documentação. Zero mudança de comportamento de runtime; zero flag nova.

## Diagnóstico que motivou (evidências de 05-06/08)

1. **CI vermelho ≠ código quebrado.** Os jobs "Cancelled" do e-mail de 06/08 foram
   starvation de runner hospedado ("The job was not acquired by Runner of type hosted
   even after multiple attempts"); o re-run do MESMO commit ficou verde. Amplificador:
   ~100 runs em 05/08 sem `concurrency` no workflow + `strict:true` na proteção de main
   (cada merge re-bloqueia todos os PRs abertos até re-CI).
2. **Silos de PR.** 4 PRs abertos com 3/4 tocando `Manutenabilidade_iso.md` +
   `docker-compose.yml`; #58/#60 colidindo em `server/message_handler.py`,
   `database/outbox_integration.py`, `.silent_except_baseline.json`. PR #59 fechado
   como trabalho duplicado do #57. Board dizia V1/V2 "READY" quando já estavam MERGED.
3. **Código mergeado ≠ código rodando.** Compose de produção com
   `SDA_PHASE_BUFFER_SYNC=0`, `SDA_MIN_SPIN_INTERVAL_MS=0`, `SDA_PHASE_EVENT_AUDIT=0`,
   `SDA_DIRECTION_VISION_SHADOW=0`: os sprints V1/V2/V4 estão deployados e **inertes**,
   e os relógios de gate (30d do V6B, 7d do T4) nunca começaram a contar.
4. **Branches `spr/SPR-V1`/`spr/SPR-V2` órfãos** (só o commit do brief do Diretor);
   os executores trabalharam em branches auto-gerados `ivandirfilho-*`, invisíveis
   para o board.

## O que muda (decisões)

| # | Decisão | Materialização |
|---|---|---|
| 1 | Workflows com `concurrency` por ref; `main` nunca cancela | `.github/workflows/ci.yml`, `iso-guardrails.yml` |
| 2 | ADENDO vira **arquivo próprio** em `docs/iso/adendos/` | esta pasta + ponteiro no fim do doc-mãe + guardrail aceita ambos |
| 3 | Executor renomeia branch para `spr/SPR-XXX` no kickoff; título do PR começa com `SPR-XXX:` | agentes/skills + copilot-instructions |
| 4 | Lock check pré-PR inclui **PRs abertos** (`gh pr list` + diff), não só sprints DOING | BOARD.md (Como usar) + copilot-instructions |
| 5 | Executor **não edita** `sprints/BOARD.md` (2º maior ímã de conflito); Diretor atualiza em lote pós-janela de integração | sprint-director.md |
| 6 | Merge train para `strict:true`: um PR por vez, update-branch entre cada. Fila 06/08: #60 → #61 → #58 → #43 (fatiar) | BOARD.md |

## Reversão

Processo/documentação: revert do PR restaura o fluxo anterior. Sem flag, sem migração,
sem impacto de runtime.

## Lição ISO

- **ISO/IEC 14764 (manutenibilidade de processo):** artefatos append-only compartilhados
  entre trilhas paralelas viram pontos de serialização; a evolução paralela exige
  superfícies de escrita disjuntas (arquivo-por-mudança).
- **ISO 25010 – manutenibilidade/modularidade:** o "estado do sistema" (board, relógios
  de ativação) precisa de dono único (Diretor) e atualização em lote; N escritores
  concorrentes em um singleton geram estado obsoleto, não estado rico.
