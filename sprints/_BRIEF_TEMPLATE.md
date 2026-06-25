# SPR-XXX · <título curto> · Bloco BLK-? · Pri P?

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte/visão: `fluxo_mental_24.md` (card §6 do bloco, linha §7 do backlog, navegação no grafo §8).

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []           # SPR-* que precisam estar MERGED antes
locks:      []           # ex.: schema, alembic, BLK-G, compose, extensão
touches:    []           # arquivos/dirs principais
base_sha:   origin/main
branch:     spr/SPR-XXX
```

## Setup (worktree próprio — NÃO use o working dir do Diretor)
```text
git -C <repo> worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main
cd ..\rc-SPR-XXX     # comece limpo a partir de origin/main
```

## Objetivo (1 frase)
<o que resolver e por quê — a "dor">

## Âncoras (onde entrar — NÃO faça grep cego)
- Grafo: nó-âncora `<God node>` (§8) → `graphify.get_neighbors <nó>` ANTES de ler arquivos.
- `caminho/arquivo.py:LINHA` — <papel>
- `...`

## Tarefa (passos)
1. ...
2. ...

## Critério de "pronto" (Definition of Done — copiado do §7)
- [ ] <verificável: coluna populada / teste passa / métrica / query funciona>
- [ ] Teste(s) em `tests/` cobrindo a mudança.

## Guardrails (inviolável)
- **INV-3**: a estratégia NUNCA fica sem indicação (vetos modulam stake, não suprimem).
- **Flags na compose**: comportamento novo nasce **atrás de flag default-OFF**; leitura por chamada (não cachear); nada hardcoded.
- **Migração Alembic aditiva/retrocompatível** (o rollback de deploy NÃO faz downgrade de schema).
- **Git:** trabalhe só no worktree/branch `spr/SPR-XXX`; **NUNCA** push/checkout/reset/merge em `main`. Entregue por **PR**.
- **Produção intocável:** sem SSH/systemd/edição no host; testes e migrations só em DB **local/teste**. Aborte se o working tree começar sujo.
- Mudança cirúrgica dentro dos `locks`/Raio (§6); sem segredos no commit; sem comando destrutivo.

## Validação (rode e cole o resultado no Log)
```
<comando(s) de teste/reprodução — ex.: pytest tests/ -k "<alvo>"; alembic upgrade head; curl :8766/health>
```

## Rollback (ISO — sempre documentar)
Reverter SEM perda (ISO obrig.): preferir **flag default-OFF na compose** (`SDA_...=0` + redeploy) OU `git revert` do PR. Schema: o rollback de deploy **NÃO faz downgrade** → migração tem de ser **aditiva**.
- Flag de rollback: `<SDA_FLAG=0>` · ou `git revert <commit>`.

## Conformidade ISO (marque ANTES de abrir o PR — `Manutenabilidade_iso.md`)
- [ ] Atrás de **flag default-OFF** no `docker-compose.yml` (ISO obrig. #4); leitura por-chamada (não cachear).
- [ ] **Aditivo/retro-compatível** (migração + contrato/overlay; sem remover/renomear chaves).
- [ ] **INV-3** intacto; **suíte completa verde** (`pytest tests/`).
- [ ] Novo `except Exception` → `python tools/lint_silent_except.py --update`.
- [ ] Campo de motor novo → round-trip em `save()`+`load()`+`reset_session()`.
- [ ] Mexeu em `extension/` → bump `manifest.version` + nota de reload no Chrome.

## Closeout (a ORDEM importa — não commitar antes de gerar o log)
1. Rodar a **Validação** (incl. **suíte completa verde**) e colar o resultado no `## Log`.
2. **ADENDO ISO**: anexar entrada em `Manutenabilidade_iso.md` (capacidades + impacto ISO por característica + scorecard delta + obrigações + **Rollback**) — exigência do ciclo.
3. **Code-review pós-implantação** (subagent `code-review` ou rodada manual) → corrigir bugs antes do PR.
4. **Append** no `## Log` (data · status · o que mudou · validação · arquivos).
5. `graphify update .` só p/ navegação **local** → **NÃO commitar `graphify-out/`** (Diretor/CI atualiza após o merge).
6. `git status` → **commitar TODOS os arquivos** (código + ADENDO + ESTE brief com o log) em `spr/SPR-XXX` (`SPR-XXX: <resumo>` + trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`). Excluir `graphify-out/`.
7. `git push -u origin spr/SPR-XXX` e **abrir PR** (NÃO fazer merge).
8. `store_memory` do achado durável (escopo repository); avisar o Diretor: *"PR de SPR-XXX aberto"*.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
