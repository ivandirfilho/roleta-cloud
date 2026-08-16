# instruções_15_08 — Guia do dono (para quem NÃO é programador)

> **Para quem é este arquivo:** você, Ivandir — ou qualquer pessoa leiga que precise
> operar essa infraestrutura. Sem jargão sem explicação. Atualizado em 15/08/2026.
> Documentos técnicos (se um dia quiser aprofundar): `blueprint_roleta_atual.md` (este repo),
> `blueprint_copilot_app.md` e `agente_atual.md` (repo `xmaiatec/Software-House`).

---

## 1. A ideia em uma frase

**Você fala o que quer em português; os agentes de IA fazem o resto — escrevem o código,
testam, revisam, integram e colocam no ar sozinhos.** Você é o dono que decide O QUÊ;
a esteira decide COMO e executa.

```mermaid
flowchart LR
    A["🗣️ Você pede<br/>(em português)"] --> B["🤖 Agente trabalha<br/>numa cópia isolada"]
    B --> C["📋 PR<br/>(pedido de integração)"]
    C --> D["✅ Testes automáticos<br/>(CI)"]
    D --> E["🔀 Integra sozinho<br/>(auto-merge)"]
    E --> F["🚀 No ar em ~2 min<br/>(deploy automático)"]
```

## 2. As três camadas (onde as coisas vivem)

| Camada | O que é | Analogia | Você mexe? |
|---|---|---|---|
| **Seu computador** | onde os agentes trabalham (cópias descartáveis do projeto) | bancada de trabalho | Só conversando com o Copilot App |
| **GitHub** | a ÚNICA verdade: código, regras, histórico | cartório + linha de montagem | Só por PR (o agente faz) |
| **Servidor (produção)** | roda o sistema de verdade; se atualiza sozinho a cada ~2 min | vitrine da loja | **NUNCA. Ninguém mexe — nem você, nem agente** |

**Regra de ouro:** se algo só existe no seu computador, não existe. Se está no GitHub
(na `main`), está no ar em ~2 minutos.

## 3. Como usar o GitHub Copilot App (o dia a dia)

1. **Abra o app** e escolha o projeto (ex.: *Roleta Cloud*).
2. **Nova sessão** — cada sessão é uma bancada limpa e isolada. Pode abrir várias ao
   mesmo tempo sem medo: elas não se atrapalham (cada uma trabalha numa cópia própria).
3. **Fale em português, como falaria com um funcionário sênior.** Não precisa termo
   técnico. Diga a DOR ou o DESEJO, não a solução:
   - ✅ "os giros estão demorando para aparecer no painel"
   - ❌ "otimize o websocket handler" (deixe o agente decidir o como)
4. **O agente devolve um plano ou executa.** Se ele perguntar algo, responda — é a única
   "aprovação" que existe.
5. **Fim natural de toda tarefa = um PR com integração automática.** Você não precisa
   apertar nada: quando os testes passam, integra e vai pro ar sozinho.

### Frases prontas que funcionam (copie e cole)

| Você quer… | Diga na sessão… |
|---|---|
| Saber como está tudo | `status` |
| Corrigir um problema | `Dor: <descreva o que está errado ou incomodando>` |
| Uma melhoria/ideia nova | `Plano para <sua ideia>` (ele propõe sprints antes de mexer) |
| Executar um sprint já planejado | `Rodar SPR-X` |
| Rodar vários trabalhos em paralelo | `GO` (dispara a metodologia de sprints) |
| Entender qualquer coisa do sistema | `Me explique como funciona <tema>` |
| Auditar/melhorar a governança | `bootstrap de governança no repo <nome>` |

## 4. Quem são os agentes (e quem chama quem)

Você não precisa escolher agente — **fale normal e o orquestrador roteia sozinho**.
Mas saber quem existe ajuda a entender o que está acontecendo:

### No Roleta Cloud
| Agente | Papel | Como acionar |
|---|---|---|
| **Diretor de Sprints** | planeja, abre briefs, acompanha o board — NÃO programa | `Dor: …`, `Plano para …`, `status` |
| **Executor de Sprint** | pega UM sprint e leva até o PR integrado | `Rodar SPR-X` (o Diretor delega sozinho) |

### Na empresa (xmaiatec/Software-House)
| Agente | Papel | Como acionar |
|---|---|---|
| **arquiteto-plataforma** | desenha/audita a arquitetura, mantém o blueprint | "audite a governança", "repo novo" |
| **executor-core** | implementa uma tarefa e entrega por PR | qualquer pedido de implementação |
| **evolucao-continua** | transforma lições aprendidas em melhorias das regras | "destile as lições da semana" |

## 5. Repositório por repositório — como interagir

### 🎰 `ivandirfilho/roleta-cloud` (o produto principal)
- **O que é:** backend da roleta em tempo real + extensão Chrome. **A `main` É a produção**
  — servidor Debian puxa e deploya sozinho a cada ~2 min.
- **Como pedir mudanças:** abra sessão no projeto *Roleta Cloud* e use as frases da §3.
  Toda mudança de comportamento nasce DESLIGADA (atrás de "flag") e é ligada depois por
  outro PR automático — por isso é seguro pedir qualquer coisa.
- **Acompanhar:** pergunte `status` (cruza board, PRs e testes) — ou olhe
  `sprints/BOARD.md` no GitHub.
- **Se quebrar:** o próprio sistema abre uma issue chamada `main-red` e qualquer agente
  a trata como prioridade máxima. Você não precisa fazer nada além de, se quiser,
  abrir uma sessão e dizer "resolva a main-red".

### 🏭 `xmaiatec/Software-House` (a fábrica da empresa)
- **O que é:** a plataforma-modelo com os 3 agentes da empresa, os blueprints e a
  linha de montagem (workflows numerados 00–99).
- **Como pedir:** issues criadas lá seguem um rito (o robô orienta com comentário se
  faltar algo — não fica mais vermelho à toa). Para trabalho grande: abra sessão e
  descreva; o agente cria a issue no formato certo sozinho.

### 🗂️ Demais repos da xmaiatec (`Agente_Github`, `AWS_Managment`, `Azure_Terraform`, `xmaia-sentinel`, `sistema-de-gesto-de`)
- Todos já têm o "kit de governança" instalado (contrato de agentes + testes + proteção).
- Interação idêntica: abra sessão no repo → fale o que quer → PR automático.
- `xmaiatec/.github` guarda os padrões da empresa — repo novo? Diga
  `bootstrap de governança` que o agente instala o kit e o repo nasce no padrão.

## 6. As 7 regras de ouro do dono

1. **Nunca peça para "mexer direto na main" ou "entrar no servidor".** Os agentes vão
   recusar — é por design. Tudo passa pela esteira (PR → testes → auto-merge → deploy).
2. **Não aprove nada manualmente no GitHub.** Se um PR está parado, a pergunta certa na
   sessão é: "por que o PR #X não integrou?"
3. **Uma sessão = um assunto.** Quer 3 coisas? Abra 3 sessões (ou diga `GO` e deixe o
   Diretor paralelizar com segurança).
4. **Erro em produção não é emergência sua.** Vira issue `main-red` automática; reverter
   leva ~4 min. Você só orienta prioridade se quiser.
5. **E-mails do GitHub:** falha VERMELHA só importa se for na `main` (aí já existe issue
   cuidando). O resto é informativo — a política anti-ruído mantém ≤1 aviso por PR.
6. **Decisões de negócio são SUAS** (ligar comportamento novo, arquivar repo, dar acesso
   a alguém). Os agentes preparam tudo e te perguntam — responder a pergunta É a aprovação.
7. **Tudo fica registrado sozinho** (adendos, board, memória dos agentes). Não precisa
   anotar nada — pergunte "o que foi feito ontem?" em qualquer sessão.

## 7. Se algo parecer estranho — roteiro de 3 passos

1. Abra uma sessão no projeto e pergunte: **`status`**
2. Se houver problema, diga: **"investigue e resolva pela esteira"** (ele acha a causa,
   corrige por PR e te mostra o resultado)
3. Nada resolve? Diga: **"reverta a última mudança"** — voltar atrás é barato (~4 min)
   e sempre seguro.

## 8. Glossário de bolso

| Termo | Tradução |
|---|---|
| **PR (Pull Request)** | pedido formal de integração — o "pacote" de uma mudança |
| **Merge / auto-merge** | aceitar o pacote na linha oficial — aqui é automático quando os testes passam |
| **CI / ci-ok** | bateria de testes automáticos; `ci-ok` verde = aprovado |
| **main** | a linha oficial do código = o que está em produção |
| **Deploy** | colocar no ar (aqui: automático, ~2 min após o merge) |
| **Flag** | interruptor de comportamento; tudo novo nasce desligado |
| **Worktree / sessão** | bancada isolada onde o agente trabalha sem afetar o resto |
| **Issue `main-red`** | alarme automático de "produção quebrou" — já nasce com dono |
| **Sprint / brief** | pacote de trabalho planejado (`sprints/SPR-*.md`) |
| **Adendo** | registro histórico de uma mudança (`docs/iso/adendos/`) |

---

## 9. Perguntas do dono — respondidas (15/08, noite)

### 9.1 "O Software-House configura tudo? Devo abrir a main por lá?"

**Não — e essa é a confusão mais importante de desfazer.** O Software-House é a
**fábrica-modelo**: guarda os blueprints, os 3 agentes da empresa e o rito. Ele NÃO
configura os outros repos sozinho. Quem faz cada papel:

| Papel | Quem faz |
|---|---|
| **Guardar o padrão** (blueprints, agentes-modelo, rito) | `Software-House` |
| **Distribuir o padrão** (instruções que todo repo da org recebe + kit de templates) | `xmaiatec/.github` |
| **Obrigar o padrão** (trava da org: PR obrigatório, squash, sem force-push) | **Ruleset da org** — desde hoje vale para TODOS os repos, inclusive os que você criar amanhã |
| **Instalar o padrão** num repo (CI, contrato de agentes, proteção) | você dizer **"bootstrap de governança"** numa sessão |

**"Abrir a main por lá" não existe:** cada produto tem a própria `main`. Regra prática —
**abra a sessão no repo do ASSUNTO**:

| Assunto | Onde abrir a sessão |
|---|---|
| Roleta (produto, apostas, painel, extensão) | projeto **Roleta Cloud** |
| Governança da empresa, novos padrões, agentes corporativos | **Software-House** |
| Infra AWS / Terraform / sentinel / gestão | o repo correspondente |
| Repo novo | crie o repo → abra sessão nele → `bootstrap de governança` |

### 9.2 "O que já está configurado no roleta-cloud?"

É o repo mais completo (o piloto que provou o modelo). Checklist do que JÁ existe:

| ✅ | O quê |
|---|---|
| ✅ | Contrato de agentes (`AGENTS.md`) + invioláveis auto-carregados (`.github/copilot-instructions.md`) |
| ✅ | Papéis: Diretor de Sprints + Executor (`.github/agents/`) e skills `GO`/`status`/executor |
| ✅ | Esteira completa: testes obrigatórios (`ci-ok`), auto-merge, anti-fila (`concurrency`), alarme `main-red`, guardrails ISO |
| ✅ | Deploy automático (~2 min) com rollback; flags default-OFF; espelho Azure forçado por teste |
| ✅ | Registro histórico (adendos ISO) + board de sprints + memória de agentes |

### 9.3 "Projeto novo já herda configurações nativas?"

**Herda automaticamente** (sem fazer nada):
- Instruções org-wide do Copilot (vêm do `xmaiatec/.github`);
- A trava da org (PR obrigatório, squash, sem apagar branch) — **corrigido hoje**: antes
  valia só para 5 repos listados; agora vale para todos, inclusive futuros;
- O plano Enterprise (Copilot, modelos, etc.).

**NÃO herda sozinho** (é o papel do bootstrap — 1 frase, ~5 min):
- CI com `ci-ok` + `main-red` · contrato `AGENTS.md` do domínio · proteção da main ·
  auto-merge ligado · pasta de adendos.

**Ritual do repo novo:** criar → abrir sessão → dizer `bootstrap de governança` → o PR
instala tudo e integra sozinho.

### 9.4 "Os MCPs estão instruídos em cada repositório novo?"

**MCPs não moram nos repos — moram na SUA máquina** (`~/.copilot/`). Por isso **todo
projeto, novo ou velho, já nasce com os 8 MCPs funcionando** (memória, grafo de código,
arquivos, buscas etc.) e com as skills que ensinam QUANDO usá-los (ex.: "grafo antes de
busca cega"). Não há o que instalar por repo.

Só existe UM caso para configurar MCP dentro de um repo: ferramenta específica daquele
projeto (ex.: banco de dados próprio) — aí o agente cria `.github/mcp.json` nele. Hoje
nenhum repo precisa disso.

### 9.5 "Como evoluem técnicas e tecnologias ao longo do tempo?"

Existe um **ciclo de aprendizado** rodando:

```mermaid
flowchart LR
    A["Sessões de trabalho<br/>(lições, incidentes)"] --> B["Memória + adendos<br/>(registro automático)"]
    B --> C["Agente evolucao-continua<br/>destila em melhorias"]
    C --> D["PR atualiza regras,<br/>skills e agentes"]
    D --> E["Kit de bootstrap atualizado<br/>(xmaiatec/.github)"]
    E --> F["Repos novos já nascem<br/>com a lição aprendida"]
```

Exemplo real: um workflow quebrou a `main` do roleta por falta de senha externa (PR #64)
→ em 24h virou regra do kit ("workflow com segredo nasce desligado") → nenhum repo novo
repete o erro. **Hoje o ciclo roda quando você pede** ("destile as lições da semana").
A recomendação da 9.7 é agendar isso.

### 9.6 "Vale a pena um framework/script de funcionamento no Software-House?"

**Sim — é o próximo passo natural (Fase 2.1).** Hoje o kit de bootstrap vive em
templates no `xmaiatec/.github` + uma skill **na sua máquina**. Funciona, mas depende do
seu computador. O upgrade certo: um **workflow versionado no Software-House**
("bootstrap-repo": você escolhe o repo alvo, ele abre o PR com o kit sozinho) — assim a
fábrica instala o padrão a partir do próprio GitHub, de qualquer lugar, sem depender da
sua máquina. Peça **"crie o workflow de bootstrap na fábrica"** quando quiser ativar.

### 9.7 "Vale a pena automations dentro do GitHub Copilot App?"

**Sim, para as SUAS rotinas** (o que valida código já é automático no GitHub). Regra de
bolso: **código → CI no GitHub · rotina do dono → workflow do App**. As 4 que valem ouro:

| Automation (no App) | Frequência | O que faz |
|---|---|---|
| Painel matinal | diária | roda `status` no roleta + PRs/issues abertas e te deixa o resumo pronto |
| Scanner de conformidade | semanal | refaz a auditoria da org (a mesma da issue #37) e aponta drift |
| Evolução contínua | semanal | roda o ciclo da 9.5 sem você pedir |
| Vigia main-red | diária | se houver issue `main-red` aberta, abre sessão e resolve |

Peça **"crie as automations do App"** que eu configuro as quatro na hora.
