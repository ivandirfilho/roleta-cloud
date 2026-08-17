# SPR-G7 — backtest de staking tiers, E7 e régua 17/21

## Escopo e dados

O leitor `tools/backtest_staking_tiers.py` abre SQLite com `mode=ro` e nunca
escreve no CSV. Cada entrada é contada antes da validação e cada descarte é
impresso como `SKIP` com motivo.

| Período | Entrada (`TOTAL`) | Processadas | Observação |
|---|---:|---:|---|
| 16/08 (`week_series.csv`) | 246 | 243 | 3 linhas corrompidas (traceback Python intercalado) |
| Junho (`decisions.db`) | 55 | 39 | 16 decisões pendentes, explicitamente `SKIP` |

O E7 está confirmado no histórico: `pnl_units` mistura P&L por unidade
(ex.: `1.1176` para 17 números) e total (ex.: `19.0`); `pnl_total(row)`
detecta a escala pela cobertura e pelo stake e converte somente o primeiro
caso. O ledger atual grava o stake efetivo em `gale_bet_value`; portanto o
backtest normaliza antes de multiplicar tiers.

## Resultado principal — todas as apostas válidas

`maxDD` é a maior queda a partir do pico; `ruin_bootstrap` é a fração de
1.000 reamostragens com DD >= 1.000u.

| Esquema | 16/08 PnL / DD / maxStake | Junho PnL / DD / maxStake |
|---|---:|---:|
| flat | +168.55 / 145.12 / 21 | +24.39 / 102.96 / 34 |
| 5×1→5×2→5×4 | +169.98 / 145.12 / 21 | +90.62 / 102.73 / 68 |
| 2×1→2×2→2×4 | +225.84 / 178.43 / 42 | +70.78 / 177.76 / 136 |
| ×2 pós-2 misses (teto ×2) | +224.13 / 178.40 / 42 | +6.31 / 139.76 / 68 |
| 1,2,4 cap2 (teto ×2) | **+295.42 / 228.29 / 42** | **+102.35 / 142.00 / 68** |
| 1,1,2,2,3 | +224.98 / 177.86 / 42 | +38.55 / 158.76 / 102 |

Todos os `ruin_bootstrap` foram `0.0000`; isso não elimina o risco
observacional. A pior sequência foi 5 misses em 16/08 e 7 no recorte de
junho.

## Recortes

No recorte cobertura-17, o flat foi `+247.41u / DD 99.76u` em 16/08 e
`-114.41u / DD 156.53u` em junho. O melhor tier (1,2,4 cap2) ficou
`+310.41u / DD 182.76u` e `-195.82u / DD 264.53u`, respectivamente. O
recorte móvel de dealer com HR prévia >55% teve 96 linhas em 16/08 e nenhuma
linha madura no histórico de junho; portanto não é evidência comparável.

As features `v5_would_hit_17` e `v5_would_hit_21` não existem no snapshot de
junho e não estão presentes no CSV; a régua contrafactual foi registrada como
`SKIP` por ausência de evidência, não como zero. Os dados observados ainda
confirmam o alerta: cobertura-17 foi positiva no dia 16/08, enquanto a régua
17/21 não pode ser inferida honestamente sem as features DNA.

## Recomendação

**Não adotar `GALE_TIERS` neste sprint.** O esquema 1,2,4 cap2 vence o flat em
PnL nos dois períodos, mas o DD de 16/08 é `228.29 / 145.12 = 1.574x`,
acima do limite fechado de `1.5x`. Como o critério exige vencer e respeitar o
limite nos dois períodos, a entrega fica em relatório + ferramenta + teste
E7. O comportamento de produção permanece flat-equivalente (`GALE_CAP=1`);
INV-3 não é alterado.

## Reprodução

```text
python tools/backtest_staking_tiers.py --csv <week_series.csv> --tiers "1,1,1,1,1,2,2,2,2,2,4,4,4,4,4"
```

