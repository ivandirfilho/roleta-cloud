# ADENDO ISO · SPR-ST1 · Trava de cobertura V5

- **Origem:** `SPR-ST1` (PR deste sprint).
- **Decisão:** `SDA_V5_COVERAGE_LOCK` é lida por chamada; vazia mantém o
  seletor V5 byte-idêntico, `17` fixa a cobertura 17 e `21` fixa a cobertura
  21. A indicação `APOSTAR`, stake e vetos INV-3 permanecem inalterados.
- **Observabilidade:** os contrafactuais `v5_would_hit_17/21` continuam sendo
  gravados. `tools/coverage_gate_report.py --db` agrega por janela, sentido e
  dealer e calcula `r`, `E[delta]=36r-4`, PnL sempre-17 versus atual e o
  veredito `ESCALADA_PAGA` somente para `r > 11,1pp`.
- **Ativação:** manter a flag vazia até janela shadow limpa de pelo menos três
  dias; `r < 11,1pp` sustentado mantém lock 17 ligado, enquanto
  `r >= 11,1pp` sustentado autoriza desligá-lo. A ativação será PR separado.
- **Rollback:** definir `SDA_V5_COVERAGE_LOCK=""` no host e redeploy, ou fazer
  revert do PR. Não há migração de schema.
- **ISO 25010/14764:** mudança reversível, leitura por chamada e relatório
  somente leitura preservam disponibilidade, auditabilidade e recuperação.
- **Replay envelope:** modelo `gpt-5.6-luna`; skills `sprint-executor`,
  `graphify-first`, `verification-before-completion`; duração e telemetria
  detalhadas ficam no registro da sessão.
