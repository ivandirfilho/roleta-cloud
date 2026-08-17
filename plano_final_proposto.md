# Plano final proposto — 16/08 (pós-auditoria)

> **Autor:** Diretor de Sprints · **Método:** auditoria dos meus próprios documentos
> (`resultados_semana_10_08_16_08.md` + `proposta_16_08.md`) contra um SEGUNDO probe read-only de
> produção (961 giros com contrafactual completo, dealers com n≥30 histórico, env pós-deploy).
> **Regra deste plano:** só entra em "IMEDIATO" o que tem validação empírica JÁ CUMPRIDA pela
> governança (janela shadow registrada) e reversão em minutos. O resto fica gateado.

---

## 1. Auditoria: 3 erros e 1 melhoria encontrados nos planos anteriores

### ERRO 1 (o mais importante) — "esperar 3 dias" era desnecessário: a janela JÁ ESTÁ CUMPRIDA
O plano anterior mandava ativar o coverage-lock só após "≥3 dias de contrafactual limpo", como se a
medição começasse agora. **Falso:** as features `v5_would_hit_17/21` logam desde **04/08** (go-live
do v5). A janela shadow, medida com payout normalizado (17#: +19/−17 · 21#: +15/−21):

| Dia | n | r extras | PnL real | PnL sempre-17 | Δ (sempre-17 − real) |
|---|---|---|---|---|---|
| 04/08 | 3 | 0,0% | +17 | +21 | +4 |
| 05/08 | 278 | 9,0% | −230 | −118 | **+112** |
| 06/08 | 398 | 10,8% | +270 | +290 | +20 |
| 16/08 | 203 | 8,4% | +397 | +473 | **+76** |
| 17/08* | 79 | 12,7% | +73 | +97 | +24 |
| **Total** | **961** | **9,9%** | **+527** | **+763** | **+236** |

*madrugada UTC. **Sempre-17 venceu ou empatou o seletor atual em 5 de 5 dias** — inclusive no dia
RUIM (05/08: perderia 112u a menos) e no dia com r acima do breakeven (17/08: ainda +24). A régua
de 3 dias que eu mesmo propus está cumprida com folga → **ativação imediata é legítima**.

### ERRO 2 — o "dealer quente" do dia era ruído; o sinal robusto é o dealer FRIO
`proposta_16_08` sugeria stake maior em STEPHEN/DIEGO (70%/62% no dia, n=24/21). No histórico com
n≥30, **STEPHEN cai para 50,9%/45,5%** — o recorte de 1 dia era variância. O que sobrevive ao n:

| Sinal robusto | n | HR | PnL normalizado |
|---|---|---|---|
| **ELINE (2 sentidos)** | **302** | **40,7% / 39,5%** | **−627u** |
| OLIVER×horário | 46 | 34,8% | −136u |
| JONES×horário | 43 | 32,6% | −135u |
| CARLOS×horário | 41 | 39,0% | −221u |
| THEO (2 sentidos) | 124 | 60,7% / 55,6% | +415u |

Conclusão invertida: a alavanca não é "apostar mais nos quentes" (ruído), é **reduzir stake nos
comprovadamente frios** — e ELINE é o único com n grande E consistência nos dois sentidos.

### ERRO 3 — o upside anunciado estava otimista
"+88u/dia" era o recorte de 16/08. A média honesta da janela completa é **+47u/dia** (236u/5 dias)
— e com a ressalva de que o lock **não torna dia ruim em dia bom** (05/08 seguiria negativo), ele
apenas **domina o seletor atual em todos os regimes observados**.

### MELHORIA 4 — a régua de ativação/desativação certa é o Δ, não só o r
O breakeven r>11,1pp é a régua da spec por-giro-de-escalada, mas 17/08 mostrou r=12,7% com Δ ainda
positivo (o seletor não escala em todo giro). A régua operacional do
`tools/coverage_gate_report.py` deve ser o **Δ contrafactual direto** (PnL sempre-17 − PnL real da
política ativa), com r como diagnóstico secundário. Desligar o lock exige Δ<0 sustentado ≥3 dias.

---

## 2. IMPLANTAÇÃO IMEDIATA (sem shadow adicional — a validação já existe)

### 2.1 ✅ ATIVAR `SDA_V5_COVERAGE_LOCK=17` — **executado neste ciclo**
- **O quê:** default `:-}` → `:-17}` nas duas composes (PR `flag/ativar-coverage-lock-17`,
  auto-merge; deploy ~2min; código do lock já estava na main pelo #99).
- **Por que é legítimo sem shadow novo:** a governança pede "flag de comportamento liga após
  janela shadow limpa registrada em adendo" — a janela É a tabela do §1 (5 dias, 961 giros,
  5/5 positivos), registrada no adendo de ativação.
- **Lucro esperado se o comportamento se mantiver:** +47u/dia sobre o seletor atual (média da
  janela; range observado +4 a +112). Em dias como 16/08: PnL absoluto ~+473u/dia.
- **Risco e reversão:** pior streak de miss na visão sempre-17 em 961 giros = 9 seguidos
  (1 ocorrência) = −153u com stake 17u ⇒ banca de referência 1.000u aguenta 6× o pior caso.
  Rollback: `SDA_V5_COVERAGE_LOCK=""` no host + redeploy (~3min) ou revert do PR.
- **Validação contínua embutida:** os contrafactuais continuam logando com o lock ativo; o
  `coverage_gate_report.py` (régua do §1.4) roda diariamente e manda desligar se Δ<0 por 3 dias.

### 2.2 O que fica de guarda no mesmo movimento (sem custo novo)
- `SDA_ERROR_ENGINE=1` + `SDA_R2_DEALER_SHADOW=1` **já ativos** (deploy do #93 confirmado no env)
  → o funil dealer×sentido começou a encher HOJE; é ele que gradua o passo 3.1.

## 3. FILA GATEADA (lucro adicional, mas SÓ com o gate batido)

| # | Ação | Upside estimado | Gate objetivo | Dono |
|---|---|---|---|---|
| 3.1 | **Stake-floor em dealer frio** (ELINE: stake×0,25 via `min()` INV-3, flag `SDA_DEALER_STAKE_VETO` default-OFF) | histórico: ELINE custou −627u/302 giros; floor 0,25 economizaria ~470u | shadow do #93 confirmar HR<45% de ELINE com n≥50 novos giros (≈1 semana) | sprint novo (BLK-G) |
| 3.2 | **R2 dealer-aware LIVE** (`SDA_R2_DEALER=1`) | bandit escolhe centro por dealer×sentido | funil `r2_source` populado + would-hit ≥ baseline por ≥7d no shadow | PR de ativação |
| 3.3 | **Gate temporal anti-fantasma** (`SDA_MIN_SPIN_INTERVAL_MS=15000`) | elimina flips de fase por giro impossível | **Reload da extensão 3.11.0 no Chrome (única ação humana)** | PR de ativação |
| 3.4 | **Re-teste multi-tier/martingale** | G7 reprovou (maxDD 1,574×>1,5×); redistribuição pós-lock pode mudar o veredito | ≥2 semanas de povoamento contínuo COM lock=17 (a distribuição muda; recalibrar sobre ela) | `backtest_staking_tiers.py` |
| 3.5 | **SPR-REL1** — relatório diário automatizado (Δ contrafactual + funil dealer + PnL) | tira o Diretor do loop manual | brief a escrever | sprint novo |

**O que segue PROIBIDO de ligar** (auditoria mantém): martingale em produção (reprovado por
drawdown), `SDA_DIRECTION_VISION` (fail-close até V7/auth), dual-write/cutover Azure (freeze formal).

## 4. Projeção consolidada (se os comportamentos da janela se mantiverem)

| Cenário/dia típico (~200-280 giros resolvidos) | PnL esperado |
|---|---|
| Seletor atual (antes deste plano) | referência (ex.: 16/08 = +397u) |
| **+ lock-17 (2.1, ATIVO agora)** | **+47u/dia sobre a referência** (5/5 dias dominante) |
| + stake-floor ELINE (3.1, ~1 semana) | +30 a 60u/dia adicionais quando ELINE está na mesa |
| + R2 dealer live (3.2, ~1-2 semanas) | a medir no shadow (sem número honesto ainda) |

Honestidade estatística: 961 giros ≈ 4 dias efetivos de operação. O lock-17 é a única mudança com
dominância consistente em TODOS os regimes observados — por isso é a única que entra sem gate
adicional. Dias negativos continuarão existindo (05/08 teria sido −118u mesmo com lock); o plano
otimiza a esperança e o controle de dano, não elimina variância de roleta.

## 5. Registro de execução deste plano

- [x] Auditoria com segundo probe (961 giros, dealers n≥30, env) — este documento §1.
- [x] PR `flag/ativar-coverage-lock-17` (composes + adendo com a janela) — auto-merge armado.
- [x] Adendo ISO: `docs/iso/adendos/2026-08-16-ativa-coverage-lock-17.md`.
- [x] Board: relógio `ativado_coverage_lock` registrado no lote.
- [ ] D+1: rodar `coverage_gate_report.py` e colar o Δ do primeiro dia com lock ativo.
- [ ] D+7: decisão 3.1 (ELINE) com o funil do shadow.
