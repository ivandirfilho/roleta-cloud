# ADENDO — Ativação `SDA_V5_COVERAGE_LOCK=17` (trava de cobertura 17)

**Data:** 2026-08-16 · **PR:** `flag/ativar-coverage-lock-17` · **Tipo:** ativação de flag de
comportamento com janela shadow cumprida · **Código da flag:** PR #99 (SPR-ST1, já na main).

## O que muda
O seletor v5_1721 passa a jogar **sempre cobertura 17** por sentido (a escalada 17→21 do flip-puro
fica suspensa). Indicação `APOSTAR`, vetos de stake e INV-3 **inalterados** — só a cobertura.
Contrafactuais `v5_would_hit_17/21` **continuam logando** (são a validação contínua da própria trava).

## Evidência (janela shadow 04→17/08, 961 giros, payout normalizado 1u/número)

| Dia | n | PnL real | PnL sempre-17 | Δ |
|---|---|---|---|---|
| 04/08 | 3 | +17 | +21 | +4 |
| 05/08 | 278 | −230 | −118 | +112 |
| 06/08 | 398 | +270 | +290 | +20 |
| 16/08 | 203 | +397 | +473 | +76 |
| 17/08 | 79 | +73 | +97 | +24 |
| **Σ** | **961** | **+527** | **+763** | **+236** |

Sempre-17 dominou o seletor atual em **5/5 dias** (inclusive dia negativo e dia com r>11,1pp).
r médio dos 4 extras = 9,9% < breakeven 11,1pp (E[Δ]=36r−4). Pior streak de miss sempre-17 na
janela: 9 (1×) = −153u a stake 17u — 6× de folga na banca de referência (1.000u).
Fonte: probe read-only do DB de produção (`decisions` × `decision_dna`), 16/08 23:10 BRT;
metodologia em `plano_final_proposto.md` §1.

## Régua de desativação (contínua)
Rodar `tools/coverage_gate_report.py` (diário). **Desligar** (`SDA_V5_COVERAGE_LOCK=""` no host +
redeploy) se Δ contrafactual (sempre-17 − política-com-21) ficar **negativo por 3 dias corridos** —
sinal de regime onde a escalada voltou a pagar. r>11,1pp sustentado é diagnóstico de alerta.

## Rollback
`SDA_V5_COVERAGE_LOCK=""` no `.env` do host + redeploy (~3min) **ou** `git revert` deste PR
(deploy automático ~2min). Sem schema; sem estado persistido pela flag.

## Replay envelope
Modelo Diretor: claude-fable-5 (sessão "Resultados semana e sprints") · probes via SSH read-only
autorizado · ferramentas-chave: sqlite3 no container (read-only URI), decision_dna contrafactual ·
~6 turnos entre auditoria e ativação · execução da flag: edição direta das composes (2 defaults)
neste PR de ativação, código pré-existente do SPR-ST1.
