# ADENDO ISO — SPR-G7 staking tiers

- **Origem:** SPR-G7 (PR deste sprint).
- **Decisão:** normalizar E7 em leitor read-only, medir tiers em junho e
  16/08, e não introduzir `GALE_TIERS` porque o melhor esquema excedeu 1,5x do
  DD flat em 16/08.
- **Arquivos:** `tools/backtest_staking_tiers.py`,
  `tests/test_backtest_staking_tiers.py`,
  `docs/backtests/2026-08-16-staking-tiers.md`.
- **Flags:** nenhuma criada ou alterada; produção continua
  `GALE_CAP=1`/flat-equivalente.
- **INV-3:** não há supressão de indicação; nenhuma mudança de runtime foi
  entregue.
- **Rollback:** relatório e ferramenta são aditivos; remover o PR não altera
  produção. Se uma implementação futura nascer, deverá manter a flag vazia
  por default.
- **ISO 25010/14764:** reprodutibilidade (TOTAL conferido, SKIP explícito,
  bootstrap determinístico) e segurança operacional (SQLite `mode=ro`).
- **Replay envelope:** modelo gpt-5.6-luna; skills sprint-executor,
  graphify-first e verification-before-completion; duração aproximada de uma
  sessão de sprint.
