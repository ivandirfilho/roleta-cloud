# SPR-ST1 · Trava de cobertura 17 (flag shadow-validada) + gate empírico da escalada-21 · Bloco BLK-G · Pri P1

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> **SDD: este brief É a spec.** Decisões FECHADAS não se reabrem; ambiguidade real → 1 pergunta ao Diretor.

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []
locks:      [BLK-G, settings, compose]    # BLK-G serializa (G7 já liberou)
touches:    [strategies/, app_config/settings.py, docker-compose.yml,
             deploy/azure/compose.azure.yml, tools/, tests/, docs/iso/adendos/]
base_sha:   origin/main
branch:     spr/SPR-ST1 (brief publicado); executor trabalha no branch da sessão, PR base main
modelo:     gpt-5.6-luna
timebox:    60min
```

## Objetivo (1 frase)
A escalada 17→21 do seletor v5 está DESTRUINDO lucro no regime atual (contrafactual: sempre-17
= +564u vs seletor atual +476u no dia 16/08, payout normalizado) — criar a trava de cobertura 17
atrás de flag default-OFF e a régua empírica que decide QUANDO a 21 volta a valer.

## Contexto factual (probe read-only do Diretor, 16/08 22:30 — 276 giros resolvidos)
- Payout verdadeiro (1u/número): 17# → +19/−17 · 21# → +15/−21.
- PnL real normalizado do dia: **+476u** (cov17 +560u em 164 giros; cov21 **−84u** em 112 giros).
- Contrafactuais `v5_would_hit_17`/`v5_would_hit_21` (DNA, 0 nulos): sempre-17 **+564u**;
  sempre-21 +396u; default-17-com-21-pós-miss +444u.
- Regra da spec 03/08 (`estrategia_proposta_03_08.md`): escalada paga se r (extras pegam) > 11,1pp
  (E[Δ]=36r−4). **Medido: r = 26/276 = 9,4%** → escalada NÃO paga neste regime. A régua deve ser
  CONTÍNUA, não fixa: se r subir de forma sustentada, a 21 volta.
- E7 confirmado: `pnl_units` mistura escalas; usar normalização do G7 (`tools/backtest_staking_tiers.py`).

## Âncoras (onde entrar — NÃO faça grep cego)
- `strategies/` — composer/seletor v5_1721 (grep `v5_coverage_mode`, `SDA_V5_FLIP_PURO`,
  `would_hit_17`): é ali que a cobertura 17/21 é escolhida por sentido.
- `app_config/settings.py` — padrão de leitura por-chamada de flags.
- `docker-compose.yml` — bloco das flags V5 (onde a nova flag nasce, com comentário completo).
- `database/dna_logger.py` — features `v5_would_hit_17/21` (JÁ existem — não duplicar).
- `tests/` — testes existentes do seletor (grep `flip_puro`, `v5_1721`, `coverage`).

## Tarefa (passos)
1. **Flag `SDA_V5_COVERAGE_LOCK`** (string, default **vazia = OFF**, leitura por-chamada):
   - `""`/ausente → comportamento atual intacto (byte-idêntico).
   - `"17"` → cobertura SEMPRE 17 por sentido (seletor não escala p/ 21). `"21"` → sempre 21
     (simetria barata p/ teste A/B futuro).
   - INV-3 intacto: só a COBERTURA muda; indicação `APOSTAR` e vetos de stake não são tocados.
   - Contrafactuais continuam logando SEMPRE (são a validação contínua da própria trava).
2. Compose: flag nova com comentário (contexto: contrafactual 16/08, r=9,4% < 11,1pp; rollback
   `=""` + redeploy) + **espelho Azure no MESMO PR**.
3. **Régua empírica**: `tools/coverage_gate_report.py` (read-only, `--db`) que imprime por
   janela/sentido/dealer: r dos extras (P(21 pega ∧ 17 não)), E[Δ]=36r−4, PnL contrafactual
   sempre-17 vs atual, e veredito `ESCALADA_PAGA`/`NAO_PAGA` com `TOTAL n` conferido (anti-skip,
   lição PR #82). É este relatório que autoriza (des)ligar a trava daqui pra frente.
4. Testes: unit da flag (lock 17 força cobertura 17; vazia = seleção atual; INV-3 preservado) +
   teste do report com fixture pequena.
5. NÃO ativar a flag neste sprint (é flag de comportamento — ativação é PR separado
   `flag/ativar-coverage-lock-17` que o Diretor abre com a janela shadow: os contrafactuais de
   ≥3 dias contínuos mantendo r<11,1pp).

## FECHADAS (não reabrir)
- INV-3 · flag default-OFF (vazia) · migração NENHUMA · contrafactuais intocados ·
  sem SSH/produção · PR base `main` + auto-merge · ADENDO como arquivo novo.

## Critério de "pronto" (DoD)
- [ ] Flag nas DUAS composes (paridade `pytest tests/test_azure_pre_cutover.py` verde).
- [ ] Com flag vazia: suíte inteira verde SEM ajustar testes existentes (prova de byte-idêntico).
- [ ] `tools/coverage_gate_report.py` com `TOTAL n` e veredito; teste com fixture.
- [ ] ADENDO novo em `docs/iso/adendos/` com a régua de ativação (r<11,1pp sustentado ⇒ lock ON;
      r≥11,1pp sustentado ⇒ lock OFF).

## Validação (rode e cole no Log)
```
pytest tests/test_azure_pre_cutover.py -q
pytest tests/ -q --ignore=tests/test_obs_reload.py
python tools/coverage_gate_report.py --help
```

## Rollback (ISO)
Flag `SDA_V5_COVERAGE_LOCK=""` no host + redeploy (~3min) ou `git revert`. Sem schema.

## Closeout (ordem)
Validação → ADENDO → code-review → Log → commit `SPR-ST1: ...` (+trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`) → push → **PR base `main`**
(conferir `baseRefName==main`; ANTES do PR: `git fetch origin; git merge origin/main` e no conflito
add/add de `sprints/SPR-ST1.md` manter a SUA versão com Log) → título `SPR-ST1:` → auto-merge
(`gh pr merge --auto --squash <nº>`) → avisar o Diretor com nº do PR.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
