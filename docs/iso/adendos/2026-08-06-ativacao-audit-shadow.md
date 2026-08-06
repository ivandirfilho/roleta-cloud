# ADENDO 2026-08-06 — Ativação: SDA_PHASE_EVENT_AUDIT + SDA_DIRECTION_VISION_SHADOW

## O que muda
Defaults na compose: `SDA_PHASE_EVENT_AUDIT:-0 → :-1` e `SDA_DIRECTION_VISION_SHADOW:-0 → :-1`.

## Por quê
Ambas são **shadow-by-design** (comentários na própria compose: "sem efeito sobre o giro").
Auditam/observam sem alterar comportamento. Pela política do ciclo zero-humano
(adendo 2026-08-06-fluxo-zero-humano.md), flag shadow/audit ativa IMEDIATAMENTE via PR —
não vira pendência humana. Esta ativação **inicia o relógio de 7 dias** do gate T4
(coleta de phase_events em produção) e a validação shadow do direction-vision (V4).

## Segurança
- Sem efeito no giro/stake/indicação (INV-3 intacto).
- Rollback: exportar `SDA_PHASE_EVENT_AUDIT=0` / `SDA_DIRECTION_VISION_SHADOW=0` no host
  ou revert deste PR (~4 min até produção).

## Evidência esperada
Linhas em `phase_events` + logs `[direction-vision]` no serviço a partir do deploy pós-merge.
Verificação por agente: SPR-OBS-1 (endpoint de estado) tornará isso legível sem SSH.