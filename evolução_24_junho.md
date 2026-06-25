# evolução_24_junho — Estrutura de trabalho nativa no Copilot CLI: PLAN → GO (auditoria + proposta · versão final)

**Data:** 2026-06-24 · **CLI:** 1.0.63 · **Objetivo:** deixar o modelo de sprints (`fluxo_mental_24.md` §10–§12)
**embutido nas superfícies nativas** do Copilot CLI — skills, agents, instructions, hooks, permissions/guardrails,
sandbox, `/delegate` — para que, ao abrir uma sessão depois, o comportamento (Diretor/Executor + rituais ISO)
**já esteja carregado e, onde importa, IMPOSTO** (não só sugerido). Stack: filesystem · web (docs oficiais) · graphify.

> Verdade-base desta auditoria (verificada nesta máquina): `config.json allow_all=true`; `permissions-config.json`
> da pasta Roleta Cloud **pré-aprova `git push`, `ssh`, `docker`, `Remove-Item`**; `graphify-out/` é **versionado**
> (54 arquivos, ~2,5 MB, não-ignorado); `/fleet` = **403**; agents/skills/instructions podem ser **de repositório**.

---

## 0. Modelo operacional — PLAN → GO (discutir, depois rodar tudo automático)

Seu fluxo de verdade tem **2 fases**, espelhando `plan mode` + `autopilot` do Copilot CLI:

- **FASE A — PLAN (discussão com o gestor = Diretor).** Você conversa comigo sobre estruturas/dores/sprints, **sem mexer em código** (`Shift+Tab` entra/sai do plan mode, ou `/plan`). Saída: **plano acordado** + **briefs** (`sprints/SPR-*.md`) + **board** atualizado. Aqui decidimos escopo, ordem, paralelismo e riscos — **uma decisão só** no fim ("aprovado, rodar").
- **FASE B — GO (autopilot, zero aprovação no meio).** Você diz **"rodar"** e a execução acontece **sozinha** — inclusive as mudanças de infra que já combinamos no PLAN. Sem aprovar comando a comando.

### 0.1 Aberturas de conversa (como você começa comigo)
| Você diz | Eu (Diretor) faço — em PLAN |
|---|---|
| **"Dor: <descrição>"** | viro 1+ sprint(s): brief + linha no board |
| **"Plano para <tema>"** | plan mode: proponho sprints + ordem/paralelismo + bugs/riscos |
| **"Status"** | cruzo `sprints/BOARD.md` × `gh pr list` × CI → standup (1 tela) |
| **"Auditar o plano"** | rubber-duck/`code-review` do plano antes do GO |
| **"Rodar SPR-X [, Y, Z em paralelo]"** | **GO** (autopilot) |

### 0.2 Zero aprovação no meio — como, sem perder segurança
Você pré-autoriza no GO; a segurança vem da **ESTRUTURA**, não de prompts:
- Executor **abre PR** (ação segura/reversível) — **nunca** bloqueia esperando você.
- `main` protegida (PR+CI verde) + **toda mudança nasce flag default-OFF** → mesmo um merge é **inócuo** (o código dorme).
- **git hooks** barram o perigoso (push `main` / `graphify-out`); **`/sandbox`** no executor barra prod/rede.
- ⇒ O **único** ato deliberado que sobra é **ligar a flag** quando você quiser validar em produção — **assíncrono** (na hora que quiser), **nunca um prompt no meio**.
> Verdade (trade-off): quer **100% hands-off**? dá pra **auto-merge no CI-verde** — mas aí ninguém revisa o comportamento antes de ele chegar (dormente) em prod; a **flag** continua sendo seu ponto de controle.

### 0.3 Acompanhar N sprints em paralelo (clareza no dia a dia)
**Fonte única do dia:** `sprints/BOARD.md` (kanban) + os **PRs** (execução viva). Cada sprint = 1 branch `spr/SPR-*` = 1 PR = 1 linha no board.
- **Standup ao abrir a sessão:** peça **"status"** → eu devolvo 1 tela: `DOING/REVIEW/BLOCKED`, PRs verdes/vermelhos, e **o que pede você** (merge-ready ou flag-flip).
- **`/every 30m "status"`** numa sessão longa → digest automático. **`/tasks`** = subagents/PRs em voo.
- Paralelo seguro = `locks` disjuntos (board). Histórico: **`/chronicle`**; retomar: **`copilot --continue`** / **`/resume`**.

### 0.4 Evoluir bugs & melhorias NO plano (loop)
O **plano é vivo** (este arquivo + `fluxo_mental_24.md`). A cada discussão:
1. Registro a ideia/bug como item (sprint `SPR-*` ou nota).
2. **Antes do GO**, passo `rubber-duck`/`code-review` (como já fizemos: 9+7 bugs achados) → corrijo o plano.
3. A mudança vira 1 linha no **§7 Changelog** — o plano nunca regride em silêncio.
4. Pós-execução, o **ADENDO ISO** fecha o ciclo e o board marca `MERGED`.

---

## 1. Superfícies nativas reais do Copilot CLI (onde "morar")

| Superfície | Local (repo = versionado/compartilhado) | Papel no workflow |
|---|---|---|
| **Custom instructions** | `.github/copilot-instructions.md` · `.github/instructions/*.instructions.md` · `AGENTS.md` | Regras SEMPRE carregadas (INV-3, ISO, flag-OFF, "executor não mexe em main/prod") |
| **Custom agents** | `.github/agents/*.md` (repo) · `~/.copilot/agents/` (user) · `.github-private` (org) | Personas `sprint-director` / `sprint-executor` (frontmatter `name`/`description`/`model`) |
| **Skills** | `.github/skills/<n>/SKILL.md` (repo) · `~/.copilot/skills/` (user) | Auto-injeção por gatilho (`description`/`trigger`); pode levar scripts + `allowed-tools` |
| **Hooks** | `~/.copilot/hooks/` (scripts user-level) · **+ git-native `.git/hooks/`** | Automação de ciclo de vida / enforcement local |
| **Permissions/guardrails** | `permissions-config.json` (allow-list por pasta) + `config.json allow_all` | Aprovação de tools; **hoje TUDO liberado** (ver §3 BUG-1) |
| **Sandbox** | `/sandbox enable` (local) · `copilot --cloud` | Restringe fs/rede do executor (impede tocar prod) |
| **Delegação** | `/delegate` (cloud agent → PR) · `/fleet` (**403**) | Executor paralelo SEM abrir terminal (resolve o ônus do escalonador manual) |
| **Scheduling** | `/every` · `/after` | Diretor poll de PRs / refresh de board |
| **Subagent models** | `settings.json` `subagents.agents.*.model` (já = opus-4.8) | Rubber-duck/code-review/explore dentro de um sprint |

---

## 2. Mapeamento — peça do workflow → superfície nativa

| Peça (`fluxo_mental_24.md`) | Vira nativamente |
|---|---|
| Persona Diretor (§10) | `.github/agents/sprint-director.md` (`model: claude-opus-4.7`) |
| Persona Executor (§9–§12) | `.github/agents/sprint-executor.md` (`model: claude-opus-4.7`) |
| Protocolo + rituais ISO (§12) | `.github/copilot-instructions.md` (auto-load em TODA sessão, incl. `/delegate`) |
| "Execute `sprints/SPR-*.md`" | skill `.github/skills/sprint-executor/SKILL.md` (description casa o pedido; injeta DoD+ISO+closeout) |
| Board vivo / backlog | `sprints/BOARD.md` + `fluxo_mental_24.md` §7 (já existe) |
| Spawn paralelo de executores | **`/delegate`** (1 por sprint → PR) — não mais "abrir N terminais" |
| Gate de merge (=deploy) | **GitHub branch protection na `main`** (server-side, IMPOSTO) |
| "Nunca push/commit em main / graphify-out" | **git hooks** `pre-push`/`pre-commit` (impostos localmente) + `.gitignore` |
| "Executor não toca prod/rede" | `/sandbox enable` no executor |
| Poll de PRs / status | `/every 15m` no Diretor |

---

## 3. AUDITORIA — bugs (🔴/🟡) e melhorias (🟢)

### 🔴 BUG-1 (crítico) — guardrails do workflow NÃO são impostos hoje
`allow_all=true` + a pasta Roleta Cloud pré-aprova `git push`, `ssh`, `docker`, `Remove-Item`. Logo um **executor em
autopilot empurraria pra `main` / faria `ssh` em prod SEM perguntar**. Meu "nunca push main / nunca toque prod" é
**prosa**, não enforcement. **Fixes (em ordem de robustez):**
1. **Branch protection na `main`** (server-side, não burlável): exige PR + CI verde + 1 review. → impõe o gate de merge.
2. **git-native hooks** (impostos localmente, independem do agente):
   - `.git/hooks/pre-push` → rejeita push cujo ref de destino seja `main`.
   - `.git/hooks/pre-commit` → rejeita commit que toque `graphify-out/` ou caminhos de prod.
3. **Executor em `/sandbox`** (sem rede → `ssh`/deploy impossíveis) ou rodar via **worktree** (pasta nova ≠ aprovações da Roleta Cloud → comandos perigosos voltam a pedir confirmação).
4. **Endurecer `permissions-config.json`**: remover `git push`/`ssh`/`Remove-Item` das auto-aprovações da pasta (ou desligar `allow_all` no executor). *(edição sensível — requer sua aprovação.)*

### 🔴 BUG-2 (crítico) — `graphify-out/` versionado e NÃO ignorado
54 arquivos (~2,5 MB) tracked; `graphify update .` em cada branch → **conflito garantido** em paralelo. **Fix:** `.gitignore`
`graphify-out/graph.json` e `graph.html` (manter só `GRAPH_REPORT.md`, ou nada) **+** o `pre-commit` hook do BUG-1; Diretor/CI atualiza o grafo 1× após o merge.

### 🟡 BUG-3 — worktree do executor precisa de trust/escopo
`..\rc-SPR-XXX` é pasta nova. Está sob `C:\Users\Windows` (já em `trustedFolders`) → provável auto-trust, mas **não herda** as auto-aprovações da Roleta Cloud → comandos perigosos pedem confirmação (✅ bom p/ segurança; documentar para não assustar).

### 🟡 BUG-4 — `/delegate` vs `/fleet`: confirmar o caminho de paralelismo
`/fleet`=403. `/delegate` (cloud agent → PR) **provavelmente funciona** (há branches `origin/copilot/*`). Se confirmado, é o **melhor executor nativo** (sem terminal, roda em sandbox cloud, abre PR). **Fix:** padronizar em `/delegate`; fallback = sessão manual + worktree. *(Auditar: rodar 1 `/delegate` de teste.)*

### 🟡 BUG-5 — colocar agents/skills só em `~/.copilot` quebra `/delegate` e o time
O cloud agent do `/delegate` clona o **repo**, não o seu `~/.copilot`. Se as personas/rituais ficarem só user-level, o executor cloud **não os vê**. **Fix:** publicar **repo-level** (`.github/agents`, `.github/skills`, `.github/copilot-instructions.md`). (O `yolo-orchestrator` user-level permanece como seu default pessoal.)

### 🟡 BUG-6 — `allowed-tools: shell` em skill = risco de prompt-injection
A doc **alerta**: pré-aprovar `shell`/`bash` numa skill deixa script malicioso/injeção rodar comando arbitrário. **Fix:** **omitir** `shell` do `allowed-tools` da skill do executor; o agente pede confirmação p/ rodar scripts.

### 🟡 BUG-7 — conflito de modelo (GPT vs Opus)
`config.json` experimental empurra GPT-5.4 p/ subagents; `AGENTS.md`/yolo exige Opus. **Fix:** fixar `model: claude-opus-4.7` no frontmatter dos agents repo-level (honra "não delegar a GPT").

### 🟢 Melhorias
- **M1 — `.github/copilot-instructions.md` é a maior alavanca:** carrega INV-3 + rituais ISO + gates em **TODA** sessão (incl. `/delegate`). Torna o ritual **inescapável** sem depender da memória.
- **M2 — CI vira o gate ISO imposto:** somar ao `ci.yml` checks de PR: (a) PR de comportamento exige ADENDO em `Manutenabilidade_iso.md`; (b) diff não contém `graphify-out/`; (c) flags novas nascem default-OFF. Server-side = não burlável.
- **M3 — `/every 15m` no Diretor:** `gh pr list` → atualiza `sprints/BOARD.md` (REVIEW/MERGED) sozinho; reduz o "feito SPR-X" manual.
- **M4 — `/delegate` mata o ônus do escalonador manual:** do prior audit, o gargalo era "abrir N terminais"; com `/delegate` o paralelismo vira nativo (N PRs).
- **M5 — `gh skill`** p/ versionar/compartilhar as skills; `/skills reload` + `/skills info` p/ validar.

---

## 4. Artefatos nativos a criar (repo-level, prontos)

**`.github/copilot-instructions.md`** (regras sempre-on):
```markdown
# Roleta Cloud — instruções (sprints + ISO)
- INV-3: a estratégia SEMPRE indica APOSTAR; veto entra como min(), nunca suprime.
- Mudança de comportamento nasce atrás de FLAG default-OFF no docker-compose.yml; migração Alembic ADITIVA.
- Executor: trabalhe só em branch `spr/SPR-*` (worktree); NUNCA push/checkout/reset/merge em `main`; entregue por PR.
- Produção intocável: sem ssh/host/deploy; testes/migrations só em DB local/teste.
- Todo sprint: suíte verde + ADENDO em Manutenabilidade_iso.md (capacidades+impacto ISO+scorecard+obrigações+Rollback).
- NÃO commitar graphify-out/. Detalhes: fluxo_mental_24.md §6–§12; sprints/BOARD.md.
```

**`.github/agents/sprint-director.md`**:
```markdown
---
name: sprint-director
description: Orquestra sprints (board+briefs), NÃO implementa. Lê sprints/BOARD.md, gera briefs, lê PRs.
model: claude-opus-4.7
---
Você é o Diretor. Mantenha sprints/BOARD.md e os briefs (sprints/_BRIEF_TEMPLATE.md). Nunca implemente.
Loop e gates em fluxo_mental_24.md §10–§12. Leia resultados via `gh pr list`/`--stat`/memória — nunca diffs grandes.
```

**`.github/agents/sprint-executor.md`**:
```markdown
---
name: sprint-executor
description: Executa UM brief sprints/SPR-*.md em worktree+branch, valida pela DoD, abre PR. Não toca main/prod.
model: claude-opus-4.7
---
Execute o brief indicado seguindo o protocolo §9 e os rituais ISO §12. Worktree próprio; PR; closeout (ADENDO+log+memória).
```

**`.github/skills/sprint-executor/SKILL.md`** (sem `allowed-tools: shell`):
```markdown
---
name: sprint-executor
description: Use quando pedirem para executar um sprint (sprints/SPR-*.md). Injeta DoD, rituais ISO e closeout.
---
Abra o brief, crie worktree (`git worktree add ..\rc-SPR-XXX -b spr/SPR-XXX origin/main`), implemente, valide,
preencha o checklist ISO, escreva o ADENDO, e abra PR. Nunca push/merge em main. Detalhes: fluxo_mental_24.md §12.
```

**git hooks (enforcement local) + .gitignore:**
```bash
# .git/hooks/pre-push  (chmod +x)
while read _ _ ref _; do [ "$ref" = "refs/heads/main" ] && { echo "BLOQUEADO: push em main é via PR"; exit 1; }; done
# .git/hooks/pre-commit
git diff --cached --name-only | grep -q '^graphify-out/' && { echo "BLOQUEADO: não commitar graphify-out/"; exit 1; }; true
# .gitignore  (+ acrescentar)
graphify-out/graph.json
graphify-out/graph.html
```

**Branch protection (1× via gh):**
```bash
gh api -X PUT repos/ivandirfilho/roleta-cloud/branches/main/protection \
  -f required_status_checks.strict=true -f enforce_admins=true \
  -F required_pull_request_reviews.required_approving_review_count=1
```

---

## 5. Enforcement — o que é IMPOSTO vs CONVENÇÃO (o ponto da auditoria)

| Regra | Hoje | Proposto (imposto por) |
|---|---|---|
| Merge só por PR+CI+review | convenção | **branch protection** (server) |
| Não push direto em main | convenção (e hoje pré-aprovado!) | **git pre-push** + branch protection |
| Não commitar graphify-out | convenção | **git pre-commit** + `.gitignore` |
| Flag default-OFF / aditivo / ADENDO | convenção | **CI checks** (M2) + instructions |
| Executor não toca prod | convenção | **/sandbox** + permissions endurecidas |
| INV-3 / rituais ISO | memória/prosa | **.github/copilot-instructions.md** (sempre-on) |

> **Por que isto casa com "zero aprovação no meio":** o enforcement é **estrutural** (server/local) → o autopilot roda **livre, sem prompts**; o que seria perigoso é **bloqueado**, não **perguntado**. O gate humano vira **assíncrono** (revisar PR / ligar flag), nunca no meio da execução.

---

## 6. GO playbook — o que roda automático quando você diz "rodar" (pré-autorizado)

> No PLAN você já aprovou o escopo; no GO **não há aprovação comando-a-comando** (autopilot + allow_all). Sequência:

**Bootstrap nativo (1ª vez, idempotente — depois disto toda sessão futura já nasce configurada):**
1. Criar repo-level: `.github/copilot-instructions.md`, `.github/agents/{sprint-director,sprint-executor}.md`, `.github/skills/sprint-executor/SKILL.md` → commit.
2. `.gitignore` graphify-out + git hooks `pre-push`/`pre-commit` (chmod +x) → commit.
3. **Branch protection** na `main` via `gh api` (PR + CI verde + 1 review).
4. CI: somar checks ISO (ADENDO presente / sem `graphify-out` no diff / flags default-OFF) ao `ci.yml` → PR.
5. *(Opcional)* endurecer `permissions-config.json` **ou** padronizar executor em worktree + `/sandbox`.

**Por sprint (no GO, em paralelo — `locks` disjuntos):**
6. Para cada `SPR-*` READY: **`/delegate`** (cloud → PR) **ou** sessão+worktree → executor implementa → testa → ISO/ADENDO → **abre PR** (não bloqueia).
7. CI roda no PR; verde → **merge** (branch protection garante o piso). Código entra **dormente** (flag-OFF) → merge é seguro.
8. Board → `MERGED`; eu te aviso o que está **flag-ready**.

**Seu único ato deliberado (assíncrono, fora da sessão):** ligar a flag na `docker-compose.yml` quando quiser validar em prod. *(Quer 100% hands-off? auto-merge-on-green + você só cuida da flag.)*

> Resumo: **abriu a sessão →** personas+rituais já carregados; **"plano para X" →** discutimos (sem código); **"rodar" →** bootstrap + sprints rodam sozinhos; **tentou furar** (push main / graphify-out) **→** bloqueado; **merge →** esteira automática (`fluxo_mental_24.md` §12). Gates humanos sobrando, por escolha: revisar PR (async) e ligar flag (async).

---

## 7. Changelog do plano (o plano é vivo — bugs/melhorias entram aqui)

> Cada discussão que muda o plano vira 1 linha. O plano nunca regride em silêncio; `rubber-duck`/`code-review` antes do GO.

- **24/06 v1** — proposta nativa: superfícies + mapeamento + 7 bugs + 5 melhorias + artefatos prontos.
- **24/06 v2 (final)** — + **Modelo PLAN → GO** (§0); **zero aprovação no meio** via enforcement estrutural (§0.2/§5); **painel diário** p/ N sprints paralelos (§0.3); **aberturas de conversa** (§0.1); **loop de evolução do plano** (§0.4); §6 vira **GO playbook pré-autorizado**.
- **24/06 v3** — + **§8: backlog de implantação `SPR-M1…M14`** (7 ondas) + desenho do **comando GO** (skill `methodology-go` + `scripts/methodology-go.ps1` + hook a verificar). Confirmado: arquivos repo-level em `.github/` auto-carregam em TODA sessão (mecanismo que "obriga" os agentes futuros).

---

## 8. Sprints de implantação da metodologia (SPR-M* — backlog completo)

> Estes sprints **constroem a própria metodologia** (infra nativa + enforcement). São distintos do backlog de **produto** (`fluxo_mental_24.md` §7: SPR-G/S/T/X/O). Prefixo **SPR-M** (Metodologia).
> **Onde moram:** DENTRO do repo, em `.github/` — o Copilot CLI auto-carrega `copilot-instructions.md` + `agents/` + `skills/` de repositório em TODA sessão aberta aqui, e o `/delegate` herda (clona o repo). É assim que se "obriga" os agentes futuros. Confira com `/env`.

### 8.1 O comando "GO" — sair do plan e disparar TODA a sequência (`SPR-M7`)
**Verdade nativa:** o Copilot CLI **não** deixa criar um slash-command novo, e o **plan mode** é toggle SEU (`Shift+Tab`) — o agente não força. Então o "comando GO" se monta com 3 peças:
1. **Gatilho (palavra-chave):** skill repo `methodology-go` com `description: "Use quando o usuário disser GO/RODAR/IMPLANTAR"` → o modelo reconhece a frase e dispara.
2. **Sequência determinística (script):** `scripts/methodology-go.ps1` **idempotente** = roda o bootstrap inteiro; a skill manda o agente executá-lo.
3. **Hook (ideal, a verificar):** `~/.copilot/hooks/` aceita scripts user-level; SE houver evento "prompt submit", um hook detecta a frase e dispara sozinho (schema a confirmar em `copilot help`/`/env`; até lá, skill+script bastam).

**Fluxo real:** em plan, você faz **`Shift+Tab` → "RODAR IMPLANTAÇÃO"** → autopilot roda `methodology-go.ps1` ponta-a-ponta, **sem aprovação no meio**. Esqueleto:
```powershell
# scripts/methodology-go.ps1 — bootstrap idempotente da metodologia
# 1) cria .github/{copilot-instructions.md, agents/*, skills/*} se ausentes
# 2) .gitignore += graphify-out/graph.{json,html}; instala git hooks pre-push/pre-commit
# 3) gh api → branch protection na main (PR+CI+1 review)
# 4) ci.yml += checks ISO; 5) abre PRs dos SPR-M pendentes; 6) /env check final
```

### 8.2 Backlog SPR-M (por onda; ✅=não-sensível roda no GO · ⛳=pede seu aceite no PLAN)
| ID | Onda | Sprint | Superfície / arquivo | Critério de "pronto" | Dep |
|---|---|---|---|---|---|
| `SPR-M1` ✅ | 1 Núcleo | Instruções repo-level | `.github/copilot-instructions.md` (INV-3, ISO, flag-OFF, regras do executor) | `/env` lista; sessão nova obedece | — |
| `SPR-M2` ✅ | 1 Núcleo | Personas (agents) | `.github/agents/sprint-director.md` + `sprint-executor.md` (`model: opus-4.7`) | `/agent` lista; `/delegate` herda | — |
| `SPR-M3` ✅ | 1 Núcleo | Skill do executor | `.github/skills/sprint-executor/SKILL.md` (injeta DoD/ISO/closeout; sem `allowed-tools: shell`) | `/skills info` ok | M2 |
| `SPR-M4` ✅ | 2 Guardrail local | git hooks + ignore | `.git/hooks/pre-push` (bloqueia `main`) + `pre-commit` (bloqueia `graphify-out/`) + `.gitignore` | push main / commit graphify-out **bloqueados** | — |
| `SPR-M5` ⛳ | 2 Guardrail server | Branch protection | `gh api` PUT proteção `main` (PR + CI verde + 1 review) | push direto rejeitado; merge exige PR verde | M6 |
| `SPR-M6` ✅ | 3 Gate ISO | CI checks ISO | `ci.yml` += ADENDO presente / sem `graphify-out` no diff / flags novas default-OFF | PR sem ADENDO **falha** | — |
| `SPR-M7` ✅ | 4 Comando GO | Comando/hook GO | `scripts/methodology-go.ps1` + skill `methodology-go` + verificar hook | 1 trigger roda todo o bootstrap idempotente | M1–M6 |
| `SPR-M8` ✅ | 4 Painel | Painel "status" | skill/script que cruza `BOARD.md` × `gh pr list` × CI | "status" → 1 tela (DOING/REVIEW/BLOCKED + o que pede você) | M2 |
| `SPR-M9` ⛳ | 5 Paralelismo | `/delegate` padrão | validar 1 piloto (`SPR-G6`) + documentar fallback worktree | 1 PR criado via `/delegate` | M1–M3 |
| `SPR-M10` ✅ | 5 Segurança | Sandbox do executor | padronizar `/sandbox enable` (ou `copilot --cloud`) p/ executores | executor sem rede/prod | — |
| `SPR-M11` ⛳ | 5 Segurança | Permissions hardening | `permissions-config.json` (tirar push/ssh/Remove-Item) **ou** só worktree+sandbox | executor sem push/ssh pré-aprovado | M10 |
| `SPR-M12` ⛳ | 6 Esteira | Imagem versionada (GHCR) | CI build+push GHCR + host puxa + path-filter (liga `SPR-G3`) | imagem digest-pinned; docs/sprints não reiniciam prod | M5,M6 |
| `SPR-M13` ⛳ | 6 Automação | Auto-merge opcional | `gh pr merge --auto` p/ sprints flag-OFF (opt-in 100% hands-off) | PR verde mescla sozinho | M5 |
| `SPR-M14` ✅ | 7 Onboarding | Guia da metodologia | `sprints/README.md` + atualizar `AGENTS.md`/`README.md` (aberturas, status, GO) | novo dev/agente entende em 1 leitura | M1–M8 |

### 8.3 Ordem & o que pede seu aceite (no PLAN, não no meio)
- **Caminho mínimo p/ "nativo + seguro":** M1→M2→M3→M4→M6→M7 (núcleo + guardrails locais + CI + comando GO). Depois disto, **toda sessão futura já nasce configurada** e o GO existe.
- **Aceites ⛳ (decididos no PLAN, 1× cada):** M5 (branch protection — escrita GitHub), M9 (`/delegate` — cria PR), M11 (mexe nas suas permissões), M12 (registry/deploy), M13 (auto-merge). No GO eles rodam sozinhos; o aceite é prévio, não um prompt no meio.
- **Paralelizável** (locks disjuntos): {M1,M2,M3} ∥ {M4} ∥ {M6}; M7/M8 dependem do núcleo; M9–M14 depois.

> Backlog completo desta implantação: **§8**. O GO playbook operacional (o que a sequência executa): **§6**.

---

### Apêndice — fontes
- Doc oficial: `use-copilot-cli` (custom agents repo/user/org; skills `SKILL.md` name/description/`allowed-tools`; `/sandbox`; `/delegate`; `/every`); `cli-config-dir-reference` (hooks = scripts user-level; permissions por projeto).
- Local: `~/.copilot/{config.json,permissions-config.json,settings.json,skills/,agents/,hooks/}`; `fluxo_mental_24.md` §10–§12.
