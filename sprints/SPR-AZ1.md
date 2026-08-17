# SPR-AZ1 · Espelho Azure: freshness real do standby + sonda no kickoff + issue OIDC · Bloco deploy-azure · Pri P2

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> **SDD: este brief É a spec.** Decisões FECHADAS não se reabrem; ambiguidade real → 1 pergunta ao Diretor.

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []
locks:      [deploy-azure, docs, scripts]
touches:    [scripts/agent-kickoff.ps1, docs/azure/, .github/ (nada de workflow novo sem gate)]
base_sha:   origin/main
branch:     spr/SPR-AZ1 (brief publicado); executor trabalha no branch da sessão, PR base main
modelo:     gpt-5.6-luna
timebox:    45min
```

## Setup
Sessão/worktree própria a partir de `spr/SPR-AZ1`. `git status` limpo antes de começar.

## Objetivo (1 frase)
Tornar auditável (e visível no ritual de abertura) o estado do espelho Azure — que hoje é standby
frio por snapshot — e abrir para o dono a issue com o passo exato que falta para o povoamento
contínuo (secrets OIDC + gate).

## Contexto factual (probe do Diretor 16/08 — `resultados_semana_10_08_16_08.md` §8)
- Timer `roleta-hostdime-snapshot` ATIVO no host Debian (a cada 10 min; SQLite+state.json → Blob).
- VM Azure `20.226.77.194` viva (Caddy): `/health` → 404; o path correto é **`/healthz`**
  (`deploy/azure/README.md`). Freshness do restore (`/opt/roleta/standby`) não comprovada de fora.
- Workflow `acr-image.yml` gateado por `vars.AZURE_PUBLISH_ENABLED == '1'` — a variable **não
  existe** (`gh variable list` vazio) e não há secrets OIDC → todos os runs `skipped`.
- PG analítico Azure vazio; HostDime é o único escritor (correto, pré-cutover).

## Âncoras
- `deploy/azure/README.md` + `deploy/azure/compose.azure.yml` + `deploy/azure/systemd/*.timer`.
- `azure_05_08_arquitetura.md` (desenho do snapshot/manifesto) · `maquina_azure_agora_25.md` (VM, testes T1–T45).
- `scripts/agent-kickoff.ps1` — seção "4. Produção": ponto de extensão para a sonda Azure.
- `.github/workflows/acr-image.yml` — só LEITURA (referência p/ a issue).
- Chave local: `~\.ssh\id_rsa_azure` (usuário `azureuser`) — VM standby, NÃO é produção.

## Tarefa (passos)
1. **Probe read-only da VM standby** (permitido: NÃO é o servidor de produção; Debian
   `187.45.181.75` continua PROIBIDO): `curl -m 5 https://20-226-77-194.sslip.io/healthz` (e
   variantes do README). Se necessário e disponível, `ssh -i ~/.ssh/id_rsa_azure -o BatchMode=yes
   azureuser@20.226.77.194` SOMENTE leitura (`systemctl list-timers`, `ls -la /opt/roleta/standby`,
   manifesto mais recente) para medir o **lag real** snapshot→restore. Se o SSH não autenticar,
   registrar e seguir (não é bloqueante).
2. **Sonda no kickoff:** adicionar ao `scripts/agent-kickoff.ps1` uma linha best-effort (timeout 3s,
   nunca falha o script) mostrando o estado do standby Azure (`/healthz` + código) ao lado da sonda
   de produção. Manter o script read-only e rápido (~10s de orçamento total).
3. **Issue para o dono** (gh issue create): título claro ("Azure: criar secrets OIDC + variable
   AZURE_PUBLISH_ENABLED para destravar publicação de imagens"), corpo com passo-a-passo exato
   (nomes dos secrets `AZURE_CLIENT_ID/TENANT_ID/SUBSCRIPTION_ID`, variable `=1`, o que o workflow
   passa a fazer, risco zero p/ produção HostDime) e o link do run `skipped` mais recente.
4. **Relatório** `docs/azure/2026-08-16-standby-freshness.md`: números medidos (códigos HTTP, lag do
   manifesto se obtido, estado dos timers), o desenho atual (snapshot 10min → poll 2min), e a
   distância exata até "povoamento em tempo real" (dual-write pós-cutover; NÃO propor ligar agora).

## FECHADAS (não reabrir)
- NENHUM workflow novo com secrets sem gate default-OFF (inviolável).
- NÃO criar a variable/secrets (é ação do dono via issue) — o sprint só prepara e documenta.
- NÃO tocar DNS, compose de produção, nem dual-write.

## Critério de "pronto" (DoD)
- [ ] `agent-kickoff.ps1` com sonda Azure best-effort (rodar o script e colar o output no Log).
- [ ] Issue criada (nº no Log).
- [ ] Relatório em `docs/azure/` com medições reais e o gap para tempo-real.
- [ ] Suíte verde (`pytest tests/ -q --ignore=tests/test_obs_reload.py`) — nada de código de app muda,
      mas o CI roda tudo.

## Guardrails (inviolável)
Sem SSH ao Debian de produção; standby Azure só leitura; sem segredos em commit; PR base `main` +
auto-merge; ADENDO como arquivo novo.

## Validação (rode e cole no Log)
```
pwsh -File scripts/agent-kickoff.ps1
pytest tests/ -q --ignore=tests/test_obs_reload.py
```

## Rollback (ISO)
`git revert` do PR (sonda é aditiva e best-effort; sem flag de runtime).

## Conformidade ISO (antes do PR)
- [ ] Aditivo · [ ] sem secrets · [ ] suíte verde · [ ] ADENDO novo.

## Closeout (ordem)
Validação → ADENDO `docs/iso/adendos/` → code-review → Log → commit `SPR-AZ1: ...` (+trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`) → push → **PR base `main`**
título `SPR-AZ1:` → auto-merge → avisar o Diretor.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
2026-08-16 · concluído · sonda Azure best-effort, relatório de freshness e issue de verificação OIDC · kickoff + pytest · scripts/agent-kickoff.ps1, docs/azure/2026-08-16-standby-freshness.md, docs/iso/adendos/2026-08-16-spr-az1-standby.md
