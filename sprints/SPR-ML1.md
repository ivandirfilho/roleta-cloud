# SPR-ML1 · Assinatura do dealer entra no loop de IA/ML (shadow) · Bloco BLK-G(borda)/compose · Pri P1

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> **SDD: este brief É a spec.** Decisões FECHADAS não se reabrem; ambiguidade real → 1 pergunta ao Diretor.

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []
locks:      [compose, settings]
touches:    [docker-compose.yml, deploy/azure/compose.azure.yml, docs/iso/adendos/, tests/]
base_sha:   origin/main
branch:     spr/SPR-ML1 (brief publicado); executor trabalha no branch da própria sessão, PR base main
modelo:     gpt-5.6-luna
timebox:    45min
```

## Setup
Você já está numa sessão/worktree própria criada a partir de `spr/SPR-ML1` (o brief está no repo).
Confirme `git status` limpo antes de começar. NUNCA trabalhe no checkout principal.

## Objetivo (1 frase)
O dealer é coletado em 100% das jogadas (OCR + fill-forward) mas está **fora** do loop de ML
(flags OFF, DNA sem feature de dealer): ligar a camada **shadow** (zero efeito em aposta) para a
assinatura do dealer começar a ser validada com dados reais.

## Contexto factual (probe de produção 16/08, Diretor)
- Env real do container: `SDA_ERROR_ENGINE=0`, `SDA_R2_DEALER_SHADOW=0`, `SDA_R2_DEALER=0`,
  `SDA_DEALER_FORCE_PROFILE=0`. Dealer povoado: `cw.spin_features` 3.599/3.599, `ccw` 3.349/3.349.
- Recorte do dia 16/08 (n≥15): STEPHEN×horário HR 70,8% (+127,1u), STEPHEN×anti 65,2% (+121,5u),
  DIEGO +103,6u; JESSICA/VICTORIA/ELINE negativos. O dado separa; ninguém consome.
- Política de ativação (AGENTS.md §2.8): flag **shadow/audit liga imediatamente** via PR mudando o
  default na compose + adendo. É exatamente este sprint.

## Âncoras (onde entrar — NÃO faça grep cego)
- `docker-compose.yml` — bloco "R2 dealer-aware + Error Engine (05/08 noite-2)": flags
  `SDA_ERROR_ENGINE` e `SDA_R2_DEALER_SHADOW` (defaults `:-0}` → mudar para `:-1}`).
- `deploy/azure/compose.azure.yml` — espelho OBRIGATÓRIO no MESMO PR (contrato
  `tests/test_azure_pre_cutover.py` falha se divergir).
- `app_config/settings.py` — leitura por-chamada das flags (não mexer na semântica).
- `strategies/sda17.py` + `database/dna_logger.py` — funil shadow: confirmar que com as flags ON os
  campos `error_class` / `r2_source` / `r2_signed_err` passam a ser gravados no `decision_dna`.
- `tests/` — procurar testes existentes de error engine / r2 shadow (grep `SDA_ERROR_ENGINE`,
  `r2_source`, `R2_DEALER_SHADOW`) e mantê-los verdes com os novos defaults.

## Tarefa (passos)
1. Mudar defaults na compose: `SDA_ERROR_ENGINE=${SDA_ERROR_ENGINE:-1}` e
   `SDA_R2_DEALER_SHADOW=${SDA_R2_DEALER_SHADOW:-1}`; atualizar os comentários das flags (dizer que
   shadow ligou em 16/08 por decisão do Diretor pós-análise `resultados_semana_10_08_16_08.md`,
   rollback = `=0` + redeploy).
2. Espelhar exatamente no `deploy/azure/compose.azure.yml`.
3. Validar o funil em teste local (unit/integração existente ou novo teste pequeno): com as flags ON,
   uma decisão resolvida produz DNA com `r2_source` e classificação `error_class` (usar harness de
   testes local; **nenhum** acesso a produção).
4. Se algum teste asserta default OFF, ajustar o teste ao novo default (documentar no Log).

## FECHADAS (não reabrir)
- **NÃO** ligar `SDA_R2_DEALER` (live) nem `SDA_DEALER_FORCE_PROFILE` — fora de escopo; o live só
  entra depois de janela shadow limpa registrada em adendo.
- Shadow não muda aposta: qualquer diff em stake/indicação é BUG — abortar e reportar.

## Critério de "pronto" (DoD)
- [ ] Defaults `:-1}` nas DUAS composes (paridade Azure verde: `pytest tests/test_azure_pre_cutover.py`).
- [ ] Teste cobrindo o funil shadow (DNA ganha `r2_source`/`error_class` com flag ON).
- [ ] Suíte completa verde (`pytest tests/` — no Windows local: `--ignore=tests/test_obs_reload.py`).
- [ ] ADENDO novo em `docs/iso/adendos/2026-08-16-ativa-dealer-shadow.md` (ou data corrente).

## Guardrails (inviolável)
- **INV-3** intacto (shadow = zero efeito em indicação/stake).
- Leitura por-chamada; nada hardcoded; migração NENHUMA (não é necessária).
- Sem SSH/host; testes só em DB local/teste. Working tree sujo no início = abortar.

## Validação (rode e cole no Log)
```
pytest tests/test_azure_pre_cutover.py -q
pytest tests/ -q --ignore=tests/test_obs_reload.py -k "error_engine or r2 or dealer or dna"
pytest tests/ -q --ignore=tests/test_obs_reload.py
```

## Rollback (ISO)
`SDA_ERROR_ENGINE=0` + `SDA_R2_DEALER_SHADOW=0` no `.env` do host + redeploy (~3min), ou
`git revert` do PR. Sem schema envolvido.

## Conformidade ISO (antes do PR)
- [ ] Flags na compose (leitura por-chamada) · [ ] aditivo/retro-compatível · [ ] INV-3 · [ ] suíte verde
- [ ] Novo `except` → `python tools/lint_silent_except.py --update`.

## Closeout (ordem)
1. Validação no Log → 2. ADENDO (arquivo novo) → 3. code-review → 4. append Log → 5. commit tudo
(`SPR-ML1: ...` + trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`)
→ 6. push → **PR base `main`** (conferir `baseRefName==main`!) título `SPR-ML1:` → auto-merge
(`gh pr merge --auto --squash <nº>`) → 7. avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
