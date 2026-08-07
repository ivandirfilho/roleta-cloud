# ADENDO 07/08/2026 — Instruções nativas de agentes e as três camadas (local · git · Debian)

**Origem:** sessão `governanca/instrucoes-nativas` (fechamento da esteira zero-humano de
06–07/08: PRs #58, #43, #61, #64 mergeados; 0 abertos; main verde).

## 1. O que mudou e por quê

Auditoria das camadas de instrução revelou três lacunas após a virada zero-humano (#62):

1. **`AGENTS.md` não existia na raiz.** O padrão cross-ferramenta (lido por Copilot coding
   agent, Codex, Cursor etc.) não recebia o contrato — só quem carregava
   `.github/copilot-instructions.md` (ecossistema Copilot) conhecia as regras. **Criado**
   como fonte canônica do fluxo: camadas físicas, ciclo de mudança, anti-conflito, lições.
2. **O congelamento do `Manutenabilidade_iso.md` só era declarado na última linha
   (~4039).** Agente lendo o topo não via a convenção e podia apendar de novo. **Corrigido:**
   bloco de STATUS no cabeçalho apontando adendos, `AGENTS.md` e a regra "git = única fonte
   de verdade". Header também deixou de mentir o tamanho da suíte (374 → 1249 testes).
3. **Lições dos merges de 07/08 não estavam em lugar nativo** (só na memória de sessão):
   gate de workflow com secrets (#64), espelho Azure no mesmo PR (#43), resolução
   preservando os dois canais (#58). **Gravadas** em `AGENTS.md` §4 e nos invioláveis.

## 2. Arquitetura de instruções decidida (anti-drift)

| Artefato | Papel | Quem lê |
|---|---|---|
| `.github/copilot-instructions.md` | invioláveis compactos (vencem em conflito) | auto-load Copilot App/CLI/VS Code |
| `AGENTS.md` (raiz) | contrato operacional completo | qualquer agente/ferramenta |
| `.github/agents/*.md` + `.github/skills/*` | papéis Diretor/Executor e rituais | Copilot custom agents |
| `docs/iso/adendos/` | evolução ISO, 1 arquivo por mudança | humanos + agentes (histórico) |
| `~/.copilot/` (máquina local) | prefs pessoais do operador | só a máquina local — NUNCA verdade do projeto |
| Servidor Debian | consumidor cego (`timer → pull main → deploy`) | ninguém edita; leitura via endpoints |

Regra de manutenção: mudou o fluxo → edita `AGENTS.md` por PR e ajusta o resumo dos
invioláveis; skills/agents apontam, não duplicam.

## 3. Flags criadas/alteradas

Nenhuma. (Governança/documentação; a repo variable `AZURE_PUBLISH_ENABLED` do #64 permanece
ausente = OFF até o cutover Azure.)

## 4. Como reverter

`git revert` do PR — docs puros, sem migração, sem flag, sem efeito em runtime.

## 5. Lições ISO 25010/14764

- **Manutenibilidade/Modificabilidade:** convenção que só existe no fim de um arquivo de
  4 mil linhas não é convenção — é armadilha. Contrato tem que estar onde o leitor entra
  (cabeçalho) e no caminho padrão da ferramenta (`AGENTS.md`).
- **Portabilidade do processo:** instruções em pasta local (`~/.copilot/`) não viajam com
  clone/worktree/CI; tudo que define o projeto precisa estar versionado no git.
- **ISO/IEC 14764 (manutenção):** o ciclo pull→PR→auto-merge→deploy com servidor consumidor
  cego elimina a classe inteira de erros de "estado divergente entre máquinas".
