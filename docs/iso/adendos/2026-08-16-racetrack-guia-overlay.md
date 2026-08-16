# ADENDO — 2026-08-16 · Roletinha guia (racetrack) no overlay minimizado da Escuta Beat

> **Origem:** SPR-X5 (bloco BLK-A, P0) · PR `SPR-X5: racetrack guia no overlay minimizado`.
> Pedido do operador em 16/08; decisões de UX fechadas pelo Diretor no brief
> `sprints/SPR-X5.md`. Extensão **3.10.0 → 3.11.0**.

## 1. O que mudou e por quê (decisão, não diff)

Quando o overlay da Escuta Beat recebe sugestão `APOSTAR`, o quadro **minimizado**
passa a exibir uma **mini-roleta racetrack** (SVG 760×210, espelho do widget de
vizinhos da Evolution) logo abaixo da linha `[C1] [C2] [C3]`: os 17/21 números
cobertos (`sugestao.numeros`) acendem em **amarelo** (`.active`) e os 3 centros
(`centrosFromSugestao`, fonte única c2/c3/c1) ganham **destaque forte**
(`.active-center`: stroke branco + glow maior + número maior). Objetivo: o
operador localiza em **<1s** onde clicar na mesa real.

Decisões estruturais relevantes:

- **Ordem física canônica** (37 casas, doada pelo operador): top L→R
  `24,16,33,1,20,14,31,9,22,18,29,7,28,12,35` · arco direito `3/26/0` · bottom
  R→L `32,15,19,4,21,2,25,17,34,6,27,13,36,11,30` · arco esquerdo `8/23/10/5`.
  Geometria: `R_OUT=95, R_IN=50, CY=105, CX_L=95, CX_R=665, SLOT_W=38`. O SVG é
  gerado por **função pura** (`buildRacetrackSVG`) a partir desses dados locais —
  sem `<script>` injetado, sem innerHTML de fonte externa (o HTML standalone do
  operador ficou como referência no PR, não foi colado cru).
- **Não-interativa:** o contêiner `#eb-racetrack` é **irmão** de `.eb-panel`
  (o root do overlay já é `pointer-events:none`), então o clique **atravessa de
  verdade** para a mesa da Evolution — dentro do painel (`pointer-events:auto`)
  ele seria capturado. O listener de clique do HTML original NÃO foi portado.
- **Helper único** `renderMiniRacetrack(sugestao)` usado pelos **3 writers** do
  minimizado — `toggleMinimize`, `updateOverlay` e `handleStateSync` (heartbeat)
  — e pela limpeza (`handleNewSession`/`handleSessionReset`, via `null`). Lição
  das "3 telas" divergentes de 05/08: um formato, uma fonte, zero divergência.
  Assinatura interna (`dataset.ebRtSig`) evita re-render no heartbeat de 1s.
- **Ciclo de vida:** acende só com `acao==='APOSTAR'`; `PULAR`/`AGUARDAR`/reset
  de sessão limpam/escondem. Degrada limpo: payload sem `numeros` acende só os
  centros; sem centros e sem números, esconde (payload do servidor NÃO mudou —
  mudança 100% client-side e retro-compatível).
- **Escopo de vista:** entregue **só no minimizado** (decisão 6 do brief era
  "expandido opcional, só se couber limpo" — a vista expandida já mostra os 17
  números em texto no `#eb-regiao`; a roletinha lá poluiria).
- **Largura:** `.minimized .eb-panel` foi de 200px → **240px** (220px no mobile
  ≤768px) — dentro da faixa 200–250px autorizada pelo Diretor. Rótulo numérico
  **apenas nos 3 centros** (auditoria SPR-U1, item 1: legibilidade dos acesos >
  completude a ~220px; acesos comuns = amarelo puro, apagados = só cor).

## 1b. Refinamentos da auditoria SPR-U1 (incorporados neste mesmo PR)

A auditoria de UX (SPR-U1) confirmou a decisão do racetrack e trouxe 4
refinamentos, todos incorporados:

1. **Número só nos 3 centros** (acima).
2. **Consolidação dos DOIS blocos CSS `.minimized` duplicados** num bloco único
   declarado ANTES da media query mobile — corrige de quebra um bug real: a
   regra mobile de 220px era **morta** (mesma especificidade, fonte anterior à
   duplicata tardia; media query não soma especificidade). Sem mudança visual
   no desktop; no mobile o pill minimizado passa a respeitar 220px.
3. **Desconexão limpa o racetrack** (achado OV-01 P0): `showConnectionStatus(
   connected===false)` chama `renderMiniRacetrack(null)` — o guia nunca fica
   aceso com sugestão velha de servidor morto ("brilhar mentira"). Reconectar
   NÃO reacende sozinho; o próximo `updateOverlay`/`state_sync` reacende. O
   estado de erro completo do overlay virá no SPR-UX-CONN.
4. **Clamp do drag nos dois eixos** (`setupDrag`): com o racetrack o pill fica
   ~2× mais alto e dava para empurrar o overlay para fora da borda inferior;
   agora `right`/`top` são limitados ao viewport (`offsetWidth/offsetHeight`).

## 2. Flags criadas/alteradas e default

**Nenhuma flag na compose.** Guia **passivo de exibição**, sem efeito em aposta,
stake ou estratégia — não é comportamento de motor, logo não exige flag
server-side (decisão 5 do brief). A "flag" client-side é o próprio **toggle 🎡**
no header do overlay, persistido em `chrome.storage.local` (`overlayUIState.
racetrackEnabled`, padrão `loadUIState`/`saveUIState`), **default ON**; estado
ausente/legado ⇒ ON. Espelho Azure: n/a (compose intocada).

## 3. Como reverter (rollback)

1. **Kill-switch do operador:** toggle 🎡 OFF esconde o racetrack na hora
   (persiste entre reloads).
2. **Revert do PR** (`git revert`, ~4 min até o deploy) — mudança aditiva no
   overlay; a extensão 3.10.0 anterior continua 100% funcional (payload
   inalterado, nada no servidor depende do racetrack).
3. Após revert, recarregar a extensão unpacked no Chrome (`chrome://extensions`
   → Reload).

## 4. Validação registrada

- `pytest tests/ --ignore=tests/test_obs_reload.py` **verde** (suíte Python não
  regride — mudança só em `extension/`).
- `node --test tests/js/*.test.js` verde (job JS do CI).
- Servidor de produção estava **FORA (502)** — não bloqueou: validação
  client-side com payload sintético do brief (passo 5) em harness com stub de
  `chrome.*` + o `content.js` REAL: **28/28 checks** (ordem física com 0 entre
  26 e 32, 17 acesos + 3 centros fortes, formato único do pill intacto,
  PULAR/AGUARDAR/reset limpam, toggle persiste após reload, degradação limpa,
  desconexão limpa/reconexão só reacende com dado novo)
  e screenshots headless (Edge) das cenas APOSTAR/PULAR/OFF/expandido/mobile +
  **prova de click-through** via `elementFromPoint` ⇒ `hit=click-probe · OK`.
  Evidências coladas no `## Log` do brief.

## 5. Lições ISO 25010/14764

- **Usabilidade (25010):** guia espacial reduz o tempo de localização do clique
  — o racetrack do overlay espelha 1:1 o widget da mesa, eliminando a tradução
  mental "número → posição física".
- **Manutenibilidade (14764):** repetir o padrão "helper único para N writers"
  (já provado no `minimizedStatusHTML` de 05/08) impediu, por construção, a
  reintrodução da classe de bug "3 telas". Writers novos do minimizado DEVEM
  passar por `renderMiniRacetrack`/`minimizedStatusHTML`.
- **Portabilidade:** mexeu em `extension/` ⇒ bump `manifest.version` (3.11.0) e
  **nota de reload**: o Chrome só aplica content script novo após Reload da
  extensão em `chrome://extensions` (unpacked) — registrado no Log do brief.
