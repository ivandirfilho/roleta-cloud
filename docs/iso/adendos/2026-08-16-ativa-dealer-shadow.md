# ADENDO ISO — SPR-ML1: dealer shadow ativo

## Origem

- Sprint: `SPR-ML1`
- Data: 2026-08-16
- Escopo: ativação shadow do Error Engine e do R2 dealer-aware.

## Decisão e impacto

Os defaults de `SDA_ERROR_ENGINE` e `SDA_R2_DEALER_SHADOW` foram ligados (`:-1}`)
nas composes HostDime e Azure após a análise semanal do dealer. A resolução passa a
classificar o erro e medir o R2 por dealer/sentido no `decision_dna`. O modo live
(`SDA_R2_DEALER`) permanece desligado.

Shadow é telemetria e aprendizado contrafactual: não altera indicação, cobertura
ou stake, preservando o INV-3.

## Rollback

Definir `SDA_ERROR_ENGINE=0` e `SDA_R2_DEALER_SHADOW=0` no ambiente e recriar os
containers, ou reverter o PR. Não há alteração de schema.

## Conformidade ISO

- Leitura das flags continua por chamada.
- Paridade entre as composes foi mantida.
- O funil local foi coberto por teste: `error_class`, `r2_source` e
  `r2_signed_err` são gravados no DNA.

## Replay envelope

- Modelo: gpt-5.6-luna.
- Skills/MCPs: kickoff, graphify-first, ferramentas nativas de leitura/edição.
- Turnos: aproximadamente 8; duração: aproximadamente 15 minutos.
