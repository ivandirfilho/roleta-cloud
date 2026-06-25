# SPR-G2 · `flags_snapshot`/`geometry_tag` por linha de `decisions` · Bloco BLK-H/I · Pri P0

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte: `fluxo_mental_24.md` (§4.2, §6 BLK-H/BLK-I, §7) e `auditoria_24_junho.md`.

## Meta
```text
blocked_by: []
locks:      [schema, alembic, BLK-I]      # serializa com QUALQUER outra migração Alembic
touches:    [migrations/versions/0010_*, database/sqlite_repo.py, database/models.py, database/service.py, server/message_handler.py]
base_sha:   origin/main
branch:     spr/SPR-G2
```

## Setup (worktree próprio)
```text
git -C "C:\Users\Windows\Desktop\Roleta Cloud" worktree add ..\rc-SPR-G2 -b spr/SPR-G2 origin/main
cd ..\rc-SPR-G2
```

## Objetivo (1 frase)
Gravar, em cada linha de `decisions`, um **snapshot das flags/geometria efetivas** no instante da decisão, para que análises por geometria parem de **inferir N** por `len(sda_numbers)` (a era 14–22/06 misturou 21#/14#/17# por toggling de flags e isso não ficou registrado).

## Âncoras (onde entrar — NÃO faça grep cego)
- Grafo: `graphify.get_neighbors MessageHandler` (§8) antes de ler.
- `database/sqlite_repo.py:186` — DDL `decisions`; `:300-365` — **padrão de ALTER idempotente** (copie este padrão).
- `database/models.py` — dataclass `Decision` (adicionar campo(s)).
- `database/service.py` — INSERT da `Decision` (incluir novas colunas).
- `server/message_handler.py:~960-979` — montagem da `Decision` em `handle_new_result` (preencher os valores aqui).
- `app_config/settings.py` — funções de flag a capturar: `strategy_regions_v4_enabled` (`:110`), `bet_pair_mode` (`:141`), `staking_mode` (`:125`), `force17_exact_enabled`, `gale_cap`, `geometry_v2_enabled` (`:83`), `sat_asym_enabled` (`:98`).
- `migrations/versions/0009_vision_features.py` — modelo p/ criar `0010_decision_flags.py`.

## Tarefa (passos)
1. **Migration** `migrations/versions/0010_decision_flags.py`: adiciona em `decisions` (idempotente; espelhar nos schemas se aplicável):
   - `flags_snapshot TEXT` (JSON do dict de flags efetivas),
   - `geometry_tag TEXT` (derivado: `force17` | `regions_v4_21` | `c2c3_14` | `full_21` | `v2v3_17`),
   - `coverage_n INTEGER` (= `len(sda_numbers)`).
2. **Espelhar o ALTER** no bloco de migração in-code de `database/sqlite_repo.py` (mesmo padrão `:300-365`) p/ DBs já existentes (prod usa este caminho além do alembic).
3. Em `handle_new_result`, ao montar a `Decision`: montar `flags = {regions_v4, bet_pair, staking_mode, force17_exact, gale_cap, geometry_v2, sat_asym}` chamando as funções de `settings`; derivar `geometry_tag`; `coverage_n=len(sda_numbers)`; `flags_snapshot=json.dumps(flags, sort_keys=True)`.
4. Propagar o(s) campo(s) por `database/models.Decision` + INSERT em `database/service.py`/`sqlite_repo`.

### Derivação de `geometry_tag` (precedência EXATA — o `bet_pair` recorta DEPOIS do `analyze`)
```text
bp = bet_pair_mode()
if   bp == 'force17':                tag = 'force17'        # união real ~15
elif bp == 'c2c3':                   tag = 'c2c3_14'
elif bp == 'c1c3':                   tag = 'c1c3_14'
elif bp == 'var_c1c2_c3':            tag = 'var_c1c2_c3'
elif strategy_regions_v4_enabled():  tag = 'regions_v4_21'  # bp=='full' + V4 ON
elif geometry_v2_enabled():          tag = 'v2v3_17'        # bp=='full' + V2/V3
else:                                tag = 'legacy_755'     # 7+5+5
```
`coverage_n = len(sda_numbers)` é sempre a contagem real (independe do tag). `flags_snapshot` guarda o dict bruto p/ auditoria.

## Critério de "pronto" (Definition of Done)
- [ ] Decisões NOVAS têm `flags_snapshot`, `geometry_tag`, `coverage_n` populados.
- [ ] `SELECT geometry_tag, COUNT(*), AVG(coverage_n) FROM decisions WHERE id > <X> GROUP BY 1;` funciona **sem inferir N**.
- [ ] Teste em `tests/` (schema + preenchimento de uma `Decision`).
- [ ] Teste **por caso** de `geometry_tag` (force17 / c2c3_14 / regions_v4_21 / v2v3_17) com flags mockadas → tag esperado.
- [ ] `alembic upgrade head` limpo; migração **aditiva** (sem DROP/rename de coluna existente).

## Guardrails (inviolável)
- **Metadata-only**: NÃO toca a aposta, a cobertura, nem o INV-3. Só registra.
- Flags lidas **como em runtime** (as funções de `settings` já leem env/compose) — não cachear, não hardcode.
- **Migração aditiva/retrocompatível** (rollback de deploy não dá downgrade). Numeração `0010` serializa: confirme que não há outra migração em voo.
- **Git:** só no worktree `spr/SPR-G2`; **NUNCA** push/reset/merge em `main`; entregue por **PR**. Sem SSH/host/prod. Aborte se o working tree começar sujo.
- Mudança restrita a BLK-H/I (config + persistência).

## Validação
```
# migração
docker compose run --rm roleta-cloud alembic upgrade head   # (ou: alembic upgrade head)
# testes
python -m pytest tests/ -k "decision or schema or migration" -v
# fumaça: gerar 1 decisão (1 spin local) e inspecionar a coluna
sqlite3 data/decisions.db "SELECT id, geometry_tag, coverage_n, flags_snapshot FROM decisions ORDER BY id DESC LIMIT 1;"
```

## Rollback (ISO)
Migração **aditiva** e **metadata-only** → reversível por `git revert` do PR (a coluna fica nullable, inofensiva); não toca aposta nem exige flag de runtime. (Opcional: popular sob `SDA_DECISION_FLAGS_SNAPSHOT` default-ON se quiser gate.)

## Closeout (a ORDEM importa)
1. **Validação** acima → colar no `## Log`; rodar a **suíte completa** (`pytest tests/`) verde.
2. **ADENDO** em `Manutenabilidade_iso.md` (capacidade nova + impacto ISO [Manutenibilidade/analytics: análise por geometria sem inferir N] + obrigações + Rollback).
3. **Code-review pós-implantação** (subagent `code-review`) → corrigir antes do PR.
4. **Append** no `## Log`.
5. `graphify update .` **local, sem commitar `graphify-out/`**.
6. `git status` → commit em `spr/SPR-G2` (`SPR-G2: telemetria de flags/geometria por decisão` + trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`), incluindo ADENDO + este brief; excluir `graphify-out/`.
7. `git push -u origin spr/SPR-G2` e **abrir PR**.
8. `store_memory`: "decisions agora grava flags_snapshot/geometry_tag/coverage_n por linha (SPR-G2) — análise por geometria não infere mais N"; avisar o Diretor: *"PR de SPR-G2 aberto"*.

---

## Log (EXECUTOR faz append; DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
