# SPR-U1 · Auditoria UX sênior do front (Glass Box + popup + overlay Escuta Beat) · Bloco BLK-A/L · Pri P1

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Pedido do operador 16/08: "senior em front" testando cada item/modo de interação do app
> e da extensão — melhorias, usos inadequados, bugs e mal-funcionamentos.

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []
locks:      []            # entrega = 1 arquivo NOVO de docs; ZERO mudança de código
touches:    [docs/ux/2026-08-16-auditoria-ux-front.md (novo)]
base_sha:   origin/main
branch:     o branch da PRÓPRIA sessão (spr/SPR-U1 contém este brief; PR com título `SPR-U1:`)
```

## Objetivo (1 frase)
Relatório de auditoria UX/qualidade-front acionável cobrindo **todas** as superfícies de
interação (dashboard Glass Box `frontend/`, popup `extension/popup.*`, overlay
`extension/content.js`+`overlay.css` nos modos expandido/minimizado/painel de controle),
classificando achados por severidade e propondo sprints candidatos.

## Escopo e método (walkthrough dirigido por código + execução local quando possível)
1. **Inventário de interações** — para CADA elemento interativo, documentar: o que faz,
   estados possíveis, feedback ao usuário, falhas. Superfícies:
   - Overlay expandido: header (status/role ⚡/🔄 nova sessão/🎯 force master/− minimizar),
     corpo (Último, região/centros force17, veredito, gale, aposta, barra de confiança,
     timer), botão 🎛️ Controles + seção de controle (LED conexão, mesa/📸 captura,
     ▶️/⏹️, grid de resultados).
   - Overlay minimizado: pill `[C1] [C2] [C3]` + badge 17/21 + gale; drag; reaparecimento.
   - Popup (`popup.html/js`): conexão, mesas, logs, versão vs overlay (duplicação?).
   - Glass Box (`frontend/`): status ONLINE/OFFLINE, fluxo escuta→server→sda→overlay,
     cards de spin/resultado, barras CW/CCW, métricas, trace, logs, performance/martingale.
2. **Matriz de estados**: {AGUARDANDO, APOSTAR, PULAR} × {expandido, minimizado} ×
   {conectado, desconectado, reconectando} × {com/sem sugestão em cache} — o que o usuário
   vê em cada célula? Onde a informação mente (ex.: sugestão velha após desconexão)?
3. **Bugs candidatos já suspeitados pelo Diretor (verificar, achar mais):**
   - `frontend/app.js:277` — status ONLINE usa "⚫ ONLINE" (bolinha PRETA para online;
     CSS pinta, mas o glifo textual é idêntico ao OFFLINE — acessibilidade/clareza).
   - `extension/content.js:510-538` — `setupDrag` só escuta `touchstart/move/end`:
     **sem drag por mouse no desktop** (operador usa desktop!).
   - Overlay some/anima em `pointer-events: none` no contêiner raiz + `auto` no panel —
     verificar zonas mortas de clique (mudar aba da mesa com overlay por cima).
   - 3 writers do minimizado (lição 05/08) — conferir se `handleStateSync` heartbeat ainda
     pode divergir do formato único em edge-cases (sem sugestão em cache, v5_mode null).
   - Reconexão: `RECONNECT_INTERVAL` fixo 5s no dashboard (sem backoff/jitter); o que a
     extensão faz (`background.js`)? Tempestade de reconexão quando o servidor volta?
   - `innerHTML` com payload do servidor (`buildForce17HTML`, logs do dashboard) —
     sanitização? (payload é nosso, mas via WS público — XSS surface, severidade honesta).
   - Estado `WAITING/AGUARDANDO` com timer "Conectando..." permanente quando o servidor
     está fora (caso REAL de hoje: /ws 502) — o usuário não distingue "sem sugestão" de
     "sem servidor". Proposta esperada: estado de erro explícito no overlay minimizado.
   - Duplicação popup × seção de controle do overlay (v5.0): fontes de verdade divergem?
4. **Execução local:** dashboard = abrir `frontend/index.html` (vai ficar OFFLINE — o
   servidor está 502 hoje; avalie exatamente essa jornada de erro!). Extensão = unpacked +
   payload sintético no console (`updateOverlay({...})` — exemplos no brief SPR-X5).
5. **Heurísticas:** Nielsen (visibilidade de status, prevenção de erro, reconhecimento),
   Fitts (alvos de clique <1s em jogo ao vivo), contraste/legibilidade (fundo de cassino),
   latência percebida (feedback em <100ms nos toggles).

## Entregável ÚNICO
`docs/ux/2026-08-16-auditoria-ux-front.md`:
- Sumário executivo (≤15 linhas) · Matriz de estados · Tabela de achados:
  `ID | Severidade (P0-P3) | Superfície | Evidência (arquivo:linha) | Sintoma | Proposta`
- Seção "sprints candidatos" (agrupamento dos achados em 2-4 sprints coesos com locks) —
  o Diretor decide o que vira brief.
- Validação da decisão do SPR-X5 (racetrack abaixo dos centros no minimizado): confirmar
  ou propor refinamento v2 (não bloqueia o X5).

## Critério de "pronto" (Definition of Done)
- [ ] 100% dos elementos interativos das 4 superfícies inventariados (checklist no doc).
- [ ] ≥1 achado com evidência arquivo:linha por superfície; matriz de estados completa.
- [ ] Jornada "servidor fora" descrita de ponta a ponta com propostas.
- [ ] Zero mudança de código (docs-only). PR pequeno.

## Guardrails (inviolável)
- **NÃO alterar código** — achou bug? vai para a tabela, não para um patch.
- **Sem ssh/produção**; sondas externas só leitura se precisar (curl no domínio público).
- **Git:** só no branch da sessão; PR; nunca `main`. NÃO commitar `graphify-out/`.

## Validação
Docs-only: revisão de consistência (todo achado tem evidência) + links relativos válidos.

## Rollback
`git revert` do PR (arquivo novo, zero risco).

## Conformidade ISO
- [ ] ADENDO dispensado (auditoria é doc, não mudança de sistema) — registrar essa decisão
      no PR body. Se o Diretor discordar, vira adendo curto.

## Closeout
1. Doc completo → commit no branch da sessão (`SPR-U1: auditoria UX front` + trailer
`Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`).
2. Lock check (`gh pr list`) — docs novos não colidem. 3. Push + PR `SPR-U1: ...` +
auto-merge (`gh pr merge --auto --squash <nº>`). 4. Avisar o Diretor com top-3 achados.

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->
