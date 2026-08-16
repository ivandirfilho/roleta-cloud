# ADENDO ISO — 2026-08-16 · Rotinas ISO nativas nas camadas de instrução (pós-mortem do ciclo 16/08)

**Origem:** pergunta do dono ("por que as PRs não atualizaram as estruturas segundo o ISO?
como incorporar de forma nativa?") + 3 lições do ciclo 16/08. PR de governança único.

## 1. O que mudou e por quê (decisão, não diff)

O ciclo 16/08 (SPR-U1/D1/X5/D2 + incidente 502) provou que as rotinas ISO **documentais**
rodaram (3 adendos novos), mas três rotinas **operacionais** não estavam encodadas em camada
nenhuma — cada uma falhou de forma silenciosa:

1. **Base do PR**: 2 executores abriram PR com base `spr/<ID>` (herdada da sessão);
   auto-merge executou sem CI e o trabalho não chegou à main.
2. **Última milha**: artefatos consumidos fora do git (entrypoint systemd, `roleta.conf`,
   extensão do operador em `Desktop\Roleta Cloud\extension`) não recebiam os merges —
   *mergeou ≠ implantado* (3 casos no mesmo dia).
3. **Skip silencioso em harness**: cenário de teste que se auto-pulava imprimindo PASS
   (*suíte verde ≠ cenário testado*).

**Correção estrutural:** as três rotinas viraram texto nas camadas que os agentes JÁ
carregam automaticamente — nenhuma depende de memória de sessão:

| Camada | Carregada por | O que ganhou |
|---|---|---|
| `.github/copilot-instructions.md` | toda sessão Copilot (auto) | base main no fluxo do executor; inviolável "última milha é parte da entrega" |
| `AGENTS.md` §2/§4 | qualquer agente que leia AGENTS.md (nativo) | passo 7 com base main; 3 lições novas no §4 |
| `.github/agents/sprint-executor.md` | agente de papel (kickoff) | passo 8 com `--base main` + verificação |
| `.github/agents/sprint-director.md` | agente de papel (kickoff) | `baseRefName != main` = entrega FALSA; checklist de última milha no closeout |
| `sprints/_BRIEF_TEMPLATE.md` | todo brief novo | closeout 7 com `--base main` + verificação |
| `.github/workflows/iso-guardrails.yml` | CI de todo PR → main | ADENDO deixou de ser *warning*: **erro bloqueante** em mudança de comportamento sem `docs/iso/adendos/*.md` novo (exceção: títulos `Revert*` — emergência main-red) |

## 2. Por que `Manutenabilidade_iso.md` não é editado nas PRs (resposta canônica)

O singleton está **congelado desde 06/08** (era o maior ímã de conflito do repo). A rotina
ISO viva é: **um arquivo novo por mudança** em `docs/iso/adendos/` (convenção no README da
pasta). O guardrail agora aponta para lá e rejeita append no singleton como cumprimento.

## 3. Flags criadas/alteradas

Nenhuma flag de compose. O guardrail de CI endureceu (warning → error) — mitigado pela
exceção de revert para não travar recuperação de main-red.

## 4. Como reverter

`git revert` do PR (texto de instrução + 1 workflow; sem efeito em runtime de produção).
Para voltar o guardrail a advisory: trocar `::error` + `exit 1` por `::warning`.

## 5. Lições ISO 25010/14764

- **Manutenibilidade:** regra que vive só na cabeça do orquestrador não é regra — é sorte.
  Encodar nas camadas auto-carregadas é o equivalente agêntico de "shift-left".
- **Confiabilidade:** guardrail advisory que nunca bloqueia não muda comportamento de
  agente autônomo; gate que bloqueia com exceção de emergência sim.

## 6. Replay envelope (D7)

Modelo: Claude Fable 5 (Diretor, sessão "Roletinha guia + UX") · MCPs: memory,
sequential-thinking, graphify, github · ~10 turnos nesta entrega · ~25 min · gatilho:
pergunta de governança do dono em 16/08 ~11:38 BRT.
