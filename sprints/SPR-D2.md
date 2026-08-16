# SPR-D2 · Última milha do deploy: nginx conf + entrypoint autogeridos pelo repo · Bloco BLK-K · Pri P0

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Origem: achado principal do SPR-D1 (16/08) — *"mergeou" ≠ "implantado"* enquanto
> `roleta.conf` e o entrypoint `/usr/local/bin/roleta-deploy-pull.sh` viverem fora do git
> sem nenhum mecanismo que os instale. O fix-forward do D1 não curou produção por isso
> (adendo `docs/iso/adendos/2026-08-16-diagnostico-502-self-heal.md` §5, issue #76).

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: [SPR-D1]      # MERGED (PR #74) — este sprint constrói em cima do self-heal
locks:      [deploy]      # scripts de deploy + roleta.conf + runbooks + unit exemplo
touches:    [scripts/roleta-deploy-pull.sh, scripts/roleta-deploy-install.sh,
             scripts/ (novo shim), roleta.conf (se precisar), docs/runbooks/, docs/DEPLOY.md,
             tests/ (cenários bash), issue #76 (comentário de atualização)]
base_sha:   origin/main
branch:     o branch da PRÓPRIA sessão. ⚠️ O PR final DEVE ter **base `main`**
            (`gh pr create --base main ...` ou create_pull_request já aponta main).
            NUNCA abra PR com base spr/SPR-D2 — auto-merge em branch sem proteção
            executa na hora e o trabalho NÃO chega à main (lição 2× em 16/08).
```

## Objetivo (1 frase)
Depois de UM único bootstrap do dono (bloco copy-paste na issue #76), **todo** artefato de
produção passa a ser dirigido pelo repo: o deploy instala/atualiza o `roleta.conf` do nginx
(com `nginx -t` + rollback) e o entrypoint do systemd nunca mais congela (padrão **shim
imutável → exec do script versionado**), fechando a lacuna *"mergeou ≠ implantado"*.

## Contexto técnico essencial (leia antes de projetar)
- `scripts/roleta-deploy-pull.sh` é a fonte VERSIONADA; o systemd roda a cópia congelada
  em `/usr/local/bin/` que **não se auto-atualiza**. O próprio script documenta a decisão
  histórica de NÃO se auto-instalar ("um deploy que reescreve o proprio entrypoint pode se
  tornar irrecuperavel") — sua tarefa é **superar essa objeção com engenharia**, não ignorá-la.
- `scripts/roleta-deploy-install.sh --check` hoje só DETECTA drift (não instala).
- O deploy já faz `nginx -t` + `reload` pós-sync do frontend, mas **nunca copia o conf**;
  `roleta.conf` versionado ≠ conf instalado em `/etc/nginx/` (o D1 adicionou `/health` e
  `/metrics` que produção ainda não tem).
- SPR-D1 adicionou self-heal no tick NOOP + testes de cenário do deploy em `tests/`
  (descubra o arquivo: `grep -r "roleta-deploy" tests/`) — ESTENDA esse harness.
- Issue #76 é o canal com o dono: o bootstrap manual único DEVE ser atualizado lá.

## Desenho recomendado (o executor pode refinar, justificando no Log)
1. **Shim imutável** `scripts/roleta-deploy-shim.sh` (novo, ~15 linhas): instalado UMA vez
   pelo dono em `/usr/local/bin/`; a unit passa a chamá-lo. A cada tick:
   `cd $REPO_DIR && git fetch origin main && git reset --hard origin/main` →
   `bash -n scripts/roleta-deploy-pull.sh` (gate de sintaxe) → `exec` do script do repo.
   Propriedade-chave: **um PR de revert cura um deploy-script quebrado no tick seguinte**
   (o shim sempre puxa a main ANTES de executar) — é isso que torna o self-update seguro
   e responde à objeção histórica. Shim minimalista = nunca precisa mudar; se um dia
   mudar, aí sim `roleta-deploy-install.sh install` cobre (item 3).
2. **Instalação do nginx conf no deploy** (`roleta-deploy-pull.sh`, pós-healthcheck, antes
   do bloco de frontend ou junto): se `roleta.conf` do repo difere do instalado
   (`cmp -s`), copiar para o path do site (descobrir/parametrizar `NGINX_CONF_DST`,
   default `/etc/nginx/sites-available/roleta.conf` — documente incerteza no runbook),
   backup `.bak`, `nginx -t`; falhou → restaura backup + `nginx -t` de novo + log
   `NGINX CONF ROLLBACK` + `exit ≠ 0` (unit failed, visível); passou → `reload`.
   Idempotente: sem diff ⇒ não toca no nginx.
3. **`roleta-deploy-install.sh`**: ganhar modo `install` real (atômico: `install -m755`
   em tmp + `mv`; backup `.bak`; `bash -n` antes) para instalar o SHIM (e opcionalmente
   re-instalar a si mesmo). O deploy chama `--check` como hoje (informativo) — a cura
   contínua vem do shim, não de auto-reescrita do entrypoint em voo.
4. **Bootstrap do dono (issue #76):** comentar na issue substituindo o passo-a-passo por
   UM bloco copy-paste: instalar shim + apontar a unit (`ExecStart=/usr/local/bin/
   roleta-deploy-shim.sh` via `systemctl edit` drop-in documentado) + instalar conf novo
   (`cp` + `nginx -t` + `reload`) + `systemctl start roleta-deploy.service` para o tick
   imediato. Deixar claro: **é a ÚLTIMA intervenção manual desta classe** — depois disso,
   conf e entrypoint seguem o repo sozinhos.
5. **Runbook/DEPLOY.md:** atualizar `docs/DEPLOY.md` + runbook do 502 com o novo modelo
   (shim, onde ficam os backups, como reverter: revert PR ⇒ tick seguinte cura).

## Tarefa (passos)
1. Ler o adendo do D1 §5, o runbook `docs/runbooks/servidor-502-glassbox.md`, a issue #76
   e os testes de deploy existentes.
2. Implementar itens 1–3 (shim + conf-install + install real) com os freios: tudo
   idempotente; falha de conf → rollback + exit≠0; `bash -n` em todos os pontos; nada de
   `set -e` engolindo rollback (o script usa `set -euo pipefail` — cuidado com traps).
3. Estender o harness de testes bash do D1: cenários (a) conf diff → instala+reload,
   (b) conf igual → no-op, (c) `nginx -t` falha → restaura backup + exit≠0, (d) shim com
   script quebrado → gate `bash -n` segura + exit≠0, (e) shim puxa main nova antes do exec.
4. `bash -n` em todos os .sh; `pytest tests/` completo (Windows local:
   `--ignore=tests/test_obs_reload.py`).
5. Comentar na issue #76 (bloco bootstrap) — via `gh issue comment 76 --body-file <f>`.
6. ADENDO novo: `docs/iso/adendos/2026-08-16-ultima-milha-deploy.md` (capacidade nova,
   riscos endereçados — inclua a objeção histórica e como o shim a resolve — rollback).

## Critério de "pronto" (Definition of Done)
- [ ] Shim versionado + testado; unit drop-in documentado; instalação atômica com backup.
- [ ] Deploy instala conf com `nginx -t`+rollback+reload, idempotente, falha visível.
- [ ] Cenários (a)–(e) no harness de teste passando; suíte pytest verde.
- [ ] Issue #76 atualizada com bootstrap único copy-paste (e o aviso "última vez").
- [ ] Runbook + DEPLOY.md refletem o modelo novo; ADENDO novo criado.
- [ ] **PR com base `main`** + auto-merge armado; título `SPR-D2: ...`.

## Guardrails (inviolável)
- **PROIBIDO ssh/host** — a implantação real acontece pelo bootstrap do dono (issue) e
  pelos merges; você só entrega repo + issue + runbook.
- Scripts defensivos: backup antes de sobrescrever, rollback testado, exit codes honestos.
- **INV-3** intacto (não é estratégia). Sem flag de compose ⇒ sem espelho Azure (confirme).
- **Git:** só no branch da sessão; PR base main; NUNCA tocar `main` direto; sem segredos;
  NÃO commitar `graphify-out/`.

## Validação (rode e cole o resultado no Log)
```
bash -n scripts/roleta-deploy-pull.sh scripts/roleta-deploy-install.sh scripts/roleta-deploy-shim.sh
pytest tests/ --ignore=tests/test_obs_reload.py
# harness de cenários do deploy (descobrir invocação no D1 e estender)
```

## Rollback (ISO — sempre documentar)
`git revert` do PR (tick seguinte do shim já executa a versão revertida — essa é a
propriedade central do desenho) · conf: backup `.bak` restaurado automaticamente em falha
de `nginx -t` · shim: o dono pode reapontar a unit para o script antigo (drop-in removível).

## Conformidade ISO (marque ANTES de abrir o PR)
- [ ] Aditivo/retro-compatível (script antigo continua funcional se o dono não fizer o
      bootstrap; nada quebra sem ele).
- [ ] Novo `except Exception` (Python)? → lint; bash não conta mas mantenha `|| true` só
      onde não-fatal for deliberado e logado.
- [ ] ADENDO como arquivo NOVO (nunca apendar em `Manutenabilidade_iso.md`).
- [ ] Mexeu em `extension/`? Não previsto — se sim, bump manifest.

## Closeout (a ORDEM importa)
1. Validação → Log. 2. ADENDO. 3. Code-review (subagent) → corrigir. 4. Append no Log.
5. Commit no branch da sessão (`SPR-D2: <resumo>` + trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`).
6. **Lock check pré-PR:** `gh pr list` — #77 (Log do D1, `sprints/SPR-D1.md`) e #78
   (governança, template/agents) são disjuntos; se surgir PR tocando `scripts/` deploy,
   serialize.
7. Push + **PR base `main`** título `SPR-D2: ...` + auto-merge
   (`gh pr merge --auto --squash <nº>`). Verifique `baseRefName == main` no output.
8. Comentário na issue #76 + avisar o Diretor: "PR de SPR-D2 aberto (base main confirmada)".

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
