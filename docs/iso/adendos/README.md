# ADENDOs ISO — um arquivo por sprint/mudança

## Por que esta pasta existe

Até 06/08/2026 todo ADENDO era **apendado ao fim de `Manutenabilidade_iso.md`**
(singleton de >300 KB). Com múltiplos executores em paralelo isso virou o maior
ímã de conflito do repo: 3 dos 4 PRs abertos em 06/08 tocavam o mesmo arquivo,
ADENDOs do mesmo dia acabaram espalhados em 4 posições diferentes do documento
e houve até título duplicado ("ADENDO 05/08/2026 (noite-2)" duas vezes).

**Novo contrato:** cada ADENDO é um **arquivo próprio** nesta pasta. Arquivos
novos nunca conflitam entre si — N executores podem trabalhar em paralelo sem
serializar no documento-mãe.

## Convenção

- **Nome:** `AAAA-MM-DD-<slug>.md` (data de abertura do PR + slug curto do tema).
  Ex.: `2026-08-06-governanca-fluxo-pr.md`.
- **Conteúdo mínimo** (mesmo espírito do ADENDO clássico):
  1. Sprint/PR de origem (`SPR-XXX`, nº do PR).
  2. O que mudou e por quê (decisão, não diff).
  3. Flags criadas/alteradas e default.
  4. Como reverter (flag OFF / revert do PR).
  5. Lições ISO 25010/14764 se houver.
  6. **Replay envelope** (D7 do blueprint): modelo(s) usados, skills/MCPs-chave,
     nº de turnos aprox e duração — rastro fino fica em `~/.copilot/telemetry/events.ndjson`.
- `Manutenabilidade_iso.md` **continua valendo** como corpo histórico e
  arquitetural — só não recebe mais ADENDOs incrementais por append. Um
  ponteiro no fim dele aponta para cá.
- O guardrail de CI (`iso-guardrails.yml`) aceita mudança de comportamento
  acompanhada de arquivo aqui **ou** edição no documento-mãe.

## Índice

| Data | Arquivo | Origem |
|---|---|---|
| 2026-08-06 | `2026-08-06-governanca-fluxo-pr.md` | Diagnóstico de silos de PR (sessão fix-fluxo-ci-governanca) |
| 2026-08-06 | `2026-08-06-fluxo-zero-humano.md` | Auto-merge + ativação por PR + main-red (mesma sessão, noite) |
| 2026-08-06 | `2026-08-06-ativacao-audit-shadow.md` | PR #63 — flags `SDA_..._AUDIT`/`_SHADOW` ligadas em produção |
| 2026-08-07 | `2026-08-07-instrucoes-nativas-camadas.md` | Auditoria pós-esteira: `AGENTS.md` raiz, header do singleton, lições #58/#43/#64 |
| 2026-08-16 | `2026-08-16-racetrack-guia-overlay.md` | SPR-X5 — roletinha guia (racetrack) no overlay minimizado da Escuta Beat (ext. 3.11.0) |
| 2026-08-16 | `2026-08-16-diagnostico-502-self-heal.md` | SPR-D1 — incidente 502 no `/ws`: `/health` no nginx + self-heal do tick NOOP |
| 2026-08-16 | `2026-08-16-ultima-milha-deploy.md` | SPR-D2 — "mergeou ≠ implantado": shim de deploy auto-sincronizado + instalação do `roleta.conf` |
