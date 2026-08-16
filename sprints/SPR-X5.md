# SPR-X5 · Roletinha guia (racetrack) no overlay minimizado da Escuta Beat · Bloco BLK-A · Pri P0

> **Brief auto-contido para um agente EXECUTOR em sessão nova.** Não exige contexto prévio.
> Fonte/visão: `fluxo_mental_24.md` (§1.A extensão), pedido do operador em 16/08.

## Meta (o Diretor preenche; o executor respeita)
```text
blocked_by: []           # nenhum — client-side puro, NÃO depende do servidor estar de pé
locks:      [extensão-JS]   # content.js + overlay.css + manifest (serializa com V6A/X1..X4/V5)
touches:    [extension/content.js, extension/overlay.css, extension/manifest.json]
base_sha:   origin/main
branch:     o branch da PRÓPRIA sessão (spr/SPR-X5 já existe com este brief — NÃO renomeie
            para ele; abra o PR do branch da sessão com título `SPR-X5:`)
```

## Objetivo (1 frase)
Quando o overlay recebe sugestão `APOSTAR`, mostrar uma **mini-roleta racetrack** com as
regiões **acesas** logo **abaixo da linha dos números centrais** no quadro **minimizado**,
para o operador localizar em <1s onde clicar na mesa real (o racetrack espelha o widget de
vizinhos da Evolution).

## Código doado pelo operador (adaptar, não copiar cru)
O operador forneceu um HTML standalone com racetrack SVG **760×210** (viewBox `0 0 760 210`),
37 casas na ordem física da roleta europeia (15 top + arco direito 3/26/0 + 15 bottom + arco
esquerdo 8/23/10/5), API `window.RacetrackAPI.highlight([...])/clear()`, classe `.active`
(amarelo #ffe600 + drop-shadow) e clique por slot disparando `ROULETTE_NUMBER_CLICKED`.
Reproduza a MESMA geometria/ordem dos slots (dados `slotsData`, `createArcPath`, `polar`)
como função pura em `content.js` que gera o SVG string — **sem** `<script>` injetado, sem
innerHTML de fonte externa. O HTML original fica como referência no PR (cole no brief/log).

### slotsData canônico (ordem física — usar EXATAMENTE esta)
top L→R: 24,16,33,1,20,14,31,9,22,18,29,7,28,12,35 · arcR: 3(-90..-30), 26(-30..30), 0(30..90, verde)
bottom R→L: 32,15,19,4,21,2,25,17,34,6,27,13,36,11,30 · arcL: 8(90..135), 23(135..180), 10(180..225), 5(225..270)
Geometria: R_OUT=95, R_IN=50, CY=105, CX_L=95, CX_R=665, SLOT_W=(665-95)/15.

## Decisões de UX (fechadas pelo Diretor — não reabrir)
1. **Posição:** no estado **minimizado**, o pill vira coluna: linha 1 = `[C1] [C2] [C3]` +
   badge 17/21 + gale (formato ÚNICO `minimizedStatusHTML` — NÃO alterar); linha 2 = o
   racetrack. Largura-alvo do racetrack ≈ largura do pill minimizado (~200–240px; pode
   elevar `max-width` do `.minimized .eb-panel` até ~250px se precisar).
2. **O que acende:** TODOS os números cobertos (`sugestao.numeros`, os 17/21) acendem
   amarelo; os 3 centros (`centrosFromSugestao(s)` — fonte ÚNICA, ordem c2,c3,c1) acendem
   MAIS FORTE (stroke branco + glow maior + número visível). Legibilidade dos ACESOS >
   completude: em ~220px, número visível só nos slots acesos (apagados = só cor).
3. **Não-interativo:** `pointer-events: none` no racetrack (guia visual; o clique real é na
   mesa da Evolution — capturar clique aqui atrapalharia). NÃO portar o listener de clique.
4. **Ciclo de vida:** renderiza/acende quando `acao === 'APOSTAR'`; **limpa/esconde** em
   `PULAR`/`AGUARDAR`/reset de sessão (`handleSessionReset`) e quando a sugestão expira.
   Writers: os MESMOS pontos que hoje chamam `minimizedStatusHTML` (toggleMinimize,
   updateOverlay, heartbeat state_sync) — reutilize helper único `renderMiniRacetrack(s)`
   para nunca divergirem (lição das "3 telas" de 05/08).
5. **Toggle do operador:** botão 🎡 pequeno no header minimizado alterna mostrar/esconder;
   persistir em `chrome.storage` junto do `eb_ui_state` (padrão `loadUIState/saveUIState`).
   Default **ON** (guia passivo, sem efeito em aposta — não é comportamento de estratégia,
   logo NÃO exige flag na compose; a flag client-side é o próprio toggle persistido).
6. **Expandido (opcional, só se couber limpo):** mesma roletinha abaixo de `#eb-regiao`,
   um pouco maior (~260px). Se poluir, entregar só no minimizado e registrar no log.

## Âncoras (onde entrar — NÃO faça grep cego)
- `extension/content.js:19-105` — helpers `buildCentroHTML`/`centrosFromSugestao`/
  `minimizedStatusHTML`/`buildForce17HTML` (fonte única dos centros; siga o padrão).
- `extension/content.js:464-507` — `toggleMinimize` (writer 1) · `:541-660` —
  `updateOverlay` (writer 2) · `handleStateSync` ~`:884` (writer 3, heartbeat).
- `extension/content.js:694-760` — `handleNewSession`/`handleSessionReset` (limpeza).
- `extension/overlay.css:275-300` e `:359+` — regras `.minimized` (duas media queries!).
- `extension/manifest.json` — bump `3.10.0` → `3.11.0`.

## Tarefa (passos)
1. Função pura `buildRacetrackSVG()` (uma vez) + `renderMiniRacetrack(sugestao)` que acende
   via classes (`.active`, `.active-center`) — espelho fiel de `RacetrackAPI.highlight`.
2. Inserir o contêiner `#eb-racetrack` no template do overlay (`createOverlay`) — visível
   no minimizado (exceção às regras `display:none` do `.minimized .eb-body`: o racetrack
   vive FORA de `.eb-body` ou ganha regra própria) e limpo por padrão.
3. Ligar os 3 writers + limpeza; botão 🎡 + persistência.
4. CSS: escala responsiva (SVG com viewBox escala sozinho; ajustar strokes/фонts para o
   tamanho mini), respeitar `pointer-events` e as DUAS media queries do minimizado.
5. Validação manual com payload sintético (servidor está FORA — não bloqueia): carregar a
   extensão unpacked no Chrome, simular no console da página
   `updateOverlay({acao:'APOSTAR', regioes:[{center:5,label:'c2'},{center:24,label:'c3'},{center:16,label:'c1'}], numeros:[5,24,16,10,23,8,30,11,36,13,27,6,34,17,25,2,21], force17:{v5_mode:17}})`
   (adapte ao entrypoint real; documente os passos e cole screenshot/descrição no log).
6. `pytest tests/` (suíte Python não pode regredir — mudou só extensão, deve passar).

## Critério de "pronto" (Definition of Done)
- [ ] Minimizado + APOSTAR ⇒ racetrack aparece abaixo dos centros, 17/21 números acesos,
      3 centros em destaque forte, ordem física correta (conferir 0 entre 3/26 e 32).
- [ ] PULAR/AGUARDAR/reset ⇒ racetrack limpa/esconde. Toggle 🎡 persiste após reload.
- [ ] Racetrack não captura cliques (clicar "através" continua funcionando).
- [ ] Os 3 writers produzem o MESMO resultado (helper único; sem divergência).
- [ ] `manifest.version` 3.11.0 + nota de reload no Chrome no log.
- [ ] `pytest tests/` verde (Windows: `--ignore=tests/test_obs_reload.py`).

## Guardrails (inviolável)
- **INV-3**: não tocar em lógica de estratégia/stake — isto é só camada de exibição.
- **Git:** só no worktree/branch da sessão; NUNCA push/checkout/reset/merge em `main`. PR.
- **Produção intocável:** sem SSH/host; a validação é local (extensão unpacked + fixture).
- Mudança cirúrgica dentro dos `locks`; sem segredos; sem comando destrutivo.
- NÃO commitar `graphify-out/`.

## Validação (rode e cole o resultado no Log)
```
pytest tests/ --ignore=tests/test_obs_reload.py   # Windows local
# + passos manuais do item 5 (payload sintético) documentados no Log
```

## Rollback (ISO — sempre documentar)
Toggle 🎡 OFF esconde o racetrack (kill-switch do operador) · `git revert` do PR ·
extensão anterior 3.10.0 continua funcional (mudança é aditiva no overlay).

## Conformidade ISO (marque ANTES de abrir o PR)
- [ ] Aditivo/retro-compatível (payload NÃO muda; overlay degrada limpo sem `numeros`).
- [ ] INV-3 intacto; suíte verde.
- [ ] Novo `except Exception`? (JS não conta; Python não deve mudar) — n/a esperado.
- [ ] Mexeu em `extension/` → bump `manifest.version` + nota de reload no Chrome.
- [ ] ADENDO ISO: arquivo NOVO `docs/iso/adendos/2026-08-16-racetrack-guia-overlay.md`
      (NÃO apendar em `Manutenabilidade_iso.md`).

## Closeout (a ORDEM importa)
1. Validação → colar no `## Log`. 2. ADENDO (arquivo novo). 3. Code-review (subagent) →
corrigir. 4. Append no `## Log`. 5. Commit TUDO no branch da sessão
(`SPR-X5: <resumo>` + trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`).
6. **Lock check pré-PR:** `gh pr list` — colisão em `extension/*` ⇒ serialize.
7. Push + PR título `SPR-X5: ...` + **armar auto-merge** (`gh pr merge --auto --squash <nº>`).
8. Avisar o Diretor: "PR de SPR-X5 aberto".

---

## Log (o EXECUTOR faz append; o DIRETOR lê só o tail)
<!-- AAAA-MM-DD · status · resumo · validação · arquivos tocados -->

2026-08-16 · validado · Racetrack guia implementado e validado (servidor de produção
FORA/502 — validação 100% client-side com payload sintético do passo 5, como previsto).
- **Implementação:** `buildRacetrackSVG()` pura (slotsData/geometria canônicos do brief:
  R_OUT=95, R_IN=50, CY=105, CX_L=95, CX_R=665, SLOT_W=38; sem `<script>`/fonte externa) +
  helper único `renderMiniRacetrack(s)` ligado nos 3 writers (toggleMinimize, updateOverlay,
  handleStateSync c/ assinatura anti-re-render no heartbeat 1s) e na limpeza
  (handleNewSession/handleSessionReset). `#eb-racetrack` é IRMÃO de `.eb-panel` (root já é
  `pointer-events:none` ⇒ clique atravessa DE VERDADE p/ a mesa; dentro do painel seria
  capturado). Toggle 🎡 no header, persistido em `overlayUIState.racetrackEnabled`
  (default ON; legado/ausente ⇒ ON). `.minimized .eb-panel` 200→240px (220px mobile),
  nos DOIS blocos `.minimized` + media query. Número visível SÓ nos acesos (decisão 2).
- **Vista expandida:** NÃO recebeu a roletinha (decisão 6 era opcional; o `#eb-regiao` já
  lista os 17 números em texto — screenshot confirmou que ficaria poluído). Registrado.
- **Validação automatizada (content.js REAL em jsdom + stub chrome.*): 24/24 ✅** —
  37 casas na ordem física canônica (0 entre 26 e 32 ✔), 17 acesos = 14 `.active` +
  3 `.active-center` (5/24/16 via `centrosFromSugestao`, fonte única), formato ÚNICO do
  pill intacto (`minimizedStatusHTML` não alterado), PULAR/AGUARDAR/reset limpam,
  heartbeat não diverge, toggle OFF persiste após reload (ON ao religar), degradação
  limpa sem `numeros` (só centros) e sem nada (esconde).
- **Screenshots headless (Edge --headless=new, harness com payload sintético):**
  APOSTAR minimizado (racetrack abaixo de `[5] [24] [16] ⑰ G1 0/0`, arco contíguo de 17
  aceso, centros destacados), PULAR (some), toggle OFF (some, botão dimmed), expandido
  (sem racetrack, layout intacto), e prova de click-through via `elementFromPoint` no
  centro do racetrack aceso ⇒ `hit=click-probe · clickthrough=OK`.
- **Suítes:** `pytest tests/ --ignore=tests/test_obs_reload.py` ⇒ **1225 passed,
  14 skipped, 1 xfailed** (Python intocado) · `node --test tests/js/*.test.js` ⇒ 53/53 ✅
  · `node --check content.js` OK · manifest.json parse OK.
- **Manifest:** 3.10.0 → **3.11.0**. ⚠️ Reload obrigatório da extensão unpacked em
  `chrome://extensions` para o Chrome aplicar o content script novo.
- **Arquivos:** `extension/content.js`, `extension/overlay.css`, `extension/manifest.json`,
  `docs/iso/adendos/2026-08-16-racetrack-guia-overlay.md` (novo) + índice do README.
- **Referência doada pelo operador:** HTML standalone (racetrack 760×210, RacetrackAPI
  .highlight/.clear, `.active` #ffe600, clique por slot) — geometria/ordem reproduzidas
  como função pura; listener de clique intencionalmente NÃO portado (decisão 3).

2026-08-16 · refinado+revisado · Auditoria SPR-U1 (Diretor) incorporada + code-review.
- **Code-review (subagent):** 1 achado Médio — a regra mobile de 220px do minimizado era
  MORTA (bloco `.minimized` duplicado tardio vencia por ordem de fonte; media query não
  soma especificidade). Corrigido pelo item 2 da auditoria (abaixo). Demais checagens do
  review: geometria/ordem executadas e conferidas (37 casas, 18R/18B/1G, 0 entre 26 e 32),
  sem injeção via payload (numeros/centros só entram em `classList`/`dataset`), click-through
  estrutural OK, `minimizedStatusHTML`/estratégia/stake intocados, manifest OK.
- **Auditoria SPR-U1 — 4 refinamentos aplicados:** (1) rótulo numérico SÓ nos 3 centros
  (acesos comuns = amarelo puro; CSS `.active .eb-rt-num` removido); (2) blocos `.minimized`
  duplicados CONSOLIDADOS em bloco único ANTES da media query mobile ⇒ override 220px
  passa a valer (sem mudança visual desktop); (3) OV-01: `showConnectionStatus(false)` ⇒
  `renderMiniRacetrack(null)` — racetrack NUNCA fica aceso com sugestão velha de servidor
  morto; reconexão só reacende no próximo updateOverlay/state_sync (estado de erro completo
  fica p/ SPR-UX-CONN); (4) clamp do drag nos 2 eixos no `setupDrag` (pill ~2× mais alto
  não sai mais do viewport).
- **Re-validação:** jsdom **28/28 ✅** (nova cena 7: desconexão limpa, reconexão não
  reacende sozinha, novo APOSTAR reacende) · screenshots: APOSTAR v2 (número só nos
  centros 5/24/16), mobile 375px (pill 220px vivo) · `node --check` OK ·
  `pytest tests/ --ignore=tests/test_obs_reload.py` ⇒ **1225 passed, 14 skipped,
  1 xfailed** (re-run pós-refinamentos).
- ⚠️ Nota de reload: extensão unpacked exige Reload em `chrome://extensions` (v3.11.0).


