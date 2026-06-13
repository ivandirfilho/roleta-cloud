# Sprints Válidas — 12/06/2026 (implantação do Modelo Universal M5)

> Autorização do owner 21:39: "execute todas sem parar com todo ciclo necessário".
> Base de evidência: `analise_12_junho.md` §6 — replay causal 2.762 decisões/109
> sessões; M5 único modelo com saldo miss→hit positivo nos 4 quadrantes e aprovado
> no gate A4 (cw EV-flat −0.60→+0.21; ccw corta 77% da perda). Sem fase de shadow
> por decisão do owner ("não quero fazer testes") — o replay causal É a validação.

## Auditoria pré-implantação (10 pontos, ver memória/sequential-thinking)

| # | Risco verificado | Resolução de desenho |
|---|---|---|
| 1 | Integrador da EMA difere da simulação | Idêntico: prod já alimenta EMA com a aposta REAL (fix BUG-B) → erro residual pós-shift, como no M5 simulado ✓ |
| 2 | Shift vazar entre dealers | `_region_err_*` zera no `reset_adaptive` (B1) → shift renasce 0 (P10) ✓ |
| 3 | Shift no fallback N=21 | **Gate explícito**: só aplica no Triple Focus (3 centros) |
| 4 | Testes legados assumem sigmoid ON | Flags com default de PRODUÇÃO no código e default de SUITE no conftest (pattern PROFIT_CUT_V1) |
| 5 | Batch-tune tunando parâmetro morto | Skip com `action='sigmoid-off'` quando satélites OFF |
| 6 | QW-4 hot-substitution interage com offsets fixos | Com sigmoid OFF retorna offset base (sem substituição) |
| 7 | QW-7 freeze congelaria o M5 | M5 NÃO participa do freeze (α=0.2 já é lento; modelo vencedor não tinha freeze) |
| 8 | Rollback | `_sigmoid_off` segue persistido; religar `SDA_SIGMOID_SATELLITES=1` restaura comportamento anterior |
| 9 | Overlay/extension quebrar com campo novo | `region_bias` é additive (extension ignora desconhecidos — mesmo pattern dealer/round_id) |
| 10 | Downstream (ledger/DNA/atribuição) | Shift ocorre ANTES do `store_prediction` → numbers/centers gravados = aposta real; pipeline B2 intacto |

## SV-01 — Atuador M5: `REGION_SHIFT_V1` (default ON em prod)
- `sda17.analyze` (Triple Focus apenas): `shift = clamp(round(−ema_c1·0.5), ±4)` com
  `n_c1 ≥ 3` no sentido → desloca o índice de C1 ANTES de posicionar C2/C3;
  satélites: correção relativa `clamp(round(−ema_c2·0.5), ±2)` em off2 (análogo, sinal
  oposto, em off3) com `n ≥ 3`.
- Parâmetros: `REGION_SHIFT_K=0.5`, `REGION_SHIFT_CLAMP_C1=4`, `_SAT=2`,
  `REGION_SHIFT_MIN_N=3` (constantes de classe; flag por env).
- Detalhe `details["region_shift"]` para rastreabilidade por decisão.

## SV-02 — Aposentar sigmoid dos satélites (default OFF em prod)
- Flag `SDA_SIGMOID_SATELLITES` (default OFF): `_get_adaptive_offset` retorna prior
  fixo (10/10); `_pct_sigmoid_update` pula passos 5-6 (freeze/adaptação) e o
  regularizador; QW-4 substituição desativada; batch-tune vira no-op rotulado.
- Continuam ATIVOS: EMA por região (insumo do M5), `_recent_hits` (QW-1/2/6),
  histórico, telemetria. Suite legada roda com flag ON via conftest.

## SV-03 — Regime de viés visível
- Alerta `RoletaRegionBiasHigh`: `abs(roleta_region_err_ema{region="C1"}) > 4` AND
  `roleta_region_err_n ≥ 10` (novo gauge de n), for 5m, severity warning —
  anotação sugere reset de sessão (P10).
- Overlay: campo `region_bias: {dir, ema_c1, n, shift_aplicado}` no payload
  `sugestao` (additive).

## SV-04 — Ciclo completo
- Testes novos (`tests/test_sv_m5_12_06.py`): shift aplicado/clampado/gated;
  fallback sem shift; sigmoid OFF congela offsets no prior; reset zera shift;
  rollback flag; suite inteira verde + lint baseline.
- Commit → push → CI verde → pull-deploy → validação em prod (health, /metrics com
  novo gauge, /api/strategy com shift, latência <500ms).

## Critérios de aceitação (pós-deploy)
1. `/api/strategy` expõe `region_shift` por sentido; decisões novas com
   `details.region_shift` ≠ 0 quando |ema|≥2 e n≥3.
2. `sigmoid_off` congelado no prior (10/10) nas decisões novas.
3. 16+1 rules no Prometheus (`RoletaRegionBiasHigh` carregada).
4. Latência de spin ≤ 500ms (sem regressão do caminho crítico).
5. Suite 387+ e CI verdes.
