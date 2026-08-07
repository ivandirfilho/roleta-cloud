# ADENDO 06/08/2026 (noite) — Ciclo zero-humano: auto-merge, ativação por PR, main-red

**Origem:** continuação da sessão `ivandirfilho-fix-fluxo-ci-governanca` (PR #62), a pedido
explícito: *"não quero ter nenhuma ação humana; a estrutura tem que ser resolvida pela IA no
próprio modelo de fluxo"*.
**Escopo:** processo/CI/configuração do GitHub. Zero mudança de runtime.

## Por que os merges de 04-06/08 "não rodaram"

O fluxo anterior parava em dois degraus humanos que nunca aconteceram:
1. **Merge**: executores abriam PR e paravam (correto), mas ninguém regia o trem → PRs
   acumularam, divergiram e conflitaram entre si.
2. **Ativação**: tudo nasce flag default-OFF (correto), mas ligar a flag era "decisão humana"
   sem dono nem prazo → V1/V2/V4 deployados e **inertes**, relógios de gate nunca iniciados.

## Decisões (todas já aplicadas)

| # | Decisão | Materialização |
|---|---|---|
| 1 | **Auto-merge nativo do GitHub** — executor arma `gh pr merge --auto --squash` ao abrir o PR; mergeia sozinho com `ci-ok` verde | setting `allow_auto_merge=true`; regra nos agentes/skills/instruções |
| 2 | **`strict` OFF por design** — com strict:true, o update-branch pós-cada-merge exigiria humano (ou PAT); sem ele o auto-merge flui | branch protection `required_status_checks.strict=false` (o check `ci-ok` continua obrigatório) |
| 3 | **Rede contra merge skew** (troca consciente pelo strict): matrix completa roda no push de `main`; se quebrar, o job `main-red-alert` abre issue `main-red` sozinho (dedup: 1 aberta por vez) → vira sessão de agente para revert/fix-forward. Camadas: tudo flag-OFF + deploy 2min + revert 4min | `ci.yml` job `main-red-alert`; label `main-red` |
| 4 | **Ativação é PR, não pendência humana** — política: flag **shadow/audit** (sem efeito em aposta) liga imediatamente via PR `flag/ativar-<slug>` (default `:-1}` na compose + adendo + auto-merge); flag de **comportamento** liga quando a janela shadow do adendo fechar limpa | instruções/agentes; primeiro exemplar: `flag/ativar-audit-shadow` |
| 5 | **`delete_branch_on_merge=true`** — branch de PR morre no merge (fim dos órfãos; `spr/SPR-V1`/`spr/SPR-V2` deletados manualmente hoje) | setting do repo |
| 6 | **Diretor deixa de "reger o trem"** (agora é automático) e passa a cuidar do que o auto-merge não resolve: CONFLICTING, vermelho real, issues `main-red`, relógios no board | `sprint-director.md` |

## O único degrau humano restante (físico, não de processo)

Instalar/recarregar a **extensão Chrome 3.10.0 no navegador do operador** — pré-requisito do
relógio V1/V2 (`SDA_PHASE_BUFFER_SYNC`). Software não instala extensão unpacked no Chrome de
terceiros; é ação física do operador, como trocar um cabo. Tudo o mais roda sem humano.

## Reversão

- Auto-merge/strict/delete-branch: settings do GitHub (1 chamada de API cada).
- `main-red-alert`: revert do PR.
- Política de ativação: revert dos arquivos de instrução.

## Lição ISO

**ISO/IEC 25010 – Confiabilidade (recuperabilidade) + 14764:** automação de integração sem
automação de *recuperação* só move o gargalo humano do merge para o incidente. O par
auto-merge ⇄ main-red-alert fecha o ciclo: o mesmo fluxo que integra sem humano também
converte falha de integração em unidade de trabalho para agente, mantendo o humano fora do
caminho crítico em ambos os sentidos.
