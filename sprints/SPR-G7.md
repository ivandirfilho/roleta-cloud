# SPR-G7 · Staking multi-tier (martingale adaptativo) — backtest honesto + régua 17/21 + E7 · Bloco BLK-G · Pri P1

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> **SDD: este brief É a spec.** Decisões FECHADAS não se reabrem; ambiguidade real → 1 pergunta ao Diretor.

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []
locks:      [BLK-G, staking, compose]     # BLK-G serializa: NÃO abrir em paralelo com S1/S2/T1/T2
touches:    [tools/, staking/block_gale.py, app_config/settings.py, docker-compose.yml,
             deploy/azure/compose.azure.yml, docs/backtests/, tests/]
base_sha:   origin/main
branch:     spr/SPR-G7 (brief publicado); executor trabalha no branch da sessão, PR base main
modelo:     gpt-5.6-luna
timebox:    75min
```

## Setup
Sessão/worktree própria a partir de `spr/SPR-G7`. `git status` limpo antes de começar.

## Objetivo (1 frase)
Decidir COM DADOS se escalada de stake (martingale adaptativo) melhora o lucro sem risco de ruína —
e, no caminho, corrigir a leitura de `pnl_units` (E7) e auditar a régua 17/21 que queimou lucro.

## Contexto factual (probe + simulação do Diretor, 16/08 — `resultados_semana_10_08_16_08.md` §6-7)
- Dia 16/08 real: 243 resolvidas, HR 56,8%, flat +168,6u. Cobertura-17: +247,4u (HR 55,2%);
  cobertura-21: **−78,9u** (HR 59,2%, breakeven 58,3% — no fio). Streak máx de derrotas = 5.
- Sims do Diretor na série real: blocos do dono (5×1→5×2→5×4) ≈ flat (só engaja no 6º miss);
  ×2 pós-2-misses teto ×2 → +224u (maxDD −178); 1-2-4 cap2 → +407u (maxDD −315);
  ×2 clássico teto 5 → +431u (maxDD −377). Multiplicador amplifica os DOIS lados.
- **E7 (bug de leitura):** `decisions.pnl_units` mistura escala POR-UNIDADE (+1,12/−1,0) e TOTAL
  (+19/−17) entre linhas. Todo backtest tem de normalizar primeiro.
- Histórico (junho, mesmas jogadas): gale clássico −77u vs flat +99u — gale só sangra em regime ruim.

## Âncoras (onde entrar — NÃO faça grep cego)
- `staking/block_gale.py` — motor de staking atual (`GALE_CAP=1` = flat-equivalente; solvency guard
  com `GALE_BANKROLL`).
- `app_config/settings.py` — padrão de leitura por-chamada de flags.
- `tools/backtest_from_db.py` — leitor de `decisions` existente (replay determinístico).
- `database/sqlite_repo.py` + `server/message_handler.py` — onde `pnl_units` é calculado/gravado
  (raiz do E7: descobrir QUANDO grava por-unidade vs total; documentar a regra de normalização).
- Dados read-only para o backtest (NUNCA escrever nesses caminhos):
  a) `C:\Users\Windows\Desktop\Roleta Cloud\data\decisions.db` — histórico até 25/06 (cópia local);
  b) `C:\Users\Windows\.copilot\session-state\d67daa01-a502-4997-ae18-98a3249f15d9\files\week_series.csv`
     — série real de 16/08 (243 linhas: id|ts|hit|pnl|cobertura|stake|dealer|sentido).
- `decision_dna` (features `v5_would_hit_17`/`v5_would_hit_21`) — contrafactuais p/ a régua 17/21.

## Tarefa (passos)
1. **E7:** ler o código de gravação de `pnl_units` e escrever a função de normalização
   (`pnl_total(row)`) com teste unitário provando as duas escalas. Documentar a causa no relatório.
2. Criar `tools/backtest_staking_tiers.py` (novo, standalone, read-only): recebe `--db <path>` e/ou
   `--csv <path>`, aplica esquemas de tier (`--tiers "1,1,2,2,3"` etc.) e recortes
   (`--por dealer|sentido|cobertura`), e imprime PnL, maxStake, maxDD, risco-num-run e **`TOTAL n`
   conferido contra o nº de linhas de entrada** (lição PR #82: pulo silencioso é mentira — linha
   descartada = `SKIP` explícito com motivo).
3. Rodar sobre (a) histórico jun + (b) série 16/08, esquemas mínimos: flat; blocos do dono
   `5×1→5×2→5×4`; blocos curtos `2×1→2×2→2×4`; `x2-pós-2-misses` teto ×2; `1,2,4` cap2; escada
   `1,1,2,2,3`; cada um também restrito a cobertura-17 e a dealers HR>55% (janela móvel, sem lookahead).
4. **Régua 17/21:** com `v5_would_hit_17/21` do DNA (ou recomputando do histórico), medir o PnL
   contrafactual "sempre-17" vs "flip-puro atual" vs "17-exceto-pós-2-misses". Relatar.
5. Relatório `docs/backtests/2026-08-16-staking-tiers.md`: tabelas por esquema × recorte × período,
   metodologia E7, risco de ruína (pior sequência observada + bootstrap simples de 1.000 reamostras),
   e RECOMENDAÇÃO explícita (adotar/não adotar; qual esquema; com que teto).
6. **Somente se** um esquema vencer o flat em PnL com maxDD ≤ 1,5× do flat nos DOIS períodos:
   implementar `GALE_TIERS` (env string, ex.: `"1,1,2,2,3"`; vazia = comportamento atual cap 1) em
   `staking/block_gale.py`, leitura por-chamada, **default vazio (OFF)** na compose + espelho Azure
   no MESMO PR + testes. Senão: entregar só relatório + recomendação (também é entrega válida).

## FECHADAS (não reabrir)
- **INV-3:** tiers modulam STAKE; a indicação `APOSTAR` nunca é suprimida.
- Solvency guard permanece: stake escalado passa pelo `min()` com a banca (`GALE_BANKROLL`).
- Nenhuma mudança de comportamento nasce ligada: `GALE_TIERS` default vazio; ligar é PR futuro.
- Sem SSH/produção; bancos citados são cópias locais READ-ONLY.

## Critério de "pronto" (DoD)
- [ ] Relatório em `docs/backtests/` com `TOTAL n` batendo e recomendação explícita.
- [ ] Teste unitário da normalização E7.
- [ ] Se implementou `GALE_TIERS`: flag default-OFF nas DUAS composes + testes de tier + paridade
      Azure verde; suíte completa verde.

## Guardrails (inviolável)
Template padrão: flags default-OFF na compose; migração NENHUMA; sem comando destrutivo; worktree
próprio; PR base `main` + auto-merge; NUNCA tocar `Manutenabilidade_iso.md`.

## Validação (rode e cole no Log)
```
python tools/backtest_staking_tiers.py --csv <artefato week_series.csv> --tiers "1,1,1,1,1,2,2,2,2,2,4,4,4,4,4"
pytest tests/ -q --ignore=tests/test_obs_reload.py
```

## Rollback (ISO)
Relatório = sem rollback. `GALE_TIERS` (se nascer) = flag vazia por default; rollback = manter vazia
ou `git revert`.

## Conformidade ISO (antes do PR)
- [ ] Flag na compose (se houver código) · [ ] INV-3 · [ ] suíte verde · [ ] lint silent-except se novo `except`.

## Closeout (ordem)
Validação → ADENDO novo `docs/iso/adendos/` → code-review → Log → commit `SPR-G7: ...` (+trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`) → push → **PR base `main`**
título `SPR-G7:` → auto-merge → avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
2026-08-16 · DONE · E7 normalizado; ferramenta read-only e relatório executados em 246 linhas do CSV (243 válidas) e 55 decisões do DB (39 resolvidas); nenhum tier passou o limite DD≤1,5x nos dois períodos · `pytest tests/test_backtest_staking_tiers.py -q` (4 passed), comando de validação do brief · `tools/backtest_staking_tiers.py`, `tests/test_backtest_staking_tiers.py`, `docs/backtests/2026-08-16-staking-tiers.md`, ADENDO ISO
